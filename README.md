# Winget Mirror Tool

A Python-based tool for mirroring and downloading Microsoft Winget packages from the official winget-pkgs repository. This tool allows you to create a local mirror of package installers, validate their integrity, and manage downloads efficiently.

## Features

- **Sparse Git Checkout**: Only downloads the `manifests/` directory from the winget-pkgs repository, reducing clone size from ~1GB to ~100MB.
- **Package Downloading**: Download the latest versions of packages matching publisher filters.
- **Hash Validation**: Verify SHA256 integrity of downloaded files.
- **State Management**: Tracks downloaded packages and their metadata.
- **CLI Interface**: Uses Invoke for task-based command execution.
- **Flexible Filtering**: Search and manage packages by publisher or package name.

## Requirements

- **Python**: 3.11 or higher
- **Git**: For repository operations
- **Dependencies**: Listed in `requirements.txt`

## Installation

1. **Clone or download the repository**:
   ```
   git clone <repository-url>
   cd winget-mirror
   ```

2. **Install Python dependencies**:
   ```
   pip install -r requirements.txt
   ```

3. **Verify Python version**:
   ```
   python --version  # Should be 3.11+
   ```

## Quick Start

1. **Initialize a new mirror**:
   ```
   invoke init --path="/path/to/your/mirror"
   ```
   This creates the directory structure, `config.json`, and `state.json`.

2. **Navigate to the mirror directory**:
   ```
   cd /path/to/your/mirror
   ```

3. **Sync the repository**:
   ```
   invoke sync-repo
   ```
   Downloads package manifests using sparse checkout.

4. **Download packages**:
   ```
   invoke sync Microsoft
   ```
   Downloads the latest Microsoft packages.

5. **Validate downloads**:
   ```
   invoke validate-hash
   ```

## Usage

All tasks are run using Invoke. Invoke automatically finds `tasks.py` in the current directory or parent directories.

### General Syntax
```
invoke <task-name> [arguments]
```

### Available Tasks

- **`init --path=<path>`**: Initialize a new mirror at the specified path. Creates config and state files.
- **`sync-repo`**: Sync the winget-pkgs git repository to the configured revision using sparse checkout.
- **`sync <publisher>[/<package>]`**: Download the latest version of packages matching the filter.
- **`refresh-synced`**: Update all previously downloaded packages to their latest versions.
- **`search <publisher>`**: List packages matching the publisher filter with download status.
- **`validate-hash [--output=json]`**: Validate SHA256 hashes of downloaded files.
- **`purge-package <publisher>`**: Remove downloaded packages matching the publisher filter.
- **`purge-all-packages`**: Remove all downloaded packages (with confirmation).
- **`patch-repo --server-url=<url> --output-dir=<dir>`**: Create patched manifests with corrected InstallerURL paths.

## Configuration

- **`config.json`**: Contains repository settings
  ```json
  {
    "repo_url": "https://github.com/microsoft/winget-pkgs",
    "revision": "master",
    "mirror_dir": "mirror",
    "server_url": null
  }
  ```
- **`state.json`**: Tracks downloaded packages and sync state
  ```json
  {
    "path": "/path/to/mirror",
    "last_sync": "2025-11-09T15:30:00",
    "downloads": {
      "Microsoft.PowerShell": {
        "version": "7.4.0",
        "timestamp": "2025-11-09T15:30:00",
        "files": {
          "PowerShell-7.4.0-win-x64.msi": "sha256-hash"
        }
      }
    }
  }
  ```

## Examples

### Initialize and Setup
```bash
# Initialize mirror
invoke init --path=./my-mirror

# Change to mirror directory
cd my-mirror

# Sync repository (first time may take a few minutes due to sparse checkout)
invoke sync-repo
```

### Download Packages
```bash
# Download all Microsoft packages
invoke sync Microsoft

# Download specific package
invoke sync Spotify/Spotify

# Download all Spotify packages
invoke sync Spotify
```

