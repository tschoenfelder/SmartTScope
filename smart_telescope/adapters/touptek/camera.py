"""ToupcamCamera — CameraPort adapter for Touptek cameras via toupcam SDK."""
from __future__ import annotations

import ctypes
import logging
import time
import threading
from typing import Any

_log = logging.getLogger(__name__)

import numpy as np
from astropy.io import fits

from ...domain.camera_capabilities import CameraCapabilities, ConversionGain
from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort, CaptureAbortedError

# Event constants from toupcam SDK — stable protocol values, not imported at runtime.
_EVENT_IMAGE        = 0x0004
_EVENT_STILLIMAGE   = 0x0005
_EVENT_TRIGGER_FAIL = 0x0007
_EVENT_ERROR        = 0x0080
_EVENT_DISCONNECTED = 0x0081

# toupcam flag bits we care about
_FLAG_TEC         = 0x00000080
_FLAG_TEC_ONOFF   = 0x00020000
_FLAG_CG          = 0x04000000
_FLAG_CGHDR       = 0x0000000800000000
_FLAG_RAW16       = 0x00008000  # camera has true 16-bit ADC depth


def _detect_pixel_shift(raw: np.ndarray) -> int:
    """Detect right-shift to convert MSB-aligned sub-16-bit data to native ADC range.

    ToupTek SDK in 16-bit output mode stores data MSB-aligned:
    12-bit ADC → ×16 (shift=4), 14-bit → ×4 (shift=2), true 16-bit → no shift.
    Returns -1 if the frame has too few distinct non-zero pixels to decide reliably.

    Uses the GCD of differences between adjacent distinct values to find the
    quantization step.  This is robust to non-zero black-level offsets: with
    offset O applied to MSB-aligned data, pixel values are (ADC×16)+O.  The step
    between adjacent ADC values is still 16, but (ADC×16+O) % 16 == O%16 ≠ 0 when
    O is not a multiple of 16 — divisibility/majority tests would wrongly return
    shift=2, creating a 4-ADU comb artifact in the histogram.
    """
    from math import gcd
    from functools import reduce

    flat = raw.ravel()
    nonzero = flat[flat > 0]
    if len(nonzero) < 100:
        return -1
    distinct = np.unique(nonzero[:4096].astype(np.int32))
    if len(distinct) < 4:
        return -1  # not enough variety — retry on next frame
    diffs = np.diff(distinct)
    pos_diffs = diffs[diffs > 0]
    if len(pos_diffs) == 0:
        return -1
    step = int(reduce(gcd, pos_diffs.tolist()))
    if step >= 16:
        return 4  # 12-bit ADC
    if step >= 4:
        return 2  # 14-bit ADC
    return 0  # true 16-bit
_FLAG_BLACKLEVEL  = 0x00400000
_FLAG_MONO        = 0x00000040  # monochrome / no Bayer filter

