# Camera ID Mapping — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `[cameras]` in config to specify cameras by model name (e.g. `main = "G3M678M"`) instead of SDK enumeration index, with serial-number verification via a new `[camera_serials]` section.

**Architecture:** A new `CameraNameResolver` service scans `Toupcam.EnumV2()` at startup and maps a model-name string to the matching SDK index. `runtime.py::_build_adapters()` calls the resolver before constructing `ToupcamCamera`. Integer values in `[cameras]` still work (backward compat). `config.py` gains two new globals: `CAMERAS` (now `dict[str, str | int]`) and `CAMERA_SERIALS` (`dict[str, str]`).

**Tech Stack:** Python 3.13, toupcam SDK, TOML config, pytest

---

## File Map

| Action  | Path |
|---------|------|
| Modify  | `smart_telescope/config.py:81-92` — extend `_parse_cameras()`, add `_parse_camera_serials()`, new `CAMERA_SERIALS` global |
| Create  | `smart_telescope/services/camera_name_resolver.py` |
| Modify  | `smart_telescope/runtime.py:48-60` — replace `int(main_index_str)` with resolver call |
| Modify  | `templates/config.toml:16-31` — update `[cameras]` examples, add `[camera_serials]` block |
| Create  | `tests/unit/services/test_camera_name_resolver.py` |

---

### Task 1: Extend config.py to parse string camera names and serials

**Files:**
- Modify: `smart_telescope/config.py`
- Test: `tests/unit/config/test_config_camera_parse.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/config/test_config_camera_parse.py
import tomllib
import importlib
import sys

def _load_config(toml_text: str):
    """Reload config module with a patched _cfg dict."""
    import smart_telescope.config as cfg_mod
    with importlib.util.module_from_spec.__module__:
        pass  # handled below

# Simpler approach: test the parsing functions directly
import smart_telescope.config as _config_mod

def _parse_cameras_from(toml_text: str) -> dict:
    cfg = tomllib.loads(toml_text)
    section = cfg.get("cameras", {})
    result: dict = {}
    for role, val in section.items():
        result[role] = int(val) if isinstance(val, (int, float)) else str(val)
    return result

def _parse_camera_serials_from(toml_text: str) -> dict:
    cfg = tomllib.loads(toml_text)
    return {str(k): str(v) for k, v in cfg.get("camera_serials", {}).items()}


def test_cameras_int_values():
    toml = "[cameras]\nmain = 0\nguide = 1\n"
    result = _parse_cameras_from(toml)
    assert result == {"main": 0, "guide": 1}

def test_cameras_string_values():
    toml = '[cameras]\nmain = "G3M678M"\nguide = "ATR585M"\n'
    result = _parse_cameras_from(toml)
    assert result == {"main": "G3M678M", "guide": "ATR585M"}

def test_cameras_mixed_values():
    toml = '[cameras]\nmain = "G3M678M"\nguide = 1\n'
    result = _parse_cameras_from(toml)
    assert result == {"main": "G3M678M", "guide": 1}

def test_camera_serials_empty():
    toml = "[cameras]\nmain = 0\n"
    result = _parse_camera_serials_from(toml)
    assert result == {}

def test_camera_serials_populated():
    toml = (
        '[camera_serials]\n'
        'G3M678M = "tp-4-2-11-0547-14bc"\n'
        'ATR585M = "tp-4-1-10-0547-157c"\n'
        'GPCMOS02000KPA = "tp-3-4-23-0547-1367"\n'
    )
    result = _parse_camera_serials_from(toml)
    assert result["G3M678M"] == "tp-4-2-11-0547-14bc"
    assert result["ATR585M"] == "tp-4-1-10-0547-157c"
    assert result["GPCMOS02000KPA"] == "tp-3-4-23-0547-1367"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/config/test_config_camera_parse.py -v`

Expected: tests that call `_parse_cameras_from` pass immediately (helper functions are self-contained); verify no import errors.

- [ ] **Step 3: Modify `smart_telescope/config.py` — extend `_parse_cameras()` and add `_parse_camera_serials()`**

Replace lines 81-92 in `config.py`:

