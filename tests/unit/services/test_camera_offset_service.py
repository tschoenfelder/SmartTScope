# tests/unit/services/test_camera_offset_service.py
import pytest
from unittest.mock import MagicMock
from smart_telescope.services.camera_offset_service import CameraOffsetService
from smart_telescope.domain.camera_capabilities import ConversionGain


OFFSETS = {
    "G3M678M":        {"lcg": 150, "hcg": 150},
    "GPCMOS02000KPA": {"lcg": 10,  "hcg": 10},
    "ATR585M":        {"lcg": 150, "hcg": 150},
}


def _mock_camera(logical_name: str, cg: ConversionGain = ConversionGain.LCG) -> MagicMock:
    cam = MagicMock()
    cam.get_logical_name.return_value = logical_name
    cam.get_conversion_gain.return_value = cg
    return cam


# --- get_offset ---

def test_get_offset_exact_match_lcg():
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("G3M678M", ConversionGain.LCG) == 150


def test_get_offset_exact_match_hcg():
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("G3M678M", ConversionGain.HCG) == 150


def test_get_offset_substring_match():
    # "GPCMOS02000KPA" contains "CMOS02000KPA" — should still match
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("CMOS02000KPA", ConversionGain.LCG) == 10


def test_get_offset_case_insensitive():
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("g3m678m", ConversionGain.LCG) == 150


def test_get_offset_unknown_model_returns_none():
    svc = CameraOffsetService(OFFSETS)
    assert svc.get_offset("UNKNOWN_CAM", ConversionGain.LCG) is None


def test_get_offset_unknown_gain_mode_returns_none():
    svc = CameraOffsetService(OFFSETS)
    # HDR not configured for G3M678M
    assert svc.get_offset("G3M678M", ConversionGain.HDR) is None


def test_get_offset_empty_config_returns_none():
    svc = CameraOffsetService({})
    assert svc.get_offset("G3M678M", ConversionGain.LCG) is None


# --- apply ---

def test_apply_sets_black_level_when_configured():
    svc = CameraOffsetService(OFFSETS)
    cam = _mock_camera("G3M678M", ConversionGain.LCG)
    svc.apply(cam)
    cam.set_black_level.assert_called_once_with(150)


def test_apply_hcg_uses_hcg_offset():
    svc = CameraOffsetService(OFFSETS)
    cam = _mock_camera("ATR585M", ConversionGain.HCG)
    svc.apply(cam)
    cam.set_black_level.assert_called_once_with(150)


def test_apply_no_config_does_not_call_set():
    svc = CameraOffsetService({})
    cam = _mock_camera("G3M678M")
    svc.apply(cam)
    cam.set_black_level.assert_not_called()


def test_apply_unknown_camera_does_not_call_set():
    svc = CameraOffsetService(OFFSETS)
    cam = _mock_camera("UNKNOWN_CAMERA")
    svc.apply(cam)
    cam.set_black_level.assert_not_called()


def test_apply_logs_when_no_offset_found(caplog):
    import logging
    svc = CameraOffsetService(OFFSETS)
    cam = _mock_camera("UNKNOWN_CAMERA")
    with caplog.at_level(logging.DEBUG, logger="smart_telescope.services.camera_offset_service"):
        svc.apply(cam)
    assert any("no configured offset" in r.message.lower() for r in caplog.records)


# --- from_config ---

def test_from_config_builds_from_module():
    from unittest.mock import patch
    import smart_telescope.config as cfg
    with patch.object(cfg, "CAMERA_OFFSETS", OFFSETS):
        svc = CameraOffsetService.from_config()
        assert svc.get_offset("G3M678M", ConversionGain.LCG) == 150
