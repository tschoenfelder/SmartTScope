"""Session lifecycle API — POST /api/session/connect, /run, /status, /stop."""

from __future__ import annotations

import io
import logging
import threading
import uuid
from pathlib import Path

import numpy as np
from astropy.io import fits
from fastapi import APIRouter, Depends, HTTPException, Query

_log = logging.getLogger(__name__)
from pydantic import BaseModel

from .. import config as _config
from ..domain.autofocus import FocusRunConfig
from ..adapters.astap.solver import catalog_search_paths as _catalog_search_paths
from ..adapters.astap.solver import find_astap as _find_astap
from ..adapters.astap.solver import find_catalog as _find_catalog
from ..domain.catalog import get_by_name as _catalog_get
from ..domain.solar import is_solar_target
from ..domain.states import SessionState
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..services.optical_train_registry import OpticalTrainRegistry
from ..workflow.runner import C8_BARLOW2X, C8_NATIVE, C8_REDUCER, OpticalProfile, VerticalSliceRunner
from . import deps

_PROFILES: dict[str, OpticalProfile] = {
    "c8_native":   C8_NATIVE,
    "c8_reducer":  C8_REDUCER,
    "c8_barlow2x": C8_BARLOW2X,
}

router = APIRouter(prefix="/api/session")


def _load_fits_master(path: str) -> np.ndarray:
    """Load a calibration master FITS from *path* and return its pixel array."""
    p = Path(path)
    if not p.exists():
        raise HTTPException(status_code=422, detail=f"Calibration master not found: {path}")
    try:
        with fits.open(io.BytesIO(p.read_bytes())) as hdul:
            return np.array(hdul[0].data, dtype=np.float32)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot read calibration FITS {path}: {exc}") from exc


def _apply_calibration(stacker, bias, dark, flat) -> None:  # noqa: ANN001
    if not any(x is not None for x in (bias, dark, flat)):
        return
    if hasattr(stacker, "set_calibration"):
        stacker.set_calibration(bias=bias, dark=dark, flat=flat)
        _log.info(
            "Calibration masters applied — bias=%s dark=%s flat=%s",
            bias is not None, dark is not None, flat is not None,
        )
    else:
        _log.warning("Stacker does not support set_calibration; calibration skipped")

# ── Session runner state ─────────────────────────────────────────────────────
# State lives in RuntimeContext so reset_for_tests() covers it automatically.

from ..runtime import get_runtime as _get_runtime
from ..services.job_manager import ResourceConflictError


def _reset_session() -> None:
    rt = _get_runtime()
    with rt.session_lock:
        rt.clear_session()
    rt.job_manager.cancel_by_name("session")


def get_active_runner() -> VerticalSliceRunner | None:
    return _get_runtime().get_active_runner()  # type: ignore[return-value]


def get_session_running() -> bool:
    return _get_runtime().is_session_running()

_ACTIONS: dict[str, str] = {
    "camera": "Check USB connection and power; ensure ToupTek driver is installed",
    "mount": "Check serial connection and OnStep power; verify onstep_port in smart_telescope.toml",
    "focuser": "Check focuser serial connection and power",
}

_ASTAP_INSTALL_URL = "https://www.hnsky.org/astap.htm"


class DeviceResult(BaseModel):
    status: str           # "ok" or "error"
    error: str | None = None
    action: str | None = None


class ConnectResult(BaseModel):
    camera: DeviceResult
    mount: DeviceResult
    focuser: DeviceResult
    solver: DeviceResult


def _try_connect(device: str, connect_fn: object) -> DeviceResult:
    try:
        ok: bool = connect_fn()  # type: ignore[operator]
        if ok:
            return DeviceResult(status="ok")
        return DeviceResult(
            status="error",
            error=f"{device.capitalize()} refused connection",
            action=_ACTIONS[device],
        )
    except Exception as exc:
        return DeviceResult(
            status="error",
            error=str(exc),
            action=_ACTIONS[device],
        )


