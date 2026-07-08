"""Unit tests for the top-level ObservingStateMachine (smarttscope_requirements_full.md §6-7)."""

from __future__ import annotations

from smart_telescope.domain.observing_state import (
    Guards,
    Intent,
    ObservingInput,
    ObservingPhase,
    ObservingStateMachine,
)

P = ObservingPhase
IT = Intent


def _inp(phase: ObservingPhase, intent: Intent | None = None, **guard_kwargs) -> ObservingInput:
    return ObservingInput(phase=phase, intent=intent, guards=Guards(**guard_kwargs))


class TestBootstrap:
    def test_bootstrap_always_advances(self) -> None:
        fsm = ObservingStateMachine()
        assert fsm.next(_inp(P.BOOTSTRAP)) == P.WAIT_CONTEXT_CONFIRMATION
        assert fsm.next(_inp(P.BOOTSTRAP, IT.CONFIRM_CONTEXT)) == P.WAIT_CONTEXT_CONFIRMATION


class TestWaitContextConfirmation:
    def test_confirm_with_guard_true_advances(self) -> None:
        fsm = ObservingStateMachine()
        inp = _inp(P.WAIT_CONTEXT_CONFIRMATION, IT.CONFIRM_CONTEXT, g1_context_confirmed=True)
        assert fsm.next(inp) == P.WAIT_HOME_CONFIRMATION

    def test_confirm_without_guard_stays(self) -> None:
        fsm = ObservingStateMachine()
        inp = _inp(P.WAIT_CONTEXT_CONFIRMATION, IT.CONFIRM_CONTEXT, g1_context_confirmed=False)
        assert fsm.next(inp) == P.WAIT_CONTEXT_CONFIRMATION

    def test_confirm_with_unknown_guard_stays(self) -> None:
        fsm = ObservingStateMachine()
        inp = _inp(P.WAIT_CONTEXT_CONFIRMATION, IT.CONFIRM_CONTEXT)
        assert fsm.next(inp) == P.WAIT_CONTEXT_CONFIRMATION

    def test_wrong_intent_stays(self) -> None:
        fsm = ObservingStateMachine()
        inp = _inp(P.WAIT_CONTEXT_CONFIRMATION, IT.CONFIRM_HOME, g1_context_confirmed=True)
        assert fsm.next(inp) == P.WAIT_CONTEXT_CONFIRMATION


class TestWaitHomeConfirmation:
    def test_start_home_kicks_off_without_transition(self) -> None:
        fsm = ObservingStateMachine()
        assert fsm.next(_inp(P.WAIT_HOME_CONFIRMATION, IT.START_HOME)) == P.WAIT_HOME_CONFIRMATION

    def test_confirm_home_requires_g2(self) -> None:
        fsm = ObservingStateMachine()
        blocked = _inp(P.WAIT_HOME_CONFIRMATION, IT.CONFIRM_HOME, g2_home_confirmed=False)
        assert fsm.next(blocked) == P.WAIT_HOME_CONFIRMATION
        allowed = _inp(P.WAIT_HOME_CONFIRMATION, IT.CONFIRM_HOME, g2_home_confirmed=True)
        assert fsm.next(allowed) == P.POLAR_ALIGN

    def test_pause_and_stop_not_available_before_polar_align(self) -> None:
        fsm = ObservingStateMachine()
        assert fsm.next(_inp(P.WAIT_HOME_CONFIRMATION, IT.PAUSE)) == P.WAIT_HOME_CONFIRMATION
        assert fsm.next(_inp(P.WAIT_HOME_CONFIRMATION, IT.STOP_SAFELY)) == P.WAIT_HOME_CONFIRMATION


class TestPolarAlign:
    def test_start_kicks_off_without_transition(self) -> None:
        fsm = ObservingStateMachine()
        assert fsm.next(_inp(P.POLAR_ALIGN, IT.START_POLAR_ALIGN)) == P.POLAR_ALIGN

    def test_accept_requires_g3(self) -> None:
        fsm = ObservingStateMachine()
        blocked = _inp(P.POLAR_ALIGN, IT.ACCEPT_POLAR_ALIGN, g3_polar_within_tolerance=False)
        assert fsm.next(blocked) == P.POLAR_ALIGN
        allowed = _inp(P.POLAR_ALIGN, IT.ACCEPT_POLAR_ALIGN, g3_polar_within_tolerance=True)
        assert fsm.next(allowed) == P.FOCUS_READYING

    def test_pause_and_stop_available(self) -> None:
        fsm = ObservingStateMachine()
        assert fsm.next(_inp(P.POLAR_ALIGN, IT.PAUSE)) == P.PAUSED_SAFE
        assert fsm.next(_inp(P.POLAR_ALIGN, IT.STOP_SAFELY)) == P.SAFE_STOPPING


