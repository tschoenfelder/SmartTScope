"""DeviceStateService — background poll of mount (and future: focuser) state.

Rather than querying hardware on every API request, a background thread polls
at a fixed interval and caches the result.  Status endpoints read from this
cache.  This decouples UI polling frequency from serial bus load and makes
state changes (park confirmed, slew complete) visible as soon as they happen.

Stale detection: if the last successful poll is older than STALE_THRESHOLD_S,
callers should treat the state as uncertain and say so in the UI.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
import time

from ..ports.mount import MountPort, MountPosition, MountState

_log = logging.getLogger(__name__)

_POLL_INTERVAL_S  = 2.0   # seconds between state polls
_STALE_THRESHOLD_S = 10.0  # seconds — state older than this is shown as uncertain


@dataclasses.dataclass
class MountObservedState:
    state:     MountState
    ra:        float | None
    dec:       float | None
    polled_at: float          # time.monotonic() timestamp
    error:     str | None = None

    def age_seconds(self) -> float:
        return time.monotonic() - self.polled_at

    def is_stale(self) -> bool:
        return self.age_seconds() > _STALE_THRESHOLD_S


class DeviceStateService:
    """Background-polling cache of observed device state.

    Lifecycle::

        service.start(mount)   # called after connect_devices()
        service.stop()         # called from RuntimeContext.shutdown()

    Thread safety: all public methods are safe to call from any thread.
    """

    def __init__(self) -> None:
        self._mount_state: MountObservedState | None = None
        self._lock         = threading.Lock()
        self._stop_event   = threading.Event()
        self._thread: threading.Thread | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self, mount: MountPort, poll_interval: float = _POLL_INTERVAL_S) -> None:
        """Start the background polling thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._poll_loop,
            args=(mount, poll_interval),
            daemon=True,
            name="device-state-poll",
        )
        self._thread.start()
        _log.info("DeviceStateService: polling started (interval=%.1fs)", poll_interval)

    def stop(self) -> None:
        """Signal the polling thread to stop and wait up to 5 s."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        _log.info("DeviceStateService: polling stopped")

    # ── state access ──────────────────────────────────────────────────────────

    def get_mount_state(self) -> MountObservedState | None:
        """Return the last observed mount state, or None if no poll has run yet."""
        with self._lock:
            return self._mount_state

    # ── internal ──────────────────────────────────────────────────────────────

    def _poll_loop(self, mount: MountPort, interval: float) -> None:
        while not self._stop_event.is_set():
            self._poll_once(mount)
            self._stop_event.wait(timeout=interval)

    def _poll_once(self, mount: MountPort) -> None:
        try:
            state = mount.get_state()
            pos: MountPosition | None = None
            if state != MountState.UNKNOWN:
                try:
                    pos = mount.get_position()
                except Exception:
                    pass
            observed = MountObservedState(
                state=state,
                ra=pos.ra if pos else None,
                dec=pos.dec if pos else None,
                polled_at=time.monotonic(),
            )
        except Exception as exc:
            _log.warning("DeviceStateService: mount poll error: %s", exc)
            observed = MountObservedState(
                state=MountState.UNKNOWN,
                ra=None,
                dec=None,
                polled_at=time.monotonic(),
                error=str(exc),
            )
        with self._lock:
            self._mount_state = observed
