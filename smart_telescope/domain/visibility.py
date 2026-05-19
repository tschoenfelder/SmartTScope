"""Target visibility — altitude/azimuth computation for a ground observer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time
import astropy.units as u


class HorizonProfile:
    """Piecewise-linear local horizon loaded from a KStars Alt-Az export.

    Provides the minimum visible altitude at any azimuth via linear
    interpolation between the file's control points.  Returns 0.0
    gracefully when no file is loaded.
    """

    def __init__(self, points: list[tuple[float, float]]) -> None:
        self._pts: list[tuple[float, float]] = sorted(points)

    @classmethod
    def load(cls, path: str | Path) -> "HorizonProfile":
        """Parse a KStars artificial horizon export (Alt Az format)."""
        pts: list[tuple[float, float]] = []
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or not line[0].isdigit():
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    pts.append((float(parts[0]), float(parts[1])))
        return cls(pts)

    def min_alt_at(self, az_deg: float) -> float:
        """Return interpolated minimum altitude for *az_deg* (0 = N, CW)."""
        if not self._pts:
            return 0.0
        az = az_deg % 360.0
        pts = self._pts
        for i in range(len(pts) - 1):
            az0, alt0 = pts[i]
            az1, alt1 = pts[i + 1]
            if az0 <= az <= az1:
                if az1 == az0:
                    return alt0
                return alt0 + (az - az0) / (az1 - az0) * (alt1 - alt0)
        # wrap: interpolate between last point and first point + 360°
        az0, alt0 = pts[-1]
        az1, alt1 = pts[0][0] + 360.0, pts[0][1]
        az_w = az if az >= az0 else az + 360.0
        return alt0 + (az_w - az0) / (az1 - az0) * (alt1 - alt0)

    def is_visible(self, alt_deg: float, az_deg: float) -> bool:
        return alt_deg >= self.min_alt_at(az_deg)


def load_horizon(path: str | Path) -> HorizonProfile | None:
    """Return a HorizonProfile if *path* exists, else None."""
    p = Path(path)
    return HorizonProfile.load(p) if p.exists() else None


def compute_altaz(
    ra_hours: float,
    dec_deg: float,
    observer_lat: float,
    observer_lon: float,
    obs_time: Time | None = None,
) -> tuple[float, float]:
    """Return (altitude_deg, azimuth_deg) for *ra_hours* / *dec_deg* at the observer.

    *obs_time* defaults to ``Time.now()`` (UTC).  Pass an explicit value in
    tests so results are deterministic.
    """
    if obs_time is None:
        obs_time = Time.now()
    location = EarthLocation(lat=observer_lat * u.deg, lon=observer_lon * u.deg)
    frame = AltAz(obstime=obs_time, location=location)
    coord = SkyCoord(ra=ra_hours * u.hourangle, dec=dec_deg * u.deg)
    altaz = coord.transform_to(frame)
    return float(altaz.alt.deg), float(altaz.az.deg)


def is_observable(
    ra_hours: float,
    dec_deg: float,
    observer_lat: float,
    observer_lon: float,
    min_altitude: float = 20.0,
    obs_time: Time | None = None,
    horizon: HorizonProfile | None = None,
) -> bool:
    alt, az = compute_altaz(ra_hours, dec_deg, observer_lat, observer_lon, obs_time)
    if alt < min_altitude:
        return False
    return horizon is None or horizon.is_visible(alt, az)


@dataclass(frozen=True)
class VisibilityWindow:
    rises_at:      datetime | None  # first sample at/above min_altitude (or night_start if always up)
    sets_at:       datetime | None  # last sample at/above min_altitude (or night_end if always up)
    peak_altitude: float            # maximum sampled altitude during the window
    peak_time:     datetime | None  # time of peak altitude
    is_observable: bool             # True iff peak_altitude >= min_altitude_deg


def compute_visibility_window(
    ra_hours: float,
    dec_deg: float,
    observer_lat: float,
    observer_lon: float,
    night_start: datetime,
    night_end: datetime,
    min_altitude_deg: float = 20.0,
    sample_minutes: int = 5,
    horizon: HorizonProfile | None = None,
) -> VisibilityWindow:
    """Sample the target's altitude at *sample_minutes* intervals and derive the window.

    *night_start* / *night_end* should be UTC-aware datetimes (civil/astronomical
    twilight boundaries for the observation night).  *rises_at* / *sets_at* are
    the first and last sample times at or above *min_altitude_deg*; they are
    accurate to within ±*sample_minutes* minutes of the true crossing.
    When *horizon* is supplied, samples below the local horizon profile are
    treated as not visible even if they clear *min_altitude_deg*.
    """
    dt = timedelta(minutes=sample_minutes)
    times: list[datetime] = []
    t = night_start
    while t <= night_end:
        times.append(t)
        t += dt
    if not times or times[-1] < night_end:
        times.append(night_end)

    altitudes: list[float] = []
    visible: list[bool] = []
    for sample_t in times:
        astro_t = Time(sample_t.replace(tzinfo=None), format="datetime", scale="utc")
        alt, az = compute_altaz(ra_hours, dec_deg, observer_lat, observer_lon, astro_t)
        altitudes.append(alt)
        above = alt >= min_altitude_deg and (horizon is None or horizon.is_visible(alt, az))
        visible.append(above)

    peak_idx = int(np.argmax(altitudes))
    peak_altitude = float(altitudes[peak_idx])
    peak_time = times[peak_idx]

    if not any(visible):
        return VisibilityWindow(
            rises_at=None, sets_at=None,
            peak_altitude=peak_altitude, peak_time=peak_time,
            is_observable=False,
        )

    rises_at = next(t for v, t in zip(visible, times) if v)
    sets_at  = next(t for v, t in zip(reversed(visible), reversed(times)) if v)

    return VisibilityWindow(
        rises_at=rises_at, sets_at=sets_at,
        peak_altitude=peak_altitude, peak_time=peak_time,
        is_observable=True,
    )
