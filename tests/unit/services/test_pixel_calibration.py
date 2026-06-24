"""Tests for PixelCalibrationService (M7-003 / DD-004 / TEST-002)."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest

from smart_telescope.domain.pixel_calibration import (
    PixelCalibration,
    PixelCalibrationError,
    PixelCalibrationState,
)
from smart_telescope.services.pixel_calibration_service import PixelCalibrationService
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.mount import MountPort
from smart_telescope.domain.frame import FitsFrame


# ── helpers ───────────────────────────────────────────────────────────────────

def _frame_with_star(peak_x: int, peak_y: int, size: int = 128) -> FitsFrame:
    """Create a FitsFrame with a single bright star at (peak_x, peak_y)."""
    pixels = np.zeros((size, size), dtype=np.float32)
    pixels[peak_y, peak_x] = 60000.0
    return FitsFrame(pixels=pixels, header={}, exposure_seconds=2.0)


def _mock_camera(*frames: FitsFrame) -> MagicMock:
    m = MagicMock(spec=CameraPort)
    m.capture.side_effect = list(frames)
    return m


def _mock_mount() -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.move.return_value = True
    return m


def _run_cal(
    service: PixelCalibrationService,
    camera: MagicMock,
    mount: MagicMock | None = None,
) -> PixelCalibration:
    if mount is None:
        mount = _mock_mount()
    return service.run(camera, mount, "c8_native", 1, 0.0)


# ── TEST-002-1: valid calibration stored and returned ─────────────────────────

def test_calibration_stored_and_returned():
    """After run(), get_calibration() returns the stored PixelCalibration."""
    svc = PixelCalibrationService()
    # star at (64, 64), then moves to (74, 64) for RA, (64, 74) for DEC
    # mount return moves do not trigger a capture, so only 3 frames are needed
    frames = [
        _frame_with_star(64, 64),   # reference
        _frame_with_star(74, 64),   # after RA east move
        _frame_with_star(64, 74),   # after DEC north move
    ]
    camera = _mock_camera(*frames)
    cal = _run_cal(svc, camera)

    assert isinstance(cal, PixelCalibration)
    assert svc.state == PixelCalibrationState.CALIBRATED
    assert svc.get_calibration() is cal
    assert cal.optical_train_id == "c8_native"
    assert cal.binning == 1
    # RA moved east → star shifted +10 px in x
    assert abs(cal.ra_vector_px[0] - 10.0) < 0.5
    assert abs(cal.ra_vector_px[1]) < 0.5


# ── TEST-002-2: second call returns cached calibration ────────────────────────

def test_second_call_returns_cache():
    """get_calibration() after run() returns the same object without re-running."""
    svc = PixelCalibrationService()
    frames = [
        _frame_with_star(64, 64),
        _frame_with_star(80, 64),
        _frame_with_star(64, 80),
    ]
    camera = _mock_camera(*frames)
    cal1 = _run_cal(svc, camera)
    cal2 = svc.get_calibration()
    assert cal1 is cal2


# ── TEST-002-3: calibration error when no star signal ─────────────────────────

def test_calibration_error_when_no_stars():
    """run() raises PixelCalibrationError when the reference frame has no signal."""
    svc = PixelCalibrationService()
    blank = FitsFrame(pixels=np.zeros((128, 128), dtype=np.float32), header={}, exposure_seconds=2.0)
    camera = _mock_camera(blank)
    with pytest.raises(PixelCalibrationError, match="No star signal"):
        _run_cal(svc, camera)
    assert svc.state == PixelCalibrationState.FAILED
    assert svc.last_error is not None


# ── TEST-002-4: invalidation on optical train change ─────────────────────────

def test_invalidation_clears_calibration():
    """invalidate() sets state to UNCALIBRATED and clears stored calibration."""
    svc = PixelCalibrationService()
    frames = [
        _frame_with_star(64, 64),
        _frame_with_star(80, 64),
        _frame_with_star(64, 80),
    ]
    camera = _mock_camera(*frames)
    _run_cal(svc, camera)
    assert svc.state == PixelCalibrationState.CALIBRATED

    svc.invalidate("optical train changed")
    assert svc.state == PixelCalibrationState.UNCALIBRATED
    with pytest.raises(PixelCalibrationError, match="not available"):
        svc.get_calibration()


# ── TEST-002-5: insufficient displacement raises error ────────────────────────

def test_insufficient_ra_displacement_raises():
    """run() raises PixelCalibrationError when RA move produces < 3 px displacement."""
    svc = PixelCalibrationService()
    # reference and post-RA frames have same star position → 0 px displacement
    frames = [
        _frame_with_star(64, 64),  # reference
        _frame_with_star(65, 64),  # RA move only 1 px → too small
    ]
    camera = _mock_camera(*frames)
    with pytest.raises(PixelCalibrationError, match="RA move"):
        _run_cal(svc, camera)
    assert svc.state == PixelCalibrationState.FAILED


# ── to_pixel_offset helper ────────────────────────────────────────────────────

def test_to_pixel_offset():
    """PixelCalibration.to_pixel_offset() combines RA and DEC vectors correctly."""
    cal = PixelCalibration(
        ra_vector_px=(10.0, 0.0),
        dec_vector_px=(0.0, 10.0),
        optical_train_id="test",
        binning=1,
        camera_orientation_deg=0.0,
        calibrated_at="2026-01-01T00:00:00+00:00",
    )
    dx, dy = cal.to_pixel_offset(2.0, 3.0)
    assert abs(dx - 20.0) < 1e-6   # 2 arcsec RA × 10 px/arcsec
    assert abs(dy - 30.0) < 1e-6   # 3 arcsec DEC × 10 px/arcsec
