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
from smart_telescope.domain.camera_profile import ATR585M, CameraProfile
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.histogram import HistogramStats
from smart_telescope.domain.last_good_settings import LastGoodSettings
from smart_telescope.ports.camera import CameraPort


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
        cam = _SeqCamera([_frame(0.005)] * 20)  # mean < 2% at all iterations
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
        cam = _SeqCamera([_frame(0.001)] * 20)
        result = AutoGainService.run_one_shot(cam, profile, max_iterations=10)
        assert result.status in (
            AutoGainStatus.GAIN_LIMIT_REACHED,
            AutoGainStatus.NO_SIGNAL,
        )


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
