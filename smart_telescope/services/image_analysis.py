"""Shared image-analysis module (M7-009 / DD-005).

Provides a unified interface for star detection and focus quality measurement
used by autofocus, collimation, and plate-solving services.

Focus quality contract:
- Strongly out-of-focus frames (no detectable stars, blank frames) return
  focus_quality = UNKNOWN rather than a misleading HFD/FWHM value.
- This prevents the autofocus V-curve from accepting invalid samples.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

import numpy as np

from ..domain.focus_metric import half_flux_diameter

_log = logging.getLogger(__name__)

# HFD above this → frame too out-of-focus for a reliable metric
_HFD_UNKNOWN_THRESHOLD = 200.0


class FocusQualityLevel(str, Enum):
    GOOD    = "GOOD"     # HFD within expected range; star well-focused
    POOR    = "POOR"     # HFD detectable but above quality threshold
    UNKNOWN = "UNKNOWN"  # no stars / blank frame / extreme defocus


@dataclass
class StarInfo:
    centroid_x: float
    centroid_y: float
    peak_value: float
    snr: float


@dataclass
class ImageAnalysisResult:
    """Unified output of one frame analysis pass."""

    # ── focus quality ─────────────────────────────────────────────────────────
    hfd_px: float | None           # Half-Flux Diameter in pixels (None = unknown)
    fwhm_px: float | None          # Estimated FWHM (≈ HFD × 0.85 for point sources)
    focus_quality: FocusQualityLevel

    # ── star census ──────────────────────────────────────────────────────────
    stars_found: int = 0           # number of stars above threshold
    brightest_star: StarInfo | None = None

    # ── diagnostics ──────────────────────────────────────────────────────────
    reason: str | None = None      # non-None when focus_quality == UNKNOWN


def analyze_frame(
    pixels: "np.ndarray[Any, np.dtype[Any]]",
    *,
    quality_threshold_hfd: float = 10.0,
) -> ImageAnalysisResult:
    """Analyze a single frame and return focus quality + star information.

    Args:
        pixels: 2-D float32 pixel array.
        quality_threshold_hfd: HFD at or below which focus quality is GOOD.

    Returns:
        ImageAnalysisResult with focus_quality = UNKNOWN for blank/no-signal frames.
    """
    flat = pixels.astype(np.float32)
    if flat.ndim == 3:
        flat = flat[:, :, 0]

    total = float(flat.sum())
    if total <= 0.0:
        return ImageAnalysisResult(
            hfd_px=None,
            fwhm_px=None,
            focus_quality=FocusQualityLevel.UNKNOWN,
            stars_found=0,
            reason="No signal in frame",
        )

    background = float(np.median(flat))
    if float(flat.max()) <= background:
        return ImageAnalysisResult(
            hfd_px=None,
            fwhm_px=None,
            focus_quality=FocusQualityLevel.UNKNOWN,
            stars_found=0,
            reason="No signal above background",
        )

    # Measure HFD
    try:
        hfd = half_flux_diameter(flat)
    except Exception as exc:
        _log.debug("image_analysis: HFD failed: %s", exc)
        return ImageAnalysisResult(
            hfd_px=None,
            fwhm_px=None,
            focus_quality=FocusQualityLevel.UNKNOWN,
            reason=f"HFD measurement failed: {exc}",
        )

    if hfd >= _HFD_UNKNOWN_THRESHOLD:
        return ImageAnalysisResult(
            hfd_px=hfd,
            fwhm_px=None,
            focus_quality=FocusQualityLevel.UNKNOWN,
            reason="Frame too out-of-focus for reliable metric",
        )

    fwhm = hfd * 0.85  # empirical approximation for point sources

    # Detect brightest star via centroid
    peak_idx = int(np.argmax(flat))
    h, w = flat.shape
    peak_y, peak_x = divmod(peak_idx, w)
    peak_val = float(flat[peak_y, peak_x])
    bg = float(np.median(flat))
    signal = peak_val - bg
    noise = float(np.std(flat)) + 1e-6
    snr = signal / noise

    brightest = StarInfo(
        centroid_x=float(peak_x),
        centroid_y=float(peak_y),
        peak_value=peak_val,
        snr=snr,
    )

    # Count rough star estimate: pixels > 5-sigma above background
    sigma = noise
    threshold = bg + 5.0 * sigma
    stars_found = int((flat > threshold).sum() > 0)

    quality = (
        FocusQualityLevel.GOOD if hfd <= quality_threshold_hfd
        else FocusQualityLevel.POOR
    )

    return ImageAnalysisResult(
        hfd_px=hfd,
        fwhm_px=fwhm,
        focus_quality=quality,
        stars_found=stars_found,
        brightest_star=brightest,
    )
