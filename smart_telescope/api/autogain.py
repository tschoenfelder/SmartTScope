"""One-shot Auto Gain API — POST /api/autogain/run, GET /api/autogain/status."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..domain.autogain import AutoGainMode
from ..domain.autogain_service import AutoGainResult, AutoGainService, AutoGainStatus
from ..domain.camera_profile import ALL_PROFILES, CameraProfile
from ..domain.last_good_settings import LastGoodSettings, LastGoodStore
from . import deps

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/autogain")

_DEFAULT_APP_STATE = Path.home() / ".SmartTScope"


def _app_state_dir() -> Path:
    d = config.APP_STATE_DIR
    return Path(d) if d else _DEFAULT_APP_STATE


# ── Request / Response models ─────────────────────────────────────────────────

_DIAGNOSTIC_EXP_MS = 10_000.0  # extended exposure for diagnostic runs


class RunRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    camera_role: str | None = Field(default=None, description="Optical train role (preferred over camera_index if configured)")
    mode: str = Field(default="DSO")
    camera_model: str | None = Field(default=None, description="Profile model name (e.g. ATR585M)")
    max_iterations: int = Field(default=12, ge=1, le=30)
    diagnostic: bool = Field(default=False, description="Extend max exposure to 10 s for no-signal diagnosis")


class AutoGainStatusResponse(BaseModel):
    running: bool
    diagnostic: bool = False
    cancelling: bool = False   # True after cancel requested, before thread exits
    status: str | None = None
    exposure_ms: float | None = None
    gain: int | None = None
    offset: int | None = None
    conversion_gain: str | None = None
    warning_msg: str | None = None
    error: str | None = None


# ── Job state ─────────────────────────────────────────────────────────────────
# Owned by RuntimeContext so reset_for_tests() covers it automatically.

from ..runtime import get_runtime as _get_runtime
from ..services.job_manager import ResourceConflictError


@dataclass
class _Job:
    running: bool
    diagnostic: bool = False
    cancelling: bool = False
    result: AutoGainResult | None = None
    error: str | None = None
    cancel: threading.Event = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.cancel is None:
            self.cancel = threading.Event()


def _get_job() -> _Job | None:
    return _get_runtime().get_autogain_job()  # type: ignore[return-value]


def _set_job(job: _Job | None) -> None:
    _get_runtime().set_autogain_job(job)


# ── Background worker ─────────────────────────────────────────────────────────

def _worker(
    job: _Job,
    camera_index: int,
    profile: CameraProfile,
    mode: AutoGainMode,
    max_iterations: int,
) -> None:
    rt = _get_runtime()
    try:
        camera = deps.get_preview_camera(camera_index)
    except Exception as exc:
        with rt.autogain_lock:
            job.running = False
            job.error = str(exc)
        return

    try:
        focuser_available = deps.get_focuser().is_available
        # Per-train focuser capability (BUG-024): a guide camera with no focuser
        # configured should never receive POSSIBLE_FOCUS_OR_POINTING_ERROR even
        # when the mount's focuser (for the main train) is available.
        has_focuser = focuser_available
        try:
            registry = deps.get_optical_train_registry()
            train = registry.by_camera_index(camera_index)
            if train is not None:
                has_focuser = train.has_focuser and focuser_available
        except Exception:
            pass
        result = AutoGainService.run_one_shot(
            camera=camera,
            profile=profile,
            mode=mode,
            cancellation_flag=job.cancel,
            max_iterations=max_iterations,
            has_focuser=has_focuser,
            offset_service=rt.camera_offset_service,
        )
    except Exception as exc:
        _log.error("AutoGain worker error: %s", exc)
        with rt.autogain_lock:
            job.running = False
            job.error = str(exc)
        return

    # Persist last-good on success
    if result.status == AutoGainStatus.OK:
        _save_last_good(result, profile, mode)

    with rt.autogain_lock:
        job.running = False
        job.result = result

    _log.info(
        "AutoGain complete: status=%s exp=%.1fms gain=%d offset=%d cg=%s",
        result.status, result.exposure_ms, result.gain, result.offset,
        result.conversion_gain.name if result.conversion_gain else "?",
    )


def _save_last_good(
    result: AutoGainResult,
    profile: CameraProfile,
    mode: AutoGainMode,
) -> None:
    try:
        store = LastGoodStore(_app_state_dir())
        lg = LastGoodSettings(
            camera_model=profile.model,
            camera_serial="",
            mode=mode.value,
            gain=result.gain,
            exposure_ms=result.exposure_ms,
            offset=result.offset,
            conversion_gain=result.conversion_gain.name if result.conversion_gain else "LCG",
            saved_at=_utc_now(),
        )
        store.save(lg)
        _log.info("LastGood saved: model=%s mode=%s", profile.model, mode.value)
    except Exception as exc:
        _log.warning("LastGood save failed: %s", exc)


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/run", status_code=202)
def run_autogain(req: RunRequest) -> dict:
    """Start a one-shot auto-gain run in the background.

    Returns 202 immediately.  Poll GET /api/autogain/status for results.
    Returns 409 if a run is already in progress.
    Returns 400 if the camera_model is unknown.
    """
    rt = _get_runtime()

    # Resolve profile
    profile: CameraProfile | None = None
    if req.camera_model:
        profile = ALL_PROFILES.get(req.camera_model)
        if profile is None:
            raise HTTPException(status_code=400, detail=f"Unknown camera model: {req.camera_model!r}")

    if profile is None:
        # Use a permissive fallback profile with wide limits
        from ..domain.camera_profile import ATR585M
        profile = ATR585M

    # Extend max exposure for diagnostic runs (FR-AG-040)
    if req.diagnostic and profile.max_preview_exp_ms < _DIAGNOSTIC_EXP_MS:
        from dataclasses import replace as _dc_replace
        profile = _dc_replace(profile, max_preview_exp_ms=_DIAGNOSTIC_EXP_MS)

    # Resolve mode
    try:
        mode = AutoGainMode(req.mode)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unknown mode: {req.mode!r}")

    # Resolve camera_role → camera_index (R4-005)
    camera_index = req.camera_index
    if req.camera_role:
        try:
            registry = deps.get_optical_train_registry()
            train = registry.by_camera_role(req.camera_role) or registry.get(req.camera_role)
            if train is not None:
                camera_index = train.camera_index
        except Exception:
            pass

    job = _Job(running=True, diagnostic=req.diagnostic)
    try:
        rt.job_manager.submit(
            "autogain",
            {f"camera:{camera_index}"},
            _worker,
            job, camera_index, profile, mode, req.max_iterations,
            cancel_event=job.cancel,
            timeout_s=300,
        )
    except ResourceConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    with rt.autogain_lock:
        _set_job(job)
    _log.info("AutoGain started: camera_index=%d camera_role=%s model=%s mode=%s",
              camera_index, req.camera_role or "(by index)", profile.model, mode.value)
    return {"started": True}


@router.get("/status", response_model=AutoGainStatusResponse)
def get_status() -> AutoGainStatusResponse:
    """Return the current auto-gain state.  Always 200.

    *running* is True while a run is in progress.
    When a result is available, all result fields are populated.
    """
    rt = _get_runtime()
    with rt.autogain_lock:
        j = _get_job()

    if j is None:
        return AutoGainStatusResponse(running=False)

    if j.running:
        return AutoGainStatusResponse(running=True, diagnostic=j.diagnostic, cancelling=j.cancelling)

    if j.error:
        return AutoGainStatusResponse(running=False, diagnostic=j.diagnostic, error=j.error)

    r = j.result
    if r is None:
        return AutoGainStatusResponse(running=False, diagnostic=j.diagnostic)

    # If cancel was requested but the job completed before the worker saw the
    # flag (race: worker finished POSSIBLE_FOCUS_OR_POINTING_ERROR right as the
    # cancel arrived), report CANCELLED so the UI never shows a stale warning
    # after the user clicked Cancel.
    if j.cancelling and r.status != AutoGainStatus.CANCELLED:
        return AutoGainStatusResponse(
            running=False,
            diagnostic=j.diagnostic,
            status=AutoGainStatus.CANCELLED.value,
        )

    return AutoGainStatusResponse(
        running=False,
        diagnostic=j.diagnostic,
        status=r.status.value,
        exposure_ms=round(r.exposure_ms, 3),
        gain=r.gain,
        offset=r.offset,
        conversion_gain=r.conversion_gain.name if r.conversion_gain else None,
        warning_msg=r.warning_msg,
    )


@router.post("/cancel", status_code=200)
def cancel_autogain() -> dict:
    """Cancel an in-progress auto-gain run.  No-op if idle."""
    rt = _get_runtime()
    with rt.autogain_lock:
        j = _get_job()
    if j is not None and j.running:
        j.cancel.set()
        with rt.autogain_lock:
            j.cancelling = True
        _log.info("AutoGain cancellation requested")
    return {"cancelled": True}


def _reset() -> None:
    """Clear state (used by tests)."""
    rt = _get_runtime()
    with rt.autogain_lock:
        j = _get_job()
        if j is not None and j.running:
            j.cancel.set()
        _set_job(None)
    rt.job_manager.cancel_by_name("autogain")
