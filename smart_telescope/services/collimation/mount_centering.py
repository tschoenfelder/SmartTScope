"""Safe pulse-guide star centering — Collimation Phase 4, Task 4.1.

Converts a pixel offset (star − reference_center) into guide pulses,
iterates until the star is within tolerance, and stops safely on:
  - star lost
  - repeated divergence
  - cancellation
  - max iteration limit

No camera logic lives here — the caller provides a measurement function
so the centering loop can be tested without hardware.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass
from typing import Callable

from ...domain.collimation.config import MountCenteringConfig
from ...ports.mount import MountPort

_log = logging.getLogger(__name__)

# Sidereal rate at the equator (arcsec / s).
_SIDEREAL_ARCSEC_PER_S: float = 15.041


@dataclass(frozen=True)
class MountCorrectionResult:
    """Outcome of a pulse-guide centering attempt.

    success         : True when the star landed within fine_tolerance_px.
    pulses_issued   : total number of individual guide pulses sent.
    final_offset_px : |star − reference| in pixels at the last measurement.
    reason          : one of "within_tolerance", "star_lost", "diverging",
                      "max_pulses", "cancelled".
    """
    success: bool
    pulses_issued: int
    final_offset_px: float
    reason: str


class PulseCenterer:
    """Iterative pulse-guide centering loop for collimation star acquisition.

    Algorithm per iteration
    -----------------------
    1. Call ``get_offset_px()`` → (dx, dy) in pixels from reference center.
    2. If None → star lost → abort.
    3. If |offset| ≤ fine_tolerance_px → done.
    4. Choose largest axis, derive guide direction and pulse duration.
    5. Clamp to max_pulse_ms.
    6. Issue guide pulse via ``MountPort.guide()``.
    7. Wait settle_ms.
    8. Repeat.

    Divergence detection
    --------------------
    If the distance grows by > 10 % compared with the previous iteration,
    increment a counter.  After ``max_diverge_count`` consecutive divergent
    steps the loop aborts with ``reason="diverging"``.

    Coordinate convention (image pixels)
    -------------------------------------
    - x increases east (right).  dx > 0 → guide west ("w").
    - y increases south (down).  dy > 0 → guide north ("n").
    This matches the standard equatorial telescope orientation; add a flip
    flag in a later phase if the optical train reverses one axis.
    """

    def __init__(
        self,
        mount: MountPort,
        config: MountCenteringConfig,
        pixel_scale_arcsec: float,
        guide_rate_factor: float = 0.5,
        max_iterations: int = 30,
        max_diverge_count: int = 3,
    ) -> None:
        """
        Args:
            mount               : live or mock MountPort.
            config              : tolerances and pulse limits from CollimationConfig.
            pixel_scale_arcsec  : arcsec / pixel for the current optical train.
            guide_rate_factor   : fraction of sidereal rate (default 0.5 ×).
            max_iterations      : hard cap on correction cycles.
            max_diverge_count   : abort after this many consecutive diverging steps.
        """
        self._mount = mount
        self._cfg = config
        self._pixel_scale = pixel_scale_arcsec
        self._guide_rate_factor = guide_rate_factor
        self._max_iter = max_iterations
        self._max_diverge = max_diverge_count

    def center(
        self,
        get_offset_px: Callable[[], tuple[float, float] | None],
        cancel_check: Callable[[], bool] | None = None,
        dec_deg: float = 0.0,
    ) -> MountCorrectionResult:
        """Run the centering loop.

        Args:
            get_offset_px : callable returning (dx_px, dy_px) offset of the
                            star from the reference center, or None if the star
                            is not detected.  Called before each pulse and once
                            after the last one to measure final position.
            cancel_check  : optional callable returning True when the operator
                            has requested cancellation.
            dec_deg       : current declination in degrees; used to scale the
                            RA guide rate by cos(dec).

        Returns:
            MountCorrectionResult describing the outcome.
        """
        cos_dec = math.cos(math.radians(dec_deg))
        ra_rate_as_per_ms = (
            _SIDEREAL_ARCSEC_PER_S * max(abs(cos_dec), 0.1) * self._guide_rate_factor
        ) / 1000.0
        dec_rate_as_per_ms = (
            _SIDEREAL_ARCSEC_PER_S * self._guide_rate_factor
        ) / 1000.0

        pulses = 0
        prev_dist: float | None = None
        diverge_count = 0

        for iteration in range(self._max_iter):
            if cancel_check and cancel_check():
                return MountCorrectionResult(
                    success=False,
                    pulses_issued=pulses,
                    final_offset_px=prev_dist if prev_dist is not None else 999.0,
                    reason="cancelled",
                )

            offset = get_offset_px()
            if offset is None:
                _log.warning("PulseCenterer: star lost at iteration %d", iteration)
                return MountCorrectionResult(
                    success=False,
                    pulses_issued=pulses,
                    final_offset_px=999.0,
                    reason="star_lost",
                )

            dx, dy = float(offset[0]), float(offset[1])
            dist = math.hypot(dx, dy)

            _log.debug(
                "PulseCenterer iter=%d offset=(%.1f, %.1f)px dist=%.1fpx",
                iteration, dx, dy, dist,
            )

            if dist <= self._cfg.fine_tolerance_px:
                return MountCorrectionResult(
                    success=True,
                    pulses_issued=pulses,
                    final_offset_px=dist,
                    reason="within_tolerance",
                )

            # Divergence bookkeeping
            if prev_dist is not None:
                if dist > prev_dist * 1.1:
                    diverge_count += 1
                    if diverge_count >= self._max_diverge:
                        _log.warning(
                            "PulseCenterer: diverging for %d iterations, aborting",
                            self._max_diverge,
                        )
                        return MountCorrectionResult(
                            success=False,
                            pulses_issued=pulses,
                            final_offset_px=dist,
                            reason="diverging",
                        )
                else:
                    diverge_count = max(0, diverge_count - 1)
            prev_dist = dist

            # Choose the dominant axis for this correction step.
            if abs(dx) >= abs(dy):
                direction = "w" if dx > 0 else "e"
                offset_arcsec = abs(dx) * self._pixel_scale
                rate = ra_rate_as_per_ms
            else:
                direction = "n" if dy > 0 else "s"
                offset_arcsec = abs(dy) * self._pixel_scale
                rate = dec_rate_as_per_ms

            pulse_ms = int(min(
                offset_arcsec / max(rate, 1e-9),
                self._cfg.max_pulse_ms,
            ))
            pulse_ms = max(1, pulse_ms)

            _log.debug(
                "PulseCenterer: guide %s for %d ms", direction, pulse_ms
            )
            self._mount.guide(direction, pulse_ms)
            pulses += 1

            if self._cfg.settle_ms > 0:
                time.sleep(self._cfg.settle_ms / 1000.0)

        # Exhausted max iterations — check final position.
        final_offset = get_offset_px()
        if final_offset is None:
            final_dist = 999.0
        else:
            final_dist = math.hypot(*final_offset)

        return MountCorrectionResult(
            success=final_dist <= self._cfg.rough_tolerance_px,
            pulses_issued=pulses,
            final_offset_px=final_dist,
            reason="max_pulses",
        )
