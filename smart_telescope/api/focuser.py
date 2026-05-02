"""Focuser control API — GET status, POST move/nudge/stop/autofocus/connect."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..domain.autofocus import AutofocusParams
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..workflow.autofocus import run_autofocus
from . import deps

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


@router.post("/move")
def focuser_move(
    body: MoveRequest, focuser: FocuserPort = Depends(deps.get_focuser)
) -> dict[str, bool]:
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")
    max_pos = focuser.get_max_position()
    target = max(0, min(max_pos, body.position)) if max_pos else body.position
    focuser.move(target)
    return {"ok": True}


@router.post("/nudge")
def focuser_nudge(
    body: NudgeRequest, focuser: FocuserPort = Depends(deps.get_focuser)
) -> dict[str, int]:
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")
    current = focuser.get_position()
    max_pos = focuser.get_max_position()
    target = current + body.delta
    if max_pos:
        target = max(0, min(max_pos, target))
    focuser.move(target)
    return {"target": target}


@router.post("/stop")
def focuser_stop(focuser: FocuserPort = Depends(deps.get_focuser)) -> dict[str, bool]:
    focuser.stop()
    return {"ok": True}


class AutofocusRequest(BaseModel):
    range_steps: int   = 1000  # total sweep width in focuser steps
    step_size:   int   = 100   # step between samples
    exposure:    float = 2.0   # seconds per frame


@router.post("/autofocus")
def focuser_autofocus(
    body:    AutofocusRequest,
    focuser: FocuserPort = Depends(deps.get_focuser),
    camera:  CameraPort  = Depends(deps.get_camera),
) -> dict[str, object]:
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")

    try:
        params = AutofocusParams(
            range_steps = body.range_steps,
            step_size   = body.step_size,
            exposure    = body.exposure,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        result = run_autofocus(focuser, camera, params)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return result.to_dict()
