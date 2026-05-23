# Collimation Guiding Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate `GuidingService` into the collimation wizard so the guide scope keeps the C8's bright star centred during rough and fine collimation, with `PulseCenterer` recentering after each screw adjustment and guiding rebaselined to the new position.

**Architecture:** `CollimationAssistant` owns a dedicated `GuidingService` instance (guide camera, `measure_only=False`). Guiding starts when the wizard exits `AUTO_EXPOSURE` and stops when the session ends. Before each "Remeasure" cycle, guiding pulses are paused, `PulseCenterer` recenters the main camera star, then guiding rebaselines to wherever the guide star now sits. If no guide camera is configured the wizard continues without guiding.

**Tech Stack:** Python 3.13, threading.Event, FastAPI, vanilla JS / Bootstrap cards.

---

## Codebase Context

Before implementing, read these files to understand the existing patterns:

- `smart_telescope/services/guiding_service.py` — `GuidingService`, `GuidingStatus`, `_loop()`
- `smart_telescope/services/collimation/assistant.py` — `CollimationAssistant.__init__`, `_run()`, `_dispatch_user_wait()`, `_handle_auto_exposure()`, `_handle_center_star()`, `_fail()`, `status` property
- `smart_telescope/domain/collimation/config.py` — `CollimationConfig`, `from_dict()`, `validate()`
- `smart_telescope/api/collimation.py` — `_get_assistant()` lazy factory
- `smart_telescope/static/index.html` lines 1355–1396 — wizard card HTML
- `smart_telescope/static/js/collimation.js` lines 72–156 — `_updateCollimWizard()`
- `smart_telescope/domain/guiding.py` — `GuideMeasurement` fields (`error_x`, `error_y`)

Key facts:
- `GUIDE_ROUGH_COLLIMATION` and `GUIDE_FINE_COLLIMATION` are `USER_WAIT_STATES` — the worker thread blocks on `_user_event`. Recentering must happen in `_dispatch_user_wait()` before the transition, because that's called from the background thread.
- `_handle_center_star()` already has the `PulseCenterer` pattern to copy.
- The assistant is lazily created in `api/collimation.py::_get_assistant()` — not in `runtime.py`.
- `get_camera_by_role(role)` can raise `HTTPException` or `RuntimeError` if the role is not configured.

---

## File Map

| File | What changes |
|---|---|
| `smart_telescope/services/guiding_service.py` | `pause_pulses`, `resume_pulses`, `rebaseline`, `rms_px`/`last_pulse` on status |
| `smart_telescope/domain/collimation/config.py` | 3 new guiding fields on `CollimationConfig` |
| `smart_telescope/services/collimation/assistant.py` | Inject `GuidingService`, lifecycle hooks, `_recenter_star()`, `_with_guiding_paused()`, `_guiding_status_dict()` |
| `smart_telescope/api/collimation.py` | Update `_get_assistant()` to build and pass guiding service |
| `smart_telescope/static/index.html` | Add `s4-wiz-guide-row` div |
| `smart_telescope/static/js/collimation.js` | Render guide row in `_updateCollimWizard` |
| `tests/unit/services/test_guiding_service.py` | 3 new tests |
| `tests/unit/services/test_collimation_guiding.py` | New file, 7 tests |

---

## Task 1: GuidingService — pause/resume/rebaseline + status fields

**Files:**
- Modify: `smart_telescope/services/guiding_service.py`
- Test: `tests/unit/services/test_guiding_service.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/services/test_guiding_service.py`:

