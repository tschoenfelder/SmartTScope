"""Collimation assistant REST API — Phase 1.3 + COL-022.

Endpoints:
  GET  /api/collimation/status           — current state + instruction
  POST /api/collimation/start            — begin session (IDLE → PRECHECK)
  POST /api/collimation/pause            — pause background work
  POST /api/collimation/resume           — resume after pause
  POST /api/collimation/cancel           — abort and reset to IDLE
  POST /api/collimation/next             — advance a USER_WAIT state with user input
  POST /api/collimation/retry            — reset after FAILED or COMPLETE
  GET  /api/collimation/overlay          — latest measurement for camera overlay
  GET  /api/collimation/report           — session summary

  POST /api/collimation/selftest/camera  — capture 1 frame, return shape + peak ADU
  POST /api/collimation/selftest/mount   — fire a guide pulse, return ok/error
  POST /api/collimation/selftest/focuser — move ±10 steps, return before/after position
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .deps import get_camera, get_camera_by_role, get_focuser, get_mount
from ..ports.camera import CameraPort, CaptureAbortedError
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..services.collimation.assistant import CollimationAssistant

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/collimation", tags=["collimation"])

_assistant: CollimationAssistant | None = None
_assistant_lock = threading.Lock()


def _get_assistant() -> CollimationAssistant:
    global _assistant
    if _assistant is None:
        with _assistant_lock:
            if _assistant is None:
                from ..services.guiding_service import GuidingService
                from ..services.guide_measurement import CentroidConfig, GuideControllerConfig
                from .. import config as _cfg_mod

                col_cfg = _cfg_mod.get_collimation_config()
                guiding_svc: GuidingService | None = None
                guide_cameras: dict = {}
                try:
                    guide_cam = get_camera_by_role(col_cfg.guiding_camera_role)
                    guide_cameras = {col_cfg.guiding_camera_role: guide_cam}
                    guiding_svc = GuidingService.from_config(
                        primary_role=col_cfg.guiding_camera_role,
                        allow_fallback=False,
                        fallback_after_bad_frames=5,
                        max_frame_age_s=col_cfg.guiding_cadence_s * 3,
                        centroid_config=CentroidConfig(),
                        controller_config=GuideControllerConfig(),
                        measure_only=False,
                    )
                except Exception:
                    _log.info(
                        "CollimationAssistant: guide camera '%s' not available — "
                        "starting without guiding",
                        col_cfg.guiding_camera_role,
                    )

                from ..services.collimation.frame_archive import CollimationFrameArchive
                from pathlib import Path
                arc_cfg = col_cfg.archive
                frame_archive: CollimationFrameArchive | None = None
                if arc_cfg.enabled:
                    archive_dir = (
                        Path(arc_cfg.archive_dir)
                        if arc_cfg.archive_dir
                        else Path.home() / ".SmartTScope" / "frame_archive"
                    )
                    frame_archive = CollimationFrameArchive(
                        archive_dir, arc_cfg.max_frames_per_session
                    )

                _assistant = CollimationAssistant(
                    camera=get_camera(),
                    mount=get_mount(),
                    focuser=get_focuser(),
                    guiding_service=guiding_svc,
                    guide_cameras=guide_cameras,
                    frame_archive=frame_archive,
                )
    return _assistant


# ── Request schemas ───────────────────────────────────────────────────────────

class NextPayload(BaseModel):
    """Payload for POST /next.

    For SELECT_STAR: provide ra + dec.
    For GUIDE_ROUGH/FINE: set finish=true to declare the phase done.
    For MASKLESS_VALIDATION: set accept=false to request more adjustment.
    """
    ra:     float | None = None
    dec:    float | None = None
    finish: bool = False
    accept: bool = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
def collimation_status() -> dict[str, Any]:
    return _get_assistant().status


@router.post("/start")
def collimation_start() -> dict[str, Any]:
    try:
        _get_assistant().start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.post("/pause")
def collimation_pause() -> dict[str, Any]:
    try:
        _get_assistant().pause()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.post("/resume")
def collimation_resume() -> dict[str, Any]:
    try:
        _get_assistant().resume()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.post("/cancel")
def collimation_cancel() -> dict[str, Any]:
    _get_assistant().cancel()
    return _get_assistant().status


@router.post("/next")
def collimation_next(payload: NextPayload = NextPayload()) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if payload.ra is not None:
        data["ra"] = payload.ra
    if payload.dec is not None:
        data["dec"] = payload.dec
    if payload.finish:
        data["finish"] = True
    if not payload.accept:
        data["accept"] = False
    try:
        _get_assistant().advance(data)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.post("/retry")
def collimation_retry() -> dict[str, Any]:
    try:
        _get_assistant().retry()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.get("/overlay")
def collimation_overlay() -> dict[str, Any]:
    return _get_assistant().overlay


@router.get("/report")
def collimation_report() -> dict[str, Any]:
    return _get_assistant().report


# ── Archive endpoints ─────────────────────────────────────────────────────────

@router.get("/archive")
def archive_list_sessions() -> dict[str, Any]:
    """List all archived collimation sessions."""
    archive = _get_assistant().frame_archive
    if archive is None:
        return {"enabled": False, "sessions": []}
    return {"enabled": True, "sessions": archive.list_sessions()}


@router.get("/archive/{session_id}")
def archive_list_frames(session_id: str) -> dict[str, Any]:
    """List frames in a single archived session."""
    archive = _get_assistant().frame_archive
    if archive is None:
        return {"enabled": False, "session_id": session_id, "frames": []}
    return {
        "enabled": True,
        "session_id": session_id,
        "frames": archive.list_frames(session_id),
    }


@router.post("/archive/{session_id}/{frame_stem}/replay")
def archive_replay(session_id: str, frame_stem: str) -> dict[str, Any]:
    """Re-run stored frame through its original analysis pipeline."""
    archive = _get_assistant().frame_archive
    if archive is None:
        raise HTTPException(status_code=503, detail="Frame archive is not enabled")
    try:
        raw = archive.load_frame(session_id, frame_stem)
        sidecar = archive.load_sidecar(session_id, frame_stem)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Frame {session_id}/{frame_stem} not found"
        )

    from ..domain.collimation.processing.frame import normalize_frame
    bit_depth = int(sidecar.get("bit_depth", 16))
    processed = normalize_frame(raw, bit_depth=bit_depth)
    state = sidecar["state"]

    new_result: dict[str, Any]
    if state == "measure_donut":
        from ..domain.collimation.processing.donut_detection import DonutAnalyzer
        result = DonutAnalyzer().analyze(processed)
        if result.reason == "ok" and result.measurement is not None:
            d = result.measurement
            new_result = {
                "reason": "ok",
                "error_x_px": d.error_x_px,
                "error_y_px": d.error_y_px,
                "error_magnitude_px": d.error_magnitude_px,
                "confidence": d.confidence,
            }
        else:
            new_result = {"reason": result.reason}
    elif state == "measure_spikes":
        from ..domain.collimation.models import Point2D
        from ..domain.collimation.processing.spike_detection import detect_spikes
        ref = Point2D(
            x=float(sidecar.get("ref_x", processed.width / 2)),
            y=float(sidecar.get("ref_y", processed.height / 2)),
        )
        sr = detect_spikes(processed, ref)
        if sr.measurement is not None:
            m = sr.measurement
            new_result = {
                "reason": sr.reason,
                "focus_error_px": m.focus_error_px,
                "offset_from_ref_px": m.offset_from_ref_px,
                "confidence": m.confidence,
            }
        else:
            new_result = {"reason": sr.reason}
    else:
        raise HTTPException(
            status_code=422, detail=f"No replay handler for state '{state}'"
        )

    return {
        "session_id": session_id,
        "frame_stem": frame_stem,
        "state": state,
        "original": sidecar.get("analysis", {}),
        "replayed": new_result,
    }


# ── Self-test endpoints (COL-022) ─────────────────────────────────────────────

class MountTestRequest(BaseModel):
    direction: str = "n"
    duration_ms: int = 500


class FocuserTestRequest(BaseModel):
    steps: int = 10


@router.post("/selftest/camera")
def selftest_camera(
    camera: CameraPort = Depends(get_camera),
) -> dict[str, Any]:
    """Capture one 1-second frame and return image dimensions and peak ADU."""
    try:
        frame = camera.capture(1.0)
    except CaptureAbortedError:
        raise HTTPException(status_code=503, detail="Camera capture aborted")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Camera capture failed: {exc}")
    peak = int(np.max(frame.pixels))
    return {
        "ok": True,
        "width": frame.width,
        "height": frame.height,
        "peak_adu": peak,
    }


@router.post("/selftest/mount")
def selftest_mount(
    body: MountTestRequest = MountTestRequest(),
    mount: MountPort = Depends(get_mount),
) -> dict[str, Any]:
    """Fire a short guide pulse in the requested direction."""
    direction = body.direction.lower()
    if direction not in ("n", "s", "e", "w"):
        raise HTTPException(status_code=422, detail="direction must be n/s/e/w")
    ok = mount.guide(direction, body.duration_ms)
    if not ok:
        raise HTTPException(status_code=503, detail="Guide pulse rejected by mount")
    return {"ok": True, "direction": direction, "duration_ms": body.duration_ms}


@router.post("/selftest/focuser")
def selftest_focuser(
    body: FocuserTestRequest = FocuserTestRequest(),
    focuser: FocuserPort = Depends(get_focuser),
) -> dict[str, Any]:
    """Move the focuser by ±steps and return before/after position."""
    if not focuser.is_available:
        return {"ok": False, "message": "Focuser not available"}
    steps = body.steps
    if steps == 0:
        raise HTTPException(status_code=422, detail="steps must be non-zero")
    before = focuser.get_position()
    focuser.move(steps)
    after = focuser.get_position()
    return {"ok": True, "steps": steps, "position_before": before, "position_after": after}
