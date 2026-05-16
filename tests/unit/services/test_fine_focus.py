"""Tests for FineFocusController — Collimation Phase 11, COL-111."""
from __future__ import annotations

import pytest

from smart_telescope.services.collimation.fine_focus import (
    FineFocusController,
    FineFocusResult,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _controller(**kwargs) -> FineFocusController:
    defaults = dict(
        target_px=1.0,
        coarse_step=50,
        fine_step=10,
        coarse_threshold_px=5.0,
        max_steps=20,
        settle_seconds=0.0,
        final_approach_direction=1,
    )
    defaults.update(kwargs)
    return FineFocusController(**defaults)


def _seq(*errors: float | None):
    """Provide a get_error callable from a sequence; last value repeats forever."""
    idx = [0]
    values = list(errors)

    def get():
        v = values[min(idx[0], len(values) - 1)]
        idx[0] += 1
        return v

    return get


def _moves_recorder():
    moves = []
    def move(step: int) -> None:
        moves.append(step)
    return move, moves


# ── FineFocusResult fields ────────────────────────────────────────────────────

class TestFineFocusResultFields:
    def test_fields(self):
        r = FineFocusResult(
            reason="converged", initial_error_px=10.0, final_error_px=0.5,
            steps_taken=3, frame_count=4,
        )
        assert r.reason == "converged"
        assert r.initial_error_px == pytest.approx(10.0)
        assert r.final_error_px   == pytest.approx(0.5)
        assert r.steps_taken      == 3
        assert r.frame_count      == 4


# ── Convergence ───────────────────────────────────────────────────────────────

class TestConvergence:
    def test_converges_when_error_below_target(self):
        ctrl = _controller()
        result = ctrl.focus(_seq(10.0, 5.0, 2.0, 0.5), lambda s: None)
        assert result.reason == "converged"

    def test_final_error_below_target(self):
        ctrl = _controller(target_px=1.0)
        result = ctrl.focus(_seq(10.0, 5.0, 0.5), lambda s: None)
        assert result.final_error_px < 1.0

    def test_initial_error_recorded(self):
        ctrl = _controller()
        result = ctrl.focus(_seq(8.0, 0.5), lambda s: None)
        assert result.initial_error_px == pytest.approx(8.0)

    def test_frame_count_increments(self):
        ctrl = _controller()
        result = ctrl.focus(_seq(5.0, 2.0, 0.5), lambda s: None)
        assert result.frame_count >= 2


# ── Star lost ─────────────────────────────────────────────────────────────────

class TestStarLost:
    def test_star_lost_on_first_call(self):
        ctrl = _controller()
        result = ctrl.focus(_seq(None), lambda s: None)
        assert result.reason == "star_lost"
        assert result.final_error_px is None

    def test_star_lost_initial_error_zero_when_first_call_lost(self):
        ctrl = _controller()
        result = ctrl.focus(_seq(None), lambda s: None)
        assert result.initial_error_px == pytest.approx(0.0)

    def test_star_lost_after_some_steps(self):
        ctrl = _controller()
        result = ctrl.focus(_seq(5.0, 3.0, None), lambda s: None)
        assert result.reason == "star_lost"
        assert result.frame_count == 3


# ── Cancellation ──────────────────────────────────────────────────────────────

class TestCancellation:
    def test_cancelled_returns_cancelled(self):
        ctrl = _controller()
        result = ctrl.focus(_seq(10.0, 8.0, 6.0), lambda s: None,
                            cancel_check=lambda: True)
        assert result.reason == "cancelled"

    def test_not_cancelled_when_check_false(self):
        ctrl = _controller()
        result = ctrl.focus(_seq(0.5), lambda s: None,
                            cancel_check=lambda: False)
        assert result.reason == "converged"


# ── Max steps ─────────────────────────────────────────────────────────────────

class TestMaxSteps:
    def test_max_steps_when_not_converging(self):
        ctrl = _controller(max_steps=3, target_px=0.01)
        # errors stay far from target
        result = ctrl.focus(_seq(10.0, 9.0, 8.0, 7.0), lambda s: None)
        assert result.reason == "max_steps"
        assert result.steps_taken <= 3

    def test_frame_count_at_max(self):
        ctrl = _controller(max_steps=3, target_px=0.01)
        result = ctrl.focus(_seq(10.0, 9.0, 8.0, 7.0), lambda s: None)
        assert result.frame_count <= 4  # initial + max_steps measurements


# ── Step sizes ────────────────────────────────────────────────────────────────

class TestStepSizes:
    def test_coarse_step_used_far_from_target(self):
        ctrl = _controller(coarse_step=50, fine_step=10, coarse_threshold_px=3.0)
        mover, moves = _moves_recorder()
        # Error starts far from threshold; should use coarse_step
        ctrl.focus(_seq(10.0, 6.0, 0.5), mover)
        # First move should be coarse (50)
        assert abs(moves[0]) == 50

    def test_fine_step_used_near_target(self):
        ctrl = _controller(coarse_step=50, fine_step=10, coarse_threshold_px=5.0)
        mover, moves = _moves_recorder()
        # Error starts within coarse threshold (3.0 < 5.0) → fine step
        ctrl.focus(_seq(3.0, 0.5), mover)
        # All moves should be fine_step
        for m in moves:
            assert abs(m) == 10

    def test_negative_error_causes_positive_step(self):
        # error < 0 → direction = +1 → step positive
        ctrl = _controller(coarse_threshold_px=1.0, fine_step=10)
        mover, moves = _moves_recorder()
        ctrl.focus(_seq(-3.0, 0.0, 0.5), mover)
        assert moves[0] > 0

    def test_positive_error_causes_negative_step(self):
        # error > 0 → direction = -1 → step negative
        ctrl = _controller(coarse_threshold_px=1.0, fine_step=10)
        mover, moves = _moves_recorder()
        ctrl.focus(_seq(3.0, 0.0, 0.5), mover)
        assert moves[0] < 0


# ── Final approach direction ───────────────────────────────────────────────────

class TestFinalApproach:
    def test_overshoot_inserted_when_wrong_side(self):
        # final_approach_direction = -1 (CCW / negative steps)
        # Error starts at -2.0 (within coarse threshold), natural direction = +1 (CW)
        # → overshoot: one step of +fine_step (opposite to final_dir)
        ctrl = _controller(
            final_approach_direction=-1,
            coarse_threshold_px=5.0,
            fine_step=10,
            target_px=1.0,
        )
        mover, moves = _moves_recorder()
        # after overshoot error will be positive; then approach with negative steps
        ctrl.focus(_seq(-2.0, -3.0, 0.5), mover)
        # First move is the overshoot: direction opposite to final_dir (+1 direction = positive)
        assert moves[0] > 0

    def test_no_overshoot_when_correct_side(self):
        # final_approach_direction = 1, error = -3.0 → natural dir = +1 = final → no overshoot
        ctrl = _controller(
            final_approach_direction=1,
            coarse_threshold_px=5.0,
            fine_step=10,
            target_px=1.0,
        )
        mover, moves = _moves_recorder()
        ctrl.focus(_seq(-3.0, 0.5), mover)
        # No extra overshoot step; first move is the natural correction
        assert len(moves) == 1
        assert moves[0] > 0
