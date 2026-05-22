# camera_adapter Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge `resources/camera_adapter` into `smart_telescope/` using the copy-on-release model defined in the design spec, and create the sync infrastructure for future releases.

**Architecture:** External-owned files (adapters, domain models, tools) are copied verbatim from `resources/camera_adapter/`. Smart-telescope-owned files (`config.py`, `runtime.py`) are updated to consume the new APIs. A sync script and `SYNC.md` make future releases repeatable.

**Tech Stack:** Python 3.13, FastAPI, toupcam SDK (optional at runtime), pytest

---

## File Map

| Action | File |
|--------|------|
| Create | `smart_telescope/domain/__init__.py` |
| Create | `smart_telescope/domain/guiding.py` |
| Create | `smart_telescope/adapters/touptek/filter_wheel.py` |
| Create | `smart_telescope/tools/__init__.py` |
| Create | `smart_telescope/tools/camera_loadtest.py` |
| Create | `smart_telescope/tools/guide_measuretest.py` |
| Create | `tests/unit/services/test_guide_measurement.py` |
| Replace | `smart_telescope/adapters/touptek/camera.py` |
| Update | `smart_telescope/adapters/touptek/managed.py` (keep SYNC-OVERRIDE fix) |
| Update | `smart_telescope/config.py` (add CoolingSpec, FilterWheelSpec, GuidingSpec) |
| Update | `smart_telescope/runtime.py` (add role cameras, filter wheel, validation) |
| Create | `scripts/sync_camera_adapter.sh` |
| Create | `SYNC.md` |

---

### Task 1: Copy new domain and adapter files

**Files:**
- Create: `smart_telescope/domain/__init__.py`
- Create: `smart_telescope/domain/guiding.py`
- Create: `smart_telescope/adapters/touptek/filter_wheel.py`
- Create: `smart_telescope/tools/__init__.py`
- Create: `smart_telescope/tools/camera_loadtest.py`
- Create: `smart_telescope/tools/guide_measuretest.py`
- Create: `tests/unit/services/test_guide_measurement.py`

- [ ] **Step 1: Create domain package and copy guiding.py**

```bash
mkdir -p smart_telescope/domain
touch smart_telescope/domain/__init__.py
cp resources/camera_adapter/domain/guiding.py smart_telescope/domain/guiding.py
```

- [ ] **Step 2: Copy filter_wheel.py**

```bash
cp resources/camera_adapter/adapters/touptek/filter_wheel.py \
   smart_telescope/adapters/touptek/filter_wheel.py
```

- [ ] **Step 3: Create tools package and copy tools**

```bash
mkdir -p smart_telescope/tools
touch smart_telescope/tools/__init__.py
cp resources/camera_adapter/tools/camera_loadtest.py smart_telescope/tools/camera_loadtest.py
cp resources/camera_adapter/tools/guide_measuretest.py smart_telescope/tools/guide_measuretest.py
```

- [ ] **Step 4: Copy test file**

```bash
mkdir -p tests/unit/services
cp resources/camera_adapter/tests/unit/services/test_guide_measurement.py \
   tests/unit/services/test_guide_measurement.py
```

- [ ] **Step 5: Verify syntax of all copied files**

```bash
python -c "
import ast, sys
files = [
    'smart_telescope/domain/guiding.py',
    'smart_telescope/adapters/touptek/filter_wheel.py',
    'smart_telescope/tools/camera_loadtest.py',
    'smart_telescope/tools/guide_measuretest.py',
    'tests/unit/services/test_guide_measurement.py',
]
for f in files:
    try:
        ast.parse(open(f).read())
        print(f'OK  {f}')
    except SyntaxError as e:
        print(f'ERR {f}: {e}'); sys.exit(1)
"
```
Expected: `OK` for all five files.

- [ ] **Step 6: Commit**

```bash
git add smart_telescope/domain/ smart_telescope/adapters/touptek/filter_wheel.py \
        smart_telescope/tools/ tests/unit/services/test_guide_measurement.py
git commit -m "feat(sync): copy new domain/guiding, filter_wheel, tools from camera_adapter"
```

---

### Task 2: Replace camera.py with camera_adapter version

**Files:**
- Replace: `smart_telescope/adapters/touptek/camera.py`

The camera_adapter version adds `camera_id`, `model`, `name`, `capture_mode`, `setup_profile`, `startup_delay_s`, `startup_monitor_interval_s`, `prime_attempts`, `prime_timeout_s`, `prime_exposure_s` constructor parameters and several SDK option constants that the smart_telescope version omits.

