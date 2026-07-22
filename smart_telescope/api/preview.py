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

from ..domain.autogain import AutoGainController, AutoGainMode
from ..domain.frame import FitsFrame
from ..domain.histogram import analyze as _hist_analyze
from ..domain.histogram import histogram_bins_focused as _hist_bins
from ..domain.stretch import auto_stretch
from . import deps

_log = logging.getLogger(__name__)

router = APIRouter()

# Latest preview pixels per camera_index — populated after each capture.
# Used by click-to-center refinement (M8-026).
_last_preview_pixels: dict[int, "np.ndarray"] = {}


def get_last_preview_pixels(camera_index: int) -> "np.ndarray | None":
    """Return the most recent preview frame pixels for the given camera index, or None."""
    return _last_preview_pixels.get(camera_index)


@router.websocket("/ws/preview")
async def ws_preview(
    websocket: WebSocket,
    exposure: float = Query(default=2.0, gt=0.0, le=3600.0),
    gain: int = Query(default=100, ge=100, le=15000),
    camera_index: int = Query(default=0, ge=0, le=7),
    camera_role: str = Query(default=""),
    autogain: bool = Query(default=False),
    offset: int = Query(default=0, ge=0, le=65535),
    stretch: bool = Query(default=True),
) -> None:
    """Stream auto-stretched JPEG frames to the client until it disconnects.

    When *autogain* is True the server adaptively adjusts exposure (≤ 4 s) and
    gain (near minimum) after each frame to keep the display well-exposed.
    Raw capture settings for science operations are not affected.
    """
    await websocket.accept()

    # Resolve camera_role → camera instance (R4-005: role-based selection).
    # When cameras are identified by model name (no explicit SDK index in config),
    # all optical trains default to camera_index=0 in the registry, causing every
    # train to open the same physical camera.  Use get_camera_by_role() instead so
    # model-matching (SmartTouptekCamera) finds the correct device.
    _pre_resolved_camera = None
    if camera_role:
        try:
            registry = deps.get_optical_train_registry()
            train = registry.by_camera_role(camera_role) or registry.get(camera_role)
            if train is not None:
                camera_index = train.camera_index  # kept for logging / fallback
                _role_key = train.camera_role
                try:
                    # Run in a thread: first call may connect the camera (blocking SDK I/O).
                    _pre_resolved_camera = await asyncio.to_thread(
                        deps.get_camera_by_role, _role_key
                    )
                    _log.info(
                        "Preview WS: resolved camera_role=%r → train=%r role_key=%r adapter=%s",
                        camera_role, train.name, _role_key,
                        type(_pre_resolved_camera).__name__,
                    )
                except Exception as exc:
                    _log.warning(
                        "Preview WS: role-based resolution failed for %r → fallback camera_index=%d: %s",
                        _role_key, camera_index, exc,
                    )
        except Exception:
            pass

    # Guide cameras stare at a mostly-dark sparse field — the DSO mean-based
    # autogain target never reaches band there (see AutoGainController's
    # guiding-mode signal metric), so select the guide-star-peak metric
    # whenever this connection is for the guide role.
    _ag_mode = AutoGainMode.GUIDING if camera_role == "guide" else AutoGainMode.DSO

    _log.info(
        "Preview WS accepted: camera_index=%d camera_role=%r exposure=%.3f gain=%d autogain=%s",
        camera_index, camera_role or "(by index)", exposure, gain, autogain,
    )

    try:
        camera = (
            _pre_resolved_camera
            if _pre_resolved_camera is not None
            else deps.get_preview_camera(camera_index)
        )
    except (RuntimeError, Exception) as exc:
        _log.error("Preview: camera unavailable (role=%r index=%d): %s", camera_role, camera_index, exc)
        # Send reason as text before closing so the UI status bar shows it
        try:
            await websocket.send_text(f"camera_error: {exc}")
        except Exception:
            pass
        await websocket.close(code=1011, reason=str(exc)[:123])
        return

    ctrl: AutoGainController | None = None  # created after bit_depth is known
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

    # Read back effective offset (camera may clamp or silently ignore the value).
    # Use the actual hardware readback as eff_offset so the UI and log are honest.
    eff_offset = offset
    try:
        eff_offset = camera.get_black_level()
        if eff_offset != offset and offset != 0:
            _log.warning(
                "Preview: set_black_level(%d) not reflected — readback=%d "
                "(camera does not support black level or value is out of range)",
                offset, eff_offset,
            )
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
        "requested_exposure_s=%.4f effective_exposure_s=%.4f "
        "requested_gain=%d effective_gain=%d "
        "requested_offset=%d effective_offset=%d stretch=%s",
        getattr(camera, "get_logical_name", lambda: "unknown")(),
        camera_index,
        type(camera).__name__,
        cur_exposure,
        eff_exposure_s,
        cur_gain,
        eff_gain,
        offset,
        eff_offset,
        stretch,
    )

    cur_bit_depth = 16
    try:
        cur_bit_depth = camera.get_bit_depth()
    except Exception:
        pass

    if autogain:
        ctrl = AutoGainController(exposure, gain, mode=_ag_mode, bit_depth=cur_bit_depth)

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

    # Send one-shot camera identity so the UI can warn if MockCamera is active
    # and reflect the effective settings back into the input fields.
    try:
        await websocket.send_text(json.dumps({
            "type": "camera_info",
            "adapter": type(camera).__name__,
            "name": getattr(camera, "get_logical_name", lambda: "")(),
            "is_color": bool(bayer_pattern),
            "bayer_pattern": bayer_pattern,
            "effective_exposure": round(eff_exposure_s, 6),
            "effective_gain": eff_gain,
            "effective_offset": eff_offset,
        }))
    except Exception:
        pass

    # Background task: listen for set_params messages from the client.
    _params_q: asyncio.Queue[dict] = asyncio.Queue()

    async def _settings_listener() -> None:
        try:
            while True:
                text = await websocket.receive_text()
                try:
                    _params_q.put_nowait(json.loads(text))
                except Exception:
                    pass
        except Exception:
            pass

    _listener = asyncio.create_task(_settings_listener())

    try:
        while True:
            # --- apply any pending settings from the client ---
            while not _params_q.empty():
                try:
                    msg = _params_q.get_nowait()
                    if msg.get("type") != "set_params":
                        continue
                    if "exposure" in msg and ctrl is None:
                        cur_exposure = float(msg["exposure"])
                    if "gain" in msg and ctrl is None:
                        cur_gain = int(msg["gain"])
                        camera.set_gain(cur_gain)
                    if "offset" in msg:
                        eff_offset = int(msg["offset"])
                        camera.set_black_level(eff_offset)
                    if "stretch" in msg:
                        stretch = bool(msg["stretch"])
                    if "autogain" in msg:
                        if msg["autogain"] and ctrl is None:
                            ctrl = AutoGainController(
                                cur_exposure, cur_gain, mode=_ag_mode, bit_depth=cur_bit_depth,
                            )
                            _log.info("Autogain enabled via set_params (exp=%.4fs gain=%d)", cur_exposure, cur_gain)
                        elif not msg["autogain"] and ctrl is not None:
                            ctrl = None
                            _log.info("Autogain disabled via set_params")
                except Exception:
                    pass

            # --- yield while a background job owns the camera ---
            _cam_res = f"camera:{camera_index}"
            while True:
                try:
                    if not deps.get_job_manager().is_resource_held(_cam_res):
                        break
                    await websocket.send_text(json.dumps({"type": "camera_busy"}))
                except (WebSocketDisconnect, RuntimeError, AssertionError):
                    break
                await asyncio.sleep(0.25)

            # --- capture frame ---
            _t_capture = time.monotonic()
            try:
                frame: FitsFrame = await asyncio.to_thread(camera.capture, cur_exposure)
            except Exception as exc:
                exc_str = str(exc)
                # Capture was preempted by a background job (abort_capture fired or
                # camera-busy timeout).  Loop back to the yield check so the preview
                # resumes automatically once the job releases the camera.
                try:
                    if deps.get_job_manager().is_resource_held(_cam_res):
                        continue
                except Exception:
                    pass
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
            # Refresh bit depth from the frame header — shift detection runs on the
            # first capture so cur_bit_depth (read before any frame) may be stale.
            frame_bd = frame.header.get("BITDEPTH") if hasattr(frame.header, "get") else None
            if frame_bd is not None:
                cur_bit_depth = int(frame_bd)

            stats = None
            try:
                stats = _hist_analyze(frame.pixels, bit_depth=cur_bit_depth)
                counts, edges, adu_hi = _hist_bins(
                    frame.pixels, bit_depth=cur_bit_depth, n_bins=256,
                )
                # Low-range histogram: fixed 0–1000 ADU, 100 bins (10 ADU/bin)
                # Always shown for pedestal / offset inspection.
                _LOW_ADU = 1000.0
                _adc_max = float((1 << cur_bit_depth) - 1)
                _low_norm = frame.pixels.astype(np.float64).ravel() / _adc_max
                _low_c, _low_e = np.histogram(
                    _low_norm, bins=200, range=(0.0, _LOW_ADU / _adc_max)
                )
                await websocket.send_text(json.dumps({
                    "type": "histogram",
                    "stats": dataclasses.asdict(stats),
                    "bin_counts": counts,
                    "bin_edges": edges,
                    "hist_adu_hi": adu_hi,
                    "low_bin_counts": _low_c.tolist(),
                    "low_bin_edges": _low_e.tolist(),
                    "low_adu_hi": _LOW_ADU,
                }))
            except (WebSocketDisconnect, RuntimeError, AssertionError):
                break
            except Exception:
                pass  # histogram failure must never block frame delivery

            # Read back what the hardware actually reports, separately from
            # what we requested (cur_exposure/cur_gain) — a silently-failed
            # SDK call (see SmartTouptekCamera._try's new warning log) or an
            # auto-exposure override would otherwise be invisible: capture
            # would keep "succeeding" while the sensor ignores our settings.
            _actual_exp_ms = None
            _actual_gain = None
            try:
                _actual_exp_ms = camera.get_exposure_ms()
                _actual_gain = camera.get_gain()
            except Exception:
                pass

            _log.info(
                "Preview frame: camera_index=%d adapter=%s capture=%.3fs "
                "exp=%.4fs gain=%d actual_exp_ms=%s actual_gain=%s offset=%d "
                "bit_depth=%d mean_adu=%.0f p99_adu=%.0f p99_9_adu=%.0f sat=%.2f%%",
                camera_index, type(camera).__name__, _dt,
                cur_exposure, cur_gain, _actual_exp_ms, _actual_gain, eff_offset, cur_bit_depth,
                (stats.mean_frac * stats.adc_max) if stats else 0.0,
                (stats.p99 * stats.adc_max) if stats else 0.0,
                (stats.p99_9 * stats.adc_max) if stats else 0.0,
                stats.saturation_pct if stats else 0.0,
            )

            # --- cache latest pixels for click-to-center refinement (M8-026) ---
            _last_preview_pixels[camera_index] = frame.pixels

            # --- encode and send JPEG ---
            try:
                await websocket.send_bytes(
                    _to_jpeg(frame, stretch=stretch, bayer_pattern=bayer_pattern)
                )
            except (WebSocketDisconnect, RuntimeError, AssertionError):
                # Client disconnected or Starlette transport error mid-send
                break

            # --- autogain update ---
            if ctrl is not None:
                prev_exp, prev_gain = ctrl.exposure, ctrl.gain
                ctrl.update(frame.pixels, bit_depth=cur_bit_depth)
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
    finally:
        _listener.cancel()


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


