"""PlateSolveReadiness — 8-condition pre-check before plate solving (M8-020 / REQ-PS-001)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

READINESS_CONDITIONS: tuple[str, ...] = (
    "frame_exists",
    "frame_saved_as_fits",
    "optical_train_metadata_available",
    "pixel_size_available",
    "focal_length_or_hint_available",
    "star_count_measured",
    "astap_available",
    "operation_gate_allows_plate_solve",
)


@dataclass
class ReadinessCondition:
    """One of the 8 readiness conditions with its satisfaction state and failure reason."""
    name:      str
    satisfied: bool
    reason:    str | None = None  # specific failure reason when satisfied=False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "satisfied": self.satisfied, "reason": self.reason}


@dataclass
class PlateSolveReadinessResult:
    """Result of the plate-solve readiness pre-check (8 conditions, REQ-PS-001).

    ready=True only when all conditions are satisfied.
    Each failed condition includes a specific reason string.
    """
    ready:      bool
    conditions: list[ReadinessCondition] = field(default_factory=list)

    @property
    def first_failure(self) -> ReadinessCondition | None:
        """Return the first unsatisfied condition, or None if all pass."""
        for c in self.conditions:
            if not c.satisfied:
                return c
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready":         self.ready,
            "conditions":    [c.to_dict() for c in self.conditions],
            "first_failure": self.first_failure.to_dict() if self.first_failure else None,
        }

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), default=str)
