# Collimation Frame Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add opt-in FITS frame storage during collimation sessions so accepted donut and spike frames are saved to disk with JSON sidecars, enabling offline algorithm replay and improvement.

**Architecture:** A new `CollimationFrameArchive` service saves raw `FitsFrame` objects as FITS files plus JSON sidecars (state, analysis result, ref coords, bit depth) under `~/.SmartTScope/frame_archive/<session_id>/`. `CollimationAssistant` gains a `frame_archive` parameter; it generates a UUID session ID on `start()` and calls `archive.save_frame()` after each accepted donut or spike measurement. Three new `GET/POST /api/collimation/archive/*` endpoints list sessions, list frames, and replay a stored frame through its original analysis pipeline. Disabled by default (`archive.enabled = false` in `[collimation]` config).

**Tech Stack:** Python 3.13, astropy.io.fits (`FitsFrame.to_fits_bytes()` / `from_fits_bytes()`), json, pathlib, threading.Lock, FastAPI, pytest + tmp_path.

---

## Background: what already exists

| Symbol | Location | Notes |
|---|---|---|
| `FitsFrame` | `smart_telescope/domain/frame.py` | `to_fits_bytes()` serialises pixels; `from_fits_bytes()` loads |
| `CollimationAssistant` | `smart_telescope/services/collimation/assistant.py` | `_handle_measure_donut`, `_handle_measure_spikes` capture raw frames |
| `CollimationConfig` | `smart_telescope/domain/collimation/config.py` | Frozen dataclass, `from_dict()`, nested sub-configs pattern |
| `get_collimation_config()` | `smart_telescope/config.py` | Returns validated `CollimationConfig` |
| `_get_assistant()` | `smart_telescope/api/collimation.py` | Lazy factory; creates `CollimationAssistant` with camera/mount/focuser |
| `DonutAnalyzer` | `smart_telescope/domain/collimation/processing/donut_detection.py` | `analyze(processed) → DonutAnalysisResult` |
| `detect_spikes` | `smart_telescope/domain/collimation/processing/spike_detection.py` | `detect_spikes(processed, ref: Point2D) → SpikeDetectionResult` |
| `normalize_frame` | `smart_telescope/domain/collimation/processing/frame.py` | `normalize_frame(raw: FitsFrame, bit_depth: int) → ProcessedFrame` |
| `Point2D` | `smart_telescope/domain/collimation/models.py` | `NamedTuple` with `.x`, `.y`; returned by `ReferenceCenterCalibration.compute()` |

---

## File Map

| File | What changes |
|---|---|
| `smart_telescope/domain/collimation/config.py` | Add `ArchiveConfig` dataclass + `archive` field on `CollimationConfig` |
| `smart_telescope/services/collimation/frame_archive.py` | **New** — `CollimationFrameArchive` service |
| `smart_telescope/services/collimation/assistant.py` | Add `frame_archive` param, `session_id`, `frame_archive` property, archive calls in handlers |
| `smart_telescope/api/collimation.py` | Wire archive in `_get_assistant()`; add 3 archive endpoints |
| `templates/config.toml` | Add commented `[collimation.archive]` section |
| `tests/unit/services/test_collimation_guiding.py` | Append 3 assistant wiring tests |
| `tests/unit/services/test_frame_archive.py` | **New** — 7 unit tests for `CollimationFrameArchive` |
| `tests/unit/api/test_collimation_archive_api.py` | **New** — 6 API tests |

---

## Task 1: ArchiveConfig in CollimationConfig

