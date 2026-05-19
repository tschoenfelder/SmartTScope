"""HardwareCommandCoordinator — single control point for all motion commands.

All normal mount and focuser motion commands must pass through this
coordinator's context managers so that:

  - Only one mount command is in progress at a time.
  - Only one focuser command is in progress at a time.
  - The lock owner is always released even if the command thread dies.

STOP is explicitly NOT serialized here — emergency stop must call
mount.stop() / focuser.stop() directly and must never wait for a lock.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections.abc import Iterator

_log = logging.getLogger(__name__)

_MOUNT_LOCK_TIMEOUT   = 5.0   # seconds — goto, park, home, goto_and_center
_FOCUSER_LOCK_TIMEOUT = 3.0   # seconds — move, nudge (> serial read timeout)


class CommandConflictError(Exception):
    """Raised when the lock for a resource is held by another command."""


class HardwareCommandCoordinator:
    """Thread-safe command serializer for mount and focuser.

    Usage in API modules::

        coordinator = deps.get_coordinator()
        try:
            with coordinator.mount_command():
                mount.goto(ra, dec)
        except CommandConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    """

    def __init__(self) -> None:
        self._mount_lock   = threading.Lock()
        self._focuser_lock = threading.Lock()

    @contextlib.contextmanager
    def mount_command(self, *, timeout: float = _MOUNT_LOCK_TIMEOUT) -> Iterator[None]:
        """Acquire the mount serialization lock for the duration of one command.

        Raises CommandConflictError immediately if the lock cannot be acquired
        within *timeout* seconds.  The lock is always released on exit.

        STOP must never call this — it bypasses all locks.
        """
        if not self._mount_lock.acquire(blocking=True, timeout=timeout):
            raise CommandConflictError(
                "Another mount command is already in progress — try again shortly"
            )
        try:
            yield
        finally:
            self._mount_lock.release()

    @contextlib.contextmanager
    def focuser_command(self, *, timeout: float = _FOCUSER_LOCK_TIMEOUT) -> Iterator[None]:
        """Acquire the focuser serialization lock for the duration of one command.

        Raises CommandConflictError immediately if the lock cannot be acquired
        within *timeout* seconds.  The lock is always released on exit.
        """
        if not self._focuser_lock.acquire(blocking=True, timeout=timeout):
            raise CommandConflictError(
                "Another focuser command is already in progress — try again shortly"
            )
        try:
            yield
        finally:
            self._focuser_lock.release()
