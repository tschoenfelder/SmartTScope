"""Stateful autofocus service — frame-by-frame analyzer (M7-007 / AF-001..AF-005).

This service does NOT control hardware directly (AF-001). The caller:
  1. Captures a frame and passes it to analyze().
  2. Reads focus_movement_steps from the result and moves the focuser.
  3. Repeats until autofocus_finished is True.

AF-005: Mount movement recommendations are returned as pixel offsets only.
  The caller converts to RA/DEC via PixelCalibrationService.

AF-003: HFD (Half-Flux Diameter) is used as the focus quality metric.
  Strongly out-of-focus frames return focus_quality = UNKNOWN.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any

import numpy as np

from ..domain.focus_metric import half_flux_diameter

_log = logging.getLogger(__name__)

# HFD above this threshold → frame too out-of-focus for reliable metric
_HFD_UNKNOWN_THRESHOLD = 200.0

# Minimum HFD improvement (pixels) required to declare autofocus finished
_FINISH_IMPROVEMENT_PX = 2.0

# Minimum number of samples before deciding we're done
_MIN_SAMPLES = 3


class FocusQuality(str, Enum):
    GOOD    = "GOOD"     # HFD within expected range for focused star
    POOR    = "POOR"     # detectable but not good
    UNKNOWN = "UNKNOWN"  # frame too out-of-focus or no signal


@dataclass
class AutofocusDiagnostics:
    number_of_stars_detected: int = 0
    median_fwhm_px: float | None = None
    median_hfr_px: float | None = None
    best_focus_position_if_known: int | None = None
    current_focus_position_if_known: int | None = None
    reason: str | None = None


@dataclass
class AutofocusRecommendation:
    """AF-002 output from one analyze() call."""
    focus_movement_steps: int        # signed; 0 = stay
    target_offset_x_px: float        # AF-005: mount correction x (pixels)
    target_offset_y_px: float        # AF-005: mount correction y (pixels)
    focus_quality: FocusQuality
    autofocus_finished: bool
    diagnostics: AutofocusDiagnostics


class AutofocusService:
    """Frame-by-frame autofocus analyzer.

    Thread-safe. Call reset() to start a new run.
    """

    def __init__(
        self,
        step_size: int = 20,
        quality_threshold_hfd: float = 5.0,
        max_samples: int = 20,
    ) -> None:
        self._step_size = step_size
        self._quality_threshold_hfd = quality_threshold_hfd
        self._max_samples = max_samples
        self._lock = threading.Lock()
        self._samples: list[tuple[int, float]] = []  # (position, hfd)
        self._direction: int = 1   # +1 = increasing position, -1 = decreasing

    def reset(self) -> None:
        """Start a new autofocus run, clearing all sample history."""
        with self._lock:
            self._samples.clear()
            self._direction = 1
        _log.info("AutofocusService: reset")

    def analyze(
        self,
        pixels: "np.ndarray[Any, np.dtype[Any]]",
        current_position: int,
    ) -> AutofocusRecommendation:
        """Analyze one frame and return a movement recommendation.

        Args:
            pixels:           2-D float32 pixel array from the camera.
            current_position: current focuser position (steps).
        """
        hfd = self._measure_hfd(pixels)
        quality = self._classify_quality(hfd)

        with self._lock:
            if quality != FocusQuality.UNKNOWN:
                self._samples.append((current_position, hfd))

            samples = list(self._samples)
            direction = self._direction

        diag = AutofocusDiagnostics(
            median_hfr_px=hfd / 2.0 if quality != FocusQuality.UNKNOWN else None,
            median_fwhm_px=hfd * 0.85 if quality != FocusQuality.UNKNOWN else None,
            current_focus_position_if_known=current_position,
            reason=(
                "Frame too out-of-focus for reliable metric" if quality == FocusQuality.UNKNOWN
                else None
            ),
        )

        if len(samples) < _MIN_SAMPLES:
            # Not enough samples yet — keep stepping in current direction
            move = self._step_size * direction
            return AutofocusRecommendation(
                focus_movement_steps=move,
                target_offset_x_px=0.0,
                target_offset_y_px=0.0,
                focus_quality=quality,
                autofocus_finished=False,
                diagnostics=diag,
            )

        best_idx = min(range(len(samples)), key=lambda i: samples[i][1])
        best_pos, best_hfd = samples[best_idx]
        diag.best_focus_position_if_known = best_pos

        # V-curve complete when HFD rises on BOTH sides of the best sample
        has_left_rise = (
            best_idx > 0
            and samples[0][1] > best_hfd + _FINISH_IMPROVEMENT_PX
        )
        has_right_rise = (
            best_idx < len(samples) - 1
            and samples[-1][1] > best_hfd + _FINISH_IMPROVEMENT_PX
        )

        if has_left_rise and has_right_rise:
            # V-curve fully sampled — return exact delta to best position
            move = best_pos - current_position
            fin_quality = FocusQuality.GOOD if best_hfd <= self._quality_threshold_hfd else quality
            _log.info(
                "AutofocusService: V-curve complete — best_pos=%d best_hfd=%.1f move=%d",
                best_pos, best_hfd, move,
            )
            return AutofocusRecommendation(
                focus_movement_steps=move,
                target_offset_x_px=0.0,
                target_offset_y_px=0.0,
                focus_quality=fin_quality,
                autofocus_finished=True,
                diagnostics=diag,
            )

        if len(samples) >= self._max_samples:
            # Safety cap: stop regardless of outcome
            _log.warning("AutofocusService: max_samples=%d reached", self._max_samples)
            return AutofocusRecommendation(
                focus_movement_steps=0,
                target_offset_x_px=0.0,
                target_offset_y_px=0.0,
                focus_quality=quality,
                autofocus_finished=True,
                diagnostics=diag,
            )

        # Still improving — continue in current direction
        move = self._step_size * direction
        return AutofocusRecommendation(
            focus_movement_steps=move,
            target_offset_x_px=0.0,
            target_offset_y_px=0.0,
            focus_quality=quality,
            autofocus_finished=False,
            diagnostics=diag,
        )

    # ── internals ─────────────────────────────────────────────────────────────

    def _measure_hfd(self, pixels: "np.ndarray[Any, np.dtype[Any]]") -> float:
        flat = pixels.astype(np.float32)
        if float(flat.sum()) <= 0.0:
            # No signal → frame too dark to measure
            return _HFD_UNKNOWN_THRESHOLD + 1.0
        try:
            return half_flux_diameter(flat)
        except Exception:
            return _HFD_UNKNOWN_THRESHOLD + 1.0

    def _classify_quality(self, hfd: float) -> FocusQuality:
        if hfd >= _HFD_UNKNOWN_THRESHOLD:
            return FocusQuality.UNKNOWN
        if hfd <= self._quality_threshold_hfd:
            return FocusQuality.GOOD
        return FocusQuality.POOR
