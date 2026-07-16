"""Thin re-export from the external onstep_adapter package (see SYNC.md).

``FocuserStatus``/``FocuserMoveResult`` stay canonical in
``smart_telescope.ports.focuser`` (ONS-MIGRATE-009b); they are field-identical
to upstream's and duck-type compatible with what the upstream focuser returns.
"""
from onstep_adapter.results import (
    AxisMotionResult,
    OnStepConnectionResult,
    OnStepMotionCalibration,
    SetParkPositionResult,
    StoredParkPosition,
)

from ...ports.focuser import FocuserMoveResult, FocuserStatus

__all__ = [
    "AxisMotionResult",
    "FocuserMoveResult",
    "FocuserStatus",
    "OnStepConnectionResult",
    "OnStepMotionCalibration",
    "SetParkPositionResult",
    "StoredParkPosition",
]
