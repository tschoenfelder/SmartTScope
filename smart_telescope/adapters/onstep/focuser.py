"""OnStep V4 focuser adapter — delegates serial I/O to OnStepMount.

The OnStep controller uses a single serial port for both mount and focuser
commands.  OnStepFocuser holds no serial handle of its own; it calls
OnStepMount._send / _raw_send so that all traffic shares the mount's lock.
"""

from __future__ import annotations

import logging

from ...ports.focuser import FocuserPort
from .mount import OnStepMount

_log = logging.getLogger(__name__)


class OnStepFocuser(FocuserPort):
    """Controls the OnStep focuser via the mount's shared serial connection.

    Args:
        mount: connected OnStepMount whose serial handle and lock are reused.
    """

    def __init__(self, mount: OnStepMount) -> None:
        self._mount = mount
        self._available: bool = False
        self._max_position: int = 0

    # ── FocuserPort ───────────────────────────────────────────────────────────

    def connect(self) -> bool:
        reply = self._mount._send(":FA#")
        self._available = reply == "1"
        _log.info("OnStepFocuser.connect(): :FA# reply=%r available=%s", reply, self._available)
        if self._available:
            self._max_position = self._fetch_max_position()
            _log.info("OnStepFocuser.connect(): max_position=%d", self._max_position)
        else:
            _log.warning("OnStepFocuser.connect(): focuser not available — check OnStep focuser wiring/config")
        return True

    def disconnect(self) -> None:
        pass  # serial owned by OnStepMount

    @property
    def is_available(self) -> bool:
        return self._available

    def get_position(self) -> int:
        reply = self._mount._send(":FG#")
        try:
            return int(reply)
        except ValueError:
            return 0

    def get_max_position(self) -> int:
        return self._max_position

    def move(self, steps: int) -> None:
        _log.info("OnStepFocuser.move(): steps=%d", steps)
        self._mount._raw_send(f":FS{steps}#")

    def is_moving(self) -> bool:
        return self._mount._send(":FT#") == "M"

    def stop(self) -> None:
        # Bypass the serial lock — stop must be immediate even when another
        # command is in progress.  Write-only: no response expected from :FQ#.
        s = self._mount._serial
        if s is not None:
            import contextlib
            with contextlib.suppress(Exception):
                s.write(b":FQ#")

    # ── private ───────────────────────────────────────────────────────────────

    def _fetch_max_position(self) -> int:
        reply = self._mount._send(":FM#")
        try:
            return int(reply)
        except ValueError:
            return 0