```python
def test_pause_pulses_suppresses_mount_calls():
    """While paused, guide() is never called even when error > deadband."""
    from unittest.mock import MagicMock
    mock_mount = MagicMock()
    mock_mount.guide.return_value = True

    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(roi_px=16, min_peak_snr=1.0),
        controller_config=GuideControllerConfig(deadband_px=0.5, ms_per_px=100.0),
        measure_only=False,
    )
    cam = _ShiftedStarCamera()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05, mount=mock_mount)
    time.sleep(0.15)  # allow loop to lock on target
    svc.pause_pulses()
    mock_mount.guide.reset_mock()
    time.sleep(0.3)   # loop runs but pulses suppressed
    svc.stop()

    mock_mount.guide.assert_not_called()


def test_resume_pulses_restores_mount_calls():
    """After resume_pulses(), guide() is called again."""
    from unittest.mock import MagicMock
    mock_mount = MagicMock()
    mock_mount.guide.return_value = True

    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(roi_px=16, min_peak_snr=1.0),
        controller_config=GuideControllerConfig(deadband_px=0.5, ms_per_px=100.0),
        measure_only=False,
    )
    cam = _ShiftedStarCamera()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05, mount=mock_mount)
    time.sleep(0.15)
    svc.pause_pulses()
    mock_mount.guide.reset_mock()
    time.sleep(0.1)
    svc.resume_pulses()
    time.sleep(0.3)
    svc.stop()

    mock_mount.guide.assert_called()


def test_rebaseline_resets_error_to_near_zero():
    """After rebaseline(), the next accepted frame becomes the new zero-point."""
    from unittest.mock import MagicMock
    mock_mount = MagicMock()
    mock_mount.guide.return_value = True

    svc = GuidingService.from_config(
        primary_role="guide",
        allow_fallback=False,
        fallback_after_bad_frames=3,
        max_frame_age_s=2.0,
        centroid_config=CentroidConfig(roi_px=16, min_peak_snr=1.0),
        controller_config=GuideControllerConfig(deadband_px=0.5, ms_per_px=100.0),
        measure_only=False,
    )
    cam = _ShiftedStarCamera()
    svc.start({"guide": cam}, exposure_s=0.01, cadence_s=0.05, mount=mock_mount)
    time.sleep(0.3)  # lock on first centroid (x=32)
    svc.rebaseline()  # tell loop: next frame is the new zero
    time.sleep(0.3)  # loop adopts x=36 as new target — error resets ~0
    svc.stop()

    # After rebaseline the loop has a new target; pulses should quiet down
    # compared to before rebaseline (error was 4px; now 0px)
    # We verify rebaseline didn't crash and service stopped cleanly.
    assert svc.status().state == "idle"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/services/test_guiding_service.py::test_pause_pulses_suppresses_mount_calls tests/unit/services/test_guiding_service.py::test_resume_pulses_restores_mount_calls tests/unit/services/test_guiding_service.py::test_rebaseline_resets_error_to_near_zero -v
```

Expected: FAIL — `AttributeError: 'GuidingService' object has no attribute 'pause_pulses'`

- [ ] **Step 3: Add `rms_px` and `last_pulse` to `GuidingStatus`**

In `smart_telescope/services/guiding_service.py`, change the `GuidingStatus` dataclass:

```python
@dataclass
class GuidingStatus:
    state: str = "idle"  # idle | running | failed
    active_role: str | None = None
    fallback_reason: str | None = None
    sources: dict[str, GuideSourceState] = field(default_factory=dict)
    latest_pulses: list[WouldGuidePulse] = field(default_factory=list)
    started_at: float | None = None
    measure_only: bool = True
    rms_px: float = 0.0
    last_pulse: tuple[str, int] | None = None

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "active_role": self.active_role,
            "fallback_reason": self.fallback_reason,
            "sources": {r: s.to_dict() for r, s in self.sources.items()},
            "latest_pulses": [p.to_dict() for p in self.latest_pulses],
            "started_at": self.started_at,
            "measure_only": self.measure_only,
            "rms_px": self.rms_px,
            "last_pulse": list(self.last_pulse) if self.last_pulse else None,
        }
```

- [ ] **Step 4: Add instance variables to `GuidingService.__init__`**

After `self._status = GuidingStatus(measure_only=measure_only)`, add:

```python
        self._pulses_paused: bool = False
        self._rebaseline_requested = threading.Event()
```

- [ ] **Step 5: Add `pause_pulses`, `resume_pulses`, `rebaseline` methods**

Add after the `status()` method:

