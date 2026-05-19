"""Tests for FWHMFocusController — Collimation Phase 12, COL-120."""
from __future__ import annotations

import pytest

from smart_telescope.services.collimation.fwhm_focus import (
    FWHMFocusController,
    MasklessFocusResult,
)


# ── FWHM sequence helpers ─────────────────────────────────────────────────────

def _constant(value):
    """get_fwhm that always returns the same value."""
    def _f():
        return value
    return _f


def _sequence(*values):
    """get_fwhm returning successive values from a list (None = star lost)."""
    it = iter(values)
    def _f():
        return next(it, None)
    return _f


def _noop_move(steps: int) -> None:
    pass


# ── MasklessFocusResult fields ────────────────────────────────────────────────

class TestMasklessFocusResultFields:
    def test_has_all_fields(self):
        r = MasklessFocusResult(
            reason="converged", quality="excellent",
            initial_fwhm_px=3.0, best_fwhm_px=1.5, final_fwhm_px=1.6,
            steps_taken=5, frame_count=8,
        )
        assert r.reason == "converged"
        assert r.quality == "excellent"
        assert r.initial_fwhm_px == 3.0
        assert r.best_fwhm_px == 1.5
        assert r.final_fwhm_px == 1.6
        assert r.steps_taken == 5
        assert r.frame_count == 8


# ── Star lost on first measurement ───────────────────────────────────────────

class TestStarLostImmediate:
    def test_returns_star_lost_reason(self):
        ctrl = FWHMFocusController()
        result = ctrl.focus(get_fwhm=_constant(None), move_focuser=_noop_move)
        assert result.reason == "star_lost"
        assert result.quality == "failed"

    def test_initial_fwhm_is_none(self):
        ctrl = FWHMFocusController()
        result = ctrl.focus(get_fwhm=_constant(None), move_focuser=_noop_move)
        assert result.initial_fwhm_px is None

    def test_one_frame_taken(self):
        ctrl = FWHMFocusController()
        result = ctrl.focus(get_fwhm=_constant(None), move_focuser=_noop_move)
        assert result.frame_count == 1

    def test_zero_steps_taken(self):
        ctrl = FWHMFocusController()
        result = ctrl.focus(get_fwhm=_constant(None), move_focuser=_noop_move)
        assert result.steps_taken == 0


# ── Probe finds forward direction ─────────────────────────────────────────────

class TestProbeForward:
    def _make_ctrl(self):
        return FWHMFocusController(
            excellent_fwhm_px=2.0, good_fwhm_px=4.0,
            coarse_step=100, fine_step=10,
            max_coarse_steps=5, max_consecutive_no_improve=2,
            improvement_fraction=0.05,
        )

    def test_converges_forward(self):
        # initial=8, fwd probe=7 (improved) → scan finds 3.0 as best → converge
        ctrl = self._make_ctrl()
        values = [8.0, 7.0, 6.0, 5.0, 4.0, 3.0, 3.1, 3.2, 3.0]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.reason == "converged"

    def test_quality_excellent_when_best_fwhm_below_threshold(self):
        ctrl = FWHMFocusController(excellent_fwhm_px=2.0, good_fwhm_px=4.0,
                                    coarse_step=100, fine_step=10,
                                    max_coarse_steps=5, max_consecutive_no_improve=2,
                                    improvement_fraction=0.05)
        # probe forward improves, scan quickly finds 1.5
        values = [8.0, 7.5, 1.5, 1.6, 1.7, 1.5]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.quality == "excellent"

    def test_quality_good_when_between_thresholds(self):
        ctrl = FWHMFocusController(excellent_fwhm_px=2.0, good_fwhm_px=4.0,
                                    coarse_step=100, fine_step=10,
                                    max_coarse_steps=5, max_consecutive_no_improve=2,
                                    improvement_fraction=0.05)
        # probe forward improves, best=3.0 → "good"
        values = [8.0, 7.5, 3.0, 3.1, 3.2, 3.0]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.quality == "good"

    def test_quality_poor_when_above_good_threshold(self):
        ctrl = FWHMFocusController(excellent_fwhm_px=2.0, good_fwhm_px=4.0,
                                    coarse_step=100, fine_step=10,
                                    max_coarse_steps=5, max_consecutive_no_improve=2,
                                    improvement_fraction=0.05)
        # probe improves, best stays at 5.0 → "poor"
        values = [8.0, 7.5, 5.0, 5.1, 5.2, 5.0]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.quality == "poor"


# ── Probe finds backward direction ────────────────────────────────────────────

class TestProbeBackward:
    def test_converges_backward(self):
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10,
            max_coarse_steps=5, max_consecutive_no_improve=2,
            improvement_fraction=0.05,
        )
        # initial=8, fwd probe=8.5 (no improvement), bwd=7.0 (improved) → direction=-1
        values = [8.0, 8.5, 7.0, 6.0, 5.5, 5.4, 5.4, 5.4]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.reason == "converged"

    def test_initial_fwhm_recorded(self):
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10,
            max_coarse_steps=5, max_consecutive_no_improve=2,
            improvement_fraction=0.05,
        )
        values = [8.0, 8.5, 7.0, 6.0, 5.4, 5.4, 5.4]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.initial_fwhm_px == pytest.approx(8.0)


# ── No improving direction found (max_steps) ─────────────────────────────────

