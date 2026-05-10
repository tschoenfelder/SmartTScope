"""Guide-camera monitoring API — POST /api/guide_monitor/start, /stop, GET /status."""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.camera_profile import ALL_PROFILES, CameraProfile
from ..domain.guide_monitor import GuideMonitor, GuideMonitorConfig, GuideMonitorResult
from . import deps

router = APIRouter(prefix="/api/guide_monitor")

_monitor: GuideMonitor | None = None
_lock = threading.Lock()


# ── Request / Response models ─────────────────────────────────────────────────

class StartRequest(BaseModel):
    camera_index: int = Field(default=1, ge=0, le=7)
    camera_model: str = Field(default="GPCMOS02000KPA")
    check_interval_s: float = Field(default=300.0, ge=10.0, le=3600.0)
    max_gain_step_pct: float = Field(default=10.0, ge=1.0, le=50.0)
    max_exp_step_pct: float = Field(default=20.0, ge=1.0, le=50.0)
    hysteresis_pct: float = Field(default=15.0, ge=1.0, le=50.0)
    dawn_threshold_pct: float = Field(default=20.0, ge=5.0, le=100.0)


class GuideMonitorStatusResponse(BaseModel):
    running: bool
    status: str | None = None
    exposure_ms: float | None = None
    gain: int | None = None
    p99_9: float | None = None
    checked_at: str | None = None
    dawn_warning: bool = False
    warning_msg: str | None = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/start", status_code=202)
def start_monitor(req: StartRequest) -> dict:
    """Launch the guide-monitor background task.

    Returns 400 if the camera model is unknown.
    Returns 409 if already running.
    """
    global _monitor

    profile: CameraProfile | None = ALL_PROFILES.get(req.camera_model)
    if profile is None:
        raise HTTPException(status_code=400, detail=f"Unknown camera model: {req.camera_model!r}")

    with _lock:
        if _monitor is not None and _monitor.running:
            raise HTTPException(status_code=409, detail="Guide monitor already running")

        try:
            camera = deps.get_preview_camera(req.camera_index)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Camera unavailable: {exc}") from exc

        config = GuideMonitorConfig(
            check_interval_s=req.check_interval_s,
            max_gain_step_pct=req.max_gain_step_pct,
            max_exp_step_pct=req.max_exp_step_pct,
            hysteresis_pct=req.hysteresis_pct,
            dawn_threshold_pct=req.dawn_threshold_pct,
        )
        _monitor = GuideMonitor(camera=camera, profile=profile, config=config)
        _monitor.start()

    return {"started": True}


@router.post("/stop", status_code=200)
def stop_monitor() -> dict:
    """Stop the guide-monitor background task.  No-op if not running."""
    with _lock:
        m = _monitor
    if m is not None:
        m.stop()
    return {"stopped": True}


@router.get("/status", response_model=GuideMonitorStatusResponse)
def get_status() -> GuideMonitorStatusResponse:
    """Return the last monitor check result.  Always 200."""
    with _lock:
        m = _monitor

    if m is None:
        return GuideMonitorStatusResponse(running=False)

    r: GuideMonitorResult | None = m.last_result
    if r is None:
        return GuideMonitorStatusResponse(running=m.running)

    return GuideMonitorStatusResponse(
        running=m.running,
        status=r.status.value,
        exposure_ms=round(r.exposure_ms, 3),
        gain=r.gain,
        p99_9=round(r.p99_9, 4),
        checked_at=r.checked_at,
        dawn_warning=r.dawn_warning,
        warning_msg=r.warning_msg,
    )


def _reset() -> None:
    """Stop and clear state — used by tests."""
    global _monitor
    with _lock:
        if _monitor is not None:
            _monitor.stop()
        _monitor = None
