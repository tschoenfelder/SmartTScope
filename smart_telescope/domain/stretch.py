"""Auto-stretch for display: maps science pixels to uint8 for JPEG output."""

from __future__ import annotations

from typing import Any

import numpy as np


def auto_stretch(
    pixels: np.ndarray[Any, np.dtype[Any]],
    adc_max: float = 65535.0,
) -> np.ndarray[Any, np.dtype[np.uint8]]:
    """Background-subtracted sigma stretch → [0, 255] uint8.

    Uses median + MAD-based sigma so the sky background maps to black and faint
    stars remain visible.  Falls back to percentile stretch for uniform frames
    (MockCamera, all-zero data) where sigma is negligible.
    """
    flat = pixels.ravel().astype(np.float64)
    background = float(np.median(flat))
    mad = float(np.median(np.abs(flat - background)))
    sigma = mad / 0.6745  # robust sigma from median absolute deviation
    if sigma < 0.5:
        lo = float(np.percentile(flat, 0.5))
        hi = float(np.percentile(flat, 99.5))
    else:
        lo = max(0.0, background - 1.5 * sigma)
        hi = background + 15.0 * sigma
    if hi <= lo:
        # Uniform frame — no dynamic range to stretch. Map it to flat grey at
        # its true relative brightness rather than always black, so a fully
        # saturated/overexposed capture (background == adc_max) renders white
        # instead of looking identical to a dark/no-signal frame.
        level = float(np.clip(background / adc_max, 0.0, 1.0) * 255.0)
        return np.full(pixels.shape, level, dtype=np.uint8)
    stretch_range = hi - lo
    x = (pixels.astype(np.float64) - lo) / stretch_range
    scaled = np.arcsinh(x * 3.0) / np.arcsinh(3.0) * 255.0
    return np.clip(scaled, 0.0, 255.0).astype(np.uint8)
