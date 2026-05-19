"""Live collimation monitor — Collimation Phase 9, COL-091.

Captures successive frames while the user turns a screw and reports whether
the collimation error is improving or worsening.  The caller supplies a
get_measurement callable (no args) that returns a DonutMeasurement or None;
this separation keeps image analysis out of the monitoring loop and makes
the monitor easy to unit-test.

Stop conditions
---------------
"converged"  : error < green_fraction × outer_radius  (rough collimation done).
"worsened"   : N consecutive frames without improvement (user should stop / reverse).
"star_lost"  : get_measurement returned None.
"cancelled"  : cancel_check() returned True.
"max_frames" : loop exhausted without converging.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from ...domain.collimation.models import DonutMeasurement

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class LiveGuidanceResult:
    """Outcome of a live collimation monitoring session.

    final_measurement : last DonutMeasurement obtained (None if star was lost
                        immediately).
    reason            : stop condition string.
    initial_error_px  : error magnitude at the start of monitoring.
    final_error_px    : error magnitude at the final measurement (None if lost).
    improvement_px    : initial_error − final_error; positive = improved.
    frame_count       : number of frames analysed (not counting the initial one).
    """
    final_measurement: DonutMeasurement | None
    reason: str
    initial_error_px: float
    final_error_px: float | None
    improvement_px: float
    frame_count: int


class LiveGuidanceMonitor:
    """Monitor donut measurements live while the user adjusts a screw.

    Args:
        settle_seconds         : wait between frames (default 1.0 s).
        max_frames             : give up after this many frames (default 30).
        improvement_fraction   : relative error drop required to count as
                                 improvement (default 5 %).
        max_consecutive_worse  : frames without improvement before reporting
                                 "worsened" (default 2).
        green_fraction         : error/outer_radius below which "converged"
                                 is declared (default 5 %).
    """

    def __init__(
        self,
        settle_seconds: float = 1.0,
        max_frames: int = 30,
        improvement_fraction: float = 0.05,
        max_consecutive_worse: int = 2,
        green_fraction: float = 0.05,
    ) -> None:
        self._settle_s      = settle_seconds
        self._max_frames    = max_frames
        self._impr_frac     = improvement_fraction
        self._max_worse     = max_consecutive_worse
        self._green_frac    = green_fraction

    def monitor(
        self,
        get_measurement: Callable[[], DonutMeasurement | None],
        initial_measurement: DonutMeasurement,
        cancel_check: Callable[[], bool] | None = None,
    ) -> LiveGuidanceResult:
        """Run the monitoring loop.

        Args:
            get_measurement     : callable (no args) that returns a
                                  DonutMeasurement or None if the donut is lost.
            initial_measurement : DonutMeasurement taken before the loop starts
                                  (used to compute improvement_px).
            cancel_check        : optional; returns True when the user cancelled.

        Returns:
            LiveGuidanceResult describing why monitoring stopped.
        """
        initial_error = initial_measurement.error_magnitude_px
        outer_r       = max(initial_measurement.outer_ring.mean_radius, 1.0)
        green_threshold = self._green_frac * outer_r

        best_error       = initial_error
        consecutive_worse = 0
        frame_count       = 0
        current           = initial_measurement

        for _ in range(self._max_frames):
            if cancel_check and cancel_check():
                return self._result(current, "cancelled", initial_error, frame_count)

            if self._settle_s > 0:
                time.sleep(self._settle_s)

            measurement = get_measurement()
            frame_count += 1

            if measurement is None:
                return LiveGuidanceResult(
                    final_measurement=None,
                    reason="star_lost",
                    initial_error_px=initial_error,
                    final_error_px=None,
                    improvement_px=initial_error - (current.error_magnitude_px if current else initial_error),
                    frame_count=frame_count,
                )

            current = measurement
            error   = measurement.error_magnitude_px

            _log.debug(
                "LiveGuidanceMonitor frame=%d error=%.1f best=%.1f green=%.1f",
                frame_count, error, best_error, green_threshold,
            )

            if error < green_threshold:
                return self._result(current, "converged", initial_error, frame_count)

            if error < best_error * (1.0 - self._impr_frac):
                best_error        = error
                consecutive_worse = 0
            else:
                consecutive_worse += 1
                if consecutive_worse >= self._max_worse:
                    return self._result(current, "worsened", initial_error, frame_count)

        return self._result(current, "max_frames", initial_error, frame_count)

    # ── Private ───────────────────────────────────────────────────────────────

    def _result(
        self,
        measurement: DonutMeasurement,
        reason: str,
        initial_error: float,
        frame_count: int,
    ) -> LiveGuidanceResult:
        final_error = measurement.error_magnitude_px
        return LiveGuidanceResult(
            final_measurement=measurement,
            reason=reason,
            initial_error_px=initial_error,
            final_error_px=final_error,
            improvement_px=initial_error - final_error,
            frame_count=frame_count,
        )
