"""Mount orchestration operations — multi-step sequences extracted from api/mount.py.

R6-001: API modules should be thin (validate → call service → map response).
        Multi-step mount sequences live here; API maps domain exceptions to HTTP.

Note: _compute_ha_alt / _check_mount_limits are kept in api/mount.py because the
existing test suite patches ``smart_telescope.api.mount.Time`` and
``smart_telescope.api.mount.is_solar_target`` at that import site.
"""

from __future__ import annotations

import logging
import time

from ..ports.mount import MountPort, MountState
from ..services.hardware_coordinator import CommandConflictError, HardwareCommandCoordinator
from ..services.device_state import DeviceStateService

_log = logging.getLogger(__name__)


# ── Domain exceptions ─────────────────────────────────────────────────────────

class MountSlewingError(Exception):
    """Raised when a goto/park is attempted while the mount is already slewing."""


# ── Single-command wrappers ───────────────────────────────────────────────────

def safe_goto(
    mount: MountPort,
    coordinator: HardwareCommandCoordinator,
    ra: float,
    dec: float,
) -> None:
    """Issue a goto only when the mount is confirmed idle via the coordinator.

    Raises:
        MountSlewingError: mount is already slewing
        CommandConflictError: coordinator is busy with another command
        RuntimeError: mount rejected the goto command
    """
    # Time/location verification is enforced at the API layer (M7-002).
    # safe_goto() trusts that the caller has already checked TimeLocationStatus.
    try:
        with coordinator.mount_command():
            if mount.is_slewing():
                raise MountSlewingError("Mount is currently slewing — stop it before issuing a new GoTo")
            try:
                mount.goto(ra, dec)
            except RuntimeError:
                raise
            _log.info("Mount goto issued: ra=%.4fh dec=%.2f°", ra, dec)
    except CommandConflictError:
        raise


# ── Multi-step sequences ──────────────────────────────────────────────────────

def unpark_sequence(mount: MountPort, device_state: DeviceStateService) -> bool:
    """:hR# is synchronous — OnStep blocks ~2 s then returns '1' (ok) or '0' (rejected).

    OnStep auto-starts tracking after :hR#.  We disable it immediately so the
    mount stays stationary until the user explicitly enables tracking.  A 1 s
    settle delay separates :hR# from the subsequent :Q#/:Td# to avoid a transient
    GU# 'parked' flag that some firmware versions show when :Q# arrives too soon
    after :hR#.

    If OnStep returns '0' (no alignment, etc.) we log a warning but still return
    True — the JS poll loop will reflect the current state.
    """
    ok = mount.unpark()
    _log.info("Mount unpark: OnStep reply = %s", "1 (ok)" if ok else "0 (rejected)")
    if not ok:
        _log.warning(
            "Mount unpark rejected by OnStep (:hR# returned 0) — "
            "check alignment / firmware"
        )
    time.sleep(1.0)
    dt_ok = mount.disable_tracking()
    _log.info("Mount unpark: disable_tracking = %s", "ok" if dt_ok else "rejected")
    device_state.poll_now()
    obs = device_state.get_mount_state()
    state_name = obs.state.name if obs else "?"
    _log.info("Mount unpark: state = %s", state_name)
    return True


def track_sequence(mount: MountPort) -> None:
    """Auto-unpark if parked, then enable tracking.

    Raises:
        RuntimeError: auto-unpark or enable-tracking failed
    """
    # Time/location verification is enforced at the API layer (M7-002).
    if mount.get_state() == MountState.PARKED:
        if not mount.unpark():
            raise RuntimeError("Auto-unpark before tracking failed")
    ok = mount.enable_tracking()
    if not ok:
        raise RuntimeError("Enable tracking failed")


