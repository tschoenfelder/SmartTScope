"""Tests for adapters/mock/camera.py — MockCamera used in other unit tests."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest

from smart_telescope.adapters.mock.camera import MockCamera, _MOCK_CAPABILITIES
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.ports.camera import CaptureAbortedError


class TestMockCameraConnect:
    def test_connect_returns_true(self) -> None:
        cam = MockCamera()
        assert cam.connect() is True

    def test_connect_fail_returns_false(self) -> None:
        cam = MockCamera(fail_connect=True)
        assert cam.connect() is False


class TestMockCameraCapture:
    def test_capture_returns_frame(self) -> None:
        cam = MockCamera()
        frame = cam.capture(1.0)
        assert frame is not None

    def test_capture_black_frame_is_zeros(self) -> None:
        cam = MockCamera()
        frame = cam.capture(1.0)
        assert np.all(frame.pixels == 0)

    def test_capture_bright_frame_has_stars(self) -> None:
        cam = MockCamera(return_bright=True)
        frame = cam.capture(1.0)
        # Bright frame has star pixels >> 0
        assert frame.pixels.max() > 100

    def test_capture_dim_frame_on_selected_capture(self) -> None:
        cam = MockCamera(dim_on_captures=frozenset({1}))
        frame = cam.capture(1.0)
        # Dim frame has some non-zero pixels but much lower max than bright
        assert frame.pixels.max() < 500

    def test_capture_fails_on_specified_count(self) -> None:
        cam = MockCamera(fail_on_capture=2)
        cam.capture(1.0)  # first: ok
        with pytest.raises(RuntimeError, match="call #2"):
            cam.capture(1.0)  # second: fails

    def test_capture_exposure_seconds_stored(self) -> None:
        cam = MockCamera()
        frame = cam.capture(2.5)
        assert frame.exposure_seconds == pytest.approx(2.5)

    def test_abort_capture_raises(self) -> None:
        cam = MockCamera(capture_delay_s=10.0)

        def _abort() -> None:
            time.sleep(0.05)
            cam.abort_capture()

        t = threading.Thread(target=_abort, daemon=True)
        t.start()
        with pytest.raises(CaptureAbortedError):
            cam.capture(10.0)
        t.join(timeout=1.0)


class TestMockCameraGettersSetters:
    def test_get_set_exposure_ms(self) -> None:
        cam = MockCamera()
        cam.set_exposure_ms(3000.0)
        assert cam.get_exposure_ms() == pytest.approx(3000.0)

    def test_set_exposure_ms_clamps_to_min(self) -> None:
        cam = MockCamera()
        cam.set_exposure_ms(0.0)
        assert cam.get_exposure_ms() == pytest.approx(0.1)

    def test_get_set_gain(self) -> None:
        cam = MockCamera()
        cam.set_gain(500)
        assert cam.get_gain() == 500

    def test_set_gain_clamps_to_min(self) -> None:
        cam = MockCamera()
        cam.set_gain(50)
        assert cam.get_gain() == 100

    def test_get_set_black_level(self) -> None:
        cam = MockCamera()
        cam.set_black_level(10)
        assert cam.get_black_level() == 10

    def test_set_black_level_clamps_to_zero(self) -> None:
        cam = MockCamera()
        cam.set_black_level(-5)
        assert cam.get_black_level() == 0

    def test_get_set_conversion_gain(self) -> None:
        cam = MockCamera()
        cam.set_conversion_gain(ConversionGain.HCG)
        assert cam.get_conversion_gain() == ConversionGain.HCG

    def test_get_bit_depth(self) -> None:
        cam = MockCamera()
        assert cam.get_bit_depth() == 16

    def test_get_temperature_returns_none(self) -> None:
        cam = MockCamera()
        assert cam.get_temperature() is None

    def test_get_capabilities(self) -> None:
        cam = MockCamera()
        caps = cam.get_capabilities()
        assert caps is _MOCK_CAPABILITIES

    def test_get_serial_number_returns_empty(self) -> None:
        cam = MockCamera()
        assert cam.get_serial_number() == ""

    def test_get_logical_name(self) -> None:
        cam = MockCamera()
        assert cam.get_logical_name() == "MockCamera"

    def test_disconnect_is_safe(self) -> None:
        cam = MockCamera()
        cam.disconnect()  # should not raise
