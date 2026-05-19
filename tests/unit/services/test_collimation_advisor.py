"""Tests for CollimationAdvisor — Collimation Phase 9, COL-090."""
from __future__ import annotations

import math

import pytest

from smart_telescope.domain.collimation.models import (
    AdjustmentSize,
    CircleEllipseFit,
    CollimationRecommendation,
    DonutMeasurement,
    ScrewCalibration,
    TurnDirection,
)
from smart_telescope.services.collimation.collimation_advisor import CollimationAdvisor


# ── Helpers ───────────────────────────────────────────────────────────────────

def _circle(cx: float, cy: float, r: float = 40.0, conf: float = 0.8) -> CircleEllipseFit:
    return CircleEllipseFit(
        center_x=cx, center_y=cy,
        radius_x=r, radius_y=r,
        angle_deg=0.0, confidence=conf,
    )


def _measurement(
    error_x: float = 0.0,
    error_y: float = 0.0,
    outer_r: float = 40.0,
) -> DonutMeasurement:
    outer = _circle(128.0, 128.0, r=outer_r)
    inner = _circle(128.0 + error_x, 128.0 + error_y, r=20.0)
    error_mag = math.hypot(error_x, error_y)
    error_ang = math.degrees(math.atan2(error_y, error_x)) if error_mag > 0 else 0.0
    return DonutMeasurement(
        outer_ring=outer, inner_hole=inner,
        error_x_px=error_x, error_y_px=error_y,
        error_magnitude_px=error_mag, error_angle_deg=error_ang,
        confidence=0.8,
    )


def _cal(screw_id: str, rx: float, ry: float, confidence: float = 0.8) -> ScrewCalibration:
    return ScrewCalibration(
        screw_id=screw_id,
        response_vector_x=rx,
        response_vector_y=ry,
        samples=3,
        confidence=confidence,
    )


# ── No calibrations ───────────────────────────────────────────────────────────

class TestNoCalibration:
    def test_returns_none_when_no_calibrations(self):
        advisor = CollimationAdvisor(calibrations=[])
        assert advisor.recommend(_measurement(error_x=10.0)) is None

    def test_returns_none_when_all_responses_negligible(self):
        # Response magnitude < 0.5 → ignored
        advisor = CollimationAdvisor(calibrations=[_cal("T1", 0.1, 0.0)])
        assert advisor.recommend(_measurement(error_x=10.0)) is None


# ── Already collimated ────────────────────────────────────────────────────────

class TestAlreadyCollimated:
    def test_returns_none_when_error_below_threshold(self):
        # outer_r=40, collimated_fraction=0.02 → threshold = 0.8 px
        advisor = CollimationAdvisor(calibrations=[_cal("T1", 5.0, 0.0)])
        m = _measurement(error_x=0.5, outer_r=40.0)
        assert advisor.recommend(m) is None

    def test_returns_recommendation_when_error_above_threshold(self):
        advisor = CollimationAdvisor(calibrations=[_cal("T1", 5.0, 0.0)])
        m = _measurement(error_x=5.0, outer_r=40.0)
        assert advisor.recommend(m) is not None


# ── Correct screw selection ───────────────────────────────────────────────────

class TestScrewSelection:
    def _setup_two_screws(self):
        # T1 response: +x direction (helps with +x error correction = -x correction needed)
        # T2 response: +y direction
        cals = [_cal("T1", 5.0, 0.0), _cal("T2", 0.0, 5.0)]
        return CollimationAdvisor(calibrations=cals)

    def test_selects_x_screw_for_x_error(self):
        advisor = self._setup_two_screws()
        # error_x = +8 → correction target = -8 in x → T1 (rx=-8 dot +5 = -40 < 0... wait
        # correction = (-error_x, -error_y) = (-8, 0)
        # T1: dot = (-8)*5 + 0*0 = -40  → dot < 0 → CCW helps (|dot|=40)
        # T2: dot = (-8)*0 + 0*5 = 0    → no help
        # Best: T1 CCW
        rec = advisor.recommend(_measurement(error_x=8.0))
        assert rec is not None
        assert rec.screw_id == "T1"

    def test_selects_y_screw_for_y_error(self):
        advisor = self._setup_two_screws()
        rec = advisor.recommend(_measurement(error_y=8.0))
        assert rec is not None
        assert rec.screw_id == "T2"

    def test_three_screws_picks_dominant(self):
        # T1 aligned with x, T2 with y, T3 diagonal
        cals = [
            _cal("T1", 5.0, 0.0),
            _cal("T2", 0.0, 5.0),
            _cal("T3", 3.5, 3.5),
        ]
        advisor = CollimationAdvisor(calibrations=cals)
        # Pure x error → T1 should win (dot = 5*8 = 40 > T3 dot = 3.5*8 ≈ 28)
        rec = advisor.recommend(_measurement(error_x=8.0))
        assert rec is not None
        assert rec.screw_id == "T1"


