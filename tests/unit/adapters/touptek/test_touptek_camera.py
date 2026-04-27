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
from smart_telescope.domain.frame import FitsFrame

_WIDTH, _HEIGHT = 100, 80


def _make_toupcam_mock(
    num_devices: int = 1,
    open_succeeds: bool = True,
) -> MagicMock:
    tc = MagicMock()
    tc.TOUPCAM_OPTION_TRIGGER = 0x0B
    tc.TOUPCAM_OPTION_RAW = 0x04
    tc.TOUPCAM_OPTION_BITDEPTH = 0x06
    tc.Toupcam.EnumV2.return_value = [MagicMock() for _ in range(num_devices)]
    if open_succeeds:
        hw = MagicMock()
        hw.get_Size.return_value = (_WIDTH, _HEIGHT)
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

    def test_false_when_no_devices(self) -> None:
        cam = ToupcamCamera()
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(num_devices=0)}):
            assert cam.connect() is False

    def test_false_when_index_exceeds_device_count(self) -> None:
        cam = ToupcamCamera(index=1)
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(num_devices=1)}):
            assert cam.connect() is False

    def test_false_when_open_returns_none(self) -> None:
        cam = ToupcamCamera()
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(open_succeeds=False)}):
            assert cam.connect() is False

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

    def test_false_and_camera_closed_when_option_raises(self) -> None:
        tc = _make_toupcam_mock()
        tc.Toupcam.Open.return_value.put_Option.side_effect = RuntimeError("hw fault")
        cam = ToupcamCamera()
        with patch.dict(sys.modules, {"toupcam": tc}):
            assert cam.connect() is False
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
