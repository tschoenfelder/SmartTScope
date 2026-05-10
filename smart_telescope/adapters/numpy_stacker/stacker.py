"""NumpyStacker — real frame stacker using astroalign registration."""

from __future__ import annotations

import io
import logging
from typing import Any

import numpy as np
from astropy.io import fits

from ...domain.frame import FitsFrame
from ...ports.stacker import StackedImage, StackerPort

logger = logging.getLogger(__name__)

try:
    import astroalign as _aa
except ImportError:
    _aa = None


class NumpyStacker(StackerPort):
    """Mean-stack frames after astroalign registration against the first frame.

    Frames that cannot be registered are silently rejected and counted.
    Calibration masters (dark, flat) can be supplied via set_calibration().
    """

    def __init__(self) -> None:
        self._reference: np.ndarray[Any, np.dtype[Any]] | None = None
        self._frames: list[np.ndarray[Any, np.dtype[Any]]] = []
        self._rejected: int = 0
        self._dark: np.ndarray[Any, np.dtype[Any]] | None = None
        self._flat_norm: np.ndarray[Any, np.dtype[Any]] | None = None

    def set_calibration(
        self,
        bias: np.ndarray[Any, np.dtype[Any]] | None = None,
        dark: np.ndarray[Any, np.dtype[Any]] | None = None,
        flat: np.ndarray[Any, np.dtype[Any]] | None = None,
    ) -> None:
        """Set calibration masters. Dark takes precedence over bias for subtraction.

        If both dark and bias are supplied, only dark is used (dark already includes bias).
        Flat is normalised to its own mean before storage.
        """
        if dark is not None:
            self._dark = dark.astype(np.float32)
        elif bias is not None:
            self._dark = bias.astype(np.float32)
        else:
            self._dark = None

        if flat is not None:
            flat_f = flat.astype(np.float32)
            flat_mean = float(np.mean(flat_f))
            self._flat_norm = flat_f / flat_mean if flat_mean > 0 else None
        else:
            self._flat_norm = None

    def reset(self) -> None:
        self._reference = None
        self._frames = []
        self._rejected = 0

    def add_frame(self, frame: FitsFrame, frame_number: int) -> StackedImage:
        pixels = frame.pixels.astype(np.float32)
        pixels = self._calibrate(pixels)

        if self._reference is None:
            self._reference = pixels
            self._frames.append(pixels)
            logger.debug("Frame %d set as reference", frame_number)
        else:
            if _aa is None:
                raise ImportError("astroalign is required for stacking: pip install astroalign")
            try:
                registered, _ = _aa.register(pixels, self._reference)
                self._frames.append(registered.astype(np.float32))
                logger.debug("Frame %d registered OK (%d integrated)", frame_number, len(self._frames))  # noqa: E501
            except Exception as exc:
                self._rejected += 1
                logger.warning("Frame %d rejected (registration failed): %s", frame_number, exc)

        return self._build_result()

    def get_current_stack(self) -> StackedImage:
        return self._build_result()

    def _calibrate(self, pixels: np.ndarray[Any, np.dtype[Any]]) -> np.ndarray[Any, np.dtype[Any]]:
        if self._dark is not None:
            pixels = pixels - self._dark
        if self._flat_norm is not None:
            pixels = pixels / self._flat_norm
        return pixels

    def _build_result(self) -> StackedImage:
        if not self._frames:
            return StackedImage(data=b"", frames_integrated=0, frames_rejected=self._rejected)
        stacked: np.ndarray[Any, np.dtype[Any]] = np.mean(self._frames, axis=0).astype(np.float32)
        calibrated = self._dark is not None or self._flat_norm is not None
        return StackedImage(
            data=_to_fits_bytes(stacked),
            frames_integrated=len(self._frames),
            frames_rejected=self._rejected,
            calibrated=calibrated,
        )


def _to_fits_bytes(pixels: np.ndarray[Any, np.dtype[Any]]) -> bytes:
    hdu = fits.PrimaryHDU(data=pixels)
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    return buf.getvalue()
