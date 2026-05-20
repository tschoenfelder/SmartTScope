"""Tests for CameraOffsetService wiring in RuntimeContext."""
from unittest.mock import MagicMock
import smart_telescope.config as cfg
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.services.camera_offset_service import CameraOffsetService


def test_apply_camera_offsets_calls_apply_on_all_cameras(monkeypatch):
    """RuntimeContext._apply_camera_offsets() applies offset to each connected camera."""
    monkeypatch.setattr(cfg, "CAMERA_OFFSETS", {"MockCam": {"lcg": 42}})

    # Build a service from the patched config
    svc = CameraOffsetService.from_config()

    from smart_telescope.runtime import RuntimeContext
    ctx = RuntimeContext.__new__(RuntimeContext)
    ctx.camera_offset_service = svc

    mock_cam = MagicMock()
    mock_cam.get_logical_name.return_value = "MockCam"
    mock_cam.get_conversion_gain.return_value = ConversionGain.LCG

    ctx._camera = mock_cam
    ctx._preview_cameras = {}

    ctx._apply_camera_offsets()

    mock_cam.set_black_level.assert_called_once_with(42)


def test_apply_camera_offsets_includes_preview_cameras(monkeypatch):
    """_apply_camera_offsets() also applies to preview cameras."""
    monkeypatch.setattr(cfg, "CAMERA_OFFSETS", {"MockCam": {"lcg": 10}})

    svc = CameraOffsetService.from_config()

    from smart_telescope.runtime import RuntimeContext
    ctx = RuntimeContext.__new__(RuntimeContext)
    ctx.camera_offset_service = svc

    ctx._camera = None
    preview_cam = MagicMock()
    preview_cam.get_logical_name.return_value = "MockCam"
    preview_cam.get_conversion_gain.return_value = ConversionGain.LCG
    ctx._preview_cameras = {"solver": preview_cam}

    ctx._apply_camera_offsets()

    preview_cam.set_black_level.assert_called_once_with(10)


def test_apply_camera_offsets_exception_does_not_propagate(monkeypatch):
    """A failing apply() is logged as warning but does not raise."""
    monkeypatch.setattr(cfg, "CAMERA_OFFSETS", {})

    from smart_telescope.runtime import RuntimeContext
    ctx = RuntimeContext.__new__(RuntimeContext)
    ctx.camera_offset_service = CameraOffsetService.from_config()

    broken_cam = MagicMock()
    broken_cam.get_logical_name.side_effect = RuntimeError("camera gone")
    ctx._camera = broken_cam
    ctx._preview_cameras = {}

    ctx._apply_camera_offsets()  # must not raise
