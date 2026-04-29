"""Emergency stop — POST /api/emergency_stop.

Halts all mount motion and cancels any running session immediately.
Always returns 200 so the client can confirm the stop was received
even if one subsystem was already idle.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..ports.mount import MountPort
from . import deps
from .session import get_active_runner

router = APIRouter()
logger = logging.getLogger(__name__)


class EmergencyStopResponse(BaseModel):
    mount_stopped: bool
    session_stopped: bool


@router.post("/api/emergency_stop", response_model=EmergencyStopResponse)
def emergency_stop(
    mount: MountPort = Depends(deps.get_mount),
) -> EmergencyStopResponse:
    """Immediate halt: stop mount motion and cancel any active session."""
    mount_stopped = False
    try:
        mount.stop()
        mount_stopped = True
    except Exception as exc:
        logger.error("Emergency stop: mount.stop() raised %s", exc)

    session_stopped = False
    runner = get_active_runner()
    if runner is not None:
        try:
            runner.stop()
            session_stopped = True
        except Exception as exc:
            logger.error("Emergency stop: runner.stop() raised %s", exc)

    return EmergencyStopResponse(mount_stopped=mount_stopped, session_stopped=session_stopped)
