"""Display stretch pipeline — Collimation Phase 3, Task 3.2.

Provides contrast stretching for overlay display, background estimation,
and saturation detection.  All functions operate on float32/uint16 arrays
and do not mutate the input.
"""
from __future__ import annotations

import numpy as np


def estimate_background(data: np.ndarray) -> tuple[float, float]:
    """Return (background_median, background_sigma) via iterative sigma-clipping.

    Clips outliers above 3-sigma from the running median for up to 5 iterations.
    Convergence is typical by iteration 3 for astronomical images.
    """
    flat = data.ravel().astype(np.float64)
    for _ in range(5):
        median = float(np.median(flat))
        sigma = float(np.std(flat))
        if sigma == 0.0:
            return median, 1.0
        clipped = flat[flat < median + 3.0 * sigma]
        if len(clipped) < 10 or len(clipped) == len(flat):
            flat = clipped if len(clipped) >= 10 else flat
            break
        flat = clipped

    bg = float(np.median(flat))
    sigma = float(np.std(flat)) if len(flat) > 1 else 1.0
    return bg, max(sigma, 1.0)


def auto_stretch(
    data: np.ndarray,
    low_percentile: float = 0.5,
    high_percentile: float = 99.9,
) -> np.ndarray:
    """Return a uint8 contrast-stretched copy for display.

    Clips to [low_percentile, high_percentile] then maps linearly to [0, 255].
    Does not mutate the input.
    """
    lo = float(np.percentile(data, low_percentile))
    hi = float(np.percentile(data, high_percentile))
    if hi <= lo:
        hi = lo + 1.0
    stretched = np.clip(
        (data.astype(np.float32) - lo) / (hi - lo),
        0.0, 1.0,
    )
    return (stretched * 255.0).astype(np.uint8)


def saturation_fraction(data: np.ndarray, bit_depth: int) -> float:
    """Return fraction [0, 1] of pixels at or above 99 % of full-well capacity."""
    threshold = float(2 ** bit_depth - 1) * 0.99
    return float(np.sum(data >= threshold)) / max(1, data.size)


def peak_location(data: np.ndarray) -> tuple[float, float, float]:
    """Return (col, row, value) of the brightest pixel."""
    idx = int(np.argmax(data))
    row, col = divmod(idx, data.shape[1])
    return float(col), float(row), float(data.ravel()[idx])
