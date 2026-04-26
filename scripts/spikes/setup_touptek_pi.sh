#!/usr/bin/env bash
# setup_touptek_pi.sh — Install ToupTek SDK (ARM64) on Raspberry Pi OS
#
# What this script does:
#   1. Downloads the ToupTek SDK zip from GitHub (touptek/toupcamsdk)
#   2. Extracts libtoupcam.so (ARM64/aarch64) to /usr/lib/
#   3. Adds a udev rule so the camera is accessible without sudo
#   4. Adds the current user to the plugdev group
#   5. Verifies the library loads with ctypes
#
# Usage:
#   bash setup_touptek_pi.sh
#   bash setup_touptek_pi.sh --local /path/to/sdk.zip   # use downloaded zip
#
# After running this script, log out and back in (or: newgrp plugdev)
# then run:  python sp1_touptek_arm64.py --fits-out /tmp/sp1_frame.fits

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ToupTek publish their SDK on GitHub.  The aarch64 .so lives at:
#   lin/aarch64/libtoupcam.so
SDK_GITHUB_ZIP="https://github.com/touptek/toupcamsdk/archive/refs/heads/master.zip"
SDK_ZIP_LOCAL="/tmp/toupcamsdk.zip"
SDK_EXTRACT_DIR="/tmp/toupcamsdk_extract"
EXPECTED_SO_PATH="toupcamsdk-master/lin/aarch64/libtoupcam.so"
INSTALL_SO="/usr/lib/libtoupcam.so"

# ToupTek cameras use USB VID 0x547 (ToupTek) — covers AstroCamera, ATR3, etc.
UDEV_RULE_FILE="/etc/udev/rules.d/99-touptek.rules"
TOUPTEK_VID="0547"

# ── colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
info() { echo -e "${CYAN}[·]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

# ── option parsing ─────────────────────────────────────────────────────────────
LOCAL_ZIP=""
for arg in "$@"; do
    case "$arg" in
        --local) shift; LOCAL_ZIP="$1"; shift ;;
        --help|-h)
            echo "Usage: bash setup_touptek_pi.sh [--local /path/to/sdk.zip]"
            exit 0 ;;
        *) err "Unknown option: $arg" ;;
    esac
done

# ── 1. platform check ─────────────────────────────────────────────────────────
section_platform() {
    info "Platform check..."
    local arch
    arch="$(uname -m)"
    if [[ "$arch" != "aarch64" ]]; then
        err "This script targets aarch64 (ARM64). Got: $arch"
    fi
    log "ARM64 (aarch64) confirmed"
    command -v curl   &>/dev/null || err "'curl' not found — run: sudo apt-get install curl"
    command -v unzip  &>/dev/null || { warn "'unzip' not found — installing..."; sudo apt-get install -y unzip; }
    command -v python3 &>/dev/null || err "'python3' not found"
}

# ── 2. download / locate SDK zip ──────────────────────────────────────────────
section_download() {
    if [[ -n "$LOCAL_ZIP" ]]; then
        [[ -f "$LOCAL_ZIP" ]] || err "Local zip not found: $LOCAL_ZIP"
        SDK_ZIP_LOCAL="$LOCAL_ZIP"
        log "Using local SDK zip: $SDK_ZIP_LOCAL"
        return
    fi

    if [[ -f "$SDK_ZIP_LOCAL" ]]; then
        log "SDK zip already downloaded: $SDK_ZIP_LOCAL"
        return
    fi

    info "Downloading ToupTek SDK from GitHub..."
    info "URL: $SDK_GITHUB_ZIP"
    if curl -fsSL --retry 3 --retry-delay 5 "$SDK_GITHUB_ZIP" -o "$SDK_ZIP_LOCAL"; then
        log "Download complete: $SDK_ZIP_LOCAL ($(du -sh "$SDK_ZIP_LOCAL" | cut -f1))"
    else
        warn "GitHub download failed."
        echo ""
        echo "  Manual download instructions:"
        echo "  1. On any PC, go to:  https://github.com/touptek/toupcamsdk"
        echo "     Click 'Code' → 'Download ZIP'"
        echo "  2. Copy the ZIP to the Pi:"
        echo "     scp toupcamsdk-main.zip pi@<IP>:/tmp/toupcamsdk.zip"
        echo "  3. Re-run this script:"
        echo "     bash setup_touptek_pi.sh --local /tmp/toupcamsdk.zip"
        echo ""
        echo "  Alternatively download the SDK from ToupTek's website:"
        echo "    https://www.touptek.com/download/showdownload.php?lang=en&id=37"
        echo "  Extract lin/aarch64/libtoupcam.so and place it in /usr/lib/"
        err "Cannot continue without SDK."
    fi
}

