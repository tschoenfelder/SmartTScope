"""Fine collimation guidance from Tri-Bahtinov residuals — Phase 11, COL-112.

Given per-sector collimation residuals (from SpikeErrorDecomposition) and a
mapping from sector index to screw ID (from MaskSectorCalibration), this
module recommends which screw to turn and in which direction to reduce the
worst residual.

Turn direction convention
-------------------------
A positive residual (outer-spike intersection is on the "positive" side of
the sector line) is corrected by a CLOCKWISE turn.  A negative residual
requires a COUNTER_CLOCKWISE turn.  The physical relationship is captured
by the ScrewCalibration response vectors; this module uses a simplified
sign convention that is consistent with the residual sign from
decompose_spike_errors().

Recommendation is suppressed when:
  - All |residuals| < target_residual_px  (already within spec).
  - Jitter exceeds seeing_limited_threshold_px  (seeing-limited; unreliable).
  - confidence < confidence_threshold  (low-quality measurements).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ...domain.bahtinov import SpikeLine
from ...domain.collimation.models import (
    AdjustmentSize,
    CollimationRecommendation,
    MaskSectorCalibration,
    TurnDirection,
)
from ...domain.collimation.processing.spike_decomposition import SpikeErrorDecomposition
from .spike_smoother import SmoothedSpikeResult


@dataclass(frozen=True)
class _ScrewOrder:
    """Internal: sorted screw list derived from MaskSectorCalibration."""
    screws: tuple[str, str, str]  # index 0/1/2 = sector_0/120/240 order


def _calibration_to_screws(cal: MaskSectorCalibration) -> _ScrewOrder:
    return _ScrewOrder(screws=(cal.sector_0_deg, cal.sector_120_deg, cal.sector_240_deg))


def align_residuals_to_screws(
    decomposition: SpikeErrorDecomposition,
    lines: list[SpikeLine],
    calibration: MaskSectorCalibration,
) -> dict[str, float]:
    """Map per-sector residuals to their controlling screws.

    The three spike lines are sorted by ascending angle; the sorted order
    matches the sector_0_deg / sector_120_deg / sector_240_deg assignment
    produced by SectorMapper.build_calibration().

    Args:
        decomposition : SpikeErrorDecomposition from decompose_spike_errors(lines).
        lines         : the same 3 SpikeLine objects used for decomposition.
        calibration   : MaskSectorCalibration from a completed SectorMapper.

    Returns:
        dict mapping screw_id → residual_px.
    """
    sorted_indices = sorted(range(3), key=lambda i: lines[i].angle_deg)
    screws = (calibration.sector_0_deg, calibration.sector_120_deg, calibration.sector_240_deg)
    return {
        screws[pos]: decomposition.residuals_px[sorted_indices[pos]]
        for pos in range(3)
    }


class FineCollimationAdvisor:
    """Recommend fine collimation screw turns from per-sector spike residuals.

    Args:
        target_residual_px      : residuals below this threshold → no action (default 2.0).
        seeing_limited_px       : jitter above this → suppress recommendation (default 3.0).
        confidence_threshold    : measurement confidence below this → suppress (default 0.5).
        medium_threshold_ratio  : residual/target ratio above this → MEDIUM size (default 1.5).
    """

    def __init__(
        self,
        target_residual_px: float = 2.0,
        seeing_limited_px: float = 3.0,
        confidence_threshold: float = 0.5,
        medium_threshold_ratio: float = 1.5,
    ) -> None:
        self._target        = target_residual_px
        self._seeing_px     = seeing_limited_px
        self._conf_thresh   = confidence_threshold
        self._medium_ratio  = medium_threshold_ratio

    # ── public ────────────────────────────────────────────────────────────────

    def recommend(
        self,
        residuals_by_screw: dict[str, float],
        smoothed: SmoothedSpikeResult,
    ) -> CollimationRecommendation | None:
        """Return a screw recommendation or None when no action is warranted.

        Args:
            residuals_by_screw : dict mapping screw_id → residual_px (from
                                 align_residuals_to_screws or manual mapping).
            smoothed           : SmoothedSpikeResult from SpikeSmoother for
                                 jitter and confidence checks.

        Returns:
            CollimationRecommendation, or None if blocked.
        """
        if not residuals_by_screw:
            return None

        # Block on seeing or low confidence.
        if smoothed.seeing_limited:
            return None
        if smoothed.confidence < self._conf_thresh:
            return None

        # Find worst screw.
        worst_screw = max(residuals_by_screw, key=lambda s: abs(residuals_by_screw[s]))
        worst_res   = residuals_by_screw[worst_screw]

        if abs(worst_res) < self._target:
            return None

        # Direction: positive residual → CW corrects it.
        direction = (
            TurnDirection.CLOCKWISE
            if worst_res > 0
            else TurnDirection.COUNTER_CLOCKWISE
        )

        # Size: MEDIUM when significantly above target, else SMALL.
        ratio    = abs(worst_res) / self._target
        adj_size = AdjustmentSize.MEDIUM if ratio >= self._medium_ratio else AdjustmentSize.SMALL

        # Confidence proportional to measurement quality and margin above target.
        margin_conf = min(1.0, ratio / 5.0)
        confidence  = smoothed.confidence * margin_conf

        reason = (
            f"Fine residual {abs(worst_res):.1f} px on {worst_screw} "
            f"(target {self._target:.1f} px, jitter {smoothed.jitter_px:.1f} px)"
        )

        return CollimationRecommendation(
            screw_id=worst_screw,
            turn_direction=direction,
            adjustment_size=adj_size,
            reason=reason,
            confidence=confidence,
        )
