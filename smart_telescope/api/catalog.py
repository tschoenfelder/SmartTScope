"""Catalog search API — GET /api/catalog/search, GET /api/catalog/objects."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..domain.catalog import CatalogObject, get_all, search

router = APIRouter(prefix="/api/catalog")


class CatalogEntry(BaseModel):
    name: str
    common_name: str
    ra_hours: float
    dec_deg: float
    object_type: str
    magnitude: float

    @classmethod
    def from_domain(cls, obj: CatalogObject) -> "CatalogEntry":
        return cls(
            name=obj.name,
            common_name=obj.common_name,
            ra_hours=obj.ra_hours,
            dec_deg=obj.dec_deg,
            object_type=obj.object_type,
            magnitude=obj.magnitude,
        )


@router.get("/search", response_model=list[CatalogEntry])
def catalog_search(
    q: str = Query(min_length=1, max_length=64),
    limit: int = Query(default=10, ge=1, le=50),
) -> list[CatalogEntry]:
    return [CatalogEntry.from_domain(obj) for obj in search(q, limit=limit)]


@router.get("/objects", response_model=list[CatalogEntry])
def catalog_objects() -> list[CatalogEntry]:
    return [CatalogEntry.from_domain(obj) for obj in get_all()]
