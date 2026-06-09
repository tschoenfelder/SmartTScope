#!/usr/bin/env bash
# SmartTScope — hard-reset launcher for ~/astro_sw/
#
# Like astro_start.sh but forces the local repo to exactly match origin/main
# using `git reset --hard` before building and starting.  Use this whenever
# `astro_start.sh` fails because of a diverged local state.
#
# Place (or symlink) this file at ~/astro_sw/astro_pull_start.sh on the Pi.
#
# Usage:
#   bash ~/astro_sw/astro_pull_start.sh
#   bash ~/astro_sw/astro_pull_start.sh --no-install   # skip pip reinstall

set -euo pipefail

REPO_DIR="$HOME/astro_sw/SmartTScope"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

GREEN='\033[0;32m'; CYAN='\033[0;36m'; RED='\033[0;31m'; NC='\033[0m'
ok()  { echo -e "${GREEN}  ✓${NC}  $*"; }
info(){ echo -e "${CYAN}  ·${NC}  $*"; }
err() { echo -e "${RED}  ✗${NC}  $*" >&2; exit 1; }

[[ -d "$REPO_DIR/.git" ]] \
    || err "Repository not found at $REPO_DIR.  Run scripts/install_pi.sh first."

info "Fetching origin..."
git -C "$REPO_DIR" fetch origin

BEFORE=$(git -C "$REPO_DIR" rev-parse HEAD)
git -C "$REPO_DIR" reset --hard origin/main
AFTER=$(git -C "$REPO_DIR" rev-parse HEAD)

if [[ "$BEFORE" != "$AFTER" ]]; then
    ok "Updated  : ${BEFORE:0:8} → ${AFTER:0:8}"
else
    ok "Already at origin/main (${AFTER:0:8})"
fi

# Hand off to astro_start.sh — skip its pull step since we already hard-reset.
exec bash "$SCRIPT_DIR/astro_start.sh" --no-pull "$@"
