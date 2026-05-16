"""Tri-Bahtinov mask sector mapper — Collimation Phase 10, COL-101.

Maps each Tri-Bahtinov mask sector to a physical collimation screw by
observing which spike line disappears when a blade sector is closed.

Usage
-----
1. Create a SectorMapper with the user-supplied sector→screw mapping.
2. For each sector, call observe() with the full-open lines and the
   same-frame lines captured with that sector's blade closed.
3. After all three sectors, call build_calibration().

Sector labels ("A", "B", "C") are arbitrary user-facing names; the
output MaskSectorCalibration uses sorted spike-angle order to assign
sector_0_deg / sector_120_deg / sector_240_deg positions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ...domain.bahtinov import SpikeLine
from ...domain.collimation.models import MaskSectorCalibration

_ANGLE_MATCH_TOL_DEG = 10.0   # two spike lines are "the same" within this tolerance


def _spike_angle_diff(a: float, b: float) -> float:
    """Smallest difference between two spike-line angles (0–180° range)."""
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


class SectorMapper:
    """Identify which collimation screw each Tri-Bahtinov sector controls.

    Args:
        sector_to_screw : dict mapping sector label (e.g. "A") to screw
                          identifier (e.g. "T1").  All three labels must be
                          present before build_calibration() can succeed.
    """

    def __init__(self, sector_to_screw: dict[str, str]) -> None:
        self._sector_to_screw: dict[str, str] = dict(sector_to_screw)
        self._observations: dict[str, float] = {}  # sector_label -> missing angle_deg

    # ── public ────────────────────────────────────────────────────────────────

    def observe(
        self,
        sector_label: str,
        open_lines: list[SpikeLine],
        closed_lines: list[SpikeLine],
    ) -> float | None:
        """Record which spike line disappeared when a sector blade was closed.

        Args:
            sector_label : user-supplied label for the closed sector.
            open_lines   : spike lines detected with all sectors open (≥ 3).
            closed_lines : spike lines detected with this sector closed (< len(open_lines)).

        Returns:
            The angle_deg of the missing spike line, or None if indeterminate.
        """
        if len(open_lines) < 3:
            return None
        if len(closed_lines) >= len(open_lines):
            return None

        for ol in open_lines:
            matched = any(
                _spike_angle_diff(ol.angle_deg, cl.angle_deg) < _ANGLE_MATCH_TOL_DEG
                for cl in closed_lines
            )
            if not matched:
                self._observations[sector_label] = ol.angle_deg % 180.0
                return ol.angle_deg % 180.0

        return None

    def build_calibration(self, calibrated_at: str | None = None) -> MaskSectorCalibration | None:
        """Produce a MaskSectorCalibration once all sectors have been observed.

        The three observed spike-line angles are sorted ascending; the sector
        with the smallest angle becomes sector_0_deg, middle → sector_120_deg,
        largest → sector_240_deg.

        Returns None if any required sector observation is missing or if two
        sectors produced the same spike-line angle (ambiguous mask orientation).
        """
        needed = set(self._sector_to_screw.keys())
        if not needed.issubset(self._observations.keys()):
            return None

        labeled = [
            (self._observations[label], self._sector_to_screw[label])
            for label in needed
        ]
        labeled.sort(key=lambda t: t[0])

        if len(labeled) < 3:
            return None

        # Check for ambiguous duplicates — two sectors at the same angle
        angles = [t[0] for t in labeled]
        for i in range(len(angles) - 1):
            if _spike_angle_diff(angles[i], angles[i + 1]) < _ANGLE_MATCH_TOL_DEG:
                return None

        ts = calibrated_at or datetime.now(timezone.utc).isoformat()
        return MaskSectorCalibration(
            sector_0_deg=labeled[0][1],
            sector_120_deg=labeled[1][1],
            sector_240_deg=labeled[2][1],
            calibrated_at=ts,
        )

    @property
    def observed_sectors(self) -> set[str]:
        return set(self._observations.keys())
