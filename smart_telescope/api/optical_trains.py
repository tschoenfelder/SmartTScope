"""Optical train registry API — GET /api/optical_trains."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..services.optical_train_registry import OpticalTrain, OpticalTrainRegistry
from . import deps

router = APIRouter(prefix="/api/optical_trains", tags=["optical_trains"])


def _train_to_dict(t: OpticalTrain) -> dict:
    return {
        "name": t.name,
        "camera_role": t.camera_role,
        "camera_index": t.camera_index,
        "telescope": t.telescope_name,
        "focal_mm": t.focal_mm,
        "reducer_factor": t.reducer_factor,
        "pixel_scale_arcsec": t.pixel_scale_arcsec,
        "has_focuser": t.has_focuser,
        "focuser": t.focuser,
    }


@router.get("")
def list_optical_trains(
    registry: OpticalTrainRegistry = Depends(deps.get_optical_train_registry),
) -> list[dict]:
    """Return all configured optical trains ordered by name."""
    return [_train_to_dict(t) for t in sorted(registry.all(), key=lambda t: t.name)]


@router.get("/{name}")
def get_optical_train(
    name: str,
    registry: OpticalTrainRegistry = Depends(deps.get_optical_train_registry),
) -> dict:
    """Return a single optical train by name, or 404 if not configured."""
    from fastapi import HTTPException
    train = registry.get(name)
    if train is None:
        raise HTTPException(status_code=404, detail=f"Optical train '{name}' not configured")
    return _train_to_dict(train)
