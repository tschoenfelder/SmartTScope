"""Refocus trigger logic — detects when re-running autofocus is warranted.

Three independent triggers are evaluated on every check() call:
  elapsed   — more than refocus_elapsed_min minutes since last focus
  altitude  — target altitude has changed by >= refocus_alt_delta_deg
  temperature — CCD temperature has changed by >= refocus_temp_delta_c

The caller is responsible for computing the current altitude and supplying
the temperature from the latest captured frame header (None = disabled).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class RefocusConfig:
    """Thresholds for automatic refocus triggering."""
    temp_delta_c:      float = 1.0   # re-focus if temp changed by this many °C
    altitude_delta_deg: float = 5.0  # re-focus if altitude changed by this many degrees
    elapsed_min:       float = 30.0  # re-focus if this many minutes have passed


@dataclass
class RefocusTriggerResult:
    should_refocus: bool
    reason: str | None = None   # "elapsed" | "altitude" | "temperature" | None


class RefocusTracker:
    """Tracks the conditions at last focus and detects trigger conditions.

    Usage:
        tracker.record_focus(altitude, temperature)   # after autofocus completes
        result = tracker.check(altitude, temperature) # before each stack frame
    """

    def __init__(self, config: RefocusConfig) -> None:
        self._config = config
        self._last_time:     datetime | None = None
        self._last_altitude: float    | None = None
        self._last_temp:     float    | None = None

    # ── public API ──────────────────────────────────────────────────────────

    def record_focus(self, altitude: float, temperature: float | None = None) -> None:
        """Record the conditions at the moment autofocus completed."""
        self._last_time     = datetime.now(UTC)
        self._last_altitude = altitude
        self._last_temp     = temperature

    def check(self, altitude: float, temperature: float | None = None) -> RefocusTriggerResult:
        """Return whether any trigger condition is met.

        Returns should_refocus=False when no baseline has been recorded yet
        (e.g. autofocus was skipped).
        """
        if self._last_time is None:
            return RefocusTriggerResult(should_refocus=False)

        elapsed_min = (datetime.now(UTC) - self._last_time).total_seconds() / 60.0
        if elapsed_min >= self._config.elapsed_min:
            return RefocusTriggerResult(should_refocus=True, reason="elapsed")

        if self._last_altitude is not None:
            if abs(altitude - self._last_altitude) >= self._config.altitude_delta_deg:
                return RefocusTriggerResult(should_refocus=True, reason="altitude")

        if temperature is not None and self._last_temp is not None:
            if abs(temperature - self._last_temp) >= self._config.temp_delta_c:
                return RefocusTriggerResult(should_refocus=True, reason="temperature")

        return RefocusTriggerResult(should_refocus=False)