- [ ] **Step 1: Replace the file**

```bash
cp resources/camera_adapter/adapters/touptek/camera.py \
   smart_telescope/adapters/touptek/camera.py
```

- [ ] **Step 2: Verify syntax**

```bash
python -c "import ast; ast.parse(open('smart_telescope/adapters/touptek/camera.py').read()); print('OK')"
```

- [ ] **Step 3: Commit**

```bash
git add smart_telescope/adapters/touptek/camera.py
git commit -m "feat(sync): replace camera.py with camera_adapter version (richer constructor)"
```

---

### Task 3: Update managed.py — take upstream changes, keep SYNC-OVERRIDE fix

**Files:**
- Update: `smart_telescope/adapters/touptek/managed.py`

The only diff between camera_adapter's managed.py and ours is the `connect()` → `return False` fix (our version) vs `raise RuntimeError` (theirs). All other content is identical. We keep our fix annotated as `# SYNC-OVERRIDE` until the external party ships it.

- [ ] **Step 1: Confirm the diff is only the connect() fix**

```bash
diff resources/camera_adapter/adapters/touptek/managed.py \
     smart_telescope/adapters/touptek/managed.py
```

Expected: only 13 lines of diff, all in the `if device is None:` block around line 121–127.

- [ ] **Step 2: No file change needed — annotate the override**

The current `smart_telescope/adapters/touptek/managed.py` at lines ~119–127 reads:

```python
            if device is None:
                listing = ", ".join(f"{i}:{d.displayname}" for i, d in enumerate(devices)) or "none"
                # Log and return False so callers can fall back gracefully (e.g. to MockCamera).
                _log.error(
                    "ToupTek: no camera matching index=%s, id=%r, model=%r, name=%r. Found: %s",
                    self._index, self._camera_id_hint, self._model_selector,
                    self._name_selector, listing,
                )
                return False
```

Add the `# SYNC-OVERRIDE` annotation to the comment line so it reads:

```python
            if device is None:
                listing = ", ".join(f"{i}:{d.displayname}" for i, d in enumerate(devices)) or "none"
                # SYNC-OVERRIDE: return False instead of raising — remove after camera_adapter ships the fix.
                _log.error(
                    "ToupTek: no camera matching index=%s, id=%r, model=%r, name=%r. Found: %s",
                    self._index, self._camera_id_hint, self._model_selector,
                    self._name_selector, listing,
                )
                return False
```

- [ ] **Step 3: Commit**

```bash
git add smart_telescope/adapters/touptek/managed.py
git commit -m "chore(sync): annotate managed.py connect() fix as SYNC-OVERRIDE"
```

---

### Task 4: Add CoolingSpec, FilterWheelSpec, GuidingSpec to config.py

**Files:**
- Modify: `smart_telescope/config.py` (after the existing `CAMERA_SPECS` block, before `_parse_camera_serials`)

- [ ] **Step 1: Insert the three new dataclasses and their parse functions**

In `smart_telescope/config.py`, find the line:

```python
def _parse_camera_serials() -> dict[str, str]:
```

Insert the following block immediately before it:

```python
@dataclass(frozen=True)
class CoolingSpec:
    default_target_c: float = -10.0


@dataclass(frozen=True)
class FilterWheelSpec:
    enabled: bool = False
    backend: str = "native"
    model: str = ""
    name: str = ""
    wheel_id: str = ""
    settle_s: float = 1.5
    active_camera_role: str = "main"


@dataclass(frozen=True)
class GuidingSpec:
    primary_role: str = "guide"
    allow_fallback: bool = True
    fallback_after_bad_frames: int = 3
    max_frame_age_s: float = 2.0
    centroid_roi_px: int = 32
    min_peak_snr: float = 5.0
    saturation_fraction: float = 0.98
    measure_only: bool = True


def _parse_cooling_spec() -> CoolingSpec:
    section = _cfg.get("cooling", {})
    return CoolingSpec(default_target_c=float(section.get("default_target_c", -10.0)))


def _parse_filter_wheel_spec() -> FilterWheelSpec:
    section = _cfg.get("filter_wheel", {})
    return FilterWheelSpec(
        enabled=bool(section.get("enabled", False)),
        backend=str(section.get("backend", "native")),
        model=str(section.get("model", "")),
        name=str(section.get("name", "")),
        wheel_id=str(section.get("wheel_id", "")),
        settle_s=float(section.get("settle_s", 1.5)),
        active_camera_role=str(section.get("active_camera_role", "main")),
    )


def _parse_guiding_spec() -> GuidingSpec:
    section = _cfg.get("guiding", {})
    return GuidingSpec(
        primary_role=str(section.get("primary_role", "guide")),
        allow_fallback=bool(section.get("allow_fallback", True)),
        fallback_after_bad_frames=int(section.get("fallback_after_bad_frames", 3)),
        max_frame_age_s=float(section.get("max_frame_age_s", 2.0)),
        centroid_roi_px=int(section.get("centroid_roi_px", 32)),
        min_peak_snr=float(section.get("min_peak_snr", 5.0)),
        saturation_fraction=float(section.get("saturation_fraction", 0.98)),
        measure_only=bool(section.get("measure_only", True)),
    )


COOLING: CoolingSpec = _parse_cooling_spec()
FILTER_WHEEL: FilterWheelSpec = _parse_filter_wheel_spec()
GUIDING: GuidingSpec = _parse_guiding_spec()

```

