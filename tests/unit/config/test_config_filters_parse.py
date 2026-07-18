# tests/unit/config/test_config_filters_parse.py
"""[filters] parser — M10-014: 1-based wheel slot → filter name."""
from unittest.mock import patch

import smart_telescope.config as config_mod


def _with_cfg(cfg_dict):
    return patch.object(config_mod, "_cfg", cfg_dict)


def test_canonical_slot_to_name_format():
    with _with_cfg({"filters": {"1": "Luminance", "2": "Red", "5": "H_Alpha"}}):
        result = config_mod._parse_filters()
    assert result == {1: "Luminance", 2: "Red", 5: "H_Alpha"}


def test_int_keys_accepted():
    # tomllib always yields string keys, but a dict injected in tests may not.
    with _with_cfg({"filters": {1: "Luminance"}}):
        result = config_mod._parse_filters()
    assert result == {1: "Luminance"}


def test_legacy_name_to_slot_format_inverted():
    with _with_cfg({"filters": {"red": 1, "h-alpha": 5}}):
        result = config_mod._parse_filters()
    assert result == {1: "red", 5: "h-alpha"}


def test_canonical_wins_over_legacy_for_same_slot():
    with _with_cfg({"filters": {"1": "Luminance", "red": 1}}):
        result = config_mod._parse_filters()
    assert result == {1: "Luminance"}


def test_unparseable_entries_skipped():
    with _with_cfg({"filters": {"red": "not-a-slot"}}):
        result = config_mod._parse_filters()
    assert result == {}


def test_no_filters_section_gives_empty_dict():
    with _with_cfg({}):
        result = config_mod._parse_filters()
    assert result == {}
