"""Lifecycle tests for RuntimeContext — R0-010."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.adapters.mock.camera import MockCamera
from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.ports.mount import MountState
from smart_telescope.runtime import (
    RuntimeContext,
    get_runtime,
    set_runtime,
)
from smart_telescope.services.device_state import DeviceStateService
from smart_telescope.services.hardware_coordinator import HardwareCommandCoordinator
from smart_telescope.services.job_manager import JobManager


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_ctx() -> RuntimeContext:
    """Fresh RuntimeContext backed by mock adapters (no env vars needed)."""
    ctx = RuntimeContext()
    ctx._camera  = MockCamera()
    ctx._mount   = MockMount()
    ctx._focuser = MockFocuser()
    ctx._adapters_built = True
    ctx.device_state.start(ctx._mount, poll_interval=0.05)
    return ctx


# ── init ──────────────────────────────────────────────────────────────────────

class TestRuntimeContextInit:
    def test_adapter_slots_are_none(self):
        ctx = RuntimeContext()
        assert ctx._camera   is None
        assert ctx._mount    is None
        assert ctx._focuser  is None
        assert ctx._stacker  is None
        assert ctx._storage  is None
        assert ctx._solver   is None

    def test_adapters_not_built(self):
        ctx = RuntimeContext()
        assert ctx._adapters_built is False

    def test_coordinator_is_fresh_instance(self):
        ctx = RuntimeContext()
        assert isinstance(ctx.coordinator, HardwareCommandCoordinator)

    def test_device_state_is_fresh_instance(self):
        ctx = RuntimeContext()
        assert isinstance(ctx.device_state, DeviceStateService)
        assert ctx.device_state.get_mount_state() is None

    def test_session_lock_exists(self):
        ctx = RuntimeContext()
        assert isinstance(ctx.session_lock, threading.Lock)

    def test_autogain_lock_exists(self):
        ctx = RuntimeContext()
        assert isinstance(ctx.autogain_lock, threading.Lock)

    def test_session_state_is_none(self):
        ctx = RuntimeContext()
        assert ctx.get_active_runner() is None
        assert not ctx.is_session_running()

    def test_autogain_job_is_none(self):
        ctx = RuntimeContext()
        assert ctx.get_autogain_job() is None

    def test_job_manager_is_fresh_instance(self):
        ctx = RuntimeContext()
        assert isinstance(ctx.job_manager, JobManager)
        assert ctx.job_manager.list_active() == []


# ── connect_devices ───────────────────────────────────────────────────────────

class TestConnectDevices:
    def test_mock_mode_builds_mock_adapters(self):
        ctx = RuntimeContext()
        ctx.connect_devices()
        assert isinstance(ctx._camera,  MockCamera)
        assert isinstance(ctx._mount,   MockMount)
        assert isinstance(ctx._focuser, MockFocuser)
        ctx.shutdown()

    def test_adapters_built_flag_is_set(self):
        ctx = RuntimeContext()
        ctx.connect_devices()
        assert ctx._adapters_built is True
        ctx.shutdown()

    def test_connect_devices_is_idempotent(self):
        ctx = RuntimeContext()
        ctx.connect_devices()
        cam1 = ctx._camera
        ctx.connect_devices()  # second call must not rebuild
        assert ctx._camera is cam1
        ctx.shutdown()

    def test_connect_devices_starts_device_state_polling(self):
        ctx = RuntimeContext()
        ctx.connect_devices()
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if ctx.device_state.get_mount_state() is not None:
                break
            time.sleep(0.05)
        ctx.shutdown()
        assert ctx.device_state.get_mount_state() is not None

    def test_simulator_mode_with_env_var(self, monkeypatch: pytest.MonkeyPatch, tmp_path):
        from smart_telescope.adapters.simulator.camera import SimulatorCamera
        from smart_telescope.adapters.simulator.mount import SimulatorMount
        monkeypatch.setenv("SIMULATOR_FITS_DIR", str(tmp_path))
        ctx = RuntimeContext()
        ctx.connect_devices()
        assert isinstance(ctx._camera, SimulatorCamera)
        assert isinstance(ctx._mount,  SimulatorMount)
        ctx.shutdown()


# ── shutdown ──────────────────────────────────────────────────────────────────

class TestShutdown:
    def test_shutdown_stops_device_state_polling(self):
        ctx = _make_ctx()
        assert ctx.device_state._thread is not None
        ctx.shutdown()
        assert ctx.device_state._thread is None or not ctx.device_state._thread.is_alive()

    def test_shutdown_calls_focuser_stop(self):
        ctx = RuntimeContext()
        mock_focuser = MagicMock()
        mock_mount   = MagicMock()
        mock_mount.get_state.return_value = MountState.PARKED
        ctx._focuser = mock_focuser
        ctx._mount   = mock_mount
        ctx._adapters_built = True
        ctx.shutdown()
        mock_focuser.stop.assert_called_once()

    def test_shutdown_calls_mount_stop_before_disconnect(self):
        ctx = RuntimeContext()
        call_order = []
        mock_mount = MagicMock()
        mock_mount.stop.side_effect       = lambda: call_order.append("stop")
        mock_mount.disconnect.side_effect = lambda: call_order.append("disconnect")
        mock_mount.get_state.return_value = MountState.PARKED
        ctx._mount = mock_mount
        ctx._adapters_built = True
        ctx.shutdown()
        assert call_order == ["stop", "disconnect"]

    def test_shutdown_closes_preview_cameras(self):
        ctx = _make_ctx()
        extra_cam = MagicMock()
        ctx._preview_cameras[1] = extra_cam
        ctx.shutdown()
        extra_cam.disconnect.assert_called_once()

    def test_shutdown_tolerates_stop_error(self):
        ctx = RuntimeContext()
        mock_mount = MagicMock()
        mock_mount.stop.side_effect = OSError("serial gone")
        mock_mount.get_state.return_value = MountState.PARKED
        ctx._mount = mock_mount
        ctx._adapters_built = True
        ctx.shutdown()  # must not raise
        mock_mount.disconnect.assert_called_once()


# ── reset_for_tests ───────────────────────────────────────────────────────────

class TestResetForTests:
    def test_reset_clears_all_adapters(self):
        ctx = _make_ctx()
        ctx.reset_for_tests()
        assert ctx._camera  is None
        assert ctx._mount   is None
        assert ctx._focuser is None

    def test_reset_clears_adapters_built_flag(self):
        ctx = _make_ctx()
        ctx.reset_for_tests()
        assert ctx._adapters_built is False

    def test_reset_stops_device_state_polling(self):
        ctx = _make_ctx()
        old_thread = ctx.device_state._thread
        ctx.reset_for_tests()
        if old_thread is not None:
            assert not old_thread.is_alive()

    def test_reset_installs_fresh_coordinator(self):
        ctx = _make_ctx()
        old_coord = ctx.coordinator
        ctx.reset_for_tests()
        assert ctx.coordinator is not old_coord

    def test_reset_installs_fresh_device_state(self):
        ctx = _make_ctx()
        old_ds = ctx.device_state
        ctx.reset_for_tests()
        assert ctx.device_state is not old_ds

    def test_reset_clears_session_state(self):
        ctx = RuntimeContext()
        fake_runner = MagicMock()
        fake_thread = MagicMock()
        fake_thread.is_alive.return_value = True
        ctx.set_session(fake_runner, fake_thread)
        ctx.reset_for_tests()
        assert ctx.get_active_runner() is None
        assert not ctx.is_session_running()

    def test_reset_clears_autogain_job(self):
        ctx = RuntimeContext()
        ctx.set_autogain_job(object())
        ctx.reset_for_tests()
        assert ctx.get_autogain_job() is None

    def test_reset_allows_new_adapters_to_be_built(self):
        ctx = RuntimeContext()
        ctx.connect_devices()
        cam1 = ctx._camera
        ctx.reset_for_tests()
        ctx.connect_devices()
        assert ctx._camera is not cam1
        ctx.shutdown()

    def test_reset_installs_fresh_job_manager(self):
        ctx = _make_ctx()
        old_jm = ctx.job_manager
        ctx.reset_for_tests()
        assert ctx.job_manager is not old_jm
        assert isinstance(ctx.job_manager, JobManager)


# ── module-level singleton ────────────────────────────────────────────────────

class TestModuleSingleton:
    @pytest.fixture(autouse=True)
    def _restore_runtime(self):
        from smart_telescope import runtime as _rt_module
        original = _rt_module._runtime
        yield
        _rt_module._runtime = original

    def test_get_runtime_returns_a_context(self):
        from smart_telescope import runtime as _rt_module
        _rt_module._runtime = None
        rt = get_runtime()
        assert isinstance(rt, RuntimeContext)

    def test_get_runtime_is_idempotent(self):
        from smart_telescope import runtime as _rt_module
        _rt_module._runtime = None
        assert get_runtime() is get_runtime()

    def test_set_runtime_replaces_singleton(self):
        ctx = RuntimeContext()
        set_runtime(ctx)
        assert get_runtime() is ctx

    def test_set_runtime_then_get_runtime(self):
        ctx1 = RuntimeContext()
        ctx2 = RuntimeContext()
        set_runtime(ctx1)
        assert get_runtime() is ctx1
        set_runtime(ctx2)
        assert get_runtime() is ctx2


# ── session state management ──────────────────────────────────────────────────

class TestSessionState:
    def test_is_session_running_false_when_no_thread(self):
        ctx = RuntimeContext()
        assert not ctx.is_session_running()

    def test_set_session_stores_runner_and_thread(self):
        ctx = RuntimeContext()
        runner = MagicMock()
        thread = MagicMock()
        thread.is_alive.return_value = True
        ctx.set_session(runner, thread)
        assert ctx.get_active_runner() is runner
        assert ctx.is_session_running()

    def test_is_session_running_false_after_thread_dies(self):
        ctx = RuntimeContext()
        thread = MagicMock()
        thread.is_alive.return_value = False
        ctx.set_session(MagicMock(), thread)
        assert not ctx.is_session_running()

    def test_clear_session_removes_state(self):
        ctx = RuntimeContext()
        ctx.set_session(MagicMock(), MagicMock())
        ctx.clear_session()
        assert ctx.get_active_runner() is None
        assert not ctx.is_session_running()

    def test_session_lock_is_reentrant_safe(self):
        ctx = RuntimeContext()
        acquired = []
        def _try():
            with ctx.session_lock:
                acquired.append(True)
        t = threading.Thread(target=_try)
        t.start()
        t.join(timeout=1.0)
        assert acquired == [True]


# ── autogain state management ─────────────────────────────────────────────────

class TestAutogainState:
    def test_get_autogain_job_initially_none(self):
        ctx = RuntimeContext()
        assert ctx.get_autogain_job() is None

    def test_set_autogain_job_stores_reference(self):
        ctx = RuntimeContext()
        job = object()
        ctx.set_autogain_job(job)
        assert ctx.get_autogain_job() is job

    def test_set_autogain_job_none_clears_it(self):
        ctx = RuntimeContext()
        ctx.set_autogain_job(object())
        ctx.set_autogain_job(None)
        assert ctx.get_autogain_job() is None


# ── FastAPI lifespan smoke test ───────────────────────────────────────────────

class TestLifespan:
    def test_lifespan_sets_and_clears_runtime(self):
        from fastapi.testclient import TestClient
        from smart_telescope.app import app
        from smart_telescope.api import deps

        # Use TestClient as context manager to trigger lifespan startup + shutdown
        with TestClient(app) as client:
            rt = get_runtime()
            assert isinstance(rt, RuntimeContext)
            # runtime is accessible via app state
            assert app.state.runtime is rt
            # readiness check works while app is live
            r = client.get("/api/readiness")
            assert r.status_code == 200

    def test_lifespan_shutdown_stops_device_state(self):
        from fastapi.testclient import TestClient
        from smart_telescope.app import app

        with TestClient(app) as client:
            rt = get_runtime()
            ds_thread = rt.device_state._thread

        # After __exit__, shutdown() was called; thread should be dead
        if ds_thread is not None:
            assert not ds_thread.is_alive()
