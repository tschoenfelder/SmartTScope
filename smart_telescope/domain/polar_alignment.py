"""Polar alignment math — find EQ mount pole from 3 plate-solved positions."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class SkyPoint:
    ra: float   # hours
    dec: float  # degrees


def _to_xyz(ra_h: float, dec_deg: float) -> tuple[float, float, float]:
    ra_r  = math.radians(ra_h * 15.0)
    dec_r = math.radians(dec_deg)
    return (
        math.cos(dec_r) * math.cos(ra_r),
        math.cos(dec_r) * math.sin(ra_r),
        math.sin(dec_r),
    )


def _normalize(v: tuple[float, float, float]) -> tuple[float, float, float]:
    mag = math.sqrt(v[0] ** 2 + v[1] ** 2 + v[2] ** 2)
    if mag < 1e-12:
        raise ValueError("zero-length vector — plate-solve positions are collinear")
    return (v[0] / mag, v[1] / mag, v[2] / mag)


def _cross(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _sub(a: tuple[float, float, float], b: tuple[float, float, float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def find_rotation_pole(p1: SkyPoint, p2: SkyPoint, p3: SkyPoint) -> SkyPoint:
    """Return the mount RA-axis direction (actual pole) from 3 plate-solved positions.

    The three frame-centre positions trace a small circle on the celestial sphere
    as the mount is rotated in RA.  The centre of that circle = the rotation axis =
    where the mount is actually pointing its polar axis.

    Derivation: pole vector P satisfies P·(v1−v2) = 0 and P·(v2−v3) = 0,
    so P ∝ (v1−v2) × (v2−v3).
    """
    v1 = _to_xyz(p1.ra, p1.dec)
    v2 = _to_xyz(p2.ra, p2.dec)
    v3 = _to_xyz(p3.ra, p3.dec)

    pole = _normalize(_cross(_sub(v1, v2), _sub(v2, v3)))

    if pole[2] < 0:   # ensure northern hemisphere
        pole = (-pole[0], -pole[1], -pole[2])

    dec_deg = math.degrees(math.asin(max(-1.0, min(1.0, pole[2]))))
    ra_h    = math.degrees(math.atan2(pole[1], pole[0])) / 15.0
    if ra_h < 0:
        ra_h += 24.0

    return SkyPoint(ra=round(ra_h, 4), dec=round(dec_deg, 4))


@dataclass
class PolarError:
    alt_error_arcmin: float   # >0 = pole too high → lower the altitude screw
    az_error_arcmin: float    # >0 = pole too far east → move azimuth screw west
    total_error_arcmin: float


def compute_polar_error(
    pole: SkyPoint,
    observer_lat: float,  # degrees
    lst: float,           # local sidereal time, hours
) -> PolarError:
    """Convert detected pole position to ALT/AZ mount-screw corrections.

    Perfect polar alignment: mount pole at ALT = observer latitude, AZ = 0° (N).
    """
    ha_h   = lst - pole.ra
    ha_r   = math.radians(((ha_h + 12.0) % 24.0 - 12.0) * 15.0)
    dec_r  = math.radians(pole.dec)
    lat_r  = math.radians(observer_lat)

    sin_alt = (math.sin(lat_r) * math.sin(dec_r)
               + math.cos(lat_r) * math.cos(dec_r) * math.cos(ha_r))
    alt_rad = math.asin(max(-1.0, min(1.0, sin_alt)))
    alt_deg = math.degrees(alt_rad)

    cos_alt = math.cos(alt_rad)
    if cos_alt > 1e-9:
        cos_az_val = (math.sin(dec_r) - math.sin(alt_rad) * math.sin(lat_r)) / (
            cos_alt * math.cos(lat_r))
        az_deg = math.degrees(math.acos(max(-1.0, min(1.0, cos_az_val))))
        if math.sin(ha_r) > 0:
            az_deg = 360.0 - az_deg
    else:
        az_deg = 0.0

    alt_error_deg = alt_deg - observer_lat
    az_error_deg  = az_deg if az_deg <= 180.0 else az_deg - 360.0

    return PolarError(
        alt_error_arcmin=round(alt_error_deg * 60.0, 1),
        az_error_arcmin=round(az_error_deg * 60.0, 1),
        total_error_arcmin=round(math.hypot(alt_error_deg, az_error_deg) * 60.0, 1),
    )
