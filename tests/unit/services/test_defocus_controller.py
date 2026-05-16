"""Tests for DefocusController — Collimation Phase 6, Task 6.2."""
from __future__ import annotations

from typing import Iterator

import numpy as np
import pytest

from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.domain.collimation.config import (
    FocuserCollimationConfig,
    FocuserDirection,
    RoughCollimationConfig,
)
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.services.collimation.defocus_controller import (
    DefocusController,
    DefocusResult,
)
from smart_telescope.services.collimation.focuser_control import CollimationFocuserControl


# ── Frame factories ───────────────────────────────────────────────────────────

def _make_donut_frame(
    ring_radius: float = 30.0,
    cx: float = 128.0,
    cy: float = 128.0,
    width: int = 256,
    height: int = 256,
    ring_width: float = 8.0,
    ring_adu: float = 5000.0,
    bg: float = 100.0,
) -> FitsFrame:
    """Synthetic annular ring (donut) frame."""
    rng = np.random.default_rng(42)
    data = rng.normal(bg, 10.0, (height, width)).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    ring_mask = np.abs(dist - ring_radius) < ring_width
    data[ring_mask] += ring_adu
    return FitsFrame(pixels=data.astype(np.float32), header={}, exposure_seconds=1.0)


def _make_star_frame(
    sigma: float = 3.0,
    cx: float = 128.0,
    cy: float = 128.0,
    width: int = 256,
    height: int = 256,
    peak_adu: float = 30_000.0,
    bg: float = 100.0,
) -> FitsFrame:
    rng = np.random.default_rng(7)
    data = rng.normal(bg, 10.0, (height, width)).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    data += (peak_adu * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))).astype(np.float32)
    return FitsFrame(pixels=data, header={}, exposure_seconds=1.0)


def _dim_frame(width: int = 256, height: int = 256) -> FitsFrame:
    rng = np.random.default_rng(3)
    return FitsFrame(
        pixels=rng.normal(100.0, 10.0, (height, width)).astype(np.float32),
        header={}, exposure_seconds=1.0,
    )


def _clipped_donut_frame(
    ring_radius: float = 40.0,
    cx: float = 3.0,
    cy: float = 128.0,
    width: int = 256,
    height: int = 256,
) -> FitsFrame:
    """Donut whose centroid is very close to the left edge → clipped."""
    return _make_donut_frame(ring_radius=ring_radius, cx=cx, cy=cy,
                             width=width, height=height)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _focuser_cfg(
    coarse_step: int = 200,
    defocus_direction: FocuserDirection = FocuserDirection.CLOCKWISE,
    increasing_value_direction: FocuserDirection = FocuserDirection.CLOCKWISE,
    max_single_step: int = 1000,
) -> FocuserCollimationConfig:
    return FocuserCollimationConfig(
        coarse_step=coarse_step,
        fine_step=20,
        defocus_direction=defocus_direction,
        final_approach_direction=FocuserDirection.CLOCKWISE,
        increasing_value_direction=increasing_value_direction,
        max_single_step=max_single_step,
        min_position=0,
        max_position=50000,
    )


def _rough_cfg(
    target_min: float = 0.25,
    target_max: float = 0.50,
) -> RoughCollimationConfig:
    return RoughCollimationConfig(
        target_donut_diameter_ratio_min=target_min,
        target_donut_diameter_ratio_max=target_max,
    )


def _ctrl(
    focuser_cfg: FocuserCollimationConfig | None = None,
    rough_cfg: RoughCollimationConfig | None = None,
    max_steps: int = 20,
) -> DefocusController:
    fcfg = focuser_cfg or _focuser_cfg()
    f = MockFocuser(available=True)
    f._position = 5000
    fc = CollimationFocuserControl(focuser=f, config=fcfg)
    return DefocusController(
        focuser=fc,
        focuser_cfg=fcfg,
        rough_cfg=rough_cfg or _rough_cfg(),
        bit_depth=16,
        max_steps=max_steps,
        settle_seconds=0.0,
    )


# ── DefocusResult ─────────────────────────────────────────────────────────────

class TestDefocusResult:
    def test_fields(self):
        r = DefocusResult(
            success=True, reason="at_target",
            estimated_radius_px=40.0,
            target_min_px=32.0, target_max_px=64.0,
            net_steps=400,
        )
        assert r.success is True
        assert r.reason == "at_target"
        assert r.estimated_radius_px == pytest.approx(40.0)
        assert r.target_min_px == pytest.approx(32.0)
        assert r.target_max_px == pytest.approx(64.0)
        assert r.net_steps == 400


# ── Target radius calculation ─────────────────────────────────────────────────