class TestFocusReadying:
    def test_accept_requires_g4(self) -> None:
        fsm = ObservingStateMachine()
        blocked = _inp(P.FOCUS_READYING, IT.ACCEPT_FOCUS, g4_focus_sufficient=False)
        assert fsm.next(blocked) == P.FOCUS_READYING
        allowed = _inp(P.FOCUS_READYING, IT.ACCEPT_FOCUS, g4_focus_sufficient=True)
        assert fsm.next(allowed) == P.TARGET_ACQUIRE


class TestTargetAcquire:
    def test_accept_requires_g5(self) -> None:
        fsm = ObservingStateMachine()
        blocked = _inp(P.TARGET_ACQUIRE, IT.ACCEPT_TARGET, g5_target_centered=False)
        assert fsm.next(blocked) == P.TARGET_ACQUIRE
        allowed = _inp(P.TARGET_ACQUIRE, IT.ACCEPT_TARGET, g5_target_centered=True)
        assert fsm.next(allowed) == P.GUIDE_READYING

    def test_cannot_skip_ahead_to_capture(self) -> None:
        """Cannot reach CAPTURE_ACTIVE by feeding START_CAPTURE while still in TARGET_ACQUIRE."""
        fsm = ObservingStateMachine()
        inp = _inp(P.TARGET_ACQUIRE, IT.START_CAPTURE, g5_target_centered=True, g6_guiding_ok=True)
        assert fsm.next(inp) == P.TARGET_ACQUIRE


class TestGuideReadying:
    def test_start_and_skip_guiding_do_not_transition(self) -> None:
        fsm = ObservingStateMachine()
        assert fsm.next(_inp(P.GUIDE_READYING, IT.START_GUIDING)) == P.GUIDE_READYING
        assert fsm.next(_inp(P.GUIDE_READYING, IT.SKIP_GUIDING)) == P.GUIDE_READYING

    def test_start_capture_requires_g6(self) -> None:
        fsm = ObservingStateMachine()
        blocked = _inp(P.GUIDE_READYING, IT.START_CAPTURE, g6_guiding_ok=False)
        assert fsm.next(blocked) == P.GUIDE_READYING
        allowed = _inp(P.GUIDE_READYING, IT.START_CAPTURE, g6_guiding_ok=True)
        assert fsm.next(allowed) == P.CAPTURE_ACTIVE


class TestCaptureActive:
    def test_stop_safely_transitions_unconditionally(self) -> None:
        fsm = ObservingStateMachine()
        assert fsm.next(_inp(P.CAPTURE_ACTIVE, IT.STOP_SAFELY)) == P.SAFE_STOPPING

    def test_session_may_not_continue_auto_stops(self) -> None:
        fsm = ObservingStateMachine()
        inp = _inp(P.CAPTURE_ACTIVE, None, g7_session_may_continue=False)
        assert fsm.next(inp) == P.SAFE_STOPPING

    def test_pause_transitions_to_paused_safe(self) -> None:
        fsm = ObservingStateMachine()
        assert fsm.next(_inp(P.CAPTURE_ACTIVE, IT.PAUSE)) == P.PAUSED_SAFE

    def test_no_intent_stays_capturing(self) -> None:
        fsm = ObservingStateMachine()
        inp = _inp(P.CAPTURE_ACTIVE, None, g7_session_may_continue=True)
        assert fsm.next(inp) == P.CAPTURE_ACTIVE


class TestSafeStopping:
    def test_advances_to_parked_once_g8_true(self) -> None:
        fsm = ObservingStateMachine()
        blocked = _inp(P.SAFE_STOPPING, None, g8_safe_stop_possible=False)
        assert fsm.next(blocked) == P.SAFE_STOPPING
        allowed = _inp(P.SAFE_STOPPING, None, g8_safe_stop_possible=True)
        assert fsm.next(allowed) == P.PARKED_SAFE


