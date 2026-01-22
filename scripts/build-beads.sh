#!/usr/bin/env bash
#
# Build and bundle beads binary for quinnai
#
# This script:
# 1. Downloads or builds the beads binary
# 2. Places it in cli/bin/ for bundling with the Python package
#
# Usage:
#   ./scripts/build-beads.sh [--platform darwin|linux] [--arch amd64|arm64]
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CLI_BIN_DIR="$PROJECT_ROOT/cli/bin"

# Default to current platform
PLATFORM="${PLATFORM:-$(uname -s | tr '[:upper:]' '[:lower:]')}"
ARCH="${ARCH:-$(uname -m)}"

# Normalize architecture names
case "$ARCH" in
    x86_64) ARCH="amd64" ;;
    aarch64) ARCH="arm64" ;;
esac

# Beads version to bundle
BEADS_VERSION="${BEADS_VERSION:-0.46.0}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --platform)
            PLATFORM="$2"
            shift 2
            ;;
        --arch)
            ARCH="$2"
            shift 2
            ;;
        --version)
            BEADS_VERSION="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "Building beads for $PLATFORM/$ARCH (version $BEADS_VERSION)"

# Create bin directory
mkdir -p "$CLI_BIN_DIR"

# Binary name varies by platform
if [[ "$PLATFORM" == "windows" ]]; then
    BINARY_NAME="bd.exe"
else
    BINARY_NAME="bd"
fi

OUTPUT_PATH="$CLI_BIN_DIR/$BINARY_NAME"

# Check if we have a local beads-org source to build from
BEADS_ORG_DIR="$PROJECT_ROOT/cli/beads-org"

if [[ -d "$BEADS_ORG_DIR" ]]; then
    echo "Building from local beads-org source..."

    # Check for Go
    if ! command -v go &> /dev/null; then
        echo "Error: Go is required to build beads-org"
        echo "Install Go from https://golang.org/dl/"
        exit 1
    fi

    cd "$BEADS_ORG_DIR"

    # Build for target platform
    GOOS="$PLATFORM" GOARCH="$ARCH" go build -o "$OUTPUT_PATH" ./cmd/bd

    echo "Built beads from source: $OUTPUT_PATH"
else
    # Download pre-built binary from releases
    echo "Downloading pre-built beads binary..."

    # Construct download URL (assumes GitHub releases format)
    # Format: beads-{version}-{platform}-{arch}.tar.gz
    RELEASE_URL="https://github.com/beads-org/beads/releases/download/v${BEADS_VERSION}"

    case "$PLATFORM" in
        darwin)
            ARCHIVE_NAME="beads-${BEADS_VERSION}-darwin-${ARCH}.tar.gz"
            ;;
        linux)
            ARCHIVE_NAME="beads-${BEADS_VERSION}-linux-${ARCH}.tar.gz"
            ;;
        windows)
            ARCHIVE_NAME="beads-${BEADS_VERSION}-windows-${ARCH}.zip"
            ;;
        *)
            echo "Error: Unsupported platform: $PLATFORM"
            exit 1
            ;;
    esac

    DOWNLOAD_URL="${RELEASE_URL}/${ARCHIVE_NAME}"
    TEMP_DIR=$(mktemp -d)

    echo "Downloading from: $DOWNLOAD_URL"

    if command -v curl &> /dev/null; then
        curl -fsSL "$DOWNLOAD_URL" -o "$TEMP_DIR/$ARCHIVE_NAME" || {
            echo "Download failed. Falling back to local bd installation..."

            # Fall back to copying the locally installed bd
            LOCAL_BD=$(which bd 2>/dev/null || true)
            if [[ -n "$LOCAL_BD" && -f "$LOCAL_BD" ]]; then
                cp "$LOCAL_BD" "$OUTPUT_PATH"
                chmod +x "$OUTPUT_PATH"
                echo "Copied local bd to: $OUTPUT_PATH"
                rm -rf "$TEMP_DIR"
                exit 0
            else
                echo "Error: No local bd installation found"
                rm -rf "$TEMP_DIR"
                exit 1
            fi
        }
    else
        echo "Error: curl is required to download beads"
        rm -rf "$TEMP_DIR"
        exit 1
    fi

    # Extract archive
    cd "$TEMP_DIR"
    if [[ "$ARCHIVE_NAME" == *.tar.gz ]]; then
        tar -xzf "$ARCHIVE_NAME"
    else
        unzip -q "$ARCHIVE_NAME"
    fi

    # Find and copy the binary
    find . -name "bd" -o -name "bd.exe" | head -1 | xargs -I {} cp {} "$OUTPUT_PATH"

    # Cleanup
    rm -rf "$TEMP_DIR"

    echo "Downloaded beads to: $OUTPUT_PATH"
fi

# Make executable
chmod +x "$OUTPUT_PATH"

# Verify
if [[ -f "$OUTPUT_PATH" ]]; then
    echo ""
    echo "Success! Beads binary ready at: $OUTPUT_PATH"
    "$OUTPUT_PATH" --version 2>/dev/null || echo "(version check skipped)"
else
    echo "Error: Binary not found at $OUTPUT_PATH"
    exit 1
fi
