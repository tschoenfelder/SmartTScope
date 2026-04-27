"""WebSocket live stack viewer — GET /ws/stack.

Streams the current stacked image as JPEG bytes each time a new frame is
integrated.  Also sends a JSON text frame with progress metadata before each
binary JPEG so the client can update a frame counter.

Message sequence per update:
  1. text  → {"frames_integrated": N, "frames_rejected": M}
  2. bytes → JPEG of the current mean stack (auto-stretched)
"""

from __future__ import annotations

import asyncio
import io

from fastapi import APIRouter
from starlette.websockets import WebSocket, WebSocketDisconnect

from ..domain.stretch import auto_stretch
from . import deps

router = APIRouter()

_POLL_INTERVAL_S: float = 2.0


@router.websocket("/ws/stack")
async def ws_stack(websocket: WebSocket) -> None:
    stacker = deps.get_stacker()
    await websocket.accept()
    last_count = -1
    try:
        while True:
            current = stacker.get_current_stack()
            if current.frames_integrated != last_count:
                last_count = current.frames_integrated
                await websocket.send_json({
                    "frames_integrated": current.frames_integrated,
                    "frames_rejected": current.frames_rejected,
                })
                if current.data:
                    await websocket.send_bytes(_to_jpeg(current.data))
            await asyncio.sleep(_POLL_INTERVAL_S)
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass


def _to_jpeg(fits_bytes: bytes) -> bytes:
    import numpy as np
    from astropy.io import fits
    from PIL import Image

    with fits.open(io.BytesIO(fits_bytes)) as hdul:
        pixels = np.array(hdul[0].data, dtype=np.float32)
    stretched = auto_stretch(pixels)
    buf = io.BytesIO()
    Image.fromarray(stretched).save(buf, format="JPEG", quality=85)
    return buf.getvalue()
