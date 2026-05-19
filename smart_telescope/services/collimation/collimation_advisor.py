"""Rough collimation screw recommendations — Collimation Phase 9, COL-090.

Given a DonutMeasurement (error vector) and the learned per-screw response
vectors (ScrewCalibration), this module picks the screw and turn direction
that best opposes the measured error.

Algorithm
---------
For each calibrated screw T_k with response vector r_k (px per CW turn):
  - Desired correction = –error_vector  (we want to push the inner hole back)
  - dot_cw = correction · r_k  (positive → CW turn helps)
  - contribution = |dot_cw|    (how much this screw corrects)
  - alignment    = contribution / (|correction| × |r_k|)  (cosine similarity)

Best screw = argmax(contribution).
Turn CW when dot_cw > 0, CCW otherwise.

Adjustment size (never LARGE):
  - error_mag / outer_radius > 0.15  → MEDIUM
  - else                              → SMALL

Confidence = alignment × screw_calibration.confidence
"""
from __future__ import annotations

import math
import logging
from dataclasses import dataclass

from ...domain.collimation.models import (
    AdjustmentSize,
    CollimationRecommendation,
    DonutMeasurement,
    ScrewCalibration,
    TurnDirection,
)

_log = logging.getLogger(__name__)

_COLLIMATED_FRACTION  = 0.02   # error/outer_r below this → already collimated
_MEDIUM_FRACTION      = 0.15   # error/outer_r above this → MEDIUM turn
_RECAL_CONFIDENCE     = 0.30   # screw confidence below this → ask recalibration
_MIN_RESPONSE_PX      = 0.5    # ignore screws with negligible response magnitude


class CollimationAdvisor:
    """Compute a screw-turn recommendation from error vector + response vectors.

    Args:
        calibrations       : list of ScrewCalibration (one per known screw).
        collimated_fraction: error/outer_radius below which no action is needed.
        recal_confidence   : if the best screw confidence is below this, the
                             recommendation's confidence is reduced and the
                             reason string asks for recalibration.
    """

    def __init__(
        self,
        calibrations: list[ScrewCalibration],
        collimated_fraction: float = _COLLIMATED_FRACTION,
        recal_confidence: float = _RECAL_CONFIDENCE,
    ) -> None:
        self._cals         = [c for c in calibrations if c.response_magnitude >= _MIN_RESPONSE_PX]
        self._collimated_f = collimated_fraction
        self._recal_conf   = recal_confidence

    def recommend(
        self,
        measurement: DonutMeasurement,
        outer_radius: float | None = None,
    ) -> CollimationRecommendation | None:
        """Return the best screw recommendation, or None when already collimated
        or no calibration is available.

        Args:
            measurement  : current DonutMeasurement.
            outer_radius : outer ring radius in px.  Defaults to
                           measurement.outer_ring.mean_radius when None.

        Returns:
            CollimationRecommendation, or None when collimated / uncalibrated.
        """
        if not self._cals:
            return None

        r_outer = outer_radius if outer_radius is not None else measurement.outer_ring.mean_radius
        r_outer = max(r_outer, 1.0)

        error_x   = measurement.error_x_px
        error_y   = measurement.error_y_px
        error_mag = measurement.error_magnitude_px

        if error_mag < self._collimated_f * r_outer:
            return None   # already collimated

        # Desired correction direction
        corr_x = -error_x
        corr_y = -error_y

        # Score each screw
        best_screw: ScrewCalibration | None = None
        best_dot  = 0.0
        best_align = 0.0

        for cal in self._cals:
            dot_cw = corr_x * cal.response_vector_x + corr_y * cal.response_vector_y
            contrib = abs(dot_cw)
            if contrib > abs(best_dot):
                best_dot   = dot_cw
                best_screw = cal
                denom      = error_mag * cal.response_magnitude
                best_align = contrib / denom if denom > 0 else 0.0

        if best_screw is None:
            return None

        turn_direction = (
            TurnDirection.CLOCKWISE if best_dot > 0 else TurnDirection.COUNTER_CLOCKWISE
        )

        # Adjustment size — capped at MEDIUM (never LARGE)
        ratio = error_mag / r_outer
        adjustment_size = AdjustmentSize.MEDIUM if ratio > _MEDIUM_FRACTION else AdjustmentSize.SMALL

        # Overall confidence: alignment × screw calibration confidence
        confidence = best_align * best_screw.confidence
        reason_parts = [
            f"error {error_mag:.1f} px ({ratio:.1%} of ring radius)",
            f"screw alignment {best_align:.0%}",
        ]
        if best_screw.confidence < self._recal_conf:
            confidence *= 0.5
            reason_parts.append("low calibration confidence — consider recalibrating")

        _log.debug(
            "CollimationAdvisor: best=%s dot=%.1f align=%.2f conf=%.2f",
            best_screw.screw_id, best_dot, best_align, confidence,
        )

        return CollimationRecommendation(
            screw_id=best_screw.screw_id,
            turn_direction=turn_direction,
            adjustment_size=adjustment_size,
            reason="; ".join(reason_parts),
            confidence=min(1.0, confidence),
        )