**Files:**
- Modify: `smart_telescope/domain/collimation/config.py`
- Test: `tests/unit/services/test_collimation_guiding.py` (append 2 tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/services/test_collimation_guiding.py`:

```python
def test_archive_config_defaults():
    cfg = CollimationConfig.from_dict({})
    assert cfg.archive.enabled is False
    assert cfg.archive.archive_dir == ""
    assert cfg.archive.max_frames_per_session == 50


def test_archive_config_from_dict():
    cfg = CollimationConfig.from_dict({
        "archive": {
            "enabled": True,
            "archive_dir": "/tmp/test_archive",
            "max_frames_per_session": 10,
        }
    })
    assert cfg.archive.enabled is True
    assert cfg.archive.archive_dir == "/tmp/test_archive"
    assert cfg.archive.max_frames_per_session == 10
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/services/test_collimation_guiding.py::test_archive_config_defaults tests/unit/services/test_collimation_guiding.py::test_archive_config_from_dict -v
```

Expected: `AttributeError: 'CollimationConfig' object has no attribute 'archive'`

- [ ] **Step 3: Add `ArchiveConfig` to `smart_telescope/domain/collimation/config.py`**

Insert after the `FineCollimationConfig` class and before `# ── Top-level config ──`:

```python
@dataclass(frozen=True)
class ArchiveConfig:
    """Opt-in frame archive — saves accepted FITS frames and JSON sidecars."""
    enabled: bool = False
    archive_dir: str = ""   # empty → ~/.SmartTScope/frame_archive
    max_frames_per_session: int = 50

    @classmethod
    def from_dict(cls, d: dict) -> "ArchiveConfig":
        return cls(
            enabled=bool(d.get("enabled", False)),
            archive_dir=str(d.get("archive_dir", "")),
            max_frames_per_session=int(d.get("max_frames_per_session", 50)),
        )
```

- [ ] **Step 4: Add `archive` field to `CollimationConfig`**

In the `CollimationConfig` dataclass, add after the `fine_collimation` field:

```python
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)
```

In `from_dict()`, add after `fine_collimation=FineCollimationConfig.from_dict(d.get("fine_collimation", {})),`:

```python
            archive=ArchiveConfig.from_dict(d.get("archive", {})),
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/unit/services/test_collimation_guiding.py::test_archive_config_defaults tests/unit/services/test_collimation_guiding.py::test_archive_config_from_dict -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add smart_telescope/domain/collimation/config.py tests/unit/services/test_collimation_guiding.py
git commit -m "feat(COL-ARC): add ArchiveConfig to CollimationConfig"
```

---

## Task 2: CollimationFrameArchive service

**Files:**
- Create: `smart_telescope/services/collimation/frame_archive.py`
- Create: `tests/unit/services/test_frame_archive.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/services/test_frame_archive.py`:

```python
"""Unit tests for CollimationFrameArchive."""
import json
import pytest
import numpy as np
from astropy.io import fits

from smart_telescope.domain.frame import FitsFrame
from smart_telescope.services.collimation.frame_archive import CollimationFrameArchive


def _frame(width: int = 100, height: int = 80) -> FitsFrame:
    pixels = np.zeros((height, width), dtype=np.float32)
    pixels[40, 50] = 1000.0
    return FitsFrame(pixels=pixels, header=fits.Header(), exposure_seconds=2.0)


def _save(archive: CollimationFrameArchive, session_id: str, idx: int = 1,
          state: str = "measure_donut") -> str | None:
    return archive.save_frame(
        session_id=session_id,
        state=state,
        frame_index=idx,
        captured_at="2026-01-01T00:00:00+00:00",
        exposure_s=2.0,
        gain=100,
        bit_depth=16,
        ref_x=50.0,
        ref_y=40.0,
        raw_frame=_frame(),
        analysis={"reason": "ok", "error_x_px": 1.5},
    )


def test_save_and_load_frame(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("s1")
    stem = _save(archive, "s1")
    assert stem == "measure_donut_0001"
    loaded = archive.load_frame("s1", stem)
    assert loaded.width == 100
    assert loaded.height == 80


def test_sidecar_content(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("s2")
    _save(archive, "s2")
    sidecar = archive.load_sidecar("s2", "measure_donut_0001")
    assert sidecar["state"] == "measure_donut"
    assert sidecar["analysis"]["error_x_px"] == 1.5
    assert sidecar["ref_x"] == 50.0
    assert sidecar["bit_depth"] == 16


def test_max_frames_cap(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=2)
    archive.new_session("s3")
    results = [_save(archive, "s3", idx=i + 1) for i in range(3)]
    assert results[0] is not None
    assert results[1] is not None
    assert results[2] is None   # over cap


def test_list_sessions(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    for sid in ["sess-a", "sess-b"]:
        archive.new_session(sid)
        _save(archive, sid)
    sessions = archive.list_sessions()
    assert len(sessions) == 2
    assert all("session_id" in s for s in sessions)
    assert all(s["frame_count"] == 1 for s in sessions)


def test_list_frames(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("s4")
    for i in range(3):
        _save(archive, "s4", idx=i + 1)
    frames = archive.list_frames("s4")
    assert len(frames) == 3
    assert frames[0]["frame_stem"] == "measure_donut_0001"
    assert frames[0]["state"] == "measure_donut"


def test_list_sessions_empty_dir(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    assert archive.list_sessions() == []


def test_load_missing_frame_raises(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("s5")
    with pytest.raises(FileNotFoundError):
        archive.load_frame("s5", "measure_donut_0099")
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/services/test_frame_archive.py -v
```

Expected: `ImportError: cannot import name 'CollimationFrameArchive'`

- [ ] **Step 3: Create `smart_telescope/services/collimation/frame_archive.py`**

```python
"""CollimationFrameArchive — opt-in FITS frame + JSON sidecar storage."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.frame import FitsFrame

_log = logging.getLogger(__name__)


class CollimationFrameArchive:
    """Saves accepted collimation frames (FITS) and analysis sidecars (JSON).

    Directory layout::

        <archive_dir>/
            <session_id>/
                measure_donut_0001.fits
                measure_donut_0001.json
                measure_spikes_0002.fits
                measure_spikes_0002.json

    When max_frames_per_session is reached, further saves are silently skipped.
    """

    def __init__(self, archive_dir: Path, max_frames_per_session: int = 50) -> None:
        self._root = Path(archive_dir)
        self._max = max_frames_per_session
        self._lock = threading.Lock()

    def new_session(self, session_id: str) -> None:
        """Create the session subdirectory. Call once at CollimationAssistant.start()."""
        session_dir = self._root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        _log.info("CollimationFrameArchive: new session %s at %s", session_id, session_dir)

    def save_frame(
        self,
        session_id: str,
        state: str,
        frame_index: int,
        captured_at: str,
        exposure_s: float,
        gain: int,
        bit_depth: int,
        ref_x: float,
        ref_y: float,
        raw_frame: "FitsFrame",
        analysis: dict,
    ) -> str | None:
        """Save FITS + JSON sidecar. Returns frame_stem, or None if at cap."""
        session_dir = self._root / session_id
        with self._lock:
            existing = list(session_dir.glob("*.fits"))
            if len(existing) >= self._max:
                _log.debug(
                    "CollimationFrameArchive: session %s at cap (%d), skipping",
                    session_id, self._max,
                )
                return None

        frame_stem = f"{state}_{frame_index:04d}"
        fits_path = session_dir / f"{frame_stem}.fits"
        json_path = session_dir / f"{frame_stem}.json"

        try:
            fits_path.write_bytes(raw_frame.to_fits_bytes())
        except Exception as exc:
            _log.warning("CollimationFrameArchive: FITS write failed: %s", exc)
            return None

        sidecar = {
            "session_id": session_id,
            "state": state,
            "frame_index": frame_index,
            "captured_at": captured_at,
            "exposure_s": exposure_s,
            "gain": gain,
            "bit_depth": bit_depth,
            "ref_x": ref_x,
            "ref_y": ref_y,
            "analysis": analysis,
        }
        try:
            json_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.warning("CollimationFrameArchive: JSON write failed: %s", exc)

        _log.debug("CollimationFrameArchive: saved %s/%s", session_id, frame_stem)
        return frame_stem

    def list_sessions(self) -> list[dict]:
        """Return sessions sorted newest-first by directory mtime."""
        if not self._root.exists():
            return []
        sessions = []
        for session_dir in sorted(
            self._root.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            if not session_dir.is_dir():
                continue
            fits_files = list(session_dir.glob("*.fits"))
            state_counts: dict[str, int] = {}
            for f in fits_files:
                state = f.stem.rsplit("_", 1)[0]
                state_counts[state] = state_counts.get(state, 0) + 1
            size_bytes = sum(f.stat().st_size for f in session_dir.iterdir())
            sessions.append({
                "session_id": session_dir.name,
                "frame_count": len(fits_files),
                "state_counts": state_counts,
                "size_bytes": size_bytes,
            })
        return sessions

    def list_frames(self, session_id: str) -> list[dict]:
        """Return frames in session sorted by filename (= frame_index order)."""
        session_dir = self._root / session_id
        if not session_dir.exists():
            return []
        frames = []
        for fits_path in sorted(session_dir.glob("*.fits")):
            frame_stem = fits_path.stem
            json_path = session_dir / f"{frame_stem}.json"
            entry: dict = {
                "frame_stem": frame_stem,
                "size_bytes": fits_path.stat().st_size,
            }
            if json_path.exists():
                try:
                    sidecar = json.loads(json_path.read_text(encoding="utf-8"))
                    entry.update({
                        "state": sidecar.get("state"),
                        "frame_index": sidecar.get("frame_index"),
                        "captured_at": sidecar.get("captured_at"),
                        "exposure_s": sidecar.get("exposure_s"),
                        "gain": sidecar.get("gain"),
                    })
                except Exception:
                    pass
            frames.append(entry)
        return frames

    def load_frame(self, session_id: str, frame_stem: str) -> "FitsFrame":
        """Load a stored FITS frame. Raises FileNotFoundError if absent."""
        from ...domain.frame import FitsFrame
        fits_path = self._root / session_id / f"{frame_stem}.fits"
        if not fits_path.exists():
            raise FileNotFoundError(fits_path)
        return FitsFrame.from_fits_bytes(fits_path.read_bytes())

    def load_sidecar(self, session_id: str, frame_stem: str) -> dict:
        """Load JSON sidecar. Raises FileNotFoundError if absent."""
        json_path = self._root / session_id / f"{frame_stem}.json"
        if not json_path.exists():
            raise FileNotFoundError(json_path)
        return json.loads(json_path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/services/test_frame_archive.py -v
```

Expected: all 7 PASS

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/services/collimation/frame_archive.py tests/unit/services/test_frame_archive.py
git commit -m "feat(COL-ARC): add CollimationFrameArchive FITS+sidecar storage service"
```

---

## Task 3: CollimationAssistant — session ID and archive wiring

**Files:**
- Modify: `smart_telescope/services/collimation/assistant.py`
- Test: `tests/unit/services/test_collimation_guiding.py` (append 3 tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/services/test_collimation_guiding.py`:

```python
def test_frame_archive_property_returns_injected_archive():
    from unittest.mock import MagicMock
    archive = MagicMock()
    assistant = _make_minimal_assistant(frame_archive=archive)
    assert assistant.frame_archive is archive


def test_no_frame_archive_property_is_none():
    assistant = _make_minimal_assistant()
    assert assistant.frame_archive is None


def test_archive_new_session_called_on_start():
    from unittest.mock import MagicMock
    from smart_telescope.services.collimation.assistant import CollimationAssistant
    archive = MagicMock()
    a = CollimationAssistant(
        camera=MagicMock(
            **{"get_bit_depth.return_value": 16,
               "get_exposure_ms.return_value": 100.0,
               "get_gain.return_value": 100}
        ),
        mount=MagicMock(),
        focuser=MagicMock(),
        frame_archive=archive,
    )
    a.start()
    archive.new_session.assert_called_once()
```

- [ ] **Step 2: Update `_make_minimal_assistant` helper to accept `frame_archive`**

In `tests/unit/services/test_collimation_guiding.py`, change the `_make_minimal_assistant` function signature:

```python
def _make_minimal_assistant(guiding_service=None, guide_cameras=None, frame_archive=None):
    from smart_telescope.services.collimation.assistant import CollimationAssistant
    cam = MagicMock()
    cam.get_bit_depth.return_value = 16
    cam.get_exposure_ms.return_value = 100.0
    cam.get_gain.return_value = 100
    mount = MagicMock()
    focuser = MagicMock()
    return CollimationAssistant(
        camera=cam,
        mount=mount,
        focuser=focuser,
        guiding_service=guiding_service,
        guide_cameras=guide_cameras or {},
        frame_archive=frame_archive,
    )
```

- [ ] **Step 3: Run tests to verify they fail**

```
pytest tests/unit/services/test_collimation_guiding.py::test_frame_archive_property_returns_injected_archive tests/unit/services/test_collimation_guiding.py::test_no_frame_archive_property_is_none tests/unit/services/test_collimation_guiding.py::test_archive_new_session_called_on_start -v
```

Expected: `TypeError: CollimationAssistant.__init__() got an unexpected keyword argument 'frame_archive'`

- [ ] **Step 4: Update `smart_telescope/services/collimation/assistant.py`**

**4a. Add TYPE_CHECKING import for `CollimationFrameArchive`**

In the `if TYPE_CHECKING:` block (currently has `GuidingService`), add:

```python
if TYPE_CHECKING:
    from ...services.guiding_service import GuidingService
    from .frame_archive import CollimationFrameArchive
```

**4b. Add `frame_archive` parameter to `__init__`**

Change the `__init__` signature to add the new optional parameter after `guide_cameras`:

```python
    def __init__(
        self,
        camera: CameraPort,
        mount: MountPort,
        focuser: FocuserPort,
        guiding_service: "GuidingService | None" = None,
        guide_cameras: "dict[str, CameraPort] | None" = None,
        frame_archive: "CollimationFrameArchive | None" = None,
    ) -> None:
```

In the `__init__` body, after `self._guide_cameras: dict[str, CameraPort] = guide_cameras or {}`, add:

```python
        self._frame_archive = frame_archive
        self._session_id: str = ""
```

**4c. Add `frame_archive` property**

Add after the `_new_report_builder` method:

```python
    @property
    def frame_archive(self) -> "CollimationFrameArchive | None":
        return self._frame_archive
```

**4d. Generate session ID and call `new_session` in `start()`**

Inside the `with self._lock:` block in `start()`, after `self._frame_counter = 0`, add:

```python
            import uuid
            self._session_id = str(uuid.uuid4())
            if self._frame_archive is not None:
                self._frame_archive.new_session(self._session_id)
```

**4e. Save accepted donut frames in `_handle_measure_donut`**

In `_handle_measure_donut`, inside the `if result.reason == "ok" and result.measurement is not None:` block, after the `with self._lock:` block and before `self._do_transition(CollimationState.GUIDE_ROUGH_COLLIMATION)`, add:

```python
                if self._frame_archive is not None:
                    self._frame_archive.save_frame(
                        session_id=self._session_id,
                        state="measure_donut",
                        frame_index=self._frame_counter,
                        captured_at=_now(),
                        exposure_s=exposure_s,
                        gain=self._camera.get_gain(),
                        bit_depth=bit_depth,
                        ref_x=raw.width / 2.0,
                        ref_y=raw.height / 2.0,
                        raw_frame=raw,
                        analysis={
                            "reason": "ok",
                            "error_x_px": donut.error_x_px,
                            "error_y_px": donut.error_y_px,
                            "error_magnitude_px": donut.error_magnitude_px,
                            "confidence": donut.confidence,
                        },
                    )
```

**4f. Save accepted spike frames in `_handle_measure_spikes`**

In `_handle_measure_spikes`, inside the loop, after the `with self._lock:` block that sets `self._last_frame` and before the `_log.info(...)` call, add:

```python
            if self._frame_archive is not None:
                self._frame_archive.save_frame(
                    session_id=self._session_id,
                    state="measure_spikes",
                    frame_index=self._frame_counter,
                    captured_at=_now(),
                    exposure_s=exposure_s,
                    gain=self._camera.get_gain(),
                    bit_depth=bit_depth,
                    ref_x=ref.x,
                    ref_y=ref.y,
                    raw_frame=raw,
                    analysis={
                        "reason": "ok",
                        "focus_error_px": spike_result.measurement.focus_error_px,
                        "offset_from_ref_px": spike_result.measurement.offset_from_ref_px,
                        "confidence": spike_result.measurement.confidence,
                    },
                )
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/unit/services/test_collimation_guiding.py -v
```

Expected: all 10 tests PASS

- [ ] **Step 6: Run full suite to check no regressions**

```
pytest tests/unit/ -q --tb=short --ignore=tests/unit/api/test_bug005_isolation.py 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add smart_telescope/services/collimation/assistant.py tests/unit/services/test_collimation_guiding.py
git commit -m "feat(COL-ARC): inject CollimationFrameArchive into CollimationAssistant; save donut+spike frames"
```

---

## Task 4: API wiring and archive endpoints

**Files:**
- Modify: `smart_telescope/api/collimation.py`
- Create: `tests/unit/api/test_collimation_archive_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/api/test_collimation_archive_api.py`:

```python
"""API tests for GET/POST /api/collimation/archive/*."""
import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from smart_telescope.app import app
from smart_telescope.api import collimation as col_module
from smart_telescope.domain.frame import FitsFrame


def _make_frame(width: int = 100, height: int = 100) -> FitsFrame:
    pixels = np.zeros((height, width), dtype=np.float32)
    pixels[50, 50] = 1000.0
    return FitsFrame(pixels=pixels, header=fits.Header(), exposure_seconds=2.0)


@pytest.fixture(autouse=True)
def reset_assistant():
    original = col_module._assistant
    yield
    col_module._assistant = original


@pytest.fixture()
def mock_archive():
    archive = MagicMock()
    archive.list_sessions.return_value = [
        {
            "session_id": "abc-123",
            "frame_count": 2,
            "state_counts": {"measure_donut": 2},
            "size_bytes": 1000,
        }
    ]
    archive.list_frames.return_value = [
        {
            "frame_stem": "measure_donut_0001",
            "state": "measure_donut",
            "frame_index": 1,
            "captured_at": "2026-01-01T00:00:00+00:00",
            "exposure_s": 2.0,
            "gain": 100,
            "size_bytes": 500,
        }
    ]
    archive.load_frame.return_value = _make_frame()
    archive.load_sidecar.return_value = {
        "state": "measure_donut",
        "bit_depth": 16,
        "ref_x": 50.0,
        "ref_y": 50.0,
        "analysis": {"reason": "ok", "error_x_px": 1.5, "error_y_px": -0.5},
    }
    return archive


@pytest.fixture()
def client(mock_archive):
    assistant = MagicMock()
    assistant.frame_archive = mock_archive
    col_module._assistant = assistant
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_no_archive():
    assistant = MagicMock()
    assistant.frame_archive = None
    col_module._assistant = assistant
    with TestClient(app) as c:
        yield c


def test_list_sessions_returns_list(client):
    r = client.get("/api/collimation/archive")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["session_id"] == "abc-123"


def test_list_sessions_no_archive_returns_disabled(client_no_archive):
    r = client_no_archive.get("/api/collimation/archive")
    assert r.status_code == 200
    data = r.json()
    assert data == {"enabled": False, "sessions": []}


def test_list_frames_returns_list(client):
    r = client.get("/api/collimation/archive/abc-123")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert len(data["frames"]) == 1
    assert data["frames"][0]["frame_stem"] == "measure_donut_0001"


def test_list_frames_no_archive_returns_disabled(client_no_archive):
    r = client_no_archive.get("/api/collimation/archive/abc-123")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "session_id": "abc-123", "frames": []}


def test_replay_returns_original_and_replayed(client):
    r = client.post("/api/collimation/archive/abc-123/measure_donut_0001/replay")
    assert r.status_code == 200
    data = r.json()
    assert "original" in data
    assert "replayed" in data
    assert data["original"]["error_x_px"] == 1.5
    assert data["state"] == "measure_donut"


def test_replay_missing_frame_returns_404(client, mock_archive):
    mock_archive.load_frame.side_effect = FileNotFoundError("not found")
    r = client.post("/api/collimation/archive/abc-123/nonexistent_0001/replay")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/api/test_collimation_archive_api.py -v
```

Expected: 404 errors on archive routes (endpoints don't exist yet)

- [ ] **Step 3: Update `_get_assistant()` to build and pass the archive**

In `smart_telescope/api/collimation.py`, inside the `_get_assistant()` function, in the `with _assistant_lock:` block, after the existing `guiding_svc` setup block and before creating `_assistant`, add:

```python
                from ..services.collimation.frame_archive import CollimationFrameArchive
                from pathlib import Path
                arc_cfg = col_cfg.archive
                frame_archive: CollimationFrameArchive | None = None
                if arc_cfg.enabled:
                    archive_dir = (
                        Path(arc_cfg.archive_dir)
                        if arc_cfg.archive_dir
                        else Path.home() / ".SmartTScope" / "frame_archive"
                    )
                    frame_archive = CollimationFrameArchive(
                        archive_dir, arc_cfg.max_frames_per_session
                    )
```

Change the `CollimationAssistant(...)` call to include `frame_archive=frame_archive`:

```python
                _assistant = CollimationAssistant(
                    camera=get_camera(),
                    mount=get_mount(),
                    focuser=get_focuser(),
                    guiding_service=guiding_svc,
                    guide_cameras=guide_cameras,
                    frame_archive=frame_archive,
                )
```

- [ ] **Step 4: Add the three archive endpoints to `smart_telescope/api/collimation.py`**

Add after the existing `GET /report` endpoint and before the `# ── Self-test endpoints` section:

```python
# ── Archive endpoints ─────────────────────────────────────────────────────────

@router.get("/archive")
def archive_list_sessions() -> dict[str, Any]:
    """List all archived collimation sessions."""
    archive = _get_assistant().frame_archive
    if archive is None:
        return {"enabled": False, "sessions": []}
    return {"enabled": True, "sessions": archive.list_sessions()}


@router.get("/archive/{session_id}")
def archive_list_frames(session_id: str) -> dict[str, Any]:
    """List frames in a single archived session."""
    archive = _get_assistant().frame_archive
    if archive is None:
        return {"enabled": False, "session_id": session_id, "frames": []}
    return {
        "enabled": True,
        "session_id": session_id,
        "frames": archive.list_frames(session_id),
    }


@router.post("/archive/{session_id}/{frame_stem}/replay")
def archive_replay(session_id: str, frame_stem: str) -> dict[str, Any]:
    """Re-run stored frame through its original analysis pipeline."""
    archive = _get_assistant().frame_archive
    if archive is None:
        raise HTTPException(status_code=503, detail="Frame archive is not enabled")
    try:
        raw = archive.load_frame(session_id, frame_stem)
        sidecar = archive.load_sidecar(session_id, frame_stem)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Frame {session_id}/{frame_stem} not found"
        )

    from ..domain.collimation.processing.frame import normalize_frame
    bit_depth = int(sidecar.get("bit_depth", 16))
    processed = normalize_frame(raw, bit_depth=bit_depth)
    state = sidecar["state"]

    new_result: dict[str, Any]
    if state == "measure_donut":
        from ..domain.collimation.processing.donut_detection import DonutAnalyzer
        result = DonutAnalyzer().analyze(processed)
        if result.reason == "ok" and result.measurement is not None:
            d = result.measurement
            new_result = {
                "reason": "ok",
                "error_x_px": d.error_x_px,
                "error_y_px": d.error_y_px,
                "error_magnitude_px": d.error_magnitude_px,
                "confidence": d.confidence,
            }
        else:
            new_result = {"reason": result.reason}
    elif state == "measure_spikes":
        from ..domain.collimation.models import Point2D
        from ..domain.collimation.processing.spike_detection import detect_spikes
        ref = Point2D(
            x=float(sidecar.get("ref_x", processed.width / 2)),
            y=float(sidecar.get("ref_y", processed.height / 2)),
        )
        sr = detect_spikes(processed, ref)
        if sr.measurement is not None:
            m = sr.measurement
            new_result = {
                "reason": sr.reason,
                "focus_error_px": m.focus_error_px,
                "offset_from_ref_px": m.offset_from_ref_px,
                "confidence": m.confidence,
            }
        else:
            new_result = {"reason": sr.reason}
    else:
        raise HTTPException(
            status_code=422, detail=f"No replay handler for state '{state}'"
        )

    return {
        "session_id": session_id,
        "frame_stem": frame_stem,
        "state": state,
        "original": sidecar.get("analysis", {}),
        "replayed": new_result,
    }
```

- [ ] **Step 5: Run archive API tests**

```
pytest tests/unit/api/test_collimation_archive_api.py -v
```

Expected: all 6 PASS

- [ ] **Step 6: Run full suite to check no regressions**

```
pytest tests/unit/ -q --tb=short --ignore=tests/unit/api/test_bug005_isolation.py 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 7: Commit**

```bash
git add smart_telescope/api/collimation.py tests/unit/api/test_collimation_archive_api.py
git commit -m "feat(COL-ARC): add archive API endpoints list-sessions/list-frames/replay"
```

---

## Task 5: Config template and wiki

**Files:**
- Modify: `templates/config.toml`
- Modify: `wiki/index.md`
- Modify: `wiki/log.md`

- [ ] **Step 1: Add `[collimation.archive]` section to `templates/config.toml`**

Find the `[collimation]` section. After all existing collimation keys (before the next top-level section), add:

```toml
# ---------------------------------------------------------------------------
# Collimation frame archive (opt-in)
# Saves accepted donut/spike frames as FITS + JSON sidecar for offline replay.
# ---------------------------------------------------------------------------
[collimation.archive]
enabled                  = false
# archive_dir            = ""      # empty = ~/.SmartTScope/frame_archive
max_frames_per_session   = 50
```

- [ ] **Step 2: Update `wiki/index.md`**

In the `## Collimation Assistant` section, append after the last `- **Phase N done:**` bullet:

```markdown
- **Frame archive done:** `CollimationFrameArchive` saves accepted FITS frames + JSON sidecars (state, analysis, ref, bit_depth) under `~/.SmartTScope/frame_archive/<session_id>/`; opt-in via `[collimation.archive] enabled = true`; `GET /api/collimation/archive`, `GET /api/collimation/archive/{session_id}`, `POST /api/collimation/archive/{session_id}/{frame_stem}/replay` (re-runs donut or spike analysis on stored frame)
```

- [ ] **Step 3: Append to `wiki/log.md`**

Prepend a new entry (after the `---` separator line at the top, before the existing most-recent entry):

```markdown
## 2026-05-24 — COL-ARC — Collimation frame archive

**What changed:**

- `smart_telescope/domain/collimation/config.py`: `ArchiveConfig` dataclass (`enabled`, `archive_dir`, `max_frames_per_session`); `CollimationConfig` gains `archive: ArchiveConfig` field

- `smart_telescope/services/collimation/frame_archive.py` (NEW): `CollimationFrameArchive` — `new_session()` creates `<archive_dir>/<session_id>/`; `save_frame()` writes FITS via `FitsFrame.to_fits_bytes()` + JSON sidecar with state/analysis/ref_x/ref_y/bit_depth; silently skips when `max_frames_per_session` reached; `list_sessions()` newest-first by mtime; `list_frames()` sorted by filename; `load_frame()` / `load_sidecar()` raise `FileNotFoundError` when absent; 7 tests in `tests/unit/services/test_frame_archive.py`

- `smart_telescope/services/collimation/assistant.py`: `__init__` accepts `frame_archive: CollimationFrameArchive | None`; `start()` generates `uuid4` session ID and calls `archive.new_session()`; `frame_archive` property; `_handle_measure_donut` saves raw frame + donut analysis dict after each accepted measurement; `_handle_measure_spikes` saves raw frame + spike analysis dict after each accepted measurement; 3 new tests in `test_collimation_guiding.py`

- `smart_telescope/api/collimation.py`: `_get_assistant()` builds `CollimationFrameArchive` from `col_cfg.archive` when `enabled=True`, passes to `CollimationAssistant`; `GET /api/collimation/archive` lists sessions (returns `{"enabled": false, "sessions": []}` when disabled); `GET /api/collimation/archive/{session_id}` lists frames; `POST /api/collimation/archive/{session_id}/{frame_stem}/replay` re-runs `DonutAnalyzer` or `detect_spikes` on stored frame and returns `{"original": ..., "replayed": ...}`; 6 tests in `tests/unit/api/test_collimation_archive_api.py`

- `templates/config.toml`: `[collimation.archive]` section added (disabled by default)

---
```

- [ ] **Step 4: Run full test suite**

```
pytest tests/unit/ -q --tb=short --ignore=tests/unit/api/test_bug005_isolation.py 2>&1 | tail -5
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add templates/config.toml wiki/index.md wiki/log.md
git commit -m "docs: add collimation frame archive config template and wiki entries"
```

---

## Self-Review

**1. Spec coverage:**

| Requirement | Task |
|---|---|
| Opt-in via config (`enabled = false` default) | Task 1 (`ArchiveConfig`) + Task 5 (template) |
| Save accepted donut frames | Task 3 (assistant `_handle_measure_donut`) |
| Save accepted spike frames | Task 3 (assistant `_handle_measure_spikes`) |
| FITS file per frame | Task 2 (`save_frame` via `to_fits_bytes`) |
| JSON sidecar with state + analysis + ref + bit_depth | Task 2 (`save_frame` sidecar dict) |
| Session UUID per collimation run | Task 3 (uuid4 in `start()`) |
| Max-frames-per-session cap | Task 2 (`save_frame` glob + lock) |
| Configurable archive directory | Task 1 (`archive_dir`) + Task 4 (Path resolution) |
| List sessions API | Task 4 (`GET /archive`) |
| List frames API | Task 4 (`GET /archive/{session_id}`) |
| Replay API — donut | Task 4 (`DonutAnalyzer.analyze()` replay branch) |
| Replay API — spikes | Task 4 (`detect_spikes()` replay branch) |
| 404 on missing frame | Task 4 (replay `FileNotFoundError` → 404) |
| 503 when archive disabled at replay | Task 4 (replay guard) |

No gaps found.

**2. Placeholder scan:** None. Every step has complete code.

**3. Type consistency:**

- `CollimationFrameArchive.__init__(archive_dir: Path, max_frames_per_session: int)` ✅ called with `Path(...)` in Task 4
- `save_frame(session_id, state, frame_index, captured_at, exposure_s, gain, bit_depth, ref_x, ref_y, raw_frame, analysis)` ✅ all 11 args supplied in Task 3 donut/spike calls with matching types
- `load_frame(session_id, frame_stem) → FitsFrame` ✅ used in Task 4 replay; `normalize_frame(raw, bit_depth=...)` accepts `FitsFrame`
- `load_sidecar(session_id, frame_stem) → dict` ✅ keys `state`, `bit_depth`, `ref_x`, `ref_y`, `analysis` set in Task 2 and read in Task 4
- `detect_spikes(processed, ref: Point2D)` — `ref` constructed as `Point2D(x=..., y=...)` ✅ matches `ReferenceCenterCalibration.compute()` return type
- `archive_replay` returns `{"original": sidecar["analysis"], "replayed": new_result}` ✅ tested in `test_replay_returns_original_and_replayed`
- `_get_assistant().frame_archive` property used by all 3 archive endpoints ✅ wired in Task 3
