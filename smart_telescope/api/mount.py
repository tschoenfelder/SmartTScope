"""Mount control API — GET status, POST unpark/track/stop/goto/park/goto_sky."""

from __future__ import annotations

import contextlib

from astropy.coordinates import EarthLocation
from astropy.time import Time
import astropy.units as u
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from .. import config
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


class SyncRequest(BaseModel):
    ra: float
    dec: float


@router.post("/sync")
def mount_sync(
    body: SyncRequest,
    mount: MountPort = Depends(deps.get_mount),
) -> dict[str, bool]:
    """Tell the mount it is currently pointing at the given RA/Dec."""
    ok = mount.sync(body.ra, body.dec)
    if not ok:
        raise HTTPException(status_code=500, detail="Mount sync failed")
    return {"ok": True}


@router.post("/park")
def mount_park(mount: MountPort = Depends(deps.get_mount)) -> dict[str, bool]:
    ok = mount.park()
    if not ok:
        raise HTTPException(status_code=500, detail="Park failed")
    return {"ok": True}


@router.post("/disable_tracking")
def mount_disable_tracking(mount: MountPort = Depends(deps.get_mount)) -> dict[str, bool]:
    ok = mount.disable_tracking()
    if not ok:
        raise HTTPException(status_code=500, detail="Disable tracking failed")
    return {"ok": True}


class SkyPosition(BaseModel):
    ra: float
    dec: float
    elevation_deg: float
    lst_hours: float


@router.post("/goto_sky", response_model=SkyPosition)
def mount_goto_sky(
    elevation: float = Query(default=80.0, ge=60.0, le=89.0),
    mount: MountPort = Depends(deps.get_mount),
) -> SkyPosition:
    """Slew to the local meridian at the requested elevation.

    Uses the configured observer location (OBSERVER_LAT / OBSERVER_LON) and
    the current UTC time to compute RA = LST, Dec = lat − (90° − elevation).
    Auto-unparks the mount if it is currently parked.
    """
    if mount.get_state() == MountState.PARKED:
        if not mount.unpark():
            raise HTTPException(status_code=500, detail="Auto-unpark before sky slew failed")

    loc = EarthLocation(lat=config.OBSERVER_LAT * u.deg, lon=config.OBSERVER_LON * u.deg)
    lst_hours: float = Time.now().sidereal_time("apparent", longitude=loc.lon).hour
    dec_deg: float = config.OBSERVER_LAT - (90.0 - elevation)
    ra_hours: float = lst_hours

    blocked, sep = is_solar_target(ra_hours, dec_deg)
    if blocked:
        raise HTTPException(
            status_code=403,
            detail={"error": "solar_exclusion", "sun_separation_deg": round(sep, 2)},
        )

    ok = mount.goto(ra_hours, dec_deg)
    if not ok:
        raise HTTPException(status_code=500, detail="GoTo sky failed")
    return SkyPosition(ra=ra_hours, dec=dec_deg, elevation_deg=elevation, lst_hours=lst_hours)
