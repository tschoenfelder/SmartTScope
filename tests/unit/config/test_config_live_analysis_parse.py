# tests/unit/config/test_config_live_analysis_parse.py
"""[live_analysis] parser — M10-003 core fields + M10-005 auto-tune bounds."""
from unittest.mock import patch

import smart_telescope.config as config_mod


def _with_cfg(cfg_dict):
    return patch.object(config_mod, "_cfg", cfg_dict)


def test_defaults_when_section_missing():
    with _with_cfg({}):
        spec = config_mod._parse_live_analysis_spec()
    assert spec.enabled is True
    assert spec.setup_exposure_s == 1.0
    assert spec.max_tuning_exposure_s == 5.0
    assert spec.min_tuning_exposure_s == 0.05
    assert spec.tuning_gain_min == 100
    assert spec.tuning_gain_max == 3200
    assert spec.tuning_offset_min == 0
    assert spec.tuning_offset_max == 200
    assert spec.histogram_ceiling_frac == 0.70


def test_auto_tune_bounds_parsed_from_config():
    with _with_cfg({
        "live_analysis": {
            "max_tuning_exposure_s": 8.0,
            "min_tuning_exposure_s": 0.1,
            "tuning_gain_min": 120,
            "tuning_gain_max": 2000,
            "tuning_offset_min": 5,
            "tuning_offset_max": 150,
            "histogram_ceiling_frac": 0.65,
        }
    }):
        spec = config_mod._parse_live_analysis_spec()
    assert spec.max_tuning_exposure_s == 8.0
    assert spec.min_tuning_exposure_s == 0.1
    assert spec.tuning_gain_min == 120
    assert spec.tuning_gain_max == 2000
    assert spec.tuning_offset_min == 5
    assert spec.tuning_offset_max == 150
    assert spec.histogram_ceiling_frac == 0.65


def test_core_fields_unaffected_by_new_bounds():
    with _with_cfg({"live_analysis": {"tuning_frames": 4, "star_count_min": 5}}):
        spec = config_mod._parse_live_analysis_spec()
    assert spec.tuning_frames == 4
    assert spec.star_count_min == 5
    assert spec.max_tuning_exposure_s == 5.0  # untouched default
