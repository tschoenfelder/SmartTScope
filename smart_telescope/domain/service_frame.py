"""Common frame input dataclass for all image-processing services (M7-005 / IF-001).

All image-processing services (autofocus, collimation, auto-gain, plate-solving)
consume a ServiceFrame.  Missing mandatory fields raise FrameValidationError.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

import numpy as np


class FrameValidationError(ValueError):
    """Raised when a mandatory ServiceFrame field is missing or invalid."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"ServiceFrame missing mandatory fields: {', '.join(missing)}")


# Fields that must be non-None for a valid ServiceFrame.
_MANDATORY = frozenset({
    "frame_id",
    "camera_id",
    "optical_train_id",
    "pixel_data",
    "bit_depth",
    "timestamp",
    "exposure_s",
    "gain",
    "binning_x",
    "binning_y",
    "sensor_width_px",
    "sensor_height_px",
})


@dataclass(frozen=True)
class ServiceFrame:
    """Common input type for all image-processing services.

    Mandatory fields must be set (non-None); optional fields default to None.
    Call .validate() to surface missing mandatory fields as FrameValidationError.
    """

    # ── mandatory ─────────────────────────────────────────────────────────────
    frame_id: str
    camera_id: str
    optical_train_id: str
    pixel_data: np.ndarray[Any, np.dtype[Any]]
    bit_depth: int
    timestamp: str                 # ISO-8601 UTC
    exposure_s: float
    gain: int
    binning_x: int
    binning_y: int
    sensor_width_px: int
    sensor_height_px: int

    # ── optional ──────────────────────────────────────────────────────────────
    is_mono_or_bayer: str | None = None   # "mono" | "bayer_rggb" | ...
    offset: int | None = None
    pixel_size_um: float | None = None
    effective_focal_length_mm: float | None = None
    ra: float | None = None            # hours
    dec: float | None = None           # degrees
    tracking_on: bool | None = None

    def validate(self) -> None:
        """Raise FrameValidationError if any mandatory field is None."""
        missing = [
            f.name
            for f in fields(self)
            if f.name in _MANDATORY and getattr(self, f.name) is None
        ]
        if missing:
            raise FrameValidationError(missing)

    @classmethod
    def from_fits_frame(
        cls,
        fits_frame: Any,  # FitsFrame — avoid circular import at module level
        *,
        frame_id: str,
        camera_id: str,
        optical_train_id: str,
        gain: int,
        binning_x: int = 1,
        binning_y: int = 1,
        sensor_width_px: int | None = None,
        sensor_height_px: int | None = None,
        timestamp: str | None = None,
        **kwargs: Any,
    ) -> "ServiceFrame":
        """Construct from a FitsFrame, mapping common FITS header fields."""
        import datetime

        pixels: np.ndarray = fits_frame.pixels  # type: ignore[union-attr]
        h, w = pixels.shape[:2]

        hdr = fits_frame.header or {}
        bit_depth_val: int = int(hdr.get("BITDEPTH", 16)) if hasattr(hdr, "get") else 16

        return cls(
            frame_id=frame_id,
            camera_id=camera_id,
            optical_train_id=optical_train_id,
            pixel_data=pixels,
            bit_depth=bit_depth_val,
            timestamp=timestamp or datetime.datetime.now(datetime.timezone.utc).isoformat(),
            exposure_s=fits_frame.exposure_seconds,
            gain=gain,
            binning_x=binning_x,
            binning_y=binning_y,
            sensor_width_px=sensor_width_px if sensor_width_px is not None else w,
            sensor_height_px=sensor_height_px if sensor_height_px is not None else h,
            **kwargs,
        )
