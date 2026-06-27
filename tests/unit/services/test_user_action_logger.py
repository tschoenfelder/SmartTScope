"""Tests for UserActionLogger (M8-016 / REQ-LOG-003)."""
from __future__ import annotations

import json
import logging

import pytest

from smart_telescope.domain.user_action_log import USER_ACTIONS, UserActionRecord
from smart_telescope.services.section_logger import SectionLogger
from smart_telescope.services.user_action_logger import UserActionLogger


SESSION_ID = "test-session-id-0001"


@pytest.fixture
def section_logger():
    return SectionLogger(session_id=SESSION_ID)


@pytest.fixture
def ual(section_logger):
    return UserActionLogger(section_logger=section_logger, session_id=SESSION_ID)


def _capture(section_logger: SectionLogger, section: str) -> list[logging.LogRecord]:
    records: list[logging.LogRecord] = []

    class _H(logging.Handler):
        def emit(self, rec: logging.LogRecord) -> None:
            records.append(rec)

    section_logger.get(section).logger.addHandler(_H())
    return records


# ── Domain ────────────────────────────────────────────────────────────────────

def test_all_18_actions_defined():
    assert len(USER_ACTIONS) == 18


def test_user_action_record_to_json_line():
    rec = UserActionRecord(
        action="goto_requested",
        timestamp="2026-06-27T12:00:00+00:00",
        result="ok",
        gate_reason=None,
    )
    data = json.loads(rec.to_json_line())
    assert data["action"] == "goto_requested"
    assert data["result"] == "ok"
    assert data["gate_reason"] is None


def test_user_action_record_to_dict_keys():
    rec = UserActionRecord(action="connect_all_clicked", timestamp="t", result=None, gate_reason=None)
    d = rec.to_dict()
    assert set(d.keys()) == {"action", "timestamp", "result", "gate_reason"}


# ── Logger ────────────────────────────────────────────────────────────────────

def test_log_ok_goes_to_correct_section(ual, section_logger):
    records = _capture(section_logger, "startup")
    ual.log("connect_all_clicked", result="ok")
    assert len(records) == 1
    data = json.loads(records[0].getMessage())
    assert data["action"] == "connect_all_clicked"
    assert data["result"] == "ok"


def test_log_rejected_includes_gate_reason(ual, section_logger):
    records = _capture(section_logger, "goto")
    ual.log("goto_rejected", result="rejected", gate_reason="TIME_NOT_TRUSTED")
    data = json.loads(records[0].getMessage())
    assert data["result"] == "rejected"
    assert data["gate_reason"] == "TIME_NOT_TRUSTED"


def test_goto_requested_goes_to_goto_section(ual, section_logger):
    records = _capture(section_logger, "goto")
    ual.log("goto_requested", result="ok")
    assert len(records) == 1


def test_bright_star_goto_goes_to_goto_section(ual, section_logger):
    records = _capture(section_logger, "goto")
    ual.log("bright_star_goto_requested", result="ok")
    assert len(records) == 1


def test_tracking_enable_goes_to_mount_section(ual, section_logger):
    records = _capture(section_logger, "mount")
    ual.log("tracking_enable_requested", result="ok")
    assert len(records) == 1


def test_time_location_push_goes_to_stage1_section(ual, section_logger):
    records = _capture(section_logger, "stage1_time_location")
    ual.log("time_location_push_confirmed", result="ok")
    assert len(records) == 1


def test_autofocus_goes_to_autofocus_section(ual, section_logger):
    records = _capture(section_logger, "autofocus")
    ual.log("autofocus_started", result="ok")
    assert len(records) == 1


def test_collimation_goes_to_collimation_section(ual, section_logger):
    records = _capture(section_logger, "collimation")
    ual.log("collimation_started", result="ok")
    assert len(records) == 1


def test_plate_solve_goes_to_plate_solve_section(ual, section_logger):
    records = _capture(section_logger, "plate_solve")
    ual.log("plate_solve_requested", result="ok")
    assert len(records) == 1


def test_diagnostic_goes_to_auto_gain_section(ual, section_logger):
    records = _capture(section_logger, "auto_gain")
    ual.log("diagnostic_exposure_test_started", result="ok")
    assert len(records) == 1


def test_github_push_goes_to_github_delivery_section(ual, section_logger):
    records = _capture(section_logger, "github_delivery")
    ual.log("github_push_requested", result="ok")
    assert len(records) == 1


def test_unknown_action_falls_back_to_startup(ual, section_logger):
    records = _capture(section_logger, "startup")
    ual.log("this_is_not_a_real_action")
    assert len(records) == 1


def test_write_failure_does_not_propagate():
    broken = object()
    ual = UserActionLogger(section_logger=broken, session_id=SESSION_ID)  # type: ignore[arg-type]
    ual.log("connect_all_clicked")  # should not raise


def test_timestamp_is_iso_utc(ual, section_logger):
    records = _capture(section_logger, "startup")
    ual.log("connect_all_clicked")
    data = json.loads(records[0].getMessage())
    ts = data["timestamp"]
    assert "T" in ts and (ts.endswith("+00:00") or ts.endswith("Z"))
