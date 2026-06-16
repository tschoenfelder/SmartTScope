"""Native ToupTek camera adapter with CameraTest-derived setup profiles."""

from __future__ import annotations

import ctypes
import logging
import threading
import time
from typing import Any

import numpy as np
from astropy.io import fits

from ...domain.camera_capabilities import CameraCapabilities, ConversionGain
from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort, CaptureAbortedError

_log = logging.getLogger(__name__)

_EVENT_IMAGE = 0x0004
_EVENT_STILLIMAGE = 0x0005
_EVENT_TRIGGER_FAIL = 0x0007
_EVENT_ERROR = 0x0080
_EVENT_DISCONNECTED = 0x0081

_FLAG_TEC = 0x00000080
_FLAG_TEC_ONOFF = 0x00020000
_FLAG_CG = 0x04000000
_FLAG_CGHDR = 0x0000000800000000
_FLAG_BLACKLEVEL = 0x00400000
_FLAG_MONO = 0x00000040

_OPTION_BLACKLEVEL = 0x15
_OPTION_CG = 0x19
_OPTION_BITDEPTH = 0x06
_OPTION_TEC = 0x18
_OPTION_TECTARGET = 0x07
_OPTION_TEC_VOLTAGE = 0x26
_OPTION_TEC_VOLTAGE_MAX = 0x27
_OPTION_FILTERWHEEL_POSITION = 0x49
_OPTION_TRIGGER = 0x0B
_OPTION_RAW = 0x04
_OPTION_RGB = 0x16
_OPTION_FLUSH = 0x36
_OPTION_NOFRAME_TIMEOUT = 0x3F
_OPTION_AUTOEXPO_TRIGGER = 0x5A

_sdk_lifecycle_lock = threading.RLock()


class CameraRoleConflictError(RuntimeError):
    """Raised when multiple SmartTScope roles resolve to one physical camera."""


