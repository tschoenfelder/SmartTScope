"""GPSD status and observer location update endpoints."""
from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import config
from ..services.gpsd_service import GpsdService, haversine_m

router = APIRouter()

_gpsd = GpsdService()

_CONFIG_PATH = Path.home() / ".SmartTScope" / "config.toml"


class GpsdStatusResponse(BaseModel):
    available: bool
    fix_mode: int = 0
    lat: float = 0.0
    lon: float = 0.0
    alt_m: float | None = None
    gps_time: str | None = None
    distance_m: float = 0.0
    configured_lat: float = 0.0
    configured_lon: float = 0.0


class ObserverLocationRequest(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


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
        distance_m=round(dist, 1),
        configured_lat=config.OBSERVER_LAT,
        configured_lon=config.OBSERVER_LON,
    )


@router.post("/api/observer/location")
def update_observer_location(body: ObserverLocationRequest) -> dict[str, bool]:
    """Update observer lat/lon in memory and persist to ~/.SmartTScope/config.toml."""
    config.OBSERVER_LAT = body.lat
    config.OBSERVER_LON = body.lon

    if _CONFIG_PATH.exists():
        text = _CONFIG_PATH.read_text(encoding="utf-8")
        text = re.sub(
            r"(?m)^(lat\s*=\s*).*$",
            lambda m: f"{m.group(1)}{body.lat}",
            text,
        )
        text = re.sub(
            r"(?m)^(lon\s*=\s*).*$",
            lambda m: f"{m.group(1)}{body.lon}",
            text,
        )
        _CONFIG_PATH.write_text(text, encoding="utf-8")

    return {"ok": True}
