"""Mount control API — GET status, POST unpark/track/stop/goto."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..domain.solar import is_solar_target
from ..ports.mount import MountPort, MountState
from . import deps

router = APIRouter(prefix="/api/mount")


class MountStatus(BaseModel):
    state: str
    ra: float | None
    dec: float | None


class GotoRequest(BaseModel):
    ra: float
    dec: float


@router.get("/status", response_model=MountStatus)
def mount_status(mount: MountPort = Depends(deps.get_mount)) -> MountStatus:
    state = mount.get_state()
    pos = None
    if state not in (MountState.PARKED, MountState.UNKNOWN):
        with contextlib.suppress(Exception):
            pos = mount.get_position()
    return MountStatus(
        state=state.name.lower(),
        ra=pos.ra if pos else None,
        dec=pos.dec if pos else None,
    )


@router.post("/unpark")
def mount_unpark(mount: MountPort = Depends(deps.get_mount)) -> dict[str, bool]:
    ok = mount.unpark()
    if not ok:
        raise HTTPException(status_code=500, detail="Unpark failed")
    return {"ok": True}


@router.post("/track")
def mount_track(mount: MountPort = Depends(deps.get_mount)) -> dict[str, bool]:
    ok = mount.enable_tracking()
    if not ok:
        raise HTTPException(status_code=500, detail="Enable tracking failed")
    return {"ok": True}


@router.post("/stop")
def mount_stop(mount: MountPort = Depends(deps.get_mount)) -> dict[str, bool]:
    mount.stop()
    return {"ok": True}


@router.post("/goto")
def mount_goto(
    body: GotoRequest,
    mount: MountPort = Depends(deps.get_mount),
    confirm_solar: bool = Query(default=False),
) -> dict[str, bool]:
    if not confirm_solar:
        blocked, sep = is_solar_target(body.ra, body.dec)
        if blocked:
            raise HTTPException(
                status_code=403,
                detail={"error": "solar_exclusion", "sun_separation_deg": round(sep, 2)},
            )
    ok = mount.goto(body.ra, body.dec)
    if not ok:
        raise HTTPException(status_code=500, detail="GoTo failed")
    return {"ok": True}
