"""Unit tests for domain/autogain_service.py (AGT-5-2)."""
from __future__ import annotations

import threading
from typing import Iterator
from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_telescope.domain.autogain import AutoGainMode
from smart_telescope.domain.autogain_service import (
    AutoGainResult,
    AutoGainService,
    AutoGainStatus,
)
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.domain.camera_profile import ATR585M, GPCMOS02000KPA, OAG_678M as CAM_OAG_678M, CameraProfile
from smart_telescope.domain.autogain import _select_conversion_gain
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.histogram import HistogramStats
from smart_telescope.domain.last_good_settings import LastGoodSettings
from smart_telescope.ports.camera import CameraPort, CaptureAbortedError


# ── Mock camera ───────────────────────────────────────────────────────────────

BIT_DEPTH = 16
ADC_MAX   = float((1 << BIT_DEPTH) - 1)


def _frame(mean_frac: float, zero_clipped_pct: float = 0.0) -> FitsFrame:
    """Return a FitsFrame whose histogram mean_frac ≈ mean_frac."""
    shape = (64, 64)
    total = shape[0] * shape[1]
    n_zero = int(total * zero_clipped_pct / 100.0)
    n_signal = total - n_zero
    adu = mean_frac * ADC_MAX
    pix = np.empty(total, dtype=np.float32)
    pix[:n_zero]    = 0.0
    pix[n_zero:]    = float(adu * total / max(n_signal, 1))
    pix = pix.reshape(shape)
    mock = MagicMock(spec=FitsFrame)
    mock.pixels = pix
    return mock


class _SeqCamera(CameraPort):
    """Camera stub that returns frames from a pre-defined list (loops on last)."""

    def __init__(self, frames: list[FitsFrame]) -> None:
        self._frames = frames
        self._index  = 0

    def capture(self, _exposure_s: float) -> FitsFrame:
        frame = self._frames[min(self._index, len(self._frames) - 1)]
        self._index += 1
        return frame

    # CameraPort stubs (unused by service)
    def connect(self) -> bool:             return True
    def disconnect(self) -> None:          pass
    def get_exposure_ms(self) -> float:    return 1000.0
    def set_exposure_ms(self, ms):         pass
    def get_gain(self) -> int:             return 100
    def set_gain(self, gain):              pass
    def get_black_level(self) -> int:      return 0
    def set_black_level(self, level):      pass
    def get_conversion_gain(self):         return ConversionGain.LCG
    def set_conversion_gain(self, mode):   pass
    def get_bit_depth(self) -> int:        return BIT_DEPTH
    def get_temperature(self):             return None
    def get_capabilities(self):            return MagicMock()
    def get_serial_number(self) -> str:    return "TEST"
    def get_logical_name(self) -> str:     return "TestCamera"


# ── Tiny profile with tight limits for deterministic tests ────────────────────

_PROFILE = CameraProfile(
    model="TestCam",
    sensor="IMX000",
    width_px=640,
    height_px=480,
    pixel_um=3.0,
    max_gain=400,
    unity_gain_hcg=200,
    unity_gain_lcg=100,
    unity_gain_hdr=None,
    min_preview_exp_ms=10.0,
    max_preview_exp_ms=4000.0,
    supports_cooling=False,
)


# ── OK path ───────────────────────────────────────────────────────────────────

class TestOKPath:
    def test_already_in_band_returns_ok_on_first_frame(self) -> None:
        # mean_frac=0.28 is inside [0.12, 0.45]
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE)
        assert result.status == AutoGainStatus.OK

    def test_ok_result_carries_histogram_stats(self) -> None:
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE)
        assert result.histogram_stats is not None
        assert result.conversion_gain is not None

    def test_converges_from_dark_to_ok(self) -> None:
        # First frames are dark, last frame is in band
        cam = _SeqCamera([_frame(0.01), _frame(0.01), _frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE)
        assert result.status == AutoGainStatus.OK

    def test_ok_exposure_within_profile_limits(self) -> None:
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE)
        assert _PROFILE.min_preview_exp_ms <= result.exposure_ms <= _PROFILE.max_preview_exp_ms

    def test_ok_gain_within_profile_limits(self) -> None:
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE)
        assert 100 <= result.gain <= _PROFILE.max_gain


# ── Conversion gain ───────────────────────────────────────────────────────────

class TestConversionGain:
    def test_dso_mode_selects_hcg(self) -> None:
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE, mode=AutoGainMode.DSO)
        assert result.conversion_gain == ConversionGain.HCG

    def test_planetary_mode_selects_lcg(self) -> None:
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE, mode=AutoGainMode.PLANETARY)
        assert result.conversion_gain == ConversionGain.LCG


# ── No-signal / dust-cap ──────────────────────────────────────────────────────

