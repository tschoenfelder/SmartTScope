"""Click-to-center API — M8-025/M8-026 / REQ-CLICK-001..002.

Endpoints:
  GET  /api/click_to_center/readiness — gate check
  POST /api/click_to_center/refine    — refine raw click to star centroid or ring center
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import deps as _deps
from .preview import get_last_preview_pixels
from ..domain.click_refinement import refine_click
from ..services.operation_gate import evaluate_gate, gate_inputs_from_device_state

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/click_to_center", tags=["click_to_center"])


@router.get("/readiness")
def click_to_center_readiness() -> dict:
    """Return whether click-to-center is currently allowed and why if not."""
    inputs = gate_inputs_from_device_state(
        _deps.get_device_state(),
        master_source_svc=_deps.get_master_source_service(),
        raspberry_trust_svc=_deps.get_raspberry_trust_service(),
    )
    result = evaluate_gate("click_to_center", **inputs)
    return {
        "allowed": result.allowed,
        "reason": result.human_message,
        "required_action": result.required_user_action,
    }


class RefineRequest(BaseModel):
    x_px: int
    y_px: int
    camera_index: int = 0
    mode: str = "star_centroid"   # "star_centroid" | "ring_center"
    search_radius: int = 40


@router.post("/refine")
def click_to_center_refine(req: RefineRequest) -> dict:
    """Refine a raw click coordinate using the latest preview frame.

    Returns a RefinedClick dict with refined_x/y, method, and confidence.
    Falls back to raw coords if no frame is cached or no feature is found.
    """
    pixels = get_last_preview_pixels(req.camera_index)
    if pixels is None:
        # No frame cached — return raw fallback with explicit note
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
