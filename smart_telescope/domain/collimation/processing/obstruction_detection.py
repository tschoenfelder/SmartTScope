"""Screw identification by hand-obstruction shadow — Collimation Phase 8, COL-080.

When the user touches a collimation screw, their finger partially blocks the
incoming light beam and casts a shadow in the defocused star image.  This
module compares a reference frame (clean donut) to the current frame and
locates the shadow region.

Algorithm
---------
1. Compute pixel-wise difference:  diff = reference − current.
   Positive values indicate darkening (shadow).
2. Estimate background of the difference image via sigma-clipping.
3. Threshold to find the obstruction mask: diff > bg + k·σ.
4. Require minimum shadow area (configurable, default 20 px).
5. Compute brightness-weighted centroid of the shadow region.
6. Compute angle from the supplied reference center to the shadow centroid.
7. Return ObstructionResult with angle, area, and confidence.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass

import numpy as np

from .frame import ProcessedFrame
from .stretch import estimate_background

_log = logging.getLogger(__name__)

_SHADOW_SIGMA     = 5.0   # threshold multiplier above diff background
_MIN_SHADOW_PX    = 20    # minimum shadow area to accept
_SNR_FULL_CONF    = 20.0  # diff SNR at which confidence saturates to 1.0


@dataclass(frozen=True)
class ObstructionResult:
    """Shadow detected by comparing reference and current frames.

    shadow_center_x / _y : centroid of the shadow region (pixel col / row).
    angle_deg             : angle from reference_center to shadow centroid,
                            image convention (0° = +x right, 90° = +y down).
    shadow_area_px        : number of pixels in the obstruction mask.
    confidence            : 0–1; based on shadow SNR.
    """
    shadow_center_x: float
    shadow_center_y: float
    angle_deg: float
    shadow_area_px: int
    confidence: float


def detect_obstruction(
    reference: ProcessedFrame,
    current: ProcessedFrame,
    reference_center_x: float,
    reference_center_y: float,
    shadow_sigma: float = _SHADOW_SIGMA,
    min_shadow_px: int = _MIN_SHADOW_PX,
) -> ObstructionResult | None:
    """Detect the shadow cast by touching a collimation screw.

    Args:
        reference         : clean donut frame (captured before touching the screw).
        current           : frame captured while finger is near the screw.
        reference_center_x: x coordinate of the outer ring center (pixels).
        reference_center_y: y coordinate of the outer ring center (pixels).
        shadow_sigma      : threshold multiplier above diff background (default 5).
        min_shadow_px     : minimum shadow area in pixels (default 20).

    Returns:
        ObstructionResult when a clear shadow is found, None otherwise.
    """
    ref_data = reference.mono.astype(np.float64)
    cur_data = current.mono.astype(np.float64)
    diff     = ref_data - cur_data   # positive where current is darker

    bg_diff, sigma_diff = estimate_background(diff)
    threshold = bg_diff + shadow_sigma * max(sigma_diff, 1.0)

    shadow_mask = diff > threshold
    shadow_area = int(np.sum(shadow_mask))

    _log.debug(
        "detect_obstruction bg_diff=%.1f sigma_diff=%.1f threshold=%.1f area=%d",
        bg_diff, sigma_diff, threshold, shadow_area,
    )

    if shadow_area < min_shadow_px:
        return None

    # Brightness-weighted centroid of the shadow region (weight = diff amplitude)
    weights = np.where(shadow_mask, diff - bg_diff, 0.0)
    total   = float(weights.sum())
    if total <= 0.0:
        return None

    rows_g = np.arange(reference.height, dtype=np.float64)[:, np.newaxis]
    cols_g = np.arange(reference.width,  dtype=np.float64)[np.newaxis, :]
    cy = float((weights * rows_g).sum() / total)
    cx = float((weights * cols_g).sum() / total)

    # Angle from reference center to shadow centroid
    dx  = cx - reference_center_x
    dy  = cy - reference_center_y
    angle = math.degrees(math.atan2(dy, dx))

    # Confidence: shadow SNR relative to diff noise
    mean_shadow_diff = float(np.mean(diff[shadow_mask]))
    snr              = (mean_shadow_diff - bg_diff) / max(sigma_diff, 1.0)
    confidence       = min(1.0, snr / _SNR_FULL_CONF)

    return ObstructionResult(
        shadow_center_x=cx,
        shadow_center_y=cy,
        angle_deg=angle,
        shadow_area_px=shadow_area,
        confidence=confidence,
    )
