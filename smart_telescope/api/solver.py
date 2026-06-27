"""Solver API — GET /api/solver/status, POST /api/solver/solve."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import config
from ..adapters.astap.solver import find_astap as _find_astap
from ..adapters.astap.solver import find_catalog as _find_catalog
from ..ports.solver import SolverPort
from ..services.plate_solve_readiness import check_plate_solve_readiness
from . import deps as _deps
from .deps import get_preview_camera, get_solver, resolve_camera_index

router = APIRouter(prefix="/api/solver")


class SolverStatus(BaseModel):
    astap: str | None     # path to executable, None if not found
    catalog: str | None   # path to catalog directory, None if not found
    ready: bool           # True only when both astap and catalog are present


class SolveRequest(BaseModel):
    exposure:     float = Field(default=5.0, gt=0.0, le=60.0)
    gain:         int   = Field(default=100, ge=100, le=3200)
    camera_index: int   = Field(default=0, ge=0, le=7)
    camera_role:  str | None = Field(default=None)
    pixel_scale:  float | None = Field(default=None, gt=0.0)


class SolveResponse(BaseModel):
    success:      bool
    ra:           float = 0.0   # hours
    dec:          float = 0.0   # degrees
    pa:           float = 0.0   # position angle, degrees
    solve_time_s: float = 0.0
    error:        str | None = None


@router.get("/readiness")
def solver_readiness(
    camera_role: str | None = None,
) -> dict:
    """Evaluate all 8 plate-solve readiness conditions (M8-020 / REQ-PS-001).

    Returns ready=True only when all conditions are satisfied.
    Each unsatisfied condition includes a specific failure reason.
    """
    astap   = _find_astap()
    catalog = _find_catalog(astap)

    # Resolve optional optical train metadata
    optical_train_name: str | None = None
    pixel_scale_arcsec: float | None = config.PIXEL_SCALE_ARCSEC or None
    focal_length_mm: float | None = None
    try:
        registry = _deps.get_optical_train_registry()
        if registry is not None:
            if camera_role:
                train = registry.by_camera_role(camera_role)
            else:
                train = registry.main()
            if train is not None:
                optical_train_name = train.name
                pixel_scale_arcsec = getattr(train, "pixel_scale_arcsec", None) or pixel_scale_arcsec
                focal_length_mm    = getattr(train, "focal_length_mm", None)
    except Exception:
        pass

    result = check_plate_solve_readiness(
        optical_train_name=optical_train_name,
        pixel_scale_arcsec=pixel_scale_arcsec,
        focal_length_mm=focal_length_mm,
        astap_found=astap is not None,
        catalog_found=catalog is not None,
        gate_allows=True,  # gate check requires device_state; always True for static query
        section_logger=_deps.get_section_logger(),
    )
    return result.to_dict()


@router.get("/status", response_model=SolverStatus)
def solver_status() -> SolverStatus:
    astap = _find_astap()
    catalog: Path | None = _find_catalog(astap)
    return SolverStatus(
        astap=astap,
        catalog=str(catalog) if catalog is not None else None,
        ready=astap is not None and catalog is not None,
    )


@router.post("/solve", response_model=SolveResponse)
async def solver_solve(
    body:   SolveRequest,
    solver: SolverPort = Depends(get_solver),
) -> SolveResponse:
    """Capture one frame and plate-solve it, returning RA/Dec/PA."""
    camera = get_preview_camera(resolve_camera_index(body.camera_index, body.camera_role))
    if hasattr(camera, "set_gain"):
        camera.set_gain(body.gain)  # type: ignore[union-attr]
    scale = body.pixel_scale if body.pixel_scale is not None else config.PIXEL_SCALE_ARCSEC

    _deps.get_user_action_logger().log("plate_solve_requested", result="ok")
    t0 = time.perf_counter()
    frame  = await asyncio.to_thread(camera.capture, body.exposure)
    result = await asyncio.to_thread(solver.solve, frame, scale)
    elapsed = round(time.perf_counter() - t0, 2)

    return SolveResponse(
        success=result.success,
        ra=result.ra,
        dec=result.dec,
        pa=result.pa,
        solve_time_s=elapsed,
        error=result.error,
    )
