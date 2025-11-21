import json
import yaml
import requests
import hashlib
import datetime
import sys
import os
from pathlib import Path
from invoke import task

# Add current directory to path for imports
sys.path.insert(0, os.path.join(os.getcwd(), '..'))

from winget_mirror_core import (
    GitProgress, parse_version_safe, load_config_and_state,
    get_matching_publishers, process_package,
    WingetMirrorManager, WingetPackage
)

# Check Python version
if sys.version_info < (3, 11):
    print("Error: This tool requires Python 3.11 or higher.")
    print(f"Current version: {sys.version}")
    sys.exit(1)

@task
def init(c, path):
    """Initialize a new mirror usage at the specified path.

    Creates the project directory, config.json, and state.json if they don't exist.
    If already initialized at the path, does nothing.

    Args:
        path: Absolute or relative path to the project directory.

    Example:
        invoke init --path="/path/to/mirror"
    """
    WingetMirrorManager.initialize(path)

@task
def sync(c, publisher):
    """Download the latest version of packages matching the publisher/package filter from the already synced repository.

    Downloads the latest version of packages matching the publisher/package filter.
    The repository must be synced first using 'invoke sync-repo'.

    Args:
        publisher: Publisher filter, optionally with package filter (e.g., 'Microsoft' or 'Splunk/ACS').

    Example:
        invoke sync Microsoft
        invoke sync Splunk/ACS
    """
    manager = WingetMirrorManager()
    if manager.repo is None:
        print("Repository not found. Run 'invoke sync-repo' first.")
        return

    processed_packages = set()

    # Parse publisher/package filter
    if "/" in publisher:
        pub_filter, pkg_filter = publisher.split("/", 1)
    else:
        pub_filter = publisher
        pkg_filter = None

    publishers = manager.get_matching_publishers(pub_filter)

    manifests_dir = manager.mirror_dir / 'manifests'

    for pub in publishers:
        first_letter = pub[0].lower()
        publisher_path = manifests_dir / first_letter / pub
        for package_path in publisher_path.iterdir():
            if not package_path.is_dir():
                continue

            # Filter by package name if specified
            if pkg_filter and not package_path.name.lower().startswith(pkg_filter.lower()):
                continue

            package_id = f'{pub}.{package_path.name}'
            pkg = manager.get_package(package_id)
            if pkg.download():
                processed_packages.add(package_id)

    # Update state
    manager.state['last_sync'] = datetime.datetime.now().isoformat()
    manager.save_state()

    if publisher:
        print(f"Downloaded {len(processed_packages)} packages matching '{publisher}'")

@task
def refresh_synced(c):
    """Refresh all synced packages to their latest versions.

    Checks each package in state.json for newer versions in the repository
    and downloads/updates them if available. The repository must be synced first.

    Example:
        invoke refresh-synced
    """
    manager = WingetMirrorManager()
    if manager.repo is None:
        print("Repository not found. Run 'invoke sync-repo' first.")
        return

    updated_packages = set()

    for package_id, package_info in manager.state.get('downloads', {}).items():
        current_version = package_info['version']

        pkg = manager.get_package(package_id)
        latest_version = pkg.get_latest_version()

        if latest_version and parse_version_safe(latest_version) > parse_version_safe(current_version):
            print(f"Updating {package_id} from {current_version} to {latest_version}")
            if pkg.download():
                updated_packages.add(package_id)
        else:
            print(f"{package_id} is up to date")

    # Update state
    manager.state['last_sync'] = datetime.datetime.now().isoformat()
    manager.save_state()

    print(f"Refreshed {len(updated_packages)} packages")

@task
def sync_repo(c):
    """Sync the winget-pkgs git repository to the configured revision.

    Clones the repository if it doesn't exist, pulls latest changes if it does,
    and checks out the configured revision.

    This task must be run before 'sync' to ensure the repository is up to date.

    Example:
        invoke sync-repo
    """
    manager = WingetMirrorManager()
    manager.sync_repo()

