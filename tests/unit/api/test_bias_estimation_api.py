"""Unit tests for /api/bias_estimation endpoints (COE-T3)."""
import time
import pytest
from fastapi.testclient import TestClient
from smart_telescope.app import app
from smart_telescope.runtime import RuntimeContext, set_runtime


def _make_rt():
    from smart_telescope.adapters.mock.camera import MockCamera
    rt = RuntimeContext()
    rt._camera = MockCamera()
    rt._adapters_built = True
    return rt


def test_start_bias_estimation_returns_job_id():
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)
    resp = client.post("/api/bias_estimation/start", json={
        "camera_role": "main",
        "gain_mode": "LCG",
        "frame_count": 3,
        "run_sweep": False,
    })
    assert resp.status_code in (200, 202)
    data = resp.json()
    assert "job_id" in data


def test_start_bias_estimation_invalid_gain_mode():
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)
    resp = client.post("/api/bias_estimation/start", json={
        "camera_role": "main",
        "gain_mode": "INVALID",
        "frame_count": 3,
        "run_sweep": False,
    })
    assert resp.status_code == 422


def test_status_unknown_job_returns_404():
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)
    resp = client.get("/api/bias_estimation/status/nonexistent-job-id")
    assert resp.status_code == 404


def test_status_completed_job_includes_result():
    """A completed job includes recommended_offset and sweep."""
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)

    start_resp = client.post("/api/bias_estimation/start", json={
        "camera_role": "main",
        "gain_mode": "LCG",
        "frame_count": 2,
        "run_sweep": False,
    })
    assert start_resp.status_code in (200, 202)
    job_id = start_resp.json()["job_id"]

    # Poll until done (mock camera is fast)
    for _ in range(30):
        status_resp = client.get(f"/api/bias_estimation/status/{job_id}")
        assert status_resp.status_code == 200
        data = status_resp.json()
        if data["status"] in ("DONE", "FAILED", "CANCELLED"):
            break
        time.sleep(0.1)

    assert data["status"] == "DONE"
    assert "recommended_offset" in data
    assert "sweep" in data
