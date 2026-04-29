"""Unit tests for POST /api/session/connect, /run, /status, /stop."""
import threading
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps, session as session_module
from smart_telescope.app import app
from smart_telescope.domain.session import SessionLog
from smart_telescope.domain.states import SessionState
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.ports.mount import MountPort
from smart_telescope.workflow.runner import C8_NATIVE, M42_DEC, M42_RA


def _patch_solver_ok(astap: str = "/usr/bin/astap", catalog: Path | None = None):
    """Patch solver checks to report ready — avoids ASTAP installation dependency."""
    if catalog is None:
        catalog = Path("/tmp/astap_catalog")
    return patch.multiple(
        "smart_telescope.api.session",
        _find_astap=lambda: astap,
        _find_catalog=lambda exe: catalog,
    )


def _patch_solver_missing() -> object:
    return patch.multiple(
        "smart_telescope.api.session",
        _find_astap=lambda: None,
        _find_catalog=lambda exe: None,
    )

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
    session_module._reset_session()
    yield
    app.dependency_overrides.clear()
    deps.reset()
    session_module._reset_session()


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


# ── solver validation ─────────────────────────────────────────────────────────


class TestSolverValidation:
    def test_solver_field_present_in_response(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_solver_ok():
            body = client.post("/api/session/connect").json()
        assert "solver" in body

    def test_solver_ok_when_astap_and_catalog_found(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_solver_ok():
            body = client.post("/api/session/connect").json()
        assert body["solver"]["status"] == "ok"

    def test_solver_error_when_astap_missing(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_solver_missing():
            body = client.post("/api/session/connect").json()
        assert body["solver"]["status"] == "error"

    def test_solver_error_has_message_when_astap_missing(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_solver_missing():
            body = client.post("/api/session/connect").json()
        assert body["solver"]["error"]

    def test_solver_error_has_action_when_astap_missing(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_solver_missing():
            body = client.post("/api/session/connect").json()
        assert body["solver"]["action"]

    def test_solver_error_when_catalog_missing(self, tmp_path: Path) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with patch.multiple(
            "smart_telescope.api.session",
            _find_astap=lambda: "/usr/bin/astap",
            _find_catalog=lambda exe: None,
        ):
            body = client.post("/api/session/connect").json()
        assert body["solver"]["status"] == "error"
        assert body["solver"]["action"]

    def test_devices_still_checked_when_solver_missing(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_solver_missing():
            body = client.post("/api/session/connect").json()
        assert body["camera"]["status"] == "ok"
        assert body["mount"]["status"] == "ok"
        assert body["focuser"]["status"] == "ok"


# ── POST /api/session/run ─────────────────────────────────────────────────────


def _make_fast_log(session_id: str | None = None) -> SessionLog:
    return SessionLog(
        session_id=session_id or "test-sid",
        target_name="M42", target_ra=M42_RA, target_dec=M42_DEC,
        optical_config=C8_NATIVE.name, started_at=datetime.now(UTC),
        state=SessionState.SAVED,
    )


def _patch_runner_fast(log: SessionLog | None = None) -> object:
    """Patch VerticalSliceRunner so run() returns immediately.

    Propagates the session_id kwarg into the log so status responses
    return the same ID as the /run response.
    """
    mock_log = log or _make_fast_log()
    mock_runner = MagicMock()

    def _run(**kwargs: object) -> SessionLog:
        sid = kwargs.get("session_id")
        if sid:
            mock_log.session_id = str(sid)
        mock_runner.current_log = mock_log
        return mock_log

    mock_runner.run.side_effect = _run
    mock_runner.current_log = mock_log
    return patch("smart_telescope.api.session.VerticalSliceRunner", return_value=mock_runner)


class TestSessionRun:
    def test_returns_202(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast():
            r = client.post("/api/session/run")
        assert r.status_code == 202

    def test_response_has_session_id(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast():
            body = client.post("/api/session/run").json()
        assert "session_id" in body
        assert body["session_id"]

    def test_response_state_is_idle(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast():
            body = client.post("/api/session/run").json()
        assert body["state"] == "IDLE"

    def test_session_id_is_uuid_shaped(self) -> None:
        import re
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast():
            body = client.post("/api/session/run").json()
        assert re.fullmatch(r"[0-9a-f-]{36}", body["session_id"])

    def test_409_when_session_already_running(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        gate = threading.Event()
        blocking_runner = MagicMock()
        blocking_runner.current_log = None
        blocking_runner.run.side_effect = lambda **kw: gate.wait()
        with patch("smart_telescope.api.session.VerticalSliceRunner", return_value=blocking_runner):
            client.post("/api/session/run")
            r = client.post("/api/session/run")
        gate.set()
        assert r.status_code == 409

    def test_runner_receives_generated_session_id(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        mock_runner = MagicMock()
        mock_runner.current_log = _make_fast_log()
        mock_runner.run.return_value = mock_runner.current_log
        with patch("smart_telescope.api.session.VerticalSliceRunner", return_value=mock_runner):
            body = client.post("/api/session/run").json()
        mock_runner.run.assert_called_once_with(session_id=body["session_id"])


# ── GET /api/session/status ───────────────────────────────────────────────────


class TestSessionStatus:
    def test_returns_200(self) -> None:
        assert client.get("/api/session/status").status_code == 200

    def test_running_false_when_no_session(self) -> None:
        body = client.get("/api/session/status").json()
        assert body["running"] is False

    def test_state_none_when_no_session(self) -> None:
        body = client.get("/api/session/status").json()
        assert body["state"] is None

    def test_returns_session_id_after_run(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast():
            sid = client.post("/api/session/run").json()["session_id"]
        body = client.get("/api/session/status").json()
        assert body["session_id"] == sid

    def test_state_reflects_completed_session(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast():
            client.post("/api/session/run")
        body = client.get("/api/session/status").json()
        assert body["state"] == "SAVED"

    def test_frames_integrated_in_status(self) -> None:
        log = _make_fast_log()
        log.frames_integrated = 7
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(log):
            client.post("/api/session/run")
        body = client.get("/api/session/status").json()
        assert body["frames_integrated"] == 7

    def test_warnings_in_status(self) -> None:
        log = _make_fast_log()
        log.warnings = ["centering degraded"]
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(log):
            client.post("/api/session/run")
        body = client.get("/api/session/status").json()
        assert "centering degraded" in body["warnings"]

    def test_failure_fields_in_status(self) -> None:
        log = _make_fast_log()
        log.failure_stage = "align"
        log.failure_reason = "no stars"
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(log):
            client.post("/api/session/run")
        body = client.get("/api/session/status").json()
        assert body["failure_stage"] == "align"
        assert body["failure_reason"] == "no stars"


# ── POST /api/session/stop ────────────────────────────────────────────────────


class TestSessionStop:
    def test_404_when_no_session(self) -> None:
        assert client.post("/api/session/stop").status_code == 404

    def test_204_when_session_active(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        gate = threading.Event()
        mock_runner = MagicMock()
        mock_runner.current_log = None
        mock_runner.run.side_effect = lambda **kw: gate.wait()
        with patch("smart_telescope.api.session.VerticalSliceRunner", return_value=mock_runner):
            client.post("/api/session/run")
            r = client.post("/api/session/stop")
        gate.set()
        assert r.status_code == 204

    def test_stop_calls_runner_stop(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        gate = threading.Event()
        mock_runner = MagicMock()
        mock_runner.current_log = None
        mock_runner.run.side_effect = lambda **kw: gate.wait()
        with patch("smart_telescope.api.session.VerticalSliceRunner", return_value=mock_runner):
            client.post("/api/session/run")
            client.post("/api/session/stop")
        gate.set()
        mock_runner.stop.assert_called_once()


# ── Target + profile selection ─────────────────────────────────────────────────


def _solar_patch(blocked: bool = False, sep: float = 120.0) -> object:
    return patch("smart_telescope.api.session.is_solar_target", return_value=(blocked, sep))


class TestTargetSelection:
    def test_default_target_m42_succeeds(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(), _solar_patch():
            r = client.post("/api/session/run")
        assert r.status_code == 202

    def test_valid_catalog_target_succeeds(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(), _solar_patch():
            r = client.post("/api/session/run?target=M31")
        assert r.status_code == 202

    def test_unknown_target_returns_422(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        r = client.post("/api/session/run?target=M999")
        assert r.status_code == 422
        assert "M999" in r.json()["detail"]

    def test_target_case_insensitive(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(), _solar_patch():
            r = client.post("/api/session/run?target=m51")
        assert r.status_code == 202

    def test_solar_target_returns_403(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _solar_patch(blocked=True, sep=1.5):
            r = client.post("/api/session/run?target=M42")
        assert r.status_code == 403

    def test_solar_confirm_bypasses_403(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(), _solar_patch(blocked=True, sep=1.5):
            r = client.post("/api/session/run?target=M42&confirm_solar=true")
        assert r.status_code == 202

    def test_runner_constructed_with_target_coords(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        constructed: list = []

        def capture_runner(*a: object, **kw: object) -> MagicMock:
            constructed.append(kw)
            m = MagicMock()
            m.current_log = _make_fast_log()
            m.run.return_value = m.current_log
            return m

        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", side_effect=capture_runner),
            _solar_patch(),
        ):
            client.post("/api/session/run?target=M31")
        assert constructed[0]["target_name"] == "M31"
        assert constructed[0]["target_ra"] != M42_RA


class TestProfileSelection:
    def test_default_profile_c8_native(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        constructed: list = []

        def capture_runner(*a: object, **kw: object) -> MagicMock:
            constructed.append(kw)
            m = MagicMock()
            m.current_log = _make_fast_log()
            m.run.return_value = m.current_log
            return m

        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", side_effect=capture_runner),
            _solar_patch(),
        ):
            client.post("/api/session/run")
        assert constructed[0]["optical_profile"].name == "C8-native"

    def test_reducer_profile_accepted(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(), _solar_patch():
            r = client.post("/api/session/run?profile=c8_reducer")
        assert r.status_code == 202

    def test_barlow_profile_accepted(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        with _patch_runner_fast(), _solar_patch():
            r = client.post("/api/session/run?profile=c8_barlow2x")
        assert r.status_code == 202

    def test_unknown_profile_returns_422(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        r = client.post("/api/session/run?profile=c8_schmitt")
        assert r.status_code == 422
        assert "c8_schmitt" in r.json()["detail"]

    def test_runner_constructed_with_correct_profile(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        constructed: list = []

        def capture_runner(*a: object, **kw: object) -> MagicMock:
            constructed.append(kw)
            m = MagicMock()
            m.current_log = _make_fast_log()
            m.run.return_value = m.current_log
            return m

        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", side_effect=capture_runner),
            _solar_patch(),
        ):
            client.post("/api/session/run?profile=c8_reducer")
        assert constructed[0]["optical_profile"].name == "C8-reducer"
