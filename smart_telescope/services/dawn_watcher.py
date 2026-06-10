"""DawnWatcher — auto-park mount at astronomical dawn (sun at −18°).

Parks the mount exactly once per session when the Sun's altitude crosses
ASTRONOMICAL_DAWN_ALT_DEG.  Hardware stays connected after park so the
operator can inspect state or retry without a full reconnect cycle.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from ..domain.solar import ASTRONOMICAL_DAWN_ALT_DEG, sun_altitude_now
from ..ports.mount import MountPort
from ..services.device_state import DeviceStateService

_log = logging.getLogger(__name__)

_POLL_INTERVAL_S: float = 60.0


@dataclass(frozen=True)
class DawnStatus:
    sun_altitude_deg: float
    is_dawn: bool           # sun >= ASTRONOMICAL_DAWN_ALT_DEG
    parked_at_dawn: bool    # park command was issued this session
    parked_at: float | None  # time.monotonic() when park was sent, or None


class DawnWatcher:
    """Background service that parks the mount at astronomical dawn.

    Lifecycle::

        watcher.start(mount, device_state, lat, lon)
        # ... mount parks automatically when sun reaches -18° ...
        watcher.stop()
    """

    def __init__(self) -> None:
        self._status: DawnStatus | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._night_seen: bool = False  # True once sun has been seen below threshold

    # ── lifecycle ──────────────────────────────────────────────────────────────

    def start(
        self,
        mount: MountPort,
        device_state: DeviceStateService,
        observer_lat: float,
        observer_lon: float,
        poll_interval: float = _POLL_INTERVAL_S,
    ) -> None:
        """Start the background dawn-watch thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(mount, device_state, observer_lat, observer_lon, poll_interval),
            daemon=True,
            name="dawn-watcher",
        )
        self._thread.start()
        _log.info(
            "DawnWatcher: started (lat=%.3f lon=%.3f threshold=%.1f°)",
            observer_lat, observer_lon, ASTRONOMICAL_DAWN_ALT_DEG,
        )

    def stop(self) -> None:
        """Signal the poll thread to stop and wait up to 5 s."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        _log.info("DawnWatcher: stopped")

    # ── state access ───────────────────────────────────────────────────────────

    def get_status(self) -> DawnStatus | None:
        """Return the last observed status, or None before the first poll."""
        with self._lock:
            return self._status

    # ── internal ───────────────────────────────────────────────────────────────

    def _poll_loop(
        self,
        mount: MountPort,
        device_state: DeviceStateService,
        lat: float,
        lon: float,
        interval: float,
    ) -> None:
        while not self._stop_event.is_set():
            self._poll_once(mount, device_state, lat, lon)
            self._stop_event.wait(timeout=interval)

    def _poll_once(
        self,
        mount: MountPort,
        device_state: DeviceStateService,
        lat: float,
        lon: float,
    ) -> None:
        try:
            alt = sun_altitude_now(lat, lon)
        except Exception as exc:
            _log.warning("DawnWatcher: sun altitude error: %s", exc)
            return

        if alt < ASTRONOMICAL_DAWN_ALT_DEG:
            self._night_seen = True

        with self._lock:
            prev = self._status
            already_parked = prev is not None and prev.parked_at_dawn
            is_dawn = alt >= ASTRONOMICAL_DAWN_ALT_DEG and self._night_seen
            self._status = DawnStatus(
                sun_altitude_deg=alt,
                is_dawn=is_dawn,
                parked_at_dawn=already_parked or (is_dawn and not already_parked),
                parked_at=prev.parked_at if (prev and prev.parked_at) else (
                    time.monotonic() if (is_dawn and not already_parked) else None
                ),
            )
            should_park = is_dawn and not already_parked

        if should_park:
            self._issue_park(mount, device_state, alt)

    def _issue_park(
        self,
        mount: MountPort,
        device_state: DeviceStateService,
        sun_alt: float,
    ) -> None:
        _log.warning(
            "DawnWatcher: astronomical dawn — sun altitude %.1f° (≥ %.1f°) — parking mount",
            sun_alt, ASTRONOMICAL_DAWN_ALT_DEG,
        )
        try:
            mount.park()
            device_state.poll_now()
            _log.info("DawnWatcher: mount parked at dawn")
        except Exception as exc:
            _log.error("DawnWatcher: park command failed: %s", exc)
