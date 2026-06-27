"""RaspberryTimeTrustService — evaluates Pi clock trust source (REQ-TIME-002, REQ-TIME-004).

Priority: GPSD_FIX > NTP > ONSTEP_COMPARISON > USER_CONFIRMED > NOT_TRUSTED.

DEC-006 trust chain (ONSTEP_COMPARISON):
  OnStep's clock, when trusted via GPS/NTP or a previous Stage 1 verification,
  can act as a reference to validate the Pi's own clock.  This establishes a
  secondary but legitimate trust chain: OnStep(trusted) → compare → Pi validated.

  Requirements for ONSTEP_COMPARISON to be active:
    (a) Stage 1 was VERIFIED — OnStep time compared to Pi master time, within tolerance.
    (b) ONSTEP_COMPARISON trust was explicitly established at comparison time
        (DeviceStateService.set_onstep_comparison_established() called by mount_sync_clock
        only when master source was GPS_FIX or NTP at that moment).
    (c) Trust is within the session expiry window (default 120 minutes).

  Pushing Pi time → OnStep alone does NOT create ONSTEP_COMPARISON trust.
  A subsequent re-comparison step (Stage 1 re-run or confirmed comparison) is required.

USER_CONFIRMED trust:
  Valid for the session up to session_trust_expiry_minutes.
  A warning is logged whenever USER_CONFIRMED is the active trust source.
"""
from __future__ import annotations

import logging
import subprocess
import time

from ..domain.raspberry_time_trust import RaspberryTimeTrustSource, is_trusted
from .gpsd_service import GpsdService

_log = logging.getLogger(__name__)

_MIN_GPS_MODE = 2  # mode < 2 means no valid 2-D/3-D fix


def _check_ntp_sync() -> bool:
    """Return True if the OS reports NTP synchronization (Linux: timedatectl)."""
    try:
        result = subprocess.run(
            ["timedatectl", "show", "--no-pager", "-p", "NTPSynchronized"],
            capture_output=True, text=True, timeout=3.0,
        )
        return "NTPSynchronized=yes" in result.stdout
    except Exception:
        return False


class RaspberryTimeTrustService:
    """Evaluates the Raspberry Pi clock trust source."""

    def __init__(
        self,
        gpsd: GpsdService | None = None,
        session_trust_expiry_minutes: int = 120,
    ) -> None:
        self._gpsd = gpsd
        self._expiry_s = session_trust_expiry_minutes * 60

    def evaluate(
        self,
        *,
        time_location_verified: bool,
        onstep_comparison_established_at: float | None,
        user_confirmed: bool,
        user_confirmed_at: float | None,
    ) -> RaspberryTimeTrustSource:
        """Return the highest-priority trust source for the Raspberry Pi clock.

        Args:
            time_location_verified: True when Stage 1 completed with VERIFIED status.
            onstep_comparison_established_at: Monotonic timestamp when ONSTEP_COMPARISON
                trust was established (None if not yet established in this session).
            user_confirmed: True when user explicitly confirmed Pi clock.
            user_confirmed_at: Monotonic timestamp of the user confirmation (None if
                user_confirmed is False or confirmation was cleared).
        """
        # 1. GPSD_FIX: Pi clock synced from a local GPS receiver
        if self._check_gpsd_fix():
            _log.debug("Raspberry Pi time trust: GPSD_FIX")
            return RaspberryTimeTrustSource.GPSD_FIX

        # 2. NTP: OS clock synchronised via NTP
        if _check_ntp_sync():
            _log.debug("Raspberry Pi time trust: NTP")
            return RaspberryTimeTrustSource.NTP

        # 3. ONSTEP_COMPARISON (DEC-006 trust chain)
        # OnStep's trusted clock validates the Pi clock when:
        #   - Stage 1 verified (comparison within tolerance to trusted master source), AND
        #   - ONSTEP_COMPARISON was explicitly established (master was GPS/NTP at the time), AND
        #   - Still within session expiry.
        # See module docstring for full conditions and "push alone not sufficient" rule.
        if (
            time_location_verified
            and onstep_comparison_established_at is not None
            and not self._is_expired(onstep_comparison_established_at)
        ):
            _log.debug("Raspberry Pi time trust: ONSTEP_COMPARISON")
            return RaspberryTimeTrustSource.ONSTEP_COMPARISON

        # 4. USER_CONFIRMED: user asserted Pi clock is correct (warning logged each evaluation)
        if (
            user_confirmed
            and user_confirmed_at is not None
            and not self._is_expired(user_confirmed_at)
        ):
            _log.warning(
                "Raspberry Pi time trust: USER_CONFIRMED "
                "(user-asserted only — no GPS, NTP, or OnStep verification)"
            )
            return RaspberryTimeTrustSource.USER_CONFIRMED

        _log.debug("Raspberry Pi time trust: NOT_TRUSTED")
        return RaspberryTimeTrustSource.NOT_TRUSTED

    def _check_gpsd_fix(self) -> bool:
        if self._gpsd is None:
            return False
        try:
            fix = self._gpsd.get_fix()
            return fix is not None and fix.is_fresh() and fix.mode >= _MIN_GPS_MODE
        except Exception:
            return False

    def _is_expired(self, established_at: float) -> bool:
        """Return True if the trust timestamp is older than the session expiry window."""
        return (time.monotonic() - established_at) > self._expiry_s

    @staticmethod
    def is_trusted(source: RaspberryTimeTrustSource) -> bool:
        """Return True for any source that unlocks mount automation."""
        return is_trusted(source)
