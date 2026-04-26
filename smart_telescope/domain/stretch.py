"""Auto-stretch for display: maps science pixels to uint8 for JPEG output."""

from __future__ import annotations

from typing import Any

import numpy as np


def auto_stretch(pixels: np.ndarray[Any, np.dtype[Any]]) -> np.ndarray[Any, np.dtype[np.uint8]]:
    """Percentile-clip linear stretch: 0.5th–99.5th percentile → [0, 255] uint8.

    Handles uniform arrays (all-zero MockCamera frames) by returning black.
    """
    lo = float(np.percentile(pixels, 0.5))
    hi = float(np.percentile(pixels, 99.5))
    if hi <= lo:
        return np.zeros(pixels.shape, dtype=np.uint8)
    scaled = (pixels.astype(np.float64) - lo) / (hi - lo) * 255.0
    return np.clip(scaled, 0.0, 255.0).astype(np.uint8)
