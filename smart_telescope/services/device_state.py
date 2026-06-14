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

_POLL_INTERVAL_S     = 2.0   # seconds between state polls
_STALE_THRESHOLD_S   = 10.0  # seconds — state older than this is shown as uncertain
_WATCHDOG_SLEW_S     = 120.0 # M1-004: warn if mount stays SLEWING beyond this
_WATCHDOG_COOLDOWN_S = 30.0  # suppress repeated watchdog log lines within this window
_RECONNECT_INTERVAL_S = 30.0 # minimum seconds between serial reconnect attempts


@dataclasses.dataclass
class MountObservedState:
    state:     MountState
    ra:        float | None
    dec:       float | None
    polled_at: float          # time.monotonic() timestamp
    error:     str | None = None
    safety_violation: str | None = None  # populated from adapter safety_lock when active

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
        self._mount: MountPort | None = None
        self._lock         = threading.Lock()
        self._stop_event   = threading.Event()
        self._thread: threading.Thread | None = None
        # R2-003: last command tracking; R1-006: sequential command IDs
        self._last_command:       str   | None = None
        self._last_command_id:    str   | None = None
        self._last_command_at:    float | None = None  # time.monotonic()
        self._last_command_error: str   | None = None
        self._cmd_counter: int = 0
        # M1-004: hardware watchdog
        self._watchdog_warning:   str   | None = None
        self._watchdog_fired_at:  float | None = None  # time.monotonic() of last log
        # serial reconnect throttle
        self._last_reconnect_at:  float | None = None
        # Sticky AT_HOME: OnStep only sets 'H' in :GU# briefly after hC# completes.
        # We preserve AT_HOME until the mount actually moves or starts tracking.
        self._sticky_at_home: bool = False
        # Require SLEWING to be observed after the home command before UNPARKED is
        # promoted to AT_HOME.  Without this gate, the first poll after :hC# can see
        # UNPARKED (OnStep hasn't set the S flag yet) and display HOME prematurely.
        self._home_cmd_issued: bool = False
        self._home_slew_seen:  bool = False

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self, mount: MountPort, poll_interval: float = _POLL_INTERVAL_S) -> None:
        """Start the background polling thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._mount = mount
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
        self._mount = None
        _log.info("DeviceStateService: polling stopped")

    def poll_now(self) -> None:
        """Run a single mount poll immediately and update the cache.

        Used after park/unpark commands to refresh the cached state without
        waiting for the next background poll interval (nominally 2 s).
        No-op when called before start() or after stop().
        """
        mount = self._mount
        if mount is None:
            return
        self._poll_once(mount)

    # ── state access ──────────────────────────────────────────────────────────

    def get_mount_state(self) -> MountObservedState | None:
        """Return the last observed mount state, or None if no poll has run yet."""
        with self._lock:
            return self._mount_state

    # ── R2-003 / R1-006: command tracking with structured IDs ─────────────────

    def record_command(self, command: str) -> str:
        """Record that a mount command was issued and return its command ID.

        Each call increments an internal counter and generates a unique ID of
        the form ``cmd-0001``.  The ID is included in the structured log line
        so that the matching ``record_command_error`` entry can be correlated.

        Returns:
            The assigned command ID string (e.g. ``"cmd-0001"``).
        """
        with self._lock:
            self._cmd_counter += 1
            cmd_id = f"cmd-{self._cmd_counter:04d}"
            self._last_command       = command
            self._last_command_id    = cmd_id
            self._last_command_at    = time.monotonic()
            self._last_command_error = None
            self._watchdog_warning   = None
            self._watchdog_fired_at  = None
            # home: don't set sticky immediately — wait until SLEWING is observed
            # (OnStep's S flag), then promote UNPARKED → AT_HOME after slew ends.
            # Prevents premature HOME display before OnStep sets the S flag.
            if command == "home":
                self._home_cmd_issued = True
                self._home_slew_seen  = False
            elif command in ("goto", "park", "track"):
                self._sticky_at_home  = False
                self._home_cmd_issued = False
                self._home_slew_seen  = False
        _log.info("command issued command_id=%s command=%r", cmd_id, command)
        return cmd_id

    def record_command_error(self, error: str) -> None:
        """Record the error string from the most recent command."""
        with self._lock:
            self._last_command_error = error
            cmd_id   = self._last_command_id
            command  = self._last_command
        _log.warning("command failed command_id=%s command=%r error=%r",
                     cmd_id, command, error)

    def get_last_command(self) -> tuple[str | None, float | None, str | None]:
        """Return (command_name, monotonic_timestamp, error_or_None)."""
        with self._lock:
            return self._last_command, self._last_command_at, self._last_command_error

    def get_last_command_id(self) -> str | None:
        """Return the ID assigned to the most recently issued command."""
        with self._lock:
            return self._last_command_id

    def get_watchdog_warning(self) -> str | None:
        """Return the active watchdog warning string, or None if hardware is responding normally."""
        with self._lock:
            return self._watchdog_warning

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
        """Poll hardware until state differs from *current_state* or times out.

        Calls poll_now() each iteration for a fresh hardware query.
        Returns True when the state changed; False on timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.poll_now()
            obs = self.get_mount_state()
            if obs is not None and obs.state != current_state:
                return True
            if time.monotonic() < deadline:
                time.sleep(poll_s)
        return False

    def poll_until_changed(
        self,
        from_state: MountState,
        timeout_s: float = 10.0,
        interval_s: float = 0.5,
    ) -> bool:
        """Poll hardware until state differs from *from_state*, or timeout.

        Issues a fresh :GU# query on each iteration — does not rely on the
        background-poll cache.  Returns True if state changed; False on timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            self.poll_now()
            obs = self.get_mount_state()
            if obs is not None and obs.state != from_state:
                return True
            if time.monotonic() < deadline:
                time.sleep(interval_s)
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
            else:
                _log.warning("DeviceStateService: get_state() returned UNKNOWN — Stage 4 will stay locked until this clears")

            # Sticky AT_HOME: OnStep's 'H' flag clears quickly after the home slew.
            # Promotion rules (SLEWING / TRACKING / PARKED are always shown as-is):
            # 1. Hardware 'H' flag observed → set sticky directly.
            # 2. SLEWING observed after home command → mark slew as confirmed.
            # 3. UNPARKED after confirmed home slew → promote to AT_HOME + set sticky.
            # 4. UNPARKED with existing sticky (previous confirmed home) → stay AT_HOME.
            with self._lock:
                if state == MountState.AT_HOME:
                    self._sticky_at_home  = True
                    self._home_cmd_issued = False
                    self._home_slew_seen  = False
                elif state == MountState.SLEWING and self._home_cmd_issued:
                    self._home_slew_seen = True
                elif state == MountState.UNPARKED:
                    if self._home_cmd_issued and self._home_slew_seen:
                        # Slew started and ended: mount is at home position
                        self._sticky_at_home  = True
                        self._home_cmd_issued = False
                        self._home_slew_seen  = False
                        state = MountState.AT_HOME
                    elif self._sticky_at_home:
                        state = MountState.AT_HOME

            safety_lock = getattr(mount, "safety_lock", None)
            observed = MountObservedState(
                state=state,
                ra=pos.ra if pos else None,
                dec=pos.dec if pos else None,
                polled_at=time.monotonic(),
                safety_violation=safety_lock.reason if safety_lock else None,
            )
        except Exception as exc:
            _log.warning("DeviceStateService: mount poll error (will store UNKNOWN): %s", exc)
            observed = MountObservedState(
                state=MountState.UNKNOWN,
                ra=None,
                dec=None,
                polled_at=time.monotonic(),
                error=str(exc),
            )
            now = time.monotonic()
            if (self._last_reconnect_at is None
                    or now - self._last_reconnect_at >= _RECONNECT_INTERVAL_S):
                self._last_reconnect_at = now
                _log.info("DeviceStateService: serial error — attempting reconnect")
                try:
                    ok = mount.connect()
                    if ok:
                        _log.info("DeviceStateService: reconnect succeeded")
                    else:
                        _log.warning("DeviceStateService: reconnect failed — will retry in %.0fs",
                                     _RECONNECT_INTERVAL_S)
                except Exception as reconnect_exc:
                    _log.warning("DeviceStateService: reconnect error: %s", reconnect_exc)
        with self._lock:
            self._mount_state = observed
            self._check_watchdog_locked()

    def _check_watchdog_locked(self) -> None:
        """M1-004: fire a warning if mount stays SLEWING past the watchdog threshold.

        Must be called while ``self._lock`` is held.
        """
        obs = self._mount_state
        now = time.monotonic()

        if obs is None or obs.state != MountState.SLEWING:
            if self._watchdog_warning is not None:
                _log.info("Watchdog: mount left SLEWING state — clearing warning")
                self._watchdog_warning  = None
                self._watchdog_fired_at = None
            return

        if self._last_command_at is None:
            return
        age = now - self._last_command_at
        if age < _WATCHDOG_SLEW_S:
            return

        if (self._watchdog_fired_at is not None
                and (now - self._watchdog_fired_at) < _WATCHDOG_COOLDOWN_S):
            return

        msg = (
            f"Mount has been SLEWING for {age:.0f} s "
            f"(command: {self._last_command!r}) — "
            "OnStep may not be responding; consider issuing a STOP"
        )
        self._watchdog_warning  = msg
        self._watchdog_fired_at = now
        _log.warning("Watchdog: %s", msg)
