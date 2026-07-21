"""Unit tests for /api/autofocus (M10-033) — sequence capture + frame metrics."""
from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient

from smart_telescope import config
from smart_telescope.api import autofocus_sequence as af_mod
from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CameraPort
from smart_telescope.ports.focuser import FocuserPort, FocuserStatus

client = TestClient(app)


def _mock_focuser(
    position: int = 1000,
    moving: bool = False,
    available: bool = True,
    max_position: int = 5000,
) -> MagicMock:
    f = MagicMock(spec=FocuserPort)
    type(f).is_available = PropertyMock(return_value=available)
    f.is_moving.return_value = moving
    f.status.return_value = FocuserStatus(
        available=available, position=position, max_position=max_position, moving=moving,
    )
    return f


def _mock_camera() -> MagicMock:
    c = MagicMock(spec=CameraPort)
    rng = np.random.default_rng(0)
    pixels = rng.random((16, 16)).astype(np.float32)
    hdr = fits.Header()
    hdr["EXPTIME"] = 1.0
    c.capture.return_value = FitsFrame(pixels=pixels, header=hdr, exposure_seconds=1.0)
    return c


def _wait_for_job(job_id: str, timeout: float = 5.0, interval: float = 0.05) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/autofocus/sequence/status/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(interval)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


@pytest.fixture(autouse=True)
def _reset() -> None:
    deps.reset()
    af_mod._reset_jobs()
    yield
    app.dependency_overrides.clear()
    deps.reset()
    af_mod._reset_jobs()


class TestStartSequence:
    def test_returns_422_when_end_not_greater_than_start(self, tmp_path: Path) -> None:
        f = _mock_focuser()
        app.dependency_overrides[deps.get_focuser] = lambda: f
        r = client.post("/api/autofocus/sequence", json={
            "start_offset": 100, "end_offset": 100, "step": 10,
        })
        assert r.status_code == 422

    def test_returns_422_when_range_exceeds_focuser_max(self, tmp_path: Path) -> None:
        f = _mock_focuser(position=100, max_position=500)
        app.dependency_overrides[deps.get_focuser] = lambda: f
        r = client.post("/api/autofocus/sequence", json={
            "start_offset": -200, "end_offset": 800, "step": 50,
        })
        assert r.status_code == 422

    def test_returns_503_when_focuser_unavailable(self) -> None:
        f = _mock_focuser(available=False)
        app.dependency_overrides[deps.get_focuser] = lambda: f
        r = client.post("/api/autofocus/sequence", json={
            "start_offset": -100, "end_offset": 100, "step": 50,
        })
        assert r.status_code == 503

    def test_returns_503_when_image_root_unconfigured(self, monkeypatch) -> None:
        f = _mock_focuser(position=1000, max_position=5000)
        app.dependency_overrides[deps.get_focuser] = lambda: f
        monkeypatch.setattr(config, "IMAGE_ROOT", "")
        r = client.post("/api/autofocus/sequence", json={
            "start_offset": -100, "end_offset": 100, "step": 50,
        })
        assert r.status_code == 503

    def test_job_completes_and_writes_position_tagged_fits_files(
        self, tmp_path: Path, monkeypatch,
    ) -> None:
        f = _mock_focuser(position=1000, max_position=5000)
        cam = _mock_camera()
        app.dependency_overrides[deps.get_focuser] = lambda: f
        monkeypatch.setattr(config, "IMAGE_ROOT", str(tmp_path))
        with patch.object(deps, "get_preview_camera", return_value=cam):
            r = client.post("/api/autofocus/sequence", json={
                "start_offset": -50, "end_offset": 50, "step": 50, "exposure": 1.0,
            })
        assert r.status_code == 202
        body = r.json()
        assert body["n_frames"] == 3  # positions: 950, 1000, 1050

        status = _wait_for_job(body["job_id"])
        assert status["status"] == "done"
        assert status["frames_done"] == 3
        assert status["positions"] == [950, 1000, 1050]

        result_dir = Path(status["result_dir"])
        saved = list(result_dir.glob("*.fits"))
        assert len(saved) == 3
        names = {p.name for p in saved}
        assert names == {
            "af-seq_pos-950_000.fits", "af-seq_pos-1000_001.fits", "af-seq_pos-1050_002.fits",
        }

        first_frame = result_dir / "af-seq_pos-950_000.fits"
        with fits.open(first_frame) as hdul:
            assert hdul[0].header["FOCUSPOS"] == 950

    def test_job_fails_gracefully_on_capture_error(self, tmp_path: Path, monkeypatch) -> None:
        f = _mock_focuser(position=1000, max_position=5000)
        cam = _mock_camera()
        cam.capture.side_effect = RuntimeError("camera disconnected")
        app.dependency_overrides[deps.get_focuser] = lambda: f
        monkeypatch.setattr(config, "IMAGE_ROOT", str(tmp_path))
        with patch.object(deps, "get_preview_camera", return_value=cam):
            r = client.post("/api/autofocus/sequence", json={
                "start_offset": -50, "end_offset": 50, "step": 50,
            })
        assert r.status_code == 202
        status = _wait_for_job(r.json()["job_id"])
        assert status["status"] == "failed"
        assert "camera disconnected" in status["error"]


class TestSequenceStatus:
    def test_returns_404_for_unknown_job(self) -> None:
        r = client.get("/api/autofocus/sequence/status/does-not-exist")
        assert r.status_code == 404


class TestFrameMetrics:
    def test_returns_hfd(self) -> None:
        cam = _mock_camera()
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(af_mod.live_analysis_shim, "live_analysis_available", return_value=False),
        ):
            r = client.post("/api/autofocus/frame_metrics", json={"exposure": 1.0})
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body["hfd"], float)
        assert body["stars_found"] is None

    def test_includes_star_count_when_live_analysis_available(self) -> None:
        cam = _mock_camera()
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(af_mod.live_analysis_shim, "live_analysis_available", return_value=True),
            patch.object(af_mod.live_analysis_shim, "build_camera_info", return_value={}),
            patch.object(af_mod.live_analysis_shim, "analyze", return_value={
                "single_frame": {"stars_found": 7, "image_quality": "good"},
            }),
        ):
            r = client.post("/api/autofocus/frame_metrics", json={"exposure": 1.0})
        assert r.status_code == 200
        body = r.json()
        assert body["stars_found"] == 7
        assert body["image_quality"] == "good"

    def test_unknown_camera_role_returns_422(self) -> None:
        reg = MagicMock()
        reg.by_camera_role.return_value = None
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            r = client.post("/api/autofocus/frame_metrics", json={
                "exposure": 1.0, "camera_role": "nope",
            })
        assert r.status_code == 422
