"""Observation queue domain — ordered list of pending observation jobs."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class QueueEntryStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE    = "DONE"
    FAILED  = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass
class QueueEntry:
    target_name:      str
    target_ra:        float
    target_dec:       float
    profile:          str   = "c8_native"
    exposure:         float = 30.0
    stack_depth:      int   = 10
    min_altitude_deg: float = 20.0
    entry_id:         str              = field(default_factory=lambda: str(uuid.uuid4()))
    status:           QueueEntryStatus = field(default=QueueEntryStatus.PENDING)
    added_at:         datetime         = field(default_factory=lambda: datetime.now(UTC))
    started_at:       datetime | None  = None
    completed_at:     datetime | None  = None
    session_id:       str | None       = None
    failure_reason:   str | None       = None

    def to_dict(self) -> dict[str, object]:
        return {
            "entry_id":         self.entry_id,
            "target_name":      self.target_name,
            "target_ra":        self.target_ra,
            "target_dec":       self.target_dec,
            "profile":          self.profile,
            "exposure":         self.exposure,
            "stack_depth":      self.stack_depth,
            "min_altitude_deg": self.min_altitude_deg,
            "status":           self.status.value,
            "added_at":         self.added_at.isoformat(),
            "started_at":       self.started_at.isoformat() if self.started_at else None,
            "completed_at":     self.completed_at.isoformat() if self.completed_at else None,
            "session_id":       self.session_id,
            "failure_reason":   self.failure_reason,
        }


class ObservationQueue:
    """Thread-safe ordered list of observation jobs.

    Entries are processed in insertion order.  Only PENDING entries may be
    removed; RUNNING / DONE / FAILED / SKIPPED entries are read-only from the
    queue's perspective (the queue runner owns those state transitions).
    """

    def __init__(self) -> None:
        self._entries: list[QueueEntry] = []
        self._lock = threading.Lock()

    # ── Mutations ─────────────────────────────────────────────────────────

    def add(self, entry: QueueEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def remove(self, entry_id: str) -> bool:
        """Remove a PENDING entry by ID.  Returns True if an entry was removed."""
        with self._lock:
            before = len(self._entries)
            self._entries = [
                e for e in self._entries
                if not (e.entry_id == entry_id and e.status == QueueEntryStatus.PENDING)
            ]
            return len(self._entries) < before

    def clear_completed(self) -> None:
        """Drop all DONE, FAILED, and SKIPPED entries, keeping PENDING and RUNNING."""
        with self._lock:
            self._entries = [
                e for e in self._entries
                if e.status in (QueueEntryStatus.PENDING, QueueEntryStatus.RUNNING)
            ]

    # ── Queries ───────────────────────────────────────────────────────────

    def get(self, entry_id: str) -> QueueEntry | None:
        with self._lock:
            return next((e for e in self._entries if e.entry_id == entry_id), None)

    def next_pending(self) -> QueueEntry | None:
        """Return the first PENDING entry without removing it, or None."""
        with self._lock:
            return next(
                (e for e in self._entries if e.status == QueueEntryStatus.PENDING),
                None,
            )

    def all(self) -> list[QueueEntry]:
        with self._lock:
            return list(self._entries)

    def pending(self) -> list[QueueEntry]:
        with self._lock:
            return [e for e in self._entries if e.status == QueueEntryStatus.PENDING]

    def to_list(self) -> list[dict[str, object]]:
        with self._lock:
            return [e.to_dict() for e in self._entries]
