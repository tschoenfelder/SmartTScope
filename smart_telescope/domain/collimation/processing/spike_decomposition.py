"""Tri-Bahtinov spike error decomposition — Collimation Phase 11, COL-110.

Separates the common focus error (global defocus) from the per-sector
collimation residuals by treating each spike line in turn as the "middle"
spike of a standard Bahtinov analysis.

Mathematical basis
------------------
For a set of 3 normalised lines L0, L1, L2 (ax + by + c = 0, ||(a,b)|| = 1):

  error_i = a_i * Pjk_x + b_i * Pjk_y + c_i        (signed distance)

where Pjk is the intersection of the two lines j, k ≠ i.

When the telescope is perfectly collimated AND in focus, all three pairwise
intersections coincide and all three error values are zero.
  - A common non-zero shift (error_0 ≈ error_1 ≈ error_2 ≠ 0) indicates pure
    defocus; the focuser can correct it.
  - Residuals (error_i − common) indicate collimation misalignment; corrected
    by turning screw i.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from ...bahtinov import SpikeLine


@dataclass(frozen=True)
class SpikeErrorDecomposition:
    """Result of a 3-way Bahtinov error decomposition.

    sector_errors_px   : signed focus error for each of the 3 spike lines
                         (treating that line as the "middle" spike).
    common_focus_error_px : mean of sector_errors — the global defocus signal.
    residuals_px       : per-sector collimation residuals
                         (sector_errors[i] − common_focus_error).
    max_residual_px    : max absolute residual across the three sectors.
    rms_residual_px    : root-mean-square of residuals.
    """
    sector_errors_px: tuple[float, float, float]
    common_focus_error_px: float
    residuals_px: tuple[float, float, float]
    max_residual_px: float
    rms_residual_px: float

    @property
    def worst_sector_index(self) -> int:
        """Index of the sector with the largest absolute residual."""
        return max(range(3), key=lambda i: abs(self.residuals_px[i]))


def decompose_spike_errors(lines: list[SpikeLine]) -> SpikeErrorDecomposition:
    """Compute per-sector focus errors and the common/residual decomposition.

    Args:
        lines: exactly 3 SpikeLine objects from a CrossingAnalysisResult.

    Raises:
        ValueError: if fewer or more than 3 lines are supplied.
    """
    if len(lines) != 3:
        raise ValueError(f"Expected exactly 3 spike lines, got {len(lines)}")

    errors: list[float] = []
    for i in range(3):
        j, k = [x for x in range(3) if x != i]
        px, py = _intersect(lines[j], lines[k])
        err = lines[i].a * px + lines[i].b * py + lines[i].c
        errors.append(err)

    common = sum(errors) / 3.0
    residuals = tuple(e - common for e in errors)  # type: ignore[assignment]
    max_res = max(abs(r) for r in residuals)
    rms_res = math.sqrt(sum(r * r for r in residuals) / 3.0)

    return SpikeErrorDecomposition(
        sector_errors_px=(errors[0], errors[1], errors[2]),
        common_focus_error_px=common,
        residuals_px=residuals,  # type: ignore[arg-type]
        max_residual_px=max_res,
        rms_residual_px=rms_res,
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _intersect(l1: SpikeLine, l2: SpikeLine) -> tuple[float, float]:
    """Intersection of two normal-form lines; returns (0, 0) for near-parallel."""
    d = l1.a * l2.b - l2.a * l1.b
    if abs(d) < 1e-10:
        return (0.0, 0.0)
    x = (l1.b * l2.c - l2.b * l1.c) / d
    y = (l2.a * l1.c - l1.a * l2.c) / d
    return (x, y)
