"""Contradiction detector for collimation guidance safety — Phase 11, COL-113.

Compares multiple measurement indicators and blocks screw-turn guidance when
they disagree or when measurement quality is too low.  Returns a
ContradictionAssessment which, when stop_guidance is True, should prevent the
caller from issuing any screw instruction.

Checks performed (in order)
----------------------------
1. Seeing-limited  : jitter_px > seeing_threshold → star seeing prevents reliable measurement.
2. Focus drift     : |common_focus_error_px| > focus_target_px → scope needs refocus first.
3. Low confidence  : smoothed.confidence < confidence_threshold → measurements unreliable.
4. Residuals worse : max_residual worse than previous call → collimation drifting backward.

Any failing check sets stop_guidance = True and appends a human-readable
description to conflicting_indicators.
"""
from __future__ import annotations

from ...domain.collimation.models import ContradictionAssessment
from ...domain.collimation.processing.spike_decomposition import SpikeErrorDecomposition
from .spike_smoother import SmoothedSpikeResult

_DEFAULT_RECOMMENDED_ACTION = (
    "Recenter the star, refocus, and remeasure before resuming screw adjustments."
)


class ContradictionDetector:
    """Assess whether multiple collimation indicators agree.

    Args:
        focus_target_px      : |common_focus_error| above this triggers focus-drift check.
        confidence_threshold : measurement confidence below this → blocked.
        seeing_threshold_px  : jitter above this → seeing-limited → blocked.
    """

    def __init__(
        self,
        focus_target_px: float = 2.0,
        confidence_threshold: float = 0.5,
        seeing_threshold_px: float = 3.0,
    ) -> None:
        self._focus_target = focus_target_px
        self._conf_thresh  = confidence_threshold
        self._seeing_px    = seeing_threshold_px
        self._prev_max_res: float | None = None

    # ── public ────────────────────────────────────────────────────────────────

    def assess(
        self,
        smoothed: SmoothedSpikeResult,
        decomposition: SpikeErrorDecomposition,
    ) -> ContradictionAssessment:
        """Evaluate all indicators and return a ContradictionAssessment.

        Args:
            smoothed      : SmoothedSpikeResult from SpikeSmoother.
            decomposition : SpikeErrorDecomposition from decompose_spike_errors().

        Returns:
            ContradictionAssessment; stop_guidance is True when any check fails.
        """
        conflicts: list[str] = []

        # 1. Seeing-limited
        if smoothed.jitter_px > self._seeing_px:
            conflicts.append(
                f"Poor seeing: jitter {smoothed.jitter_px:.1f} px "
                f"exceeds threshold {self._seeing_px:.1f} px — measurements unreliable."
            )

        # 2. Focus drift
        focus_err = abs(decomposition.common_focus_error_px)
        if focus_err > self._focus_target:
            conflicts.append(
                f"Focus drift: common focus error {focus_err:.1f} px "
                f"exceeds target {self._focus_target:.1f} px — refocus required."
            )

        # 3. Low confidence
        if smoothed.confidence < self._conf_thresh:
            conflicts.append(
                f"Low measurement confidence {smoothed.confidence:.2f} "
                f"(threshold {self._conf_thresh:.2f}) — check star centering."
            )

        # 4. Residuals worsening (stateful — compares to previous assess() call)
        cur_max = decomposition.max_residual_px
        if self._prev_max_res is not None and cur_max > self._prev_max_res + 0.5:
            conflicts.append(
                f"Residuals worsened: max residual increased from "
                f"{self._prev_max_res:.1f} px to {cur_max:.1f} px — check screw direction."
            )
        self._prev_max_res = cur_max

        stop  = len(conflicts) > 0
        # Overall confidence: mean of smoothed.confidence and a quality score
        # derived from jitter vs threshold.
        jitter_score = max(0.0, 1.0 - smoothed.jitter_px / max(self._seeing_px, 1e-3))
        overall_conf = (smoothed.confidence + jitter_score) / 2.0

        action = _DEFAULT_RECOMMENDED_ACTION if stop else "All indicators consistent — proceed."

        return ContradictionAssessment(
            has_contradiction=stop,
            conflicting_indicators=conflicts,
            stop_guidance=stop,
            recommended_action=action,
            confidence=round(overall_conf, 3),
        )

    def reset(self) -> None:
        """Clear stored state (call when starting a new collimation session)."""
        self._prev_max_res = None
