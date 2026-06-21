"""Tests for /api/guide_monitor endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import guide_monitor as gm_module
from smart_telescope.domain.guide_monitor import (
    GuideMonitorResult,
    GuideMonitorStatus,
)
from smart_telescope.app import app

client = TestClient(app)

_VALID_MODEL = "GPCMOS02000KPA"


def _mock_camera() -> MagicMock:
    return MagicMock()


def _mock_monitor(*, running: bool = False, last_result: GuideMonitorResult | None = None) -> MagicMock:
    m = MagicMock()
    m.running = running
    m.last_result = last_result
    return m


@pytest.fixture(autouse=True)
def _reset() -> None:
    gm_module._reset()
    yield  # type: ignore[misc]
    gm_module._reset()


class TestGuideMonitorStart:
    def test_unknown_model_returns_400(self) -> None:
        r = client.post("/api/guide_monitor/start", json={"camera_model": "NONEXISTENT"})
        assert r.status_code == 400

    def test_unknown_model_error_mentions_model(self) -> None:
        r = client.post("/api/guide_monitor/start", json={"camera_model": "BOGUS"})
        assert "BOGUS" in r.json()["detail"]

    def test_already_running_returns_409(self) -> None:
        gm_module._monitor = _mock_monitor(running=True)
        with patch("smart_telescope.api.guide_monitor.deps.get_preview_camera", return_value=_mock_camera()):
            r = client.post("/api/guide_monitor/start", json={"camera_model": _VALID_MODEL})
        assert r.status_code == 409

    def test_camera_unavailable_returns_503(self) -> None:
        with patch(
            "smart_telescope.api.guide_monitor.deps.get_preview_camera",
            side_effect=RuntimeError("no cam"),
        ):
            r = client.post("/api/guide_monitor/start", json={"camera_model": _VALID_MODEL})
        assert r.status_code == 503

    def test_success_returns_202(self) -> None:
        with (
            patch("smart_telescope.api.guide_monitor.deps.get_preview_camera", return_value=_mock_camera()),
            patch("smart_telescope.api.guide_monitor.GuideMonitor") as MockGM,
        ):
            MockGM.return_value = _mock_monitor()
            r = client.post("/api/guide_monitor/start", json={"camera_model": _VALID_MODEL})
        assert r.status_code == 202

    def test_success_body_started_true(self) -> None:
        with (
            patch("smart_telescope.api.guide_monitor.deps.get_preview_camera", return_value=_mock_camera()),
            patch("smart_telescope.api.guide_monitor.GuideMonitor") as MockGM,
        ):
            MockGM.return_value = _mock_monitor()
            r = client.post("/api/guide_monitor/start", json={"camera_model": _VALID_MODEL})
        assert r.json() == {"started": True}


class TestGuideMonitorStop:
    def test_no_monitor_returns_200(self) -> None:
        r = client.post("/api/guide_monitor/stop")
        assert r.status_code == 200

    def test_no_monitor_body_stopped_true(self) -> None:
        r = client.post("/api/guide_monitor/stop")
        assert r.json() == {"stopped": True}

    def test_existing_monitor_is_stopped(self) -> None:
        m = _mock_monitor(running=True)
        gm_module._monitor = m
        client.post("/api/guide_monitor/stop")
        m.stop.assert_called_once()


class TestGuideMonitorStatus:
    def test_no_monitor_not_running(self) -> None:
        r = client.get("/api/guide_monitor/status")
        assert r.status_code == 200
        assert r.json()["running"] is False

    def test_monitor_no_result_returns_running_state(self) -> None:
        gm_module._monitor = _mock_monitor(running=True, last_result=None)
        r = client.get("/api/guide_monitor/status")
        assert r.status_code == 200
        assert r.json()["running"] is True

    def test_monitor_with_result_returns_full_status(self) -> None:
        result = GuideMonitorResult(
            status=GuideMonitorStatus.GUIDE_GAIN_OK,
            exposure_ms=2000.0,
            gain=200,
            p99_9=0.45,
            checked_at="12:00:00Z",
            dawn_warning=False,
            warning_msg=None,
        )
        gm_module._monitor = _mock_monitor(running=True, last_result=result)
        r = client.get("/api/guide_monitor/status")
        data = r.json()
        assert data["running"] is True
        assert data["status"] == "GUIDE_GAIN_OK"
        assert data["gain"] == 200
        assert data["dawn_warning"] is False
