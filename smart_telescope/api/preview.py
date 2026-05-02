"""WebSocket endpoint for live camera preview."""

from __future__ import annotations

import asyncio
import io

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..domain.frame import FitsFrame
from ..domain.stretch import auto_stretch
from .deps import get_preview_camera

router = APIRouter()


@router.websocket("/ws/preview")
async def ws_preview(
    websocket: WebSocket,
    exposure: float = Query(default=2.0, gt=0.0, le=60.0),
    gain: int = Query(default=100, ge=100, le=3200),
    camera_index: int = Query(default=0, ge=0, le=7),
) -> None:
    """Stream auto-stretched JPEG frames to the client until it disconnects."""
    await websocket.accept()
    try:
        camera = get_preview_camera(camera_index)
    except RuntimeError as exc:
        await websocket.close(code=1011, reason=str(exc))
        return
    if hasattr(camera, "set_gain"):
        camera.set_gain(gain)  # type: ignore[union-attr]
    try:
        while True:
            frame: FitsFrame = await asyncio.to_thread(camera.capture, exposure)
            await websocket.send_bytes(_to_jpeg(frame))
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Raised by Starlette when the send channel is closed mid-flight
        pass


def _to_jpeg(frame: FitsFrame) -> bytes:
    from PIL import Image  # runtime import — keeps startup fast on Pi
    stretched = auto_stretch(frame.pixels)
    buf = io.BytesIO()
    Image.fromarray(stretched).save(buf, format="JPEG", quality=85)
    return buf.getvalue()
