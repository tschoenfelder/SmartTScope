"""Bias-frame offset estimation wizard API — /api/bias_estimation endpoints."""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..api import deps
from ..domain.camera_capabilities import ConversionGain
from ..services.bias_estimation_service import BiasEstimationService
from ..domain.bias_estimation import DEFAULT_SWEEP_OFFSETS

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bias_estimation")

# ── Valid conversion gain names ───────────────────────────────────────────────

_VALID_CG = {cg.name: cg for cg in ConversionGain}

# ── Job registry ──────────────────────────────────────────────────────────────


@dataclass
class _JobState:
    job_id: str
    status: str = "RUNNING"   # "RUNNING" | "DONE" | "FAILED" | "CANCELLED"
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)


_jobs: dict[str, _JobState] = {}
_jobs_lock = threading.Lock()


def _register_job() -> _JobState:
    job = _JobState(job_id=str(uuid.uuid4()))
    with _jobs_lock:
        _jobs[job.job_id] = job
    return job


def _get_job(job_id: str) -> _JobState | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def _reset_jobs() -> None:
    with _jobs_lock:
        _jobs.clear()


# ── Request / response models ─────────────────────────────────────────────────


class BiasEstimationRequest(BaseModel):
    camera_role: str = Field(default="main", description="Camera role: main | guide | atr")
    gain_mode: str = Field(description="Conversion gain mode: LCG | HCG | HDR")
    frame_count: int = Field(default=10, ge=1, le=200)
    run_sweep: bool = Field(default=True, description="When True, sweep all DEFAULT_SWEEP_OFFSETS; when False, test only offset 0")

    @field_validator("gain_mode")
    @classmethod
    def validate_gain_mode(cls, v: str) -> str:
        key = v.upper()
        if key not in _VALID_CG:
            raise ValueError(
                f"Unknown gain_mode '{v}'. Valid values: {list(_VALID_CG)}"
            )
        return key


class BiasEstimationStartResponse(BaseModel):
    job_id: str
    status: str = "RUNNING"


class SweepPointResponse(BaseModel):
    offset: int
    zero_fraction: float
    min_val: float
    is_safe: bool


class BiasEstimationStatusResponse(BaseModel):
    job_id: str
    status: str                          # RUNNING | DONE | FAILED | CANCELLED
    error: str | None = None
    # Fields populated when status == DONE
    camera_model: str | None = None
    gain_mode: str | None = None
    frame_count: int | None = None
    recommended_offset: int | None = None
    safe: bool | None = None
    toml_snippet: str | None = None
    sweep: list[SweepPointResponse] = []


# ── Camera resolution helper ──────────────────────────────────────────────────


def _get_camera_for_role(camera_role: str):
    """Resolve camera_role to a camera adapter.

    Resolution order:
    1. Try optical train registry via resolve_camera_index(0, camera_role).
    2. Fall back to get_preview_camera(0) when the role is not in the registry
       (typical in unit tests and minimal configs).
    """
    try:
        idx = deps.resolve_camera_index(0, camera_role)
        return deps.get_preview_camera(idx)
    except HTTPException as exc:
        if exc.status_code == 422:
            # Role not in optical train registry — use default preview camera
            _log.debug(
                "camera_role %r not in optical train registry, falling back to camera 0",
                camera_role,
            )
            return deps.get_preview_camera(0)
        raise


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/start", response_model=BiasEstimationStartResponse, status_code=202)
def start_bias_estimation(req: BiasEstimationRequest) -> BiasEstimationStartResponse:
    """Start a bias-frame offset estimation job (async).

    When *run_sweep* is True, captures frames at all DEFAULT_SWEEP_OFFSETS to
    find the minimum safe offset.  When False, tests only offset 0 (faster).

    Poll GET /api/bias_estimation/status/{job_id} for results.
    """
    try:
        camera = _get_camera_for_role(req.camera_role)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    cg = _VALID_CG[req.gain_mode]   # already validated by Pydantic
    sweep_offsets = DEFAULT_SWEEP_OFFSETS if req.run_sweep else [0]
    job = _register_job()

    def _run() -> None:
        try:
            svc = BiasEstimationService(camera)
            result = svc.estimate(
                gain_mode=cg,
                frame_count=req.frame_count,
                sweep_offsets=sweep_offsets,
            )
            sweep_data = [
                {
                    "offset": pt.offset,
                    "zero_fraction": pt.zero_fraction,
                    "min_val": pt.min_val,
                    "is_safe": pt.is_safe,
                }
                for pt in result.sweep
            ]
            with _jobs_lock:
                job.status = "DONE"
                job.result = {
                    "camera_model": result.camera_model,
                    "gain_mode": result.gain_mode_name,
                    "frame_count": result.frame_count,
                    "recommended_offset": result.recommended_offset,
                    "safe": result.safe,
                    "toml_snippet": result.toml_snippet(),
                    "sweep": sweep_data,
                }
            _log.info(
                "BiasEstimation job %s done: offset=%d safe=%s",
                job.job_id,
                result.recommended_offset,
                result.safe,
            )
        except Exception as exc:
            with _jobs_lock:
                job.status = "FAILED"
                job.error = f"Unexpected error: {exc}"
            _log.exception("BiasEstimation job %s failed", job.job_id)

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"bias-est-{job.job_id[:8]}",
    ).start()
    return BiasEstimationStartResponse(job_id=job.job_id)


@router.get("/status/{job_id}", response_model=BiasEstimationStatusResponse)
def get_bias_estimation_status(job_id: str) -> BiasEstimationStatusResponse:
    """Return current status of a bias estimation job."""
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    with _jobs_lock:
        sweep = [SweepPointResponse(**pt) for pt in job.result.get("sweep", [])]
        return BiasEstimationStatusResponse(
            job_id=job.job_id,
            status=job.status,
            error=job.error,
            camera_model=job.result.get("camera_model"),
            gain_mode=job.result.get("gain_mode"),
            frame_count=job.result.get("frame_count"),
            recommended_offset=job.result.get("recommended_offset"),
            safe=job.result.get("safe"),
            toml_snippet=job.result.get("toml_snippet"),
            sweep=sweep,
        )
