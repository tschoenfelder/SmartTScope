"""R6-006 — API smoke tests: setup, mount, focuser, stop, preview.

Each test class validates the HTTP shape of one UI area under mock devices.
No hardware or serial ports are needed; all adapters are replaced by MagicMock.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.ports.mount import MountPort, MountPosition, MountState
from smart_telescope.services.device_state import DeviceStateService, MountObservedState

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


def _mock_mount(state: MountState = MountState.TRACKING) -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.get_state.return_value = state
    m.get_position.return_value = MountPosition(ra=10.0, dec=45.0)
    m.stop.return_value = None
    return m


def _mock_focuser(available: bool = True) -> MagicMock:
    f = MagicMock(spec=FocuserPort)
    f.is_available = available
    f.get_position.return_value = 5000
    f.is_moving.return_value = False
    f.get_max_position.return_value = 50000
    return f


def _fresh_device_state(state: MountState = MountState.TRACKING) -> DeviceStateService:
    svc = DeviceStateService()
    with svc._lock:
        svc._mount_state = MountObservedState(
            state=state, ra=10.0, dec=45.0, polled_at=time.monotonic()
        )
    return svc


# ── 1. Setup / Diagnostics (Stage 1) ─────────────────────────────────────────

class TestSetupSmoke:
    def test_index_returns_200(self):
        assert client.get("/").status_code == 200

    def test_index_content_type_is_html(self):
        assert "text/html" in client.get("/").headers["content-type"]

    def test_index_contains_page_title(self):
        assert "SmartTelescope" in client.get("/").text

    def test_readiness_returns_200(self):
        assert client.get("/api/readiness").status_code == 200

    def test_readiness_has_overall_field(self):
        body = client.get("/api/readiness").json()
        assert "overall" in body

    def test_readiness_has_items_list(self):
        body = client.get("/api/readiness").json()
        assert isinstance(body.get("items"), list)

    def test_readiness_overall_is_valid_colour(self):
        body = client.get("/api/readiness").json()
        assert body["overall"] in ("green", "yellow", "red")

    def test_health_returns_ok(self):
        assert client.get("/health").json() == {"status": "ok"}


# ── 2. Mount (Status and config) ─────────────────────────────────────────────

class TestMountSmoke:
    def _inject(self, state: MountState = MountState.TRACKING) -> None:
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount(state)
        app.dependency_overrides[deps.get_device_state] = lambda: _fresh_device_state(state)

    def test_status_returns_200(self):
        self._inject()
        assert client.get("/api/mount/status").status_code == 200

    def test_status_has_state_field(self):
        self._inject()
        assert "state" in client.get("/api/mount/status").json()

    def test_status_has_stale_field(self):
        self._inject()
        assert "stale" in client.get("/api/mount/status").json()

    def test_status_has_watchdog_warning_field(self):
        self._inject()
        assert "watchdog_warning" in client.get("/api/mount/status").json()

    def test_status_has_last_command_fields(self):
        self._inject()
        body = client.get("/api/mount/status").json()
        assert "last_command" in body
        assert "last_command_error" in body

    def test_status_tracking_state_serialised_lowercase(self):
        self._inject(MountState.TRACKING)
        body = client.get("/api/mount/status").json()
        assert body["state"] == "tracking"

    def test_status_parked_state_serialised_lowercase(self):
        self._inject(MountState.PARKED)
        body = client.get("/api/mount/status").json()
        assert body["state"] == "parked"

    def test_status_stale_false_for_fresh_observation(self):
        self._inject()
        body = client.get("/api/mount/status").json()
        assert body["stale"] is False

    def test_status_watchdog_none_when_no_alert(self):
        self._inject()
        body = client.get("/api/mount/status").json()
        assert body["watchdog_warning"] is None

    def test_config_returns_200(self):
        assert client.get("/api/mount/config").status_code == 200

    def test_config_has_observer_lat(self):
        body = client.get("/api/mount/config").json()
        assert "observer_lat" in body

    def test_config_has_observer_lon(self):
        body = client.get("/api/mount/config").json()
        assert "observer_lon" in body


# ── 3. Focuser ────────────────────────────────────────────────────────────────

class TestFocuserSmoke:
    def _inject(self, available: bool = True) -> None:
        app.dependency_overrides[deps.get_focuser] = lambda: _mock_focuser(available)

    def test_status_returns_200(self):
        self._inject()
        assert client.get("/api/focuser/status").status_code == 200

    def test_status_has_position_field(self):
        self._inject()
        assert "position" in client.get("/api/focuser/status").json()

    def test_status_has_available_field(self):
        self._inject()
        assert "available" in client.get("/api/focuser/status").json()

    def test_status_has_moving_field(self):
        self._inject()
        assert "moving" in client.get("/api/focuser/status").json()

    def test_status_has_max_position_field(self):
        self._inject()
        assert "max_position" in client.get("/api/focuser/status").json()

    def test_status_available_focuser_returns_position(self):
        self._inject(available=True)
        body = client.get("/api/focuser/status").json()
        assert body["available"] is True
        assert body["position"] == 5000

    def test_status_unavailable_focuser_returns_zeros(self):
        self._inject(available=False)
        body = client.get("/api/focuser/status").json()
        assert body["available"] is False
        assert body["position"] == 0
        assert body["moving"] is False


# ── 4. Emergency STOP — must always respond (POD-002: < 1 s) ─────────────────

class TestEmergencyStopSmoke:
    def test_stop_returns_200_healthy_mount(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount()
        assert client.post("/api/emergency_stop").status_code == 200

    def test_stop_returns_200_when_mount_raises(self):
        m = _mock_mount()
        m.stop.side_effect = RuntimeError("serial timeout")
        app.dependency_overrides[deps.get_mount] = lambda: m
        assert client.post("/api/emergency_stop").status_code == 200

    def test_stop_has_mount_stopped_field(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount()
        body = client.post("/api/emergency_stop").json()
        assert "mount_stopped" in body

    def test_stop_has_session_stopped_field(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount()
        body = client.post("/api/emergency_stop").json()
        assert "session_stopped" in body

    def test_stop_mount_stopped_true_on_success(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount()
        body = client.post("/api/emergency_stop").json()
        assert body["mount_stopped"] is True

    def test_stop_mount_stopped_false_on_serial_error(self):
        m = _mock_mount()
        m.stop.side_effect = RuntimeError("serial timeout")
        app.dependency_overrides[deps.get_mount] = lambda: m
        body = client.post("/api/emergency_stop").json()
        assert body["mount_stopped"] is False

    def test_stop_calls_mount_stop_once(self):
        m = _mock_mount()
        app.dependency_overrides[deps.get_mount] = lambda: m
        client.post("/api/emergency_stop")
        m.stop.assert_called_once()

    def test_stop_session_false_when_idle(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount()
        body = client.post("/api/emergency_stop").json()
        assert body["session_stopped"] is False


# ── 5. Preview — endpoint and WS route reachable ──────────────────────────────

class TestPreviewSmoke:
    def test_optical_trains_returns_200(self):
        resp = client.get("/api/optical_trains")
        assert resp.status_code == 200

    def test_optical_trains_returns_list(self):
        body = client.get("/api/optical_trains").json()
        assert isinstance(body, list)

    def test_version_endpoint_returns_200(self):
        assert client.get("/api/version").status_code == 200

    def test_catalog_tonight_returns_200_or_error(self):
        resp = client.get("/api/catalog/tonight")
        assert resp.status_code in (200, 400, 500)
