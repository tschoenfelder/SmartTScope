"""SimulatorMount — MountPort with configurable slew delay.

Simulates real mount behaviour: goto() briefly enters SLEWING state and
transitions to TRACKING after slew_time_s.  slew_time_s=0.0 (default)
resolves instantly, matching SimulatorCamera's speed=0.0 convention.
"""
from __future__ import annotations

import threading

from ...ports.mount import MountPort, MountPosition, MountState


class SimulatorMount(MountPort):
    """MountPort simulator with optional timed slew.

    Args:
        slew_time_s: seconds to spend in SLEWING state after goto().
            0.0 (default) = instant transition to TRACKING.
    """

    def __init__(self, slew_time_s: float = 0.0) -> None:
        if slew_time_s < 0.0:
            raise ValueError(f"slew_time_s must be >= 0, got {slew_time_s}")
        self._slew_time_s = slew_time_s
        self._state = MountState.PARKED
        self._position = MountPosition(ra=0.0, dec=0.0)
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    # ── MountPort ─────────────────────────────────────────────────────────────

    def connect(self) -> bool:
        return True

    def get_state(self) -> MountState:
        with self._lock:
            return self._state

    def unpark(self) -> bool:
        with self._lock:
            self._state = MountState.UNPARKED
        return True

    def enable_tracking(self) -> bool:
        with self._lock:
            self._state = MountState.TRACKING
        return True

    def get_position(self) -> MountPosition:
        with self._lock:
            return self._position

    def sync(self, ra: float, dec: float) -> bool:
        with self._lock:
            self._position = MountPosition(ra=ra, dec=dec)
        return True

    def goto(self, ra: float, dec: float) -> bool:
        with self._lock:
            self._cancel_timer()
            self._position = MountPosition(ra=ra, dec=dec)
            if self._slew_time_s > 0.0:
                self._state = MountState.SLEWING
                timer = threading.Timer(self._slew_time_s, self._finish_slew)
                self._timer = timer
                timer.start()
            else:
                self._state = MountState.TRACKING
        return True

    def is_slewing(self) -> bool:
        with self._lock:
            return self._state == MountState.SLEWING

    def stop(self) -> None:
        with self._lock:
            self._cancel_timer()
            self._state = MountState.UNPARKED

    def disconnect(self) -> None:
        with self._lock:
            self._cancel_timer()
            self._state = MountState.PARKED

    # ── private ───────────────────────────────────────────────────────────────

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _finish_slew(self) -> None:
        with self._lock:
            if self._state == MountState.SLEWING:
                self._state = MountState.TRACKING
            self._timer = None
