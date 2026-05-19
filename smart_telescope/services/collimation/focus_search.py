"""Image-based rough focus search — Collimation Phase 6, Task 6.1.

Finds best focus by measuring FWHM from captured frames.  Absolute focuser
position is not trusted; only relative moves are used.

Algorithm
---------
1. Initial measurement: capture frame, detect star, record FWHM.
2. Probe: try one coarse step to determine which direction improves FWHM.
3. Scan: move in the improving direction, tracking the best FWHM seen.
   Stop when two consecutive steps show no improvement (≥ improvement_fraction),
   the star is lost, a soft limit is hit, or max_coarse_steps is exhausted.
4. Backtrack: return to the position of best FWHM.
5. Final approach: overshoot slightly in the anti-approach direction, then
   step in fine_step increments from the configured final_approach_direction
   so backlash/hysteresis is consistent.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ...domain.collimation.config import FocuserCollimationConfig
from ...domain.collimation.processing.frame import normalize_frame, ProcessedFrame
from ...domain.collimation.processing.star_detection import detect_star
from ...domain.frame import FitsFrame
from .focuser_control import CollimationFocuserControl

_log = logging.getLogger(__name__)

_FINAL_APPROACH_OVERSHOOT = 3   # fine_steps to overshoot before final approach
_MAX_FINE_STEPS           = 15  # max steps in final approach phase
_MIN_FWHM_IMPROVEMENT     = 0.5 # px; minimum absolute FWHM drop to continue fine phase


@dataclass(frozen=True)
class FocusSearchResult:
    """Outcome of a focus search run.

    success       : True when a good focus position was reached.
    reason        : "in_focus" | "star_lost" | "no_improvement" |
                    "max_steps" | "cancelled".
    best_fwhm     : best FWHM measured (px), or None if no star ever found.
    net_steps     : net signed focuser steps from start position to final position.
    """
    success: bool
    reason: str
    best_fwhm: float | None
    net_steps: int


class FocusSearcher:
    """Image-based rough focus search for the collimation assistant.

    Inject a ``capture_frame`` callable in ``search()`` so the logic can be
    tested without real camera hardware.

    Args:
        focuser            : CollimationFocuserControl (wraps the real focuser).
        config             : FocuserCollimationConfig with step sizes and direction.
        bit_depth          : camera bit depth (passed to normalize_frame).
        max_coarse_steps   : maximum scan steps before giving up (default 20).
        improvement_fraction: relative FWHM drop required to count as improvement
                              (default 5 %).
        settle_seconds     : wait between move and capture (default 0.5 s).
    """

    def __init__(
        self,
        focuser: CollimationFocuserControl,
        config: FocuserCollimationConfig,
        bit_depth: int = 16,
        max_coarse_steps: int = 20,
        improvement_fraction: float = 0.05,
        settle_seconds: float = 0.5,
    ) -> None:
        self._focuser   = focuser
        self._cfg       = config
        self._bit_depth = bit_depth
        self._max_coarse = max_coarse_steps
        self._impr_frac  = improvement_fraction
        self._settle_s   = settle_seconds

    # ── Public API ────────────────────────────────────────────────────────────

    def search(
        self,
        capture_frame: Callable[[], FitsFrame],
        cancel_check: Callable[[], bool] | None = None,
    ) -> FocusSearchResult:
        """Run the focus search from the current focuser position.

        Args:
            capture_frame : callable that takes a frame (no args).  Called
                            each time a new measurement is needed.
            cancel_check  : optional; returns True when operator cancelled.
        """
        # ── Initial measurement ──────────────────────────────────────────────
        fwhm0 = self._get_fwhm(capture_frame)
        if fwhm0 is None:
            return FocusSearchResult(success=False, reason="star_lost",
                                     best_fwhm=None, net_steps=0)

        best_fwhm   = fwhm0
        net_steps   = 0
        best_net    = 0

        # ── Probe ────────────────────────────────────────────────────────────
        good_dir, net_steps, best_fwhm, best_net = self._probe(
            capture_frame, best_fwhm, net_steps, best_net
        )
        if good_dir is None:
            # Soft limits in both directions — stay put
            return FocusSearchResult(success=False, reason="no_improvement",
                                     best_fwhm=best_fwhm, net_steps=net_steps)

        # ── Scan ─────────────────────────────────────────────────────────────
        scan_reason, net_steps, best_fwhm, best_net, cancelled = self._scan(
            capture_frame, cancel_check, good_dir, net_steps, best_fwhm, best_net
        )

        if cancelled:
            self._return_to_best(net_steps, best_net)
            return FocusSearchResult(success=False, reason="cancelled",
                                     best_fwhm=best_fwhm, net_steps=best_net)

        # ── Backtrack to best position ────────────────────────────────────────
        net_steps = self._return_to_best(net_steps, best_net)

        if scan_reason == "star_lost" and best_fwhm == fwhm0:
            return FocusSearchResult(success=False, reason="star_lost",
                                     best_fwhm=best_fwhm, net_steps=net_steps)

        if scan_reason == "max_steps":
            return FocusSearchResult(success=False, reason="max_steps",
                                     best_fwhm=best_fwhm, net_steps=net_steps)

        # ── Final approach from configured direction ───────────────────────────
        net_steps, best_fwhm = self._final_approach(capture_frame, net_steps, best_fwhm)

        return FocusSearchResult(success=True, reason="in_focus",
                                 best_fwhm=best_fwhm, net_steps=net_steps)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _probe(
        self,
        capture_frame: Callable[[], FitsFrame],
        best_fwhm: float,
        net_steps: int,
        best_net: int,
    ) -> tuple[int | None, int, float, int]:
        """Try one step to determine which direction improves focus.

        Returns (good_dir, net_steps, best_fwhm, best_net).
        good_dir is +1 / -1; None if both directions are blocked.
        """
        coarse = self._cfg.coarse_step
        result = self._focuser.move_focus_relative(+coarse)
        actual = result.steps_taken

        if actual == 0:
            # Positive direction blocked — try negative
            result = self._focuser.move_focus_relative(-coarse)
            actual = result.steps_taken
            if actual == 0:
                return None, net_steps, best_fwhm, best_net
            net_steps += actual
            fwhm = self._get_fwhm(capture_frame)
            if fwhm is not None and fwhm < best_fwhm * (1 - self._impr_frac):
                best_fwhm = fwhm
                best_net  = net_steps
                return -1, net_steps, best_fwhm, best_net
            # Undo
            result2 = self._focuser.move_focus_relative(-actual)
            net_steps += result2.steps_taken
            return -1, net_steps, best_fwhm, best_net

        net_steps += actual
        fwhm = self._get_fwhm(capture_frame)
        if fwhm is not None and fwhm < best_fwhm * (1 - self._impr_frac):
            best_fwhm = fwhm
            best_net  = net_steps
            return +1, net_steps, best_fwhm, best_net

        # Positive didn't help — undo and go negative
        result2 = self._focuser.move_focus_relative(-actual)
        net_steps += result2.steps_taken
        return -1, net_steps, best_fwhm, best_net

    def _scan(
        self,
        capture_frame: Callable[[], FitsFrame],
        cancel_check: Callable[[], bool] | None,
        good_dir: int,
        net_steps: int,
        best_fwhm: float,
        best_net: int,
    ) -> tuple[str, int, float, int, bool]:
        """Scan in good_dir until focus stops improving.

        Returns (reason, net_steps, best_fwhm, best_net, cancelled).
        """
        coarse           = self._cfg.coarse_step
        consecutive_worse = 0

        for _ in range(self._max_coarse):
            if cancel_check and cancel_check():
                return "cancelled", net_steps, best_fwhm, best_net, True

            result = self._focuser.move_focus_relative(good_dir * coarse)
            actual = result.steps_taken
            if actual == 0:
                return "soft_limit", net_steps, best_fwhm, best_net, False

            net_steps += actual

            if self._settle_s > 0:
                time.sleep(self._settle_s)

            fwhm = self._get_fwhm(capture_frame)
            if fwhm is None:
                return "star_lost", net_steps, best_fwhm, best_net, False

            if fwhm < best_fwhm * (1 - self._impr_frac):
                best_fwhm         = fwhm
                best_net          = net_steps
                consecutive_worse = 0
            else:
                consecutive_worse += 1
                if consecutive_worse >= 2:
                    return "stalled", net_steps, best_fwhm, best_net, False

        return "max_steps", net_steps, best_fwhm, best_net, False

    def _return_to_best(self, net_steps: int, best_net: int) -> int:
        backtrack = best_net - net_steps
        if backtrack != 0:
            result = self._focuser.move_focus_relative(backtrack)
            net_steps += result.steps_taken
        return net_steps

    def _final_approach(
        self,
        capture_frame: Callable[[], FitsFrame],
        net_steps: int,
        best_fwhm: float,
    ) -> tuple[int, float]:
        """Overshoot in anti-approach direction then step in fine steps."""
        fine    = self._cfg.fine_step
        # Determine anti-approach direction in raw step sign
        # final_approach_direction == increasing_value_direction → positive raw
        final_is_positive = (
            self._cfg.final_approach_direction == self._cfg.increasing_value_direction
        )
        anti_sign = -1 if final_is_positive else +1

        overshoot = anti_sign * _FINAL_APPROACH_OVERSHOOT * fine
        r = self._focuser.move_focus_relative(overshoot)
        net_steps += r.steps_taken

        for _ in range(_MAX_FINE_STEPS):
            r = self._focuser.focus_fine()
            if r.steps_taken == 0:
                break
            net_steps += r.steps_taken

            if self._settle_s > 0:
                time.sleep(self._settle_s)

            fwhm = self._get_fwhm(capture_frame)
            if fwhm is None:
                break
            if fwhm < best_fwhm - _MIN_FWHM_IMPROVEMENT:
                best_fwhm = fwhm
            else:
                break

        return net_steps, best_fwhm

    def _get_fwhm(self, capture_frame: Callable[[], FitsFrame]) -> float | None:
        """Capture a frame and return FWHM if a star is detected, else None."""
        frame = capture_frame()
        processed = normalize_frame(frame, bit_depth=self._bit_depth)
        m = detect_star(processed)
        if m is None:
            return None
        return m.fwhm_px
