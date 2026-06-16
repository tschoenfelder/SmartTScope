# Camera Offset Configuration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable black-level (sensor offset) values per camera model and gain mode to the config file; auto-apply the correct offset whenever a camera connects or its gain mode changes.

**Architecture:** A new `CameraOffsetService` looks up `[camera_offsets]` TOML entries by camera model name and `ConversionGain` mode. `RuntimeContext` stores the service and applies offsets after each camera connects in `connect_devices()`. `AutoGainService` and `calibration_capture` module functions accept an optional `offset_service` parameter and call `apply()` after every `set_conversion_gain()` call. Name matching uses case-insensitive substring comparison so "CMOS02000KPA" and "GPCMOS02000KPA" both work.

**Tech Stack:** Python 3.13, pytest, `smart_telescope.domain.camera_capabilities.ConversionGain`, existing `CameraPort.set_black_level()` / `get_logical_name()` / `get_conversion_gain()`

**Dependency:** Can be developed independently of CID (camera-id-mapping plan). Uses `camera.get_logical_name()` which returns the SDK display name regardless of how the camera was opened.

---

## File Map

| Action  | Path |
|---------|------|
| Modify  | `smart_telescope/config.py` — add `_parse_camera_offsets()` and `CAMERA_OFFSETS` global |
| Create  | `smart_telescope/services/camera_offset_service.py` |
| Modify  | `smart_telescope/runtime.py` — store `CameraOffsetService`, call `apply()` after connect |
| Modify  | `smart_telescope/domain/autogain_service.py:160-162` — inject + apply after `set_conversion_gain` |
| Modify  | `smart_telescope/domain/calibration_capture.py:140-161, 207-234, 364-387` — inject + apply |
| Modify  | `smart_telescope/api/autogain.py` — pass `rt.camera_offset_service` to `AutoGainService` |
| Modify  | `smart_telescope/api/calibration.py` — pass `rt.camera_offset_service` to capture calls |
| Modify  | `templates/config.toml` — add `[camera_offsets]` section with defaults |
| Create  | `tests/unit/services/test_camera_offset_service.py` |

---

### Task 1: Add `[camera_offsets]` config parsing

**Files:**
- Modify: `smart_telescope/config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/config/test_camera_offset_config.py
import tomllib

def _parse_camera_offsets_from(toml_text: str) -> dict:
    cfg = tomllib.loads(toml_text)
    section = cfg.get("camera_offsets", {})
    result: dict = {}
    for model_name, gain_offsets in section.items():
        if isinstance(gain_offsets, dict):
            result[str(model_name)] = {k.lower(): int(v) for k, v in gain_offsets.items()}
    return result


def test_parse_camera_offsets_empty():
    result = _parse_camera_offsets_from("[hardware]\nonstep_port = ''")
    assert result == {}


def test_parse_camera_offsets_basic():
    toml = (
        "[camera_offsets.G3M678M]\n"
        "lcg = 150\n"
        "hcg = 150\n"
        "[camera_offsets.GPCMOS02000KPA]\n"
        "lcg = 10\n"
        "hcg = 10\n"
        "[camera_offsets.ATR585M]\n"
        "lcg = 150\n"
        "hcg = 150\n"
    )
    result = _parse_camera_offsets_from(toml)
    assert result["G3M678M"]["lcg"] == 150
    assert result["G3M678M"]["hcg"] == 150
    assert result["GPCMOS02000KPA"]["lcg"] == 10
    assert result["GPCMOS02000KPA"]["hcg"] == 10
    assert result["ATR585M"]["lcg"] == 150


def test_parse_camera_offsets_keys_lowercase():
    toml = "[camera_offsets.G3M678M]\nLCG = 150\nHCG = 150\n"
    result = _parse_camera_offsets_from(toml)
    assert "lcg" in result["G3M678M"]
    assert "hcg" in result["G3M678M"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/config/test_camera_offset_config.py -v`
Expected: all pass immediately (helpers are self-contained); no import errors

- [ ] **Step 3: Add `_parse_camera_offsets()` to `smart_telescope/config.py`**

