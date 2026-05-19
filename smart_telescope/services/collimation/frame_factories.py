"""Synthetic frame factories for collimation replay and testing — COL-130.

All functions return float32 NumPy arrays with pixel values in raw ADU units
(same range as a real camera frame before normalize_frame).  Pass the result
as ``FitsFrame.pixels`` to feed into the standard processing pipeline.

Typical bit_depth is 16 (values 0 – 65535).
"""
from __future__ import annotations

import math

import numpy as np


def gaussian_star(
    height: int,
    width: int,
    cx: float,
    cy: float,
    fwhm_px: float,
    peak_adu: float = 40_000.0,
    bg_adu: float = 1_000.0,
) -> np.ndarray:
    """Generate a synthetic Gaussian PSF star image.

    Args:
        height, width : frame dimensions (pixels).
        cx, cy        : star centre position (pixels, origin = top-left).
        fwhm_px       : full-width at half-maximum of the PSF (pixels).
        peak_adu      : peak ADU above background.
        bg_adu        : uniform background level (ADU).

    Returns:
        float32 ndarray shaped (height, width) with values ≥ 0.
    """
    sigma = fwhm_px / (2.0 * math.sqrt(2.0 * math.log(2.0)))
    y, x = np.mgrid[0:height, 0:width].astype(np.float32)
    psf = np.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (2.0 * sigma ** 2))
    return (bg_adu + peak_adu * psf).astype(np.float32)


def donut_ring(
    height: int,
    width: int,
    outer_cx: float,
    outer_cy: float,
    outer_r: float,
    inner_r: float,
    error_x: float = 0.0,
    error_y: float = 0.0,
    peak_adu: float = 30_000.0,
    bg_adu: float = 1_000.0,
    ring_width_px: float = 8.0,
) -> np.ndarray:
    """Generate a synthetic defocused-star (donut) ring image.

    The outer bright ring is centred at (outer_cx, outer_cy) with radius
    outer_r.  The inner dark hole is centred at (outer_cx + error_x,
    outer_cy + error_y) with radius inner_r, which models the secondary
    mirror shadow displacement due to collimation error.

    Args:
        height, width   : frame dimensions (pixels).
        outer_cx, outer_cy: centre of the outer ring.
        outer_r         : radius of the outer ring (pixels).
        inner_r         : radius of the inner dark hole (pixels).
        error_x, error_y: offset of the inner hole from outer centre (px).
        peak_adu        : peak ADU of the ring above background.
        bg_adu          : uniform background level (ADU).
        ring_width_px   : Gaussian sigma used to soften the ring edge.

    Returns:
        float32 ndarray shaped (height, width) with values ≥ 0.
    """
    inner_cx = outer_cx + error_x
    inner_cy = outer_cy + error_y

    y, x = np.mgrid[0:height, 0:width].astype(np.float32)

    r_outer = np.sqrt((x - outer_cx) ** 2 + (y - outer_cy) ** 2)
    r_inner = np.sqrt((x - inner_cx) ** 2 + (y - inner_cy) ** 2)

    # Bright ring: Gaussian centred on outer_r
    ring = np.exp(-((r_outer - outer_r) ** 2) / (2.0 * (ring_width_px / 2.0) ** 2))

    # Dark inner hole: suppression inside inner_r (sigmoid-smoothed boundary)
    hole_suppression = 1.0 / (
        1.0 + np.exp(-(r_inner - inner_r) / max(ring_width_px / 4.0, 1.0))
    )

    frame = bg_adu + peak_adu * ring * hole_suppression
    return frame.astype(np.float32)


def focus_sequence(
    height: int,
    width: int,
    cx: float,
    cy: float,
    fwhm_values: list[float],
    peak_adu: float = 40_000.0,
    bg_adu: float = 1_000.0,
) -> list[np.ndarray]:
    """Build a sequence of gaussian star frames with different FWHM values.

    Useful for simulating a focus run: supply a list of FWHM values (in px)
    that decreases to a minimum then increases again, and the replay camera
    will return them in order.

    Returns a list of float32 ndarrays, one per FWHM value.
    """
    return [
        gaussian_star(height, width, cx, cy, fwhm, peak_adu=peak_adu, bg_adu=bg_adu)
        for fwhm in fwhm_values
    ]