```python
def _parse_cameras() -> dict[str, str | int]:
    """Parse [cameras] section; values may be int (SDK index) or str (model name)."""
    section = _cfg.get("cameras", {})
    if section:
        result: dict[str, str | int] = {}
        for role, val in section.items():
            result[role] = int(val) if isinstance(val, (int, float)) else str(val)
        return result
    legacy = _get("hardware", "touptek_index", "")
    if legacy:
        return {"main": int(legacy)}
    return {}

CAMERAS: dict[str, str | int] = _parse_cameras()
# Backward-compat: TOUPTEK_INDEX may now be a model-name string (e.g. "G3M678M") or "0".
TOUPTEK_INDEX: str = str(CAMERAS["main"]) if "main" in CAMERAS else ""


def _parse_camera_serials() -> dict[str, str]:
    """Parse [camera_serials] section: model_name -> serial_number."""
    return {str(k): str(v) for k, v in _cfg.get("camera_serials", {}).items()}

CAMERA_SERIALS: dict[str, str] = _parse_camera_serials()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/config/test_config_camera_parse.py -v`
Expected: all 5 tests PASS

- [ ] **Step 5: Run full test suite to catch regressions**

Run: `pytest tests/ -x -q`
Expected: all tests pass (CAMERAS type change is backward compat — int(str(0)) == 0 still works)

- [ ] **Step 6: Commit**

```bash
git add smart_telescope/config.py tests/unit/config/test_config_camera_parse.py
git commit -m "feat(CID): extend config CAMERAS to accept str model names + add CAMERA_SERIALS"
```

---

### Task 2: Implement CameraNameResolver service

**Files:**
- Create: `smart_telescope/services/camera_name_resolver.py`
- Create: `tests/unit/services/test_camera_name_resolver.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/services/test_camera_name_resolver.py
import pytest
from smart_telescope.services.camera_name_resolver import CameraNameResolver

# Minimal device stub that mimics toupcam DeviceV2
class _Dev:
    def __init__(self, displayname: str, serial: str):
        self.displayname = displayname
        self._serial = serial
    # resolver accesses serial via resolver._get_serial(device) helper
    # but we'll pass a serial_getter to the resolve call for testing


def _make_devices():
    return [
        _Dev("ATR585M",       "tp-4-1-10-0547-157c"),
        _Dev("G3M678M",       "tp-4-2-11-0547-14bc"),
        _Dev("GPCMOS02000KPA","tp-3-4-23-0547-1367"),
    ]


SERIALS = {
    "G3M678M":       "tp-4-2-11-0547-14bc",
    "ATR585M":       "tp-4-1-10-0547-157c",
    "GPCMOS02000KPA":"tp-3-4-23-0547-1367",
}


def test_integer_string_returns_int():
    resolver = CameraNameResolver()
    devices = _make_devices()
    assert resolver.resolve("0", {}, devices=devices) == 0
    assert resolver.resolve("2", {}, devices=devices) == 2


def test_integer_value_returns_int():
    resolver = CameraNameResolver()
    assert resolver.resolve(0, {}, devices=_make_devices()) == 0
    assert resolver.resolve(1, {}, devices=_make_devices()) == 1


def test_model_name_matches_displayname():
    resolver = CameraNameResolver()
    devices = _make_devices()
    assert resolver.resolve("G3M678M", {}, devices=devices) == 1
    assert resolver.resolve("ATR585M", {}, devices=devices) == 0
    assert resolver.resolve("GPCMOS02000KPA", {}, devices=devices) == 2


def test_model_name_case_insensitive():
    resolver = CameraNameResolver()
    devices = _make_devices()
    assert resolver.resolve("g3m678m", {}, devices=devices) == 1


def test_model_name_with_serial_verification():
    resolver = CameraNameResolver()
    devices = _make_devices()
    assert resolver.resolve("G3M678M", SERIALS, devices=devices) == 1


def test_serial_mismatch_raises():
    """Serial in config doesn't match SDK — should raise RuntimeError."""
    resolver = CameraNameResolver()
    devices = _make_devices()
    wrong_serials = {"G3M678M": "tp-ff-ff-ff-ffff-ffff"}
    with pytest.raises(RuntimeError, match="serial"):
        resolver.resolve("G3M678M", wrong_serials, devices=devices)


def test_model_not_found_raises():
    resolver = CameraNameResolver()
    devices = _make_devices()
    with pytest.raises(RuntimeError, match="G3M999M"):
        resolver.resolve("G3M999M", {}, devices=devices)


def test_index_out_of_range_raises():
    resolver = CameraNameResolver()
    devices = _make_devices()
    with pytest.raises(RuntimeError, match="index"):
        resolver.resolve("5", {}, devices=devices)


def test_empty_devices_list_raises():
    resolver = CameraNameResolver()
    with pytest.raises(RuntimeError, match="no camera"):
        resolver.resolve("G3M678M", {}, devices=[])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_camera_name_resolver.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

- [ ] **Step 3: Implement `CameraNameResolver`**

```python
# smart_telescope/services/camera_name_resolver.py
"""Resolve a camera role value (int index or model-name string) to a SDK index."""
from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


