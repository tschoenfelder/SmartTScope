"""Guiding API — start/stop/status for the measure-only guide loop."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import get_guiding_service, get_runtime
from ..services.guiding_service import GuidingService

router = APIRouter(prefix="/api/guiding", tags=["guiding"])


class GuidingStartRequest(BaseModel):
    exposure_s: float = 0.5
    cadence_s: float = 0.5
    roles: list[str] = []  # empty = try ["guide", "oag"] from runtime


@router.post("/start", status_code=202)
def guiding_start(
    body: GuidingStartRequest,
    svc: GuidingService = Depends(get_guiding_service),
    rt=Depends(get_runtime),
) -> dict:
    if svc.status().state == "running":
        raise HTTPException(status_code=409, detail="Guiding is already running")

    roles = body.roles or ["guide", "oag"]
    role_cameras: dict = {}
    for role in roles:
        try:
            cam = rt.get_camera_by_role(role)
            role_cameras[role] = cam
        except Exception:
            pass  # role not configured — skip silently

    if not role_cameras:
        raise HTTPException(status_code=422, detail="No guide-capable camera roles are configured")

    mount = getattr(rt, "_mount", None)
    svc.start(role_cameras, exposure_s=body.exposure_s, cadence_s=body.cadence_s, mount=mount)
    return {"state": "starting", "roles": list(role_cameras)}


@router.post("/stop")
def guiding_stop(svc: GuidingService = Depends(get_guiding_service)) -> dict:
    svc.stop()
    return {"state": "idle"}


@router.get("/status")
def guiding_status(svc: GuidingService = Depends(get_guiding_service)) -> dict:
    return svc.status().to_dict()
