"""SimulatorFocuser — FocuserPort with configurable move delay.

Simulates real focuser behaviour: move() briefly enters moving state and
settles to the target position after move_time_s.  move_time_s=0.0 (default)
resolves instantly.
"""
from __future__ import annotations

import logging
import threading

from ...ports.focuser import FocuserMoveResult, FocuserPort, FocuserStatus

_log = logging.getLogger(__name__)


class SimulatorFocuser(FocuserPort):
    """FocuserPort simulator with optional timed movement.

    Args:
        move_time_s: seconds before position updates after move().
            0.0 (default) = instant.
    """

    def __init__(self, move_time_s: float = 0.0) -> None:
        if move_time_s < 0.0:
            raise ValueError(f"move_time_s must be >= 0, got {move_time_s}")
        _log.info("SimulatorFocuser initialised (move_time_s=%.1f) — software simulation, no real hardware", move_time_s)
        self._move_time_s = move_time_s
        self._position = 0
        self._target: int | None = None
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()

    # ── FocuserPort ───────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        return True

    def connect(self) -> bool:
        _log.info("SimulatorFocuser.connect(): connected (simulated)")
        return True

    def disconnect(self) -> None:
        with self._lock:
            self._cancel_timer()
            self._target = None

    def status(self) -> FocuserStatus:
        return FocuserStatus(
            available=self.is_available,
            position=self.get_position(),
            max_position=self.get_max_position(),
            moving=self.is_moving(),
        )

    def move_absolute(self, steps: int) -> FocuserMoveResult:
        start = self.get_position()
        self.move(steps)
        return FocuserMoveResult(
            accepted=True,
            target_position=steps,
            start_position=start,
            onstep_reply="1",
        )

    def move(self, steps: int) -> None:
        with self._lock:
            self._cancel_timer()
            if self._move_time_s > 0.0:
                self._target = steps
                timer = threading.Timer(self._move_time_s, self._finish_move)
                self._timer = timer
                timer.start()
            else:
                self._position = steps

    def get_position(self) -> int:
        with self._lock:
            return self._position

    def get_max_position(self) -> int:
        return 5000

    def is_moving(self) -> bool:
        with self._lock:
            return self._target is not None

    def stop(self) -> None:
        with self._lock:
            self._cancel_timer()
            self._target = None

    # ── private ───────────────────────────────────────────────────────────────

    def _cancel_timer(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None

    def _finish_move(self) -> None:
        with self._lock:
            if self._target is not None:
                self._position = self._target
                self._target = None
            self._timer = None