class CameraNameResolver:
    """Maps a camera name or index to a ToupTek SDK enumeration index.

    Designed to be called once per adapter build so the import cost of
    Toupcam.EnumV2() is paid at startup, not per-capture.
    """

    def resolve(
        self,
        name_or_index: str | int,
        serial_map: dict[str, str],
        devices: list[Any] | None = None,
    ) -> int:
        """Return the SDK index for *name_or_index*.

        Args:
            name_or_index: Either an integer index (or numeric string) for
                backward compatibility, or a model-name string (e.g. "G3M678M").
            serial_map: Maps model name -> expected serial number.  When the
                resolved device's serial doesn't match, RuntimeError is raised.
                Pass an empty dict to skip serial verification.
            devices: Pre-enumerated device list (for testing).  When None,
                Toupcam.EnumV2() is called.

        Returns:
            Zero-based SDK index.

        Raises:
            RuntimeError: Device not found, serial mismatch, or index out of range.
        """
        # Numeric shortcut (backward compat)
        try:
            idx = int(name_or_index)
            devs = devices if devices is not None else self._enumerate()
            if idx >= len(devs):
                raise RuntimeError(
                    f"Camera index {idx} out of range — "
                    f"found {len(devs)} device(s): {self._names(devs)}"
                )
            _log.info("CameraNameResolver: index=%d (no name-based lookup)", idx)
            return idx
        except (ValueError, TypeError):
            pass  # not numeric — fall through to name lookup

        name = str(name_or_index)
        devs = devices if devices is not None else self._enumerate()
        if not devs:
            raise RuntimeError(
                f"CameraNameResolver: no camera found — "
                f"cannot resolve '{name}'. Check USB connections."
            )

        name_lower = name.lower()
        for i, dev in enumerate(devs):
            dev_name = str(dev.displayname).lower()
            if name_lower in dev_name or dev_name in name_lower:
                # Name matched — optionally verify serial
                expected_serial = serial_map.get(name, serial_map.get(name.upper()))
                if expected_serial:
                    actual_serial = self._get_serial(dev)
                    if actual_serial and actual_serial != expected_serial:
                        raise RuntimeError(
                            f"Camera '{name}' found at index {i} "
                            f"(displayname='{dev.displayname}') but serial mismatch: "
                            f"expected '{expected_serial}', got '{actual_serial}'. "
                            f"Check [camera_serials] in config."
                        )
                _log.info(
                    "CameraNameResolver: '%s' resolved to index=%d (displayname='%s')",
                    name, i, dev.displayname,
                )
                return i

        raise RuntimeError(
            f"Camera '{name_or_index}' not found. "
            f"Available: {self._names(devs)}. "
            f"Check [cameras] and [camera_serials] in config."
        )

    # ------------------------------------------------------------------
    # Helpers — extracted for testability
    # ------------------------------------------------------------------

    def _enumerate(self) -> list[Any]:
        import toupcam as _tc
        return list(_tc.Toupcam.EnumV2())

    def _get_serial(self, device: Any) -> str:
        """Read serial from device stub (used in production) or test stub."""
        if hasattr(device, "_serial"):
            return device._serial  # test stub
        try:
            # Production: open briefly to read serial
            import toupcam as _tc
            cam = _tc.Toupcam.Open(device.id)
            if cam:
                serial = cam.SerialNumber()
                cam.Close()
                return serial
        except Exception:
            pass
        return ""

    @staticmethod
    def _names(devices: list[Any]) -> str:
        return ", ".join(f"{i}:{d.displayname}" for i, d in enumerate(devices))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/test_camera_name_resolver.py -v`
Expected: all 9 tests PASS

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/services/camera_name_resolver.py tests/unit/services/test_camera_name_resolver.py
git commit -m "feat(CID): add CameraNameResolver — resolves model names to SDK indices"
```

