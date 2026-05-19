"""Emergency stop — POST /api/emergency_stop.

Halts all mount motion and cancels any running session immediately.
Always returns 200 so the client can confirm the stop was received
even if one subsystem was already idle.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from . import deps
from .session import get_active_runner

router = APIRouter()
logger = logging.getLogger(__name__)


class EmergencyStopResponse(BaseModel):
    mount_stopped: bool
    focuser_stopped: bool
    session_stopped: bool


@router.post("/api/emergency_stop", response_model=EmergencyStopResponse)
def emergency_stop(
    mount: MountPort = Depends(deps.get_mount),
    focuser: FocuserPort = Depends(deps.get_focuser),
) -> EmergencyStopResponse:
    """Immediate halt: stop mount and focuser motion; cancel any active session.

    Always returns 200.  Stop commands bypass API-level locks so they are sent
    even when a move command is in progress.
    """
    mount_stopped = False
    try:
        mount.stop()
        mount_stopped = True
    except Exception as exc:
        logger.error("Emergency stop: mount.stop() raised %s", exc)

    focuser_stopped = False
    try:
        focuser.stop()
        focuser_stopped = True
    except Exception as exc:
        logger.error("Emergency stop: focuser.stop() raised %s", exc)

    session_stopped = False
    runner = get_active_runner()
    if runner is not None:
        try:
            runner.stop()
            session_stopped = True
        except Exception as exc:
            logger.error("Emergency stop: runner.stop() raised %s", exc)

    logger.warning(
        "Emergency stop: mount=%s focuser=%s session=%s",
        mount_stopped, focuser_stopped, session_stopped,
    )
    return EmergencyStopResponse(
        mount_stopped=mount_stopped,
        focuser_stopped=focuser_stopped,
        session_stopped=session_stopped,
    )
