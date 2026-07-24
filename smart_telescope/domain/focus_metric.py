"""Focus sharpness metrics for a 2-D pixel array.

half_flux_diameter — primary metric, safe for SCTs (donut stars).
multi_star_hfd — the metric autofocus actually samples: detects several
    star-like blobs, measures each in isolation, returns the median. A
    real sky frame has many stars scattered across it and a background
    level that drifts over a long sweep; half_flux_diameter() alone
    operates on the whole frame, so on real data its result tracks that
    frame-wide drift instead of any star's blur (M10-051).
laplacian_variance — kept as a utility; NOT used for SCT autofocus because
    defocused SCT donuts have high edge energy on both sides of focus,
    producing two local maxima instead of one.
"""

from __future__ import annotations

import numpy as np

# ── multi_star_hfd tuning ──────────────────────────────────────────────────────
_STAR_THRESHOLD_SIGMA     = 6.0    # detection threshold above background
_MIN_STAR_BLOB_PIXELS     = 4      # reject hot-pixel spikes smaller than this
_MAX_STAR_BLOB_ROI_FRAC   = 0.9    # reject blobs covering > 90 % of the local ROI
                                   # (an isolated point source, however defocused,
                                   # should still fall off before filling its own
                                   # crop edge-to-edge; a blob that doesn't is more
                                   # likely a nebula/galaxy/satellite trail extending
                                   # beyond the crop, not a star). Relative to the
                                   # ROI itself, not the whole frame — a whole-frame
                                   # fraction is the wrong scale here: for any
                                   # realistically-sized sensor frame it would never
                                   # bind (the ROI's total pixel count is far smaller
                                   # than 2% of a multi-megapixel frame), so it would
                                   # silently never reject anything.
_STAR_ROI_HALF_SIZE       = 32     # half-side of the per-star isolation crop (px)
_DEFAULT_MAX_STARS        = 20     # stop after this many candidate peaks


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


def multi_star_hfd(arr: np.ndarray, max_stars: int = _DEFAULT_MAX_STARS) -> float | None:
    """Return the median Half-Flux Diameter across several detected stars.

    Repeatedly finds the brightest remaining peak above a MAD-based
    background threshold, isolates it in a small local crop, measures that
    crop's HFD, then masks the crop out before searching for the next peak
    — so each measurement reflects one star's own blur, not the whole
    frame's flux distribution (which a real multi-star sky frame with a
    drifting background would otherwise dominate; see module docstring).

    Returns None when no candidate blob passes the star-shape checks
    (blob too small = hot pixel / cosmic ray, or too large = nebula/
    saturated trail), rather than falling back to a whole-frame
    measurement — confirmed on real hardware data that a single hot pixel
    routinely outranks a heavily defocused real star (whose flux is spread
    so thin per-pixel that it never crosses the per-pixel threshold at
    all), so silently returning *some* number for such a frame is actively
    misleading, not just imprecise. Callers should treat None the same as
    AF-003's "focus quality UNKNOWN" — skip the sample rather than fit a
    curve through it.
    """
    if arr.ndim != 2:
        raise ValueError(f"Expected a 2-D array, got shape {arr.shape}")

    work = arr.astype(np.float64).copy()
    h, w = work.shape
    background = float(np.median(work))
    mad = float(np.median(np.abs(work - background)))
    sigma = 1.4826 * mad
    threshold = background + _STAR_THRESHOLD_SIGMA * sigma

    hfds: list[float] = []
    for _ in range(max_stars):
        peak_flat = int(np.argmax(work))
        peak_row, peak_col = divmod(peak_flat, w)
        if work[peak_row, peak_col] < threshold:
            break

        r0 = max(0, peak_row - _STAR_ROI_HALF_SIZE)
        r1 = min(h, peak_row + _STAR_ROI_HALF_SIZE + 1)
        c0 = max(0, peak_col - _STAR_ROI_HALF_SIZE)
        c1 = min(w, peak_col + _STAR_ROI_HALF_SIZE + 1)
        roi = work[r0:r1, c0:c1]
        max_blob = int(roi.size * _MAX_STAR_BLOB_ROI_FRAC)

        blob_size = int(np.sum(roi > threshold))
        if _MIN_STAR_BLOB_PIXELS <= blob_size <= max_blob and roi.shape[0] >= 3 and roi.shape[1] >= 3:
            hfds.append(half_flux_diameter(roi))

        # Remove this candidate regardless of accept/reject, so the next
        # iteration finds the next-brightest distinct source.
        work[r0:r1, c0:c1] = background

    if not hfds:
        return None

    return float(np.median(hfds))


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