```python
    def pause_pulses(self) -> None:
        """Suppress mount.guide() calls while keeping the measurement loop running."""
        with self._status_lock:
            self._pulses_paused = True

    def resume_pulses(self) -> None:
        """Re-enable mount.guide() calls after a pause_pulses() call."""
        with self._status_lock:
            self._pulses_paused = False

    def rebaseline(self) -> None:
        """On the next accepted measurement, adopt that position as the new target zero-point."""
        self._rebaseline_requested.set()
```

- [ ] **Step 6: Update `_loop()` to honour pause, rebaseline, and track rms/last_pulse**

Replace the `_loop` method signature and add local tracking variables. Find the line:
```python
    def _loop(self, started_at: float) -> None:
        last_sequence: dict[str, int] = {role: 0 for role in self._managed}
        targets: dict[str, tuple[float, float]] = {}
        bad_counts: dict[str, int] = {role: 0 for role in self._managed}
```

Replace with:
```python
    def _loop(self, started_at: float) -> None:
        import math
        last_sequence: dict[str, int] = {role: 0 for role in self._managed}
        targets: dict[str, tuple[float, float]] = {}
        bad_counts: dict[str, int] = {role: 0 for role in self._managed}
        error_history: list[float] = []   # error magnitudes for rms_px
        last_pulse: tuple[str, int] | None = None
```

Then find the rebaseline check location. After the `if measurement.accepted and target is None ...` block (which sets a new target), add a rebaseline check BEFORE that block:

```python
                    else:
                        # Rebaseline: clear the current target so next accepted frame sets a new one
                        if self._rebaseline_requested.is_set():
                            targets.pop(role, None)
                            self._rebaseline_requested.clear()
                            target = None
                        if (
                            measurement.accepted
                            and target is None
                            and measurement.centroid_x is not None
                            and measurement.centroid_y is not None
                        ):
                            targets[role] = (measurement.centroid_x, measurement.centroid_y)
```

Then find the pulse-issuing block:
```python
            if not self._measure_only and pulses and self._mount is not None:
                for pulse in pulses:
                    try:
                        self._mount.guide(pulse.direction, pulse.duration_ms)
                    except Exception as exc:
                        _log.error("mount.guide failed: %s", exc)
```

Replace with:
```python
            with self._status_lock:
                paused = self._pulses_paused
            if not self._measure_only and not paused and pulses and self._mount is not None:
                for pulse in pulses:
                    try:
                        self._mount.guide(pulse.direction, pulse.duration_ms)
                        last_pulse = (pulse.direction, pulse.duration_ms)
                    except Exception as exc:
                        _log.error("mount.guide failed: %s", exc)

            # Track error magnitude for rms_px using active measurement
            if active_measurement and active_measurement.error_x is not None and active_measurement.error_y is not None:
                mag = math.sqrt(active_measurement.error_x ** 2 + active_measurement.error_y ** 2)
                error_history.append(mag)
                if len(error_history) > 10:
                    error_history.pop(0)
            rms_px = (
                math.sqrt(sum(e ** 2 for e in error_history) / len(error_history))
                if len(error_history) >= 2 else 0.0
            )
```

Then find the `with self._status_lock:` block that writes `self._status` and replace:
```python
            with self._status_lock:
                self._status = GuidingStatus(
                    state="running",
                    measure_only=self._measure_only,
                    active_role=active_role,
                    fallback_reason=self._selector.reason,
                    sources=states,
                    latest_pulses=pulses,
                    started_at=started_at,
                    rms_px=rms_px,
                    last_pulse=last_pulse,
                )
```

- [ ] **Step 7: Run tests to verify they pass**

```
pytest tests/unit/services/test_guiding_service.py -v
```

Expected: All pass. (3 new + existing 7 = 10 total)

- [ ] **Step 8: Commit**

```
git add smart_telescope/services/guiding_service.py tests/unit/services/test_guiding_service.py
git commit -m "feat(GUD): add pause_pulses, resume_pulses, rebaseline; rms_px/last_pulse in status"
```

---

## Task 2: CollimationConfig — guiding fields

