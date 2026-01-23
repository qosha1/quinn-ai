#!/usr/bin/env bash
#
# QuinnAI Installer
#
# Usage:
#   curl -fsSL https://quinnai.dev/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/quinnai/quinnai/main/scripts/install.sh | bash
#
# Options (via environment variables):
#   QUINNAI_VERSION    - Specific version to install (default: latest)
#   QUINNAI_INSTALL_DIR - Installation directory (default: ~/.quinnai)
#   QUINNAI_NO_MODIFY_PATH - Set to 1 to skip PATH modification
#

set -euo pipefail

# Configuration
GITHUB_REPO="quinnai/quinnai"
INSTALL_DIR="${QUINNAI_INSTALL_DIR:-$HOME/.quinnai}"
BIN_DIR="$INSTALL_DIR/bin"
VERSION="${QUINNAI_VERSION:-latest}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info() {
    echo -e "${BLUE}==>${NC} $1"
}

success() {
    echo -e "${GREEN}==>${NC} $1"
}

warn() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

error() {
    echo -e "${RED}Error:${NC} $1" >&2
    exit 1
}

# Detect platform
detect_platform() {
    local os arch

    os="$(uname -s | tr '[:upper:]' '[:lower:]')"
    arch="$(uname -m)"

    # Normalize OS
    case "$os" in
        darwin) os="darwin" ;;
        linux) os="linux" ;;
        mingw*|msys*|cygwin*) os="windows" ;;
        *)
            error "Unsupported operating system: $os"
            ;;
    esac

    # Normalize architecture
    case "$arch" in
        x86_64|amd64) arch="amd64" ;;
        arm64|aarch64) arch="arm64" ;;
        *)
            error "Unsupported architecture: $arch"
            ;;
    esac

    echo "${os}-${arch}"
}

# Get latest release version from GitHub
get_latest_version() {
    local url="https://api.github.com/repos/${GITHUB_REPO}/releases/latest"

    if command -v curl &> /dev/null; then
        curl -fsSL "$url" | grep '"tag_name":' | sed -E 's/.*"v([^"]+)".*/\1/'
    elif command -v wget &> /dev/null; then
        wget -qO- "$url" | grep '"tag_name":' | sed -E 's/.*"v([^"]+)".*/\1/'
    else
        error "Neither curl nor wget is available. Please install one of them."
    fi
}

# Download file
download() {
    local url="$1"
    local dest="$2"

    info "Downloading from $url"

    if command -v curl &> /dev/null; then
        curl -fsSL "$url" -o "$dest"
    elif command -v wget &> /dev/null; then
        wget -q "$url" -O "$dest"
    else
        error "Neither curl nor wget is available."
    fi
}

# Get shell configuration file
get_shell_rc() {
    local shell_name
    shell_name="$(basename "$SHELL")"

    case "$shell_name" in
        bash)
            if [[ -f "$HOME/.bash_profile" ]]; then
                echo "$HOME/.bash_profile"
            else
                echo "$HOME/.bashrc"
            fi
            ;;
        zsh)
            echo "$HOME/.zshrc"
            ;;
        fish)
            echo "$HOME/.config/fish/config.fish"
            ;;
        *)
            echo "$HOME/.profile"
            ;;
    esac
}

# Add to PATH
add_to_path() {
    if [[ "${QUINNAI_NO_MODIFY_PATH:-0}" == "1" ]]; then
        warn "Skipping PATH modification (QUINNAI_NO_MODIFY_PATH=1)"
        return
    fi

    local shell_rc
    shell_rc="$(get_shell_rc)"
    local path_line="export PATH=\"$BIN_DIR:\$PATH\""
    local fish_path_line="set -gx PATH $BIN_DIR \$PATH"

    # Check if already in rc file
    if grep -q "quinnai" "$shell_rc" 2>/dev/null; then
        info "PATH already configured in $shell_rc"
        return
    fi

    info "Adding QuinnAI to PATH in $shell_rc"

    # Add appropriate line based on shell
    if [[ "$(basename "$SHELL")" == "fish" ]]; then
        echo "" >> "$shell_rc"
        echo "# QuinnAI" >> "$shell_rc"
        echo "$fish_path_line" >> "$shell_rc"
    else
        echo "" >> "$shell_rc"
        echo "# QuinnAI" >> "$shell_rc"
        echo "$path_line" >> "$shell_rc"
    fi
}

# Main installation
main() {
    echo ""
    echo "  QuinnAI Installer"
    echo "  ================="
    echo ""

    # Detect platform
    local platform
    platform="$(detect_platform)"
    info "Detected platform: $platform"

    # Get version
    if [[ "$VERSION" == "latest" ]]; then
        info "Fetching latest version..."
        VERSION="$(get_latest_version)"
        if [[ -z "$VERSION" ]]; then
            error "Failed to determine latest version"
        fi
    fi
    info "Installing version: $VERSION"

    # Create directories
    mkdir -p "$BIN_DIR"

    # Construct download URL
    local wheel_name
    case "$platform" in
        darwin-arm64)
            wheel_name="quinnai-${VERSION}-py3-none-macosx_11_0_arm64.whl"
            ;;
        darwin-amd64)
            wheel_name="quinnai-${VERSION}-py3-none-macosx_10_15_x86_64.whl"
            ;;
        linux-amd64)
            wheel_name="quinnai-${VERSION}-py3-none-manylinux_2_17_x86_64.whl"
            ;;
        linux-arm64)
            wheel_name="quinnai-${VERSION}-py3-none-manylinux_2_17_aarch64.whl"
            ;;
        *)
            error "No pre-built wheel for platform: $platform"
            ;;
    esac

    local download_url="https://github.com/${GITHUB_REPO}/releases/download/v${VERSION}/${wheel_name}"

    # Check for Python and pip
    if ! command -v python3 &> /dev/null; then
        error "Python 3 is required but not installed. Please install Python 3.11 or later."
    fi

    local python_version
    python_version="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    info "Python version: $python_version"

    # Create temp directory
    local temp_dir
    temp_dir="$(mktemp -d)"
    trap "rm -rf $temp_dir" EXIT

    # Download wheel
    local wheel_path="$temp_dir/$wheel_name"
    download "$download_url" "$wheel_path"

    # Install with pip
    info "Installing QuinnAI..."
    python3 -m pip install --quiet --upgrade "$wheel_path"

    # Verify installation
    info "Verifying installation..."
    if command -v qn &> /dev/null; then
        local installed_version
        installed_version="$(qn --version 2>/dev/null || echo 'unknown')"
        success "QuinnAI installed successfully!"
        echo ""
        echo "  Version: $installed_version"
        echo "  Command: qn"
        echo ""
    else
        # qn might not be in PATH yet
        warn "Installation complete but 'qn' not found in PATH."
        echo ""
        echo "  Try running: python3 -m cli.commands.main --version"
        echo ""
    fi

    # Instructions
    echo "Getting Started:"
    echo "  1. Initialize an org:  qn org init my-ai-company"
    echo "  2. Start the org:      qn org start ./my-ai-company"
    echo "  3. Check status:       qn org status ./my-ai-company"
    echo ""
    echo "Documentation: https://github.com/${GITHUB_REPO}#readme"
    echo ""
}

main "$@"
