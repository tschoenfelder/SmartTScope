"""Unit tests for ToupcamCamera — exercised without hardware via sys.modules injection."""
import sys
import threading
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from smart_telescope.adapters.touptek.camera import (
    _EVENT_DISCONNECTED,
    _EVENT_ERROR,
    _EVENT_IMAGE,
    _EVENT_TRIGGER_FAIL,
    ToupcamCamera,
    _camera_event,
)
from smart_telescope.domain.camera_capabilities import CameraCapabilities, ConversionGain
from smart_telescope.domain.frame import FitsFrame

_WIDTH, _HEIGHT = 100, 80


def _make_toupcam_mock(
    num_devices: int = 1,
    open_succeeds: bool = True,
    model_flag: int = 0,
) -> MagicMock:
    tc = MagicMock()
    tc.TOUPCAM_OPTION_TRIGGER = 0x0B
    tc.TOUPCAM_OPTION_RAW = 0x04
    tc.TOUPCAM_OPTION_BITDEPTH = 0x06

    device = MagicMock()
    device.model.flag = model_flag
    tc.Toupcam.EnumV2.return_value = [device for _ in range(num_devices)]

    if open_succeeds:
        hw = MagicMock()
        hw.get_Size.return_value = (_WIDTH, _HEIGHT)
        hw.get_ExpoAGain.return_value = 100
        hw.get_ExpoAGainRange.return_value = (100, 3200, 100)
        hw.get_ExpTimeRange.return_value = (100, 60_000_000, 2_000_000)
        hw.get_Option.return_value = 1  # BITDEPTH=1 → 16-bit, CG=1 → HCG
        hw.get_Temperature.return_value = 235  # 23.5 °C
        hw.get_PixelSize.return_value = (2.4, 2.4)
        tc.Toupcam.Open.return_value = hw
    else:
        tc.Toupcam.Open.return_value = None
    return tc


def _connect(
    tc: MagicMock,
    index: int = 0,
    timeout_extra: float = 0.3,
) -> ToupcamCamera:
    cam = ToupcamCamera(index=index, _timeout_extra=timeout_extra)
    with patch.dict(sys.modules, {"toupcam": tc}):
        cam.connect()
    return cam


def _fire(cam: ToupcamCamera, event: int) -> None:
    threading.Thread(target=_camera_event, args=(event, cam), daemon=True).start()


# ── connect ────────────────────────────────────────────────────────────────────