@task
def validate_hash(c, output=None):
    """Validate SHA256 hashes of all downloaded files against stored checksums.

    Checks that all expected files exist and their hashes match the recorded values.
    Exits with error code 1 if any validation fails.

    Args:
        output: Optional output format. Use 'json' for JSON output, otherwise human-readable text.

    Examples:
        invoke validate-hash
        invoke validate-hash --output=json
    """
    manager = WingetMirrorManager()

    if 'downloads' not in manager.state or not manager.state['downloads']:
        if output == 'json':
            print(json.dumps({"all_valid": True, "packages": {}}, indent=4))
        else:
            print("No downloaded packages found in state.json")
        return

    results = {
        "all_valid": True,
        "packages": {}
    }

    for package_id in manager.state['downloads']:
        pkg = manager.get_package(package_id)
        pkg_results = pkg.validate_hashes()
        results["packages"][package_id] = pkg_results
        if not pkg_results["valid"]:
            results["all_valid"] = False

    if output == 'json':
        print(json.dumps(results, indent=4))
    else:
        # Print human-readable output
        for package_id, pkg_data in results["packages"].items():
            if not pkg_data["files"] and not pkg_data["missing_files"]:
                print(f"Warning: No files recorded for {package_id}")
                continue

            if not pkg_data["valid"] and not pkg_data["files"] and pkg_data["missing_files"]:
                publisher, package = package_id.split('.', 1)
                download_dir = manager.downloads_dir / publisher / package / manager.state['downloads'][package_id]['version']
                print(f"Error: Download directory missing for {package_id}: {download_dir}")
                continue

            for filename, file_data in pkg_data["files"].items():
                status = file_data["status"]
                print(f"Validating {package_id}/{filename}: {status}")
                print(f"  Tracked hash: {file_data['expected']}")
                print(f"  Computed hash: {file_data['computed']}")

            for missing in pkg_data["missing_files"]:
                print(f"Error: Expected file missing for {package_id}: {missing}")

            for unexpected in pkg_data["unexpected_files"]:
                print(f"Warning: Unexpected files in {package_id}: {unexpected}")

        if results["all_valid"]:
            print("All downloaded files validated successfully!")
        else:
            print("Validation failed! Some files are missing or corrupted.")
            sys.exit(1)

@task
def purge_package(c, publisher):
    """Purge downloaded packages matching the publisher filter.

    Removes downloaded files and state entries for packages matching the publisher.
    Asks for confirmation before proceeding.

    Args:
        publisher: Publisher filter (e.g., 'Microsoft', 'Spotify')

    Example:
        invoke purge-package Microsoft
    """
    manager = WingetMirrorManager()

    if 'downloads' not in manager.state or not manager.state['downloads']:
        print("No downloaded packages found in state.json")
        return

    # Find matching packages
    matching_packages = [
        package_id for package_id in manager.state['downloads']
        if package_id.split('.', 1)[0].lower().startswith(publisher.lower())
    ]

    if not matching_packages:
        print(f"No packages found matching publisher '{publisher}'")
        return

    print(f"Found {len(matching_packages)} package(s) matching '{publisher}':")
    for pkg in matching_packages:
        print(f"  - {pkg}")

    # Ask for confirmation
    confirm = input("Are you sure you want to purge these packages? (yes/no) [no]: ").strip()
    if not confirm:
        confirm = "no"
    if confirm.lower() not in ('yes', 'y'):
        print("Purge cancelled.")
        return

    # Purge
    purged_count = 0
    for package_id in matching_packages:
        pkg = manager.get_package(package_id)
        if pkg.purge():
            purged_count += 1

    print(f"Successfully purged {purged_count} package(s)")

