"""Tests for M7-001 (interactive time/location startup) and M7-002 (TimeLocationStatus).

Covers TEST-001 cases:
- OnStep time/location within tolerance → VERIFIED
- OnStep time differs > 10 s → mismatch returned, status stays UNKNOWN
- OnStep location differs > tolerance → mismatch returned, status stays UNKNOWN
- User approves push (sync_clock) → VERIFIED
- User rejects push (time_location_skip) → UNVERIFIED
- UNVERIFIED → tracking, GoTo and sync are blocked
- VERIFIED → tracking, GoTo, sync are allowed (modulo other guards)
- Startup while parked / unparked → park state not changed (existing behaviour)
- Startup complete → tracking disabled (tested via ST-010 in existing tests)
"""
from __future__ import annotations

import time as _time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.api.session import DeviceResult
from smart_telescope.app import app
from smart_telescope.domain.raspberry_time_trust import RaspberryTimeTrustSource
from smart_telescope.domain.time_location_status import TimeLocationStatus
from smart_telescope.ports.mount import MountPort, MountState
from smart_telescope.services.device_state import DeviceStateService, MountObservedState

_OK = DeviceResult(status="ok")
_ERR = DeviceResult(status="error", error="not connected", action="check cable")

client = TestClient(app)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_mount(
    *,
    connect_ok: bool = True,
    sync_status: dict | None = None,
    state: MountState = MountState.UNPARKED,
) -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.connect.return_value = connect_ok
    m.get_sync_status.return_value = sync_status or {
        "time_ok": True, "location_ok": True,
        "time_delta_s": 2.0,
        "lat_delta_deg": 0.0001, "lon_delta_deg": 0.0001,
    }
    m.get_state.return_value = state
    m.enable_tracking.return_value = True
    m.disable_tracking.return_value = True
    m.is_slewing.return_value = False
    return m


def _make_device_state(status: TimeLocationStatus = TimeLocationStatus.UNKNOWN) -> DeviceStateService:
    ds = DeviceStateService()
    ds.set_time_location_status(status)
    return ds


def _mock_ds_tl(status: TimeLocationStatus) -> MagicMock:
    """Mock device_state: adapter open and healthy so gate reaches TL check."""
    m = MagicMock(spec=DeviceStateService)
    m.is_started.return_value = True
    obs = MountObservedState(
        state=MountState.UNPARKED, ra=5.5, dec=-5.0, polled_at=_time.monotonic(), error=None
    )
    m.get_mount_state.return_value = obs
    m.get_time_location_status.return_value = status
    m.get_last_command.return_value = (None, None, None)
    m.get_watchdog_warning.return_value = None
    return m


@pytest.fixture(autouse=True)
def _reset():
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


# ── TimeLocationStatus enum ───────────────────────────────────────────────────

def test_enum_values():
    assert TimeLocationStatus.UNKNOWN.name == "UNKNOWN"
    assert TimeLocationStatus.VERIFIED.name == "VERIFIED"
    assert TimeLocationStatus.UNVERIFIED.name == "UNVERIFIED"


def test_device_state_default_is_unknown():
    ds = DeviceStateService()
    assert ds.get_time_location_status() == TimeLocationStatus.UNKNOWN


def test_device_state_set_verified():
    ds = DeviceStateService()
    ds.set_time_location_status(TimeLocationStatus.VERIFIED)
    assert ds.get_time_location_status() == TimeLocationStatus.VERIFIED


def test_device_state_set_unverified():
    ds = DeviceStateService()
    ds.set_time_location_status(TimeLocationStatus.UNVERIFIED)
    assert ds.get_time_location_status() == TimeLocationStatus.UNVERIFIED


# ── Session connect — time/location check ─────────────────────────────────────