# ── 3. extract ARM64 .so ──────────────────────────────────────────────────────
section_extract() {
    info "Extracting ARM64 library from zip..."
    rm -rf "$SDK_EXTRACT_DIR"
    mkdir -p "$SDK_EXTRACT_DIR"
    unzip -q "$SDK_ZIP_LOCAL" -d "$SDK_EXTRACT_DIR"

    # The zip may unpack as toupcamsdk-master/ or toupcamsdk-main/
    local so_path
    so_path="$(find "$SDK_EXTRACT_DIR" -name "libtoupcam.so" -path "*/aarch64/*" | head -n1)"

    if [[ -z "$so_path" ]]; then
        info "Directory listing of extracted zip:"
        find "$SDK_EXTRACT_DIR" -maxdepth 4 | sed 's|'"$SDK_EXTRACT_DIR/"'||'
        err "libtoupcam.so (aarch64) not found in zip. Wrong SDK package?"
    fi

    log "Found: $so_path"

    # Verify it is actually ARM64
    if command -v file &>/dev/null; then
        local file_out
        file_out="$(file "$so_path")"
        info "$file_out"
        if echo "$file_out" | grep -qiE "aarch64|ARM aarch64"; then
            log "Confirmed ARM64 binary"
        else
            warn "Binary may not be ARM64: $file_out"
            warn "Proceeding anyway — ctypes will fail if wrong arch."
        fi
    fi

    sudo cp "$so_path" "$INSTALL_SO"
    sudo ldconfig
    log "Installed: $INSTALL_SO"
    rm -rf "$SDK_EXTRACT_DIR"
}

# ── 4. udev rule ──────────────────────────────────────────────────────────────
section_udev() {
    info "Setting up udev rule for ToupTek cameras..."

    # Rule: any USB device with ToupTek VID gets plugdev group + rw access
    local rule_content
    rule_content='SUBSYSTEM=="usb", ATTRS{idVendor}=="'"$TOUPTEK_VID"'", GROUP="plugdev", MODE="0666"'

    if [[ -f "$UDEV_RULE_FILE" ]]; then
        local existing
        existing="$(cat "$UDEV_RULE_FILE")"
        if [[ "$existing" == "$rule_content" ]]; then
            log "udev rule already in place: $UDEV_RULE_FILE"
            return
        fi
    fi

    echo "$rule_content" | sudo tee "$UDEV_RULE_FILE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    log "udev rule installed: $UDEV_RULE_FILE"
}

# ── 5. add user to plugdev ─────────────────────────────────────────────────────
section_plugdev() {
    local user="${SUDO_USER:-$USER}"
    if groups "$user" | grep -qw plugdev; then
        log "User '$user' already in plugdev group"
    else
        sudo usermod -aG plugdev "$user"
        log "Added '$user' to plugdev group"
        warn "Log out and back in (or run: newgrp plugdev) for group change to take effect"
    fi
}

# ── 6. verify ─────────────────────────────────────────────────────────────────
section_verify() {
    info "Verifying library loads with ctypes..."

    python3 - <<'PYEOF'
import ctypes, sys
try:
    lib = ctypes.cdll.LoadLibrary("libtoupcam.so")
    print(f"  ✓ libtoupcam.so loaded: {lib}")
except OSError as e:
    print(f"  ✗ Failed to load libtoupcam.so: {e}", file=sys.stderr)
    sys.exit(1)
PYEOF
    log "Library loads successfully"
}

# ── 7. copy toupcam.py alongside spike ────────────────────────────────────────
section_copy_py() {
    local src="$REPO_ROOT/resources/touptek/toupcam.py"
    local dst="$SCRIPT_DIR/toupcam.py"
    if [[ -f "$src" && ! -f "$dst" ]]; then
        cp "$src" "$dst"
        log "Copied toupcam.py to $SCRIPT_DIR"
    fi
}

# ── summary ───────────────────────────────────────────────────────────────────
section_summary() {
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ToupTek SDK setup complete${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Library : $INSTALL_SO"
    echo "  udev    : $UDEV_RULE_FILE"
    echo ""
    echo "  Next steps:"
    echo "    1. Connect the ToupTek camera via USB"
    echo "    2. Run SP-1 to verify capture:"
    echo "       cd $SCRIPT_DIR"
    echo "       python sp1_touptek_arm64.py --fits-out /tmp/sp1_frame.fits"
    echo ""
    echo "  The captured FITS (/tmp/sp1_frame.fits) is the input for SP-2."
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}ToupTek SDK — ARM64 Pi OS setup${NC}"
    echo ""
    section_platform
    section_download
    section_extract
    section_udev
    section_plugdev
    section_verify
    section_copy_py
    section_summary
}

main "$@"
