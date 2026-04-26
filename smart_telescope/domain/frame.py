"""FitsFrame — typed domain object carrying a single camera exposure."""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from astropy.io import fits


@dataclass(frozen=True)
class FitsFrame:
    """Immutable container for a single FITS image from the camera.

    pixels: float32 ndarray shaped (height, width)
    header: parsed FITS header
    exposure_seconds: value from EXPTIME header key, or 0.0 if absent
    data: raw FITS bytes (empty when constructed directly from arrays)
    """

    pixels: np.ndarray[Any, np.dtype[Any]]
    header: object
    exposure_seconds: float
    data: bytes = field(default=b"")

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])

    def to_fits_bytes(self) -> bytes:
        """Return raw FITS bytes, serializing from pixels if no cached bytes exist."""
        if self.data:
            return self.data
        hdr = self.header if isinstance(self.header, fits.Header) else fits.Header()
        hdu = fits.PrimaryHDU(data=self.pixels, header=hdr)
        buf = io.BytesIO()
        fits.HDUList([hdu]).writeto(buf)
        return buf.getvalue()

    @classmethod
    def from_fits_bytes(cls, raw: bytes) -> FitsFrame:
        try:
            with fits.open(io.BytesIO(raw)) as hdul:
                hdu = hdul[0]
                header = hdu.header.copy()
                pixels: np.ndarray[Any, np.dtype[Any]] = np.array(hdu.data, dtype=np.float32)
                exposure_seconds = float(header.get("EXPTIME", 0.0))
        except Exception as exc:
            raise ValueError(f"Cannot parse FITS data: {exc}") from exc
        return cls(pixels=pixels, header=header, exposure_seconds=exposure_seconds, data=raw)
