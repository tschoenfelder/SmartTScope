# BUG-007 Session Auto-Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a session starts, automatically load and apply matching bias/dark/flat masters from the `CalibrationIndex` instead of requiring the user to pass explicit file paths.

**Architecture:** A new `_auto_resolve_calibration(camera, exposure_s, profile, image_root)` helper in `api/session.py` reads the camera's current properties, queries the `CalibrationIndex`, loads matching FITS arrays, and returns them. The `session_run()` endpoint calls this helper when `use_calibration=True` (the new default) and no explicit `bias_path`/`dark_path`/`flat_path` are given. The helper is fully best-effort: any error (camera not connected, index empty, file missing) is logged and returns `(None, None, None)` so the session always starts. No frontend changes are required.

**Tech Stack:** Python 3.13 / FastAPI / numpy / astropy.io.fits (backend), pytest (tests).

---

## File Map

| File | Change |
|------|--------|
| `smart_telescope/api/session.py` | Add `_load_master_safe()`, `_auto_resolve_calibration()`, `use_calibration` param to `session_run()` |
| `tests/unit/api/test_auto_calibration.py` | New — 8 tests for `_auto_resolve_calibration()` + session endpoint wiring |
| `docs/todo.md` | Mark BUG-007 done |
| `wiki/log.md` | Prepend log entry |

---

### Task 1: Add `_auto_resolve_calibration()` helper and wire into session endpoint

**Files:**
- Modify: `smart_telescope/api/session.py`
- Create: `tests/unit/api/test_auto_calibration.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/api/test_auto_calibration.py`:

