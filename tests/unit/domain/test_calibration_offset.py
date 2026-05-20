"""Tests that calibration_capture functions apply camera offsets after gain change.

CO-T5: inject CameraOffsetService into prepare_bias, prepare_dark, prepare_flat.
"""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, call

import numpy as np
import pytest
from astropy.io import fits

from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.services.camera_offset_service import CameraOffsetService
from smart_telescope.domain import calibration_capture


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_frame():
    from smart_telescope.domain.frame import FitsFrame
    hdr = fits.Header()
    hdr["BITPIX"] = -32
    return FitsFrame(
        pixels=np.full((100, 100), 150.0, dtype=np.float32),
        header=hdr,
        exposure_seconds=0.001,
    )


def _mock_camera(name: str = "G3M678M") -> MagicMock:
    cam = MagicMock()
    cam.get_logical_name.return_value = name
    cam.get_conversion_gain.return_value = ConversionGain.LCG
    cam.get_gain.return_value = 100
    cam.get_black_level.return_value = 150
    cam.get_bit_depth.return_value = 16
    cam.get_exposure_ms.return_value = 0.05
    cam.get_serial_number.return_value = "SN1"
    cam.get_temperature.return_value = 20.0
    cam.get_capabilities.return_value = MagicMock(
        min_exposure_ms=0.05,
        max_exposure_ms=3_600_000.0,
    )
    cam.capture.return_value = _make_frame()
    return cam


# ── signature tests ───────────────────────────────────────────────────────────


def test_prepare_bias_accepts_offset_service():
    """prepare_bias must accept an offset_service keyword argument."""
    sig = inspect.signature(calibration_capture.prepare_bias)
    assert "offset_service" in sig.parameters


def test_prepare_dark_accepts_offset_service():
    sig = inspect.signature(calibration_capture.prepare_dark)
    assert "offset_service" in sig.parameters


def test_prepare_flat_accepts_offset_service():
    sig = inspect.signature(calibration_capture.prepare_flat)
    assert "offset_service" in sig.parameters


def test_prepare_bias_offset_service_defaults_to_none():
    """offset_service=None is the default (backward-compatible)."""
    param = inspect.signature(calibration_capture.prepare_bias).parameters["offset_service"]
    assert param.default is None


def test_prepare_dark_offset_service_defaults_to_none():
    param = inspect.signature(calibration_capture.prepare_dark).parameters["offset_service"]
    assert param.default is None


def test_prepare_flat_offset_service_defaults_to_none():
    param = inspect.signature(calibration_capture.prepare_flat).parameters["offset_service"]
    assert param.default is None


# ── apply-after-gain-change tests ─────────────────────────────────────────────


def test_prepare_bias_applies_offset_after_gain_change(tmp_path):
    """prepare_bias calls offset_service.apply(camera) after set_conversion_gain."""
    cam = _mock_camera()
    offset_svc = MagicMock(spec=CameraOffsetService)
    idx_mock = MagicMock()

    # Track call order
    call_order: list[str] = []
    cam.set_conversion_gain.side_effect = lambda cg: call_order.append("set_gain")
    offset_svc.apply.side_effect = lambda c: call_order.append("apply")

    calibration_capture.prepare_bias(
        cam, 2, tmp_path, idx_mock,
        gain=100,
        offset=None,
        conversion_gain=ConversionGain.HCG,
        offset_service=offset_svc,
    )

    cam.set_conversion_gain.assert_called_with(ConversionGain.HCG)
    offset_svc.apply.assert_called_with(cam)
    assert call_order.index("set_gain") < call_order.index("apply"), \
        "set_conversion_gain must be called before offset_service.apply()"


def test_prepare_dark_applies_offset_after_gain_change(tmp_path):
    """prepare_dark calls offset_service.apply(camera) after set_conversion_gain."""
    cam = _mock_camera()
    offset_svc = MagicMock(spec=CameraOffsetService)
    idx_mock = MagicMock()

    # Track call order
    call_order: list[str] = []
    cam.set_conversion_gain.side_effect = lambda cg: call_order.append("set_gain")
    offset_svc.apply.side_effect = lambda c: call_order.append("apply")

    calibration_capture.prepare_dark(
        cam, 50.0, 2, tmp_path, idx_mock,
        gain=100,
        offset=None,
        conversion_gain=ConversionGain.HCG,
        offset_service=offset_svc,
    )

    cam.set_conversion_gain.assert_called_with(ConversionGain.HCG)
    offset_svc.apply.assert_called_with(cam)
    assert call_order.index("set_gain") < call_order.index("apply"), \
        "set_conversion_gain must be called before offset_service.apply()"


