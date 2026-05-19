"""Touptek frame normalization — Collimation Phase 3, Task 3.1.

Converts a FitsFrame (float32, any bit depth) into a ProcessedFrame
that collimation algorithms can consume without touching hardware.
Does NOT mutate the input frame.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np

from ....domain.frame import FitsFrame


@dataclass(frozen=True)
class ProcessedFrame:
    """Normalized single-frame output for collimation processing.

    raw       : uint16 pixel data, shape (height, width).
                Values are clamped from the float32 source.
    mono      : float32 grayscale copy, same shape, same values.
                Range is [0, 2**bit_depth − 1] (not normalized to [0, 1]).
    bit_depth : sensor bit depth (8 or 16).
    width, height : frame dimensions in pixels.
    timestamp : capture timestamp (time.monotonic(), seconds).

    Use the ``normalized`` property to obtain a [0, 1] float32 view.
    """

    raw: np.ndarray        # uint16, (height, width)
    mono: np.ndarray       # float32, (height, width)
    bit_depth: int
    width: int
    height: int
    timestamp: float

    @property
    def normalized(self) -> np.ndarray:
        """Return float32 array normalized to [0, 1]."""
        max_val = float(2 ** self.bit_depth - 1)
        return self.mono / max_val


def normalize_frame(
    fits_frame: FitsFrame,
    bit_depth: int = 16,
) -> ProcessedFrame:
    """Convert a FitsFrame to a ProcessedFrame.

    Works for ATR585M and G3M678M mono frames.  For colour sensors the caller
    should demosaic first; this function treats the pixel array as mono.

    Args:
        fits_frame: immutable container from the camera adapter.
        bit_depth:  sensor bit depth (8 or 16).  Defaults to 16.

    Returns:
        ProcessedFrame with independent copies of the pixel data.
    """
    pix = fits_frame.pixels  # float32, (H, W)
    if pix.dtype != np.float32:
        pix = pix.astype(np.float32)
    else:
        pix = pix.copy()  # own copy — do not alias the FitsFrame buffer

    raw = np.clip(pix, 0.0, float(2 ** bit_depth - 1)).astype(np.uint16)

    return ProcessedFrame(
        raw=raw,
        mono=pix,
        bit_depth=bit_depth,
        width=fits_frame.width,
        height=fits_frame.height,
        timestamp=time.monotonic(),
    )