- [ ] **Step 2: Verify config.py parses cleanly and the new symbols are importable**

```bash
python -c "
from smart_telescope.config import COOLING, FILTER_WHEEL, GUIDING, CoolingSpec, FilterWheelSpec, GuidingSpec
print('COOLING:', COOLING)
print('FILTER_WHEEL:', FILTER_WHEEL)
print('GUIDING:', GUIDING)
"
```

Expected: three lines printed, each showing a dataclass with default values.

- [ ] **Step 3: Commit**

```bash
git add smart_telescope/config.py
git commit -m "feat(sync): add CoolingSpec, FilterWheelSpec, GuidingSpec to config"
```

---

### Task 5: Update runtime.py — role cameras, filter wheel, role validation

**Files:**
- Modify: `smart_telescope/runtime.py`

Five targeted changes. Apply them in order.

- [ ] **Step 1: Add `_role_cameras` and `_filter_wheel` to `__init__`**

Find this block in `RuntimeContext.__init__`:

```python
        self._preview_cameras: dict[int, CameraPort] = {}
        self._adapters_built: bool = False
```

Replace with:

```python
        self._preview_cameras: dict[int, CameraPort] = {}
        self._role_cameras: dict[str, CameraPort] = {}
        self._filter_wheel: object | None = None
        self._adapters_built: bool = False
```

- [ ] **Step 2: Add `_validate_camera_role_ownership` call to `connect_devices` and add the method**

Find this block in `connect_devices`:

```python
            if not self._adapters_built:
                self._camera, self._mount, self._focuser = _build_adapters(self)
```

Replace with:

```python
            if not self._adapters_built:
                self._validate_camera_role_ownership(_config.CAMERA_SPECS)
                self._camera, self._mount, self._focuser = _build_adapters(self)
```

Then add the method after `connect_devices` (before `shutdown`):

```python
    def _validate_camera_role_ownership(self, specs: dict[str, object]) -> None:
        if not specs:
            return
        try:
            from .adapters.touptek.managed import validate_unique_camera_roles
            validate_unique_camera_roles(specs)
        except ImportError:
            return
```

- [ ] **Step 3: Update `shutdown` to close role cameras and filter wheel**

Find this block in `shutdown`:

```python
        for cam in list(self._preview_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        if self._preview_cameras:
            _log.info("Shutdown: %d secondary camera handle(s) closed", len(self._preview_cameras))
```

Replace with:

```python
        for cam in list(self._preview_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        for cam in list(self._role_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        if self._filter_wheel is not None:
            with contextlib.suppress(Exception):
                self._filter_wheel.disconnect()  # type: ignore[attr-defined]
        if self._preview_cameras or self._role_cameras:
            _log.info(
                "Shutdown: %d preview + %d role camera handle(s) closed",
                len(self._preview_cameras), len(self._role_cameras),
            )
```

- [ ] **Step 4: Update `disconnect_devices` and `reset_for_tests` to clear new state**

In `disconnect_devices`, find:

```python
        for cam in list(self._preview_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        self._camera = None
        self._mount = None
        self._focuser = None
        self._preview_cameras = {}
        self._adapters_built = False
```

Replace with:

```python
        for cam in list(self._preview_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        for cam in list(self._role_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        if self._filter_wheel is not None:
            with contextlib.suppress(Exception):
                self._filter_wheel.disconnect()  # type: ignore[attr-defined]
        self._camera = None
        self._mount = None
        self._focuser = None
        self._preview_cameras = {}
        self._role_cameras = {}
        self._filter_wheel = None
        self._adapters_built = False
```

