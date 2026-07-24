"""Autofocus screen support API — M10-033.

Two endpoints for the new dedicated Autofocus screen (main camera only):

- POST /api/autofocus/sequence: capture a bracketed sequence of raw FITS
  frames at different focuser positions, saved individually (not stacked)
  with position-tagged filenames, to support tuning autofocus later.
  Distinct from workflow/autofocus.py's run_autofocus(), which searches for
  the single best focus position — this endpoint just records raw data at
  every requested position.
- POST /api/autofocus/frame_metrics: one-shot sharpness (HFD) + star-count
  readout for the screen's live-preview overlay, sky mode only (callers
  gate this on their own terrestrial/sky toggle — no such concept exists
  server-side).
"""
from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from astropy.io import fits
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..domain.focus_metric import multi_star_hfd
from ..ports.focuser import FocuserPort
from ..services import live_analysis_shim
from ..services.hardware_coordinator import CommandConflictError, HardwareCommandCoordinator
from ..services.job_manager import ResourceConflictError
from . import deps

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/autofocus")

_SETTLE_POLL_S = 0.1
_SETTLE_TIMEOUT_S = 30.0


def _wait_stopped(focuser: FocuserPort) -> None:
    elapsed = 0.0
    while focuser.is_moving():
        time.sleep(_SETTLE_POLL_S)
        elapsed += _SETTLE_POLL_S
        if elapsed >= _SETTLE_TIMEOUT_S:
            break  # proceed anyway; matches workflow/autofocus.py's own tolerance


# ── Sequence capture job registry (mirrors api/calibration.py's pattern) ──────


@dataclass
class _SeqJobState:
    job_id: str
    status: str = "running"       # "running" | "done" | "failed"
    frames_done: int = 0
    n_frames: int = 0
    error: str | None = None
    result_dir: str | None = None
    positions: list[int] = field(default_factory=list)


_jobs: dict[str, _SeqJobState] = {}
_jobs_lock = threading.Lock()


def _register_job(n_frames: int) -> _SeqJobState:
    job = _SeqJobState(job_id=str(uuid.uuid4()), n_frames=n_frames)
    with _jobs_lock:
        _jobs[job.job_id] = job
    return job


def _get_job(job_id: str) -> _SeqJobState | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def _reset_jobs() -> None:
    with _jobs_lock:
        _jobs.clear()


class SequenceRequest(BaseModel):
    start_offset: int = Field(..., description="Sweep start, relative to the current focuser position")
    end_offset:   int = Field(..., description="Sweep end, relative to the current focuser position")
    step:         int = Field(gt=0, le=5000)
    exposure:     float = Field(default=2.0, gt=0.0, le=60.0)
    gain:         int | None = Field(default=None, ge=0, le=5000)
    camera_index: int = Field(default=0, ge=0, le=7)
    camera_role:  str | None = Field(default=None)


class SequenceStartedResponse(BaseModel):
    job_id: str
    status: str = "running"
    n_frames: int


class SequenceStatusResponse(BaseModel):
    job_id: str
    status: str
    frames_done: int
    n_frames: int
    error: str | None = None
    result_dir: str | None = None
    positions: list[int] = []


