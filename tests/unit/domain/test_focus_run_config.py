"""Unit tests for FocusRunConfig — the focus-run policy object."""
import pytest

from smart_telescope.domain.autofocus import AutofocusParams, FocusRunConfig


class TestFocusRunConfigDefaults:
    def test_skip_defaults_to_false(self):
        assert FocusRunConfig().skip is False

    def test_defaults_produce_valid_autofocus_params(self):
        params = FocusRunConfig().to_params()
        assert isinstance(params, AutofocusParams)

    def test_default_range_steps(self):
        assert FocusRunConfig().range_steps == 200

    def test_default_step_size(self):
        assert FocusRunConfig().step_size == 20

    def test_default_exposure_s(self):
        assert FocusRunConfig().exposure_s == pytest.approx(3.0)

    def test_default_backlash_steps(self):
        assert FocusRunConfig().backlash_steps == 0


class TestFocusRunConfigToParams:
    def test_to_params_maps_range_steps(self):
        params = FocusRunConfig(range_steps=500).to_params()
        assert params.range_steps == 500

    def test_to_params_maps_step_size(self):
        params = FocusRunConfig(step_size=50).to_params()
        assert params.step_size == 50

    def test_to_params_maps_exposure_s_to_exposure(self):
        params = FocusRunConfig(exposure_s=4.5).to_params()
        assert params.exposure == pytest.approx(4.5)

    def test_to_params_maps_backlash_steps(self):
        params = FocusRunConfig(backlash_steps=30).to_params()
        assert params.backlash_steps == 30

    def test_to_params_excludes_skip_field(self):
        params = FocusRunConfig(skip=True).to_params()
        assert not hasattr(params, "skip")

    def test_to_params_invalid_step_raises(self):
        with pytest.raises(ValueError):
            FocusRunConfig(step_size=0).to_params()
