"""Mount control API — GET status, POST unpark/track/stop/goto/park/goto_sky."""

from __future__ import annotations

import contextlib
import dataclasses
import logging
import math
import time

from astropy.coordinates import EarthLocation
from astropy.time import Time
import astropy.units as u
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .. import config
from ..domain.command_status import CommandStatus
from ..domain.solar import is_solar_target
from ..domain.time_location_status import TimeLocationStatus
from ..ports.mount import MountPort, MountState
from ..services.command_history import CommandHistoryService
from ..services.operation_gate import evaluate_gate, gate_inputs_from_device_state
from ..ports.solver import SolverPort
from ..services.hardware_coordinator import CommandConflictError, HardwareCommandCoordinator
from ..services.device_state import DeviceStateService
from ..services import mount_operations as mount_ops
from ..workflow.goto_center import goto_and_center
from . import deps

from ..adapters.onstep import OnStepSafetyError

_log = logging.getLogger(__name__)
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
    ha, alt_deg = _compute_ha_alt(ra_hours, dec_deg)

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


def _gate_check(
    device_state: DeviceStateService,
    operation: str,
    master_source_svc: object = None,
    raspberry_trust_svc: object = None,
) -> None:
    """Raise structured HTTPException(409) if the gate blocks this operation."""
    inputs = gate_inputs_from_device_state(
        device_state,
        master_source_svc=master_source_svc,
        raspberry_trust_svc=raspberry_trust_svc,
    )
    result = evaluate_gate(operation, **inputs)
    if not result.allowed:
        raise HTTPException(status_code=409, detail={
            "gate_blocked": True,
            "reason_code": result.reason_code,
            "human_message": result.human_message,
            "required_user_action": result.required_user_action,
            "blocking_states": result.blocking_states,
        })


class MountStatus(BaseModel):
    state: str
    ra: float | None
    dec: float | None
    ha: float | None        # hour angle in hours, normalised [-12, +12]
    alt: float | None       # altitude in degrees
    park_ra: float | None = None   # stored park position (hours)
    park_dec: float | None = None  # stored park position (degrees)
    home_ra: float | None = None   # home RA = LST (HA=0, Dec 89°)
    home_dec: float | None = None  # always 89.0°
    stale: bool = False            # True if the cached state may be outdated
    # R2-003: last command tracking
    last_command: str | None = None
    last_command_age_s: float | None = None
    last_command_error: str | None = None
    # M1-004: hardware watchdog
    watchdog_warning: str | None = None
    # adapter safety lock (populated when OnStep safety system blocks movement)
    safety_violation: str | None = None
    # M7-002: time/location verification status (UNKNOWN / VERIFIED / UNVERIFIED)
    time_location_status: str = "UNKNOWN"
    # M8-004: REQ-CONN-001 — explicit connection state breakdown
    adapter_open: bool = False
    health_check_ok: bool | None = None
    connected: bool = False
    park_state: str = "UNKNOWN"       # PARKED | UNPARKED | UNKNOWN
    tracking_state: str = "UNKNOWN"   # TRACKING | NOT_TRACKING | UNKNOWN
    last_error: str | None = None


_PARK_STATE: dict[MountState, str] = {
    MountState.PARKED:   "PARKED",
    MountState.UNPARKED: "UNPARKED",
    MountState.TRACKING: "UNPARKED",
    MountState.SLEWING:  "UNPARKED",
    MountState.AT_LIMIT: "UNPARKED",
    MountState.AT_HOME:  "UNPARKED",
    MountState.UNKNOWN:  "UNKNOWN",
}

_TRACKING_STATE: dict[MountState, str] = {
    MountState.PARKED:   "NOT_TRACKING",
    MountState.UNPARKED: "NOT_TRACKING",
    MountState.TRACKING: "TRACKING",
    MountState.SLEWING:  "NOT_TRACKING",
    MountState.AT_LIMIT: "NOT_TRACKING",
    MountState.AT_HOME:  "NOT_TRACKING",
    MountState.UNKNOWN:  "UNKNOWN",
}


