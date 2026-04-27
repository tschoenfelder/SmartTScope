"""Target visibility — altitude/azimuth computation for a ground observer."""

from __future__ import annotations

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
