"""Unit tests for GET /api/commands (M8-012 / REQ-API-003)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps, session as session_module
from smart_telescope.app import app
from smart_telescope.domain.command_status import CommandStatus
from smart_telescope.services.command_history import CommandHistoryService

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    session_module._reset_session()
    yield
    app.dependency_overrides.clear()
    deps.reset()
    session_module._reset_session()


def _svc() -> CommandHistoryService:
    return CommandHistoryService(session_id="test-session")


def _inject(svc: CommandHistoryService) -> None:
    app.dependency_overrides[deps.get_command_history_service] = lambda: svc


def _get() -> dict:
    return client.get("/api/commands").json()


class TestGetCommands:
    def test_returns_200(self) -> None:
        _inject(_svc())
        assert client.get("/api/commands").status_code == 200

    def test_empty_when_no_commands(self) -> None:
        _inject(_svc())
        assert _get()["commands"] == []

    def test_requested_command_visible(self) -> None:
        svc = _svc()
        svc.record("goto", "goto", {"ra": 5.5, "dec": -5.3})
        _inject(svc)
        cmds = _get()["commands"]
        assert len(cmds) == 1
        assert cmds[0]["user_action"] == "goto"
        assert cmds[0]["status"] == "REQUESTED"

    def test_rejected_command_included(self) -> None:
        svc = _svc()
        rec = svc.record("goto", "goto")
        svc.update(rec.command_id, CommandStatus.REJECTED,
                   reason_code="GATE_BLOCKED", human_message="Mount not connected")
        _inject(svc)
        cmds = _get()["commands"]
        assert cmds[0]["status"] == "REJECTED"
        assert cmds[0]["reason_code"] == "GATE_BLOCKED"
        assert cmds[0]["human_message"] == "Mount not connected"

    def test_multiple_commands_in_order(self) -> None:
        svc = _svc()
        svc.record("park", "park")
        svc.record("goto", "goto")
        _inject(svc)
        cmds = _get()["commands"]
        assert len(cmds) == 2
        assert cmds[0]["user_action"] == "park"
        assert cmds[1]["user_action"] == "goto"

    def test_all_required_fields_present(self) -> None:
        svc = _svc()
        svc.record("goto", "goto", {"ra": 1.0})
        _inject(svc)
        record = _get()["commands"][0]
        for field in (
            "command_id", "session_id", "timestamp", "user_action", "operation",
            "requested_parameters", "status", "reason_code", "human_message",
            "backend_response", "related_log_file", "related_frame_file_if_any",
        ):
            assert field in record, f"missing field: {field}"
