"""Unit tests for mount_operations — R6-001."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.ports.mount import MountPort, MountState
from smart_telescope.services.hardware_coordinator import (
    CommandConflictError,
    HardwareCommandCoordinator,
)
from smart_telescope.services.device_state import DeviceStateService, MountObservedState
from smart_telescope.services.mount_operations import (
    MountSlewingError,
    safe_goto,
    unpark_sequence,
    track_sequence,
    park_sequence,
    home_sequence,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_mount(
    state: MountState = MountState.TRACKING,
    slewing: bool = False,
    unpark_ok: bool = True,
    track_ok: bool = True,
    park_ok: bool = True,
    goto_ok: bool = True,
) -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.get_state.return_value = state
    m.is_slewing.return_value = slewing
    m.unpark.return_value = unpark_ok
    m.enable_tracking.return_value = track_ok
    m.park.return_value = park_ok
    if goto_ok:
        m.goto.return_value = True
    else:
        m.goto.side_effect = RuntimeError("GoTo rejected")
    return m


def _coordinator() -> HardwareCommandCoordinator:
    return HardwareCommandCoordinator()


def _device_state(observed_state: MountState | None = None) -> DeviceStateService:
    svc = DeviceStateService()
    if observed_state is not None:
        with svc._lock:
            svc._mount_state = MountObservedState(
                state=observed_state, ra=None, dec=None, polled_at=time.monotonic(),
            )
    return svc


# ── safe_goto ─────────────────────────────────────────────────────────────────

def test_safe_goto_calls_mount_goto():
    m = _mock_mount()
    c = _coordinator()
    safe_goto(m, c, ra=5.0, dec=45.0)
    m.goto.assert_called_once_with(5.0, 45.0)


def test_safe_goto_raises_slewing_error_when_slewing():
    m = _mock_mount(slewing=True)
    c = _coordinator()
    with pytest.raises(MountSlewingError):
        safe_goto(m, c, ra=5.0, dec=45.0)


def test_safe_goto_raises_runtime_on_goto_failure():
    m = _mock_mount(goto_ok=False)
    c = _coordinator()
    with pytest.raises(RuntimeError):
        safe_goto(m, c, ra=5.0, dec=45.0)


def test_safe_goto_raises_conflict_when_coordinator_busy():
    m = _mock_mount()
    c = _coordinator()
    with c.mount_command():
        with pytest.raises(CommandConflictError):
            safe_goto(m, c, ra=5.0, dec=45.0)


# ── unpark_sequence ───────────────────────────────────────────────────────────

def test_unpark_sequence_calls_unpark():
    m = _mock_mount(state=MountState.PARKED, unpark_ok=True)
    ds = _device_state(MountState.TRACKING)
    unpark_sequence(m, ds)
    m.unpark.assert_called_once()


def test_unpark_sequence_always_returns_true():
    m = _mock_mount()
    ds = _device_state(MountState.TRACKING)
    result = unpark_sequence(m, ds)
    assert result is True


def test_unpark_sequence_returns_true_even_when_rejected():
    # If OnStep rejects :hR# (e.g. no alignment), unpark_sequence still returns True.
    m = _mock_mount()
    m.unpark.return_value = False
    ds = _device_state(MountState.PARKED)
    result = unpark_sequence(m, ds)
    assert result is True


# ── track_sequence ────────────────────────────────────────────────────────────

def test_track_sequence_enables_tracking():
    m = _mock_mount(state=MountState.TRACKING)
    track_sequence(m)
    m.enable_tracking.assert_called_once()


def test_track_sequence_auto_unparks_when_parked():
    m = _mock_mount(state=MountState.PARKED, unpark_ok=True)
    track_sequence(m)
    m.unpark.assert_called_once()


def test_track_sequence_raises_on_unpark_failure():
    m = _mock_mount(state=MountState.PARKED, unpark_ok=False)
    with pytest.raises(RuntimeError, match="Auto-unpark"):
        track_sequence(m)


def test_track_sequence_raises_on_track_failure():
    m = _mock_mount(state=MountState.TRACKING, track_ok=False)
    with pytest.raises(RuntimeError, match="Enable tracking"):
        track_sequence(m)


# ── park_sequence ─────────────────────────────────────────────────────────────

def test_park_sequence_calls_park():
    m = _mock_mount(park_ok=True)
    c = _coordinator()
    ds = _device_state(MountState.PARKED)   # non-UNPARKED → poll_until_changed exits fast
    park_sequence(m, c, ds)
    m.park.assert_called_once()


def test_park_sequence_skips_park_when_already_parked():
    m = _mock_mount(state=MountState.PARKED, park_ok=True)
    c = _coordinator()
    ds = _device_state()
    park_sequence(m, c, ds)
    m.park.assert_not_called()


def test_park_sequence_polls_against_actual_pre_state_not_hardcoded_unparked():
    """Regression test for a real-hardware bug: park_sequence() used to
    always compare against a hardcoded MountState.UNPARKED regardless of the
    mount's actual pre-park state, so parking from AT_HOME (the guided-flow
    "Home the mount" -> "Stop safely" path) always looked like it "started"
    immediately even though the mount never moved at all -- confirmed via a
    real-hardware server log where :hP# was accepted (reply='1') but state
    stayed AT_HOME throughout. See wiki/log.md 2026-07-08 M9-026."""
    m = _mock_mount(state=MountState.AT_HOME, park_ok=True)
    c = _coordinator()
    ds = _device_state()
    with patch.object(ds, "poll_until_changed", return_value=True) as mock_poll:
        park_sequence(m, c, ds)
    mock_poll.assert_called_once_with(MountState.AT_HOME, timeout_s=5.0)


def test_park_sequence_does_not_raise_when_stuck_unparked():
    # If OnStep never starts the slew (e.g. no park position), park_sequence
    # warns but does not raise — the JS polls for PARKED for 60 s.
    m = _mock_mount(park_ok=True)
    c = _coordinator()
    ds = _device_state(MountState.UNPARKED)
    with patch.object(ds, "poll_until_changed", return_value=False):
        park_sequence(m, c, ds)   # must not raise


def test_park_sequence_stops_slew_before_parking():
    # If mount is slewing (non-home slew), park_sequence stops it then parks.
    m = _mock_mount(slewing=True, park_ok=True)
    c = _coordinator()
    ds = _device_state()
    with patch("smart_telescope.services.mount_operations.time.sleep"):
        with patch.object(ds, "poll_until_changed", return_value=True):
            park_sequence(m, c, ds)
    m.stop.assert_called_once()
    m.park.assert_called_once()



def test_park_sequence_raises_on_park_failure():
    m = _mock_mount(park_ok=False)
    c = _coordinator()
    ds = _device_state()
    with pytest.raises(RuntimeError, match=r"hP# rejected by OnStep"):
        park_sequence(m, c, ds)


def test_park_sequence_raises_conflict_when_busy():
    m = _mock_mount()
    c = _coordinator()
    ds = _device_state()
    with c.mount_command():
        with pytest.raises(CommandConflictError):
            park_sequence(m, c, ds)


# ── home_sequence ─────────────────────────────────────────────────────────────

def test_home_sequence_issues_go_home():
    m = _mock_mount()
    c = _coordinator()
    home_sequence(m, c)
    m.go_home.assert_called_once()


def test_home_sequence_does_not_goto():
    m = _mock_mount()
    c = _coordinator()
    home_sequence(m, c)
    m.goto.assert_not_called()


def test_home_sequence_auto_unparks_when_parked():
    m = _mock_mount(state=MountState.PARKED, unpark_ok=True)
    # get_state() call sequence: PARKED (auto-unpark), PARKED (tracking check),
    # then AT_HOME on first poll iteration so the loop exits immediately.
    m.get_state.side_effect = [MountState.PARKED, MountState.PARKED, MountState.AT_HOME]
    c = _coordinator()
    with patch("smart_telescope.services.mount_operations.time") as mock_time:
        # monotonic: deadline = 0.0 + 60.0 = 60.0; loop check = 0.5 < 60.0 → True → enter loop
        mock_time.monotonic.side_effect = [0.0, 0.5]
        home_sequence(m, c)
    m.unpark.assert_called_once()


def test_home_sequence_disables_tracking_immediately_after_unpark():
    """Some OnStep firmware auto-starts sidereal tracking on :hR# (unpark),
    but the very next GU# query might not yet reflect it. disable_tracking()
    must be called unconditionally right after a successful unpark, not
    gated behind a get_state() check that could race with the firmware and
    leave the mount tracking (moving) unexpectedly."""
    m = _mock_mount(state=MountState.PARKED, unpark_ok=True)
    # Deliberately UNPARKED (not TRACKING) on the tracking-check query, to
    # prove disable_tracking() already ran from the unconditional call above
    # it, not from this check.
    m.get_state.side_effect = [MountState.PARKED, MountState.UNPARKED, MountState.AT_HOME]
    c = _coordinator()
    with patch("smart_telescope.services.mount_operations.time") as mock_time:
        mock_time.monotonic.side_effect = [0.0, 0.5]
        home_sequence(m, c)
    m.disable_tracking.assert_called_once()


def test_home_sequence_raises_on_unpark_failure():
    m = _mock_mount(state=MountState.PARKED, unpark_ok=False)
    c = _coordinator()
    with pytest.raises(RuntimeError, match="Auto-unpark"):
        home_sequence(m, c)


def test_home_sequence_raises_slewing_error():
    m = _mock_mount(slewing=True)
    c = _coordinator()
    with pytest.raises(MountSlewingError):
        home_sequence(m, c)


def test_home_sequence_disables_tracking_before_go_home():
    m = _mock_mount(state=MountState.TRACKING)
    c = _coordinator()
    call_order: list[str] = []
    m.disable_tracking.side_effect = lambda: call_order.append("disable_tracking") or True
    m.go_home.side_effect = lambda: call_order.append("go_home")
    home_sequence(m, c)
    assert call_order == ["disable_tracking", "go_home"]


def test_home_sequence_skips_disable_tracking_when_unparked():
    m = _mock_mount(state=MountState.UNPARKED)
    c = _coordinator()
    home_sequence(m, c)
    m.disable_tracking.assert_not_called()
    m.go_home.assert_called_once()


def test_home_sequence_returns_true_when_at_home_confirmed():
    m = _mock_mount(state=MountState.UNPARKED)
    m.get_state.return_value = MountState.AT_HOME
    c = _coordinator()
    assert home_sequence(m, c) is True


def test_home_sequence_returns_false_when_at_home_flag_already_cleared():
    """Real OnStep hardware: AT_HOME is a brief flag that can clear before a
    caller re-checks get_state() a second time — home_sequence() itself must
    report False in that case rather than let a caller be fooled by a later,
    separate get_state() call (see observing_service.py's _run_home)."""
    m = _mock_mount(state=MountState.UNPARKED)
    m.get_state.return_value = MountState.TRACKING  # AT_HOME already cleared
    c = _coordinator()
    assert home_sequence(m, c) is False
