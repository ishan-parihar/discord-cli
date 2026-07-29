#!/usr/bin/env bash
# install.sh - Install discord-cli using uv (user-scoped)

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

info() { echo -e "${GREEN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERR]${NC} $*"; }

# ============================================================================
# FRESH-SYSTEM INSTALL (curl | bash)
# ============================================================================
# Run this on any fresh system to install uv + discord-cli in one go:
#
#   curl -LsSf https://raw.githubusercontent.com/ishan-parihar/discord-cli/main/install.sh | bash
#
# Or with explicit uv install:
#
#   curl -LsSf https://astral.sh/uv/install.sh | sh && \
#   curl -LsSf https://raw.githubusercontent.com/ishan-parihar/discord-cli/main/install.sh | bash
# ============================================================================

# Check for uv
if ! command -v uv &>/dev/null; then
    err "uv not found. Install it first:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  # or: pipx install uv"
    exit 1
fi

info "Installing discord-cli with uv..."

# Install as a uv tool (isolated, user-scoped, binary in ~/.local/bin)
uv tool install --from git+https://github.com/ishan-parihar/discord-cli kabi-discord-cli

# Verify installation
if command -v discord &>/dev/null; then
    info "Installation successful!"
    discord --version
else
    warn "Binary not in PATH. Adding ~/.local/bin to PATH..."
    case ":$PATH:" in
        *":$HOME/.local/bin:"*) ;;
        *) export PATH="$HOME/.local/bin:$PATH" ;;
    esac

    if command -v discord &>/dev/null; then
        info "Installation successful! (PATH updated)"
        discord --version
    else
        err "Installation completed but 'discord' command not found."
        echo "Try: export PATH=\"\$HOME/.local/bin:\$PATH\""
        exit 1
    fi
fi

echo
info "Quick start:"
echo "  discord auth --save   # Extract & save token from browser"
echo "  discord status        # Verify token works"
echo "  discord               # Show ambient dashboard"
echo
info "For agents (TOON output):"
echo "  discord search \"term\" --toon"
echo "  discord dc guilds --toon"
echo
info "Session hook (auto-inject context at agent startup):"
echo "  discord hook install --force"