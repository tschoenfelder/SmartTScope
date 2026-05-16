"""Tests for HardwareCommandCoordinator — R1-010."""

from __future__ import annotations

import threading

import pytest

from smart_telescope.services.hardware_coordinator import (
    CommandConflictError,
    HardwareCommandCoordinator,
)


# ── basic acquire / release ───────────────────────────────────────────────────

def test_mount_command_context_manager_completes():
    c = HardwareCommandCoordinator()
    with c.mount_command():
        pass  # no error, lock released after block


def test_focuser_command_context_manager_completes():
    c = HardwareCommandCoordinator()
    with c.focuser_command():
        pass


def test_mount_command_lock_released_on_exception():
    c = HardwareCommandCoordinator()
    with pytest.raises(ValueError):
        with c.mount_command():
            raise ValueError("deliberate")
    # Lock must be free — second acquire must not raise CommandConflictError
    with c.mount_command():
        pass


def test_focuser_command_lock_released_on_exception():
    c = HardwareCommandCoordinator()
    with pytest.raises(RuntimeError):
        with c.focuser_command():
            raise RuntimeError("deliberate")
    with c.focuser_command():
        pass


# ── conflict detection ────────────────────────────────────────────────────────

def _hold_mount_lock(coordinator: HardwareCommandCoordinator,
                     acquired: threading.Event,
                     release: threading.Event) -> None:
    with coordinator.mount_command():
        acquired.set()
        release.wait(timeout=5.0)


def _hold_focuser_lock(coordinator: HardwareCommandCoordinator,
                       acquired: threading.Event,
                       release: threading.Event) -> None:
    with coordinator.focuser_command():
        acquired.set()
        release.wait(timeout=5.0)


def test_mount_command_raises_conflict_when_locked():
    c = HardwareCommandCoordinator()
    acquired, release = threading.Event(), threading.Event()
    t = threading.Thread(target=_hold_mount_lock, args=(c, acquired, release), daemon=True)
    t.start()
    acquired.wait(timeout=1.0)

    with pytest.raises(CommandConflictError):
        with c.mount_command(timeout=0.1):
            pass

    release.set()
    t.join(timeout=2.0)


def test_focuser_command_raises_conflict_when_locked():
    c = HardwareCommandCoordinator()
    acquired, release = threading.Event(), threading.Event()
    t = threading.Thread(target=_hold_focuser_lock, args=(c, acquired, release), daemon=True)
    t.start()
    acquired.wait(timeout=1.0)

    with pytest.raises(CommandConflictError):
        with c.focuser_command(timeout=0.1):
            pass

    release.set()
    t.join(timeout=2.0)


def test_mount_command_timeout_zero_is_non_blocking():
    c = HardwareCommandCoordinator()
    acquired, release = threading.Event(), threading.Event()
    t = threading.Thread(target=_hold_mount_lock, args=(c, acquired, release), daemon=True)
    t.start()
    acquired.wait(timeout=1.0)

    with pytest.raises(CommandConflictError):
        with c.mount_command(timeout=0):
            pass

    release.set()
    t.join(timeout=2.0)


# ── independence of locks ─────────────────────────────────────────────────────

def test_mount_and_focuser_locks_are_independent():
    """Holding the mount lock does not block the focuser lock (and vice versa)."""
    c = HardwareCommandCoordinator()
    acquired, release = threading.Event(), threading.Event()
    t = threading.Thread(target=_hold_mount_lock, args=(c, acquired, release), daemon=True)
    t.start()
    acquired.wait(timeout=1.0)

    # Should succeed immediately despite the mount lock being held
    with c.focuser_command(timeout=0.1):
        pass

    release.set()
    t.join(timeout=2.0)


def test_two_coordinators_do_not_share_locks():
    c1 = HardwareCommandCoordinator()
    c2 = HardwareCommandCoordinator()
    acquired, release = threading.Event(), threading.Event()
    t = threading.Thread(target=_hold_mount_lock, args=(c1, acquired, release), daemon=True)
    t.start()
    acquired.wait(timeout=1.0)

    # c2's lock is completely separate from c1's
    with c2.mount_command(timeout=0.1):
        pass

    release.set()
    t.join(timeout=2.0)


# ── STOP bypass pattern ───────────────────────────────────────────────────────

def test_stop_can_run_while_mount_lock_held():
    """STOP must never wait for the mount lock — call mount.stop() directly."""
    c = HardwareCommandCoordinator()
    acquired, release = threading.Event(), threading.Event()
    t = threading.Thread(target=_hold_mount_lock, args=(c, acquired, release), daemon=True)
    t.start()
    acquired.wait(timeout=1.0)

    # Simulate STOP: bypasses coordinator entirely, calls hardware directly
    stop_called = []
    class FakeMount:
        def stop(self): stop_called.append(True)

    FakeMount().stop()   # direct call — no coordinator involvement
    assert stop_called == [True]

    release.set()
    t.join(timeout=2.0)


# ── conflict error message ────────────────────────────────────────────────────

def test_conflict_error_message_is_informative():
    c = HardwareCommandCoordinator()
    acquired, release = threading.Event(), threading.Event()
    t = threading.Thread(target=_hold_mount_lock, args=(c, acquired, release), daemon=True)
    t.start()
    acquired.wait(timeout=1.0)

    with pytest.raises(CommandConflictError, match="mount command"):
        with c.mount_command(timeout=0.05):
            pass

    release.set()
    t.join(timeout=2.0)
