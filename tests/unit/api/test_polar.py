"""Unit tests for POST /api/polar/measure — AT_HOME gate + camera_role resolution.

Hardware feedback (2026-07-19/20): a polar-alignment "HOME solve" ran with the
mount not actually at home (the safety checklist's mount_at_home field is a
pure client-side checkbox, never cross-checked against real mount state), and
it was unclear which camera had been used (camera_index only, no role
resolution/reporting like api/solver.py already has). These tests cover the
new server-side AT_HOME hard gate and camera_role support in polar_measure().
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps, polar
from smart_telescope.app import app
from smart_telescope.ports.mount import MountPort, MountState
from smart_telescope.services.device_state import DeviceStateService, MountObservedState

client = TestClient(app)

_patches: list = []


def _mock_mount() -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.get_state.return_value = MountState.AT_HOME
    m.unpark.return_value = True
    return m


def _mock_device_state(state: MountState | None) -> MagicMock:
    """DeviceStateService mock — state=None simulates "no poll has run yet"."""
    m = MagicMock(spec=DeviceStateService)
    m.get_mount_state.return_value = (
        MountObservedState(state=state, ra=None, dec=None, polled_at=time.monotonic())
        if state is not None else None
    )
    return m


def _confirm_checklist() -> None:
    body = {
        "mount_at_home": True, "telescope_points_north": True, "clutches_locked": True,
        "camera_connected": True, "focus_ok": True, "cables_slack": True,
        "no_collision_risk": True, "mount_stable": True, "alt_az_screws_accessible": True,
    }
    r = client.post("/api/polar/checklist", json=body)
    assert r.json()["confirmed"] is True


def _inject(mount: MagicMock, device_state: MagicMock) -> None:
    app.dependency_overrides[deps.get_mount] = lambda: mount
    app.dependency_overrides[deps.get_device_state] = lambda: device_state
    app.dependency_overrides[deps.get_solver] = lambda: MagicMock()
    # Isolate these tests to polar_measure()'s own gating/resolution logic —
    # the actual 3-position workflow is covered by test_polar_workflow.py.
    p = patch.object(polar, "_run_workflow_loop", new=AsyncMock(return_value=None))
    p.start()
    _patches.append(p)


@pytest.fixture(autouse=True)
def _reset() -> None:
    polar._state = polar._PolarState()
    polar._checklist_confirmed = False
    polar._task = None
    yield
    app.dependency_overrides.clear()
    for p in _patches:
        p.stop()
    _patches.clear()
    polar._state = polar._PolarState()
    polar._checklist_confirmed = False
    polar._task = None


class TestAtHomeGate:
    def test_blocked_when_mount_not_at_home(self) -> None:
        _confirm_checklist()
        _inject(_mock_mount(), _mock_device_state(MountState.TRACKING))
        r = client.post("/api/polar/measure", json={})
        body = r.json()
        assert body["step"] == "error"
        assert "HOME" in body["error_msg"]
        assert body["running"] is False

    def test_blocked_when_no_poll_has_run_yet(self) -> None:
        _confirm_checklist()
        _inject(_mock_mount(), _mock_device_state(None))
        r = client.post("/api/polar/measure", json={})
        body = r.json()
        assert body["step"] == "error"
        assert body["running"] is False

    def test_proceeds_when_mount_at_home(self) -> None:
        _confirm_checklist()
        _inject(_mock_mount(), _mock_device_state(MountState.AT_HOME))
        r = client.post("/api/polar/measure", json={})
        body = r.json()
        assert body["step"] != "error"
        assert body["running"] is True

    def test_blocked_before_checklist_confirmed_takes_precedence(self) -> None:
        # Checklist gate still runs first — AT_HOME gate must not mask it.
        _inject(_mock_mount(), _mock_device_state(MountState.AT_HOME))
        r = client.post("/api/polar/measure", json={})
        body = r.json()
        assert "checklist" in body["error_msg"].lower()


class TestCameraRoleResolution:
    def test_unknown_camera_role_returns_422(self) -> None:
        _confirm_checklist()
        _inject(_mock_mount(), _mock_device_state(MountState.AT_HOME))
        reg = MagicMock()
        reg.by_camera_role.return_value = None
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/polar/measure", json={"camera_role": "nope"})
        assert r.status_code == 422

    def test_camera_role_resolves_index_and_is_reported_back(self) -> None:
        _confirm_checklist()
        _inject(_mock_mount(), _mock_device_state(MountState.AT_HOME))
        train = MagicMock()
        train.camera_index = 2
        train.camera_role = "guide"
        reg = MagicMock()
        reg.by_camera_role.return_value = train
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/polar/measure", json={"camera_role": "guide"})
        body = r.json()
        assert body["cam_index"] == 2
        assert body["cam_role"] == "guide"

    def test_no_camera_role_falls_back_to_index_and_reports_resolved_role(self) -> None:
        _confirm_checklist()
        _inject(_mock_mount(), _mock_device_state(MountState.AT_HOME))
        train = MagicMock()
        train.camera_index = 0
        train.camera_role = "main"
        reg = MagicMock()
        reg.by_camera_index.return_value = train
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/polar/measure", json={"camera_index": 0})
        body = r.json()
        assert body["cam_index"] == 0
        assert body["cam_role"] == "main"
