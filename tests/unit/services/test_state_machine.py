"""Tests for CollimationStateMachine — COL-131."""
from __future__ import annotations

import pytest

from smart_telescope.services.collimation.state_machine import (
    TERMINAL_STATES,
    USER_WAIT_STATES,
    VALID_TRANSITIONS,
    CollimationState,
    CollimationStateMachine,
    InvalidTransitionError,
    STATE_INSTRUCTIONS,
)


# ── Initial state ─────────────────────────────────────────────────────────────

class TestInitialState:
    def test_starts_at_idle(self):
        sm = CollimationStateMachine()
        assert sm.state == CollimationState.IDLE

    def test_not_terminal_at_idle(self):
        sm = CollimationStateMachine()
        assert not sm.is_terminal()

    def test_not_waiting_for_user_at_idle(self):
        sm = CollimationStateMachine()
        assert not sm.is_waiting_for_user()

    def test_prev_state_is_none_at_start(self):
        sm = CollimationStateMachine()
        assert sm.prev_state is None


# ── Valid transitions ─────────────────────────────────────────────────────────

class TestValidTransitions:
    def test_idle_to_precheck(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        assert sm.state == CollimationState.PRECHECK

    def test_precheck_to_select_star(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        sm.transition(CollimationState.SELECT_STAR)
        assert sm.state == CollimationState.SELECT_STAR

    def test_precheck_to_failed(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        sm.transition(CollimationState.FAILED)
        assert sm.state == CollimationState.FAILED

    def test_guide_rough_to_measure_donut(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.GUIDE_ROUGH_COLLIMATION)
        sm.transition(CollimationState.MEASURE_DONUT)
        assert sm.state == CollimationState.MEASURE_DONUT

    def test_guide_rough_to_install_tribahtinov(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.GUIDE_ROUGH_COLLIMATION)
        sm.transition(CollimationState.INSTALL_TRIBAHTINOV)
        assert sm.state == CollimationState.INSTALL_TRIBAHTINOV

    def test_final_refocus_to_maskless_validation(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.FINAL_REFOCUS)
        sm.transition(CollimationState.MASKLESS_VALIDATION)
        assert sm.state == CollimationState.MASKLESS_VALIDATION

    def test_maskless_validation_to_complete(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.MASKLESS_VALIDATION)
        sm.transition(CollimationState.COMPLETE)
        assert sm.state == CollimationState.COMPLETE

    def test_maskless_validation_to_guide_fine(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.MASKLESS_VALIDATION)
        sm.transition(CollimationState.GUIDE_FINE_COLLIMATION)
        assert sm.state == CollimationState.GUIDE_FINE_COLLIMATION

    def test_complete_to_idle_via_reset(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.COMPLETE)
        sm.reset()
        assert sm.state == CollimationState.IDLE

    def test_failed_to_idle_via_reset(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        sm.transition(CollimationState.FAILED)
        sm.reset()
        assert sm.state == CollimationState.IDLE


# ── Invalid transitions ───────────────────────────────────────────────────────

class TestInvalidTransitions:
    def test_idle_to_acquire_star_raises(self):
        sm = CollimationStateMachine()
        with pytest.raises(InvalidTransitionError):
            sm.transition(CollimationState.ACQUIRE_STAR)

    def test_precheck_to_idle_raises(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        with pytest.raises(InvalidTransitionError):
            sm.transition(CollimationState.IDLE)

    def test_complete_direct_transition_raises(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.COMPLETE)
        with pytest.raises(InvalidTransitionError):
            sm.transition(CollimationState.PRECHECK)

    def test_error_message_includes_state_names(self):
        sm = CollimationStateMachine()
        try:
            sm.transition(CollimationState.FINE_FOCUS)
            assert False, "should have raised"
        except InvalidTransitionError as exc:
            msg = str(exc)
            assert "idle" in msg or "fine_focus" in msg


# ── Pause / resume ────────────────────────────────────────────────────────────

class TestPauseResume:
    def test_pause_stores_prev_state(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        sm.pause()
        assert sm.prev_state == CollimationState.PRECHECK

    def test_state_becomes_paused(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        sm.pause()
        assert sm.state == CollimationState.PAUSED

    def test_resume_restores_state(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        sm.pause()
        resumed = sm.resume()
        assert sm.state == CollimationState.PRECHECK
        assert resumed == CollimationState.PRECHECK

    def test_resume_clears_prev_state(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        sm.pause()
        sm.resume()
        assert sm.prev_state is None

    def test_pause_in_idle_raises(self):
        sm = CollimationStateMachine()
        with pytest.raises(InvalidTransitionError):
            sm.pause()

    def test_pause_in_terminal_raises(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.COMPLETE)
        with pytest.raises(InvalidTransitionError):
            sm.pause()

    def test_resume_when_not_paused_raises(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        with pytest.raises(InvalidTransitionError):
            sm.resume()


# ── Predicates ────────────────────────────────────────────────────────────────

class TestPredicates:
    def test_is_terminal_false_during_workflow(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        assert not sm.is_terminal()

    def test_is_terminal_true_at_complete(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.COMPLETE)
        assert sm.is_terminal()

    def test_is_terminal_true_at_failed(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        sm.transition(CollimationState.FAILED)
        assert sm.is_terminal()

    def test_is_waiting_true_at_select_star(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.SELECT_STAR)
        assert sm.is_waiting_for_user()

    def test_is_waiting_false_at_precheck(self):
        sm = CollimationStateMachine()
        sm.transition(CollimationState.PRECHECK)
        assert not sm.is_waiting_for_user()

    def test_terminal_states_set_contents(self):
        assert CollimationState.COMPLETE in TERMINAL_STATES
        assert CollimationState.FAILED in TERMINAL_STATES
        assert CollimationState.IDLE not in TERMINAL_STATES

    def test_user_wait_states_set_contents(self):
        assert CollimationState.SELECT_STAR in USER_WAIT_STATES
        assert CollimationState.GUIDE_ROUGH_COLLIMATION in USER_WAIT_STATES
        assert CollimationState.INSTALL_TRIBAHTINOV in USER_WAIT_STATES
        assert CollimationState.GUIDE_FINE_COLLIMATION in USER_WAIT_STATES
        assert CollimationState.MASKLESS_VALIDATION in USER_WAIT_STATES
        assert CollimationState.PRECHECK not in USER_WAIT_STATES


# ── Instructions ──────────────────────────────────────────────────────────────

class TestInstructions:
    def test_all_states_have_instruction(self):
        for state in CollimationState:
            assert sm_with_state(state).instruction(), f"{state.value} has no instruction"

    def test_idle_instruction_mentions_start(self):
        sm = CollimationStateMachine()
        assert "start" in sm.instruction().lower()

    def test_complete_instruction_is_non_empty(self):
        sm = CollimationStateMachine()
        _walk_to(sm, CollimationState.COMPLETE)
        assert len(sm.instruction()) > 5


# ── Helpers ───────────────────────────────────────────────────────────────────

def sm_with_state(state: CollimationState) -> CollimationStateMachine:
    sm = CollimationStateMachine()
    sm._state = state  # bypass transition validation for testing
    return sm


def _walk_to(sm: CollimationStateMachine, target: CollimationState) -> None:
    """Advance the state machine along the primary happy path to *target*."""
    path = [
        CollimationState.PRECHECK,
        CollimationState.SELECT_STAR,
        CollimationState.SLEW_TO_STAR,
        CollimationState.ACQUIRE_STAR,
        CollimationState.CENTER_STAR,
        CollimationState.AUTO_EXPOSURE,
        CollimationState.ROUGH_DEFOCUS,
        CollimationState.MAP_SCREWS_BY_OBSTRUCTION,
        CollimationState.MEASURE_DONUT,
        CollimationState.GUIDE_ROUGH_COLLIMATION,
        CollimationState.INSTALL_TRIBAHTINOV,
        CollimationState.MAP_MASK_SECTORS,
        CollimationState.FINE_FOCUS,
        CollimationState.MEASURE_SPIKES,
        CollimationState.GUIDE_FINE_COLLIMATION,
        CollimationState.FINAL_REFOCUS,
        CollimationState.MASKLESS_VALIDATION,
        CollimationState.COMPLETE,
    ]
    for state in path:
        if sm.state == target:
            return
        sm.transition(state)
    if sm.state != target:
        raise RuntimeError(f"Could not walk to {target.value}")
