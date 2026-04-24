"""Session lifecycle API — POST /api/session/connect."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..adapters.astap.solver import find_astap as _find_astap
from ..adapters.astap.solver import find_g17_catalog as _find_catalog
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from . import deps

router = APIRouter(prefix="/api/session")

_ACTIONS: dict[str, str] = {
    "camera": "Check USB connection and power; ensure ToupTek driver is installed",
    "mount": "Check serial connection and OnStep power; verify ONSTEP_PORT env var",
    "focuser": "Check focuser serial connection and power",
}

_ASTAP_INSTALL_URL = "https://www.hnsky.org/astap.htm"


class DeviceResult(BaseModel):
    status: str           # "ok" or "error"
    error: str | None = None
    action: str | None = None


class ConnectResult(BaseModel):
    camera: DeviceResult
    mount: DeviceResult
    focuser: DeviceResult
    solver: DeviceResult


def _try_connect(device: str, connect_fn: object) -> DeviceResult:
    try:
        ok: bool = connect_fn()  # type: ignore[operator]
        if ok:
            return DeviceResult(status="ok")
        return DeviceResult(
            status="error",
            error=f"{device.capitalize()} refused connection",
            action=_ACTIONS[device],
        )
    except Exception as exc:
        return DeviceResult(
            status="error",
            error=str(exc),
            action=_ACTIONS[device],
        )


def _check_solver() -> DeviceResult:
    astap = _find_astap()
    if astap is None:
        return DeviceResult(
            status="error",
            error="ASTAP executable not found",
            action=f"Install ASTAP from {_ASTAP_INSTALL_URL}",
        )
    catalog = _find_catalog(astap)
    if catalog is None:
        return DeviceResult(
            status="error",
            error="G17 star catalog not found",
            action=f"Download the G17 catalog from {_ASTAP_INSTALL_URL}",
        )
    return DeviceResult(status="ok")


@router.post("/connect", response_model=ConnectResult)
def session_connect(
    camera: CameraPort = Depends(deps.get_camera),
    mount: MountPort = Depends(deps.get_mount),
    focuser: FocuserPort = Depends(deps.get_focuser),
) -> ConnectResult:
    return ConnectResult(
        camera=_try_connect("camera", camera.connect),
        mount=_try_connect("mount", mount.connect),
        focuser=_try_connect("focuser", focuser.connect),
        solver=_check_solver(),
    )
