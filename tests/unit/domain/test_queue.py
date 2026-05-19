"""Unit tests for the ObservationQueue domain object."""
from __future__ import annotations

import threading
from datetime import UTC, datetime

import pytest

from smart_telescope.domain.queue import (
    ObservationQueue,
    QueueEntry,
    QueueEntryStatus,
)


# ── helpers ───────────────────────────────────────────────────────────────────


def _entry(name: str = "M42", ra: float = 5.588, dec: float = -5.391) -> QueueEntry:
    return QueueEntry(target_name=name, target_ra=ra, target_dec=dec)


# ── QueueEntry ────────────────────────────────────────────────────────────────


class TestQueueEntry:
    def test_defaults(self) -> None:
        e = _entry()
        assert e.profile == "c8_native"
        assert e.exposure == 30.0
        assert e.stack_depth == 10
        assert e.min_altitude_deg == 20.0
        assert e.status == QueueEntryStatus.PENDING
        assert e.session_id is None
        assert e.failure_reason is None

    def test_entry_id_is_unique(self) -> None:
        a = _entry()
        b = _entry()
        assert a.entry_id != b.entry_id

    def test_to_dict_keys(self) -> None:
        d = _entry().to_dict()
        for key in ("entry_id", "target_name", "target_ra", "target_dec", "profile",
                    "exposure", "stack_depth", "min_altitude_deg", "status",
                    "added_at", "started_at", "completed_at", "session_id", "failure_reason"):
            assert key in d

    def test_to_dict_status_is_string(self) -> None:
        d = _entry().to_dict()
        assert d["status"] == "PENDING"

    def test_to_dict_timestamps_none_when_not_started(self) -> None:
        d = _entry().to_dict()
        assert d["started_at"] is None
        assert d["completed_at"] is None

    def test_to_dict_iso_format_when_timestamp_set(self) -> None:
        e = _entry()
        e.started_at = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        d = e.to_dict()
        assert isinstance(d["started_at"], str)
        assert "2026-04-30" in d["started_at"]  # type: ignore[operator]


# ── ObservationQueue ──────────────────────────────────────────────────────────


class TestObservationQueue:
    def test_empty_queue(self) -> None:
        q = ObservationQueue()
        assert q.all() == []
        assert q.pending() == []
        assert q.next_pending() is None

    def test_add_single_entry(self) -> None:
        q = ObservationQueue()
        e = _entry()
        q.add(e)
        assert len(q.all()) == 1
        assert q.all()[0] is e

    def test_pending_returns_only_pending(self) -> None:
        q = ObservationQueue()
        e1 = _entry("M42")
        e2 = _entry("M31")
        e2.status = QueueEntryStatus.DONE
        q.add(e1)
        q.add(e2)
        assert q.pending() == [e1]

    def test_next_pending_returns_first(self) -> None:
        q = ObservationQueue()
        e1 = _entry("M42")
        e2 = _entry("M31")
        q.add(e1)
        q.add(e2)
        assert q.next_pending() is e1

    def test_next_pending_skips_non_pending(self) -> None:
        q = ObservationQueue()
        e1 = _entry("M42")
        e1.status = QueueEntryStatus.DONE
        e2 = _entry("M31")
        q.add(e1)
        q.add(e2)
        assert q.next_pending() is e2

    def test_get_by_id(self) -> None:
        q = ObservationQueue()
        e = _entry()
        q.add(e)
        assert q.get(e.entry_id) is e

    def test_get_unknown_id_returns_none(self) -> None:
        q = ObservationQueue()
        assert q.get("no-such-id") is None

    def test_remove_pending_entry(self) -> None:
        q = ObservationQueue()
        e = _entry()
        q.add(e)
        removed = q.remove(e.entry_id)
        assert removed is True
        assert q.all() == []

    def test_remove_returns_false_when_not_found(self) -> None:
        q = ObservationQueue()
        assert q.remove("phantom-id") is False

    def test_remove_does_not_remove_running_entry(self) -> None:
        q = ObservationQueue()
        e = _entry()
        e.status = QueueEntryStatus.RUNNING
        q.add(e)
        removed = q.remove(e.entry_id)
        assert removed is False
        assert len(q.all()) == 1

    def test_clear_completed_removes_done_and_failed(self) -> None:
        q = ObservationQueue()
        pending = _entry("M42")
        done = _entry("M31")
        done.status = QueueEntryStatus.DONE
        failed = _entry("M45")
        failed.status = QueueEntryStatus.FAILED
        q.add(pending)
        q.add(done)
        q.add(failed)
        q.clear_completed()
        assert q.all() == [pending]

    def test_clear_completed_keeps_running(self) -> None:
        q = ObservationQueue()
        running = _entry()
        running.status = QueueEntryStatus.RUNNING
        q.add(running)
        q.clear_completed()
        assert q.all() == [running]

    def test_to_list_serialises_all_entries(self) -> None:
        q = ObservationQueue()
        q.add(_entry("M42"))
        q.add(_entry("M31"))
        lst = q.to_list()
        assert len(lst) == 2
        assert all(isinstance(item, dict) for item in lst)

    def test_insertion_order_preserved(self) -> None:
        q = ObservationQueue()
        names = ["M42", "M31", "M45", "M51"]
        for n in names:
            q.add(_entry(n))
        assert [e.target_name for e in q.all()] == names

    def test_thread_safety_concurrent_adds(self) -> None:
        q = ObservationQueue()
        errors: list[Exception] = []

        def add_many() -> None:
            try:
                for _ in range(50):
                    q.add(_entry())
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=add_many) for _ in range(4)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert errors == []
        assert len(q.all()) == 200
