"""Tests for ScrewResponseLearner — Collimation Phase 8, COL-081."""
from __future__ import annotations

import math

import pytest

from smart_telescope.domain.collimation.models import (
    CircleEllipseFit,
    DonutMeasurement,
    ScrewAngularPosition,
    ScrewCalibration,
)
from smart_telescope.services.collimation.screw_mapper import ScrewResponseLearner


# ── Helpers ───────────────────────────────────────────────────────────────────

def _circle(cx: float, cy: float, r: float = 40.0) -> CircleEllipseFit:
    return CircleEllipseFit(
        center_x=cx, center_y=cy,
        radius_x=r, radius_y=r,
        angle_deg=0.0, confidence=0.8,
    )


def _measurement(
    outer_cx: float = 128.0, outer_cy: float = 128.0,
    inner_cx: float = 128.0, inner_cy: float = 128.0,
) -> DonutMeasurement:
    outer = _circle(outer_cx, outer_cy)
    inner = _circle(inner_cx, inner_cy, r=20.0)
    error_x = inner_cx - outer_cx
    error_y = inner_cy - outer_cy
    error_mag = math.hypot(error_x, error_y)
    error_ang = math.degrees(math.atan2(error_y, error_x))
    return DonutMeasurement(
        outer_ring=outer, inner_hole=inner,
        error_x_px=error_x, error_y_px=error_y,
        error_magnitude_px=error_mag, error_angle_deg=error_ang,
        confidence=0.8,
    )


# ── ScrewAngularPosition domain model ────────────────────────────────────────

class TestScrewAngularPosition:
    def test_fields(self):
        s = ScrewAngularPosition(screw_id="T1", angle_deg=90.0, confidence=0.85)
        assert s.screw_id == "T1"
        assert s.angle_deg == pytest.approx(90.0)
        assert s.confidence == pytest.approx(0.85)

    def test_different_screws(self):
        s1 = ScrewAngularPosition("T1", 90.0, 0.9)
        s2 = ScrewAngularPosition("T2", 210.0, 0.8)
        assert s1.screw_id != s2.screw_id
        assert s1.angle_deg != s2.angle_deg


# ── ScrewResponseLearner — initial state ──────────────────────────────────────

class TestInitialState:
    def test_get_calibration_returns_none_for_unknown_screw(self):
        learner = ScrewResponseLearner()
        assert learner.get_calibration("T1") is None

    def test_get_all_returns_empty_list(self):
        learner = ScrewResponseLearner()
        assert learner.get_all() == []


# ── Single CW observation ─────────────────────────────────────────────────────

class TestSingleCWObservation:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.learner = ScrewResponseLearner()
        # Before: no error; After: inner hole shifted +5 px right
        before = _measurement(inner_cx=128.0)
        after  = _measurement(inner_cx=133.0)
        self.cal = self.learner.observe("T1", before, after, turn_cw=True)

    def test_screw_id(self):
        assert self.cal.screw_id == "T1"

    def test_response_x_positive(self):
        assert self.cal.response_vector_x == pytest.approx(5.0)

    def test_response_y_zero(self):
        assert self.cal.response_vector_y == pytest.approx(0.0)

    def test_samples_one(self):
        assert self.cal.samples == 1

    def test_confidence_nonzero(self):
        assert self.cal.confidence > 0.0

    def test_confidence_below_one(self):
        assert self.cal.confidence < 1.0


# ── Single CCW observation (negated) ─────────────────────────────────────────

class TestSingleCCWObservation:
    def test_ccw_negates_delta(self):
        learner = ScrewResponseLearner()
        # Turning CCW caused inner hole to shift +3 px right
        # → CW equivalent = −3 px right
        before = _measurement(inner_cx=128.0)
        after  = _measurement(inner_cx=131.0)
        cal = learner.observe("T2", before, after, turn_cw=False)
        assert cal.response_vector_x == pytest.approx(-3.0)
        assert cal.response_vector_y == pytest.approx(0.0)


# ── Multiple observations — averaging ────────────────────────────────────────

