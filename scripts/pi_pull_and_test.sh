#!/usr/bin/env bash
# pi_pull_and_test.sh — Pull latest code from origin/master and run the unit suite.
#
# Usage:
#   bash scripts/pi_pull_and_test.sh           # pull + unit tests
#   bash scripts/pi_pull_and_test.sh --no-pull # skip pull (re-run tests only)
#   bash scripts/pi_pull_and_test.sh --lint    # also run ruff + mypy
#
# Exit codes:
#   0 — all steps passed
#   1 — one or more steps failed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── colour helpers ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓ PASS${NC}  $*"; }
info() { echo -e "${CYAN}  INFO${NC}  $*"; }
warn() { echo -e "${YELLOW}  WARN${NC}  $*"; }
fail() { echo -e "${RED}✗ FAIL${NC}  $*"; FAILED=$((FAILED+1)); }

FAILED=0
DO_PULL=true
DO_LINT=false

# ── venv detection ─────────────────────────────────────────────────────────────
# Prefer the venv that install_pi.sh creates; fall back to any activated venv.
VENV_DIR="$REPO_ROOT/.venv"
if [[ -x "$VENV_DIR/bin/python" ]]; then
    PIP="$VENV_DIR/bin/pip"
    PYTHON="$VENV_DIR/bin/python"
elif [[ -n "${VIRTUAL_ENV:-}" && -x "$VIRTUAL_ENV/bin/python" ]]; then
    PIP="$VIRTUAL_ENV/bin/pip"
    PYTHON="$VIRTUAL_ENV/bin/python"
else
    echo -e "\033[0;31m[✗]\033[0m No virtual environment found at $VENV_DIR"
    echo "    Run ./scripts/install_pi.sh first to create it."
    exit 1
fi

for arg in "$@"; do
    case "$arg" in
        --no-pull) DO_PULL=false ;;
        --lint)    DO_LINT=true  ;;
        --help|-h)
            echo "Usage: bash scripts/pi_pull_and_test.sh [--no-pull] [--lint]"
            exit 0 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
done

cd "$REPO_ROOT"

echo ""
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo -e "${CYAN}  SmartTScope — Pi pull + test  $(date '+%Y-%m-%d %H:%M')${NC}"
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo ""

# ── 1. Git pull ────────────────────────────────────────────────────────────────
if $DO_PULL; then
    echo -e "${CYAN}── 1. Git pull (master) ──────────────────────────${NC}"
    info "Branch: $(git rev-parse --abbrev-ref HEAD)"
    info "Remote: $(git remote get-url origin)"

    # Discard any local changes so the pull is never blocked.
    # The Pi is a deployment target; authoritative code lives on the dev machine.
    if ! git diff --quiet || ! git diff --cached --quiet; then
        warn "Local changes detected — discarding to allow clean pull:"
        git diff --name-only
        git diff --cached --name-only
        git checkout -- .
        git clean -fd --quiet
        warn "Local changes discarded."
    fi

    git fetch origin master
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/master)

    if [ "$LOCAL" = "$REMOTE" ]; then
        ok "Already up to date ($(git rev-parse --short HEAD))"
    else
        info "Pulling $(git rev-list HEAD..origin/master --count) new commit(s)..."
        git pull --ff-only origin master
        ok "Pulled → $(git rev-parse --short HEAD): $(git log -1 --format='%s')"
    fi
    echo ""
fi

# ── 2. Install / sync dependencies ────────────────────────────────────────────
echo -e "${CYAN}── 2. Dependencies ───────────────────────────────${NC}"
info "Python : $PYTHON  ($(${PYTHON} --version))"
info "Installing package in editable mode + dev extras..."
if "$PIP" install -q -e ".[dev]"; then
    ok "pip install complete"
else
    fail "pip install failed"
fi
echo ""

# ── 3. Unit tests ─────────────────────────────────────────────────────────────
echo -e "${CYAN}── 3. Unit tests ─────────────────────────────────${NC}"
# Run without the coverage fail-under threshold so partial envs don't hard-fail.
# The full threshold is enforced in CI; on the Pi we just want test pass/fail.
if "$PYTHON" -m pytest tests/unit/ --no-cov -q 2>&1; then
    ok "All unit tests passed"
else
    fail "One or more unit tests failed (see output above)"
fi
echo ""

# ── 4. Optional lint (ruff + mypy) ────────────────────────────────────────────
if $DO_LINT; then
    echo -e "${CYAN}── 4. Lint (ruff) ────────────────────────────────${NC}"
    if "$PYTHON" -m ruff check smart_telescope/ 2>&1; then
        ok "ruff clean"
    else
        fail "ruff reported issues"
    fi

    echo ""
    echo -e "${CYAN}── 5. Type check (mypy) ──────────────────────────${NC}"
    if "$PYTHON" -m mypy smart_telescope/ 2>&1; then
        ok "mypy clean"
    else
        fail "mypy reported issues"
    fi
    echo ""
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
if [ "$FAILED" -eq 0 ]; then
    echo -e "${GREEN}  ALL CHECKS PASSED${NC}"
else
    echo -e "${RED}  $FAILED CHECK(S) FAILED${NC}"
fi
echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
echo ""

exit "$FAILED"
