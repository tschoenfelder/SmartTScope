# tests/unit/config/test_config_camera_parse.py
from unittest.mock import patch
import smart_telescope.config as config_mod


def _with_cfg(cfg_dict):
    """Context manager: patch _cfg with a test dict, then call the parsing functions."""
    return patch.object(config_mod, "_cfg", cfg_dict)


def test_cameras_int_values():
    with _with_cfg({"cameras": {"main": 0, "guide": 1}}):
        result = config_mod._parse_cameras()
    assert result == {"main": 0, "guide": 1}


def test_cameras_string_values():
    with _with_cfg({"cameras": {"main": "G3M678M", "guide": "ATR585M"}}):
        result = config_mod._parse_cameras()
    assert result == {"main": "G3M678M", "guide": "ATR585M"}


def test_cameras_mixed_values():
    with _with_cfg({"cameras": {"main": "G3M678M", "guide": 1}}):
        result = config_mod._parse_cameras()
    assert result == {"main": "G3M678M", "guide": 1}


def test_cameras_empty_falls_back_to_legacy():
    with _with_cfg({"hardware": {"touptek_index": "0"}}):
        result = config_mod._parse_cameras()
    assert result == {"main": 0}


def test_cameras_entirely_empty():
    with _with_cfg({}):
        result = config_mod._parse_cameras()
    assert result == {}


def test_camera_serials_empty():
    with _with_cfg({"cameras": {"main": 0}}):
        result = config_mod._parse_camera_serials()
    assert result == {}


def test_camera_serials_populated():
    with _with_cfg({
        "camera_serials": {
            "G3M678M":        "tp-4-2-11-0547-14bc",
            "ATR585M":        "tp-4-1-10-0547-157c",
            "GPCMOS02000KPA": "tp-3-4-23-0547-1367",
        }
    }):
        result = config_mod._parse_camera_serials()
    assert result["G3M678M"] == "tp-4-2-11-0547-14bc"
    assert result["ATR585M"] == "tp-4-1-10-0547-157c"
    assert result["GPCMOS02000KPA"] == "tp-3-4-23-0547-1367"
