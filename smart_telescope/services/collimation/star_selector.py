"""Collimation star selection — Phase 5, Task 5.1.

Picks the best visible bright star for collimation:
  - Primary criterion: altitude >= 60°, sorted by magnitude (brightest first).
  - Fallback: altitude >= 45°, same sort, with a warning in the result.
  - Manual override: caller names a specific star.

The star list is loaded from a TOML file matching the stars.cfg format
(targets[].type == "star") or injected directly for testing.
"""
from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass
from pathlib import Path

from astropy.time import Time

from ... import config as _config
from ...domain.visibility import compute_altaz, compute_ha

_log = logging.getLogger(__name__)

_PRIMARY_MIN_ALT:  float = 60.0
_FALLBACK_MIN_ALT: float = 45.0


@dataclass(frozen=True)
class BrightStar:
    """Catalog entry for a collimation star."""
    name: str
    ra_hours: float
    dec_deg: float
    magnitude: float


@dataclass(frozen=True)
class CollimationStarCandidate:
    """Selected star with computed altitude/azimuth."""
    star: BrightStar
    altitude_deg: float
    azimuth_deg: float


@dataclass(frozen=True)
class StarSelectionResult:
    """Outcome of a star selection attempt."""
    candidate: CollimationStarCandidate | None
    reason: str       # "selected" | "fallback" | "none_visible" | "manual"
    warning: str | None


def load_bright_stars(path: str | Path) -> list[BrightStar]:
    """Parse a stars.cfg TOML file and return all type="star" entries."""
    with open(path, "rb") as fh:
        data = tomllib.load(fh)
    stars: list[BrightStar] = []
    for entry in data.get("targets", []):
        if entry.get("type") != "star":
            continue
        mag = entry.get("magnitude")
        if mag is None:
            continue
        stars.append(BrightStar(
            name=entry["name"],
            ra_hours=float(entry["ra"]),
            dec_deg=float(entry["dec"]),
            magnitude=float(mag),
        ))
    return stars


class CollimationStarSelector:
    """Select the best visible bright star for collimation.

    Inject a list of BrightStar entries and the observer location.
    Call select() for automatic selection or select_by_name() for manual override.
    """

    def __init__(
        self,
        stars: list[BrightStar],
        observer_lat: float,
        observer_lon: float,
    ) -> None:
        self._stars = stars
        self._lat = observer_lat
        self._lon = observer_lon

    def select(
        self,
        obs_time: Time | None = None,
        primary_min_alt: float = _PRIMARY_MIN_ALT,
        fallback_min_alt: float = _FALLBACK_MIN_ALT,
    ) -> StarSelectionResult:
        """Select the best star, falling back to a lower altitude limit if needed.

        Args:
            obs_time        : observation time; defaults to Time.now().
            primary_min_alt : preferred minimum altitude in degrees (default 60°).
            fallback_min_alt: fallback minimum altitude in degrees (default 45°).
        """
        candidates: list[CollimationStarCandidate] = []
        for star in self._stars:
            ha = compute_ha(star.ra_hours, self._lon, obs_time)
            if ha > _config.MOUNT_HA_WEST_LIMIT_H or ha < _config.MOUNT_HA_EAST_LIMIT_H:
                continue
            alt, az = compute_altaz(star.ra_hours, star.dec_deg, self._lat, self._lon, obs_time)
            candidates.append(CollimationStarCandidate(star=star, altitude_deg=alt, azimuth_deg=az))

        # Prefer stars above primary threshold; within group sort by magnitude (brightest = lowest)
        primary = [c for c in candidates if c.altitude_deg >= primary_min_alt]
        if primary:
            best = min(primary, key=lambda c: c.star.magnitude)
            return StarSelectionResult(candidate=best, reason="selected", warning=None)

        fallback = [c for c in candidates if c.altitude_deg >= fallback_min_alt]
        if fallback:
            best = min(fallback, key=lambda c: c.star.magnitude)
            warn = (
                f"No collimation star above {primary_min_alt:.0f}°; "
                f"using {best.star.name} at {best.altitude_deg:.1f}° (fallback)"
            )
            _log.warning(warn)
            return StarSelectionResult(candidate=best, reason="fallback", warning=warn)

        return StarSelectionResult(candidate=None, reason="none_visible", warning=None)

    def select_by_name(
        self,
        name: str,
        obs_time: Time | None = None,
    ) -> StarSelectionResult:
        """Manual override — select a specific star by name (case-insensitive)."""
        for star in self._stars:
            if star.name.lower() == name.lower():
                ha = compute_ha(star.ra_hours, self._lon, obs_time)
                if ha > _config.MOUNT_HA_WEST_LIMIT_H or ha < _config.MOUNT_HA_EAST_LIMIT_H:
                    return StarSelectionResult(
                        candidate=None,
                        reason="none_visible",
                        warning=f"{star.name} is outside mount HA limits (HA {ha:.2f}h)",
                    )
                alt, az = compute_altaz(star.ra_hours, star.dec_deg, self._lat, self._lon, obs_time)
                candidate = CollimationStarCandidate(star=star, altitude_deg=alt, azimuth_deg=az)
                return StarSelectionResult(candidate=candidate, reason="manual", warning=None)
        return StarSelectionResult(
            candidate=None,
            reason="none_visible",
            warning=f"Star not found in catalog: {name!r}",
        )
