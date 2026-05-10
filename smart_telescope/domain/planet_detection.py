"""Planet / bright-object detection for PLANET_PROTECTED auto-gain mode.

Scores candidate components by total_flux × √area so that a compact bright
disk (planet) beats a collection of hot pixels or faint stars.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

_log = logging.getLogger(__name__)

_THRESHOLD_FRAC = 0.50   # candidate pixels: those above (frame_max × this)
_MIN_AREA_PX    = 4      # components smaller than this are treated as hot pixels


@dataclass(frozen=True)
class DetectedObject:
    """Brightest real object found in a camera frame."""
    center_px: tuple[int, int]   # (row, col) centroid
    radius_px: float             # approximate radius = √(area / π)
    peak_frac: float             # brightest pixel in object / ADC max
    saturation_pct: float        # % of object pixels at ≥ 99 % full-scale


def detect_planet(pixels: np.ndarray, bit_depth: int = 16) -> DetectedObject | None:
    """Return the highest-scoring object in *pixels*, or None when the frame is dark.

    Score per connected component = total_flux × √area.
    This favours large bright disks over isolated hot pixels (area ≈ 1).
    Components with area < _MIN_AREA_PX are rejected as hot pixels.
    """
    adc_max = float((1 << bit_depth) - 1)
    norm = pixels.astype(np.float32) / adc_max

    pix_max = float(norm.max())
    if pix_max < 0.01:
        _log.debug("PlanetDetect: frame too dark (max=%.4f)", pix_max)
        return None

    threshold = pix_max * _THRESHOLD_FRAC
    mask = norm >= threshold

    labels, n_labels = _label(mask)
    if n_labels == 0:
        return None

    best_score = -1.0
    best_label = -1
    for lbl in range(1, n_labels + 1):
        component = labels == lbl
        area = int(component.sum())
        if area < _MIN_AREA_PX:
            continue
        total_flux = float(norm[component].sum())
        score = total_flux * (area ** 0.5)
        if score > best_score:
            best_score = score
            best_label = lbl

    if best_label < 0:
        _log.debug("PlanetDetect: no qualifying component (all hot pixels?)")
        return None

    component = labels == best_label
    rows, cols = np.where(component)
    center_r = int(np.round(float(np.mean(rows))))
    center_c = int(np.round(float(np.mean(cols))))
    area = int(component.sum())
    radius_px = float((area / np.pi) ** 0.5)

    comp_pixels = norm[component]
    peak_frac = float(comp_pixels.max())
    saturation_pct = float(np.sum(comp_pixels >= 0.99) / area * 100.0)

    _log.info(
        "PlanetDetect: area=%d radius=%.1fpx peak=%.3f sat=%.1f%% center=(%d,%d)",
        area, radius_px, peak_frac, saturation_pct, center_r, center_c,
    )
    return DetectedObject(
        center_px=(center_r, center_c),
        radius_px=radius_px,
        peak_frac=peak_frac,
        saturation_pct=saturation_pct,
    )


def _label(mask: np.ndarray) -> tuple[np.ndarray, int]:
    """4-connectivity BFS connected-component labeling (pure numpy).

    Returns (labels_array, n_labels).  labels_array has the same shape as
    *mask*; component IDs start at 1; background pixels stay 0.
    """
    labels = np.zeros(mask.shape, dtype=np.int32)
    n_rows, n_cols = mask.shape
    flat_labels = labels.ravel()   # view into labels (C-contiguous → view guaranteed)
    flat_mask   = mask.ravel()
    n_pixels    = int(flat_mask.size)

    stack = np.empty(n_pixels, dtype=np.int32)
    current_label = 0

    for start_idx in np.where(flat_mask)[0]:
        start_idx = int(start_idx)
        if flat_labels[start_idx] != 0:
            continue
        current_label += 1
        sp = 1
        stack[0] = start_idx
        flat_labels[start_idx] = current_label
        while sp > 0:
            sp -= 1
            idx = int(stack[sp])
            r, c = divmod(idx, n_cols)
            for nr, nc in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)):
                if 0 <= nr < n_rows and 0 <= nc < n_cols:
                    nidx = nr * n_cols + nc
                    if flat_mask[nidx] and flat_labels[nidx] == 0:
                        flat_labels[nidx] = current_label
                        stack[sp] = nidx
                        sp += 1

    return labels, current_label
