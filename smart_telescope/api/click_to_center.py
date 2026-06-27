"""Click-to-center readiness API — M8-025 / REQ-CLICK-001.

Endpoints:
  GET /api/click_to_center/readiness — gate check for click-to-center
"""
from __future__ import annotations

from fastapi import APIRouter

from . import deps as _deps
from ..services.operation_gate import evaluate_gate, gate_inputs_from_device_state

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