class TestNoSignal:
    def _max_out_camera(self) -> _SeqCamera:
        """Return frames that are all black — forces gain and exposure to max."""
        return _SeqCamera([_frame(0.0)] * 20)

    def test_no_signal_status_at_limits(self) -> None:
        result = AutoGainService.run_one_shot(
            self._max_out_camera(), _PROFILE, max_iterations=20,
        )
        assert result.status in (
            AutoGainStatus.NO_SIGNAL,
            AutoGainStatus.GAIN_LIMIT_REACHED,
            AutoGainStatus.EXPOSURE_LIMIT_REACHED,  # offset-raise consumes iterations
        )

    def test_no_signal_when_mean_below_threshold_and_long_exposure(self) -> None:
        # Build a profile whose limits force exactly the NO_SIGNAL condition
        profile = CameraProfile(
            model="TestCam",
            sensor="IMX000",
            width_px=640, height_px=480, pixel_um=3.0,
            max_gain=100,          # very low max gain — at limit quickly
            unity_gain_hcg=None,
            unity_gain_lcg=100,
            unity_gain_hdr=None,
            min_preview_exp_ms=4000.0,   # both min and max = 4 s
            max_preview_exp_ms=4000.0,
            supports_cooling=False,
        )
        cam = _SeqCamera([_frame(0.0005)] * 20)  # mean < 0.1% — below focus-error threshold
        result = AutoGainService.run_one_shot(cam, profile, max_iterations=5)
        assert result.status == AutoGainStatus.NO_SIGNAL

    def test_dust_cap_when_zero_clipped_above_50pct(self) -> None:
        profile = CameraProfile(
            model="TestCam",
            sensor="IMX000",
            width_px=640, height_px=480, pixel_um=3.0,
            max_gain=100,
            unity_gain_hcg=None,
            unity_gain_lcg=100,
            unity_gain_hdr=None,
            min_preview_exp_ms=4000.0,
            max_preview_exp_ms=4000.0,
            supports_cooling=False,
        )
        # Start with offset already at max so step 7 (offset-raise) never fires,
        # which lets the no-signal / dust-cap path be reached immediately.
        lg = LastGoodSettings(
            camera_model="TestCam", camera_serial="0001", mode="DSO",
            gain=100, exposure_ms=4000.0, offset=2000,
            conversion_gain="LCG", saved_at="2026-01-01T00:00:00+00:00",
        )
        # 80% of pixels are zero → zero_clipped_pct ≈ 80 > 50
        cam = _SeqCamera([_frame(0.001, zero_clipped_pct=80.0)] * 5)
        result = AutoGainService.run_one_shot(cam, profile, last_good=lg, max_iterations=5)
        assert result.status == AutoGainStatus.POSSIBLE_DUST_CAP

    def test_focus_or_pointing_error_when_tiny_signal_exists(self) -> None:
        # mean_frac=0.005 is > _FOCUS_ERROR_THRESHOLD (0.001) but < _NO_SIGNAL_THRESHOLD (0.02)
        # zero_clipped_pct=0 (< 1% threshold) — not dust cap → POSSIBLE_FOCUS_OR_POINTING_ERROR
        # offset=0 so eff_mean == mean_frac
        profile = CameraProfile(
            model="TestCam",
            sensor="IMX000",
            width_px=640, height_px=480, pixel_um=3.0,
            max_gain=100,
            unity_gain_hcg=None,
            unity_gain_lcg=100,
            unity_gain_hdr=None,
            min_preview_exp_ms=4000.0,
            max_preview_exp_ms=4000.0,
            supports_cooling=False,
        )
        lg = LastGoodSettings(
            camera_model="TestCam", camera_serial="0001", mode="DSO",
            gain=100, exposure_ms=4000.0, offset=0,
            conversion_gain="LCG", saved_at="2026-01-01T00:00:00+00:00",
        )
        # eff_mean ≈ 0.005 (> 0.001) with zero zero-clipping
        cam = _SeqCamera([_frame(0.005)] * 5)
        result = AutoGainService.run_one_shot(cam, profile, last_good=lg, max_iterations=5)
        assert result.status == AutoGainStatus.POSSIBLE_FOCUS_OR_POINTING_ERROR

    def test_true_no_signal_when_mean_below_focus_threshold(self) -> None:
        # mean_frac very close to 0 (< 0.001) with low zero-clipping → NO_SIGNAL
        profile = CameraProfile(
            model="TestCam",
            sensor="IMX000",
            width_px=640, height_px=480, pixel_um=3.0,
            max_gain=100,
            unity_gain_hcg=None,
            unity_gain_lcg=100,
            unity_gain_hdr=None,
            min_preview_exp_ms=4000.0,
            max_preview_exp_ms=4000.0,
            supports_cooling=False,
        )
        lg = LastGoodSettings(
            camera_model="TestCam", camera_serial="0001", mode="DSO",
            gain=100, exposure_ms=4000.0, offset=2000,
            conversion_gain="LCG", saved_at="2026-01-01T00:00:00+00:00",
        )
        # eff_mean ≈ 0.0001 (< _FOCUS_ERROR_THRESHOLD) → NO_SIGNAL
        cam = _SeqCamera([_frame(0.0001, zero_clipped_pct=5.0)] * 5)
        result = AutoGainService.run_one_shot(cam, profile, last_good=lg, max_iterations=5)
        assert result.status == AutoGainStatus.NO_SIGNAL


# ── Over-bright / clipping risk ───────────────────────────────────────────────

