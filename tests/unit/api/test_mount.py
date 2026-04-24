"""Unit tests for mount API endpoints — no hardware required."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from smart_telescope.app import app
from smart_telescope.api import deps
from smart_telescope.ports.mount import MountPort, MountPosition, MountState

client = TestClient(app)


def _mock_mount(
    state: MountState = MountState.TRACKING,
    ra: float = 5.58,
    dec: float = -5.39,
    unpark_ok: bool = True,
    track_ok: bool = True,
    goto_ok: bool = True,
) -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.get_state.return_value = state
    m.get_position.return_value = MountPosition(ra=ra, dec=dec)
    m.unpark.return_value = unpark_ok
    m.enable_tracking.return_value = track_ok
    m.goto.return_value = goto_ok
    return m


@pytest.fixture(autouse=True)
def _reset_deps() -> None:
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


def _inject(mount: MagicMock) -> None:
    app.dependency_overrides[deps.get_mount] = lambda: mount


# ── GET /api/mount/status ──────────────────────────────────────────────────────


class TestMountStatus:
    def test_returns_200(self) -> None:
        _inject(_mock_mount())
        assert client.get("/api/mount/status").status_code == 200

    def test_state_field_is_lowercase_enum_name(self) -> None:
        _inject(_mock_mount(state=MountState.TRACKING))
        data = client.get("/api/mount/status").json()
        assert data["state"] == "tracking"

    def test_ra_and_dec_present_when_not_parked(self) -> None:
        _inject(_mock_mount(state=MountState.TRACKING, ra=5.58, dec=-5.39))
        data = client.get("/api/mount/status").json()
        assert data["ra"] == pytest.approx(5.58, abs=0.01)
        assert data["dec"] == pytest.approx(-5.39, abs=0.01)

    def test_ra_dec_none_when_parked(self) -> None:
        m = _mock_mount(state=MountState.PARKED)
        _inject(m)
        data = client.get("/api/mount/status").json()
        assert data["ra"] is None
        assert data["dec"] is None

    def test_ra_dec_none_when_unknown(self) -> None:
        m = _mock_mount(state=MountState.UNKNOWN)
        _inject(m)
        data = client.get("/api/mount/status").json()
        assert data["ra"] is None
        assert data["dec"] is None

    def test_unparked_state(self) -> None:
        _inject(_mock_mount(state=MountState.UNPARKED))
        data = client.get("/api/mount/status").json()
        assert data["state"] == "unparked"

    def test_slewing_state(self) -> None:
        _inject(_mock_mount(state=MountState.SLEWING))
        data = client.get("/api/mount/status").json()
        assert data["state"] == "slewing"


# ── POST /api/mount/unpark ─────────────────────────────────────────────────────


class TestMountUnpark:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(unpark_ok=True))
        assert client.post("/api/mount/unpark").status_code == 200

    def test_returns_ok_true_on_success(self) -> None:
        _inject(_mock_mount(unpark_ok=True))
        assert client.post("/api/mount/unpark").json() == {"ok": True}

    def test_returns_500_when_unpark_fails(self) -> None:
        _inject(_mock_mount(unpark_ok=False))
        assert client.post("/api/mount/unpark").status_code == 500

    def test_calls_unpark_on_mount(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/unpark")
        m.unpark.assert_called_once()


# ── POST /api/mount/track ──────────────────────────────────────────────────────


class TestMountTrack:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(track_ok=True))
        assert client.post("/api/mount/track").status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount(track_ok=True))
        assert client.post("/api/mount/track").json() == {"ok": True}

    def test_returns_500_when_tracking_fails(self) -> None:
        _inject(_mock_mount(track_ok=False))
        assert client.post("/api/mount/track").status_code == 500

    def test_calls_enable_tracking(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/track")
        m.enable_tracking.assert_called_once()


# ── POST /api/mount/stop ───────────────────────────────────────────────────────


class TestMountStop:
    def test_returns_200(self) -> None:
        _inject(_mock_mount())
        assert client.post("/api/mount/stop").status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount())
        assert client.post("/api/mount/stop").json() == {"ok": True}

    def test_calls_stop_on_mount(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/stop")
        m.stop.assert_called_once()


# ── POST /api/mount/goto ───────────────────────────────────────────────────────


class TestMountGoto:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(goto_ok=True))
        assert client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39}).status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount(goto_ok=True))
        data = client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39}).json()
        assert data == {"ok": True}

    def test_returns_500_when_goto_fails(self) -> None:
        _inject(_mock_mount(goto_ok=False))
        assert client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39}).status_code == 500

    def test_calls_goto_with_ra_dec(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39})
        m.goto.assert_called_once_with(pytest.approx(5.58, abs=0.01), pytest.approx(-5.39, abs=0.01))

    def test_returns_422_when_body_missing(self) -> None:
        _inject(_mock_mount())
        assert client.post("/api/mount/goto", json={}).status_code == 422
