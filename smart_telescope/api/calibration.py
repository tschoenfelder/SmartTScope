"""Calibration preparation API — POST /api/calibration/bias, GET /api/calibration/status/{job_id}."""
from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..api import deps
from ..domain.calibration_capture import BiasValidationError, prepare_bias
from ..domain.calibration_store import CalibrationIndex
from ..domain.camera_capabilities import ConversionGain

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/calibration")

# ── Job registry ──────────────────────────────────────────────────────────────

_VALID_CG = {cg.name: cg for cg in ConversionGain}


@dataclass
class _JobState:
    job_id: str
    status: str = "running"       # "running" | "done" | "failed"
    frames_done: int = 0
    n_frames: int = 0
    error: str | None = None
    result_path: str | None = None
    result_entry: dict[str, Any] = field(default_factory=dict)


_jobs: dict[str, _JobState] = {}
_jobs_lock = threading.Lock()


def _register_job(n_frames: int) -> _JobState:
    job = _JobState(job_id=str(uuid.uuid4()), n_frames=n_frames)
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


class BiasRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    n_frames: int = Field(default=32, ge=1, le=200)
    gain: int | None = Field(default=None, ge=0, le=5000)
    offset: int | None = Field(default=None, ge=0, le=255)
    conversion_gain: str | None = Field(default=None, description="HCG | LCG | HDR")


class JobStartedResponse(BaseModel):
    job_id: str
    status: str = "running"


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    frames_done: int
    n_frames: int
    error: str | None = None
    result_path: str | None = None
    result_entry: dict[str, Any] = {}


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/bias", response_model=JobStartedResponse, status_code=202)
def start_bias(req: BiasRequest) -> JobStartedResponse:
    """Start a bias master preparation job.

    Runs asynchronously; poll GET /api/calibration/status/{job_id} for progress.
    """
    image_root = config.IMAGE_ROOT
    if not image_root:
        raise HTTPException(
            status_code=503,
            detail="IMAGE_ROOT is not configured — set it in smart_telescope.toml or the IMAGE_ROOT env var.",
        )

    try:
        camera = deps.get_preview_camera(req.camera_index)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    cg: ConversionGain | None = None
    if req.conversion_gain is not None:
        cg_name = req.conversion_gain.upper()
        if cg_name not in _VALID_CG:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown conversion_gain '{req.conversion_gain}'. Valid: {list(_VALID_CG)}",
            )
        cg = _VALID_CG[cg_name]

    job = _register_job(req.n_frames)
    cal_index = CalibrationIndex.load(image_root)

    def _run() -> None:
        def _progress(done: int, total: int) -> None:
            with _jobs_lock:
                job.frames_done = done

        try:
            entry = prepare_bias(
                camera,
                req.n_frames,
                image_root,
                cal_index,
                gain=req.gain,
                offset=req.offset,
                conversion_gain=cg,
                progress=_progress,
            )
            cal_index.save()
            abs_path = Path(image_root) / entry.relative_path
            with _jobs_lock:
                job.status = "done"
                job.frames_done = req.n_frames
                job.result_path = str(abs_path)
                job.result_entry = entry.to_dict()
            _log.info("Bias job %s done: %s", job.job_id, abs_path)
        except BiasValidationError as exc:
            with _jobs_lock:
                job.status = "failed"
                job.error = str(exc)
            _log.warning("Bias job %s validation failed: %s", job.job_id, exc)
        except Exception as exc:
            with _jobs_lock:
                job.status = "failed"
                job.error = f"Unexpected error: {exc}"
            _log.exception("Bias job %s failed", job.job_id)

    threading.Thread(target=_run, daemon=True, name=f"bias-{job.job_id[:8]}").start()
    return JobStartedResponse(job_id=job.job_id)


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_job_status(job_id: str) -> JobStatusResponse:
    """Return the current status of a calibration job."""
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    with _jobs_lock:
        return JobStatusResponse(
            job_id=job.job_id,
            status=job.status,
            frames_done=job.frames_done,
            n_frames=job.n_frames,
            error=job.error,
            result_path=job.result_path,
            result_entry=job.result_entry,
        )
