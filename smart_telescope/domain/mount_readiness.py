"""MountReadinessState — derived composite state (M8-002 / REQ-STATE-002).

Derived from the six separate state categories exposed by /api/status.
Drives UI messages and reconnect guidance: reconnect is only suggested when
the state is DISCONNECTED or ERROR — not for trust/verification failures.
"""

from __future__ import annotations

from enum import Enum


class MountReadinessState(Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTED_HEALTH_UNKNOWN = "CONNECTED_HEALTH_UNKNOWN"
    CONNECTED_RESTRICTED = "CONNECTED_RESTRICTED"
    CONNECTED_TIME_LOCATION_UNVERIFIED = "CONNECTED_TIME_LOCATION_UNVERIFIED"
    CONNECTED_RASPBERRY_TIME_UNTRUSTED = "CONNECTED_RASPBERRY_TIME_UNTRUSTED"
    CONNECTED_READY = "CONNECTED_READY"
    ERROR = "ERROR"


def derive_mount_readiness(
    adapter_connection: str,
    adapter_health: str,
    onstep_time_location: str,
    raspberry_time_trust: str,
) -> MountReadinessState:
    """Derive the composite mount readiness state from the four relevant categories.

    Priority order (highest to lowest):
      1. Adapter not open          → DISCONNECTED
      2. Health check failing      → ERROR
      3. Health check unknown      → CONNECTED_HEALTH_UNKNOWN
      4. Time/location not checked → CONNECTED_RESTRICTED   (Stage 1 not run)
      5. Time/location unverified  → CONNECTED_TIME_LOCATION_UNVERIFIED
      6. Raspberry time not trusted→ CONNECTED_RASPBERRY_TIME_UNTRUSTED
      7. All conditions met        → CONNECTED_READY
    """
    if adapter_connection != "OPEN":
        return MountReadinessState.DISCONNECTED
    if adapter_health == "FAILED":
        return MountReadinessState.ERROR
    if adapter_health == "UNKNOWN":
        return MountReadinessState.CONNECTED_HEALTH_UNKNOWN
    # adapter_health == "OK"
    if onstep_time_location == "UNKNOWN":
        return MountReadinessState.CONNECTED_RESTRICTED
    if onstep_time_location == "UNVERIFIED":
        return MountReadinessState.CONNECTED_TIME_LOCATION_UNVERIFIED
    # onstep_time_location == "VERIFIED"
    if raspberry_time_trust != "TRUSTED":
        return MountReadinessState.CONNECTED_RASPBERRY_TIME_UNTRUSTED
    return MountReadinessState.CONNECTED_READY