def _compute_ha_alt(ra_hours: float, dec_deg: float) -> tuple[float, float]:
    """Return (ha_hours, alt_deg) for the given RA/Dec at the configured site."""
    loc = EarthLocation(lat=config.OBSERVER_LAT * u.deg, lon=config.OBSERVER_LON * u.deg)
    lst_hours: float = Time.now().sidereal_time("apparent", longitude=loc.lon).hour
    ha = lst_hours - ra_hours
    ha = ((ha + 12.0) % 24.0) - 12.0
    lat_r = math.radians(config.OBSERVER_LAT)
    dec_r = math.radians(dec_deg)
    ha_r  = math.radians(ha * 15.0)
    sin_alt = (math.sin(lat_r) * math.sin(dec_r)
               + math.cos(lat_r) * math.cos(dec_r) * math.cos(ha_r))
    alt_deg = math.degrees(math.asin(max(-1.0, min(1.0, sin_alt))))
    return round(ha, 4), round(alt_deg, 2)


def _safe_goto(
    mount: MountPort,
    coordinator: HardwareCommandCoordinator,
    ra: float,
    dec: float,
) -> None:
    """Issue a goto via the service layer; map domain exceptions to HTTP."""
    try:
        mount_ops.safe_goto(mount, coordinator, ra, dec)
    except mount_ops.MountSlewingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CommandConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        if OnStepSafetyError is not None and isinstance(exc, OnStepSafetyError):
            raise HTTPException(status_code=409, detail=exc.violation.reason) from exc
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class GotoRequest(BaseModel):
    ra: float
    dec: float


def _get_lst() -> float | None:
    with contextlib.suppress(Exception):
        loc = EarthLocation(lat=config.OBSERVER_LAT * u.deg, lon=config.OBSERVER_LON * u.deg)
        return round(Time.now().sidereal_time("apparent", longitude=loc.lon).hour, 4)
    return None


