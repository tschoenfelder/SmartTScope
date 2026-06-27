"""UserActionRecord — one structured entry for a user-initiated UI action (M8-016 / REQ-LOG-003)."""
from __future__ import annotations

import json
from dataclasses import dataclass


USER_ACTIONS: tuple[str, ...] = (
    "connect_all_clicked",
    "time_location_push_confirmed",
    "time_location_push_rejected",
    "raspberry_time_manually_confirmed",
    "goto_requested",
    "goto_rejected",
    "bright_star_goto_requested",
    "tracking_enable_requested",
    "tracking_enable_rejected",
    "plate_solve_requested",
    "autofocus_started",
    "autofocus_cancelled",
    "collimation_started",
    "collimation_mode_selected",
    "click_to_center_requested",
    "click_to_center_cancelled",
    "diagnostic_exposure_test_started",
    "github_push_requested",
)


@dataclass
class UserActionRecord:
    """One structured log entry for a user-initiated UI action (REQ-LOG-003).

    All 18 named actions share this schema.  Rejections populate gate_reason.
    """

    action: str
    timestamp: str           # ISO-8601 UTC string
    result: str | None       # "ok" | "rejected" | None
    gate_reason: str | None  # present when result == "rejected" and reason is known

    def to_dict(self) -> dict:
        return {
            "action":      self.action,
            "timestamp":   self.timestamp,
            "result":      self.result,
            "gate_reason": self.gate_reason,
        }

    def to_json_line(self) -> str:
        return json.dumps(self.to_dict(), default=str)
