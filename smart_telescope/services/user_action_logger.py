"""UserActionLogger — writes user-action records to section loggers (M8-016 / REQ-LOG-003).

Usage::

    rt.user_action_logger.log("connect_all_clicked")
    rt.user_action_logger.log("goto_rejected", result="rejected", gate_reason="TIME_NOT_TRUSTED")
    rt.user_action_logger.log("goto_requested", result="ok")
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .section_logger import SectionLogger

from ..domain.user_action_log import UserActionRecord

_log = logging.getLogger(__name__)

# Maps each of the 18 named actions to the most relevant section logger.
_ACTION_SECTIONS: dict[str, str] = {
    "connect_all_clicked":            "startup",
    "time_location_push_confirmed":   "stage1_time_location",
    "time_location_push_rejected":    "stage1_time_location",
    "raspberry_time_manually_confirmed": "stage1_time_location",
    "goto_requested":                 "goto",
    "goto_rejected":                  "goto",
    "bright_star_goto_requested":     "goto",
    "tracking_enable_requested":      "mount",
    "tracking_enable_rejected":       "mount",
    "plate_solve_requested":          "plate_solve",
    "autofocus_started":              "autofocus",
    "autofocus_cancelled":            "autofocus",
    "collimation_started":            "collimation",
    "collimation_mode_selected":      "collimation",
    "click_to_center_requested":      "click_to_center",
    "click_to_center_cancelled":      "click_to_center",
    "diagnostic_exposure_test_started": "auto_gain",
    "github_push_requested":          "github_delivery",
}


class UserActionLogger:
    """Writes one JSON-line UserActionRecord to the appropriate section logger.

    One instance lives on RuntimeContext for the lifetime of the app session.
    """

    def __init__(self, section_logger: SectionLogger, session_id: str) -> None:
        self._section_logger = section_logger
        self._session_id     = session_id

    def log(
        self,
        action: str,
        result: str | None = None,
        gate_reason: str | None = None,
    ) -> None:
        """Write one user-action log record.

        Args:
            action:      One of the 18 named action strings (USER_ACTIONS).
            result:      "ok" | "rejected" | None.
            gate_reason: Human-readable gate/rejection reason (when result=="rejected").
        """
        section = _ACTION_SECTIONS.get(action, "startup")
        rec = UserActionRecord(
            action=action,
            timestamp=datetime.now(timezone.utc).isoformat(),
            result=result,
            gate_reason=gate_reason,
        )
        try:
            self._section_logger.get(section).info("%s", rec.to_json_line())
        except Exception as exc:
            _log.warning("UserActionLogger: failed to write record for %r: %s", action, exc)
