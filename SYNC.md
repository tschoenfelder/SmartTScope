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
