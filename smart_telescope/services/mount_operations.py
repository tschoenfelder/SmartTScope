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

from astropy.coordinates import EarthLocation
from astropy.time import Time
import astropy.units as u

from .. import config
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
    """Unpark the mount and wait up to 3 s for observed state to change.

    Raises:
        RuntimeError: unpark command rejected by the mount
    Returns:
        True if the observed state changed (confirmed not parked); False on timeout.
    """
    ok = mount.unpark()
    if not ok:
        raise RuntimeError("Unpark rejected by OnStep")
    _log.info("Mount unpark issued")
    changed = device_state.wait_while_mount_state(MountState.PARKED, timeout_s=3.0)
    if changed:
        obs = device_state.get_mount_state()
        _log.info("Mount unparked — state is now %s", obs.state.name if obs else "?")
    else:
        _log.warning("Mount unpark: state still PARKED after 3 s — check OnStep")
    return changed


def track_sequence(mount: MountPort) -> None:
    """Auto-unpark if parked, then enable tracking.

    Raises:
        RuntimeError: auto-unpark or enable-tracking failed
    """
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
    """Park the mount via the coordinator and wait up to 5 s for confirmation.

    Raises:
        MountSlewingError: mount is currently slewing
        CommandConflictError: coordinator is busy
        RuntimeError: park command rejected by the mount
    """
    try:
        with coordinator.mount_command():
            if mount.is_slewing():
                raise MountSlewingError("Rejected — mount is slewing")
            ok = mount.park()
            if not ok:
                raise RuntimeError("Park command rejected by OnStep")
            _log.info("Mount park issued")
    except CommandConflictError:
        raise

    converged = device_state.wait_for_mount_state(MountState.PARKED, timeout_s=5.0)
    if not converged:
        _log.warning("Mount park: state not confirmed PARKED within 5 s — mount may still be slewing")


def home_sequence(
    mount: MountPort,
    coordinator: HardwareCommandCoordinator,
) -> tuple[float, float]:
    """Slew to the home position (HA=0, Dec=85°).

    Auto-unparks if the mount is currently parked.  Returns (ra_hours, dec_deg)
    of the commanded home position.

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

    loc = EarthLocation(lat=config.OBSERVER_LAT * u.deg, lon=config.OBSERVER_LON * u.deg)
    lst_hours: float = Time.now().sidereal_time("apparent", longitude=loc.lon).hour
    ra_hours: float = lst_hours
    dec_deg: float  = 85.0
    _log.info("Mount home: slewing to RA=%.4fh Dec=%.1f°", ra_hours, dec_deg)

    try:
        with coordinator.mount_command():
            if mount.is_slewing():
                raise MountSlewingError("Rejected — mount is slewing")
            try:
                mount.goto(ra_hours, dec_deg)
            except RuntimeError:
                raise
    except CommandConflictError:
        raise

    return ra_hours, dec_deg
