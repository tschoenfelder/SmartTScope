"""Solver validation API — GET /api/solver/status."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

from ..adapters.astap.solver import find_astap as _find_astap
from ..adapters.astap.solver import find_g17_catalog as _find_catalog

router = APIRouter(prefix="/api/solver")


class SolverStatus(BaseModel):
    astap: str | None     # path to executable, None if not found
    catalog: str | None   # path to catalog directory, None if not found
    ready: bool           # True only when both astap and catalog are present


@router.get("/status", response_model=SolverStatus)
def solver_status() -> SolverStatus:
    astap = _find_astap()
    catalog: Path | None = _find_catalog(astap)
    return SolverStatus(
        astap=astap,
        catalog=str(catalog) if catalog is not None else None,
        ready=astap is not None and catalog is not None,
    )
