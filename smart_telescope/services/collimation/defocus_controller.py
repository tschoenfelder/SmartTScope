"""Controlled defocus for rough collimation — Collimation Phase 6, Task 6.2.

Moves the focuser in the configured defocus direction until the defocused star
ring (donut) reaches the target size range: 25–50 % of the shorter frame
dimension.

Ring size is estimated by counting pixels above a low threshold (bg + 2σ)
and computing the effective radius as sqrt(N / π).  This works because the
donut area ≈ π × r²  and does not require Phase 7 circle fitting.

Clipping is detected by checking whether the above-threshold blob approaches
any frame edge within a configurable margin.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

import numpy as np

from ...domain.collimation.config import FocuserCollimationConfig, RoughCollimationConfig
from ...domain.collimation.processing.frame import normalize_frame
from ...domain.collimation.processing.stretch import estimate_background
from ...domain.frame import FitsFrame
from .focuser_control import CollimationFocuserControl

_log = logging.getLogger(__name__)

_SIGNAL_THRESHOLD_SIGMA = 6.0  # σ above background — any real star/donut exceeds this
_CLIP_MARGIN_PX         = 10.0  # px from edge before clipping is declared


@dataclass(frozen=True)
class DefocusResult:
    """Outcome of a controlled defocus run.

    success             : True when the donut is within the target size range.
    reason              : "at_target" | "clipped" | "star_lost" |
                          "max_steps" | "cancelled".
    estimated_radius_px : measured ring effective radius (px), or None.
    target_min_px       : lower bound of the target radius range.
    target_max_px       : upper bound of the target radius range.
    net_steps           : net signed focuser steps from start to final position.
    """
    success: bool
    reason: str
    estimated_radius_px: float | None
    target_min_px: float
    target_max_px: float
    net_steps: int


class DefocusController:
    """Defocus the star to the donut regime for rough SCT collimation analysis.

    Args:
        focuser       : CollimationFocuserControl (wraps the real focuser).
        focuser_cfg   : step sizes and defocus direction.
        rough_cfg     : target donut size ratios (25–50 % of shorter frame dim).
        bit_depth     : camera bit depth (for normalize_frame).
        max_steps     : maximum defocus steps before giving up (default 40).
        settle_seconds: wait between move and capture (default 0.5 s).
    """

    def __init__(
        self,
        focuser: CollimationFocuserControl,
        focuser_cfg: FocuserCollimationConfig,
        rough_cfg: RoughCollimationConfig,
        bit_depth: int = 16,
        max_steps: int = 40,
        settle_seconds: float = 0.5,
    ) -> None:
        self._focuser    = focuser
        self._fcfg       = focuser_cfg
        self._rcfg       = rough_cfg
        self._bit_depth  = bit_depth
        self._max_steps  = max_steps
        self._settle_s   = settle_seconds

    # ── Public API ────────────────────────────────────────────────────────────

    def defocus(
        self,
        capture_frame: Callable[[], FitsFrame],
        frame_width: int,
        frame_height: int,
        cancel_check: Callable[[], bool] | None = None,
    ) -> DefocusResult:
        """Move focuser in defocus_direction until the donut reaches target size.

        Args:
            capture_frame  : callable with no args that returns a FitsFrame.
            frame_width    : image width in pixels (for clipping / target calc).
            frame_height   : image height in pixels.
            cancel_check   : optional; returns True when operator cancelled.
        """
        min_dim = min(frame_width, frame_height)
        target_min_px = self._rcfg.target_donut_diameter_ratio_min * min_dim / 2.0
        target_max_px = self._rcfg.target_donut_diameter_ratio_max * min_dim / 2.0

        net_steps = 0

        for step_idx in range(self._max_steps):
            if cancel_check and cancel_check():
                radius = self._measure_radius(capture_frame(), frame_width, frame_height)
                return DefocusResult(
                    success=False, reason="cancelled",
                    estimated_radius_px=radius,
                    target_min_px=target_min_px, target_max_px=target_max_px,
                    net_steps=net_steps,
                )

            # Measure current state before moving (first iteration uses start pos)
            frame = capture_frame()
            processed = normalize_frame(frame, bit_depth=self._bit_depth)
            radius, clipped = self._measure_radius_and_clipping(
                processed, frame_width, frame_height
            )

            _log.debug(
                "DefocusController step=%d radius=%.1f target=[%.1f–%.1f] clipped=%s",
                step_idx, radius or -1, target_min_px, target_max_px, clipped,
            )

            if radius is None:
                return DefocusResult(
                    success=False, reason="star_lost",
                    estimated_radius_px=None,
                    target_min_px=target_min_px, target_max_px=target_max_px,
                    net_steps=net_steps,
                )

            if clipped:
                return DefocusResult(
                    success=False, reason="clipped",
                    estimated_radius_px=radius,
                    target_min_px=target_min_px, target_max_px=target_max_px,
                    net_steps=net_steps,
                )

            if target_min_px <= radius <= target_max_px:
                return DefocusResult(
                    success=True, reason="at_target",
                    estimated_radius_px=radius,
                    target_min_px=target_min_px, target_max_px=target_max_px,
                    net_steps=net_steps,
                )

            # Not yet at target — move one coarse step in defocus direction
            result = self._focuser.defocus()
            actual = result.steps_taken
            if actual == 0:
                # Soft limit hit
                radius2, _ = self._measure_radius_and_clipping(
                    normalize_frame(capture_frame(), bit_depth=self._bit_depth),
                    frame_width, frame_height,
                )
                return DefocusResult(
                    success=False, reason="max_steps",
                    estimated_radius_px=radius2 or radius,
                    target_min_px=target_min_px, target_max_px=target_max_px,
                    net_steps=net_steps,
                )
            net_steps += actual

            if self._settle_s > 0:
                time.sleep(self._settle_s)

        # Exhausted max_steps
        frame = capture_frame()
        radius, _ = self._measure_radius_and_clipping(
            normalize_frame(frame, bit_depth=self._bit_depth),
            frame_width, frame_height,
        )
        return DefocusResult(
            success=False, reason="max_steps",
            estimated_radius_px=radius,
            target_min_px=target_min_px, target_max_px=target_max_px,
            net_steps=net_steps,
        )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _measure_radius(
        self,
        frame: FitsFrame,
        frame_width: int,
        frame_height: int,
    ) -> float | None:
        processed = normalize_frame(frame, bit_depth=self._bit_depth)
        radius, _ = self._measure_radius_and_clipping(processed, frame_width, frame_height)
        return radius

    def _measure_radius_and_clipping(
        self,
        processed,
        frame_width: int,
        frame_height: int,
    ) -> tuple[float | None, bool]:
        """Return (rms_radius_px, is_clipped).

        rms_radius_px is the brightness-weighted RMS radius from the centroid:
          sqrt(Σ(above_bg × r²) / Σ(above_bg))
        This equals sigma_gauss for an in-focus star and approximately the ring
        radius for a donut, without requiring a blob-count threshold.

        Clipping uses pixels above 10 % of the peak value — well above noise,
        so scattered noise pixels near the frame edge do not trigger false clips.

        Returns (None, False) when no real star/donut is present.
        """
        data = processed.mono
        bg, sigma = estimate_background(data)

        # Reject frames with no real signal
        peak_val = float(np.max(data))
        if peak_val < bg + _SIGNAL_THRESHOLD_SIGMA * sigma:
            return None, False

        # Only count pixels clearly above background — avoids noise inflating RMS
        signal_mask = data > (bg + _SIGNAL_THRESHOLD_SIGMA * sigma)
        weights = np.where(signal_mask, data.astype(np.float64) - bg, 0.0)
        total = float(weights.sum())
        if total < 1.0:
            return None, False

        # Brightness-weighted centroid
        rows_g = np.arange(processed.height, dtype=np.float64)[:, np.newaxis]
        cols_g = np.arange(processed.width,  dtype=np.float64)[np.newaxis, :]
        cy = float((weights * rows_g).sum() / total)
        cx = float((weights * cols_g).sum() / total)

        # Brightness-weighted RMS radius (second moment)
        dist_sq = (rows_g - cy) ** 2 + (cols_g - cx) ** 2
        rms_radius = float(np.sqrt((weights * dist_sq).sum() / total))
        if rms_radius < 0.5:
            return None, False

        # Clipping check: use pixels above 10 % of peak (eliminates noise false-positives)
        clip_threshold = bg + (peak_val - bg) * 0.10
        clip_mask = data > clip_threshold
        clip_rows, clip_cols = np.where(clip_mask)
        if len(clip_rows) > 0:
            clipped = bool(
                clip_rows.min() < _CLIP_MARGIN_PX
                or clip_rows.max() > frame_height - _CLIP_MARGIN_PX
                or clip_cols.min() < _CLIP_MARGIN_PX
                or clip_cols.max() > frame_width  - _CLIP_MARGIN_PX
            )
        else:
            clipped = False

        return rms_radius, clipped
