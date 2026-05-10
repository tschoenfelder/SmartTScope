"""Cooling control API — POST /api/cooling/set_target, GET /api/cooling/status."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.cooling import CoolingAction, CoolingConfig, CoolingController
from . import deps

_log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cooling")

_POLL_INTERVAL_S = 30.0


# ── Request / Response models ─────────────────────────────────────────────────

class SetTargetRequest(BaseModel):
    camera_index: int = Field(default=0, ge=0, le=7)
    target_c: float = Field(default=-10.0, ge=-10.0, le=10.0)
    enabled: bool = True


class SetTargetResponse(BaseModel):
    ok: bool
    target_c: float
    message: str | None = None


class CoolingStatusResponse(BaseModel):
    enabled: bool
    camera_index: int | None = None
    current_temp_c: float | None = None
    target_c: float | None = None
    power_pct: float | None = None
    stable: bool = False
    action: str | None = None
    warning_msg: str | None = None
    seconds_remaining: float | None = None


# ── Session state ─────────────────────────────────────────────────────────────

@dataclass
class _Session:
    camera_index: int
    ctrl: CoolingController
    last_action: CoolingAction | None = None
    last_temp_c: float | None = None
    last_power_pct: float = 0.0
    warning_msg: str | None = None
    stop_event: threading.Event = None  # type: ignore[assignment]
    thread: threading.Thread = None     # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.stop_event is None:
            self.stop_event = threading.Event()


_session: _Session | None = None
_lock = threading.Lock()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _camera_has_tec(camera: object) -> bool:
    return (
        hasattr(camera, "set_tec_enabled")
        and hasattr(camera, "set_tec_target_c")
        and hasattr(camera, "get_tec_power_pct")
    )


def _poll_once(session: _Session) -> None:
    """Read camera state, run controller tick, apply any target change."""
    try:
        camera = deps.get_preview_camera(session.camera_index)
    except Exception as exc:
        _log.warning("Cooling poll: camera unavailable — %s", exc)
        return

    temp_c: float | None = None
    try:
        temp_c = camera.get_temperature()
    except Exception:
        pass

    power_pct: float = 0.0
    try:
        power_pct = camera.get_tec_power_pct()  # type: ignore[attr-defined]
    except Exception:
        pass

    if temp_c is None:
        _log.debug("Cooling poll: temperature unavailable, skipping tick")
        with _lock:
            session.last_temp_c = None
            session.last_power_pct = power_pct
        return

    prev_target = session.ctrl.current_target_c
    action = session.ctrl.tick(temp_c, power_pct)

    warning_msg: str | None = None
    if action == CoolingAction.RAISE_TARGET:
        new_target = session.ctrl.current_target_c
        warning_msg = f"TEC power too high — target relaxed to {new_target:.1f} °C"
        _log.warning("Cooling: %s", warning_msg)
        try:
            camera.set_tec_target_c(new_target)  # type: ignore[attr-defined]
        except Exception as exc:
            _log.warning("Cooling: set_tec_target_c(%.1f) failed: %s", new_target, exc)
    elif action == CoolingAction.WARN:
        warning_msg = f"TEC power {power_pct:.0f}% — above warning threshold"

    _log.info(
        "Cooling poll: camera_index=%d temp=%.1f°C target=%.1f°C power=%.0f%% action=%s",
        session.camera_index, temp_c, session.ctrl.current_target_c, power_pct, action.name,
    )

    with _lock:
        session.last_temp_c = temp_c
        session.last_power_pct = power_pct
        session.last_action = action
        if action in (CoolingAction.RAISE_TARGET, CoolingAction.WARN):
            session.warning_msg = warning_msg
        elif action == CoolingAction.STABLE:
            session.warning_msg = None


def _polling_loop(session: _Session) -> None:
    _poll_once(session)  # immediate first poll
    while not session.stop_event.wait(timeout=_POLL_INTERVAL_S):
        _poll_once(session)


def _stop_current_session() -> None:
    """Stop the running session if any.  Caller must hold _lock or be in startup."""
    global _session
    s = _session
    if s is not None:
        s.stop_event.set()
        # Release lock while joining so the poll thread can finish
        _lock.release()
        try:
            s.thread.join(timeout=5.0)
        finally:
            _lock.acquire()
        # Disable TEC on the camera
        try:
            camera = deps.get_preview_camera(s.camera_index)
            camera.set_tec_enabled(False)  # type: ignore[attr-defined]
        except Exception:
            pass
        _session = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/set_target", response_model=SetTargetResponse)
def set_target(req: SetTargetRequest) -> SetTargetResponse:
    """Start, reconfigure, or stop TEC cooling on a camera.

    When *enabled* is False, cooling is disabled and the TEC is turned off.
    """
    global _session

    if not req.enabled:
        with _lock:
            _stop_current_session()
        _log.info("Cooling disabled by request")
        return SetTargetResponse(ok=True, target_c=req.target_c, message="Cooling disabled")

    # Validate camera supports TEC
    try:
        camera = deps.get_preview_camera(req.camera_index)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    if not _camera_has_tec(camera):
        raise HTTPException(
            status_code=409,
            detail=f"Camera at index {req.camera_index} does not support TEC cooling",
        )

    cfg = CoolingConfig(target_c=req.target_c)  # clamps to ≥ −10 °C

    with _lock:
        # Stop any existing session first
        if _session is not None:
            _stop_current_session()

        ctrl = CoolingController(cfg)
        session = _Session(camera_index=req.camera_index, ctrl=ctrl)
        session.thread = threading.Thread(
            target=_polling_loop, args=(session,), daemon=True, name="cooling-poll"
        )
        _session = session

    # Apply initial TEC settings before starting the poll thread
    try:
        camera.set_tec_target_c(cfg.target_c)   # type: ignore[attr-defined]
        camera.set_tec_enabled(True)             # type: ignore[attr-defined]
    except Exception as exc:
        _log.warning("Cooling: initial TEC setup failed: %s", exc)

    session.thread.start()
    _log.info(
        "Cooling enabled: camera_index=%d target=%.1f°C",
        req.camera_index, cfg.target_c,
    )
    return SetTargetResponse(ok=True, target_c=cfg.target_c)


@router.get("/status", response_model=CoolingStatusResponse)
def get_status() -> CoolingStatusResponse:
    """Return the current cooling state.  Always 200; *enabled* is False when inactive."""
    with _lock:
        s = _session

    if s is None:
        return CoolingStatusResponse(enabled=False)

    action = s.last_action
    return CoolingStatusResponse(
        enabled=True,
        camera_index=s.camera_index,
        current_temp_c=s.last_temp_c,
        target_c=s.ctrl.current_target_c,
        power_pct=round(s.last_power_pct, 1),
        stable=action == CoolingAction.STABLE,
        action=action.name if action is not None else None,
        warning_msg=s.warning_msg,
        seconds_remaining=round(s.ctrl.seconds_remaining, 0),
    )


def _reset() -> None:
    """Stop cooling and clear state (used by tests)."""
    global _session
    with _lock:
        if _session is not None:
            _stop_current_session()