def _auto_stretch_color(rgb: np.ndarray, adc_max: float = 65535.0) -> np.ndarray:
    """Per-channel sigma stretch (H, W, 3) float32 → uint8."""
    out = np.empty(rgb.shape, dtype=np.uint8)
    for c in range(3):
        ch = rgb[:, :, c].ravel().astype(np.float64)
        background = float(np.median(ch))
        mad = float(np.median(np.abs(ch - background)))
        sigma = mad / 0.6745
        if sigma < 0.5:
            lo = float(np.percentile(ch, 0.5))
            hi = float(np.percentile(ch, 99.5))
        else:
            lo = max(0.0, background - 1.5 * sigma)
            hi = background + 15.0 * sigma
        channel = rgb[:, :, c]
        if hi > lo:
            x = (channel.astype(np.float64) - lo) / (hi - lo)
            scaled = np.arcsinh(x * 3.0) / np.arcsinh(3.0) * 255.0
        else:
            # Uniform channel — no dynamic range to stretch. Flat grey at its
            # true relative brightness, so a saturated channel renders bright,
            # not indistinguishable from a dark/no-signal one (see
            # domain/stretch.py's auto_stretch for the mono equivalent).
            level = np.clip(background / adc_max, 0.0, 1.0) * 255.0
            scaled = np.full_like(channel, level, dtype=np.float64)
        out[:, :, c] = np.clip(scaled, 0.0, 255.0).astype(np.uint8)
    return out


def _to_jpeg(frame: FitsFrame, stretch: bool = True, bayer_pattern: str = "") -> bytes:
    from PIL import Image  # runtime import — keeps startup fast on Pi
    bd = int(frame.header.get("BITDEPTH", 16)) if hasattr(frame.header, "get") else 16
    adc_scale = float((1 << bd) - 1)
    if bayer_pattern:
        # Colour camera: demosaic then per-channel stretch
        rgb = _debayer(frame.pixels, bayer_pattern)
        display = _auto_stretch_color(rgb, adc_max=adc_scale) if stretch else np.clip(
            rgb / adc_scale * 255.0, 0.0, 255.0
        ).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(display, mode="RGB").save(buf, format="JPEG", quality=85)
    else:
        # Monochrome camera: existing single-channel path
        if stretch:
            display = auto_stretch(frame.pixels, adc_max=adc_scale)
        else:
            display = np.clip(
                frame.pixels.astype(np.float64) / adc_scale * 255.0, 0.0, 255.0
            ).astype(np.uint8)
        buf = io.BytesIO()
        Image.fromarray(display).save(buf, format="JPEG", quality=85)
    return buf.getvalue()
