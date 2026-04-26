"""Solar exclusion gate — prevent accidental slews toward the Sun."""

from __future__ import annotations

from dataclasses import dataclass

import astropy.units as u
from astropy.coordinates import SkyCoord, get_sun
from astropy.time import Time

SOLAR_EXCLUSION_DEG: float = 10.0


@dataclass(frozen=True)
class SolarPosition:
    ra_hours: float
    dec_deg: float


def sun_position_now() -> SolarPosition:
    sun = get_sun(Time.now())
    return SolarPosition(
        ra_hours=float(sun.ra.hour),
        dec_deg=float(sun.dec.deg),
    )


def angular_separation_deg(
    ra1_h: float, dec1_d: float,
    ra2_h: float, dec2_d: float,
) -> float:
    c1 = SkyCoord(ra=ra1_h * u.hourangle, dec=dec1_d * u.deg)
    c2 = SkyCoord(ra=ra2_h * u.hourangle, dec=dec2_d * u.deg)
    return float(c1.separation(c2).deg)


def is_solar_target(
    target_ra_h: float,
    target_dec_d: float,
    *,
    threshold_deg: float = SOLAR_EXCLUSION_DEG,
    sun: SolarPosition | None = None,
) -> tuple[bool, float]:
    """Return (blocked, sun_separation_deg). blocked=True when too close to the Sun."""
    if sun is None:
        sun = sun_position_now()
    sep = angular_separation_deg(target_ra_h, target_dec_d, sun.ra_hours, sun.dec_deg)
    return sep < threshold_deg, sep
