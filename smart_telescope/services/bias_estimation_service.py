"""Capture bias frames and estimate the minimum safe sensor offset."""
from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from ..domain.bias_estimation import (
    BiasEstimationResult,
    BiasFrameStats,
    OffsetSweepPoint,
    analyze_frame,
    DEFAULT_SWEEP_OFFSETS,
)
from ..domain.camera_capabilities import ConversionGain

if TYPE_CHECKING:
    from ..ports.camera import CameraPort

_log = logging.getLogger(__name__)


class BiasEstimationService:
    """Capture bias frames and sweep offset values to find the minimum safe offset."""

    def __init__(self, camera: "CameraPort") -> None:
        self._camera = camera

    def estimate(
        self,
        gain_mode: ConversionGain,
        frame_count: int = 10,
        sweep_offsets: list[int] | None = None,
        cancel_event: threading.Event | None = None,
    ) -> BiasEstimationResult:
        """Capture bias frames and estimate minimum safe offset.

        Args:
            gain_mode: Conversion gain mode to test (LCG/HCG/HDR).
            frame_count: Number of frames to capture per offset value.
            sweep_offsets: Offset values to test. None = DEFAULT_SWEEP_OFFSETS.
            cancel_event: When set, estimation stops and returns partial results.

        Returns:
            BiasEstimationResult with per-offset stats and recommended_offset.
        """
        if sweep_offsets is None:
            sweep_offsets = DEFAULT_SWEEP_OFFSETS

        caps = self._camera.get_capabilities()
        exp_s = caps.min_exposure_ms / 1000.0

        original_offset = self._camera.get_black_level()
        original_gain = self._camera.get_conversion_gain()
        self._camera.set_conversion_gain(gain_mode)
        model = self._camera.get_logical_name()

        sweep_points: list[OffsetSweepPoint] = []
        base_stats: BiasFrameStats | None = None

        try:
            for offset in sweep_offsets:
                if cancel_event and cancel_event.is_set():
                    _log.info("BiasEstimation: cancelled at offset=%d", offset)
                    break

                self._camera.set_black_level(offset)
                frame_stats = self._capture_and_analyze(frame_count, exp_s, cancel_event)
                if frame_stats is None:
                    break  # cancelled
                if not frame_stats:
                    continue  # frame_count=0, skip this offset

                avg = self._avg_stats(frame_stats)
                pt = OffsetSweepPoint(
                    offset=offset,
                    zero_fraction=avg.zero_fraction,
                    min_val=avg.min_val,
                )
                sweep_points.append(pt)
                if base_stats is None:
                    base_stats = avg

                _log.info(
                    "BiasEstimation: offset=%d zero_fraction=%.4f min=%.1f safe=%s",
                    offset, pt.zero_fraction, pt.min_val, pt.is_safe,
                )
        finally:
            self._camera.set_black_level(original_offset)
            self._camera.set_conversion_gain(original_gain)

        return BiasEstimationResult(
            camera_model=model,
            gain_mode_name=gain_mode.name,
            frame_count=frame_count,
            mean_stats=base_stats,
            sweep=sweep_points,
        )

    def _capture_and_analyze(
        self,
        count: int,
        exp_s: float,
        cancel_event: threading.Event | None,
    ) -> list[BiasFrameStats] | None:
        """Return list of stats, or None if cancelled before any frame was captured."""
        stats: list[BiasFrameStats] = []
        for i in range(count):
            if cancel_event and cancel_event.is_set():
                _log.info("BiasEstimation: cancelled during frame capture at frame %d", i)
                return None  # explicitly cancelled
            frame = self._camera.capture(exp_s)
            stats.append(analyze_frame(frame.pixels, frame_index=i))
        return stats

    @staticmethod
    def _avg_stats(stats: list[BiasFrameStats]) -> BiasFrameStats:
        if not stats:
            raise ValueError("_avg_stats called with empty list")
        n = len(stats)
        hist_len = len(stats[0].histogram) if stats[0].histogram else 256
        agg_hist = [
            sum(s.histogram[i] for s in stats if i < len(s.histogram))
            for i in range(hist_len)
        ]
        # Note: averaging per-frame medians is an approximation; the true combined
        # median requires all pixel data and is not computed here.
        return BiasFrameStats(
            frame_index=0,
            min_val=sum(s.min_val for s in stats) / n,
            max_val=max(s.max_val for s in stats),
            mean=sum(s.mean for s in stats) / n,
            median=sum(s.median for s in stats) / n,
            std=sum(s.std for s in stats) / n,
            zero_count=sum(s.zero_count for s in stats),
            zero_fraction=sum(s.zero_fraction for s in stats) / n,
            histogram=agg_hist,
        )
