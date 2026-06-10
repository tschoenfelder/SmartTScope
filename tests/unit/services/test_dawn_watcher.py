"""Tests for DawnWatcher — M5-013 dawn auto-park."""

from __future__ import annotations

import time
from itertools import chain, repeat
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.services.dawn_watcher import (
    ASTRONOMICAL_DAWN_ALT_DEG,
    DawnStatus,
    DawnWatcher,
    _POLL_INTERVAL_S,
)


# ── helpers ────────────────────────────────────────────────────────────────────

_FAST_INTERVAL = 0.05  # seconds — speeds up background-thread tests


def _mock_mount() -> MagicMock:
    m = MagicMock()
    m.park.return_value = None
    return m


def _mock_device_state() -> MagicMock:
    ds = MagicMock()
    ds.poll_now.return_value = None
    return ds


def _wait_for_status(watcher: DawnWatcher, max_wait: float = 2.0) -> DawnStatus | None:
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        s = watcher.get_status()
        if s is not None:
            return s
        time.sleep(0.02)
    return None


# ── DawnStatus dataclass ───────────────────────────────────────────────────────

class TestDawnStatus:
    def test_frozen(self) -> None:
        s = DawnStatus(sun_altitude_deg=-20.0, is_dawn=False, parked_at_dawn=False, parked_at=None)
        with pytest.raises(Exception):
            s.sun_altitude_deg = 0.0  # type: ignore[misc]

    def test_is_dawn_true_at_threshold(self) -> None:
        s = DawnStatus(sun_altitude_deg=-18.0, is_dawn=True, parked_at_dawn=False, parked_at=None)
        assert s.is_dawn is True

    def test_is_dawn_false_below_threshold(self) -> None:
        s = DawnStatus(sun_altitude_deg=-19.0, is_dawn=False, parked_at_dawn=False, parked_at=None)
        assert s.is_dawn is False


# ── DawnWatcher lifecycle ──────────────────────────────────────────────────────

class TestDawnWatcherLifecycle:
    def test_status_none_before_start(self) -> None:
        watcher = DawnWatcher()
        assert watcher.get_status() is None

    def test_stop_before_start_is_noop(self) -> None:
        watcher = DawnWatcher()
        watcher.stop()  # must not raise

    def test_stop_terminates_thread(self) -> None:
        mount = _mock_mount()
        ds = _mock_device_state()
        watcher = DawnWatcher()
        with patch(
            "smart_telescope.services.dawn_watcher.sun_altitude_now",
            return_value=-30.0,
        ):
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            _wait_for_status(watcher)
            watcher.stop()
        assert watcher._thread is None

    def test_start_is_idempotent(self) -> None:
        mount = _mock_mount()
        ds = _mock_device_state()
        watcher = DawnWatcher()
        with patch(
            "smart_telescope.services.dawn_watcher.sun_altitude_now",
            return_value=-30.0,
        ):
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            thread_id = id(watcher._thread)
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            assert id(watcher._thread) == thread_id
            watcher.stop()


# ── polling behaviour ──────────────────────────────────────────────────────────

class TestDawnWatcherPolling:
    def test_status_reflects_sun_altitude(self) -> None:
        mount = _mock_mount()
        ds = _mock_device_state()
        watcher = DawnWatcher()
        with patch(
            "smart_telescope.services.dawn_watcher.sun_altitude_now",
            return_value=-25.0,
        ):
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            status = _wait_for_status(watcher)
            watcher.stop()

        assert status is not None
        assert status.sun_altitude_deg == pytest.approx(-25.0)
        assert status.is_dawn is False
        assert status.parked_at_dawn is False

    def test_park_triggered_at_dawn(self) -> None:
        mount = _mock_mount()
        ds = _mock_device_state()
        watcher = DawnWatcher()
        # First poll returns a night altitude so _night_seen is set; subsequent polls hit dawn.
        altitudes = chain([-30.0], repeat(ASTRONOMICAL_DAWN_ALT_DEG))
        with patch(
            "smart_telescope.services.dawn_watcher.sun_altitude_now",
            side_effect=altitudes,
        ):
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            # wait until parked_at_dawn is set
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                s = watcher.get_status()
                if s is not None and s.parked_at_dawn:
                    break
                time.sleep(0.02)
            watcher.stop()

        mount.park.assert_called_once()
        ds.poll_now.assert_called_once()
        s = watcher.get_status()
        assert s is not None
        assert s.parked_at_dawn is True
        assert s.parked_at is not None

    def test_no_repark_after_dawn(self) -> None:
        """Park must be issued at most once even if the watcher fires many times."""
        mount = _mock_mount()
        ds = _mock_device_state()
        watcher = DawnWatcher()
        # Simulate night crossing then persistent above-threshold altitude.
        altitudes = chain([-30.0], repeat(-17.0))
        with patch(
            "smart_telescope.services.dawn_watcher.sun_altitude_now",
            side_effect=altitudes,
        ):
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            # let it fire several times
            time.sleep(_FAST_INTERVAL * 5)
            watcher.stop()

        assert mount.park.call_count == 1

    def test_no_park_during_daytime_start(self) -> None:
        """Watcher started while sun is already above threshold must not park."""
        mount = _mock_mount()
        ds = _mock_device_state()
        watcher = DawnWatcher()
        with patch(
            "smart_telescope.services.dawn_watcher.sun_altitude_now",
            return_value=30.0,  # daytime — never dips below threshold
        ):
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            time.sleep(_FAST_INTERVAL * 5)
            watcher.stop()

        mount.park.assert_not_called()

    def test_no_park_when_sun_below_threshold(self) -> None:
        mount = _mock_mount()
        ds = _mock_device_state()
        watcher = DawnWatcher()
        with patch(
            "smart_telescope.services.dawn_watcher.sun_altitude_now",
            return_value=-19.0,  # below -18° → not dawn
        ):
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            _wait_for_status(watcher)
            watcher.stop()

        mount.park.assert_not_called()

    def test_sun_altitude_error_does_not_crash(self) -> None:
        mount = _mock_mount()
        ds = _mock_device_state()
        watcher = DawnWatcher()
        with patch(
            "smart_telescope.services.dawn_watcher.sun_altitude_now",
            side_effect=RuntimeError("astropy failure"),
        ):
            watcher.start(mount, ds, 50.0, 8.0, poll_interval=_FAST_INTERVAL)
            time.sleep(_FAST_INTERVAL * 3)
            watcher.stop()
        # status stays None when every poll errors
        assert watcher.get_status() is None
        mount.park.assert_not_called()
