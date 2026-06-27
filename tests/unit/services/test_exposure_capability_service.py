"""Tests for exposure capability test service (M8-023 / REQ-AG-003..004)."""
from __future__ import annotations

import json
import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_telescope.domain.exposure_capability import (
    TEST_EXPOSURES_S,
    ExposureCapabilityResult,
    ExposureStepDiagnostics,
)
from smart_telescope.services.exposure_capability_service import run_exposure_test


# ── Domain ────────────────────────────────────────────────────────────────────

def test_test_exposures_s_correct():
    assert TEST_EXPOSURES_S == (0.5, 1.0, 2.0, 4.0, 8.0)


def test_exposure_step_diagnostics_has_correct_fields():
    """13 diagnostic fields + exposure_s = 14 total; the 13 named in the spec are all present."""
    step = ExposureStepDiagnostics(
        exposure_s=1.0,
        number_of_stars_detected=10,
        background_median_adu=100.0,
        background_stddev_adu=5.0,
        saturated_pixel_ratio=0.0,
        black_clipped_pixel_ratio=0.0,
        median_fwhm_px=2.5,
        median_hfr_px=1.25,
        exposure_limit_reached=False,
        gain_limit_reached=False,
        offset_limit_reached=False,
        tracking_blur_suspected=False,
        reason_for_next_step="no saturation or blur detected",
        reason_for_stop=None,
    )
    d = step.to_dict()
    # 13 diagnostic fields (REQ-AG-003) + exposure_s = 14 total dict entries
    assert len(d) == 14
    required_13 = {
        "number_of_stars_detected", "background_median_adu", "background_stddev_adu",
        "saturated_pixel_ratio", "black_clipped_pixel_ratio", "median_fwhm_px",
        "median_hfr_px", "exposure_limit_reached", "gain_limit_reached",
        "offset_limit_reached", "tracking_blur_suspected",
        "reason_for_next_step", "reason_for_stop",
    }
    assert required_13.issubset(d.keys())


def test_exposure_capability_result_to_dict():
    r = ExposureCapabilityResult(steps=[], recommended_exposure_s=4.0, stopped_early=False, stop_reason=None)
    d = r.to_dict()
    assert set(d.keys()) == {"steps", "recommended_exposure_s", "stopped_early", "stop_reason"}


def test_exposure_capability_result_to_json_line():
    r = ExposureCapabilityResult()
    data = json.loads(r.to_json_line())
    assert "steps" in data


# ── run_exposure_test() ───────────────────────────────────────────────────────

def _make_camera(mean_frac: float = 0.3, bit_depth: int = 16) -> MagicMock:
    adc_max = (1 << bit_depth) - 1
    mean_val = mean_frac * adc_max
    frame = MagicMock()
    frame.pixels = np.full((64, 64), mean_val, dtype=np.float32)
    frame.header = {"BITDEPTH": bit_depth}
    camera = MagicMock()
    camera.capture = MagicMock(return_value=frame)
    return camera


def test_run_all_five_steps_when_no_issue():
    camera = _make_camera(mean_frac=0.1)  # dark but not saturated
    result = run_exposure_test(camera, gain=100, offset=0)
    assert len(result.steps) == 5
    assert not result.stopped_early
    assert result.stop_reason == "All exposures tested"
    assert camera.capture.call_count == 5


def test_each_step_has_correct_exposure():
    camera = _make_camera(mean_frac=0.1)
    result = run_exposure_test(camera, gain=100, offset=0)
    for step, exp_s in zip(result.steps, TEST_EXPOSURES_S):
        assert step.exposure_s == exp_s


def test_last_step_has_exposure_limit_reached():
    camera = _make_camera()
    result = run_exposure_test(camera, gain=100, offset=0)
    assert result.steps[-1].exposure_limit_reached is True
    for step in result.steps[:-1]:
        assert step.exposure_limit_reached is False


def test_reason_for_next_step_set_on_all_but_last():
    camera = _make_camera(mean_frac=0.1)
    result = run_exposure_test(camera, gain=100, offset=0)
    for step in result.steps[:-1]:
        assert step.reason_for_next_step is not None
    assert result.steps[-1].reason_for_next_step is None