def park_sequence(
    mount: MountPort,
    coordinator: HardwareCommandCoordinator,
    device_state: DeviceStateService,
) -> None:
    """Park the mount via the coordinator.

    Sends :hP# to park to OnStep's stored park position.  If the mount is
    currently slewing, stops it first then parks.  The park position must be
    configured in OnStep directly — this function never modifies it (:hS# is
    a user-only operation to avoid overwriting EEPROM park data).

    After sending :hP#, polls :GU# until state leaves UNPARKED (confirming
    the slew started) or times out after 5 s.  The full park slew can take
    30–120 s — JS polls for 60 s to detect final PARKED state.

    Raises:
        MountSlewingError: mount is currently slewing
        CommandConflictError: coordinator is busy
        RuntimeError: park command rejected by the mount
    """
    pre_state = mount.get_state()
    _log.info("park_sequence: pre-park state = %s", pre_state.name)

    if pre_state == MountState.PARKED:
        _log.info("park_sequence: mount already PARKED — skipping :hP#")
        return

    try:
        with coordinator.mount_command():
            slewing_now = mount.is_slewing() or pre_state == MountState.SLEWING
            if slewing_now:
                _log.info("park_sequence: stopping active slew before parking")
                mount.stop()
                time.sleep(0.3)  # let :Q# register before :hP#
            ok = mount.park()
            if not ok:
                raise RuntimeError(
                    ":hP# rejected by OnStep — home the mount first to establish "
                    "the park position, then park"
                )
            _log.info("Mount park issued")
    except CommandConflictError:
        raise

    changed = device_state.poll_until_changed(MountState.UNPARKED, timeout_s=5.0)
    obs = device_state.get_mount_state()
    state_name = obs.state.name if obs else "?"
    if changed:
        _log.info("Mount park slew started: state = %s", state_name)
    else:
        _log.warning(
            "Mount park: state still UNPARKED after 5 s — "
            "check OnStep park position / firmware; state: %s",
            state_name,
        )


def home_sequence(
    mount: MountPort,
    coordinator: HardwareCommandCoordinator,
) -> bool:
    """Slew to the OnStep stored home position (:hC#).

    Uses OnStep's own home position (set via :hF# during initial setup)
    rather than computing a SmartTScope-side target.  Auto-unparks if the
    mount is currently parked.

    Returns True if AT_HOME was confirmed during the tight poll below, False
    otherwise. Callers that need to know whether homing actually succeeded
    must use this return value rather than re-querying mount.get_state()
    afterward — AT_HOME is a brief flag on real OnStep hardware (see the tight
    poll comment) and can already have cleared to something else by the time
    a second, independent query runs.

    Raises:
        RuntimeError: auto-unpark failed
        MountSlewingError: mount is already slewing
        CommandConflictError: coordinator is busy
    """
    if mount.get_state() == MountState.PARKED:
        if not mount.unpark():
            raise RuntimeError("Auto-unpark before home failed")
        _log.info("Mount home: unparked — waiting for state to propagate")
        time.sleep(1.0)

    # OnStep silently ignores :hC# while sidereal tracking is active on some
    # firmware versions.  Disable tracking first so the home slew always starts.
    if mount.get_state() == MountState.TRACKING:
        mount.disable_tracking()
        _log.info("Mount home: tracking disabled before home command")

    try:
        with coordinator.mount_command():
            if mount.is_slewing():
                raise MountSlewingError("Rejected — mount is slewing")
            mount.go_home()
            _log.info("Mount home: go_home() issued")
    except CommandConflictError:
        raise

    # Poll directly at 0.5 s to catch the brief at_home ('H') GU# flag.
    # The 2 s background poll is too coarse — if the mount is already near home
    # the slew completes and 'H' clears before the next background poll fires.
    _HOME_POLL_INTERVAL_S = 0.5
    _HOME_TIMEOUT_S       = 60.0
    deadline = time.monotonic() + _HOME_TIMEOUT_S
    last_state = MountState.SLEWING
    while time.monotonic() < deadline:
        last_state = mount.get_state()
        if last_state == MountState.AT_HOME:
            _log.info("Mount home: AT_HOME confirmed by tight poll")
            break
        if last_state not in (MountState.SLEWING, MountState.UNPARKED):
            _log.info("Mount home: unexpected state %s — stopping poll", last_state.name)
            break
        time.sleep(_HOME_POLL_INTERVAL_S)
    else:
        _log.warning("Mount home: AT_HOME not confirmed within %.0f s (last state: %s)",
                     _HOME_TIMEOUT_S, last_state.name)
    return last_state == MountState.AT_HOME
