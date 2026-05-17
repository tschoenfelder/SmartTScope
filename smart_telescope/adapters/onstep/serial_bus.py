"""OnStep serial bus — thread-safe serial I/O shared by mount and focuser."""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import serial

_log = logging.getLogger(__name__)


class OnStepSerialBus:
    """Thread-safe wrapper around the single serial connection used by OnStep.

    OnStep uses one serial port for all commands — both mount and focuser.
    This class owns the connection and serialises all I/O behind a lock so
    that the focuser never needs to reach into the mount's private members.

    Emergency-stop callers use write_bypass() to write without acquiring the
    lock so they can interrupt an in-progress command.
    """

    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    def raw_send(self, cmd: str) -> bytes:
        """Send *cmd* and return the raw reply bytes (up to the next newline)."""
        if self._serial is None:
            return b""
        with self._lock:
            try:
                self._serial.write(cmd.encode())
                return bytes(self._serial.readline())
            except Exception:
                self._serial = None
                raise

    def send(self, cmd: str) -> str:
        """Send *cmd* and return the decoded, stripped reply string."""
        return self.raw_send(cmd).decode(errors="replace").rstrip("#\r\n")

    def write_bypass(self, data: bytes) -> None:
        """Write *data* without acquiring the lock.

        Intended only for emergency-stop commands (:Q#, :FQ#) that must be
        delivered immediately even when another command is in progress.
        """
        s = self._serial
        if s is not None:
            with contextlib.suppress(Exception):
                s.write(data)