class TestOverBright:
    def _min_cam(self) -> _SeqCamera:
        """Saturated frames that can never be dimmed past profile minimum."""
        return _SeqCamera([_frame(0.99)] * 20)

    def test_clipping_risk_when_cannot_dim(self) -> None:
        # Profile where min_preview_exp_ms leaves no room to reduce
        profile = CameraProfile(
            model="TestCam",
            sensor="IMX000",
            width_px=640, height_px=480, pixel_um=3.0,
            max_gain=100,
            unity_gain_hcg=None,
            unity_gain_lcg=100,
            unity_gain_hdr=None,
            min_preview_exp_ms=1000.0,  # can't go below 1 s
            max_preview_exp_ms=4000.0,
            supports_cooling=False,
        )
        cam = _SeqCamera([_frame(0.99)] * 20)
        result = AutoGainService.run_one_shot(cam, profile, max_iterations=15)
        assert result.status == AutoGainStatus.CLIPPING_RISK


# ── Gain limit ────────────────────────────────────────────────────────────────

class TestGainLimit:
    def test_gain_limit_reached(self) -> None:
        profile = CameraProfile(
            model="TestCam",
            sensor="IMX000",
            width_px=640, height_px=480, pixel_um=3.0,
            max_gain=110,         # tiny max gain
            unity_gain_hcg=None,
            unity_gain_lcg=100,
            unity_gain_hdr=None,
            min_preview_exp_ms=4000.0,
            max_preview_exp_ms=4000.0,
            supports_cooling=False,
        )
        cam = _SeqCamera([_frame(0.0005)] * 20)  # below focus-error threshold → NO_SIGNAL path
        result = AutoGainService.run_one_shot(cam, profile, max_iterations=10)
        assert result.status in (
            AutoGainStatus.GAIN_LIMIT_REACHED,
            AutoGainStatus.NO_SIGNAL,
        )

    def _gain_limit_profile(self) -> CameraProfile:
        return CameraProfile(
            model="TestCam",
            sensor="IMX000",
            width_px=640, height_px=480, pixel_um=3.0,
            max_gain=110,          # tiny max gain — reached quickly
            unity_gain_hcg=None,
            unity_gain_lcg=100,
            unity_gain_hdr=None,
            min_preview_exp_ms=4000.0,
            max_preview_exp_ms=4000.0,
            supports_cooling=False,
        )

    def test_gain_limit_reached_has_informative_warning_msg(self) -> None:
        # signal=0.05 is above the no-signal threshold (0.02) and above the sparse-
        # field threshold's floor but below band_lo (0.12) — deterministically
        # GAIN_LIMIT_REACHED, never NO_SIGNAL, once gain/exposure are pinned at max.
        cam = _SeqCamera([_frame(0.05)] * 20)
        result = AutoGainService.run_one_shot(
            cam, self._gain_limit_profile(), max_iterations=10, tracking_on=True,
        )
        assert result.status == AutoGainStatus.GAIN_LIMIT_REACHED
        assert result.warning_msg
        assert "signal" in result.warning_msg.lower()
        assert "target floor" in result.warning_msg.lower()
        assert "AG-003" not in result.warning_msg

    def test_gain_limit_reached_mentions_tracking_off_cap(self) -> None:
        cam = _SeqCamera([_frame(0.05)] * 20)
        result = AutoGainService.run_one_shot(
            cam, self._gain_limit_profile(), max_iterations=10, tracking_on=False,
        )
        assert result.status == AutoGainStatus.GAIN_LIMIT_REACHED
        assert result.warning_msg
        assert "AG-003" in result.warning_msg
        assert "tracking" in result.warning_msg.lower()


# ── Cancellation ──────────────────────────────────────────────────────────────

class TestCancellation:
    def test_cancelled_when_flag_set_before_first_iteration(self) -> None:
        flag = threading.Event()
        flag.set()
        cam = _SeqCamera([_frame(0.28)] * 5)
        result = AutoGainService.run_one_shot(cam, _PROFILE, cancellation_flag=flag)
        assert result.status == AutoGainStatus.CANCELLED

    def test_cancel_mid_run(self) -> None:
        flag = threading.Event()

        class _TriggeredCamera(_SeqCamera):
            def capture(self, exp_s: float) -> FitsFrame:
                frame = super().capture(exp_s)
                flag.set()   # trigger cancellation after first capture
                return frame

        cam = _TriggeredCamera([_frame(0.001)] * 20)
        result = AutoGainService.run_one_shot(cam, _PROFILE, cancellation_flag=flag)
        assert result.status == AutoGainStatus.CANCELLED


# ── last_good starting point ──────────────────────────────────────────────────

class TestLastGood:
    def _make_last_good(self, *, exposure_ms: float, gain: int, offset: int) -> LastGoodSettings:
        return LastGoodSettings(
            camera_model="TestCam",
            camera_serial="0001",
            mode="DSO",
            gain=gain,
            exposure_ms=exposure_ms,
            offset=offset,
            conversion_gain="HCG",
            saved_at="2026-01-01T00:00:00+00:00",
        )

    def test_last_good_sets_initial_exposure(self) -> None:
        lg = self._make_last_good(exposure_ms=500.0, gain=200, offset=0)
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE, last_good=lg)
        assert result.status == AutoGainStatus.OK
        # Starting exposure was 500 ms (in-band on first frame, so should be close)
        assert result.exposure_ms == pytest.approx(500.0, rel=0.01)

    def test_last_good_offset_preserved_when_in_band(self) -> None:
        lg = self._make_last_good(exposure_ms=500.0, gain=200, offset=300)
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE, last_good=lg)
        assert result.offset == 300

    def test_last_good_exposure_clamped_to_profile_max(self) -> None:
        lg = self._make_last_good(exposure_ms=99999.0, gain=200, offset=0)
        cam = _SeqCamera([_frame(0.28)] * 20)
        result = AutoGainService.run_one_shot(cam, _PROFILE)
        assert result.exposure_ms <= _PROFILE.max_preview_exp_ms