def test_reason_for_stop_set_only_on_last():
    camera = _make_camera(mean_frac=0.1)
    result = run_exposure_test(camera, gain=100, offset=0)
    for step in result.steps[:-1]:
        assert step.reason_for_stop is None
    assert result.steps[-1].reason_for_stop is not None


def test_stops_early_on_saturation():
    bit_depth = 16
    adc_max = (1 << bit_depth) - 1

    frame_normal = MagicMock()
    frame_normal.pixels = np.full((64, 64), 0.2 * adc_max, dtype=np.float32)
    frame_normal.header = {"BITDEPTH": 16}

    frame_sat = MagicMock()
    sat_pixels = np.zeros((64, 64), dtype=np.float32)
    sat_pixels[:2, :] = 0.999 * adc_max  # >1% saturated
    frame_sat.pixels = sat_pixels
    frame_sat.header = {"BITDEPTH": 16}

    call_count = [0]

    def _capture(exp_s: float):
        call_count[0] += 1
        return frame_normal if call_count[0] < 3 else frame_sat

    camera = MagicMock()
    camera.capture = MagicMock(side_effect=_capture)

    result = run_exposure_test(camera, gain=100, offset=0)
    assert result.stopped_early is True
    assert "saturati" in (result.stop_reason or "").lower()
    assert call_count[0] == 3  # stopped at step 3


def test_stops_early_on_tracking_blur():
    """Second frame has horizontal stripes (high elongation) → stop after frame 2."""
    bit_depth = 16
    adc_max = (1 << bit_depth) - 1
    dark = 0.05 * adc_max

    frame1 = MagicMock()
    frame1.pixels = np.full((64, 64), dark, dtype=np.float32)
    frame1.header = {"BITDEPTH": 16}

    frame2 = MagicMock()
    px2 = np.zeros((64, 64), dtype=np.float32)
    for row in range(0, 64, 2):
        px2[row, :] = dark * 4  # alternating rows → strong vertical gradient → elongation
    frame2.pixels = px2
    frame2.header = {"BITDEPTH": 16}

    call_count = [0]

    def _capture(exp_s: float):
        call_count[0] += 1
        return frame1 if call_count[0] == 1 else frame2

    camera = MagicMock()
    camera.capture = MagicMock(side_effect=_capture)

    result = run_exposure_test(camera, gain=100, offset=0)
    assert result.stopped_early is True
    assert "blur" in (result.stop_reason or "").lower() or "elongation" in (result.stop_reason or "").lower()
    assert call_count[0] == 2
    assert result.steps[-1].tracking_blur_suspected is True


def test_cancelled_by_flag():
    flag = threading.Event()
    flag.set()

    camera = _make_camera()
    result = run_exposure_test(camera, gain=100, offset=0, cancellation_flag=flag)
    assert result.stopped_early is True
    assert "cancel" in (result.stop_reason or "").lower()
    assert camera.capture.call_count == 0


def test_recommended_exposure_is_last_good_step():
    """recommended_exposure_s should be the last step before blur/saturation."""
    camera = _make_camera(mean_frac=0.1)  # all frames good
    result = run_exposure_test(camera, gain=100, offset=0)
    # All 5 steps OK → recommended = last step = 8.0 s
    assert result.recommended_exposure_s == 8.0


def test_gain_at_limit_flag_propagated():
    camera = _make_camera()
    result = run_exposure_test(camera, gain=100, offset=0, gain_at_limit=True)
    for step in result.steps:
        assert step.gain_limit_reached is True


def test_offset_at_limit_flag_propagated():
    camera = _make_camera()
    result = run_exposure_test(camera, gain=100, offset=0, offset_at_limit=True)
    for step in result.steps:
        assert step.offset_limit_reached is True


def test_background_stats_computed():
    camera = _make_camera(mean_frac=0.2)
    result = run_exposure_test(camera, gain=100, offset=0)
    for step in result.steps:
        assert step.background_median_adu >= 0
        assert step.background_stddev_adu >= 0


def test_custom_exposures_used():
    camera = _make_camera(mean_frac=0.1)
    result = run_exposure_test(camera, gain=100, offset=0, exposures_s=(1.0, 2.0))
    assert len(result.steps) == 2
    assert result.steps[0].exposure_s == 1.0
    assert result.steps[1].exposure_s == 2.0
