"""Tests for api/event_log.py — in-memory circular event log."""

import pytest

from smart_telescope.api import event_log


@pytest.fixture(autouse=True)
def _clear() -> None:
    event_log.clear()
    yield  # type: ignore[misc]
    event_log.clear()


def test_log_tx_appends_entry() -> None:
    event_log.log_tx("CMD")
    entries = event_log.get_recent()
    assert len(entries) == 1
    assert entries[0]["dir"] == "tx"
    assert entries[0]["msg"] == "CMD"


def test_log_rx_appends_entry() -> None:
    event_log.log_rx("RESPONSE")
    entries = event_log.get_recent()
    assert len(entries) == 1
    assert entries[0]["dir"] == "rx"
    assert entries[0]["msg"] == "RESPONSE"


def test_log_err_appends_entry() -> None:
    event_log.log_err("OOPS")
    entries = event_log.get_recent()
    assert len(entries) == 1
    assert entries[0]["dir"] == "err"
    assert entries[0]["msg"] == "OOPS"


def test_entries_have_timestamp() -> None:
    event_log.log_tx("TS")
    entry = event_log.get_recent()[0]
    assert "ts" in entry
    assert entry["ts"].endswith("Z")


def test_get_recent_limits_by_n() -> None:
    for i in range(10):
        event_log.log_tx(str(i))
    recent = event_log.get_recent(3)
    assert len(recent) == 3
    assert recent[-1]["msg"] == "9"


def test_clear_removes_all() -> None:
    event_log.log_tx("A")
    event_log.log_rx("B")
    event_log.clear()
    assert event_log.get_recent() == []


def test_mixed_entries_preserve_order() -> None:
    event_log.log_tx("TX")
    event_log.log_rx("RX")
    event_log.log_err("ERR")
    entries = event_log.get_recent()
    assert [e["dir"] for e in entries] == ["tx", "rx", "err"]


def test_get_recent_default_limit_returns_all_when_few() -> None:
    event_log.log_tx("X")
    event_log.log_rx("Y")
    assert len(event_log.get_recent()) == 2