### Search and Manage
```bash
# Search for Microsoft packages
invoke search Microsoft

# Validate all downloads
invoke validate-hash

# Update all downloaded packages
invoke refresh-synced

# Remove Microsoft packages
invoke purge-package Microsoft

# Remove all packages
invoke purge-all-packages
```

### JSON Output
```bash
# Get validation results as JSON
invoke validate-hash --output=json
```

### Patch Manifests
```bash
# Create patched manifests for self-hosted mirror
invoke patch-repo --server-url="https://mirror.example.com" --output-dir="./patched-manifests"
```

## Manifest Patching

The `patch-repo` command is used to create modified winget manifest files that point to your local mirror instead of the original download URLs. This enables you to host your own winget package repository with custom installer URLs.

### Purpose

Winget packages contain `InstallerUrl` fields that point to the original download locations (e.g., GitHub releases, vendor websites). When creating a local mirror, you need to update these URLs to point to your mirrored files so that winget clients can download from your server instead of the original sources.

### How to Run

Run the command from your mirror directory (where `config.json` and `state.json` are located):

```bash
invoke patch-repo --server-url="https://your-mirror-domain.com" --output-dir="./patched-manifests"
```

### Arguments

- **`--server-url`**: The base URL of your mirror server where the downloads folder will be hosted. Must be a valid HTTP or HTTPS URL (e.g., `https://mirror.example.com` or `https://winget.mydomain.com`). This URL will be prepended to the download paths.
- **`--output-dir`**: Directory where the patched manifest files will be created. The command will create this directory if it doesn't exist. The folder structure will mirror the original manifests directory.

### What It Does

1. **Reads downloaded packages**: Scans `state.json` for all packages that have been downloaded and verified.
2. **Copies manifest structure**: Recreates the exact same folder hierarchy as the original `mirror/manifests/` directory.
3. **Patches URLs**: For each installer manifest (`.installer.yaml` files), replaces `InstallerUrl` fields with new URLs pointing to your mirror.
4. **Preserves metadata**: All other manifest data (version info, hashes, dependencies, etc.) remains unchanged.

### URL Transformation

Original URL in manifest:
```
https://github.com/vendor/package/releases/download/v1.0/installer.exe
```

Becomes:
```
https://your-mirror-domain.com/downloads/Vendor/Package/1.0/installer.exe
```

The path structure matches your local `downloads/` folder:
```
downloads/
└── Vendor/
    └── Package/
        └── 1.0/
            └── installer.exe
```

### NGINX Static File Hosting

To serve the patched manifests and downloads via NGINX:

1. **Host the patched manifests**: Copy the contents of your `--output-dir` to a web-accessible directory on your NGINX server.

2. **Host the downloads folder**: Ensure your `downloads/` folder is also web-accessible at the same domain.

3. **NGINX Configuration Example**:
   ```nginx
   server {
       listen 80;
       server_name your-mirror-domain.com;

       # Serve patched manifests
       location /manifests/ {
           alias /path/to/patched-manifests/manifests/;
           autoindex on;  # Optional: enable directory listing
       }

       # Serve downloads
       location /downloads/ {
           alias /path/to/mirror/downloads/;
           autoindex off;  # Disable directory listing for security
       }

       # Optional: Add caching headers
       location ~* \.(exe|msi|zip)$ {
           add_header Cache-Control "public, max-age=31536000";  # 1 year
       }
   }
   ```

4. **Winget Client Configuration**: Configure winget to use your mirror by setting the source URL to point to your manifests directory:
   ```bash
   winget source add --name "My Mirror" --arg "https://your-mirror-domain.com/manifests"
   ```

### Requirements

- Run `invoke sync-repo` and `invoke sync` first to download packages
- Valid HTTP/HTTPS server URL
- Sufficient disk space for copied manifests
- NGINX or compatible web server for hosting

### Output Usage

The patched manifests in `--output-dir` are ready to be served by your web server. They can be used to:

