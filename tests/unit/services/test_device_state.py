"""Tests for DeviceStateService — R2-008."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.ports.mount import MountPosition, MountState
from smart_telescope.services.device_state import (
    DeviceStateService,
    MountObservedState,
    _STALE_THRESHOLD_S,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_mount(state: MountState = MountState.TRACKING,
                ra: float = 10.0,
                dec: float = 45.0) -> MagicMock:
    m = MagicMock()
    m.get_state.return_value = state
    m.get_position.return_value = MountPosition(ra=ra, dec=dec)
    return m


def _wait_for_poll(svc: DeviceStateService, max_wait: float = 2.0) -> MountObservedState | None:
    deadline = time.monotonic() + max_wait
    while time.monotonic() < deadline:
        obs = svc.get_mount_state()
        if obs is not None:
            return obs
        time.sleep(0.02)
    return None


# ── MountObservedState ────────────────────────────────────────────────────────

def test_fresh_observed_state_is_not_stale():
    obs = MountObservedState(
        state=MountState.TRACKING,
        ra=10.0,
        dec=45.0,
        polled_at=time.monotonic(),
    )
    assert not obs.is_stale()


def test_old_observed_state_is_stale():
    obs = MountObservedState(
        state=MountState.TRACKING,
        ra=10.0,
        dec=45.0,
        polled_at=time.monotonic() - (_STALE_THRESHOLD_S + 1),
    )
    assert obs.is_stale()


def test_age_seconds_increases_over_time():
    obs = MountObservedState(
        state=MountState.TRACKING,
        ra=0.0,
        dec=0.0,
        polled_at=time.monotonic() - 5.0,
    )
    assert obs.age_seconds() >= 5.0


# ── DeviceStateService lifecycle ──────────────────────────────────────────────

def test_initial_state_is_none():
    svc = DeviceStateService()
    assert svc.get_mount_state() is None


def test_start_populates_state():
    mount = _mock_mount()
    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.05)
    obs = _wait_for_poll(svc)
    svc.stop()
    assert obs is not None
    assert obs.state == MountState.TRACKING
    assert obs.ra == 10.0
    assert obs.dec == 45.0


def test_start_is_idempotent():
    mount = _mock_mount()
    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.05)
    svc.start(mount, poll_interval=0.05)   # second call is a no-op
    _wait_for_poll(svc)
    svc.stop()
    assert mount.get_state.call_count >= 1


def test_stop_halts_polling():
    mount = _mock_mount()
    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.05)
    _wait_for_poll(svc)
    svc.stop()
    count_after_stop = mount.get_state.call_count
    time.sleep(0.2)
    assert mount.get_state.call_count == count_after_stop


# ── R2-008: command accepted but observed state unchanged ─────────────────────

def test_poll_error_stored_in_state():
    mount = MagicMock()
    mount.get_state.side_effect = RuntimeError("serial timeout")
    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.05)
    obs = _wait_for_poll(svc)
    svc.stop()
    assert obs is not None
    assert obs.state == MountState.UNKNOWN
    assert obs.error is not None
    assert "serial timeout" in obs.error


def test_state_reverts_to_unknown_after_poll_error():
    call_count = {"n": 0}
    def flaky_state():
        call_count["n"] += 1
        if call_count["n"] == 1:
            return MountState.TRACKING
        raise RuntimeError("disconnected")

    mount = MagicMock()
    mount.get_state.side_effect = flaky_state
    mount.get_position.return_value = MountPosition(ra=5.0, dec=30.0)

    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.05)
    # Wait long enough for at least 2 polls
    time.sleep(0.3)
    svc.stop()
    obs = svc.get_mount_state()
    assert obs is not None
    assert obs.state == MountState.UNKNOWN


def test_unknown_state_skips_position_query():
    mount = _mock_mount(state=MountState.UNKNOWN)
    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.05)
    _wait_for_poll(svc)
    svc.stop()
    mount.get_position.assert_not_called()


def test_parked_state_includes_position():
    mount = _mock_mount(state=MountState.PARKED, ra=6.0, dec=20.0)
    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.05)
    obs = _wait_for_poll(svc)
    svc.stop()
    assert obs is not None
    assert obs.state == MountState.PARKED
    assert obs.ra == 6.0


def test_position_error_does_not_crash_poll():
    mount = MagicMock()
    mount.get_state.return_value = MountState.TRACKING
    mount.get_position.side_effect = OSError("serial read failed")
    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.05)
    obs = _wait_for_poll(svc)
    svc.stop()
    assert obs is not None
    assert obs.state == MountState.TRACKING
    assert obs.ra is None
    assert obs.dec is None


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_reads_are_safe():
    import threading
    mount = _mock_mount()
    svc = DeviceStateService()
    svc.start(mount, poll_interval=0.01)

    results = []
    errors = []

    def reader():
        for _ in range(50):
            try:
                results.append(svc.get_mount_state())
            except Exception as exc:
                errors.append(exc)
            time.sleep(0.005)

    threads = [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    svc.stop()

    assert not errors
