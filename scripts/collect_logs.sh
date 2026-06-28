#!/usr/bin/env bash
# collect_logs.sh — bundle the last N lines of all SmartTScope logs into a zip
# for developer analysis.
#
# Usage:
#   bash scripts/collect_logs.sh            # last 500 lines per file (default)
#   bash scripts/collect_logs.sh 200        # last 200 lines per file
#
# Output:  ~/smarttscope_logs_<timestamp>.zip
# Send that file to the developer.

set -euo pipefail

LINES="${1:-500}"
LOGS_DIR="${LOG_DIR:-$HOME/.SmartTScope/logs}"
TIMESTAMP=$(date '+%Y%m%d_%H%M%S')
ZIP="$HOME/smarttscope_logs_${TIMESTAMP}.zip"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "=== SmartTScope log collector ==="
echo "Log root : $LOGS_DIR"
echo "Tail     : last $LINES lines per file"
echo ""

# ── section logs (most recent session) ────────────────────────────────────────
SESSION_DIR=$(ls -td "$LOGS_DIR"/???????? 2>/dev/null | head -1 || true)

if [[ -n "$SESSION_DIR" ]]; then
    SESSION_ID=$(basename "$SESSION_DIR")
    echo "Session  : $SESSION_ID"
    for f in "$SESSION_DIR"/*.log; do
        [[ -f "$f" ]] || continue
        name=$(basename "$f")
        tail -n "$LINES" "$f" > "$TMP/${SESSION_ID}_${name}"
        wc_lines=$(wc -l < "$f")
        echo "  + $name  ($wc_lines total → last $LINES)"
    done
else
    echo "  [no session directory found in $LOGS_DIR]"
fi

# ── server log (stderr/stdout tee'd by astro_start.sh) ────────────────────────
SERVER_LOG="$LOGS_DIR/server.log"
if [[ -f "$SERVER_LOG" ]]; then
    tail -n "$LINES" "$SERVER_LOG" > "$TMP/server.log"
    wc_lines=$(wc -l < "$SERVER_LOG")
    echo "  + server.log  ($wc_lines total → last $LINES)"
else
    echo "  [server.log not found — redeploy with updated astro_start.sh to enable]"
fi

# ── config snapshot (no secrets expected) ─────────────────────────────────────
CONFIG="$HOME/.SmartTScope/config.toml"
[[ -f "$CONFIG" ]] && cp "$CONFIG" "$TMP/config.toml" && echo "  + config.toml"

# ── system info ───────────────────────────────────────────────────────────────
{
    echo "=== collect_logs.sh ==="
    echo "collected_at : $(date -Iseconds)"
    echo "hostname     : $(hostname)"
    echo "uname        : $(uname -a)"
    echo "disk_free    : $(df -h "$HOME" | tail -1)"
    echo ""
    echo "=== git log (last 5) ==="
    git -C "$(dirname "$0")/.." log --oneline -5 2>/dev/null || echo "(not a git repo)"
} > "$TMP/sysinfo.txt"
echo "  + sysinfo.txt"

# ── zip ───────────────────────────────────────────────────────────────────────
(cd "$TMP" && zip -qr "$ZIP" .)

echo ""
echo "Bundle   : $ZIP"
echo "$(du -h "$ZIP" | cut -f1)  — send this file for analysis."
