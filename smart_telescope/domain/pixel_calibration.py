"""Domain models for pixel-to-RA/DEC calibration (M7-003 / DD-004)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class PixelCalibrationError(Exception):
    """Raised when pixel calibration fails or is unavailable.

    The caller should block the requesting operation and surface the reason
    to the user together with a Retry option.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PixelCalibrationState(Enum):
    UNCALIBRATED = auto()   # no calibration stored
    CALIBRATING  = auto()   # calibration procedure in progress
    CALIBRATED   = auto()   # valid calibration available
    FAILED       = auto()   # last attempt failed; blocked until user retries


@dataclass(frozen=True)
class PixelCalibration:
    """Pixel-to-sky mapping for one optical train configuration.

    ra_vector_px  : (dx, dy) pixel displacement per 1 arcsec of RA motion
    dec_vector_px : (dx, dy) pixel displacement per 1 arcsec of DEC motion
    """

    ra_vector_px: tuple[float, float]
    dec_vector_px: tuple[float, float]
    optical_train_id: str
    binning: int
    camera_orientation_deg: float
    calibrated_at: str  # ISO-8601 UTC

    def to_pixel_offset(self, delta_ra_arcsec: float, delta_dec_arcsec: float) -> tuple[float, float]:
        """Convert sky offset (arcsec) to pixel displacement (dx, dy)."""
        dx = self.ra_vector_px[0] * delta_ra_arcsec + self.dec_vector_px[0] * delta_dec_arcsec
        dy = self.ra_vector_px[1] * delta_ra_arcsec + self.dec_vector_px[1] * delta_dec_arcsec
        return dx, dy
