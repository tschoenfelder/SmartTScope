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


class _ShiftedStarCamera:
    """First frame has star at x=32; subsequent frames at x=36 (4px shift)."""

    def __init__(self) -> None:
        self._calls = 0

    def capture(self, exposure_s: float):
        from smart_telescope.domain.frame import FitsFrame

        self._calls += 1
        pixels = np.full((64, 64), 100, dtype=np.uint16)
        x = 32 if self._calls == 1 else 36
        pixels[32, x] = 5000
        return FitsFrame(pixels=pixels, header={}, exposure_seconds=exposure_s)

    def abort_capture(self) -> None:
        pass


def test_guiding_service_measure_only_false_sends_pulses_to_mount():
    """When measure_only=False, guide pulses are forwarded to mount.guide()."""
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
    time.sleep(0.5)
    svc.stop()

    mock_mount.guide.assert_called()


def test_guiding_service_measure_only_false_mount_error_does_not_kill_loop():
    """A raising mount.guide() is swallowed; the guide loop stays running."""
    from unittest.mock import MagicMock

    mock_mount = MagicMock()
    mock_mount.guide.side_effect = RuntimeError("mount disconnected")

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
    time.sleep(0.5)
    status = svc.status()
    svc.stop()

    assert status.state == "running"


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
    """After rebaseline(), corrections should quiet down because new target == current position."""
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
    time.sleep(0.3)  # lock on first centroid (x=32), corrections firing for 4px error

    # Record how many guide calls happened BEFORE rebaseline
    calls_before = mock_mount.guide.call_count
    assert calls_before > 0, "expected corrections before rebaseline"

    # Rebaseline: x=36 becomes the new zero
    mock_mount.guide.reset_mock()
    svc.rebaseline()
    time.sleep(0.3)  # star is now AT the target → error ≈ 0 → corrections should stop

    calls_after = mock_mount.guide.call_count
    svc.stop()

    assert calls_after < calls_before, (
        f"expected fewer corrections after rebaseline, got {calls_after} vs {calls_before} before"
    )
