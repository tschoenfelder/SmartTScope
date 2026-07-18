#!/usr/bin/env bash
# check_connect_stall.sh — M10-024 hardware evidence: does an in-progress
# camera SDK connect (Open/EnumV2) stall *unrelated* HTTP requests?
#
# M10-021/022 decoupled the mount/time/location flow from camera locks in
# Python — but if the ToupTek SDK binding holds the GIL during Open()/
# EnumV2() (a C-extension call), every Python thread freezes regardless of
# locking, including the FastAPI event loop and threadpool. This script
# tells the two cases apart:
#
#   - Static asset (/static/js/app.js, no device dependency at all) AND
#     /api/location/status (mount-only, no camera dependency, see
#     api/location.py) both stall during camera connect  → GIL-held SDK call
#     (locks are not the whole story — file a SYNC.md candidate, M10-024).
#   - Only camera-touching endpoints stall (not exercised by this script;
#     see docs/todo.md M10-021/022)                        → the locks already
#     fixed are the whole story, nothing further needed.
#
# Usage:
#   1. Restart the server (bash ~/astro_sw/astro_start.sh) with cameras
#      connected so a real connect+prime happens on startup.
#   2. Immediately: bash scripts/check_connect_stall.sh
#      (run it from a second terminal/SSH session right after starting the
#      server — the window that matters is the first ~10-30s after start).
#
# Output: one line per request with its latency; a summary at the end.
# Anything > 250 ms on either endpoint during that window is a stall worth
# reporting — paste the output back for the M10-024 write-up.

set -uo pipefail

HOST="${1:-http://127.0.0.1:8000}"
DURATION_S="${2:-30}"
INTERVAL_S="0.2"

echo "=== check_connect_stall.sh (M10-024) ==="
echo "Host     : $HOST"
echo "Duration : ${DURATION_S}s @ ${INTERVAL_S}s interval, alternating endpoints"
echo "Started  : $(date -Iseconds)"
echo ""
printf '%-8s %-28s %10s\n' "n" "endpoint" "latency_ms"

STATIC_MAX=0
STATUS_MAX=0
STATIC_STALLS=0
STATUS_STALLS=0
N=0
DEADLINE=$(( $(date +%s) + DURATION_S ))

while [[ "$(date +%s)" -lt "$DEADLINE" ]]; do
    N=$((N + 1))
    for path in "/static/js/app.js" "/api/location/status"; do
        t0=$(date +%s%N)
        curl -s -o /dev/null -m 5 "$HOST$path" || true
        t1=$(date +%s%N)
        ms=$(( (t1 - t0) / 1000000 ))
        printf '%-8s %-28s %10s\n' "$N" "$path" "$ms"
        if [[ "$path" == "/static/js/app.js" ]]; then
            [[ "$ms" -gt "$STATIC_MAX" ]] && STATIC_MAX=$ms
            [[ "$ms" -gt 250 ]] && STATIC_STALLS=$((STATIC_STALLS + 1))
        else
            [[ "$ms" -gt "$STATUS_MAX" ]] && STATUS_MAX=$ms
            [[ "$ms" -gt 250 ]] && STATUS_STALLS=$((STATUS_STALLS + 1))
        fi
    done
    sleep "$INTERVAL_S"
done

echo ""
echo "=== Summary ==="
echo "static asset  : max=${STATIC_MAX}ms  requests>250ms=${STATIC_STALLS}"
echo "location/status: max=${STATUS_MAX}ms  requests>250ms=${STATUS_STALLS}"
echo ""
if [[ "$STATIC_STALLS" -gt 0 ]]; then
    echo "VERDICT: the static asset (no device dependency) stalled — this points"
    echo "to the toupcam SDK binding holding the GIL during Open()/EnumV2(), not"
    echo "just the runtime.py locks. See docs/todo.md M10-024 / SYNC.md."
elif [[ "$STATUS_STALLS" -gt 0 ]]; then
    echo "VERDICT: /api/location/status stalled but the static asset did not —"
    echo "unexpected given M10-021/022 (mount/location path should be lock-free"
    echo "of camera opens); re-check the request path, this needs a closer look."
else
    echo "VERDICT: no stalls observed on either endpoint — M10-021/022's lock"
    echo "changes appear sufficient; no GIL-held SDK call blocking unrelated"
    echo "requests during camera connect."
fi
echo ""
echo "Also record from the server log (grep 'Camera connect+prime timing'):"
echo "  grep 'Camera connect+prime timing' ~/.SmartTScope/logs/server.log | tail -5"
