"""ToupcamCamera — CameraPort adapter for Touptek cameras via toupcam SDK."""
from __future__ import annotations

import ctypes
import threading
from typing import Any

import numpy as np
from astropy.io import fits

from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort

# Event constants from toupcam SDK — stable protocol values, not imported at runtime.
_EVENT_IMAGE        = 0x0004
_EVENT_TRIGGER_FAIL = 0x0007
_EVENT_ERROR        = 0x0080
_EVENT_DISCONNECTED = 0x0081


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
        self._frame_ready = threading.Event()
        self._capture_error: Exception | None = None

    # ------------------------------------------------------------------
    # CameraPort
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
            raise RuntimeError(
                f"ToupTek: no camera at index {self._index} "
                f"({len(devices)} device(s) found)"
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
        return True

    def set_gain(self, gain: int) -> None:
        """Set analog gain (100 = 1×, camera-specific max, typically 3200)."""
        self._gain = max(100, gain)
        if self._cam is not None:
            try:
                self._cam.put_ExpoAGain(self._gain)
            except Exception:
                pass

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

    def disconnect(self) -> None:
        if self._cam is not None:
            try:
                self._cam.Stop()
            finally:
                self._cam.Close()
                self._cam = None
        self._buf = None
        self._tc = None


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