class TestParkedSafe:
    def test_terminal_ignores_all_intents(self) -> None:
        fsm = ObservingStateMachine()
        for intent in Intent:
            assert fsm.next(_inp(P.PARKED_SAFE, intent)) == P.PARKED_SAFE
        assert fsm.next(_inp(P.PARKED_SAFE)) == P.PARKED_SAFE


class TestPausedSafe:
    def test_resume_returns_to_paused_from_phase(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(
            phase=P.PAUSED_SAFE, intent=IT.RESUME, paused_from_phase=P.CAPTURE_ACTIVE,
        )
        assert fsm.next(inp) == P.CAPTURE_ACTIVE

    def test_resume_without_remembered_phase_defaults_to_capture_active(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(phase=P.PAUSED_SAFE, intent=IT.RESUME)
        assert fsm.next(inp) == P.CAPTURE_ACTIVE

    def test_stop_safely_from_paused(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(phase=P.PAUSED_SAFE, intent=IT.STOP_SAFELY)
        assert fsm.next(inp) == P.SAFE_STOPPING

    def test_other_intents_stay_paused(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(phase=P.PAUSED_SAFE, intent=IT.PAUSE)
        assert fsm.next(inp) == P.PAUSED_SAFE


class TestFaultHandling:
    def test_fault_detected_overrides_intent_from_active_phase(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(
            phase=P.TARGET_ACQUIRE, intent=IT.ACCEPT_TARGET, fault_detected=True,
            guards=Guards(g5_target_centered=True),
        )
        assert fsm.next(inp) == P.FAULT

    def test_fault_detected_from_wait_states(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(phase=P.WAIT_CONTEXT_CONFIRMATION, fault_detected=True)
        assert fsm.next(inp) == P.FAULT

    def test_fault_not_re_triggered_while_already_in_fault(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(phase=P.FAULT, fault_detected=True)
        assert fsm.next(inp) == P.FAULT

    def test_acknowledge_recoverable_returns_to_fault_from_phase(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(
            phase=P.FAULT, intent=IT.ACKNOWLEDGE_FAULT, fault_from_phase=P.TARGET_ACQUIRE,
            guards=Guards(g9_error_recoverable=True),
        )
        assert fsm.next(inp) == P.TARGET_ACQUIRE

    def test_acknowledge_not_recoverable_stays_in_fault(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(
            phase=P.FAULT, intent=IT.ACKNOWLEDGE_FAULT, fault_from_phase=P.TARGET_ACQUIRE,
            guards=Guards(g9_error_recoverable=False),
        )
        assert fsm.next(inp) == P.FAULT

    def test_abort_to_park_always_available_from_fault(self) -> None:
        fsm = ObservingStateMachine()
        inp = ObservingInput(phase=P.FAULT, intent=IT.ABORT_TO_PARK)
        assert fsm.next(inp) == P.SAFE_STOPPING


class TestFullHappyPathChain:
    def test_walks_every_phase_in_order(self) -> None:
        fsm = ObservingStateMachine()
        phase = P.BOOTSTRAP

        phase = fsm.next(_inp(phase))
        assert phase == P.WAIT_CONTEXT_CONFIRMATION

        phase = fsm.next(_inp(phase, IT.CONFIRM_CONTEXT, g1_context_confirmed=True))
        assert phase == P.WAIT_HOME_CONFIRMATION

        phase = fsm.next(_inp(phase, IT.CONFIRM_HOME, g2_home_confirmed=True))
        assert phase == P.POLAR_ALIGN

        phase = fsm.next(_inp(phase, IT.ACCEPT_POLAR_ALIGN, g3_polar_within_tolerance=True))
        assert phase == P.FOCUS_READYING

        phase = fsm.next(_inp(phase, IT.ACCEPT_FOCUS, g4_focus_sufficient=True))
        assert phase == P.TARGET_ACQUIRE

        phase = fsm.next(_inp(phase, IT.ACCEPT_TARGET, g5_target_centered=True))
        assert phase == P.GUIDE_READYING

        phase = fsm.next(_inp(phase, IT.START_CAPTURE, g6_guiding_ok=True))
        assert phase == P.CAPTURE_ACTIVE

        phase = fsm.next(_inp(phase, IT.STOP_SAFELY))
        assert phase == P.SAFE_STOPPING

        phase = fsm.next(_inp(phase, None, g8_safe_stop_possible=True))
        assert phase == P.PARKED_SAFE
