"""GPSD status endpoint.

Observer-location writes moved to api/location.py (Confirm Time & Location panel).
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from .. import config
from ..services.gpsd_service import GpsdService, haversine_m

router = APIRouter()

_gpsd = GpsdService()


class GpsdStatusResponse(BaseModel):
    available: bool
    fix_mode: int = 0
    lat: float = 0.0
    lon: float = 0.0
    alt_m: float | None = None
    gps_time: str | None = None
    fix_age_s: float | None = None   # seconds since GPS timestamp (CFG-002)
    is_fresh: bool = False            # True when fix_age_s ≤ 60 min
    distance_m: float = 0.0
    configured_lat: float = 0.0
    configured_lon: float = 0.0


@router.get("/api/gpsd/status", response_model=GpsdStatusResponse)
def gpsd_status() -> GpsdStatusResponse:
    """Query local GPSD for a GPS fix. Returns available=false when GPSD is not running."""
    fix = _gpsd.get_fix()
    if fix is None:
        return GpsdStatusResponse(available=False)
    dist = haversine_m(fix.lat, fix.lon, config.OBSERVER_LAT, config.OBSERVER_LON)
    return GpsdStatusResponse(
        available=True,
        fix_mode=fix.mode,
        lat=fix.lat,
        lon=fix.lon,
        alt_m=fix.alt,
        gps_time=fix.gps_time,
        fix_age_s=fix.fix_age_s,
        is_fresh=fix.is_fresh(),
        distance_m=round(dist, 1),
        configured_lat=config.OBSERVER_LAT,
        configured_lon=config.OBSERVER_LON,
    )
