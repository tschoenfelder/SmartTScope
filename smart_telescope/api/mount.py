"""Mount control API — GET status, POST unpark/track/stop/goto/park/goto_sky."""

from __future__ import annotations

import contextlib
import dataclasses
import math

from astropy.coordinates import EarthLocation
from astropy.time import Time
import astropy.units as u
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import config
from ..domain.solar import is_solar_target
from ..ports.camera import CameraPort
from ..ports.mount import MountPort, MountState
from ..ports.solver import SolverPort
from ..workflow.goto_center import goto_and_center
from . import deps

router = APIRouter(prefix="/api/mount")


@router.get("/config")
def mount_config_view() -> dict:
    """Return observer location and mount limit settings."""
    return {
        "observer_lat": config.OBSERVER_LAT,
        "observer_lon": config.OBSERVER_LON,
        "mount_min_alt_deg": config.MOUNT_MIN_ALT_DEG,
        "mount_max_alt_deg": config.MOUNT_MAX_ALT_DEG,
        "mount_ha_east_limit_h": config.MOUNT_HA_EAST_LIMIT_H,
        "mount_ha_west_limit_h": config.MOUNT_HA_WEST_LIMIT_H,
    }


def _check_mount_limits(ra_hours: float, dec_deg: float) -> None:
    """Raise HTTPException(400) if the target violates mount position limits."""
    loc = EarthLocation(lat=config.OBSERVER_LAT * u.deg, lon=config.OBSERVER_LON * u.deg)
    lst_hours: float = Time.now().sidereal_time("apparent", longitude=loc.lon).hour
    ha = lst_hours - ra_hours
    ha = ((ha + 12.0) % 24.0) - 12.0  # normalise to [-12, +12]

    if ha < config.MOUNT_HA_EAST_LIMIT_H:
        raise HTTPException(status_code=400, detail={
            "error": "mount_limit", "reason": "hour_angle_east",
            "ha_hours": round(ha, 3), "limit_hours": config.MOUNT_HA_EAST_LIMIT_H,
        })
    if ha > config.MOUNT_HA_WEST_LIMIT_H:
        raise HTTPException(status_code=400, detail={
            "error": "mount_limit", "reason": "counterweight_up",
            "ha_hours": round(ha, 3), "limit_hours": config.MOUNT_HA_WEST_LIMIT_H,
        })

    lat_r = math.radians(config.OBSERVER_LAT)
    dec_r = math.radians(dec_deg)
    ha_r  = math.radians(ha * 15.0)
    sin_alt = (math.sin(lat_r) * math.sin(dec_r)
               + math.cos(lat_r) * math.cos(dec_r) * math.cos(ha_r))
    alt_deg = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))

    if alt_deg < config.MOUNT_MIN_ALT_DEG:
        raise HTTPException(status_code=400, detail={
            "error": "mount_limit", "reason": "below_horizon",
            "altitude_deg": round(alt_deg, 2), "limit_deg": config.MOUNT_MIN_ALT_DEG,
        })
    if alt_deg > config.MOUNT_MAX_ALT_DEG:
        raise HTTPException(status_code=400, detail={
            "error": "mount_limit", "reason": "zenith_exclusion",
            "altitude_deg": round(alt_deg, 2), "limit_deg": config.MOUNT_MAX_ALT_DEG,
        })


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
    _check_mount_limits(body.ra, body.dec)
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


@router.post("/home")
def mount_home(mount: MountPort = Depends(deps.get_mount)) -> dict:
    """Slew to the celestial pole (RA = current LST, Dec = 89°, HA = 0).

    Sets the mount to its starting position pointing at the polar region.
    Auto-unparks if necessary.  Bypasses position limits — the pole is
    always at altitude ≈ observer latitude, well within any sane limit set.
    """
    if mount.get_state() == MountState.PARKED:
        if not mount.unpark():
            raise HTTPException(status_code=500, detail="Auto-unpark before home failed")
    loc = EarthLocation(lat=config.OBSERVER_LAT * u.deg, lon=config.OBSERVER_LON * u.deg)
    lst_hours: float = Time.now().sidereal_time("apparent", longitude=loc.lon).hour
    ra_hours: float = lst_hours      # HA = 0 → on meridian
    dec_deg: float  = 89.0           # near celestial pole
    ok = mount.goto(ra_hours, dec_deg)
    if not ok:
        raise HTTPException(status_code=500, detail="Home slew failed")
    return {"ok": True, "ra": ra_hours, "dec": dec_deg}


