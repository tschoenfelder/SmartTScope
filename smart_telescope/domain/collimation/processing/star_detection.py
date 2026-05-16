"""Star detection — Collimation Phase 3, Task 3.3.

Finds the brightest star in a ProcessedFrame and returns a StarMeasurement.
Uses only NumPy; no scipy required.

Algorithm
---------
1. Estimate background (median + sigma-clip).
2. Locate peak pixel — that is the star candidate.
3. Extract a local ROI around the peak.
4. Compute intensity-weighted centroid.
5. Estimate FWHM from the radial profile.
6. Compute SNR and a heuristic confidence score.
7. Reject hot pixels (blob too small) and galaxies/nebulae (blob too large).
"""
from __future__ import annotations

import numpy as np

from ....domain.collimation.models import StarMeasurement
from .frame import ProcessedFrame
from .stretch import estimate_background

# ── Tunable constants ─────────────────────────────────────────────────────────

_THRESHOLD_SIGMA   = 5.0    # detection threshold above background
_MIN_BLOB_PIXELS   = 4      # reject hot-pixel spikes smaller than this
_MAX_BLOB_FRACTION = 0.02   # reject blobs covering > 2 % of the frame area
_ROI_HALF_SIZE     = 64     # half-side of the star extraction box (pixels)
_SNR_FULL_CONF     = 30.0   # SNR at which confidence saturates to 1.0
_MIN_FWHM          = 1.0    # reject stars narrower than 1 px (dead pixels)
_MAX_FWHM          = 60.0   # reject blobs wider than this (e.g. bright nebula)


def detect_star(frame: ProcessedFrame) -> StarMeasurement | None:
    """Find the brightest star in *frame*.

    Returns None when no convincing star is detected (sky too bright,
    hot pixel only, or completely dark frame).
    """
    data = frame.mono  # float32, (H, W)
    bg, sigma = estimate_background(data)

    # ── Peak search ───────────────────────────────────────────────────────────
    threshold = bg + _THRESHOLD_SIGMA * sigma
    if float(np.max(data)) < threshold:
        return None

    peak_flat = int(np.argmax(data))
    peak_row, peak_col = divmod(peak_flat, frame.width)
    peak_val = float(data[peak_row, peak_col])

    max_val = float(2 ** frame.bit_depth - 1)
    is_saturated = peak_val >= max_val * 0.99

    # ── ROI extraction ────────────────────────────────────────────────────────
    r0 = max(0, peak_row - _ROI_HALF_SIZE)
    r1 = min(frame.height, peak_row + _ROI_HALF_SIZE + 1)
    c0 = max(0, peak_col - _ROI_HALF_SIZE)
    c1 = min(frame.width, peak_col + _ROI_HALF_SIZE + 1)
    roi = data[r0:r1, c0:c1]

    # ── Blob size (hot-pixel / nebula rejection) ──────────────────────────────
    roi_mask = roi > threshold
    blob_size = int(np.sum(roi_mask))
    max_blob = max(_MIN_BLOB_PIXELS, int(frame.width * frame.height * _MAX_BLOB_FRACTION))
    if blob_size < _MIN_BLOB_PIXELS or blob_size > max_blob:
        return None

    # ── Centroid ──────────────────────────────────────────────────────────────
    roi_above = np.clip(roi.astype(np.float64) - bg, 0.0, None)
    total_flux = float(roi_above.sum())
    if total_flux <= 0.0:
        return None

    rows_grid = np.arange(r0, r1, dtype=np.float64)[:, np.newaxis]
    cols_grid = np.arange(c0, c1, dtype=np.float64)[np.newaxis, :]
    cx = float((roi_above * cols_grid).sum() / total_flux)
    cy = float((roi_above * rows_grid).sum() / total_flux)

    # ── FWHM ──────────────────────────────────────────────────────────────────
    rr, cc = np.mgrid[r0:r1, c0:c1]
    dist = np.sqrt((rr.astype(np.float64) - cy) ** 2
                   + (cc.astype(np.float64) - cx) ** 2)
    half_max_level = (peak_val - bg) * 0.5 + bg
    fwhm = _estimate_fwhm(dist, roi.astype(np.float64), half_max_level)

    # ── Confidence ────────────────────────────────────────────────────────────
    snr = (peak_val - bg) / sigma
    confidence = _confidence(snr, is_saturated, fwhm, blob_size, max_blob)
    if confidence < 0.1:
        return None

    return StarMeasurement(
        center_x=cx,
        center_y=cy,
        fwhm_px=fwhm,
        peak_adu=peak_val,
        total_flux=total_flux,
        snr=snr,
        confidence=confidence,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _estimate_fwhm(
    dist: np.ndarray,
    intensity: np.ndarray,
    half_max_level: float,
) -> float:
    """Estimate FWHM from a 2-D radial intensity profile.

    Sorts all pixels by distance from centroid, then finds the radius
    where the profile crosses half-maximum via linear interpolation.
    Returns FWHM in pixels (= 2 × half-radius).
    """
    order = np.argsort(dist.ravel())
    r_sorted = dist.ravel()[order]
    i_sorted = intensity.ravel()[order]

    above = i_sorted >= half_max_level
    if not np.any(above):
        return 2.0

    last_above_idx = int(np.where(above)[0][-1])
    if last_above_idx >= len(r_sorted) - 1:
        return float(r_sorted[-1]) * 2.0

    r_lo = float(r_sorted[last_above_idx])
    r_hi = float(r_sorted[last_above_idx + 1])
    i_lo = float(i_sorted[last_above_idx])
    i_hi = float(i_sorted[last_above_idx + 1])
    if i_lo == i_hi:
        half_r = r_lo
    else:
        t = (half_max_level - i_lo) / (i_hi - i_lo)
        half_r = r_lo + t * (r_hi - r_lo)

    return max(0.5, float(half_r) * 2.0)


def _confidence(
    snr: float,
    is_saturated: bool,
    fwhm: float,
    blob_size: int,
    max_blob: int,
) -> float:
    """Heuristic confidence ∈ [0, 1]."""
    snr_conf = min(1.0, snr / _SNR_FULL_CONF)
    sat_penalty = 0.3 if is_saturated else 0.0
    fwhm_penalty = 0.4 if not (_MIN_FWHM <= fwhm <= _MAX_FWHM) else 0.0
    size_penalty = 0.3 if blob_size > max_blob * 0.5 else 0.0
    return max(0.0, min(1.0, snr_conf - sat_penalty - fwhm_penalty - size_penalty))