In `reset_for_tests`, find:

```python
        self._adapters_built = False
        self._hardware_mode = "mock"
        self._preview_cameras = {}
```

Replace with:

```python
        self._adapters_built = False
        self._hardware_mode = "mock"
        self._preview_cameras = {}
        self._role_cameras = {}
        self._filter_wheel = None
```

- [ ] **Step 5: Replace `get_camera_by_role` and add `get_filter_wheel`**

Find and replace the existing `get_camera_by_role` method:

```python
    def get_camera_by_role(self, role: str) -> CameraPort:
        from . import config
        from fastapi import HTTPException

        if role not in config.CAMERAS:
            configured = list(config.CAMERAS.keys()) or ["(none)"]
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Camera role '{role}' not configured. "
                    f"Configured roles: {', '.join(configured)}. "
                    f"Add it to [cameras] in smart_telescope.toml."
                ),
            )
        return self.get_preview_camera(config.CAMERAS[role])
```

Replace with:

```python
    def get_camera_by_role(self, role: str) -> CameraPort:
        from . import config
        from fastapi import HTTPException

        if role in config.CAMERA_SPECS and config.CAMERA_SPECS[role].enabled:
            self.connect_devices()
            if role == "main" and self._camera is not None:
                return self._camera
            if role not in self._role_cameras:
                spec = config.CAMERA_SPECS[role]
                if spec.backend.lower() != "native":
                    raise HTTPException(
                        status_code=501,
                        detail=(
                            f"Camera role '{role}' requests backend '{spec.backend}'. "
                            "The MVP runtime currently supports native cameras only."
                        ),
                    )
                from .adapters.touptek.managed import SmartTouptekCamera
                cam = SmartTouptekCamera(
                    index=spec.index or 0,
                    camera_id=spec.camera_id or None,
                    model=spec.model or None,
                    name=spec.name or None,
                    capture_mode=spec.capture_mode,
                    setup_profile=spec.setup_profile,
                    startup_delay_s=spec.startup_delay_s,
                    startup_monitor_interval_s=spec.startup_monitor_interval_s,
                    prime_attempts=spec.prime_attempts,
                    prime_timeout_s=spec.prime_timeout_s,
                    prime_exposure_s=spec.prime_exposure_s,
                    bit_depth=spec.bit_depth,
                )
                if not cam.connect():
                    raise RuntimeError(f"Camera role {role!r} failed to connect — no device found")
                cam.set_gain(spec.gain)
                if spec.offset_hcg or spec.offset_lcg:
                    cam.set_black_level(spec.offset_for("HCG"))
                self._role_cameras[role] = cam
                _log.info("get_camera_by_role(%s): connected %s", role, cam.get_logical_name())
            return self._role_cameras[role]

        if role not in config.CAMERAS:
            configured = list(config.CAMERAS.keys()) or ["(none)"]
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Camera role '{role}' not configured. "
                    f"Configured roles: {', '.join(configured)}. "
                    f"Add it to [cameras] in smart_telescope.toml."
                ),
            )
        return self.get_preview_camera(config.CAMERAS[role])
```

Then add `get_filter_wheel` immediately after `get_focuser`:

```python
    def get_filter_wheel(self) -> object:
        from . import config

        if not config.FILTER_WHEEL.enabled:
            raise RuntimeError("Filter wheel is disabled in config")
        if self._filter_wheel is None:
            spec = config.FILTER_WHEEL
            if spec.backend.lower() != "native":
                raise RuntimeError(f"Unsupported filter wheel backend: {spec.backend}")
            from .adapters.touptek.filter_wheel import TouptekFilterWheel
            wheel = TouptekFilterWheel(
                wheel_id=spec.wheel_id or None,
                model=spec.model or None,
                name=spec.name or None,
                settle_s=spec.settle_s,
            )
            if not wheel.connect():
                raise RuntimeError("ToupTek filter wheel failed to connect")
            self._filter_wheel = wheel
        return self._filter_wheel
```

- [ ] **Step 6: Verify syntax**

```bash
python -c "import ast; ast.parse(open('smart_telescope/runtime.py').read()); print('OK')"
```

- [ ] **Step 7: Smoke-test the app still imports cleanly**

```bash
python -c "from smart_telescope.app import app; print('app OK')"
```

- [ ] **Step 8: Commit**

```bash
git add smart_telescope/runtime.py
git commit -m "feat(sync): add role cameras, filter wheel, role validation to RuntimeContext"
```