```python
"""Tests for BUG-007: _auto_resolve_calibration helper + session endpoint wiring."""
from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.api import session as session_module
from smart_telescope.api.session import _auto_resolve_calibration
from smart_telescope.domain.calibration_store import (
    CalibrationEntry,
    CalibrationIndex,
    MismatchDetail,
)
from smart_telescope.ports.camera import CameraPort


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_camera(
    model: str = "MockCam",
    serial: str = "SN001",
    gain: int = 200,
    offset: int = 10,
    cg_name: str = "HCG",
    bit_depth: int = 12,
) -> MagicMock:
    cam = MagicMock(spec=CameraPort)
    cam.get_logical_name.return_value = model
    cam.get_serial_number.return_value = serial
    cam.get_gain.return_value = gain
    cam.get_black_level.return_value = offset
    cg = MagicMock()
    cg.name = cg_name
    cam.get_conversion_gain.return_value = cg
    cam.get_bit_depth.return_value = bit_depth
    return cam


def _mock_entry(cal_type: str, relative_path: str) -> CalibrationEntry:
    return CalibrationEntry(
        cal_type=cal_type,
        camera_model="MockCam",
        camera_serial="SN001",
        gain=200,
        offset=10,
        conversion_gain="HCG",
        bit_depth=12,
        frame_count=10,
        relative_path=relative_path,
        created_at="2026-05-20T00:00:00+00:00",
        exposure_ms=30000.0 if cal_type == "dark" else None,
        optical_train="c8_native" if cal_type == "flat" else None,
        filter_id="none" if cal_type == "flat" else None,
    )


def _write_fake_fits(path: Path, value: float = 100.0) -> None:
    """Write a minimal valid FITS file with 4×4 float32 pixels."""
    data = np.full((4, 4), value, dtype=np.float32)
    hdr = fits.Header()
    hdu = fits.PrimaryHDU(data=data, header=hdr)
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buf.getvalue())


# ── TestAutoResolveCalibration ────────────────────────────────────────────────

class TestAutoResolveCalibration:
    def test_returns_none_tuple_when_camera_raises(self, tmp_path: Path) -> None:
        cam = MagicMock(spec=CameraPort)
        cam.get_logical_name.side_effect = RuntimeError("camera not connected")
        bias, dark, flat = _auto_resolve_calibration(cam, 30.0, "c8_native", str(tmp_path))
        assert bias is None
        assert dark is None
        assert flat is None

    def test_returns_none_tuple_when_index_empty(self, tmp_path: Path) -> None:
        cam = _mock_camera()
        bias, dark, flat = _auto_resolve_calibration(cam, 30.0, "c8_native", str(tmp_path))
        assert bias is None
        assert dark is None
        assert flat is None

    def test_loads_bias_when_exact_match_found(self, tmp_path: Path) -> None:
        cam = _mock_camera()
        entry = _mock_entry("bias", "masters/MockCam_SN001/biases/master_bias.fits")
        fits_path = tmp_path / entry.relative_path
        _write_fake_fits(fits_path, value=42.0)

        index = CalibrationIndex(tmp_path)
        index.add(entry)
        index.save()

        bias, dark, flat = _auto_resolve_calibration(cam, 30.0, "c8_native", str(tmp_path))
        assert bias is not None
        assert float(np.mean(bias)) == pytest.approx(42.0, rel=1e-3)
        assert dark is None  # no dark in index
        assert flat is None  # no flat in index

    def test_loads_dark_matching_exposure(self, tmp_path: Path) -> None:
        cam = _mock_camera()
        entry = _mock_entry("dark", "masters/MockCam_SN001/darks/master_dark_e30000ms.fits")
        fits_path = tmp_path / entry.relative_path
        _write_fake_fits(fits_path, value=55.0)

        index = CalibrationIndex(tmp_path)
        index.add(entry)
        index.save()

        bias, dark, flat = _auto_resolve_calibration(cam, 30.0, "c8_native", str(tmp_path))
        assert dark is not None
        assert float(np.mean(dark)) == pytest.approx(55.0, rel=1e-3)
        assert bias is None

    def test_partial_match_still_loads_array(self, tmp_path: Path) -> None:
        cam = _mock_camera(gain=300)  # session camera gain=300; entry has gain=200
        entry = _mock_entry("bias", "masters/MockCam_SN001/biases/master_bias.fits")
        fits_path = tmp_path / entry.relative_path
        _write_fake_fits(fits_path, value=10.0)

        index = CalibrationIndex(tmp_path)
        index.add(entry)
        index.save()

        bias, dark, flat = _auto_resolve_calibration(cam, 30.0, "c8_native", str(tmp_path))
        # partial match (gain mismatch) is still loaded
        assert bias is not None

    def test_missing_fits_file_returns_none(self, tmp_path: Path) -> None:
        cam = _mock_camera()
        entry = _mock_entry("bias", "masters/MockCam_SN001/biases/master_bias.fits")
        # Do NOT write the FITS file — index points to non-existent file

        index = CalibrationIndex(tmp_path)
        index.add(entry)
        index.save()

        bias, dark, flat = _auto_resolve_calibration(cam, 30.0, "c8_native", str(tmp_path))
        assert bias is None  # file not found → graceful None


# ── TestSessionAutoCalibration ────────────────────────────────────────────────

from fastapi.testclient import TestClient
from smart_telescope.app import app
from smart_telescope.api import deps

client = TestClient(app)


def _start_session_params(**overrides) -> dict:
    return {
        "target": "M42",
        "profile": "c8_native",
        "exposure": "5.0",
        "stack_depth": "2",
        **overrides,
    }


class TestSessionUsesAutoCalibration:
    def test_auto_calibration_applied_when_no_explicit_paths(self, tmp_path: Path) -> None:
        """With use_calibration=True (default) and no explicit paths, _auto_resolve_calibration is called."""
        bias_arr = np.zeros((4, 4), dtype=np.float32)
        dark_arr = np.ones((4, 4), dtype=np.float32)
        with patch.object(
            session_module,
            "_auto_resolve_calibration",
            return_value=(bias_arr, dark_arr, None),
        ) as mock_auto:
            with patch.object(session_module, "_get_runtime") as mock_rt:
                mock_rt.return_value.job_manager.claim.side_effect = Exception("stop here")
                try:
                    client.post(f"/api/session/run?{'&'.join(f'{k}={v}' for k, v in _start_session_params().items())}")
                except Exception:
                    pass
            assert mock_auto.called

    def test_auto_calibration_skipped_when_explicit_bias_path_given(self, tmp_path: Path) -> None:
        fits_path = tmp_path / "bias.fits"
        _write_fake_fits(fits_path)
        with patch.object(
            session_module,
            "_auto_resolve_calibration",
            return_value=(None, None, None),
        ) as mock_auto:
            with patch.object(session_module, "_get_runtime") as mock_rt:
                mock_rt.return_value.job_manager.claim.side_effect = Exception("stop here")
                try:
                    params = _start_session_params(bias_path=str(fits_path))
                    client.post(f"/api/session/run?{'&'.join(f'{k}={v}' for k, v in params.items())}")
                except Exception:
                    pass
            # Explicit path given → auto-resolve not called
            assert not mock_auto.called

    def test_auto_calibration_skipped_when_use_calibration_false(self, tmp_path: Path) -> None:
        with patch.object(
            session_module,
            "_auto_resolve_calibration",
            return_value=(None, None, None),
        ) as mock_auto:
            with patch.object(session_module, "_get_runtime") as mock_rt:
                mock_rt.return_value.job_manager.claim.side_effect = Exception("stop here")
                try:
                    params = _start_session_params(use_calibration="false")
                    client.post(f"/api/session/run?{'&'.join(f'{k}={v}' for k, v in params.items())}")
                except Exception:
                    pass
            assert not mock_auto.called
```

