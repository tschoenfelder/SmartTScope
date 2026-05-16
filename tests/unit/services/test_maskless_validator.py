"""Tests for MasklessValidator — Collimation Phase 12, COL-121."""
from __future__ import annotations

import pytest

from smart_telescope.domain.collimation.models import CircleEllipseFit, DonutMeasurement
from smart_telescope.services.collimation.maskless_validator import (
    MasklessValidator,
    ValidationReport,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ring(radius: float, confidence: float = 1.0) -> CircleEllipseFit:
    return CircleEllipseFit(
        center_x=256.0, center_y=256.0,
        radius_x=radius, radius_y=radius,
        confidence=confidence,
    )


def _donut(
    error_px: float,
    outer_radius: float = 100.0,
    confidence: float = 0.9,
) -> DonutMeasurement:
    import math
    return DonutMeasurement(
        outer_ring=_ring(outer_radius),
        inner_hole=CircleEllipseFit(
            center_x=256.0 + error_px,
            center_y=256.0,
            radius_x=20.0, radius_y=20.0,
        ),
        error_x_px=error_px,
        error_y_px=0.0,
        error_magnitude_px=abs(error_px),
        error_angle_deg=0.0,
        confidence=confidence,
    )


# ── ValidationReport fields ───────────────────────────────────────────────────

class TestValidationReportFields:
    def test_has_all_fields(self):
        r = ValidationReport(
            status="complete", donut_error_px=1.0, donut_error_ratio=0.01,
            is_collimated=True, confidence=0.9, warnings=[],
        )
        assert r.status == "complete"
        assert r.donut_error_px == pytest.approx(1.0)
        assert r.donut_error_ratio == pytest.approx(0.01)
        assert r.is_collimated is True
        assert r.confidence == pytest.approx(0.9)
        assert r.warnings == []

    def test_warnings_defaults_to_empty_list(self):
        r = ValidationReport(
            status="complete", donut_error_px=0.5, donut_error_ratio=0.005,
            is_collimated=True, confidence=0.8,
        )
        assert r.warnings == []


# ── Complete (well collimated) ────────────────────────────────────────────────

class TestComplete:
    def test_status_complete_when_error_below_good_ratio(self):
        # error=1px, outer_radius=100 → ratio=0.01 < good=0.02
        v = MasklessValidator(good_error_ratio=0.02, fallback_error_ratio=0.05)
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0))
        assert r.status == "complete"

    def test_is_collimated_true_when_complete(self):
        v = MasklessValidator(good_error_ratio=0.02)
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0))
        assert r.is_collimated is True

    def test_no_warnings_when_complete(self):
        v = MasklessValidator(good_error_ratio=0.02)
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0))
        assert r.warnings == []

    def test_error_ratio_computed_correctly(self):
        # error=2px, outer_radius=100 → ratio=0.02
        v = MasklessValidator(good_error_ratio=0.02)
        r = v.assess(_donut(error_px=2.0, outer_radius=100.0))
        assert r.donut_error_ratio == pytest.approx(0.02)

    def test_error_px_matches_donut(self):
        v = MasklessValidator(good_error_ratio=0.02)
        r = v.assess(_donut(error_px=1.5, outer_radius=100.0))
        assert r.donut_error_px == pytest.approx(1.5)


# ── Acceptable with warning (marginal) ───────────────────────────────────────

class TestAcceptableWithWarning:
    def test_status_acceptable_when_above_good_below_fallback(self):
        # error=3px, radius=100 → ratio=0.03; good=0.02, fallback=0.05
        v = MasklessValidator(good_error_ratio=0.02, fallback_error_ratio=0.05)
        r = v.assess(_donut(error_px=3.0, outer_radius=100.0))
        assert r.status == "acceptable_with_warning"

    def test_is_collimated_false_when_acceptable(self):
        v = MasklessValidator(good_error_ratio=0.02, fallback_error_ratio=0.05)
        r = v.assess(_donut(error_px=3.0, outer_radius=100.0))
        assert r.is_collimated is False

    def test_warning_present_when_acceptable(self):
        v = MasklessValidator(good_error_ratio=0.02, fallback_error_ratio=0.05)
        r = v.assess(_donut(error_px=3.0, outer_radius=100.0))
        assert len(r.warnings) >= 1


