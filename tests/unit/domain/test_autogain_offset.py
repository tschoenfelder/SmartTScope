"""Tests that AutoGainService re-applies camera offset after every gain change (CO-T4)."""
from __future__ import annotations

import inspect
from unittest.mock import MagicMock, call

import numpy as np
import pytest

from smart_telescope.domain.autogain import AutoGainMode
from smart_telescope.domain.autogain_service import AutoGainService
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.domain.camera_profile import ATR585M
from smart_telescope.domain.frame import FitsFrame
from smart_telescope.services.camera_offset_service import CameraOffsetService


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_offset_service() -> MagicMock:
    return MagicMock(spec=CameraOffsetService)


def _frame(mean_frac: float) -> MagicMock:
    """Return a minimal FitsFrame mock with 64×64 pixels at the given mean_frac."""
    BIT_DEPTH = 16
    ADC_MAX = float((1 << BIT_DEPTH) - 1)
    pix = np.full((64, 64), mean_frac * ADC_MAX, dtype=np.float32)
    mock = MagicMock(spec=FitsFrame)
    mock.pixels = pix
    return mock


def _make_camera(cg: ConversionGain = ConversionGain.LCG) -> MagicMock:
    """Return a camera stub that captures one in-band frame."""
    cam = MagicMock()
    cam.get_logical_name.return_value = "MockCam"
    cam.get_bit_depth.return_value = 16
    cam.get_conversion_gain.return_value = cg
    # Return a frame with mean_frac=0.50 (inside DSO band 0.30–0.70 → OK on iter 1)
    cam.capture.return_value = _frame(0.50)
    return cam


# ── signature tests ───────────────────────────────────────────────────────────

def test_run_one_shot_accepts_offset_service_param():
    """run_one_shot must accept an offset_service keyword argument."""
    sig = inspect.signature(AutoGainService.run_one_shot)
    assert "offset_service" in sig.parameters, (
        "AutoGainService.run_one_shot must have an 'offset_service' parameter"
    )


def test_offset_service_defaults_to_none():
    """offset_service defaults to None for backward compatibility."""
    sig = inspect.signature(AutoGainService.run_one_shot)
    param = sig.parameters["offset_service"]
    assert param.default is None, (
        "offset_service parameter must default to None"
    )


# ── behaviour tests ───────────────────────────────────────────────────────────

def test_apply_called_after_set_conversion_gain():
    """offset_service.apply(camera) is called after set_conversion_gain."""
    offset_svc = _make_offset_service()
    camera = _make_camera()

    call_order: list[str] = []
    camera.set_conversion_gain.side_effect = lambda _cg: call_order.append("set_gain")
    offset_svc.apply.side_effect = lambda _cam: call_order.append("apply")

    AutoGainService.run_one_shot(
        camera=camera,
        profile=ATR585M,
        mode=AutoGainMode.DSO,
        max_iterations=1,
        offset_service=offset_svc,
    )

    assert "set_gain" in call_order, "set_conversion_gain was never called"
    assert "apply" in call_order, "offset_service.apply was never called"

    # apply must immediately follow set_gain
    idx_gain  = call_order.index("set_gain")
    idx_apply = call_order.index("apply")
    assert idx_apply == idx_gain + 1, (
        f"apply() must be called immediately after set_conversion_gain; "
        f"call_order={call_order}"
    )


def test_apply_called_with_camera_instance():
    """offset_service.apply is called with the camera that changed gain."""
    offset_svc = _make_offset_service()
    camera = _make_camera()

    AutoGainService.run_one_shot(
        camera=camera,
        profile=ATR585M,
        mode=AutoGainMode.DSO,
        max_iterations=1,
        offset_service=offset_svc,
    )

    offset_svc.apply.assert_called_with(camera)


def test_apply_not_called_when_offset_service_is_none():
    """No crash and no apply when offset_service=None (default)."""
    camera = _make_camera()
    # Should complete without error — no offset service
    result = AutoGainService.run_one_shot(
        camera=camera,
        profile=ATR585M,
        mode=AutoGainMode.DSO,
        max_iterations=1,
        offset_service=None,
    )
    # Just verify it returned a valid result
    assert result is not None
