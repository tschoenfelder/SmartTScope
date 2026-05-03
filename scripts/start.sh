#!/usr/bin/env bash
# SmartTScope — hardware startup script
#
# Hardware is now configured in smart_telescope.toml at the project root.
# Individual settings can still be overridden by environment variables:
#
#   ONSTEP_PORT=/dev/ttyUSB0        bash scripts/start.sh
#   TOUPTEK_INDEX=1                 bash scripts/start.sh
#   STORAGE_DIR=/mnt/ssd/astro      bash scripts/start.sh
#   SIMULATOR_FITS_DIR=~/fits       bash scripts/start.sh   # no-hardware mode
#   OBSERVER_LAT=48.0 OBSERVER_LON=11.0 bash scripts/start.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── colour helpers ─────────────────────────────────────────────────────────────
GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
ok()   { echo -e "${GREEN}  ✓${NC}  $*"; }
info() { echo -e "${CYAN}  ·${NC}  $*"; }
warn() { echo -e "${YELLOW}  !${NC}  $*"; }
err()  { echo -e "${RED}  ✗${NC}  $*" >&2; exit 1; }

# ── storage directory ─────────────────────────────────────────────────────────
# STORAGE_DIR still has a default here because we need it for mkdir below.
# It can also be set in smart_telescope.toml [session] storage_dir.
export STORAGE_DIR="${STORAGE_DIR:-$HOME/smarttscope_data}"
mkdir -p "$STORAGE_DIR"

# ── activate virtual environment ───────────────────────────────────────────────
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

# ── pre-flight display ─────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  SmartTScope  $(date '+%Y-%m-%d %H:%M:%S')${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo ""

info "Python   : $(python --version 2>&1)"
info "Project  : $PROJECT_ROOT"

TOML_PATH="$PROJECT_ROOT/smart_telescope.toml"
if [[ -f "$TOML_PATH" ]]; then
    ok "Config   : $TOML_PATH"
else
    warn "Config   : smart_telescope.toml not found — using env vars / defaults"
fi
echo ""

if [[ -n "${SIMULATOR_FITS_DIR:-}" ]]; then
    warn "Mode     : SIMULATOR  (SIMULATOR_FITS_DIR=$SIMULATOR_FITS_DIR)"
else
    # Show hardware status from env var if explicitly set; otherwise defer to TOML
    if [[ -n "${ONSTEP_PORT:-}" ]]; then
        if [[ -e "$ONSTEP_PORT" ]]; then
            ok "Mount    : OnStep  →  $ONSTEP_PORT  (env var)"
        else
            warn "Mount    : $ONSTEP_PORT not found (env var)"
        fi
    else
        info "Mount    : port from smart_telescope.toml"
    fi

    if [[ -n "${TOUPTEK_INDEX:-}" ]]; then
        ok "Camera   : ToupTek index $TOUPTEK_INDEX  (env var)"
    else
        info "Camera   : index from smart_telescope.toml"
    fi
fi

ok "Storage  : $STORAGE_DIR"
echo ""

# ── launch ─────────────────────────────────────────────────────────────────────
# CD to project root so config.py finds smart_telescope.toml via Path.cwd().
cd "$PROJECT_ROOT"
echo -e "${CYAN}── Starting server ───────────────────────────────${NC}"
exec python -m smart_telescope
