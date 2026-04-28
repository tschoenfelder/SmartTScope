#!/usr/bin/env bash
# SmartTScope — Raspberry Pi 5 installation script
#
# Usage:
#   bash install_pi.sh            # runtime + dev dependencies
#   bash install_pi.sh --with-astap   # also install ASTAP plate solver
#   bash install_pi.sh --dev-only     # skip clone; install into current directory
#
# Requirements: Raspberry Pi OS 64-bit (Bookworm), internet access, sudo rights.

set -euo pipefail

# ── configuration ─────────────────────────────────────────────────────────────
PYTHON_REQUIRED="3.13"
REPO_URL="https://github.com/tschoenfelder/SmartTScope.git"
INSTALL_DIR="$HOME/SmartTScope"
ASTAP_URL="https://www.hnsky.org/astap_arm64.deb"
ASTAP_DEB="/tmp/astap_arm64.deb"

# ── option parsing ─────────────────────────────────────────────────────────────
WITH_ASTAP=false
DEV_ONLY=false
for arg in "$@"; do
    case "$arg" in
        --with-astap) WITH_ASTAP=true ;;
        --dev-only)   DEV_ONLY=true; INSTALL_DIR="$(pwd)" ;;
        --help|-h)
            echo "Usage: bash install_pi.sh [--with-astap] [--dev-only]"
            exit 0 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

# VENV_DIR must be derived after option parsing so --dev-only is reflected.
VENV_DIR="$INSTALL_DIR/.venv"

# ── helpers ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
log()  { echo -e "${GREEN}[+]${NC} $*"; }
info() { echo -e "${CYAN}[·]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*" >&2; exit 1; }

require_cmd() { command -v "$1" &>/dev/null || err "Required command not found: $1"; }

# ── platform check ────────────────────────────────────────────────────────────
section_platform() {
    info "Checking platform..."
    local arch
    arch="$(uname -m)"
    [[ "$arch" == "aarch64" ]] || warn "Expected aarch64 (ARM64); got $arch — proceed with caution."

    if [[ -f /etc/os-release ]]; then
        # shellcheck source=/dev/null
        source /etc/os-release
        info "OS: $PRETTY_NAME"
        [[ "${ID:-}" == "raspbian" || "${ID:-}" == "debian" ]] \
            || warn "Expected Raspberry Pi OS (Debian); got $ID — some steps may differ."
    fi
}

# ── system packages ───────────────────────────────────────────────────────────
section_system_packages() {
    log "Installing system packages..."
    sudo apt-get update -qq

    # Core build and runtime dependencies
    sudo apt-get install -y --no-install-recommends \
        git \
        curl \
        ca-certificates \
        build-essential \
        libssl-dev \
        libffi-dev \
        zlib1g-dev \
        libbz2-dev \
        libreadline-dev \
        libsqlite3-dev \
        liblzma-dev \
        libncurses-dev \
        tk-dev \
        libxml2-dev \
        libxmlsec1-dev \
        \
        libcfitsio-dev \
        libwcs8 \
        wcslib-dev \
        \
        libjpeg-dev \
        libpng-dev \
        libtiff-dev \
        \
        python3-dev \
        python3-venv \
        \
        libhdf5-dev \
        libopenblas-dev

    log "System packages installed."
}

# ── Python 3.13 ───────────────────────────────────────────────────────────────
section_python() {
    info "Checking for Python ${PYTHON_REQUIRED}..."

    local python_bin
    python_bin="$(command -v python3.13 2>/dev/null || true)"

    if [[ -n "$python_bin" ]]; then
        log "Python ${PYTHON_REQUIRED} already installed: $python_bin"
        return
    fi

    # Detect distro family: Debian ships Python 3.13 natively from trixie onwards;
    # Ubuntu does not and needs the deadsnakes PPA.
    local distro_id=""
    [[ -f /etc/os-release ]] && { source /etc/os-release; distro_id="${ID:-}"; }

    if [[ "$distro_id" == "debian" ]]; then
        log "Python ${PYTHON_REQUIRED} not found — installing from Debian repos..."
        sudo apt-get install -y --no-install-recommends \
            python3.13 \
            python3.13-venv \
            python3.13-dev \
            || err "python3.13 not found in Debian repos. Is this Debian 13 (trixie) or later?"
    else
        log "Python ${PYTHON_REQUIRED} not found — installing via deadsnakes PPA..."
        # deadsnakes PPA provides Python 3.13 for Ubuntu ARM64
        sudo apt-get install -y --no-install-recommends software-properties-common
        sudo add-apt-repository -y ppa:deadsnakes/ppa
        sudo apt-get update -qq
        sudo apt-get install -y --no-install-recommends \
            python3.13 \
            python3.13-venv \
            python3.13-dev
    fi

    log "Python ${PYTHON_REQUIRED} installed."

    # Verify
    python3.13 --version || err "Python 3.13 installation failed."
}

# ── clone repository ──────────────────────────────────────────────────────────
section_clone() {
    if [[ "$DEV_ONLY" == true ]]; then
        info "Skipping clone (--dev-only); using current directory: $(pwd)"
        return
    fi

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log "Repository already exists at $INSTALL_DIR — pulling latest..."
        git -C "$INSTALL_DIR" pull --ff-only
    else
        log "Cloning SmartTScope into $INSTALL_DIR..."
        git clone "$REPO_URL" "$INSTALL_DIR"
    fi
}