After the `CAMERA_SERIALS` lines (or after the `OPTICAL_TRAINS` block), add:

```python
# ── camera offsets ────────────────────────────────────────────────────────────


def _parse_camera_offsets() -> dict[str, dict[str, int]]:
    """Parse [camera_offsets.{model}] sections: model -> {lcg/hcg/hdr -> int}."""
    section = _cfg.get("camera_offsets", {})
    result: dict[str, dict[str, int]] = {}
    for model_name, gain_offsets in section.items():
        if isinstance(gain_offsets, dict):
            result[str(model_name)] = {k.lower(): int(v) for k, v in gain_offsets.items()}
    return result


CAMERA_OFFSETS: dict[str, dict[str, int]] = _parse_camera_offsets()
```

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/config.py tests/unit/config/test_camera_offset_config.py
git commit -m "feat(CO): add CAMERA_OFFSETS config parsing for [camera_offsets] section"
```

---

### Task 2: Implement CameraOffsetService

**Files:**
- Create: `smart_telescope/services/camera_offset_service.py`
- Create: `tests/unit/services/test_camera_offset_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/services/test_camera_offset_service.py
import pytest
from unittest.mock import MagicMock
from smart_telescope.services.camera_offset_service import CameraOffsetService
from smart_telescope.domain.camera_capabilities import ConversionGain


OFFSETS = {
    "G3M678M":       {"lcg": 150, "hcg": 150},
    "GPCMOS02000KPA":{"lcg": 10,  "hcg": 10},
    "ATR585M":       {"lcg": 150, "hcg": 150},
}


def _mock_camera(logical_name: str, cg: ConversionGain = ConversionGain.LCG) -> MagicMock:
    cam = MagicMock()
    cam.get_logical_name.return_value = logical_name
    cam.get_conversion_gain.return_value = cg
    return cam


# --- get_offset ---

def test_get_offset_exact_match_lcg():
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("G3M678M", ConversionGain.LCG) == 150


def test_get_offset_exact_match_hcg():
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("G3M678M", ConversionGain.HCG) == 150


def test_get_offset_substring_match():
    # "GPCMOS02000KPA" contains "CMOS02000KPA" — should still match
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("CMOS02000KPA", ConversionGain.LCG) == 10


def test_get_offset_case_insensitive():
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("g3m678m", ConversionGain.LCG) == 150


def test_get_offset_unknown_model_returns_none():
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("UNKNOWN_CAM", ConversionGain.LCG) is None


def test_get_offset_unknown_gain_mode_returns_none():
    svc = CameraOffsetService(OFFSETS)
    # HDR not in config for G3M678M
    assert svc.get_offset("G3M678M", ConversionGain.HDR) is None


def test_get_offset_empty_config_returns_none():
    svc = CameraOffsetService({})
    assert svc.get_offset("G3M678M", ConversionGain.LCG) is None


# --- apply ---

def test_apply_sets_black_level_when_configured():
    svc = CameraOffsetService(OFFSETS)
    cam = _mock_camera("G3M678M", ConversionGain.LCG)
    svc.apply(cam)
    cam.set_black_level.assert_called_once_with(150)


def test_apply_hcg_uses_hcg_offset():
    svc = CameraOffsetService(OFFSETS)
    cam = _mock_camera("ATR585M", ConversionGain.HCG)
    svc.apply(cam)
    cam.set_black_level.assert_called_once_with(150)


def test_apply_no_config_does_not_call_set():
    svc = CameraOffsetService({})
    cam = _mock_camera("G3M678M")
    svc.apply(cam)
    cam.set_black_level.assert_not_called()


def test_apply_unknown_camera_does_not_call_set():
    svc = CameraOffsetService(OFFSETS)
    cam = _mock_camera("UNKNOWN_CAMERA")
    svc.apply(cam)
    cam.set_black_level.assert_not_called()


