# tests/unit/config/test_config_locations_parse.py
from unittest.mock import patch
import smart_telescope.config as config_mod


def _with_cfg(cfg_dict):
    """Context manager: patch _cfg with a test dict, then call the parsing functions."""
    return patch.object(config_mod, "_cfg", cfg_dict)


def test_locations_entirely_empty():
    with _with_cfg({}):
        result = config_mod._parse_locations()
    assert result == {}


def test_locations_one_full_entry():
    with _with_cfg({"locations": {"star_party": {"lat": 49.9, "lon": 9.1, "height_m": 210.0}}}):
        result = config_mod._parse_locations()
    assert result == {
        "star_party": config_mod.LocationSpec(name="star_party", lat=49.9, lon=9.1, height_m=210.0)
    }


def test_locations_missing_height_defaults_to_zero():
    with _with_cfg({"locations": {"balcony": {"lat": 50.0, "lon": 8.0}}}):
        result = config_mod._parse_locations()
    assert result["balcony"].height_m == 0.0


def test_locations_multiple_entries_keyed_by_name():
    with _with_cfg({
        "locations": {
            "a": {"lat": 1.0, "lon": 2.0, "height_m": 3.0},
            "b": {"lat": 4.0, "lon": 5.0, "height_m": 6.0},
        }
    }):
        result = config_mod._parse_locations()
    assert set(result.keys()) == {"a", "b"}
    assert result["a"].lat == 1.0
    assert result["b"].lat == 4.0


def test_locations_malformed_entry_skipped_not_raised():
    with _with_cfg({"locations": {"bad": "not-a-dict", "good": {"lat": 1.0, "lon": 2.0}}}):
        result = config_mod._parse_locations()
    assert "bad" not in result
    assert "good" in result
