#!/usr/bin/env bash
# setup_touptek_pi.sh — Install toupcam.py and libtoupcam.so into the venv.
#
# toupcam.py is already bundled in resources/touptek/. libtoupcam.so must be
# downloaded from ToupTek and placed in the same directory first:
#
#   1. Download the ARM64 Linux SDK from the ToupTek website
#      (the URL is shown in the SmartTScope "ToupTek SDK not available" error)
#   2. Extract the archive and copy libtoupcam.so to this repo's root:
#        cp /path/to/sdk/libtoupcam.so .
#   3. Run this script:
#        bash scripts/setup_touptek_pi.sh
#
# After this script completes, restart the SmartTScope server.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}[+]${NC} $*"; }
info() { echo -e "${CYAN}[·]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

# ── locate venv ───────────────────────────────────────────────────────────────
VENV_DIR="$REPO_ROOT/.venv"
[[ -x "$VENV_DIR/bin/python" ]] \
    || err "No venv at $VENV_DIR — run scripts/install_pi.sh --dev-only first."

PYTHON="$VENV_DIR/bin/python"
SITE_PACKAGES="$("$PYTHON" -c "import sysconfig; print(sysconfig.get_path('purelib'))")"
info "Venv site-packages: $SITE_PACKAGES"

# ── copy toupcam.py ───────────────────────────────────────────────────────────
TOUPCAM_SRC="$REPO_ROOT/resources/touptek/toupcam.py"
[[ -f "$TOUPCAM_SRC" ]] || err "toupcam.py not found at $TOUPCAM_SRC"

cp "$TOUPCAM_SRC" "$SITE_PACKAGES/toupcam.py"
ok "Installed toupcam.py → $SITE_PACKAGES/toupcam.py"

# ── copy libtoupcam.so ────────────────────────────────────────────────────────
# Search in the repo root (user drops it there) and the script directory.
LIBSO=""
for candidate in "$REPO_ROOT/libtoupcam.so" "$SCRIPT_DIR/libtoupcam.so"; do
    if [[ -f "$candidate" ]]; then
        LIBSO="$candidate"
        break
    fi
done

if [[ -z "$LIBSO" ]]; then
    echo ""
    echo -e "${RED}[✗]${NC} libtoupcam.so not found."
    echo "    Download the ARM64 Linux SDK from the ToupTek website,"
    echo "    extract it, and copy libtoupcam.so to the repo root:"
    echo ""
    echo "      cp /path/to/sdk/libtoupcam.so $REPO_ROOT/"
    echo ""
    echo "    Then re-run this script."
    exit 1
fi

cp "$LIBSO" "$SITE_PACKAGES/libtoupcam.so"
ok "Installed libtoupcam.so → $SITE_PACKAGES/libtoupcam.so"

# ── verify import ─────────────────────────────────────────────────────────────
if "$PYTHON" -c "import toupcam; print('  toupcam version:', getattr(toupcam, '__version__', 'unknown'))"; then
    ok "import toupcam succeeded"
else
    err "import toupcam failed — libtoupcam.so may be the wrong architecture."
fi

echo ""
ok "ToupTek SDK ready. Restart the SmartTScope server to apply."
