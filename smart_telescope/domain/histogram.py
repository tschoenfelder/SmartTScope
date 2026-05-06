"""Frame histogram statistics for Auto Gain and calibration validation (FR-AG-050, FR-AG-060).

Key design choices:
- All percentiles are computed on normalised [0.0, 1.0] values so results
  are independent of bit depth and float vs integer dtype.
- "effective_bit_depth" is inferred from the declared bit_depth parameter,
  not from the raw pixel dtype (which is always float32 in FitsFrame).
- Saturation is defined as pixels at or above 99.9 % of the ADC range, to
  allow for realistic camera non-linearity near full-well.
- Zero-clipped pixels are those at exactly 0.0 after normalisation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class HistogramStats:
    """Summary statistics derived from one camera frame."""
    p50: float          # median signal, normalised [0, 1]
    p95: float
    p99: float
    p99_5: float
    p99_9: float
    mean_frac: float    # mean signal, normalised [0, 1]
    saturation_pct: float   # fraction of pixels >= 99.9 % of adc_max
    zero_clipped_pct: float # fraction of pixels == 0 (after normalisation)
    black_level: float      # p0.5 estimate of the pedestal, normalised
    effective_bit_depth: int
    adc_max: float          # ADC full-scale value used for normalisation


def _adc_max(bit_depth: int) -> float:
    return float((1 << bit_depth) - 1)


def analyze(
    pixels: np.ndarray[Any, np.dtype[Any]],
    bit_depth: int = 16,
) -> HistogramStats:
    """Return histogram statistics for *pixels* normalised to *bit_depth*.

    *pixels* may be any numeric dtype (uint16, float32, etc.).  Values are
    normalised to [0, 1] using *bit_depth* before statistics are computed.
    """
    amax = _adc_max(bit_depth)
    flat = pixels.astype(np.float64, copy=False).ravel()
    normed = flat / amax

    p50, p95, p99, p99_5, p99_9 = np.percentile(normed, [50, 95, 99, 99.5, 99.9])
    black = float(np.percentile(normed, 0.5))
    mean_frac = float(np.mean(normed))

    saturation_pct = float(np.mean(normed >= 0.999) * 100.0)
    zero_clipped_pct = float(np.mean(normed == 0.0) * 100.0)

    return HistogramStats(
        p50=float(p50),
        p95=float(p95),
        p99=float(p99),
        p99_5=float(p99_5),
        p99_9=float(p99_9),
        mean_frac=mean_frac,
        saturation_pct=saturation_pct,
        zero_clipped_pct=zero_clipped_pct,
        black_level=black,
        effective_bit_depth=bit_depth,
        adc_max=amax,
    )


def histogram_bins(
    pixels: np.ndarray[Any, np.dtype[Any]],
    bit_depth: int = 16,
    n_bins: int = 512,
) -> tuple[list[int], list[float]]:
    """Return (counts, edges) for a linear histogram over the ADC range.

    counts: list of n_bins integers
    edges:  list of n_bins + 1 normalised [0, 1] bin boundaries
    """
    amax = _adc_max(bit_depth)
    flat = pixels.astype(np.float64, copy=False).ravel()
    normed = flat / amax
    counts, edges = np.histogram(normed, bins=n_bins, range=(0.0, 1.0))
    return counts.tolist(), edges.tolist()
