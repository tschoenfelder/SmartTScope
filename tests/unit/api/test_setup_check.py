"""Tests for BUG-006 — extended setup check API and service."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.ports.mount import MountPosition, MountState
from smart_telescope.services.setup_check_service import (
    FocuserMoveResult,
    HomeResult,
    MountSlewResult,
    PerCameraSolveResult,
    PlateSolveResult,
    run_focuser_move,
    run_home_return,
    run_mount_slew,
    run_plate_solve,
)
from smart_telescope.services.hardware_coordinator import HardwareCommandCoordinator

client = TestClient(app)


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_focuser(available=True, position=12500):
    f = MagicMock()
    f.is_available = available
    f.get_position.return_value = position
    f.move.return_value = None
    return f


def _mock_mount(state=MountState.TRACKING, ra=5.5, dec=22.0):
    m = MagicMock()
    m.get_state.return_value = state
    pos = MountPosition(ra=ra, dec=dec)
    m.get_position.return_value = pos
    m.goto.return_value = True
    m.home.return_value = True
    return m


def _mock_device_state(target_reached=True):
    ds = MagicMock()
    ds.wait_while_mount_state.return_value = True
    ds.wait_for_mount_state.return_value = target_reached
    ds.poll_now.return_value = None
    return ds


def _mock_solver(solved=True):
    s = MagicMock()
    result = MagicMock()
    result.solved = solved
    result.ra_h = 5.5
    result.dec_deg = 22.0
    s.solve.return_value = result
    return s


def _mock_registry(train_name="main", camera_index=0, pixel_scale=0.38):
    registry = MagicMock()
    train = MagicMock()
    train.name = train_name
    train.camera_role = train_name
    train.camera_index = camera_index
    train.pixel_scale_arcsec = pixel_scale
    registry.all.return_value = [train]
    return registry


def _mock_runtime():
    rt = MagicMock()
    camera = MagicMock()
    frame = MagicMock()
    frame.pixels = __import__("numpy").zeros((100, 100), dtype="uint16")
    camera.capture.return_value = frame
    rt.get_camera_by_role.return_value = camera
    return rt


# ── run_focuser_move ──────────────────────────────────────────────────────────

class TestFocuserMove:
    def test_returns_ok_when_position_changes(self):
        # get_position returns: before=12500, after=12600 (moved +100)
        positions = iter([12500, 12600])
        f = _mock_focuser()
        f.get_position.side_effect = positions
        result = run_focuser_move(f, steps=100)
        assert result.ok is True
        assert result.before == 12500
        assert result.after == 12600
        assert result.delta == 100

    def test_fails_when_focuser_unavailable(self):
        f = _mock_focuser(available=False)
        result = run_focuser_move(f)
        assert result.ok is False
        assert "not available" in result.message.lower()

    def test_fails_when_position_unchanged(self):
        f = _mock_focuser(position=5000)
        result = run_focuser_move(f, steps=100)
        assert result.ok is False
        assert "did not move" in result.message.lower()

    def test_restores_position_after_move(self):
        f = _mock_focuser()
        f.get_position.side_effect = [10000, 10100]
        run_focuser_move(f, steps=100)
        # move called twice: forward (absolute target) then restore (absolute before)
        assert f.move.call_count == 2
        calls = [c[0][0] for c in f.move.call_args_list]
        assert calls[0] == 10100   # before + steps = 10000 + 100
        assert calls[1] == 10000   # restore to before

    def test_returns_fail_on_exception(self):
        f = _mock_focuser()
        f.get_position.side_effect = RuntimeError("serial timeout")
        result = run_focuser_move(f)
        assert result.ok is False
        assert "serial timeout" in result.message


# ── run_mount_slew ────────────────────────────────────────────────────────────

class TestMountSlew:
    def test_returns_ok_on_successful_slew(self):
        m  = _mock_mount(state=MountState.TRACKING, ra=5.5, dec=22.0)
        ds = _mock_device_state(target_reached=True)
        m.get_position.side_effect = [MountPosition(5.5, 22.0), MountPosition(5.5, 27.0)]
        result = run_mount_slew(m, ds, offset_dec_deg=5.0)
        assert result.ok is True
        assert result.dec_before == pytest.approx(22.0)
        assert result.dec_after  == pytest.approx(27.0)

    def test_fails_when_mount_parked(self):
        m  = _mock_mount(state=MountState.PARKED)
        ds = _mock_device_state()
        result = run_mount_slew(m, ds)
        assert result.ok is False
        assert "PARKED" in result.message

    def test_fails_when_mount_unknown(self):
        m  = _mock_mount(state=MountState.UNKNOWN)
        ds = _mock_device_state()
        result = run_mount_slew(m, ds)
        assert result.ok is False

    def test_fails_when_goto_rejected(self):
        m  = _mock_mount()
        m.goto.return_value = False
        ds = _mock_device_state()
        result = run_mount_slew(m, ds)
        assert result.ok is False
        assert "rejected" in result.message.lower()

    def test_fails_when_slew_does_not_start(self):
        m  = _mock_mount()
        ds = _mock_device_state()
        ds.wait_while_mount_state.return_value = False
        result = run_mount_slew(m, ds)
        assert result.ok is False
        assert "did not start slewing" in result.message.lower()

    def test_fails_when_slew_times_out(self):
        m  = _mock_mount()
        ds = _mock_device_state()
        ds.wait_while_mount_state.return_value = True
        ds.wait_for_mount_state.return_value = False  # never reaches TRACKING
        result = run_mount_slew(m, ds)
        assert result.ok is False
        assert "did not complete" in result.message.lower()

    def test_clamps_dec_target_at_80(self):
        m  = _mock_mount(dec=79.0)
        ds = _mock_device_state()
        m.get_position.side_effect = [MountPosition(5.5, 79.0), MountPosition(5.5, 80.0)]
        result = run_mount_slew(m, ds, offset_dec_deg=5.0)
        # GoTo should clamp to 80° max
        call_dec = m.goto.call_args[0][1]
        assert call_dec <= 80.0


# ── run_plate_solve ───────────────────────────────────────────────────────────

class TestPlateSolve:
    def test_returns_ok_when_solved(self):
        registry = _mock_registry()
        rt       = _mock_runtime()
        solver   = _mock_solver(solved=True)
        result   = run_plate_solve(registry, rt, solver)
        assert result.ok is True
        assert len(result.per_camera) == 1
        assert result.per_camera[0].solved is True

    def test_returns_fail_when_not_solved(self):
        registry = _mock_registry()
        rt       = _mock_runtime()
        solver   = _mock_solver(solved=False)
        result   = run_plate_solve(registry, rt, solver)
        assert result.ok is False
        assert result.per_camera[0].solved is False

    def test_returns_fail_when_no_trains(self):
        registry = MagicMock()
        registry.all.return_value = []
        result = run_plate_solve(registry, MagicMock(), MagicMock())
        assert result.ok is False
        assert "no optical trains" in result.message.lower()

    def test_capture_failure_recorded_per_camera(self):
        registry = _mock_registry()
        rt = _mock_runtime()
        rt.get_camera_by_role.side_effect = RuntimeError("camera disconnected")
        solver = _mock_solver()
        result = run_plate_solve(registry, rt, solver)
        assert result.ok is False
        assert result.per_camera[0].solved is False
        assert "Capture failed" in result.per_camera[0].error

    def test_solver_exception_recorded_per_camera(self):
        registry = _mock_registry()
        rt = _mock_runtime()
        solver = MagicMock()
        solver.solve.side_effect = RuntimeError("ASTAP not found")
        result = run_plate_solve(registry, rt, solver)
        assert result.ok is False
        assert "Solver error" in result.per_camera[0].error


def _mock_coordinator():
    """Mock HardwareCommandCoordinator that always allows mount_command()."""
    from contextlib import contextmanager
    coord = MagicMock(spec=HardwareCommandCoordinator)

    @contextmanager
    def _ctx():
        yield
    coord.mount_command.return_value = _ctx()
    coord.mount_command.side_effect = None
    coord.mount_command = MagicMock(side_effect=lambda: _ctx())
    return coord


# ── run_home_return ───────────────────────────────────────────────────────────

class TestHomeReturn:
    def test_returns_ok_on_successful_home(self):
        m    = _mock_mount(state=MountState.TRACKING)
        ds   = _mock_device_state(target_reached=True)
        coord = _mock_coordinator()
        with patch("smart_telescope.services.setup_check_service.home_sequence",
                   return_value=(5.5, 85.0)):
            result = run_home_return(m, ds, coord)
        assert result.ok is True
        assert result.elapsed_s is not None

    def test_fails_when_home_sequence_raises(self):
        m    = _mock_mount()
        ds   = _mock_device_state()
        coord = _mock_coordinator()
        with patch("smart_telescope.services.setup_check_service.home_sequence",
                   side_effect=RuntimeError("OnStep not responding")):
            result = run_home_return(m, ds, coord)
        assert result.ok is False
        assert "OnStep not responding" in result.message

    def test_fails_when_slew_times_out(self):
        m    = _mock_mount()
        ds   = _mock_device_state(target_reached=False)
        coord = _mock_coordinator()
        with patch("smart_telescope.services.setup_check_service.home_sequence",
                   return_value=(5.5, 85.0)):
            result = run_home_return(m, ds, coord, timeout_s=0.01)
        assert result.ok is False

    def test_fails_on_mount_slewing_error(self):
        from smart_telescope.services.setup_check_service import MountSlewingError
        m    = _mock_mount()
        ds   = _mock_device_state()
        coord = _mock_coordinator()
        with patch("smart_telescope.services.setup_check_service.home_sequence",
                   side_effect=MountSlewingError("already slewing")):
            result = run_home_return(m, ds, coord)
        assert result.ok is False
        assert "already slewing" in result.message


# ── API endpoint smoke tests ───────────────────────────────────────────────────

class TestSetupCheckEndpoints:
    def run_focuser_move_returns_200(self):
        resp = client.post("/api/setup/focuser_move")
        assert resp.status_code == 200
        assert "ok" in resp.json()

    def run_mount_slew_returns_200(self):
        resp = client.post("/api/setup/mount_slew")
        assert resp.status_code == 200
        assert "ok" in resp.json()

    def run_plate_solve_returns_200(self):
        resp = client.post("/api/setup/plate_solve")
        assert resp.status_code == 200
        assert "ok" in resp.json()

    def run_home_return_returns_200(self):
        resp = client.post("/api/setup/home_return")
        assert resp.status_code == 200
        assert "ok" in resp.json()

    def test_run_all_returns_200_with_steps(self):
        resp = client.post("/api/setup/run_all")
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data
        assert "passed" in data
        assert set(data["steps"].keys()) == {
            "focuser_move", "mount_slew", "plate_solve", "home_return"
        }

    def test_run_all_total_is_four(self):
        resp = client.post("/api/setup/run_all")
        assert resp.json()["total"] == 4

    def run_focuser_move_with_custom_steps(self):
        resp = client.post("/api/setup/focuser_move", json={"steps": 50})
        assert resp.status_code == 200

    def run_mount_slew_with_custom_offset(self):
        resp = client.post("/api/setup/mount_slew", json={"offset_dec_deg": 3.0})
        assert resp.status_code == 200
