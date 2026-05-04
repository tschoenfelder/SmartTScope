"""Polar alignment API — 3-position plate-solve to measure and correct pole error."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from typing import Literal

import astropy.units as u
from astropy.coordinates import EarthLocation
from astropy.time import Time
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from .. import config
from ..domain.polar_alignment import (
    Precision,
    SkyPoint,
    classify_alignment,
    compute_polar_error,
    correction_direction_alt,
    correction_direction_az,
    find_rotation_pole,
)
from ..domain.visibility import HorizonProfile, compute_altaz, load_horizon
from ..ports.mount import MountPort, MountState
from ..ports.solver import SolverPort
from . import deps

router = APIRouter(prefix="/api/polar")

_HORIZON: HorizonProfile | None = load_horizon(config.HORIZON_DAT)

Step = Literal[
    "idle", "slewing",
    "solving_1", "solving_2", "solving_3",
    "checking",                  # coarse alignment check after HOME solve
    "coarse_required",           # mount too far from NCP; manual repositioning needed
    "computing", "done",
    "refining",                  # re-measure using cached RA positions
    "live",                      # passive no-slew solve loop during fine adjustment
    "camera_fallback_offered",   # repeated solve failures; guide camera offered
    "error",
]


@dataclass
class _PolarState:
    running: bool = False
    step: Step = "idle"
    progress: int = 0
    # error results
    alt_error_arcmin: float | None = None
    az_error_arcmin: float | None = None
    total_error_arcmin: float | None = None
    pole_ra: float | None = None
    pole_dec: float | None = None
    # guidance (tasks 1-3)
    correction_alt: str | None = None
    correction_az: str | None = None
    quality_label: str | None = None
    target_precision_arcmin: float = Precision.GOOD_IMAGING
    target_reached: bool = False
    # messages
    error_msg: str | None = None
    warning_msg: str | None = None
    # coarse check (task 6)
    coarse_error_deg: float | None = None
    # cached for refine / live
    p1: SkyPoint | None = None
    p2: SkyPoint | None = None
    p3: SkyPoint | None = None
    cam_index: int = 0
    exposure: float = 5.0
    gain: int = 100
    ra_step_h: float = 1.0
    # retry / fallback (tasks 9-10)
    solve_retries: int = 0
    fallback_available: bool = False


_state = _PolarState()
_task: asyncio.Task | None = None
_checklist_confirmed: bool = False   # persists within server session (task 8)


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_lst() -> float:
    loc = EarthLocation(lat=config.OBSERVER_LAT * u.deg, lon=config.OBSERVER_LON * u.deg)
    return Time.now().sidereal_time("apparent", longitude=loc.lon).hour


async def _wait_not_slewing(mount: MountPort, timeout_s: float = 120.0) -> bool:
    deadline = asyncio.get_event_loop().time() + timeout_s
    while asyncio.get_event_loop().time() < deadline:
        st = await asyncio.to_thread(mount.get_state)
        if st != MountState.SLEWING:
            return True
        await asyncio.sleep(2.0)
    return False


def _check_ha_limits(ra_h: float) -> None:
    """Raise if ra_h falls outside the configured safe HA envelope."""
    ha = (_get_lst() - ra_h + 12.0) % 24.0 - 12.0
    if ha < config.MOUNT_HA_EAST_LIMIT_H:
        raise RuntimeError(
            f"Target HA {ha:.2f}h east of limit {config.MOUNT_HA_EAST_LIMIT_H}h"
        )
    if ha > config.MOUNT_HA_WEST_LIMIT_H:
        raise RuntimeError(
            f"Target HA {ha:.2f}h west of limit {config.MOUNT_HA_WEST_LIMIT_H}h"
        )


def _check_horizon(ra_h: float, dec_deg: float, label: str) -> None:
    """Raise if the position falls below the local horizon profile."""
    if _HORIZON is None:
        return
    alt, az = compute_altaz(ra_h, dec_deg, config.OBSERVER_LAT, config.OBSERVER_LON)
    if not _HORIZON.is_visible(alt, az):
        min_alt = _HORIZON.min_alt_at(az)
        raise RuntimeError(
            f"{label} blocked by horizon profile "
            f"(az {az:.0f}°, alt {alt:.1f}° < min {min_alt:.1f}°)"
        )


def _update_result(pole: SkyPoint, err, precision: float) -> None:
    """Write computed error + all derived guidance fields into _state."""
    _state.pole_ra            = pole.ra
    _state.pole_dec           = pole.dec
    _state.alt_error_arcmin   = err.alt_error_arcmin
    _state.az_error_arcmin    = err.az_error_arcmin
    _state.total_error_arcmin = err.total_error_arcmin
    _state.correction_alt     = correction_direction_alt(err.alt_error_arcmin)
    _state.correction_az      = correction_direction_az(err.az_error_arcmin)
    _state.quality_label      = classify_alignment(err.total_error_arcmin)
    _state.target_reached     = err.total_error_arcmin <= precision


# ── coroutines ────────────────────────────────────────────────────────────────

async def _run_measurement(
    ra_step_h: float,
    exposure: float,
    gain: int,
    camera_index: int,
    precision: float,
    mount: MountPort,
    solver: SolverPort,
) -> None:
    global _state
    consecutive_failures = 0
    try:
        camera = deps.get_preview_camera(camera_index)
        if hasattr(camera, "set_gain"):
            camera.set_gain(gain)  # type: ignore[union-attr]
        scale = config.PIXEL_SCALE_ARCSEC

        if await asyncio.to_thread(mount.get_state) == MountState.PARKED:
            await asyncio.to_thread(mount.unpark)
            await asyncio.sleep(1.0)

        # ── position 1: HOME ──────────────────────────────────────────────────
        lst = _get_lst()
        ra1 = lst % 24.0
        _check_ha_limits(ra1)
        _check_horizon(ra1, 89.0, "Position 1 (HOME)")
        _state.step = "slewing"; _state.progress = 8
        if not await asyncio.to_thread(mount.goto, ra1, 89.0):
            raise RuntimeError("GoTo home failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 1 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_1"; _state.progress = 20
        frame = await asyncio.to_thread(camera.capture, exposure)
        r1 = await asyncio.to_thread(solver.solve, frame, scale)
        if not r1.success:
            consecutive_failures += 1
            raise RuntimeError(f"Solve 1 failed: {r1.error}")
        consecutive_failures = 0
        p1 = SkyPoint(ra=r1.ra, dec=r1.dec)

        # ── coarse alignment check (task 6) ───────────────────────────────────
        _state.step = "checking"; _state.progress = 25
        coarse_err_deg = abs(90.0 - p1.dec)
        _state.coarse_error_deg = round(coarse_err_deg, 2)
        if coarse_err_deg > 5.0:
            _state.step = "coarse_required"
            raise RuntimeError(
                f"Mount is {coarse_err_deg:.1f}° from the pole — "
                "rough mechanical repositioning required before precise measurement"
            )
        if coarse_err_deg > 1.0:
            _state.warning_msg = (
                f"Mount is {coarse_err_deg:.1f}° from pole — "
                "may be outside fine azimuth screw range"
            )

        # ── position 2: RA + step ─────────────────────────────────────────────
        ra2 = (ra1 + ra_step_h) % 24.0
        _check_ha_limits(ra2)
        _check_horizon(ra2, 89.0, "Position 2")
        _state.step = "slewing"; _state.progress = 38
        if not await asyncio.to_thread(mount.goto, ra2, 89.0):
            raise RuntimeError("GoTo position 2 failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 2 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_2"; _state.progress = 55
        frame = await asyncio.to_thread(camera.capture, exposure)
        r2 = await asyncio.to_thread(solver.solve, frame, scale)
        if not r2.success:
            consecutive_failures += 1
            _state.solve_retries += 1
            ra2 = (ra1 + 3 * ra_step_h) % 24.0   # retry at +3× step
            _check_ha_limits(ra2)
            _check_horizon(ra2, 89.0, "Position 2 retry")
            _state.step = "slewing"; _state.progress = 40
            if not await asyncio.to_thread(mount.goto, ra2, 89.0):
                raise RuntimeError("GoTo position 2 retry failed")
            if not await _wait_not_slewing(mount):
                raise RuntimeError("Slew to position 2 retry timed out")
            await asyncio.sleep(1.5)
            _state.step = "solving_2"; _state.progress = 55
            frame = await asyncio.to_thread(camera.capture, exposure)
            r2 = await asyncio.to_thread(solver.solve, frame, scale)
            if not r2.success:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    _state.fallback_available = True
                    _state.step = "camera_fallback_offered"
                    _state.error_msg = (
                        "Plate solve failed twice — guide camera fallback available. "
                        "Call POST /api/polar/use_fallback_camera with a camera_index."
                    )
                    return
                raise RuntimeError(f"Solve 2 failed (with retry): {r2.error}")
        consecutive_failures = 0
        p2 = SkyPoint(ra=r2.ra, dec=r2.dec)

        # ── position 3: RA + 2×step ───────────────────────────────────────────
        ra3 = (ra1 + 2 * ra_step_h) % 24.0
        _check_ha_limits(ra3)
        _check_horizon(ra3, 89.0, "Position 3")
        _state.step = "slewing"; _state.progress = 65
        if not await asyncio.to_thread(mount.goto, ra3, 89.0):
            raise RuntimeError("GoTo position 3 failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 3 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_3"; _state.progress = 82
        frame = await asyncio.to_thread(camera.capture, exposure)
        r3 = await asyncio.to_thread(solver.solve, frame, scale)
        if not r3.success:
            consecutive_failures += 1
            _state.solve_retries += 1
            ra3 = (ra1 - ra_step_h) % 24.0   # retry at −step
            _check_ha_limits(ra3)
            _check_horizon(ra3, 89.0, "Position 3 retry")
            _state.step = "slewing"; _state.progress = 67
            if not await asyncio.to_thread(mount.goto, ra3, 89.0):
                raise RuntimeError("GoTo position 3 retry failed")
            if not await _wait_not_slewing(mount):
                raise RuntimeError("Slew to position 3 retry timed out")
            await asyncio.sleep(1.5)
            _state.step = "solving_3"; _state.progress = 82
            frame = await asyncio.to_thread(camera.capture, exposure)
            r3 = await asyncio.to_thread(solver.solve, frame, scale)
            if not r3.success:
                consecutive_failures += 1
                if consecutive_failures >= 2:
                    _state.fallback_available = True
                    _state.step = "camera_fallback_offered"
                    _state.error_msg = (
                        "Plate solve failed twice — guide camera fallback available. "
                        "Call POST /api/polar/use_fallback_camera with a camera_index."
                    )
                    return
                raise RuntimeError(f"Solve 3 failed (with retry): {r3.error}")
        p3 = SkyPoint(ra=r3.ra, dec=r3.dec)

        # ── cache and compute ─────────────────────────────────────────────────
        _state.p1 = p1
        _state.p2 = p2
        _state.p3 = p3
        _state.cam_index  = camera_index
        _state.exposure   = exposure
        _state.gain       = gain
        _state.ra_step_h  = ra_step_h
        _state.target_precision_arcmin = precision

        _state.step = "computing"; _state.progress = 93
        pole = find_rotation_pole(p1, p2, p3)
        err  = compute_polar_error(pole, config.OBSERVER_LAT, _get_lst())
        _update_result(pole, err, precision)

        with contextlib.suppress(Exception):
            await asyncio.to_thread(mount.goto, ra1, 89.0)

        _state.step = "done"; _state.progress = 100

    except Exception as exc:
        if _state.step not in ("coarse_required", "camera_fallback_offered"):
            _state.step = "error"
        _state.error_msg = str(exc)
    finally:
        _state.running = False


async def _run_refine(
    p2_target: SkyPoint,
    p3_target: SkyPoint,
    exposure: float,
    gain: int,
    camera_index: int,
    precision: float,
    mount: MountPort,
    solver: SolverPort,
) -> None:
    global _state
    try:
        camera = deps.get_preview_camera(camera_index)
        if hasattr(camera, "set_gain"):
            camera.set_gain(gain)  # type: ignore[union-attr]
        scale = config.PIXEL_SCALE_ARCSEC

        if await asyncio.to_thread(mount.get_state) == MountState.PARKED:
            await asyncio.to_thread(mount.unpark)
            await asyncio.sleep(1.0)

        # position 1: fresh home (current LST)
        lst = _get_lst()
        ra1 = lst % 24.0
        _check_ha_limits(ra1)
        _check_horizon(ra1, 89.0, "Position 1 (HOME)")
        _state.step = "slewing"; _state.progress = 8
        if not await asyncio.to_thread(mount.goto, ra1, 89.0):
            raise RuntimeError("GoTo home failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 1 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_1"; _state.progress = 20
        frame = await asyncio.to_thread(camera.capture, exposure)
        r1 = await asyncio.to_thread(solver.solve, frame, scale)
        if not r1.success:
            raise RuntimeError(f"Solve 1 failed: {r1.error}")
        p1 = SkyPoint(ra=r1.ra, dec=r1.dec)

        # position 2: cached RA from prior measurement
        _check_ha_limits(p2_target.ra)
        _check_horizon(p2_target.ra, 89.0, "Position 2")
        _state.step = "slewing"; _state.progress = 38
        if not await asyncio.to_thread(mount.goto, p2_target.ra, 89.0):
            raise RuntimeError("GoTo position 2 failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 2 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_2"; _state.progress = 55
        frame = await asyncio.to_thread(camera.capture, exposure)
        r2 = await asyncio.to_thread(solver.solve, frame, scale)
        if not r2.success:
            raise RuntimeError(f"Solve 2 failed: {r2.error}")
        p2 = SkyPoint(ra=r2.ra, dec=r2.dec)

        # position 3: cached RA from prior measurement
        _check_ha_limits(p3_target.ra)
        _check_horizon(p3_target.ra, 89.0, "Position 3")
        _state.step = "slewing"; _state.progress = 65
        if not await asyncio.to_thread(mount.goto, p3_target.ra, 89.0):
            raise RuntimeError("GoTo position 3 failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 3 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_3"; _state.progress = 82
        frame = await asyncio.to_thread(camera.capture, exposure)
        r3 = await asyncio.to_thread(solver.solve, frame, scale)
        if not r3.success:
            raise RuntimeError(f"Solve 3 failed: {r3.error}")
        p3 = SkyPoint(ra=r3.ra, dec=r3.dec)

        _state.step = "computing"; _state.progress = 93
        pole = find_rotation_pole(p1, p2, p3)
        err  = compute_polar_error(pole, config.OBSERVER_LAT, _get_lst())
        _update_result(pole, err, precision)
        _state.p1 = p1
        _state.p2 = p2
        _state.p3 = p3

        with contextlib.suppress(Exception):
            await asyncio.to_thread(mount.goto, ra1, 89.0)

        _state.step = "done"; _state.progress = 100

    except Exception as exc:
        _state.step      = "error"
        _state.error_msg = str(exc)
    finally:
        _state.running = False


async def _run_live(
    p1: SkyPoint,
    p2: SkyPoint,
    exposure: float,
    gain: int,
    camera_index: int,
    precision: float,
    solver: SolverPort,
) -> None:
    """Capture + solve at the current mount position in a loop.

    No slewing.  Uses cached p1/p2 and each new solve as p3 to recompute
    polar error after each ALT/AZ screw adjustment.
    """
    global _state
    try:
        camera = deps.get_preview_camera(camera_index)
        if hasattr(camera, "set_gain"):
            camera.set_gain(gain)  # type: ignore[union-attr]
        scale = config.PIXEL_SCALE_ARCSEC

        while True:
            _state.step = "live"
            frame = await asyncio.to_thread(camera.capture, exposure)
            r = await asyncio.to_thread(solver.solve, frame, scale)
            if r.success:
                p3_new = SkyPoint(ra=r.ra, dec=r.dec)
                _state.p3 = p3_new
                with contextlib.suppress(Exception):
                    pole = find_rotation_pole(p1, p2, p3_new)
                    err  = compute_polar_error(pole, config.OBSERVER_LAT, _get_lst())
                    _update_result(pole, err, precision)
                if _state.target_reached:
                    _state.step = "done"
                    break
            await asyncio.sleep(2.0)

    except asyncio.CancelledError:
        _state.step = "done"   # preserve last result on user cancel
    except Exception as exc:
        _state.step      = "error"
        _state.error_msg = str(exc)
    finally:
        _state.running = False


# ── models ────────────────────────────────────────────────────────────────────

class ChecklistConfirmation(BaseModel):
    mount_at_home:            bool
    telescope_points_north:   bool
    clutches_locked:          bool
    camera_connected:         bool
    focus_ok:                 bool
    cables_slack:             bool
    no_collision_risk:        bool
    mount_stable:             bool
    alt_az_screws_accessible: bool


class MeasureRequest(BaseModel):
    ra_step_h:              float = Field(default=1.0,  gt=0.1,  le=3.0)
    exposure:               float = Field(default=5.0,  gt=0.0,  le=60.0)
    gain:                   int   = Field(default=100,  ge=100,  le=3200)
    camera_index:           int   = Field(default=0,    ge=0,    le=7)
    target_precision_arcmin: float = Field(default=Precision.GOOD_IMAGING, gt=0.0, le=180.0)


class RefineRequest(BaseModel):
    exposure:               float | None = Field(default=None, gt=0.0,  le=60.0)
    gain:                   int   | None = Field(default=None, ge=100,  le=3200)
    target_precision_arcmin: float | None = Field(default=None, gt=0.0, le=180.0)


class FallbackCameraRequest(BaseModel):
    camera_index:           int   = Field(default=1, ge=0, le=7)
    target_precision_arcmin: float | None = Field(default=None, gt=0.0, le=180.0)


class PolarStatus(BaseModel):
    running:                bool
    step:                   str
    progress:               int
    alt_error_arcmin:       float | None = None
    az_error_arcmin:        float | None = None
    total_error_arcmin:     float | None = None
    pole_ra:                float | None = None
    pole_dec:               float | None = None
    correction_alt:         str   | None = None
    correction_az:          str   | None = None
    quality_label:          str   | None = None
    target_precision_arcmin: float | None = None
    target_reached:         bool         = False
    coarse_error_deg:       float | None = None
    solve_retries:          int          = 0
    fallback_available:     bool         = False
    warning_msg:            str   | None = None
    error_msg:              str   | None = None
    checklist_confirmed:    bool         = False


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.post("/checklist")
def polar_checklist(req: ChecklistConfirmation) -> dict[str, bool]:
    """Confirm the pre-start safety checklist. All fields must be True."""
    global _checklist_confirmed
    all_ok = all([
        req.mount_at_home, req.telescope_points_north, req.clutches_locked,
        req.camera_connected, req.focus_ok, req.cables_slack,
        req.no_collision_risk, req.mount_stable, req.alt_az_screws_accessible,
    ])
    _checklist_confirmed = all_ok
    return {"confirmed": all_ok}


@router.post("/measure", response_model=PolarStatus)
async def polar_measure(
    req:    MeasureRequest,
    mount:  MountPort  = Depends(deps.get_mount),
    solver: SolverPort = Depends(deps.get_solver),
) -> PolarStatus:
    """Start a 3-position plate-solve measurement of polar alignment error."""
    global _task, _state
    if _state.running:
        return _to_response()
    if not _checklist_confirmed:
        _state.step = "error"
        _state.error_msg = "Safety checklist not confirmed — call POST /api/polar/checklist first"
        return _to_response()
    _state = _PolarState(running=True, target_precision_arcmin=req.target_precision_arcmin)
    _task = asyncio.create_task(
        _run_measurement(
            req.ra_step_h, req.exposure, req.gain, req.camera_index,
            req.target_precision_arcmin, mount, solver,
        )
    )
    return _to_response()


@router.get("/status", response_model=PolarStatus)
def polar_status() -> PolarStatus:
    """Poll the current state and latest errors."""
    return _to_response()


@router.post("/refine", response_model=PolarStatus)
async def polar_refine(
    req:    RefineRequest,
    mount:  MountPort  = Depends(deps.get_mount),
    solver: SolverPort = Depends(deps.get_solver),
) -> PolarStatus:
    """Re-run 3-position measurement using cached RA positions after adjusting screws."""
    global _task, _state
    if _state.running:
        return _to_response()
    if _state.p2 is None or _state.p3 is None:
        _state.step      = "error"
        _state.error_msg = "No prior measurement — run /measure first"
        return _to_response()
    exposure  = req.exposure  if req.exposure  is not None else _state.exposure
    gain      = req.gain      if req.gain      is not None else _state.gain
    precision = req.target_precision_arcmin if req.target_precision_arcmin is not None \
                else _state.target_precision_arcmin
    _state.running   = True
    _state.step      = "refining"
    _state.error_msg = None
    _task = asyncio.create_task(
        _run_refine(
            _state.p2, _state.p3, exposure, gain, _state.cam_index,
            precision, mount, solver,
        )
    )
    return _to_response()


@router.post("/live", response_model=PolarStatus)
async def polar_live(
    solver: SolverPort = Depends(deps.get_solver),
) -> PolarStatus:
    """Start passive live adjustment loop — solves at current position, no slewing."""
    global _task, _state
    if _state.running:
        return _to_response()
    if _state.p1 is None or _state.p2 is None:
        _state.step      = "error"
        _state.error_msg = "No prior measurement — run /measure first"
        return _to_response()
    _state.running   = True
    _state.step      = "live"
    _state.error_msg = None
    _task = asyncio.create_task(
        _run_live(
            _state.p1, _state.p2, _state.exposure, _state.gain,
            _state.cam_index, _state.target_precision_arcmin, solver,
        )
    )
    return _to_response()


@router.post("/use_fallback_camera", response_model=PolarStatus)
async def polar_use_fallback_camera(
    req:    FallbackCameraRequest,
    mount:  MountPort  = Depends(deps.get_mount),
    solver: SolverPort = Depends(deps.get_solver),
) -> PolarStatus:
    """Restart measurement with a fallback camera after repeated solve failures."""
    global _task, _state
    if _state.running:
        return _to_response()
    if not _state.fallback_available:
        _state.step      = "error"
        _state.error_msg = "No fallback pending — call /measure first"
        return _to_response()
    precision  = req.target_precision_arcmin or _state.target_precision_arcmin
    ra_step_h  = _state.ra_step_h
    exposure   = _state.exposure
    gain       = _state.gain
    _state = _PolarState(running=True, target_precision_arcmin=precision)
    _task = asyncio.create_task(
        _run_measurement(
            ra_step_h, exposure, gain, req.camera_index,
            precision, mount, solver,
        )
    )
    return _to_response()


@router.post("/cancel")
def polar_cancel() -> dict[str, bool]:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _state.running = False
    _state.step    = "idle"
    return {"ok": True}


def _to_response() -> PolarStatus:
    return PolarStatus(
        running=_state.running,
        step=_state.step,
        progress=_state.progress,
        alt_error_arcmin=_state.alt_error_arcmin,
        az_error_arcmin=_state.az_error_arcmin,
        total_error_arcmin=_state.total_error_arcmin,
        pole_ra=_state.pole_ra,
        pole_dec=_state.pole_dec,
        correction_alt=_state.correction_alt,
        correction_az=_state.correction_az,
        quality_label=_state.quality_label,
        target_precision_arcmin=_state.target_precision_arcmin,
        target_reached=_state.target_reached,
        coarse_error_deg=_state.coarse_error_deg,
        solve_retries=_state.solve_retries,
        fallback_available=_state.fallback_available,
        warning_msg=_state.warning_msg,
        error_msg=_state.error_msg,
        checklist_confirmed=_checklist_confirmed,
    )
