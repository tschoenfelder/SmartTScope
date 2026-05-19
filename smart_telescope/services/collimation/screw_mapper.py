"""Screw calibration services — Collimation Phase 8, COL-080/081.

ScrewResponseLearner (COL-081):
    Accumulates before/after DonutMeasurement pairs per screw and computes
    a running average of the response vector (error-vector shift per CW turn).
    Confidence increases with the number of observations.

ScrewAngularPosition and ScrewMapCalibration are domain models defined in
domain/collimation/models.py; this module only imports and re-exports them
for convenience.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from ...domain.collimation.models import DonutMeasurement, ScrewCalibration


@dataclass
class ScrewResponseLearner:
    """Accumulate before/after donut measurements to learn screw responses.

    For each observation call (screw_id, before, after, turn_cw):
    - delta_x = after.error_x_px − before.error_x_px
    - delta_y = after.error_y_px − before.error_y_px
    - If turn_cw is False the deltas are negated (convert to CW-equivalent).

    Call get_calibration(screw_id) to retrieve the averaged ScrewCalibration.
    Call get_all() to retrieve all screws that have at least one observation.

    Confidence saturates at _CONF_SATURATION_SAMPLES observations.
    """

    _CONF_SATURATION_SAMPLES: int = field(default=5, init=False, repr=False)

    def __post_init__(self) -> None:
        # {screw_id: [(delta_x, delta_y), ...]}  — all as CW-equivalent deltas
        self._observations: dict[str, list[tuple[float, float]]] = {}

    def observe(
        self,
        screw_id: str,
        before: DonutMeasurement,
        after: DonutMeasurement,
        turn_cw: bool,
    ) -> ScrewCalibration:
        """Record one before/after observation for a screw.

        Args:
            screw_id : "T1", "T2", or "T3".
            before   : DonutMeasurement taken before the user turned the screw.
            after    : DonutMeasurement taken after the user turned the screw.
            turn_cw  : True if the user turned the screw clockwise.

        Returns:
            Updated ScrewCalibration for screw_id (averaged across all
            observations so far).
        """
        dx = after.error_x_px - before.error_x_px
        dy = after.error_y_px - before.error_y_px
        if not turn_cw:
            dx, dy = -dx, -dy

        if screw_id not in self._observations:
            self._observations[screw_id] = []
        self._observations[screw_id].append((dx, dy))

        return self._build_calibration(screw_id)

    def get_calibration(self, screw_id: str) -> ScrewCalibration | None:
        """Return the current ScrewCalibration for screw_id, or None if unknown."""
        if screw_id not in self._observations:
            return None
        return self._build_calibration(screw_id)

    def get_all(self) -> list[ScrewCalibration]:
        """Return ScrewCalibration for every screw with at least one observation."""
        return [self._build_calibration(sid) for sid in self._observations]

    # ── Private ───────────────────────────────────────────────────────────────

    def _build_calibration(self, screw_id: str) -> ScrewCalibration:
        obs = self._observations[screw_id]
        n   = len(obs)
        avg_x = sum(dx for dx, _ in obs) / n
        avg_y = sum(dy for _, dy in obs) / n
        confidence = min(1.0, n / self._CONF_SATURATION_SAMPLES)
        return ScrewCalibration(
            screw_id=screw_id,
            response_vector_x=avg_x,
            response_vector_y=avg_y,
            samples=n,
            confidence=confidence,
        )
