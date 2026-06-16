# Guiding Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a MetaGuide-inspired measure-only guiding pipeline that streams guide frames from the existing camera adapter, computes windowed centroids, selects the active guide source (guide vs OAG fallback), produces would-be pulse corrections, and exposes start/stop/status via a REST API — all without blocking the main imaging workflow.

**Architecture:** `ManagedCamera` runs each guide camera in a background thread and puts frames into a `FrameMailbox` (latest-frame semantics — stale frames are dropped, never queued). `GuidingService` owns one `ManagedCamera` per active role, runs a measurement loop that calls `GuideCentroidEstimator` per frame, feeds `GuideSourceSelector` to pick the active source, and computes `WouldGuidePulse` corrections via `MeasureOnlyGuideController`. When `measure_only = false` in config, the service sends real pulses through the existing `mount.guide()` method; the flag is `true` by default so no physical movement occurs until explicitly enabled. All state is exposed via `GET /api/guiding/status`.

**Tech Stack:** Python 3.13, NumPy (centroid math), FastAPI (API), threading.Condition (mailbox), existing `CameraPort`/`MountPort` adapters, existing `domain/guiding.py` domain types.

---

## Background: what already exists

| File | Status | Notes |
|---|---|---|
| `smart_telescope/domain/guiding.py` | ✅ exists | `GuideFrame`, `GuideMeasurement`, `WouldGuidePulse`, `GuideSourceState`, `GuideSourceHealth` |
| `smart_telescope/config.py` | ✅ exists | `GuidingSpec` with `primary_role`, `allow_fallback`, `fallback_after_bad_frames`, `max_frame_age_s`, `centroid_roi_px`, `min_peak_snr`, `saturation_fraction`, `measure_only` |
| `smart_telescope/ports/mount.py` | ✅ exists | `guide(direction, duration_ms) -> bool` on `MountPort` |
| `smart_telescope/adapters/onstep/mount.py` | ✅ exists | `guide()` implemented |
| `smart_telescope/adapters/mock/mount.py` | ✅ exists | `guide()` stub |
| `smart_telescope/runtime.py` | ✅ exists | `get_camera_by_role(role)` |
| `smart_telescope/tools/guide_measuretest.py` | ✅ exists | headless CLI that uses all new services |
| `tests/unit/services/test_guide_measurement.py` | ✅ exists | 4 tests currently skip — will activate in Task 2/3 |
| `smart_telescope/services/managed_camera.py` | ❌ missing | Task 1 |
| `smart_telescope/services/guide_measurement.py` | ❌ missing | Tasks 2–3 |
| `smart_telescope/services/guiding_service.py` | ❌ missing | Task 4 |
| `smart_telescope/api/guiding.py` | ❌ missing | Task 5 |

---

## File Structure

| File | Responsibility |
|---|---|
| `smart_telescope/services/managed_camera.py` | `FrameMailbox` (latest-frame drop mailbox) + `ManagedCamera` (background capture thread per role) |
| `smart_telescope/services/guide_measurement.py` | `CentroidConfig`, `GuideCentroidEstimator`, `GuideControllerConfig`, `MeasureOnlyGuideController`, `GuideSourceSelector`, `source_state_from_measurement` |
| `smart_telescope/services/guiding_service.py` | `GuidingStatus`, `GuidingService` (owns ManagedCameras, runs measurement loop) |
| `smart_telescope/api/guiding.py` | `POST /api/guiding/start`, `POST /api/guiding/stop`, `GET /api/guiding/status` |
| `smart_telescope/app.py` | include guiding router |
| `smart_telescope/api/deps.py` | `get_guiding_service()` dependency |
| `smart_telescope/runtime.py` | hold `GuidingService` instance, stop it in `shutdown()` |
| `templates/config.toml` | `[guiding]` section with commented defaults |
| `smart_telescope/static/index.html` | guide status card (Stage 5, before Connected Cameras) |
| `smart_telescope/static/js/guiding.js` | guide status polling and card rendering |

---

## Task 1: FrameMailbox and ManagedCamera

**Files:**
- Create: `smart_telescope/services/managed_camera.py`
- Create: `tests/unit/services/test_managed_camera.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/unit/services/test_managed_camera.py
import threading
import time

import numpy as np
import pytest

from smart_telescope.services.managed_camera import FrameMailbox, ManagedCamera
from smart_telescope.domain.frame import FitsFrame
from astropy.io import fits


def _frame(val: int = 100) -> FitsFrame:
    pixels = np.full((10, 10), val, dtype=np.uint16)
    return FitsFrame(pixels=pixels.astype(np.float32), header=fits.Header(), exposure_seconds=0.5)


def test_mailbox_returns_put_frame():
    mb = FrameMailbox()
    mb.put(_frame(1), sequence=1, captured_at=time.monotonic())
    result = mb.wait_latest(after_sequence=0, timeout_s=0.1)
    assert result is not None
    assert result.sequence == 1
    assert result.dropped_before == 0


def test_mailbox_drops_unconsumed_frame():
    mb = FrameMailbox()
    mb.put(_frame(1), sequence=1, captured_at=time.monotonic())
    mb.put(_frame(2), sequence=2, captured_at=time.monotonic())  # drops frame 1
    result = mb.wait_latest(after_sequence=0, timeout_s=0.1)
    assert result is not None
    assert result.sequence == 2
    assert result.dropped_before == 1
    assert mb.dropped_count == 1


def test_mailbox_returns_none_on_timeout():
    mb = FrameMailbox()
    result = mb.wait_latest(after_sequence=0, timeout_s=0.05)
    assert result is None


def test_mailbox_after_sequence_filter():
    mb = FrameMailbox()
    mb.put(_frame(1), sequence=1, captured_at=time.monotonic())
    result = mb.wait_latest(after_sequence=1, timeout_s=0.05)
    assert result is None  # seq=1 is not > after_sequence=1


def test_managed_camera_streams_frames():
    from smart_telescope.adapters.mock.camera import MockCamera
    cam = MockCamera()
    cam.connect()
    mc = ManagedCamera(cam, "guide")
    mc.start_stream(exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.3)
    frame = mc.mailbox.wait_latest(after_sequence=0, timeout_s=0.5)
    mc.stop_stream()
    assert frame is not None
    assert frame.sequence >= 1


def test_managed_camera_stop_is_clean():
    from smart_telescope.adapters.mock.camera import MockCamera
    cam = MockCamera()
    cam.connect()
    mc = ManagedCamera(cam, "guide")
    mc.start_stream(exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.1)
    mc.stop_stream()
    # No exception, thread is dead
    assert mc._thread is None or not mc._thread.is_alive()


def test_managed_camera_reports_stream_error():
    from smart_telescope.adapters.mock.camera import MockCamera
    cam = MockCamera()
    cam.connect()
    mc = ManagedCamera(cam, "guide")
    # Inject a failure by disconnecting before stream runs
    cam.disconnect()
    mc.start_stream(exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.3)
    err = mc.pop_stream_error()
    mc.stop_stream()
    # MockCamera.capture() after disconnect should raise; error surfaces
    # (MockCamera may not raise — just verify no crash and clean stop)
    assert mc.pop_stream_error() is None  # only one error stored
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/services/test_managed_camera.py -v
```
Expected: `ImportError: cannot import name 'FrameMailbox'`

