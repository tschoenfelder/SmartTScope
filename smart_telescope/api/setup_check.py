"""Extended setup check API — exercises hardware beyond static readiness checks.

Endpoints:
  POST /api/setup/focuser_move   — move focuser ±100 steps, verify position change
  POST /api/setup/mount_slew    — GoTo +5° Dec, wait for TRACKING, verify
  POST /api/setup/plate_solve   — capture + ASTAP solve for each optical train
  POST /api/setup/home_return   — issue home command, wait for completion
  POST /api/setup/run_all       — run all four steps in sequence
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..ports.solver import SolverPort
from ..services.device_state import DeviceStateService
from ..services.hardware_coordinator import HardwareCommandCoordinator
from ..services.optical_train_registry import OpticalTrainRegistry
from ..services.setup_check_service import (
    run_focuser_move,
    run_home_return,
    run_mount_slew,
    run_plate_solve,
)
from . import deps

router = APIRouter(prefix="/api/setup")


class FocuserMoveRequest(BaseModel):
    steps: int = 100


class MountSlewRequest(BaseModel):
    offset_dec_deg: float = 5.0
    timeout_s: float = 40.0


class PlateSolveRequest(BaseModel):
    exposure_s: float = 3.0
    timeout_s: float = 15.0


class HomeReturnRequest(BaseModel):
    timeout_s: float = 90.0


@router.post("/focuser_move")
def check_focuser_move(
    body: FocuserMoveRequest = FocuserMoveRequest(),
    focuser: FocuserPort = Depends(deps.get_focuser),
) -> dict[str, Any]:
    """Move focuser by *steps*, verify position changed, then restore."""
    result = run_focuser_move(focuser, steps=body.steps)
    return result.to_dict()


@router.post("/mount_slew")
def check_mount_slew(
    body: MountSlewRequest = MountSlewRequest(),
    mount: MountPort = Depends(deps.get_mount),
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> dict[str, Any]:
    """GoTo (current RA, current Dec + offset_dec_deg), verify slew completes."""
    result = run_mount_slew(mount, device_state,
                              offset_dec_deg=body.offset_dec_deg,
                              timeout_s=body.timeout_s)
    return result.to_dict()


@router.post("/plate_solve")
def check_plate_solve(
    body: PlateSolveRequest = PlateSolveRequest(),
    registry: OpticalTrainRegistry = Depends(deps.get_optical_train_registry),
    solver: SolverPort = Depends(deps.get_solver),
) -> dict[str, Any]:
    """Capture from each optical train and attempt a plate solve."""
    rt = deps.get_runtime()
    result = run_plate_solve(registry, rt, solver,
                               exposure_s=body.exposure_s,
                               timeout_s=body.timeout_s)
    return result.to_dict()


@router.post("/home_return")
def check_home_return(
    body: HomeReturnRequest = HomeReturnRequest(),
    mount: MountPort = Depends(deps.get_mount),
    device_state: DeviceStateService = Depends(deps.get_device_state),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
) -> dict[str, Any]:
    """Slew mount to OnStep stored home position and wait for completion."""
    result = run_home_return(mount, device_state, coordinator, timeout_s=body.timeout_s)
    return result.to_dict()


@router.post("/run_all")
def check_run_all(
    focuser: FocuserPort = Depends(deps.get_focuser),
    mount: MountPort = Depends(deps.get_mount),
    device_state: DeviceStateService = Depends(deps.get_device_state),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
    registry: OpticalTrainRegistry = Depends(deps.get_optical_train_registry),
    solver: SolverPort = Depends(deps.get_solver),
) -> dict[str, Any]:
    """Run all four extended setup checks in sequence."""
    rt = deps.get_runtime()

    focuser_result = run_focuser_move(focuser)
    slew_result    = run_mount_slew(mount, device_state)
    solve_result   = run_plate_solve(registry, rt, solver)
    home_result    = run_home_return(mount, device_state, coordinator)

    steps = {
        "focuser_move":  focuser_result.to_dict(),
        "mount_slew":    slew_result.to_dict(),
        "plate_solve":   solve_result.to_dict(),
        "home_return":   home_result.to_dict(),
    }
    passed = sum(1 for s in steps.values() if s["ok"])
    return {"steps": steps, "passed": passed, "total": len(steps)}
