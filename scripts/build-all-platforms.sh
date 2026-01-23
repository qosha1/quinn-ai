#!/usr/bin/env bash
#
# Build beads binaries for all supported platforms
#
# This script builds beads for cross-platform distribution.
# Requires Go for cross-compilation or downloads pre-built binaries.
#
# Usage:
#   ./scripts/build-all-platforms.sh [--source-dir PATH]
#
# Outputs:
#   cli/bin/darwin-arm64/bd
#   cli/bin/darwin-amd64/bd
#   cli/bin/linux-amd64/bd
#   cli/bin/linux-arm64/bd

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
CLI_BIN_DIR="$PROJECT_ROOT/cli/bin"

# Beads source directory (optional - for building from source)
BEADS_SOURCE_DIR="${BEADS_SOURCE_DIR:-}"

# Target platforms
PLATFORMS=(
    "darwin:arm64"
    "darwin:amd64"
    "linux:amd64"
    "linux:arm64"
)

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --source-dir)
            BEADS_SOURCE_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [--source-dir PATH]"
            echo ""
            echo "Options:"
            echo "  --source-dir PATH  Path to beads Go source for cross-compilation"
            echo ""
            echo "If no source dir is provided, uses local bd installation."
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

echo "========================================"
echo "Building beads for all platforms"
echo "========================================"

# Check if we have Go for cross-compilation
HAS_GO=false
if command -v go &> /dev/null; then
    HAS_GO=true
    echo "Go found: $(go version)"
fi

# Check for beads source
HAS_SOURCE=false
if [[ -n "$BEADS_SOURCE_DIR" && -d "$BEADS_SOURCE_DIR" ]]; then
    HAS_SOURCE=true
    echo "Beads source: $BEADS_SOURCE_DIR"
elif [[ -d "$PROJECT_ROOT/cli/beads-org" ]]; then
    BEADS_SOURCE_DIR="$PROJECT_ROOT/cli/beads-org"
    HAS_SOURCE=true
    echo "Beads source: $BEADS_SOURCE_DIR (submodule)"
fi

# Check for local bd installation
LOCAL_BD=""
if command -v bd &> /dev/null; then
    LOCAL_BD="$(which bd)"
    echo "Local bd: $LOCAL_BD"
fi

# Determine build strategy
if [[ "$HAS_SOURCE" == "true" && "$HAS_GO" == "true" ]]; then
    BUILD_STRATEGY="source"
    echo "Strategy: Cross-compile from source"
elif [[ -n "$LOCAL_BD" ]]; then
    BUILD_STRATEGY="local"
    echo "Strategy: Copy local bd (current platform only)"
else
    BUILD_STRATEGY="download"
    echo "Strategy: Download pre-built binaries"
fi

echo ""

# Build function for source compilation
build_from_source() {
    local os="$1"
    local arch="$2"
    local output_dir="$CLI_BIN_DIR/${os}-${arch}"
    local output_file="$output_dir/bd"

    mkdir -p "$output_dir"

    echo "Building for ${os}/${arch}..."

    cd "$BEADS_SOURCE_DIR"
    GOOS="$os" GOARCH="$arch" CGO_ENABLED=0 go build -ldflags="-s -w" -o "$output_file" ./cmd/bd

    chmod +x "$output_file"
    echo "  -> $output_file ($(du -h "$output_file" | cut -f1))"
}

# Copy local installation
copy_local() {
    local current_os current_arch
    current_os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    current_arch="$(uname -m)"

    # Normalize arch
    case "$current_arch" in
        x86_64) current_arch="amd64" ;;
        aarch64) current_arch="arm64" ;;
    esac

    local output_dir="$CLI_BIN_DIR/${current_os}-${current_arch}"
    local output_file="$output_dir/bd"

    mkdir -p "$output_dir"
    cp "$LOCAL_BD" "$output_file"
    chmod +x "$output_file"

    echo "Copied local bd to: $output_file"
    echo ""
    echo "Note: Only current platform available."
    echo "For cross-platform builds, provide --source-dir with beads Go source."
}

# Download pre-built binary
download_binary() {
    local os="$1"
    local arch="$2"
    local version="${BEADS_VERSION:-0.46.0}"
    local output_dir="$CLI_BIN_DIR/${os}-${arch}"
    local output_file="$output_dir/bd"

    mkdir -p "$output_dir"

    # Construct download URL
    local archive_name="beads-${version}-${os}-${arch}.tar.gz"
    local url="https://github.com/beads-org/beads/releases/download/v${version}/${archive_name}"

    echo "Downloading ${os}/${arch} from releases..."

    local temp_dir
    temp_dir=$(mktemp -d)

    if curl -fsSL "$url" -o "$temp_dir/$archive_name" 2>/dev/null; then
        cd "$temp_dir"
        tar -xzf "$archive_name"
        find . -name "bd" -type f | head -1 | xargs -I {} cp {} "$output_file"
        chmod +x "$output_file"
        rm -rf "$temp_dir"
        echo "  -> $output_file"
    else
        rm -rf "$temp_dir"
        echo "  -> Failed to download (release may not exist)"
        return 1
    fi
}

# Execute build strategy
case "$BUILD_STRATEGY" in
    source)
        for platform in "${PLATFORMS[@]}"; do
            os="${platform%%:*}"
            arch="${platform##*:}"
            build_from_source "$os" "$arch"
        done
        ;;
    local)
        copy_local
        ;;
    download)
        for platform in "${PLATFORMS[@]}"; do
            os="${platform%%:*}"
            arch="${platform##*:}"
            download_binary "$os" "$arch" || true
        done
        ;;
esac

echo ""
echo "========================================"
echo "Build complete. Binaries:"
echo "========================================"
find "$CLI_BIN_DIR" -name "bd" -type f 2>/dev/null | while read -r f; do
    echo "  $f ($(du -h "$f" | cut -f1))"
done

# Also copy to root cli/bin/bd for current platform
CURRENT_OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
CURRENT_ARCH="$(uname -m)"
case "$CURRENT_ARCH" in
    x86_64) CURRENT_ARCH="amd64" ;;
    aarch64) CURRENT_ARCH="arm64" ;;
esac

if [[ -f "$CLI_BIN_DIR/${CURRENT_OS}-${CURRENT_ARCH}/bd" ]]; then
    cp "$CLI_BIN_DIR/${CURRENT_OS}-${CURRENT_ARCH}/bd" "$CLI_BIN_DIR/bd"
    echo ""
    echo "Current platform binary: $CLI_BIN_DIR/bd"
fi