def _make_flat_frame(bit_depth: int = 16):
    """Return a FitsFrame whose p50 falls in the 40–60% accept zone."""
    from smart_telescope.domain.frame import FitsFrame
    hdr = fits.Header()
    hdr["BITPIX"] = -32
    max_adu = (2**bit_depth) - 1
    # p50 ≈ 50% of range → uniform value at 50%
    fill_value = float(max_adu * 0.50)
    return FitsFrame(
        pixels=np.full((100, 100), fill_value, dtype=np.float32),
        header=hdr,
        exposure_seconds=1.0,
    )


def test_prepare_flat_applies_offset_after_gain_change(tmp_path):
    """prepare_flat calls offset_service.apply(camera) after set_conversion_gain."""
    cam = _mock_camera()
    # Override capture to return a frame with p50 ≈ 50% so flat tuning succeeds
    cam.capture.return_value = _make_flat_frame()
    cam.get_exposure_ms.return_value = 1000.0
    offset_svc = MagicMock(spec=CameraOffsetService)
    idx_mock = MagicMock()

    # Track call order
    call_order: list[str] = []
    cam.set_conversion_gain.side_effect = lambda cg: call_order.append("set_gain")
    offset_svc.apply.side_effect = lambda c: call_order.append("apply")

    calibration_capture.prepare_flat(
        cam, "main-train", "none", 2, tmp_path, idx_mock,
        gain=100,
        offset=None,
        conversion_gain=ConversionGain.HCG,
        offset_service=offset_svc,
    )

    cam.set_conversion_gain.assert_called_with(ConversionGain.HCG)
    offset_svc.apply.assert_called_with(cam)
    assert call_order.index("set_gain") < call_order.index("apply"), \
        "set_conversion_gain must be called before offset_service.apply()"


def test_offset_not_called_when_service_is_none(tmp_path):
    """No crash when offset_service=None (backward compatibility)."""
    cam = _mock_camera()
    idx_mock = MagicMock()

    # Should complete without error
    calibration_capture.prepare_bias(
        cam, 1, tmp_path, idx_mock,
        gain=100,
        offset=None,
        conversion_gain=ConversionGain.LCG,
        offset_service=None,
    )
    cam.set_black_level.assert_not_called()


def test_offset_not_called_when_no_conversion_gain(tmp_path):
    """When conversion_gain=None, set_conversion_gain is not called so apply is not called."""
    cam = _mock_camera()
    offset_svc = MagicMock(spec=CameraOffsetService)
    idx_mock = MagicMock()

    calibration_capture.prepare_bias(
        cam, 1, tmp_path, idx_mock,
        gain=100,
        offset=None,
        conversion_gain=None,
        offset_service=offset_svc,
    )

    cam.set_conversion_gain.assert_not_called()
    offset_svc.apply.assert_not_called()


def test_dark_offset_not_called_when_no_conversion_gain(tmp_path):
    """prepare_dark: offset_service.apply() is not called when conversion_gain=None."""
    cam = _mock_camera()
    offset_svc = MagicMock(spec=CameraOffsetService)
    idx_mock = MagicMock()

    calibration_capture.prepare_dark(
        cam, 50.0, 1, tmp_path, idx_mock,
        gain=100,
        offset=None,
        conversion_gain=None,
        offset_service=offset_svc,
    )

    cam.set_conversion_gain.assert_not_called()
    offset_svc.apply.assert_not_called()


def test_flat_offset_not_called_when_no_conversion_gain(tmp_path):
    """prepare_flat: offset_service.apply() is not called when conversion_gain=None."""
    cam = _mock_camera()
    cam.capture.return_value = _make_flat_frame()
    cam.get_exposure_ms.return_value = 1000.0
    offset_svc = MagicMock(spec=CameraOffsetService)
    idx_mock = MagicMock()

    calibration_capture.prepare_flat(
        cam, "main-train", "none", 1, tmp_path, idx_mock,
        gain=100,
        offset=None,
        conversion_gain=None,
        offset_service=offset_svc,
    )

    cam.set_conversion_gain.assert_not_called()
    offset_svc.apply.assert_not_called()
