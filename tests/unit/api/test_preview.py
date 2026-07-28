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
    with patch("smart_telescope.api.deps.get_preview_camera", return_value=_make_cam()):
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
            patch("smart_telescope.api.deps.get_preview_camera", return_value=cam),
            TestClient(app).websocket_connect("/ws/preview?exposure=5.0") as ws,
        ):
            ws.receive_bytes()
        cam.capture.assert_called_with(5.0)

    def test_camera_index_passed_to_get_preview_camera(self) -> None:
        cam = _make_cam()
        with patch("smart_telescope.api.deps.get_preview_camera", return_value=cam) as mock_get:
            with TestClient(app).websocket_connect("/ws/preview?camera_index=1") as ws:
                ws.receive_bytes()
        mock_get.assert_called_once_with(1)


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

    def test_exposure_above_3600_rejected(self, preview_client: TestClient) -> None:
        with pytest.raises(WebSocketDisconnect), \
                preview_client.websocket_connect("/ws/preview?exposure=3601") as ws:
            ws.receive_bytes()


# ── concurrent-connection race (M10-05x) ───────────────────────────────────────


class TestWsPreviewSingleOwner:
    def test_second_connection_aborts_the_first(self) -> None:
        cam = _make_cam()
        with patch("smart_telescope.api.deps.get_preview_camera", return_value=cam):
            client = TestClient(app)
            with client.websocket_connect("/ws/preview?camera_index=0") as ws1:
                ws1.receive_bytes()  # first connection is up and streaming
                cam.abort_capture.assert_not_called()

                with client.websocket_connect("/ws/preview?camera_index=0") as ws2:
                    ws2.receive_bytes()
                    # the new connection for the same camera_index must have
                    # signaled the old one to stop instead of racing it
                    cam.abort_capture.assert_called()

    def test_different_camera_indexes_do_not_interact(self) -> None:
        cam = _make_cam()
        with patch("smart_telescope.api.deps.get_preview_camera", return_value=cam):
            client = TestClient(app)
            with client.websocket_connect("/ws/preview?camera_index=0") as ws1:
                ws1.receive_bytes()
                with client.websocket_connect("/ws/preview?camera_index=1") as ws2:
                    ws2.receive_bytes()
                    cam.abort_capture.assert_not_called()
                    # both connections keep receiving frames independently
                    ws1.receive_bytes()
                    ws2.receive_bytes()

    def test_superseded_connection_closes_with_clean_code(self) -> None:
        # M10-05x follow-up: a superseded connection must close with code
        # 1000 ("normal closure"). Every client-side reconnect guard in this
        # codebase (autofocus.js, preview.js) only skips reconnecting on
        # exactly this code — anything else (e.g. the 1006 the ASGI layer
        # sends by default when a handler just returns) makes the loser
        # immediately reconnect and re-supersede the winner, producing a
        # continuous reconnect loop between two screens instead of one clean
        # handoff.
        cam = _make_cam()
        with patch("smart_telescope.api.deps.get_preview_camera", return_value=cam):
            client = TestClient(app)
            with client.websocket_connect("/ws/preview?camera_index=0") as ws1:
                ws1.receive_bytes()
                with client.websocket_connect("/ws/preview?camera_index=0"):
                    with pytest.raises(WebSocketDisconnect) as exc_info:
                        while True:
                            ws1.receive_bytes()
                    assert exc_info.value.code == 1000

    def test_registry_entry_cleared_after_normal_close(self) -> None:
        from smart_telescope.api import preview as preview_module

        cam = _make_cam()
        with patch("smart_telescope.api.deps.get_preview_camera", return_value=cam):
            client = TestClient(app)
            with client.websocket_connect("/ws/preview?camera_index=0") as ws:
                ws.receive_bytes()
            # connection closed cleanly — a fresh one must not be treated as
            # superseding a stale entry that was never cleaned up
            with client.websocket_connect("/ws/preview?camera_index=0") as ws2:
                ws2.receive_bytes()
                assert preview_module._active_preview_owner[0]["superseded"] is False
