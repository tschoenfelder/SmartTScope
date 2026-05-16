"""Tests for DonutOverlay builder — Collimation Phase 7, COL-072."""
from __future__ import annotations

import math

import pytest

from smart_telescope.domain.collimation.models import (
    CircleEllipseFit,
    DonutMeasurement,
)
from smart_telescope.services.collimation.donut_overlay import (
    DonutOverlay,
    ScrewMarker,
    build_donut_overlay,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _circle(cx: float, cy: float, r: float, confidence: float = 0.8) -> CircleEllipseFit:
    return CircleEllipseFit(
        center_x=cx, center_y=cy,
        radius_x=r, radius_y=r,
        angle_deg=0.0, confidence=confidence,
    )


def _measurement(
    outer_cx: float = 128.0,
    outer_cy: float = 128.0,
    outer_r: float = 40.0,
    inner_cx: float = 128.0,
    inner_cy: float = 128.0,
    inner_r: float = 20.0,
) -> DonutMeasurement:
    outer = _circle(outer_cx, outer_cy, outer_r)
    inner = _circle(inner_cx, inner_cy, inner_r)
    error_x = inner_cx - outer_cx
    error_y = inner_cy - outer_cy
    error_mag = math.hypot(error_x, error_y)
    error_ang = math.degrees(math.atan2(error_y, error_x))
    return DonutMeasurement(
        outer_ring=outer,
        inner_hole=inner,
        error_x_px=error_x,
        error_y_px=error_y,
        error_magnitude_px=error_mag,
        error_angle_deg=error_ang,
        confidence=(outer.confidence + inner.confidence) / 2.0,
    )


# ── ScrewMarker ───────────────────────────────────────────────────────────────

class TestScrewMarker:
    def test_fields(self):
        m = ScrewMarker(label="T1", position_x=128.0, position_y=50.0, angle_deg=90.0)
        assert m.label == "T1"
        assert m.position_x == pytest.approx(128.0)
        assert m.position_y == pytest.approx(50.0)
        assert m.angle_deg == pytest.approx(90.0)


# ── DonutOverlay fields ───────────────────────────────────────────────────────

class TestDonutOverlayFields:
    @pytest.fixture(autouse=True)
    def _overlay(self):
        self.m = _measurement(inner_cx=136.0)  # 8 px error right
        self.overlay = build_donut_overlay(self.m)

    def test_outer_center(self):
        assert self.overlay.outer_center_x == pytest.approx(128.0)
        assert self.overlay.outer_center_y == pytest.approx(128.0)

    def test_outer_radius(self):
        assert self.overlay.outer_radius_px == pytest.approx(40.0)

    def test_inner_center(self):
        assert self.overlay.inner_center_x == pytest.approx(136.0)
        assert self.overlay.inner_center_y == pytest.approx(128.0)

    def test_inner_radius(self):
        assert self.overlay.inner_radius_px == pytest.approx(20.0)

    def test_error_x(self):
        assert self.overlay.error_x_px == pytest.approx(8.0)

    def test_error_y(self):
        assert self.overlay.error_y_px == pytest.approx(0.0)

    def test_error_magnitude(self):
        assert self.overlay.error_magnitude_px == pytest.approx(8.0)

    def test_three_screws(self):
        assert len(self.overlay.screws) == 3

    def test_screw_labels(self):
        labels = [s.label for s in self.overlay.screws]
        assert labels == ["T1", "T2", "T3"]

    def test_confidence_propagated(self):
        assert self.overlay.confidence == pytest.approx(self.m.confidence)


# ── Traffic light ─────────────────────────────────────────────────────────────

class TestTrafficLight:
    def test_green_when_error_very_small(self):
        # error = 0.5 px, outer_r = 40 → ratio = 0.5/40 = 1.25 % < 2 %
        m = _measurement(inner_cx=128.5)
        overlay = build_donut_overlay(m)
        assert overlay.traffic_light == "green"

    def test_yellow_when_error_medium(self):
        # error = 3 px, outer_r = 40 → ratio = 7.5 % (between 2 % and 10 %)
        m = _measurement(inner_cx=131.0)
        overlay = build_donut_overlay(m)
        assert overlay.traffic_light == "yellow"

    def test_red_when_error_large(self):
        # error = 6 px, outer_r = 40 → ratio = 15 % > 10 %
        m = _measurement(inner_cx=134.0)
        overlay = build_donut_overlay(m)
        assert overlay.traffic_light == "red"

    def test_just_below_green_boundary(self):
        # error = 0.79 px → ratio = 1.975 % < 2 % → green
        m = _measurement(inner_cx=128.79)
        overlay = build_donut_overlay(m)
        assert overlay.traffic_light == "green"

    def test_just_above_green_boundary(self):
        # error = 0.82 px → ratio = 2.05 % > 2 % → yellow
        m = _measurement(inner_cx=128.82)
        overlay = build_donut_overlay(m)
        assert overlay.traffic_light == "yellow"

    def test_just_below_yellow_boundary(self):
        # error = 3.9 px → ratio = 9.75 % < 10 % → yellow
        m = _measurement(inner_cx=131.9)
        overlay = build_donut_overlay(m)
        assert overlay.traffic_light == "yellow"

    def test_just_above_yellow_boundary(self):
        # error = 4.1 px → ratio = 10.25 % > 10 % → red
        m = _measurement(inner_cx=132.1)
        overlay = build_donut_overlay(m)
        assert overlay.traffic_light == "red"


# ── Screw positions ───────────────────────────────────────────────────────────

class TestScrewPositions:
    def test_default_screw_angles(self):
        """Default angles: T1=90°, T2=210°, T3=330°."""
        m = _measurement()
        overlay = build_donut_overlay(m)
        expected_angles = [90.0, 210.0, 330.0]
        for screw, expected in zip(overlay.screws, expected_angles):
            assert screw.angle_deg == pytest.approx(expected)

    def test_screw_at_outer_radius_offset(self):
        """Screw markers are at outer_radius × 1.25 from the outer center."""
        m = _measurement()
        overlay = build_donut_overlay(m)
        expected_r = 40.0 * 1.25  # 50 px
        for screw in overlay.screws:
            dist = math.hypot(
                screw.position_x - overlay.outer_center_x,
                screw.position_y - overlay.outer_center_y,
            )
            assert dist == pytest.approx(expected_r, abs=0.5)

    def test_t1_at_90_degrees(self):
        """T1 at 90° → (cx + r*cos(90°), cy + r*sin(90°)) = (cx, cy + r)."""
        m = _measurement()
        overlay = build_donut_overlay(m)
        t1 = overlay.screws[0]
        expected_r = 40.0 * 1.25
        assert t1.position_x == pytest.approx(128.0, abs=0.5)
        assert t1.position_y == pytest.approx(128.0 + expected_r, abs=0.5)

    def test_custom_screw_angles(self):
        """Custom angles propagate correctly."""
        m = _measurement()
        overlay = build_donut_overlay(m, screw_angles_deg=(0.0, 120.0, 240.0))
        expected_angles = [0.0, 120.0, 240.0]
        for screw, expected in zip(overlay.screws, expected_angles):
            assert screw.angle_deg == pytest.approx(expected)

    def test_custom_t1_at_0_degrees(self):
        """T1 at 0° → (cx + r, cy)."""
        m = _measurement()
        overlay = build_donut_overlay(m, screw_angles_deg=(0.0, 120.0, 240.0))
        t1 = overlay.screws[0]
        expected_r = 40.0 * 1.25
        assert t1.position_x == pytest.approx(128.0 + expected_r, abs=0.5)
        assert t1.position_y == pytest.approx(128.0, abs=0.5)


# ── Error-angle propagation ───────────────────────────────────────────────────

class TestErrorAngle:
    def test_rightward_error_angle_zero(self):
        m = _measurement(inner_cx=132.0)  # error to the right
        overlay = build_donut_overlay(m)
        assert abs(overlay.error_angle_deg) < 1.0

    def test_downward_error_angle_90(self):
        m = _measurement(inner_cy=136.0)  # error downward (+y)
        overlay = build_donut_overlay(m)
        assert overlay.error_angle_deg == pytest.approx(90.0, abs=1.0)
