"""Session lifecycle API — POST /api/session/connect, /run, /status, /stop."""

from __future__ import annotations

import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..adapters.astap.solver import find_astap as _find_astap
from ..adapters.astap.solver import find_catalog as _find_catalog
from ..domain.states import SessionState
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..workflow.runner import VerticalSliceRunner
from . import deps

router = APIRouter(prefix="/api/session")

# ── Session runner state ─────────────────────────────────────────────────────

_session_lock = threading.Lock()
_active_runner: VerticalSliceRunner | None = None
_runner_thread: threading.Thread | None = None


def _reset_session() -> None:
    global _active_runner, _runner_thread
    with _session_lock:
        _active_runner = None
        _runner_thread = None

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
            error="ASTAP star catalog not found",
            action=f"Download the D80 catalog from {_ASTAP_INSTALL_URL} and extract .290 files to ~/.astap/",
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


# ── Run / Status / Stop ──────────────────────────────────────────────────────


class RunResponse(BaseModel):
    session_id: str
    state: str


class SessionStatusResponse(BaseModel):
    running: bool
    session_id: str | None = None
    state: str | None = None
    frames_integrated: int = 0
    frames_rejected: int = 0
    centering_offset_arcmin: float = 0.0
    warnings: list[str] = []
    failure_stage: str | None = None
    failure_reason: str | None = None
    saved_image_path: str | None = None


@router.post("/run", response_model=RunResponse, status_code=202)
def session_run(
    camera: CameraPort = Depends(deps.get_camera),
    mount: MountPort = Depends(deps.get_mount),
    focuser: FocuserPort = Depends(deps.get_focuser),
) -> RunResponse:
    global _active_runner, _runner_thread
    with _session_lock:
        if _runner_thread is not None and _runner_thread.is_alive():
            raise HTTPException(status_code=409, detail="Session already running")
        session_id = str(uuid.uuid4())
        runner = VerticalSliceRunner(
            camera=camera,
            mount=mount,
            solver=deps.get_solver(),
            stacker=deps.get_stacker(),
            storage=deps.get_storage(),
            focuser=focuser,
        )
        _active_runner = runner
        _runner_thread = threading.Thread(
            target=runner.run, kwargs={"session_id": session_id}, daemon=True,
        )
        _runner_thread.start()
    return RunResponse(session_id=session_id, state=SessionState.IDLE.name)


@router.get("/status", response_model=SessionStatusResponse)
def session_status() -> SessionStatusResponse:
    runner = _active_runner
    thread = _runner_thread
    running = thread is not None and thread.is_alive()
    if runner is None:
        return SessionStatusResponse(running=False)
    log = runner.current_log
    if log is None:
        return SessionStatusResponse(running=running)
    return SessionStatusResponse(
        running=running,
        session_id=log.session_id,
        state=log.state.name,
        frames_integrated=log.frames_integrated,
        frames_rejected=log.frames_rejected,
        centering_offset_arcmin=log.centering_offset_arcmin,
        warnings=list(log.warnings),
        failure_stage=log.failure_stage,
        failure_reason=log.failure_reason,
        saved_image_path=log.saved_image_path,
    )


@router.post("/stop", status_code=204)
def session_stop() -> None:
    runner = _active_runner
    if runner is None:
        raise HTTPException(status_code=404, detail="No active session")
    runner.stop()
