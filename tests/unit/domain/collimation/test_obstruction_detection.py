"""Tests for detect_obstruction — Collimation Phase 8, COL-080."""
from __future__ import annotations

import math

import numpy as np
import pytest

from smart_telescope.domain.collimation.processing.frame import normalize_frame
from smart_telescope.domain.collimation.processing.obstruction_detection import (
    ObstructionResult,
    detect_obstruction,
)
from smart_telescope.domain.frame import FitsFrame


# ── Frame factories ───────────────────────────────────────────────────────────

def _make_donut_frame(
    cx: float = 128.0,
    cy: float = 128.0,
    outer_r: float = 40.0,
    inner_r: float = 20.0,
    width: int = 256,
    height: int = 256,
    ring_adu: float = 5000.0,
    bg: float = 100.0,
    seed: int = 42,
) -> FitsFrame:
    rng  = np.random.default_rng(seed)
    data = rng.normal(bg, 10.0, (height, width)).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    bright = (dist <= outer_r) & (dist >= inner_r)
    data[bright] += ring_adu
    return FitsFrame(pixels=data, header={}, exposure_seconds=1.0)


def _add_shadow(
    ref: FitsFrame,
    shadow_cx: float,
    shadow_cy: float,
    shadow_r: float = 10.0,
    shadow_depth: float = 0.90,
    seed: int = 7,
) -> FitsFrame:
    """Return a copy of ref with a circular shadow added at (shadow_cx, shadow_cy).

    shadow_depth=0.90 means the shadow region is reduced to 10 % of original.
    """
    data = ref.pixels.copy()
    yy, xx = np.mgrid[0:data.shape[0], 0:data.shape[1]]
    dist = np.sqrt((xx - shadow_cx) ** 2 + (yy - shadow_cy) ** 2)
    mask = dist <= shadow_r
    data[mask] *= (1.0 - shadow_depth)
    return FitsFrame(pixels=data, header={}, exposure_seconds=1.0)


def _proc(frame: FitsFrame):
    return normalize_frame(frame, bit_depth=16)


# ── ObstructionResult fields ──────────────────────────────────────────────────

class TestObstructionResult:
    def test_fields(self):
        r = ObstructionResult(
            shadow_center_x=160.0,
            shadow_center_y=128.0,
            angle_deg=0.0,
            shadow_area_px=50,
            confidence=0.9,
        )
        assert r.shadow_center_x == pytest.approx(160.0)
        assert r.shadow_center_y == pytest.approx(128.0)
        assert r.angle_deg == pytest.approx(0.0)
        assert r.shadow_area_px == 50
        assert r.confidence == pytest.approx(0.9)


# ── No shadow ─────────────────────────────────────────────────────────────────

class TestNoShadow:
    def test_identical_frames_returns_none(self):
        ref = _make_donut_frame(seed=42)
        result = detect_obstruction(
            _proc(ref), _proc(ref),
            reference_center_x=128.0, reference_center_y=128.0,
        )
        assert result is None

    def test_pure_noise_frames_returns_none(self):
        ref = _make_donut_frame(seed=42)
        cur = _make_donut_frame(seed=99)   # different noise, no shadow
        result = detect_obstruction(
            _proc(ref), _proc(cur),
            reference_center_x=128.0, reference_center_y=128.0,
        )
        assert result is None

    def test_tiny_shadow_below_min_area_returns_none(self):
        """Shadow smaller than min_shadow_px is rejected."""
        ref = _make_donut_frame(seed=42)
        # Shadow of radius 1 → area ≈ 3 px (below default min of 20)
        cur = _add_shadow(ref, shadow_cx=165.0, shadow_cy=128.0, shadow_r=1.0)
        result = detect_obstruction(
            _proc(ref), _proc(cur),
            reference_center_x=128.0, reference_center_y=128.0,
            min_shadow_px=20,
        )
        assert result is None


# ── Shadow detected ───────────────────────────────────────────────────────────

class TestShadowDetected:
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.ref = _make_donut_frame(seed=42)
        # Shadow on the right side of the ring (at outer_r from center)
        self.shadow_cx = 165.0
        self.shadow_cy = 128.0
        cur = _add_shadow(self.ref, self.shadow_cx, self.shadow_cy, shadow_r=10.0)
        self.result = detect_obstruction(
            _proc(self.ref), _proc(cur),
            reference_center_x=128.0, reference_center_y=128.0,
        )

    def test_result_not_none(self):
        assert self.result is not None

    def test_shadow_area_positive(self):
        assert self.result.shadow_area_px >= 20

    def test_shadow_center_x_approximate(self):
        assert abs(self.result.shadow_center_x - self.shadow_cx) < 5.0

    def test_shadow_center_y_approximate(self):
        assert abs(self.result.shadow_center_y - self.shadow_cy) < 5.0

    def test_confidence_above_zero(self):
        assert self.result.confidence > 0.0


# ── Angle accuracy ────────────────────────────────────────────────────────────

class TestAngleAccuracy:
    def _make_result(self, shadow_cx, shadow_cy, ref_cx=128.0, ref_cy=128.0):
        ref = _make_donut_frame(seed=42, outer_r=40.0)
        cur = _add_shadow(ref, shadow_cx, shadow_cy, shadow_r=10.0)
        return detect_obstruction(
            _proc(ref), _proc(cur),
            reference_center_x=ref_cx, reference_center_y=ref_cy,
        )

    def test_shadow_right_gives_angle_near_zero(self):
        # Shadow at (165, 128), center at (128, 128) → angle ≈ 0°
        result = self._make_result(shadow_cx=165.0, shadow_cy=128.0)
        assert result is not None
        assert abs(result.angle_deg) < 20.0

    def test_shadow_left_gives_angle_near_180(self):
        # Shadow at (91, 128) → angle ≈ ±180°
        result = self._make_result(shadow_cx=91.0, shadow_cy=128.0)
        assert result is not None
        assert abs(abs(result.angle_deg) - 180.0) < 25.0

    def test_shadow_below_gives_positive_angle(self):
        # Shadow at (128, 165) → angle ≈ +90° (downward in image)
        result = self._make_result(shadow_cx=128.0, shadow_cy=165.0)
        assert result is not None
        assert result.angle_deg > 45.0

    def test_shadow_above_gives_negative_angle(self):
        # Shadow at (128, 91) → angle ≈ −90°
        result = self._make_result(shadow_cx=128.0, shadow_cy=91.0)
        assert result is not None
        assert result.angle_deg < -45.0


# ── Confidence ────────────────────────────────────────────────────────────────

class TestConfidence:
    def test_high_confidence_for_strong_shadow(self):
        """A deep shadow (90 % darkening) should give high confidence."""
        ref = _make_donut_frame(seed=42)
        cur = _add_shadow(ref, shadow_cx=165.0, shadow_cy=128.0,
                          shadow_r=12.0, shadow_depth=0.90)
        result = detect_obstruction(
            _proc(ref), _proc(cur),
            reference_center_x=128.0, reference_center_y=128.0,
        )
        assert result is not None
        assert result.confidence > 0.5

    def test_confidence_bounded_at_one(self):
        ref = _make_donut_frame(seed=42)
        cur = _add_shadow(ref, 165.0, 128.0, shadow_r=15.0, shadow_depth=1.0)
        result = detect_obstruction(
            _proc(ref), _proc(cur),
            reference_center_x=128.0, reference_center_y=128.0,
        )
        assert result is not None
        assert result.confidence <= 1.0
