"""Catalog search API — GET /api/catalog/search, /objects, /tonight, /stars, /visible."""

from __future__ import annotations

import tomllib
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .. import config
from ..domain.catalog import CatalogObject, get_all, search
from ..domain.solar import is_solar_target
from ..domain.visibility import compute_altaz, compute_visibility_window

_STARS_CFG = Path(config.STARS_CFG)

router = APIRouter(prefix="/api/catalog")


class CatalogEntry(BaseModel):
    name: str
    common_name: str
    ra_hours: float
    dec_deg: float
    object_type: str
    magnitude: float
    altitude_deg: float | None = None
    azimuth_deg: float | None = None

    @classmethod
    def from_domain(
        cls,
        obj: CatalogObject,
        with_altaz: bool = False,
    ) -> "CatalogEntry":
        alt: float | None = None
        az: float | None = None
        if with_altaz:
            alt, az = compute_altaz(
                obj.ra_hours, obj.dec_deg,
                config.OBSERVER_LAT, config.OBSERVER_LON,
            )
        return cls(
            name=obj.name,
            common_name=obj.common_name,
            ra_hours=obj.ra_hours,
            dec_deg=obj.dec_deg,
            object_type=obj.object_type,
            magnitude=obj.magnitude,
            altitude_deg=round(alt, 1) if alt is not None else None,
            azimuth_deg=round(az, 1) if az is not None else None,
        )


@router.get("/search", response_model=list[CatalogEntry])
def catalog_search(
    q: str = Query(min_length=1, max_length=64),
    limit: int = Query(default=10, ge=1, le=50),
    min_altitude: float | None = Query(default=None, ge=-90.0, le=90.0),
) -> list[CatalogEntry]:
    results = search(q, limit=limit if min_altitude is None else 110)
    entries = [CatalogEntry.from_domain(obj, with_altaz=True) for obj in results]
    if min_altitude is not None:
        entries = [e for e in entries if e.altitude_deg is not None and e.altitude_deg >= min_altitude]
    return entries[:limit]


@router.get("/objects", response_model=list[CatalogEntry])
def catalog_objects(
    min_altitude: float | None = Query(default=None, ge=-90.0, le=90.0),
) -> list[CatalogEntry]:
    entries = [CatalogEntry.from_domain(obj, with_altaz=min_altitude is not None) for obj in get_all()]
    if min_altitude is not None:
        entries = [e for e in entries if e.altitude_deg is not None and e.altitude_deg >= min_altitude]
    return entries


class TonightEntry(CatalogEntry):
    solar_safe: bool


@router.get("/tonight", response_model=list[TonightEntry])
def catalog_tonight(
    min_altitude: float = Query(default=20.0, ge=-90.0, le=90.0),
    object_type: str | None = Query(default=None, description="Comma-separated types, e.g. GC,SG"),
    max_magnitude: float | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=110),
) -> list[TonightEntry]:
    """Observable Messier objects tonight, sorted highest-first."""
    type_filter = (
        {t.strip().upper() for t in object_type.split(",")} if object_type else None
    )

    results: list[TonightEntry] = []
    for obj in get_all():
        if type_filter and obj.object_type not in type_filter:
            continue
        if max_magnitude is not None and obj.magnitude > max_magnitude:
            continue
        alt, az = compute_altaz(
            obj.ra_hours, obj.dec_deg, config.OBSERVER_LAT, config.OBSERVER_LON
        )
        if alt < min_altitude:
            continue
        blocked, _ = is_solar_target(obj.ra_hours, obj.dec_deg)
        results.append(TonightEntry(
            name=obj.name,
            common_name=obj.common_name,
            ra_hours=obj.ra_hours,
            dec_deg=obj.dec_deg,
            object_type=obj.object_type,
            magnitude=obj.magnitude,
            altitude_deg=round(alt, 1),
            azimuth_deg=round(az, 1),
            solar_safe=not blocked,
        ))

    results.sort(key=lambda e: e.altitude_deg or 0.0, reverse=True)
    return results[:limit]


class CustomTarget(BaseModel):
    name: str
    common_name: str = ""
    ra: float
    dec: float
    type: str = "star"
    tracking: str = "sidereal"
    magnitude: float | None = None


@router.get("/stars", response_model=list[CustomTarget])
def catalog_stars() -> list[CustomTarget]:
    """Return custom targets from stars.cfg (TOML format)."""
    if not _STARS_CFG.exists():
        return []
    with _STARS_CFG.open("rb") as fh:
        data = tomllib.load(fh)
    return [CustomTarget(**t) for t in data.get("targets", [])]


# ── /visible — full-night visibility windows ──────────────────────────────────


class VisibleEntry(BaseModel):
    name: str
    common_name: str
    ra_hours: float
    dec_deg: float
    object_type: str
    magnitude: float
    rises_at: str | None = None
    sets_at: str | None = None
    peak_altitude: float
    peak_time: str | None = None
    is_observable: bool
    solar_safe: bool


@router.get("/visible", response_model=list[VisibleEntry])
def catalog_visible(
    lat: float | None = Query(default=None, ge=-90.0, le=90.0),
    lon: float | None = Query(default=None, ge=-180.0, le=180.0),
    hours: float = Query(default=10.0, ge=1.0, le=24.0),
    min_altitude: float = Query(default=20.0, ge=0.0, le=90.0),
    object_type: str | None = Query(default=None, description="Comma-separated types, e.g. GC,SG"),
    max_magnitude: float | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=110),
) -> list[VisibleEntry]:
    """Return Messier objects whose peak altitude exceeds *min_altitude* within the
    next *hours* hours, sorted highest-first. Rise/set/peak times are UTC ISO8601."""
    obs_lat = lat if lat is not None else config.OBSERVER_LAT
    obs_lon = lon if lon is not None else config.OBSERVER_LON

    now       = datetime.now(UTC)
    night_end = now + timedelta(hours=hours)

    type_filter = (
        {t.strip().upper() for t in object_type.split(",")} if object_type else None
    )

    results: list[VisibleEntry] = []
    for obj in get_all():
        if type_filter and obj.object_type not in type_filter:
            continue
        if max_magnitude is not None and obj.magnitude > max_magnitude:
            continue
        window = compute_visibility_window(
            obj.ra_hours, obj.dec_deg,
            obs_lat, obs_lon,
            now, night_end,
            min_altitude_deg=min_altitude,
            sample_minutes=15,
        )
        if not window.is_observable:
            continue
        blocked, _ = is_solar_target(obj.ra_hours, obj.dec_deg)
        results.append(VisibleEntry(
            name=obj.name,
            common_name=obj.common_name,
            ra_hours=obj.ra_hours,
            dec_deg=obj.dec_deg,
            object_type=obj.object_type,
            magnitude=obj.magnitude,
            rises_at=window.rises_at.isoformat() if window.rises_at else None,
            sets_at=window.sets_at.isoformat() if window.sets_at else None,
            peak_altitude=round(window.peak_altitude, 1),
            peak_time=window.peak_time.isoformat() if window.peak_time else None,
            is_observable=True,
            solar_safe=not blocked,
        ))

    results.sort(key=lambda e: e.peak_altitude, reverse=True)
    return results[:limit]