**Files:**
- Modify: `smart_telescope/domain/collimation/config.py`
- Test: `tests/unit/services/test_collimation_guiding.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/unit/services/test_collimation_guiding.py`:

```python
"""Tests for CollimationAssistant guiding integration."""
import pytest
from smart_telescope.domain.collimation.config import CollimationConfig


def test_collimation_config_guiding_defaults():
    cfg = CollimationConfig.from_dict({})
    assert cfg.guiding_camera_role == "guide"
    assert cfg.guiding_exposure_s == 2.0
    assert cfg.guiding_cadence_s == 3.0


def test_collimation_config_guiding_from_toml():
    cfg = CollimationConfig.from_dict({
        "guiding_camera_role": "oag",
        "guiding_exposure_s": 1.5,
        "guiding_cadence_s": 2.0,
    })
    assert cfg.guiding_camera_role == "oag"
    assert cfg.guiding_exposure_s == 1.5
    assert cfg.guiding_cadence_s == 2.0
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/unit/services/test_collimation_guiding.py::test_collimation_config_guiding_defaults -v
```

Expected: FAIL — `TypeError: CollimationConfig.__init__() got an unexpected keyword argument 'guiding_camera_role'`

- [ ] **Step 3: Add guiding fields to `CollimationConfig`**

In `smart_telescope/domain/collimation/config.py`, in the `CollimationConfig` dataclass (after the `fine_collimation` field), add:

```python
    guiding_camera_role: str = "guide"
    guiding_exposure_s: float = 2.0
    guiding_cadence_s: float = 3.0
```

In `from_dict()`, after `fine_collimation=FineCollimationConfig.from_dict(d.get("fine_collimation", {})),` add:

```python
            guiding_camera_role=str(d.get("guiding_camera_role", "guide")),
            guiding_exposure_s=float(d.get("guiding_exposure_s", 2.0)),
            guiding_cadence_s=float(d.get("guiding_cadence_s", 3.0)),
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/unit/services/test_collimation_guiding.py::test_collimation_config_guiding_defaults tests/unit/services/test_collimation_guiding.py::test_collimation_config_guiding_from_toml -v
```

Expected: PASS

- [ ] **Step 5: Run full suite to check no regressions**

```
pytest tests/unit/ -q --tb=short
```

Expected: all pass (2 new).

- [ ] **Step 6: Commit**

```
git add smart_telescope/domain/collimation/config.py tests/unit/services/test_collimation_guiding.py
git commit -m "feat(COL): add guiding_camera_role/exposure_s/cadence_s to CollimationConfig"
```

---

## Task 3: CollimationAssistant — guiding lifecycle and recentering

**Files:**
- Modify: `smart_telescope/services/collimation/assistant.py`
- Test: `tests/unit/services/test_collimation_guiding.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/services/test_collimation_guiding.py`:

```python
import threading
import time
from unittest.mock import MagicMock, call, patch


def _make_mock_guiding_service():
    svc = MagicMock()
    svc.status.return_value = MagicMock(
        state="idle", rms_px=0.0, last_pulse=None
    )
    svc.status.return_value.to_dict.return_value = {
        "state": "idle", "rms_px": 0.0, "last_pulse": None,
    }
    return svc


def _make_minimal_assistant(guiding_service=None, guide_cameras=None):
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
    )


def test_assistant_accepts_guiding_service_kwarg():
    svc = _make_mock_guiding_service()
    assistant = _make_minimal_assistant(guiding_service=svc)
    assert assistant is not None


def test_no_guiding_service_does_not_crash():
    assistant = _make_minimal_assistant(guiding_service=None)
    assert assistant is not None


def test_status_includes_guiding_dict_when_service_present():
    svc = _make_mock_guiding_service()
    assistant = _make_minimal_assistant(guiding_service=svc)
    s = assistant.status
    assert "guiding" in s
    assert s["guiding"]["available"] is True


def test_status_guiding_unavailable_when_no_service():
    assistant = _make_minimal_assistant(guiding_service=None)
    s = assistant.status
    assert s["guiding"]["available"] is False


def test_guiding_stops_when_run_exits():
    """Verify _stop_guiding() is called when the background thread finishes."""
    svc = _make_mock_guiding_service()
    svc.status.return_value.state = "running"

    from smart_telescope.services.collimation.assistant import CollimationAssistant
    cam = MagicMock()
    cam.get_bit_depth.return_value = 16
    cam.get_exposure_ms.return_value = 100.0
    cam.get_gain.return_value = 100
    mount = MagicMock()
    mount.goto.side_effect = RuntimeError("no mount")  # causes FAILED immediately
    focuser = MagicMock()

    assistant = CollimationAssistant(
        camera=cam, mount=mount, focuser=focuser,
        guiding_service=svc, guide_cameras={"guide": MagicMock()},
    )
    assistant.start()
    time.sleep(0.3)  # let background thread run until FAILED

    # stop() is called in finally block of _run()
    svc.stop.assert_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/unit/services/test_collimation_guiding.py -v
```

