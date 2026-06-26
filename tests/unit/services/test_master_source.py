"""M8-006: MasterSourceService — master time source selection.

Tests cover:
- GPS_FIX when gpsd reports a fresh fix with mode >= 2
- NTP when no GPS but OS reports NTP synchronized
- USER_CONFIRMED when neither GPS nor NTP but user has confirmed
- FALLBACK when nothing available
- GPS exceptions / stale fix / mode < 2 fall through
- is_trusted() returns True for GPS/NTP/USER_CONFIRMED, False for FALLBACK
- gate_inputs_from_device_state() uses master_source_svc to set raspberry_time_trust
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.domain.master_time_source import MasterTimeSource
from smart_telescope.services.gpsd_service import GpsdFix, GpsdService
from smart_telescope.services.master_source import MasterSourceService
from smart_telescope.services.device_state import DeviceStateService, MountObservedState
from smart_telescope.ports.mount import MountState
from smart_telescope.services.operation_gate import gate_inputs_from_device_state
import time as _time

_NTP_PATH = "smart_telescope.services.master_source._check_ntp_sync"


def _fresh_fix(mode: int = 3) -> GpsdFix:
    return GpsdFix(
        lat=50.336, lon=8.533, alt=200.0,
        gps_time="2026-06-26T00:00:00Z",
        mode=mode, hdop=1.2,
        fix_age_s=30.0,
    )


def _stale_fix() -> GpsdFix:
    return GpsdFix(
        lat=50.0, lon=8.0, alt=None,
        gps_time=None, mode=3, hdop=None,
        fix_age_s=None,  # is_fresh() returns False
    )


# ── priority: GPS_FIX ────────────────────────────────────────────────────────

def test_gps_fix_available_returns_gps_fix():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _fresh_fix()
    svc = MasterSourceService(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=False):
        assert svc.evaluate() == MasterTimeSource.GPS_FIX


def test_gps_mode1_no_fix_falls_through_to_ntp():
    """mode=1 means no fix — should fall through."""
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _fresh_fix(mode=1)
    svc = MasterSourceService(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=True):
        assert svc.evaluate() == MasterTimeSource.NTP


def test_gps_stale_falls_through_to_ntp():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _stale_fix()
    svc = MasterSourceService(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=True):
        assert svc.evaluate() == MasterTimeSource.NTP


def test_gps_returns_none_falls_through_to_ntp():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = None
    svc = MasterSourceService(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=True):
        assert svc.evaluate() == MasterTimeSource.NTP


def test_gps_exception_falls_through_to_ntp():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.side_effect = Exception("gpsd unreachable")
    svc = MasterSourceService(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=True):
        assert svc.evaluate() == MasterTimeSource.NTP


# ── priority: NTP ────────────────────────────────────────────────────────────

def test_no_gps_ntp_sync_returns_ntp():
    svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=True):
        assert svc.evaluate() == MasterTimeSource.NTP


# ── priority: USER_CONFIRMED ─────────────────────────────────────────────────

def test_user_confirmed_without_gps_ntp_returns_user_confirmed():
    svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=False):
        assert svc.evaluate(user_confirmed=True) == MasterTimeSource.USER_CONFIRMED


def test_gps_takes_priority_over_user_confirmed():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _fresh_fix()
    svc = MasterSourceService(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=False):
        assert svc.evaluate(user_confirmed=True) == MasterTimeSource.GPS_FIX


def test_ntp_takes_priority_over_user_confirmed():
    svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=True):
        assert svc.evaluate(user_confirmed=True) == MasterTimeSource.NTP


# ── priority: FALLBACK ───────────────────────────────────────────────────────

def test_no_source_returns_fallback():
    svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=False):
        assert svc.evaluate() == MasterTimeSource.FALLBACK


def test_no_source_no_user_confirmed_returns_fallback():
    svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=False):
        assert svc.evaluate(user_confirmed=False) == MasterTimeSource.FALLBACK


# ── is_trusted ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("source", [
    MasterTimeSource.GPS_FIX,
    MasterTimeSource.NTP,
    MasterTimeSource.USER_CONFIRMED,
])
def test_trusted_sources_are_trusted(source):
    assert MasterSourceService.is_trusted(source) is True


def test_fallback_is_not_trusted():
    assert MasterSourceService.is_trusted(MasterTimeSource.FALLBACK) is False


# ── gate_inputs_from_device_state integration ────────────────────────────────

def _mock_ds_open() -> MagicMock:
    """Adapter open and healthy so gate reaches raspberry_time_trust."""
    ds = MagicMock(spec=DeviceStateService)
    ds.is_started.return_value = True
    ds.get_mount_state.return_value = MountObservedState(
        state=MountState.UNPARKED, ra=5.5, dec=-5.0,
        polled_at=_time.monotonic(), error=None,
    )
    from smart_telescope.domain.time_location_status import TimeLocationStatus
    ds.get_time_location_status.return_value = TimeLocationStatus.VERIFIED
    ds.is_user_time_confirmed.return_value = False
    return ds


def test_gate_inputs_trusted_when_ntp_sync():
    ds = _mock_ds_open()
    svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=True):
        inputs = gate_inputs_from_device_state(ds, master_source_svc=svc)
    assert inputs["raspberry_time_trust"] == "TRUSTED"
    assert inputs["master_time_source"] == "NTP"


def test_gate_inputs_not_trusted_when_fallback():
    ds = _mock_ds_open()
    svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=False):
        inputs = gate_inputs_from_device_state(ds, master_source_svc=svc)
    assert inputs["raspberry_time_trust"] == "NOT_TRUSTED"
    assert inputs["master_time_source"] == "FALLBACK"


def test_gate_inputs_trusted_when_gps_fix():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _fresh_fix()
    ds = _mock_ds_open()
    svc = MasterSourceService(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=False):
        inputs = gate_inputs_from_device_state(ds, master_source_svc=svc)
    assert inputs["raspberry_time_trust"] == "TRUSTED"
    assert inputs["master_time_source"] == "GPS_FIX"


def test_gate_inputs_trusted_when_user_confirmed():
    ds = _mock_ds_open()
    ds.is_user_time_confirmed.return_value = True
    svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=False):
        inputs = gate_inputs_from_device_state(ds, master_source_svc=svc)
    assert inputs["raspberry_time_trust"] == "TRUSTED"
    assert inputs["master_time_source"] == "USER_CONFIRMED"


def test_gate_inputs_stub_when_no_master_source_svc():
    """Without master_source_svc the stub returns TRUSTED (backward-compat until M8-007 wiring)."""
    ds = _mock_ds_open()
    inputs = gate_inputs_from_device_state(ds, master_source_svc=None)
    assert inputs["raspberry_time_trust"] == "TRUSTED"
    assert inputs["master_time_source"] == "STUB"


# ── DeviceStateService.user_time_confirmed ────────────────────────────────────

def test_device_state_user_time_confirmed_default_false():
    ds = DeviceStateService()
    assert ds.is_user_time_confirmed() is False


def test_device_state_set_user_time_confirmed():
    ds = DeviceStateService()
    ds.set_user_time_confirmed(True)
    assert ds.is_user_time_confirmed() is True


def test_device_state_clear_user_time_confirmed():
    ds = DeviceStateService()
    ds.set_user_time_confirmed(True)
    ds.set_user_time_confirmed(False)
    assert ds.is_user_time_confirmed() is False