class SmartTouptekCamera(CameraPort):
    """CameraPort backed by one native ToupTek camera.

    This class keeps SmartTScope's existing synchronous `capture()` contract but
    adds the capture modes and startup behavior that proved stable in CameraTest.
    """

    def __init__(
        self,
        index: int = 0,
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
        timeout_extra_s: float = 5.0,
    ) -> None:
        self._index = index
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
        self._timeout_extra_s = timeout_extra_s

        self._cam: Any = None
        self._tc: Any = None
        self._width = 0
        self._height = 0
        self._gain = 100
        self._model_flag = 0
        self._serial_number = ""
        self._logical_name = ""
        self._device_id = ""
        self._frame_ready = threading.Event()
        self._abort = threading.Event()
        self._capture_error: Exception | None = None
        self._last_event: int | None = None
        self._capture_lock = threading.Lock()

    def connect(self) -> bool:
        if self._cam is not None:
            return True
        try:
            import toupcam as tc
        except ImportError:
            return False
        with _sdk_lifecycle_lock:
            devices = tc.Toupcam.EnumV2()
            self._tc = tc
            self._index, device = self._select_device(devices)
            if device is None:
                listing = ", ".join(f"{i}:{d.displayname}" for i, d in enumerate(devices)) or "none"
                raise RuntimeError(
                    f"ToupTek: no camera matching index={self._index}, "
                    f"id={self._camera_id_hint!r}, model={self._model_selector!r}, name={self._name_selector!r}. "
                    f"Found: {listing}"
                )
            cam = tc.Toupcam.Open(device.id)
        if not cam:
            raise RuntimeError(f"ToupTek: Open() failed for {device.displayname}")
        self._cam = cam
        self._logical_name = str(device.displayname or device.model.name)
        self._device_id = str(device.id)
        self._model_flag = int(getattr(device.model, "flag", 0))
        try:
            self._serial_number = cam.SerialNumber()
        except Exception:
            self._serial_number = ""
        try:
            self._width, self._height = cam.get_Size()
        except Exception:
            self._width = int(device.model.res[0].width)
            self._height = int(device.model.res[0].height)

        self._capture_mode = self._resolve_capture_mode()
        self._basic_configure()
        self._apply_setup_profile()
        self._prepare_capture_mode()
        self._startup_settle()
        self._prime_capture_path()
        return True

    def disconnect(self) -> None:
        if self._cam is not None:
            with _sdk_lifecycle_lock:
                try:
                    self._cam.Stop()
                finally:
                    self._cam.Close()
        self._cam = None
        self._tc = None

    def abort_capture(self) -> None:
        self._abort.set()

    def capture(self, exposure_seconds: float) -> FitsFrame:
        if self._cam is None:
            raise RuntimeError("Camera not connected")
        if not self._capture_lock.acquire(timeout=exposure_seconds + self._timeout_extra_s + 12.0):
            raise RuntimeError("Camera busy")
        try:
            self._cam.put_ExpoTime(max(1, int(exposure_seconds * 1_000_000)))
            pixels = self._capture_raw(exposure_seconds + self._timeout_extra_s).astype(np.float32)
            hdr = fits.Header()
            hdr["SIMPLE"] = True
            hdr["BITPIX"] = -32
            hdr["NAXIS"] = 2
            hdr["NAXIS1"] = int(pixels.shape[1])
            hdr["NAXIS2"] = int(pixels.shape[0])
            hdr["EXPTIME"] = exposure_seconds
            hdr["CAMERA"] = self._logical_name
            hdr["CAMID"] = self._device_id
            hdr["SERIAL"] = self._serial_number
            hdr["BACKEND"] = "native"
            hdr["CAPMODE"] = self._capture_mode
            return FitsFrame(pixels=pixels, header=hdr, exposure_seconds=exposure_seconds)
        finally:
            self._capture_lock.release()

    def get_exposure_ms(self) -> float:
        if self._cam is None:
            return 0.0
        return float(self._cam.get_ExpoTime()) / 1000.0

    def set_exposure_ms(self, ms: float) -> None:
        if self._cam is not None:
            self._cam.put_ExpoTime(max(1, int(ms * 1000)))

    def get_gain(self) -> int:
        if self._cam is not None:
            try:
                return int(self._cam.get_ExpoAGain())
            except Exception:
                pass
        return self._gain

    def set_gain(self, gain: int) -> None:
        self._gain = max(0, int(gain))
        if self._cam is not None:
            self._try(lambda: self._cam.put_ExpoAGain(self._gain))

    def get_black_level(self) -> int:
        if self._cam is not None:
            value = self._try(lambda: self._cam.get_Option(_opt(self._tc, "TOUPCAM_OPTION_BLACKLEVEL", _OPTION_BLACKLEVEL)))
            if value is not None:
                return int(value)
        return 0

    def set_black_level(self, level: int) -> None:
        if self._cam is not None:
            self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_BLACKLEVEL", _OPTION_BLACKLEVEL), max(0, int(level))))

    def get_conversion_gain(self) -> ConversionGain:
        if self._cam is not None:
            value = self._try(lambda: self._cam.get_Option(_opt(self._tc, "TOUPCAM_OPTION_CG", _OPTION_CG)))
            if value is not None:
                try:
                    return ConversionGain(int(value))
                except ValueError:
                    pass
        return ConversionGain.LCG

    def set_conversion_gain(self, mode: ConversionGain) -> None:
        if self._cam is not None:
            self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_CG", _OPTION_CG), int(mode)))

    def get_bit_depth(self) -> int:
        return self._bit_depth

    def get_temperature(self) -> float | None:
        if self._cam is None:
            return None
        value = self._try(lambda: self._cam.get_Temperature())
        return None if value is None else round(float(value) / 10.0, 1)

    def get_capabilities(self) -> CameraCapabilities:
        min_gain = max_gain = 100
        if self._cam is not None:
            rng = self._try(lambda: self._cam.get_ExpoAGainRange())
            if rng:
                min_gain, max_gain = int(rng[0]), int(rng[1])
        min_exp_ms = max_exp_ms = 2000.0
        if self._cam is not None:
            rng = self._try(lambda: self._cam.get_ExpTimeRange())
            if rng:
                min_exp_ms = float(rng[0]) / 1000.0
                max_exp_ms = float(rng[1]) / 1000.0
        return CameraCapabilities(
            min_gain=min_gain,
            max_gain=max_gain,
            min_exposure_ms=min_exp_ms,
            max_exposure_ms=max_exp_ms,
            supports_cooling=bool(self._model_flag & (_FLAG_TEC | _FLAG_TEC_ONOFF)),
            supports_hcg=bool(self._model_flag & (_FLAG_CG | _FLAG_CGHDR)),
            supports_lcg=True,
            supports_hdr=bool(self._model_flag & _FLAG_CGHDR),
            supports_black_level=bool(self._model_flag & _FLAG_BLACKLEVEL),
            bit_depth=self._bit_depth,
            pixel_size_um=0.0,
            sensor_width_px=self._width,
            sensor_height_px=self._height,
        )

    def get_serial_number(self) -> str:
        return self._serial_number

    def get_logical_name(self) -> str:
        return self._logical_name

    def set_tec_enabled(self, on: bool) -> None:
        if self._cam is not None:
            self._try(lambda: self._cam.put_Option(_OPTION_TEC, 1 if on else 0))

    def set_tec_target_c(self, target_c: float) -> None:
        if self._cam is not None:
            self._try(lambda: self._cam.put_Option(_OPTION_TECTARGET, int(target_c * 10)))

    def get_tec_target_c(self) -> float | None:
        if self._cam is None:
            return None
        value = self._try(lambda: self._cam.get_Option(_OPTION_TECTARGET))
        return None if value is None else round(float(value) / 10.0, 1)

    def get_tec_power_pct(self) -> float:
        if self._cam is None:
            return 0.0
        voltage = self._try(lambda: self._cam.get_Option(_OPTION_TEC_VOLTAGE))
        voltage_max = self._try(lambda: self._cam.get_Option(_OPTION_TEC_VOLTAGE_MAX))
        if voltage is None or not voltage_max:
            return 0.0
        return min(100.0, max(0.0, float(voltage) / float(voltage_max) * 100.0))

    def get_filter_position(self) -> int | None:
        if self._cam is None:
            return None
        option = _opt(self._tc, "TOUPCAM_OPTION_FILTERWHEEL_POSITION", _OPTION_FILTERWHEEL_POSITION)
        value = self._try(lambda: self._cam.get_Option(option))
        if value is None or int(value) < 0:
            return None
        return int(value) + 1

    def set_filter_position(self, position: int) -> None:
        if position < 1:
            raise ValueError("Filter position is 1-based and must be >= 1")
        if self._cam is None:
            raise RuntimeError("Camera not connected")
        option = _opt(self._tc, "TOUPCAM_OPTION_FILTERWHEEL_POSITION", _OPTION_FILTERWHEEL_POSITION)
        self._cam.put_Option(option, int(position) - 1)

    def is_color_sensor(self) -> bool:
        return not bool(self._model_flag & _FLAG_MONO)

    def get_bayer_pattern(self) -> str:
        return "RGGB"

    def _select_device(self, devices: Any) -> tuple[int, Any | None]:
        if self._camera_id_hint:
            for idx, dev in enumerate(devices):
                if str(dev.id) == self._camera_id_hint:
                    return idx, dev
        selector = self._name_selector or self._model_selector
        if selector:
            needle = _normalise_camera_name(selector)
            for idx, dev in enumerate(devices):
                haystack = _normalise_camera_name(f"{dev.displayname} {dev.model.name}")
                if needle in haystack:
                    return idx, dev
        if len(devices) > self._index:
            return self._index, devices[self._index]
        return self._index, None

    def _resolve_capture_mode(self) -> str:
        if self._capture_mode_requested != "auto":
            return self._capture_mode_requested
        name = _normalise_camera_name(f"{self._logical_name} {self._model_selector or ''}")
        if "GPCMOS02000KPA" in name:
            return "snap"
        return "indi-stream-trigger"

    def _basic_configure(self) -> None:
        assert self._cam is not None and self._tc is not None
        self._try(lambda: self._cam.put_AutoExpoEnable(0))
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_AUTOEXPO_TRIGGER", _OPTION_AUTOEXPO_TRIGGER), 0))
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_RAW", _OPTION_RAW), 1))
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_BITDEPTH", _OPTION_BITDEPTH), 1 if self._bit_depth > 8 else 0))
        if not self.is_color_sensor():
            self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_RGB", _OPTION_RGB), 4 if self._bit_depth > 8 else 3))

    def _apply_setup_profile(self) -> None:
        if self._setup_profile != "indi" or self._cam is None or self._tc is None:
            return
        self._try(lambda: self._cam.put_HZ(2))
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_NOFRAME_TIMEOUT", _OPTION_NOFRAME_TIMEOUT), 1))
        zero_padding = getattr(self._tc, "TOUPCAM_OPTION_ZERO_PADDING", None)
        if zero_padding is not None:
            self._try(lambda: self._cam.put_Option(zero_padding, 1))
        self._try(lambda: self._cam.put_Speed(0))
        framerate = getattr(self._tc, "TOUPCAM_OPTION_FRAMERATE", None)
        if framerate is not None:
            self._try(lambda: self._cam.put_Option(framerate, 63))

    def _prepare_capture_mode(self) -> None:
        assert self._cam is not None and self._tc is not None
        self._try(lambda: self._cam.Stop())
        self._drain_state()
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_FLUSH", _OPTION_FLUSH), 3))
        if self._capture_mode == "snap":
            self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_TRIGGER", _OPTION_TRIGGER), 0))
            self._cam.StartPullModeWithCallback(_camera_event, self)
            return
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_TRIGGER", _OPTION_TRIGGER), 0))
        self._cam.StartPullModeWithCallback(_camera_event, self)
        time.sleep(0.2)
        self._drain_state()
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_TRIGGER", _OPTION_TRIGGER), 1))
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_NOFRAME_TIMEOUT", _OPTION_NOFRAME_TIMEOUT), 1))
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_FLUSH", _OPTION_FLUSH), 3))

    def _startup_settle(self) -> None:
        if self._startup_delay_s <= 0:
            return
        deadline = time.monotonic() + self._startup_delay_s
        while time.monotonic() < deadline:
            time.sleep(min(self._startup_monitor_interval_s, max(0.0, deadline - time.monotonic())))

    def _prime_capture_path(self) -> None:
        if self._prime_attempts <= 0 or self._cam is None:
            return
        original_us = self._try(lambda: self._cam.get_ExpoTime())
        if self._prime_exposure_s is not None:
            self._try(lambda: self._cam.put_ExpoTime(max(1, int(self._prime_exposure_s * 1_000_000))))
        try:
            for _ in range(self._prime_attempts):
                try:
                    self._capture_raw(self._prime_timeout_s)
                    return
                except Exception as exc:
                    _log.debug("prime frame failed on %s: %s", self._logical_name, exc)
        finally:
            if original_us is not None:
                self._try(lambda: self._cam.put_ExpoTime(original_us))

    def _capture_raw(self, timeout_s: float) -> np.ndarray:
        assert self._cam is not None and self._tc is not None
        self._drain_state()
        self._try(lambda: self._cam.put_Option(_opt(self._tc, "TOUPCAM_OPTION_FLUSH", _OPTION_FLUSH), 3))
        if self._capture_mode == "snap":
            self._cam.Snap(0xFFFFFFFF)
        else:
            self._cam.Trigger(1)
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._frame_ready.wait(min(0.05, max(0.0, deadline - time.monotonic()))):
                break
            if self._abort.is_set():
                self._abort.clear()
                raise CaptureAbortedError("capture aborted")
        else:
            raise TimeoutError(f"No frame received within {timeout_s:.1f}s")
        if self._capture_error is not None:
            raise self._capture_error
        return self._pull_pixels(still=self._last_event == _EVENT_STILLIMAGE)

    def _pull_pixels(self, still: bool = False) -> np.ndarray:
        assert self._cam is not None and self._tc is not None
        bytes_per_pixel = 2 if self._bit_depth > 8 else 1
        buffer = ctypes.create_string_buffer(self._width * self._height * bytes_per_pixel)
        if self._capture_mode == "snap":
            info = self._tc.ToupcamFrameInfoV4()
            self._cam.PullImageV4(buffer, 1 if still else 0, self._bit_depth, -1, info)
            width = int(getattr(info, "width", 0) or self._width)
            height = int(getattr(info, "height", 0) or self._height)
        else:
            info = self._tc.ToupcamFrameInfoV2()
            self._cam.PullImageWithRowPitchV2(buffer, self._bit_depth, -1, info)
            width = int(getattr(info, "width", 0) or self._width)
            height = int(getattr(info, "height", 0) or self._height)
        dtype = np.uint16 if bytes_per_pixel == 2 else np.uint8
        pixels = np.frombuffer(buffer, dtype=dtype, count=width * height).reshape((height, width))
        if pixels.dtype != np.uint16:
            pixels = pixels.astype(np.uint16) << 8
        return pixels.copy()

    def _drain_state(self) -> None:
        self._frame_ready.clear()
        self._capture_error = None
        self._last_event = None
        self._abort.clear()

    def _try(self, fn: Any) -> Any:
        try:
            return fn()
        except Exception:
            return None

    @staticmethod
    def enumerate_devices() -> list[dict[str, Any]]:
        """Return native ToupTek devices without opening any camera handle."""
        try:
            import toupcam as tc
        except ImportError:
            return []
        with _sdk_lifecycle_lock:
            devices = tc.Toupcam.EnumV2()
        result: list[dict[str, Any]] = []
        for idx, dev in enumerate(devices):
            model = getattr(dev, "model", None)
            res = getattr(model, "res", []) if model is not None else []
            width = int(getattr(res[0], "width", 0)) if res else 0
            height = int(getattr(res[0], "height", 0)) if res else 0
            result.append(
                {
                    "index": idx,
                    "id": str(getattr(dev, "id", "")),
                    "name": str(getattr(dev, "displayname", "")),
                    "model": str(getattr(model, "name", "")),
                    "width": width,
                    "height": height,
                }
            )
        return result

    @staticmethod
    def resolve_device_id(
        *,
        index: int = 0,
        camera_id: str | None = None,
        model: str | None = None,
        name: str | None = None,
    ) -> dict[str, Any] | None:
        """Resolve a config selector to one physical native camera identity."""
        devices = SmartTouptekCamera.enumerate_devices()
        if camera_id:
            for dev in devices:
                if str(dev["id"]) == str(camera_id):
                    return dev
            return None
        selector = name or model
        if selector:
            needle = _normalise_camera_name(selector)
            for dev in devices:
                haystack = _normalise_camera_name(f"{dev.get('name', '')} {dev.get('model', '')}")
                if needle in haystack:
                    return dev
            return None
        if 0 <= index < len(devices):
            return devices[index]
        return None


