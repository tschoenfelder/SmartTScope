"""Unit tests for domain/guide_monitor.py (AGT-7-2)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import numpy as np
import pytest

from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.domain.camera_profile import GPCMOS02000KPA
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.domain.guide_monitor import (
    GuideMonitor,
    GuideMonitorConfig,
    GuideMonitorStatus,
)
from smart_telescope.ports.camera import CameraPort

BIT_DEPTH = 16
ADC_MAX   = float((1 << BIT_DEPTH) - 1)


# ── Frame helpers ─────────────────────────────────────────────────────────────

def _guide_frame(star_peak_frac: float, background_frac: float = 0.001) -> FitsFrame:
    """Guide frame: 12 bright star pixels + uniform dim background.

    p99_9 ≈ star_peak_frac, p50 ≈ background_frac.
    """
    total = 64 * 64
    pix   = np.full(total, background_frac * ADC_MAX, dtype=np.float32)
    pix[:12] = float(star_peak_frac * ADC_MAX)
    m = MagicMock(spec=FitsFrame)
    m.pixels = pix.reshape((64, 64))
    return m


def _uniform_frame(mean_frac: float) -> FitsFrame:
    """Uniform frame — p99_9 ≈ p50 ≈ mean_frac."""
    pix = np.full((64, 64), mean_frac * ADC_MAX, dtype=np.float32)
    m = MagicMock(spec=FitsFrame)
    m.pixels = pix
    return m


# ── Camera stub ───────────────────────────────────────────────────────────────

class _FakeCamera(CameraPort):
    """Camera that returns frames from a queue; falls back to last on exhaustion."""

    def __init__(self, frames: list[FitsFrame], *, exp_ms: float = 2000.0, gain: int = 100) -> None:
        self._frames   = frames
        self._index    = 0
        self._exp_ms   = exp_ms
        self._gain     = gain

    def capture(self, _exp_s: float) -> FitsFrame:
        frame = self._frames[min(self._index, len(self._frames) - 1)]
        self._index += 1
        return frame

    def connect(self) -> bool:             return True
    def disconnect(self) -> None:          pass
    def get_exposure_ms(self) -> float:    return self._exp_ms
    def set_exposure_ms(self, ms) -> None: self._exp_ms = ms
    def get_gain(self) -> int:             return self._gain
    def set_gain(self, g) -> None:         self._gain = g
    def get_black_level(self) -> int:      return 0
    def set_black_level(self, l) -> None:  pass
    def get_conversion_gain(self):         return ConversionGain.LCG
    def set_conversion_gain(self, m):      pass
    def get_bit_depth(self) -> int:        return BIT_DEPTH
    def get_temperature(self):             return None
    def get_capabilities(self):            return MagicMock()
    def get_serial_number(self) -> str:    return "FAKE"
    def get_logical_name(self) -> str:     return "FakeGuide"


# ── Check-once helper (avoids threading in unit tests) ────────────────────────

def _check(monitor: GuideMonitor):
    """Run a single monitoring cycle synchronously without spawning a thread."""
    return monitor._check_once()


# ── GUIDE_GAIN_OK path ────────────────────────────────────────────────────────

class TestGuideGainOK:
    def test_in_band_star_returns_ok(self) -> None:
        cam = _FakeCamera([_guide_frame(0.45)])
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        r = _check(mon)
        assert r.status == GuideMonitorStatus.GUIDE_GAIN_OK

    def test_no_settings_change_when_in_band(self) -> None:
        cam = _FakeCamera([_guide_frame(0.45)], exp_ms=500.0, gain=200)
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        mon._cur_exp_ms = 500.0
        mon._cur_gain   = 200
        _check(mon)
        assert mon._cur_exp_ms == pytest.approx(500.0)
        assert mon._cur_gain == 200

    def test_lower_edge_ok(self) -> None:
        # target=0.45, hysteresis=15% → lo = 0.45*0.85 = 0.3825
        cam = _FakeCamera([_guide_frame(0.39)])
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        r = _check(mon)
        assert r.status == GuideMonitorStatus.GUIDE_GAIN_OK

    def test_upper_edge_ok(self) -> None:
        # hi = 0.45*1.15 = 0.5175
        cam = _FakeCamera([_guide_frame(0.51)])
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        r = _check(mon)
        assert r.status == GuideMonitorStatus.GUIDE_GAIN_OK

    def test_p99_9_in_result(self) -> None:
        cam = _FakeCamera([_guide_frame(0.45)])
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        r = _check(mon)
        assert r.p99_9 == pytest.approx(0.45, abs=0.01)

    def test_checked_at_is_set(self) -> None:
        cam = _FakeCamera([_guide_frame(0.45)])
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        r = _check(mon)
        assert r.checked_at is not None
        assert "T" in r.checked_at   # ISO-8601 contains 'T'


# ── STAR_WEAK path ────────────────────────────────────────────────────────────

class TestStarWeak:
    def test_weak_star_triggers_exp_increase(self) -> None:
        # p99_9 = 0.10 < lo = 0.3825 → exposure should increase
        cam = _FakeCamera([_guide_frame(0.10)], exp_ms=500.0)
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        mon._cur_exp_ms = 500.0
        r = _check(mon)
        assert r.status == GuideMonitorStatus.ADJUSTED
        assert mon._cur_exp_ms > 500.0

    def test_exp_increase_bounded_by_max_step(self) -> None:
        cfg = GuideMonitorConfig(max_exp_step_pct=20.0)
        cam = _FakeCamera([_guide_frame(0.10)], exp_ms=500.0)
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        mon._cur_exp_ms = 500.0
        _check(mon)
        assert mon._cur_exp_ms <= 500.0 * 1.20 + 0.1

    def test_gain_increased_when_exp_at_max(self) -> None:
        cam = _FakeCamera([_guide_frame(0.10)], exp_ms=GPCMOS02000KPA.max_preview_exp_ms, gain=100)
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        mon._cur_exp_ms = GPCMOS02000KPA.max_preview_exp_ms
        mon._cur_gain   = 100
        r = _check(mon)
        assert r.status == GuideMonitorStatus.ADJUSTED
        assert mon._cur_gain > 100

    def test_star_weak_returned_when_at_all_limits(self) -> None:
        cam = _FakeCamera([_guide_frame(0.10)],
                          exp_ms=GPCMOS02000KPA.max_preview_exp_ms,
                          gain=GPCMOS02000KPA.max_gain)
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        mon._cur_exp_ms = GPCMOS02000KPA.max_preview_exp_ms
        mon._cur_gain   = GPCMOS02000KPA.max_gain
        r = _check(mon)
        assert r.status == GuideMonitorStatus.STAR_WEAK

    def test_star_weak_message_set(self) -> None:
        cam = _FakeCamera([_guide_frame(0.10)],
                          exp_ms=GPCMOS02000KPA.max_preview_exp_ms,
                          gain=GPCMOS02000KPA.max_gain)
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        mon._cur_exp_ms = GPCMOS02000KPA.max_preview_exp_ms
        mon._cur_gain   = GPCMOS02000KPA.max_gain
        r = _check(mon)
        assert r.warning_msg is not None


# ── STAR_SATURATED path ───────────────────────────────────────────────────────

class TestStarSaturated:
    def test_bright_star_triggers_exp_decrease(self) -> None:
        cam = _FakeCamera([_guide_frame(0.90)], exp_ms=2000.0)
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        mon._cur_exp_ms = 2000.0
        r = _check(mon)
        assert r.status == GuideMonitorStatus.ADJUSTED
        assert mon._cur_exp_ms < 2000.0

    def test_exp_decrease_bounded_by_max_step(self) -> None:
        cfg = GuideMonitorConfig(max_exp_step_pct=20.0)
        cam = _FakeCamera([_guide_frame(0.90)], exp_ms=2000.0)
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        mon._cur_exp_ms = 2000.0
        _check(mon)
        assert mon._cur_exp_ms >= 2000.0 * 0.80 - 0.1

    def test_gain_decreased_when_exp_at_min(self) -> None:
        cam = _FakeCamera([_guide_frame(0.90)], exp_ms=GPCMOS02000KPA.min_preview_exp_ms, gain=300)
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        mon._cur_exp_ms = GPCMOS02000KPA.min_preview_exp_ms
        mon._cur_gain   = 300
        r = _check(mon)
        assert r.status == GuideMonitorStatus.ADJUSTED
        assert mon._cur_gain < 300

    def test_star_saturated_returned_when_at_floor(self) -> None:
        cam = _FakeCamera([_guide_frame(0.90)],
                          exp_ms=GPCMOS02000KPA.min_preview_exp_ms, gain=100)
        mon = GuideMonitor(cam, GPCMOS02000KPA)
        mon._cur_exp_ms = GPCMOS02000KPA.min_preview_exp_ms
        mon._cur_gain   = 100   # _GAIN_MIN
        r = _check(mon)
        assert r.status == GuideMonitorStatus.STAR_SATURATED


# ── Dawn warning path ─────────────────────────────────────────────────────────

class TestDawnWarning:
    def test_rising_background_triggers_dawn_warning(self) -> None:
        # First check: background = 0.01 (sets baseline)
        # Second check: background = 0.015 (+50% > dawn_threshold_pct=20%)
        cfg = GuideMonitorConfig(dawn_threshold_pct=20.0)
        cam = _FakeCamera([
            _guide_frame(0.45, background_frac=0.01),   # baseline
            _guide_frame(0.45, background_frac=0.015),  # risen 50%
        ])
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        _check(mon)                 # sets _initial_p50
        r = _check(mon)            # detects dawn
        assert r.dawn_warning is True

    def test_dawn_warning_status_when_in_band(self) -> None:
        cfg = GuideMonitorConfig(dawn_threshold_pct=20.0)
        cam = _FakeCamera([
            _guide_frame(0.45, background_frac=0.01),
            _guide_frame(0.45, background_frac=0.015),
        ])
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        _check(mon)
        r = _check(mon)
        assert r.status == GuideMonitorStatus.DAWN_WARNING

    def test_dawn_warning_with_adjustment(self) -> None:
        cfg = GuideMonitorConfig(dawn_threshold_pct=20.0)
        cam = _FakeCamera([
            _guide_frame(0.45, background_frac=0.01),   # baseline
            _guide_frame(0.10, background_frac=0.015),  # dawn + weak star
        ])
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        mon._cur_exp_ms = 500.0
        _check(mon)
        r = _check(mon)
        assert r.dawn_warning is True
        assert r.status == GuideMonitorStatus.DAWN_WARNING

    def test_stable_background_no_dawn_warning(self) -> None:
        cfg = GuideMonitorConfig(dawn_threshold_pct=20.0)
        cam = _FakeCamera([
            _guide_frame(0.45, background_frac=0.01),
            _guide_frame(0.45, background_frac=0.01),   # same background
        ])
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        _check(mon)
        r = _check(mon)
        assert r.dawn_warning is False

    def test_dawn_warning_message_set(self) -> None:
        cfg = GuideMonitorConfig(dawn_threshold_pct=20.0)
        cam = _FakeCamera([
            _guide_frame(0.45, background_frac=0.01),
            _guide_frame(0.45, background_frac=0.015),
        ])
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        _check(mon)
        r = _check(mon)
        assert r.warning_msg is not None
        assert "session" in r.warning_msg.lower() or "bright" in r.warning_msg.lower()


# ── Configuration ─────────────────────────────────────────────────────────────

class TestConfig:
    def test_default_interval(self) -> None:
        cfg = GuideMonitorConfig()
        assert cfg.check_interval_s == pytest.approx(300.0)

    def test_custom_interval(self) -> None:
        cfg = GuideMonitorConfig(check_interval_s=60.0)
        assert cfg.check_interval_s == pytest.approx(60.0)

    def test_hysteresis_narrows_band(self) -> None:
        # Tighter hysteresis (5%) → star at 0.40 is outside band
        cfg = GuideMonitorConfig(hysteresis_pct=5.0)
        cam = _FakeCamera([_guide_frame(0.40)], exp_ms=500.0)
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        mon._cur_exp_ms = 500.0
        r = _check(mon)
        # 0.40 < 0.45*0.95=0.4275 → too weak → ADJUSTED
        assert r.status == GuideMonitorStatus.ADJUSTED

    def test_wider_hysteresis_allows_more_drift(self) -> None:
        # Wide hysteresis (40%) → lo=0.45*0.60=0.27, star at 0.30 is in-band
        cfg = GuideMonitorConfig(hysteresis_pct=40.0)
        cam = _FakeCamera([_guide_frame(0.30)])
        mon = GuideMonitor(cam, GPCMOS02000KPA, cfg)
        r = _check(mon)
        assert r.status == GuideMonitorStatus.GUIDE_GAIN_OK


# ── Lifecycle (start / stop / properties) ─────────────────────────────────────

class TestLifecycle:
    def _make_monitor(self) -> GuideMonitor:
        cam = _FakeCamera([_guide_frame(0.45)] * 100)
        return GuideMonitor(cam, GPCMOS02000KPA, GuideMonitorConfig(check_interval_s=0.1))

    def test_running_false_before_start(self) -> None:
        mon = self._make_monitor()
        assert mon.running is False

    def test_last_result_none_before_start(self) -> None:
        mon = self._make_monitor()
        assert mon.last_result is None

    def test_start_sets_running_true(self) -> None:
        mon = self._make_monitor()
        mon.start()
        assert mon.running is True
        mon.stop()

    def test_stop_sets_running_false(self) -> None:
        mon = self._make_monitor()
        mon.start()
        mon.stop()
        assert mon.running is False

    def test_last_result_set_after_first_check(self) -> None:
        mon = self._make_monitor()
        mon.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and mon.last_result is None:
            time.sleep(0.02)
        mon.stop()
        assert mon.last_result is not None

    def test_start_is_idempotent(self) -> None:
        mon = self._make_monitor()
        mon.start()
        thread_id = id(mon._thread)
        mon.start()  # second call: should not spawn a new thread
        assert id(mon._thread) == thread_id
        mon.stop()

    def test_capture_exception_produces_star_weak_result(self) -> None:
        cam = MagicMock(spec=_FakeCamera)
        cam.get_exposure_ms.return_value = 1000.0
        cam.get_gain.return_value = 100
        cam.get_bit_depth.return_value = 16
        cam.capture.side_effect = RuntimeError("shutter stuck")
        mon = GuideMonitor(cam, GPCMOS02000KPA, GuideMonitorConfig(check_interval_s=0.1))
        mon.start()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline and mon.last_result is None:
            time.sleep(0.02)
        mon.stop()
        assert mon.last_result is not None
        assert mon.last_result.status == GuideMonitorStatus.STAR_WEAK