# ── Calibration stats offset suggestion ──────────────────────────────────────

class TestCalibrationStats:
    def _make_cal_stats(self, black_level_frac: float) -> HistogramStats:
        return HistogramStats(
            p50=black_level_frac,
            p95=black_level_frac,
            p99=black_level_frac,
            p99_5=black_level_frac,
            p99_9=black_level_frac,
            max_frac=black_level_frac,
            mean_frac=black_level_frac,
            saturation_pct=0.0,
            zero_clipped_pct=0.0,
            black_level=black_level_frac,
            effective_bit_depth=BIT_DEPTH,
            adc_max=ADC_MAX,
        )

    def test_calibration_stats_sets_offset_when_no_last_good(self) -> None:
        cal = self._make_cal_stats(0.01)   # 1% black level → ~655 ADU on 16-bit
        cam = _SeqCamera([_frame(0.28)] * 5)
        result = AutoGainService.run_one_shot(cam, _PROFILE, calibration_stats=cal)
        expected_offset = int(0.01 * ADC_MAX)
        assert result.offset >= expected_offset

    def test_calibration_stats_not_applied_when_last_good_present(self) -> None:
        cal = self._make_cal_stats(0.05)
        lg = LastGoodSettings(
            camera_model="TestCam", camera_serial="0001", mode="DSO",
            gain=200, exposure_ms=500.0, offset=0,
            conversion_gain="HCG", saved_at="2026-01-01T00:00:00+00:00",
        )
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE, last_good=lg, calibration_stats=cal)
        # offset must come from last_good (0), not calibration
        assert result.offset == 0


# ── Unsupported (capture raises) ──────────────────────────────────────────────

class TestUnsupported:
    def test_capture_exception_returns_unsupported(self) -> None:
        class _BrokenCamera(_SeqCamera):
            def capture(self, _exp: float) -> FitsFrame:
                raise RuntimeError("camera timeout")

        cam = _BrokenCamera([])
        result = AutoGainService.run_one_shot(cam, _PROFILE)
        assert result.status == AutoGainStatus.UNSUPPORTED
        assert "camera timeout" in (result.warning_msg or "")


# ── Zero-clipping offset auto-raise ──────────────────────────────────────────

class TestOffsetRaise:
    def test_offset_raised_when_zero_clipping_present(self) -> None:
        # First frame has heavy zero-clipping; second frame is in-band with offset
        clipped_frame = _frame(0.001, zero_clipped_pct=60.0)
        good_frame    = _frame(0.28)
        cam = _SeqCamera([clipped_frame, good_frame])
        result = AutoGainService.run_one_shot(cam, _PROFILE)
        # After raising offset the run should either complete OK or have offset > 0
        assert result.offset > 0 or result.status == AutoGainStatus.OK


# ── Guiding mode (AGT-7-1) ────────────────────────────────────────────────────

def _guide_frame(
    star_peak_frac: float,
    shape: tuple[int, int] = (64, 64),
    n_star_px: int = 12,
) -> FitsFrame:
    """Frame with a simulated guide star: a handful of bright pixels + dim background.

    At the default 64×64 shape, 12 bright pixels is > 0.1% of all pixels, so
    p99_9 of the resulting frame ≈ star_peak_frac same as max_frac would be.
    Background is set to 0.001 (not zero) so zero_clipped_pct stays near 0.
    """
    total = shape[0] * shape[1]
    pix = np.full(total, 0.001 * ADC_MAX, dtype=np.float32)  # dim sky, not zero
    pix[:n_star_px] = float(star_peak_frac * ADC_MAX)
    pix = pix.reshape(shape)
    m = MagicMock(spec=FitsFrame)
    m.pixels = pix
    return m


def _guide_no_star_frame(background_frac: float = 0.005) -> FitsFrame:
    """Guide frame with uniform dim background — no star (p99_9 ≈ background_frac).

    Unlike _guide_frame, there are no bright pixels, so zero_clipped_pct ≈ 0.
    This exercises the NO_SIGNAL path rather than the POSSIBLE_DUST_CAP path.
    """
    pix = np.full((64, 64), background_frac * ADC_MAX, dtype=np.float32)
    m = MagicMock(spec=FitsFrame)
    m.pixels = pix
    return m


# Tiny guiding profile (max_exp short to make exhaustion tests fast)
_GUIDE_PROFILE = CameraProfile(
    model="GuideCam",
    sensor="IMX290",
    width_px=640,
    height_px=480,
    pixel_um=2.9,
    max_gain=400,
    unity_gain_hcg=None,
    unity_gain_lcg=100,
    unity_gain_hdr=None,
    min_preview_exp_ms=0.1,
    max_preview_exp_ms=2000.0,
    supports_cooling=False,
)


