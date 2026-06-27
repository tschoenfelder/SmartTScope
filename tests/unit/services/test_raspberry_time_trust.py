"""M8-007: RaspberryTimeTrustService — Raspberry Pi clock trust sources.

Tests cover:
- GPSD_FIX when gpsd has a fresh fix (mode >= 2)
- NTP when no GPS but OS reports NTP synchronised
- ONSTEP_COMPARISON when Stage 1 verified + established_at set + within expiry
- ONSTEP_COMPARISON: not triggered without established_at
- ONSTEP_COMPARISON: not triggered without Stage 1 VERIFIED
- ONSTEP_COMPARISON: expired → falls through
- USER_CONFIRMED when no GPS/NTP/ONSTEP_COMPARISON + confirmed + within expiry
- USER_CONFIRMED: expired → NOT_TRUSTED
- NOT_TRUSTED when nothing
- Priority ordering: GPSD_FIX > NTP > ONSTEP_COMPARISON > USER_CONFIRMED > NOT_TRUSTED
- is_trusted(): all sources except NOT_TRUSTED return True
- gate_inputs_from_device_state with raspberry_trust_svc
- DeviceStateService: set/get_onstep_comparison_established_at, get_user_time_confirmed_at
- USER_CONFIRMED warning logged
"""
from __future__ import annotations

import logging
import time as _time
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.domain.raspberry_time_trust import RaspberryTimeTrustSource, is_trusted
from smart_telescope.services.gpsd_service import GpsdFix, GpsdService
from smart_telescope.services.raspberry_time_trust import RaspberryTimeTrustService
from smart_telescope.services.device_state import DeviceStateService, MountObservedState
from smart_telescope.ports.mount import MountState
from smart_telescope.services.operation_gate import gate_inputs_from_device_state
from smart_telescope.domain.time_location_status import TimeLocationStatus

_NTP_PATH = "smart_telescope.services.raspberry_time_trust._check_ntp_sync"


def _fresh_fix(mode: int = 3) -> GpsdFix:
    return GpsdFix(
        lat=50.336, lon=8.533, alt=200.0,
        gps_time="2026-06-27T00:00:00Z",
        mode=mode, hdop=1.2,
        fix_age_s=30.0,
    )


def _stale_fix() -> GpsdFix:
    return GpsdFix(
        lat=50.0, lon=8.0, alt=None,
        gps_time=None, mode=3, hdop=None,
        fix_age_s=None,  # is_fresh() returns False
    )


def _svc(gpsd=None, expiry_minutes=120) -> RaspberryTimeTrustService:
    return RaspberryTimeTrustService(gpsd=gpsd, session_trust_expiry_minutes=expiry_minutes)


# ── GPSD_FIX ─────────────────────────────────────────────────────────────────