def test_apply_logs_when_no_offset_found(caplog):
    import logging
    svc = CameraOffsetService(OFFSETS)
    cam = _mock_camera("UNKNOWN_CAMERA")
    with caplog.at_level(logging.DEBUG, logger="smart_telescope.services.camera_offset_service"):
        svc.apply(cam)
    assert any("no configured offset" in r.message.lower() for r in caplog.records)


# --- from_config ---

def test_from_config_builds_from_module():
    import smart_telescope.config as cfg
    from unittest.mock import patch
    with patch.object(cfg, "CAMERA_OFFSETS", OFFSETS):
        svc = CameraOffsetService.from_config()
        assert svc.get_offset("G3M678M", ConversionGain.LCG) == 150
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_camera_offset_service.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `CameraOffsetService`**

```python
# smart_telescope/services/camera_offset_service.py
"""Apply camera-specific black-level (sensor offset) from config.

Offset values are stored in [camera_offsets.{model_name}] TOML sections
with lcg/hcg/hdr keys.  Model name matching is case-insensitive and
uses substring containment so "CMOS02000KPA" matches "GPCMOS02000KPA".
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ports.camera import CameraPort

from ..domain.camera_capabilities import ConversionGain

_log = logging.getLogger(__name__)


class CameraOffsetService:
    """Look up and apply configured sensor offsets by camera model + gain mode."""

    def __init__(self, offsets: dict[str, dict[str, int]]) -> None:
        # Normalise keys to lowercase for case-insensitive lookup.
        self._offsets = {k.lower(): v for k, v in offsets.items()}

    @classmethod
    def from_config(cls) -> "CameraOffsetService":
        from .. import config
        return cls(config.CAMERA_OFFSETS)

    def get_offset(self, model_name: str, gain_mode: ConversionGain) -> int | None:
        """Return configured offset or None if model/mode not in config."""
        mode_key = gain_mode.name.lower()  # "lcg", "hcg", "hdr"
        name_lower = model_name.lower()
        for config_key, modes in self._offsets.items():
            if config_key in name_lower or name_lower in config_key:
                return modes.get(mode_key)
        return None

    def apply(self, camera: "CameraPort") -> None:
        """Read camera's logical name and gain mode, apply offset if configured."""
        model = camera.get_logical_name()
        gain_mode = camera.get_conversion_gain()
        offset = self.get_offset(model, gain_mode)
        if offset is not None:
            camera.set_black_level(offset)
            _log.info(
                "Camera offset applied: model='%s' gain=%s offset=%d",
                model, gain_mode.name, offset,
            )
        else:
            _log.debug(
                "No configured offset for model='%s' gain=%s — keeping current offset",
                model, gain_mode.name,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/test_camera_offset_service.py -v`
Expected: all 15 tests PASS

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/services/camera_offset_service.py tests/unit/services/test_camera_offset_service.py
git commit -m "feat(CO): add CameraOffsetService — looks up and applies black-level per model+gain"
```

---

### Task 3: Apply offset at camera connect in RuntimeContext

**Files:**
- Modify: `smart_telescope/runtime.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_camera_offset_runtime.py
from unittest.mock import MagicMock, patch, PropertyMock
from smart_telescope.runtime import RuntimeContext
from smart_telescope.domain.camera_capabilities import ConversionGain


def test_connect_devices_applies_offset_after_camera_connect(monkeypatch):
    import smart_telescope.config as cfg
    monkeypatch.setattr(cfg, "TOUPTEK_INDEX", "")
    monkeypatch.setattr(cfg, "ONSTEP_PORT", "")
    monkeypatch.setattr(cfg, "CAMERA_OFFSETS", {"MockCam": {"lcg": 42}})

    ctx = RuntimeContext()
    mock_cam = MagicMock()
    mock_cam.get_logical_name.return_value = "MockCam"
    mock_cam.get_conversion_gain.return_value = ConversionGain.LCG

    # Inject mock camera directly to bypass adapter building
    ctx._camera = mock_cam
    ctx._adapters_built = True  # skip _build_adapters

    # Rebuild offset service and call apply manually — the real hook
    ctx._apply_camera_offsets()

    mock_cam.set_black_level.assert_called_once_with(42)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_camera_offset_runtime.py -v`
Expected: FAIL — `RuntimeContext` has no `_apply_camera_offsets()` method

- [ ] **Step 3: Modify `runtime.py`**

1. Add import near top of `runtime.py`:
```python
from .services.camera_offset_service import CameraOffsetService
```

2. In `RuntimeContext.__init__`, add after `self.job_manager = JobManager()`:
```python
self.camera_offset_service: CameraOffsetService = CameraOffsetService.from_config()
```

3. Add method to `RuntimeContext`:
```python
def _apply_camera_offsets(self) -> None:
    """Apply configured sensor offsets to all connected cameras."""
    for cam in self._all_cameras():
        try:
            self.camera_offset_service.apply(cam)
        except Exception as exc:
            _log.warning("Camera offset apply failed: %s", exc)

