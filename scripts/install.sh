#!/usr/bin/env bash
#
# QuinnAI Installer
#
# Installs the `quinnai` and `quinnai-board` Python packages from PyPI.
# Prefers pipx (isolated, recommended), then uv tool, falls back to pip --user.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/qosha1/quinn-ai/main/scripts/install.sh | bash
#
# Options (env vars):
#   QUINNAI_VERSION    Specific version (default: latest)
#   QUINNAI_NO_BOARD   Set to 1 to skip the board UI (CLI only)
#   QUINNAI_FORCE_PIP  Set to 1 to skip pipx/uv detection and go straight to pip
#

set -euo pipefail

REPO_URL="https://github.com/qosha1/quinn-ai"
PKG_CLI="quinnai"
PKG_BOARD="quinnai-board"
VERSION="${QUINNAI_VERSION:-}"
INSTALL_BOARD=1
[[ "${QUINNAI_NO_BOARD:-0}" == "1" ]] && INSTALL_BOARD=0

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}==>${NC} $1"; }
success() { echo -e "${GREEN}==>${NC} $1"; }
warn()    { echo -e "${YELLOW}Warning:${NC} $1"; }
error()   { echo -e "${RED}Error:${NC} $1" >&2; exit 1; }

# 1. Python 3.11+ check
if ! command -v python3 &>/dev/null; then
    error "python3 is required. Install Python 3.11+ from https://www.python.org/downloads/."
fi
PY_MAJOR=$(python3 -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$(python3 -c 'import sys; print(sys.version_info.minor)')
if (( PY_MAJOR < 3 )) || { (( PY_MAJOR == 3 )) && (( PY_MINOR < 11 )); }; then
    error "Python 3.11+ required. Found ${PY_MAJOR}.${PY_MINOR}."
fi
info "Python: ${PY_MAJOR}.${PY_MINOR}"

# 2. bd (beads) check — runtime system dependency
if ! command -v bd &>/dev/null; then
    warn "'bd' (beads) not found on PATH."
    warn "QuinnAI uses bd for issue tracking. Install it from:"
    warn "  https://github.com/steveyegge/beads"
    warn "  e.g. 'brew install bd' on macOS"
    warn "Continuing — qn-bd commands will fail until bd is on PATH."
else
    info "bd: $(bd --version 2>&1 | head -1)"
fi

# 3. Pick installer (pipx preferred, then uv, then pip)
INSTALLER=""
if [[ "${QUINNAI_FORCE_PIP:-0}" != "1" ]] && command -v pipx &>/dev/null; then
    INSTALLER="pipx"
elif [[ "${QUINNAI_FORCE_PIP:-0}" != "1" ]] && command -v uv &>/dev/null; then
    INSTALLER="uv"
else
    INSTALLER="pip"
fi
info "Using installer: ${INSTALLER}"

pkg_spec() {
    local pkg="$1"
    if [[ -n "$VERSION" ]]; then
        echo "${pkg}==${VERSION}"
    else
        echo "${pkg}"
    fi
}

# 4. Install
# quinnai-board depends on quinnai, so installing it pulls in both packages.
# When QUINNAI_NO_BOARD=1, install only the CLI package.
TARGET="$PKG_BOARD"
(( INSTALL_BOARD )) || TARGET="$PKG_CLI"
SPEC="$(pkg_spec "$TARGET")"
info "Installing ${SPEC}..."

case "$INSTALLER" in
    pipx) pipx install --force "$SPEC" ;;
    uv)   uv tool install --force "$SPEC" ;;
    pip)
        warn "Neither pipx nor uv found — falling back to 'pip install --user'."
        warn "Recommend installing pipx (https://pipx.pypa.io/) and re-running for an isolated environment."
        python3 -m pip install --user --upgrade "$SPEC"
        ;;
esac

# 5. Verify
if command -v qn &>/dev/null; then
    success "qn installed: $(command -v qn)"
else
    warn "'qn' not on PATH."
    warn "If using pipx: run 'pipx ensurepath' and restart your shell."
    warn "If using pip --user: ensure ~/.local/bin is in PATH."
fi

cat <<EOF

  Getting started:
    qn --org-path my-org org init   # create an org folder
    qn --org-path my-org org start  # boot the org

  Docs: ${REPO_URL}#readme
EOF
