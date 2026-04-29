"""System health dashboard — GET /api/status."""

from __future__ import annotations

import os
import shutil

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..adapters.astap.solver import find_astap as _find_astap
from ..adapters.astap.solver import find_catalog as _find_catalog
from ..ports.mount import MountPort
from . import deps
from .session import get_active_runner, get_session_running

router = APIRouter()


class MountHealth(BaseModel):
    ok: bool
    state: str | None = None
    message: str | None = None


class DeviceHealth(BaseModel):
    ok: bool
    message: str | None = None


class SolverHealth(BaseModel):
    ok: bool
    astap_found: bool
    catalog_found: bool


class StorageHealth(BaseModel):
    ok: bool
    free_gb: float | None = None
    path: str | None = None
    message: str | None = None


class SessionHealth(BaseModel):
    running: bool
    state: str | None = None
    session_id: str | None = None


class SystemHealth(BaseModel):
    mount: MountHealth
    camera: DeviceHealth
    focuser: DeviceHealth
    solver: SolverHealth
    storage: StorageHealth
    session: SessionHealth


@router.get("/api/status", response_model=SystemHealth)
def system_status(
    mount: MountPort = Depends(deps.get_mount),
) -> SystemHealth:
    """Return the health of every subsystem. Always 200."""
    # ── Mount ────────────────────────────────────────────────────────────────
    try:
        state = mount.get_state()
        mount_health = MountHealth(ok=True, state=state.name)
    except Exception as exc:
        mount_health = MountHealth(ok=False, message=str(exc))

    # ── Camera / Focuser — no lightweight probe in the port; report available ─
    camera_health  = DeviceHealth(ok=True, message="adapter available")
    focuser_health = DeviceHealth(ok=True, message="adapter available")

    # ── Solver ───────────────────────────────────────────────────────────────
    astap_path = _find_astap()
    catalog    = _find_catalog(astap_path) if astap_path else None
    solver_health = SolverHealth(
        ok=astap_path is not None and catalog is not None,
        astap_found=astap_path is not None,
        catalog_found=catalog is not None,
    )

    # ── Storage ──────────────────────────────────────────────────────────────
    storage_dir = os.environ.get("STORAGE_DIR", "")
    if storage_dir:
        try:
            usage    = shutil.disk_usage(storage_dir)
            free_gb  = round(usage.free / (1024 ** 3), 2)
            storage_health = StorageHealth(ok=True, free_gb=free_gb, path=storage_dir)
        except Exception as exc:
            storage_health = StorageHealth(ok=False, path=storage_dir, message=str(exc))
    else:
        storage_health = StorageHealth(ok=True)

    # ── Session ──────────────────────────────────────────────────────────────
    running = get_session_running()
    runner  = get_active_runner()
    log     = runner.current_log if runner is not None else None
    session_health = SessionHealth(
        running=running,
        state=log.state.name if log is not None else None,
        session_id=log.session_id if log is not None else None,
    )

    return SystemHealth(
        mount=mount_health,
        camera=camera_health,
        focuser=focuser_health,
        solver=solver_health,
        storage=storage_health,
        session=session_health,
    )
