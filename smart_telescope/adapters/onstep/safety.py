"""SmartTScope safety-config extension over the external onstep_adapter package.

Everything except ``OnStepSafetyConfig`` is a thin re-export (see SYNC.md).
"""
from dataclasses import dataclass

from onstep_adapter.safety import (
    OnStepLimitError,
    OnStepLimits,
    OnStepSafetyError,
    OverheadCorridor,
    SafetySeverity,
    SafetyViolation,
)
from onstep_adapter.safety import OnStepSafetyConfig as _BaseOnStepSafetyConfig


@dataclass(frozen=True)
class OnStepSafetyConfig(_BaseOnStepSafetyConfig):
    # SYNC-OVERRIDE (pending upstream request): time/location sync tolerances
    # read by the shim's get_sync_status() (REQ-ST-008 area); absent upstream
    # as of v0.3.1. Remove once upstream OnStepSafetyConfig adopts them.
    onstep_time_tolerance_s: float = 10.0
    onstep_location_tolerance_m: float = 100.0


__all__ = [
    "OnStepLimitError",
    "OnStepLimits",
    "OnStepSafetyConfig",
    "OnStepSafetyError",
    "OverheadCorridor",
    "SafetySeverity",
    "SafetyViolation",
]
