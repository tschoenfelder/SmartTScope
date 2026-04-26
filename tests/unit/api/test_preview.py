"""Unit tests for GET /ws/preview WebSocket endpoint."""
import io
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from starlette.websockets import WebSocketDisconnect

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.ports.camera import CameraPort

_SMALL_PIXELS: np.ndarray[Any, np.dtype[Any]] = np.random.default_rng(42).uniform(
    100, 60000, (48, 64)
).astype(np.float32)


def _small_frame(exposure: float = 2.0) -> FitsFrame:
    return FitsFrame(pixels=_SMALL_PIXELS, header={}, exposure_seconds=exposure)


def _make_cam() -> MagicMock:
    cam = MagicMock(spec=CameraPort)
    cam.capture.return_value = _small_frame()
    return cam


@pytest.fixture(autouse=True)
def _reset_deps() -> Any:
    deps.reset()
    yield
    deps.reset()


@pytest.fixture()
def preview_client() -> TestClient:
    with patch("smart_telescope.api.preview.get_camera", return_value=_make_cam()):
        yield TestClient(app)


# ── connection ────────────────────────────────────────────────────────────────


class TestWsPreviewConnection:
    def test_connection_accepted(self, preview_client: TestClient) -> None:
        with preview_client.websocket_connect("/ws/preview"):
            pass

    def test_custom_exposure_accepted(self, preview_client: TestClient) -> None:
        with preview_client.websocket_connect("/ws/preview?exposure=5.0"):
            pass

    def test_max_exposure_accepted(self, preview_client: TestClient) -> None:
        with preview_client.websocket_connect("/ws/preview?exposure=60.0"):
            pass


# ── frame content ─────────────────────────────────────────────────────────────


class TestWsPreviewFrames:
    def test_receives_bytes(self, preview_client: TestClient) -> None:
        with preview_client.websocket_connect("/ws/preview") as ws:
            data = ws.receive_bytes()
        assert isinstance(data, bytes) and len(data) > 0

    def test_frame_is_valid_jpeg(self, preview_client: TestClient) -> None:
        with preview_client.websocket_connect("/ws/preview") as ws:
            data = ws.receive_bytes()
        assert data[:2] == b"\xff\xd8", "Missing JPEG SOI marker"
        assert data[-2:] == b"\xff\xd9", "Missing JPEG EOI marker"

    def test_jpeg_is_decodable(self, preview_client: TestClient) -> None:
        with preview_client.websocket_connect("/ws/preview") as ws:
            data = ws.receive_bytes()
        img = Image.open(io.BytesIO(data))
        assert img.format == "JPEG"

    def test_jpeg_dimensions_match_frame(self, preview_client: TestClient) -> None:
        with preview_client.websocket_connect("/ws/preview") as ws:
            data = ws.receive_bytes()
        img = Image.open(io.BytesIO(data))
        height, width = _SMALL_PIXELS.shape
        assert img.size == (width, height)

    def test_multiple_frames_received(self, preview_client: TestClient) -> None:
        with preview_client.websocket_connect("/ws/preview") as ws:
            frames = [ws.receive_bytes() for _ in range(3)]
        assert len(frames) == 3
        assert all(f[:2] == b"\xff\xd8" for f in frames)

    def test_camera_called_with_exposure(self) -> None:
        cam = _make_cam()
        cam.capture.return_value = _small_frame(5.0)
        with (
            patch("smart_telescope.api.preview.get_camera", return_value=cam),
            TestClient(app).websocket_connect("/ws/preview?exposure=5.0") as ws,
        ):
            ws.receive_bytes()
        cam.capture.assert_called_with(5.0)


# ── query param validation ────────────────────────────────────────────────────


class TestWsPreviewParams:
    def test_zero_exposure_rejected(self, preview_client: TestClient) -> None:
        with pytest.raises(WebSocketDisconnect), \
                preview_client.websocket_connect("/ws/preview?exposure=0") as ws:
            ws.receive_bytes()

    def test_negative_exposure_rejected(self, preview_client: TestClient) -> None:
        with pytest.raises(WebSocketDisconnect), \
                preview_client.websocket_connect("/ws/preview?exposure=-1") as ws:
            ws.receive_bytes()

    def test_exposure_above_60_rejected(self, preview_client: TestClient) -> None:
        with pytest.raises(WebSocketDisconnect), \
                preview_client.websocket_connect("/ws/preview?exposure=61") as ws:
            ws.receive_bytes()