def _check_solver() -> DeviceResult:
    astap = _find_astap()
    if astap is None:
        return DeviceResult(
            status="error",
            error="ASTAP executable not found",
            action=f"Install ASTAP from {_ASTAP_INSTALL_URL}",
        )
    catalog_dir = _config.ASTAP_CATALOG_DIR or None
    catalog = _find_catalog(astap, catalog_dir=catalog_dir)
    if catalog is None:
        searched = ", ".join(_catalog_search_paths(astap, catalog_dir))
        return DeviceResult(
            status="error",
            error="ASTAP star catalog not found",
            action=(
                f"Download the D80 catalog from {_ASTAP_INSTALL_URL} and extract .290 files "
                f"to one of: {searched} — or set catalog_dir in smart_telescope.toml"
            ),
        )
    return DeviceResult(status="ok")


@router.post("/connect", response_model=ConnectResult)
def session_connect(
    camera: CameraPort = Depends(deps.get_camera),
    mount: MountPort = Depends(deps.get_mount),
    focuser: FocuserPort = Depends(deps.get_focuser),
) -> ConnectResult:
    from .cameras import invalidate_camera_scan
    invalidate_camera_scan()  # force re-enumeration after hardware may have been plugged in
    return ConnectResult(
        camera=_try_connect("camera", camera.connect),
        mount=_try_connect("mount", mount.connect),
        focuser=_try_connect("focuser", focuser.connect),
        solver=_check_solver(),
    )


# ── Run / Status / Stop ──────────────────────────────────────────────────────


class RunResponse(BaseModel):
    session_id: str
    state: str


class SessionStatusResponse(BaseModel):
    running: bool
    session_id: str | None = None
    state: str | None = None
    frames_integrated: int = 0
    frames_rejected: int = 0
    centering_offset_arcmin: float = 0.0
    autofocus_best_position: int | None = None
    autofocus_metric_gain: float | None = None
    refocus_count: int = 0
    warnings: list[str] = []
    failure_stage: str | None = None
    failure_reason: str | None = None
    saved_image_path: str | None = None


