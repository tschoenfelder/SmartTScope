"""Tests for M8-022: 6 auto-gain purpose modes and PLATE_SOLVE tracking-quality gate."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_telescope.domain.autogain import AutoGainMode, measure_elongation_ratio, _select_conversion_gain
from smart_telescope.domain.camera_capabilities import ConversionGain


# ── Mode enum coverage ────────────────────────────────────────────────────────

def test_six_purpose_modes_exist():
    names = {m.value for m in AutoGainMode}
    for expected in ("PLATE_SOLVE", "DSO", "PLANET", "MOON", "COLLIMATION", "AUTOFOCUS"):
        assert expected in names, f"{expected} not in AutoGainMode"


def test_backward_compat_modes_exist():
    names = {m.value for m in AutoGainMode}
    for legacy in ("PLANETARY", "LUNAR", "GUIDING"):
        assert legacy in names, f"Legacy mode {legacy} missing"


def test_plate_solve_is_str_enum():
    assert AutoGainMode.PLATE_SOLVE == "PLATE_SOLVE"
    assert AutoGainMode.COLLIMATION == "COLLIMATION"
    assert AutoGainMode.AUTOFOCUS == "AUTOFOCUS"


# ── Conversion gain selection for new modes ───────────────────────────────────

def _profile_with_hcg():
    p = MagicMock()
    p.unity_gain_hcg = 200
    p.unity_gain_lcg = 100
    return p


def test_plate_solve_selects_hcg():
    assert _select_conversion_gain(_profile_with_hcg(), AutoGainMode.PLATE_SOLVE) == ConversionGain.HCG


def test_collimation_selects_hcg():
    assert _select_conversion_gain(_profile_with_hcg(), AutoGainMode.COLLIMATION) == ConversionGain.HCG


def test_autofocus_selects_hcg():
    assert _select_conversion_gain(_profile_with_hcg(), AutoGainMode.AUTOFOCUS) == ConversionGain.HCG


def test_planet_selects_lcg():
    assert _select_conversion_gain(_profile_with_hcg(), AutoGainMode.PLANET) == ConversionGain.LCG


def test_moon_selects_lcg():
    assert _select_conversion_gain(_profile_with_hcg(), AutoGainMode.MOON) == ConversionGain.LCG


# ── measure_elongation_ratio ──────────────────────────────────────────────────

def test_round_stars_have_ratio_near_one():
    """Symmetric PSF (equal horizontal and vertical gradients) → ratio ≈ 1.0."""
    np.random.seed(42)
    px = np.random.normal(100, 10, (64, 64)).astype(np.float32)
    ratio = measure_elongation_ratio(px)
    assert 0.5 <= ratio <= 2.0


def test_horizontally_trailed_stars_high_ratio():
    """Stars trailed horizontally → high horizontal gradients → ratio > 2."""
    px = np.zeros((64, 64), dtype=np.float32)
    # Add horizontal streaks only
    for row in [10, 20, 30, 40, 50]:
        px[row, :] = 1000.0
    ratio = measure_elongation_ratio(px)
    assert ratio > 2.0, f"Expected ratio > 2.0 for horizontal trails, got {ratio:.2f}"


def test_vertically_trailed_stars_high_ratio():
    """Stars trailed vertically → high vertical gradients → ratio > 2."""
    px = np.zeros((64, 64), dtype=np.float32)
    for col in [10, 20, 30, 40, 50]:
        px[:, col] = 1000.0
    ratio = measure_elongation_ratio(px)
    assert ratio > 2.0, f"Expected ratio > 2.0 for vertical trails, got {ratio:.2f}"


def test_uniform_image_ratio_near_one():
    """Uniform image → near-zero gradients in both axes → ratio near 1.0."""
    px = np.full((64, 64), 500.0, dtype=np.float32)
    ratio = measure_elongation_ratio(px)
    assert 0.5 <= ratio <= 2.0


# ── PLATE_SOLVE mode: offset forced to zero ───────────────────────────────────

def _make_profile():
    p = MagicMock()
    p.max_gain = 3200
    p.min_preview_exp_ms = 1.0
    p.max_preview_exp_ms = 8000.0
    p.unity_gain_hcg = 200
    p.unity_gain_lcg = 100
    return p


def _make_camera(mean_frac: float = 0.3) -> MagicMock:
    """Return a mock camera whose capture() returns a frame in the target band."""
    bit_depth = 16
    adc_max = (1 << bit_depth) - 1
    target_mean = mean_frac * adc_max
    frame = MagicMock()
    pixels = np.full((64, 64), target_mean, dtype=np.float32)
    frame.pixels = pixels
    frame.header = {"BITDEPTH": 16}

    camera = MagicMock()
    camera.capture = MagicMock(return_value=frame)
    camera.get_logical_name = MagicMock(return_value="main")
    return camera


def test_plate_solve_mode_forces_offset_zero():
    """PLATE_SOLVE mode should set cur_offset=0 regardless of starting conditions."""
    from datetime import datetime, timezone
    from smart_telescope.domain.autogain_service import AutoGainService
    from smart_telescope.domain.last_good_settings import LastGoodSettings

    camera = _make_camera(mean_frac=0.3)
    profile = _make_profile()
    last_good = LastGoodSettings(
        camera_model="TestCam",
        camera_serial="SN001",
        mode="PLATE_SOLVE",
        gain=200,
        exposure_ms=2000.0,
        offset=500,
        conversion_gain="HCG",
        saved_at=datetime.now(timezone.utc).isoformat(),
    )

    result = AutoGainService.run_one_shot(
        camera=camera,
        profile=profile,
        mode=AutoGainMode.PLATE_SOLVE,
        last_good=last_good,
    )
    # Even though last_good.offset = 500, PLATE_SOLVE forces offset=0
    assert result.offset == 0


def test_collimation_mode_accepted():
    """COLLIMATION mode should complete without error."""
    from smart_telescope.domain.autogain_service import AutoGainService

    camera = _make_camera(mean_frac=0.3)
    result = AutoGainService.run_one_shot(
        camera=camera,
        profile=_make_profile(),
        mode=AutoGainMode.COLLIMATION,
    )
    from smart_telescope.domain.autogain_service import AutoGainStatus
    assert result.status == AutoGainStatus.OK


def test_autofocus_mode_accepted():
    """AUTOFOCUS mode should complete without error."""
    from smart_telescope.domain.autogain_service import AutoGainService

    camera = _make_camera(mean_frac=0.3)
    result = AutoGainService.run_one_shot(
        camera=camera,
        profile=_make_profile(),
        mode=AutoGainMode.AUTOFOCUS,
    )
    from smart_telescope.domain.autogain_service import AutoGainStatus
    assert result.status == AutoGainStatus.OK


def test_planet_mode_accepted():
    """PLANET mode should route to planetary signal metric (no crash)."""
    from smart_telescope.domain.autogain_service import AutoGainService

    camera = _make_camera(mean_frac=0.6)  # planet-mode band 0.4–0.8
    result = AutoGainService.run_one_shot(
        camera=camera,
        profile=_make_profile(),
        mode=AutoGainMode.PLANET,
    )
    from smart_telescope.domain.autogain_service import AutoGainStatus
    # Planet mode uses peak_frac from detect_planet — OK or limit reached is acceptable
    assert result.status in (AutoGainStatus.OK, AutoGainStatus.EXPOSURE_LIMIT_REACHED,
                             AutoGainStatus.GAIN_LIMIT_REACHED, AutoGainStatus.NO_SIGNAL,
                             AutoGainStatus.CLIPPING_RISK)


def test_moon_mode_accepted():
    """MOON mode should behave like PLANET (no crash)."""
    from smart_telescope.domain.autogain_service import AutoGainService

    camera = _make_camera(mean_frac=0.6)
    result = AutoGainService.run_one_shot(
        camera=camera,
        profile=_make_profile(),
        mode=AutoGainMode.MOON,
    )
    from smart_telescope.domain.autogain_service import AutoGainStatus
    assert result.status in (AutoGainStatus.OK, AutoGainStatus.EXPOSURE_LIMIT_REACHED,
                             AutoGainStatus.GAIN_LIMIT_REACHED, AutoGainStatus.NO_SIGNAL,
                             AutoGainStatus.CLIPPING_RISK)


def test_plate_solve_caps_on_tracking_blur():
    """PLATE_SOLVE caps exposure when elongation ratio jumps above 2.0 on second+ frame.

    Frame 1: too dark (mean = 5% of ADC) so the loop increments exposure to frame 2.
    Frame 2: same low brightness but with horizontal stripes → high elongation → cap.
    """
    from smart_telescope.domain.autogain_service import AutoGainService

    bit_depth = 16
    adc_max = (1 << bit_depth) - 1
    dark_mean = 0.05 * adc_max  # below band_lo=0.12 → service tries to increase exposure

    # Frame 1: uniformly dark, round (no elongation)
    frame1 = MagicMock()
    frame1.pixels = np.full((64, 64), dark_mean, dtype=np.float32)
    frame1.header = {"BITDEPTH": 16}

    # Frame 2: dark with horizontal stripes → high vertical gradient anisotropy
    # (stripes are at every-other-row → g_y >> g_x)
    frame2 = MagicMock()
    px2 = np.zeros((64, 64), dtype=np.float32)
    for row in range(0, 64, 2):
        px2[row, :] = dark_mean * 4  # alternating rows → strong vertical gradient
    frame2.pixels = px2
    frame2.header = {"BITDEPTH": 16}

    call_count = [0]

    def _capture(exp_s: float):
        call_count[0] += 1
        return frame1 if call_count[0] == 1 else frame2

    camera = MagicMock()
    camera.capture = MagicMock(side_effect=_capture)
    camera.get_logical_name = MagicMock(return_value="main")

    result = AutoGainService.run_one_shot(
        camera=camera,
        profile=_make_profile(),
        mode=AutoGainMode.PLATE_SOLVE,
        max_iterations=4,
    )
    from smart_telescope.domain.autogain_service import AutoGainStatus
    # Should stop at OK with a tracking-quality warning after exactly 2 captures
    assert result.status == AutoGainStatus.OK
    assert result.warning_msg is not None
    assert "elongation" in result.warning_msg.lower() or "capped" in result.warning_msg.lower()
    assert call_count[0] == 2  # stopped after detecting blur on frame 2
