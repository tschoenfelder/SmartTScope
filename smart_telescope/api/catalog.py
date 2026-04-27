"""Catalog search API — GET /api/catalog/search, GET /api/catalog/objects."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from .. import config
from ..domain.catalog import CatalogObject, get_all, search
from ..domain.visibility import compute_altaz

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
