"""Maskless FWHM-based final refocus — Collimation Phase 12, COL-120.

Finds best focus by minimising star FWHM after the Tri-Bahtinov mask has been
removed.  The caller supplies a ``get_fwhm`` callable (no args) that returns
the current FWHM in pixels (or None when the star is lost) and a
``move_focuser`` callable for relative focuser steps.

Algorithm
---------
1. Probe  : initial measurement, then try +coarse_step to determine which
            direction improves FWHM.  If neither direction helps, report
            "max_steps".
2. Scan   : move in the improving direction, tracking the best FWHM seen.
            Stop when N consecutive steps show no improvement.
3. Backtrack : return to the position of the best FWHM.
4. Final approach : if the scan direction differed from ``final_approach_direction``,
            insert a one-step overshoot so that the last move comes from the
            correct side (eliminates backlash/hysteresis bias).

Stop conditions
---------------
"converged"  : scan completed and best position was found.
"star_lost"  : get_fwhm returned None.
"cancelled"  : cancel_check() returned True.
"max_steps"  : coarse probe found no improving direction.

Quality tiers (based on best_fwhm_px)
--------------------------------------
"excellent"  : best_fwhm ≤ excellent_fwhm_px
"good"       : best_fwhm ≤ good_fwhm_px
"poor"       : best_fwhm > good_fwhm_px (but converged)
"failed"     : stop reason is not "converged"
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class MasklessFocusResult:
    """Outcome of a maskless FWHM focus run.

    reason           : stop condition string (see module docstring).
    quality          : focus quality tier ("excellent"|"good"|"poor"|"failed").
    initial_fwhm_px  : FWHM at the start of the run (None if lost immediately).
    best_fwhm_px     : best FWHM measured during the run.
    final_fwhm_px    : FWHM at the final position (None if star lost).
    steps_taken      : total move calls issued to the focuser.
    frame_count      : total FWHM measurements taken.
    """
    reason: str
    quality: str
    initial_fwhm_px: float | None
    best_fwhm_px: float | None
    final_fwhm_px: float | None
    steps_taken: int
    frame_count: int


class FWHMFocusController:
    """Maskless hill-climb focus using star FWHM as feedback.

    Args:
        excellent_fwhm_px        : FWHM threshold for "excellent" quality (px).
        good_fwhm_px             : FWHM threshold for "good" quality (px).
        coarse_step              : coarse focuser step (default 250).
        fine_step                : fine step for final approach (default 25).
        max_coarse_steps         : maximum coarse scan steps (default 20).
        max_consecutive_no_improve: consecutive non-improving steps → stop scan (default 2).
        improvement_fraction     : relative FWHM drop required to count as improvement.
        settle_seconds           : pause after each move (default 0 for tests).
        final_approach_direction : +1 = CW (increasing), −1 = CCW (decreasing).
    """

    def __init__(
        self,
        excellent_fwhm_px: float = 2.0,
        good_fwhm_px: float = 4.0,
        coarse_step: int = 250,
        fine_step: int = 25,
        max_coarse_steps: int = 20,
        max_consecutive_no_improve: int = 2,
        improvement_fraction: float = 0.05,
        settle_seconds: float = 0.0,
        final_approach_direction: int = 1,
    ) -> None:
        self._excellent     = excellent_fwhm_px
        self._good          = good_fwhm_px
        self._coarse        = coarse_step
        self._fine          = fine_step
        self._max_coarse    = max_coarse_steps
        self._max_consec    = max_consecutive_no_improve
        self._impr_frac     = improvement_fraction
        self._settle_s      = settle_seconds
        self._final_dir     = 1 if final_approach_direction >= 0 else -1

    # ── public ────────────────────────────────────────────────────────────────

    def focus(
        self,
        get_fwhm: Callable[[], float | None],
        move_focuser: Callable[[int], None],
        cancel_check: Callable[[], bool] | None = None,
    ) -> MasklessFocusResult:
        """Run the FWHM hill-climb.

        Args:
            get_fwhm       : returns current FWHM (px) or None if star lost.
            move_focuser   : callable taking a signed integer step.
            cancel_check   : optional; returns True when cancelled.
        """
        initial_fwhm = get_fwhm()
        if initial_fwhm is None:
            return MasklessFocusResult(
                reason="star_lost", quality="failed",
                initial_fwhm_px=None, best_fwhm_px=None, final_fwhm_px=None,
                steps_taken=0, frame_count=1,
            )

        frame_count   = 1
        steps_taken   = 0
        current_pos   = 0        # accumulated steps from start
        best_fwhm     = initial_fwhm
        best_pos      = 0

        # ── Phase 1: Probe direction ──────────────────────────────────────────
        direction, frame_count, steps_taken, current_pos, best_fwhm, best_pos = \
            self._probe(
                get_fwhm, move_focuser, cancel_check,
                initial_fwhm, frame_count, steps_taken, current_pos,
            )

        if direction == 0:
            # Probe found no improving direction; return to start.
            if current_pos != 0:
                move_focuser(-current_pos)
                steps_taken += 1
            return MasklessFocusResult(
                reason="max_steps", quality="failed",
                initial_fwhm_px=initial_fwhm, best_fwhm_px=best_fwhm,
                final_fwhm_px=initial_fwhm,
                steps_taken=steps_taken, frame_count=frame_count,
            )
        if direction is None:
            # Star lost during probe.
            return MasklessFocusResult(
                reason="star_lost", quality="failed",
                initial_fwhm_px=initial_fwhm, best_fwhm_px=best_fwhm,
                final_fwhm_px=None,
                steps_taken=steps_taken, frame_count=frame_count,
            )

        # ── Phase 2: Coarse scan ──────────────────────────────────────────────
        consecutive = 0

        for _ in range(self._max_coarse):
            if cancel_check and cancel_check():
                return MasklessFocusResult(
                    reason="cancelled", quality="failed",
                    initial_fwhm_px=initial_fwhm, best_fwhm_px=best_fwhm,
                    final_fwhm_px=None,
                    steps_taken=steps_taken, frame_count=frame_count,
                )

            self._settle()
            move_focuser(direction * self._coarse)
            steps_taken += 1
            current_pos += direction * self._coarse

            fwhm = get_fwhm()
            frame_count += 1

            if fwhm is None:
                return MasklessFocusResult(
                    reason="star_lost", quality="failed",
                    initial_fwhm_px=initial_fwhm, best_fwhm_px=best_fwhm,
                    final_fwhm_px=None,
                    steps_taken=steps_taken, frame_count=frame_count,
                )

            if fwhm < best_fwhm * (1.0 - self._impr_frac):
                best_fwhm     = fwhm
                best_pos      = current_pos
                consecutive   = 0
            else:
                consecutive += 1
                if consecutive >= self._max_consec:
                    break

        # ── Phase 3: Backtrack to best position ───────────────────────────────
        backtrack = best_pos - current_pos
        if backtrack != 0:
            move_focuser(backtrack)
            steps_taken += 1
            current_pos = best_pos

        # ── Phase 4: Final approach direction ─────────────────────────────────
        # If the scan direction differs from the configured final approach,
        # insert one overshoot then one correction so the last move is canonical.
        if direction != self._final_dir:
            move_focuser(-self._final_dir * self._fine)
            steps_taken += 1
            self._settle()
            move_focuser(self._final_dir * self._fine)
            steps_taken += 1

        final_fwhm = get_fwhm()
        frame_count += 1
        if final_fwhm is None:
            return MasklessFocusResult(
                reason="star_lost", quality="failed",
                initial_fwhm_px=initial_fwhm, best_fwhm_px=best_fwhm,
                final_fwhm_px=None,
                steps_taken=steps_taken, frame_count=frame_count,
            )

        reported_best = min(best_fwhm, final_fwhm)
        quality = self._quality(reported_best)
        return MasklessFocusResult(
            reason="converged", quality=quality,
            initial_fwhm_px=initial_fwhm, best_fwhm_px=reported_best,
            final_fwhm_px=final_fwhm,
            steps_taken=steps_taken, frame_count=frame_count,
        )

    # ── Private ───────────────────────────────────────────────────────────────

    def _probe(
        self,
        get_fwhm, move_focuser, cancel_check,
        initial_fwhm, frame_count, steps_taken, current_pos,
    ):
        """Try one step forward; if not better try backward.

        Returns (direction, frame_count, steps_taken, current_pos, best_fwhm, best_pos)
        where direction ∈ {+1, −1, 0 (no direction), None (star lost)}.
        """
        best_fwhm = initial_fwhm
        best_pos  = 0

        self._settle()
        move_focuser(self._coarse)
        steps_taken += 1
        current_pos += self._coarse

        fwhm_fwd = get_fwhm()
        frame_count += 1

        if fwhm_fwd is None:
            return None, frame_count, steps_taken, current_pos, best_fwhm, best_pos

        if fwhm_fwd < initial_fwhm * (1.0 - self._impr_frac):
            best_fwhm = fwhm_fwd
            best_pos  = current_pos
            return 1, frame_count, steps_taken, current_pos, best_fwhm, best_pos

        # Forward didn't help — try backward (move -2 coarse from current)
        move_focuser(-2 * self._coarse)
        steps_taken += 1
        current_pos -= 2 * self._coarse

        self._settle()
        fwhm_bwd = get_fwhm()
        frame_count += 1

        if fwhm_bwd is None:
            return None, frame_count, steps_taken, current_pos, best_fwhm, best_pos

        if fwhm_bwd < initial_fwhm * (1.0 - self._impr_frac):
            best_fwhm = fwhm_bwd
            best_pos  = current_pos
            return -1, frame_count, steps_taken, current_pos, best_fwhm, best_pos

        # Neither direction improved — move back to start before returning
        move_focuser(self._coarse)   # +coarse from (-coarse) = back to 0
        steps_taken += 1
        current_pos += self._coarse
        return 0, frame_count, steps_taken, current_pos, best_fwhm, best_pos

    def _quality(self, fwhm: float) -> str:
        if fwhm <= self._excellent:
            return "excellent"
        if fwhm <= self._good:
            return "good"
        return "poor"

    def _settle(self) -> None:
        if self._settle_s > 0:
            time.sleep(self._settle_s)
