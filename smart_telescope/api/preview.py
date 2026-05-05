"""WebSocket endpoint for live camera preview."""

from __future__ import annotations

import asyncio
import io

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..domain.autogain import AutoGainController
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
    autogain: bool = Query(default=False),
) -> None:
    """Stream auto-stretched JPEG frames to the client until it disconnects.

    When *autogain* is True the server adaptively adjusts exposure (≤ 4 s) and
    gain (near minimum) after each frame to keep the display well-exposed.
    Raw capture settings for science operations are not affected.
    """
    await websocket.accept()
    try:
        camera = get_preview_camera(camera_index)
    except RuntimeError as exc:
        await websocket.close(code=1011, reason=str(exc))
        return

    ctrl: AutoGainController | None = AutoGainController(exposure, gain) if autogain else None
    cur_exposure = exposure
    cur_gain     = gain

    camera.set_gain(cur_gain)
    try:
        while True:
            frame: FitsFrame = await asyncio.to_thread(camera.capture, cur_exposure)
            await websocket.send_bytes(_to_jpeg(frame))
            if ctrl is not None:
                ctrl.update(frame.pixels)
                if ctrl.gain != cur_gain:
                    cur_gain = ctrl.gain
                    camera.set_gain(cur_gain)
                cur_exposure = ctrl.exposure
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        # Raised by Starlette when the send channel is closed mid-flight
        pass
    except Exception as exc:
        try:
            await websocket.send_text(f"error: {exc}")
        except Exception:
            pass


def _to_jpeg(frame: FitsFrame) -> bytes:
    from PIL import Image  # runtime import — keeps startup fast on Pi
    stretched = auto_stretch(frame.pixels)
    buf = io.BytesIO()
    Image.fromarray(stretched).save(buf, format="JPEG", quality=85)
    return buf.getvalue()