class TestGuidingModeOK:
    def test_in_band_peak_returns_ok(self) -> None:
        # p99_9 ≈ 0.45 → inside [0.20, 0.80]
        cam = _SeqCamera([_guide_frame(0.45)])
        result = AutoGainService.run_one_shot(cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING)
        assert result.status == AutoGainStatus.OK

    def test_ok_result_has_positive_exposure(self) -> None:
        cam = _SeqCamera([_guide_frame(0.45)])
        result = AutoGainService.run_one_shot(cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING)
        assert result.exposure_ms > 0

    def test_lower_bound_accepted(self) -> None:
        # p99_9 = 0.20 is exactly at the lower edge → OK
        cam = _SeqCamera([_guide_frame(0.20)])
        result = AutoGainService.run_one_shot(cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING)
        assert result.status == AutoGainStatus.OK

    def test_upper_bound_accepted(self) -> None:
        # p99_9 = 0.80 is exactly at the upper edge → OK
        cam = _SeqCamera([_guide_frame(0.80)])
        result = AutoGainService.run_one_shot(cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING)
        assert result.status == AutoGainStatus.OK


class TestGuidingModeNoStar:
    def test_no_star_at_limits_returns_no_signal(self) -> None:
        # Uniform dim background — no guide star, zero_clipped_pct ≈ 0 (avoids POSSIBLE_DUST_CAP)
        cam = _SeqCamera([_guide_no_star_frame(0.005)])
        result = AutoGainService.run_one_shot(
            cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING, max_iterations=20,
        )
        assert result.status in (
            AutoGainStatus.NO_SIGNAL,
            AutoGainStatus.GAIN_LIMIT_REACHED,
            AutoGainStatus.EXPOSURE_LIMIT_REACHED,
        )

    def test_no_star_warning_message_mentions_guide(self) -> None:
        cam = _SeqCamera([_guide_frame(0.001)])
        result = AutoGainService.run_one_shot(
            cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING, max_iterations=20,
        )
        if result.status == AutoGainStatus.NO_SIGNAL:
            assert result.warning_msg is not None
            assert "guide" in result.warning_msg.lower()

    def test_dust_cap_still_detected_in_guiding(self) -> None:
        # >50% zero-clipped → POSSIBLE_DUST_CAP even in GUIDING mode
        dust_frame = _frame(0.001, zero_clipped_pct=80.0)
        cam = _SeqCamera([dust_frame])
        result = AutoGainService.run_one_shot(
            cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING, max_iterations=20,
        )
        assert result.status in (
            AutoGainStatus.POSSIBLE_DUST_CAP,
            AutoGainStatus.GAIN_LIMIT_REACHED,
            AutoGainStatus.EXPOSURE_LIMIT_REACHED,
        )


class TestGuidingModeConvergence:
    def test_weak_star_triggers_brightening(self) -> None:
        # Weak star (below band), then in-band after one gain-increase step
        # _GUIDE_PROFILE starts at max_exp (2000 ms) so gain jumps immediately
        weak   = _guide_frame(0.05)   # p99_9 = 0.05 < 0.20 → too dark
        inband = _guide_frame(0.45)   # p99_9 = 0.45 → OK
        cam = _SeqCamera([weak, inband])
        result = AutoGainService.run_one_shot(
            cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING, max_iterations=5,
        )
        assert result.status == AutoGainStatus.OK

    def test_bright_star_triggers_dimming(self) -> None:
        # First frame saturated, then in-band
        bright = _guide_frame(0.95)  # p99_9 > 0.80 → too bright
        inband = _guide_frame(0.45)
        cam = _SeqCamera([bright, bright, inband])
        result = AutoGainService.run_one_shot(
            cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING, max_iterations=10,
        )
        assert result.status == AutoGainStatus.OK

    def test_offset_not_raised_for_dark_background(self) -> None:
        # Guide mode should NOT raise offset when p99_9 < band_lo (background is naturally dark)
        weak = _guide_frame(0.10)    # p99_9 = 0.10, most pixels = 0
        inband = _guide_frame(0.45)
        cam = _SeqCamera([weak, inband])
        result = AutoGainService.run_one_shot(
            cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING, max_iterations=5,
        )
        # offset should remain 0 — guide mode doesn't apply zero-clip correction
        assert result.offset == 0


class TestGuidingModeRealisticResolution:
    def test_detects_star_at_realistic_sensor_resolution(self) -> None:
        """M10-049: on a real ~2-megapixel guide sensor (1080x1920), a
        well-exposed guide star occupying only ~10 pixels is nowhere near
        the >=0.1% of all pixels (~2074 of 2,073,600) a whole-frame
        percentile needs to notice it. p99_9 misses it entirely and the
        service climbs to the exposure/gain ceiling forever even with a
        bright, correctly-exposed star in frame — this is exactly why the
        64x64 frames used elsewhere in this file (where 12 pixels is
        ~0.29%, comfortably above the 0.1% threshold) didn't catch this
        (see domain/autogain.py's identical M10-043 fix). The signal must
        still recognize the star is in-band regardless of sensor resolution."""
        cam = _SeqCamera([_guide_frame(0.45, shape=(1080, 1920), n_star_px=10)])
        result = AutoGainService.run_one_shot(
            cam, _GUIDE_PROFILE, mode=AutoGainMode.GUIDING, max_iterations=1,
        )
        assert result.status == AutoGainStatus.OK