@router.post("/run", response_model=RunResponse, status_code=202)
def session_run(
    target: str = Query(default="M42", min_length=1, max_length=16),
    profile: str = Query(default="c8_native"),
    confirm_solar: bool = Query(default=False),
    exposure: float = Query(default=30.0, gt=0.0, le=300.0),
    stack_depth: int = Query(default=10, ge=1, le=100),
    preview_exposure: float = Query(default=5.0, gt=0.0, le=60.0),
    autofocus_range: int = Query(default=200, ge=10, le=2000),
    autofocus_step: int = Query(default=20, ge=1, le=500),
    autofocus_exposure: float = Query(default=3.0, gt=0.0, le=30.0),
    autofocus_backlash: int = Query(default=0, ge=0, le=500),
    skip_autofocus: bool = Query(default=False),
    refocus_temp_delta: float = Query(default=1.0, gt=0.0, le=20.0),
    refocus_alt_delta: float = Query(default=5.0, gt=0.0, le=90.0),
    refocus_elapsed_min: float = Query(default=30.0, gt=0.0, le=480.0),
    enable_refocus: bool = Query(default=True),
    enable_quality_filter: bool = Query(default=True),
    quality_min_snr: float = Query(default=0.3, ge=0.0, le=1.0),
    quality_baseline_frames: int = Query(default=3, ge=1, le=20),
    bias_path: str | None = Query(default=None, description="Absolute path to master bias FITS"),
    dark_path: str | None = Query(default=None, description="Absolute path to master dark FITS"),
    flat_path: str | None = Query(default=None, description="Absolute path to master flat FITS"),
    mount: MountPort = Depends(deps.get_mount),
    focuser: FocuserPort = Depends(deps.get_focuser),
    registry: OpticalTrainRegistry = Depends(deps.get_optical_train_registry),
) -> RunResponse:
    target_obj = _catalog_get(target)
    if target_obj is None:
        raise HTTPException(status_code=422, detail=f"Target '{target}' not found in catalog")
    optical_profile = _PROFILES.get(profile)
    if optical_profile is None:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown profile '{profile}'. Valid: {', '.join(_PROFILES)}",
        )
    if not confirm_solar:
        blocked, sep = is_solar_target(target_obj.ra_hours, target_obj.dec_deg)
        if blocked:
            raise HTTPException(
                status_code=403,
                detail={"error": "solar_exclusion", "sun_separation_deg": round(sep, 2)},
            )

    # Resolve main camera from optical train; fall back to index 0 if unconfigured
    main_train = registry.main() if registry is not None else None
    if main_train is not None:
        camera: CameraPort = deps.get_camera_by_role(main_train.camera_role)
        camera_resource = f"camera:{main_train.camera_index}"
    else:
        camera = deps.get_camera()
        camera_resource = "camera:0"

    bias_arr = _load_fits_master(bias_path) if bias_path else None
    dark_arr = _load_fits_master(dark_path) if dark_path else None
    flat_arr = _load_fits_master(flat_path) if flat_path else None

    rt = _get_runtime()
    try:
        jm_job = rt.job_manager.claim("session", {camera_resource, "mount", "focuser"})
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))

    try:
        with rt.session_lock:
            stacker = deps.get_stacker()
            _apply_calibration(stacker, bias_arr, dark_arr, flat_arr)
            session_id = str(uuid.uuid4())
            runner = VerticalSliceRunner(
                camera=camera,
                mount=mount,
                solver=deps.get_solver(),
                stacker=stacker,
                storage=deps.get_storage(),
                focuser=focuser,
                optical_profile=optical_profile,
                target_name=target_obj.name,
                target_ra=target_obj.ra_hours,
                target_dec=target_obj.dec_deg,
                stack_exposure_s=exposure,
                stack_depth=stack_depth,
                preview_exposure_s=preview_exposure,
                focus_config=FocusRunConfig(
                    range_steps=autofocus_range,
                    step_size=autofocus_step,
                    exposure_s=autofocus_exposure,
                    backlash_steps=autofocus_backlash,
                    skip=skip_autofocus,
                ),
                enable_refocus_triggers=enable_refocus,
                refocus_temp_delta_c=refocus_temp_delta,
                refocus_alt_delta_deg=refocus_alt_delta,
                refocus_elapsed_min=refocus_elapsed_min,
                enable_frame_quality=enable_quality_filter,
                frame_quality_min_snr=quality_min_snr,
                frame_quality_baseline_frames=quality_baseline_frames,
            )

            def _session_thread() -> None:
                try:
                    runner.run(session_id=session_id)
                finally:
                    rt.job_manager.release(jm_job.job_id)

            thread = threading.Thread(target=_session_thread, daemon=True)
            rt.set_session(runner, thread)
            thread.start()
    except Exception:
        rt.job_manager.release(jm_job.job_id, error="setup failed")
        raise

    return RunResponse(session_id=session_id, state=SessionState.IDLE.name)


@router.get("/status", response_model=SessionStatusResponse)
def session_status() -> SessionStatusResponse:
    rt = _get_runtime()
    runner = rt.get_active_runner()
    running = rt.is_session_running()
    if runner is None:
        return SessionStatusResponse(running=False)
    log = runner.current_log
    if log is None:
        return SessionStatusResponse(running=running)
    return SessionStatusResponse(
        running=running,
        session_id=log.session_id,
        state=log.state.name,
        frames_integrated=log.frames_integrated,
        frames_rejected=log.frames_rejected,
        centering_offset_arcmin=log.centering_offset_arcmin,
        autofocus_best_position=log.autofocus_best_position,
        autofocus_metric_gain=log.autofocus_metric_gain,
        refocus_count=log.refocus_count,
        warnings=list(log.warnings),
        failure_stage=log.failure_stage,
        failure_reason=log.failure_reason,
        saved_image_path=log.saved_image_path,
    )


@router.post("/stop", status_code=204)
def session_stop() -> None:
    runner = _get_runtime().get_active_runner()
    if runner is None:
        raise HTTPException(status_code=404, detail="No active session")
    runner.stop()  # type: ignore[union-attr]