- [ ] **Step 2: Run the tests to confirm they fail**

```powershell
cd "C:\Users\tscho\Documents\Torsten\TSBrain"
python -m pytest tests/unit/api/test_auto_calibration.py -v --tb=short -q 2>&1 | head -30
```

Expected: FAIL — `ImportError: cannot import name '_auto_resolve_calibration' from 'smart_telescope.api.session'`

- [ ] **Step 3: Add `_load_master_safe()` and `_auto_resolve_calibration()` to `api/session.py`**

In `smart_telescope/api/session.py`, add the following imports at the top (after the existing imports block, before `_PROFILES`):

```python
from ..domain.calibration_store import CalibrationIndex, find_best_match
```

Then add the two new functions immediately after the existing `_apply_calibration()` function (around line 64). The existing `_apply_calibration()` ends with a `_log.warning(...)` call. Add after that:

```python

def _load_master_safe(path: Path) -> np.ndarray | None:
    """Load a FITS master pixel array without raising HTTPException on failure."""
    try:
        with fits.open(io.BytesIO(path.read_bytes())) as hdul:
            return np.array(hdul[0].data, dtype=np.float32)
    except Exception:
        return None


def _auto_resolve_calibration(
    camera: CameraPort,
    exposure_s: float,
    profile: str,
    image_root: str,
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None]:
    """Return (bias_arr, dark_arr, flat_arr) by looking up the CalibrationIndex.

    Best-effort: any failure (camera not readable, index empty, file missing)
    returns None for that slot; session always starts regardless.
    """
    try:
        cam_model  = camera.get_logical_name()
        cam_serial = camera.get_serial_number()
        gain       = camera.get_gain()
        offset     = camera.get_black_level()
        cg_obj     = camera.get_conversion_gain()
        cg_name    = cg_obj.name if hasattr(cg_obj, "name") else str(cg_obj)
        bit_depth  = camera.get_bit_depth()
    except Exception:
        _log.warning("auto_calibration: could not read camera properties — skipping calibration lookup")
        return None, None, None

    try:
        index = CalibrationIndex.load(image_root)
    except Exception:
        _log.warning("auto_calibration: could not load calibration index — skipping")
        return None, None, None

    base: dict = {
        "camera_model":    cam_model,
        "camera_serial":   cam_serial,
        "gain":            gain,
        "offset":          offset,
        "conversion_gain": cg_name.upper(),
        "bit_depth":       bit_depth,
    }

    def _resolve(cal_type: str, criteria: dict) -> np.ndarray | None:
        entry, mismatches = find_best_match(index, cal_type, criteria)
        if entry is None:
            return None
        if mismatches:
            fields = ", ".join(m.field for m in mismatches)
            _log.warning("auto_calibration: %s partial match (differs: %s) — applying", cal_type, fields)
        else:
            _log.info("auto_calibration: %s exact match found — applying", cal_type)
        arr = _load_master_safe(Path(image_root) / entry.relative_path)
        if arr is None:
            _log.warning("auto_calibration: %s master file not found: %s", cal_type, entry.relative_path)
        return arr

    bias_arr = _resolve("bias", base)
    dark_arr = _resolve("dark", {**base, "exposure_ms": exposure_s * 1000.0})
    flat_arr = _resolve("flat", {**base, "optical_train": profile, "filter_id": None})
    return bias_arr, dark_arr, flat_arr
```

- [ ] **Step 4: Add `use_calibration` param to `session_run()` and wire the auto-lookup**

In `smart_telescope/api/session.py`, find the `session_run` function signature. It currently has these calibration params near the end of the Query list:

```python
    bias_path: str | None = Query(default=None, description="Absolute path to master bias FITS"),
    dark_path: str | None = Query(default=None, description="Absolute path to master dark FITS"),
    flat_path: str | None = Query(default=None, description="Absolute path to master flat FITS"),
```

Replace with:

```python
    bias_path: str | None = Query(default=None, description="Absolute path to master bias FITS"),
    dark_path: str | None = Query(default=None, description="Absolute path to master dark FITS"),
    flat_path: str | None = Query(default=None, description="Absolute path to master flat FITS"),
    use_calibration: bool = Query(default=True, description="Auto-load matching calibration masters from index when no explicit paths given"),
```