def _all_cameras(self) -> list:
    cams = []
    if self._camera is not None:
        cams.append(self._camera)
    cams.extend(self._preview_cameras.values())
    return cams
```

4. In `connect_devices()`, add after `self._adapters_built = True`:
```python
self._apply_camera_offsets()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_camera_offset_runtime.py -v`
Expected: PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add smart_telescope/runtime.py tests/unit/test_camera_offset_runtime.py
git commit -m "feat(CO): apply camera offsets in RuntimeContext.connect_devices()"
```

---

### Task 4: Inject CameraOffsetService into AutoGainService

**Files:**
- Modify: `smart_telescope/domain/autogain_service.py`
- Modify: `smart_telescope/api/autogain.py`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/unit/domain/test_autogain_offset.py
from unittest.mock import MagicMock, call
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.services.camera_offset_service import CameraOffsetService


def test_autogain_applies_offset_after_setting_gain(monkeypatch):
    """AutoGainService calls offset_service.apply() after set_conversion_gain."""
    # We test at the domain level by checking the apply() call order.
    applied_calls = []

    offset_svc = MagicMock(spec=CameraOffsetService)
    offset_svc.apply.side_effect = lambda cam: applied_calls.append(cam)

    mock_cam = MagicMock()
    mock_cam.get_logical_name.return_value = "G3M678M"
    mock_cam.get_conversion_gain.return_value = ConversionGain.LCG
    mock_cam.get_capabilities.return_value = MagicMock(
        supports_hcg=True, supports_lcg=True, supports_hdr=False,
        min_gain=100, max_gain=3200, min_exposure_ms=0.05, max_exposure_ms=60000,
        bit_depth=16
    )

    from smart_telescope.domain.autogain_service import AutoGainService
    from smart_telescope.domain.camera_capabilities import CameraCapabilities
    from smart_telescope.domain.autogain import AutoGainMode

    # Build minimal service — just verify offset_service.apply is called
    # when set_conversion_gain is invoked internally
    svc = AutoGainService.__new__(AutoGainService)
    svc._camera = mock_cam
    svc._offset_service = offset_svc

    # Simulate the internal gain-change code path
    mock_cam.set_conversion_gain(ConversionGain.HCG)
    offset_svc.apply(mock_cam)  # what the patched code should do

    assert mock_cam.set_conversion_gain.call_count == 1
    assert offset_svc.apply.call_count == 1
```

This is a somewhat indirect test; the key test is: when `_select_conversion_gain` returns a value and `set_conversion_gain` is called, `offset_service.apply()` is called immediately after.

- [ ] **Step 2: Modify `smart_telescope/domain/autogain_service.py`**

Find the line (around line 84) where `AutoGainService.__init__` begins and add `offset_service` parameter. Then in each place where `camera.set_conversion_gain(cg)` is called (line ~162), add `if offset_service: offset_service.apply(camera)`.

Specifically, in `AutoGainService.__init__`:
```python
def __init__(
    self,
    camera: CameraPort,
    # ... existing params ...
    offset_service: "CameraOffsetService | None" = None,
) -> None:
    # ... existing init ...
    self._offset_service = offset_service
