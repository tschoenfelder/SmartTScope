"""Unit tests for GET /api/stage1/time-location (M8-010 / REQ-API-004)."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps, session as session_module
from smart_telescope.app import app
from smart_telescope.domain.raspberry_time_trust import RaspberryTimeTrustSource
from smart_telescope.domain.time_location_status import TimeLocationStatus
from smart_telescope.services.device_state import DeviceStateService

client = TestClient(app)

_NTP_PATH = "smart_telescope.services.raspberry_time_trust._check_ntp_sync"


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    session_module._reset_session()
    yield
    app.dependency_overrides.clear()
    deps.reset()
    session_module._reset_session()


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_device_state(
    started: bool = True,
    tl_status: TimeLocationStatus = TimeLocationStatus.UNKNOWN,
    sync: dict | None = None,
    verification_at: float | None = None,
    push_at: float | None = None,
    user_confirmed: bool = False,
    user_confirmed_at: float | None = None,
    onstep_comparison_at: float | None = None,
) -> MagicMock:
    ds = MagicMock(spec=DeviceStateService)
    ds.is_started.return_value = started
    ds.get_mount_state.return_value = None
    ds.get_time_location_status.return_value = tl_status
    ds.get_last_sync_status.return_value = sync
    ds.get_last_verification_at.return_value = verification_at
    ds.get_last_push_at.return_value = push_at
    ds.is_user_time_confirmed.return_value = user_confirmed
    ds.get_user_time_confirmed_at.return_value = user_confirmed_at
    ds.get_onstep_comparison_established_at.return_value = onstep_comparison_at
    return ds


def _inject_trusted_raspberry_svc() -> None:
    mock_svc = MagicMock()
    mock_svc.evaluate.return_value = RaspberryTimeTrustSource.NTP
    mock_svc.is_trusted.return_value = True
    app.dependency_overrides[deps.get_raspberry_trust_service] = lambda: mock_svc


def _inject(ds: MagicMock) -> None:
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    _inject_trusted_raspberry_svc()


def _get() -> dict:
    return client.get("/api/stage1/time-location").json()


# ── basic response shape ──────────────────────────────────────────────────────

class TestShape:
    def test_returns_200(self) -> None:
        _inject(_mock_device_state())
        assert client.get("/api/stage1/time-location").status_code == 200

    def test_required_fields_present(self) -> None:
        _inject(_mock_device_state())
        body = _get()
        for field in (
            "onstep_time_location",
            "raspberry_time_trust",
            "raspberry_trust_source",
            "master_source",
            "adapter_connection_state",
            "adapter_health_state",
            "time_delta_s",
            "time_tolerance_s",
            "time_ok",
            "onstep_lat",
            "onstep_lon",
            "master_lat",
            "master_lon",
            "location_delta_m",
            "location_tolerance_m",
            "location_ok",
            "last_verification_at_utc",
            "last_push_at_utc",
            "available_actions",
        ):
            assert field in body, f"missing field: {field}"

    def test_onstep_time_location_state_unknown_when_not_verified(self) -> None:
        _inject(_mock_device_state(tl_status=TimeLocationStatus.UNKNOWN))
        assert _get()["onstep_time_location"] == "UNKNOWN"

    def test_onstep_time_location_state_verified(self) -> None:
        _inject(_mock_device_state(tl_status=TimeLocationStatus.VERIFIED))
        assert _get()["onstep_time_location"] == "VERIFIED"

    def test_onstep_time_location_state_unverified(self) -> None:
        _inject(_mock_device_state(tl_status=TimeLocationStatus.UNVERIFIED))
        assert _get()["onstep_time_location"] == "UNVERIFIED"


# ── sync status cache ─────────────────────────────────────────────────────────

class TestSyncStatusCache:
    def test_delta_none_when_no_sync_checked(self) -> None:
        _inject(_mock_device_state(sync=None))
        body = _get()
        assert body["time_delta_s"] is None
        assert body["location_delta_m"] is None
        assert body["time_ok"] is None
        assert body["location_ok"] is None

    def test_delta_from_cached_sync_status(self) -> None:
        sync = {
            "time_delta_s": 3.5, "time_ok": True, "time_tolerance_s": 10.0,
            "location_delta_m": 42.1, "location_ok": True, "location_tolerance_m": 100.0,
            "onstep_lat": 50.336, "onstep_lon": 8.533,
            "onstep_time_local": "2026-06-27T22:00:00",
            "master_time_local": "2026-06-27T22:00:03",
        }
        _inject(_mock_device_state(sync=sync))
        body = _get()
        assert body["time_delta_s"] == pytest.approx(3.5)
        assert body["location_delta_m"] == pytest.approx(42.1)
        assert body["time_ok"] is True
        assert body["location_ok"] is True
        assert body["onstep_lat"] == pytest.approx(50.336)
        assert body["onstep_time_local"] == "2026-06-27T22:00:00"
        assert body["master_time_local"] == "2026-06-27T22:00:03"


# ── tolerances come from config ───────────────────────────────────────────────

class TestTolerances:
    def test_time_tolerance_s_is_configured_value(self) -> None:
        _inject(_mock_device_state())
        from smart_telescope import config
        body = _get()
        assert body["time_tolerance_s"] == pytest.approx(config.ONSTEP_TIME_TOLERANCE_S)

    def test_location_tolerance_m_is_configured_value(self) -> None:
        _inject(_mock_device_state())
        from smart_telescope import config
        body = _get()
        assert body["location_tolerance_m"] == pytest.approx(config.ONSTEP_LOCATION_TOLERANCE_M)


# ── available actions ─────────────────────────────────────────────────────────

class TestAvailableActions:
    def test_rerun_always_present(self) -> None:
        _inject(_mock_device_state(started=False))
        assert "rerun_check" in _get()["available_actions"]

    def test_push_present_when_adapter_open(self) -> None:
        _inject(_mock_device_state(started=True))
        assert "push_to_onstep" in _get()["available_actions"]

    def test_push_absent_when_adapter_closed(self) -> None:
        _inject(_mock_device_state(started=False))
        assert "push_to_onstep" not in _get()["available_actions"]

    def test_confirm_time_present_when_not_trusted(self) -> None:
        ds = _mock_device_state()
        app.dependency_overrides[deps.get_device_state] = lambda: ds
        mock_svc = MagicMock()
        mock_svc.evaluate.return_value = RaspberryTimeTrustSource.NOT_TRUSTED
        mock_svc.is_trusted.return_value = False
        app.dependency_overrides[deps.get_raspberry_trust_service] = lambda: mock_svc
        assert "confirm_raspberry_time" in _get()["available_actions"]

    def test_confirm_time_absent_when_trusted(self) -> None:
        _inject(_mock_device_state())  # injects NTP trust
        assert "confirm_raspberry_time" not in _get()["available_actions"]


# ── timestamps ────────────────────────────────────────────────────────────────

class TestTimestamps:
    def test_last_verification_null_when_never_verified(self) -> None:
        _inject(_mock_device_state(verification_at=None))
        assert _get()["last_verification_at_utc"] is None

    def test_last_verification_iso_utc_when_set(self) -> None:
        ts = time.time()
        _inject(_mock_device_state(verification_at=ts))
        utc_str = _get()["last_verification_at_utc"]
        assert utc_str is not None
        assert utc_str.endswith("Z")

    def test_last_push_null_when_never_pushed(self) -> None:
        _inject(_mock_device_state(push_at=None))
        assert _get()["last_push_at_utc"] is None

    def test_last_push_iso_utc_when_set(self) -> None:
        ts = time.time()
        _inject(_mock_device_state(push_at=ts))
        utc_str = _get()["last_push_at_utc"]
        assert utc_str is not None
        assert utc_str.endswith("Z")


# ── master / observer location ────────────────────────────────────────────────

class TestMasterLocation:
    def test_master_lat_lon_from_config(self) -> None:
        from smart_telescope import config
        _inject(_mock_device_state())
        body = _get()
        assert body["master_lat"] == pytest.approx(config.OBSERVER_LAT)
        assert body["master_lon"] == pytest.approx(config.OBSERVER_LON)