class TestTargetRadius:
    def test_target_radius_from_frame_dimensions(self):
        """target_min = 0.25*min_dim/2; target_max = 0.5*min_dim/2."""
        # 256×256 frame: min_dim=256, target_min=32, target_max=64
        ctrl = _ctrl(rough_cfg=_rough_cfg(0.25, 0.50))
        # Supply a donut that's already at target (radius ≈ 40 px → between 32 and 64)
        frame = _make_donut_frame(ring_radius=40.0, ring_width=6.0)
        result = ctrl.defocus(
            capture_frame=lambda: frame,
            frame_width=256, frame_height=256,
        )
        assert result.target_min_px == pytest.approx(32.0)
        assert result.target_max_px == pytest.approx(64.0)

    def test_rectangular_frame_uses_shorter_dimension(self):
        """For 400×256 frame, min_dim=256 → same targets as 256×256."""
        ctrl = _ctrl(rough_cfg=_rough_cfg(0.25, 0.50))
        frame = _make_donut_frame(ring_radius=40.0, ring_width=6.0, width=400, height=256)
        result = ctrl.defocus(
            capture_frame=lambda: frame,
            frame_width=400, frame_height=256,
        )
        assert result.target_min_px == pytest.approx(32.0)
        assert result.target_max_px == pytest.approx(64.0)


# ── at_target success ─────────────────────────────────────────────────────────

class TestAtTarget:
    def test_already_at_target_returns_success(self):
        """Donut is already in the 32–64 px range on first frame → success."""
        frame = _make_donut_frame(ring_radius=40.0, ring_width=8.0)
        ctrl = _ctrl()
        result = ctrl.defocus(
            capture_frame=lambda: frame,
            frame_width=256, frame_height=256,
        )
        assert result.success is True
        assert result.reason == "at_target"
        assert result.estimated_radius_px is not None
        assert result.net_steps == 0   # no moves needed

    def test_estimated_radius_within_target(self):
        frame = _make_donut_frame(ring_radius=40.0, ring_width=8.0)
        ctrl = _ctrl()
        result = ctrl.defocus(
            capture_frame=lambda: frame,
            frame_width=256, frame_height=256,
        )
        assert result.estimated_radius_px is not None
        # Effective radius should be in the rough target range
        assert result.target_min_px <= result.estimated_radius_px <= result.target_max_px


# ── Growing donut — reaches target after steps ────────────────────────────────

class TestGrowsToTarget:
    def test_reaches_target_after_defocus_steps(self):
        """Start with tiny blob, grow to target size after a few steps."""
        radii = [5.0, 10.0, 20.0, 40.0, 40.0, 40.0]
        idx = [0]

        def _capture():
            r = radii[min(idx[0], len(radii) - 1)]
            idx[0] += 1
            return _make_donut_frame(ring_radius=r, ring_width=6.0)

        ctrl = _ctrl(max_steps=10)
        result = ctrl.defocus(
            capture_frame=_capture,
            frame_width=256, frame_height=256,
        )
        assert result.success is True
        assert result.reason == "at_target"
        assert result.net_steps > 0   # had to move

    def test_net_steps_positive_when_defocusing(self):
        """Defocuser must have moved (net_steps != 0) to grow the donut."""
        radii = [5.0, 20.0, 40.0, 40.0, 40.0]
        idx = [0]

        def _capture():
            r = radii[min(idx[0], len(radii) - 1)]
            idx[0] += 1
            return _make_donut_frame(ring_radius=r, ring_width=6.0)

        ctrl = _ctrl(max_steps=10)
        result = ctrl.defocus(
            capture_frame=_capture,
            frame_width=256, frame_height=256,
        )
        assert result.net_steps != 0


# ── Clipping ──────────────────────────────────────────────────────────────────

class TestClipping:
    def test_clipped_donut_returns_clipped(self):
        """Donut touching the frame edge → reason='clipped'."""
        frame = _clipped_donut_frame(ring_radius=30.0, cx=3.0)
        ctrl = _ctrl()
        result = ctrl.defocus(
            capture_frame=lambda: frame,
            frame_width=256, frame_height=256,
        )
        assert result.success is False
        assert result.reason == "clipped"


# ── Star lost ────────────────────────────────────────────────────────────────

class TestStarLost:
    def test_dim_frame_returns_star_lost(self):
        ctrl = _ctrl()
        result = ctrl.defocus(
            capture_frame=lambda: _dim_frame(),
            frame_width=256, frame_height=256,
        )
        assert result.success is False
        assert result.reason == "star_lost"
        assert result.estimated_radius_px is None


# ── Max steps ────────────────────────────────────────────────────────────────

class TestMaxSteps:
    def test_returns_max_steps_when_donut_too_small(self):
        """Donut never reaches target → exhausts max_steps."""
        frame = _make_donut_frame(ring_radius=5.0, ring_width=3.0)
        ctrl = _ctrl(max_steps=3)
        result = ctrl.defocus(
            capture_frame=lambda: frame,
            frame_width=256, frame_height=256,
        )
        assert result.success is False
        assert result.reason == "max_steps"


# ── Cancellation ─────────────────────────────────────────────────────────────

class TestCancellation:
    def test_cancelled_returns_cancelled(self):
        frame = _make_donut_frame(ring_radius=5.0, ring_width=3.0)
        ctrl = _ctrl(max_steps=10)
        result = ctrl.defocus(
            capture_frame=lambda: frame,
            frame_width=256, frame_height=256,
            cancel_check=lambda: True,
        )
        assert result.success is False
        assert result.reason == "cancelled"

    def test_not_cancelled_when_check_is_false(self):
        frame = _make_donut_frame(ring_radius=40.0, ring_width=8.0)
        ctrl = _ctrl()
        result = ctrl.defocus(
            capture_frame=lambda: frame,
            frame_width=256, frame_height=256,
            cancel_check=lambda: False,
        )
        assert result.reason != "cancelled"