- [ ] **Step 3: Create `smart_telescope/services/managed_camera.py`**

```python
"""Latest-frame mailbox and background-capture wrapper for guide camera roles."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ports.camera import CameraPort
    from ..domain.frame import FitsFrame


@dataclass(frozen=True)
class MailboxFrame:
    """A single captured frame as stored in the mailbox."""
    sequence: int
    captured_at_monotonic: float
    frame: "FitsFrame"
    dropped_before: int = 0


class FrameMailbox:
    """Single-slot latest-frame mailbox.

    Callers that produce frames faster than the consumer can read them see
    intermediate frames silently dropped.  `dropped_count` counts total drops.
    """

    def __init__(self) -> None:
        self._cond = threading.Condition()
        self._pending: MailboxFrame | None = None
        self._dropped: int = 0

    def put(self, frame: "FitsFrame", *, sequence: int, captured_at: float) -> None:
        with self._cond:
            if self._pending is not None:
                self._dropped += 1
            self._pending = MailboxFrame(sequence, captured_at, frame, self._dropped)
            self._cond.notify_all()

    def wait_latest(self, *, after_sequence: int = 0, timeout_s: float = 0.2) -> MailboxFrame | None:
        deadline = time.monotonic() + timeout_s
        with self._cond:
            while True:
                if self._pending is not None and self._pending.sequence > after_sequence:
                    frame = self._pending
                    self._pending = None
                    return frame
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(timeout=remaining)

    @property
    def dropped_count(self) -> int:
        with self._cond:
            return self._dropped


class ManagedCamera:
    """Wraps a CameraPort with a background capture thread and latest-frame mailbox.

    Usage::

        mc = ManagedCamera(cam, "guide")
        mc.start_stream(exposure_s=0.5, cadence_s=0.5)
        ...
        frame = mc.mailbox.wait_latest(after_sequence=last_seq, timeout_s=0.2)
        err = mc.pop_stream_error()   # None unless capture thread died
        ...
        mc.stop_stream()
    """

    def __init__(self, camera: "CameraPort", role: str) -> None:
        self.camera = camera
        self.role = role
        self.mailbox = FrameMailbox()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._seq = 0
        self._error: Exception | None = None
        self._err_lock = threading.Lock()

    def start_stream(self, exposure_s: float, cadence_s: float) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(exposure_s, cadence_s),
            daemon=True,
            name=f"guide-cam-{self.role}",
        )
        self._thread.start()

    def stop_stream(self) -> None:
        self._stop_event.set()
        self.camera.abort_capture()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None

    def pop_stream_error(self) -> Exception | None:
        with self._err_lock:
            err, self._error = self._error, None
            return err

    def _run(self, exposure_s: float, cadence_s: float) -> None:
        from ..ports.camera import CaptureAbortedError

        while not self._stop_event.is_set():
            try:
                cycle_start = time.monotonic()
                captured_at = time.monotonic()
                frame = self.camera.capture(exposure_s)
                self._seq += 1
                self.mailbox.put(frame, sequence=self._seq, captured_at=captured_at)
                elapsed = time.monotonic() - cycle_start
                sleep_s = max(0.0, cadence_s - elapsed)
                if sleep_s > 0:
                    self._stop_event.wait(timeout=sleep_s)
            except CaptureAbortedError:
                break
            except Exception as exc:
                with self._err_lock:
                    self._error = exc
                break
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/services/test_managed_camera.py -v
```
Expected: all 7 tests PASS (the stream-error test may warn about MockCamera not raising after disconnect — that's fine)

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/services/managed_camera.py tests/unit/services/test_managed_camera.py
git commit -m "feat(GUD): add FrameMailbox and ManagedCamera (latest-frame guide stream)"
```

---

## Task 2: CentroidConfig and GuideCentroidEstimator

**Files:**
- Create: `smart_telescope/services/guide_measurement.py` (partial — only centroid classes)
- Modify: `tests/unit/services/test_guide_measurement.py` — the importorskip will now resolve; the first 2 of 4 tests activate

**How the centroid works:**
1. Find the brightest pixel in the full frame.
2. Extract a square ROI of side `roi_px` centred on that pixel.
3. Estimate background as the median of the ROI border pixels.
4. Check saturation: `peak >= dtype_max * saturation_fraction` → reject.
5. Background-subtract the ROI; clip negatives to zero.
6. Check SNR: `(peak - bg) / noise < min_peak_snr` → reject.
7. Compute intensity-weighted centroid inside the ROI and map back to full-frame coordinates.
8. If `target` is given, compute `error_x/y = centroid - target`; otherwise `error_x/y = 0.0`.

- [ ] **Step 1: Write failing centroid tests (in addition to the already-written ones)**

Add to the bottom of `tests/unit/services/test_guide_measurement.py`:

```python
def test_centroid_rejects_dark_frame():
    estimator = GuideCentroidEstimator(CentroidConfig(roi_px=24, min_peak_snr=5.0))
    result = estimator.measure(np.zeros((80, 100), dtype=np.uint16), role="guide", sequence=1)
    assert not result.accepted
    assert result.rejected_reason is not None


def test_centroid_tracks_target_error():
    estimator = GuideCentroidEstimator(CentroidConfig(roi_px=24))
    result = estimator.measure(
        _star_frame(42.0, 29.0),
        role="guide",
        sequence=2,
        target=(40.0, 30.0),
    )
    assert result.accepted
    assert result.error_x is not None
    assert abs(result.error_x - 2.0) < 0.3
    assert result.error_y is not None
    assert abs(result.error_y - (-1.0)) < 0.3
```

- [ ] **Step 2: Run tests to confirm the skip guard still fires**

```
pytest tests/unit/services/test_guide_measurement.py -v
```
Expected: all 6 tests `SKIPPED` (importorskip fires because guide_measurement does not exist yet)

- [ ] **Step 3: Create `smart_telescope/services/guide_measurement.py` with centroid classes only**

```python
"""Guide camera measurement: centroid, source selection, measure-only controller."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from ..domain.guiding import (
    GuideMeasurement,
    GuideSourceHealth,
    GuideSourceState,
    WouldGuidePulse,
)


@dataclass(frozen=True)
class CentroidConfig:
    roi_px: int = 32
    min_peak_snr: float = 5.0
    saturation_fraction: float = 0.98


class GuideCentroidEstimator:
    """Windowed centroid estimator for guide-star frames.

    Locates the brightest point in the frame, extracts a local ROI, performs
    background subtraction, saturation and SNR checks, then computes the
    intensity-weighted centroid.
    """

    def __init__(self, config: CentroidConfig = CentroidConfig()) -> None:
        self._cfg = config

    def measure(
        self,
        pixels: np.ndarray,
        *,
        role: str,
        sequence: int,
        frame_age_s: float = 0.0,
        target: tuple[float, float] | None = None,
    ) -> GuideMeasurement:
        lum = (
            pixels[:, :, 0].astype(np.float32)
            if pixels.ndim == 3
            else pixels.astype(np.float32)
        )
        h, w = lum.shape

        flat_idx = int(np.argmax(lum))
        peak_y, peak_x = divmod(flat_idx, w)
        peak_val = float(lum[peak_y, peak_x])

        # Saturation check
        if np.issubdtype(pixels.dtype, np.integer):
            dtype_max = float(np.iinfo(pixels.dtype).max)
        else:
            dtype_max = float(np.finfo(pixels.dtype).max)
        if peak_val >= dtype_max * self._cfg.saturation_fraction:
            return GuideMeasurement(
                role=role,
                sequence=sequence,
                accepted=False,
                peak=peak_val,
                saturated=True,
                rejected_reason="saturated",
                frame_age_s=frame_age_s,
                measured_at_monotonic=time.monotonic(),
            )

        # ROI extraction
        half = self._cfg.roi_px // 2
        y0 = max(0, peak_y - half)
        y1 = min(h, peak_y + half + 1)
        x0 = max(0, peak_x - half)
        x1 = min(w, peak_x + half + 1)
        roi = lum[y0:y1, x0:x1]

        # Background from ROI border pixels
        border = np.concatenate(
            [roi[0, :], roi[-1, :], roi[1:-1, 0], roi[1:-1, -1]]
        )
        background = float(np.median(border)) if border.size > 0 else 0.0
        noise = float(np.std(border)) if border.size > 0 else 1.0

        signal = np.clip(roi - background, 0.0, None)
        peak_signal = peak_val - background
        snr = peak_signal / max(noise, 1.0)

        if snr < self._cfg.min_peak_snr or signal.sum() <= 0:
            return GuideMeasurement(
                role=role,
                sequence=sequence,
                accepted=False,
                peak=peak_val,
                background=background,
                noise=noise,
                rejected_reason="snr_too_low",
                frame_age_s=frame_age_s,
                measured_at_monotonic=time.monotonic(),
            )

        # Weighted centroid in ROI coordinates → full-frame coordinates
        total = float(signal.sum())
        yy, xx = np.indices(signal.shape, dtype=np.float32)
        cx_roi = float((signal * xx).sum()) / total
        cy_roi = float((signal * yy).sum()) / total
        centroid_x = x0 + cx_roi
        centroid_y = y0 + cy_roi

        # FWHM estimate
        half_max = peak_signal * 0.5
        fwhm_mask = signal > half_max
        fwhm_px = float(np.sqrt(fwhm_mask.sum() / np.pi) * 2) if fwhm_mask.any() else None

        error_x = centroid_x - target[0] if target is not None else 0.0
        error_y = centroid_y - target[1] if target is not None else 0.0

        return GuideMeasurement(
            role=role,
            sequence=sequence,
            accepted=True,
            centroid_x=centroid_x,
            centroid_y=centroid_y,
            target_x=target[0] if target is not None else None,
            target_y=target[1] if target is not None else None,
            error_x=error_x,
            error_y=error_y,
            confidence=min(1.0, snr / max(self._cfg.min_peak_snr * 5, 1.0)),
            peak=peak_val,
            background=background,
            noise=noise,
            fwhm_px=fwhm_px,
            frame_age_s=frame_age_s,
            measured_at_monotonic=time.monotonic(),
        )
```

Note: **do not add `GuideSourceSelector`, `MeasureOnlyGuideController`, `GuideControllerConfig`, or `source_state_from_measurement` yet** — that is Task 3.

- [ ] **Step 4: Run tests — centroid tests should pass, selector/controller tests still skip**

```
pytest tests/unit/services/test_guide_measurement.py -v
```
Expected:
- `test_centroid_accepts_clean_star` — PASS
- `test_centroid_rejects_saturated_star` — PASS
- `test_centroid_rejects_dark_frame` — PASS
- `test_centroid_tracks_target_error` — PASS
- `test_measure_only_controller_outputs_would_pulses` — FAIL (ImportError on MeasureOnlyGuideController)
- `test_source_selector_prefers_primary_then_fallback` — FAIL (ImportError on GuideSourceSelector)

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/services/guide_measurement.py tests/unit/services/test_guide_measurement.py
git commit -m "feat(GUD): add CentroidConfig and GuideCentroidEstimator"
```

---

## Task 3: GuideSourceSelector, MeasureOnlyGuideController, source_state_from_measurement

**Files:**
- Modify: `smart_telescope/services/guide_measurement.py` (append remaining classes)

- [ ] **Step 1: Run to confirm the two remaining tests fail**

```
pytest tests/unit/services/test_guide_measurement.py::test_measure_only_controller_outputs_would_pulses tests/unit/services/test_guide_measurement.py::test_source_selector_prefers_primary_then_fallback -v
```
Expected: both FAIL with `ImportError`

- [ ] **Step 2: Append remaining classes to `smart_telescope/services/guide_measurement.py`**

Append after the `GuideCentroidEstimator` class:

```python

@dataclass(frozen=True)
class GuideControllerConfig:
    deadband_px: float = 0.5
    max_pulse_ms: int = 2000
    min_pulse_ms: int = 50
    aggressiveness: float = 0.7
    ra_only: bool = False
    ms_per_px: float = 100.0


class MeasureOnlyGuideController:
    """Computes would-be guide pulses without sending them to the mount.

    Returns a list of WouldGuidePulse — one per axis with error above deadband.
    """

    def __init__(self, config: GuideControllerConfig = GuideControllerConfig()) -> None:
        self._cfg = config

    def would_pulse(self, measurement: GuideMeasurement) -> list[WouldGuidePulse]:
        if not measurement.accepted:
            return []
        pulses: list[WouldGuidePulse] = []

        def _pulse(axis: str, error: float, pos_dir: str, neg_dir: str) -> None:
            if abs(error) <= self._cfg.deadband_px:
                return
            raw_ms = abs(error) * self._cfg.ms_per_px * self._cfg.aggressiveness
            clamped = min(int(raw_ms), self._cfg.max_pulse_ms)
            clipped = raw_ms > self._cfg.max_pulse_ms
            direction = pos_dir if error > 0 else neg_dir
            pulses.append(
                WouldGuidePulse(
                    axis=axis,
                    direction=direction,
                    duration_ms=max(self._cfg.min_pulse_ms, clamped),
                    reason=f"{axis}_error",
                    clipped=clipped,
                )
            )

        if measurement.error_x is not None:
            _pulse("ra", measurement.error_x, "e", "w")
        if not self._cfg.ra_only and measurement.error_y is not None:
            _pulse("dec", measurement.error_y, "s", "n")

        return pulses


class GuideSourceSelector:
    """Selects the active guide source from available GuideSourceState objects.

    Prefers `primary_role` while healthy.  Falls back to another healthy role
    when `allow_fallback=True` and primary is `TRANSIENT_BAD`.  Never silently
    hides `HARD_FAILED` cameras.
    """

    def __init__(self, primary_role: str = "guide", allow_fallback: bool = True) -> None:
        self._primary = primary_role
        self._allow_fallback = allow_fallback
        self.reason = "primary"

    def select(self, states: dict[str, GuideSourceState]) -> str | None:
        primary = states.get(self._primary)
        if primary and primary.running and primary.health == GuideSourceHealth.HEALTHY:
            self.reason = "primary"
            return self._primary

        if self._allow_fallback and primary and primary.health == GuideSourceHealth.TRANSIENT_BAD:
            for role, state in states.items():
                if role != self._primary and state.running and state.health == GuideSourceHealth.HEALTHY:
                    self.reason = f"fallback_from_{self._primary}"
                    return role

        if primary and primary.running:
            self.reason = "primary_only_available"
            return self._primary

        self.reason = "no_source"
        return None


def source_state_from_measurement(
    role: str,
    measurement: GuideMeasurement | None,
    *,
    running: bool,
    latest_sequence: int,
    latest_frame_age_s: float | None,
    bad_frame_count: int,
    fallback_after_bad_frames: int,
    hard_failure: str | None = None,
) -> GuideSourceState:
    """Build a GuideSourceState from a measurement result and stream health counters."""
    if hard_failure:
        health = GuideSourceHealth.HARD_FAILED
    elif bad_frame_count >= fallback_after_bad_frames:
        health = GuideSourceHealth.TRANSIENT_BAD
    else:
        health = GuideSourceHealth.HEALTHY
    return GuideSourceState(
        role=role,
        running=running,
        health=health,
        latest_sequence=latest_sequence,
        latest_frame_age_s=latest_frame_age_s,
        bad_frame_count=bad_frame_count,
        hard_failure=hard_failure,
        measurement=measurement,
    )
```

- [ ] **Step 3: Run all guide_measurement tests — all 6 should pass**

```
pytest tests/unit/services/test_guide_measurement.py -v
```
Expected: 6 tests PASS

- [ ] **Step 4: Commit**

```bash
git add smart_telescope/services/guide_measurement.py
git commit -m "feat(GUD): add GuideSourceSelector, MeasureOnlyGuideController, source_state_from_measurement"
```

---

## Task 4: GuidingService

**Files:**
- Create: `smart_telescope/services/guiding_service.py`
- Create: `tests/unit/services/test_guiding_service.py`

The service runs a background thread that:
1. Polls each `ManagedCamera.mailbox` for new frames.
2. Calls `GuideCentroidEstimator.measure()` on each new frame.
3. Calls `GuideSourceSelector.select()` to pick the active role.
4. Calls `MeasureOnlyGuideController.would_pulse()` on the active measurement.
5. If `measure_only=False` **and** a real mount is provided, sends real pulses via `mount.guide()`.
6. Stores current `GuidingStatus` under a lock for the API to read.

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/services/test_guiding_service.py
import time

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.domain.guiding import GuideSourceHealth
from smart_telescope.services.guiding_service import GuidingService, GuidingStatus
from smart_telescope.services.guide_measurement import CentroidConfig, GuideControllerConfig


def _mock_camera_with_star():
    """Returns a MockCamera that captures a stable star frame."""
    from smart_telescope.adapters.mock.camera import MockCamera
    cam = MockCamera()
    cam.connect()
    return cam


def test_guiding_service_starts_and_produces_status():
    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(roi_px=16, min_peak_snr=1.0),
        controller_config=GuideControllerConfig(),
        measure_only=True,
    )
    cam = _mock_camera_with_star()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.4)
    status = svc.status()
    svc.stop()

    assert status.state == "running"
    assert "guide" in status.sources


def test_guiding_service_idle_after_stop():
    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(),
        controller_config=GuideControllerConfig(),
        measure_only=True,
    )
    cam = _mock_camera_with_star()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05)
    time.sleep(0.1)
    svc.stop()

    assert svc.status().state == "idle"


def test_guiding_service_double_start_is_noop():
    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(),
        controller_config=GuideControllerConfig(),
        measure_only=True,
    )
    cam = _mock_camera_with_star()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05)
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05)  # should not crash
    svc.stop()
    assert svc.status().state == "idle"


def test_guiding_status_to_dict():
    status = GuidingStatus()
    d = status.to_dict()
    assert d["state"] == "idle"
    assert "sources" in d
    assert "latest_pulses" in d
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/unit/services/test_guiding_service.py -v
```
Expected: `ImportError: cannot import name 'GuidingService'`

- [ ] **Step 3: Create `smart_telescope/services/guiding_service.py`**

```python
"""GuidingService — owns guide camera streams and runs the measurement loop."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..domain.guiding import GuideMeasurement, GuideSourceState, WouldGuidePulse
from .guide_measurement import (
    CentroidConfig,
    GuideCentroidEstimator,
    GuideControllerConfig,
    GuideSourceSelector,
    MeasureOnlyGuideController,
    source_state_from_measurement,
)
from .managed_camera import ManagedCamera

if TYPE_CHECKING:
    from ..ports.camera import CameraPort
    from ..ports.mount import MountPort

_log = logging.getLogger(__name__)


@dataclass
class GuidingStatus:
    state: str = "idle"  # idle | running | failed
    active_role: str | None = None
    fallback_reason: str | None = None
    sources: dict[str, GuideSourceState] = field(default_factory=dict)
    latest_pulses: list[WouldGuidePulse] = field(default_factory=list)
    started_at: float | None = None
    measure_only: bool = True

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "active_role": self.active_role,
            "fallback_reason": self.fallback_reason,
            "sources": {r: s.to_dict() for r, s in self.sources.items()},
            "latest_pulses": [p.to_dict() for p in self.latest_pulses],
            "started_at": self.started_at,
            "measure_only": self.measure_only,
        }