# ── virtual environment ───────────────────────────────────────────────────────
section_venv() {
    if [[ -d "$VENV_DIR" ]]; then
        log "Virtual environment already exists at $VENV_DIR"
    else
        log "Creating Python ${PYTHON_REQUIRED} virtual environment..."
        python3.13 -m venv "$VENV_DIR"
    fi

    # Upgrade pip + setuptools so setuptools.backends.legacy is available.
    # Not quiet: a silent failure here is the root cause of the editable-install
    # BackendUnavailable error that follows.
    "$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel \
        || err "Failed to upgrade pip/setuptools/wheel"
    log "Virtual environment ready. (setuptools $("$VENV_DIR/bin/python" -c 'import setuptools; print(setuptools.__version__)'))"
}

# ── install SmartTScope ───────────────────────────────────────────────────────
section_install() {
    log "Installing SmartTScope and all dependencies..."

    # pip 26 on Debian 13 cannot run the PEP 517 build-backend hook subprocess
    # (BackendUnavailable: Cannot import 'setuptools.backends.legacy') regardless
    # of --no-build-isolation or PYTHONPATH workarounds.
    #
    # Workaround: call setuptools.build_meta.build_wheel() IN-PROCESS (no
    # subprocess, always finds the venv's setuptools 82), then install the
    # resulting wheel with plain 'pip install <wheel.whl>' — installing a
    # pre-built wheel never invokes any build backend.

    local wheel_dir="$INSTALL_DIR/dist"
    mkdir -p "$wheel_dir"
    rm -f "$wheel_dir"/smart_telescope-*.whl

    log "Building wheel (in-process, no hook subprocess)..."
    INSTALL_DIR="$INSTALL_DIR" WHEEL_DIR="$wheel_dir" \
        "$VENV_DIR/bin/python" - <<'PYEOF' || err "Wheel build failed"
import os, sys, shutil, tempfile, pathlib
src = pathlib.Path(os.environ["INSTALL_DIR"])
dst = pathlib.Path(os.environ["WHEEL_DIR"])
os.chdir(src)
sys.path.insert(0, str(src))
from setuptools.build_meta import build_wheel
with tempfile.TemporaryDirectory() as tmp:
    name = build_wheel(tmp)
    shutil.copy(f"{tmp}/{name}", dst / name)
    print(f"  built: {name}")
PYEOF

    local wheel
    wheel="$(ls "$wheel_dir/smart_telescope-"*.whl | head -1)"
    [[ -n "$wheel" ]] || err "No wheel found in $wheel_dir after build"

    log "Installing wheel and dependencies..."
    "$VENV_DIR/bin/pip" install --quiet "$wheel"

    # Dev extras are standard PyPI packages — no build backend needed for them.
    "$VENV_DIR/bin/pip" install --quiet \
        "pytest>=8.0" "pytest-asyncio>=0.23" "pytest-cov>=5.0" \
        "pytest-mock>=3.15" "httpx>=0.27" "ruff>=0.4" "mypy>=1.10" \
        "pyserial>=3.5" "build>=1.0"

    log "SmartTScope installed."
}

# ── ASTAP plate solver ────────────────────────────────────────────────────────
section_astap() {
    if [[ "$WITH_ASTAP" != true ]]; then
        info "Skipping ASTAP (pass --with-astap to install)."
        return
    fi

    if command -v astap &>/dev/null; then
        log "ASTAP already installed: $(command -v astap)"
        return
    fi

    log "Downloading ASTAP for ARM64..."
    curl -fsSL "$ASTAP_URL" -o "$ASTAP_DEB" \
        || err "Failed to download ASTAP. Check the URL: $ASTAP_URL"

    sudo dpkg -i "$ASTAP_DEB" || sudo apt-get install -f -y
    rm -f "$ASTAP_DEB"

    log "ASTAP installed: $(command -v astap)"

    warn "ASTAP star catalog is NOT installed."
    warn "Download a D-series catalog from https://www.hnsky.org/astap.htm"
    warn "(D80 recommended — ~1.25 GB, widest coverage, no other drawbacks)."
    warn "Extract the .zip and place the .290 files in the ASTAP data directory"
    warn "(shown via: astap --help)."
    warn ""
    warn "For plate-solver integration tests, also place a C8 M42 FITS frame at:"
    warn "  $INSTALL_DIR/tests/fixtures/c8_native_m42.fits"
}

# ── verify installation ───────────────────────────────────────────────────────
section_verify() {
    log "Verifying installation..."

    # Run the full unit + integration suite (hardware tests excluded)
    "$VENV_DIR/bin/pytest" \
        "$INSTALL_DIR/tests/unit/" \
        "$INSTALL_DIR/tests/integration/" \
        -q --tb=short \
        || err "Test suite failed — check output above."

    log "All tests passed."
}

# ── activation helper ─────────────────────────────────────────────────────────
section_summary() {
    echo ""
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  SmartTScope installed successfully${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Location : $INSTALL_DIR"
    echo "  Python   : $VENV_DIR/bin/python  ($(${VENV_DIR}/bin/python --version))"
    echo ""
    echo "  Activate the virtual environment:"
    echo "    source $VENV_DIR/bin/activate"
    echo ""
    echo "  Run the dev pipeline:"
    echo "    ruff check smart_telescope/ tests/"
    echo "    mypy smart_telescope/"
    echo "    pytest tests/unit/ tests/integration/"
    echo ""
    if [[ "$WITH_ASTAP" == true ]] && command -v astap &>/dev/null; then
        echo "  ASTAP    : $(command -v astap)"
        echo "  Remember : install the D80 star catalog from hnsky.org"
        echo ""
    fi
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${CYAN}SmartTScope — Raspberry Pi 5 installer${NC}"
    echo ""

    section_platform
    section_system_packages
    section_python
    section_clone
    section_venv
    section_install
    section_astap
    section_verify
    section_summary
}

main "$@"