@router.post("/park")
def mount_park(mount: MountPort = Depends(deps.get_mount)) -> dict[str, bool]:
    ok = mount.park()
    if not ok:
        raise HTTPException(status_code=500, detail="Park failed")
    return {"ok": True}


class GuideRequest(BaseModel):
    direction: str = Field(pattern=r"^[nsewNSEW]$")
    duration_ms: int = Field(default=500, ge=1, le=9999)


@router.post("/guide")
def mount_guide(
    body: GuideRequest,
    mount: MountPort = Depends(deps.get_mount),
) -> dict[str, bool]:
    """Send a fixed-duration guide pulse — no stop command required."""
    ok = mount.guide(body.direction.lower(), body.duration_ms)
    if not ok:
        raise HTTPException(status_code=500, detail="Guide pulse failed")
    return {"ok": True}


class AlignStartRequest(BaseModel):
    num_stars: int = Field(default=1, ge=1, le=9)


@router.post("/align/start")
def mount_align_start(
    body: AlignStartRequest,
    mount: MountPort = Depends(deps.get_mount),
) -> dict[str, bool]:
    """Begin n-star alignment sequence."""
    ok = mount.start_alignment(body.num_stars)
    if not ok:
        raise HTTPException(status_code=500, detail="Alignment start failed")
    return {"ok": True}


@router.post("/align/accept")
def mount_align_accept(mount: MountPort = Depends(deps.get_mount)) -> dict[str, bool]:
    """Accept current pointing as the next alignment star."""
    ok = mount.accept_alignment_star()
    if not ok:
        raise HTTPException(status_code=500, detail="Accept alignment star failed")
    return {"ok": True}


@router.post("/align/save")
def mount_align_save(mount: MountPort = Depends(deps.get_mount)) -> dict[str, bool]:
    """Write the computed pointing model to EEPROM."""
    ok = mount.save_alignment()
    if not ok:
        raise HTTPException(status_code=500, detail="Save alignment failed")
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


class GotoAndCenterRequest(BaseModel):
    ra:               float
    dec:              float
    exposure:         float      = Field(default=5.0, gt=0.0, le=60.0)
    pixel_scale:      float | None = Field(default=None, gt=0.0)
    tolerance_arcmin: float      = Field(default=2.0, gt=0.0)
    max_iterations:   int        = Field(default=3, ge=1, le=5)


class GotoAndCenterResponse(BaseModel):
    success:       bool
    final_ra:      float
    final_dec:     float
    iterations:    int
    offset_arcmin: float
    error:         str | None = None


@router.post("/goto_and_center", response_model=GotoAndCenterResponse)
async def mount_goto_and_center(
    body:   GotoAndCenterRequest,
    mount:  MountPort  = Depends(deps.get_mount),
    camera: CameraPort = Depends(deps.get_camera),
    solver: SolverPort = Depends(deps.get_solver),
    confirm_solar: bool = Query(default=False),
) -> GotoAndCenterResponse:
    """Goto target, plate-solve, sync, and refine until centered."""
    if not confirm_solar:
        blocked, sep = is_solar_target(body.ra, body.dec)
        if blocked:
            raise HTTPException(
                status_code=403,
                detail={"error": "solar_exclusion", "sun_separation_deg": round(sep, 2)},
            )
    _check_mount_limits(body.ra, body.dec)
    scale = body.pixel_scale if body.pixel_scale is not None else config.PIXEL_SCALE_ARCSEC
    result = await goto_and_center(
        mount, camera, solver,
        body.ra, body.dec,
        pixel_scale=scale,
        exposure=body.exposure,
        tolerance_arcmin=body.tolerance_arcmin,
        max_iterations=body.max_iterations,
    )
    return GotoAndCenterResponse(**dataclasses.asdict(result))


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
