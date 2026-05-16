"""Donut detection for rough SCT collimation — Collimation Phase 7, COL-070/071.

Detects the outer bright ring and inner dark shadow of a defocused C8 star
and returns a DonutMeasurement with the collimation error vector.

Algorithm
---------
1. Background estimation via iterative sigma-clipping.
2. Signal presence check: peak > bg + signal_sigma × σ.
3. Build ring mask: pixels above max(3σ, 10 % of peak-above-bg).
4. Brightness-weighted centroid of ring mask pixels.
5. Extract all edge pixels of the ring mask (4-connected boundary).
6. Split edges at the median distance from centroid:
   – outer edges (dist > median) → outer ring boundary
   – inner edges (dist ≤ median) → inner hole boundary
7. Fit circles to both edge sets (Kasa algebraic fit).
8. Clipping check on the fitted outer circle.
9. Error vector = inner_center − outer_center.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

from ....domain.collimation.models import DonutMeasurement
from .frame import ProcessedFrame
from .geometry_fits import detect_clipping, extract_edge_points, fit_circle
from .stretch import estimate_background

_log = logging.getLogger(__name__)

_SIGNAL_SIGMA = 5.0   # peak threshold for "any real signal present"
_MIN_RING_SIGMA = 3.0  # ring mask minimum above background (σ units)
_RING_FRACTION = 0.10  # ring mask: 10 % of peak-above-bg (or _MIN_RING_SIGMA·σ if larger)
_MIN_EDGES = 6         # minimum edge pixels per boundary to attempt a fit


@dataclass(frozen=True)
class DonutAnalysisResult:
    """Outcome of donut analysis on one frame.

    measurement : populated when reason == "ok"; None otherwise.
    reason      : "ok" | "no_signal" | "no_ring_shape" |
                  "inner_hole_unclear" | "clipped".
    """
    measurement: DonutMeasurement | None
    reason: str


class DonutAnalyzer:
    """Detect outer ring and inner shadow in a defocused star frame.

    Args:
        signal_sigma  : sigma multiplier for signal presence check (default 5.0).
        min_confidence: minimum circle-fit confidence accepted for outer ring
                        and inner hole fits (default 0.15).
    """

    def __init__(
        self,
        signal_sigma: float = _SIGNAL_SIGMA,
        min_confidence: float = 0.15,
    ) -> None:
        self._sig_sigma = signal_sigma
        self._min_conf  = min_confidence

    def analyze(self, processed: ProcessedFrame) -> DonutAnalysisResult:
        """Analyze a defocused star frame.

        Args:
            processed: output of normalize_frame() for a defocused star image.

        Returns:
            DonutAnalysisResult with measurement populated on success.
        """
        data = processed.mono
        bg, sigma = estimate_background(data)

        # 1. Signal presence
        peak_val = float(np.max(data))
        if peak_val < bg + self._sig_sigma * sigma:
            return DonutAnalysisResult(measurement=None, reason="no_signal")

        # 2. Ring mask: pixels above the ring threshold
        ring_thresh = bg + max(_MIN_RING_SIGMA * sigma, (peak_val - bg) * _RING_FRACTION)
        bright = data > ring_thresh
        if not np.any(bright):
            return DonutAnalysisResult(measurement=None, reason="no_signal")

        # 3. Brightness-weighted centroid of ring pixels
        bright_f = bright.astype(np.float64)
        total    = bright_f.sum()
        rows_g   = np.arange(processed.height, dtype=np.float64)[:, np.newaxis]
        cols_g   = np.arange(processed.width,  dtype=np.float64)[np.newaxis, :]
        cy = float((bright_f * rows_g).sum() / total)
        cx = float((bright_f * cols_g).sum() / total)

        # 4. RMS radius of bright pixels — always between inner and outer ring radius,
        #    so it cleanly separates inner from outer edge pixels regardless of how many
        #    edge pixels each boundary contributes.
        dist_sq_grid = (rows_g - cy) ** 2 + (cols_g - cx) ** 2
        rms_sq       = float((bright_f * dist_sq_grid).sum() / total)
        split_radius = float(np.sqrt(max(rms_sq, 1.0)))

        # 5. Edge pixels of the bright mask; split by distance from centroid
        all_edges = extract_edge_points(bright)    # shape (N, 2): (x, y) = (col, row)
        if len(all_edges) < _MIN_EDGES * 2:
            return DonutAnalysisResult(measurement=None, reason="no_ring_shape")

        edge_dist   = np.sqrt((all_edges[:, 0] - cx) ** 2 + (all_edges[:, 1] - cy) ** 2)
        outer_edges = all_edges[edge_dist >  split_radius]
        inner_edges = all_edges[edge_dist <= split_radius]

        if len(outer_edges) < _MIN_EDGES or len(inner_edges) < _MIN_EDGES:
            return DonutAnalysisResult(measurement=None, reason="no_ring_shape")

        # 6. Fit circles
        outer_fit = fit_circle(outer_edges)
        inner_fit = fit_circle(inner_edges)

        _log.debug(
            "DonutAnalyzer outer=(%.1f,%.1f) r=%.1f conf=%.2f  "
            "inner=(%.1f,%.1f) r=%.1f conf=%.2f",
            outer_fit.center_x, outer_fit.center_y,
            outer_fit.radius_x, outer_fit.confidence,
            inner_fit.center_x, inner_fit.center_y,
            inner_fit.radius_x, inner_fit.confidence,
        )

        if outer_fit.confidence < self._min_conf:
            return DonutAnalysisResult(measurement=None, reason="no_ring_shape")
        if inner_fit.confidence < self._min_conf:
            return DonutAnalysisResult(measurement=None, reason="inner_hole_unclear")

        # 7. Clipping check on the outer ring
        if detect_clipping(outer_fit, processed.width, processed.height):
            return DonutAnalysisResult(measurement=None, reason="clipped")

        # 8. Error vector: inner_center − outer_center
        error_x   = inner_fit.center_x - outer_fit.center_x
        error_y   = inner_fit.center_y - outer_fit.center_y
        error_mag = math.hypot(error_x, error_y)
        error_ang = math.degrees(math.atan2(error_y, error_x))

        confidence = (outer_fit.confidence + inner_fit.confidence) / 2.0

        measurement = DonutMeasurement(
            outer_ring=outer_fit,
            inner_hole=inner_fit,
            error_x_px=error_x,
            error_y_px=error_y,
            error_magnitude_px=error_mag,
            error_angle_deg=error_ang,
            confidence=confidence,
        )
        return DonutAnalysisResult(measurement=measurement, reason="ok")
