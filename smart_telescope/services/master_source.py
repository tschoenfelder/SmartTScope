"""MasterSourceService — selects the master time/location source (REQ-TIME-001).

Priority order: GPS_FIX > NTP > USER_CONFIRMED > FALLBACK.
FALLBACK does not unlock mount automation.
"""
from __future__ import annotations

import logging
import subprocess

from ..domain.master_time_source import MasterTimeSource
from .gpsd_service import GpsdService

_log = logging.getLogger(__name__)

_MIN_GPS_MODE = 2  # 2 = 2-D fix, 3 = 3-D fix; mode < 2 means no valid fix


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


class MasterSourceService:
    """Evaluates the highest-priority available time/location master source."""

    def __init__(self, gpsd: GpsdService | None = None) -> None:
        self._gpsd = gpsd

    def evaluate(self, user_confirmed: bool = False) -> MasterTimeSource:
        """Return the highest-priority available source.

        Args:
            user_confirmed: True if the user has explicitly confirmed Pi clock is correct.
        """
        # 1. GPS fix
        if self._gpsd is not None:
            try:
                fix = self._gpsd.get_fix()
                if fix is not None and fix.is_fresh() and fix.mode >= _MIN_GPS_MODE:
                    _log.info("Master source: GPS_FIX (mode=%d age=%.0fs)", fix.mode, fix.fix_age_s or 0)
                    return MasterTimeSource.GPS_FIX
            except Exception as exc:
                _log.warning("GPS check failed, falling through: %s", exc)

        # 2. NTP
        if _check_ntp_sync():
            _log.info("Master source: NTP")
            return MasterTimeSource.NTP

        # 3. USER_CONFIRMED
        if user_confirmed:
            _log.info("Master source: USER_CONFIRMED")
            return MasterTimeSource.USER_CONFIRMED

        # 4. Fallback
        _log.info("Master source: FALLBACK (time untrusted)")
        return MasterTimeSource.FALLBACK

    @staticmethod
    def is_trusted(source: MasterTimeSource) -> bool:
        """Return True for any source that unlocks mount automation."""
        return source != MasterTimeSource.FALLBACK
