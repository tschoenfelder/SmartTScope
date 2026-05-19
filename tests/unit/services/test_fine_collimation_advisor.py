"""Tests for FineCollimationAdvisor — Collimation Phase 11, COL-112."""
from __future__ import annotations

import pytest

from smart_telescope.domain.collimation.models import AdjustmentSize, TurnDirection
from smart_telescope.services.collimation.fine_collimation_advisor import (
    FineCollimationAdvisor,
)
from smart_telescope.services.collimation.spike_smoother import SmoothedSpikeResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _smoothed(
    jitter: float = 0.5,
    confidence: float = 0.8,
    seeing_limited: bool = False,
) -> SmoothedSpikeResult:
    return SmoothedSpikeResult(
        focus_error_px=0.0,
        focus_trend_px=0.0,
        jitter_px=jitter,
        seeing_limited=seeing_limited,
        frame_count=5,
        confidence=confidence,
    )


def _advisor(**kwargs) -> FineCollimationAdvisor:
    defaults = dict(
        target_residual_px=2.0,
        seeing_limited_px=3.0,
        confidence_threshold=0.5,
        medium_threshold_ratio=1.5,
    )
    defaults.update(kwargs)
    return FineCollimationAdvisor(**defaults)


# ── No recommendation cases ───────────────────────────────────────────────────

class TestNoRecommendation:
    def test_returns_none_when_all_residuals_within_target(self):
        adv = _advisor(target_residual_px=2.0)
        res = adv.recommend({"T1": 0.5, "T2": 1.0, "T3": -0.3}, _smoothed())
        assert res is None

    def test_returns_none_when_seeing_limited(self):
        adv = _advisor()
        res = adv.recommend({"T1": 5.0, "T2": 1.0}, _smoothed(seeing_limited=True))
        assert res is None

    def test_returns_none_when_low_confidence(self):
        adv = _advisor(confidence_threshold=0.5)
        res = adv.recommend({"T1": 5.0}, _smoothed(confidence=0.3))
        assert res is None

    def test_returns_none_for_empty_residuals(self):
        adv = _advisor()
        assert adv.recommend({}, _smoothed()) is None


# ── Screw selection ───────────────────────────────────────────────────────────

class TestScrewSelection:
    def test_selects_worst_screw(self):
        adv = _advisor()
        res = adv.recommend({"T1": 1.0, "T2": 5.0, "T3": -2.5}, _smoothed())
        assert res is not None
        assert res.screw_id == "T2"

    def test_selects_negative_worst_correctly(self):
        adv = _advisor()
        res = adv.recommend({"T1": 1.0, "T2": -6.0, "T3": 2.5}, _smoothed())
        assert res is not None
        assert res.screw_id == "T2"

    def test_single_screw(self):
        adv = _advisor()
        res = adv.recommend({"T1": 4.0}, _smoothed())
        assert res is not None
        assert res.screw_id == "T1"


# ── Turn direction ────────────────────────────────────────────────────────────

class TestTurnDirection:
    def test_clockwise_for_positive_residual(self):
        adv = _advisor()
        res = adv.recommend({"T1": 5.0}, _smoothed())
        assert res is not None
        assert res.turn_direction == TurnDirection.CLOCKWISE

    def test_counter_clockwise_for_negative_residual(self):
        adv = _advisor()
        res = adv.recommend({"T1": -5.0}, _smoothed())
        assert res is not None
        assert res.turn_direction == TurnDirection.COUNTER_CLOCKWISE


# ── Adjustment size ───────────────────────────────────────────────────────────

class TestAdjustmentSize:
    def test_small_for_modest_residual(self):
        # ratio = 2.5 / 2.0 = 1.25 < medium_threshold_ratio 1.5 → SMALL
        adv = _advisor(target_residual_px=2.0, medium_threshold_ratio=1.5)
        res = adv.recommend({"T1": 2.5}, _smoothed())
        assert res is not None
        assert res.adjustment_size == AdjustmentSize.SMALL

    def test_medium_for_large_residual(self):
        # ratio = 4.0 / 2.0 = 2.0 >= medium_threshold_ratio 1.5 → MEDIUM
        adv = _advisor(target_residual_px=2.0, medium_threshold_ratio=1.5)
        res = adv.recommend({"T1": 4.0}, _smoothed())
        assert res is not None
        assert res.adjustment_size == AdjustmentSize.MEDIUM

    def test_never_large(self):
        adv = _advisor()
        res = adv.recommend({"T1": 100.0}, _smoothed())
        assert res is not None
        assert res.adjustment_size != AdjustmentSize.LARGE


# ── Confidence ────────────────────────────────────────────────────────────────

class TestConfidence:
    def test_confidence_between_zero_and_one(self):
        adv = _advisor()
        res = adv.recommend({"T1": 5.0}, _smoothed(confidence=0.8))
        assert res is not None
        assert 0.0 <= res.confidence <= 1.0

    def test_lower_smoothed_confidence_reduces_recommendation_confidence(self):
        adv = _advisor()
        r_high = adv.recommend({"T1": 5.0}, _smoothed(confidence=0.9))
        r_low  = adv.recommend({"T1": 5.0}, _smoothed(confidence=0.6))
        assert r_high is not None and r_low is not None
        assert r_low.confidence < r_high.confidence


# ── Reason string ─────────────────────────────────────────────────────────────

class TestReasonString:
    def test_reason_mentions_screw_id(self):
        adv = _advisor()
        res = adv.recommend({"T2": 5.0}, _smoothed())
        assert res is not None
        assert "T2" in res.reason

    def test_reason_mentions_residual(self):
        adv = _advisor()
        res = adv.recommend({"T1": 5.0}, _smoothed())
        assert res is not None
        assert "residual" in res.reason.lower() or "px" in res.reason