# ── Failed (too much error) ───────────────────────────────────────────────────

class TestFailed:
    def test_status_failed_when_above_fallback(self):
        # error=6px, radius=100 → ratio=0.06 > fallback=0.05
        v = MasklessValidator(good_error_ratio=0.02, fallback_error_ratio=0.05)
        r = v.assess(_donut(error_px=6.0, outer_radius=100.0))
        assert r.status == "failed"

    def test_is_collimated_false_when_failed(self):
        v = MasklessValidator(good_error_ratio=0.02, fallback_error_ratio=0.05)
        r = v.assess(_donut(error_px=6.0, outer_radius=100.0))
        assert r.is_collimated is False

    def test_warning_present_when_failed(self):
        v = MasklessValidator(good_error_ratio=0.02, fallback_error_ratio=0.05)
        r = v.assess(_donut(error_px=6.0, outer_radius=100.0))
        assert len(r.warnings) >= 1


# ── Low confidence → failed ───────────────────────────────────────────────────

class TestLowConfidence:
    def test_failed_when_confidence_below_minimum(self):
        v = MasklessValidator(min_confidence=0.5)
        # confidence=0.3 < 0.5
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0, confidence=0.3))
        assert r.status == "failed"
        assert r.is_collimated is False

    def test_confidence_warning_when_below_minimum(self):
        v = MasklessValidator(min_confidence=0.5)
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0, confidence=0.3))
        assert len(r.warnings) >= 1

    def test_status_not_failed_when_confidence_at_minimum(self):
        v = MasklessValidator(good_error_ratio=0.02, min_confidence=0.5)
        # confidence=0.5 is exactly at threshold → should pass
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0, confidence=0.5))
        assert r.status != "failed"


# ── Seeing limited ────────────────────────────────────────────────────────────

class TestSeeingLimited:
    def test_seeing_limited_when_jitter_above_threshold(self):
        v = MasklessValidator(
            good_error_ratio=0.02, fallback_error_ratio=0.05,
            seeing_jitter_threshold_px=3.0,
        )
        # good error ratio but high jitter
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0), jitter_px=4.0)
        assert r.status == "seeing_limited"

    def test_is_collimated_false_when_seeing_limited(self):
        v = MasklessValidator(
            good_error_ratio=0.02,
            seeing_jitter_threshold_px=3.0,
        )
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0), jitter_px=4.0)
        assert r.is_collimated is False

    def test_seeing_warning_present(self):
        v = MasklessValidator(seeing_jitter_threshold_px=3.0)
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0), jitter_px=4.0)
        assert any("jitter" in w.lower() for w in r.warnings)

    def test_no_seeing_limit_when_jitter_at_zero(self):
        v = MasklessValidator(
            good_error_ratio=0.02,
            seeing_jitter_threshold_px=3.0,
        )
        r = v.assess(_donut(error_px=1.0, outer_radius=100.0), jitter_px=0.0)
        assert r.status == "complete"

    def test_seeing_limited_status_when_marginal_error_and_high_jitter(self):
        # error between good and fallback + high jitter → still "seeing_limited"
        v = MasklessValidator(
            good_error_ratio=0.02, fallback_error_ratio=0.05,
            seeing_jitter_threshold_px=3.0,
        )
        r = v.assess(_donut(error_px=3.0, outer_radius=100.0), jitter_px=5.0)
        assert r.status == "seeing_limited"


# ── Elliptical outer ring ─────────────────────────────────────────────────────

class TestEllipticalRing:
    def test_uses_mean_radius_for_ratio(self):
        outer = CircleEllipseFit(
            center_x=256.0, center_y=256.0,
            radius_x=80.0, radius_y=120.0,  # mean = 100
        )
        inner = CircleEllipseFit(
            center_x=257.0, center_y=256.0,
            radius_x=20.0, radius_y=20.0,
        )
        donut = DonutMeasurement(
            outer_ring=outer, inner_hole=inner,
            error_x_px=1.0, error_y_px=0.0,
            error_magnitude_px=1.0, error_angle_deg=0.0,
            confidence=0.9,
        )
        v = MasklessValidator(good_error_ratio=0.02)
        r = v.assess(donut)
        # mean radius = 100, ratio = 1/100 = 0.01
        assert r.donut_error_ratio == pytest.approx(0.01)
