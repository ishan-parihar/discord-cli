#!/usr/bin/env bash
set -euo pipefail
IFS=$'\n\t'

# install.sh - Install discord-cli using uv (user-scoped)
# curl -fsSL https://raw.githubusercontent.com/ishan-parihar/discord-cli/main/install.sh | bash

BIN_DIR="$HOME/.local/bin"
NAME="discord-lyr"
PKG="discord-lyr"
BIN="discord"

# Colors (TTY-gated)
if [ -t 2 ]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; NC=''
fi
info() { echo -e "${GREEN}[INFO]${NC} $*" >&2; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*" >&2; }
err()  { echo -e "${RED}[ERR]${NC} $*" >&2; }
step()  { echo -e "${YELLOW}▸${NC} $*" >&2; }
die()  { err "$*"; exit 1; }
generated() { printf '%s\n' ">>> generated: $1 <<<"; }

# ── Args ───────────────────────────────────────────────────────────────────
# ── Args ──
for arg in "$@"; do
  case "$arg" in
    --no-cta) SKIP_CTA=1 ;;
    --no-harness) SKIP_HARNESS=1 ;;
    --all-harnesses) ALL_HARNESS=1 ;;
    --help|-h) sed -n '3,7p' "$0"; exit 0 ;;
    --force-root) ;;
    *) die "Unknown option: $arg (supported: --no-cta, --no-harness, --all-harnesses)" ;;
  esac
done

# ── OS / arch detection ───────────────────────────────────────────────────
OS="$(uname -s)"
case "$OS" in
  Linux*)     DISTRO="$(. /etc/os-release 2>/dev/null && echo "${ID:-unknown}")" ;;
  Darwin*)    DISTRO="macos" ;;
  *) die "Unsupported OS: $OS — Windows: use install.ps1" ;;
esac

# ── Root guard ────────────────────────────────────────────────────────────
if [ "${EUID:-$(id -u)}" -eq 0 ] && [ "${1:-}" != "--force-root" ]; then
  die "Don't run as root — installs to \$HOME. Re-run as your user (override: --force-root)."
fi

# ── Package-manager matrix ────────────────────────────────────────────────
pm_install() {
  case "$DISTRO" in
    ubuntu|debian|linuxmint|pop)      sudo apt-get update -qq && sudo apt-get install -y "$@" ;;
    fedora|rhel|centos|rocky|alma)    sudo dnf install -y "$@" ;;
    arch|manjaro|cachyos|endeavouros)  sudo pacman -Sy --needed --noconfirm "$@" ;;
    opensuse*)                         sudo zypper -n install "$@" ;;
    alpine)                            sudo apk add "$@" ;;
    macos) command -v brew >/dev/null || die "Homebrew required: https://brew.sh (install it, re-run)"; brew install "$@" ;;
    *) die "Unknown distro '$DISTRO' — install manually: $*" ;;
  esac
}
need() {
  command -v "$1" >/dev/null 2>&1 && return 0
  info "Installing prerequisite: $1"
  pm_install "${@:2}"
  command -v "$1" >/dev/null || die "$1 still missing after install"
}

# ── Idempotent PATH injection ─────────────────────────────────────────────
ensure_path() {
  mkdir -p "$BIN_DIR"
  case ":$PATH:" in *":$BIN_DIR:"*) return 0 ;; esac
  local rc="$HOME/.bashrc"
  if [ -f "$HOME/.zshrc" ] || [ -n "${ZSH_VERSION:-}" ]; then rc="$HOME/.zshrc"; fi
  if ! grep -qs "export PATH=\"${BIN_DIR}:\$PATH\"" "$rc"; then
    printf '\n# added by %s installer\nexport PATH="%s:$PATH"\n' "$NAME" "$BIN_DIR" >> "$rc"
    generated "$rc"
  fi
  export PATH="$BIN_DIR:$PATH"
}

# ── Bootstrap uv ──────────────────────────────────────────────────────────
ensure_uv() {
    if command -v uv &>/dev/null; then
        info "uv already installed: $(uv --version)"
        return 0
    fi
    step "uv not found — bootstrapping via astral.sh installer"
    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        export PATH="$HOME/.local/bin:$PATH"
        if command -v uv &>/dev/null; then
            info "uv installed: $(uv --version)"
            return 0
        fi
    fi
    warn "uv installation failed, falling back to pipx/pip"
    return 1
}

install_via_uv() {
    step "Installing ${PKG} using uv tool..."
    uv tool install --from "git+https://github.com/ishan-parihar/discord-lyr" "${PKG}"
    ensure_path
}

