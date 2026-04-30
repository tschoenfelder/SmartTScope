"""Shared types and constants for the workflow layer."""

from collections.abc import Callable
from dataclasses import dataclass

from ..domain.session import SessionLog
from ..domain.states import SessionState

# ── Callback type ────────────────────────────────────────────────────────────

StateCallback = Callable[[SessionState], None]
TransitionCallback = Callable[[SessionLog, SessionState], None]

# ── Exceptions ───────────────────────────────────────────────────────────────


class WorkflowError(Exception):
    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason
        super().__init__(f"[{stage}] {reason}")


# ── Optical profiles ─────────────────────────────────────────────────────────


@dataclass
class OpticalProfile:
    name: str
    pixel_scale_arcsec: float  # hint passed to the plate solver


C8_NATIVE   = OpticalProfile("C8-native",   pixel_scale_arcsec=0.38)
C8_REDUCER  = OpticalProfile("C8-reducer",  pixel_scale_arcsec=0.60)
C8_BARLOW2X = OpticalProfile("C8-barlow2x", pixel_scale_arcsec=0.19)

# ── Target ───────────────────────────────────────────────────────────────────

M42_RA  = 5.5881   # hours  (05h 35m 17.3s)
M42_DEC = -5.391   # degrees (−05° 23′ 28″)

# ── Session tuning ───────────────────────────────────────────────────────────

WIDE_FIELD_SEARCH_RADIUS_DEG = 180.0
AUTOFOCUS_RANGE_STEPS   = 200
AUTOFOCUS_STEP_SIZE     = 20
AUTOFOCUS_EXPOSURE_S    = 3.0
AUTOFOCUS_BACKLASH_STEPS = 0
REFOCUS_TEMP_DELTA_C     = 1.0
REFOCUS_ALT_DELTA_DEG    = 5.0
REFOCUS_ELAPSED_MIN      = 30.0
FRAME_QUALITY_MIN_SNR_FACTOR = 0.3
FRAME_QUALITY_BASELINE_FRAMES = 3
CENTERING_TOLERANCE_ARCMIN = 2.0
MAX_RECENTER_ITERATIONS    = 3
SOLVE_MAX_ATTEMPTS         = 2
PREVIEW_FRAMES             = 3
STACK_DEPTH                = 10
PREVIEW_EXPOSURE_S         = 5.0
STACK_EXPOSURE_S           = 30.0
SLEW_TIMEOUT_S             = 120.0
SLEW_POLL_INTERVAL_S       = 2.0
RECENTER_EVERY_N_FRAMES    = 5   # mid-stack recenter cadence