_OPTION_BLACKLEVEL      = 0x15
_OPTION_CG              = 0x19
_OPTION_BITDEPTH        = 0x06
_OPTION_TEC             = 0x18  # 0=off, 1=on
_OPTION_TECTARGET       = 0x07  # target temp × 10 (e.g. -100 = −10.0 °C)
_OPTION_TEC_VOLTAGE     = 0x26  # current TEC voltage (0–1000, proportional to power)
_OPTION_TEC_VOLTAGE_MAX = 0x27  # max TEC voltage rating for this model
_OPTION_TRIGGER         = 0x0B
_OPTION_RAW             = 0x04
_OPTION_RGB             = 0x16
_OPTION_FLUSH           = 0x36
_OPTION_NOFRAME_TIMEOUT = 0x3F
_OPTION_AUTOEXPO_TRIGGER = 0x5A


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

    def __init__(
        self,
        index: int = 0,
        _timeout_extra: float = 5.0,
        camera_id: str | None = None,
        model: str | None = None,
        name: str | None = None,
        capture_mode: str = "auto",
        setup_profile: str = "default",
        startup_delay_s: float = 0.0,
        startup_monitor_interval_s: float = 1.0,
        prime_attempts: int = 0,
        prime_timeout_s: float = 1.5,
        prime_exposure_s: float | None = None,
        bit_depth: int = 16,
    ) -> None:
        self._index = index
        self._timeout_extra = _timeout_extra
        self._camera_id_hint = camera_id
        self._model_selector = model
        self._name_selector = name
        self._capture_mode_requested = capture_mode
        self._capture_mode = capture_mode
        self._setup_profile = setup_profile
        self._startup_delay_s = max(0.0, startup_delay_s)
        self._startup_monitor_interval_s = max(0.1, startup_monitor_interval_s)
        self._prime_attempts = max(0, prime_attempts)
        self._prime_timeout_s = max(0.1, prime_timeout_s)
        self._prime_exposure_s = prime_exposure_s
        self._bit_depth = 16 if bit_depth > 8 else 8
        self._cam: Any = None
        self._tc: Any = None
        self._buf: ctypes.Array[ctypes.c_char] | None = None
        self._width = 0
        self._height = 0
        self._gain: int = 100  # AGain% — 100 = 1×; camera-specific max (typically 3200)
        self._model_flag: int = 0
        self._serial_number: str = ""
        self._logical_name: str = ""
        self._device_id: str = ""
        self._frame_ready = threading.Event()
        self._abort = threading.Event()
        self._capture_error: Exception | None = None
        self._last_event: int | None = None
        self._capture_lock = threading.Lock()  # prevents concurrent captures on same handle
        self._pixel_shift: int = -1  # -1=not yet detected; 0/2/4=right-shift to native range

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
                f"Check [cameras] in smart_telescope.toml or visit /api/cameras"
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
        if self._model_flag & _FLAG_RAW16:
            self._pixel_shift = 0  # true 16-bit sensor — no shift needed
        try:
            self._logical_name = str(devices[self._index].displayname)
        except Exception:
            self._logical_name = ""
        try:
            self._serial_number = cam.SerialNumber()
        except Exception:
            self._serial_number = ""
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

    def abort_capture(self) -> None:
        """Signal abort to any in-progress capture() call."""
        self._abort.set()

    # ------------------------------------------------------------------
    # CameraPort — capture
    # ------------------------------------------------------------------

    def capture(self, exposure_seconds: float) -> FitsFrame:
        if self._cam is None or self._buf is None:
            raise RuntimeError("Camera not connected")
        _log.debug("capture(%s index=%d): waiting for lock", self._logical_name or "?", self._index)
        if not self._capture_lock.acquire(blocking=True, timeout=12.0):
            raise RuntimeError("Camera busy — timed out after 12 s waiting for previous capture to finish")
        try:
            us = max(1, int(exposure_seconds * 1_000_000))
            _log.debug("capture(%s index=%d): put_ExpoTime(%d µs)", self._logical_name or "?", self._index, us)
            try:
                self._cam.put_ExpoTime(us)
            except Exception as exc:
                raise RuntimeError(f"put_ExpoTime({us} µs) failed: {exc}") from exc

            self._capture_error = None
            self._frame_ready.clear()
            _log.debug("capture(%s index=%d): Trigger(1)", self._logical_name or "?", self._index)
            try:
                self._cam.Trigger(1)
            except Exception as exc:
                raise RuntimeError(f"Trigger(1) failed: {exc}") from exc

            timeout = exposure_seconds + self._timeout_extra
            _log.debug("capture(%s index=%d): waiting for frame (timeout=%.1fs)", self._logical_name or "?", self._index, timeout)
            self._abort.clear()
            got_frame = False
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                if self._frame_ready.wait(timeout=min(0.05, remaining)):
                    got_frame = True
                    break
                if self._abort.is_set():
                    self._abort.clear()
                    raise CaptureAbortedError("capture aborted")
            if not got_frame:
                _log.error("capture(%s index=%d): TIMEOUT — no frame callback within %.1fs", self._logical_name or "?", self._index, timeout)
                raise TimeoutError(f"No frame received within {timeout:.1f}s")
            _log.debug("capture(%s index=%d): frame_ready set (error=%s)", self._logical_name or "?", self._index, self._capture_error)
            if self._capture_error is not None:
                raise self._capture_error

            # bits=16 → always request 16-bit output (matches TOUPCAM_OPTION_BITDEPTH=1)
            # rowPitch=-1 → auto (width * 2 bytes per row for RAW-16)
            # Retry on E_PENDING (-2147483638 / 0x8000000A): some camera models fire
            # EVENT_IMAGE slightly before the buffer is fully populated.
            _pull_exc: Exception | None = None
            for _attempt in range(3):
                try:
                    self._cam.PullImageV4(self._buf, 0, 16, -1, None)
                    _pull_exc = None
                    break
                except Exception as exc:
                    _pull_exc = exc
                    time.sleep(0.05)
            if _pull_exc is not None:
                raise RuntimeError(f"PullImageV4 failed after 3 attempts: {_pull_exc}") from _pull_exc

            raw_u16 = (
                np.frombuffer(self._buf, dtype=np.uint16)
                .reshape(self._height, self._width)
            )
            if self._pixel_shift < 0:
                self._pixel_shift = _detect_pixel_shift(raw_u16)
            shift = max(0, self._pixel_shift)
            pixels = (raw_u16 >> shift).astype(np.float32)

            hdr = fits.Header()
            hdr["SIMPLE"] = True
            hdr["BITPIX"] = -32
            hdr["NAXIS"] = 2
            hdr["NAXIS1"] = self._width
            hdr["NAXIS2"] = self._height
            hdr["EXPTIME"] = exposure_seconds
            hdr["BITDEPTH"] = 16 - shift

            return FitsFrame(pixels=pixels, header=hdr, exposure_seconds=exposure_seconds)
        finally:
            self._capture_lock.release()

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
                self._pixel_shift = -1  # offset changes 16-bit alignment; re-detect on next frame
            except Exception as exc:
                _log.warning("ToupcamCamera.set_black_level(%d): SDK rejected: %s", level, exc)

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
                if raw != 1:
                    return 8
            except Exception:
                pass
        # Return sensor native depth (shift detected lazily on first frame).
        # Returns 16 until the first capture completes — callers should prefer
        # reading BITDEPTH from the FitsFrame header for per-frame accuracy.
        return 16 - max(0, self._pixel_shift)

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

    def get_serial_number(self) -> str:
        return self._serial_number

    def get_logical_name(self) -> str:
        return self._logical_name

    # ------------------------------------------------------------------
    # TEC cooling control (ATR585M and other cooled cameras)
    # ------------------------------------------------------------------

    def set_tec_enabled(self, on: bool) -> None:
        if self._cam is not None:
            try:
                self._cam.put_Option(_OPTION_TEC, 1 if on else 0)
            except Exception:
                pass

    def set_tec_target_c(self, target_c: float) -> None:
        if self._cam is not None:
            try:
                self._cam.put_Option(_OPTION_TECTARGET, int(target_c * 10))
            except Exception:
                pass

    def get_tec_power_pct(self) -> float:
        """Return TEC power draw as 0–100 %.  Returns 0.0 if unavailable."""
        if self._cam is not None:
            try:
                v     = self._cam.get_Option(_OPTION_TEC_VOLTAGE)
                v_max = self._cam.get_Option(_OPTION_TEC_VOLTAGE_MAX)
                if v_max > 0:
                    return min(100.0, max(0.0, v / v_max * 100.0))
            except Exception:
                pass
        return 0.0

    # ------------------------------------------------------------------
    # CameraPort — color sensor detection
    # ------------------------------------------------------------------

    def is_color_sensor(self) -> bool:
        """Return True when the sensor has a Bayer colour filter (not monochrome)."""
        return not bool(self._model_flag & _FLAG_MONO)

    def get_bayer_pattern(self) -> str:
        """Return the Bayer CFA pattern string: 'RGGB', 'BGGR', 'GRBG', or 'GBRG'.

        Reads the FOURCC from the SDK if available; defaults to 'RGGB' on failure
        (the most common pattern for Touptek colour cameras).
        """
        if self._cam is None:
            return "RGGB"
        try:
            fourcc, _ = self._cam.get_RawFormat()
            # FOURCC uint32 → 4 ASCII bytes (little-endian)
            s = bytes(
                [(fourcc >> (8 * i)) & 0xFF for i in range(4)]
            ).decode("ascii", errors="replace")
            if s in ("RGGB", "BGGR", "GRBG", "GBRG"):
                return s
        except Exception:
            pass
        return "RGGB"


_EVENT_EXPOSURE = 0x0001  # auto-exposure changed — fired on every put_ExpoTime, not useful

def _camera_event(event: int, ctx: ToupcamCamera) -> None:
    """SDK callback fired from a native thread; must be fast and non-blocking."""
    if event != _EVENT_EXPOSURE:
        _log.debug("SDK event 0x%04X on %s index=%d", event, ctx._logical_name or "?", ctx._index)
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