install_via_pipx() {
    command -v pipx &>/dev/null || return 1
    step "Installing ${PKG} using pipx..."
    pipx install "git+https://github.com/ishan-parihar/discord-lyr" || pipx install "${PKG}"
    pipx ensurepath 2>/dev/null || true
}

install_via_pip() {
    local py=""
    for cmd in python3 python3.12 python3.11 python3.10; do
        command -v "$cmd" &>/dev/null && py="$cmd" && break
    done
    [[ -z "$py" ]] && die "Python 3.10+ not found. Install Python 3.10+ first."
    step "Installing ${PKG} using pip..."
    "$py" -m pip install --user --upgrade "git+https://github.com/ishan-parihar/discord-lyr"
    local user_bin
    user_bin="$("$py" -m site --user-base)/bin"
    export PATH="${user_bin}:${PATH}"
}

# ── Harness detection ─────────────────────────────────────────────────────
detect_harnesses() {
    local found=""
    for h in claude codex opencode gemini qwen grok goose hermes zeroclaw omp omo pi droid; do
        command -v "$h" >/dev/null 2>&1 && found="$found $h"
    done
    echo "$found"
}

run_harness_integration() {
    [ "${SKIP_HARNESS:-0}" = "1" ] && { info "Harness integration: skipped (SKIP_HARNESS)"; return 0; }
    local found; found="$(detect_harnesses)"
    [ -z "$found" ] && { info "No AI harnesses detected — skipping agent integration"; return 0; }
    if ! [ -t 0 ] && [ "${ALL_HARNESS:-0}" != "1" ]; then
        info "Detected harnesses:${found} — non-interactive, skipping (re-run with --all-harnesses)"
        return 0
    fi
    if [ "${ALL_HARNESS:-0}" = "1" ]; then local answer="y";
    else read -rp "Configure ${found} ? [Y/n] " answer || answer="y"; fi
    case "$answer" in n|N) return 0 ;; esac
    if command -v npx >/dev/null 2>&1; then
        npx --yes skills add ishan-parihar/discord-cli --agent '*' --skill '*' -y 2>/dev/null ||
            warn "npx skills add failed — register manually"
    fi
    info "Harness integration complete"
}

# ── Verify ────────────────────────────────────────────────────────────────
verify() {
    step "Verifying installation..."
    if command -v "$BIN" &>/dev/null; then
        info "$BIN installed successfully: $($BIN --version 2>/dev/null || echo 'version check failed')"
    else
        die "$BIN command not found on PATH. Open a new shell or run: export PATH=\"$BIN_DIR:\$PATH\""
    fi
}

# ── CTA ───────────────────────────────────────────────────────────────────
print_cta() {
    [ "${SKIP_CTA:-0}" = "1" ] && return 0
    printf '\n%s\n' "──────────────────────────────────────────────────────"
    printf ' ⭐  Found %s useful? Star it:  https://github.com/ishan-parihar/%s\n' "$NAME" "$NAME"
    printf ' 💜  Support development:\n'
    printf '     GitHub Sponsors : https://github.com/sponsors/ishan-parihar\n'
    printf '     Razorpay (UPI)  : https://rzp.io/rzp/ishan-parihar\n'
    printf '     Or run `%s donate` anytime.\n' "$BIN"
    printf '%s\n' "──────────────────────────────────────────────────────"
}

# ── Main ──────────────────────────────────────────────────────────────────
main() {
    info "Installing discord-cli..."
    echo

    need curl curl
    need git git

    # Try uv first (preferred)
    if ensure_uv && install_via_uv; then
        verify
        run_harness_integration
        finish
        exit 0
    fi
    warn "uv install failed — trying pipx..."

    # Try pipx
    if install_via_pipx; then
        verify
        run_harness_integration
        finish
        exit 0
    fi

    # Fallback to pip
    install_via_pip
    verify
    run_harness_integration
    finish
}

finish() {
    echo
    info "Quick start:"
    echo "  discord auth --save   # Extract & save token from browser"
    echo "  discord status        # Verify token works"
    echo "  discord               # Show ambient dashboard"
    echo "  discord update --check && discord update  # Update through the owning package manager"
    echo
    info "For agents (TOON output):"
    echo "  discord search \"term\" --toon"
    echo "  discord dc guilds --toon"
    echo
    info "Session hook (auto-inject context at agent startup):"
    echo "  discord hook install --force"
    echo
    print_cta
}

main "$@"