- Create a private winget package source
- Provide offline package access for air-gapped networks
- Reduce bandwidth costs by serving from local infrastructure
- Ensure package availability even if original sources go down

### Example Workflow

```bash
# 1. Initialize and sync packages
invoke init --path=./my-mirror
cd my-mirror
invoke sync-repo
invoke sync Microsoft
invoke sync Notepad++

# 2. Patch manifests for your domain
invoke patch-repo --server-url="https://winget.company.com" --output-dir="./patched"

# 3. Deploy to NGINX
# Copy ./patched/manifests/ to /var/www/winget/manifests/
# Ensure ./downloads/ is accessible at /var/www/winget/downloads/

# 4. Configure winget clients
winget source add --name "Company Mirror" --arg "https://winget.company.com/manifests"
```

## Testing

### Local Testing

Use the provided Makefile for basic testing or run the full test script from anywhere:

```bash
# Using Makefile (from project root)
make full

# Using full test script (from project root - creates and cleans up test directory automatically)
./scripts/full_test.sh
```

**Note**: The full test script automatically creates a `test-local` directory, runs all tests using Notepad++ as the example package, and cleans up afterwards.

### CI/CD

This repository includes GitHub Actions CI that runs on every push and pull request:

- **Trigger**: Push to any branch, pull requests
- **Environment**: Ubuntu latest with Python 3.11, 3.12, 3.13
- **Tests**: Full sequence using Notepad++ package including manifest patching
- **Workflow**: `.github/workflows/ci.yml`

The CI automatically runs the complete test suite, which handles test directory creation, execution, and cleanup.

## Directory Structure

After initialization:
```
your-mirror/
├── config.json          # Configuration file
├── state.json           # State and download tracking
├── mirror/              # Git repository (sparse checkout)
│   └── manifests/       # Package manifests
└── downloads/           # Downloaded installers
    └── Publisher/
        └── Package/
            └── version/
                └── installer.exe
```

## Notes

- **Sparse Checkout**: The tool uses Git sparse checkout to only download the `manifests/` directory, significantly reducing storage and bandwidth requirements.
- **Error Handling**: Tasks will propagate errors; use try/catch if needed in scripts.
- **Large Downloads**: Initial repository sync may take time depending on internet connection.
- **Validation**: Always run `validate-hash` after downloads to ensure file integrity.
- **Publisher Filtering**: Filters are case-insensitive and match from the start of publisher names.

## Troubleshooting

- **"No idea what 'task' is!"**: Ensure `tasks.py` is in the current or parent directories.
- **Git errors**: Ensure Git is installed and accessible.
- **Permission errors**: Run with appropriate permissions for file operations.
- **Validation failures**: Check internet connection and re-run sync if needed.

## Contributing

1. Follow Python 3.11+ best practices
2. Use `ruff` for linting
3. Add tests for new features
4. Update documentation

## Development and Agent Tooling

This repository is an experiment in **100% Vibe Coding** - all code is generated, maintained, and evolved exclusively through Agent tooling. No manual coding is permitted.

### Experimental Setup

- **IDE**: VSCode Insider program (required for Agent integration)
- **AI Model**: Grok Code Fast 1 (exclusively)
- **Approach**: Zero manual intervention - all development is Agent-driven

### 100% Vibe Coding Policy

This project serves as a proof-of-concept for fully automated software development:
- **No Manual Code**: All code changes must be produced by the Agent
- **Rejection Criteria**: Manual submissions or changes from other AI models will be rejected
- **Quality Control**: The Agent maintains consistent coding standards and patterns
- **Evolution**: The codebase grows and adapts through iterative Agent interactions

### Submission Guidelines

To participate in this experiment:
- Use only VSCode Insider with Grok Code Fast 1 for any interactions
- Allow the Agent to handle all code modifications
- Manual pull requests will be declined to preserve the purity of the experiment
- Report issues or request features through Agent-mediated channels

This repository demonstrates the potential of fully automated development workflows while maintaining high code quality and consistency.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
