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
from .deps import get_preview_camera, get_solver

router = APIRouter(prefix="/api/solver")


class SolverStatus(BaseModel):
    astap: str | None     # path to executable, None if not found
    catalog: str | None   # path to catalog directory, None if not found
    ready: bool           # True only when both astap and catalog are present


class SolveRequest(BaseModel):
    exposure:     float = Field(default=5.0, gt=0.0, le=60.0)
    gain:         int   = Field(default=100, ge=100, le=3200)
    camera_index: int   = Field(default=0, ge=0, le=7)
    pixel_scale:  float | None = Field(default=None, gt=0.0)


class SolveResponse(BaseModel):
    success:      bool
    ra:           float = 0.0   # hours
    dec:          float = 0.0   # degrees
    pa:           float = 0.0   # position angle, degrees
    solve_time_s: float = 0.0
    error:        str | None = None


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
    camera = get_preview_camera(body.camera_index)
    if hasattr(camera, "set_gain"):
        camera.set_gain(body.gain)  # type: ignore[union-attr]
    scale = body.pixel_scale if body.pixel_scale is not None else config.PIXEL_SCALE_ARCSEC

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
