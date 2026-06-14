# OnStepAdapter Sync State

Last synced: 2026-06-14
Source: https://github.com/tschoenfelder/OnStepAdapter
Version: 0.3.0

Never edit files inside the installed `onstep_adapter` PyPI package directly.
Implementation files are synced from the GitHub source into `smart_telescope/adapters/onstep/`.

## Owned files (synced from OnStepAdapter GitHub release on each update)

| Source (GitHub: tschoenfelder/OnStepAdapter) | Destination (smart_telescope/) |
|---|---|
| smart_telescope/adapters/onstep/__init__.py | adapters/onstep/__init__.py |
| smart_telescope/adapters/onstep/client.py | adapters/onstep/client.py |
| smart_telescope/adapters/onstep/focuser.py | adapters/onstep/focuser.py |
| smart_telescope/adapters/onstep/firmware_proof.py | adapters/onstep/firmware_proof.py |
| smart_telescope/adapters/onstep/mount.py | adapters/onstep/mount.py |
| smart_telescope/adapters/onstep/results.py | adapters/onstep/results.py |
| smart_telescope/adapters/onstep/safety.py | adapters/onstep/safety.py |
| smart_telescope/adapters/onstep/serial_bus.py | adapters/onstep/serial_bus.py |
| smart_telescope/adapters/onstep/state_store.py | adapters/onstep/state_store.py |

## Active SYNC-OVERRIDEs

| File | Override | Waiting for |
|---|---|---|
| smart_telescope/adapters/onstep/mount.py | `def move(self, direction: str, move_ms: int) -> bool` — delegates to `self.mechanical_manual_move(direction, move_ms, cancel_check=None)` (center/slew rate via `:Me#`/`:Mw#` etc.). Faster than the v0.2.0 `guide()` workaround. Upstream still needs `move()` with exact MountPort signature. | REQ-1 |
| smart_telescope/adapters/onstep/mount.py | `def set_park_position(self) -> bool` — delegates to `self.set_park_position_from_current(confirmed_safe=True).ok`. Sends `:hQ#` and persists to state store. Upstream needs `set_park_position() → bool` matching MountPort signature. | REQ-2 |

## Pending external requirements

| ID | Request | Status (v0.3.0) | Opened |
|---|---|---|---|
| REQ-1 | Add `move(direction: str, move_ms: int) -> bool` to `OnStepMount` with exact MountPort signature. v0.3.0 added `mechanical_manual_move()` at center rate — SYNC-OVERRIDE updated to use it (faster than guide rate). Remaining gap: upstream signature differs. | **IMPROVED** — SYNC-OVERRIDE upgraded | 2026-06-14 |
| REQ-2 `get` | `get_park_position() → MountPosition \| None` via state store (not serial). | **DONE** — native in v0.3.0; `GpA#`/`GpD#` removed | 2026-06-14 |
| REQ-2 `set` | `set_park_position() → bool` with exact MountPort signature. v0.3.0 added `set_park_position_from_current()` — SYNC-OVERRIDE wraps it. Remaining gap: upstream signature differs. | **PARTIAL** — SYNC-OVERRIDE added | 2026-06-14 |
| REQ-3 | Sticky AT_HOME state (preserve HOME flag until mount moves after `:hC#`). Workaround: maintained in `DeviceStateService`. | **Open** | 2026-06-14 |
| REQ-4 | Hardware watchdog with configurable timeout and `watchdog_warning` property. Workaround: maintained in `DeviceStateService`. | **Open** | 2026-06-14 |
| REQ-5 | Command audit trail (`last_command`, `last_command_at`, `last_command_error`) as properties on `OnStepMount`. Workaround: maintained in `DeviceStateService`. | **Open** | 2026-06-14 |

## How to sync

When a new OnStepAdapter release ships:
```bash
# 1. Download the new source files from the GitHub release
# 2. Copy each file from the table above into smart_telescope/adapters/onstep/
# 3. Re-apply all SYNC-OVERRIDEs listed above
# 4. Run: python -m pytest tests/unit/adapters/onstep/ -q
# 5. Update "Last synced" and "Version" at the top of this file
# 6. Commit: git commit -m "chore: sync onstep_adapter vX.Y.Z"
```

## Smart_telescope-owned files that consume OnStepAdapter APIs

| File | External APIs consumed |
|---|---|
| `smart_telescope/config.py` | `OnStepSafetyConfig` constructor (via `build_onstep_safety_config()`) |
| `smart_telescope/runtime.py` | `OnStepClient(port, safety_config=...)`, `client.mount`, `client.focuser`, `client.connect()`, `client.close()` |
| `smart_telescope/services/device_state.py` | `mount.safety_lock` (via `getattr`, optional) |
| `smart_telescope/services/mount_operations.py` | `OnStepSafetyError` (imported with fallback) |
| `smart_telescope/api/mount.py` | `OnStepSafetyError` (imported with fallback); `MountStatus.safety_violation` field |

---

# camera_adapter Sync State

Last synced: 2026-05-22
Source commit: 03d5823a4e26172c55dfd3df4e18fd38e72dd8c0

## Owned files (copy verbatim from resources/camera_adapter/ on each release)

| Source (resources/camera_adapter/) | Destination (smart_telescope/) |
|---|---|
| adapters/touptek/camera.py | adapters/touptek/camera.py |
| adapters/touptek/managed.py | adapters/touptek/managed.py |
| adapters/touptek/filter_wheel.py | adapters/touptek/filter_wheel.py |
| domain/guiding.py | domain/guiding.py |
| tools/camera_loadtest.py | tools/camera_loadtest.py |
| tools/guide_measuretest.py | tools/guide_measuretest.py |
| tests/unit/services/test_guide_measurement.py | tests/unit/services/test_guide_measurement.py |

## Active SYNC-OVERRIDEs

| File | Override | Waiting for |
|---|---|---|
| smart_telescope/adapters/touptek/managed.py | `connect()` returns `False` instead of raising `RuntimeError` when no device is found | camera_adapter to ship the fix |
| smart_telescope/adapters/touptek/camera.py | Added `_FLAG_RAW16`, `_detect_pixel_shift()`, `self._pixel_shift`; `capture()` right-shifts MSB-aligned sub-16-bit data to native ADC range and writes `BITDEPTH` header; `get_bit_depth()` returns sensor native depth | camera_adapter to incorporate pixel-shift detection |
| smart_telescope/adapters/touptek/managed.py | Same pixel-shift detection as camera.py: `_FLAG_RAW16`, `_detect_pixel_shift()`, `self._pixel_shift`, right-shift in `capture()`, `BITDEPTH` header, updated `get_bit_depth()` | camera_adapter to incorporate pixel-shift detection |

## Pending external requirements

_(none)_

## How to sync

```bash
bash scripts/sync_camera_adapter.sh --dry-run   # check for drift
bash scripts/sync_camera_adapter.sh              # apply update
# review diff, update this file if needed, then commit
```

## Smart_telescope-owned files that consume camera_adapter APIs

When camera_adapter changes API surface, manually update these:

| File | External APIs consumed |
|---|---|
| `smart_telescope/config.py` | `CameraSpec`, `CoolingSpec`, `FilterWheelSpec`, `GuidingSpec` shape |
| `smart_telescope/runtime.py` | `SmartTouptekCamera`, `TouptekFilterWheel`, `get_camera_by_role` pattern |