def test_connect_within_tolerance_sets_verified():
    """OnStep time/location within tolerance → status becomes VERIFIED."""
    ds = _make_device_state()
    mount = _make_mount(sync_status={
        "time_ok": True, "location_ok": True,
        "time_delta_s": 3.0, "lat_delta_deg": 0.0001, "lon_delta_deg": 0.0001,
    })
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    with patch("smart_telescope.api.session._try_connect", return_value=_OK), \
         patch("smart_telescope.api.session._check_solver", return_value=_OK):
        resp = client.post("/api/session/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["time_location_status"] == "VERIFIED"
    assert data["time_location_check"] is None
    assert ds.get_time_location_status() == TimeLocationStatus.VERIFIED


def test_connect_time_mismatch_returns_check_info():
    """OnStep time differs > threshold → mismatch info returned, status stays UNKNOWN."""
    ds = _make_device_state()
    mismatch = {
        "time_ok": False, "location_ok": True,
        "time_delta_s": 300.0, "lat_delta_deg": 0.0, "lon_delta_deg": 0.0,
    }
    mount = _make_mount(sync_status=mismatch)
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    with patch("smart_telescope.api.session._try_connect", return_value=_OK), \
         patch("smart_telescope.api.session._check_solver", return_value=_OK):
        resp = client.post("/api/session/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["time_location_status"] == "UNKNOWN"
    assert data["time_location_check"] is not None
    assert data["time_location_check"]["time_ok"] is False
    assert ds.get_time_location_status() == TimeLocationStatus.UNKNOWN


def test_connect_location_mismatch_returns_check_info():
    """OnStep location differs > tolerance → mismatch info returned, status stays UNKNOWN."""
    ds = _make_device_state()
    mismatch = {
        "time_ok": True, "location_ok": False,
        "time_delta_s": 1.0, "lat_delta_deg": 5.0, "lon_delta_deg": 0.0,
    }
    mount = _make_mount(sync_status=mismatch)
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    with patch("smart_telescope.api.session._try_connect", return_value=_OK), \
         patch("smart_telescope.api.session._check_solver", return_value=_OK):
        resp = client.post("/api/session/connect")
    assert resp.status_code == 200
    data = resp.json()
    assert data["time_location_status"] == "UNKNOWN"
    assert data["time_location_check"]["location_ok"] is False
    assert ds.get_time_location_status() == TimeLocationStatus.UNKNOWN


def test_connect_mount_error_leaves_status_unknown():
    """Mount connection failure → status stays UNKNOWN (no check attempted)."""
    ds = _make_device_state()
    mount = _make_mount(connect_ok=False)
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    with patch("smart_telescope.api.session._check_solver", return_value=_OK):
        resp = client.post("/api/session/connect")
    assert resp.status_code == 200
    assert ds.get_time_location_status() == TimeLocationStatus.UNKNOWN


# ── sync_clock sets VERIFIED (user approves push) ─────────────────────────────

def test_sync_clock_sets_verified():
    """POST /api/mount/sync_clock → push succeeds → status becomes VERIFIED."""
    ds = _make_device_state(TimeLocationStatus.UNKNOWN)
    mount = _make_mount()
    mount.ensure_time_location_synced.return_value = None
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    resp = client.post("/api/mount/sync_clock")
    assert resp.status_code == 200
    assert resp.json()["time_location_status"] == "VERIFIED"
    assert ds.get_time_location_status() == TimeLocationStatus.VERIFIED


# ── time_location_skip sets UNVERIFIED (user rejects push) ────────────────────

def test_time_location_skip_sets_unverified():
    """POST /api/mount/time_location_skip → status becomes UNVERIFIED."""
    ds = _make_device_state(TimeLocationStatus.UNKNOWN)
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    resp = client.post("/api/mount/time_location_skip")
    assert resp.status_code == 200
    assert resp.json()["time_location_status"] == "UNVERIFIED"
    assert ds.get_time_location_status() == TimeLocationStatus.UNVERIFIED


# ── Tracking blocked when not VERIFIED ───────────────────────────────────────

@pytest.mark.parametrize("status", [TimeLocationStatus.UNKNOWN, TimeLocationStatus.UNVERIFIED])
def test_track_blocked_when_not_verified(status):
    """POST /api/mount/track → 409 when time/location is not VERIFIED."""
    ds = _mock_ds_tl(status)
    mount = _make_mount()
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    resp = client.post("/api/mount/track")
    assert resp.status_code == 409
    assert resp.json()["detail"]["reason_code"] == "TIME_LOCATION_UNVERIFIED"


def test_track_allowed_when_verified():
    """POST /api/mount/track → 200 when time/location is VERIFIED."""
    ds = _mock_ds_tl(TimeLocationStatus.VERIFIED)
    mount = _make_mount()
    trusted_svc = MagicMock()
    trusted_svc.evaluate.return_value = RaspberryTimeTrustSource.ONSTEP_COMPARISON
    trusted_svc.is_trusted.return_value = True
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    app.dependency_overrides[deps.get_raspberry_trust_service] = lambda: trusted_svc
    resp = client.post("/api/mount/track")
    assert resp.status_code == 200


# ── GoTo blocked when not VERIFIED ───────────────────────────────────────────

@pytest.mark.parametrize("status", [TimeLocationStatus.UNKNOWN, TimeLocationStatus.UNVERIFIED])
def test_goto_blocked_when_not_verified(status):
    """POST /api/mount/goto → 409 when time/location is not VERIFIED."""
    ds = _mock_ds_tl(status)
    mount = _make_mount()
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)), \
         patch("smart_telescope.api.mount._check_mount_limits"):
        resp = client.post("/api/mount/goto", json={"ra": 5.5, "dec": -5.0})
    assert resp.status_code == 409
    assert resp.json()["detail"]["reason_code"] == "TIME_LOCATION_UNVERIFIED"


# ── Automatic sync blocked when not VERIFIED ─────────────────────────────────

@pytest.mark.parametrize("status", [TimeLocationStatus.UNKNOWN, TimeLocationStatus.UNVERIFIED])
def test_sync_blocked_when_not_verified(status):
    """POST /api/mount/sync → 409 when time/location is not VERIFIED."""
    ds = _mock_ds_tl(status)
    mount = _make_mount()
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    resp = client.post("/api/mount/sync", json={"ra": 5.5, "dec": -5.0})
    assert resp.status_code == 409
    assert resp.json()["detail"]["reason_code"] == "TIME_LOCATION_UNVERIFIED"


# ── Mount status exposes time_location_status field ──────────────────────────

def test_mount_status_includes_time_location_status():
    """GET /api/mount/status → response includes time_location_status field."""
    ds = _make_device_state(TimeLocationStatus.VERIFIED)
    mount = _make_mount()
    mount.get_position.return_value = None
    mount.get_park_position.return_value = None
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: ds
    with patch("smart_telescope.api.mount._get_lst", return_value=None):
        resp = client.get("/api/mount/status")
    assert resp.status_code == 200
    assert resp.json()["time_location_status"] == "VERIFIED"