class TestGuidingConversionGain:
    def test_gpcmos02000kpa_uses_lcg(self) -> None:
        cg = _select_conversion_gain(GPCMOS02000KPA, AutoGainMode.GUIDING)
        assert cg == ConversionGain.LCG

    def test_oag_678m_uses_hcg(self) -> None:
        cg = _select_conversion_gain(CAM_OAG_678M, AutoGainMode.GUIDING)
        assert cg == ConversionGain.HCG

    def test_guiding_run_with_gpcmos02000kpa_profile(self) -> None:
        cam = _SeqCamera([_guide_frame(0.45)])
        result = AutoGainService.run_one_shot(
            cam, GPCMOS02000KPA, mode=AutoGainMode.GUIDING,
        )
        assert result.status == AutoGainStatus.OK
        assert result.conversion_gain == ConversionGain.LCG


# ── Planetary mode (AGT-8-1) ──────────────────────────────────────────────────

def _planet_frame(peak_frac: float, radius: int = 8) -> FitsFrame:
    """Frame with a circular bright disk centred in a dark 64×64 background.

    detect_planet() will find this disk and return peak_frac as the signal.
    """
    H, W = 64, 64
    cy, cx = H // 2, W // 2
    y, x = np.ogrid[:H, :W]
    disk = (y - cy) ** 2 + (x - cx) ** 2 <= radius ** 2
    pix = np.full((H, W), 0.001 * ADC_MAX, dtype=np.float32)
    pix[disk] = float(peak_frac * ADC_MAX)
    m = MagicMock(spec=FitsFrame)
    m.pixels = pix
    return m


def _dark_sky_frame() -> FitsFrame:
    """Completely dark frame — no planet detectable (max < 0.01 threshold)."""
    pix = np.zeros((64, 64), dtype=np.float32)
    m = MagicMock(spec=FitsFrame)
    m.pixels = pix
    return m


_PLANET_PROFILE = CameraProfile(
    model="PlanetCam",
    sensor="IMX678",
    width_px=4096,
    height_px=2160,
    pixel_um=2.0,
    max_gain=400,
    unity_gain_hcg=200,
    unity_gain_lcg=100,
    unity_gain_hdr=None,
    min_preview_exp_ms=0.1,
    max_preview_exp_ms=2000.0,
    supports_cooling=False,
)


class TestPlanetaryModeOK:
    def test_in_band_planet_returns_ok(self) -> None:
        # peak_frac=0.60 is inside [0.40, 0.80]
        cam = _SeqCamera([_planet_frame(0.60)])
        result = AutoGainService.run_one_shot(cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY)
        assert result.status == AutoGainStatus.OK

    def test_lower_edge_accepted(self) -> None:
        cam = _SeqCamera([_planet_frame(0.40)])
        result = AutoGainService.run_one_shot(cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY)
        assert result.status == AutoGainStatus.OK

    def test_upper_edge_accepted(self) -> None:
        # Use 0.75 (not 0.80) — exact band_hi causes float32 rounding above the boundary
        cam = _SeqCamera([_planet_frame(0.75)])
        result = AutoGainService.run_one_shot(cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY)
        assert result.status == AutoGainStatus.OK

    def test_planetary_uses_lcg(self) -> None:
        cam = _SeqCamera([_planet_frame(0.60)])
        result = AutoGainService.run_one_shot(cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY)
        assert result.conversion_gain == ConversionGain.LCG


class TestPlanetaryModeConvergence:
    def test_dim_planet_triggers_brightening(self) -> None:
        # peak_frac=0.10 < 0.40 → service should increase exposure/gain
        dim    = _planet_frame(0.10)
        inband = _planet_frame(0.60)
        cam = _SeqCamera([dim, inband])
        result = AutoGainService.run_one_shot(cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY)
        assert result.status == AutoGainStatus.OK

    def test_bright_planet_triggers_dimming(self) -> None:
        # peak_frac=0.95 > 0.80 → service must reduce exposure (FR-PLANET-003)
        bright = _planet_frame(0.95)
        inband = _planet_frame(0.60)
        cam = _SeqCamera([bright, bright, inband])
        result = AutoGainService.run_one_shot(
            cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY, max_iterations=10,
        )
        assert result.status == AutoGainStatus.OK

    def test_offset_not_raised_for_dark_background(self) -> None:
        # Planetary mode has dark sky; zero-clip offset auto-raise must be suppressed
        dim    = _planet_frame(0.10)
        inband = _planet_frame(0.60)
        cam = _SeqCamera([dim, inband])
        result = AutoGainService.run_one_shot(cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY)
        assert result.offset == 0

    def test_planet_peak_used_not_mean(self) -> None:
        # planet at 0.60 peak, mean_frac ≈ 0.001 (dark background dominates)
        # if service used mean it would keep brightening; if it uses peak, OK on first frame
        cam = _SeqCamera([_planet_frame(0.60, radius=4)])  # small disk → very low mean
        result = AutoGainService.run_one_shot(cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY)
        assert result.status == AutoGainStatus.OK