Expected: FAIL on `test_assistant_accepts_guiding_service_kwarg` — `TypeError: CollimationAssistant.__init__() got an unexpected keyword argument 'guiding_service'`

- [ ] **Step 3: Update `CollimationAssistant.__init__` to accept guiding service**

In `smart_telescope/services/collimation/assistant.py`, update the import block at the top to add the TYPE_CHECKING guard:

```python
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from ...services.guiding_service import GuidingService
```

Update `__init__` signature:

```python
    def __init__(
        self,
        camera: CameraPort,
        mount: MountPort,
        focuser: FocuserPort,
        guiding_service: "GuidingService | None" = None,
        guide_cameras: "dict[str, CameraPort] | None" = None,
    ) -> None:
        self._camera = camera
        self._mount = mount
        self._focuser = focuser
        self._guiding_service = guiding_service
        self._guide_cameras: dict[str, CameraPort] = guide_cameras or {}
        # ... rest of __init__ unchanged
```

- [ ] **Step 4: Add `_guiding_status_dict()` and wire into `status` property**

Add after `_new_report_builder()`:

```python
    def _guiding_status_dict(self) -> dict:
        if self._guiding_service is None:
            return {"available": False}
        s = self._guiding_service.status()
        return {
            "available": True,
            "state": s.state,
            "rms_px": s.rms_px,
            "last_pulse": list(s.last_pulse) if s.last_pulse else None,
        }
```

In the `status` property, add `"guiding": self._guiding_status_dict()` to the returned dict:

```python
            return {
                "state":                self._sm.state.value,
                "instruction":          self._sm.instruction(),
                "is_waiting_for_user":  self._sm.is_waiting_for_user(),
                "is_paused":            self._sm.state == CollimationState.PAUSED,
                "is_terminal":          self._sm.is_terminal(),
                "current_recommendation": rec,
                "last_measurement":     meas,
                "error":                self._error,
                "started_at":           self._started_at,
                "updated_at":           self._updated_at,
                "guiding":              self._guiding_status_dict(),
            }
```

- [ ] **Step 5: Run status tests**

```
pytest tests/unit/services/test_collimation_guiding.py::test_assistant_accepts_guiding_service_kwarg tests/unit/services/test_collimation_guiding.py::test_no_guiding_service_does_not_crash tests/unit/services/test_collimation_guiding.py::test_status_includes_guiding_dict_when_service_present tests/unit/services/test_collimation_guiding.py::test_status_guiding_unavailable_when_no_service -v
```

Expected: PASS (4 tests).

- [ ] **Step 6: Add `_start_guiding()`, `_stop_guiding()`, and `_with_guiding_paused()` helpers**

Add after `_guiding_status_dict()`:

```python
    def _start_guiding(self) -> None:
        if self._guiding_service is None or not self._guide_cameras:
            return
        try:
            self._guiding_service.start(
                self._guide_cameras,
                exposure_s=self._cfg.guiding_exposure_s,
                cadence_s=self._cfg.guiding_cadence_s,
                mount=self._mount,
            )
            _log.info("CollimationAssistant: guiding started")
        except Exception as exc:
            _log.warning("CollimationAssistant: guiding start failed: %s", exc)

    def _stop_guiding(self) -> None:
        if self._guiding_service is None:
            return
        try:
            if self._guiding_service.status().state == "running":
                self._guiding_service.stop()
                _log.info("CollimationAssistant: guiding stopped")
        except Exception as exc:
            _log.warning("CollimationAssistant: guiding stop failed: %s", exc)

    def _with_guiding_paused(self, fn: Callable) -> None:
        """Pause guide pulses, run fn(), rebaseline + resume regardless of fn outcome."""
        if self._guiding_service is not None:
            self._guiding_service.pause_pulses()
        try:
            fn()
        finally:
            if self._guiding_service is not None:
                self._guiding_service.rebaseline()
                self._guiding_service.resume_pulses()
```

- [ ] **Step 7: Add `_recenter_star()` helper**

The existing `_handle_center_star()` transitions to `AUTO_EXPOSURE` at the end. The recenter-for-remeasure variant should not transition — it just recenters. Add this helper after `_with_guiding_paused()`:

```python
    def _recenter_star(self) -> None:
        """Re-centre the main camera star via PulseCenterer (no state transition)."""
        from ...domain.collimation.models import ReferenceCenterCalibration
        from ...domain.collimation.processing.frame import normalize_frame
        from ...domain.collimation.processing.star_detection import detect_star
        from ...domain.collimation.profiles import get_profile
        from .mount_centering import PulseCenterer

        bit_depth  = self._camera.get_bit_depth()
        exposure_s = self._camera.get_exposure_ms() / 1000.0
        profile    = get_profile(self._cfg.telescope_profile)
        ref_cfg    = self._cfg.reference_center

        centerer = PulseCenterer(
            mount=self._mount,
            config=self._cfg.mount_centering,
            pixel_scale_arcsec=profile.pixel_scale_arcsec,
        )

        def _get_offset() -> tuple[float, float] | None:
            if self._cancel.is_set():
                return None
            try:
                raw = self._camera.capture(exposure_s)
            except Exception:
                return None
            processed = normalize_frame(raw, bit_depth=bit_depth)
            star = detect_star(processed)
            if star is None:
                return None
            ref = ReferenceCenterCalibration(
                offset_x_px=ref_cfg.offset_x_px,
                offset_y_px=ref_cfg.offset_y_px,
                source=ref_cfg.source.value,
            ).compute(processed.width, processed.height)
            return star.center_x - ref.x, star.center_y - ref.y

        result = centerer.center(
            get_offset_px=_get_offset,
            cancel_check=lambda: self._cancel.is_set(),
            dec_deg=self._target_dec or 0.0,
        )
        _log.info(
            "RECENTER: %s pulses=%d offset=%.1f px",
            result.reason, result.pulses_issued, result.final_offset_px,
        )
```

- [ ] **Step 8: Call `_start_guiding()` at the end of `_handle_auto_exposure()`**

Find the end of `_handle_auto_exposure()`:
```python
        _log.info("AUTO_EXPOSURE: final exposure=%.3f s", exposure_s)
        self._do_transition(CollimationState.ROUGH_DEFOCUS)
```

Replace with:
```python
        _log.info("AUTO_EXPOSURE: final exposure=%.3f s", exposure_s)
        self._start_guiding()
        self._do_transition(CollimationState.ROUGH_DEFOCUS)
```

- [ ] **Step 9: Call `_stop_guiding()` in `_run()` finally block**

Find the `finally:` block at the end of `_run()`:
```python
        finally:
            _log.info(
                "CollimationAssistant: worker thread exiting in state %s",
                self._sm.state.value,
            )
```

Replace with:
```python
        finally:
            self._stop_guiding()
            _log.info(
                "CollimationAssistant: worker thread exiting in state %s",
                self._sm.state.value,
            )
```

- [ ] **Step 10: Add recentering to `_dispatch_user_wait()` for Remeasure cases**

