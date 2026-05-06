"""Unit tests for /api/calibration endpoints (AGT-3-1, AGT-3-2)."""
from __future__ import annotations

import io
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient

from smart_telescope.api import calibration as cal_mod
from smart_telescope.app import app

client = TestClient(app)


# ── helpers ───────────────────────────────────────────────────────────────────


def _write_fits(path: Path, value: int = 150) -> None:
    pixels = np.full((32, 32), value, dtype=np.uint16)
    hdu = fits.PrimaryHDU(data=pixels)
    buf = io.BytesIO()
    hdu.writeto(buf)
    path.write_bytes(buf.getvalue())


def _wait_for_job(job_id: str, timeout: float = 5.0, interval: float = 0.05) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/api/calibration/status/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        if data["status"] in ("done", "failed"):
            return data
        time.sleep(interval)
    raise TimeoutError(f"Job {job_id} did not finish within {timeout}s")


# ── POST /api/calibration/bias ────────────────────────────────────────────────


class TestBiasStart:
    def setup_method(self) -> None:
        cal_mod._reset_jobs()

    def test_returns_202(self, tmp_path: Path) -> None:
        fits_path = tmp_path / "f.fits"
        _write_fits(fits_path)
        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps
        from smart_telescope.domain.calibration_store import CalibrationIndex

        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
            patch.object(cal_mod, "CalibrationIndex") as mock_idx_cls,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            mock_idx_cls.load.return_value = CalibrationIndex(tmp_path)
            resp = client.post("/api/calibration/bias", json={"n_frames": 2})
        assert resp.status_code == 202

    def test_returns_job_id(self, tmp_path: Path) -> None:
        fits_path = tmp_path / "f.fits"
        _write_fits(fits_path)
        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps
        from smart_telescope.domain.calibration_store import CalibrationIndex

        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
            patch.object(cal_mod, "CalibrationIndex") as mock_idx_cls,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            mock_idx_cls.load.return_value = CalibrationIndex(tmp_path)
            data = client.post("/api/calibration/bias", json={"n_frames": 2}).json()
        assert "job_id" in data
        assert len(data["job_id"]) > 0

    def test_503_when_image_root_not_configured(self) -> None:
        with patch.object(cal_mod, "config") as mock_cfg:
            mock_cfg.IMAGE_ROOT = ""
            resp = client.post("/api/calibration/bias", json={})
        assert resp.status_code == 503

    def test_422_on_invalid_conversion_gain(self, tmp_path: Path) -> None:
        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps

        fits_path = tmp_path / "f.fits"
        _write_fits(fits_path)
        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            resp = client.post(
                "/api/calibration/bias",
                json={"n_frames": 2, "conversion_gain": "INVALID"},
            )
        assert resp.status_code == 422


# ── GET /api/calibration/status/{job_id} ─────────────────────────────────────


class TestJobStatus:
    def setup_method(self) -> None:
        cal_mod._reset_jobs()

    def test_404_for_unknown_job(self) -> None:
        resp = client.get("/api/calibration/status/nonexistent-id")
        assert resp.status_code == 404

    def test_job_completes_successfully(self, tmp_path: Path) -> None:
        fits_path = tmp_path / "f.fits"
        _write_fits(fits_path)
        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps
        from smart_telescope.domain.calibration_store import CalibrationIndex

        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
            patch.object(cal_mod, "CalibrationIndex") as mock_idx_cls,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            mock_idx_cls.load.return_value = CalibrationIndex(tmp_path)
            resp = client.post("/api/calibration/bias", json={"n_frames": 1})
        job_id = resp.json()["job_id"]

        result = _wait_for_job(job_id)
        assert result["status"] == "done"

    def test_done_job_has_result_path(self, tmp_path: Path) -> None:
        fits_path = tmp_path / "f.fits"
        _write_fits(fits_path)
        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps
        from smart_telescope.domain.calibration_store import CalibrationIndex

        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
            patch.object(cal_mod, "CalibrationIndex") as mock_idx_cls,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            mock_idx_cls.load.return_value = CalibrationIndex(tmp_path)
            job_id = client.post("/api/calibration/bias", json={"n_frames": 1}).json()["job_id"]

        result = _wait_for_job(job_id)
        assert result["result_path"] is not None
        assert result["result_path"].endswith(".fits")

    def test_job_fails_on_zero_pixels(self, tmp_path: Path) -> None:
        fits_path = tmp_path / "zero.fits"
        pixels = np.zeros((32, 32), dtype=np.uint16)
        hdu = fits.PrimaryHDU(data=pixels)
        buf = io.BytesIO()
        hdu.writeto(buf)
        fits_path.write_bytes(buf.getvalue())

        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps
        from smart_telescope.domain.calibration_store import CalibrationIndex

        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
            patch.object(cal_mod, "CalibrationIndex") as mock_idx_cls,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            mock_idx_cls.load.return_value = CalibrationIndex(tmp_path)
            job_id = client.post("/api/calibration/bias", json={"n_frames": 1}).json()["job_id"]

        result = _wait_for_job(job_id)
        assert result["status"] == "failed"
        assert result["error"] is not None

    def test_frames_done_increments(self, tmp_path: Path) -> None:
        """frames_done should reach n_frames when done."""
        fits_path = tmp_path / "f.fits"
        _write_fits(fits_path)
        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps
        from smart_telescope.domain.calibration_store import CalibrationIndex

        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
            patch.object(cal_mod, "CalibrationIndex") as mock_idx_cls,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            mock_idx_cls.load.return_value = CalibrationIndex(tmp_path)
            job_id = client.post("/api/calibration/bias", json={"n_frames": 3}).json()["job_id"]

        result = _wait_for_job(job_id)
        assert result["frames_done"] == 3