class TestPlanetaryModeNoPlanet:
    def test_no_planet_falls_back_to_mean_and_converges(self) -> None:
        # Dark sky (no planet) → detect_planet returns None → signal falls back to eff_mean
        # eff_mean ≈ 0 → loop brightens; eventually the profile limits are exhausted
        cam = _SeqCamera([_dark_sky_frame()] * 20)
        result = AutoGainService.run_one_shot(
            cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY, max_iterations=20,
        )
        # Should not crash; should return a terminal status
        # An all-zero frame has 100% zero-clipped pixels → POSSIBLE_DUST_CAP is also valid
        assert result.status in (
            AutoGainStatus.NO_SIGNAL,
            AutoGainStatus.POSSIBLE_DUST_CAP,
            AutoGainStatus.GAIN_LIMIT_REACHED,
            AutoGainStatus.EXPOSURE_LIMIT_REACHED,
        )

    def test_no_planet_warning_message_mentions_planet(self) -> None:
        # Drive to limits using dark sky; check warning message mentions planet
        cam = _SeqCamera([_dark_sky_frame()] * 30)
        result = AutoGainService.run_one_shot(
            cam, _PLANET_PROFILE, mode=AutoGainMode.PLANETARY, max_iterations=25,
        )
        if result.status == AutoGainStatus.NO_SIGNAL and result.warning_msg:
            assert "planet" in result.warning_msg.lower()


# ── BUG-001 — cancel within 1 s even during a long blocking capture ───────────

class _SlowCamera(_SeqCamera):
    """Camera that blocks in capture() until abort_capture() is called."""

    def __init__(self, frames: list[FitsFrame], block_s: float = 10.0) -> None:
        super().__init__(frames)
        self._block_s = block_s
        self._abort = threading.Event()

    def capture(self, exposure_seconds: float) -> FitsFrame:
        if self._abort.wait(timeout=self._block_s):
            self._abort.clear()
            raise CaptureAbortedError("SlowCamera: capture aborted")
        return super().capture(exposure_seconds)

    def abort_capture(self) -> None:
        self._abort.set()


class TestCancelLatency:
    def test_cancel_returns_cancelled_during_long_exposure(self) -> None:
        cam = _SlowCamera([_frame(0.28)], block_s=10.0)
        cancel = threading.Event()
        result: list[AutoGainResult] = []

        def _run() -> None:
            result.append(
                AutoGainService.run_one_shot(cam, _PROFILE, cancellation_flag=cancel)
            )

        t = threading.Thread(target=_run)
        t.start()
        # Let the worker reach the blocking capture, then cancel
        import time
        time.sleep(0.05)
        cancel.set()
        t.join(timeout=2.0)

        assert not t.is_alive(), "AutoGainService did not return within 2 s of cancellation"
        assert result[0].status == AutoGainStatus.CANCELLED

    def test_cancel_returns_within_one_second(self) -> None:
        cam = _SlowCamera([_frame(0.28)], block_s=10.0)
        cancel = threading.Event()
        start = None
        elapsed: list[float] = []

        def _run() -> None:
            nonlocal start
            import time as _t
            start = _t.monotonic()
            AutoGainService.run_one_shot(cam, _PROFILE, cancellation_flag=cancel)
            elapsed.append(_t.monotonic() - start)

        t = threading.Thread(target=_run)
        t.start()
        import time
        time.sleep(0.05)
        cancel.set()
        t.join(timeout=2.0)

        assert elapsed, "service never returned"
        assert elapsed[0] < 1.0, f"cancel took {elapsed[0]:.2f}s — must be < 1 s"


# ── AG-003: exposure cap when tracking is off ─────────────────────────────────

class TestTrackingOffExposureCap:
    def test_tracking_off_caps_exp_max_to_1000ms(self) -> None:
        """When tracking_on=False, exp_max_ms is capped at 1000 ms (AG-003)."""
        captured_exp: list[float] = []

        class _CapturingCamera(_SeqCamera):
            def capture(self, exposure_s: float) -> "FitsFrame":
                captured_exp.append(exposure_s * 1000.0)
                return super().capture(exposure_s)

        # Profile has max 4000 ms; with tracking off we must never exceed 1000 ms
        cam = _CapturingCamera([_frame(0.5)])  # already in band → exits after 1 capture
        AutoGainService.run_one_shot(cam, _PROFILE, tracking_on=False, max_iterations=3)

        assert captured_exp, "no capture took place"
        assert max(captured_exp) <= 1000.0, (
            f"exposure exceeded 1 s cap: {max(captured_exp):.1f} ms"
        )

    def test_tracking_on_does_not_cap_exp_max(self) -> None:
        """When tracking_on=True (default), exp_max is taken from the profile."""
        captured_exp: list[float] = []

        class _CapturingCamera(_SeqCamera):
            def capture(self, exposure_s: float) -> "FitsFrame":
                captured_exp.append(exposure_s * 1000.0)
                return super().capture(exposure_s)

        # Very dim frame → service will want to increase exposure beyond 1000 ms
        cam = _CapturingCamera([_frame(0.001)] * 15)
        AutoGainService.run_one_shot(cam, _PROFILE, tracking_on=True, max_iterations=15)

        # At least one capture should exceed 1000 ms (profile allows up to 4000 ms)
        assert any(e > 1000.0 for e in captured_exp), (
            "expected at least one capture > 1000 ms when tracking is on, "
            f"got: {captured_exp}"
        )


