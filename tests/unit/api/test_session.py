"""Unit tests for POST /api/session/connect."""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.ports.mount import MountPort

client = TestClient(app)


# ── fixtures ──────────────────────────────────────────────────────────────────


def _mock_camera(connect_ok: bool = True, connect_raises: Exception | None = None) -> MagicMock:
    m = MagicMock(spec=CameraPort)
    if connect_raises:
        m.connect.side_effect = connect_raises
    else:
        m.connect.return_value = connect_ok
    return m


def _mock_mount(connect_ok: bool = True, connect_raises: Exception | None = None) -> MagicMock:
    m = MagicMock(spec=MountPort)
    if connect_raises:
        m.connect.side_effect = connect_raises
    else:
        m.connect.return_value = connect_ok
    return m


def _mock_focuser(connect_ok: bool = True, connect_raises: Exception | None = None) -> MagicMock:
    m = MagicMock(spec=FocuserPort)
    if connect_raises:
        m.connect.side_effect = connect_raises
    else:
        m.connect.return_value = connect_ok
    return m


def _inject(
    camera: MagicMock | None = None,
    mount: MagicMock | None = None,
    focuser: MagicMock | None = None,
) -> None:
    if camera is not None:
        app.dependency_overrides[deps.get_camera] = lambda: camera
    if mount is not None:
        app.dependency_overrides[deps.get_mount] = lambda: mount
    if focuser is not None:
        app.dependency_overrides[deps.get_focuser] = lambda: focuser


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


# ── happy path ────────────────────────────────────────────────────────────────


class TestAllConnected:
    def test_returns_200(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        r = client.post("/api/session/connect")
        assert r.status_code == 200

    def test_all_devices_ok(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["camera"]["status"] == "ok"
        assert body["mount"]["status"] == "ok"
        assert body["focuser"]["status"] == "ok"

    def test_ok_result_has_no_error_field(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["camera"].get("error") is None
        assert body["camera"].get("action") is None

    def test_connect_called_once_per_device(self) -> None:
        cam, mnt, foc = _mock_camera(), _mock_mount(), _mock_focuser()
        _inject(cam, mnt, foc)
        client.post("/api/session/connect")
        cam.connect.assert_called_once()
        mnt.connect.assert_called_once()
        foc.connect.assert_called_once()


# ── camera failure ────────────────────────────────────────────────────────────


class TestCameraFailure:
    def test_camera_error_status(self) -> None:
        _inject(_mock_camera(connect_ok=False), _mock_mount(), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["camera"]["status"] == "error"

    def test_camera_error_has_message(self) -> None:
        _inject(_mock_camera(connect_ok=False), _mock_mount(), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["camera"]["error"]

    def test_camera_error_has_action(self) -> None:
        _inject(_mock_camera(connect_ok=False), _mock_mount(), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["camera"]["action"]

    def test_other_devices_still_ok_when_camera_fails(self) -> None:
        _inject(_mock_camera(connect_ok=False), _mock_mount(), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["mount"]["status"] == "ok"
        assert body["focuser"]["status"] == "ok"

    def test_camera_exception_reported_as_error(self) -> None:
        _inject(
            _mock_camera(connect_raises=RuntimeError("port busy")),
            _mock_mount(),
            _mock_focuser(),
        )
        body = client.post("/api/session/connect").json()
        assert body["camera"]["status"] == "error"
        assert "port busy" in body["camera"]["error"]


# ── mount failure ─────────────────────────────────────────────────────────────


class TestMountFailure:
    def test_mount_error_status(self) -> None:
        _inject(_mock_camera(), _mock_mount(connect_ok=False), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["mount"]["status"] == "error"

    def test_mount_error_has_action(self) -> None:
        _inject(_mock_camera(), _mock_mount(connect_ok=False), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["mount"]["action"]

    def test_other_devices_still_ok_when_mount_fails(self) -> None:
        _inject(_mock_camera(), _mock_mount(connect_ok=False), _mock_focuser())
        body = client.post("/api/session/connect").json()
        assert body["camera"]["status"] == "ok"
        assert body["focuser"]["status"] == "ok"

    def test_mount_exception_reported_as_error(self) -> None:
        _inject(
            _mock_camera(),
            _mock_mount(connect_raises=OSError("no such device")),
            _mock_focuser(),
        )
        body = client.post("/api/session/connect").json()
        assert body["mount"]["status"] == "error"
        assert "no such device" in body["mount"]["error"]


# ── focuser failure ───────────────────────────────────────────────────────────


class TestFocuserFailure:
    def test_focuser_error_status(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser(connect_ok=False))
        body = client.post("/api/session/connect").json()
        assert body["focuser"]["status"] == "error"

    def test_focuser_error_has_action(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser(connect_ok=False))
        body = client.post("/api/session/connect").json()
        assert body["focuser"]["action"]

    def test_focuser_exception_reported_as_error(self) -> None:
        _inject(
            _mock_camera(),
            _mock_mount(),
            _mock_focuser(connect_raises=RuntimeError("timeout")),
        )
        body = client.post("/api/session/connect").json()
        assert body["focuser"]["status"] == "error"
        assert "timeout" in body["focuser"]["error"]


# ── all fail ──────────────────────────────────────────────────────────────────


class TestAllFail:
    def test_all_error_statuses(self) -> None:
        _inject(
            _mock_camera(connect_ok=False),
            _mock_mount(connect_ok=False),
            _mock_focuser(connect_ok=False),
        )
        body = client.post("/api/session/connect").json()
        assert body["camera"]["status"] == "error"
        assert body["mount"]["status"] == "error"
        assert body["focuser"]["status"] == "error"

    def test_still_returns_200_on_all_fail(self) -> None:
        _inject(
            _mock_camera(connect_ok=False),
            _mock_mount(connect_ok=False),
            _mock_focuser(connect_ok=False),
        )
        r = client.post("/api/session/connect")
        assert r.status_code == 200
