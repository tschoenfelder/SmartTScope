# Camera Offset Estimation Wizard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dedicated bias-frame estimation wizard (card in Stage 6) that captures bias frames at minimum exposure, analyzes pixel statistics, sweeps offset values from 0 upward, and recommends the lowest safe offset per camera model and gain mode.

**Architecture:** `domain/bias_estimation.py` holds pure domain models (`BiasFrameStats`, `OffsetSweepPoint`, `BiasEstimationResult`). `services/bias_estimation_service.py` captures frames and runs analysis using numpy. `api/bias_estimation.py` exposes async endpoints (`POST /start`, `GET /status/{job_id}`) backed by `JobManager`. A new wizard card in Stage 6 (`static/js/bias_estimation.js` + HTML in `index.html`) drives the workflow. The wizard shows per-offset stats in a table and highlights the recommended value. Result includes a config snippet the user can copy to `config.toml`.

**Tech Stack:** Python 3.13, numpy, pytest, FastAPI; existing `CameraPort`, `ConversionGain`, `JobManager`, `FitsFrame`

**Dependency:** Standalone — does not depend on CID or CO plans. Naturally follows CO (so users can estimate offsets then enter them in config).

---

## File Map

| Action  | Path |
|---------|------|
| Create  | `smart_telescope/domain/bias_estimation.py` |
| Create  | `smart_telescope/services/bias_estimation_service.py` |
| Create  | `smart_telescope/api/bias_estimation.py` |
| Modify  | `smart_telescope/app.py` — register router |
| Create  | `smart_telescope/static/js/bias_estimation.js` |
| Modify  | `smart_telescope/static/index.html` — add wizard card in Stage 6 |
| Create  | `tests/unit/domain/test_bias_estimation.py` |
| Create  | `tests/unit/services/test_bias_estimation_service.py` |
| Create  | `tests/unit/api/test_bias_estimation_api.py` |

---

### Task 1: Domain models

