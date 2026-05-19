"""Collimation assistant state machine — Phase 1.1.

Defines the 20-state collimation workflow with explicit VALID_TRANSITIONS.
pause() / resume() are handled outside VALID_TRANSITIONS to avoid polluting
every state's outbound set with PAUSED.
"""
from __future__ import annotations

import threading
from enum import Enum


class CollimationState(str, Enum):
    IDLE                      = "idle"
    PAUSED                    = "paused"
    PRECHECK                  = "precheck"
    SELECT_STAR               = "select_star"
    SLEW_TO_STAR              = "slew_to_star"
    ACQUIRE_STAR              = "acquire_star"
    CENTER_STAR               = "center_star"
    AUTO_EXPOSURE             = "auto_exposure"
    ROUGH_DEFOCUS             = "rough_defocus"
    MAP_SCREWS_BY_OBSTRUCTION = "map_screws_by_obstruction"
    MEASURE_DONUT             = "measure_donut"
    GUIDE_ROUGH_COLLIMATION   = "guide_rough_collimation"
    INSTALL_TRIBAHTINOV       = "install_tribahtinov"
    MAP_MASK_SECTORS          = "map_mask_sectors"
    FINE_FOCUS                = "fine_focus"
    MEASURE_SPIKES            = "measure_spikes"
    GUIDE_FINE_COLLIMATION    = "guide_fine_collimation"
    FINAL_REFOCUS             = "final_refocus"
    MASKLESS_VALIDATION       = "maskless_validation"
    COMPLETE                  = "complete"
    FAILED                    = "failed"


# States where the workflow stops and waits for explicit user input via /next.
USER_WAIT_STATES: frozenset[CollimationState] = frozenset({
    CollimationState.SELECT_STAR,
    CollimationState.GUIDE_ROUGH_COLLIMATION,
    CollimationState.INSTALL_TRIBAHTINOV,
    CollimationState.GUIDE_FINE_COLLIMATION,
    CollimationState.MASKLESS_VALIDATION,
})

TERMINAL_STATES: frozenset[CollimationState] = frozenset({
    CollimationState.COMPLETE,
    CollimationState.FAILED,
})

# Explicit allowed forward transitions (pause/resume handled separately).
VALID_TRANSITIONS: dict[CollimationState, frozenset[CollimationState]] = {
    CollimationState.IDLE: frozenset({
        CollimationState.PRECHECK,
    }),
    CollimationState.PRECHECK: frozenset({
        CollimationState.SELECT_STAR,
        CollimationState.FAILED,
    }),
    CollimationState.SELECT_STAR: frozenset({
        CollimationState.SLEW_TO_STAR,
    }),
    CollimationState.SLEW_TO_STAR: frozenset({
        CollimationState.ACQUIRE_STAR,
        CollimationState.SELECT_STAR,   # slew rejected — pick another star
        CollimationState.FAILED,
    }),
    CollimationState.ACQUIRE_STAR: frozenset({
        CollimationState.CENTER_STAR,
        CollimationState.SELECT_STAR,   # no star detected — pick another
        CollimationState.FAILED,
    }),
    CollimationState.CENTER_STAR: frozenset({
        CollimationState.AUTO_EXPOSURE,
        CollimationState.ACQUIRE_STAR,  # star lost during centering
        CollimationState.FAILED,
    }),
    CollimationState.AUTO_EXPOSURE: frozenset({
        CollimationState.ROUGH_DEFOCUS,
        CollimationState.FAILED,
    }),
    CollimationState.ROUGH_DEFOCUS: frozenset({
        CollimationState.MAP_SCREWS_BY_OBSTRUCTION,
        CollimationState.FAILED,
    }),
    CollimationState.MAP_SCREWS_BY_OBSTRUCTION: frozenset({
        CollimationState.MEASURE_DONUT,
        CollimationState.FAILED,
    }),
    CollimationState.MEASURE_DONUT: frozenset({
        CollimationState.GUIDE_ROUGH_COLLIMATION,
        CollimationState.ACQUIRE_STAR,  # star drifted out of frame
        CollimationState.FAILED,
    }),
    CollimationState.GUIDE_ROUGH_COLLIMATION: frozenset({
        CollimationState.MEASURE_DONUT,       # user applied hint → remeasure
        CollimationState.INSTALL_TRIBAHTINOV, # user declares rough done
    }),
    CollimationState.INSTALL_TRIBAHTINOV: frozenset({
        CollimationState.MAP_MASK_SECTORS,
    }),
    CollimationState.MAP_MASK_SECTORS: frozenset({
        CollimationState.FINE_FOCUS,
        CollimationState.FAILED,
    }),
    CollimationState.FINE_FOCUS: frozenset({
        CollimationState.MEASURE_SPIKES,
        CollimationState.FAILED,
    }),
    CollimationState.MEASURE_SPIKES: frozenset({
        CollimationState.GUIDE_FINE_COLLIMATION,
        CollimationState.FINE_FOCUS,            # needs refocus before spike read
        CollimationState.FAILED,
    }),
    CollimationState.GUIDE_FINE_COLLIMATION: frozenset({
        CollimationState.MEASURE_SPIKES,        # user applied hint → remeasure
        CollimationState.FINAL_REFOCUS,         # user declares fine done
    }),
    CollimationState.FINAL_REFOCUS: frozenset({
        CollimationState.MASKLESS_VALIDATION,
        CollimationState.FAILED,
    }),
    CollimationState.MASKLESS_VALIDATION: frozenset({
        CollimationState.COMPLETE,
        CollimationState.GUIDE_FINE_COLLIMATION,  # user requests more fine adjustment
    }),
    CollimationState.COMPLETE: frozenset({CollimationState.IDLE}),
    CollimationState.FAILED:   frozenset({CollimationState.IDLE}),
}

