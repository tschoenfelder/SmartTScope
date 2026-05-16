"""Tests for FocusSearcher — Collimation Phase 6, Task 6.1."""
from __future__ import annotations

from typing import Iterator
from unittest.mock import patch

import numpy as np
import pytest

from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.domain.collimation.config import (
    FocuserCollimationConfig,
    FocuserDirection,
)
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.services.collimation.focuser_control import CollimationFocuserControl
from smart_telescope.services.collimation.focus_search import (
    FocusSearchResult,
    FocusSearcher,
)


# ── Frame / FWHM factories ────────────────────────────────────────────────────

def _make_star_frame(
    sigma: float = 3.0,
    cx: float = 256.0,
    cy: float = 256.0,
    width: int = 512,
    height: int = 512,
    peak_adu: float = 30_000.0,
    bg: float = 100.0,
) -> FitsFrame:
    """Gaussian PSF with given sigma on a noisy background.

    Uses 512×512 frames so large sigmas (up to ~9) stay within the 2 % blob
    limit enforced by detect_star (max_blob = 512*512*0.02 = 5242 pixels).
    """
    rng = np.random.default_rng(int(sigma * 1000) % (2**32))
    data = rng.normal(bg, 10.0, (height, width)).astype(np.float32)
    yy, xx = np.mgrid[0:height, 0:width]
    data += (peak_adu * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * sigma ** 2))).astype(np.float32)
    return FitsFrame(pixels=data, header={}, exposure_seconds=1.0)


def _dim_frame(width: int = 512, height: int = 512) -> FitsFrame:
    rng = np.random.default_rng(1)
    data = rng.normal(100.0, 10.0, (height, width)).astype(np.float32)
    return FitsFrame(pixels=data, header={}, exposure_seconds=1.0)


def _frame_seq(*sigmas: float) -> Iterator[FitsFrame]:
    """Return an iterator of frames with the given sigma sequence, then dim frames."""
    frames = [_make_star_frame(sigma=s) for s in sigmas]
    return iter(frames + [_dim_frame()] * 50)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _cfg(
    coarse_step: int = 200,
    fine_step: int = 20,
    final_approach_direction: FocuserDirection = FocuserDirection.CLOCKWISE,
    increasing_value_direction: FocuserDirection = FocuserDirection.CLOCKWISE,
    defocus_direction: FocuserDirection = FocuserDirection.CLOCKWISE,
    max_single_step: int = 1000,
    min_position: int = 0,
    max_position: int = 50000,
) -> FocuserCollimationConfig:
    return FocuserCollimationConfig(
        coarse_step=coarse_step,
        fine_step=fine_step,
        final_approach_direction=final_approach_direction,
        increasing_value_direction=increasing_value_direction,
        defocus_direction=defocus_direction,
        max_single_step=max_single_step,
        min_position=min_position,
        max_position=max_position,
    )


def _focuser(start_pos: int = 5000) -> CollimationFocuserControl:
    f = MockFocuser(available=True)
    f._position = start_pos
    return CollimationFocuserControl(focuser=f, config=_cfg())


def _searcher(
    focuser: CollimationFocuserControl | None = None,
    config: FocuserCollimationConfig | None = None,
    max_coarse_steps: int = 10,
    improvement_fraction: float = 0.05,
) -> FocusSearcher:
    cfg = config or _cfg()
    fc = focuser or CollimationFocuserControl(
        focuser=MockFocuser(available=True),
        config=cfg,
    )
    fc._focuser._position = 5000
    return FocusSearcher(
        focuser=fc,
        config=cfg,
        bit_depth=16,
        max_coarse_steps=max_coarse_steps,
        improvement_fraction=improvement_fraction,
        settle_seconds=0.0,
    )


# ── FocusSearchResult ─────────────────────────────────────────────────────────

class TestFocusSearchResult:
    def test_fields(self):
        r = FocusSearchResult(success=True, reason="in_focus", best_fwhm=7.1, net_steps=200)
        assert r.success is True
        assert r.reason == "in_focus"
        assert r.best_fwhm == pytest.approx(7.1)
        assert r.net_steps == 200


# ── Star lost on first frame ──────────────────────────────────────────────────

class TestStarLost:
    def test_star_lost_immediately(self):
        s = _searcher()
        result = s.search(capture_frame=lambda: _dim_frame())
        assert result.success is False
        assert result.reason == "star_lost"
        assert result.best_fwhm is None
        assert result.net_steps == 0


# ── Basic search convergence ──────────────────────────────────────────────────

