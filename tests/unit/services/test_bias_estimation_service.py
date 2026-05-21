"""Tests for BiasEstimationService — TDD for COE-T2."""
import threading
import numpy as np
import pytest
from unittest.mock import MagicMock, call
from astropy.io import fits

from smart_telescope.domain.bias_estimation import ZERO_CLIP_THRESHOLD, DEFAULT_SWEEP_OFFSETS
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.services.bias_estimation_service import BiasEstimationService


def _make_frame(fill: float = 20.0, shape: tuple = (100, 100)) -> FitsFrame:
    pixels = np.full(shape, fill, dtype=np.float32)
    hdr = fits.Header()
    hdr["BITPIX"] = -32
    return FitsFrame(pixels=pixels, header=hdr, exposure_seconds=0.0001)


def _zero_frame(shape: tuple = (100, 100)) -> FitsFrame:
    return _make_frame(fill=0.0, shape=shape)


def _mock_camera(
    logical_name: str = "G3M678M",
    gain_mode: ConversionGain = ConversionGain.LCG,
    min_exp_ms: float = 0.1,
    frame_factory=None,
) -> MagicMock:
    cam = MagicMock()
    cam.get_logical_name.return_value = logical_name
    cam.get_conversion_gain.return_value = gain_mode
    caps = MagicMock()
    caps.min_exposure_ms = min_exp_ms
    cam.get_capabilities.return_value = caps
    cam.get_black_level.return_value = 0
    if frame_factory is None:
        cam.capture.return_value = _make_frame(50.0)
    else:
        cam.capture.side_effect = frame_factory
    return cam


# --- basic capture + analyze ---

def test_estimate_returns_result_with_model_and_gain():
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=3, sweep_offsets=[])
    assert result.camera_model == "G3M678M"
    assert result.gain_mode_name == "LCG"
    assert result.frame_count == 3


def test_estimate_captures_at_minimum_exposure():
    cam = _mock_camera(min_exp_ms=0.05)
    svc = BiasEstimationService(cam)
    svc.estimate(ConversionGain.LCG, frame_count=2, sweep_offsets=[])
    for c in cam.capture.call_args_list:
        exp_s = c.args[0] if c.args else c.kwargs.get("exposure_seconds", 1.0)
        assert exp_s == pytest.approx(0.05 / 1000.0)


def test_estimate_sets_gain_mode_before_capture():
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    svc.estimate(ConversionGain.HCG, frame_count=2, sweep_offsets=[])
    cam.set_conversion_gain.assert_called_with(ConversionGain.HCG)


def test_estimate_restores_original_offset_after_sweep():
    cam = _mock_camera()
    cam.get_black_level.return_value = 42
    svc = BiasEstimationService(cam)
    svc.estimate(ConversionGain.LCG, frame_count=1, sweep_offsets=[0, 10, 20])
    # Last set_black_level call must restore original offset
    last_call = cam.set_black_level.call_args_list[-1]
    assert last_call == call(42)


# --- sweep logic ---

def test_sweep_produces_one_point_per_offset_value():
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=2, sweep_offsets=[0, 5, 10, 20])
    assert len(result.sweep) == 4
    assert [pt.offset for pt in result.sweep] == [0, 5, 10, 20]


def test_sweep_detects_clipping_at_zero_offset():
    cam = _mock_camera(frame_factory=lambda exp_s: _zero_frame())
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=1, sweep_offsets=[0])
    assert result.sweep[0].zero_fraction > ZERO_CLIP_THRESHOLD
    assert result.sweep[0].is_safe is False


def test_sweep_marks_safe_when_no_zero_pixels():
    cam = _mock_camera()  # returns fill=50 frame, no zeros
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=1, sweep_offsets=[50])
    assert result.sweep[0].is_safe is True


def test_sweep_uses_default_offsets_when_none():
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    result = svc.estimate(ConversionGain.LCG, frame_count=1, sweep_offsets=None)
    assert [pt.offset for pt in result.sweep] == DEFAULT_SWEEP_OFFSETS


# --- cancellation ---

def test_estimate_respects_cancel_event():
    cancel = threading.Event()
    cancel.set()  # cancelled immediately
    cam = _mock_camera()
    svc = BiasEstimationService(cam)
    result = svc.estimate(
        ConversionGain.LCG, frame_count=100,
        sweep_offsets=[0, 5, 10, 20, 30],
        cancel_event=cancel,
    )
    # Should return early — far fewer than 100 captures
    assert cam.capture.call_count < 100
