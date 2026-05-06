"""WebSocket endpoint for live camera preview."""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..domain.autogain import AutoGainController
from ..domain.frame import FitsFrame
from ..domain.histogram import analyze as _hist_analyze
from ..domain.histogram import histogram_bins as _hist_bins
from ..domain.stretch import auto_stretch
from . import deps

_log = logging.getLogger(__name__)

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
    _log.info(
        "Preview WS accepted: camera_index=%d exposure=%.3f gain=%d autogain=%s",
        camera_index, exposure, gain, autogain,
    )

    try:
        camera = deps.get_preview_camera(camera_index)
    except RuntimeError as exc:
        _log.error("Preview: camera_index=%d unavailable: %s", camera_index, exc)
        # Send reason as text before closing so the UI status bar shows it
        try:
            await websocket.send_text(f"camera_error: {exc}")
        except Exception:
            pass
        await websocket.close(code=1011, reason=str(exc)[:123])
        return

    ctrl: AutoGainController | None = AutoGainController(exposure, gain) if autogain else None
    cur_exposure = exposure
    cur_gain     = gain

    try:
        camera.set_gain(cur_gain)
    except Exception as exc:
        _log.warning("Preview: set_gain(%d) failed on camera_index=%d: %s", cur_gain, camera_index, exc)

    # Read back effective gain (camera may clamp the requested value)
    eff_gain = cur_gain
    try:
        eff_gain = camera.get_gain()
    except Exception:
        pass

    # Set and read back effective exposure so the log matches what the camera will use
    try:
        camera.set_exposure_ms(cur_exposure * 1000.0)
    except Exception:
        pass
    eff_exposure_s = cur_exposure
    try:
        eff_exposure_s = camera.get_exposure_ms() / 1000.0
    except Exception:
        pass

    # STS-ADDON-005: log camera identity and all effective settings
    _log.info(
        "Preview started: camera=%s camera_index=%d adapter=%s "
        "requested_exposure_s=%.3f effective_exposure_s=%.3f "
        "requested_gain=%d effective_gain=%d",
        getattr(camera, "get_logical_name", lambda: "unknown")(),
        camera_index,
        type(camera).__name__,
        cur_exposure,
        eff_exposure_s,
        cur_gain,
        eff_gain,
    )

    cur_bit_depth = 16
    try:
        cur_bit_depth = camera.get_bit_depth()
    except Exception:
        pass

    try:
        while True:
            # --- capture frame ---
            try:
                frame: FitsFrame = await asyncio.to_thread(camera.capture, cur_exposure)
            except Exception as exc:
                _log.error(
                    "Preview: capture failed on camera_index=%d adapter=%s: %s",
                    camera_index, type(camera).__name__, exc,
                )
                try:
                    await websocket.send_text(f"capture_error: {exc}")
                except Exception:
                    pass
                break

            # --- STS-ADDON-007: send histogram JSON before the JPEG ---
            try:
                stats = _hist_analyze(frame.pixels, bit_depth=cur_bit_depth)
                counts, edges = _hist_bins(frame.pixels, bit_depth=cur_bit_depth, n_bins=128)
                await websocket.send_text(json.dumps({
                    "type": "histogram",
                    "stats": dataclasses.asdict(stats),
                    "bin_counts": counts,
                    "bin_edges": edges,
                }))
            except (WebSocketDisconnect, RuntimeError):
                break
            except Exception:
                pass  # histogram failure must never block frame delivery

            # --- encode and send JPEG ---
            try:
                await websocket.send_bytes(_to_jpeg(frame))
            except (WebSocketDisconnect, RuntimeError):
                # Client disconnected or Starlette transport error mid-send
                break

            # --- autogain update ---
            if ctrl is not None:
                ctrl.update(frame.pixels)
                if ctrl.gain != cur_gain:
                    cur_gain = ctrl.gain
                    try:
                        camera.set_gain(cur_gain)
                    except Exception:
                        pass
                cur_exposure = ctrl.exposure

    except WebSocketDisconnect:
        pass


def _to_jpeg(frame: FitsFrame) -> bytes:
    from PIL import Image  # runtime import — keeps startup fast on Pi
    stretched = auto_stretch(frame.pixels)
    buf = io.BytesIO()
    Image.fromarray(stretched).save(buf, format="JPEG", quality=85)
    return buf.getvalue()
