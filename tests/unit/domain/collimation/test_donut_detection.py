"""Tests for DonutAnalyzer — Collimation Phase 7, COL-070/071."""
from __future__ import annotations

import math

import numpy as np
import pytest

from smart_telescope.domain.collimation.processing.donut_detection import (
    DonutAnalysisResult,
    DonutAnalyzer,
)
from smart_telescope.domain.collimation.processing.frame import normalize_frame
from smart_telescope.domain.frame import FitsFrame


# ── Frame factories ───────────────────────────────────────────────────────────

def _make_donut_frame(
    outer_cx: float = 128.0,
    outer_cy: float = 128.0,
    outer_r: float = 40.0,
    inner_cx: float = 128.0,
    inner_cy: float = 128.0,
    inner_r: float = 20.0,
    width: int = 256,
    height: int = 256,
    ring_adu: float = 5000.0,
    bg: float = 100.0,
    seed: int = 42,
) -> FitsFrame:
    """Synthetic donut frame.

    Bright region = within outer_r of (outer_cx, outer_cy)
                    AND outside inner_r of (inner_cx, inner_cy).
    When outer center == inner center → perfectly centered ring.
    When centers differ → off-center hole (miscollimated donut).
    """
    rng = np.random.default_rng(seed)
    data = rng.normal(bg, 10.0, (height, width)).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    dist_outer = np.sqrt((xx - outer_cx) ** 2 + (yy - outer_cy) ** 2)
    dist_inner = np.sqrt((xx - inner_cx) ** 2 + (yy - inner_cy) ** 2)
    bright = (dist_outer <= outer_r) & (dist_inner >= inner_r)
    data[bright] += ring_adu
    return FitsFrame(pixels=data, header={}, exposure_seconds=1.0)


def _dim_frame(width: int = 256, height: int = 256) -> FitsFrame:
    rng = np.random.default_rng(1)
    return FitsFrame(
        pixels=rng.normal(100.0, 10.0, (height, width)).astype(np.float32),
        header={}, exposure_seconds=1.0,
    )


def _processed(frame: FitsFrame, bit_depth: int = 16):
    return normalize_frame(frame, bit_depth=bit_depth)


# ── DonutAnalysisResult ───────────────────────────────────────────────────────

class TestDonutAnalysisResult:
    def test_reason_and_measurement_fields(self):
        r = DonutAnalysisResult(measurement=None, reason="no_signal")
        assert r.reason == "no_signal"
        assert r.measurement is None

    def test_ok_result_has_measurement(self):
        frame = _make_donut_frame()
        result = DonutAnalyzer().analyze(_processed(frame))
        assert result.reason == "ok"
        assert result.measurement is not None


# ── No-signal / dim frame ─────────────────────────────────────────────────────

class TestNoSignal:
    def test_dim_frame_returns_no_signal(self):
        result = DonutAnalyzer().analyze(_processed(_dim_frame()))
        assert result.reason == "no_signal"
        assert result.measurement is None


# ── Centered donut — basic correctness ───────────────────────────────────────

class TestCenteredDonut:
    @pytest.fixture(autouse=True)
    def _result(self):
        frame = _make_donut_frame(
            outer_cx=128.0, outer_cy=128.0, outer_r=40.0,
            inner_cx=128.0, inner_cy=128.0, inner_r=20.0,
        )
        self.result = DonutAnalyzer().analyze(_processed(frame))

    def test_reason_ok(self):
        assert self.result.reason == "ok"

    def test_measurement_not_none(self):
        assert self.result.measurement is not None

    def test_outer_radius_approximate(self):
        m = self.result.measurement
        assert m is not None
        assert pytest.approx(40.0, abs=4.0) == m.outer_ring.mean_radius

    def test_inner_radius_approximate(self):
        m = self.result.measurement
        assert m is not None
        assert pytest.approx(20.0, abs=4.0) == m.inner_hole.mean_radius

    def test_error_magnitude_small(self):
        m = self.result.measurement
        assert m is not None
        # Centered donut → error vector should be close to zero
        assert m.error_magnitude_px < 5.0

    def test_confidence_reasonable(self):
        m = self.result.measurement
        assert m is not None
        assert m.confidence > 0.0

    def test_outer_center_near_frame_center(self):
        m = self.result.measurement
        assert m is not None
        assert abs(m.outer_ring.center_x - 128.0) < 5.0
        assert abs(m.outer_ring.center_y - 128.0) < 5.0


# ── Offset (miscollimated) donut ──────────────────────────────────────────────

class TestOffsetDonut:
    @pytest.fixture(autouse=True)
    def _result(self):
        # Inner hole shifted 12 px to the right
        frame = _make_donut_frame(
            outer_cx=128.0, outer_cy=128.0, outer_r=40.0,
            inner_cx=140.0, inner_cy=128.0, inner_r=18.0,
        )
        self.result = DonutAnalyzer().analyze(_processed(frame))
        self.offset_x = 12.0  # inner_cx - outer_cx

    def test_reason_ok(self):
        assert self.result.reason == "ok"

    def test_detects_positive_x_error(self):
        m = self.result.measurement
        assert m is not None
        # error_x_px should be positive (inner center is to the right)
        assert m.error_x_px > 0.0

    def test_error_magnitude_nonzero(self):
        m = self.result.measurement
        assert m is not None
        assert m.error_magnitude_px > 3.0

    def test_error_direction_roughly_horizontal(self):
        m = self.result.measurement
        assert m is not None
        # Error angle should be close to 0° (pointing right)
        angle = m.error_angle_deg
        # Normalise to [-180, 180]
        angle = (angle + 180.0) % 360.0 - 180.0
        assert abs(angle) < 45.0


# ── Clipping ──────────────────────────────────────────────────────────────────

class TestClipping:
    def test_clipped_donut_returns_clipped(self):
        # Donut center near left edge — outer ring extends outside frame
        frame = _make_donut_frame(
            outer_cx=20.0, outer_cy=128.0, outer_r=30.0,
            inner_cx=20.0, inner_cy=128.0, inner_r=12.0,
        )
        result = DonutAnalyzer().analyze(_processed(frame))
        assert result.reason == "clipped"
        assert result.measurement is None


# ── Frame-position independence ───────────────────────────────────────────────

class TestFramePositionIndependence:
    def test_off_center_donut_detected(self):
        """Donut well inside frame but not at center."""
        frame = _make_donut_frame(
            outer_cx=80.0, outer_cy=170.0, outer_r=35.0,
            inner_cx=80.0, inner_cy=170.0, inner_r=15.0,
            width=256, height=256,
        )
        result = DonutAnalyzer().analyze(_processed(frame))
        assert result.reason == "ok"
        m = result.measurement
        assert m is not None
        assert abs(m.outer_ring.center_x - 80.0) < 6.0
        assert abs(m.outer_ring.center_y - 170.0) < 6.0


# ── Custom confidence threshold ───────────────────────────────────────────────

class TestCustomConfidence:
    def test_very_high_threshold_rejects_result(self):
        """With min_confidence=0.99 nothing should pass."""
        frame = _make_donut_frame()
        analyzer = DonutAnalyzer(min_confidence=0.99)
        result = analyzer.analyze(_processed(frame))
        # Either no_ring_shape or inner_hole_unclear — not "ok"
        assert result.reason != "ok"
        assert result.measurement is None
