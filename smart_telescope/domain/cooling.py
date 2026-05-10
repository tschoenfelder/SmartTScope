"""TEC cooling controller for cameras with active cooling (ATR585M).

Keeps the sensor temperature at a configurable target while monitoring TEC
power draw.  When the TEC cannot maintain the target (power stays above the
stable limit for longer than the stabilisation timeout), the target is relaxed
step-wise to avoid sustained overloading of the Peltier element.

Typical call pattern::

    ctrl = CoolingController(CoolingConfig(target_c=-10.0))
    while session_running:
        temp = camera.get_temperature()
        power = camera.get_tec_power_pct()
        action = ctrl.tick(temp, power)
        if action == CoolingAction.RAISE_TARGET:
            camera.set_tec_target(ctrl.current_target_c)
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable


# Temperature tolerance: within this many °C of target counts as "near target".
_TEMP_TOLERANCE = 1.0


class CoolingAction(Enum):
    HOLD         = auto()  # cooling in progress, power within normal limits
    WARN         = auto()  # power above warning threshold (TEC may be straining)
    STABLE       = auto()  # at target temperature, power within stable limit
    RAISE_TARGET = auto()  # timed out at high power — target has been relaxed


@dataclass(frozen=True)
class CoolingConfig:
    """Immutable configuration for a CoolingController instance.

    Args:
        target_c: Desired sensor temperature.  Clamped to ≥ −10 °C.
        stable_power_limit_pct: TEC power % below which stabilisation is confirmed.
        warning_power_pct: TEC power % above which WARN is emitted.
        stabilisation_timeout_s: Seconds of sustained high power before target is relaxed.
        relax_step_c: Degrees to raise the target per relaxation step.
    """
    target_c: float = -10.0
    stable_power_limit_pct: float = 75.0
    warning_power_pct: float = 80.0
    stabilisation_timeout_s: float = 300.0
    relax_step_c: float = 1.0

    _MIN_TARGET_C: float = -10.0  # class-level constant; not a field

    def __post_init__(self) -> None:
        if self.target_c < self._MIN_TARGET_C:
            object.__setattr__(self, "target_c", self._MIN_TARGET_C)


class CoolingController:
    """Stateful TEC cooling controller.

    Args:
        config: Cooling parameters.
        clock: Callable returning monotonic time in seconds.  Defaults to
               ``time.monotonic``; pass a fake clock in tests.
    """

    def __init__(
        self,
        config: CoolingConfig,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._clock = clock
        self._current_target = config.target_c
        self._start_time: float = clock()

    @property
    def current_target_c(self) -> float:
        """Effective target temperature after any relaxation steps."""
        return self._current_target

    def tick(self, current_temp_c: float, current_power_pct: float) -> CoolingAction:
        """Evaluate current sensor state and return the recommended action.

        Args:
            current_temp_c: Current sensor temperature in °C.
            current_power_pct: Current TEC power draw as a percentage (0–100).

        Returns:
            CoolingAction indicating what the controller recommends.
        """
        now = self._clock()

        near_target = abs(current_temp_c - self._current_target) <= _TEMP_TOLERANCE
        power_stable = current_power_pct <= self._config.stable_power_limit_pct
        power_warning = current_power_pct >= self._config.warning_power_pct
        elapsed = now - self._start_time

        # Reached target and TEC is not overloaded — stable.
        if near_target and power_stable:
            return CoolingAction.STABLE

        # Sustained high power past the stabilisation window — relax target.
        if elapsed >= self._config.stabilisation_timeout_s and not power_stable:
            self._current_target += self._config.relax_step_c
            self._start_time = now  # reset timer for next convergence window
            return CoolingAction.RAISE_TARGET

        # Power is dangerously high but within the timeout — warn.
        if power_warning:
            return CoolingAction.WARN

        return CoolingAction.HOLD