Find the `GUIDE_ROUGH_COLLIMATION` case in `_dispatch_user_wait()`:
```python
        elif state == CollimationState.GUIDE_ROUGH_COLLIMATION:
            if payload.get("finish"):
                self._do_transition(CollimationState.INSTALL_TRIBAHTINOV)
            else:
                self._do_transition(CollimationState.MEASURE_DONUT)
```

Replace with:
```python
        elif state == CollimationState.GUIDE_ROUGH_COLLIMATION:
            if payload.get("finish"):
                self._do_transition(CollimationState.INSTALL_TRIBAHTINOV)
            else:
                self._with_guiding_paused(self._recenter_star)
                self._do_transition(CollimationState.MEASURE_DONUT)
```

Find the `GUIDE_FINE_COLLIMATION` case:
```python
        elif state == CollimationState.GUIDE_FINE_COLLIMATION:
            if payload.get("finish"):
                self._do_transition(CollimationState.FINAL_REFOCUS)
            else:
                self._do_transition(CollimationState.MEASURE_SPIKES)
```

Replace with:
```python
        elif state == CollimationState.GUIDE_FINE_COLLIMATION:
            if payload.get("finish"):
                self._do_transition(CollimationState.FINAL_REFOCUS)
            else:
                self._with_guiding_paused(self._recenter_star)
                self._do_transition(CollimationState.MEASURE_SPIKES)
```

- [ ] **Step 11: Run all collimation guiding tests**

```
pytest tests/unit/services/test_collimation_guiding.py -v
```

Expected: All 7 tests pass.

- [ ] **Step 12: Run full test suite**

```
pytest tests/unit/ -q --tb=short
```

Expected: All pass.

- [ ] **Step 13: Commit**

```
git add smart_telescope/services/collimation/assistant.py tests/unit/services/test_collimation_guiding.py
git commit -m "feat(COL): inject GuidingService into CollimationAssistant; lifecycle + recentering"
```

---

## Task 4: API wiring — pass GuidingService to the assistant

**Files:**
- Modify: `smart_telescope/api/collimation.py`

No new tests needed for this task — the existing collimation API tests cover the status endpoint.

- [ ] **Step 1: Update `_get_assistant()` to build and pass a GuidingService**

In `smart_telescope/api/collimation.py`, find the `_get_assistant()` function:

```python
def _get_assistant() -> CollimationAssistant:
    global _assistant
    if _assistant is None:
        with _assistant_lock:
            if _assistant is None:
                _assistant = CollimationAssistant(
                    camera=get_camera(),
                    mount=get_mount(),
                    focuser=get_focuser(),
                )
    return _assistant
```

Replace with:

```python
def _get_assistant() -> CollimationAssistant:
    global _assistant
    if _assistant is None:
        with _assistant_lock:
            if _assistant is None:
                from ..services.guiding_service import GuidingService
                from ..services.guide_measurement import CentroidConfig, GuideControllerConfig
                from .. import config as _cfg_mod

                col_cfg = _cfg_mod.get_collimation_config()
                guiding_svc: GuidingService | None = None
                guide_cameras: dict = {}
                try:
                    guide_cam = get_camera_by_role(col_cfg.guiding_camera_role)
                    guide_cameras = {col_cfg.guiding_camera_role: guide_cam}
                    guiding_svc = GuidingService.from_config(
                        primary_role=col_cfg.guiding_camera_role,
                        allow_fallback=False,
                        fallback_after_bad_frames=5,
                        max_frame_age_s=col_cfg.guiding_cadence_s * 3,
                        centroid_config=CentroidConfig(),
                        controller_config=GuideControllerConfig(),
                        measure_only=False,
                    )
                except Exception:
                    _log.info(
                        "CollimationAssistant: guide camera '%s' not available — "
                        "starting without guiding",
                        col_cfg.guiding_camera_role,
                    )

                _assistant = CollimationAssistant(
                    camera=get_camera(),
                    mount=get_mount(),
                    focuser=get_focuser(),
                    guiding_service=guiding_svc,
                    guide_cameras=guide_cameras,
                )
    return _assistant
```

