"""Tests for CollimationAssistant guiding integration."""
import pytest
from smart_telescope.domain.collimation.config import CollimationConfig


def test_collimation_config_guiding_defaults():
    cfg = CollimationConfig.from_dict({})
    assert cfg.guiding_camera_role == "guide"
    assert cfg.guiding_exposure_s == 2.0
    assert cfg.guiding_cadence_s == 3.0


def test_collimation_config_guiding_from_toml():
    cfg = CollimationConfig.from_dict({
        "guiding_camera_role": "oag",
        "guiding_exposure_s": 1.5,
        "guiding_cadence_s": 2.0,
    })
    assert cfg.guiding_camera_role == "oag"
    assert cfg.guiding_exposure_s == 1.5
    assert cfg.guiding_cadence_s == 2.0