Then find the block that loads calibration arrays (around line 243):

```python
    bias_arr = _load_fits_master(bias_path) if bias_path else None
    dark_arr = _load_fits_master(dark_path) if dark_path else None
    flat_arr = _load_fits_master(flat_path) if flat_path else None
```

Replace with:

```python
    if bias_path or dark_path or flat_path:
        bias_arr = _load_fits_master(bias_path) if bias_path else None
        dark_arr = _load_fits_master(dark_path) if dark_path else None
        flat_arr = _load_fits_master(flat_path) if flat_path else None
    elif use_calibration and _config.IMAGE_ROOT:
        bias_arr, dark_arr, flat_arr = _auto_resolve_calibration(
            camera, exposure, profile, _config.IMAGE_ROOT
        )
    else:
        bias_arr = dark_arr = flat_arr = None
```

- [ ] **Step 5: Run all tests to confirm 8 new tests pass and no regressions**

```powershell
cd "C:\Users\tscho\Documents\Torsten\TSBrain"
python -m pytest tests/unit/api/test_auto_calibration.py tests/unit/api/test_session.py tests/unit/api/test_calibration.py -v --tb=short -q
```

Expected: all pass (8 new + existing session/calibration tests).

- [ ] **Step 6: Run the full test suite to confirm coverage stays above 80%**

```powershell
python -m pytest --tb=short -q 2>&1 | tail -5
```

Expected: `N passed` with `Total coverage: ≥80%`.

- [ ] **Step 7: Commit**

```powershell
git add smart_telescope/api/session.py tests/unit/api/test_auto_calibration.py
git commit -m "feat: BUG-007 — session auto-applies calibration from index when available"
```

---

### Task 2: Mark BUG-007 done and update wiki

**Files:**
- Modify: `docs/todo.md`
- Modify: `wiki/log.md`

- [ ] **Step 1: Update `docs/todo.md`**

Find:
```
- [ ] BUG-007 Support frame types: bias, dark, flat frames; master frames; bad pixel maps `[P2 · Imaging · Source: Items_to_fix_20260513]`
  - No automatic cover exists; user must drive frame collection manually. Defer to post-MVP.
```

Replace with:
```
- [x] BUG-007 Support frame types: bias, dark, flat frames; master frames; bad pixel maps `[P2 · Imaging · Source: Items_to_fix_20260513]`
  - *Done:* `_auto_resolve_calibration()` in `api/session.py` — on session start, reads camera properties (model, serial, gain, offset, cg, bit_depth), loads `CalibrationIndex`, finds best matching bias/dark/flat masters, loads pixel arrays, and passes them to the stacker via `set_calibration()`. Lookup is best-effort (any failure → uncalibrated session). Explicit `bias_path`/`dark_path`/`flat_path` params still accepted for override. New `use_calibration=True` (default) param to disable auto-lookup. 8 new tests in `test_auto_calibration.py`.
  - *Note:* Flat-panel automation (automatic cover) remains deferred post-MVP. Manual frame collection UI is in Stage 4.
```

Also update the **Last updated** line. Find:
```
**Last updated:** 2026-05-19 (BUG-002 autogain layout; R7-006 evidence-gap report; M6-001–006 performance targets; M6-012 release notes; POD-005 isolation policy; M5-001/003/004 guided startup; POD-004/009/010 camera role API)
```
Replace with:
```
**Last updated:** 2026-05-20 (BUG-007 session auto-calibration)
```

- [ ] **Step 2: Prepend log entry to `wiki/log.md`**

Add immediately after the opening `---` separator (before the first existing `## ` entry):

```markdown
## 2026-05-20 — BUG-007 — Session auto-calibration from CalibrationIndex

**What changed:**
- `smart_telescope/api/session.py`: Added `_load_master_safe()` — loads FITS pixels without raising HTTPException; added `_auto_resolve_calibration(camera, exposure_s, profile, image_root)` — reads camera properties, queries `CalibrationIndex`, returns (bias_arr, dark_arr, flat_arr); modified `session_run()` to add `use_calibration=True` param and call auto-resolve when no explicit paths given.
- `tests/unit/api/test_auto_calibration.py`: 8 new tests — camera-raises, empty index, exact bias match, dark match by exposure, partial match loaded, missing FITS file, session wiring (auto called, skipped on explicit path, skipped on use_calibration=False).
- `docs/todo.md`: BUG-007 marked done.

**Tests:** ≥2696 passed

---
```

- [ ] **Step 3: Commit**

```powershell
git add docs/todo.md wiki/log.md
git commit -m "docs: BUG-007 done — session auto-calibration"
```