def validate_unique_camera_roles(specs: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Resolve configured native roles and fail if two roles use one device ID."""
    resolved: dict[str, dict[str, Any]] = {}
    by_id: dict[str, str] = {}
    for role, spec in specs.items():
        if not getattr(spec, "enabled", True):
            continue
        if getattr(spec, "backend", "native").lower() != "native":
            continue
        dev = SmartTouptekCamera.resolve_device_id(
            index=getattr(spec, "index", None) or 0,
            camera_id=getattr(spec, "camera_id", "") or None,
            model=getattr(spec, "model", "") or None,
            name=getattr(spec, "name", "") or None,
        )
        if dev is None:
            continue
        device_id = str(dev.get("id", ""))
        if device_id and device_id in by_id:
            other = by_id[device_id]
            raise CameraRoleConflictError(
                f"Camera roles {other!r} and {role!r} both resolve to ToupTek device "
                f"{device_id!r} ({dev.get('name') or dev.get('model')}). Disable one role or "
                "choose a different camera."
            )
        if device_id:
            by_id[device_id] = role
        resolved[role] = dev
    return resolved


def _camera_event(event: int, ctx: SmartTouptekCamera) -> None:
    ctx._last_event = event
    if event in (_EVENT_IMAGE, _EVENT_STILLIMAGE):
        ctx._frame_ready.set()
    elif event == _EVENT_TRIGGER_FAIL:
        ctx._capture_error = RuntimeError("Camera trigger failed")
        ctx._frame_ready.set()
    elif event == _EVENT_DISCONNECTED:
        ctx._capture_error = RuntimeError("Camera disconnected during capture")
        ctx._frame_ready.set()
    elif event == _EVENT_ERROR:
        ctx._capture_error = RuntimeError("Camera reported error during capture")
        ctx._frame_ready.set()


def _normalise_camera_name(value: str) -> str:
    return value.upper().replace(" ", "").replace("_", "")


def _opt(module: Any, name: str, fallback: int) -> int:
    return int(getattr(module, name, fallback))
