# tests/unit/config/test_config_camera_parse.py
import tomllib

def _parse_cameras_from(toml_text: str) -> dict:
    cfg = tomllib.loads(toml_text)
    section = cfg.get("cameras", {})
    result: dict = {}
    for role, val in section.items():
        result[role] = int(val) if isinstance(val, (int, float)) else str(val)
    return result

def _parse_camera_serials_from(toml_text: str) -> dict:
    cfg = tomllib.loads(toml_text)
    return {str(k): str(v) for k, v in cfg.get("camera_serials", {}).items()}


def test_cameras_int_values():
    toml = "[cameras]\nmain = 0\nguide = 1\n"
    result = _parse_cameras_from(toml)
    assert result == {"main": 0, "guide": 1}

def test_cameras_string_values():
    toml = '[cameras]\nmain = "G3M678M"\nguide = "ATR585M"\n'
    result = _parse_cameras_from(toml)
    assert result == {"main": "G3M678M", "guide": "ATR585M"}

def test_cameras_mixed_values():
    toml = '[cameras]\nmain = "G3M678M"\nguide = 1\n'
    result = _parse_cameras_from(toml)
    assert result == {"main": "G3M678M", "guide": 1}

def test_camera_serials_empty():
    toml = "[cameras]\nmain = 0\n"
    result = _parse_camera_serials_from(toml)
    assert result == {}

def test_camera_serials_populated():
    toml = (
        '[camera_serials]\n'
        'G3M678M = "tp-4-2-11-0547-14bc"\n'
        'ATR585M = "tp-4-1-10-0547-157c"\n'
        'GPCMOS02000KPA = "tp-3-4-23-0547-1367"\n'
    )
    result = _parse_camera_serials_from(toml)
    assert result["G3M678M"] == "tp-4-2-11-0547-14bc"
    assert result["ATR585M"] == "tp-4-1-10-0547-157c"
    assert result["GPCMOS02000KPA"] == "tp-3-4-23-0547-1367"