class TestConnect:
    def test_false_when_import_fails(self) -> None:
        cam = ToupcamCamera()
        with patch.dict(sys.modules, {"toupcam": None}):
            assert cam.connect() is False

    def test_raises_when_no_devices(self) -> None:
        cam = ToupcamCamera()
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(num_devices=0)}):
            with pytest.raises(RuntimeError, match="no camera at index"):
                cam.connect()

    def test_raises_when_index_exceeds_device_count(self) -> None:
        cam = ToupcamCamera(index=1)
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(num_devices=1)}):
            with pytest.raises(RuntimeError, match="no camera at index"):
                cam.connect()

    def test_raises_when_open_returns_none(self) -> None:
        cam = ToupcamCamera()
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(open_succeeds=False)}):
            with pytest.raises(RuntimeError, match="Open\\(\\) failed"):
                cam.connect()

    def test_true_on_success(self) -> None:
        cam = ToupcamCamera()
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock()}):
            assert cam.connect() is True

    def test_sets_trigger_software_mode(self) -> None:
        tc = _make_toupcam_mock()
        with patch.dict(sys.modules, {"toupcam": tc}):
            ToupcamCamera().connect()
        tc.Toupcam.Open.return_value.put_Option.assert_any_call(tc.TOUPCAM_OPTION_TRIGGER, 1)

    def test_sets_raw_mode(self) -> None:
        tc = _make_toupcam_mock()
        with patch.dict(sys.modules, {"toupcam": tc}):
            ToupcamCamera().connect()
        tc.Toupcam.Open.return_value.put_Option.assert_any_call(tc.TOUPCAM_OPTION_RAW, 1)

    def test_sets_16bit_depth(self) -> None:
        tc = _make_toupcam_mock()
        with patch.dict(sys.modules, {"toupcam": tc}):
            ToupcamCamera().connect()
        tc.Toupcam.Open.return_value.put_Option.assert_any_call(tc.TOUPCAM_OPTION_BITDEPTH, 1)

    def test_disables_auto_exposure(self) -> None:
        tc = _make_toupcam_mock()
        with patch.dict(sys.modules, {"toupcam": tc}):
            ToupcamCamera().connect()
        tc.Toupcam.Open.return_value.put_AutoExpoEnable.assert_called_once_with(False)

    def test_raises_and_camera_closed_when_option_raises(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.put_Option.side_effect = RuntimeError("hw fault")
        cam = ToupcamCamera()
        with patch.dict(sys.modules, {"toupcam": tc}):
            with pytest.raises(RuntimeError, match="SDK init failed"):
                cam.connect()
        tc.Toupcam.Open.return_value.Close.assert_called_once()


# ── capture ────────────────────────────────────────────────────────────────────

class TestCapture:
    def _setup(self) -> tuple[ToupcamCamera, MagicMock]:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.Trigger.side_effect = lambda n: _fire(
            # cam is not available yet; we patch it in below
            None, _EVENT_IMAGE  # placeholder — overridden per-test
        )
        cam = _connect(tc)
        # Wire real event firing now that cam exists
        tc.Toupcam.Open.return_value.Trigger.side_effect = lambda n: _fire(cam, _EVENT_IMAGE)
        return cam, tc

    def test_returns_fits_frame(self) -> None:
        cam, _ = self._setup()
        assert isinstance(cam.capture(0.001), FitsFrame)

    def test_frame_dimensions_match_camera(self) -> None:
        cam, _ = self._setup()
        frame = cam.capture(0.001)
        assert frame.width == _WIDTH
        assert frame.height == _HEIGHT

    def test_frame_exposure_seconds(self) -> None:
        cam, _ = self._setup()
        frame = cam.capture(2.5)
        assert frame.exposure_seconds == pytest.approx(2.5)

    def test_exposure_time_sent_in_microseconds(self) -> None:
        cam, tc = self._setup()
        cam.capture(1.5)
        tc.Toupcam.Open.return_value.put_ExpoTime.assert_called_with(1_500_000)

    def test_sub_microsecond_clamped_to_one(self) -> None:
        cam, tc = self._setup()
        cam.capture(0.0)
        tc.Toupcam.Open.return_value.put_ExpoTime.assert_called_with(1)

    def test_pixels_dtype_float32(self) -> None:
        cam, _ = self._setup()
        assert cam.capture(0.001).pixels.dtype == np.float32

    def test_pull_image_called_after_trigger(self) -> None:
        cam, tc = self._setup()
        cam.capture(0.001)
        tc.Toupcam.Open.return_value.PullImageV4.assert_called_once_with(
            cam._buf, 0, 0, -1, None
        )

    def test_raises_timeout_when_no_event(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc, timeout_extra=0.05)
        with pytest.raises(TimeoutError):
            cam.capture(0.001)

    def test_raises_runtime_on_error_event(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        tc.Toupcam.Open.return_value.Trigger.side_effect = lambda n: _fire(cam, _EVENT_ERROR)
        with pytest.raises(RuntimeError, match="error"):
            cam.capture(0.001)

    def test_raises_runtime_on_trigger_fail_event(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        tc.Toupcam.Open.return_value.Trigger.side_effect = lambda n: _fire(
            cam, _EVENT_TRIGGER_FAIL
        )
        with pytest.raises(RuntimeError, match="trigger"):
            cam.capture(0.001)

    def test_raises_runtime_on_disconnect_event(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        tc.Toupcam.Open.return_value.Trigger.side_effect = lambda n: _fire(
            cam, _EVENT_DISCONNECTED
        )
        with pytest.raises(RuntimeError, match="disconnected"):
            cam.capture(0.001)

    def test_raises_when_not_connected(self) -> None:
        with pytest.raises(RuntimeError, match="not connected"):
            ToupcamCamera().capture(1.0)


# ── disconnect ─────────────────────────────────────────────────────────────────

class TestDisconnect:
    def test_safe_before_connect(self) -> None:
        ToupcamCamera().disconnect()

    def test_stops_and_closes_camera(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        cam.disconnect()
        hw = tc.Toupcam.Open.return_value
        hw.Stop.assert_called_once()
        hw.Close.assert_called_once()

    def test_safe_to_call_twice(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        cam.disconnect()
        cam.disconnect()


# ── gain / exposure ────────────────────────────────────────────────────────────

class TestGainExposure:
    def test_get_gain_reads_sdk(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_ExpoAGain.return_value = 400
        cam = _connect(tc)
        assert cam.get_gain() == 400

    def test_set_gain_calls_sdk(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        cam.set_gain(500)
        tc.Toupcam.Open.return_value.put_ExpoAGain.assert_called_with(500)

    def test_set_gain_clamps_below_100(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        cam.set_gain(50)
        tc.Toupcam.Open.return_value.put_ExpoAGain.assert_called_with(100)

    def test_get_exposure_ms_converts_from_microseconds(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_ExpoTime.return_value = 2_000_000
        cam = _connect(tc)
        assert cam.get_exposure_ms() == pytest.approx(2000.0)

    def test_set_exposure_ms_converts_to_microseconds(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        cam.set_exposure_ms(500.0)
        tc.Toupcam.Open.return_value.put_ExpoTime.assert_called_with(500_000)

    def test_set_exposure_ms_clamps_below_one_microsecond(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        cam.set_exposure_ms(0.0)
        tc.Toupcam.Open.return_value.put_ExpoTime.assert_called_with(1)


# ── black level / conversion gain ─────────────────────────────────────────────

class TestBlackLevelConversionGain:
    def test_get_black_level_reads_sdk(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_Option.return_value = 42
        cam = _connect(tc)
        assert cam.get_black_level() == 42

    def test_set_black_level_calls_sdk(self) -> None:
        from smart_telescope.adapters.touptek.camera import _OPTION_BLACKLEVEL
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        cam.set_black_level(20)
        tc.Toupcam.Open.return_value.put_Option.assert_any_call(_OPTION_BLACKLEVEL, 20)

    def test_get_conversion_gain_returns_enum(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_Option.return_value = 1  # HCG
        cam = _connect(tc)
        assert cam.get_conversion_gain() == ConversionGain.HCG

    def test_set_conversion_gain_calls_sdk(self) -> None:
        from smart_telescope.adapters.touptek.camera import _OPTION_CG
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        cam.set_conversion_gain(ConversionGain.HDR)
        tc.Toupcam.Open.return_value.put_Option.assert_any_call(_OPTION_CG, 2)


# ── sensor info / capabilities ────────────────────────────────────────────────

class TestSensorInfo:
    def test_get_bit_depth_16_when_option_is_1(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_Option.return_value = 1
        cam = _connect(tc)
        assert cam.get_bit_depth() == 16

    def test_get_bit_depth_8_when_option_is_0(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_Option.return_value = 0
        cam = _connect(tc)
        assert cam.get_bit_depth() == 8

    def test_get_temperature_converts_from_tenths(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_Temperature.return_value = 235
        cam = _connect(tc)
        assert cam.get_temperature() == pytest.approx(23.5)

    def test_get_temperature_returns_none_before_connect(self) -> None:
        assert ToupcamCamera().get_temperature() is None

    def test_get_capabilities_returns_dataclass(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        caps = cam.get_capabilities()
        assert isinstance(caps, CameraCapabilities)

    def test_capabilities_gain_range_from_sdk(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_ExpoAGainRange.return_value = (100, 4800, 100)
        cam = _connect(tc)
        caps = cam.get_capabilities()
        assert caps.min_gain == 100
        assert caps.max_gain == 4800

    def test_capabilities_exposure_range_ms(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_ExpTimeRange.return_value = (200, 120_000_000, 2_000_000)
        cam = _connect(tc)
        caps = cam.get_capabilities()
        assert caps.min_exposure_ms == pytest.approx(0.2)
        assert caps.max_exposure_ms == pytest.approx(120_000.0)

    def test_capabilities_pixel_size_from_sdk(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.get_PixelSize.return_value = (3.76, 3.76)
        cam = _connect(tc)
        caps = cam.get_capabilities()
        assert caps.pixel_size_um == pytest.approx(3.76)

    def test_capabilities_sensor_size_matches_camera(self) -> None:
        tc = _make_toupcam_mock()
        cam = _connect(tc)
        caps = cam.get_capabilities()
        assert caps.sensor_width_px == _WIDTH
        assert caps.sensor_height_px == _HEIGHT

    def test_capabilities_cg_flags_from_model(self) -> None:
        _FLAG_CG = 0x04000000
        tc = _make_toupcam_mock(model_flag=_FLAG_CG)
        cam = _connect(tc)
        caps = cam.get_capabilities()
        assert caps.supports_hcg is True
        assert caps.supports_lcg is True
        assert caps.supports_hdr is False

    def test_capabilities_hdr_flag_from_model(self) -> None:
        _FLAG_CGHDR = 0x0000000800000000
        tc = _make_toupcam_mock(model_flag=_FLAG_CGHDR)
        cam = _connect(tc)
        caps = cam.get_capabilities()
        assert caps.supports_hdr is True

    def test_capabilities_cooling_flag_from_model(self) -> None:
        _FLAG_TEC = 0x00000080
        tc = _make_toupcam_mock(model_flag=_FLAG_TEC)
        cam = _connect(tc)
        caps = cam.get_capabilities()
        assert caps.supports_cooling is True
