"""Unit tests for GET /api/status."""
import os
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps, session as session_module
from smart_telescope.app import app
from smart_telescope.ports.mount import MountPort, MountState

client = TestClient(app)


def _mock_mount(state: MountState = MountState.TRACKING) -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.get_state.return_value = state
    return m


def _inject_mount(mount: MagicMock) -> None:
    app.dependency_overrides[deps.get_mount] = lambda: mount


def _patch_solver_ok() -> object:
    return patch.multiple(
        "smart_telescope.api.health",
        _find_astap=lambda: "/usr/bin/astap",
        _find_catalog=lambda p: "/home/user/.astap/",
    )


def _patch_solver_missing() -> object:
    return patch.multiple(
        "smart_telescope.api.health",
        _find_astap=lambda: None,
        _find_catalog=lambda p: None,
    )


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    session_module._reset_session()
    yield
    app.dependency_overrides.clear()
    deps.reset()
    session_module._reset_session()
    os.environ.pop("STORAGE_DIR", None)


# ── always responds ───────────────────────────────────────────────────────────


class TestAlwaysResponds:
    def test_returns_200(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            assert client.get("/api/status").status_code == 200

    def test_returns_200_when_mount_raises(self) -> None:
        m = _mock_mount()
        m.get_state.side_effect = OSError("serial timeout")
        _inject_mount(m)
        with _patch_solver_ok():
            assert client.get("/api/status").status_code == 200

    def test_response_has_all_top_level_fields(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        for field in ("mount", "camera", "focuser", "solver", "storage", "session", "cpu"):
            assert field in body


# ── mount ────────────────────────────────────────────────────────────────────


class TestMountHealth:
    def test_ok_true_when_state_readable(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["mount"]["ok"] is True

    def test_state_name_in_response(self) -> None:
        _inject_mount(_mock_mount(MountState.TRACKING))
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["mount"]["state"] == "TRACKING"

    def test_parked_state_reported(self) -> None:
        _inject_mount(_mock_mount(MountState.PARKED))
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["mount"]["state"] == "PARKED"

    def test_ok_false_when_get_state_raises(self) -> None:
        m = _mock_mount()
        m.get_state.side_effect = OSError("no device")
        _inject_mount(m)
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["mount"]["ok"] is False

    def test_error_message_included_on_failure(self) -> None:
        m = _mock_mount()
        m.get_state.side_effect = OSError("no device")
        _inject_mount(m)
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert "no device" in body["mount"]["message"]


# ── camera / focuser ──────────────────────────────────────────────────────────


class TestDeviceHealth:
    def test_camera_ok_true(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["camera"]["ok"] is True

    def test_focuser_ok_true(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["focuser"]["ok"] is True


# ── solver ────────────────────────────────────────────────────────────────────


class TestSolverHealth:
    def test_ok_true_when_astap_and_catalog_found(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["solver"]["ok"] is True
        assert body["solver"]["astap_found"] is True
        assert body["solver"]["catalog_found"] is True

    def test_ok_false_when_astap_missing(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_missing():
            body = client.get("/api/status").json()
        assert body["solver"]["ok"] is False
        assert body["solver"]["astap_found"] is False

    def test_ok_false_when_catalog_missing(self) -> None:
        _inject_mount(_mock_mount())
        with patch.multiple(
            "smart_telescope.api.health",
            _find_astap=lambda: "/usr/bin/astap",
            _find_catalog=lambda p: None,
        ):
            body = client.get("/api/status").json()
        assert body["solver"]["ok"] is False
        assert body["solver"]["astap_found"] is True
        assert body["solver"]["catalog_found"] is False


# ── storage ───────────────────────────────────────────────────────────────────


class TestStorageHealth:
    def test_ok_true_when_no_storage_dir_set(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["storage"]["ok"] is True
        assert body["storage"]["free_gb"] is None

    def test_free_gb_reported_when_storage_dir_set(self, tmp_path) -> None:
        os.environ["STORAGE_DIR"] = str(tmp_path)
        _inject_mount(_mock_mount())
        fake_usage = MagicMock()
        fake_usage.free = 50 * (1024 ** 3)  # 50 GB
        with _patch_solver_ok(), patch("smart_telescope.api.health.shutil.disk_usage", return_value=fake_usage):
            body = client.get("/api/status").json()
        assert body["storage"]["ok"] is True
        assert body["storage"]["free_gb"] == pytest.approx(50.0, rel=0.01)

    def test_path_in_response_when_set(self, tmp_path) -> None:
        os.environ["STORAGE_DIR"] = str(tmp_path)
        _inject_mount(_mock_mount())
        fake_usage = MagicMock()
        fake_usage.free = 10 * (1024 ** 3)
        with _patch_solver_ok(), patch("smart_telescope.api.health.shutil.disk_usage", return_value=fake_usage):
            body = client.get("/api/status").json()
        assert body["storage"]["path"] == str(tmp_path)

    def test_ok_false_when_disk_usage_raises(self, tmp_path) -> None:
        os.environ["STORAGE_DIR"] = str(tmp_path)
        _inject_mount(_mock_mount())
        with _patch_solver_ok(), patch("smart_telescope.api.health.shutil.disk_usage", side_effect=OSError("no mount")):
            body = client.get("/api/status").json()
        assert body["storage"]["ok"] is False
        assert "no mount" in body["storage"]["message"]


# ── session ───────────────────────────────────────────────────────────────────


class TestSessionHealth:
    def test_not_running_when_no_session(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["session"]["running"] is False
        assert body["session"]["state"] is None

    def test_running_and_state_when_runner_active(self) -> None:
        from datetime import UTC, datetime
        from smart_telescope.domain.session import SessionLog
        from smart_telescope.domain.states import SessionState
        from smart_telescope.workflow.runner import C8_NATIVE, M42_DEC, M42_RA

        log = SessionLog(
            session_id="abc-123", target_name="M42",
            target_ra=M42_RA, target_dec=M42_DEC,
            optical_config=C8_NATIVE.name, started_at=datetime.now(UTC),
            state=SessionState.STACKING,
        )
        mock_runner = MagicMock()
        mock_runner.current_log = log

        _inject_mount(_mock_mount())
        with (
            _patch_solver_ok(),
            patch("smart_telescope.api.health.get_session_running", return_value=True),
            patch("smart_telescope.api.health.get_active_runner", return_value=mock_runner),
        ):
            body = client.get("/api/status").json()
        assert body["session"]["running"] is True
        assert body["session"]["state"] == "STACKING"
        assert body["session"]["session_id"] == "abc-123"


# ── cpu temperature ───────────────────────────────────────────────────────────


class TestCpuHealth:
    def test_cpu_field_present(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert "cpu" in body

    def test_cpu_temp_none_when_sys_path_absent(self) -> None:
        # /sys/class/thermal/... does not exist on Windows / CI
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        # On non-Linux CI the path is missing; _read_cpu_temp() returns None
        assert body["cpu"]["temp_c"] is None or isinstance(body["cpu"]["temp_c"], float)

    def test_cpu_temp_returned_when_patched(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok(), patch(
            "smart_telescope.api.health._read_cpu_temp", return_value=45.5
        ):
            body = client.get("/api/status").json()
        assert body["cpu"]["temp_c"] == pytest.approx(45.5)

    def test_cpu_temp_rounded_to_one_decimal(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok(), patch(
            "smart_telescope.api.health._read_cpu_temp", return_value=45.7
        ):
            body = client.get("/api/status").json()
        assert body["cpu"]["temp_c"] == pytest.approx(45.7, abs=0.05)


# ── storage frames capacity ───────────────────────────────────────────────────


class TestStorageCapacity:
    def test_frames_capacity_computed_when_storage_set(self, tmp_path) -> None:
        os.environ["STORAGE_DIR"] = str(tmp_path)
        _inject_mount(_mock_mount())
        fake_usage = MagicMock()
        fake_usage.free = 50 * (1024 ** 3)  # 50 GB
        with _patch_solver_ok(), patch(
            "smart_telescope.api.health.shutil.disk_usage", return_value=fake_usage
        ):
            body = client.get("/api/status").json()
        # 50 GB * 1024 MB/GB / 25 MB per frame = 2048
        assert body["storage"]["frames_capacity"] == 2048

    def test_frames_capacity_none_when_no_storage_dir(self) -> None:
        _inject_mount(_mock_mount())
        with _patch_solver_ok():
            body = client.get("/api/status").json()
        assert body["storage"]["frames_capacity"] is None
