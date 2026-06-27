"""Click-to-center refinement algorithms — M8-026 / REQ-CLICK-002.

Modes:
  star_centroid — intensity-weighted centroid of the brightest peak near the click
  ring_center   — intensity-weighted centroid of the bright ring (donut center)

Both use robust background estimation (25th-percentile level, noise from
background-only pixels) so synthetic test frames with zero-noise backgrounds
behave identically to real frames.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass

import numpy as np

_log = logging.getLogger(__name__)

_SEARCH_RADIUS = 40   # px around click to search for a feature
_MIN_PEAK_SNR = 3.0   # peak must be at least 3× background stddev above background level


@dataclass
class RefinedClick:
    raw_x: int
    raw_y: int
    refined_x: int
    refined_y: int
    method: str          # "star_centroid" | "ring_center" | "raw_fallback"
    confidence: float    # 0.0–1.0
    fallback: bool       # True when refined == raw (no feature found)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json_line(self) -> str:
        return json.dumps({"event": "CLICK_REFINED", **self.to_dict()})


def _crop_window(pixels: np.ndarray, cx: int, cy: int, radius: int) -> tuple[np.ndarray, int, int]:
    """Return pixels[y0:y1, x0:x1] and the (x0, y0) offsets."""
    h, w = pixels.shape[:2]
    x0 = max(0, cx - radius)
    y0 = max(0, cy - radius)
    x1 = min(w, cx + radius + 1)
    y1 = min(h, cy + radius + 1)
    return pixels[y0:y1, x0:x1], x0, y0


def _bg_stats(window: np.ndarray) -> tuple[float, float]:
    """Return (background_level, background_noise) using robust estimators.

    Using the 25th-percentile for level and standard deviation of sub-median
    pixels for noise keeps bright objects from inflating the estimates.
    Minimum noise of 1.0 prevents division-by-zero on perfectly flat frames.
    """
    flat = window.ravel().astype(np.float64)
    bg_level = float(np.percentile(flat, 25))
    below_median = flat[flat <= float(np.median(flat))]
    bg_noise = max(1.0, float(np.std(below_median)))
    return bg_level, bg_noise


def _intensity_centroid(window: np.ndarray, x0: int, y0: int) -> tuple[float, float] | None:
    """Compute intensity-weighted centroid; return (x, y) in full-frame coords."""
    total = float(window.sum())
    if total < 1e-6:
        return None
    rows, cols = np.mgrid[0:window.shape[0], 0:window.shape[1]]
    cx = float((cols * window).sum()) / total + x0
    cy = float((rows * window).sum()) / total + y0
    return cx, cy


def _bright_centroid(
    pixels: np.ndarray,
    click_x: int,
    click_y: int,
    search_radius: int,
    threshold_fraction: float,
) -> tuple[int, int, float] | None:
    """Find centroid of bright region near (click_x, click_y).

    threshold_fraction: what fraction of (peak-bg) to use as cut-off.
    0.5 = half-peak (tight, star-like); 0.2 = lower (captures ring breadth).
    """
    window, x0, y0 = _crop_window(pixels, click_x, click_y, search_radius)
    if window.size == 0:
        return None

    px = window.astype(np.float32)
    bg_level, bg_noise = _bg_stats(px)
    peak_val = float(px.max())
    snr = (peak_val - bg_level) / bg_noise

    if snr < _MIN_PEAK_SNR:
        return None

    thresh = bg_level + threshold_fraction * (peak_val - bg_level)
    mask = np.where(px > thresh, px - thresh, 0.0)

    result = _intensity_centroid(mask, x0, y0)
    if result is None:
        return None

    confidence = min(1.0, snr / 10.0)
    return round(result[0]), round(result[1]), confidence


def refine_click(
    pixels: np.ndarray,
    click_x: int,
    click_y: int,
    mode: str = "star_centroid",
    search_radius: int = _SEARCH_RADIUS,
) -> RefinedClick:
    """Refine a click coordinate using the chosen algorithm.

    mode: "star_centroid" | "ring_center"
    Falls back to raw click if no feature is found.
    """
    if mode == "star_centroid":
        # Tight threshold captures only the star core → precise centroid
        result = _bright_centroid(pixels, click_x, click_y, search_radius, threshold_fraction=0.5)
        method_label = "star_centroid"
    elif mode == "ring_center":
        # Lower threshold captures the full ring width → centroid = ring centre
        result = _bright_centroid(pixels, click_x, click_y, search_radius, threshold_fraction=0.2)
        method_label = "ring_center"
    else:
        result = None
        method_label = "unknown"

    if result is None:
        return RefinedClick(
            raw_x=click_x, raw_y=click_y,
            refined_x=click_x, refined_y=click_y,
            method="raw_fallback",
            confidence=0.0,
            fallback=True,
        )

    rx, ry, conf = result
    return RefinedClick(
        raw_x=click_x, raw_y=click_y,
        refined_x=rx, refined_y=ry,
        method=method_label,
        confidence=conf,
        fallback=False,
    )