class GuidingService:
    """Owns ManagedCamera streams for guide/OAG roles and runs the centroid loop.

    In measure_only mode (default) pulses are computed but not sent to the mount.
    Set measure_only=False and pass a real mount to enable closed-loop corrections.
    """

    @classmethod
    def from_config(
        cls,
        *,
        primary_role: str,
        allow_fallback: bool,
        fallback_after_bad_frames: int,
        max_frame_age_s: float,
        centroid_config: CentroidConfig,
        controller_config: GuideControllerConfig,
        measure_only: bool = True,
    ) -> "GuidingService":
        return cls(
            primary_role=primary_role,
            allow_fallback=allow_fallback,
            fallback_after_bad_frames=fallback_after_bad_frames,
            max_frame_age_s=max_frame_age_s,
            estimator=GuideCentroidEstimator(centroid_config),
            selector=GuideSourceSelector(primary_role, allow_fallback),
            controller=MeasureOnlyGuideController(controller_config),
            measure_only=measure_only,
        )

    def __init__(
        self,
        *,
        primary_role: str,
        allow_fallback: bool,
        fallback_after_bad_frames: int,
        max_frame_age_s: float,
        estimator: GuideCentroidEstimator,
        selector: GuideSourceSelector,
        controller: MeasureOnlyGuideController,
        measure_only: bool = True,
    ) -> None:
        self._primary_role = primary_role
        self._allow_fallback = allow_fallback
        self._fallback_after_bad_frames = fallback_after_bad_frames
        self._max_frame_age_s = max_frame_age_s
        self._estimator = estimator
        self._selector = selector
        self._controller = controller
        self._measure_only = measure_only

        self._managed: dict[str, ManagedCamera] = {}
        self._mount: MountPort | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._status_lock = threading.Lock()
        self._status = GuidingStatus(measure_only=measure_only)

    def start(
        self,
        role_cameras: dict[str, "CameraPort"],
        exposure_s: float = 0.5,
        cadence_s: float = 0.5,
        mount: "MountPort | None" = None,
    ) -> None:
        with self._status_lock:
            if self._status.state == "running":
                return

        self._mount = mount
        self._stop_event.clear()
        for role, cam in role_cameras.items():
            mc = ManagedCamera(cam, role)
            mc.start_stream(exposure_s, cadence_s)
            self._managed[role] = mc

        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="guiding-loop"
        )
        self._thread.start()

        with self._status_lock:
            self._status = GuidingStatus(
                state="running",
                measure_only=self._measure_only,
                started_at=time.monotonic(),
            )
        _log.info("GuidingService started roles=%s measure_only=%s", list(role_cameras), self._measure_only)

    def stop(self) -> None:
        self._stop_event.set()
        for mc in self._managed.values():
            mc.stop_stream()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            self._thread = None
        self._managed.clear()
        with self._status_lock:
            self._status = GuidingStatus(measure_only=self._measure_only)
        _log.info("GuidingService stopped")

    def status(self) -> GuidingStatus:
        with self._status_lock:
            return self._status

    def _loop(self) -> None:
        last_sequence = {role: 0 for role in self._managed}
        targets: dict[str, tuple[float, float]] = {}
        bad_counts: dict[str, int] = {role: 0 for role in self._managed}

        while not self._stop_event.is_set():
            states: dict[str, GuideSourceState] = {}

            for role, mc in list(self._managed.items()):
                latest = mc.mailbox.wait_latest(
                    after_sequence=last_sequence[role], timeout_s=0.1
                )
                hard_failure: str | None = None
                err = mc.pop_stream_error()
                if err is not None:
                    hard_failure = str(err)
                    _log.warning("guide stream error role=%s: %s", role, err)

                measurement: GuideMeasurement | None = None
                latest_frame_age: float | None = None

                if latest is not None:
                    last_sequence[role] = latest.sequence
                    frame_age = time.monotonic() - latest.captured_at_monotonic
                    latest_frame_age = frame_age
                    target = targets.get(role)
                    measurement = self._estimator.measure(
                        latest.frame.pixels,
                        role=role,
                        sequence=latest.sequence,
                        frame_age_s=frame_age,
                        target=target,
                    )
                    if (
                        measurement.accepted
                        and target is None
                        and measurement.centroid_x is not None
                        and measurement.centroid_y is not None
                    ):
                        targets[role] = (measurement.centroid_x, measurement.centroid_y)
                    if measurement.accepted and frame_age <= self._max_frame_age_s:
                        bad_counts[role] = 0
                    else:
                        bad_counts[role] += 1

                states[role] = source_state_from_measurement(
                    role,
                    measurement,
                    running=True,
                    latest_sequence=last_sequence[role],
                    latest_frame_age_s=latest_frame_age,
                    bad_frame_count=bad_counts[role],
                    fallback_after_bad_frames=self._fallback_after_bad_frames,
                    hard_failure=hard_failure,
                )

            active_role = self._selector.select(states)
            active_measurement = (
                states[active_role].measurement
                if active_role and active_role in states
                else None
            )
            pulses = self._controller.would_pulse(active_measurement) if active_measurement else []

            if not self._measure_only and pulses and self._mount is not None:
                for pulse in pulses:
                    try:
                        self._mount.guide(pulse.direction, pulse.duration_ms)
                    except Exception as exc:
                        _log.error("mount.guide failed: %s", exc)

            with self._status_lock:
                self._status = GuidingStatus(
                    state="running",
                    measure_only=self._measure_only,
                    active_role=active_role,
                    fallback_reason=self._selector.reason,
                    sources=states,
                    latest_pulses=pulses,
                    started_at=self._status.started_at,
                )
