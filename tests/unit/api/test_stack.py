"""Unit tests for GET /ws/stack WebSocket endpoint."""
import io
import json
from typing import Any
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.ports.stacker import StackedImage, StackerPort

_PIXELS: np.ndarray[Any, np.dtype[Any]] = np.random.default_rng(7).uniform(
    100, 60000, (48, 64)
).astype(np.float32)


def _make_fits_bytes() -> bytes:
    from astropy.io import fits

    hdu = fits.PrimaryHDU(data=_PIXELS)
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    return buf.getvalue()


def _make_stacker(frames: int = 1, with_data: bool = True) -> MagicMock:
    stk = MagicMock(spec=StackerPort)
    stk.get_current_stack.return_value = StackedImage(
        data=_make_fits_bytes() if with_data else b"",
        frames_integrated=frames,
        frames_rejected=0,
    )
    return stk


@pytest.fixture(autouse=True)
def _reset_deps() -> Any:
    deps.reset()
    yield
    deps.reset()


@pytest.fixture()
def stack_client() -> TestClient:
    stk = _make_stacker(frames=3)
    with (
        patch("smart_telescope.api.stack.deps.get_stacker", return_value=stk),
        patch("smart_telescope.api.stack._POLL_INTERVAL_S", 0.0),
    ):
        yield TestClient(app)


# ── connection ────────────────────────────────────────────────────────────────


class TestWsStackConnection:
    def test_connection_accepted(self, stack_client: TestClient) -> None:
        with stack_client.websocket_connect("/ws/stack"):
            pass

    def test_endpoint_is_registered(self) -> None:
        routes = [r.path for r in app.routes]  # type: ignore[attr-defined]
        assert "/ws/stack" in routes


# ── message structure ─────────────────────────────────────────────────────────


class TestWsStackMessages:
    def test_receives_json_then_bytes(self, stack_client: TestClient) -> None:
        with stack_client.websocket_connect("/ws/stack") as ws:
            meta = ws.receive_text()
            data = ws.receive_bytes()
        assert isinstance(json.loads(meta), dict)
        assert isinstance(data, bytes) and len(data) > 0

    def test_json_contains_required_keys(self, stack_client: TestClient) -> None:
        with stack_client.websocket_connect("/ws/stack") as ws:
            meta = ws.receive_text()
        payload = json.loads(meta)
        assert "frames_integrated" in payload
        assert "frames_rejected" in payload

    def test_frames_integrated_matches_stacker(self) -> None:
        stk = _make_stacker(frames=7)
        with (
            patch("smart_telescope.api.stack.deps.get_stacker", return_value=stk),
            patch("smart_telescope.api.stack._POLL_INTERVAL_S", 0.0),
            TestClient(app).websocket_connect("/ws/stack") as ws,
        ):
            meta = ws.receive_text()
        assert json.loads(meta)["frames_integrated"] == 7

    def test_bytes_is_valid_jpeg(self, stack_client: TestClient) -> None:
        with stack_client.websocket_connect("/ws/stack") as ws:
            ws.receive_text()
            data = ws.receive_bytes()
        assert data[:2] == b"\xff\xd8", "Missing JPEG SOI marker"
        assert data[-2:] == b"\xff\xd9", "Missing JPEG EOI marker"

    def test_no_bytes_when_data_is_empty(self) -> None:
        stk = _make_stacker(frames=1, with_data=False)
        with (
            patch("smart_telescope.api.stack.deps.get_stacker", return_value=stk),
            patch("smart_telescope.api.stack._POLL_INTERVAL_S", 0.0),
            TestClient(app).websocket_connect("/ws/stack") as ws,
        ):
            meta = ws.receive_text()
            # Next message must be the second poll's JSON (count unchanged → no more sends)
            # The loop will sleep and re-poll; since count didn't change, nothing else is sent.
            # Closing the connection here should not raise.
        assert json.loads(meta)["frames_integrated"] == 1


# ── _to_jpeg helper ───────────────────────────────────────────────────────────


class TestToJpeg:
    def test_converts_fits_bytes_to_jpeg(self) -> None:
        from smart_telescope.api.stack import _to_jpeg

        result = _to_jpeg(_make_fits_bytes())
        assert result[:2] == b"\xff\xd8"
        assert result[-2:] == b"\xff\xd9"

    def test_output_is_decodable_image(self) -> None:
        from PIL import Image

        from smart_telescope.api.stack import _to_jpeg

        result = _to_jpeg(_make_fits_bytes())
        img = Image.open(io.BytesIO(result))
        assert img.format == "JPEG"
        assert img.size == (_PIXELS.shape[1], _PIXELS.shape[0])
