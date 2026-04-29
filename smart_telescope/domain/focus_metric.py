"""Focus sharpness metrics for a 2-D pixel array.

half_flux_diameter — primary metric, safe for SCTs (donut stars).
laplacian_variance — kept as a utility; NOT used for SCT autofocus because
    defocused SCT donuts have high edge energy on both sides of focus,
    producing two local maxima instead of one.
"""

from __future__ import annotations

import numpy as np


def half_flux_diameter(arr: np.ndarray) -> float:
    """Return the Half-Flux Diameter (HFD) in pixels.

    HFD is the diameter of the circle centred on the flux-weighted centroid
    that contains half the total star flux.  Lower = tighter star = better
    focus.  Monotonically V-shaped around focus even for SCT optics where
    defocused stars appear as donuts.
    """
    if arr.ndim != 2:
        raise ValueError(f"Expected a 2-D array, got shape {arr.shape}")
    if arr.shape[0] < 3 or arr.shape[1] < 3:
        raise ValueError(f"Array too small for HFD (minimum 3×3), got {arr.shape}")

    a = arr.astype(np.float64)
    background = float(np.median(a))
    a = np.clip(a - background, 0.0, None)

    total_flux = float(a.sum())
    if total_flux <= 0.0:
        return float(max(arr.shape))

    rows, cols = np.indices(a.shape, dtype=np.float64)
    cx = float((a * cols).sum() / total_flux)
    cy = float((a * rows).sum() / total_flux)

    r = np.sqrt((cols - cx) ** 2 + (rows - cy) ** 2)
    order = np.argsort(r.ravel())
    cumflux = np.cumsum(a.ravel()[order])
    sorted_r = r.ravel()[order]

    idx = int(np.searchsorted(cumflux, total_flux / 2.0))
    idx = min(idx, len(sorted_r) - 1)
    return float(sorted_r[idx]) * 2.0


def laplacian_variance(arr: np.ndarray) -> float:
    """Return the variance of the discrete Laplacian of *arr*.

    Uses the 4-connected approximation:
        L[i,j] = 4·arr[i,j] - arr[i-1,j] - arr[i+1,j] - arr[i,j-1] - arr[i,j+1]

    The result is zero for a uniform array and grows with high-frequency
    spatial content (sharp edges, star discs at focus).
    """
    if arr.ndim != 2:
        raise ValueError(f"Expected a 2-D array, got shape {arr.shape}")
    if arr.shape[0] < 3 or arr.shape[1] < 3:
        raise ValueError(f"Array too small for Laplacian (minimum 3×3), got {arr.shape}")
    a = arr.astype(np.float64)
    lap = (
        4 * a[1:-1, 1:-1]
        - a[:-2, 1:-1]
        - a[2:, 1:-1]
        - a[1:-1, :-2]
        - a[1:-1, 2:]
    )
    return float(np.var(lap))
