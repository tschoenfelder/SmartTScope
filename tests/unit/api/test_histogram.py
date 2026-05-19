"""Unit tests for POST /api/histogram/analyze."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from astropy.io import fits
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CameraPort

client = TestClient(app)

_EXPECTED_FIELDS = {
    "p50", "p95", "p99", "p99_5", "p99_9",
    "mean_frac", "saturation_pct", "zero_clipped_pct",
    "black_level", "effective_bit_depth", "adc_max",
    "bin_counts", "bin_edges",
}


def _mock_camera(pixels: np.ndarray | None = None) -> MagicMock:
    cam = MagicMock(spec=CameraPort)
    if pixels is None:
        rng = np.random.default_rng(0)
        pixels = (rng.random((64, 64)) * 2000).astype(np.float32)
    hdr = fits.Header()
    hdr["EXPTIME"] = 2.0
    cam.capture.return_value = FitsFrame(pixels=pixels, header=hdr, exposure_seconds=2.0)
    return cam


def _post(**params: object) -> object:
    return client.post("/api/histogram/analyze", params=params)


class TestHistogramAnalyzeEndpoint:
    def test_200_on_success(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = _post(camera_index=0, exposure=2.0, gain=200, bit_depth=12)
        assert r.status_code == 200

    def test_all_expected_fields_present(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = _post(camera_index=0, exposure=2.0, gain=200)
        data = r.json()
        assert _EXPECTED_FIELDS.issubset(data.keys())

    def test_bin_counts_length_matches_n_bins_default(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = _post(camera_index=0, exposure=2.0, gain=200)
        data = r.json()
        assert len(data["bin_counts"]) == 512

    def test_bin_edges_length_is_n_bins_plus_one(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = _post(camera_index=0, exposure=2.0, gain=200, n_bins=256)
        data = r.json()
        assert len(data["bin_edges"]) == 257

    def test_custom_n_bins(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = _post(camera_index=0, exposure=2.0, gain=200, n_bins=128)
        assert r.status_code == 200
        assert len(r.json()["bin_counts"]) == 128

    def test_effective_bit_depth_matches_request(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = _post(camera_index=0, exposure=2.0, gain=200, bit_depth=12)
        assert r.json()["effective_bit_depth"] == 12

    def test_adc_max_matches_bit_depth(self) -> None:
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera()):
            r = _post(camera_index=0, exposure=2.0, gain=200, bit_depth=12)
        assert r.json()["adc_max"] == pytest.approx(4095.0)

    def test_gain_forwarded_to_camera(self) -> None:
        cam = _mock_camera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            _post(camera_index=0, exposure=2.0, gain=350)
        cam.set_gain.assert_called_once_with(350)

    def test_zero_frame_saturation_zero(self) -> None:
        cam = _mock_camera(pixels=np.zeros((64, 64), dtype=np.float32))
        with patch.object(deps, "get_preview_camera", return_value=cam):
            r = _post(camera_index=0, exposure=1.0, gain=100)
        assert r.json()["saturation_pct"] == pytest.approx(0.0)

    def test_zero_frame_zero_clipped_100(self) -> None:
        cam = _mock_camera(pixels=np.zeros((64, 64), dtype=np.float32))
        with patch.object(deps, "get_preview_camera", return_value=cam):
            r = _post(camera_index=0, exposure=1.0, gain=100)
        assert r.json()["zero_clipped_pct"] == pytest.approx(100.0)

    def test_503_when_no_camera(self) -> None:
        with patch.object(deps, "get_preview_camera", side_effect=RuntimeError("no camera")):
            r = _post(camera_index=0, exposure=2.0, gain=100)
        assert r.status_code == 503

    def test_503_on_capture_failure(self) -> None:
        cam = MagicMock(spec=CameraPort)
        cam.capture.side_effect = RuntimeError("camera timeout")
        with patch.object(deps, "get_preview_camera", return_value=cam):
            r = _post(camera_index=0, exposure=2.0, gain=100)
        assert r.status_code == 503

    def test_422_on_invalid_exposure(self) -> None:
        r = _post(camera_index=0, exposure=0.0, gain=100)
        assert r.status_code == 422

    def test_422_on_invalid_n_bins(self) -> None:
        r = _post(camera_index=0, exposure=2.0, gain=100, n_bins=10)
        assert r.status_code == 422

    def test_percentile_ordering_in_response(self) -> None:
        rng = np.random.default_rng(7)
        pixels = (rng.random((128, 128)) * 4000).astype(np.float32)
        with patch.object(deps, "get_preview_camera", return_value=_mock_camera(pixels)):
            r = _post(camera_index=0, exposure=2.0, gain=200)
        d = r.json()
        assert d["p50"] <= d["p95"] <= d["p99"] <= d["p99_5"] <= d["p99_9"]
