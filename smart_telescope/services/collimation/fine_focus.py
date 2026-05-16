"""Fine focus loop using Tri-Bahtinov image feedback — Collimation Phase 11, COL-111.

The controller polls a ``get_error`` callable (no args) that returns the
current common focus error in pixels (from a SpikeErrorDecomposition), or
None when the star is lost.  It moves the focuser in steps and reduces the
step size when close to the target.

Final approach direction
------------------------
Mechanical focuser backlash can cause the true focus position to shift
slightly depending on the direction of the last movement.  The
``final_approach_direction`` parameter (±1) enforces that the loop always
converges by approaching focus from one side.  If the natural convergence
would come from the wrong side, a single overshoot step is inserted at the
start of the fine phase to get onto the correct side.

Stop conditions
---------------
"converged"  : |error| < target_px
"max_steps"  : step budget exhausted
"star_lost"  : get_error returned None
"cancelled"  : cancel_check() returned True
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class FineFocusResult:
    """Outcome of a fine focus loop.

    reason          : stop condition string (see module docstring).
    initial_error_px: common focus error at the start of the loop.
    final_error_px  : error at the last measurement (None if star was lost).
    steps_taken     : total focuser move calls issued.
    frame_count     : total measurements taken (including the initial one).
    """
    reason: str
    initial_error_px: float
    final_error_px: float | None
    steps_taken: int
    frame_count: int


class FineFocusController:
    """Image-feedback fine focus loop for the Tri-Bahtinov collimation assistant.

    Args:
        target_px               : |error| below this → converged (px, default 2.0).
        coarse_step             : focuser step used far from focus (default 250).
        fine_step               : step used within coarse_threshold_px (default 25).
        coarse_threshold_px     : |error| below this → switch to fine steps (default 5.0).
        max_steps               : maximum focuser moves before giving up (default 20).
        settle_seconds          : pause between move and measurement (default 1.0).
        final_approach_direction: +1 = converge by moving CW (increasing position),
                                  −1 = converge by moving CCW (decreasing position).
    """

    def __init__(
        self,
        target_px: float = 2.0,
        coarse_step: int = 250,
        fine_step: int = 25,
        coarse_threshold_px: float = 5.0,
        max_steps: int = 20,
        settle_seconds: float = 1.0,
        final_approach_direction: int = 1,
    ) -> None:
        self._target_px         = target_px
        self._coarse_step       = coarse_step
        self._fine_step         = fine_step
        self._coarse_threshold  = coarse_threshold_px
        self._max_steps         = max_steps
        self._settle_s          = settle_seconds
        self._final_dir         = 1 if final_approach_direction >= 0 else -1

    # ── public ────────────────────────────────────────────────────────────────

    def focus(
        self,
        get_error: Callable[[], float | None],
        move_focuser: Callable[[int], None],
        cancel_check: Callable[[], bool] | None = None,
    ) -> FineFocusResult:
        """Run the fine focus loop.

        Args:
            get_error      : returns current common_focus_error_px, or None if
                             star/signal is lost.
            move_focuser   : callable taking a signed integer step; positive =
                             CW / increasing focuser position.
            cancel_check   : optional; returns True when the user cancelled.

        Returns:
            FineFocusResult with stop reason and summary statistics.
        """
        initial_error = get_error()
        if initial_error is None:
            return FineFocusResult(
                reason="star_lost",
                initial_error_px=0.0,
                final_error_px=None,
                steps_taken=0,
                frame_count=1,
            )

        frame_count  = 1
        steps_taken  = 0
        current      = initial_error
        fine_started = False

        for _ in range(self._max_steps):
            if cancel_check and cancel_check():
                return FineFocusResult(
                    reason="cancelled",
                    initial_error_px=initial_error,
                    final_error_px=current,
                    steps_taken=steps_taken,
                    frame_count=frame_count,
                )

            if abs(current) < self._target_px:
                return FineFocusResult(
                    reason="converged",
                    initial_error_px=initial_error,
                    final_error_px=current,
                    steps_taken=steps_taken,
                    frame_count=frame_count,
                )

            near = abs(current) < self._coarse_threshold

            # At the transition to fine phase: enforce final approach direction.
            # natural_dir: direction that reduces |error| from the current side.
            # If natural_dir differs from final_dir, insert one overshoot step
            # so that all subsequent steps arrive from the correct side.
            if near and not fine_started:
                fine_started = True
                natural_dir = -1 if current > 0 else 1
                if natural_dir != self._final_dir:
                    move_focuser(-self._final_dir * self._fine_step)
                    steps_taken += 1
                    # Re-measure after overshoot before continuing the loop.
                    if self._settle_s > 0:
                        time.sleep(self._settle_s)
                    current = get_error()  # type: ignore[assignment]
                    frame_count += 1
                    if current is None:
                        return FineFocusResult(
                            reason="star_lost",
                            initial_error_px=initial_error,
                            final_error_px=None,
                            steps_taken=steps_taken,
                            frame_count=frame_count,
                        )
                    continue

            # Normal step: move in the direction that reduces |error|.
            direction = -1 if current > 0 else 1
            step_size = self._fine_step if near else self._coarse_step
            move_focuser(direction * step_size)
            steps_taken += 1

            if self._settle_s > 0:
                time.sleep(self._settle_s)

            current = get_error()  # type: ignore[assignment]
            frame_count += 1

            if current is None:
                return FineFocusResult(
                    reason="star_lost",
                    initial_error_px=initial_error,
                    final_error_px=None,
                    steps_taken=steps_taken,
                    frame_count=frame_count,
                )

        # Exhausted step budget.
        return FineFocusResult(
            reason="max_steps",
            initial_error_px=initial_error,
            final_error_px=current,
            steps_taken=steps_taken,
            frame_count=frame_count,
        )
