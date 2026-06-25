"""OperationGateService — M8-003 / REQ-STATE-003.

Evaluates whether each of the 13 gated operations is currently allowed,
returning a GateResult per operation. Callers pass the already-computed
state strings so this module has no I/O dependencies.
"""

from __future__ import annotations

import dataclasses

GATED_OPERATIONS: tuple[str, ...] = (
    "camera_capture",
    "manual_mount_move",
    "tracking_enable",
    "goto",
    "bright_star_goto",
    "sync",
    "plate_solve",
    "plate_solve_mount_correction",
    "collimation_preview",
    "collimation_slew_to_target",
    "collimation_mount_centering",
    "autofocus",
    "click_to_center",
)

# Operations that only use the camera — no mount state required.
_CAMERA_ONLY = {"camera_capture", "plate_solve", "collimation_preview"}

# Operations that need adapter OPEN + health OK, but NOT Stage 1 time/location.
_PARTIAL_MOUNT = {"manual_mount_move", "autofocus"}

# Remaining operations require full Stage 1 (OPEN + OK + VERIFIED + TRUSTED).
# A subset also block when the mount is PARKED.
_PARKED_BLOCKED = {"goto", "bright_star_goto", "click_to_center"}

_REASON_MESSAGES: dict[str, tuple[str, str]] = {
    "ADAPTER_DISCONNECTED": (
        "Mount adapter is not connected. Run Connect All to establish a connection.",
        "run_connect_all",
    ),
    "ADAPTER_HEALTH_FAILED": (
        "Mount adapter reported a hardware error. Check cables and restart.",
        "run_connect_all",
    ),
    "ADAPTER_HEALTH_UNKNOWN": (
        "Mount adapter health has not been confirmed yet.",
        "run_connect_all",
    ),
    "TIME_LOCATION_UNVERIFIED": (
        "Stage 1 (time/location verification) has not been completed.",
        "run_stage1",
    ),
    "RASPBERRY_TIME_UNTRUSTED": (
        "Raspberry Pi system time is not trusted. Run Stage 1 to establish trust.",
        "run_stage1",
    ),
    "MOUNT_PARKED": (
        "The mount is parked. Unpark it before issuing movement commands.",
        "unpark_mount",
    ),
}


@dataclasses.dataclass
class GateResult:
    allowed: bool
    reason_code: str | None = None
    human_message: str | None = None
    required_user_action: str | None = None
    blocking_states: list[str] = dataclasses.field(default_factory=list)


def _allowed() -> GateResult:
    return GateResult(allowed=True)


def _blocked(reason_code: str, blocking_state: str) -> GateResult:
    message, action = _REASON_MESSAGES[reason_code]
    return GateResult(
        allowed=False,
        reason_code=reason_code,
        human_message=message,
        required_user_action=action,
        blocking_states=[blocking_state],
    )


def _evaluate_one(
    op: str,
    adapter_connection: str,
    adapter_health: str,
    mount_operational_state: str,
    onstep_time_location: str,
    raspberry_time_trust: str,
) -> GateResult:
    if op in _CAMERA_ONLY:
        return _allowed()

    # All remaining ops need adapter open and health not failed/unknown.
    if adapter_connection != "OPEN":
        return _blocked("ADAPTER_DISCONNECTED", "adapter_connection_state=CLOSED")
    if adapter_health == "FAILED":
        return _blocked("ADAPTER_HEALTH_FAILED", "adapter_health_state=FAILED")
    if adapter_health == "UNKNOWN":
        return _blocked("ADAPTER_HEALTH_UNKNOWN", "adapter_health_state=UNKNOWN")

    if op in _PARTIAL_MOUNT:
        return _allowed()

    # Full Stage 1 required for the rest.
    if onstep_time_location != "VERIFIED":
        return _blocked("TIME_LOCATION_UNVERIFIED", f"onstep_time_location_state={onstep_time_location}")
    if raspberry_time_trust != "TRUSTED":
        return _blocked("RASPBERRY_TIME_UNTRUSTED", f"raspberry_time_trust_state={raspberry_time_trust}")

    if op in _PARKED_BLOCKED and mount_operational_state == "PARKED":
        return _blocked("MOUNT_PARKED", "mount_operational_state=PARKED")

    return _allowed()


def evaluate_all_gates(
    adapter_connection: str,
    adapter_health: str,
    mount_operational_state: str,
    onstep_time_location: str,
    raspberry_time_trust: str,
) -> dict[str, GateResult]:
    """Return a GateResult for every gated operation given the current system state."""
    return {
        op: _evaluate_one(
            op,
            adapter_connection,
            adapter_health,
            mount_operational_state,
            onstep_time_location,
            raspberry_time_trust,
        )
        for op in GATED_OPERATIONS
    }
