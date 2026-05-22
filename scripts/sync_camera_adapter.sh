#!/usr/bin/env bash
# sync_camera_adapter.sh — sync external-owned files from resources/camera_adapter/
# into smart_telescope/.  Run after each camera_adapter release.
#
# Usage:
#   bash scripts/sync_camera_adapter.sh [--dry-run]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$ROOT/resources/camera_adapter"
DST="$ROOT/smart_telescope"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

# Files owned by camera_adapter (relative to resources/camera_adapter/ → smart_telescope/)
FILES=(
  "adapters/touptek/camera.py"
  "adapters/touptek/managed.py"
  "adapters/touptek/filter_wheel.py"
  "domain/guiding.py"
  "tools/camera_loadtest.py"
  "tools/guide_measuretest.py"
)

# Test files (relative to resources/camera_adapter/ → repo root)
TEST_FILES=(
  "tests/unit/services/test_guide_measurement.py"
)

changed=0

for f in "${FILES[@]}"; do
  src="$SRC/$f"
  dst="$DST/$f"
  if [[ ! -f "$src" ]]; then
    echo "MISSING  $src — skipping"
    continue
  fi
  if ! diff -q "$src" "$dst" &>/dev/null 2>&1; then
    echo "CHANGED  $f"
    if ! $DRY_RUN; then
      mkdir -p "$(dirname "$dst")"
      cp "$src" "$dst"
    fi
    ((changed++)) || true
  else
    echo "ok       $f"
  fi
done

for f in "${TEST_FILES[@]}"; do
  src="$SRC/$f"
  dst="$ROOT/$f"
  if [[ ! -f "$src" ]]; then
    echo "MISSING  $src — skipping"
    continue
  fi
  if ! diff -q "$src" "$dst" &>/dev/null 2>&1; then
    echo "CHANGED  $f"
    if ! $DRY_RUN; then
      mkdir -p "$(dirname "$dst")"
      cp "$src" "$dst"
    fi
    ((changed++)) || true
  else
    echo "ok       $f"
  fi
done

if $DRY_RUN; then
  echo ""
  if [[ $changed -eq 0 ]]; then
    echo "No drift detected — smart_telescope/ is in sync with camera_adapter."
  else
    echo "$changed file(s) differ from camera_adapter. Run without --dry-run to apply."
    exit 1
  fi
else
  HASH=$(cd "$ROOT" && git log -1 --format="%H" -- resources/camera_adapter 2>/dev/null || echo "unknown")
  DATE=$(date '+%Y-%m-%d')
  if [[ -f "$ROOT/SYNC.md" ]]; then
    sed -i "s/^Last synced:.*/Last synced: $DATE/" "$ROOT/SYNC.md" || true
    sed -i "s/^Source commit:.*/Source commit: $HASH/" "$ROOT/SYNC.md" || true
  fi
  echo ""
  echo "Sync complete. $changed file(s) updated."
  echo "Review the diff, update SYNC.md if needed, then commit."
fi