**Files:**
- Create: `smart_telescope/domain/bias_estimation.py`
- Create: `tests/unit/domain/test_bias_estimation.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/domain/test_bias_estimation.py
import numpy as np
import pytest
from smart_telescope.domain.bias_estimation import (
    BiasFrameStats,
    OffsetSweepPoint,
    BiasEstimationResult,
    analyze_frame,
    ZERO_CLIP_THRESHOLD,
)


# --- analyze_frame ---

def test_analyze_frame_all_zero_pixels():
    pixels = np.zeros((100, 100), dtype=np.float32)
    stats = analyze_frame(pixels, frame_index=0)
    assert stats.min_val == 0
    assert stats.max_val == 0
    assert stats.mean == pytest.approx(0.0)
    assert stats.zero_count == 10000
    assert stats.zero_fraction == pytest.approx(1.0)


def test_analyze_frame_no_zero_pixels():
    pixels = np.full((100, 100), 50, dtype=np.float32)
    stats = analyze_frame(pixels, frame_index=0)
    assert stats.min_val == 50
    assert stats.zero_count == 0
    assert stats.zero_fraction == pytest.approx(0.0)


def test_analyze_frame_partial_zeros():
    pixels = np.full((100, 100), 10, dtype=np.float32)
    pixels[:10, :] = 0  # 1000 zero pixels out of 10000
    stats = analyze_frame(pixels, frame_index=0)
    assert stats.zero_count == 1000
    assert stats.zero_fraction == pytest.approx(0.1)


def test_analyze_frame_mean_median_std():
    rng = np.random.default_rng(42)
    pixels = rng.normal(loc=150.0, scale=10.0, size=(200, 200)).astype(np.float32)
    pixels = np.clip(pixels, 0, 65535)
    stats = analyze_frame(pixels, frame_index=2)
    assert stats.frame_index == 2
    assert abs(stats.mean - 150.0) < 2.0
    assert abs(stats.median - 150.0) < 2.0
    assert abs(stats.std - 10.0) < 2.0


def test_analyze_frame_histogram_has_256_bins():
    pixels = np.arange(256, dtype=np.float32).reshape(16, 16)
    stats = analyze_frame(pixels, frame_index=0)
    assert len(stats.histogram) == 256


# --- OffsetSweepPoint is_safe ---

def test_sweep_point_safe_when_below_threshold():
    pt = OffsetSweepPoint(offset=50, zero_fraction=0.0001, min_val=5)
    assert pt.is_safe is True


def test_sweep_point_unsafe_when_above_threshold():
    pt = OffsetSweepPoint(offset=0, zero_fraction=0.005, min_val=0)
    assert pt.is_safe is False


def test_sweep_point_threshold_boundary():
    # ZERO_CLIP_THRESHOLD = 0.001 (0.1%)
    pt_just_safe     = OffsetSweepPoint(offset=0, zero_fraction=ZERO_CLIP_THRESHOLD - 1e-9, min_val=1)
    pt_just_unsafe   = OffsetSweepPoint(offset=0, zero_fraction=ZERO_CLIP_THRESHOLD, min_val=0)
    assert pt_just_safe.is_safe is True
    assert pt_just_unsafe.is_safe is False


# --- BiasEstimationResult.recommended_offset logic ---

def test_result_recommends_lowest_safe_offset():
    sweep = [
        OffsetSweepPoint(offset=0,  zero_fraction=0.05,  min_val=0),   # unsafe
        OffsetSweepPoint(offset=5,  zero_fraction=0.002, min_val=0),   # unsafe
        OffsetSweepPoint(offset=10, zero_fraction=0.0005,min_val=2),   # safe ← first safe
        OffsetSweepPoint(offset=20, zero_fraction=0.0,   min_val=15),  # safe
    ]
    result = BiasEstimationResult(
        camera_model="G3M678M", gain_mode_name="LCG",
        frame_count=10, mean_stats=sweep[0],  # reusing OffsetSweepPoint as placeholder
        sweep=sweep,
    )
    assert result.recommended_offset == 10


def test_result_recommends_zero_when_no_clipping():
    sweep = [
        OffsetSweepPoint(offset=0, zero_fraction=0.0, min_val=5),
    ]
    result = BiasEstimationResult(
        camera_model="G3M678M", gain_mode_name="LCG",
        frame_count=10, mean_stats=sweep[0],
        sweep=sweep,
    )
    assert result.recommended_offset == 0


def test_result_recommends_max_when_all_unsafe():
    sweep = [
        OffsetSweepPoint(offset=i*10, zero_fraction=0.01, min_val=0)
        for i in range(5)
    ]
    result = BiasEstimationResult(
        camera_model="G3M678M", gain_mode_name="LCG",
        frame_count=10, mean_stats=sweep[0],
        sweep=sweep,
    )
    # Falls back to highest tested offset when nothing is safe
    assert result.recommended_offset == 40
    assert result.safe is False


def test_result_toml_snippet():
    sweep = [OffsetSweepPoint(offset=150, zero_fraction=0.0, min_val=10)]
    result = BiasEstimationResult(
        camera_model="G3M678M", gain_mode_name="LCG",
        frame_count=10, mean_stats=sweep[0],
        sweep=sweep,
    )
    snippet = result.toml_snippet()
    assert "[camera_offsets.G3M678M]" in snippet
    assert "lcg = 150" in snippet
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/domain/test_bias_estimation.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `smart_telescope/domain/bias_estimation.py`**

```python
# smart_telescope/domain/bias_estimation.py
"""Domain models and pure analysis functions for bias-frame offset estimation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

ZERO_CLIP_THRESHOLD = 0.001  # 0.1 % zero pixels = clipping


@dataclass
class BiasFrameStats:
    frame_index: int
    min_val: float
    max_val: float
    mean: float
    median: float
    std: float
    zero_count: int
    zero_fraction: float   # 0.0–1.0
    histogram: list[int]   # 256 bins across [0, max_val] range


@dataclass
class OffsetSweepPoint:
    offset: int
    zero_fraction: float
    min_val: float

    @property
    def is_safe(self) -> bool:
        return self.zero_fraction < ZERO_CLIP_THRESHOLD


@dataclass
class BiasEstimationResult:
    camera_model: str
    gain_mode_name: str        # "LCG", "HCG", "HDR"
    frame_count: int
    mean_stats: Any            # BiasFrameStats for the base offset (no-sweep capture)
    sweep: list[OffsetSweepPoint]

    @property
    def recommended_offset(self) -> int:
        safe = [pt for pt in self.sweep if pt.is_safe]
        if safe:
            return min(safe, key=lambda pt: pt.offset).offset
        return max(self.sweep, key=lambda pt: pt.offset).offset if self.sweep else 0

    @property
    def safe(self) -> bool:
        return any(pt.is_safe for pt in self.sweep)

    def toml_snippet(self) -> str:
        offset = self.recommended_offset
        mode_key = self.gain_mode_name.lower()
        return (
            f"[camera_offsets.{self.camera_model}]\n"
            f"{mode_key} = {offset}\n"
        )


def analyze_frame(pixels: np.ndarray, frame_index: int = 0) -> BiasFrameStats:
    """Compute per-frame statistics for bias analysis."""
    flat = pixels.ravel().astype(np.float32)
    total = flat.size
    zero_count = int(np.sum(flat == 0))

    # 256-bin histogram from 0 to max (or 65535 if all zero)
    max_val_f = float(flat.max()) if total > 0 else 0.0
    hist_max = max(max_val_f, 1.0)
    hist, _ = np.histogram(flat, bins=256, range=(0, hist_max))

    return BiasFrameStats(
        frame_index=frame_index,
        min_val=float(flat.min()) if total > 0 else 0.0,
        max_val=max_val_f,
        mean=float(flat.mean()) if total > 0 else 0.0,
        median=float(np.median(flat)) if total > 0 else 0.0,
        std=float(flat.std()) if total > 0 else 0.0,
        zero_count=zero_count,
        zero_fraction=zero_count / total if total > 0 else 0.0,
        histogram=hist.tolist(),
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/domain/test_bias_estimation.py -v`
Expected: all 14 tests PASS

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/domain/bias_estimation.py tests/unit/domain/test_bias_estimation.py
git commit -m "feat(COE): add bias estimation domain models and analyze_frame function"
```

---

### Task 2: BiasEstimationService — frame capture and sweep

**Files:**
- Create: `smart_telescope/services/bias_estimation_service.py`
- Create: `tests/unit/services/test_bias_estimation_service.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/services/test_bias_estimation_service.py
import threading
import numpy as np
import pytest
from unittest.mock import MagicMock, call
from astropy.io import fits

from smart_telescope.domain.bias_estimation import ZERO_CLIP_THRESHOLD
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.services.bias_estimation_service import BiasEstimationService


def _make_frame(fill: float = 20.0, shape: tuple = (100, 100)) -> FitsFrame:
    pixels = np.full(shape, fill, dtype=np.float32)
    hdr = fits.Header()
    hdr["BITPIX"] = -32
    return FitsFrame(pixels=pixels, header=hdr, exposure_seconds=0.0001)


def _zero_frame(shape: tuple = (100, 100)) -> FitsFrame:
    return _make_frame(fill=0.0, shape=shape)


def _mock_camera(
    logical_name: str = "G3M678M",
    gain_mode: ConversionGain = ConversionGain.LCG,
    min_exp_ms: float = 0.1,
    frame_factory=None,
) -> MagicMock:
    cam = MagicMock()
    cam.get_logical_name.return_value = logical_name
    cam.get_conversion_gain.return_value = gain_mode
    caps = MagicMock()
    caps.min_exposure_ms = min_exp_ms
    cam.get_capabilities.return_value = caps
    cam.get_black_level.return_value = 0
    if frame_factory is None:
        cam.capture.return_value = _make_frame(50.0)
    else:
        cam.capture.side_effect = frame_factory
    return cam


# --- basic capture + analyze ---

def test_estimate_returns_result_with_model_and_gain():
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=3, sweep_offsets=[])
    assert result.camera_model == "G3M678M"
    assert result.gain_mode_name == "LCG"
    assert result.frame_count == 3


def test_estimate_captures_at_minimum_exposure():
    cam = _mock_camera(min_exp_ms=0.05)
    svc = BiasEstimationService(cam)
    svc.estimate(ConversionGain.LCG, frame_count=2, sweep_offsets=[])
    for c in cam.capture.call_args_list:
        exp_s = c.args[0] if c.args else c.kwargs.get("exposure_seconds", 1.0)
        assert exp_s == pytest.approx(0.05 / 1000.0)


def test_estimate_sets_gain_mode_before_capture():
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    svc.estimate(ConversionGain.HCG, frame_count=2, sweep_offsets=[])
    cam.set_conversion_gain.assert_called_with(ConversionGain.HCG)


def test_estimate_restores_original_offset_after_sweep():
    cam = _mock_camera()
    cam.get_black_level.return_value = 42
    svc = BiasEstimationService(cam)
    svc.estimate(ConversionGain.LCG, frame_count=1, sweep_offsets=[0, 10, 20])
    # Last set_black_level call must restore original offset
    last_call = cam.set_black_level.call_args_list[-1]
    assert last_call == call(42)


# --- sweep logic ---

def test_sweep_produces_one_point_per_offset_value():
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=2, sweep_offsets=[0, 5, 10, 20])
    assert len(result.sweep) == 4
    assert [pt.offset for pt in result.sweep] == [0, 5, 10, 20]


def test_sweep_detects_clipping_at_zero_offset():
    def zero_then_normal(exp_s):
        # First capture (at offset=0) returns all-zero frame → clipping
        return _zero_frame()

    cam = _mock_camera(frame_factory=zero_then_normal)
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=1, sweep_offsets=[0])
    assert result.sweep[0].zero_fraction > ZERO_CLIP_THRESHOLD
    assert result.sweep[0].is_safe is False


def test_sweep_marks_safe_when_no_zero_pixels():
    cam = _mock_camera()  # returns fill=50 frame, no zeros
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=1, sweep_offsets=[50])
    assert result.sweep[0].is_safe is True


# --- cancellation ---

def test_estimate_respects_cancel_event():
    cancel = threading.Event()
    cancel.set()  # cancelled immediately
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    result = svc.estimate(
        ConversionGain.LCG, frame_count=100,
        sweep_offsets=[0, 5, 10, 20, 30],
        cancel_event=cancel,
    )
    # Should return early — far fewer than 100 captures
    assert cam.capture.call_count < 100
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/services/test_bias_estimation_service.py -v`
Expected: FAIL with ImportError

- [ ] **Step 3: Implement `BiasEstimationService`**

```python
# smart_telescope/services/bias_estimation_service.py
"""Capture bias frames and estimate the minimum safe sensor offset."""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from ..domain.bias_estimation import (
    BiasEstimationResult,
    BiasFrameStats,
    OffsetSweepPoint,
    analyze_frame,
)
from ..domain.camera_capabilities import ConversionGain
from ..domain.frame import FitsFrame

if TYPE_CHECKING:
    from ..ports.camera import CameraPort

_log = logging.getLogger(__name__)

DEFAULT_SWEEP_OFFSETS = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200]


class BiasEstimationService:
    """Capture bias frames and sweep offset values to find the minimum safe offset."""

    def __init__(self, camera: "CameraPort") -> None:
        self._camera = camera

    def estimate(
        self,
        gain_mode: ConversionGain,
        frame_count: int = 10,
        sweep_offsets: list[int] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> BiasEstimationResult:
        """Capture bias frames and estimate minimum safe offset.

        Args:
            gain_mode: Conversion gain mode to test (LCG/HCG/HDR).
            frame_count: Number of frames to capture per offset value.
            sweep_offsets: Offset values to test.  None = DEFAULT_SWEEP_OFFSETS.
            cancel_event: When set, estimation stops and returns partial results.

        Returns:
            BiasEstimationResult with per-offset stats and recommended_offset.
        """
        if sweep_offsets is None:
            sweep_offsets = DEFAULT_SWEEP_OFFSETS

        caps = self._camera.get_capabilities()
        exp_s = caps.min_exposure_ms / 1000.0

        original_offset = self._camera.get_black_level()
        self._camera.set_conversion_gain(gain_mode)
        model = self._camera.get_logical_name()

        sweep_points: list[OffsetSweepPoint] = []
        base_stats: BiasFrameStats | None = None

        try:
            for offset in sweep_offsets:
                if cancel_event and cancel_event.is_set():
                    _log.info("BiasEstimation: cancelled at offset=%d", offset)
                    break

                self._camera.set_black_level(offset)
                frame_stats = self._capture_and_analyze(frame_count, exp_s, cancel_event)
                if not frame_stats:
                    break  # cancelled during capture

                avg = self._avg_stats(frame_stats)
                pt = OffsetSweepPoint(
                    offset=offset,
                    zero_fraction=avg.zero_fraction,
                    min_val=avg.min_val,
                )
                sweep_points.append(pt)
                if base_stats is None:
                    base_stats = avg  # first offset is the base reference

                _log.info(
                    "BiasEstimation: offset=%d zero_fraction=%.4f min=%.1f safe=%s",
                    offset, pt.zero_fraction, pt.min_val, pt.is_safe,
                )
        finally:
            self._camera.set_black_level(original_offset)

        return BiasEstimationResult(
            camera_model=model,
            gain_mode_name=gain_mode.name,
            frame_count=frame_count,
            mean_stats=base_stats or BiasFrameStats(0, 0, 0, 0, 0, 0, 0, 0.0, []),
            sweep=sweep_points,
        )

    def _capture_and_analyze(
        self,
        count: int,
        exp_s: float,
        cancel_event: threading.Event | None,
    ) -> list[BiasFrameStats]:
        stats: list[BiasFrameStats] = []
        for i in range(count):
            if cancel_event and cancel_event.is_set():
                break
            frame = self._camera.capture(exp_s)
            stats.append(analyze_frame(frame.pixels, frame_index=i))
        return stats

    @staticmethod
    def _avg_stats(stats: list[BiasFrameStats]) -> BiasFrameStats:
        if not stats:
            return BiasFrameStats(0, 0, 0, 0, 0, 0, 0, 0.0, [])
        n = len(stats)
        # Aggregate histogram by summing
        hist_len = len(stats[0].histogram) if stats[0].histogram else 256
        agg_hist = [sum(s.histogram[i] for s in stats if i < len(s.histogram))
                    for i in range(hist_len)]
        return BiasFrameStats(
            frame_index=0,
            min_val=sum(s.min_val for s in stats) / n,
            max_val=max(s.max_val for s in stats),
            mean=sum(s.mean for s in stats) / n,
            median=sum(s.median for s in stats) / n,
            std=sum(s.std for s in stats) / n,
            zero_count=sum(s.zero_count for s in stats),
            zero_fraction=sum(s.zero_fraction for s in stats) / n,
            histogram=agg_hist,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/services/test_bias_estimation_service.py -v`
Expected: all 10 tests PASS

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/services/bias_estimation_service.py tests/unit/services/test_bias_estimation_service.py
git commit -m "feat(COE): add BiasEstimationService — capture bias frames and sweep offsets"
```

---

### Task 3: API endpoints for bias estimation

**Files:**
- Create: `smart_telescope/api/bias_estimation.py`
- Modify: `smart_telescope/app.py`
- Create: `tests/unit/api/test_bias_estimation_api.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/api/test_bias_estimation_api.py
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
import pytest
from smart_telescope.app import app
from smart_telescope.runtime import RuntimeContext, set_runtime


def _make_rt():
    from smart_telescope.adapters.mock.camera import MockCamera
    rt = RuntimeContext()
    rt._camera = MockCamera()
    rt._adapters_built = True
    return rt


def test_start_bias_estimation_returns_job_id():
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)
    resp = client.post("/api/bias_estimation/start", json={
        "camera_role": "main",
        "gain_mode": "LCG",
        "frame_count": 3,
        "run_sweep": False,
    })
    assert resp.status_code in (200, 202)
    data = resp.json()
    assert "job_id" in data


def test_start_bias_estimation_invalid_gain_mode():
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)
    resp = client.post("/api/bias_estimation/start", json={
        "camera_role": "main",
        "gain_mode": "INVALID",
        "frame_count": 3,
        "run_sweep": False,
    })
    assert resp.status_code == 422


def test_status_unknown_job_returns_404():
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)
    resp = client.get("/api/bias_estimation/status/nonexistent-job-id")
    assert resp.status_code == 404


def test_status_completed_job_includes_result():
    """A job that completes synchronously includes recommended_offset."""
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)

    start_resp = client.post("/api/bias_estimation/start", json={
        "camera_role": "main",
        "gain_mode": "LCG",
        "frame_count": 2,
        "run_sweep": False,
    })
    assert start_resp.status_code in (200, 202)
    job_id = start_resp.json()["job_id"]

    import time
    # Poll until done (mock camera is fast)
    for _ in range(20):
        status_resp = client.get(f"/api/bias_estimation/status/{job_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        if data["status"] in ("DONE", "FAILED", "CANCELLED"):
            break
        time.sleep(0.1)

    assert data["status"] == "DONE"
    assert "recommended_offset" in data
    assert "sweep" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/api/test_bias_estimation_api.py -v`
Expected: FAIL — endpoints not registered

- [ ] **Step 3: Create `smart_telescope/api/bias_estimation.py`**

```python
# smart_telescope/api/bias_estimation.py
"""Bias frame estimation API — wizard backend."""
from __future__ import annotations

import logging
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..api.deps import get_runtime
from ..domain.bias_estimation import DEFAULT_SWEEP_OFFSETS
from ..domain.camera_capabilities import ConversionGain
from ..runtime import RuntimeContext

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/bias_estimation", tags=["bias_estimation"])

_VALID_GAIN = {"LCG": ConversionGain.LCG, "HCG": ConversionGain.HCG, "HDR": ConversionGain.HDR}


class BiasEstimationRequest(BaseModel):
    camera_role: str = "main"
    gain_mode: str = "LCG"
    frame_count: int = 10
    run_sweep: bool = True


@router.post("/start")
def start_bias_estimation(
    req: BiasEstimationRequest,
    rt: RuntimeContext = Depends(get_runtime),
) -> dict:
    if req.gain_mode.upper() not in _VALID_GAIN:
        raise HTTPException(status_code=422, detail=f"Invalid gain_mode '{req.gain_mode}'")

    from ..api.deps import resolve_camera_index
    try:
        cam_index = resolve_camera_index(rt, camera_role=req.camera_role)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    camera = rt.get_preview_camera(cam_index)
    sweep = DEFAULT_SWEEP_OFFSETS if req.run_sweep else []
    gain = _VALID_GAIN[req.gain_mode.upper()]

    from ..services.bias_estimation_service import BiasEstimationService
    svc = BiasEstimationService(camera)
    cancel = threading.Event()

    def _worker():
        return svc.estimate(
            gain_mode=gain,
            frame_count=req.frame_count,
            sweep_offsets=sweep if sweep else [],
            cancel_event=cancel,
        )

    job = rt.job_manager.submit(
        name="bias_estimation",
        resources={f"camera:{cam_index}"},
        fn=_worker,
        cancel_event=cancel,
        timeout_s=300,
    )
    return {"job_id": job.id, "status": "RUNNING"}


@router.get("/status/{job_id}")
def get_bias_estimation_status(
    job_id: str,
    rt: RuntimeContext = Depends(get_runtime),
) -> dict:
    job = rt.job_manager.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    resp: dict = {"job_id": job_id, "status": job.status.name}

    if job.status.name == "DONE" and job.result is not None:
        result = job.result
        resp["camera_model"] = result.camera_model
        resp["gain_mode"] = result.gain_mode_name
        resp["frame_count"] = result.frame_count
        resp["recommended_offset"] = result.recommended_offset
        resp["safe"] = result.safe
        resp["toml_snippet"] = result.toml_snippet()
        resp["sweep"] = [
            {
                "offset": pt.offset,
                "zero_fraction": round(pt.zero_fraction, 6),
                "min_val": round(pt.min_val, 1),
                "is_safe": pt.is_safe,
            }
            for pt in result.sweep
        ]
        if hasattr(result, "mean_stats") and result.mean_stats:
            ms = result.mean_stats
            resp["mean_stats"] = {
                "min_val": round(ms.min_val, 1),
                "max_val": round(ms.max_val, 1),
                "mean": round(ms.mean, 2),
                "median": round(ms.median, 2),
                "std": round(ms.std, 2),
                "zero_count": ms.zero_count,
                "zero_fraction": round(ms.zero_fraction, 6),
            }

    if job.status.name == "FAILED":
        resp["error"] = str(getattr(job, "error", "unknown"))

    return resp
```

- [ ] **Step 4: Register the router in `smart_telescope/app.py`**

Add after the other router imports in `app.py`:
```python
from .api.bias_estimation import router as bias_estimation_router
```

Add after the other `app.include_router(...)` calls:
```python
app.include_router(bias_estimation_router)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/unit/api/test_bias_estimation_api.py -v`
Expected: all 4 tests PASS

- [ ] **Step 6: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add smart_telescope/api/bias_estimation.py smart_telescope/app.py tests/unit/api/test_bias_estimation_api.py
git commit -m "feat(COE): add bias estimation API endpoints /start and /status/{job_id}"
```

---

### Task 4: Frontend wizard card (Stage 6)

**Files:**
- Create: `smart_telescope/static/js/bias_estimation.js`
- Modify: `smart_telescope/static/index.html` — add card in Stage 6

- [ ] **Step 1: Create `bias_estimation.js`**

```javascript
// smart_telescope/static/js/bias_estimation.js
// Bias-frame offset estimation wizard card (Stage 6)

let _beJobId = null;
let _bePollTimer = null;

function beLaunchWizard() {
  document.getElementById("be-wizard-section").style.display = "block";
  document.getElementById("be-launch-btn").style.display = "none";
  beResetState();
}

function beHideWizard() {
  document.getElementById("be-wizard-section").style.display = "none";
  document.getElementById("be-launch-btn").style.display = "";
  if (_bePollTimer) { clearInterval(_bePollTimer); _bePollTimer = null; }
  _beJobId = null;
}

function beResetState() {
  document.getElementById("be-status").textContent = "";
  document.getElementById("be-results-table").innerHTML = "";
  document.getElementById("be-recommendation").textContent = "";
  document.getElementById("be-toml-snippet").textContent = "";
  document.getElementById("be-toml-section").style.display = "none";
}

async function beStartEstimation() {
  const cameraRole = document.getElementById("be-camera-role").value;
  const gainMode   = document.getElementById("be-gain-mode").value;
  const frameCount = parseInt(document.getElementById("be-frame-count").value, 10) || 10;
  const runSweep   = document.getElementById("be-run-sweep").checked;

  beResetState();
  document.getElementById("be-status").textContent = "Starting estimation…";

  const resp = await apiPost("/api/bias_estimation/start", {
    camera_role: cameraRole,
    gain_mode:   gainMode,
    frame_count: frameCount,
    run_sweep:   runSweep,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    document.getElementById("be-status").textContent =
      "Error: " + (err.detail || resp.statusText);
    return;
  }

  const data = await resp.json();
  _beJobId = data.job_id;
  document.getElementById("be-status").textContent = "Running…";
  _bePollTimer = setInterval(bePollStatus, 500);
}

async function bePollStatus() {
  if (!_beJobId) return;
  const resp = await fetch(`/api/bias_estimation/status/${_beJobId}`);
  if (!resp.ok) return;
  const data = await resp.json();

  if (data.status === "RUNNING") return;  // keep polling

  clearInterval(_bePollTimer);
  _bePollTimer = null;

  if (data.status === "FAILED" || data.status === "CANCELLED") {
    document.getElementById("be-status").textContent =
      data.status + ": " + (data.error || "");
    return;
  }

  // DONE
  document.getElementById("be-status").textContent =
    `Done — ${data.frame_count} frames captured`;

  // Build results table
  const table = document.getElementById("be-results-table");
  table.innerHTML = `<tr>
    <th>Offset</th><th>Zero %</th><th>Min ADU</th><th>Safe?</th>
  </tr>`;
  for (const pt of (data.sweep || [])) {
    const row = document.createElement("tr");
    const safeBadge = pt.is_safe
      ? '<span style="color:green">✓ Safe</span>'
      : '<span style="color:red">✗ Clipping</span>';
    if (pt.offset === data.recommended_offset) {
      row.style.fontWeight = "bold";
      row.style.background = "#d4f4dd";
    }
    row.innerHTML = `<td>${pt.offset}</td>
      <td>${(pt.zero_fraction * 100).toFixed(3)}%</td>
      <td>${pt.min_val.toFixed(1)}</td>
      <td>${safeBadge}</td>`;
    table.appendChild(row);
  }

  // Recommendation + TOML snippet
  const recEl = document.getElementById("be-recommendation");
  if (data.safe) {
    recEl.textContent = `Recommended offset: ${data.recommended_offset}`;
    recEl.style.color = "green";
  } else {
    recEl.textContent =
      `No fully safe offset found. Best estimate: ${data.recommended_offset}. ` +
      `Consider re-running with higher offset range.`;
    recEl.style.color = "orange";
  }

  if (data.toml_snippet) {
    document.getElementById("be-toml-snippet").textContent = data.toml_snippet;
    document.getElementById("be-toml-section").style.display = "block";
  }
}
```

- [ ] **Step 2: Add wizard card HTML to Stage 6 in `index.html`**

In `index.html`, inside the Stage 6 `<div id="stage6">` section, add the following card (before or after existing camera scan card):

```html
<!-- Bias Estimation Wizard -->
<div class="card" id="be-card">
  <h3>Sensor Offset Estimation</h3>
  <p style="color:#777;font-size:0.9em">
    Capture bias frames to find the lowest offset that prevents pixel clipping.
    Cover the sensor or close the shutter before running.
  </p>

  <button id="be-launch-btn" onclick="beLaunchWizard()">Open Offset Estimation Wizard</button>

  <div id="be-wizard-section" style="display:none">
    <button onclick="beHideWizard()" style="float:right">✕ Close</button>

    <div style="margin:0.5em 0">
      <label>Camera:
        <select id="be-camera-role">
          <option value="main">main</option>
          <option value="guide">guide</option>
        </select>
      </label>
      &nbsp;
      <label>Gain mode:
        <select id="be-gain-mode">
          <option value="LCG">LCG</option>
          <option value="HCG">HCG</option>
          <option value="HDR">HDR</option>
        </select>
      </label>
      &nbsp;
      <label>Frames per offset:
        <input id="be-frame-count" type="number" value="10" min="1" max="100" style="width:4em">
      </label>
      &nbsp;
      <label>
        <input id="be-run-sweep" type="checkbox" checked>
        Run full sweep (0→200)
      </label>
    </div>

    <button onclick="beStartEstimation()">Capture &amp; Analyze</button>

    <p id="be-status" style="margin-top:0.5em"></p>
    <table id="be-results-table" style="border-collapse:collapse;margin:0.5em 0"></table>
    <p id="be-recommendation" style="font-weight:bold;margin:0.5em 0"></p>

    <div id="be-toml-section" style="display:none;margin-top:0.5em">
      <p>Copy this snippet to your <code>config.toml</code>:</p>
      <pre id="be-toml-snippet" style="background:#f4f4f4;padding:0.5em;border-radius:4px"></pre>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Add `<script src="/static/js/bias_estimation.js">` to `index.html`**

In `index.html` in the `<head>` or at the bottom before `</body>`, add:
```html
<script src="/static/js/bias_estimation.js"></script>
```

- [ ] **Step 4: Run smoke tests**

Run: `pytest tests/unit/api/test_smoke.py -v -x`
Expected: all pass (HTML page still loads, no JS errors detectable in smoke test)

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/static/js/bias_estimation.js smart_telescope/static/index.html
git commit -m "feat(COE): add bias estimation wizard card to Stage 6 UI"
```

---

### Task 5: Export DEFAULT_SWEEP_OFFSETS from domain

**Files:**
- Modify: `smart_telescope/domain/bias_estimation.py` — ensure `DEFAULT_SWEEP_OFFSETS` is exported

- [ ] **Step 1: Verify DEFAULT_SWEEP_OFFSETS is importable**

Currently defined in `bias_estimation_service.py`. Move it to `domain/bias_estimation.py` so the API can import it without depending on the service.

In `smart_telescope/domain/bias_estimation.py`, add after `ZERO_CLIP_THRESHOLD`:
```python
DEFAULT_SWEEP_OFFSETS: list[int] = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200]
```

In `smart_telescope/services/bias_estimation_service.py`, change the import:
```python
from ..domain.bias_estimation import (
    BiasEstimationResult,
    BiasFrameStats,
    OffsetSweepPoint,
    analyze_frame,
    DEFAULT_SWEEP_OFFSETS,
)
```

And remove the local `DEFAULT_SWEEP_OFFSETS` definition from the service.

In `smart_telescope/api/bias_estimation.py`, change:
```python
from ..domain.bias_estimation import DEFAULT_SWEEP_OFFSETS
```

- [ ] **Step 2: Run full test suite**

Run: `pytest tests/ -x -q`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add smart_telescope/domain/bias_estimation.py smart_telescope/services/bias_estimation_service.py smart_telescope/api/bias_estimation.py
git commit -m "refactor(COE): move DEFAULT_SWEEP_OFFSETS to domain layer"
```

---

### Task 6: Update todo.md and wiki/log.md

- [ ] **Step 1: Add COE section to `docs/todo.md`**

```markdown
## Camera Offset Estimation Wizard

*Source: `resources/hlrequirements/camera_offset_estimation.md`*

- [x] COE-001 Domain models: `BiasFrameStats`, `OffsetSweepPoint`, `BiasEstimationResult`, `analyze_frame` `[P1 · Domain]`
- [x] COE-002 `BiasEstimationService` — capture frames + sweep offset values `[P1 · Service]`
- [x] COE-003 API endpoints: `POST /api/bias_estimation/start`, `GET /api/bias_estimation/status/{id}` `[P1 · API]`
- [x] COE-004 Frontend wizard card in Stage 6: sweep table, recommendation, TOML snippet `[P1 · UI]`
- [ ] COE-005 Verify wizard on real hardware: G3M678M LCG sweep produces expected recommendation `[P1 · Hardware]`
- [ ] COE-006 Verify wizard on real hardware: GPCMOS02000KPA LCG sweep `[P1 · Hardware]`
```

- [ ] **Step 2: Append to `wiki/log.md`**

```
## 2026-05-20 — Camera Offset Estimation Wizard (COE)
Source: resources/hlrequirements/camera_offset_estimation.md
Changes: domain models (BiasFrameStats, OffsetSweepPoint, BiasEstimationResult, analyze_frame); BiasEstimationService; /api/bias_estimation endpoints; Stage 6 wizard card with sweep table, recommendation, TOML snippet. COE-001..004 complete.
```

- [ ] **Step 3: Commit**

```bash
git add docs/todo.md wiki/log.md
git commit -m "docs: add COE items to todo.md and wiki/log.md"
```

---

## Self-Review

**Spec coverage:**
- ✅ Capture bias frames at minimum exposure → `BiasEstimationService._capture_and_analyze()` uses `caps.min_exposure_ms`
- ✅ Analyze frames: min, mean, median, std, zero-pixel count/% → `analyze_frame()` + `BiasFrameStats`
- ✅ Estimate lowest safe offset → `BiasEstimationResult.recommended_offset` picks first safe `OffsetSweepPoint`
- ✅ Separate results per camera model and gain mode → `gain_mode_name` + `camera_model` in result
- ✅ Recommended offset can be transferred to config → `toml_snippet()` shown in UI
- ✅ Acceptance: capture bias frames for new camera → Task 2 (service)
- ✅ Acceptance: report key stats including zero-pixel count → Task 1 domain models + Task 4 UI table
- ✅ Acceptance: offset keeps bias safely above zero → `is_safe` property on `OffsetSweepPoint`

**Placeholder scan:** None found.

**Type consistency:**
- `analyze_frame(pixels: np.ndarray, frame_index: int) -> BiasFrameStats` used in Task 1 tests and Task 2 service
- `BiasEstimationResult.recommended_offset` computed from `sweep: list[OffsetSweepPoint]` consistently
- `DEFAULT_SWEEP_OFFSETS` defined in domain, imported in service and API — consistent after Task 5
- `svc.estimate(gain_mode, frame_count, sweep_offsets, cancel_event)` matches Task 2 tests and Task 3 API
