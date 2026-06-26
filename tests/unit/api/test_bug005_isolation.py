"""BUG-005: crash isolation — camera failure must not block mount/focuser control.

Acceptance criteria:
  - preview/camera failure does not affect mount/focuser control
  - STOP always completes within the agreed timeout (< 1 s, POD-002)

These tests verify the isolation invariants without real hardware:
  1. STOP bypasses the coordinator lock (mount.stop() called directly)
  2. STOP still works after a session runner fails with a camera exception
  3. Mount goto is available again after a crashed session releases its resources
  4. Job manager resources are released on session thread exception
  5. Focuser stop is unaffected by a failed camera session
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps, session as session_module
from smart_telescope.app import app
from smart_telescope.domain.session import SessionLog
from smart_telescope.domain.states import SessionState
from smart_telescope.domain.time_location_status import TimeLocationStatus
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.ports.mount import MountPort, MountState
from smart_telescope.runtime import get_runtime
from smart_telescope.services.device_state import DeviceStateService, MountObservedState
from smart_telescope.workflow.runner import WorkflowError

client = TestClient(app)


# ── helpers ───────────────────────────────────────────────────────────────────

def _mock_camera() -> MagicMock:
    m = MagicMock(spec=CameraPort)
    m.connect.return_value = True
    return m


def _mock_mount() -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.connect.return_value = True
    m.stop.return_value = True
    m.is_slewing.return_value = False
    m.goto.return_value = True
    m.get_state.return_value = MountState.UNPARKED
    m.get_position.return_value = None
    return m


def _mock_focuser() -> MagicMock:
    m = MagicMock(spec=FocuserPort)
    m.connect.return_value = True
    m.stop.return_value = True
    return m


def _inject(
    camera: MagicMock | None = None,
    mount:  MagicMock | None = None,
    focuser: MagicMock | None = None,
) -> None:
    if camera is not None:
        app.dependency_overrides[deps.get_camera] = lambda: camera
    if mount is not None:
        app.dependency_overrides[deps.get_mount] = lambda: mount
    if focuser is not None:
        app.dependency_overrides[deps.get_focuser] = lambda: focuser


def _solar_ok() -> object:
    return patch("smart_telescope.api.session.is_solar_target", return_value=(False, 120.0))


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    session_module._reset_session()
    yield
    app.dependency_overrides.clear()
    deps.reset()
    session_module._reset_session()


def _crashing_runner(error_msg: str = "camera hardware fault") -> MagicMock:
    """A mock VerticalSliceRunner whose run() raises WorkflowError immediately."""
    m = MagicMock()
    m.current_log = None

    def _run(**kwargs: object) -> SessionLog:
        raise WorkflowError("connect", error_msg)

    m.run.side_effect = _run
    return m


def _wait_for_session_done(timeout: float = 2.0) -> bool:
    """Poll until the session job resource is released (session thread finished)."""
    deadline = time.monotonic() + timeout
    rt = get_runtime()
    while time.monotonic() < deadline:
        if not rt.job_manager.is_resource_held("mount"):
            return True
        time.sleep(0.02)
    return False


# ── 1. STOP bypasses coordinator lock ─────────────────────────────────────────

class TestStopBypassesCoordinatorLock:
    """mount.stop() is called directly in the STOP endpoint; no coordinator involved."""

    def test_stop_returns_200_while_coordinator_is_locked(self) -> None:
        mount = _mock_mount()
        _inject(mount=mount)
        coordinator = get_runtime().coordinator
        unlock = threading.Event()

        def hold_lock() -> None:
            with coordinator.mount_command():
                unlock.wait(timeout=3.0)

        t = threading.Thread(target=hold_lock, daemon=True)
        t.start()
        time.sleep(0.05)  # give the background thread time to acquire the lock

        r = client.post("/api/mount/stop")

        unlock.set()
        t.join(timeout=2.0)

        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_stop_calls_mount_stop_exactly_once(self) -> None:
        mount = _mock_mount()
        _inject(mount=mount)
        r = client.post("/api/mount/stop")
        assert r.status_code == 200
        mount.stop.assert_called_once()

    def test_stop_succeeds_when_coordinator_is_idle(self) -> None:
        mount = _mock_mount()
        _inject(mount=mount)
        assert client.post("/api/mount/stop").status_code == 200


# ── 2. Camera exception → job resources released ──────────────────────────────

class TestSessionCrashReleasesResources:
    """When the runner thread dies with an exception, job resources must be released."""

    def test_mount_resource_released_after_camera_crash(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        crash_runner = _crashing_runner()
        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", return_value=crash_runner),
            _solar_ok(),
        ):
            r = client.post("/api/session/run?target=M42")
        assert r.status_code == 202

        released = _wait_for_session_done(timeout=2.0)
        assert released, "job_manager still holds 'mount' resource after session crash"

    def test_focuser_resource_released_after_camera_crash(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        crash_runner = _crashing_runner()
        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", return_value=crash_runner),
            _solar_ok(),
        ):
            client.post("/api/session/run?target=M42")

        released = _wait_for_session_done(timeout=2.0)
        assert released
        rt = get_runtime()
        assert not rt.job_manager.is_resource_held("focuser"), \
            "job_manager still holds 'focuser' resource after session crash"

    def test_camera_resource_released_after_camera_crash(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        crash_runner = _crashing_runner()
        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", return_value=crash_runner),
            _solar_ok(),
        ):
            client.post("/api/session/run?target=M42")

        _wait_for_session_done(timeout=2.0)
        rt = get_runtime()
        assert not rt.job_manager.is_resource_held("camera:0"), \
            "job_manager still holds camera resource after session crash"


# ── 3. STOP still works after session crash ───────────────────────────────────

class TestStopWorksAfterSessionCrash:
    """mount.stop() and focuser.stop() must succeed after a crashed session."""

    def test_mount_stop_returns_200_after_session_failure(self) -> None:
        mount = _mock_mount()
        _inject(_mock_camera(), mount, _mock_focuser())
        crash_runner = _crashing_runner()
        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", return_value=crash_runner),
            _solar_ok(),
        ):
            client.post("/api/session/run?target=M42")

        _wait_for_session_done(timeout=2.0)
        r = client.post("/api/mount/stop")
        assert r.status_code == 200
        mount.stop.assert_called()

    def test_focuser_stop_returns_200_after_session_failure(self) -> None:
        focuser = _mock_focuser()
        _inject(_mock_camera(), _mock_mount(), focuser)
        crash_runner = _crashing_runner()
        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", return_value=crash_runner),
            _solar_ok(),
        ):
            client.post("/api/session/run?target=M42")

        _wait_for_session_done(timeout=2.0)
        r = client.post("/api/focuser/stop")
        assert r.status_code == 200


# ── 4. Mount goto available after crash ───────────────────────────────────────

class TestMountCommandsAfterSessionCrash:
    """After crash, the coordinator lock must be free and goto must be accepted."""

    def test_mount_goto_not_409_after_session_crash(self) -> None:
        mount = _mock_mount()
        _inject(_mock_camera(), mount, _mock_focuser())
        crash_runner = _crashing_runner()
        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", return_value=crash_runner),
            _solar_ok(),
        ):
            client.post("/api/session/run?target=M42")

        _wait_for_session_done(timeout=2.0)

        # Provide VERIFIED time/location status and open adapter so gate passes.
        # This test verifies the coordinator lock is released, not the gate guards.
        ds = MagicMock(spec=DeviceStateService)
        ds.is_started.return_value = True
        ds.get_mount_state.return_value = MountObservedState(
            state=MountState.UNPARKED, ra=5.5, dec=-5.4, polled_at=0.0
        )
        ds.get_time_location_status.return_value = TimeLocationStatus.VERIFIED
        ds.get_last_command.return_value = (None, None, None)
        ds.get_watchdog_warning.return_value = None
        app.dependency_overrides[deps.get_device_state] = lambda: ds

        # Goto should not be rejected with 409 (resource conflict) after the crash
        with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
            r = client.post("/api/mount/goto", json={"ra": 5.5, "dec": -5.4})
        assert r.status_code != 409, (
            f"Goto returned 409 after session crash — mount resource still locked. "
            f"Response: {r.json()}"
        )

    def test_new_session_not_409_after_crashed_session(self) -> None:
        _inject(_mock_camera(), _mock_mount(), _mock_focuser())
        crash_runner = _crashing_runner()
        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", return_value=crash_runner),
            _solar_ok(),
        ):
            client.post("/api/session/run?target=M42")

        _wait_for_session_done(timeout=2.0)

        # A new session should be accepted (resource conflict cleared)
        fast_runner = MagicMock()
        fast_log = SessionLog(
            session_id="test-session",
            target_name="M42",
            target_ra=5.5,
            target_dec=-5.4,
            optical_config="c8_native",
            started_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        )
        fast_log.state = SessionState.IDLE
        fast_runner.run.return_value = fast_log
        fast_runner.current_log = fast_log
        with (
            patch("smart_telescope.api.session.VerticalSliceRunner", return_value=fast_runner),
            _solar_ok(),
        ):
            r = client.post("/api/session/run?target=M42")
        assert r.status_code == 202, (
            f"New session returned {r.status_code} after crash — resources not released. "
            f"Response: {r.json()}"
        )
