"""
FakeOnStepSerial — stateful LX200 serial simulator for integration testing.

Mimics the pyserial Serial interface (write / readline / close / is_open).
Maintains a mount state machine so tests exercise real command sequences
without any hardware or mocker patching.

State transitions:
  parked  → unpark (:hU#)    → unparked
  unparked → track (:Te#)    → tracking
  any      → goto  (:MS#)    → slewing
  slewing  → settle()        → tracking   (helper for tests)
  slewing  → stop  (:Q#)     → tracking
"""

from __future__ import annotations

import contextlib

from smart_telescope.adapters.onstep.mount import (
    _format_dec,
    _format_ra,
    _parse_dec,
    _parse_ra,
)

_GU_RESPONSES: dict[str, bytes] = {
    "parked":   b"P|N|0|0|0|0|0|0|0|0|0|0|0|0|0#",
    "unparked": b"n|N|0|0|0|0|0|0|0|0|0|0|0|0|0#",
    "tracking": b"n|T|0|0|0|0|0|0|0|0|0|0|0|0|0#",
    "slewing":  b"n|S|0|0|0|0|0|0|0|0|0|0|0|0|0#",
    "at_limit": b"n|E|0|0|0|0|0|0|0|0|0|0|0|0|0#",
}


class FakeOnStepSerial:
    """Drop-in replacement for serial.Serial, simulating an OnStep V4 mount."""

    def __init__(
        self,
        initial_state: str = "parked",
        initial_ra: float = 0.0,
        initial_dec: float = 0.0,
    ) -> None:
        self._state = initial_state
        self._ra = initial_ra
        self._dec = initial_dec
        self._target_ra = 0.0
        self._target_dec = 0.0
        self._last_response: bytes = b""
        self.is_open = True
        self.commands_received: list[bytes] = []

    # ── pyserial interface ─────────────────────────────────────────────────────

    def write(self, data: bytes) -> None:
        self.commands_received.append(data)
        cmd = data.decode(errors="replace")
        self._last_response = self._process(cmd)

    def readline(self) -> bytes:
        r = self._last_response
        self._last_response = b""
        return r

    def close(self) -> None:
        self.is_open = False

    # ── test helper ───────────────────────────────────────────────────────────

    def settle(self) -> None:
        """Simulate slew completion — advance position to target and stop slewing."""
        if self._state == "slewing":
            self._ra = self._target_ra
            self._dec = self._target_dec
            self._state = "tracking"

    # ── LX200 command dispatcher ──────────────────────────────────────────────

    def _process(self, cmd: str) -> bytes:
        if cmd == ":GU#":
            return _GU_RESPONSES.get(self._state, b"#")

        if cmd == ":hU#":
            if self._state == "parked":
                self._state = "unparked"
            return b"#"

        if cmd == ":Te#":
            if self._state in ("unparked", "parked", "tracking"):
                self._state = "tracking"
                return b"1"
            return b"0"

        if cmd.startswith(":Sr"):
            ra_str = cmd[3:].rstrip("#")
            with contextlib.suppress(ValueError, IndexError):
                self._target_ra = _parse_ra(ra_str)
            return b"1"

        if cmd.startswith(":Sd"):
            dec_str = cmd[3:].rstrip("#")
            with contextlib.suppress(ValueError, IndexError):
                self._target_dec = _parse_dec(dec_str)
            return b"1"

        if cmd == ":MS#":
            self._state = "slewing"
            return b"0"

        if cmd == ":CM#":
            self._ra = self._target_ra
            self._dec = self._target_dec
            return b"Synchronized#"

        if cmd == ":GR#":
            return (_format_ra(self._ra) + "#").encode()

        if cmd == ":GD#":
            return (_format_dec(self._dec) + "#").encode()

        if cmd == ":D#":
            return b"|#" if self._state == "slewing" else b"#"

        if cmd == ":Q#":
            if self._state == "slewing":
                self._state = "tracking"
            return b""

        return b""
