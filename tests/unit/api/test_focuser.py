"""Unit tests for focuser API endpoints — no hardware required."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from smart_telescope.app import app
from smart_telescope.api import deps
from smart_telescope.ports.focuser import FocuserPort

client = TestClient(app)


def _mock_focuser(position: int = 1000, moving: bool = False) -> MagicMock:
    f = MagicMock(spec=FocuserPort)
    f.get_position.return_value = position
    f.is_moving.return_value = moving
    return f


@pytest.fixture(autouse=True)
def _reset_deps() -> None:
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


def _inject(focuser: MagicMock) -> None:
    app.dependency_overrides[deps.get_focuser] = lambda: focuser


# ── GET /api/focuser/status ────────────────────────────────────────────────────


class TestFocuserStatus:
    def test_returns_200(self) -> None:
        _inject(_mock_focuser())
        assert client.get("/api/focuser/status").status_code == 200

    def test_position_field(self) -> None:
        _inject(_mock_focuser(position=2500))
        data = client.get("/api/focuser/status").json()
        assert data["position"] == 2500

    def test_moving_false_when_stopped(self) -> None:
        _inject(_mock_focuser(moving=False))
        assert client.get("/api/focuser/status").json()["moving"] is False

    def test_moving_true_when_in_motion(self) -> None:
        _inject(_mock_focuser(moving=True))
        assert client.get("/api/focuser/status").json()["moving"] is True

    def test_calls_get_position_and_is_moving(self) -> None:
        f = _mock_focuser()
        _inject(f)
        client.get("/api/focuser/status")
        f.get_position.assert_called_once()
        f.is_moving.assert_called_once()


# ── POST /api/focuser/move ─────────────────────────────────────────────────────


class TestFocuserMove:
    def test_returns_200(self) -> None:
        _inject(_mock_focuser())
        assert client.post("/api/focuser/move", json={"position": 3000}).status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_focuser())
        assert client.post("/api/focuser/move", json={"position": 3000}).json() == {"ok": True}

    def test_calls_move_with_position(self) -> None:
        f = _mock_focuser()
        _inject(f)
        client.post("/api/focuser/move", json={"position": 3000})
        f.move.assert_called_once_with(3000)

    def test_move_to_zero(self) -> None:
        f = _mock_focuser()
        _inject(f)
        client.post("/api/focuser/move", json={"position": 0})
        f.move.assert_called_once_with(0)

    def test_returns_422_when_body_missing(self) -> None:
        _inject(_mock_focuser())
        assert client.post("/api/focuser/move", json={}).status_code == 422


# ── POST /api/focuser/nudge ────────────────────────────────────────────────────


class TestFocuserNudge:
    def test_returns_200(self) -> None:
        _inject(_mock_focuser(position=1000))
        assert client.post("/api/focuser/nudge", json={"delta": 100}).status_code == 200

    def test_returns_target_position(self) -> None:
        _inject(_mock_focuser(position=1000))
        data = client.post("/api/focuser/nudge", json={"delta": 100}).json()
        assert data["target"] == 1100

    def test_negative_nudge(self) -> None:
        _inject(_mock_focuser(position=1000))
        data = client.post("/api/focuser/nudge", json={"delta": -200}).json()
        assert data["target"] == 800

    def test_calls_move_with_computed_target(self) -> None:
        f = _mock_focuser(position=500)
        _inject(f)
        client.post("/api/focuser/nudge", json={"delta": 50})
        f.move.assert_called_once_with(550)

    def test_returns_422_when_body_missing(self) -> None:
        _inject(_mock_focuser())
        assert client.post("/api/focuser/nudge", json={}).status_code == 422


# ── POST /api/focuser/stop ─────────────────────────────────────────────────────


class TestFocuserStop:
    def test_returns_200(self) -> None:
        _inject(_mock_focuser())
        assert client.post("/api/focuser/stop").status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_focuser())
        assert client.post("/api/focuser/stop").json() == {"ok": True}

    def test_calls_stop_on_focuser(self) -> None:
        f = _mock_focuser()
        _inject(f)
        client.post("/api/focuser/stop")
        f.stop.assert_called_once()