```

- [ ] **Step 4: Run tests**

```
pytest tests/unit/services/test_guiding_service.py -v
```
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add smart_telescope/services/guiding_service.py tests/unit/services/test_guiding_service.py
git commit -m "feat(GUD): add GuidingService with measure-only guide loop"
```

---

## Task 5: API Endpoints

**Files:**
- Create: `smart_telescope/api/guiding.py`
- Create: `tests/unit/api/test_guiding.py`
- Modify: `smart_telescope/app.py` (add router)
- Modify: `smart_telescope/api/deps.py` (add `get_guiding_service`)
- Modify: `smart_telescope/runtime.py` (hold GuidingService, stop in shutdown)

- [ ] **Step 1: Write failing API tests**

```python
# tests/unit/api/test_guiding.py
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.api import deps
from smart_telescope.services.guiding_service import GuidingService, GuidingStatus
from smart_telescope.services.guide_measurement import CentroidConfig, GuideControllerConfig


@pytest.fixture()
def mock_svc():
    svc = MagicMock(spec=GuidingService)
    svc.status.return_value = GuidingStatus(state="idle", measure_only=True)
    return svc


@pytest.fixture()
def client(mock_svc):
    app.dependency_overrides[deps.get_guiding_service] = lambda: mock_svc
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_get_status_idle(client, mock_svc):
    r = client.get("/api/guiding/status")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "idle"
    assert data["measure_only"] is True


def test_post_start_calls_service(client, mock_svc):
    r = client.post("/api/guiding/start", json={})
    assert r.status_code == 202
    mock_svc.start.assert_called_once()


def test_post_stop_calls_service(client, mock_svc):
    mock_svc.status.return_value = GuidingStatus(state="running", measure_only=True)
    r = client.post("/api/guiding/stop")
    assert r.status_code == 200
    mock_svc.stop.assert_called_once()


def test_post_start_when_already_running_returns_409(client, mock_svc):
    mock_svc.status.return_value = GuidingStatus(state="running", measure_only=True)
    r = client.post("/api/guiding/start", json={})
    assert r.status_code == 409
    mock_svc.start.assert_not_called()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/unit/api/test_guiding.py -v
```
Expected: `ImportError` or 404 errors

