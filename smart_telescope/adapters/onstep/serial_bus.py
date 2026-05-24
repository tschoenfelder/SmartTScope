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

    Protocol note — two distinct read strategies:
      send()      → write cmd, read until '#' terminator.  Used for all GET
                    commands (":GU#", ":GR#", ":GD#", etc.) whose responses
                    are '#'-terminated.  Returns the stripped string value.
      raw_send()  → write cmd, read at most one byte.  Used for SET/action
                    commands that return a single ACK ('1'/'0') or nothing.
                    Returns raw bytes so callers can check len > 0.

    Emergency-stop callers use write_bypass() to write without acquiring the
    lock so they can interrupt an in-progress command.
    """

    def __init__(self) -> None:
        self._serial: serial.Serial | None = None
        self._lock = threading.Lock()

    def send(self, cmd: str) -> str:
        """Send *cmd* and return the decoded reply stripped of '#' and whitespace.

        Reads until the '#' terminator so the call returns as soon as OnStep
        finishes its reply — no timeout wait for a newline that never arrives.
        """
        if self._serial is None:
            return ""
        with self._lock:
            try:
                self._serial.write(cmd.encode())
                raw = bytes(self._serial.read_until(b"#"))
                return raw.decode(errors="replace").rstrip("#\r\n")
            except Exception:
                self._serial = None
                raise

    def raw_send(self, cmd: str) -> bytes:
        """Send *cmd* and return the raw reply bytes (up to the next newline).

        Used for action/SET commands that return a single ACK byte ('1'/'0')
        or nothing at all.  Reads exactly one byte so the call returns as soon
        as the ACK arrives (or after the serial timeout if there is none).
        """
        if self._serial is None:
            return b""
        with self._lock:
            try:
                self._serial.write(cmd.encode())
                return bytes(self._serial.read(1))
            except Exception:
                self._serial = None
                raise

    def write_bypass(self, data: bytes) -> None:
        """Write *data* without acquiring the lock.

        Intended only for emergency-stop commands (:Q#, :FQ#) that must be
        delivered immediately even when another command is in progress.
        """
        s = self._serial
        if s is not None:
            with contextlib.suppress(Exception):
                s.write(data)
