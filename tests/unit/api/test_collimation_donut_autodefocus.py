"""POST /api/collimation/donut/auto_defocus — standalone Defocus Donut automation.

Verifies the endpoint reuses DefocusController the same way the guided
Collimation Wizard does (services/collimation/assistant.py:_handle_rough_defocus),
without needing real hardware — DefocusController.defocus() is mocked so these
tests focus on the endpoint's request/response wiring and error handling.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CameraPort, CaptureAbortedError
from smart_telescope.ports.focuser import FocuserPort
from smart_telescope.services.collimation.defocus_controller import DefocusResult

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


def _make_frame(width: int = 640, height: int = 480) -> FitsFrame:
    from astropy.io.fits import Header
    pixels = np.zeros((height, width), dtype=np.float32)
    return FitsFrame(pixels=pixels, header=Header(), exposure_seconds=1.0)


def _mock_camera() -> MagicMock:
    cam = MagicMock(spec=CameraPort)
    cam.capture.return_value = _make_frame()
    cam.get_bit_depth.return_value = 16
    return cam


def _mock_focuser() -> MagicMock:
    return MagicMock(spec=FocuserPort)


def _patch_defocus_controller(result: DefocusResult) -> object:
    mock_ctrl = MagicMock()
    mock_ctrl.defocus.return_value = result
    return patch(
        "smart_telescope.services.collimation.defocus_controller.DefocusController",
        return_value=mock_ctrl,
    )


class TestDonutAutoDefocus:
    def test_success_returns_defocus_result_fields(self) -> None:
        app.dependency_overrides[deps.get_camera] = lambda: _mock_camera()
        app.dependency_overrides[deps.get_focuser] = lambda: _mock_focuser()
        result = DefocusResult(
            success=True, reason="at_target",
            estimated_radius_px=42.0, target_min_px=30.0, target_max_px=60.0,
            net_steps=120,
        )
        with _patch_defocus_controller(result):
            r = client.post("/api/collimation/donut/auto_defocus", json={"exposure_s": 1.0})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is True
        assert body["reason"] == "at_target"
        assert body["estimated_radius_px"] == 42.0
        assert body["net_steps"] == 120

    def test_star_lost_propagates_reason(self) -> None:
        app.dependency_overrides[deps.get_camera] = lambda: _mock_camera()
        app.dependency_overrides[deps.get_focuser] = lambda: _mock_focuser()
        result = DefocusResult(
            success=False, reason="star_lost",
            estimated_radius_px=None, target_min_px=30.0, target_max_px=60.0,
            net_steps=5,
        )
        with _patch_defocus_controller(result):
            r = client.post("/api/collimation/donut/auto_defocus", json={"exposure_s": 1.0})
        assert r.status_code == 200
        body = r.json()
        assert body["success"] is False
        assert body["reason"] == "star_lost"

    def test_camera_capture_failure_returns_503(self) -> None:
        cam = MagicMock(spec=CameraPort)
        cam.capture.side_effect = RuntimeError("sensor timeout")
        app.dependency_overrides[deps.get_camera] = lambda: cam
        app.dependency_overrides[deps.get_focuser] = lambda: _mock_focuser()
        r = client.post("/api/collimation/donut/auto_defocus", json={"exposure_s": 1.0})
        assert r.status_code == 503

    def test_capture_aborted_returns_503(self) -> None:
        cam = MagicMock(spec=CameraPort)
        cam.capture.side_effect = CaptureAbortedError("aborted")
        app.dependency_overrides[deps.get_camera] = lambda: cam
        app.dependency_overrides[deps.get_focuser] = lambda: _mock_focuser()
        r = client.post("/api/collimation/donut/auto_defocus", json={"exposure_s": 1.0})
        assert r.status_code == 503

    def test_defocus_failure_returns_503(self) -> None:
        app.dependency_overrides[deps.get_camera] = lambda: _mock_camera()
        app.dependency_overrides[deps.get_focuser] = lambda: _mock_focuser()
        mock_ctrl = MagicMock()
        mock_ctrl.defocus.side_effect = RuntimeError("focuser jammed")
        with patch(
            "smart_telescope.services.collimation.defocus_controller.DefocusController",
            return_value=mock_ctrl,
        ):
            r = client.post("/api/collimation/donut/auto_defocus", json={"exposure_s": 1.0})
        assert r.status_code == 503
