"""ToupcamCamera — CameraPort adapter for Touptek cameras via toupcam SDK."""
from __future__ import annotations

import ctypes
import threading
from typing import Any

import numpy as np
from astropy.io import fits

from ...domain.camera_capabilities import CameraCapabilities, ConversionGain
from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort

# Event constants from toupcam SDK — stable protocol values, not imported at runtime.
_EVENT_IMAGE        = 0x0004
_EVENT_TRIGGER_FAIL = 0x0007
_EVENT_ERROR        = 0x0080
_EVENT_DISCONNECTED = 0x0081

# toupcam flag bits we care about
_FLAG_TEC         = 0x00000080
_FLAG_TEC_ONOFF   = 0x00020000
_FLAG_CG          = 0x04000000
_FLAG_CGHDR       = 0x0000000800000000
_FLAG_BLACKLEVEL  = 0x00400000

_OPTION_BLACKLEVEL = 0x15
_OPTION_CG         = 0x19
_OPTION_BITDEPTH   = 0x06


class ToupcamCamera(CameraPort):
    """CameraPort backed by a Touptek camera via the official toupcam SDK.

    Operates in software-trigger RAW-16 mode: each call to capture() fires
    one exposure and blocks until the frame arrives or the timeout expires.

    The toupcam SDK (toupcam.py + native library) must be importable at
    runtime; connect() returns False if the import fails so other adapters
    can be used without the SDK installed.

    Args:
        index: zero-based index into the list returned by Toupcam.EnumV2().
        _timeout_extra: seconds added to exposure_seconds for the receive
            timeout; exposed for testing so tests don't wait 5 s.
    """

    def __init__(self, index: int = 0, _timeout_extra: float = 5.0) -> None:
        self._index = index
        self._timeout_extra = _timeout_extra
        self._cam: Any = None
        self._tc: Any = None
        self._buf: ctypes.Array[ctypes.c_char] | None = None
        self._width = 0
        self._height = 0
        self._gain: int = 100  # AGain% — 100 = 1×; camera-specific max (typically 3200)
        self._model_flag: int = 0
        self._frame_ready = threading.Event()
        self._capture_error: Exception | None = None

    # ------------------------------------------------------------------
    # CameraPort — lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        if self._cam is not None:
            return True  # already open — idempotent

        try:
            import toupcam as _tc
        except ImportError:
            return False

        devices = _tc.Toupcam.EnumV2()
        if len(devices) <= self._index:
            names = [str(d.displayname) for d in devices]
            listing = ", ".join(f"{i}:{n}" for i, n in enumerate(names)) or "none"
            raise RuntimeError(
                f"ToupTek: no camera at index {self._index} — "
                f"found {len(devices)}: [{listing}]. "
                f"Check touptek_index in smart_telescope.toml or visit /api/cameras"
            )

        cam = _tc.Toupcam.Open(devices[self._index].id)
        if not cam:
            raise RuntimeError(
                f"ToupTek: Open() failed for camera index {self._index}"
            )

        try:
            cam.put_Option(_tc.TOUPCAM_OPTION_TRIGGER, 1)   # software trigger
            cam.put_Option(_tc.TOUPCAM_OPTION_RAW, 1)       # raw sensor data
            cam.put_Option(_tc.TOUPCAM_OPTION_BITDEPTH, 1)  # 16-bit depth
            cam.put_AutoExpoEnable(False)

            width, height = cam.get_Size()
            buf = ctypes.create_string_buffer(width * height * 2)

            cam.StartPullModeWithCallback(_camera_event, self)
        except Exception as exc:
            cam.Close()
            raise RuntimeError(f"ToupTek SDK init failed: {exc}") from exc

        try:
            cam.put_ExpoAGain(self._gain)
        except Exception:
            pass  # not all cameras expose AGain control; ignore silently

        self._cam = cam
        self._tc = _tc
        self._buf = buf
        self._width = width
        self._height = height
        try:
            self._model_flag = int(devices[self._index].model.flag)
        except Exception:
            self._model_flag = 0
        return True

    def disconnect(self) -> None:
        if self._cam is not None:
            try:
                self._cam.Stop()
            finally:
                self._cam.Close()
                self._cam = None
        self._buf = None
        self._tc = None

    # ------------------------------------------------------------------
    # CameraPort — capture
    # ------------------------------------------------------------------

    def capture(self, exposure_seconds: float) -> FitsFrame:
        if self._cam is None or self._buf is None:
            raise RuntimeError("Camera not connected")

        self._cam.put_ExpoTime(max(1, int(exposure_seconds * 1_000_000)))

        self._capture_error = None
        self._frame_ready.clear()
        self._cam.Trigger(1)

        timeout = exposure_seconds + self._timeout_extra
        if not self._frame_ready.wait(timeout=timeout):
            raise TimeoutError(f"No frame received within {timeout:.1f}s")
        if self._capture_error is not None:
            raise self._capture_error

        # rowPitch=-1 → zero padding → width * 2 bytes per row (RAW 16-bit)
        self._cam.PullImageV4(self._buf, 0, 0, -1, None)

        pixels = (
            np.frombuffer(self._buf, dtype=np.uint16)
            .reshape(self._height, self._width)
            .astype(np.float32)
        )

        hdr = fits.Header()
        hdr["SIMPLE"] = True
        hdr["BITPIX"] = -32
        hdr["NAXIS"] = 2
        hdr["NAXIS1"] = self._width
        hdr["NAXIS2"] = self._height
        hdr["EXPTIME"] = exposure_seconds

        return FitsFrame(pixels=pixels, header=hdr, exposure_seconds=exposure_seconds)

    # ------------------------------------------------------------------
    # CameraPort — exposure / gain
    # ------------------------------------------------------------------

    def get_exposure_ms(self) -> float:
        if self._cam is None:
            return float(self._gain)  # not meaningful but safe
        return self._cam.get_ExpoTime() / 1000.0

    def set_exposure_ms(self, ms: float) -> None:
        us = max(1, int(ms * 1000))
        if self._cam is not None:
            self._cam.put_ExpoTime(us)

    def get_gain(self) -> int:
        if self._cam is not None:
            try:
                return int(self._cam.get_ExpoAGain())
            except Exception:
                pass
        return self._gain

    def set_gain(self, gain: int) -> None:
        """Set analog gain (100 = 1×, camera-specific max, typically 3200)."""
        self._gain = max(100, gain)
        if self._cam is not None:
            try:
                self._cam.put_ExpoAGain(self._gain)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # CameraPort — black level
    # ------------------------------------------------------------------

    def get_black_level(self) -> int:
        if self._cam is not None:
            try:
                return int(self._cam.get_Option(_OPTION_BLACKLEVEL))
            except Exception:
                pass
        return 0

    def set_black_level(self, level: int) -> None:
        if self._cam is not None:
            try:
                self._cam.put_Option(_OPTION_BLACKLEVEL, max(0, level))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # CameraPort — conversion gain
    # ------------------------------------------------------------------

    def get_conversion_gain(self) -> ConversionGain:
        if self._cam is not None:
            try:
                return ConversionGain(self._cam.get_Option(_OPTION_CG))
            except Exception:
                pass
        return ConversionGain.LCG

    def set_conversion_gain(self, mode: ConversionGain) -> None:
        if self._cam is not None:
            try:
                self._cam.put_Option(_OPTION_CG, int(mode))
            except Exception:
                pass

    # ------------------------------------------------------------------
    # CameraPort — sensor info
    # ------------------------------------------------------------------

    def get_bit_depth(self) -> int:
        if self._cam is not None:
            try:
                raw = self._cam.get_Option(_OPTION_BITDEPTH)
                return 16 if raw == 1 else 8
            except Exception:
                pass
        return 16

    def get_temperature(self) -> float | None:
        if self._cam is None:
            return None
        try:
            raw = self._cam.get_Temperature()
            return round(raw / 10.0, 1)
        except Exception:
            return None

    def get_capabilities(self) -> CameraCapabilities:
        flag = self._model_flag
        min_gain = max_gain = 100

        if self._cam is not None:
            try:
                g_min, g_max, _ = self._cam.get_ExpoAGainRange()
                min_gain, max_gain = int(g_min), int(g_max)
            except Exception:
                pass

        min_exp_ms = max_exp_ms = 2000.0
        if self._cam is not None:
            try:
                t_min, t_max, _ = self._cam.get_ExpTimeRange()
                min_exp_ms = t_min / 1000.0
                max_exp_ms = t_max / 1000.0
            except Exception:
                pass

        pixel_um = 0.0
        if self._cam is not None:
            try:
                x_um, _ = self._cam.get_PixelSize(0)
                pixel_um = float(x_um)
            except Exception:
                pass

        return CameraCapabilities(
            min_gain=min_gain,
            max_gain=max_gain,
            min_exposure_ms=min_exp_ms,
            max_exposure_ms=max_exp_ms,
            supports_cooling=bool(flag & (_FLAG_TEC | _FLAG_TEC_ONOFF)),
            supports_hcg=bool(flag & (_FLAG_CG | _FLAG_CGHDR)),
            supports_lcg=bool(flag & (_FLAG_CG | _FLAG_CGHDR)),
            supports_hdr=bool(flag & _FLAG_CGHDR),
            supports_black_level=bool(flag & _FLAG_BLACKLEVEL),
            bit_depth=self.get_bit_depth(),
            pixel_size_um=pixel_um,
            sensor_width_px=self._width,
            sensor_height_px=self._height,
        )


def _camera_event(event: int, ctx: ToupcamCamera) -> None:
    """SDK callback fired from a native thread; must be fast and non-blocking."""
    if event == _EVENT_IMAGE:
        ctx._frame_ready.set()
    elif event == _EVENT_TRIGGER_FAIL:
        ctx._capture_error = RuntimeError("Camera trigger failed — check exposure settings")
        ctx._frame_ready.set()
    elif event == _EVENT_DISCONNECTED:
        ctx._capture_error = RuntimeError("Camera disconnected during capture")
        ctx._frame_ready.set()
    elif event == _EVENT_ERROR:
        ctx._capture_error = RuntimeError("Camera reported error during capture")
        ctx._frame_ready.set()