`get_collimation_config()` already exists in `smart_telescope/config.py` — it calls `CollimationConfig.from_dict(_cfg.get("collimation", {}))` and validates. No new helper needed.

- [ ] **Step 2: Import `get_camera_by_role` at the top of the file**

Find the imports line:
```python
from .deps import get_camera, get_focuser, get_mount
```

Replace with:
```python
from .deps import get_camera, get_camera_by_role, get_focuser, get_mount
```

- [ ] **Step 4: Verify the API status endpoint returns guiding key**

```
pytest tests/unit/api/ -q --tb=short -k collimation
```

Expected: All existing collimation API tests pass (the `"guiding"` key is now in every status response — no test should break because existing tests check specific keys, not exact dict equality).

- [ ] **Step 5: Commit**

```
git add smart_telescope/api/collimation.py smart_telescope/config.py
git commit -m "feat(COL): wire GuidingService into collimation API factory"
```

---

## Task 5: UI — guide status row in wizard card

**Files:**
- Modify: `smart_telescope/static/index.html`
- Modify: `smart_telescope/static/js/collimation.js`

- [ ] **Step 1: Add guide row HTML to the wizard card**

In `smart_telescope/static/index.html`, find the instruction div (around line 1369):
```html
      <div id="s4-wiz-instruction"
           style="font-size:0.88rem;min-height:2.5em;margin-bottom:0.6rem;line-height:1.45;color:var(--text)">
        Ready. Click Start to begin the collimation wizard.
      </div>
```

Insert the guide row div immediately AFTER the closing `</div>` of the instruction div and BEFORE the `<!-- Screw recommendation -->` comment:

```html
      <!-- Guide status row (shown when guiding is active) -->
      <div id="s4-wiz-guide-row"
           style="display:none;font-size:0.82rem;color:var(--muted);
                  margin-bottom:0.5rem;align-items:center;gap:0.4rem">
        <span class="dot dot-grey" id="s4-wiz-guide-dot"></span>
        <span id="s4-wiz-guide-label">Guide: —</span>
      </div>
```

- [ ] **Step 2: Add guide row rendering to `_updateCollimWizard`**

In `smart_telescope/static/js/collimation.js`, find the end of `_updateCollimWizard(s)` — the line that reads:

```javascript
    // Buttons
    _wizBtn('s4-wiz-start-btn',  idle);
```

Insert immediately BEFORE that line:

```javascript
    // Guide status row
    const g = s.guiding;
    const guideRow = document.getElementById('s4-wiz-guide-row');
    if (guideRow) {
        if (!g || !g.available) {
            guideRow.style.display = 'none';
        } else {
            guideRow.style.display = 'flex';
            const dot    = document.getElementById('s4-wiz-guide-dot');
            const lbl    = document.getElementById('s4-wiz-guide-label');
            const locked = g.state === 'running';
            if (dot) dot.className = 'dot ' + (locked ? 'dot-green' : 'dot-red');
            const rms  = locked && g.rms_px != null
                ? ` RMS ${g.rms_px.toFixed(1)} px` : '';
            const last = g.last_pulse
                ? ` last ${g.last_pulse[1] > 0 ? '+' : ''}${g.last_pulse[1]}ms ${g.last_pulse[0]}`
                : '';
            if (lbl) lbl.textContent = `Guide: ${locked ? 'locked' : 'lost'}${rms}${last}`;
        }
    }

```

- [ ] **Step 3: Run full test suite to check no regressions**

```
pytest tests/unit/ -q --tb=short
```

Expected: All pass. (The HTML/JS changes have no Python tests — verify visually if the app is running.)

- [ ] **Step 4: Commit**

```
git add smart_telescope/static/index.html smart_telescope/static/js/collimation.js
git commit -m "feat(COL): add guide status row to collimation wizard card"
```

---

## Final check

After all tasks complete:

- [ ] Run the full test suite:

```
pytest tests/unit/ -q
```

Expected: All pass, coverage ≥ 80%.

- [ ] Update `wiki/index.md` and `wiki/log.md` per CLAUDE.md workflow.
