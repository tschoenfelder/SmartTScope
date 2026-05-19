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
from ..domain.polar_workflow import (
    AlignmentResult,
    PolarAlignmentWorkflow,
    SolveResult as DomainSolveResult,
    WorkflowInput,
)
from ..domain.visibility import HorizonProfile, load_horizon
from ..ports.mount import MountPort, MountState
from ..ports.solver import SolverPort
from . import deps

router = APIRouter(prefix="/api/polar")

_HORIZON: HorizonProfile | None = load_horizon(config.HORIZON_DAT)

Step = Literal[
    "idle", "slewing",
    "solving_1", "solving_2", "solving_3",
    "coarse_required",           # mount too far from NCP; manual repositioning needed
    "computing", "done",
    "refining",                  # re-measure using cached RA positions
    "live",                      # passive no-slew solve loop during fine adjustment
    "camera_fallback_offered",   # repeated solve failures; guide camera offered
    "error",
]

# Maps action.message → (step, progress) for UI progress reporting
_ACTION_PROGRESS: dict[str, tuple[str, int]] = {
    "Slewing to HOME position":                  ("slewing",   8),
    "Capturing HOME frame":                      ("solving_1", 20),
    "Slewing to position 2":                     ("slewing",   38),
    "Capturing position 2 frame":                ("solving_2", 55),
    "Solve 2 failed — retrying at alternate RA": ("slewing",   40),
    "Capturing position 2 retry":                ("solving_2", 55),
    "Slewing to position 3":                     ("slewing",   65),
    "Capturing position 3 frame":                ("solving_3", 82),
    "Solve 3 failed — retrying at alternate RA": ("slewing",   67),
    "Capturing position 3 retry":                ("solving_3", 82),
}


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
    # guidance
    correction_alt: str | None = None
    correction_az: str | None = None
    quality_label: str | None = None
    target_precision_arcmin: float = Precision.GOOD_IMAGING
    target_reached: bool = False
    # messages
    error_msg: str | None = None
    warning_msg: str | None = None
    # coarse check
    coarse_error_deg: float | None = None
    # cached for refine / live
    p1: SkyPoint | None = None
    p2: SkyPoint | None = None
    p3: SkyPoint | None = None
    cam_index: int = 0
    exposure: float = 5.0
    gain: int = 100
    ra_step_h: float = 1.0
    # retry / fallback
    solve_retries: int = 0
    fallback_available: bool = False


_state = _PolarState()
_task: asyncio.Task | None = None
_checklist_confirmed: bool = False   # persists within server session


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


def _apply_alignment_result(result: AlignmentResult) -> None:
    """Write all fields from a workflow AlignmentResult into _state."""
    _state.pole_ra            = result.pole_ra
    _state.pole_dec           = result.pole_dec
    _state.alt_error_arcmin   = result.alt_error_arcmin
    _state.az_error_arcmin    = result.az_error_arcmin
    _state.total_error_arcmin = result.total_error_arcmin
    _state.correction_alt     = result.correction_alt
    _state.correction_az      = result.correction_az
    _state.quality_label      = result.quality_label
    _state.target_reached     = result.target_reached
    _state.coarse_error_deg   = result.coarse_error_deg
    _state.warning_msg        = result.warning_msg
    _state.solve_retries      = result.solve_retries
    _state.p1                 = result.p1
    _state.p2                 = result.p2
    _state.p3                 = result.p3


def _update_result_from_domain(pole: SkyPoint, err, precision: float) -> None:
    """Write computed polar error into _state (used by live loop)."""
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

