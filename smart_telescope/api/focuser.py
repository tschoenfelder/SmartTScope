"""Focuser control API — GET status, POST move/nudge/stop."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..ports.focuser import FocuserPort
from . import deps

router = APIRouter(prefix="/api/focuser")


class FocuserStatus(BaseModel):
    position: int
    moving: bool


class MoveRequest(BaseModel):
    position: int


class NudgeRequest(BaseModel):
    delta: int


@router.get("/status", response_model=FocuserStatus)
def focuser_status(focuser: FocuserPort = Depends(deps.get_focuser)) -> FocuserStatus:
    return FocuserStatus(
        position=focuser.get_position(),
        moving=focuser.is_moving(),
    )


@router.post("/move")
def focuser_move(
    body: MoveRequest, focuser: FocuserPort = Depends(deps.get_focuser)
) -> dict[str, bool]:
    focuser.move(body.position)
    return {"ok": True}


@router.post("/nudge")
def focuser_nudge(
    body: NudgeRequest, focuser: FocuserPort = Depends(deps.get_focuser)
) -> dict[str, int]:
    current = focuser.get_position()
    target = current + body.delta
    focuser.move(target)
    return {"target": target}


@router.post("/stop")
def focuser_stop(focuser: FocuserPort = Depends(deps.get_focuser)) -> dict[str, bool]:
    focuser.stop()
    return {"ok": True}
