"""WebSocket endpoint for live camera preview."""

from __future__ import annotations

import asyncio
import dataclasses
import io
import json
import logging
import time

import numpy as np

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..domain.autogain import AutoGainController
from ..domain.frame import FitsFrame
from ..domain.histogram import analyze as _hist_analyze
from ..domain.histogram import histogram_bins_focused as _hist_bins
from ..domain.stretch import auto_stretch
from . import deps

_log = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/preview")
async def ws_preview(
    websocket: WebSocket,
    exposure: float = Query(default=2.0, gt=0.0, le=3600.0),
    gain: int = Query(default=100, ge=100, le=15000),
    camera_index: int = Query(default=0, ge=0, le=7),
    autogain: bool = Query(default=False),
    offset: int = Query(default=0, ge=0, le=10000),
    stretch: bool = Query(default=True),
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

    try:
        camera.set_black_level(offset)
    except Exception as exc:
        _log.warning("Preview: set_black_level(%d) failed on camera_index=%d: %s", offset, camera_index, exc)

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
        "requested_gain=%d effective_gain=%d offset=%d stretch=%s",
        getattr(camera, "get_logical_name", lambda: "unknown")(),
        camera_index,
        type(camera).__name__,
        cur_exposure,
        eff_exposure_s,
        cur_gain,
        eff_gain,
        offset,
        stretch,
    )

    cur_bit_depth = 16
    try:
        cur_bit_depth = camera.get_bit_depth()
    except Exception:
        pass

    # Detect colour sensor once; derive Bayer pattern for all frames.
    bayer_pattern = ""
    try:
        if getattr(camera, "is_color_sensor", lambda: False)():
            bayer_pattern = getattr(camera, "get_bayer_pattern", lambda: "RGGB")()
            _log.info(
                "Preview: colour sensor detected on camera_index=%d — Bayer=%s",
                camera_index, bayer_pattern,
            )
    except Exception:
        pass

    # Send one-shot camera identity so the UI can warn if MockCamera is active.
    try:
        await websocket.send_text(json.dumps({
            "type": "camera_info",
            "adapter": type(camera).__name__,
            "name": getattr(camera, "get_logical_name", lambda: "")(),
            "is_color": bool(bayer_pattern),
            "bayer_pattern": bayer_pattern,
        }))
    except Exception:
        pass

    try:
        while True:
            # --- capture frame ---
            _t_capture = time.monotonic()
            try:
                frame: FitsFrame = await asyncio.to_thread(camera.capture, cur_exposure)
            except Exception as exc:
                exc_str = str(exc)
                hex_note = ""
                if exc_str.lstrip("-").isdigit():
                    hex_note = f" (0x{int(exc_str) & 0xFFFFFFFF:08X})"
                _log.error(
                    "Preview: capture failed on camera_index=%d adapter=%s: %s%s",
                    camera_index, type(camera).__name__, exc, hex_note,
                )
                try:
                    await websocket.send_text(f"capture_error: {exc}{hex_note}")
                except Exception:
                    pass
                break
            _dt = time.monotonic() - _t_capture

            # --- STS-ADDON-007: send histogram JSON before the JPEG ---
            stats = None
            try:
                stats = _hist_analyze(frame.pixels, bit_depth=cur_bit_depth)
                counts, edges, adu_hi = _hist_bins(
                    frame.pixels, bit_depth=cur_bit_depth, n_bins=256,
                )
                await websocket.send_text(json.dumps({
                    "type": "histogram",
                    "stats": dataclasses.asdict(stats),
                    "bin_counts": counts,
                    "bin_edges": edges,
                    "hist_adu_hi": adu_hi,
                }))
            except (WebSocketDisconnect, RuntimeError):
                break
            except Exception:
                pass  # histogram failure must never block frame delivery

            _log.info(
                "Preview frame: camera_index=%d adapter=%s capture=%.3fs "
                "exp=%.4fs gain=%d mean_adu=%.0f p99_adu=%.0f sat=%.2f%%",
                camera_index, type(camera).__name__, _dt,
                cur_exposure, cur_gain,
                (stats.mean_frac * stats.adc_max) if stats else 0.0,
                (stats.p99 * stats.adc_max) if stats else 0.0,
                stats.saturation_pct if stats else 0.0,
            )

            # --- encode and send JPEG ---
            try:
                await websocket.send_bytes(
                    _to_jpeg(frame, stretch=stretch, bayer_pattern=bayer_pattern)
                )
            except (WebSocketDisconnect, RuntimeError):
                # Client disconnected or Starlette transport error mid-send
                break

            # --- autogain update ---
            if ctrl is not None:
                prev_exp, prev_gain = ctrl.exposure, ctrl.gain
                ctrl.update(frame.pixels)
                changed = ctrl.exposure != prev_exp or ctrl.gain != prev_gain
                if ctrl.gain != cur_gain:
                    cur_gain = ctrl.gain
                    try:
                        camera.set_gain(cur_gain)
                    except Exception:
                        pass
                cur_exposure = ctrl.exposure
                if changed:
                    _log.info(
                        "Autogain update: camera_index=%d exposure=%.4fs→%.4fs gain=%d→%d",
                        camera_index, prev_exp, cur_exposure, prev_gain, cur_gain,
                    )
                try:
                    await websocket.send_text(json.dumps({
                        "type": "autogain",
                        "exposure": round(cur_exposure, 4),
                        "gain": cur_gain,
                        "changed": changed,
                    }))
                except Exception:
                    pass

    except WebSocketDisconnect:
        pass


