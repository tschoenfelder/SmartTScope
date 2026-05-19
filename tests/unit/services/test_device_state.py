"""Tests for DeviceStateService — R2-003, R2-005, R2-008."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.ports.mount import MountPosition, MountState
from smart_telescope.services.device_state import (
    DeviceStateService,
    MountObservedState,
    _STALE_THRESHOLD_S,
    _WATCHDOG_SLEW_S,
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


# ── R2-003: command tracking ──────────────────────────────────────────────────

def test_initial_last_command_is_none():
    svc = DeviceStateService()
    cmd, at, err = svc.get_last_command()
    assert cmd is None
    assert at is None
    assert err is None


def test_record_command_stores_name_and_clears_error():
    svc = DeviceStateService()
    svc.record_command_error("previous error")
    svc.record_command("park")
    cmd, at, err = svc.get_last_command()
    assert cmd == "park"
    assert at is not None
    assert err is None


def test_record_command_error_stores_error():
    svc = DeviceStateService()
    svc.record_command("unpark")
    svc.record_command_error("Unpark rejected by OnStep")
    cmd, at, err = svc.get_last_command()
    assert cmd == "unpark"       # command name is kept
    assert "rejected" in err


def test_successive_commands_overwrite_previous():
    svc = DeviceStateService()
    svc.record_command("park")
    svc.record_command("goto ra=5.0h dec=45.0°")
    cmd, _, _ = svc.get_last_command()
    assert cmd == "goto ra=5.0h dec=45.0°"


# ── R1-006: command IDs ───────────────────────────────────────────────────────

def test_record_command_returns_string_id():
    svc = DeviceStateService()
    cmd_id = svc.record_command("park")
    assert isinstance(cmd_id, str)
    assert len(cmd_id) > 0


def test_command_ids_are_unique_per_call():
    svc = DeviceStateService()
    id1 = svc.record_command("unpark")
    id2 = svc.record_command("park")
    assert id1 != id2


def test_command_ids_are_sequential():
    svc = DeviceStateService()
    id1 = svc.record_command("unpark")
    id2 = svc.record_command("track")
    id3 = svc.record_command("park")
    # IDs have the form "cmd-NNNN"; extract numbers and verify strictly increasing
    nums = [int(x.split("-")[1]) for x in (id1, id2, id3)]
    assert nums[0] < nums[1] < nums[2]


def test_get_last_command_id_matches_returned_id():
    svc = DeviceStateService()
    returned_id = svc.record_command("goto ra=6.0h dec=45.0°")
    stored_id   = svc.get_last_command_id()
    assert stored_id == returned_id


def test_initial_command_id_is_none():
    svc = DeviceStateService()
    assert svc.get_last_command_id() is None


def test_command_id_logged(caplog):
    import logging
    svc = DeviceStateService()
    with caplog.at_level(logging.INFO, logger="smart_telescope.services.device_state"):
        cmd_id = svc.record_command("park")
    assert cmd_id in caplog.text
    assert "park" in caplog.text


def test_command_error_logged_with_id(caplog):
    import logging
    svc = DeviceStateService()
    with caplog.at_level(logging.WARNING, logger="smart_telescope.services.device_state"):
        cmd_id = svc.record_command("park")
        svc.record_command_error("Park rejected")
    assert cmd_id in caplog.text
    assert "Park rejected" in caplog.text


# ── R2-005: state convergence helpers ─────────────────────────────────────────

def _svc_with_state(state: MountState) -> DeviceStateService:
    """Return a DeviceStateService whose cached state is pre-loaded (no background thread)."""
    svc = DeviceStateService()
    with svc._lock:
        svc._mount_state = MountObservedState(
            state=state, ra=None, dec=None, polled_at=time.monotonic()
        )
    return svc


def test_wait_for_mount_state_immediate_match():
    svc = _svc_with_state(MountState.PARKED)
    converged = svc.wait_for_mount_state(MountState.PARKED, timeout_s=0.1)
    assert converged is True


def test_wait_for_mount_state_timeout():
    svc = _svc_with_state(MountState.TRACKING)
    converged = svc.wait_for_mount_state(MountState.PARKED, timeout_s=0.1)
    assert converged is False


def test_wait_for_mount_state_detects_transition():
    svc = DeviceStateService()
    import threading

    def _transition():
        time.sleep(0.1)
        with svc._lock:
            svc._mount_state = MountObservedState(
                state=MountState.PARKED, ra=None, dec=None, polled_at=time.monotonic()
            )

    threading.Thread(target=_transition, daemon=True).start()
    converged = svc.wait_for_mount_state(MountState.PARKED, timeout_s=1.0)
    assert converged is True


def test_wait_while_mount_state_immediate_change():
    svc = _svc_with_state(MountState.TRACKING)   # not PARKED → changed immediately
    changed = svc.wait_while_mount_state(MountState.PARKED, timeout_s=0.1)
    assert changed is True


def test_wait_while_mount_state_timeout():
    svc = _svc_with_state(MountState.PARKED)
    changed = svc.wait_while_mount_state(MountState.PARKED, timeout_s=0.1)
    assert changed is False


def test_wait_while_mount_state_detects_transition():
    svc = _svc_with_state(MountState.PARKED)
    import threading

    def _transition():
        time.sleep(0.1)
        with svc._lock:
            svc._mount_state = MountObservedState(
                state=MountState.TRACKING, ra=None, dec=None, polled_at=time.monotonic()
            )

    threading.Thread(target=_transition, daemon=True).start()
    changed = svc.wait_while_mount_state(MountState.PARKED, timeout_s=1.0)
    assert changed is True


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


# ── M1-004: hardware watchdog ─────────────────────────────────────────────────

def test_watchdog_no_warning_when_slewing_below_threshold():
    svc = DeviceStateService()
    mount = _mock_mount(state=MountState.SLEWING)
    # command issued 5 s ago — well below the 120 s threshold
    with svc._lock:
        svc._last_command    = "goto"
        svc._last_command_at = time.monotonic() - 5.0
    svc._poll_once(mount)
    assert svc.get_watchdog_warning() is None


def test_watchdog_fires_when_slewing_too_long():
    svc = DeviceStateService()
    mount = _mock_mount(state=MountState.SLEWING)
    # command issued well beyond the threshold
    with svc._lock:
        svc._last_command    = "goto"
        svc._last_command_at = time.monotonic() - (_WATCHDOG_SLEW_S + 10.0)
    svc._poll_once(mount)
    warn = svc.get_watchdog_warning()
    assert warn is not None
    assert "SLEWING" in warn or "slewing" in warn.lower()


def test_watchdog_clears_when_state_leaves_slewing():
    svc = DeviceStateService()
    # Trigger watchdog with SLEWING
    mount_slewing  = _mock_mount(state=MountState.SLEWING)
    with svc._lock:
        svc._last_command    = "goto"
        svc._last_command_at = time.monotonic() - (_WATCHDOG_SLEW_S + 10.0)
    svc._poll_once(mount_slewing)
    assert svc.get_watchdog_warning() is not None
    # Now state transitions to TRACKING
    mount_tracking = _mock_mount(state=MountState.TRACKING)
    svc._poll_once(mount_tracking)
    assert svc.get_watchdog_warning() is None


def test_watchdog_cleared_on_new_command():
    svc = DeviceStateService()
    mount = _mock_mount(state=MountState.SLEWING)
    # Trigger watchdog
    with svc._lock:
        svc._last_command    = "goto"
        svc._last_command_at = time.monotonic() - (_WATCHDOG_SLEW_S + 10.0)
    svc._poll_once(mount)
    assert svc.get_watchdog_warning() is not None
    # New command resets the watchdog
    svc.record_command("stop")
    assert svc.get_watchdog_warning() is None


# ── BUG-011/012/016: poll_now() ───────────────────────────────────────────────

class TestPollNow:
    """poll_now() refreshes the cache on demand without waiting for the 2 s background interval."""

    def test_poll_now_updates_cache_immediately(self) -> None:
        svc = DeviceStateService()
        mount = _mock_mount(state=MountState.PARKED)
        svc.start(mount, poll_interval=60.0)  # long interval so background never fires
        try:
            # Cache starts empty or with background-poll value; force an immediate update
            svc._mount_state = None
            svc.poll_now()
            obs = svc.get_mount_state()
            assert obs is not None
            assert obs.state == MountState.PARKED
        finally:
            svc.stop()

    def test_poll_now_reflects_state_change_after_command(self) -> None:
        svc = DeviceStateService()
        mount = _mock_mount(state=MountState.PARKED)
        svc.start(mount, poll_interval=60.0)
        try:
            svc.poll_now()
            assert svc.get_mount_state().state == MountState.PARKED  # type: ignore[union-attr]

            # Simulate mount leaving parked state
            mount.get_state.return_value = MountState.TRACKING
            svc.poll_now()
            assert svc.get_mount_state().state == MountState.TRACKING  # type: ignore[union-attr]
        finally:
            svc.stop()

    def test_poll_now_handles_mount_exception_gracefully(self) -> None:
        svc = DeviceStateService()
        mount = MagicMock()
        mount.get_state.side_effect = RuntimeError("serial timeout")
        svc.start(mount, poll_interval=60.0)
        try:
            svc.poll_now()  # must not raise
            obs = svc.get_mount_state()
            assert obs is not None
            assert obs.state == MountState.UNKNOWN
            assert obs.error is not None
        finally:
            svc.stop()

    def test_poll_now_is_noop_before_start(self) -> None:
        svc = DeviceStateService()
        svc.poll_now()  # must not raise; mount is None
        assert svc.get_mount_state() is None

    def test_poll_now_is_noop_after_stop(self) -> None:
        svc = DeviceStateService()
        mount = _mock_mount(state=MountState.TRACKING)
        svc.start(mount, poll_interval=60.0)
        svc.stop()
        calls_before = mount.get_state.call_count
        svc.poll_now()  # must not raise; _mount cleared by stop()
        assert mount.get_state.call_count == calls_before, \
            "poll_now() must not call get_state after stop()"