class TestMaxSteps:
    def test_max_steps_when_neither_direction_improves(self):
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10,
            improvement_fraction=0.05,
        )
        # initial=8, fwd=8.5 (no better), bwd=8.3 (no better → max_steps)
        values = [8.0, 8.5, 8.3]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.reason == "max_steps"
        assert result.quality == "failed"

    def test_max_steps_returns_initial_as_final(self):
        ctrl = FWHMFocusController(
            coarse_step=100, improvement_fraction=0.05,
        )
        values = [8.0, 8.5, 8.3]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.final_fwhm_px == pytest.approx(8.0)


# ── Cancellation ──────────────────────────────────────────────────────────────

class TestCancellation:
    def test_cancel_during_scan(self):
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10,
            max_coarse_steps=10, max_consecutive_no_improve=3,
            improvement_fraction=0.05,
        )
        cancel_count = [0]
        def cancel():
            cancel_count[0] += 1
            return cancel_count[0] >= 3  # cancel on 3rd scan step check

        # probe improves forward, then scan: cancel triggers
        values = [8.0, 7.5, 7.0, 6.5, 6.0, 5.5, 5.0, 5.0]
        result = ctrl.focus(get_fwhm=_sequence(*values),
                            move_focuser=_noop_move, cancel_check=cancel)
        assert result.reason == "cancelled"
        assert result.quality == "failed"


# ── Star lost during probe ────────────────────────────────────────────────────

class TestStarLostDuringProbe:
    def test_star_lost_on_forward_probe(self):
        ctrl = FWHMFocusController(coarse_step=100, improvement_fraction=0.05)
        values = [8.0, None]  # initial ok, probe fwd = lost
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.reason == "star_lost"
        assert result.final_fwhm_px is None

    def test_star_lost_on_backward_probe(self):
        ctrl = FWHMFocusController(coarse_step=100, improvement_fraction=0.05)
        values = [8.0, 8.5, None]  # initial ok, fwd no improve, bwd=lost
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.reason == "star_lost"
        assert result.final_fwhm_px is None


# ── Star lost during scan ─────────────────────────────────────────────────────

class TestStarLostDuringScan:
    def test_star_lost_mid_scan(self):
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10,
            max_coarse_steps=5, max_consecutive_no_improve=2,
            improvement_fraction=0.05,
        )
        # probe fwd ok, scan step 1 ok, scan step 2 = lost
        values = [8.0, 7.5, 7.0, None]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.reason == "star_lost"
        assert result.quality == "failed"


# ── Steps and frames accounting ──────────────────────────────────────────────

class TestStepAccounting:
    def test_steps_taken_is_positive(self):
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10,
            max_coarse_steps=3, max_consecutive_no_improve=2,
            improvement_fraction=0.05,
        )
        values = [8.0, 7.0, 6.0, 5.5, 5.6, 5.5]
        result = ctrl.focus(get_fwhm=_sequence(*values), move_focuser=_noop_move)
        assert result.steps_taken > 0

    def test_frame_count_matches_get_fwhm_calls(self):
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10,
            max_coarse_steps=3, max_consecutive_no_improve=2,
            improvement_fraction=0.05,
        )
        call_count = [0]
        def counted_fwhm():
            call_count[0] += 1
            seq = [8.0, 7.0, 6.0, 5.5, 5.6, 5.5, 5.5]
            idx = call_count[0] - 1
            return seq[idx] if idx < len(seq) else 5.5
        result = ctrl.focus(get_fwhm=counted_fwhm, move_focuser=_noop_move)
        assert result.frame_count == call_count[0]

    def test_move_calls_recorded(self):
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10,
            max_coarse_steps=3, max_consecutive_no_improve=2,
            improvement_fraction=0.05,
        )
        moves = []
        values = [8.0, 7.0, 6.0, 5.5, 5.6, 5.5]
        ctrl.focus(get_fwhm=_sequence(*values),
                   move_focuser=lambda s: moves.append(s))
        assert len(moves) == 5  # probe(+100) + scan×2 + backtrack + (no overshoot: same dir)


# ── Final approach overshoot ──────────────────────────────────────────────────

class TestFinalApproachOvershoot:
    def test_overshoot_inserted_when_direction_differs(self):
        """Scan goes backward (−1); final_approach_direction=+1 → expect overshoot."""
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10, max_coarse_steps=3,
            max_consecutive_no_improve=2, improvement_fraction=0.05,
            final_approach_direction=1,
        )
        moves = []
        # initial=8, fwd=8.5 (no improve), bwd=7.0 (improve → dir=-1)
        # scan: 6.5, 6.0, 6.1(no improve), 6.2(no improve) → stop → backtrack → overshoot
        values = [8.0, 8.5, 7.0, 6.5, 6.0, 6.1, 6.2, 6.0]
        ctrl.focus(get_fwhm=_sequence(*values),
                   move_focuser=lambda s: moves.append(s))
        # Last two moves before final measurement should be −fine then +fine
        overshoot_pair = moves[-2:]
        assert overshoot_pair == [-10, 10]

    def test_no_overshoot_when_direction_matches(self):
        """Scan goes forward (+1); final_approach_direction=+1 → no overshoot."""
        ctrl = FWHMFocusController(
            coarse_step=100, fine_step=10, max_coarse_steps=3,
            max_consecutive_no_improve=2, improvement_fraction=0.05,
            final_approach_direction=1,
        )
        moves = []
        # probe fwd improves → dir=+1, then scan 2 steps, then 2 non-improve → stop
        values = [8.0, 7.0, 6.0, 5.5, 5.6, 5.7, 5.5]
        ctrl.focus(get_fwhm=_sequence(*values),
                   move_focuser=lambda s: moves.append(s))
        # no overshoot pair at end
        if len(moves) >= 2:
            assert not (moves[-2] == -10 and moves[-1] == 10)