def test_gpsd_fix_returns_gpsd_fix():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _fresh_fix()
    svc = _svc(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.GPSD_FIX


def test_gpsd_mode1_no_fix_falls_through():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _fresh_fix(mode=1)
    svc = _svc(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=True):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NTP


def test_gpsd_stale_falls_through():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _stale_fix()
    svc = _svc(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=True):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NTP


def test_gpsd_exception_falls_through():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.side_effect = RuntimeError("gpsd socket error")
    svc = _svc(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=True):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NTP


# ── NTP ──────────────────────────────────────────────────────────────────────

def test_ntp_sync_returns_ntp():
    svc = _svc()
    with patch(_NTP_PATH, return_value=True):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NTP


def test_gpsd_takes_priority_over_ntp():
    gpsd = MagicMock(spec=GpsdService)
    gpsd.get_fix.return_value = _fresh_fix()
    svc = _svc(gpsd=gpsd)
    with patch(_NTP_PATH, return_value=True):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.GPSD_FIX


# ── ONSTEP_COMPARISON ─────────────────────────────────────────────────────────

def test_onstep_comparison_when_verified_and_established():
    svc = _svc()
    established_at = _time.monotonic()
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=True,
            onstep_comparison_established_at=established_at,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.ONSTEP_COMPARISON


def test_onstep_comparison_requires_stage1_verified():
    svc = _svc()
    established_at = _time.monotonic()
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=False,  # Stage 1 not verified
            onstep_comparison_established_at=established_at,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NOT_TRUSTED


def test_onstep_comparison_requires_established_at():
    svc = _svc()
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=True,
            onstep_comparison_established_at=None,  # never established
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NOT_TRUSTED


def test_onstep_comparison_expired_falls_through():
    svc = _svc(expiry_minutes=1)  # 60 s expiry
    established_at = _time.monotonic() - 61  # 61 s ago → expired
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=True,
            onstep_comparison_established_at=established_at,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NOT_TRUSTED


def test_onstep_comparison_just_within_expiry():
    svc = _svc(expiry_minutes=1)  # 60 s expiry
    established_at = _time.monotonic() - 55  # 55 s ago → within expiry
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=True,
            onstep_comparison_established_at=established_at,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.ONSTEP_COMPARISON


def test_ntp_takes_priority_over_onstep_comparison():
    svc = _svc()
    established_at = _time.monotonic()
    with patch(_NTP_PATH, return_value=True):
        result = svc.evaluate(
            time_location_verified=True,
            onstep_comparison_established_at=established_at,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NTP


# ── USER_CONFIRMED ───────────────────────────────────────────────────────────

def test_user_confirmed_returns_user_confirmed():
    svc = _svc()
    confirmed_at = _time.monotonic()
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=True,
            user_confirmed_at=confirmed_at,
        )
    assert result == RaspberryTimeTrustSource.USER_CONFIRMED


def test_user_confirmed_logs_warning(caplog):
    svc = _svc()
    confirmed_at = _time.monotonic()
    with patch(_NTP_PATH, return_value=False):
        with caplog.at_level(logging.WARNING, logger="smart_telescope.services.raspberry_time_trust"):
            svc.evaluate(
                time_location_verified=False,
                onstep_comparison_established_at=None,
                user_confirmed=True,
                user_confirmed_at=confirmed_at,
            )
    assert any("USER_CONFIRMED" in r.message for r in caplog.records)


def test_user_confirmed_requires_confirmed_at():
    svc = _svc()
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=True,
            user_confirmed_at=None,  # missing timestamp
        )
    assert result == RaspberryTimeTrustSource.NOT_TRUSTED


def test_user_confirmed_expired_returns_not_trusted():
    svc = _svc(expiry_minutes=1)
    confirmed_at = _time.monotonic() - 61  # expired
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=True,
            user_confirmed_at=confirmed_at,
        )
    assert result == RaspberryTimeTrustSource.NOT_TRUSTED


def test_onstep_comparison_takes_priority_over_user_confirmed():
    svc = _svc()
    established_at = _time.monotonic()
    confirmed_at   = _time.monotonic()
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=True,
            onstep_comparison_established_at=established_at,
            user_confirmed=True,
            user_confirmed_at=confirmed_at,
        )
    assert result == RaspberryTimeTrustSource.ONSTEP_COMPARISON


# ── NOT_TRUSTED ───────────────────────────────────────────────────────────────

def test_no_source_returns_not_trusted():
    svc = _svc()
    with patch(_NTP_PATH, return_value=False):
        result = svc.evaluate(
            time_location_verified=False,
            onstep_comparison_established_at=None,
            user_confirmed=False,
            user_confirmed_at=None,
        )
    assert result == RaspberryTimeTrustSource.NOT_TRUSTED


# ── is_trusted ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("source", [
    RaspberryTimeTrustSource.GPSD_FIX,
    RaspberryTimeTrustSource.NTP,
    RaspberryTimeTrustSource.ONSTEP_COMPARISON,
    RaspberryTimeTrustSource.USER_CONFIRMED,
])
def test_trusted_sources(source):
    assert is_trusted(source) is True


def test_not_trusted_is_not_trusted():
    assert is_trusted(RaspberryTimeTrustSource.NOT_TRUSTED) is False


def test_service_is_trusted_static():
    assert RaspberryTimeTrustService.is_trusted(RaspberryTimeTrustSource.NTP) is True
    assert RaspberryTimeTrustService.is_trusted(RaspberryTimeTrustSource.NOT_TRUSTED) is False


# ── DeviceStateService — new M8-007 fields ───────────────────────────────────

def test_device_state_onstep_comparison_default_none():
    ds = DeviceStateService()
    assert ds.get_onstep_comparison_established_at() is None


def test_device_state_set_onstep_comparison_established():
    ds = DeviceStateService()
    before = _time.monotonic()
    ds.set_onstep_comparison_established()
    after = _time.monotonic()
    ts = ds.get_onstep_comparison_established_at()
    assert ts is not None
    assert before <= ts <= after


