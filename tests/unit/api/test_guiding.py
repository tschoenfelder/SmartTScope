"""Unit tests for /api/guiding endpoints."""
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.api import deps
from smart_telescope.services.guiding_service import GuidingService, GuidingStatus
from smart_telescope.services.guide_measurement import CentroidConfig, GuideControllerConfig


@pytest.fixture()
def mock_svc():
    svc = MagicMock(spec=GuidingService)
    svc.status.return_value = GuidingStatus(state="idle", measure_only=True)
    return svc


@pytest.fixture()
def client(mock_svc):
    mock_rt = MagicMock()
    mock_rt.get_camera_by_role.return_value = MagicMock()  # any camera object
    mock_rt._mount = None
    app.dependency_overrides[deps.get_guiding_service] = lambda: mock_svc
    app.dependency_overrides[deps.get_runtime] = lambda: mock_rt
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_get_status_idle(client, mock_svc):
    r = client.get("/api/guiding/status")
    assert r.status_code == 200
    data = r.json()
    assert data["state"] == "idle"
    assert data["measure_only"] is True


def test_post_start_calls_service(client, mock_svc):
    r = client.post("/api/guiding/start", json={})
    assert r.status_code == 202
    mock_svc.start.assert_called_once()


def test_post_stop_calls_service(client, mock_svc):
    mock_svc.status.return_value = GuidingStatus(state="running", measure_only=True)
    r = client.post("/api/guiding/stop")
    assert r.status_code == 200
    mock_svc.stop.assert_called_once()


def test_post_start_when_already_running_returns_409(client, mock_svc):
    mock_svc.status.return_value = GuidingStatus(state="running", measure_only=True)
    r = client.post("/api/guiding/start", json={})
    assert r.status_code == 409
    mock_svc.start.assert_not_called()
