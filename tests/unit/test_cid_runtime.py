"""Tests for CameraNameResolver integration in runtime._build_adapters().

Task 3 of the Camera ID Mapping plan: verify that _build_adapters() passes
TOUPTEK_INDEX (string or numeric) through CameraNameResolver instead of calling
int() directly.
"""
from unittest.mock import MagicMock, patch
from smart_telescope.runtime import _build_adapters, RuntimeContext


def test_build_adapters_calls_resolver_for_named_camera(monkeypatch):
    """When TOUPTEK_INDEX is a model name string, resolver is called to get SDK index."""
    import smart_telescope.config as cfg
    import smart_telescope.services.camera_name_resolver as resolver_mod

    monkeypatch.setattr(cfg, "TOUPTEK_INDEX", "G3M678M")
    monkeypatch.setattr(cfg, "CAMERA_SERIALS", {"G3M678M": "tp-4-2-11-0547-14bc"})
    monkeypatch.setattr(cfg, "ONSTEP_PORT", "")
    monkeypatch.delenv("TOUPTEK_INDEX", raising=False)
    monkeypatch.delenv("ONSTEP_PORT", raising=False)
    monkeypatch.delenv("SIMULATOR_FITS_DIR", raising=False)
    monkeypatch.delenv("REPLAY_FITS_DIR", raising=False)

    mock_resolver_instance = MagicMock()
    mock_resolver_instance.resolve.return_value = 1
    mock_resolver_cls = MagicMock(return_value=mock_resolver_instance)
    monkeypatch.setattr(resolver_mod, "CameraNameResolver", mock_resolver_cls)

    mock_cam_instance = MagicMock()
    mock_cam_cls = MagicMock(return_value=mock_cam_instance)

    with patch("smart_telescope.adapters.touptek.camera.ToupcamCamera", mock_cam_cls):
        ctx = RuntimeContext()
        _build_adapters(ctx)

    mock_resolver_instance.resolve.assert_called_once_with(
        "G3M678M", {"G3M678M": "tp-4-2-11-0547-14bc"}
    )
    mock_cam_cls.assert_called_once_with(index=1)


def test_build_adapters_integer_index_resolves_via_resolver(monkeypatch):
    """Numeric string '0' is still passed through resolver (which fast-paths it)."""
    import smart_telescope.config as cfg
    import smart_telescope.services.camera_name_resolver as resolver_mod

    monkeypatch.setattr(cfg, "TOUPTEK_INDEX", "0")
    monkeypatch.setattr(cfg, "CAMERA_SERIALS", {})
    monkeypatch.setattr(cfg, "ONSTEP_PORT", "")
    monkeypatch.delenv("TOUPTEK_INDEX", raising=False)
    monkeypatch.delenv("ONSTEP_PORT", raising=False)
    monkeypatch.delenv("SIMULATOR_FITS_DIR", raising=False)
    monkeypatch.delenv("REPLAY_FITS_DIR", raising=False)

    mock_resolver_instance = MagicMock()
    mock_resolver_instance.resolve.return_value = 0
    mock_resolver_cls = MagicMock(return_value=mock_resolver_instance)
    monkeypatch.setattr(resolver_mod, "CameraNameResolver", mock_resolver_cls)

    mock_cam_cls = MagicMock()
    with patch("smart_telescope.adapters.touptek.camera.ToupcamCamera", mock_cam_cls):
        ctx = RuntimeContext()
        _build_adapters(ctx)

    mock_resolver_instance.resolve.assert_called_once_with("0", {})
    mock_cam_cls.assert_called_once_with(index=0)
