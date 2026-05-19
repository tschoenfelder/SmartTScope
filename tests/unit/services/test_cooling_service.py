"""Unit tests for CoolingService — R6-001."""
from __future__ import annotations

import time
import threading
from unittest.mock import MagicMock

import pytest

from smart_telescope.services.cooling import CoolingService, CoolingStatus
from smart_telescope.domain.cooling import CoolingAction


# ── Helpers ───────────────────────────────────────────────────────────────────

class _TecCam:
    def __init__(self, temp_c: float = 20.0, power_pct: float = 50.0) -> None:
        self.temp_c = temp_c
        self.power_pct = power_pct
        self.tec_enabled = False
        self.tec_target_c: float | None = None
        self.calls: list[str] = []

    def get_temperature(self) -> float:
        self.calls.append("get_temperature")
        return self.temp_c

    def get_tec_power_pct(self) -> float:
        return self.power_pct

    def set_tec_enabled(self, on: bool) -> None:
        self.calls.append(f"set_tec_enabled({on})")
        self.tec_enabled = on

    def set_tec_target_c(self, t: float) -> None:
        self.calls.append(f"set_tec_target_c({t})")
        self.tec_target_c = t


# ── Idle state ────────────────────────────────────────────────────────────────

def test_initial_status_disabled():
    svc = CoolingService()
    s = svc.get_status()
    assert s.enabled is False
    assert s.camera_index is None
    assert s.current_temp_c is None
    assert s.target_c is None


def test_stop_when_idle_is_safe():
    svc = CoolingService()
    svc.stop()  # must not raise


# ── start() ───────────────────────────────────────────────────────────────────

def test_start_enables_tec_on_camera():
    svc = CoolingService()
    cam = _TecCam()
    svc.start(cam, 0, -10.0)
    svc.stop()
    assert cam.tec_enabled is True or "set_tec_enabled(True)" in cam.calls


def test_start_sets_target_on_camera():
    svc = CoolingService()
    cam = _TecCam()
    svc.start(cam, 0, -7.0)
    svc.stop()
    assert cam.tec_target_c == pytest.approx(-7.0)


def test_start_sets_camera_index():
    svc = CoolingService()
    cam = _TecCam()
    svc.start(cam, 3, -5.0)
    s = svc.get_status()
    svc.stop()
    assert s.enabled is True
    assert s.camera_index == 3


def test_start_sets_target_c_in_status():
    svc = CoolingService()
    cam = _TecCam()
    svc.start(cam, 0, -8.0)
    s = svc.get_status()
    svc.stop()
    assert s.target_c == pytest.approx(-8.0)


# ── stop() ────────────────────────────────────────────────────────────────────

def test_stop_disables_tec():
    svc = CoolingService()
    cam = _TecCam()
    svc.start(cam, 0, -10.0)
    svc.stop()
    assert cam.tec_enabled is False


def test_stop_clears_enabled():
    svc = CoolingService()
    cam = _TecCam()
    svc.start(cam, 0, -10.0)
    svc.stop()
    assert svc.get_status().enabled is False


def test_stop_is_idempotent():
    svc = CoolingService()
    cam = _TecCam()
    svc.start(cam, 0, -10.0)
    svc.stop()
    svc.stop()  # second call must not raise


# ── restart (start over existing session) ─────────────────────────────────────

def test_second_start_replaces_session():
    svc = CoolingService()
    cam1 = _TecCam()
    cam2 = _TecCam()
    svc.start(cam1, 0, -5.0)
    svc.start(cam2, 1, -8.0)
    s = svc.get_status()
    svc.stop()
    assert s.camera_index == 1
    assert s.target_c == pytest.approx(-8.0)


def test_second_start_disables_first_camera_tec():
    svc = CoolingService()
    cam1 = _TecCam()
    cam2 = _TecCam()
    svc.start(cam1, 0, -5.0)
    svc.start(cam2, 1, -8.0)
    svc.stop()
    assert cam1.tec_enabled is False


# ── polling ───────────────────────────────────────────────────────────────────

def test_poll_populates_status():
    svc = CoolingService()
    cam = _TecCam(temp_c=15.0, power_pct=40.0)
    svc.start(cam, 0, -10.0)
    # First poll runs immediately in the background thread
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        s = svc.get_status()
        if s.current_temp_c is not None:
            break
        time.sleep(0.02)
    svc.stop()
    assert s.current_temp_c == pytest.approx(15.0, abs=0.01)


def test_poll_sets_action():
    svc = CoolingService()
    cam = _TecCam(temp_c=15.0, power_pct=40.0)
    svc.start(cam, 0, -10.0)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        s = svc.get_status()
        if s.action is not None:
            break
        time.sleep(0.02)
    svc.stop()
    assert s.action is not None
    assert isinstance(s.action, CoolingAction)


# ── thread safety ─────────────────────────────────────────────────────────────

def test_concurrent_get_status_is_safe():
    svc = CoolingService()
    cam = _TecCam(temp_c=10.0)
    svc.start(cam, 0, -10.0)

    errors = []

    def reader():
        for _ in range(30):
            try:
                svc.get_status()
            except Exception as exc:
                errors.append(exc)
            time.sleep(0.01)

    threads = [threading.Thread(target=reader) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
    svc.stop()

    assert not errors
