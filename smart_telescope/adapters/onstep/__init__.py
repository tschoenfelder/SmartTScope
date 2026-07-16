import onstep_adapter as _onstep_adapter

from .client import OnStepClient
from .focuser import OnStepFocuser
from .mount import OnStepMount
from .results import (
    AxisMotionResult,
    FocuserMoveResult,
    FocuserStatus,
    OnStepConnectionResult,
    OnStepMotionCalibration,
    SetParkPositionResult,
    StoredParkPosition,
)
from .safety import (
    OnStepSafetyConfig,
    OnStepSafetyError,
    SafetySeverity,
    SafetyViolation,
)

# Version comes from the installed wheel (readiness reporting reads this).
__version__ = _onstep_adapter.__version__

__all__ = [
    "AxisMotionResult",
    "FocuserMoveResult",
    "FocuserStatus",
    "OnStepClient",
    "OnStepConnectionResult",
    "OnStepMotionCalibration",
    "OnStepFocuser",
    "OnStepMount",
    "OnStepSafetyConfig",
    "OnStepSafetyError",
    "SafetySeverity",
    "SafetyViolation",
    "SetParkPositionResult",
    "StoredParkPosition",
]
