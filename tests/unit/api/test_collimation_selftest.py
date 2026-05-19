"""COL-022 — Hardware self-test API endpoints.

Tests for POST /api/collimation/selftest/{camera,mount,focuser}.
All adapters are replaced by MagicMock — no hardware required.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame  # noqa: F401 — used by _make_frame
from smart_telescope.ports.camera import CameraPort, CaptureAbortedError
from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.ports.mount import MountPort

client = TestClient(app)


# ── fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset():
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


def _make_frame(pixels: np.ndarray) -> FitsFrame:
    from astropy.io.fits import Header
    return FitsFrame(pixels=pixels, header=Header(), exposure_seconds=1.0)


def _mock_camera(pixels: np.ndarray | None = None) -> MagicMock:
    pixels = pixels if pixels is not None else np.zeros((100, 100), dtype=np.float32)
    cam = MagicMock(spec=CameraPort)
    cam.capture.return_value = _make_frame(pixels)
    return cam


def _mock_mount(guide_ok: bool = True) -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.guide.return_value = guide_ok
    return m


def _mock_focuser(available: bool = True, position: int = 5000) -> MagicMock:
    f = MagicMock(spec=FocuserPort)
    f.is_available = available
    f.get_position.return_value = position
    f.move.return_value = None
    return f


# ── camera self-test ───────────────────────────────────────────────────────────

class TestSelftestCamera:
    def test_returns_ok_with_dimensions(self):
        pixels = np.zeros((480, 640), dtype=np.float32)
        app.dependency_overrides[deps.get_camera] = lambda: _mock_camera(pixels)
        r = client.post("/api/collimation/selftest/camera")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["width"] == 640
        assert body["height"] == 480

    def test_returns_peak_adu(self):
        px = np.zeros((100, 100), dtype=np.float32)
        px[50, 50] = 3000.0
        app.dependency_overrides[deps.get_camera] = lambda: _mock_camera(px)
        r = client.post("/api/collimation/selftest/camera")
        assert r.status_code == 200
        assert r.json()["peak_adu"] == 3000

    def test_capture_exception_returns_503(self):
        cam = MagicMock(spec=CameraPort)
        cam.capture.side_effect = RuntimeError("sensor timeout")
        app.dependency_overrides[deps.get_camera] = lambda: cam
        r = client.post("/api/collimation/selftest/camera")
        assert r.status_code == 503
        assert "sensor timeout" in r.json()["detail"]

    def test_capture_aborted_returns_503(self):
        cam = MagicMock(spec=CameraPort)
        cam.capture.side_effect = CaptureAbortedError("aborted")
        app.dependency_overrides[deps.get_camera] = lambda: cam
        r = client.post("/api/collimation/selftest/camera")
        assert r.status_code == 503


# ── mount self-test ────────────────────────────────────────────────────────────

class TestSelftestMount:
    def test_north_pulse_ok(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount(guide_ok=True)
        r = client.post("/api/collimation/selftest/mount",
                        json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["direction"] == "n"
        assert body["duration_ms"] == 500

    def test_all_directions_accepted(self):
        for d in ("n", "s", "e", "w"):
            app.dependency_overrides[deps.get_mount] = lambda: _mock_mount(guide_ok=True)
            r = client.post("/api/collimation/selftest/mount",
                            json={"direction": d, "duration_ms": 200})
            assert r.status_code == 200, f"direction {d!r} rejected"

    def test_invalid_direction_returns_422(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount()
        r = client.post("/api/collimation/selftest/mount",
                        json={"direction": "x", "duration_ms": 200})
        assert r.status_code == 422

    def test_guide_failure_returns_503(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount(guide_ok=False)
        r = client.post("/api/collimation/selftest/mount",
                        json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 503

    def test_default_body_accepted(self):
        app.dependency_overrides[deps.get_mount] = lambda: _mock_mount(guide_ok=True)
        r = client.post("/api/collimation/selftest/mount")
        assert r.status_code == 200


# ── focuser self-test ──────────────────────────────────────────────────────────

class TestSelftestFocuser:
    def test_positive_steps_returns_positions(self):
        foc = _mock_focuser(available=True, position=5000)
        foc.get_position.side_effect = [5000, 5010]
        app.dependency_overrides[deps.get_focuser] = lambda: foc
        r = client.post("/api/collimation/selftest/focuser", json={"steps": 10})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["position_before"] == 5000
        assert body["position_after"] == 5010
        assert body["steps"] == 10

    def test_negative_steps_accepted(self):
        foc = _mock_focuser(available=True, position=5000)
        foc.get_position.side_effect = [5000, 4990]
        app.dependency_overrides[deps.get_focuser] = lambda: foc
        r = client.post("/api/collimation/selftest/focuser", json={"steps": -10})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_zero_steps_returns_422(self):
        app.dependency_overrides[deps.get_focuser] = lambda: _mock_focuser()
        r = client.post("/api/collimation/selftest/focuser", json={"steps": 0})
        assert r.status_code == 422

    def test_unavailable_focuser_returns_ok_false(self):
        app.dependency_overrides[deps.get_focuser] = lambda: _mock_focuser(available=False)
        r = client.post("/api/collimation/selftest/focuser", json={"steps": 10})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert "not available" in body["message"]

    def test_default_body_accepted(self):
        foc = _mock_focuser(available=True, position=5000)
        foc.get_position.side_effect = [5000, 5010]
        app.dependency_overrides[deps.get_focuser] = lambda: foc
        r = client.post("/api/collimation/selftest/focuser")
        assert r.status_code == 200
