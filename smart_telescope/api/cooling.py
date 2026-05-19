"""Cooling control API — POST /api/cooling/set_target, GET /api/cooling/status.

R6-002: This module is now a thin wrapper — validate request, call
CoolingService, map response.  All session/threading logic lives in
smart_telescope/services/cooling.py.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.cooling import CoolingAction
from . import deps

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cooling")


# ── Request / Response models ─────────────────────────────────────────────────

class SetTargetRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    target_c: float = Field(default=-10.0, ge=-10.0, le=10.0)
    enabled: bool = True


class SetTargetResponse(BaseModel):
    ok: bool
    target_c: float
    message: str | None = None


class CoolingStatusResponse(BaseModel):
    enabled: bool
    camera_index: int | None = None
    current_temp_c: float | None = None
    target_c: float | None = None
    power_pct: float | None = None
    stable: bool = False
    action: str | None = None
    warning_msg: str | None = None
    seconds_remaining: float | None = None


# ── Validation helper ─────────────────────────────────────────────────────────

def _camera_has_tec(camera: object) -> bool:
    return (
        hasattr(camera, "set_tec_enabled")
        and hasattr(camera, "set_tec_target_c")
        and hasattr(camera, "get_tec_power_pct")
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/set_target", response_model=SetTargetResponse)
def set_target(req: SetTargetRequest) -> SetTargetResponse:
    """Start, reconfigure, or stop TEC cooling on a camera.

    When *enabled* is False, cooling is disabled and the TEC is turned off.
    """
    svc = deps.get_cooling_service()

    if not req.enabled:
        svc.stop()
        _log.info("Cooling disabled by request")
        return SetTargetResponse(ok=True, target_c=req.target_c, message="Cooling disabled")

    try:
        camera = deps.get_preview_camera(req.camera_index)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not _camera_has_tec(camera):
        raise HTTPException(
            status_code=409,
            detail=f"Camera at index {req.camera_index} does not support TEC cooling",
        )

    svc.start(camera, req.camera_index, req.target_c)
    return SetTargetResponse(ok=True, target_c=req.target_c)


@router.get("/status", response_model=CoolingStatusResponse)
def get_status() -> CoolingStatusResponse:
    """Return the current cooling state.  Always 200; *enabled* is False when inactive."""
    status = deps.get_cooling_service().get_status()
    return CoolingStatusResponse(
        enabled=status.enabled,
        camera_index=status.camera_index,
        current_temp_c=status.current_temp_c,
        target_c=status.target_c,
        power_pct=round(status.power_pct, 1) if status.enabled else None,
        stable=status.stable,
        action=status.action.name if status.action is not None else None,
        warning_msg=status.warning_msg,
        seconds_remaining=round(status.seconds_remaining, 0) if status.enabled else None,
    )


def _reset() -> None:
    """Stop cooling and clear state (used by tests)."""
    deps.get_cooling_service().stop()