class TestMultipleObservations:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.learner = ScrewResponseLearner()
        # First obs: +4 px right (CW)
        b1, a1 = _measurement(inner_cx=128.0), _measurement(inner_cx=132.0)
        self.learner.observe("T1", b1, a1, turn_cw=True)
        # Second obs: +6 px right (CW) → average = 5 px
        b2, a2 = _measurement(inner_cx=130.0), _measurement(inner_cx=136.0)
        self.cal = self.learner.observe("T1", b2, a2, turn_cw=True)

    def test_samples_two(self):
        assert self.cal.samples == 2

    def test_response_x_averaged(self):
        assert self.cal.response_vector_x == pytest.approx(5.0)

    def test_response_y_averaged(self):
        assert self.cal.response_vector_y == pytest.approx(0.0)


# ── Confidence increases with samples ────────────────────────────────────────

class TestConfidenceGrowth:
    def test_confidence_grows_with_samples(self):
        learner = ScrewResponseLearner()
        before = _measurement()
        after  = _measurement(inner_cx=130.0)
        confs = []
        for _ in range(5):
            cal = learner.observe("T1", before, after, turn_cw=True)
            confs.append(cal.confidence)
        # Confidence must be monotonically non-decreasing
        assert all(confs[i] <= confs[i + 1] for i in range(len(confs) - 1))

    def test_confidence_saturates_at_one(self):
        learner = ScrewResponseLearner()
        before = _measurement()
        after  = _measurement(inner_cx=130.0)
        cal = None
        for _ in range(20):
            cal = learner.observe("T1", before, after, turn_cw=True)
        assert cal is not None
        assert cal.confidence == pytest.approx(1.0)


# ── get_calibration / get_all ─────────────────────────────────────────────────

class TestGetMethods:
    def test_get_calibration_returns_calibration(self):
        learner = ScrewResponseLearner()
        learner.observe("T2", _measurement(), _measurement(inner_cx=131.0), True)
        cal = learner.get_calibration("T2")
        assert cal is not None
        assert cal.screw_id == "T2"

    def test_get_calibration_matches_observe_return(self):
        learner = ScrewResponseLearner()
        returned = learner.observe("T3", _measurement(), _measurement(inner_cy=133.0), True)
        fetched  = learner.get_calibration("T3")
        assert fetched is not None
        assert returned.response_vector_x == pytest.approx(fetched.response_vector_x)
        assert returned.response_vector_y == pytest.approx(fetched.response_vector_y)

    def test_get_all_returns_all_screws(self):
        learner = ScrewResponseLearner()
        learner.observe("T1", _measurement(), _measurement(inner_cx=131.0), True)
        learner.observe("T2", _measurement(), _measurement(inner_cy=133.0), True)
        all_cals = learner.get_all()
        assert len(all_cals) == 2
        ids = {c.screw_id for c in all_cals}
        assert ids == {"T1", "T2"}

    def test_get_all_does_not_include_unseen_screws(self):
        learner = ScrewResponseLearner()
        learner.observe("T1", _measurement(), _measurement(inner_cx=131.0), True)
        all_cals = learner.get_all()
        ids = {c.screw_id for c in all_cals}
        assert "T2" not in ids
        assert "T3" not in ids


# ── Y-axis response ───────────────────────────────────────────────────────────

class TestYAxisResponse:
    def test_y_component_captured(self):
        learner = ScrewResponseLearner()
        before = _measurement(inner_cy=128.0)
        after  = _measurement(inner_cy=134.0)  # shifted down by 6 px
        cal = learner.observe("T3", before, after, turn_cw=True)
        assert cal.response_vector_x == pytest.approx(0.0)
        assert cal.response_vector_y == pytest.approx(6.0)


# ── Response magnitude property ───────────────────────────────────────────────

class TestResponseMagnitude:
    def test_response_magnitude_diagonal(self):
        learner = ScrewResponseLearner()
        # 3–4–5 right triangle
        before = _measurement()
        after  = _measurement(inner_cx=131.0, inner_cy=132.0)   # +3, +4
        cal = learner.observe("T1", before, after, turn_cw=True)
        assert cal.response_magnitude == pytest.approx(5.0, abs=0.01)
