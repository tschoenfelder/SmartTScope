"""Top-level observing state machine (smarttscope_requirements_full.md §6-7).

This is the single authoritative process state for a SmartTScope session:
BOOTSTRAP -> WAIT_CONTEXT_CONFIRMATION -> WAIT_HOME_CONFIRMATION -> POLAR_ALIGN
-> FOCUS_READYING -> TARGET_ACQUIRE -> GUIDE_READYING -> CAPTURE_ACTIVE
-> SAFE_STOPPING -> PARKED_SAFE, with PAUSED_SAFE and FAULT as side paths.

Pure domain logic only, in the same spirit as polar_workflow.py: no I/O, no
config access, no hardware calls. The caller (services/observing_service.py)
computes Guards from real subsystems, dispatches Intents to the existing
engines (polar_workflow, autofocus_service, workflow/stages, guiding_service,
mount_operations), and feeds the result back into next().

Typical driver loop::

    fsm = ObservingStateMachine()
    phase = ObservingPhase.BOOTSTRAP
    while True:
        guards = compute_guards(...)          # from real subsystems
        intent = wait_for_user_or_system_intent()
        inp = ObservingInput(phase=phase, intent=intent, guards=guards)
        phase = fsm.next(inp)

Guard-gated transitions are silently rejected (the phase does not change) when
their required guard is not satisfied — the caller surfaces *why* via the
Guards snapshot, it does not need next() to raise. Only PAUSE, STOP_SAFELY,
and ABORT_TO_PARK bypass guards entirely, because they are safety actions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ObservingPhase(Enum):
    BOOTSTRAP = "BOOTSTRAP"
    WAIT_CONTEXT_CONFIRMATION = "WAIT_CONTEXT_CONFIRMATION"
    WAIT_HOME_CONFIRMATION = "WAIT_HOME_CONFIRMATION"
    POLAR_ALIGN = "POLAR_ALIGN"
    FOCUS_READYING = "FOCUS_READYING"
    TARGET_ACQUIRE = "TARGET_ACQUIRE"
    GUIDE_READYING = "GUIDE_READYING"
    CAPTURE_ACTIVE = "CAPTURE_ACTIVE"
    SAFE_STOPPING = "SAFE_STOPPING"
    PARKED_SAFE = "PARKED_SAFE"
    PAUSED_SAFE = "PAUSED_SAFE"
    FAULT = "FAULT"


# Phases from which PAUSE / STOP_SAFELY (safety actions) are meaningful —
# i.e. phases where the mount/camera may already be in motion or in use.
_ACTIVE_PHASES = frozenset({
    ObservingPhase.POLAR_ALIGN,
    ObservingPhase.FOCUS_READYING,
    ObservingPhase.TARGET_ACQUIRE,
    ObservingPhase.GUIDE_READYING,
    ObservingPhase.CAPTURE_ACTIVE,
})

# Phases that can suffer a fault (everything except the terminal/side states).
_FAULTABLE_PHASES = _ACTIVE_PHASES | frozenset({
    ObservingPhase.WAIT_CONTEXT_CONFIRMATION,
    ObservingPhase.WAIT_HOME_CONFIRMATION,
    ObservingPhase.SAFE_STOPPING,
})


class Intent(Enum):
    CONFIRM_CONTEXT = "CONFIRM_CONTEXT"
    START_HOME = "START_HOME"
    CONFIRM_HOME = "CONFIRM_HOME"
    START_POLAR_ALIGN = "START_POLAR_ALIGN"
    ACCEPT_POLAR_ALIGN = "ACCEPT_POLAR_ALIGN"
    START_FOCUS = "START_FOCUS"
    ACCEPT_FOCUS = "ACCEPT_FOCUS"
    START_TARGET_ACQUIRE = "START_TARGET_ACQUIRE"
    ACCEPT_TARGET = "ACCEPT_TARGET"
    START_GUIDING = "START_GUIDING"
    SKIP_GUIDING = "SKIP_GUIDING"
    START_CAPTURE = "START_CAPTURE"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    STOP_SAFELY = "STOP_SAFELY"
    ACKNOWLEDGE_FAULT = "ACKNOWLEDGE_FAULT"
    ABORT_TO_PARK = "ABORT_TO_PARK"
    UNPARK_CONTINUE = "UNPARK_CONTINUE"


@dataclass(frozen=True)
class Guards:
    """Snapshot of G1-G10 from smarttscope_requirements_full.md §7.2.

    None means "not yet evaluated" (treated the same as False for gating
    purposes, but kept distinct so the API layer can render an "unknown"
    guard chip rather than a false "blocked" one).
    """
    g1_context_confirmed: bool | None = None
    g2_home_confirmed: bool | None = None
    g3_polar_within_tolerance: bool | None = None
    g4_focus_sufficient: bool | None = None
    g5_target_centered: bool | None = None
    g6_guiding_ok: bool | None = None
    g7_session_may_continue: bool | None = None
    g8_safe_stop_possible: bool | None = None
    g9_error_recoverable: bool | None = None
    g10_error_unrecoverable: bool | None = None


@dataclass(frozen=True)
class ObservingInput:
    phase: ObservingPhase
    intent: Intent | None = None
    guards: Guards = field(default_factory=Guards)
    fault_detected: bool = False
    # Caller-tracked "return to" phases — the FSM itself holds no session
    # state, so it relies on these to know where PAUSED_SAFE/FAULT came from.
    paused_from_phase: ObservingPhase | None = None
    fault_from_phase: ObservingPhase | None = None


def _guard_true(value: bool | None) -> bool:
    return value is True


class ObservingStateMachine:
    """Stateless transition table: next(input) -> next phase.

    No instance state is held between calls — every call is a pure function
    of its ObservingInput, which is why it needs no mocks to unit test.
    """

    def next(self, inp: ObservingInput) -> ObservingPhase:
        # Fault handling takes priority over everything except the FAULT
        # phase's own recovery intents and terminal phases.
        if (
            inp.fault_detected
            and inp.phase in _FAULTABLE_PHASES
            and inp.phase is not ObservingPhase.FAULT
        ):
            return ObservingPhase.FAULT

        match inp.phase:
            case ObservingPhase.BOOTSTRAP:
                return self._on_bootstrap(inp)
            case ObservingPhase.WAIT_CONTEXT_CONFIRMATION:
                return self._on_wait_context(inp)
            case ObservingPhase.WAIT_HOME_CONFIRMATION:
                return self._on_wait_home(inp)
            case ObservingPhase.POLAR_ALIGN:
                return self._on_polar_align(inp)
            case ObservingPhase.FOCUS_READYING:
                return self._on_focus_readying(inp)
            case ObservingPhase.TARGET_ACQUIRE:
                return self._on_target_acquire(inp)
            case ObservingPhase.GUIDE_READYING:
                return self._on_guide_readying(inp)
            case ObservingPhase.CAPTURE_ACTIVE:
                return self._on_capture_active(inp)
            case ObservingPhase.SAFE_STOPPING:
                return self._on_safe_stopping(inp)
            case ObservingPhase.PARKED_SAFE:
                return self._on_parked_safe(inp)
            case ObservingPhase.PAUSED_SAFE:
                return self._on_paused_safe(inp)
            case ObservingPhase.FAULT:
                return self._on_fault(inp)
        return inp.phase  # pragma: no cover — exhaustive match above

    # ── phase handlers ────────────────────────────────────────────────────────

    def _on_bootstrap(self, inp: ObservingInput) -> ObservingPhase:
        # Bootstrap (profile load, adapter check, status init) has no user
        # gate — it always advances on the first poll.
        return ObservingPhase.WAIT_CONTEXT_CONFIRMATION

    def _on_wait_context(self, inp: ObservingInput) -> ObservingPhase:
        if inp.intent == Intent.CONFIRM_CONTEXT and _guard_true(inp.guards.g1_context_confirmed):
            return ObservingPhase.WAIT_HOME_CONFIRMATION
        # Safe-park is available even before anything is "active" (nothing to
        # pause yet, so PAUSE is deliberately not offered here — see _STOP_ONLY_PHASES
        # in observing_service.py).
        if inp.intent == Intent.STOP_SAFELY:
            return ObservingPhase.SAFE_STOPPING
        return ObservingPhase.WAIT_CONTEXT_CONFIRMATION

    def _on_wait_home(self, inp: ObservingInput) -> ObservingPhase:
        if inp.intent == Intent.CONFIRM_HOME and _guard_true(inp.guards.g2_home_confirmed):
            return ObservingPhase.POLAR_ALIGN
        if inp.intent == Intent.STOP_SAFELY:
            return ObservingPhase.SAFE_STOPPING
        return self._maybe_pause_or_stop(inp, ObservingPhase.WAIT_HOME_CONFIRMATION)

    def _on_polar_align(self, inp: ObservingInput) -> ObservingPhase:
        accepted = inp.intent == Intent.ACCEPT_POLAR_ALIGN
        if accepted and _guard_true(inp.guards.g3_polar_within_tolerance):
            return ObservingPhase.FOCUS_READYING
        return self._maybe_pause_or_stop(inp, ObservingPhase.POLAR_ALIGN)

    def _on_focus_readying(self, inp: ObservingInput) -> ObservingPhase:
        if inp.intent == Intent.ACCEPT_FOCUS and _guard_true(inp.guards.g4_focus_sufficient):
            return ObservingPhase.TARGET_ACQUIRE
        return self._maybe_pause_or_stop(inp, ObservingPhase.FOCUS_READYING)

    def _on_target_acquire(self, inp: ObservingInput) -> ObservingPhase:
        if inp.intent == Intent.ACCEPT_TARGET and _guard_true(inp.guards.g5_target_centered):
            return ObservingPhase.GUIDE_READYING
        return self._maybe_pause_or_stop(inp, ObservingPhase.TARGET_ACQUIRE)

    def _on_guide_readying(self, inp: ObservingInput) -> ObservingPhase:
        if inp.intent == Intent.START_CAPTURE and _guard_true(inp.guards.g6_guiding_ok):
            return ObservingPhase.CAPTURE_ACTIVE
        return self._maybe_pause_or_stop(inp, ObservingPhase.GUIDE_READYING)

    def _on_capture_active(self, inp: ObservingInput) -> ObservingPhase:
        # STOP_SAFELY also fires automatically once the caller observes
        # g7_session_may_continue go False (dawn/meridian) — see backlog
        # Phase 4; for now the caller simply supplies STOP_SAFELY itself.
        if inp.intent == Intent.STOP_SAFELY or inp.guards.g7_session_may_continue is False:
            return ObservingPhase.SAFE_STOPPING
        if inp.intent == Intent.PAUSE:
            return ObservingPhase.PAUSED_SAFE
        return ObservingPhase.CAPTURE_ACTIVE

    def _on_safe_stopping(self, inp: ObservingInput) -> ObservingPhase:
        # M9-034: a manual STOP mid-park-slew leaves the mount neither parked
        # nor moving — SAFE_STOPPING must not be a dead end. UNPARK_CONTINUE
        # returns to the homing step (checked before g8 so an explicit user
        # choice wins even if the park happened to complete concurrently).
        if inp.intent == Intent.UNPARK_CONTINUE:
            return ObservingPhase.WAIT_HOME_CONFIRMATION
        if _guard_true(inp.guards.g8_safe_stop_possible):
            return ObservingPhase.PARKED_SAFE
        return ObservingPhase.SAFE_STOPPING

    def _on_parked_safe(self, inp: ObservingInput) -> ObservingPhase:
        # M9-028: PARKED_SAFE is no longer strictly terminal — safe-parking
        # during setup (WAIT_CONTEXT/WAIT_HOME) previously left no way back
        # into the guided flow. UNPARK_CONTINUE is a pure flow transition:
        # the mount stays parked; the physical unpark happens through
        # home_sequence()'s existing auto-unpark when START_HOME is issued
        # in WAIT_HOME_CONFIRMATION. The caller must reset g2/g8 so the
        # stale home confirmation and safe-stop guard don't leak forward.
        if inp.intent == Intent.UNPARK_CONTINUE:
            return ObservingPhase.WAIT_HOME_CONFIRMATION
        return ObservingPhase.PARKED_SAFE

    def _on_paused_safe(self, inp: ObservingInput) -> ObservingPhase:
        if inp.intent == Intent.RESUME:
            return inp.paused_from_phase or ObservingPhase.CAPTURE_ACTIVE
        if inp.intent == Intent.STOP_SAFELY:
            return ObservingPhase.SAFE_STOPPING
        return ObservingPhase.PAUSED_SAFE

    def _on_fault(self, inp: ObservingInput) -> ObservingPhase:
        if inp.intent == Intent.ACKNOWLEDGE_FAULT and _guard_true(inp.guards.g9_error_recoverable):
            return inp.fault_from_phase or ObservingPhase.WAIT_CONTEXT_CONFIRMATION
        if inp.intent == Intent.ABORT_TO_PARK:
            return ObservingPhase.SAFE_STOPPING
        return ObservingPhase.FAULT

    # ── helpers ───────────────────────────────────────────────────────────────

    def _maybe_pause_or_stop(self, inp: ObservingInput, default: ObservingPhase) -> ObservingPhase:
        """PAUSE/STOP_SAFELY are accepted from any active phase, bypassing guards."""
        if default not in _ACTIVE_PHASES:
            return default
        if inp.intent == Intent.STOP_SAFELY:
            return ObservingPhase.SAFE_STOPPING
        if inp.intent == Intent.PAUSE:
            return ObservingPhase.PAUSED_SAFE
        return default
