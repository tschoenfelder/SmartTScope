"""Unit tests for POST /api/emergency_stop."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps, session as session_module
from smart_telescope.app import app
from smart_telescope.ports.mount import MountPort

client = TestClient(app)


def _mock_mount() -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.stop.return_value = None
    return m


def _inject_mount(mount: MagicMock) -> None:
    app.dependency_overrides[deps.get_mount] = lambda: mount


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    session_module._reset_session()
    yield
    app.dependency_overrides.clear()
    deps.reset()
    session_module._reset_session()


# ── always responds ────────────────────────────────────────────────────────────


class TestEmergencyStopAlwaysResponds:
    def test_returns_200_when_idle(self) -> None:
        _inject_mount(_mock_mount())
        assert client.post("/api/emergency_stop").status_code == 200

    def test_returns_200_when_mount_stop_raises(self) -> None:
        m = _mock_mount()
        m.stop.side_effect = RuntimeError("serial timeout")
        _inject_mount(m)
        assert client.post("/api/emergency_stop").status_code == 200

    def test_response_has_mount_stopped_field(self) -> None:
        _inject_mount(_mock_mount())
        body = client.post("/api/emergency_stop").json()
        assert "mount_stopped" in body

    def test_response_has_session_stopped_field(self) -> None:
        _inject_mount(_mock_mount())
        body = client.post("/api/emergency_stop").json()
        assert "session_stopped" in body


# ── mount stop ────────────────────────────────────────────────────────────────


class TestMountStop:
    def test_mount_stop_called(self) -> None:
        m = _mock_mount()
        _inject_mount(m)
        client.post("/api/emergency_stop")
        m.stop.assert_called_once()

    def test_mount_stopped_true_on_success(self) -> None:
        _inject_mount(_mock_mount())
        body = client.post("/api/emergency_stop").json()
        assert body["mount_stopped"] is True

    def test_mount_stopped_false_when_raises(self) -> None:
        m = _mock_mount()
        m.stop.side_effect = RuntimeError("serial timeout")
        _inject_mount(m)
        body = client.post("/api/emergency_stop").json()
        assert body["mount_stopped"] is False


# ── session stop ──────────────────────────────────────────────────────────────


class TestSessionStop:
    def test_session_stopped_false_when_no_session(self) -> None:
        _inject_mount(_mock_mount())
        body = client.post("/api/emergency_stop").json()
        assert body["session_stopped"] is False

    def test_session_stopped_true_when_runner_active(self) -> None:
        _inject_mount(_mock_mount())
        mock_runner = MagicMock()
        with patch("smart_telescope.api.emergency.get_active_runner", return_value=mock_runner):
            body = client.post("/api/emergency_stop").json()
        assert body["session_stopped"] is True

    def test_runner_stop_called_when_active(self) -> None:
        _inject_mount(_mock_mount())
        mock_runner = MagicMock()
        with patch("smart_telescope.api.emergency.get_active_runner", return_value=mock_runner):
            client.post("/api/emergency_stop")
        mock_runner.stop.assert_called_once()

    def test_session_stop_attempted_even_if_mount_stop_raises(self) -> None:
        m = _mock_mount()
        m.stop.side_effect = RuntimeError("serial timeout")
        _inject_mount(m)
        mock_runner = MagicMock()
        with patch("smart_telescope.api.emergency.get_active_runner", return_value=mock_runner):
            body = client.post("/api/emergency_stop").json()
        mock_runner.stop.assert_called_once()
        assert body["session_stopped"] is True

    def test_session_stopped_false_when_runner_stop_raises(self) -> None:
        _inject_mount(_mock_mount())
        mock_runner = MagicMock()
        mock_runner.stop.side_effect = RuntimeError("oops")
        with patch("smart_telescope.api.emergency.get_active_runner", return_value=mock_runner):
            body = client.post("/api/emergency_stop").json()
        assert body["session_stopped"] is False