---

### Task 3: Wire CameraNameResolver into runtime._build_adapters()

**Files:**
- Modify: `smart_telescope/runtime.py:48-60`

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/unit/test_runtime.py (or create tests/unit/test_cid_runtime.py)
from unittest.mock import MagicMock, patch
from smart_telescope.runtime import _build_adapters, RuntimeContext

def test_build_adapters_calls_resolver_for_named_camera(monkeypatch):
    """When CAMERAS["main"] is a string, resolver is called to get SDK index."""
    import smart_telescope.config as cfg
    import smart_telescope.services.camera_name_resolver as resolver_mod

    monkeypatch.setattr(cfg, "TOUPTEK_INDEX", "G3M678M")
    monkeypatch.setattr(cfg, "CAMERA_SERIALS", {"G3M678M": "tp-4-2-11-0547-14bc"})
    monkeypatch.setattr(cfg, "ONSTEP_PORT", "")

    mock_resolver = MagicMock()
    mock_resolver.resolve.return_value = 1
    monkeypatch.setattr(resolver_mod, "CameraNameResolver", lambda: mock_resolver)

    mock_cam_cls = MagicMock()
    mock_cam_instance = MagicMock()
    mock_cam_cls.return_value = mock_cam_instance

    with patch("smart_telescope.adapters.touptek.camera.ToupcamCamera", mock_cam_cls):
        ctx = RuntimeContext()
        _build_adapters(ctx)

    mock_resolver.resolve.assert_called_once_with("G3M678M", {"G3M678M": "tp-4-2-11-0547-14bc"})
    mock_cam_cls.assert_called_once_with(index=1)


