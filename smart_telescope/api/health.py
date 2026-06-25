"""System health dashboard — GET /api/status."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..adapters.astap.solver import find_astap as _find_astap
from ..adapters.astap.solver import find_catalog as _find_catalog
from ..domain.mount_readiness import derive_mount_readiness
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..services.device_state import DeviceStateService
from ..services.operation_gate import GateResult, evaluate_all_gates
from . import deps
from .session import get_active_runner, get_session_running

router = APIRouter()

# Estimated float32 FITS frame size for C8 native (2080×3096 px × 4 bytes ≈ 24.6 MB)
_FITS_FRAME_MB = 25.0

_USER_DIR = Path.home() / ".SmartTScope"


@router.get("/api/status/storage")
def storage_paths() -> dict[str, str]:
    """Return absolute paths where session stacks and collimation frames are saved."""
    from .. import config as _cfg
    sessions_dir = (
        Path(os.environ["STORAGE_DIR"])
        if os.environ.get("STORAGE_DIR")
        else _USER_DIR / "sessions"
    )
    try:
        col_cfg = _cfg.get_collimation_config()
        arc_dir_str = col_cfg.archive.archive_dir
        archive_dir = Path(arc_dir_str) if arc_dir_str else _USER_DIR / "frame_archive"
    except Exception:
        archive_dir = _USER_DIR / "frame_archive"
    return {
        "sessions_dir": str(sessions_dir),
        "archive_dir": str(archive_dir),
    }


def _read_cpu_temp() -> float | None:
    try:
        raw = Path("/sys/class/thermal/thermal_zone0/temp").read_text().strip()
        return round(int(raw) / 1000, 1)
    except Exception:
        return None


class MountHealth(BaseModel):
    ok: bool
    state: str | None = None
    message: str | None = None


class DeviceHealth(BaseModel):
    ok: bool
    required: bool = False   # True when the device is mandatory on this hardware config
    message: str | None = None


class SolverHealth(BaseModel):
    ok: bool
    astap_found: bool
    catalog_found: bool
    catalog_path: str | None = None


class StorageHealth(BaseModel):
    ok: bool
    free_gb: float | None = None
    frames_capacity: int | None = None
    path: str | None = None
    message: str | None = None


class SessionHealth(BaseModel):
    running: bool
    state: str | None = None
    session_id: str | None = None


class CpuHealth(BaseModel):
    temp_c: float | None = None


class MountStateCategories(BaseModel):
    """REQ-STATE-001/002 — six state categories + derived readiness."""
    adapter_connection_state: str   # OPEN | CLOSED
    adapter_health_state: str       # OK | FAILED | UNKNOWN
    mount_operational_state: str    # mirrors MountState enum name
    onstep_time_location_state: str # UNKNOWN | VERIFIED | UNVERIFIED
    raspberry_time_trust_state: str # NOT_TRUSTED (stub; full impl in M8-007)
    operation_gate_states: dict[str, dict]  # GateResult per operation (REQ-STATE-003)
    mount_readiness: str                    # derived composite — MountReadinessState.name


class SystemHealth(BaseModel):
    mount: MountHealth
    camera: DeviceHealth
    focuser: DeviceHealth
    solver: SolverHealth
    storage: StorageHealth
    session: SessionHealth
    cpu: CpuHealth
    mount_states: MountStateCategories


def _build_mount_state_categories(device_state: DeviceStateService) -> MountStateCategories:
    started = device_state.is_started()
    observed = device_state.get_mount_state()

    adapter_connection = "OPEN" if started else "CLOSED"

    if observed is None:
        adapter_health = "UNKNOWN"
        operational = "UNKNOWN"
    elif observed.error:
        adapter_health = "FAILED"
        operational = observed.state.name
    else:
        adapter_health = "OK"
        operational = observed.state.name

    tl_status = device_state.get_time_location_status()

    raspberry_trust = "NOT_TRUSTED"  # stub until M8-007
    readiness = derive_mount_readiness(
        adapter_connection=adapter_connection,
        adapter_health=adapter_health,
        onstep_time_location=tl_status.name,
        raspberry_time_trust=raspberry_trust,
    )
    gate_results = evaluate_all_gates(
        adapter_connection=adapter_connection,
        adapter_health=adapter_health,
        mount_operational_state=operational,
        onstep_time_location=tl_status.name,
        raspberry_time_trust=raspberry_trust,
    )
    gate_states = {
        op: {
            "allowed": r.allowed,
            "reason_code": r.reason_code,
            "human_message": r.human_message,
            "required_user_action": r.required_user_action,
            "blocking_states": r.blocking_states,
        }
        for op, r in gate_results.items()
    }

    return MountStateCategories(
        adapter_connection_state=adapter_connection,
        adapter_health_state=adapter_health,
        mount_operational_state=operational,
        onstep_time_location_state=tl_status.name,
        raspberry_time_trust_state=raspberry_trust,
        operation_gate_states=gate_states,
        mount_readiness=readiness.name,
    )


@router.get("/api/status", response_model=SystemHealth)
def system_status(
    mount: MountPort = Depends(deps.get_mount),
    focuser: FocuserPort = Depends(deps.get_focuser),
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> SystemHealth:
    """Return the health of every subsystem. Always 200."""
    # ── Mount ────────────────────────────────────────────────────────────────
    try:
        from ..ports.mount import MountState as _MountState
        state = mount.get_state()
        mount_health = MountHealth(ok=state != _MountState.UNKNOWN, state=state.name)
    except Exception as exc:
        mount_health = MountHealth(ok=False, message=str(exc))

    # ── Camera / Focuser ─────────────────────────────────────────────────────
    camera_health = DeviceHealth(ok=True, message="adapter available")
    onstep_active = bool(os.environ.get("ONSTEP_PORT"))
    if focuser.is_available:
        focuser_health = DeviceHealth(ok=True, required=onstep_active, message="focuser active")
    else:
        focuser_health = DeviceHealth(
            ok=False,
            required=onstep_active,
            message=(
                "Focuser not found — check OnStep focuser wiring and configuration"
                if onstep_active
                else "focuser not found — autofocus disabled"
            ),
        )

    # ── Solver ───────────────────────────────────────────────────────────────
    astap_path = _find_astap()
    catalog    = _find_catalog(astap_path) if astap_path else None
    solver_health = SolverHealth(
        ok=astap_path is not None and catalog is not None,
        astap_found=astap_path is not None,
        catalog_found=catalog is not None,
        catalog_path=str(catalog) if catalog is not None else None,
    )

    # ── Storage ──────────────────────────────────────────────────────────────
    storage_dir = os.environ.get("STORAGE_DIR", "")
    if storage_dir:
        try:
            usage    = shutil.disk_usage(storage_dir)
            free_gb  = round(usage.free / (1024 ** 3), 2)
            capacity = int(free_gb * 1024 / _FITS_FRAME_MB)
            storage_health = StorageHealth(
                ok=True, free_gb=free_gb, frames_capacity=capacity, path=storage_dir
            )
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

    # ── CPU temperature ───────────────────────────────────────────────────────
    cpu_health = CpuHealth(temp_c=_read_cpu_temp())

    return SystemHealth(
        mount=mount_health,
        camera=camera_health,
        focuser=focuser_health,
        solver=solver_health,
        storage=storage_health,
        session=session_health,
        cpu=cpu_health,
        mount_states=_build_mount_state_categories(device_state),
    )
