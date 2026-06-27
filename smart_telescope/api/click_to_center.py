"""Click-to-center API — M8-025/026/027/028 / REQ-CLICK-001..004.

Endpoints:
  GET  /api/click_to_center/readiness       — gate + calibration check
  POST /api/click_to_center/refine          — refine raw click to centroid / ring center
  GET  /api/click_to_center/calibration     — current calibration status
  POST /api/click_to_center/calibration     — store a calibration record
  DELETE /api/click_to_center/calibration   — invalidate calibration for a key
  POST /api/click_to_center/center          — start iterative centering loop (blocking)
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import deps as _deps
from .preview import get_last_preview_pixels
from ..domain.click_refinement import refine_click
from ..domain.ctc_calibration import CTCCalibration
from ..services.operation_gate import evaluate_gate, gate_inputs_from_device_state
from ..services.ctc_loop_service import run_centering_loop

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/click_to_center", tags=["click_to_center"])

_CALIBRATION_REQUIRED_MSG = (
    "Click-to-center calibration is missing or expired. "
    "Run the calibration wizard to map pixels to sky coordinates."
)


def _check_calibration(optical_train: str, binning: int = 1) -> tuple[bool, str | None]:
    """Return (calibrated, reason_if_not)."""
    store = _deps.get_ctc_calibration_store()
    cal = store.get(optical_train, binning)
    if cal is None:
        return False, _CALIBRATION_REQUIRED_MSG
    if not cal.is_valid():
        age = round(cal.age_hours(), 1)
        return False, (
            f"Click-to-center calibration expired ({age} h old, max {cal.max_age_hours} h). "
            "Run the calibration wizard to refresh."
        )
    return True, None


# ── Readiness ────────────────────────────────────────────────────────────────

@router.get("/readiness")
def click_to_center_readiness(
    optical_train: str = "default",
    binning: int = 1,
) -> dict:
    """Return whether click-to-center is currently allowed and why if not.

    Checks both the OperationGate (adapter + Stage 1) and calibration validity.
    """
    # 1. Gate check
    inputs = gate_inputs_from_device_state(
        _deps.get_device_state(),
        master_source_svc=_deps.get_master_source_service(),
        raspberry_trust_svc=_deps.get_raspberry_trust_service(),
    )
    gate = evaluate_gate("click_to_center", **inputs)
    if not gate.allowed:
        return {
            "allowed": False,
            "reason": gate.human_message,
            "required_action": gate.required_user_action,
            "calibration_ok": None,
        }

    # 2. Calibration check
    cal_ok, cal_reason = _check_calibration(optical_train, binning)
    if not cal_ok:
        return {
            "allowed": False,
            "reason": cal_reason,
            "required_action": "run_ctc_calibration",
            "calibration_ok": False,
        }

    return {
        "allowed": True,
        "reason": None,
        "required_action": None,
        "calibration_ok": True,
    }


# ── Refine click ─────────────────────────────────────────────────────────────

class RefineRequest(BaseModel):
    x_px: int
    y_px: int
    camera_index: int = 0
    mode: str = "star_centroid"   # "star_centroid" | "ring_center"
    search_radius: int = 40


@router.post("/refine")
def click_to_center_refine(req: RefineRequest) -> dict:
    """Refine a raw click coordinate using the latest preview frame.

    Falls back to raw coords if no frame is cached or no feature is found.
    """
    pixels = get_last_preview_pixels(req.camera_index)
    if pixels is None:
        _log.info("CLICK_REFINE no_frame camera_index=%d raw=(%d,%d)", req.camera_index, req.x_px, req.y_px)
        return {
            "raw_x": req.x_px, "raw_y": req.y_px,
            "refined_x": req.x_px, "refined_y": req.y_px,
            "method": "raw_fallback",
            "confidence": 0.0,
            "fallback": True,
            "fallback_reason": "No preview frame available — start the live preview first.",
        }

    result = refine_click(
        pixels,
        click_x=req.x_px,
        click_y=req.y_px,
        mode=req.mode,
        search_radius=req.search_radius,
    )
    _log.info(result.to_json_line())
    d = result.to_dict()
    d["fallback_reason"] = (
        "No star or ring feature found near click — using raw position."
        if result.fallback else None
    )
    return d


# ── Calibration management ───────────────────────────────────────────────────

@router.get("/calibration")
def get_calibration(optical_train: str = "default", binning: int = 1) -> dict:
    """Return calibration status for the given optical_train/binning."""
    store = _deps.get_ctc_calibration_store()
    cal = store.get(optical_train, binning)
    if cal is None:
        return {
            "found": False,
            "valid": False,
            "optical_train": optical_train,
            "binning": binning,
            "reason": _CALIBRATION_REQUIRED_MSG,
        }
    d = cal.to_dict()
    d["found"] = True
    if not cal.is_valid():
        d["reason"] = (
            f"Calibration expired ({round(cal.age_hours(), 1)} h old, "
            f"max {cal.max_age_hours} h)."
        )
    else:
        d["reason"] = None
    return d


class SetCalibrationRequest(BaseModel):
    optical_train: str = "default"
    binning: int = 1
    arcsec_per_px_x: float
    arcsec_per_px_y: float
    rotation_deg: float
    max_age_hours: float = 24.0


@router.post("/calibration")
def set_calibration(req: SetCalibrationRequest) -> dict:
    """Store a calibration record for the given optical_train/binning.

    In the initial implementation, calibration is entered manually or by the
    plate-solve pipeline. The full calibration wizard is M8-027 future work.
    """
    cal = CTCCalibration(
        arcsec_per_px_x=req.arcsec_per_px_x,
        arcsec_per_px_y=req.arcsec_per_px_y,
        rotation_deg=req.rotation_deg,
        optical_train=req.optical_train,
        binning=req.binning,
        measured_at=time.time(),
        max_age_hours=req.max_age_hours,
    )
    _deps.get_ctc_calibration_store().put(cal)
    _log.info("CTC calibration stored: %s", cal.key)
    return {"ok": True, "key": cal.key, "calibration": cal.to_dict()}


@router.delete("/calibration")
def delete_calibration(optical_train: str = "default", binning: int = 1) -> dict:
    """Invalidate (delete) the calibration for the given optical_train/binning."""
    deleted = _deps.get_ctc_calibration_store().delete(optical_train, binning)
    return {"deleted": deleted, "key": f"{optical_train}:{binning}"}


# ── Centering loop (M8-028 / REQ-CLICK-004) ─────────────────────────────────

# Global cancellation event for the centering loop (one loop at a time)
_ctc_cancel_event: threading.Event = threading.Event()


class CenterRequest(BaseModel):
    x_px: int
    y_px: int
    optical_train: str = "default"
    binning: int = 1
    camera_role: str = "main"
    refinement_mode: str = "star_centroid"
    exposure_s: float = 2.0
    gain: int = 100


@router.post("/center")
def click_to_center_center(req: CenterRequest) -> dict:
    """Run the iterative centering loop synchronously (blocks until done or cancelled).

    Requires valid calibration and an unparked, non-blocked mount.
    """
    from .. import config as _cfg

    # Gate check
    inputs = gate_inputs_from_device_state(
        _deps.get_device_state(),
        master_source_svc=_deps.get_master_source_service(),
        raspberry_trust_svc=_deps.get_raspberry_trust_service(),
    )
    gate = evaluate_gate("click_to_center", **inputs)
    if not gate.allowed:
        raise HTTPException(status_code=409, detail=gate.human_message)

    # Calibration check
    cal = _deps.get_ctc_calibration_store().get(req.optical_train, req.binning)
    if cal is None or not cal.is_valid():
        raise HTTPException(status_code=409, detail=_CALIBRATION_REQUIRED_MSG)

    # Resolve camera + mount
    try:
        camera = _deps.get_camera_by_role(req.camera_role)
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Camera unavailable: {exc}")
    try:
        mount = _deps.get_mount()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=f"Mount unavailable: {exc}")

    _ctc_cancel_event.clear()
    result = run_centering_loop(
        camera=camera,
        mount=mount,
        calibration=cal,
        target_x_px=req.x_px,
        target_y_px=req.y_px,
        refinement_mode=req.refinement_mode,
        exposure_s=req.exposure_s,
        gain=req.gain,
        max_iterations=_cfg.CTC_MAX_ITERATIONS,
        center_tolerance_px=_cfg.CTC_CENTER_TOLERANCE_PX,
        max_single_move_px=_cfg.CTC_MAX_SINGLE_MOVE_PX,
        move_fraction=_cfg.CTC_MOVE_FRACTION,
        center_rate_arcsec_per_sec=_cfg.CTC_CENTER_RATE_ARCSEC_PER_SEC,
        allow_tracking_off=_cfg.CTC_ALLOW_TRACKING_OFF,
        cancellation_flag=_ctc_cancel_event,
    )
    return result.to_dict()


@router.post("/cancel")
def click_to_center_cancel() -> dict:
    """Cancel a running centering loop."""
    _ctc_cancel_event.set()
    return {"cancelled": True}
