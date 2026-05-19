"""Tests for spike_detection — Collimation Phase 10, COL-100."""
from __future__ import annotations

import math

import numpy as np
import pytest

from smart_telescope.domain.bahtinov import BahtinovAnalyzer, CrossingAnalysisResult, SpikeLine
from smart_telescope.domain.collimation.models import Point2D
from smart_telescope.domain.collimation.processing.frame import ProcessedFrame
from smart_telescope.domain.collimation.processing.spike_detection import (
    SpikeDetectionResult,
    detect_spikes,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _frame(h: int = 256, w: int = 256) -> ProcessedFrame:
    return ProcessedFrame(
        mono=np.zeros((h, w), dtype=np.float32),
        raw=np.zeros((h, w), dtype=np.uint16),
        bit_depth=16,
        width=w,
        height=h,
        timestamp=0.0,
    )


def _spike_line(angle_deg: float, conf: float = 500.0) -> SpikeLine:
    theta = math.radians(angle_deg)
    return SpikeLine(a=math.cos(theta), b=math.sin(theta), c=0.0,
                     angle_deg=angle_deg, confidence=conf)


def _crossing_result(
    focus_error: float = 2.0,
    crossing_x: float = 128.0,
    crossing_y: float = 128.0,
    confidence: float = 0.8,
) -> CrossingAnalysisResult:
    lines = [
        _spike_line(30.0),
        _spike_line(90.0),
        _spike_line(150.0),
    ]
    return CrossingAnalysisResult(
        object_center_px=(crossing_x, crossing_y),
        lines=lines,
        common_crossing_point_px=(crossing_x, crossing_y),
        pairwise_intersections_px=[(crossing_x, crossing_y)] * 3,
        crossing_error_rms_px=0.5,
        crossing_error_max_px=0.8,
        focus_error_px=focus_error,
        detection_confidence=confidence,
    )


class _MockAnalyzer:
    def __init__(self, result: CrossingAnalysisResult | None) -> None:
        self._result = result

    def analyze(self, pixels: np.ndarray) -> CrossingAnalysisResult:
        if self._result is None:
            raise ValueError("fewer than 3 spikes detected")
        return self._result


# ── SpikeDetectionResult fields ───────────────────────────────────────────────

class TestSpikeDetectionResult:
    def test_fields(self):
        r = SpikeDetectionResult(measurement=None, reason="too_few_spikes")
        assert r.measurement is None
        assert r.reason == "too_few_spikes"
        assert r.raw_result is None


# ── Success path ──────────────────────────────────────────────────────────────

class TestDetectSpikesOk:
    def test_reason_ok_when_3_lines(self):
        result = detect_spikes(_frame(), Point2D(128.0, 128.0),
                               analyzer=_MockAnalyzer(_crossing_result()))
        assert result.reason == "ok"

    def test_measurement_populated(self):
        result = detect_spikes(_frame(), Point2D(128.0, 128.0),
                               analyzer=_MockAnalyzer(_crossing_result(focus_error=3.5)))
        assert result.measurement is not None
        assert result.measurement.focus_error_px == pytest.approx(3.5)

    def test_raw_result_populated(self):
        cr = _crossing_result()
        result = detect_spikes(_frame(), Point2D(128.0, 128.0),
                               analyzer=_MockAnalyzer(cr))
        assert result.raw_result is cr

    def test_offset_from_ref_computed(self):
        # crossing at (128, 128), ref at (118, 128) → offset = 10 px
        cr = _crossing_result(crossing_x=128.0, crossing_y=128.0)
        result = detect_spikes(_frame(), Point2D(118.0, 128.0),
                               analyzer=_MockAnalyzer(cr))
        assert result.measurement is not None
        assert result.measurement.offset_from_ref_px == pytest.approx(10.0)

    def test_confidence_from_detection_confidence(self):
        cr = _crossing_result(confidence=0.72)
        result = detect_spikes(_frame(), Point2D(128.0, 128.0),
                               analyzer=_MockAnalyzer(cr))
        assert result.measurement is not None
        assert result.measurement.confidence == pytest.approx(0.72)

    def test_crossing_point_stored(self):
        cr = _crossing_result(crossing_x=130.0, crossing_y=125.0)
        result = detect_spikes(_frame(), Point2D(128.0, 128.0),
                               analyzer=_MockAnalyzer(cr))
        assert result.measurement is not None
        assert result.measurement.crossing_point_x == pytest.approx(130.0)
        assert result.measurement.crossing_point_y == pytest.approx(125.0)

    def test_ref_center_stored_in_measurement(self):
        result = detect_spikes(_frame(), Point2D(64.0, 96.0),
                               analyzer=_MockAnalyzer(_crossing_result()))
        assert result.measurement is not None
        assert result.measurement.reference_center_x == pytest.approx(64.0)
        assert result.measurement.reference_center_y == pytest.approx(96.0)


# ── Failure paths ─────────────────────────────────────────────────────────────

class TestDetectSpikesTooFew:
    def test_too_few_spikes_when_analyzer_raises(self):
        result = detect_spikes(_frame(), Point2D(128.0, 128.0),
                               analyzer=_MockAnalyzer(None))
        assert result.reason == "too_few_spikes"
        assert result.measurement is None
        assert result.raw_result is None

    def test_no_signal_when_zero_confidence(self):
        cr = _crossing_result(confidence=0.0)
        result = detect_spikes(_frame(), Point2D(128.0, 128.0),
                               analyzer=_MockAnalyzer(cr))
        assert result.reason == "no_signal"
        assert result.measurement is None
        assert result.raw_result is cr


# ── Default analyzer ──────────────────────────────────────────────────────────

class TestDefaultAnalyzer:
    def test_default_analyzer_used_when_none_given(self):
        # All-zero frame has no signal → BahtinovAnalyzer raises → too_few_spikes
        result = detect_spikes(_frame(), Point2D(128.0, 128.0), analyzer=None)
        assert result.reason in ("too_few_spikes", "no_signal")
