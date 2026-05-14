"""Focuser control API — GET status, POST move/nudge/stop/autofocus/connect."""

from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..domain.autofocus import AutofocusParams
from ..ports.focuser import FocuserPort
from ..workflow.autofocus import run_autofocus
from . import deps

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/focuser")

# ── Move serialisation ────────────────────────────────────────────────────────
# Prevents concurrent move commands from being sent before the focuser
# confirms the previous movement is complete (FR-SAFE-FOC-001).

_move_lock      = threading.Lock()
_MOVE_TIMEOUT_S = 15.0   # max seconds to wait for focuser to stop before issuing a new move


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


def _check_focuser_started(focuser: FocuserPort, start_pos: int, target: int) -> None:
    """Log a warning if the focuser hasn't moved 2 s after a command was sent."""
    time.sleep(2.0)
    try:
        current = focuser.get_position()
        if current == start_pos and not focuser.is_moving():
            _log.warning(
                "Focuser move may not have started: position unchanged after 2 s "
                "(start=%d target=%d current=%d) — check OnStep focuser wiring",
                start_pos, target, current,
            )
        else:
            _log.debug("Focuser moving OK: start=%d current=%d target=%d", start_pos, current, target)
    except Exception:
        pass


def _safe_move(focuser: FocuserPort, target: int) -> None:
    """Issue a move command only when the focuser is confirmed idle.

    Returns 409 immediately if the focuser is currently moving or if another
    move command is already serialised via _move_lock.  Does not block waiting
    for a long in-progress move to finish — the caller (UI nudge) should retry.
    Falls back to a best-effort move after _MOVE_TIMEOUT_S if the focuser
    reports moving for an unusually long time (stop-button safety).
    """
    # Timeout is 3 s (> serial read timeout of 2 s) so that a concurrent mount
    # status poll holding the serial lock doesn't cause a spurious 409.
    if not _move_lock.acquire(blocking=True, timeout=3.0):
        _log.warning("Focuser nudge: lock timeout — another request is already queued (target=%d)", target)
        raise HTTPException(status_code=409, detail="Another focuser move is already queued — try again shortly")

    try:
        if focuser.is_moving():
            _log.info("Focuser nudge rejected: focuser is moving (target=%d)", target)
            raise HTTPException(status_code=409, detail="Focuser is moving — try again shortly")
        start_pos = focuser.get_position()
        focuser.move(target)
        _log.info("Focuser move issued: start=%d target=%d", start_pos, target)
        threading.Thread(
            target=_check_focuser_started,
            args=(focuser, start_pos, target),
            daemon=True,
            name="focuser-move-check",
        ).start()
    finally:
        _move_lock.release()


@router.post("/move")
def focuser_move(
    body: MoveRequest, focuser: FocuserPort = Depends(deps.get_focuser)
) -> dict[str, bool]:
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")
    max_pos = focuser.get_max_position()
    target = max(0, min(max_pos, body.position)) if max_pos else body.position
    _safe_move(focuser, target)
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
    _safe_move(focuser, target)
    return {"target": target}


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
    body:    AutofocusRequest,
    focuser: FocuserPort = Depends(deps.get_focuser),
) -> dict[str, object]:
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")

    camera = deps.get_preview_camera(body.camera_index)
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
