"""Focuser control API — GET status, POST move/nudge/stop/autofocus/connect."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..domain.autofocus import AutofocusParams
from ..ports.focuser import FocuserPort
from ..services.hardware_coordinator import CommandConflictError, HardwareCommandCoordinator
from ..workflow.autofocus import run_autofocus
from . import deps

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/focuser")


class FocuserStatus(BaseModel):
    position: int
    moving: bool
    available: bool
    max_position: int | None


class MoveRequest(BaseModel):
    position: int


class NudgeRequest(BaseModel):
    delta: int


@router.post("/connect")
def focuser_connect(focuser: FocuserPort = Depends(deps.get_focuser)) -> dict[str, object]:
    focuser.connect()
    return {"ok": True, "available": focuser.is_available}


@router.get("/status", response_model=FocuserStatus)
def focuser_status(focuser: FocuserPort = Depends(deps.get_focuser)) -> FocuserStatus:
    available = focuser.is_available
    return FocuserStatus(
        position=focuser.get_position() if available else 0,
        moving=focuser.is_moving() if available else False,
        available=available,
        max_position=focuser.get_max_position() if available else None,
    )


def _safe_move(
    focuser: FocuserPort,
    coordinator: HardwareCommandCoordinator,
    target: int,
) -> bool:
    """Issue a move command only when the focuser is confirmed idle.

    Returns True when the focuser motor has confirmed started moving within
    ~300 ms of the command.  Returns False when position and is_moving() are
    both unchanged — likely a wiring or config issue.

    The coordinator lock is held ONLY during command issuance so that rapid
    nudges queue behind the serial exchange (~50-100 ms) rather than the
    started-check sleep (FR-SAFE-FOC-001).  STOP must never call this.
    """
    start_pos = 0
    try:
        with coordinator.focuser_command():
            if focuser.is_moving():
                _log.info("Focuser move rejected: focuser is moving (target=%d)", target)
                raise HTTPException(status_code=409, detail="Focuser is moving — try again shortly")
            start_pos = focuser.get_position()
            focuser.move(target)
            _log.info("Focuser move issued: start=%d target=%d", start_pos, target)
    except CommandConflictError as exc:
        _log.warning("Focuser move: lock conflict (target=%d)", target)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    # Outside the lock: rapid nudges can now proceed without queuing on this sleep
    time.sleep(0.3)
    started = focuser.is_moving() or (focuser.get_position() != start_pos)
    if not started:
        _log.warning(
            "Focuser motor did not start within 300 ms "
            "(start=%d target=%d) — check OnStep focuser wiring",
            start_pos, target,
        )
    return started


@router.post("/move")
def focuser_move(
    body: MoveRequest,
    focuser: FocuserPort = Depends(deps.get_focuser),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
) -> dict[str, bool]:
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")
    max_pos = focuser.get_max_position()
    target = max(0, min(max_pos, body.position)) if max_pos else body.position
    _safe_move(focuser, coordinator, target)
    return {"ok": True}


@router.post("/nudge")
def focuser_nudge(
    body: NudgeRequest,
    focuser: FocuserPort = Depends(deps.get_focuser),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
) -> dict[str, object]:
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")
    current = focuser.get_position()
    max_pos = focuser.get_max_position()
    target  = current + body.delta
    if max_pos:
        target = max(0, min(max_pos, target))
    started = _safe_move(focuser, coordinator, target)
    return {"target": target, "started": started}


@router.post("/stop")
def focuser_stop(focuser: FocuserPort = Depends(deps.get_focuser)) -> dict[str, bool]:
    focuser.stop()
    return {"ok": True}


class AutofocusRequest(BaseModel):
    range_steps:  int   = 1000
    step_size:    int   = 100
    exposure:     float = 2.0
    camera_index: int   = 0


@router.post("/autofocus")
def focuser_autofocus(
    body:        AutofocusRequest,
    focuser:     FocuserPort = Depends(deps.get_focuser),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
) -> dict[str, object]:
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")

    camera = deps.get_preview_camera(body.camera_index)
    try:
        params = AutofocusParams(
            range_steps=body.range_steps,
            step_size=body.step_size,
            exposure=body.exposure,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        with coordinator.focuser_command(timeout=0):
            try:
                result = run_autofocus(focuser, camera, params)
            except RuntimeError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
    except CommandConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Focuser is busy — stop the current move before starting autofocus",
        ) from exc
    return result.to_dict()