# ── POST /api/calibration/dark ────────────────────────────────────────────────


class TestDarkStart:
    def setup_method(self) -> None:
        cal_mod._reset_jobs()

    def _start_dark(self, tmp_path: Path, **extra) -> str:
        fits_path = tmp_path / "f.fits"
        _write_fits(fits_path)
        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps
        from smart_telescope.domain.calibration_store import CalibrationIndex

        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
            patch.object(cal_mod, "CalibrationIndex") as mock_idx_cls,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            mock_idx_cls.load.return_value = CalibrationIndex(tmp_path)
            payload = {"n_frames": 1, "exposure_ms": 2000.0, **extra}
            resp = client.post("/api/calibration/dark", json=payload)
        return resp

    def test_returns_202(self, tmp_path: Path) -> None:
        assert self._start_dark(tmp_path).status_code == 202

    def test_returns_job_id(self, tmp_path: Path) -> None:
        data = self._start_dark(tmp_path).json()
        assert "job_id" in data

    def test_503_when_image_root_not_configured(self) -> None:
        with patch.object(cal_mod, "config") as mock_cfg:
            mock_cfg.IMAGE_ROOT = ""
            resp = client.post("/api/calibration/dark", json={"exposure_ms": 1000.0})
        assert resp.status_code == 503

    def test_422_on_invalid_conversion_gain(self, tmp_path: Path) -> None:
        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps

        fits_path = tmp_path / "f.fits"
        _write_fits(fits_path)
        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            resp = client.post(
                "/api/calibration/dark",
                json={"exposure_ms": 2000.0, "n_frames": 1, "conversion_gain": "BAD"},
            )
        assert resp.status_code == 422

    def test_dark_job_completes(self, tmp_path: Path) -> None:
        job_id = self._start_dark(tmp_path).json()["job_id"]
        result = _wait_for_job(job_id)
        assert result["status"] == "done"

    def test_dark_result_path_is_fits(self, tmp_path: Path) -> None:
        job_id = self._start_dark(tmp_path).json()["job_id"]
        result = _wait_for_job(job_id)
        assert result["result_path"].endswith(".fits")

    def test_dark_job_fails_on_saturated_pixels(self, tmp_path: Path) -> None:
        fits_path = tmp_path / "sat.fits"
        pixels = np.full((32, 32), 65535, dtype=np.uint16)
        hdu = fits.PrimaryHDU(data=pixels)
        buf = io.BytesIO()
        hdu.writeto(buf)
        fits_path.write_bytes(buf.getvalue())

        from smart_telescope.adapters.replay.camera import ReplayCamera
        from smart_telescope.api import deps
        from smart_telescope.domain.calibration_store import CalibrationIndex

        cam = ReplayCamera([str(fits_path)])
        with (
            patch.object(deps, "get_preview_camera", return_value=cam),
            patch.object(cal_mod, "config") as mock_cfg,
            patch.object(cal_mod, "CalibrationIndex") as mock_idx_cls,
        ):
            mock_cfg.IMAGE_ROOT = str(tmp_path)
            mock_idx_cls.load.return_value = CalibrationIndex(tmp_path)
            job_id = client.post(
                "/api/calibration/dark", json={"n_frames": 1, "exposure_ms": 2000.0}
            ).json()["job_id"]

        result = _wait_for_job(job_id)
        assert result["status"] == "failed"

    def test_status_response_has_warning_field(self, tmp_path: Path) -> None:
        job_id = self._start_dark(tmp_path).json()["job_id"]
        result = _wait_for_job(job_id)
        assert "warning" in result
