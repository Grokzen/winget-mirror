.PHONY: help init sync_repo sync refresh_synced validate purge purge_all_packages search clean full

TEST_DIR = test-mirror

help:
	@echo "Winget Mirror Test Targets:"
	@echo "  init           - Create test directory and initialize mirror"
	@echo "  sync-repo      - Sync the git repository (requires init first)"
	@echo "  sync           - Sync Spotify package (requires sync-repo first)"
	@echo "  refresh-synced - Refresh all synced packages to latest versions"
	@echo "  validate       - Validate hashes of downloaded files"
	@echo "  purge          - Purge packages by publisher (requires PUBLISHER=...)"
	@echo "  purge-all      - Purge all downloaded packages"
	@echo "  search         - Search packages by publisher (requires PUBLISHER=...)"
	@echo "  clean          - Remove test directory"
	@echo "  full           - Run complete test cycle (init → sync-repo → sync → validate → clean)"

init:
	mkdir -p $(TEST_DIR)
	invoke init --path=$(TEST_DIR)

sync_repo:
	cd $(TEST_DIR) && invoke -f ../tasks.py sync-repo

sync:
	cd $(TEST_DIR) && invoke -f ../tasks.py sync Spotify/Spotify

refresh_synced:
	cd $(TEST_DIR) && invoke -f ../tasks.py refresh-synced

validate:
	cd $(TEST_DIR) && invoke -f ../tasks.py validate-hash

purge:
	cd $(TEST_DIR) && invoke -f ../tasks.py purge-package $(PUBLISHER)

purge_all_packages:
	cd $(TEST_DIR) && invoke -f ../tasks.py purge-all-packages

search:
	cd $(TEST_DIR) && invoke -f ../tasks.py search $(PUBLISHER)

clean:
	rm -rf $(TEST_DIR)

full: init sync_repo sync validate clean
