"""Focus sharpness metric — Laplacian variance of a 2-D pixel array.

Higher values mean sharper focus.  The autofocus algorithm maximises this
metric as it sweeps the focuser across its range.
"""

from __future__ import annotations

import numpy as np


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
