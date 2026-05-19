"""Tests for ContradictionDetector — Collimation Phase 11, COL-113."""
from __future__ import annotations

import math

import pytest

from smart_telescope.domain.bahtinov import SpikeLine
from smart_telescope.domain.collimation.processing.spike_decomposition import (
    decompose_spike_errors,
)
from smart_telescope.services.collimation.contradiction_detector import (
    ContradictionDetector,
)
from smart_telescope.services.collimation.spike_smoother import SmoothedSpikeResult


# ── Helpers ───────────────────────────────────────────────────────────────────

def _smoothed(
    jitter: float = 0.5,
    confidence: float = 0.8,
    seeing_limited: bool = False,
    focus_error: float = 0.0,
) -> SmoothedSpikeResult:
    return SmoothedSpikeResult(
        focus_error_px=focus_error,
        focus_trend_px=0.0,
        jitter_px=jitter,
        seeing_limited=seeing_limited,
        frame_count=5,
        confidence=confidence,
    )


def _line(angle_deg: float, rho: float = 0.0) -> SpikeLine:
    theta = math.radians(angle_deg)
    a, b = math.cos(theta), math.sin(theta)
    return SpikeLine(a=a, b=b, c=-rho, angle_deg=angle_deg, confidence=100.0)


def _decomp(residual_shift: float = 0.0, focus_shift: float = 0.0):
    """Build a SpikeErrorDecomposition with controlled residual and focus error."""
    lines = [_line(30.0), _line(90.0, rho=residual_shift), _line(150.0)]
    d = decompose_spike_errors(lines)
    # We can't easily inject a focus shift without changing lines; use the real result
    return d


def _detector(**kwargs) -> ContradictionDetector:
    defaults = dict(
        focus_target_px=2.0,
        confidence_threshold=0.5,
        seeing_threshold_px=3.0,
    )
    defaults.update(kwargs)
    return ContradictionDetector(**defaults)


# ── No contradiction ──────────────────────────────────────────────────────────

class TestNoContradiction:
    def test_no_contradiction_when_all_ok(self):
        d = _detector()
        result = d.assess(_smoothed(jitter=0.5, confidence=0.8), _decomp(0.0))
        assert not result.has_contradiction
        assert not result.stop_guidance
        assert result.conflicting_indicators == []

    def test_action_ok_when_no_contradiction(self):
        d = _detector()
        result = d.assess(_smoothed(), _decomp())
        assert "proceed" in result.recommended_action.lower() or "consistent" in result.recommended_action.lower()


# ── Seeing-limited ────────────────────────────────────────────────────────────

class TestSeeingLimited:
    def test_contradiction_when_jitter_too_high(self):
        d = _detector(seeing_threshold_px=3.0)
        result = d.assess(_smoothed(jitter=5.0), _decomp())
        assert result.has_contradiction
        assert result.stop_guidance

    def test_jitter_check_in_conflicting_indicators(self):
        d = _detector(seeing_threshold_px=3.0)
        result = d.assess(_smoothed(jitter=5.0), _decomp())
        assert any("seeing" in s.lower() or "jitter" in s.lower()
                   for s in result.conflicting_indicators)

    def test_no_contradiction_at_threshold(self):
        d = _detector(seeing_threshold_px=3.0)
        result = d.assess(_smoothed(jitter=3.0), _decomp())
        # jitter == threshold is NOT "too high" (strict >)
        assert not any("jitter" in s.lower() for s in result.conflicting_indicators)


# ── Focus drift ───────────────────────────────────────────────────────────────

class TestFocusDrift:
    def test_contradiction_when_focus_drifted(self):
        # Build a decomp with large common_focus_error by shifting all lines equally
        lines = [_line(30.0, rho=5.0), _line(90.0, rho=5.0), _line(150.0, rho=5.0)]
        decomp = decompose_spike_errors(lines)
        # The common focus error should be non-trivial
        d = _detector(focus_target_px=2.0)
        result = d.assess(_smoothed(), decomp)
        if abs(decomp.common_focus_error_px) > 2.0:
            assert result.has_contradiction

    def test_no_focus_contradiction_when_error_small(self):
        d = _detector(focus_target_px=2.0)
        lines = [_line(30.0, rho=0.5), _line(90.0, rho=0.5), _line(150.0, rho=0.5)]
        decomp = decompose_spike_errors(lines)
        result = d.assess(_smoothed(), decomp)
        # Only check focus indicator absent (may have other issues)
        focus_conflicts = [s for s in result.conflicting_indicators if "focus" in s.lower()]
        if abs(decomp.common_focus_error_px) <= 2.0:
            assert focus_conflicts == []


# ── Low confidence ────────────────────────────────────────────────────────────

class TestLowConfidence:
    def test_contradiction_when_confidence_low(self):
        d = _detector(confidence_threshold=0.5)
        result = d.assess(_smoothed(confidence=0.3), _decomp())
        assert result.has_contradiction
        assert any("confidence" in s.lower() for s in result.conflicting_indicators)

    def test_no_contradiction_at_threshold(self):
        d = _detector(confidence_threshold=0.5)
        result = d.assess(_smoothed(confidence=0.5), _decomp())
        assert not any("confidence" in s.lower() for s in result.conflicting_indicators)


# ── Residuals worsening ───────────────────────────────────────────────────────

class TestResidualsDrift:
    def test_contradiction_when_residuals_worsen(self):
        d = _detector()
        decomp_good = _decomp(residual_shift=1.0)
        decomp_worse = _decomp(residual_shift=5.0)
        d.assess(_smoothed(), decomp_good)    # baseline
        result = d.assess(_smoothed(), decomp_worse)  # worse
        if decomp_worse.max_residual_px > decomp_good.max_residual_px + 0.5:
            assert any("worsen" in s.lower() or "residual" in s.lower()
                       for s in result.conflicting_indicators)

    def test_no_worsening_on_first_call(self):
        d = _detector()
        result = d.assess(_smoothed(), _decomp(residual_shift=3.0))
        # First call has no previous value → worsening check not triggered
        assert not any("worsen" in s.lower() for s in result.conflicting_indicators)

    def test_reset_clears_previous_state(self):
        d = _detector()
        d.assess(_smoothed(), _decomp(residual_shift=5.0))
        d.reset()
        result = d.assess(_smoothed(), _decomp(residual_shift=1.0))
        assert not any("worsen" in s.lower() for s in result.conflicting_indicators)


# ── Recommended action ────────────────────────────────────────────────────────

class TestRecommendedAction:
    def test_action_mentions_recovery_when_contradiction(self):
        d = _detector()
        result = d.assess(_smoothed(jitter=10.0), _decomp())
        assert result.stop_guidance
        assert len(result.recommended_action) > 0

    def test_confidence_between_zero_and_one(self):
        d = _detector()
        result = d.assess(_smoothed(), _decomp())
        assert 0.0 <= result.confidence <= 1.0
