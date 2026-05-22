# camera_adapter Integration Design

**Date:** 2026-05-22
**Status:** Approved

## Background

`resources/camera_adapter/` is an externally maintained module that provides ToupTek camera
adapters, filter wheel support, guiding data models, and related configuration. Until now,
files were synced manually and ad-hoc, causing the Pi to diverge from the repo (the root cause
of the `RuntimeError: ToupTek: no camera matching` incident on 2026-05-22).

This design formalises the integration boundary so future releases are predictable and safe.

---

## Integration Model: Copy-on-Release

`smart_telescope/` imports nothing from `resources/`. When camera_adapter ships a new release,
a sync script copies the external-owned files into `smart_telescope/` verbatim. The person
running the sync reviews the diff, then commits.

There is no pip package, no git submodule, and no automated trigger. The user tells Claude
when a new release is available; Claude runs the sync.

---

## Ownership Table

### External-owned (copy verbatim on every release, never edit manually)

| Source (`resources/camera_adapter/`) | Destination (`smart_telescope/`) |
|---|---|
| `adapters/touptek/camera.py` | `adapters/touptek/camera.py` |
| `adapters/touptek/managed.py` | `adapters/touptek/managed.py` |
| `adapters/touptek/filter_wheel.py` | `adapters/touptek/filter_wheel.py` |
| `domain/guiding.py` | `domain/guiding.py` |
| `tools/camera_loadtest.py` | `tools/camera_loadtest.py` |
| `tools/guide_measuretest.py` | `tools/guide_measuretest.py` |
| `tests/unit/services/test_guide_measurement.py` | `tests/unit/services/test_guide_measurement.py` |

If a bug is found in an external-owned file, the fix request goes to the external party.
A workaround may be applied locally and must be annotated with `# SYNC-OVERRIDE` so it
is reviewed (and ideally removed) on the next sync.

### Smart_telescope-owned (consume camera_adapter APIs, we control content)

| File | External APIs consumed |
|---|---|
| `smart_telescope/config.py` | `CameraSpec`, `CoolingSpec`, `FilterWheelSpec`, `GuidingSpec` shape |
| `smart_telescope/runtime.py` | `SmartTouptekCamera`, `TouptekFilterWheel`, `get_camera_by_role()` pattern |
| All `api/` endpoints | Camera/mount/focuser ports (unchanged) |

When camera_adapter changes the API surface of any external-owned file, these smart_telescope-owned
files are updated manually as part of the release integration.

---

## Sync Script: `scripts/sync_camera_adapter.sh`

```
Usage:
  bash scripts/sync_camera_adapter.sh [--dry-run]

Behaviour:
  --dry-run   Diff source vs destination for each owned file.
              Prints a summary. Exits non-zero if any file differs.
  (live)      Copies all owned files from resources/camera_adapter/
              into their smart_telescope/ destinations.
              Prints a summary of changed files.
              Updates the "Last synced" entry in SYNC.md.
              Does NOT commit — the operator reviews and commits manually.
```

The script records the git hash of the HEAD commit at sync time into `SYNC.md`.

---

## SYNC.md (project root)

Tracks provenance and the ownership list in one place:

```markdown
# camera_adapter Sync State
Last synced: YYYY-MM-DD
Source commit: <git hash>

## Owned files
(ownership table)

## Pending external requirements
(list any requirements waiting for the external party)

## How to sync
bash scripts/sync_camera_adapter.sh --dry-run
bash scripts/sync_camera_adapter.sh
```

---

## This Release: Merge Steps

### 3a — Copy new files (no edits)

These files do not yet exist in `smart_telescope/` and are copied verbatim:

- `domain/guiding.py` — `GuideFrame`, `GuideMeasurement`, `WouldGuidePulse`, `GuideSourceState`
- `adapters/touptek/filter_wheel.py` — `TouptekFilterWheel`
- `tools/camera_loadtest.py` — multi-camera stress test CLI
- `tools/guide_measuretest.py` — measure-only guiding test CLI
- `tests/unit/services/test_guide_measurement.py` — unit tests for centroid & guide source selection

### 3b — Replace existing external-owned files