@router.get("/status", response_model=MountStatus)
def mount_status(
    mount: MountPort = Depends(deps.get_mount),
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> MountStatus:
    # Prefer background-poll cache to avoid hammering the serial bus on every UI poll.
    # Fall back to a direct query only if the poller has not run yet.
    observed = device_state.get_mount_state()
    if observed is not None:
        state = observed.state
        ra    = observed.ra
        dec   = observed.dec
        stale = observed.is_stale()
        age_s = round(observed.age_seconds(), 1)
        if state == MountState.UNKNOWN:
            _log.warning(
                "mount_status: cache hit but state=UNKNOWN (age=%.1fs error=%r) — Stage 4 will stay locked",
                age_s, observed.error,
            )
        else:
            _log.debug("mount_status: cache hit state=%s age=%.1fs stale=%s", state.name, age_s, stale)
    else:
        _log.warning("mount_status: no cache yet — falling back to direct mount.get_state()")
        state = mount.get_state()
        ra    = None
        dec   = None
        stale = False
        if state == MountState.UNKNOWN:
            _log.warning("mount_status: direct query also returned UNKNOWN — Stage 4 will stay locked")
        else:
            _log.info("mount_status: direct query state=%s", state.name)
        if state != MountState.UNKNOWN:
            with contextlib.suppress(Exception):
                pos = mount.get_position()
                if pos:
                    ra  = pos.ra
                    dec = pos.dec

    ha: float | None  = None
    alt: float | None = None
    if ra is not None and dec is not None:
        with contextlib.suppress(Exception):
            ha, alt = _compute_ha_alt(ra, dec)

    park_pos = None
    with contextlib.suppress(Exception):
        park_pos = mount.get_park_position()

    lst = _get_lst()

    cmd, cmd_at, cmd_err = device_state.get_last_command()
    cmd_age = round(time.monotonic() - cmd_at, 1) if cmd_at is not None else None

    # M8-004: REQ-CONN-001 — derive explicit connection state fields
    adapter_open = device_state.is_started()
    if observed is None:
        health_check_ok: bool | None = None
    elif observed.error:
        health_check_ok = False
    else:
        health_check_ok = True
    connected = adapter_open and health_check_ok is True

    return MountStatus(
        state=state.name.lower(),
        ra=ra,
        dec=dec,
        ha=ha,
        alt=alt,
        park_ra=park_pos.ra if park_pos else None,
        park_dec=park_pos.dec if park_pos else None,
        home_ra=lst,
        home_dec=89.0 if lst is not None else None,
        stale=stale,
        last_command=cmd,
        last_command_age_s=cmd_age,
        last_command_error=cmd_err,
        watchdog_warning=device_state.get_watchdog_warning(),
        safety_violation=observed.safety_violation if observed else None,
        time_location_status=device_state.get_time_location_status().name,
        adapter_open=adapter_open,
        health_check_ok=health_check_ok,
        connected=connected,
        park_state=_PARK_STATE.get(state, "UNKNOWN"),
        tracking_state=_TRACKING_STATE.get(state, "UNKNOWN"),
        last_error=observed.error if observed else None,
    )


@router.post("/unpark")
def mount_unpark(
    mount:        MountPort          = Depends(deps.get_mount),
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> dict[str, bool]:
    device_state.record_command("unpark")
    try:
        mount_ops.unpark_sequence(mount, device_state)
    except RuntimeError as exc:
        device_state.record_command_error(str(exc))
        raise HTTPException(status_code=500, detail=f"Unpark failed: {exc}") from exc
    return {"ok": True}


@router.post("/track")
def mount_track(
    mount:               MountPort          = Depends(deps.get_mount),
    device_state:        DeviceStateService = Depends(deps.get_device_state),
    master_source_svc:   object             = Depends(deps.get_master_source_service),
    raspberry_trust_svc: object             = Depends(deps.get_raspberry_trust_service),
) -> dict[str, bool]:
    _gate_check(device_state, "tracking_enable", master_source_svc=master_source_svc, raspberry_trust_svc=raspberry_trust_svc)
    device_state.record_command("track")
    try:
        mount_ops.track_sequence(mount)
    except RuntimeError as exc:
        device_state.record_command_error(str(exc))
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/stop")
def mount_stop(
    mount:        MountPort          = Depends(deps.get_mount),
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> dict[str, bool]:
    device_state.record_command("stop")
    mount.stop()
    device_state.poll_now()
    return {"ok": True}


@router.post("/goto")
def mount_goto(
    body:                GotoRequest,
    mount:               MountPort          = Depends(deps.get_mount),
    coordinator:         HardwareCommandCoordinator = Depends(deps.get_coordinator),
    device_state:        DeviceStateService = Depends(deps.get_device_state),
    master_source_svc:   object             = Depends(deps.get_master_source_service),
    raspberry_trust_svc: object             = Depends(deps.get_raspberry_trust_service),
    command_history:     CommandHistoryService = Depends(deps.get_command_history_service),
    confirm_solar:       bool = Query(default=False),
    bright_star:         bool = Query(default=False),
) -> dict[str, bool]:
    """GoTo target RA/Dec.

    ?bright_star=true uses the bright_star_goto gate operation (REQ-GOTO-002).
    ?confirm_solar=true bypasses the solar exclusion check.
    All attempts are recorded in command history (REQ-GOTO-001 / INC-005).
    """
    gate_op = "bright_star_goto" if bright_star else "goto"
    params  = {"ra": body.ra, "dec": body.dec, "bright_star": bright_star}
    rec = command_history.record("goto", gate_op, params)

    try:
        _gate_check(device_state, gate_op, master_source_svc=master_source_svc, raspberry_trust_svc=raspberry_trust_svc)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        command_history.update(
            rec.command_id, CommandStatus.REJECTED,
            reason_code=detail.get("reason_code"),
            human_message=detail.get("human_message"),
            backend_response=detail,
        )
        raise

    if not confirm_solar:
        blocked, sep = is_solar_target(body.ra, body.dec)
        if blocked:
            command_history.update(
                rec.command_id, CommandStatus.REJECTED,
                reason_code="SOLAR_EXCLUSION",
                human_message=f"Target is within {sep:.1f}° of the sun",
                backend_response={"sun_separation_deg": round(sep, 2)},
            )
            raise HTTPException(
                status_code=403,
                detail={"error": "solar_exclusion", "sun_separation_deg": round(sep, 2)},
            )

    try:
        _check_mount_limits(body.ra, body.dec)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        command_history.update(
            rec.command_id, CommandStatus.REJECTED,
            reason_code="MOUNT_LIMIT",
            human_message=str(detail.get("reason", exc.detail)),
            backend_response=detail,
        )
        raise

    command_history.update(rec.command_id, CommandStatus.ISSUED)
    device_state.record_command(f"goto ra={body.ra:.4f}h dec={body.dec:.2f}°")
    try:
        _safe_goto(mount, coordinator, body.ra, body.dec)
    except Exception as exc:
        command_history.update(rec.command_id, CommandStatus.FAILED, human_message=str(exc))
        raise
    command_history.update(rec.command_id, CommandStatus.SUCCEEDED)
    return {"ok": True}


class SyncRequest(BaseModel):
    ra: float
    dec: float


@router.post("/sync")
def mount_sync(
    body:                SyncRequest,
    mount:               MountPort          = Depends(deps.get_mount),
    device_state:        DeviceStateService = Depends(deps.get_device_state),
    master_source_svc:   object             = Depends(deps.get_master_source_service),
    raspberry_trust_svc: object             = Depends(deps.get_raspberry_trust_service),
) -> dict[str, bool]:
    """Tell the mount it is currently pointing at the given RA/Dec."""
    _gate_check(device_state, "sync", master_source_svc=master_source_svc, raspberry_trust_svc=raspberry_trust_svc)
    ok = mount.sync(body.ra, body.dec)
    if not ok:
        raise HTTPException(status_code=500, detail="Mount sync failed")
    return {"ok": True}


@router.post("/sync_clock")
def mount_sync_clock(
    mount:             MountPort          = Depends(deps.get_mount),
    device_state:      DeviceStateService = Depends(deps.get_device_state),
    master_source_svc: object             = Depends(deps.get_master_source_service),
) -> dict:
    """Push Pi system time and configured observer location into OnStep.

    This is the user-confirmation endpoint for the M7-001 interactive startup
    dialog: the UI calls this after the user approves the time/location push.
    Sets TimeLocationStatus to VERIFIED on success.

    M8-007: When the master time source at verification time is GPS_FIX or NTP,
    ONSTEP_COMPARISON trust is established for the Raspberry Pi clock (DEC-006 chain).
    """
    try:
        mount.ensure_time_location_synced()
        device_state.set_time_location_status(TimeLocationStatus.VERIFIED)
        device_state.set_last_push_at()
        # M8-007: if OnStep's reference was GPS/NTP, Pi clock is validated via DEC-006 trust chain
        from ..domain.master_time_source import MasterTimeSource
        user_confirmed: bool = device_state.is_user_time_confirmed()
        ms = master_source_svc.evaluate(user_confirmed=user_confirmed)  # type: ignore[union-attr]
        if ms in (MasterTimeSource.GPS_FIX, MasterTimeSource.NTP):
            device_state.set_onstep_comparison_established()
        return {"ok": True, "time_location_status": "VERIFIED"}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/time_location_skip")
def mount_time_location_skip(
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> dict:
    """User chose to skip the time/location push.

    Sets TimeLocationStatus to UNVERIFIED.  GoTo, tracking enable and automatic
    sync will be blocked until the user reconnects and verifies.
    """
    device_state.set_time_location_status(TimeLocationStatus.UNVERIFIED)
    return {"ok": True, "time_location_status": "UNVERIFIED"}


@router.post("/confirm_time")
def mount_confirm_time(
    device_state: DeviceStateService = Depends(deps.get_device_state),
    raspberry_trust_svc: object      = Depends(deps.get_raspberry_trust_service),
) -> dict:
    """User asserts the Raspberry Pi clock is correct.

    Sets USER_CONFIRMED trust source (M8-006/M8-007).  Trust expires after
    session_trust_expiry_minutes (config [time_location] section, default 120 min).
    """
    device_state.set_user_time_confirmed(True)
    return {"ok": True, "raspberry_trust_source": "USER_CONFIRMED"}


@router.post("/home")
def mount_home(
    mount:        MountPort          = Depends(deps.get_mount),
    coordinator:  HardwareCommandCoordinator = Depends(deps.get_coordinator),
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> dict:
    """Slew to the OnStep stored home position (:hC#).

    Uses the home position saved in OnStep's firmware (set via :hF# during
    initial mount setup).  Auto-unparks if necessary.
    """
    device_state.record_command("home")
    try:
        mount_ops.home_sequence(mount, coordinator)
    except mount_ops.MountSlewingError as exc:
        device_state.record_command_error(str(exc))
        raise HTTPException(status_code=409, detail="Mount is slewing — stop it before homing") from exc
    except RuntimeError as exc:
        device_state.record_command_error(str(exc))
        raise HTTPException(
            status_code=500,
            detail=f"Home slew failed — check mount is powered ({exc})",
        ) from exc
    except CommandConflictError as exc:
        device_state.record_command_error(str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    device_state.poll_now()
    return {"ok": True}


class ParkRequest(BaseModel):
    confirmed: bool = False


@router.post("/park")
def mount_park(
    body:         ParkRequest        = ParkRequest(),
    mount:        MountPort          = Depends(deps.get_mount),
    coordinator:  HardwareCommandCoordinator = Depends(deps.get_coordinator),
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> dict:
    if not body.confirmed:
        return {
            "confirm_required": True,
            "message": "Confirm park to stored position. The mount will slew to the saved park position.",
        }
    device_state.record_command("park")
    try:
        mount_ops.park_sequence(mount, coordinator, device_state)
    except mount_ops.MountSlewingError as exc:
        device_state.record_command_error(str(exc))
        raise HTTPException(status_code=409, detail="Mount is currently slewing — stop it before parking") from exc
    except CommandConflictError as exc:
        device_state.record_command_error(str(exc))
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        device_state.record_command_error(str(exc))
        raise HTTPException(status_code=500, detail=f"Park failed: {exc}") from exc
    return {"ok": True}


class GuideRequest(BaseModel):
    direction: str = Field(pattern=r"^[nsewNSEW]$")
    duration_ms: int = Field(default=500, ge=1, le=9999)


@router.post("/guide")
def mount_guide(
    body: GuideRequest,
    mount: MountPort = Depends(deps.get_mount),
) -> dict[str, bool]:
    """Send a fixed-duration guide pulse — no stop command required.

    Auto-enables tracking if the mount is unparked but idle — OnStep silently
    ignores guide pulses unless the mount is actively tracking.
    """
    state = mount.get_state()
    if state == MountState.PARKED:
        raise HTTPException(status_code=409, detail="Mount is parked — unpark first")
    if state == MountState.SLEWING:
        raise HTTPException(status_code=409, detail="Mount is slewing — wait for it to stop")
    if state != MountState.TRACKING:
        if not mount.enable_tracking():
            raise HTTPException(status_code=503, detail="Could not enable tracking — check mount connection")
    ok = mount.guide(body.direction.lower(), body.duration_ms)
    if not ok:
        raise HTTPException(
            status_code=500,
            detail=f"Guide pulse failed (direction={body.direction} state={state.name})"
        )
    return {"ok": True}


class NudgeRequest(BaseModel):
    direction: str = Field(pattern=r"^[nsewNSEW]$")
    duration_ms: int = Field(default=500, ge=50, le=5000)


@router.post("/nudge")
def mount_nudge(
    body: NudgeRequest,
    mount: MountPort = Depends(deps.get_mount),
) -> dict[str, bool]:
    """Move at center rate for a fixed duration — for manual object centering.

    Unlike /guide (OnStep configurable guide rate), this always uses center
    rate (:RC# + :Mn#) so motion is visually observable regardless of the
    OnStep guide-rate configuration.
    """
    state = mount.get_state()
    if state == MountState.PARKED:
        raise HTTPException(status_code=409, detail="Mount is parked — unpark first")
    if state == MountState.SLEWING:
        raise HTTPException(status_code=409, detail="Mount is slewing — wait for it to stop")
    if state != MountState.TRACKING:
        if not mount.enable_tracking():
            raise HTTPException(status_code=503, detail="Could not enable tracking — check mount connection")
    ok = mount.move(body.direction.lower(), body.duration_ms)
    if not ok:
        raise HTTPException(
            status_code=500,
            detail=f"Move command failed (direction={body.direction} state={state.name})"
        )
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
def mount_disable_tracking(
    mount: MountPort = Depends(deps.get_mount),
    device_state: DeviceStateService = Depends(deps.get_device_state),
) -> dict[str, bool]:
    ok = mount.disable_tracking()
    if not ok:
        raise HTTPException(status_code=500, detail="Disable tracking failed")
    device_state.poll_now()
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
    camera_index:     int        = Field(default=0, ge=0, le=7)


class GotoAndCenterResponse(BaseModel):
    success:       bool
    final_ra:      float
    final_dec:     float
    iterations:    int
    offset_arcmin: float
    error:         str | None = None


@router.post("/goto_and_center", response_model=GotoAndCenterResponse)
async def mount_goto_and_center(
    body:                GotoAndCenterRequest,
    mount:               MountPort  = Depends(deps.get_mount),
    solver:              SolverPort = Depends(deps.get_solver),
    coordinator:         HardwareCommandCoordinator = Depends(deps.get_coordinator),
    device_state:        DeviceStateService = Depends(deps.get_device_state),
    master_source_svc:   object             = Depends(deps.get_master_source_service),
    raspberry_trust_svc: object             = Depends(deps.get_raspberry_trust_service),
    confirm_solar:       bool = Query(default=False),
) -> GotoAndCenterResponse:
    """Goto target, plate-solve, sync, and refine until centered."""
    _gate_check(device_state, "goto", master_source_svc=master_source_svc, raspberry_trust_svc=raspberry_trust_svc)
    if not confirm_solar:
        blocked, sep = is_solar_target(body.ra, body.dec)
        if blocked:
            raise HTTPException(
                status_code=403,
                detail={"error": "solar_exclusion", "sun_separation_deg": round(sep, 2)},
            )
    _check_mount_limits(body.ra, body.dec)

    try:
        with coordinator.mount_command(timeout=0):
            if mount.is_slewing():
                raise HTTPException(
                    status_code=409,
                    detail="Mount is currently slewing — stop it before centering",
                )
            camera = deps.get_preview_camera(body.camera_index)
            scale  = body.pixel_scale if body.pixel_scale is not None else config.PIXEL_SCALE_ARCSEC
            result = await goto_and_center(
                mount, camera, solver,
                body.ra, body.dec,
                pixel_scale=scale,
                exposure=body.exposure,
                tolerance_arcmin=body.tolerance_arcmin,
                max_iterations=body.max_iterations,
            )
    except CommandConflictError as exc:
        raise HTTPException(
            status_code=409,
            detail="Another mount GoTo is in progress — try again after it completes",
        ) from exc
    return GotoAndCenterResponse(**dataclasses.asdict(result))


@router.post("/goto_sky", response_model=SkyPosition)
def mount_goto_sky(
    elevation: float = Query(default=80.0, ge=60.0, le=89.0),
    mount: MountPort = Depends(deps.get_mount),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
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
    dec_deg: float   = config.OBSERVER_LAT - (90.0 - elevation)
    ra_hours: float  = lst_hours

    blocked, sep = is_solar_target(ra_hours, dec_deg)
    if blocked:
        raise HTTPException(
            status_code=403,
            detail={"error": "solar_exclusion", "sun_separation_deg": round(sep, 2)},
        )

    _safe_goto(mount, coordinator, ra_hours, dec_deg)
    return SkyPosition(ra=ra_hours, dec=dec_deg, elevation_deg=elevation, lst_hours=lst_hours)
