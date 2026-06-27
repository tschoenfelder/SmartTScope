"""Unit tests for CommandHistoryService (M8-011 / REQ-CMD-001)."""
from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from smart_telescope.domain.command_status import CommandStatus
from smart_telescope.services.command_history import CommandHistoryService


def _svc(tmp_path: Path | None = None) -> CommandHistoryService:
    path = (tmp_path / "cmds.jsonl") if tmp_path is not None else None
    return CommandHistoryService(session_id="test-session-id", path=path)


# ── record() ─────────────────────────────────────────────────────────────────


class TestRecord:
    def test_record_creates_with_requested_status(self) -> None:
        svc = _svc()
        rec = svc.record("goto", "goto", {"ra": 5.5, "dec": -5.3})
        assert rec.status == CommandStatus.REQUESTED

    def test_record_assigns_unique_command_id(self) -> None:
        svc = _svc()
        r1 = svc.record("goto", "goto")
        r2 = svc.record("goto", "goto")
        assert r1.command_id != r2.command_id

    def test_record_sets_session_id(self) -> None:
        svc = _svc()
        rec = svc.record("park", "park")
        assert rec.session_id == "test-session-id"

    def test_record_stores_user_action_and_operation(self) -> None:
        svc = _svc()
        rec = svc.record("goto", "bright_star_goto", {"ra": 1.0, "dec": 2.0})
        assert rec.user_action == "goto"
        assert rec.operation == "bright_star_goto"
        assert rec.requested_parameters == {"ra": 1.0, "dec": 2.0}

    def test_record_optional_fields_default_none(self) -> None:
        svc = _svc()
        rec = svc.record("park", "park")
        assert rec.reason_code is None
        assert rec.human_message is None
        assert rec.backend_response is None
        assert rec.related_log_file is None
        assert rec.related_frame_file_if_any is None

    def test_record_has_utc_timestamp(self) -> None:
        svc = _svc()
        rec = svc.record("park", "park")
        assert rec.timestamp.endswith("Z")


# ── update() ─────────────────────────────────────────────────────────────────


class TestUpdate:
    def test_update_changes_status(self) -> None:
        svc = _svc()
        rec = svc.record("goto", "goto")
        svc.update(rec.command_id, CommandStatus.ISSUED)
        assert svc.get_by_id(rec.command_id).status == CommandStatus.ISSUED

    def test_update_sets_reason_code_and_human_message(self) -> None:
        svc = _svc()
        rec = svc.record("goto", "goto")
        svc.update(
            rec.command_id, CommandStatus.REJECTED,
            reason_code="GATE_BLOCKED", human_message="Mount not connected",
        )
        updated = svc.get_by_id(rec.command_id)
        assert updated.reason_code == "GATE_BLOCKED"
        assert updated.human_message == "Mount not connected"
        assert updated.status == CommandStatus.REJECTED

    def test_update_sets_backend_response(self) -> None:
        svc = _svc()
        rec = svc.record("sync_clock", "sync_clock")
        svc.update(rec.command_id, CommandStatus.SUCCEEDED, backend_response={"ok": True})
        assert svc.get_by_id(rec.command_id).backend_response == {"ok": True}

    def test_update_unknown_id_returns_none(self) -> None:
        svc = _svc()
        result = svc.update("nonexistent-id", CommandStatus.FAILED)
        assert result is None

    def test_update_through_full_lifecycle(self) -> None:
        svc = _svc()
        rec = svc.record("goto", "goto")
        for status in (CommandStatus.ISSUED, CommandStatus.RUNNING, CommandStatus.SUCCEEDED):
            svc.update(rec.command_id, status)
        assert svc.get_by_id(rec.command_id).status == CommandStatus.SUCCEEDED


# ── get_all() ────────────────────────────────────────────────────────────────


class TestGetAll:
    def test_get_all_empty_initially(self) -> None:
        svc = _svc()
        assert svc.get_all() == []

    def test_get_all_returns_all_records_in_order(self) -> None:
        svc = _svc()
        r1 = svc.record("park", "park")
        r2 = svc.record("goto", "goto")
        all_ids = [r.command_id for r in svc.get_all()]
        assert all_ids == [r1.command_id, r2.command_id]

    def test_rejected_command_visible_in_get_all(self) -> None:
        svc = _svc()
        rec = svc.record("goto", "goto")
        svc.update(rec.command_id, CommandStatus.REJECTED, reason_code="GATE_BLOCKED")
        records = svc.get_all()
        assert len(records) == 1
        assert records[0].status == CommandStatus.REJECTED


# ── JSONL persistence ─────────────────────────────────────────────────────────


class TestJSONL:
    def test_record_written_to_jsonl(self, tmp_path: Path) -> None:
        svc = _svc(tmp_path)
        svc.record("goto", "goto", {"ra": 1.0})
        lines = (tmp_path / "cmds.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["status"] == "REQUESTED"
        assert data["user_action"] == "goto"

    def test_update_appends_new_jsonl_line(self, tmp_path: Path) -> None:
        svc = _svc(tmp_path)
        rec = svc.record("goto", "goto")
        svc.update(rec.command_id, CommandStatus.ISSUED)
        lines = (tmp_path / "cmds.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        assert json.loads(lines[1])["status"] == "ISSUED"

    def test_jsonl_contains_all_required_fields(self, tmp_path: Path) -> None:
        svc = _svc(tmp_path)
        svc.record("park", "park", {"speed": 1})
        data = json.loads((tmp_path / "cmds.jsonl").read_text(encoding="utf-8").splitlines()[0])
        for field in (
            "command_id", "session_id", "timestamp", "user_action", "operation",
            "requested_parameters", "status", "reason_code", "human_message",
            "backend_response", "related_log_file", "related_frame_file_if_any",
        ):
            assert field in data, f"missing field: {field}"

    def test_no_file_io_when_path_is_none(self) -> None:
        svc = _svc()
        svc.record("park", "park")
        svc.update(svc.get_all()[0].command_id, CommandStatus.SUCCEEDED)
        assert svc.get_all()[0].status == CommandStatus.SUCCEEDED


# ── thread safety ─────────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_records_all_stored(self) -> None:
        svc = _svc()
        results = []

        def _worker():
            r = svc.record("goto", "goto")
            results.append(r.command_id)

        threads = [threading.Thread(target=_worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 20
        assert len(set(results)) == 20  # all unique IDs
        assert len(svc.get_all()) == 20
