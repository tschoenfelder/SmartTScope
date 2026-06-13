"""API tests for GET/POST /api/collimation/archive/*."""
import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient
from unittest.mock import MagicMock

from smart_telescope.app import app
from smart_telescope.api import collimation as col_module
from smart_telescope.domain.frame import FitsFrame


def _make_frame(width: int = 100, height: int = 100) -> FitsFrame:
    pixels = np.zeros((height, width), dtype=np.float32)
    pixels[50, 50] = 1000.0
    return FitsFrame(pixels=pixels, header=fits.Header(), exposure_seconds=2.0)


@pytest.fixture(autouse=True)
def reset_singletons():
    orig_assistant = col_module._assistant
    orig_archive = col_module._frame_archive
    yield
    col_module._assistant = orig_assistant
    col_module._frame_archive = orig_archive


@pytest.fixture()
def mock_archive():
    archive = MagicMock()
    archive.list_sessions.return_value = [
        {
            "session_id": "abc-123",
            "frame_count": 2,
            "state_counts": {"measure_donut": 2},
            "size_bytes": 1000,
        }
    ]
    archive.list_frames.return_value = [
        {
            "frame_stem": "measure_donut_0001",
            "has_fits": True,
            "state": "measure_donut",
            "frame_index": 1,
            "captured_at": "2026-01-01T00:00:00+00:00",
            "exposure_s": 2.0,
            "gain": 100,
            "size_bytes": 500,
        }
    ]
    archive.load_frame.return_value = _make_frame()
    archive.load_sidecar.return_value = {
        "state": "measure_donut",
        "bit_depth": 16,
        "ref_x": 50.0,
        "ref_y": 50.0,
        "analysis": {"reason": "ok", "error_x_px": 1.5, "error_y_px": -0.5},
    }
    archive.save_tag.return_value = "goto_143022"
    return archive


@pytest.fixture()
def client(mock_archive):
    col_module._frame_archive = mock_archive
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def client_no_archive():
    col_module._frame_archive = None
    with TestClient(app) as c:
        yield c


def test_list_sessions_returns_list(client):
    r = client.get("/api/collimation/archive")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["session_id"] == "abc-123"


def test_list_sessions_no_archive_returns_disabled(client_no_archive):
    r = client_no_archive.get("/api/collimation/archive")
    assert r.status_code == 200
    data = r.json()
    assert data == {"enabled": False, "sessions": []}


def test_list_frames_returns_list(client):
    r = client.get("/api/collimation/archive/abc-123")
    assert r.status_code == 200
    data = r.json()
    assert data["enabled"] is True
    assert len(data["frames"]) == 1
    assert data["frames"][0]["frame_stem"] == "measure_donut_0001"


def test_list_frames_no_archive_returns_disabled(client_no_archive):
    r = client_no_archive.get("/api/collimation/archive/abc-123")
    assert r.status_code == 200
    assert r.json() == {"enabled": False, "session_id": "abc-123", "frames": []}


def test_replay_returns_original_and_replayed(client):
    r = client.post("/api/collimation/archive/abc-123/measure_donut_0001/replay")
    assert r.status_code == 200
    data = r.json()
    assert "original" in data
    assert "replayed" in data
    assert data["original"]["error_x_px"] == 1.5
    assert data["state"] == "measure_donut"


def test_replay_missing_frame_returns_404(client, mock_archive):
    mock_archive.load_frame.side_effect = FileNotFoundError("not found")
    r = client.post("/api/collimation/archive/abc-123/nonexistent_0001/replay")
    assert r.status_code == 404


def test_archive_tag_saves_entry(client, mock_archive):
    r = client.post("/api/collimation/archive/tag", json={
        "tag_type": "goto",
        "data": {"ra": 5.588, "dec": -5.39, "target": "M42"},
    })
    assert r.status_code == 200
    data = r.json()
    assert data["frame_stem"] == "goto_143022"
    mock_archive.save_tag.assert_called_once()
    call_args = mock_archive.save_tag.call_args
    assert call_args[0][1] == "goto"


def test_archive_tag_uses_date_session_when_not_specified(client, mock_archive):
    import datetime
    expected_session = datetime.date.today().strftime("s3_%Y-%m-%d")
    r = client.post("/api/collimation/archive/tag", json={"tag_type": "solve", "data": {}})
    assert r.status_code == 200
    assert r.json()["session_id"] == expected_session


def test_archive_tag_no_archive_returns_503(client_no_archive):
    r = client_no_archive.post("/api/collimation/archive/tag",
                               json={"tag_type": "goto", "data": {}})
    assert r.status_code == 503