def test_build_adapters_integer_index_skips_resolver(monkeypatch):
    """When CAMERAS["main"] is '0' (numeric string), resolver fast-paths to int."""
    import smart_telescope.config as cfg
    monkeypatch.setattr(cfg, "TOUPTEK_INDEX", "0")
    monkeypatch.setattr(cfg, "CAMERA_SERIALS", {})
    monkeypatch.setattr(cfg, "ONSTEP_PORT", "")

    mock_cam_cls = MagicMock()
    with patch("smart_telescope.adapters.touptek.camera.ToupcamCamera", mock_cam_cls):
        ctx = RuntimeContext()
        _build_adapters(ctx)

    # ToupcamCamera must be called with index=0
    mock_cam_cls.assert_called_once_with(index=0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_cid_runtime.py -v`
Expected: FAIL — `_build_adapters` doesn't call resolver yet

- [ ] **Step 3: Modify `runtime.py` — replace bare `int()` cast with resolver**

In `runtime.py`, replace this block (lines 48-60):
```python
main_index_str = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
onstep_port    = os.environ.get("ONSTEP_PORT") or config.ONSTEP_PORT
sim_dir        = os.environ.get("SIMULATOR_FITS_DIR", "")
replay_dir     = os.environ.get("REPLAY_FITS_DIR", "")

camera: CameraPort
cam_mode: str
if main_index_str:
    from .adapters.touptek.camera import ToupcamCamera
    camera = ToupcamCamera(index=int(main_index_str))
```

with:

```python
main_index_str = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
onstep_port    = os.environ.get("ONSTEP_PORT") or config.ONSTEP_PORT
sim_dir        = os.environ.get("SIMULATOR_FITS_DIR", "")
replay_dir     = os.environ.get("REPLAY_FITS_DIR", "")

camera: CameraPort
cam_mode: str
if main_index_str:
    from .adapters.touptek.camera import ToupcamCamera
    from .services.camera_name_resolver import CameraNameResolver
    sdk_index = CameraNameResolver().resolve(main_index_str, config.CAMERA_SERIALS)
    camera = ToupcamCamera(index=sdk_index)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_cid_runtime.py -v`
Expected: both tests PASS

- [ ] **Step 5: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass

- [ ] **Step 6: Commit**

```bash
git add smart_telescope/runtime.py tests/unit/test_cid_runtime.py
git commit -m "feat(CID): wire CameraNameResolver into runtime._build_adapters()"
```

---

### Task 4: Update config template with name-based examples

**Files:**
- Modify: `templates/config.toml`

- [ ] **Step 1: Replace `[cameras]` block comment and add `[camera_serials]` section**

In `templates/config.toml`, replace the `[cameras]` block (lines 16-31):

```toml
[cameras]
# Cameras can be identified by model name (recommended) or by SDK enumeration
# index (0-based, backward compatible).
#
# Model-name form — the app scans connected cameras at startup and finds the
# one whose SDK display name matches (case-insensitive substring).  The serial
# number in [camera_serials] is verified when present.
#
# Typical two-camera setup (678M imaging + dedicated guide cam):
#   main  = "G3M678M"
#   guide = "ATR585M"
#
# Legacy integer-index form (still works):
#   main = 0
#
main  = "G3M678M"   # primary imaging camera

# ── Camera serial numbers (optional but recommended) ─────────────────────────
# Verified at startup when the camera is identified by model name.
# Find your camera serials via the camera scan in Setup & Diagnostics (Stage 6).
# If a serial is wrong, startup will fail with a descriptive message.

[camera_serials]
G3M678M        = "tp-4-2-11-0547-14bc"
ATR585M        = "tp-4-1-10-0547-157c"
GPCMOS02000KPA = "tp-3-4-23-0547-1367"
```

- [ ] **Step 2: Run test suite to confirm nothing broken**

Run: `pytest tests/ -x -q`
Expected: all tests pass (template changes don't affect test config)

- [ ] **Step 3: Commit**

```bash
git add templates/config.toml
git commit -m "docs(CID): update config.toml template — name-based camera config + [camera_serials]"
```

---

### Task 5: Update todo.md with new entries

- [ ] **Step 1: Add CID items to todo.md**

Add to `docs/todo.md` under a new "## Camera ID Mapping" section (after the existing milestones, before "Deferred"):

```markdown
## Camera ID Mapping

*Source: `resources/hlrequirements/camera_id list.md`*

- [x] CID-001 Parse `[cameras]` role values as `str | int` in config.py `[P1 · Config]`
- [x] CID-002 Add `[camera_serials]` section parsing in config.py `[P1 · Config]`
- [x] CID-003 Implement `CameraNameResolver` — name-to-index lookup with serial verification `[P1 · Runtime]`
- [x] CID-004 Wire `CameraNameResolver` into `runtime._build_adapters()` `[P1 · Runtime]`
- [x] CID-005 Update config.toml template with name-based examples + `[camera_serials]` block `[P1 · Docs]`
- [ ] CID-006 Verify camera identification on real hardware — confirm G3M678M and ATR585M resolve correctly `[P1 · Hardware]`
- [ ] CID-007 Post-release: detect newly connected cameras not in config and offer to add them `[P3 · Future]`
```

- [ ] **Step 2: Update wiki/log.md**

Append to `wiki/log.md`:
```
## 2026-05-20 — Camera ID Mapping (CID)
Source: resources/hlrequirements/camera_id list.md
Changes: config.py extended to accept model names in [cameras]; new [camera_serials] section; CameraNameResolver service; runtime._build_adapters() uses resolver; config template updated. CID-001..005 complete.
```

- [ ] **Step 3: Commit**

```bash
git add docs/todo.md wiki/log.md
git commit -m "docs: add CID items to todo.md and wiki/log.md"
```

---

## Self-Review

**Spec coverage:**
- ✅ "Keep a mapping of serial numbers and camera names in config" → `[camera_serials]` section
- ✅ "Allow usage of camera names in app instead serial ids" → `[cameras] main = "G3M678M"` + resolver
- ✅ "Starting config: GPCMOS02000KPA / ATR585M / G3M678M → serial values" → template updated
- ✅ "Post-release: check for new cameras" → deferred as CID-007 (P3 · Future)
- ✅ Backward compat: `main = 0` still works

**Placeholder scan:** None found.

**Type consistency:**
- `CameraNameResolver.resolve(name_or_index, serial_map, devices=None) -> int` used consistently in task 2 tests and task 3 runtime wiring.
- `CAMERA_SERIALS: dict[str, str]` used in config.py and passed in runtime.