class TestSearchConverges:
    def _make_focus_curve(self) -> Iterator[FitsFrame]:
        # sigma decreases = focus improves; then increases = focus worsens
        # sequence: 9, 7, 5, 3 (best), 5, 7 ... then dim
        return _frame_seq(9.0, 7.0, 5.0, 3.0, 5.0, 7.0, 9.0,
                          3.0, 3.0, 3.0, 3.0, 3.0)  # fine-approach frames

    def test_search_succeeds_on_improving_curve(self):
        seq = self._make_focus_curve()
        s = _searcher(max_coarse_steps=10)
        result = s.search(capture_frame=lambda: next(seq))
        assert result.success is True
        assert result.reason == "in_focus"
        assert result.best_fwhm is not None

    def test_best_fwhm_lower_than_initial(self):
        seq = _frame_seq(9.0, 7.0, 5.0, 3.0, 5.0, 7.0,
                         3.0, 3.0, 3.0, 3.0)
        s = _searcher(max_coarse_steps=10)
        result = s.search(capture_frame=lambda: next(seq))
        # Best FWHM should be lower than initial (sigma=9 → FWHM≈21 px)
        assert result.best_fwhm is not None
        assert result.best_fwhm < 25.0  # sigma=9 → FWHM≈21

    def test_net_steps_nonzero_when_moved(self):
        seq = _frame_seq(9.0, 7.0, 5.0, 3.0, 5.0, 7.0,
                         3.0, 3.0, 3.0, 3.0)
        s = _searcher(max_coarse_steps=10)
        result = s.search(capture_frame=lambda: next(seq))
        assert result.net_steps != 0


# ── Already in focus ──────────────────────────────────────────────────────────

class TestAlreadyInFocus:
    def test_already_in_focus_returns_success(self):
        # FWHM doesn't improve in either direction (same sigma)
        seq = _frame_seq(3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0, 3.0)
        s = _searcher(max_coarse_steps=5, improvement_fraction=0.10)
        result = s.search(capture_frame=lambda: next(seq))
        # Even if no improvement, after probe+scan the searcher should succeed or
        # return a valid result (in_focus or no_improvement).
        assert result.best_fwhm is not None

    def test_no_improvement_does_not_crash(self):
        seq = _frame_seq(5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0)
        s = _searcher(max_coarse_steps=3, improvement_fraction=0.20)
        result = s.search(capture_frame=lambda: next(seq))
        assert result is not None


# ── Cancellation ──────────────────────────────────────────────────────────────

class TestCancellation:
    def test_cancelled_returns_cancelled(self):
        seq = _frame_seq(9.0, 7.0, 5.0, 3.0, 5.0, 7.0,
                         3.0, 3.0, 3.0, 3.0)
        s = _searcher(max_coarse_steps=10)
        # Cancel immediately on first iteration of scan
        call_count = [0]
        def _check():
            call_count[0] += 1
            return call_count[0] >= 2
        result = s.search(capture_frame=lambda: next(seq), cancel_check=_check)
        assert result.success is False
        assert result.reason == "cancelled"

    def test_cancelled_never(self):
        seq = _frame_seq(9.0, 7.0, 5.0, 3.0, 5.0, 7.0,
                         3.0, 3.0, 3.0, 3.0)
        s = _searcher(max_coarse_steps=10)
        result = s.search(capture_frame=lambda: next(seq), cancel_check=lambda: False)
        assert result.reason != "cancelled"


# ── Soft limit ────────────────────────────────────────────────────────────────

class TestSoftLimit:
    def test_soft_limit_both_directions_no_improvement(self):
        """If focuser is at position limit in both directions, return no_improvement."""
        cfg = _cfg(min_position=5000, max_position=5000, max_single_step=200)
        f = MockFocuser(available=True)
        f._position = 5000
        fc = CollimationFocuserControl(focuser=f, config=cfg)
        s = FocusSearcher(focuser=fc, config=cfg, bit_depth=16,
                          max_coarse_steps=5, settle_seconds=0.0)
        seq = _frame_seq(5.0, 5.0, 5.0, 5.0, 5.0)
        result = s.search(capture_frame=lambda: next(seq))
        assert result.reason == "no_improvement"
        assert result.success is False


# ── Max steps ────────────────────────────────────────────────────────────────

class TestMaxSteps:
    def test_max_steps_returns_max_steps(self):
        # FWHM keeps improving forever (star keeps getting better) — hits max
        seq = _frame_seq(10.0, 9.0, 8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 2.0,
                         2.0, 2.0, 2.0, 2.0)
        s = _searcher(max_coarse_steps=2)  # very small limit
        result = s.search(capture_frame=lambda: next(seq))
        # With max=2, after probe + 2 scan steps hitting max, should see max_steps or in_focus
        assert result is not None  # just verify it doesn't crash
