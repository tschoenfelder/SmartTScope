"""Tests for SpikeErrorDecomposition — Collimation Phase 11, COL-110."""
from __future__ import annotations

import math

import pytest

from smart_telescope.domain.bahtinov import SpikeLine
from smart_telescope.domain.collimation.processing.spike_decomposition import (
    SpikeErrorDecomposition,
    decompose_spike_errors,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _line(angle_deg: float, rho: float = 0.0) -> SpikeLine:
    """Normalised line through (cos θ, sin θ) direction at distance rho."""
    theta = math.radians(angle_deg)
    a = math.cos(theta)
    b = math.sin(theta)
    c = -rho    # line: a*x + b*y + c = 0, normal distance from origin = rho
    nrm = math.hypot(a, b)
    return SpikeLine(a=a/nrm, b=b/nrm, c=c/nrm, angle_deg=angle_deg, confidence=100.0)


def _three_concurrent_lines() -> list[SpikeLine]:
    """Three lines meeting at the origin — represents perfect collimation + focus."""
    return [_line(30.0), _line(90.0), _line(150.0)]


# ── SpikeErrorDecomposition fields ────────────────────────────────────────────

class TestSpikeErrorDecompositionFields:
    def test_fields(self):
        lines = _three_concurrent_lines()
        d = decompose_spike_errors(lines)
        assert hasattr(d, "sector_errors_px")
        assert hasattr(d, "common_focus_error_px")
        assert hasattr(d, "residuals_px")
        assert hasattr(d, "max_residual_px")
        assert hasattr(d, "rms_residual_px")

    def test_sector_errors_has_3_values(self):
        d = decompose_spike_errors(_three_concurrent_lines())
        assert len(d.sector_errors_px) == 3

    def test_residuals_has_3_values(self):
        d = decompose_spike_errors(_three_concurrent_lines())
        assert len(d.residuals_px) == 3


# ── Perfect collimation (concurrent lines at origin) ─────────────────────────

class TestPerfectCollimation:
    def test_all_errors_near_zero_when_concurrent(self):
        d = decompose_spike_errors(_three_concurrent_lines())
        for e in d.sector_errors_px:
            assert abs(e) < 1e-9

    def test_common_focus_error_near_zero(self):
        d = decompose_spike_errors(_three_concurrent_lines())
        assert abs(d.common_focus_error_px) < 1e-9

    def test_residuals_near_zero(self):
        d = decompose_spike_errors(_three_concurrent_lines())
        for r in d.residuals_px:
            assert abs(r) < 1e-9

    def test_max_residual_near_zero(self):
        d = decompose_spike_errors(_three_concurrent_lines())
        assert d.max_residual_px < 1e-9

    def test_rms_residual_near_zero(self):
        d = decompose_spike_errors(_three_concurrent_lines())
        assert d.rms_residual_px < 1e-9


# ── Concurrent at non-origin point (models "focus error at reference") ────────

class TestConcurrentAtNonOrigin:
    def _lines_through(self, px: float, py: float) -> list[SpikeLine]:
        """Three lines at 30°, 90°, 150° all passing through (px, py)."""
        result = []
        for angle in (30.0, 90.0, 150.0):
            theta = math.radians(angle)
            a, b = math.cos(theta), math.sin(theta)
            c = -(a * px + b * py)
            result.append(SpikeLine(a=a, b=b, c=c, angle_deg=angle, confidence=100.0))
        return result

    def test_errors_all_zero_when_concurrent(self):
        # Three lines passing through (5, 3) → all pairwise intersections = (5, 3)
        # → all errors = a_i*5 + b_i*3 + c_i = 0 (by construction)
        lines = self._lines_through(5.0, 3.0)
        d = decompose_spike_errors(lines)
        for e in d.sector_errors_px:
            assert abs(e) < 1e-9

    def test_residuals_zero_when_concurrent_at_any_point(self):
        lines = self._lines_through(10.0, -7.0)
        d = decompose_spike_errors(lines)
        for r in d.residuals_px:
            assert abs(r) < 1e-9

    def test_common_focus_zero_when_concurrent(self):
        lines = self._lines_through(3.0, 3.0)
        d = decompose_spike_errors(lines)
        assert abs(d.common_focus_error_px) < 1e-9


# ── Pure collimation error (one sector different) ─────────────────────────────

class TestPureCollimationError:
    def test_one_sector_has_larger_residual(self):
        # Lines 0 and 2 concurrent at origin; line 1 shifted → sector 1 residual ≠ 0
        lines = [_line(30.0), _line(90.0, rho=3.0), _line(150.0)]
        d = decompose_spike_errors(lines)
        # Sector 1 should have the largest |residual|
        assert d.worst_sector_index == 1

    def test_max_residual_positive(self):
        lines = [_line(30.0), _line(90.0, rho=3.0), _line(150.0)]
        d = decompose_spike_errors(lines)
        assert d.max_residual_px > 0.0

    def test_rms_residual_less_than_max(self):
        lines = [_line(30.0), _line(90.0, rho=3.0), _line(150.0)]
        d = decompose_spike_errors(lines)
        assert d.rms_residual_px <= d.max_residual_px


# ── Residual = error − common ──────────────────────────────────────────────────

class TestResidualMath:
    def test_residuals_sum_to_zero(self):
        # By construction: sum(residuals) = sum(errors - common) = 0
        lines = [_line(30.0, rho=1.0), _line(90.0, rho=3.0), _line(150.0)]
        d = decompose_spike_errors(lines)
        assert abs(sum(d.residuals_px)) < 1e-9

    def test_residual_equals_error_minus_common(self):
        lines = [_line(30.0, rho=1.0), _line(90.0, rho=3.0), _line(150.0)]
        d = decompose_spike_errors(lines)
        for i in range(3):
            expected = d.sector_errors_px[i] - d.common_focus_error_px
            assert d.residuals_px[i] == pytest.approx(expected)


# ── Error conditions ──────────────────────────────────────────────────────────

class TestErrors:
    def test_raises_for_fewer_than_3_lines(self):
        with pytest.raises(ValueError, match="Expected exactly 3"):
            decompose_spike_errors([_line(30.0), _line(90.0)])

    def test_raises_for_more_than_3_lines(self):
        with pytest.raises(ValueError, match="Expected exactly 3"):
            decompose_spike_errors([_line(30.0), _line(60.0), _line(90.0), _line(150.0)])