---

### Task 6: Create sync script

**Files:**
- Create: `scripts/sync_camera_adapter.sh`

- [ ] **Step 1: Write the script**

```bash
cat > scripts/sync_camera_adapter.sh << 'SCRIPT'
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

# Owned files: source path (relative to resources/camera_adapter/) → destination prefix
FILES=(
  "adapters/touptek/camera.py"
  "adapters/touptek/managed.py"
  "adapters/touptek/filter_wheel.py"
  "domain/guiding.py"
  "tools/camera_loadtest.py"
  "tools/guide_measuretest.py"
)

# Test files: source relative to resources/camera_adapter/ → destination relative to repo root
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
SCRIPT
chmod +x scripts/sync_camera_adapter.sh
```

- [ ] **Step 2: Verify the script runs in dry-run mode**

```bash
bash scripts/sync_camera_adapter.sh --dry-run
```

Expected: all files show `ok` or `CHANGED` (managed.py will show CHANGED due to the SYNC-OVERRIDE). Exit 0 if no unexpected drift.

- [ ] **Step 3: Commit**

```bash
git add scripts/sync_camera_adapter.sh
git commit -m "feat(sync): add sync_camera_adapter.sh script"
```

---

### Task 7: Create SYNC.md

**Files:**
- Create: `SYNC.md`

- [ ] **Step 1: Write SYNC.md**

```bash
HASH=$(git log -1 --format="%H" -- resources/camera_adapter 2>/dev/null || echo "unknown")
cat > SYNC.md << EOF
# camera_adapter Sync State

Last synced: 2026-05-22
Source commit: $HASH

## Owned files (copy verbatim from resources/camera_adapter/ on each release)

| Source | Destination |
|--------|-------------|
| adapters/touptek/camera.py | smart_telescope/adapters/touptek/camera.py |
| adapters/touptek/managed.py | smart_telescope/adapters/touptek/managed.py |
| adapters/touptek/filter_wheel.py | smart_telescope/adapters/touptek/filter_wheel.py |
| domain/guiding.py | smart_telescope/domain/guiding.py |
| tools/camera_loadtest.py | smart_telescope/tools/camera_loadtest.py |
| tools/guide_measuretest.py | smart_telescope/tools/guide_measuretest.py |
| tests/unit/services/test_guide_measurement.py | tests/unit/services/test_guide_measurement.py |

## Active SYNC-OVERRIDEs

| File | Override | Waiting for |
|------|----------|-------------|
| smart_telescope/adapters/touptek/managed.py | connect() returns False instead of raising RuntimeError when no device found | camera_adapter to ship the fix |

## Pending external requirements

_(none)_

## How to sync

\`\`\`bash
bash scripts/sync_camera_adapter.sh --dry-run   # check for drift
bash scripts/sync_camera_adapter.sh              # apply update
# review diff, then commit
\`\`\`

## Smart_telescope-owned files that consume camera_adapter APIs

When camera_adapter changes API surface, manually update these:

- \`smart_telescope/config.py\` — CameraSpec, CoolingSpec, FilterWheelSpec, GuidingSpec shape
- \`smart_telescope/runtime.py\` — SmartTouptekCamera, TouptekFilterWheel, get_camera_by_role pattern
EOF
```

- [ ] **Step 2: Commit**

```bash
git add SYNC.md
git commit -m "docs(sync): add SYNC.md tracking camera_adapter sync state"
```

---

### Task 8: Push and verify

- [ ] **Step 1: Run syntax check across all changed files**

```bash
python -c "
import ast, sys
files = [
    'smart_telescope/domain/guiding.py',
    'smart_telescope/adapters/touptek/filter_wheel.py',
    'smart_telescope/adapters/touptek/camera.py',
    'smart_telescope/adapters/touptek/managed.py',
    'smart_telescope/config.py',
    'smart_telescope/runtime.py',
]
for f in files:
    try:
        ast.parse(open(f).read())
        print(f'OK  {f}')
    except SyntaxError as e:
        print(f'ERR {f}: {e}'); sys.exit(1)
"
```

- [ ] **Step 2: Smoke-test app import**

```bash
python -c "from smart_telescope.app import app; print('app import OK')"
```

- [ ] **Step 3: Run drift check**

```bash
bash scripts/sync_camera_adapter.sh --dry-run
```

Expected: only `managed.py` shows `CHANGED` (the SYNC-OVERRIDE), all others `ok`.

- [ ] **Step 4: Push**

```bash
git push
```
