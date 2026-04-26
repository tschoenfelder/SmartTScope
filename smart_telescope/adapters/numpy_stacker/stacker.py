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
    """

    def __init__(self) -> None:
        self._reference: np.ndarray[Any, np.dtype[Any]] | None = None
        self._frames: list[np.ndarray[Any, np.dtype[Any]]] = []
        self._rejected: int = 0

    def reset(self) -> None:
        self._reference = None
        self._frames = []
        self._rejected = 0

    def add_frame(self, frame: FitsFrame, frame_number: int) -> StackedImage:
        pixels = frame.pixels.astype(np.float32)

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

    def _build_result(self) -> StackedImage:
        if not self._frames:
            return StackedImage(data=b"", frames_integrated=0, frames_rejected=self._rejected)
        stacked: np.ndarray[Any, np.dtype[Any]] = np.mean(self._frames, axis=0).astype(np.float32)
        return StackedImage(
            data=_to_fits_bytes(stacked),
            frames_integrated=len(self._frames),
            frames_rejected=self._rejected,
        )


def _to_fits_bytes(pixels: np.ndarray[Any, np.dtype[Any]]) -> bytes:
    hdu = fits.PrimaryHDU(data=pixels)
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    return buf.getvalue()