@router.post("/sequence", response_model=SequenceStartedResponse, status_code=202)
def start_sequence(
    req: SequenceRequest,
    focuser: FocuserPort = Depends(deps.get_focuser),
    coordinator: HardwareCommandCoordinator = Depends(deps.get_coordinator),
) -> SequenceStartedResponse:
    """Start a bracketed focus-position FITS capture job (async).

    Poll GET /api/autofocus/sequence/status/{job_id} for progress.
    """
    if not focuser.is_available:
        raise HTTPException(status_code=503, detail="Focuser not available")
    if req.end_offset <= req.start_offset:
        raise HTTPException(status_code=422, detail="end_offset must be greater than start_offset")

    st = focuser.status()
    current = st.position
    positions = list(range(current + req.start_offset, current + req.end_offset + 1, req.step))
    if not positions:
        raise HTTPException(status_code=422, detail="No positions in the requested range/step")
    if st.max_position and (min(positions) < 0 or max(positions) > st.max_position):
        raise HTTPException(
            status_code=422,
            detail=(
                f"Requested range [{min(positions)}, {max(positions)}] exceeds the focuser's "
                f"reported range [0, {st.max_position}] — narrow the offsets/step"
            ),
        )

    image_root = config.IMAGE_ROOT
    if not image_root:
        raise HTTPException(status_code=503, detail="IMAGE_ROOT is not configured")

    camera_index = deps.resolve_camera_index(req.camera_index, req.camera_role)
    camera = deps.get_preview_camera(camera_index)
    if req.gain is not None and hasattr(camera, "set_gain"):
        camera.set_gain(req.gain)

    job = _register_job(len(positions))
    dest_dir = Path(image_root) / "autofocus_sequences" / job.job_id[:8]

    def _run() -> None:
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            for idx, pos in enumerate(positions):
                # Hold the focuser lock only around this one move+settle, not
                # the whole multi-position sequence (positions are absolute,
                # so a manual nudge slipping in between steps is harmless —
                # the next step still moves to the correct absolute target).
                # Previously the lock was held for the entire run, so jog/
                # nudge buttons elsewhere would block for the sequence's full
                # duration (potentially minutes) before timing out with a
                # 409 — read by the user as "movement cursors not responding
                # ... delayed by several seconds."
                with coordinator.focuser_command(timeout=0):
                    focuser.move(pos)
                    _wait_stopped(focuser)
                frame = camera.capture(req.exposure)
                hdr = frame.header.copy() if isinstance(frame.header, fits.Header) else fits.Header()
                hdr["FOCUSPOS"] = (pos, "Focuser position for this frame (steps)")
                hdu = fits.PrimaryHDU(data=frame.pixels, header=hdr)
                filename = f"af-seq_pos-{pos}_{idx:03d}.fits"
                hdu.writeto(str(dest_dir / filename), overwrite=True)
                with _jobs_lock:
                    job.frames_done = idx + 1
                    job.positions.append(pos)
            with _jobs_lock:
                job.status = "done"
                job.result_dir = str(dest_dir)
            _log.info("Autofocus sequence job %s done: %s", job.job_id, dest_dir)
        except CommandConflictError as exc:
            with _jobs_lock:
                job.status = "failed"
                job.error = f"Focuser busy: {exc}"
            _log.warning("Autofocus sequence job %s: focuser busy", job.job_id)
        except Exception as exc:
            with _jobs_lock:
                job.status = "failed"
                job.error = f"Unexpected error: {exc}"
            _log.exception("Autofocus sequence job %s failed", job.job_id)

    # Claim the camera resource in the shared JobManager so the live-preview
    # websocket's existing "camera busy" yield (api/preview.py) engages
    # instead of both sides silently fighting over the adapter's low-level
    # capture lock — which previously made the preview appear to hang for
    # the sequence's entire (potentially long, multi-position) duration.
    timeout_s = len(positions) * (_SETTLE_TIMEOUT_S + req.exposure + 5.0)
    try:
        deps.get_job_manager().submit(
            "autofocus_sequence", {f"camera:{camera_index}"}, _run, timeout_s=timeout_s,
        )
    except ResourceConflictError as exc:
        with _jobs_lock:
            job.status = "failed"
            job.error = f"Camera busy: {exc}"
        raise HTTPException(status_code=409, detail=str(exc))
    return SequenceStartedResponse(job_id=job.job_id, n_frames=len(positions))


@router.get("/sequence/status/{job_id}", response_model=SequenceStatusResponse)
def sequence_status(job_id: str) -> SequenceStatusResponse:
    """Return current status of an autofocus sequence-capture job."""
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    with _jobs_lock:
        return SequenceStatusResponse(
            job_id=job.job_id,
            status=job.status,
            frames_done=job.frames_done,
            n_frames=job.n_frames,
            error=job.error,
            result_dir=job.result_dir,
            positions=list(job.positions),
        )


# ── Live sharpness / star-count readout ───────────────────────────────────────


class FrameMetricsRequest(BaseModel):
    exposure:     float = Field(default=2.0, gt=0.0, le=60.0)
    camera_index: int = Field(default=0, ge=0, le=7)
    camera_role:  str | None = Field(default=None)


class FrameMetricsResponse(BaseModel):
    hfd: float | None = None  # None when no reliable star blob was detected (too far out of focus)
    stars_found: int | None = None
    image_quality: str | None = None


@router.post("/frame_metrics", response_model=FrameMetricsResponse)
def frame_metrics(req: FrameMetricsRequest) -> FrameMetricsResponse:
    """Capture one frame and return HFD sharpness + star count (sky mode only —
    the caller's own terrestrial/sky toggle decides whether to call this)."""
    camera_index = deps.resolve_camera_index(req.camera_index, req.camera_role)
    camera = deps.get_preview_camera(camera_index)
    frame = camera.capture(req.exposure)
    hfd = multi_star_hfd(frame.pixels)

    stars_found: int | None = None
    image_quality: str | None = None
    if live_analysis_shim.live_analysis_available():
        try:
            camera_info = live_analysis_shim.build_camera_info(camera, frame=frame)
            result = live_analysis_shim.analyze(camera_info, frame)
            single = result.get("single_frame", {})
            stars_found = single.get("stars_found")
            image_quality = single.get("image_quality")
        except Exception:
            _log.debug("frame_metrics: LiveAnalysis call failed", exc_info=True)

    return FrameMetricsResponse(hfd=hfd, stars_found=stars_found, image_quality=image_quality)
