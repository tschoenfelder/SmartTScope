#!/usr/bin/env bash
# SmartTScope — hardware startup script
#
# Activates the Python virtual environment, configures hardware exports,
# and starts the uvicorn server on http://0.0.0.0:8000.
#
# All settings can be overridden by prefixing the command:
#
#   bash scripts/start.sh                           # default hardware config
#   ONSTEP_PORT=/dev/ttyUSB0 bash scripts/start.sh  # different serial port
#   TOUPTEK_INDEX=1 bash scripts/start.sh            # second camera
#   STORAGE_DIR=/mnt/ssd/astro bash scripts/start.sh # custom image storage
#   SIMULATOR_FITS_DIR=~/fits bash scripts/start.sh  # simulator mode (no hardware)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC}  $*"; }
info() { echo -e "${CYAN}  ·${NC}  $*"; }
warn() { echo -e "${YELLOW}  !${NC}  $*"; }
err()  { echo -e "${RED}  ✗${NC}  $*" >&2; exit 1; }

# ── hardware configuration ─────────────────────────────────────────────────────
# Set defaults; any can be overridden by the calling environment.
export ONSTEP_PORT="${ONSTEP_PORT:-/dev/ttyACM0}"
export TOUPTEK_INDEX="${TOUPTEK_INDEX:-0}"
export STORAGE_DIR="${STORAGE_DIR:-$HOME/smarttscope_data}"

# ── observer location (Usingen, Hesse, Germany) ───────────────────────────────
export OBSERVER_LAT="${OBSERVER_LAT:-50.336}"   # decimal degrees, north-positive
export OBSERVER_LON="${OBSERVER_LON:-8.533}"    # decimal degrees, east-positive

# ── activate virtual environment ───────────────────────────────────────────────
# install_pi.sh creates the venv at <project>/.venv
# An in-place venv (python3 -m venv .) lives at the project root itself.
if [[ -f "$PROJECT_ROOT/.venv/bin/activate" ]]; then
    VENV_ACTIVATE="$PROJECT_ROOT/.venv/bin/activate"
elif [[ -f "$PROJECT_ROOT/bin/activate" ]]; then
    VENV_ACTIVATE="$PROJECT_ROOT/bin/activate"
else
    err "No virtual environment found.
       Expected: $PROJECT_ROOT/.venv/bin/activate
            or: $PROJECT_ROOT/bin/activate
       Run install_pi.sh to set one up."
fi

# shellcheck source=/dev/null
source "$VENV_ACTIVATE"

# ── storage directory ──────────────────────────────────────────────────────────
mkdir -p "$STORAGE_DIR"

# ── pre-flight checks ──────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  SmartTScope  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo ""

info "Python   : $(python --version 2>&1)"
info "Project  : $PROJECT_ROOT"
echo ""

# Report hardware mode
if [[ -n "${SIMULATOR_FITS_DIR:-}" ]]; then
    warn "Mode     : SIMULATOR  (SIMULATOR_FITS_DIR=$SIMULATOR_FITS_DIR)"
else
    if [[ -e "$ONSTEP_PORT" ]]; then
        ok "Mount    : OnStep  →  $ONSTEP_PORT"
    else
        warn "Mount    : $ONSTEP_PORT not found — check USB connection or set ONSTEP_PORT"
    fi
    ok "Camera   : ToupTek index $TOUPTEK_INDEX"
fi

ok "Storage  : $STORAGE_DIR"
echo ""

# ── launch ─────────────────────────────────────────────────────────────────────
echo -e "${CYAN}── Starting server ───────────────────────────────${NC}"
exec python -m smart_telescope
