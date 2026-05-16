"""Star acquisition for collimation — Phase 5, Task 5.2.

Orchestrates: slew → wait → enable tracking → settle → capture →
detect star → center via pulse-guide.

No camera-exposure tuning lives here (that is Phase 6 auto-exposure).
The caller sets the exposure and gain before calling acquire().
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

from ...domain.collimation.models import StarMeasurement
from ...domain.collimation.processing.frame import normalize_frame
from ...domain.collimation.processing.star_detection import detect_star
from ...ports.camera import CameraPort
from ...ports.mount import MountPort, MountState
from .mount_centering import MountCorrectionResult, PulseCenterer
from .star_selector import CollimationStarCandidate

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class AcquisitionResult:
    """Outcome of slew + detect + center."""
    success: bool
    reason: str    # "ok" | "slew_failed" | "star_not_found" | "centering_failed" | "cancelled"
    star_measurement: StarMeasurement | None
    centering: MountCorrectionResult | None


class StarAcquisition:
    """Slew to a collimation star candidate, detect it, and center it.

    The caller provides a pre-built PulseCenterer (which carries pixel scale
    and guide configuration).  Camera gain and exposure must be set before
    calling acquire().
    """

    _SLEW_POLL_S:    float = 0.5
    _SLEW_TIMEOUT_S: float = 120.0

    def __init__(
        self,
        mount: MountPort,
        camera: CameraPort,
        centerer: PulseCenterer,
        exposure_seconds: float = 1.0,
        settle_seconds: float = 2.0,
    ) -> None:
        self._mount = mount
        self._camera = camera
        self._centerer = centerer
        self._exposure_s = exposure_seconds
        self._settle_s = settle_seconds

    def acquire(
        self,
        candidate: CollimationStarCandidate,
        cancel_check: Callable[[], bool] | None = None,
        dec_deg: float = 0.0,
    ) -> AcquisitionResult:
        """Slew to candidate, detect the star, and center it.

        Args:
            candidate    : star to acquire (from CollimationStarSelector).
            cancel_check : optional callable; returns True when the operator
                           has requested cancellation.
            dec_deg      : declination in degrees for RA guide-rate scaling.
        """
        if cancel_check and cancel_check():
            return AcquisitionResult(success=False, reason="cancelled",
                                     star_measurement=None, centering=None)

        # Slew
        ok = self._mount.goto(candidate.star.ra_hours, candidate.star.dec_deg)
        if not ok:
            _log.warning("goto() failed for %s", candidate.star.name)
            return AcquisitionResult(success=False, reason="slew_failed",
                                     star_measurement=None, centering=None)

        # Wait for slew to complete
        deadline = time.monotonic() + self._SLEW_TIMEOUT_S
        while self._mount.is_slewing():
            if time.monotonic() > deadline:
                _log.warning("Slew timed out for %s", candidate.star.name)
                return AcquisitionResult(success=False, reason="slew_failed",
                                         star_measurement=None, centering=None)
            if cancel_check and cancel_check():
                self._mount.stop()
                return AcquisitionResult(success=False, reason="cancelled",
                                         star_measurement=None, centering=None)
            time.sleep(self._SLEW_POLL_S)

        # Enable tracking
        if self._mount.get_state() != MountState.TRACKING:
            self._mount.enable_tracking()

        # Settle
        time.sleep(self._settle_s)

        if cancel_check and cancel_check():
            return AcquisitionResult(success=False, reason="cancelled",
                                     star_measurement=None, centering=None)

        # Initial detection
        frame = self._camera.capture(self._exposure_s)
        bit_depth = self._camera.get_bit_depth()
        processed = normalize_frame(frame, bit_depth=bit_depth)
        measurement = detect_star(processed)

        if measurement is None:
            _log.warning("No star detected after slew to %s", candidate.star.name)
            return AcquisitionResult(success=False, reason="star_not_found",
                                     star_measurement=None, centering=None)

        # Centering loop — capture a fresh frame each iteration
        cx = processed.width  / 2.0
        cy = processed.height / 2.0

        def _get_offset() -> tuple[float, float] | None:
            f = self._camera.capture(self._exposure_s)
            p = normalize_frame(f, bit_depth=self._camera.get_bit_depth())
            m = detect_star(p)
            if m is None:
                return None
            return m.center_x - cx, m.center_y - cy

        centering = self._centerer.center(
            get_offset_px=_get_offset,
            cancel_check=cancel_check,
            dec_deg=dec_deg,
        )

        if centering.success:
            f3 = self._camera.capture(self._exposure_s)
            p3 = normalize_frame(f3, bit_depth=self._camera.get_bit_depth())
            final_m = detect_star(p3) or measurement
            return AcquisitionResult(success=True, reason="ok",
                                     star_measurement=final_m, centering=centering)

        return AcquisitionResult(
            success=False,
            reason="centering_failed",
            star_measurement=measurement,
            centering=centering,
        )