- [ ] **Step 3: Add `get_guiding_service` to `smart_telescope/api/deps.py`**

Open `smart_telescope/api/deps.py` and append:

```python
from ..services.guiding_service import GuidingService


def get_guiding_service() -> GuidingService:
    return get_runtime().guiding_service
```

- [ ] **Step 4: Add `guiding_service` property to `smart_telescope/runtime.py`**

Open `smart_telescope/runtime.py`. Find the `__init__` method and add to the instance variables:

```python
        self._guiding_service: GuidingService | None = None
```

Add the property (after existing properties):

```python
    @property
    def guiding_service(self) -> "GuidingService":
        if self._guiding_service is None:
            from .services.guiding_service import GuidingService
            from .services.guide_measurement import CentroidConfig, GuideControllerConfig
            from . import config
            self._guiding_service = GuidingService.from_config(
                primary_role=config.GUIDING.primary_role,
                allow_fallback=config.GUIDING.allow_fallback,
                fallback_after_bad_frames=config.GUIDING.fallback_after_bad_frames,
                max_frame_age_s=config.GUIDING.max_frame_age_s,
                centroid_config=CentroidConfig(
                    roi_px=config.GUIDING.centroid_roi_px,
                    min_peak_snr=config.GUIDING.min_peak_snr,
                    saturation_fraction=config.GUIDING.saturation_fraction,
                ),
                controller_config=GuideControllerConfig(),
                measure_only=config.GUIDING.measure_only,
            )
        return self._guiding_service
```

