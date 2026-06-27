"""CommandHistoryService — per-session JSONL command audit log (REQ-CMD-001).

Records all user-requested operations with their lifecycle status transitions.
In-memory dict is authoritative for the running session; JSONL file provides
durability for diagnostics (one line per status change, append-only).

Usage::

    svc = CommandHistoryService(session_id="abc123", path=Path("/tmp/cmds.jsonl"))
    rec = svc.record("goto", "goto", {"ra": 5.5, "dec": -5.3})
    svc.update(rec.command_id, CommandStatus.ISSUED)
    svc.update(rec.command_id, CommandStatus.SUCCEEDED, backend_response={"ok": True})
"""
from __future__ import annotations

import dataclasses
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..domain.command_status import CommandStatus

_log = logging.getLogger(__name__)


@dataclasses.dataclass
class CommandRecord:
    command_id:               str
    session_id:               str
    timestamp:                str          # ISO UTC — when first created
    user_action:              str          # e.g. "goto", "sync_clock", "park"
    operation:                str          # internal op name
    requested_parameters:     dict
    status:                   CommandStatus
    reason_code:              str | None   # e.g. "GATE_BLOCKED"
    human_message:            str | None
    backend_response:         dict | None
    related_log_file:         str | None
    related_frame_file_if_any: str | None

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        d["status"] = self.status.value
        return d


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CommandHistoryService:
    """Thread-safe per-session command history store.

    Parameters
    ----------
    session_id:
        UUID string identifying the current application session.
    path:
        Optional JSONL file path.  If None (default), records are kept
        in-memory only — useful for tests and environments without a
        configured COMMAND_HISTORY_DIR.
    """

    def __init__(self, session_id: str, path: Path | None = None) -> None:
        self._session_id = session_id
        self._path       = path
        self._lock       = threading.Lock()
        self._records: dict[str, CommandRecord] = {}  # ordered insertion (Python 3.7+)

        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                _log.warning("CommandHistoryService: cannot create directory %s: %s", path.parent, exc)
                self._path = None

    # ── public API ────────────────────────────────────────────────────────────

    def record(
        self,
        user_action: str,
        operation: str,
        requested_parameters: dict | None = None,
    ) -> CommandRecord:
        """Create a new REQUESTED record and return it."""
        rec = CommandRecord(
            command_id=str(uuid.uuid4()),
            session_id=self._session_id,
            timestamp=_utc_now(),
            user_action=user_action,
            operation=operation,
            requested_parameters=requested_parameters or {},
            status=CommandStatus.REQUESTED,
            reason_code=None,
            human_message=None,
            backend_response=None,
            related_log_file=None,
            related_frame_file_if_any=None,
        )
        with self._lock:
            self._records[rec.command_id] = rec
            self._append(rec)
        return rec

    def update(
        self,
        command_id: str,
        status: CommandStatus,
        *,
        reason_code: str | None = None,
        human_message: str | None = None,
        backend_response: dict | None = None,
        related_log_file: str | None = None,
        related_frame_file_if_any: str | None = None,
    ) -> CommandRecord | None:
        """Update the status (and optional metadata) of an existing record.

        Returns the updated record, or None if command_id is unknown.
        """
        with self._lock:
            rec = self._records.get(command_id)
            if rec is None:
                _log.warning("CommandHistoryService.update: unknown command_id %s", command_id)
                return None
            rec.status = status
            if reason_code is not None:
                rec.reason_code = reason_code
            if human_message is not None:
                rec.human_message = human_message
            if backend_response is not None:
                rec.backend_response = backend_response
            if related_log_file is not None:
                rec.related_log_file = related_log_file
            if related_frame_file_if_any is not None:
                rec.related_frame_file_if_any = related_frame_file_if_any
            self._append(rec)
        return rec

    def get_all(self) -> list[CommandRecord]:
        """Return all records in insertion order."""
        with self._lock:
            return list(self._records.values())

    def get_by_id(self, command_id: str) -> CommandRecord | None:
        with self._lock:
            return self._records.get(command_id)

    # ── internal ─────────────────────────────────────────────────────────────

    def _append(self, rec: CommandRecord) -> None:
        """Append a JSON snapshot of *rec* to the JSONL file (caller holds lock)."""
        if self._path is None:
            return
        try:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            _log.warning("CommandHistoryService: write failed: %s", exc)
