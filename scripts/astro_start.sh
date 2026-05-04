#!/usr/bin/env bash
# SmartTScope — launcher for ~/astro_sw/
#
# Place (or symlink) this file at ~/astro_sw/start.sh on the Raspberry Pi.
# It pulls the latest code, reinstalls if anything changed, then starts the server.
#
# Usage:
#   bash ~/astro_sw/start.sh
#   bash ~/astro_sw/start.sh --no-pull      # skip git pull (offline use)
#   bash ~/astro_sw/start.sh --no-install   # skip pip reinstall (faster cold-start)
#
# Hardware overrides via env vars (passed through to the server):
#   ONSTEP_PORT=/dev/ttyUSB_ONSTEP0  bash ~/astro_sw/start.sh
#   TOUPTEK_INDEX=0                  bash ~/astro_sw/start.sh
#   SIMULATOR_FITS_DIR=~/fits        bash ~/astro_sw/start.sh   # no-hardware mode

set -euo pipefail

REPO_DIR="$HOME/astro_sw/SmartTScope"
VENV_DIR="$REPO_DIR/.venv"

# ── option parsing ─────────────────────────────────────────────────────────────
PULL=true
INSTALL=true
for arg in "$@"; do
    case "$arg" in
        --no-pull)    PULL=false ;;
        --no-install) INSTALL=false ;;
        --help|-h)
            sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \?//'
            exit 0 ;;
        *) echo "Unknown option: $arg" >&2; exit 1 ;;
    esac
done

# ── colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC}  $*"; }
info() { echo -e "${CYAN}  ·${NC}  $*"; }
warn() { echo -e "${YELLOW}  !${NC}  $*"; }
err()  { echo -e "${RED}  ✗${NC}  $*" >&2; exit 1; }

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  SmartTScope  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo ""

# ── repo check ─────────────────────────────────────────────────────────────────
[[ -d "$REPO_DIR/.git" ]] \
    || err "Repository not found at $REPO_DIR.  Run scripts/install_pi.sh first."
[[ -d "$VENV_DIR" ]] \
    || err "Virtual environment not found at $VENV_DIR.  Run scripts/install_pi.sh first."

info "Repo     : $REPO_DIR"
info "Python   : $("$VENV_DIR/bin/python" --version 2>&1)"

# ── pull latest ───────────────────────────────────────────────────────────────
if [[ "$PULL" == true ]]; then
    info "Pulling latest changes..."
    BEFORE=$(git -C "$REPO_DIR" rev-parse HEAD)
    git -C "$REPO_DIR" pull --ff-only
    AFTER=$(git -C "$REPO_DIR" rev-parse HEAD)
    if [[ "$BEFORE" != "$AFTER" ]]; then
        ok "Updated  : $BEFORE → $AFTER"
    else
        ok "Already up to date."
    fi
else
    warn "Pull     : skipped (--no-pull)"
fi

# ── install / update ──────────────────────────────────────────────────────────
if [[ "$INSTALL" == true ]]; then
    info "Reinstalling package (Debian 13 / pip 26 workaround)..."
    #
    # pip 26 on Raspberry Pi OS (Debian 13 / trixie) cannot execute the
    # PEP 517 build-backend hook subprocess (BackendUnavailable).
    # Workaround: build the wheel in-process inside the venv's Python
    # (which can always import setuptools) then install the resulting .whl.
    #
    WHEEL_DIR="$REPO_DIR/dist"
    mkdir -p "$WHEEL_DIR"
    rm -f "$WHEEL_DIR"/smart_telescope-*.whl

    REPO_DIR="$REPO_DIR" WHEEL_DIR="$WHEEL_DIR" \
        "$VENV_DIR/bin/python" - <<'PYEOF' || err "Wheel build failed — check output above"
import os, sys, shutil, tempfile, pathlib
src = pathlib.Path(os.environ["REPO_DIR"])
dst = pathlib.Path(os.environ["WHEEL_DIR"])
os.chdir(src)
sys.path.insert(0, str(src))
from setuptools.build_meta import build_wheel
with tempfile.TemporaryDirectory() as tmp:
    name = build_wheel(tmp)
    shutil.copy(f"{tmp}/{name}", dst / name)
    print(f"  built: {name}")
PYEOF

    WHEEL="$(ls "$WHEEL_DIR"/smart_telescope-*.whl 2>/dev/null | head -1)"
    [[ -n "$WHEEL" ]] || err "No wheel found in $WHEEL_DIR"
    "$VENV_DIR/bin/pip" install --quiet "$WHEEL"
    ok "Installed: $(basename "$WHEEL")"
else
    warn "Install  : skipped (--no-install)"
fi

# ── storage directory ─────────────────────────────────────────────────────────
export STORAGE_DIR="${STORAGE_DIR:-$HOME/smarttscope_data}"
mkdir -p "$STORAGE_DIR"
ok "Storage  : $STORAGE_DIR"

# ── hardware status ────────────────────────────────────────────────────────────
if [[ -n "${SIMULATOR_FITS_DIR:-}" ]]; then
    warn "Mode     : SIMULATOR  (SIMULATOR_FITS_DIR=$SIMULATOR_FITS_DIR)"
else
    [[ -n "${ONSTEP_PORT:-}" ]] && info "Mount    : OnStep → $ONSTEP_PORT  (env)"
    [[ -n "${TOUPTEK_INDEX:-}" ]] && info "Camera   : ToupTek index $TOUPTEK_INDEX  (env)"
fi
echo ""

# ── launch ─────────────────────────────────────────────────────────────────────
cd "$REPO_DIR"
echo -e "${CYAN}── Starting server on http://0.0.0.0:8000 ─────────${NC}"
exec "$VENV_DIR/bin/python" -m smart_telescope