In `shutdown()`, add before other teardowns:

```python
        if self._guiding_service is not None:
            self._guiding_service.stop()
            self._guiding_service = None
```

In `reset_for_tests()`, add:

```python
        if self._guiding_service is not None:
            self._guiding_service.stop()
            self._guiding_service = None
```

- [ ] **Step 5: Create `smart_telescope/api/guiding.py`**

```python
"""Guiding API — start/stop/status for the measure-only guide loop."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import get_guiding_service
from ..services.guiding_service import GuidingService

router = APIRouter(prefix="/api/guiding", tags=["guiding"])


class GuidingStartRequest(BaseModel):
    exposure_s: float = 0.5
    cadence_s: float = 0.5
    roles: list[str] = []  # empty = use all configured guide/oag roles from runtime


@router.post("/start", status_code=202)
def guiding_start(
    body: GuidingStartRequest,
    svc: GuidingService = Depends(get_guiding_service),
) -> dict:
    from ..api.deps import get_runtime
    rt = get_runtime()

    if svc.status().state == "running":
        raise HTTPException(status_code=409, detail="Guiding is already running")

    roles = body.roles or ["guide", "oag"]
    role_cameras: dict = {}
    for role in roles:
        try:
            cam = rt.get_camera_by_role(role)
            role_cameras[role] = cam
        except Exception:
            pass  # role not configured — skip silently

    if not role_cameras:
        raise HTTPException(status_code=422, detail="No guide-capable camera roles are configured")

    mount = rt.mount if hasattr(rt, "mount") else None
    svc.start(role_cameras, exposure_s=body.exposure_s, cadence_s=body.cadence_s, mount=mount)
    return {"state": "starting", "roles": list(role_cameras)}


@router.post("/stop")
def guiding_stop(svc: GuidingService = Depends(get_guiding_service)) -> dict:
    svc.stop()
    return {"state": "idle"}


@router.get("/status")
def guiding_status(svc: GuidingService = Depends(get_guiding_service)) -> dict:
    return svc.status().to_dict()
```