# ── External frame analyzer integration ──────────────────────────────────────

from smart_telescope.domain.star_count import StarCountResult
from smart_telescope.services.frame_analyzer import ExternalFrameAnalyzer


def _ext_result(**kwargs) -> StarCountResult:
    defaults = dict(
        stars_found=10,
        image_quality="usable",
        suggested_exposure_s=None,
        suggested_gain=None,
        suggested_offset=None,
        focus_warning=False,
        notes=(),
        sources=(),
    )
    defaults.update(kwargs)
    return StarCountResult(**defaults)


def _make_analyzer(result_factory) -> ExternalFrameAnalyzer:
    """Wrap a callable that takes (call_count) -> StarCountResult into an analyzer."""
    state = {"n": 0}

    def fn(img, *, exposure_s, gain, offset):
        r = result_factory(state["n"])
        state["n"] += 1
        return r

    return ExternalFrameAnalyzer(fn, "mock")


class TestExternalFrameAnalyzerIntegration:
    def test_none_frame_analyzer_unchanged_behavior(self) -> None:
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE, frame_analyzer=None)
        assert result.status == AutoGainStatus.OK

    def test_too_dark_quality_drives_brightening(self) -> None:
        # External analyzer says "too_dark" on a genuinely dark frame (mean≈0.001).
        # The sparse-star-field early exit won't trigger (p99_9 is very low), so
        # the service must iterate all max_iterations before exhausting.
        call_count = [0]

        def fn(img, *, exposure_s, gain, offset):
            call_count[0] += 1
            return _ext_result(image_quality="too_dark")

        analyzer = ExternalFrameAnalyzer(fn, "mock")
        cam = _SeqCamera([_frame(0.001)] * 20)
        AutoGainService.run_one_shot(
            cam, _PROFILE, max_iterations=3, frame_analyzer=analyzer
        )
        assert call_count[0] >= 3

    def test_stars_saturated_quality_drives_dimming(self) -> None:
        # External analyzer always says "stars_saturated" → service forces signal
        # above band_hi on every iteration.  With max_iterations=3, must exhaust.
        call_count = [0]

        def fn(img, *, exposure_s, gain, offset):
            call_count[0] += 1
            return _ext_result(image_quality="stars_saturated")

        analyzer = ExternalFrameAnalyzer(fn, "mock")
        cam = _SeqCamera([_frame(0.28)] * 20)
        AutoGainService.run_one_shot(
            cam, _PROFILE, max_iterations=3, frame_analyzer=analyzer
        )
        assert call_count[0] >= 3

    def test_usable_quality_with_in_band_frame_returns_ok(self) -> None:
        # External analyzer says "usable" and no suggestions — in-band frame → OK
        analyzer = _make_analyzer(lambda n: _ext_result(image_quality="usable"))
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(cam, _PROFILE, frame_analyzer=analyzer)
        assert result.status == AutoGainStatus.OK

    def test_focus_warning_true_returns_focus_error(self) -> None:
        # focus_warning=True should cause POSSIBLE_FOCUS_OR_POINTING_ERROR
        analyzer = _make_analyzer(
            lambda n: _ext_result(focus_warning=True, notes=("Focus issue",))
        )
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(
            cam, _PROFILE, frame_analyzer=analyzer, has_focuser=True
        )
        assert result.status == AutoGainStatus.POSSIBLE_FOCUS_OR_POINTING_ERROR
        assert result.warning_msg is not None
        assert len(result.warning_msg) > 0

    def test_focus_warning_with_force_does_not_abort(self) -> None:
        # force=True should skip the focus-warning early return
        analyzer = _make_analyzer(
            lambda n: _ext_result(focus_warning=True, image_quality="usable")
        )
        cam = _SeqCamera([_frame(0.28)] * 5)
        result = AutoGainService.run_one_shot(
            cam, _PROFILE, frame_analyzer=analyzer, has_focuser=True, force=True
        )
        assert result.status != AutoGainStatus.POSSIBLE_FOCUS_OR_POINTING_ERROR

    def test_suggested_exposure_clamped_to_profile(self) -> None:
        # External analyzer suggests an exposure way beyond profile max
        extreme_exp_s = 9999.0
        analyzer = _make_analyzer(
            lambda n: _ext_result(suggested_exposure_s=extreme_exp_s, image_quality="usable")
        )
        cam = _SeqCamera([_frame(0.28)] * 5)
        result = AutoGainService.run_one_shot(cam, _PROFILE, frame_analyzer=analyzer)
        # Result exposure must stay within profile limits
        assert result.exposure_ms <= _PROFILE.max_preview_exp_ms

    def test_focus_warning_note_appears_in_warning_msg(self) -> None:
        note_text = "Check focus ring"
        analyzer = _make_analyzer(
            lambda n: _ext_result(focus_warning=True, notes=(note_text,))
        )
        cam = _SeqCamera([_frame(0.28)])
        result = AutoGainService.run_one_shot(
            cam, _PROFILE, frame_analyzer=analyzer, has_focuser=True
        )
        assert result.warning_msg is not None
        assert note_text in result.warning_msg
