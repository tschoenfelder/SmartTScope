from unittest.mock import patch
import smart_telescope.config as config_mod


def _with_cfg(cfg_dict):
    return patch.object(config_mod, "_cfg", cfg_dict)


def test_parse_camera_offsets_empty():
    with _with_cfg({}):
        result = config_mod._parse_camera_offsets()
    assert result == {}


def test_parse_camera_offsets_basic():
    with _with_cfg({
        "camera_offsets": {
            "G3M678M":        {"lcg": 150, "hcg": 150},
            "GPCMOS02000KPA": {"lcg": 10,  "hcg": 10},
            "ATR585M":        {"lcg": 150, "hcg": 150},
        }
    }):
        result = config_mod._parse_camera_offsets()
    assert result["G3M678M"]["lcg"] == 150
    assert result["G3M678M"]["hcg"] == 150
    assert result["GPCMOS02000KPA"]["lcg"] == 10
    assert result["GPCMOS02000KPA"]["hcg"] == 10
    assert result["ATR585M"]["lcg"] == 150


def test_parse_camera_offsets_keys_lowercase():
    with _with_cfg({
        "camera_offsets": {
            "G3M678M": {"LCG": 150, "HCG": 150},
        }
    }):
        result = config_mod._parse_camera_offsets()
    assert "lcg" in result["G3M678M"]
    assert "hcg" in result["G3M678M"]
    assert "LCG" not in result["G3M678M"]


def test_parse_camera_offsets_non_dict_values_skipped():
    with _with_cfg({
        "camera_offsets": {
            "G3M678M": {"lcg": 150},
            "bad_entry": "not_a_dict",
        }
    }):
        result = config_mod._parse_camera_offsets()
    assert "G3M678M" in result
    assert "bad_entry" not in result
