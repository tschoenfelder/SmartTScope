"""Unit tests for /api/bias_estimation endpoints (COE-T3)."""
import time
import pytest
from fastapi.testclient import TestClient
from smart_telescope.app import app
from smart_telescope.runtime import RuntimeContext, set_runtime
import smart_telescope.runtime as _rt_module


@pytest.fixture(autouse=True)
def _restore_runtime():
    """Save and restore the global runtime singleton after each test.

    Prevents our custom RuntimeContext from leaking into subsequent test modules.
    """
    saved = _rt_module._runtime
    yield
    _rt_module._runtime = saved


def _make_rt():
    from smart_telescope.adapters.mock.camera import MockCamera
    from smart_telescope.services.optical_train_registry import OpticalTrain, OpticalTrainRegistry
    rt = RuntimeContext()
    rt._camera = MockCamera()
    rt._adapters_built = True
    # Wire a minimal optical train so resolve_camera_index("main") → index 0.
    train = OpticalTrain(
        name="main",
        camera_role="main",
        camera_index=0,
        telescope_name="test",
        focal_mm=2000.0,
        reducer_factor=1.0,
        pixel_scale_arcsec=0.5,
        has_focuser=False,
        focuser="",
    )
    rt._optical_train_registry = OpticalTrainRegistry({"main": train})
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
    assert resp.status_code == 202
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
    assert start_resp.status_code == 202
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


def test_start_bias_estimation_unknown_camera_role():
    rt = _make_rt()
    set_runtime(rt)
    client = TestClient(app)
    resp = client.post("/api/bias_estimation/start", json={
        "camera_role": "guide",  # not available in test fixture
        "gain_mode": "LCG",
        "frame_count": 2,
        "run_sweep": False,
    })
    # resolve_camera_index raises HTTPException(422) for unknown roles
    assert resp.status_code == 422
