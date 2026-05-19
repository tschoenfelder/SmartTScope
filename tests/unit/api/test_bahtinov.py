"""Unit tests for POST /api/bahtinov/analyze."""

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


def _mock_camera(pixels: np.ndarray | None = None) -> MagicMock:
    c = MagicMock(spec=CameraPort)
    if pixels is None:
        rng = np.random.default_rng(42)
        pixels = rng.random((64, 64)).astype(np.float32)
    hdr = fits.Header()
    hdr["EXPTIME"] = 0.5
    c.capture.return_value = FitsFrame(pixels=pixels, header=hdr, exposure_seconds=0.5)
    return c


def _make_pixels_with_spikes() -> np.ndarray:
    """512×512 frame with a synthetic bright star and three spike lines."""
    img = np.zeros((512, 512), dtype=np.float32)
    cx, cy = 256, 256

    # Bright star core
    for dy in range(-8, 9):
        for dx in range(-8, 9):
            r = (dx**2 + dy**2) ** 0.5
            img[cy + dy, cx + dx] = max(0.0, 1.0 - r / 8.0)

    # Three spike lines through (cx, cy) at -20°, 0°, +20° from vertical
    import math
    for angle_deg in (-20, 0, 20):
        angle = math.radians(angle_deg)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        for t in range(-200, 201):
            x = int(cx + t * sin_a)
            y = int(cy + t * cos_a)
            if 0 <= x < 512 and 0 <= y < 512:
                img[y, x] = max(img[y, x], 0.8)

    return img


@pytest.fixture(autouse=True)
def _reset_deps() -> None:
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


def _inject(camera: MagicMock) -> None:
    app.dependency_overrides[deps.get_camera] = lambda: camera


# ── POST /api/bahtinov/analyze ─────────────────────────────────────────────────


class TestBahtinovAnalyzeError:
    def test_returns_422_when_spikes_not_detected(self) -> None:
        """All-zero frame → no pixels above threshold → 0 lines → 422."""
        c = _mock_camera(pixels=np.zeros((64, 64), dtype=np.float32))
        _inject(c)
        resp = client.post("/api/bahtinov/analyze", json={"exposure": 0.5, "gain": 100})
        assert resp.status_code == 422

    def test_error_detail_mentions_spike_count(self) -> None:
        c = _mock_camera(pixels=np.zeros((64, 64), dtype=np.float32))
        _inject(c)
        detail = client.post("/api/bahtinov/analyze", json={}).json()["detail"]
        assert "spike" in detail.lower() or "line" in detail.lower()

    def test_camera_capture_called_with_exposure(self) -> None:
        c = _mock_camera()
        _inject(c)
        client.post("/api/bahtinov/analyze", json={"exposure": 1.5, "gain": 200})
        c.capture.assert_called_once_with(exposure_seconds=1.5)

    def test_uses_default_exposure_when_body_empty(self) -> None:
        c = _mock_camera()
        _inject(c)
        client.post("/api/bahtinov/analyze", json={})
        c.capture.assert_called_once_with(exposure_seconds=0.5)


class TestBahtinovAnalyzeSuccess:
    def test_returns_200_with_spike_image(self) -> None:
        pixels = _make_pixels_with_spikes()
        c = _mock_camera(pixels)
        _inject(c)
        resp = client.post("/api/bahtinov/analyze", json={"exposure": 0.5, "gain": 100})
        assert resp.status_code == 200

    def test_response_has_required_keys(self) -> None:
        pixels = _make_pixels_with_spikes()
        c = _mock_camera(pixels)
        _inject(c)
        data = client.post("/api/bahtinov/analyze", json={}).json()
        for key in (
            "focus_error_px", "crossing_error_rms_px", "detection_confidence",
            "object_center_px", "common_crossing_point_px", "pairwise_intersections_px",
            "lines", "image_size_px",
        ):
            assert key in data, f"Missing key: {key}"

    def test_image_size_px_matches_frame(self) -> None:
        pixels = _make_pixels_with_spikes()  # 512×512
        c = _mock_camera(pixels)
        _inject(c)
        data = client.post("/api/bahtinov/analyze", json={}).json()
        assert data["image_size_px"] == [512, 512]

    def test_lines_contains_exactly_three(self) -> None:
        pixels = _make_pixels_with_spikes()
        c = _mock_camera(pixels)
        _inject(c)
        data = client.post("/api/bahtinov/analyze", json={}).json()
        assert len(data["lines"]) == 3

    def test_each_line_has_required_fields(self) -> None:
        pixels = _make_pixels_with_spikes()
        c = _mock_camera(pixels)
        _inject(c)
        data = client.post("/api/bahtinov/analyze", json={}).json()
        for line in data["lines"]:
            for field in ("a", "b", "c", "angle_deg", "confidence"):
                assert field in line

    def test_focus_error_is_numeric(self) -> None:
        pixels = _make_pixels_with_spikes()
        c = _mock_camera(pixels)
        _inject(c)
        data = client.post("/api/bahtinov/analyze", json={}).json()
        assert isinstance(data["focus_error_px"], float | int)

    def test_detection_confidence_in_0_1(self) -> None:
        pixels = _make_pixels_with_spikes()
        c = _mock_camera(pixels)
        _inject(c)
        data = client.post("/api/bahtinov/analyze", json={}).json()
        assert 0.0 <= data["detection_confidence"] <= 1.0

    def test_mocked_analyzer_success_path(self) -> None:
        """Verify the endpoint returns analyzer output when analyzer succeeds."""
        from smart_telescope.domain.bahtinov import CrossingAnalysisResult, SpikeLine

        fake_result = CrossingAnalysisResult(
            object_center_px=(100.0, 100.0),
            lines=[
                SpikeLine(a=0.0, b=1.0, c=-100.0, angle_deg=0.0, confidence=1000.0),
                SpikeLine(a=0.34, b=0.94, c=-130.0, angle_deg=20.0, confidence=900.0),
                SpikeLine(a=-0.34, b=0.94, c=-70.0, angle_deg=160.0, confidence=900.0),
            ],
            common_crossing_point_px=(100.0, 100.0),
            pairwise_intersections_px=[(100.0, 100.0)] * 3,
            crossing_error_rms_px=1.5,
            crossing_error_max_px=2.0,
            focus_error_px=5.2,
            detection_confidence=0.9,
        )

        c = _mock_camera()
        _inject(c)
        with patch(
            "smart_telescope.api.bahtinov.BahtinovAnalyzer.analyze",
            return_value=fake_result,
        ):
            resp = client.post("/api/bahtinov/analyze", json={"exposure": 0.5, "gain": 100})
        assert resp.status_code == 200
        data = resp.json()
        assert data["focus_error_px"] == pytest.approx(5.2, abs=0.1)
        assert data["image_size_px"] == [64, 64]