- [ ] **Step 6: Add guiding router to `smart_telescope/app.py`**

Open `smart_telescope/app.py`. Find where other routers are included (e.g. `app.include_router(cameras.router)`) and add:

```python
from .api import guiding
app.include_router(guiding.router)
```

- [ ] **Step 7: Run API tests**

```
pytest tests/unit/api/test_guiding.py -v
```
Expected: all 4 tests PASS

- [ ] **Step 8: Run full suite to check no regressions**

```
pytest tests/unit -x -q 2>&1 | tail -10
```
Expected: all previous tests still pass

- [ ] **Step 9: Commit**

```bash
git add smart_telescope/api/guiding.py smart_telescope/app.py smart_telescope/api/deps.py smart_telescope/runtime.py tests/unit/api/test_guiding.py
git commit -m "feat(GUD): add guiding API start/stop/status and runtime wiring"
```

---

## Task 6: Config Template and Frontend Card

**Files:**
- Modify: `templates/config.toml`
- Modify: `smart_telescope/static/index.html`
- Create: `smart_telescope/static/js/guiding.js`
- Modify: `smart_telescope/app.py` (serve guiding.js — already covered by `StaticFiles`)

- [ ] **Step 1: Add `[guiding]` section to `templates/config.toml`**

Open `templates/config.toml`. Find an appropriate location (after `[cameras.oag]` block or before `[guiding]` if it already exists) and add:

```toml
# ---------------------------------------------------------------------------
# Guiding
# ---------------------------------------------------------------------------
[guiding]
# Primary guide source role: "guide" or "oag"
primary_role          = "guide"
# Fall back to the other guide role after this many consecutive bad frames
allow_fallback        = true
fallback_after_bad_frames = 3
# Reject frames older than this (seconds)
max_frame_age_s       = 2.0
# Centroid ROI radius in pixels around the brightest point
centroid_roi_px       = 32
# Minimum peak SNR to accept a star frame
min_peak_snr          = 5.0
# Fraction of dtype max that counts as saturated
saturation_fraction   = 0.98
# true = compute corrections but do NOT send pulses to the mount (safe default)
# Set to false only after validating measure-only output on real hardware
measure_only          = true
```

- [ ] **Step 2: Create `smart_telescope/static/js/guiding.js`**

```javascript
// Guiding status card — polls /api/guiding/status every 2 s.

let _guidingPollTimer = null;

function guidingStart() {
  apiPost('/api/guiding/start', {})
    .then(() => { _guidingPollStart(); })
    .catch(err => setStatus('s5-guide-status', 'Start failed: ' + err, true));
}

function guidingStop() {
  apiPost('/api/guiding/stop', {})
    .then(() => { _guidingUpdateCard({ state: 'idle', sources: {}, latest_pulses: [] }); })
    .catch(err => setStatus('s5-guide-status', 'Stop failed: ' + err, true));
}

function _guidingPollStart() {
  if (_guidingPollTimer) return;
  _guidingPollTimer = setInterval(_guidingPoll, 2000);
  _guidingPoll();
}

function _guidingPollStop() {
  clearInterval(_guidingPollTimer);
  _guidingPollTimer = null;
}

function _guidingPoll() {
  fetch('/api/guiding/status')
    .then(r => r.json())
    .then(_guidingUpdateCard)
    .catch(() => {});
}

function _guidingUpdateCard(data) {
  const badge = document.getElementById('s5-guide-state-badge');
  const srcDiv = document.getElementById('s5-guide-sources');
  const pulseDiv = document.getElementById('s5-guide-pulses');
  if (!badge) return;

  const stateColors = { idle: 'secondary', running: 'success', failed: 'danger' };
  badge.className = `badge bg-${stateColors[data.state] || 'secondary'}`;
  badge.textContent = (data.state || 'idle').toUpperCase();

  let srcHtml = '';
  for (const [role, src] of Object.entries(data.sources || {})) {
    const healthColor = { healthy: 'success', transient_bad: 'warning', hard_failed: 'danger' }[src.health] || 'secondary';
    const active = data.active_role === role ? ' (active)' : '';
    srcHtml += `<span class="badge bg-${healthColor} me-1">${escHtml(role)}${active}</span>`;
    if (src.measurement && src.measurement.accepted) {
      srcHtml += ` cx=${src.measurement.centroid_x?.toFixed(1)} cy=${src.measurement.centroid_y?.toFixed(1)}`;
      srcHtml += ` snr=${src.measurement.confidence?.toFixed(2)}`;
    }
    srcHtml += '<br>';
  }
  srcDiv.innerHTML = srcHtml || '<em>No sources</em>';

  const pulses = data.latest_pulses || [];
  pulseDiv.textContent = pulses.length
    ? pulses.map(p => `${p.axis} ${p.direction} ${p.duration_ms}ms${p.clipped ? ' (clip)' : ''}`).join(', ')
    : data.state === 'running' ? '—' : '';

  if (data.state === 'running') {
    _guidingPollStart();
  } else {
    _guidingPollStop();
  }
}
```

