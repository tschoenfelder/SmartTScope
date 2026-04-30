"""Target visibility — altitude/azimuth computation for a ground observer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
from astropy.coordinates import AltAz, EarthLocation, SkyCoord
from astropy.time import Time
import astropy.units as u


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
) -> bool:
    alt, _ = compute_altaz(ra_hours, dec_deg, observer_lat, observer_lon, obs_time)
    return alt >= min_altitude


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
) -> VisibilityWindow:
    """Sample the target's altitude at *sample_minutes* intervals and derive the window.

    *night_start* / *night_end* should be UTC-aware datetimes (civil/astronomical
    twilight boundaries for the observation night).  *rises_at* / *sets_at* are
    the first and last sample times at or above *min_altitude_deg*; they are
    accurate to within ±*sample_minutes* minutes of the true crossing.
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
    for sample_t in times:
        astro_t = Time(sample_t.replace(tzinfo=None), format="datetime", scale="utc")
        alt, _ = compute_altaz(ra_hours, dec_deg, observer_lat, observer_lon, astro_t)
        altitudes.append(alt)

    peak_idx = int(np.argmax(altitudes))
    peak_altitude = float(altitudes[peak_idx])
    peak_time = times[peak_idx]

    if peak_altitude < min_altitude_deg:
        return VisibilityWindow(
            rises_at=None, sets_at=None,
            peak_altitude=peak_altitude, peak_time=peak_time,
            is_observable=False,
        )

    rises_at = next(t for alt, t in zip(altitudes, times) if alt >= min_altitude_deg)
    sets_at  = next(t for alt, t in zip(reversed(altitudes), reversed(times)) if alt >= min_altitude_deg)

    return VisibilityWindow(
        rises_at=rises_at, sets_at=sets_at,
        peak_altitude=peak_altitude, peak_time=peak_time,
        is_observable=True,
    )