def _debayer(raw: np.ndarray, pattern: str) -> np.ndarray:
    """2×2 block-average Bayer demosaic → (H/2, W/2, 3) float32 RGB.

    Half-resolution is acceptable for live preview and needs no extra deps.
    """
    h, w = raw.shape
    h2, w2 = h // 2, w // 2
    if pattern == "RGGB":
        r = raw[0::2, 0::2][:h2, :w2].astype(np.float32)
        g = (raw[0::2, 1::2][:h2, :w2].astype(np.float32) +
             raw[1::2, 0::2][:h2, :w2].astype(np.float32)) * 0.5
        b = raw[1::2, 1::2][:h2, :w2].astype(np.float32)
    elif pattern == "BGGR":
        b = raw[0::2, 0::2][:h2, :w2].astype(np.float32)
        g = (raw[0::2, 1::2][:h2, :w2].astype(np.float32) +
             raw[1::2, 0::2][:h2, :w2].astype(np.float32)) * 0.5
        r = raw[1::2, 1::2][:h2, :w2].astype(np.float32)
    elif pattern == "GRBG":
        g1 = raw[0::2, 0::2][:h2, :w2].astype(np.float32)
        r  = raw[0::2, 1::2][:h2, :w2].astype(np.float32)
        b  = raw[1::2, 0::2][:h2, :w2].astype(np.float32)
        g2 = raw[1::2, 1::2][:h2, :w2].astype(np.float32)
        g  = (g1 + g2) * 0.5
    else:  # GBRG
        g1 = raw[0::2, 0::2][:h2, :w2].astype(np.float32)
        b  = raw[0::2, 1::2][:h2, :w2].astype(np.float32)
        r  = raw[1::2, 0::2][:h2, :w2].astype(np.float32)
        g2 = raw[1::2, 1::2][:h2, :w2].astype(np.float32)
        g  = (g1 + g2) * 0.5
    return np.stack([r, g, b], axis=-1)


def _auto_stretch_color(rgb: np.ndarray) -> np.ndarray:
    """Per-channel percentile auto-stretch (H, W, 3) float32 → uint8."""
    out = np.empty(rgb.shape, dtype=np.uint8)
    for c in range(3):
        ch = rgb[:, :, c]
        lo = float(np.percentile(ch, 0.5))
        hi = float(np.percentile(ch, 99.5))
        if hi > lo:
            scaled = (ch - lo) / (hi - lo) * 255.0
        else:
            # Uniform channel: white = saturated, black = empty
            scaled = np.full_like(ch, 255.0 if lo > 0.0 else 0.0)
        out[:, :, c] = np.clip(scaled, 0.0, 255.0).astype(np.uint8)
    return out


def _to_jpeg(frame: FitsFrame, stretch: bool = True, bayer_pattern: str = "") -> bytes:
    from PIL import Image  # runtime import — keeps startup fast on Pi
    if bayer_pattern:
        # Colour camera: demosaic then per-channel stretch
        rgb = _debayer(frame.pixels, bayer_pattern)
        display = _auto_stretch_color(rgb) if stretch else np.clip(
            rgb / 65535.0 * 255.0, 0.0, 255.0
        ).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(display, mode="RGB").save(buf, format="JPEG", quality=85)
    else:
        # Monochrome camera: existing single-channel path
        if stretch:
            display = auto_stretch(frame.pixels)
        else:
            display = np.clip(
                frame.pixels.astype(np.float64) / 65535.0 * 255.0, 0.0, 255.0
            ).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(display).save(buf, format="JPEG", quality=85)
    return buf.getvalue()
