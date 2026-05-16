"""Tests for SpikeSmoother — Collimation Phase 10, COL-102."""
from __future__ import annotations

import math

import pytest

from smart_telescope.domain.collimation.models import SpikeMeasurement
from smart_telescope.services.collimation.spike_smoother import (
    SmoothedSpikeResult,
    SpikeSmoother,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _spike(focus_error: float, confidence: float = 0.8) -> SpikeMeasurement:
    return SpikeMeasurement(
        focus_error_px=focus_error,
        crossing_error_rms_px=0.5,
        crossing_point_x=128.0,
        crossing_point_y=128.0,
        reference_center_x=128.0,
        reference_center_y=128.0,
        offset_from_ref_px=0.0,
        confidence=confidence,
    )


def _smoother(**kwargs) -> SpikeSmoother:
    defaults = dict(window=7, min_confidence=0.3, seeing_limited_threshold_px=3.0)
    defaults.update(kwargs)
    return SpikeSmoother(**defaults)


# ── SmoothedSpikeResult fields ────────────────────────────────────────────────

class TestSmoothedSpikeResultFields:
    def test_fields(self):
        r = SmoothedSpikeResult(
            focus_error_px=1.0, focus_trend_px=0.5, jitter_px=0.2,
            seeing_limited=False, frame_count=3, confidence=0.8,
        )
        assert r.focus_error_px == pytest.approx(1.0)
        assert r.focus_trend_px == pytest.approx(0.5)
        assert r.jitter_px       == pytest.approx(0.2)
        assert r.frame_count     == 3
        assert not r.seeing_limited
        assert r.confidence       == pytest.approx(0.8)


# ── Empty window ──────────────────────────────────────────────────────────────

class TestEmptyWindow:
    def test_compute_returns_none_when_empty(self):
        s = _smoother()
        assert s.compute() is None

    def test_all_rejected_returns_none(self):
        s = _smoother(min_confidence=0.9)
        s.add(_spike(1.0, confidence=0.1))
        s.add(_spike(2.0, confidence=0.2))
        assert s.compute() is None


# ── Median ────────────────────────────────────────────────────────────────────

class TestMedian:
    def test_median_of_odd_window(self):
        s = _smoother()
        for e in [1.0, 5.0, 3.0]:
            s.add(_spike(e))
        result = s.compute()
        assert result is not None
        assert result.focus_error_px == pytest.approx(3.0)

    def test_median_of_even_window(self):
        s = _smoother()
        for e in [1.0, 2.0, 3.0, 4.0]:
            s.add(_spike(e))
        result = s.compute()
        assert result is not None
        assert result.focus_error_px == pytest.approx(2.5)

    def test_single_frame_median_equals_value(self):
        s = _smoother()
        s.add(_spike(7.0))
        result = s.compute()
        assert result is not None
        assert result.focus_error_px == pytest.approx(7.0)


# ── Confidence filtering ──────────────────────────────────────────────────────

class TestConfidenceFiltering:
    def test_low_confidence_frame_excluded(self):
        s = _smoother(min_confidence=0.5)
        s.add(_spike(100.0, confidence=0.1))  # rejected
        s.add(_spike(2.0, confidence=0.8))
        result = s.compute()
        assert result is not None
        assert result.focus_error_px == pytest.approx(2.0)

    def test_frame_count_excludes_rejected(self):
        s = _smoother(min_confidence=0.5)
        s.add(_spike(100.0, confidence=0.1))  # rejected
        s.add(_spike(2.0, confidence=0.8))
        s.add(_spike(4.0, confidence=0.9))
        result = s.compute()
        assert result is not None
        assert result.frame_count == 2

    def test_exactly_at_threshold_accepted(self):
        s = _smoother(min_confidence=0.5)
        s.add(_spike(3.0, confidence=0.5))
        result = s.compute()
        assert result is not None
        assert result.frame_count == 1


# ── Jitter ────────────────────────────────────────────────────────────────────

class TestJitter:
    def test_zero_jitter_for_identical_errors(self):
        s = _smoother()
        for _ in range(5):
            s.add(_spike(2.0))
        result = s.compute()
        assert result is not None
        assert result.jitter_px == pytest.approx(0.0)

    def test_nonzero_jitter_for_varying_errors(self):
        s = _smoother()
        for e in [1.0, 3.0]:
            s.add(_spike(e))
        result = s.compute()
        assert result is not None
        assert result.jitter_px > 0.0

    def test_seeing_limited_when_jitter_exceeds_threshold(self):
        s = _smoother(seeing_limited_threshold_px=1.0)
        for e in [-5.0, 5.0]:
            s.add(_spike(e))
        result = s.compute()
        assert result is not None
        assert result.seeing_limited

    def test_not_seeing_limited_when_jitter_below_threshold(self):
        s = _smoother(seeing_limited_threshold_px=10.0)
        for e in [1.9, 2.0, 2.1]:
            s.add(_spike(e))
        result = s.compute()
        assert result is not None
        assert not result.seeing_limited


# ── Trend ─────────────────────────────────────────────────────────────────────

class TestTrend:
    def test_trend_is_average_of_recent_half(self):
        # window=4 frames: [1, 2, 3, 4] → recent half = [3, 4] → trend = 3.5
        s = _smoother(window=4)
        for e in [1.0, 2.0, 3.0, 4.0]:
            s.add(_spike(e))
        result = s.compute()
        assert result is not None
        assert result.focus_trend_px == pytest.approx(3.5)

    def test_trend_single_frame(self):
        s = _smoother()
        s.add(_spike(5.0))
        result = s.compute()
        assert result is not None
        assert result.focus_trend_px == pytest.approx(5.0)


# ── Window size ───────────────────────────────────────────────────────────────

class TestWindowSize:
    def test_oldest_frame_evicted_beyond_window(self):
        # window=3; add 4 frames → first is evicted
        s = _smoother(window=3)
        for e in [100.0, 2.0, 3.0, 4.0]:
            s.add(_spike(e))
        result = s.compute()
        assert result is not None
        assert result.frame_count == 3
        # 100.0 evicted; median of [2, 3, 4] = 3.0
        assert result.focus_error_px == pytest.approx(3.0)

    def test_partial_window_still_computes(self):
        s = _smoother(window=7)
        s.add(_spike(1.0))
        s.add(_spike(2.0))
        result = s.compute()
        assert result is not None
        assert result.frame_count == 2


# ── Reset ─────────────────────────────────────────────────────────────────────

class TestReset:
    def test_reset_clears_window(self):
        s = _smoother()
        s.add(_spike(1.0))
        s.reset()
        assert s.compute() is None
        assert s.frame_count == 0


# ── Confidence average ────────────────────────────────────────────────────────

class TestConfidenceAverage:
    def test_mean_confidence_reported(self):
        s = _smoother()
        s.add(_spike(1.0, confidence=0.6))
        s.add(_spike(2.0, confidence=0.8))
        result = s.compute()
        assert result is not None
        assert result.confidence == pytest.approx(0.7)