STATE_INSTRUCTIONS: dict[CollimationState, str] = {
    CollimationState.IDLE:
        "Ready. Click Start to begin the collimation wizard.",
    CollimationState.PAUSED:
        "Paused. Click Resume to continue.",
    CollimationState.PRECHECK:
        "Checking hardware and configuration…",
    CollimationState.SELECT_STAR:
        "Select a collimation star from the list, then click Next.",
    CollimationState.SLEW_TO_STAR:
        "Slewing to collimation star…",
    CollimationState.ACQUIRE_STAR:
        "Acquiring star in frame…",
    CollimationState.CENTER_STAR:
        "Centering star via pulse-guide…",
    CollimationState.AUTO_EXPOSURE:
        "Finding optimal exposure for donut defocus…",
    CollimationState.ROUGH_DEFOCUS:
        "Defocusing to the donut regime…",
    CollimationState.MAP_SCREWS_BY_OBSTRUCTION:
        "Mapping collimation-screw axes from obstruction shadow…",
    CollimationState.MEASURE_DONUT:
        "Measuring donut collimation error…",
    CollimationState.GUIDE_ROUGH_COLLIMATION:
        "Apply the screw-turn hint shown below. "
        "Click Next to remeasure, or Finish Rough when the donut is concentric.",
    CollimationState.INSTALL_TRIBAHTINOV:
        "Install the Tri-Bahtinov mask on the telescope, then click Next.",
    CollimationState.MAP_MASK_SECTORS:
        "Mapping Tri-Bahtinov mask sectors to collimation screws…",
    CollimationState.FINE_FOCUS:
        "Reaching fine focus with the Tri-Bahtinov mask…",
    CollimationState.MEASURE_SPIKES:
        "Measuring Tri-Bahtinov spike residuals…",
    CollimationState.GUIDE_FINE_COLLIMATION:
        "Apply the fine-collimation screw hint shown below. "
        "Click Next to remeasure, or Finish Fine when spikes converge.",
    CollimationState.FINAL_REFOCUS:
        "Final focus pass after collimation screws settled…",
    CollimationState.MASKLESS_VALIDATION:
        "Remove the Tri-Bahtinov mask. "
        "Click Accept if the star looks collimated, or Adjust More to continue.",
    CollimationState.COMPLETE:
        "Collimation complete. Well done!",
    CollimationState.FAILED:
        "Collimation failed. Review the log below, then click Reset to try again.",
}


class InvalidTransitionError(ValueError):
    pass


class CollimationStateMachine:
    """Thread-safe explicit state machine for the collimation assistant."""

    def __init__(self) -> None:
        self._state = CollimationState.IDLE
        self._prev_state: CollimationState | None = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CollimationState:
        return self._state

    @property
    def prev_state(self) -> CollimationState | None:
        return self._prev_state

    def transition(self, target: CollimationState) -> None:
        with self._lock:
            allowed = VALID_TRANSITIONS.get(self._state, frozenset())
            if target not in allowed:
                raise InvalidTransitionError(
                    f"Invalid transition {self._state.value!r} → {target.value!r}. "
                    f"Allowed: {[s.value for s in sorted(allowed, key=lambda s: s.value)]}"
                )
            self._state = target

    def pause(self) -> None:
        with self._lock:
            if self._state in TERMINAL_STATES or self._state in (
                CollimationState.IDLE, CollimationState.PAUSED
            ):
                raise InvalidTransitionError(
                    f"Cannot pause in state {self._state.value!r}"
                )
            self._prev_state = self._state
            self._state = CollimationState.PAUSED

    def resume(self) -> CollimationState:
        """Return to the pre-pause state and return it."""
        with self._lock:
            if self._state != CollimationState.PAUSED:
                raise InvalidTransitionError("Not in PAUSED state")
            if self._prev_state is None:
                raise InvalidTransitionError("No previous state to resume to")
            self._state = self._prev_state
            self._prev_state = None
            return self._state

    def reset(self) -> None:
        with self._lock:
            self._state = CollimationState.IDLE
            self._prev_state = None

    def is_terminal(self) -> bool:
        return self._state in TERMINAL_STATES

    def is_waiting_for_user(self) -> bool:
        return self._state in USER_WAIT_STATES

    def instruction(self) -> str:
        return STATE_INSTRUCTIONS.get(self._state, "")