@task
def purge_all_packages(c):
    """Purge all downloaded packages.

    Removes downloaded files and state entries for all packages.
    Asks for confirmation before proceeding.

    Example:
        invoke purge-all-packages
    """
    manager = WingetMirrorManager()

    downloaded_packages = manager.state.get('downloads', {})
    if not downloaded_packages:
        print("No downloaded packages found in state.json")
        return

    package_ids = list(downloaded_packages.keys())
    print(f"The following {len(package_ids)} package(s) will be purged:")
    for pkg_id in package_ids:
        print(f"  - {pkg_id}")

    # Ask for confirmation
    confirm = input("Are you sure you want to purge all packages? (yes/no) [no]: ").strip()
    if not confirm:
        confirm = "no"
    if confirm.lower() not in ('yes', 'y'):
        print("Purge cancelled.")
        return

    # Purge all
    purged_count = 0
    for package_id in package_ids:
        pkg = manager.get_package(package_id)
        if pkg.purge():
            purged_count += 1

    print(f"Successfully purged {purged_count} package(s)")

@task
def search(c, publisher):
    """Search for packages matching the publisher filter.

    Lists all packages from the repository matching the publisher filter,
    along with their download status.

    Args:
        publisher: Publisher filter (e.g., 'Microsoft', 'Spotify')

    Example:
        invoke search Microsoft
    """
    manager = WingetMirrorManager()
    if not manager.mirror_dir.exists():
        print("Repository not found. Run 'invoke sync-repo' first.")
        return

    downloaded_packages = manager.state.get('downloads', {})

    # Parse publisher filter
    pub_filter = publisher

    publishers = manager.get_matching_publishers(pub_filter)
    manifests_dir = manager.mirror_dir / 'manifests'
    first_letter = pub_filter[0].lower()

    found_packages = []

    for pub in publishers:
        publisher_path = manifests_dir / first_letter / pub
        for package_path in publisher_path.iterdir():
            if not package_path.is_dir():
                continue

            package_id = f'{pub}.{package_path.name}'
            found_packages.append(package_id)

    if not found_packages:
        print(f"No packages found matching publisher '{publisher}'")
        return

    # Collect package data
    package_data = []
    max_pkg_len = len("Package")
    max_status_len = len("Status")

    for package_id in sorted(found_packages):
        pub, pkg = package_id.split('.', 1)

        # Check status
        if package_id in downloaded_packages:
            package_info = downloaded_packages[package_id]
            files = package_info.get('files', {})
            version = package_info.get('version', 'unknown')
            timestamp = package_info.get('timestamp', 'unknown')
            if timestamp != 'unknown' and timestamp != '-':
                # Format timestamp to be more readable
                try:
                    dt = datetime.datetime.fromisoformat(timestamp)
                    timestamp = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    pass
            if files:
                # Check if files actually exist
                download_dir = manager.downloads_dir / pub / pkg / version
                if download_dir.exists():
                    actual_files = list(download_dir.glob('*'))
                    if actual_files:
                        status = "Downloaded"
                    else:
                        status = "Downloaded (empty)"
                        version = "-"
                        timestamp = "-"
                else:
                    status = "Downloaded (missing)"
                    version = "-"
                    timestamp = "-"
            else:
                status = "Recorded"
                version = version
                timestamp = "-"
        else:
            status = "Not downloaded"
            version = "-"
            timestamp = "-"

        package_data.append((package_id, status, version, timestamp))
        max_pkg_len = max(max_pkg_len, len(package_id))
        max_status_len = max(max_status_len, len(status))

    # Print table
    print(f"Found {len(found_packages)} package(s) matching '{publisher}':")
    header = f"{'Package':<{max_pkg_len}}  {'Status':<{max_status_len}}  {'Version':<10}  {'Timestamp':<17}"
    print(header)
    print("-" * len(header))

    for pkg_id, status, ver, ts in package_data:
        print(f"{pkg_id:<{max_pkg_len}}  {status:<{max_status_len}}  {ver:<10}  {ts:<17}")

