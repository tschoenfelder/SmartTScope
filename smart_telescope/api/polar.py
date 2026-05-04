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
    SkyPoint,
    compute_polar_error,
    find_rotation_pole,
)
from ..ports.mount import MountPort, MountState
from ..ports.solver import SolverPort
from . import deps

router = APIRouter(prefix="/api/polar")

Step = Literal[
    "idle", "slewing", "solving_1", "solving_2", "solving_3",
    "computing", "done", "refining", "error",
]


@dataclass
class _PolarState:
    running: bool = False
    step: Step = "idle"
    progress: int = 0
    alt_error_arcmin: float | None = None
    az_error_arcmin: float | None = None
    total_error_arcmin: float | None = None
    pole_ra: float | None = None
    pole_dec: float | None = None
    error_msg: str | None = None
    # cached for live refine — set after measurement completes
    p2: SkyPoint | None = None
    p3: SkyPoint | None = None
    cam_index: int = 0
    exposure: float = 5.0
    gain: int = 100


_state = _PolarState()
_task: asyncio.Task | None = None


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


async def _run_measurement(
    ra_step_h: float,
    exposure: float,
    gain: int,
    camera_index: int,
    mount: MountPort,
    solver: SolverPort,
) -> None:
    global _state
    try:
        camera = deps.get_preview_camera(camera_index)
        if hasattr(camera, "set_gain"):
            camera.set_gain(gain)  # type: ignore[union-attr]
        scale = config.PIXEL_SCALE_ARCSEC

        # Unpark if needed
        if await asyncio.to_thread(mount.get_state) == MountState.PARKED:
            await asyncio.to_thread(mount.unpark)
            await asyncio.sleep(1.0)

        # ── position 1: home (Dec 89°, HA = 0 → RA = LST) ───────────────────
        _state.step = "slewing"; _state.progress = 8
        lst = _get_lst()
        ra1 = lst % 24.0
        if not await asyncio.to_thread(mount.goto, ra1, 89.0):
            raise RuntimeError("GoTo home failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 1 timed out")
        await asyncio.sleep(1.5)     # brief settle

        _state.step = "solving_1"; _state.progress = 20
        frame = await asyncio.to_thread(camera.capture, exposure)
        r1    = await asyncio.to_thread(solver.solve, frame, scale)
        if not r1.success:
            raise RuntimeError(f"Solve 1 failed: {r1.error}")
        p1 = SkyPoint(ra=r1.ra, dec=r1.dec)

        # ── position 2: RA + step ─────────────────────────────────────────────
        _state.step = "slewing"; _state.progress = 38
        if not await asyncio.to_thread(mount.goto, (ra1 + ra_step_h) % 24.0, 89.0):
            raise RuntimeError("GoTo position 2 failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 2 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_2"; _state.progress = 55
        frame = await asyncio.to_thread(camera.capture, exposure)
        r2    = await asyncio.to_thread(solver.solve, frame, scale)
        if not r2.success:
            raise RuntimeError(f"Solve 2 failed: {r2.error}")
        p2 = SkyPoint(ra=r2.ra, dec=r2.dec)

        # ── position 3: RA + 2×step ───────────────────────────────────────────
        _state.step = "slewing"; _state.progress = 65
        if not await asyncio.to_thread(mount.goto, (ra1 + 2 * ra_step_h) % 24.0, 89.0):
            raise RuntimeError("GoTo position 3 failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 3 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_3"; _state.progress = 82
        frame = await asyncio.to_thread(camera.capture, exposure)
        r3    = await asyncio.to_thread(solver.solve, frame, scale)
        if not r3.success:
            raise RuntimeError(f"Solve 3 failed: {r3.error}")
        p3 = SkyPoint(ra=r3.ra, dec=r3.dec)

        # cache for live refine
        _state.p2 = p2
        _state.p3 = p3
        _state.cam_index = camera_index
        _state.exposure = exposure
        _state.gain = gain

        # ── compute pole and errors ────────────────────────────────────────────
        _state.step = "computing"; _state.progress = 93
        pole = find_rotation_pole(p1, p2, p3)
        err  = compute_polar_error(pole, config.OBSERVER_LAT, _get_lst())

        _state.pole_ra             = pole.ra
        _state.pole_dec            = pole.dec
        _state.alt_error_arcmin    = err.alt_error_arcmin
        _state.az_error_arcmin     = err.az_error_arcmin
        _state.total_error_arcmin  = err.total_error_arcmin

        # Return to first position
        with contextlib.suppress(Exception):
            await asyncio.to_thread(mount.goto, ra1, 89.0)

        _state.step = "done"; _state.progress = 100

    except Exception as exc:
        _state.step      = "error"
        _state.error_msg = str(exc)
    finally:
        _state.running = False


async def _run_refine(
    p2_target: SkyPoint,
    p3_target: SkyPoint,
    exposure: float,
    gain: int,
    camera_index: int,
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
        _state.step = "slewing"; _state.progress = 8
        lst = _get_lst()
        ra1 = lst % 24.0
        if not await asyncio.to_thread(mount.goto, ra1, 89.0):
            raise RuntimeError("GoTo home failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 1 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_1"; _state.progress = 20
        frame = await asyncio.to_thread(camera.capture, exposure)
        r1    = await asyncio.to_thread(solver.solve, frame, scale)
        if not r1.success:
            raise RuntimeError(f"Solve 1 failed: {r1.error}")
        p1 = SkyPoint(ra=r1.ra, dec=r1.dec)

        # position 2: cached RA from prior measurement
        _state.step = "slewing"; _state.progress = 38
        if not await asyncio.to_thread(mount.goto, p2_target.ra, 89.0):
            raise RuntimeError("GoTo position 2 failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 2 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_2"; _state.progress = 55
        frame = await asyncio.to_thread(camera.capture, exposure)
        r2    = await asyncio.to_thread(solver.solve, frame, scale)
        if not r2.success:
            raise RuntimeError(f"Solve 2 failed: {r2.error}")
        p2 = SkyPoint(ra=r2.ra, dec=r2.dec)

        # position 3: cached RA from prior measurement
        _state.step = "slewing"; _state.progress = 65
        if not await asyncio.to_thread(mount.goto, p3_target.ra, 89.0):
            raise RuntimeError("GoTo position 3 failed")
        if not await _wait_not_slewing(mount):
            raise RuntimeError("Slew to position 3 timed out")
        await asyncio.sleep(1.5)

        _state.step = "solving_3"; _state.progress = 82
        frame = await asyncio.to_thread(camera.capture, exposure)
        r3    = await asyncio.to_thread(solver.solve, frame, scale)
        if not r3.success:
            raise RuntimeError(f"Solve 3 failed: {r3.error}")
        p3 = SkyPoint(ra=r3.ra, dec=r3.dec)

        # compute updated error
        _state.step = "computing"; _state.progress = 93
        pole = find_rotation_pole(p1, p2, p3)
        err  = compute_polar_error(pole, config.OBSERVER_LAT, _get_lst())

        _state.pole_ra            = pole.ra
        _state.pole_dec           = pole.dec
        _state.alt_error_arcmin   = err.alt_error_arcmin
        _state.az_error_arcmin    = err.az_error_arcmin
        _state.total_error_arcmin = err.total_error_arcmin
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


# ── models ────────────────────────────────────────────────────────────────────

class MeasureRequest(BaseModel):
    ra_step_h:    float = Field(default=1.0, gt=0.1, le=3.0,  description="RA rotation step in hours")
    exposure:     float = Field(default=5.0, gt=0.0, le=60.0)
    gain:         int   = Field(default=100, ge=100, le=3200)
    camera_index: int   = Field(default=0,   ge=0,   le=7)


class RefineRequest(BaseModel):
    exposure: float | None = Field(default=None, gt=0.0, le=60.0)
    gain:     int   | None = Field(default=None, ge=100, le=3200)


class PolarStatus(BaseModel):
    running:              bool
    step:                 str
    progress:             int
    alt_error_arcmin:     float | None = None
    az_error_arcmin:      float | None = None
    total_error_arcmin:   float | None = None
    pole_ra:              float | None = None
    pole_dec:             float | None = None
    error_msg:            str | None   = None


# ── endpoints ─────────────────────────────────────────────────────────────────

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
    _state = _PolarState(running=True)
    _task = asyncio.create_task(
        _run_measurement(req.ra_step_h, req.exposure, req.gain, req.camera_index, mount, solver)
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
    """Re-run measurement using cached positions — call after adjusting screws."""
    global _task, _state
    if _state.running:
        return _to_response()
    if _state.p2 is None or _state.p3 is None:
        _state.step      = "error"
        _state.error_msg = "No prior measurement — run /measure first"
        return _to_response()
    exposure = req.exposure if req.exposure is not None else _state.exposure
    gain     = req.gain     if req.gain     is not None else _state.gain
    _state.running   = True
    _state.step      = "refining"
    _state.error_msg = None
    _task = asyncio.create_task(
        _run_refine(_state.p2, _state.p3, exposure, gain, _state.cam_index, mount, solver)
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
        error_msg=_state.error_msg,
    )
