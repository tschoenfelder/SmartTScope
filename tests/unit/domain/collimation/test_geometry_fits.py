"""Tests for circle/ellipse fitting primitives — Phase 3, Task 3.4."""
from __future__ import annotations

import math

import numpy as np
import pytest

from smart_telescope.domain.collimation.models import CircleEllipseFit
from smart_telescope.domain.collimation.processing.geometry_fits import (
    compare_circle_centers,
    detect_clipping,
    extract_edge_points,
    fit_circle,
    fit_ellipse,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _circle_points(
    cx: float,
    cy: float,
    r: float,
    n: int = 64,
    noise: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Generate evenly spaced points on a circle with optional noise."""
    angles = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    x = cx + r * np.cos(angles)
    y = cy + r * np.sin(angles)
    if noise > 0.0:
        g = rng or np.random.default_rng(0)
        x += g.normal(0.0, noise, n)
        y += g.normal(0.0, noise, n)
    return np.column_stack([x, y])


def _ellipse_points(
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    angle_deg: float = 0.0,
    n: int = 64,
    noise: float = 0.0,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Generate evenly spaced points on an axis-aligned or rotated ellipse."""
    angles = np.linspace(0.0, 2 * math.pi, n, endpoint=False)
    x_local = rx * np.cos(angles)
    y_local = ry * np.sin(angles)
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    x = cx + cos_t * x_local - sin_t * y_local
    y = cy + sin_t * x_local + cos_t * y_local
    if noise > 0.0:
        g = rng or np.random.default_rng(1)
        x += g.normal(0.0, noise, n)
        y += g.normal(0.0, noise, n)
    return np.column_stack([x, y])


# ── fit_circle ────────────────────────────────────────────────────────────────

class TestFitCircle:
    def test_exact_circle(self):
        pts = _circle_points(100.0, 120.0, 50.0, n=64)
        fit = fit_circle(pts)
        assert fit.center_x == pytest.approx(100.0, abs=0.1)
        assert fit.center_y == pytest.approx(120.0, abs=0.1)
        assert fit.radius_x == pytest.approx(50.0, abs=0.1)
        assert fit.confidence > 0.95

    def test_noisy_circle(self):
        pts = _circle_points(200.0, 150.0, 80.0, n=100, noise=1.0)
        fit = fit_circle(pts)
        assert fit.center_x == pytest.approx(200.0, abs=2.0)
        assert fit.center_y == pytest.approx(150.0, abs=2.0)
        assert fit.radius_x == pytest.approx(80.0, abs=2.0)

    def test_small_circle(self):
        pts = _circle_points(10.0, 10.0, 5.0, n=32)
        fit = fit_circle(pts)
        assert fit.center_x == pytest.approx(10.0, abs=0.5)
        assert fit.radius_x == pytest.approx(5.0, abs=0.5)

    def test_radius_x_equals_radius_y(self):
        pts = _circle_points(50.0, 50.0, 30.0)
        fit = fit_circle(pts)
        assert fit.radius_x == pytest.approx(fit.radius_y, rel=1e-6)

    def test_degenerate_fewer_than_3_points(self):
        pts = np.array([[0.0, 0.0], [1.0, 0.0]])
        fit = fit_circle(pts)
        assert fit.confidence == 0.0

    def test_confidence_in_range(self):
        pts = _circle_points(50.0, 60.0, 25.0)
        fit = fit_circle(pts)
        assert 0.0 <= fit.confidence <= 1.0

    def test_three_points_exact(self):
        """Three non-collinear points uniquely determine a circle."""
        r = 40.0
        pts = np.array([
            [r, 0.0],
            [0.0, r],
            [-r, 0.0],
        ])
        fit = fit_circle(pts)
        assert fit.center_x == pytest.approx(0.0, abs=1.0)
        assert fit.radius_x == pytest.approx(r, abs=1.0)

    def test_partial_arc_still_fits(self):
        """A 120-degree arc should still produce a reasonable circle fit."""
        angles = np.linspace(0.0, 2 * math.pi / 3, 30)
        pts = np.column_stack([
            100.0 + 60.0 * np.cos(angles),
            100.0 + 60.0 * np.sin(angles),
        ])
        fit = fit_circle(pts)
        # Partial arc fit is less reliable — just check it doesn't crash
        # and produces a reasonable radius
        assert fit.radius_x == pytest.approx(60.0, abs=15.0)


# ── fit_ellipse ───────────────────────────────────────────────────────────────

class TestFitEllipse:
    def test_circle_as_ellipse(self):
        """A perfect circle should be detected as a near-circular ellipse."""
        pts = _circle_points(100.0, 100.0, 50.0, n=64)
        fit = fit_ellipse(pts)
        assert fit.center_x == pytest.approx(100.0, abs=1.0)
        assert fit.center_y == pytest.approx(100.0, abs=1.0)
        assert fit.is_circle  # radius_x ≈ radius_y

    def test_axis_aligned_ellipse(self):
        pts = _ellipse_points(150.0, 120.0, rx=80.0, ry=40.0, n=80)
        fit = fit_ellipse(pts)
        assert fit.center_x == pytest.approx(150.0, abs=2.0)
        assert fit.center_y == pytest.approx(120.0, abs=2.0)
        # Semi-axes: major ≈ 80, minor ≈ 40 (or swapped with angle)
        assert max(fit.radius_x, fit.radius_y) == pytest.approx(80.0, abs=3.0)
        assert min(fit.radius_x, fit.radius_y) == pytest.approx(40.0, abs=3.0)

    def test_noisy_ellipse(self):
        pts = _ellipse_points(100.0, 100.0, 70.0, 35.0, n=100, noise=1.5)
        fit = fit_ellipse(pts)
        assert fit.center_x == pytest.approx(100.0, abs=4.0)
        assert fit.center_y == pytest.approx(100.0, abs=4.0)

    def test_fewer_than_5_points_falls_back_to_circle(self):
        pts = _circle_points(50.0, 50.0, 20.0, n=4)
        fit = fit_ellipse(pts)
        # Should not crash; returns something (circle fallback)
        assert isinstance(fit, CircleEllipseFit)

    def test_confidence_in_range(self):
        pts = _ellipse_points(100.0, 100.0, 60.0, 30.0, n=64)
        fit = fit_ellipse(pts)
        assert 0.0 <= fit.confidence <= 1.0


# ── extract_edge_points ───────────────────────────────────────────────────────

class TestExtractEdgePoints:
    def _circle_mask(
        self,
        height: int = 100,
        width: int = 100,
        cy: float = 50.0,
        cx: float = 50.0,
        r: float = 30.0,
    ) -> np.ndarray:
        rr, cc = np.ogrid[:height, :width]
        return (rr - cy) ** 2 + (cc - cx) ** 2 <= r ** 2

    def test_empty_mask_returns_empty(self):
        mask = np.zeros((50, 50), dtype=bool)
        pts = extract_edge_points(mask)
        assert pts.shape == (0, 2)

    def test_full_mask_returns_border(self):
        mask = np.ones((50, 50), dtype=bool)
        pts = extract_edge_points(mask)
        # Border pixels = perimeter of the frame (but interior single-pixel edges)
        assert len(pts) > 0

    def test_circle_mask_edge_points_on_circle(self):
        mask = self._circle_mask(cy=50.0, cx=50.0, r=25.0)
        pts = extract_edge_points(mask)
        assert len(pts) > 10  # some points found
        # All returned points should be inside or very near the circle edge
        x, y = pts[:, 0], pts[:, 1]
        dist = np.sqrt((x - 50.0) ** 2 + (y - 50.0) ** 2)
        # Allow ±3 px tolerance (discrete pixels)
        assert np.all(dist >= 22.0)
        assert np.all(dist <= 28.0)

    def test_circle_fit_from_extracted_edge(self):
        """Edge points extracted from a disc mask should give a good circle fit."""
        mask = self._circle_mask(cy=60.0, cx=55.0, r=28.0)
        pts = extract_edge_points(mask)
        fit = fit_circle(pts)
        assert fit.center_x == pytest.approx(55.0, abs=1.5)
        assert fit.center_y == pytest.approx(60.0, abs=1.5)
        assert fit.radius_x == pytest.approx(28.0, abs=1.5)

    def test_output_dtype(self):
        mask = np.ones((10, 10), dtype=bool)
        pts = extract_edge_points(mask)
        assert pts.dtype == np.float64

    def test_columns_are_xy(self):
        """Column 0 = x (cols), column 1 = y (rows)."""
        mask = np.zeros((50, 50), dtype=bool)
        mask[10, 20] = True   # single isolated pixel
        pts = extract_edge_points(mask)
        assert len(pts) >= 1
        assert pts[0, 0] == pytest.approx(20.0)  # x = col
        assert pts[0, 1] == pytest.approx(10.0)  # y = row


# ── detect_clipping ───────────────────────────────────────────────────────────

class TestDetectClipping:
    def _fit(self, cx, cy, r) -> CircleEllipseFit:
        return CircleEllipseFit(
            center_x=cx, center_y=cy,
            radius_x=r, radius_y=r,
            confidence=1.0,
        )

    def test_centered_circle_not_clipped(self):
        fit = self._fit(100.0, 100.0, 30.0)
        assert detect_clipping(fit, 200, 200) is False

    def test_circle_touching_right_edge(self):
        # center=150, radius=60 → right edge at 210 > 200
        fit = self._fit(150.0, 100.0, 60.0)
        assert detect_clipping(fit, 200, 200) is True

    def test_circle_touching_top_edge(self):
        fit = self._fit(100.0, 10.0, 15.0)
        assert detect_clipping(fit, 200, 200) is True

    def test_circle_just_inside(self):
        fit = self._fit(100.0, 100.0, 97.0)  # 100-97=3 > margin=2
        assert detect_clipping(fit, 200, 200) is False

    def test_circle_exactly_at_margin(self):
        # center=50, r=48, margin=2 → left edge at 50-48=2 == margin
        # 2 < 2 is False → not clipped
        fit = self._fit(50.0, 50.0, 48.0)
        assert detect_clipping(fit, 200, 200) is False


# ── compare_circle_centers ────────────────────────────────────────────────────

class TestCompareCircleCenters:
    def _fit(self, cx, cy) -> CircleEllipseFit:
        return CircleEllipseFit(
            center_x=cx, center_y=cy,
            radius_x=10.0, radius_y=10.0,
            confidence=1.0,
        )

    def test_same_center(self):
        fit = self._fit(50.0, 80.0)
        assert compare_circle_centers(fit, fit) == pytest.approx(0.0)

    def test_horizontal_offset(self):
        a = self._fit(0.0, 0.0)
        b = self._fit(10.0, 0.0)
        assert compare_circle_centers(a, b) == pytest.approx(10.0)

    def test_diagonal_offset(self):
        a = self._fit(0.0, 0.0)
        b = self._fit(3.0, 4.0)
        assert compare_circle_centers(a, b) == pytest.approx(5.0)

    def test_symmetric(self):
        a = self._fit(10.0, 20.0)
        b = self._fit(40.0, 60.0)
        assert compare_circle_centers(a, b) == pytest.approx(
            compare_circle_centers(b, a)
        )