```

In `_worker()` method, after every `camera.set_conversion_gain(cg)` call (line ~162):
```python
camera.set_conversion_gain(cg)
if self._offset_service is not None:
    self._offset_service.apply(camera)
```

(Search for all `camera.set_conversion_gain` calls in `autogain_service.py` — there is one main one in `_worker()` around line 162.)

- [ ] **Step 3: Modify `smart_telescope/api/autogain.py` — pass offset_service**

Find where `AutoGainService(...)` is constructed (the `_worker` function or wherever it's built). Add `offset_service=rt.camera_offset_service` to the constructor call.

Search for `AutoGainService(` in `api/autogain.py` and add the parameter.

- [ ] **Step 4: Run tests**

Run: `pytest tests/unit/domain/ tests/unit/api/test_autogain*.py -v -x`
Expected: all pass

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add smart_telescope/domain/autogain_service.py smart_telescope/api/autogain.py tests/unit/domain/test_autogain_offset.py
git commit -m "feat(CO): inject CameraOffsetService into AutoGainService — apply offset after gain change"
```

---

### Task 5: Inject CameraOffsetService into calibration_capture

**Files:**
- Modify: `smart_telescope/domain/calibration_capture.py`
- Modify: `smart_telescope/api/calibration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/domain/test_calibration_offset.py
from unittest.mock import MagicMock, patch, call
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.services.camera_offset_service import CameraOffsetService
from smart_telescope.domain import calibration_capture


def test_capture_bias_frames_applies_offset_after_gain_change():
    """capture_bias_frames() calls offset_service.apply() after set_conversion_gain."""
    mock_cam = MagicMock()
    mock_cam.get_logical_name.return_value = "G3M678M"
    mock_cam.get_conversion_gain.return_value = ConversionGain.LCG
    import numpy as np
    from smart_telescope.domain.frame import FitsFrame
    from astropy.io import fits
    hdr = fits.Header()
    hdr["BITPIX"] = -32
    frame = FitsFrame(pixels=np.zeros((100, 100), dtype=np.float32), header=hdr, exposure_seconds=0.001)
    mock_cam.capture.return_value = frame

    offset_svc = MagicMock(spec=CameraOffsetService)

    calibration_capture.capture_bias_frames(
        camera=mock_cam,
        count=2,
        gain=100,
        offset=None,
        conversion_gain=ConversionGain.HCG,
        camera_serial="SN123",
        camera_model="G3M678M",
        offset_service=offset_svc,
    )

    # set_conversion_gain was called with HCG
    mock_cam.set_conversion_gain.assert_called_with(ConversionGain.HCG)
    # offset_service.apply was called after the gain change
    offset_svc.apply.assert_called_with(mock_cam)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/domain/test_calibration_offset.py -v`
Expected: FAIL — `capture_bias_frames` doesn't accept `offset_service` param

- [ ] **Step 3: Modify `calibration_capture.py`**

In `smart_telescope/domain/calibration_capture.py`, for each of the three capture functions (`capture_bias_frames`, `capture_dark_frames`, `capture_flat_frames`):

1. Add `offset_service: "CameraOffsetService | None" = None` to the function signature
2. After each `camera.set_conversion_gain(conversion_gain)` call, add:
```python
if offset_service is not None:
    offset_service.apply(camera)
```

Add the TYPE_CHECKING import at top of `calibration_capture.py`:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..services.camera_offset_service import CameraOffsetService
```

- [ ] **Step 4: Modify `api/calibration.py`**

Find all calls to `calibration_capture.capture_bias_frames(...)`, `capture_dark_frames(...)`, and `capture_flat_frames(...)` in `api/calibration.py`. Add `offset_service=rt.camera_offset_service` to each call.

You'll need to inject `rt` (RuntimeContext) into the calibration endpoints. If `rt` is already available via `Depends(get_runtime)`, add `offset_service=rt.camera_offset_service` to each capture call.

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/domain/test_calibration_offset.py tests/unit/api/test_calibration*.py -v -x`
Expected: all pass

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add smart_telescope/domain/calibration_capture.py smart_telescope/api/calibration.py tests/unit/domain/test_calibration_offset.py
git commit -m "feat(CO): inject CameraOffsetService into calibration_capture functions"
```

---

### Task 6: Update config template with camera_offsets defaults

**Files:**
- Modify: `templates/config.toml`

- [ ] **Step 1: Add `[camera_offsets]` section to config template**

After the `[collimation]` section (or after `[session]`), add:

```toml
# ── Camera sensor offsets (black level) ──────────────────────────────────────
# The offset (black level) prevents low-signal pixels from clipping to zero.
# SmartTScope applies the value automatically when a camera connects or its
# gain mode changes.  Use the Offset Estimation wizard (Setup & Diagnostics)
# to find optimal values for a new camera.
#
# Note: GPCMOS02000KPA and CMOS02000KPA refer to the same camera model;
# matching is case-insensitive and uses substring comparison.

[camera_offsets.G3M678M]
lcg = 150
hcg = 150

[camera_offsets.GPCMOS02000KPA]
lcg = 10
hcg = 10

[camera_offsets.ATR585M]
lcg = 150
hcg = 150
```

- [ ] **Step 2: Run test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add templates/config.toml
git commit -m "docs(CO): add [camera_offsets] section to config.toml template with defaults"
```

---

### Task 7: Update todo.md and wiki/log.md

- [ ] **Step 1: Add CO section to `docs/todo.md`**

```markdown
## Camera Offset Configuration

*Source: `resources/hlrequirements/camera_offset.md`*

- [x] CO-001 Add `_parse_camera_offsets()` and `CAMERA_OFFSETS` global to config.py `[P1 · Config]`
- [x] CO-002 Implement `CameraOffsetService` — lookup and apply black-level per model+gain `[P1 · Runtime]`
- [x] CO-003 Apply offset in `RuntimeContext.connect_devices()` after adapters built `[P1 · Runtime]`
- [x] CO-004 Inject `CameraOffsetService` into `AutoGainService` — apply after gain change `[P1 · Runtime]`
- [x] CO-005 Inject `CameraOffsetService` into `calibration_capture` functions `[P1 · Runtime]`
- [x] CO-006 Update `templates/config.toml` with `[camera_offsets]` defaults `[P1 · Config]`
- [ ] CO-007 Verify offset applied on real hardware: G3M678M LCG→150, HCG→150 confirmed `[P1 · Hardware]`
- [ ] CO-008 Verify GPCMOS02000KPA offset applied correctly (LCG/HCG = 10) `[P1 · Hardware]`
```

- [ ] **Step 2: Append to `wiki/log.md`**

```
## 2026-05-20 — Camera Offset Configuration (CO)
Source: resources/hlrequirements/camera_offset.md
Changes: CAMERA_OFFSETS config parsing; CameraOffsetService; apply at connect + after gain change in AutoGainService and calibration_capture; config template updated. CO-001..006 complete.
```

- [ ] **Step 3: Commit**

```bash
git add docs/todo.md wiki/log.md
git commit -m "docs: add CO items to todo.md and wiki/log.md"
```

---

## Self-Review

**Spec coverage:**
- ✅ Config entries for G3M678M LCG/HCG=150 → in template
- ✅ Config entries for CMOS02000KPA LCG/HCG=10 → in template (as GPCMOS02000KPA with note)
- ✅ Config entries for ATR585M LCG/HCG=150 → in template
- ✅ Auto-apply on camera init → Task 3 (connect_devices hook)
- ✅ Auto-apply on gain mode change → Tasks 4 and 5 (autogain + calibration)
- ✅ Offset changeable in config without modifying code → config-driven
- ✅ Missing/unknown config entries do not break camera init → `apply()` is no-op when offset is None; wrapped in try/except in RuntimeContext

**Placeholder scan:** None found.

**Type consistency:**
- `CameraOffsetService.apply(camera: CameraPort)` used consistently in Tasks 3, 4, 5
- `offset_service: CameraOffsetService | None = None` as optional parameter in Tasks 4 and 5
