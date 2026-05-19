"""Relative focuser control for collimation — Collimation Phase 4, Task 4.2.

Wraps FocuserPort with:
  - physical direction mapping (CW/CCW ↔ focuser unit sign)
  - max_single_step magnitude clamp
  - soft position range enforcement (min_position … max_position)

The absolute focuser position is queried before and after each move and
returned in FocuserMoveResult, but it is explicitly marked as unreliable:
do not assume the returned position value is physically accurate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from ...domain.collimation.config import FocuserCollimationConfig, FocuserDirection
from ...ports.focuser import FocuserPort

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class FocuserMoveResult:
    """Outcome of one relative focuser move.

    steps_requested : signed step count before any clamping.
    steps_taken     : signed step count actually sent to the hardware
                      (after max_single_step and soft-limit clamping).
    position_before : focuser position before the move, or None if unavailable.
    position_after  : focuser position after the move, or None if unavailable.
    clipped         : True when steps_taken differs from steps_requested.
    reason          : "ok" | "soft_limit" | "unavailable".
    """
    steps_requested: int
    steps_taken: int
    position_before: int | None
    position_after: int | None
    clipped: bool
    reason: str


class CollimationFocuserControl:
    """Relative focuser movement respecting direction config and soft limits.

    Direction mapping
    -----------------
    The config ``increasing_value_direction`` tells which physical rotation
    direction causes the focuser position counter to increase:

        CW → increasing value → CW physical rotation ≡ positive raw steps
        CCW → increasing value → CW physical rotation ≡ negative raw steps

    All public methods use physical direction names (clockwise/counterclockwise)
    and convert internally.  The raw ``move_focus_relative()`` method accepts
    signed focuser-unit steps directly.

    Soft limits
    -----------
    Moves are clamped so that the target position stays within
    [min_position, max_position].  The focuser absolute position is NOT
    trusted for absolute positioning, but it is used to prevent driving
    toward a hard limit during a collimation session.
    """

    def __init__(
        self,
        focuser: FocuserPort,
        config: FocuserCollimationConfig,
    ) -> None:
        self._focuser = focuser
        self._cfg = config

    # ── Public API — physical directions ─────────────────────────────────────

    def move_focus_relative(self, steps: int) -> FocuserMoveResult:
        """Move by *steps* in raw focuser units (positive → higher position value).

        Applies max_single_step clamp and soft position limits.
        """
        return self._apply_move(steps)

    def move_focus_clockwise(self, steps: int) -> FocuserMoveResult:
        """Move in the physical clockwise direction by *steps* raw units."""
        return self._apply_move(self._cw_sign() * abs(steps))

    def move_focus_counterclockwise(self, steps: int) -> FocuserMoveResult:
        """Move in the physical counter-clockwise direction by *steps* raw units."""
        return self._apply_move(-self._cw_sign() * abs(steps))

    def defocus(self, steps: int | None = None) -> FocuserMoveResult:
        """Move in the configured defocus direction.

        Args:
            steps: magnitude in raw units; defaults to ``coarse_step``.
        """
        n = abs(steps) if steps is not None else self._cfg.coarse_step
        sign = self._dir_sign(self._cfg.defocus_direction)
        return self._apply_move(sign * n)

    def focus_fine(self, steps: int | None = None) -> FocuserMoveResult:
        """Move one fine step in the configured final approach direction.

        Used for the last approach to focus so that hysteresis is consistent.

        Args:
            steps: magnitude in raw units; defaults to ``fine_step``.
        """
        n = abs(steps) if steps is not None else self._cfg.fine_step
        sign = self._dir_sign(self._cfg.final_approach_direction)
        return self._apply_move(sign * n)

    # ── Core move ─────────────────────────────────────────────────────────────

    def _apply_move(self, steps: int) -> FocuserMoveResult:
        if not self._focuser.is_available:
            return FocuserMoveResult(
                steps_requested=steps,
                steps_taken=0,
                position_before=None,
                position_after=None,
                clipped=steps != 0,
                reason="unavailable",
            )

        pos_before: int | None = self._safe_get_position()

        # Stage 1: magnitude clamp
        after_mag = self._clamp_magnitude(steps)

        # Stage 2: soft position limit clamp
        after_soft = after_mag
        if pos_before is not None:
            after_soft = self._clamp_soft_limits(after_mag, pos_before)

        clamped = after_soft
        clipped = clamped != steps
        soft_limited = after_soft != after_mag

        if clamped == 0:
            return FocuserMoveResult(
                steps_requested=steps,
                steps_taken=0,
                position_before=pos_before,
                position_after=pos_before,
                clipped=clipped,
                reason="soft_limit" if (soft_limited or (clipped and pos_before is not None)) else "ok",
            )

        _log.debug(
            "CollimationFocuserControl: move requested=%+d clamped=%+d pos_before=%s",
            steps, clamped, pos_before,
        )

        try:
            self._focuser.move(clamped)
        except Exception as exc:
            _log.warning("focuser.move(%d) failed: %s", clamped, exc)
            return FocuserMoveResult(
                steps_requested=steps,
                steps_taken=0,
                position_before=pos_before,
                position_after=pos_before,
                clipped=True,
                reason="unavailable",
            )

        pos_after = self._safe_get_position()

        return FocuserMoveResult(
            steps_requested=steps,
            steps_taken=clamped,
            position_before=pos_before,
            position_after=pos_after,
            clipped=clipped,
            reason="soft_limit" if soft_limited else "ok",
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _clamp_magnitude(self, steps: int) -> int:
        limit = self._cfg.max_single_step
        return max(-limit, min(limit, steps))

    def _clamp_soft_limits(self, steps: int, current: int) -> int:
        target = current + steps
        if target < self._cfg.min_position:
            return self._cfg.min_position - current
        if target > self._cfg.max_position:
            return self._cfg.max_position - current
        return steps

    def _cw_sign(self) -> int:
        return self._dir_sign(FocuserDirection.CLOCKWISE)

    def _dir_sign(self, direction: FocuserDirection) -> int:
        """Map a physical direction to a raw-step sign."""
        return +1 if direction == self._cfg.increasing_value_direction else -1

    def _safe_get_position(self) -> int | None:
        try:
            return int(self._focuser.get_position())
        except Exception:
            return None