Compare camera_adapter version against current smart_telescope version; replace if the
camera_adapter version is newer or equivalent. Specific check: confirm that
`adapters/touptek/managed.py` in camera_adapter already contains the `connect() → False`
fix (instead of raising RuntimeError) that was hand-patched earlier; if not, retain the
fix as a `# SYNC-OVERRIDE` annotation until the external party ships it.

### 3c — Update smart_telescope-owned files

**`smart_telescope/config.py`**: add three new dataclasses and their parse functions:
- `CoolingSpec` — `default_target_c: float`
- `FilterWheelSpec` — `enabled, backend, model, name, wheel_id, settle_s, active_camera_role`
- `GuidingSpec` — `primary_role, allow_fallback, fallback_after_bad_frames, max_frame_age_s,
  centroid_roi_px, min_peak_snr, saturation_fraction, measure_only`
- Module-level constants: `COOLING`, `FILTER_WHEEL`, `GUIDING`

**`smart_telescope/runtime.py`**: add two methods to `RuntimeContext`:
- `get_camera_by_role(role: str) → CameraPort` — looks up role in `CAMERA_SPECS`, opens/caches
  a `SmartTouptekCamera` for that role (or `ToupcamCamera` fallback), raises `HTTPException 503`
  if role not configured
- `get_filter_wheel() → TouptekFilterWheel | None` — lazily initialises from `FILTER_WHEEL` config;
  returns `None` if not enabled

---

## Sync Script Implementation

```bash
#!/usr/bin/env bash
# sync_camera_adapter.sh — copies external-owned files into smart_telescope/
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SRC="$ROOT/resources/camera_adapter"
DST="$ROOT/smart_telescope"
DRY_RUN=false
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN=true

FILES=(
  "adapters/touptek/camera.py"
  "adapters/touptek/managed.py"
  "adapters/touptek/filter_wheel.py"
  "domain/guiding.py"
  "tools/camera_loadtest.py"
  "tools/guide_measuretest.py"
)
TEST_FILES=(
  "tests/unit/services/test_guide_measurement.py"
)

changed=0
for f in "${FILES[@]}"; do
  src="$SRC/$f"; dst="$DST/$f"
  if ! diff -q "$src" "$dst" &>/dev/null 2>&1; then
    echo "CHANGED  $f"
    $DRY_RUN || { mkdir -p "$(dirname "$dst")"; cp "$src" "$dst"; }
    ((changed++)) || true
  else
    echo "ok       $f"
  fi
done
for f in "${TEST_FILES[@]}"; do
  src="$SRC/$f"; dst="$ROOT/$f"
  if ! diff -q "$src" "$dst" &>/dev/null 2>&1; then
    echo "CHANGED  $f"
    $DRY_RUN || { mkdir -p "$(dirname "$dst")"; cp "$src" "$dst"; }
    ((changed++)) || true
  else
    echo "ok       $f"
  fi
done

if $DRY_RUN; then
  [[ $changed -eq 0 ]] && echo "No drift detected." || { echo "$changed file(s) differ."; exit 1; }
else
  HASH=$(cd "$SRC" && git log -1 --format="%H" 2>/dev/null || echo "unknown")
  DATE=$(date '+%Y-%m-%d')
  sed -i "s/^Last synced:.*/Last synced: $DATE/" "$ROOT/SYNC.md" 2>/dev/null || true
  sed -i "s/^Source commit:.*/Source commit: $HASH/" "$ROOT/SYNC.md" 2>/dev/null || true
  echo "Sync complete. $changed file(s) updated. Review diff, then commit."
fi
```

---

## Future Requirements Process

When a new feature requires changes to an external-owned file:

1. Record it in `SYNC.md` under "Pending external requirements" with a short description.
2. Do **not** edit the external-owned file directly.
3. When the external party delivers the update, run the sync and integrate.
4. If a workaround in a smart_telescope-owned file is needed in the meantime, annotate it
   clearly; remove the workaround after the sync.

---

## Testing

- `tests/unit/services/test_guide_measurement.py` is copied verbatim from camera_adapter and
  runs against `smart_telescope.services.guide_measurement` (that module is expected to exist
  in a subsequent camera_adapter release; for now the test file is copied but may be skipped).
- The sync script itself is tested by running `--dry-run` after a known-clean sync; it must
  exit 0.
- After each release integration, run `pytest tests/` to confirm no regressions.
