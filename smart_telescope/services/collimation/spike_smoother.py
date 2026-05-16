"""Tri-Bahtinov spike measurement smoother — Collimation Phase 10, COL-102.

Accumulates SpikeMeasurement frames in a sliding window, rejects frames
below a confidence threshold, and produces a stable focus-error estimate
with jitter reporting and a seeing-limited flag.

Smoothing strategy
------------------
- Current value : median of accepted frames in the window (robust to outliers).
- Trend         : moving average of the most-recent half of the window.
- Jitter        : population std-dev of focus_error_px across the window.
- Seeing-limited: jitter > seeing_limited_threshold_px.
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from ...domain.collimation.models import SpikeMeasurement


@dataclass(frozen=True)
class SmoothedSpikeResult:
    """Smoothed outcome of the sliding-window spike analysis.

    focus_error_px  : median of focus errors in the window (primary metric).
    focus_trend_px  : moving average of the most-recent half (trend direction).
    jitter_px       : population std-dev of focus errors in the window.
    seeing_limited  : True when jitter exceeds the seeing threshold.
    frame_count     : number of accepted frames in the current window.
    confidence      : mean confidence of accepted frames.
    """
    focus_error_px: float
    focus_trend_px: float
    jitter_px: float
    seeing_limited: bool
    frame_count: int
    confidence: float


class SpikeSmoother:
    """Sliding-window smoother for Tri-Bahtinov spike measurements.

    Args:
        window                     : maximum frames kept (default 7).
        min_confidence             : frames below this confidence are rejected.
        seeing_limited_threshold_px: jitter above this → seeing_limited flag.
    """

    def __init__(
        self,
        window: int = 7,
        min_confidence: float = 0.3,
        seeing_limited_threshold_px: float = 3.0,
    ) -> None:
        self._window    = window
        self._min_conf  = min_confidence
        self._seeing_px = seeing_limited_threshold_px
        self._frames: deque[SpikeMeasurement] = deque(maxlen=window)

    # ── public ────────────────────────────────────────────────────────────────

    def add(self, measurement: SpikeMeasurement) -> None:
        """Add a frame to the window; silently drops low-confidence frames."""
        if measurement.confidence >= self._min_conf:
            self._frames.append(measurement)

    def compute(self) -> SmoothedSpikeResult | None:
        """Compute statistics over the current window.

        Returns None when the window is empty (all frames rejected or none added).
        """
        if not self._frames:
            return None

        errors = [f.focus_error_px for f in self._frames]
        n = len(errors)

        # Median (current value)
        sorted_errors = sorted(errors)
        mid = n // 2
        median = (
            sorted_errors[mid]
            if n % 2 == 1
            else (sorted_errors[mid - 1] + sorted_errors[mid]) / 2.0
        )

        # Trend: moving average of most-recent half of accepted frames
        half = max(1, n // 2)
        trend = sum(errors[-half:]) / half

        # Jitter: population std-dev
        mean = sum(errors) / n
        jitter = math.sqrt(sum((e - mean) ** 2 for e in errors) / n)

        avg_conf = sum(f.confidence for f in self._frames) / n

        return SmoothedSpikeResult(
            focus_error_px=median,
            focus_trend_px=trend,
            jitter_px=jitter,
            seeing_limited=jitter > self._seeing_px,
            frame_count=n,
            confidence=avg_conf,
        )

    def reset(self) -> None:
        """Clear the window."""
        self._frames.clear()

    @property
    def window_size(self) -> int:
        return self._window

    @property
    def frame_count(self) -> int:
        return len(self._frames)