async def _run_workflow_loop(
    workflow: PolarAlignmentWorkflow,
    mount: MountPort,
    solver: SolverPort,
    camera_index: int,
    exposure: float,
    gain: int,
) -> None:
    """Execute the polar-alignment workflow state machine against real hardware."""
    global _state
    try:
        camera = deps.get_preview_camera(camera_index)
        if hasattr(camera, "set_gain"):
            camera.set_gain(gain)  # type: ignore[union-attr]
        scale = config.PIXEL_SCALE_ARCSEC

        if await asyncio.to_thread(mount.get_state) == MountState.PARKED:
            await asyncio.to_thread(mount.unpark)
            await asyncio.sleep(1.0)

        inp = WorkflowInput(lst=_get_lst(), observer_lat=config.OBSERVER_LAT)

        while True:
            act = workflow.next_action(inp)

            step, progress = _ACTION_PROGRESS.get(act.message or "", (_state.step, _state.progress))
            _state.step     = step
            _state.progress = progress

            if act.kind == "SLEW_TO_RA":
                assert act.ra_h is not None
                ok = await asyncio.to_thread(mount.goto, act.ra_h, act.dec_deg)
                if ok:
                    ok = await _wait_not_slewing(mount)
                if ok:
                    await asyncio.sleep(1.5)
                inp = WorkflowInput(
                    lst=_get_lst(),
                    observer_lat=config.OBSERVER_LAT,
                    slew_ok=ok,
                )

            elif act.kind == "CAPTURE_AND_SOLVE":
                frame = await asyncio.to_thread(camera.capture, exposure)
                r     = await asyncio.to_thread(solver.solve, frame, scale)
                sr    = DomainSolveResult(
                    success=r.success,
                    ra=r.ra   if r.success else 0.0,
                    dec=r.dec if r.success else 0.0,
                    error=r.error or "" if not r.success else "",
                )
                inp = WorkflowInput(
                    lst=_get_lst(),
                    observer_lat=config.OBSERVER_LAT,
                    solve_result=sr,
                )

            elif act.kind == "DISPLAY_RESULT":
                assert act.result is not None
                _state.step = "computing"; _state.progress = 93
                _apply_alignment_result(act.result)
                _state.cam_index = camera_index
                _state.exposure  = exposure
                _state.gain      = gain
                with contextlib.suppress(Exception):
                    await asyncio.to_thread(mount.goto, workflow.home_ra, 89.0)
                _state.step = "done"; _state.progress = 100
                break

            elif act.kind == "COARSE_REQUIRED":
                _state.step            = "coarse_required"
                _state.coarse_error_deg = act.coarse_error_deg
                _state.error_msg       = act.message
                break

            elif act.kind == "FAILED":
                if act.camera_fallback_suggested:
                    _state.fallback_available = True
                    _state.step      = "camera_fallback_offered"
                    _state.error_msg = (
                        "Plate solve failed twice — guide camera fallback available. "
                        "Call POST /api/polar/use_fallback_camera with a camera_index."
                    )
                else:
                    _state.step      = "error"
                    _state.error_msg = act.message
                break

    except asyncio.CancelledError:
        raise
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
                    _update_result_from_domain(pole, err, precision)
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
    _state = _PolarState(
        running=True,
        ra_step_h=req.ra_step_h,
        exposure=req.exposure,
        gain=req.gain,
        cam_index=req.camera_index,
        target_precision_arcmin=req.target_precision_arcmin,
    )
    workflow = PolarAlignmentWorkflow(
        ra_step_h=req.ra_step_h,
        target_precision_arcmin=req.target_precision_arcmin,
        observer_lat=config.OBSERVER_LAT,
        observer_lon=config.OBSERVER_LON,
        ha_east_limit_h=config.MOUNT_HA_EAST_LIMIT_H,
        ha_west_limit_h=config.MOUNT_HA_WEST_LIMIT_H,
        horizon=_HORIZON,
    )
    _task = asyncio.create_task(
        _run_workflow_loop(workflow, mount, solver, req.camera_index, req.exposure, req.gain)
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
    p2_ra = _state.p2.ra
    p3_ra = _state.p3.ra
    cam   = _state.cam_index
    step  = _state.ra_step_h
    _state.running   = True
    _state.step      = "refining"
    _state.error_msg = None
    workflow = PolarAlignmentWorkflow(
        ra_step_h=step,
        target_precision_arcmin=precision,
        observer_lat=config.OBSERVER_LAT,
        observer_lon=config.OBSERVER_LON,
        ha_east_limit_h=config.MOUNT_HA_EAST_LIMIT_H,
        ha_west_limit_h=config.MOUNT_HA_WEST_LIMIT_H,
        horizon=_HORIZON,
        pos2_ra_override=p2_ra,
        pos3_ra_override=p3_ra,
    )
    _task = asyncio.create_task(
        _run_workflow_loop(workflow, mount, solver, cam, exposure, gain)
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
    precision = req.target_precision_arcmin or _state.target_precision_arcmin
    ra_step_h = _state.ra_step_h
    exposure  = _state.exposure
    gain      = _state.gain
    _state = _PolarState(
        running=True,
        ra_step_h=ra_step_h,
        exposure=exposure,
        gain=gain,
        cam_index=req.camera_index,
        target_precision_arcmin=precision,
    )
    workflow = PolarAlignmentWorkflow(
        ra_step_h=ra_step_h,
        target_precision_arcmin=precision,
        observer_lat=config.OBSERVER_LAT,
        observer_lon=config.OBSERVER_LON,
        ha_east_limit_h=config.MOUNT_HA_EAST_LIMIT_H,
        ha_west_limit_h=config.MOUNT_HA_WEST_LIMIT_H,
        horizon=_HORIZON,
    )
    _task = asyncio.create_task(
        _run_workflow_loop(workflow, mount, solver, req.camera_index, exposure, gain)
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