# ── Turn direction ────────────────────────────────────────────────────────────

class TestTurnDirection:
    def test_cw_when_response_opposes_error(self):
        # T1 response = (-5, 0): a CW turn moves error in -x direction
        # error_x = +8 → correction = (-8, 0)
        # dot_cw = (-8)*(-5) + 0*0 = +40 → CW helps
        cals = [_cal("T1", -5.0, 0.0)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=8.0))
        assert rec is not None
        assert rec.turn_direction == TurnDirection.CLOCKWISE

    def test_ccw_when_response_aligns_with_error(self):
        # T1 response = (+5, 0): CW turn worsens error, CCW corrects
        # error_x = +8 → correction = (-8, 0)
        # dot_cw = (-8)*(+5) = -40 → dot < 0 → CCW helps
        cals = [_cal("T1", 5.0, 0.0)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=8.0))
        assert rec is not None
        assert rec.turn_direction == TurnDirection.COUNTER_CLOCKWISE


# ── Adjustment size ───────────────────────────────────────────────────────────

class TestAdjustmentSize:
    def test_small_for_modest_error(self):
        # error=4 px, outer_r=40 → ratio=0.10 ≤ 0.15 → SMALL
        cals = [_cal("T1", -5.0, 0.0)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=4.0, outer_r=40.0))
        assert rec is not None
        assert rec.adjustment_size == AdjustmentSize.SMALL

    def test_medium_for_large_error(self):
        # error=8 px, outer_r=40 → ratio=0.20 > 0.15 → MEDIUM
        cals = [_cal("T1", -5.0, 0.0)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=8.0, outer_r=40.0))
        assert rec is not None
        assert rec.adjustment_size == AdjustmentSize.MEDIUM

    def test_never_large(self):
        # Even with very large error, should not return LARGE
        cals = [_cal("T1", -5.0, 0.0)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=40.0, outer_r=40.0))
        assert rec is not None
        assert rec.adjustment_size != AdjustmentSize.LARGE


# ── Confidence ────────────────────────────────────────────────────────────────

class TestConfidence:
    def test_confidence_between_zero_and_one(self):
        cals = [_cal("T1", -5.0, 0.0, confidence=0.8)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=8.0))
        assert rec is not None
        assert 0.0 <= rec.confidence <= 1.0

    def test_low_calibration_confidence_reduces_recommendation_confidence(self):
        # Low screw confidence → halved
        cals_low  = [_cal("T1", -5.0, 0.0, confidence=0.1)]
        cals_high = [_cal("T1", -5.0, 0.0, confidence=0.9)]
        a_low  = CollimationAdvisor(calibrations=cals_low)
        a_high = CollimationAdvisor(calibrations=cals_high)
        m = _measurement(error_x=8.0)
        assert a_low.recommend(m).confidence < a_high.recommend(m).confidence

    def test_is_actionable_with_high_confidence(self):
        # confidence > 0.5 and direction != NONE → is_actionable
        cals = [_cal("T1", -5.0, 0.0, confidence=0.9)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=8.0))
        assert rec is not None
        assert rec.is_actionable


# ── Reason string ────────────────────────────────────────────────────────────

class TestReasonString:
    def test_reason_contains_error_info(self):
        cals = [_cal("T1", -5.0, 0.0)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=8.0))
        assert rec is not None
        assert "error" in rec.reason.lower()

    def test_reason_mentions_recalibration_for_low_confidence(self):
        cals = [_cal("T1", -5.0, 0.0, confidence=0.1)]
        advisor = CollimationAdvisor(calibrations=cals)
        rec = advisor.recommend(_measurement(error_x=8.0))
        assert rec is not None
        assert "recal" in rec.reason.lower()


# ── Custom outer_radius parameter ─────────────────────────────────────────────

class TestCustomOuterRadius:
    def test_custom_outer_radius_used_for_size(self):
        # Same error (8 px) but huge outer_r=200 → ratio=0.04 → SMALL
        cals = [_cal("T1", -5.0, 0.0)]
        advisor = CollimationAdvisor(calibrations=cals)
        m = _measurement(error_x=8.0)
        rec = advisor.recommend(m, outer_radius=200.0)
        assert rec is not None
        assert rec.adjustment_size == AdjustmentSize.SMALL