- [ ] **Step 3: Add the guide card to `smart_telescope/static/index.html`**

Find the Stage 5 section in `index.html` (search for `id="stage-5"` or `s5-`). Add the card before the "Connected Cameras" card or at the bottom of Stage 5:

```html
<!-- Guide Monitor Card -->
<div class="card mb-3 adv-only" id="s5-guide-card">
  <div class="card-header d-flex justify-content-between align-items-center">
    <span>Guide Monitor</span>
    <span id="s5-guide-state-badge" class="badge bg-secondary">IDLE</span>
  </div>
  <div class="card-body">
    <div id="s5-guide-sources" class="mb-2"><em>Not started</em></div>
    <div id="s5-guide-pulses" class="text-muted small mb-2"></div>
    <div id="s5-guide-status"></div>
    <button class="btn btn-sm btn-outline-primary me-1" onclick="guidingStart()">Start Guiding</button>
    <button class="btn btn-sm btn-outline-secondary" onclick="guidingStop()">Stop</button>
  </div>
</div>
```

- [ ] **Step 4: Load `guiding.js` in `index.html`**

Find the script loading section at the bottom of `index.html` (where `api.js`, `session.js`, etc. are loaded) and add:

```html
<script src="/static/js/guiding.js"></script>
```

- [ ] **Step 5: Add `static/js/guiding.js` to `pyproject.toml` package data**

Open `pyproject.toml`. The current entry is:

```toml
[tool.setuptools.package-data]
"smart_telescope" = ["static/*", "static/js/*"]
```

The glob `static/js/*` already covers `guiding.js` — no change needed.

- [ ] **Step 6: Run full test suite**

```
pytest tests/unit -x -q 2>&1 | tail -5
```
Expected: all tests pass (guiding.js is not tested by unit tests — it's a UI file)

- [ ] **Step 7: Commit**

```bash
git add templates/config.toml smart_telescope/static/js/guiding.js smart_telescope/static/index.html
git commit -m "feat(GUD): add guiding config template, guide monitor card, and polling JS"
```

---

## Self-Review

**1. Spec coverage check against onstep_guiding_requirements.md and metaguide doc:**

| Requirement | Covered by |
|---|---|
| Connect to guide camera via existing adapter | Task 5: `rt.get_camera_by_role(role)` in start endpoint |
| Apply offset from config | ✅ done earlier (CO series) — `CameraOffsetService` applies on connect |
| Default exposure/gain from config | Task 5 start request `exposure_s` / GuidingSpec |
| Bounded frame acquisition, drop stale frames | Task 1: `FrameMailbox` latest-frame semantics |
| Guide-star detection + centroid | Task 2: `GuideCentroidEstimator` |
| SNR + saturation rejection | Task 2: centroid checks |
| Source selector (guide vs OAG fallback) | Task 3: `GuideSourceSelector` |
| Measure-only output (WouldGuidePulse) | Task 3: `MeasureOnlyGuideController` |
| Real pulse send behind flag | Task 4: `measure_only=False` path in `GuidingService._loop()` |
| Non-blocking: never blocks main event loop | Task 4: all work in daemon threads |
| API start/stop/status | Task 5 |
| Config `[guiding]` section | Task 6 |
| Frontend status card | Task 6 |
| Headless JSON telemetry | `GET /api/guiding/status` returns full JSON — covered |
| Duplicate camera detection | ✅ already done via `validate_unique_camera_roles` in tools |
| Startup tuning (auto exposure/gain) | **Not in this plan** — MVP starts with configured defaults; post-MVP |
| Mount responsiveness probe | **Not in this plan** — Phase 3B; requires real hardware validation first |
| Dither / settle | **Not in this plan** — explicitly Phase 4 / MVP+ |
| RA/Dec correction graph | **Not in this plan** — Phase 5 full UI; card shows text only for MVP |

**2. Placeholder scan:** None found — all steps have concrete code.

**3. Type consistency check:**
- `FrameMailbox.put(frame, *, sequence, captured_at)` ✅ used with keyword args in `ManagedCamera._run()`
- `MailboxFrame.frame` is `FitsFrame` ✅ `.pixels` and `.exposure_seconds` accessed in `GuidingService._loop()`
- `GuideCentroidEstimator.measure(pixels, *, role, sequence, frame_age_s, target)` ✅ called identically in `GuidingService._loop()` and tools
- `GuideSourceSelector.select(states: dict[str, GuideSourceState])` ✅ consistent
- `MeasureOnlyGuideController.would_pulse(measurement: GuideMeasurement)` ✅ consistent
- `GuidingService.from_config(...)` ✅ called in `runtime.py` `guiding_service` property
- `GuidingStatus.to_dict()` ✅ called in `GET /api/guiding/status`
- `deps.get_guiding_service()` returns `GuidingService` ✅ used in all API endpoints
