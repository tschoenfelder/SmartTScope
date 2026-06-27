"""Tests for ctc_loop_service — M8-028 / REQ-CLICK-004."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_telescope.domain.ctc_calibration import CTCCalibration
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.services.ctc_loop_service import (
    CTCIterationLog,
    CTCLoopResult,
    _pixel_offset_to_move,
    run_centering_loop,
)


# ── helpers ─────────────────────────────────────────────────────────────────

def _cal(arcsec_per_px=1.0, rotation_deg=0.0) -> CTCCalibration:
    import time
    return CTCCalibration(
        arcsec_per_px_x=arcsec_per_px, arcsec_per_px_y=arcsec_per_px,
        rotation_deg=rotation_deg, optical_train="test", binning=1,
        measured_at=time.time(), max_age_hours=24.0,
    )


def _frame(w=200, h=200, value=1000.0) -> FitsFrame:
    """Uniform frame — refinement will fall back to raw coords."""
    return FitsFrame(
        pixels=np.full((h, w), value, dtype=np.float32),
        header={},
        exposure_seconds=1.0,
    )


def _mock_camera(frame: FitsFrame | None = None) -> MagicMock:
    cam = MagicMock()
    cam.capture = MagicMock(return_value=frame or _frame())
    return cam


def _mock_mount() -> MagicMock:
    m = MagicMock()
    m.move = MagicMock(return_value=True)
    return m


# ── _pixel_offset_to_move ────────────────────────────────────────────────────

def test_positive_x_offset_gives_west():
    _, _, dir_ra, _, _, _ = _pixel_offset_to_move(
        offset_x_px=10, offset_y_px=0,
        arcsec_per_px_x=1.0, arcsec_per_px_y=1.0,
        rotation_deg=0.0, center_rate_arcsec_per_sec=1.0,
        fraction=1.0, max_px=1000,
    )
    assert dir_ra == "w"


def test_negative_x_offset_gives_east():
    _, _, dir_ra, _, _, _ = _pixel_offset_to_move(
        offset_x_px=-10, offset_y_px=0,
        arcsec_per_px_x=1.0, arcsec_per_px_y=1.0,
        rotation_deg=0.0, center_rate_arcsec_per_sec=1.0,
        fraction=1.0, max_px=1000,
    )
    assert dir_ra == "e"


def test_positive_y_offset_gives_south():
    _, _, _, dir_dec, _, _ = _pixel_offset_to_move(
        offset_x_px=0, offset_y_px=10,
        arcsec_per_px_x=1.0, arcsec_per_px_y=1.0,
        rotation_deg=0.0, center_rate_arcsec_per_sec=1.0,
        fraction=1.0, max_px=1000,
    )
    assert dir_dec == "s"


def test_move_duration_scales_with_offset():
    _, _, _, _, ms_ra1, _ = _pixel_offset_to_move(
        10, 0, 1.0, 1.0, 0.0, 1.0, 1.0, 1000)
    _, _, _, _, ms_ra2, _ = _pixel_offset_to_move(
        20, 0, 1.0, 1.0, 0.0, 1.0, 1.0, 1000)
    assert ms_ra2 == 2 * ms_ra1


def test_fraction_reduces_move():
    _, _, _, _, ms_full, _ = _pixel_offset_to_move(
        10, 0, 1.0, 1.0, 0.0, 1.0, 1.0, 1000)
    _, _, _, _, ms_half, _ = _pixel_offset_to_move(
        10, 0, 1.0, 1.0, 0.0, 1.0, 0.5, 1000)
    assert ms_half == ms_full // 2


def test_max_px_clamps_large_offset():
    _, _, _, _, ms_clamped, _ = _pixel_offset_to_move(
        1000, 0, 1.0, 1.0, 0.0, 1.0, 1.0, 100)
    _, _, _, _, ms_direct, _ = _pixel_offset_to_move(
        100, 0, 1.0, 1.0, 0.0, 1.0, 1.0, 1000)
    assert ms_clamped == ms_direct


# ── run_centering_loop ───────────────────────────────────────────────────────

def test_loop_runs_with_mock_camera_and_mount():
    cam = _mock_camera()
    mount = _mock_mount()
    result = run_centering_loop(
        camera=cam, mount=mount, calibration=_cal(),
        target_x_px=100, target_y_px=100,
        max_iterations=2, center_tolerance_px=500,  # very wide tolerance → should complete
        max_single_move_px=300, move_fraction=0.5,
        center_rate_arcsec_per_sec=120.0, allow_tracking_off=True,
        exposure_s=0.001,
    )
    assert isinstance(result, CTCLoopResult)


def test_loop_stops_within_tolerance():
    """Uniform frame → refinement falls back to raw click; target at frame centre → offset=0."""
    cam = _mock_camera()
    mount = _mock_mount()
    # Frame is 200×200. Target at centre (100,100) → offset_x/y = 0 → within_tolerance immediately
    result = run_centering_loop(
        camera=cam, mount=mount, calibration=_cal(),
        target_x_px=100, target_y_px=100,  # exactly at centre of 200×200 frame
        max_iterations=5, center_tolerance_px=20,
        max_single_move_px=300, move_fraction=0.5,
        center_rate_arcsec_per_sec=120.0, allow_tracking_off=True,
        exposure_s=0.001,
    )
    assert result.completed is True
    assert len(result.iterations) == 1  # tolerance met on iteration 1


def test_loop_records_iterations():
    cam = _mock_camera()
    mount = _mock_mount()
    result = run_centering_loop(
        camera=cam, mount=mount, calibration=_cal(),
        target_x_px=0, target_y_px=0,  # top-left corner → large offset from centre
        max_iterations=3, center_tolerance_px=1,  # tight tolerance — won't converge
        max_single_move_px=300, move_fraction=0.5,
        center_rate_arcsec_per_sec=120.0, allow_tracking_off=True,
        exposure_s=0.001,
    )
    assert len(result.iterations) > 0
    assert all(isinstance(it, CTCIterationLog) for it in result.iterations)


def test_loop_cancelled_by_flag():
    flag = threading.Event()
    flag.set()  # cancel immediately
    cam = _mock_camera()
    mount = _mock_mount()
    result = run_centering_loop(
        camera=cam, mount=mount, calibration=_cal(),
        target_x_px=0, target_y_px=0,
        max_iterations=5, center_tolerance_px=1,
        max_single_move_px=300, move_fraction=0.5,
        center_rate_arcsec_per_sec=120.0, allow_tracking_off=True,
        cancellation_flag=flag, exposure_s=0.001,
    )
    assert result.cancelled is True


def test_loop_camera_error_stops_loop():
    cam = MagicMock()
    cam.capture = MagicMock(side_effect=RuntimeError("Camera error"))
    mount = _mock_mount()
    result = run_centering_loop(
        camera=cam, mount=mount, calibration=_cal(),
        target_x_px=100, target_y_px=100,
        max_iterations=3, center_tolerance_px=1,
        max_single_move_px=300, move_fraction=0.5,
        center_rate_arcsec_per_sec=120.0, allow_tracking_off=True,
        exposure_s=0.001,
    )
    assert result.completed is False
    assert "Camera capture failed" in result.stop_reason


def test_loop_mount_move_error_stops_loop():
    cam = _mock_camera()
    mount = MagicMock()
    mount.move = MagicMock(side_effect=RuntimeError("Mount error"))
    result = run_centering_loop(
        camera=cam, mount=mount, calibration=_cal(),
        target_x_px=0, target_y_px=0,  # offset from centre → moves issued
        max_iterations=3, center_tolerance_px=1,
        max_single_move_px=300, move_fraction=0.5,
        center_rate_arcsec_per_sec=120.0, allow_tracking_off=True,
        exposure_s=0.001,
    )
    assert result.completed is False
    assert "Mount move failed" in result.stop_reason


def test_iteration_log_has_json_line():
    it = CTCIterationLog(
        iteration=1, target_raw_x=80, target_raw_y=80,
        target_refined_x=80, target_refined_y=80,
        offset_x_px=-20.0, offset_y_px=-20.0,
        offset_arcsec_ra=-20.0, offset_arcsec_dec=-20.0,
        move_dir_ra="e", move_dir_dec="n",
        move_ms_ra=167, move_ms_dec=167,
        within_tolerance=False,
        refinement_method="star_centroid",
        elapsed_s=1.2,
    )
    import json
    data = json.loads(it.to_json_line())
    assert data["event"] == "CTC_ITERATION"
    assert data["iteration"] == 1


def test_max_iterations_reached():
    """Single iteration with target off-centre and tolerance_px=0.5 does not complete."""
    cam = _mock_camera()
    mount = _mock_mount()
    result = run_centering_loop(
        camera=cam, mount=mount, calibration=_cal(),
        target_x_px=0, target_y_px=0,  # off-centre; uniform frame → raw fallback at (0,0)
        max_iterations=1, center_tolerance_px=0.5,  # very tight — offset ~141 px → not satisfied
        max_single_move_px=300, move_fraction=0.5,
        center_rate_arcsec_per_sec=120.0, allow_tracking_off=True,
        exposure_s=0.001,
    )
    assert result.completed is False
    assert "Max iterations" in result.stop_reason
    assert len(result.iterations) == 1
