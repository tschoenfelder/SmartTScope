"""Catalog search API — GET /api/catalog/search, /objects, /tonight, /stars."""

from __future__ import annotations

import tomllib
from pathlib import Path

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .. import config
from ..domain.catalog import CatalogObject, get_all, search
from ..domain.solar import is_solar_target
from ..domain.visibility import compute_altaz

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
