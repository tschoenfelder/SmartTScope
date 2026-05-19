"""Unit tests for the Observation Queue API."""
from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import queue as queue_module
from smart_telescope.app import app
from smart_telescope.domain.queue import QueueEntryStatus

client = TestClient(app)

_BASE = "/api/queue"
_CLEAR = "/api/queue/clear"


def _payload(**kwargs: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "target_name": "M42",
        "target_ra": 5.588,
        "target_dec": -5.391,
    }
    return {**base, **kwargs}


@pytest.fixture(autouse=True)
def _reset() -> None:
    queue_module._reset_queue()
    yield
    queue_module._reset_queue()


# ── POST /api/queue ───────────────────────────────────────────────────────────


class TestAddEntry:
    def test_201_on_valid_input(self) -> None:
        assert client.post(_BASE, json=_payload()).status_code == 201

    def test_entry_id_present_in_response(self) -> None:
        assert "entry_id" in client.post(_BASE, json=_payload()).json()

    def test_defaults_applied(self) -> None:
        body = client.post(_BASE, json=_payload()).json()
        assert body["profile"] == "c8_native"
        assert body["exposure"] == 30.0
        assert body["stack_depth"] == 10
        assert body["status"] == "PENDING"

    def test_custom_fields_stored(self) -> None:
        body = client.post(_BASE, json=_payload(
            profile="c8_reducer", exposure=60.0, stack_depth=20, min_altitude_deg=25.0,
        )).json()
        assert body["profile"] == "c8_reducer"
        assert body["exposure"] == 60.0
        assert body["stack_depth"] == 20
        assert body["min_altitude_deg"] == 25.0

    def test_422_on_invalid_profile(self) -> None:
        assert client.post(_BASE, json=_payload(profile="superzoom")).status_code == 422

    def test_422_on_ra_out_of_range(self) -> None:
        assert client.post(_BASE, json=_payload(target_ra=25.0)).status_code == 422

    def test_422_on_dec_out_of_range(self) -> None:
        assert client.post(_BASE, json=_payload(target_dec=95.0)).status_code == 422

    def test_422_on_missing_target_name(self) -> None:
        r = client.post(_BASE, json={"target_ra": 5.588, "target_dec": -5.391})
        assert r.status_code == 422

    def test_entry_appears_in_list_after_add(self) -> None:
        client.post(_BASE, json=_payload(target_name="M31"))
        names = [e["target_name"] for e in client.get(_BASE).json()]
        assert "M31" in names


# ── GET /api/queue ────────────────────────────────────────────────────────────


class TestListEntries:
    def test_empty_list_initially(self) -> None:
        assert client.get(_BASE).json() == []

    def test_returns_all_added_entries(self) -> None:
        client.post(_BASE, json=_payload(target_name="M42"))
        client.post(_BASE, json=_payload(target_name="M31"))
        assert len(client.get(_BASE).json()) == 2

    def test_insertion_order_preserved(self) -> None:
        for name in ["M42", "M31", "M45"]:
            client.post(_BASE, json=_payload(target_name=name))
        names = [e["target_name"] for e in client.get(_BASE).json()]
        assert names == ["M42", "M31", "M45"]

    def test_status_filter_returns_only_matching(self) -> None:
        eid = client.post(_BASE, json=_payload(target_name="M42")).json()["entry_id"]
        client.post(_BASE, json=_payload(target_name="M31"))
        # mark first entry as DONE
        queue_module.get_queue().get(eid).status = QueueEntryStatus.DONE  # type: ignore[union-attr]
        pending = client.get(f"{_BASE}?status=PENDING").json()
        assert len(pending) == 1
        assert pending[0]["target_name"] == "M31"

    def test_status_filter_is_case_insensitive(self) -> None:
        client.post(_BASE, json=_payload())
        assert len(client.get(f"{_BASE}?status=pending").json()) == 1

    def test_422_on_unknown_status_filter(self) -> None:
        assert client.get(f"{_BASE}?status=ZOMBIE").status_code == 422


# ── GET /api/queue/{entry_id} ─────────────────────────────────────────────────


class TestGetEntry:
    def test_returns_entry_when_found(self) -> None:
        eid = client.post(_BASE, json=_payload()).json()["entry_id"]
        body = client.get(f"{_BASE}/{eid}").json()
        assert body["entry_id"] == eid
        assert body["target_name"] == "M42"

    def test_404_when_not_found(self) -> None:
        assert client.get(f"{_BASE}/no-such-id").status_code == 404


# ── DELETE /api/queue/{entry_id} ─────────────────────────────────────────────


class TestRemoveEntry:
    def test_204_on_success(self) -> None:
        eid = client.post(_BASE, json=_payload()).json()["entry_id"]
        assert client.delete(f"{_BASE}/{eid}").status_code == 204

    def test_entry_gone_from_list_after_remove(self) -> None:
        eid = client.post(_BASE, json=_payload()).json()["entry_id"]
        client.delete(f"{_BASE}/{eid}")
        assert client.get(f"{_BASE}/{eid}").status_code == 404

    def test_404_when_not_found(self) -> None:
        assert client.delete(f"{_BASE}/phantom-id").status_code == 404

    def test_409_when_entry_is_running(self) -> None:
        eid = client.post(_BASE, json=_payload()).json()["entry_id"]
        queue_module.get_queue().get(eid).status = QueueEntryStatus.RUNNING  # type: ignore[union-attr]
        assert client.delete(f"{_BASE}/{eid}").status_code == 409

    def test_409_detail_includes_current_status(self) -> None:
        eid = client.post(_BASE, json=_payload()).json()["entry_id"]
        queue_module.get_queue().get(eid).status = QueueEntryStatus.DONE  # type: ignore[union-attr]
        detail = client.delete(f"{_BASE}/{eid}").json()["detail"]
        assert "DONE" in detail


# ── POST /api/queue/clear ─────────────────────────────────────────────────────


class TestClearCompleted:
    def test_cleared_count_returned(self) -> None:
        for _ in range(2):
            client.post(_BASE, json=_payload())
        for e in queue_module.get_queue().all():
            e.status = QueueEntryStatus.DONE
        assert client.post(_CLEAR).json()["cleared"] == 2

    def test_pending_entries_survive_clear(self) -> None:
        client.post(_BASE, json=_payload(target_name="Keep"))   # PENDING
        eid2 = client.post(_BASE, json=_payload(target_name="Remove")).json()["entry_id"]
        queue_module.get_queue().get(eid2).status = QueueEntryStatus.DONE  # type: ignore[union-attr]
        client.post(_CLEAR)
        remaining = client.get(_BASE).json()
        assert len(remaining) == 1
        assert remaining[0]["target_name"] == "Keep"

    def test_zero_cleared_when_nothing_to_clear(self) -> None:
        client.post(_BASE, json=_payload())   # PENDING stays
        assert client.post(_CLEAR).json()["cleared"] == 0