def test_device_state_user_time_confirmed_at_default_none():
    ds = DeviceStateService()
    assert ds.get_user_time_confirmed_at() is None


def test_device_state_set_user_confirmed_records_timestamp():
    ds = DeviceStateService()
    before = _time.monotonic()
    ds.set_user_time_confirmed(True)
    after = _time.monotonic()
    ts = ds.get_user_time_confirmed_at()
    assert ts is not None
    assert before <= ts <= after


def test_device_state_clear_user_confirmed_clears_timestamp():
    ds = DeviceStateService()
    ds.set_user_time_confirmed(True)
    ds.set_user_time_confirmed(False)
    assert ds.is_user_time_confirmed() is False
    assert ds.get_user_time_confirmed_at() is None


# ── gate_inputs_from_device_state integration ─────────────────────────────────

def _mock_ds_open() -> MagicMock:
    ds = MagicMock(spec=DeviceStateService)
    ds.is_started.return_value = True
    ds.get_mount_state.return_value = MountObservedState(
        state=MountState.UNPARKED, ra=5.5, dec=-5.0,
        polled_at=_time.monotonic(), error=None,
    )
    ds.get_time_location_status.return_value = TimeLocationStatus.VERIFIED
    ds.is_user_time_confirmed.return_value = False
    ds.get_onstep_comparison_established_at.return_value = None
    ds.get_user_time_confirmed_at.return_value = None
    return ds


def test_gate_inputs_trusted_when_ntp_via_raspberry_trust_svc():
    ds = _mock_ds_open()
    svc = _svc()
    with patch(_NTP_PATH, return_value=True):
        inputs = gate_inputs_from_device_state(ds, raspberry_trust_svc=svc)
    assert inputs["raspberry_time_trust"] == "TRUSTED"
    assert inputs["raspberry_trust_source"] == "NTP"


def test_gate_inputs_not_trusted_when_no_source():
    ds = _mock_ds_open()
    svc = _svc()
    with patch(_NTP_PATH, return_value=False):
        inputs = gate_inputs_from_device_state(ds, raspberry_trust_svc=svc)
    assert inputs["raspberry_time_trust"] == "NOT_TRUSTED"
    assert inputs["raspberry_trust_source"] == "NOT_TRUSTED"


def test_gate_inputs_trusted_via_onstep_comparison():
    ds = _mock_ds_open()
    ds.get_onstep_comparison_established_at.return_value = _time.monotonic()
    svc = _svc()
    with patch(_NTP_PATH, return_value=False):
        inputs = gate_inputs_from_device_state(ds, raspberry_trust_svc=svc)
    assert inputs["raspberry_time_trust"] == "TRUSTED"
    assert inputs["raspberry_trust_source"] == "ONSTEP_COMPARISON"


def test_gate_inputs_trusted_via_user_confirmed():
    ds = _mock_ds_open()
    ds.is_user_time_confirmed.return_value = True
    ds.get_user_time_confirmed_at.return_value = _time.monotonic()
    svc = _svc()
    with patch(_NTP_PATH, return_value=False):
        inputs = gate_inputs_from_device_state(ds, raspberry_trust_svc=svc)
    assert inputs["raspberry_time_trust"] == "TRUSTED"
    assert inputs["raspberry_trust_source"] == "USER_CONFIRMED"


def test_gate_inputs_stub_when_no_services():
    ds = _mock_ds_open()
    inputs = gate_inputs_from_device_state(ds)
    assert inputs["raspberry_time_trust"] == "TRUSTED"
    assert inputs["raspberry_trust_source"] == "STUB"


def test_gate_inputs_raspberry_trust_svc_overrides_master_source_svc():
    """When both services provided, raspberry_trust_svc takes precedence for trust."""
    from smart_telescope.services.master_source import MasterSourceService
    ds = _mock_ds_open()
    raspberry_svc = _svc()
    master_svc = MasterSourceService(gpsd=None)
    with patch(_NTP_PATH, return_value=False):
        with patch("smart_telescope.services.master_source._check_ntp_sync", return_value=False):
            inputs = gate_inputs_from_device_state(
                ds,
                master_source_svc=master_svc,
                raspberry_trust_svc=raspberry_svc,
            )
    assert inputs["raspberry_time_trust"] == "NOT_TRUSTED"
    assert inputs["raspberry_trust_source"] == "NOT_TRUSTED"
    assert inputs["master_time_source"] == "FALLBACK"
