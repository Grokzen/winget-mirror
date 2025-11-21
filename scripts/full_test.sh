#!/bin/bash
# Full test script for local testing
# This script creates its own test directory, runs all tests, and cleans up

set -e  # Exit on any error

TEST_DIR=test-local

# Security check: Ensure TEST_DIR is a safe relative path within current directory
if [[ "$TEST_DIR" == *".."* ]] || [[ "$TEST_DIR" == /* ]] || [[ "$TEST_DIR" == */* ]]; then
    echo "Error: TEST_DIR must be a simple directory name within the current folder"
    echo "Invalid TEST_DIR: $TEST_DIR"
    exit 1
fi

echo "Creating test directory: $TEST_DIR"
mkdir -p $TEST_DIR

echo "Initializing mirror at $TEST_DIR"
invoke init --path=$TEST_DIR

echo "Entering test directory"
cd $TEST_DIR

echo "Starting full test sequence..."

echo "Step 1: Sync repo"
invoke sync-repo

echo "Step 2: Search packages"
invoke search Notepad++

echo "Step 3: Sync package"
invoke sync Notepad++

echo "Step 4: Validate hash"
invoke validate-hash

echo "Step 5: Refresh synced"
invoke refresh-synced

echo "Step 6: Purge package"
invoke purge-package Notepad++

echo "Full test sequence completed successfully!"

echo "Cleaning up test directory"
cd ..
rm -rf $TEST_DIR

echo "Test cleanup complete."