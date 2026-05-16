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
        # R2-003: last command tracking
        self._last_command:       str   | None = None
        self._last_command_at:    float | None = None  # time.monotonic()
        self._last_command_error: str   | None = None

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

    # ── R2-003: command tracking ──────────────────────────────────────────────

    def record_command(self, command: str) -> None:
        """Record that a mount command was issued (park, unpark, goto, etc.)."""
        with self._lock:
            self._last_command       = command
            self._last_command_at    = time.monotonic()
            self._last_command_error = None

    def record_command_error(self, error: str) -> None:
        """Record the error string from the most recent command."""
        with self._lock:
            self._last_command_error = error

    def get_last_command(self) -> tuple[str | None, float | None, str | None]:
        """Return (command_name, monotonic_timestamp, error_or_None)."""
        with self._lock:
            return self._last_command, self._last_command_at, self._last_command_error

    # ── R2-005: state convergence helpers ────────────────────────────────────

    def wait_for_mount_state(
        self,
        target_state: MountState,
        timeout_s: float = 5.0,
        poll_s: float = 0.2,
    ) -> bool:
        """Poll the cached state until it equals *target_state* or times out.

        Returns True when the target was observed; False on timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            obs = self.get_mount_state()
            if obs is not None and obs.state == target_state:
                return True
            time.sleep(poll_s)
        return False

    def wait_while_mount_state(
        self,
        current_state: MountState,
        timeout_s: float = 5.0,
        poll_s: float = 0.2,
    ) -> bool:
        """Poll the cached state until it differs from *current_state* or times out.

        Returns True when the state changed; False if it stayed the same until
        the timeout.  Useful after park/unpark to confirm state transition.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            obs = self.get_mount_state()
            if obs is not None and obs.state != current_state:
                return True
            time.sleep(poll_s)
        return False

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
