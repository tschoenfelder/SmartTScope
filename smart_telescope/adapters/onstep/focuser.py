"""OnStep V4 focuser adapter — delegates serial I/O to OnStepSerialBus.

The OnStep controller uses a single serial port for both mount and focuser
commands.  OnStepFocuser holds no serial handle of its own; it calls methods
on OnStepSerialBus so that all traffic shares the mount's lock.
"""

from __future__ import annotations

import logging
import time

from ...ports.focuser import FocuserPort
from .serial_bus import OnStepSerialBus

_log = logging.getLogger(__name__)

_MAX_FA_ATTEMPTS = 3
_FA_RETRY_DELAY_S = 0.3


class OnStepFocuser(FocuserPort):
    """Controls the OnStep focuser via the shared serial bus.

    Args:
        bus: OnStepSerialBus instance obtained from OnStepMount.serial_bus.
    """

    def __init__(self, bus: OnStepSerialBus) -> None:
        self._bus = bus
        self._available: bool = False
        self._max_position: int = 0

    # ── FocuserPort ───────────────────────────────────────────────────────────

    def connect(self) -> bool:
        if self._available:
            return True  # already confirmed; skip serial round-trips
        for attempt in range(_MAX_FA_ATTEMPTS):
            if attempt:
                time.sleep(_FA_RETRY_DELAY_S)
            reply = self._bus.send(":FA#")
            self._available = reply == "1"
            _log.info(
                "OnStepFocuser.connect(): attempt=%d :FA# reply=%r available=%s",
                attempt + 1, reply, self._available,
            )
            if self._available:
                break
        if self._available:
            self._max_position = self._fetch_max_position()
            _log.info("OnStepFocuser.connect(): max_position=%d", self._max_position)
        else:
            _log.warning(
                "OnStepFocuser.connect(): focuser not available after %d attempts"
                " — check OnStep focuser wiring/config",
                _MAX_FA_ATTEMPTS,
            )
        return self._available

    def disconnect(self) -> None:
        pass  # serial owned by OnStepSerialBus

    @property
    def is_available(self) -> bool:
        return self._available

    def get_position(self) -> int:
        reply = self._bus.send(":FG#")
        try:
            return int(reply)
        except ValueError:
            return 0

    def get_max_position(self) -> int:
        return self._max_position

    def move(self, steps: int) -> None:
        _log.info("OnStepFocuser.move(): steps=%d", steps)
        self._bus.raw_send(f":FS{steps}#")

    def is_moving(self) -> bool:
        return self._bus.send(":FT#") == "M"

    def stop(self) -> None:
        # Bypass the serial lock — stop must be immediate even when another
        # command is in progress.  Write-only: no response expected from :FQ#.
        self._bus.write_bypass(b":FQ#")

    # ── private ───────────────────────────────────────────────────────────────

    def _fetch_max_position(self) -> int:
        reply = self._bus.send(":FM#")
        try:
            return int(reply)
        except ValueError:
            return 0
