"""Unit tests for camera profiles and optical train profiles."""
import pytest

from smart_telescope.domain.camera_profile import (
    ALL_PROFILES,
    ATR585M,
    G3M678M,
    GPCMOS02000KPA,
    get_profile,
)
from smart_telescope.domain.optical_train import (
    ALL_TRAINS,
    C8_BARLOW_2X_678M,
    C8_NATIVE_ATR585M,
    C8_NATIVE_678M,
    C8_REDUCER_063_ATR585M,
    C8_REDUCER_063_678M,
    GUIDESCOPE_IMX290,
    OAG_678M,
    OpticalTrainProfile,
    TrainRole,
    get_train,
)


# ── CameraProfile constants ────────────────────────────────────────────────────

class TestATR585M:
    def test_sensor(self) -> None:
        assert ATR585M.sensor == "IMX585"

    def test_dimensions(self) -> None:
        assert ATR585M.width_px == 3840
        assert ATR585M.height_px == 2160

    def test_pixel_size(self) -> None:
        assert ATR585M.pixel_um == pytest.approx(2.9)

    def test_supports_cooling(self) -> None:
        assert ATR585M.supports_cooling is True

    def test_unity_gains_present(self) -> None:
        assert ATR585M.unity_gain_hcg is not None
        assert ATR585M.unity_gain_lcg is not None
        assert ATR585M.unity_gain_hdr is not None

    def test_unity_gain_hcg_greater_than_lcg(self) -> None:
        assert ATR585M.unity_gain_hcg > ATR585M.unity_gain_lcg  # type: ignore[operator]

    def test_preview_exp_bounds(self) -> None:
        assert ATR585M.min_preview_exp_ms > 0
        assert ATR585M.max_preview_exp_ms >= 4000.0


class TestG3M678M:
    def test_sensor(self) -> None:
        assert G3M678M.sensor == "IMX678"

    def test_no_hdr(self) -> None:
        assert G3M678M.unity_gain_hdr is None

    def test_has_hcg_and_lcg(self) -> None:
        assert G3M678M.unity_gain_hcg is not None
        assert G3M678M.unity_gain_lcg is not None

    def test_no_cooling(self) -> None:
        assert G3M678M.supports_cooling is False

    def test_pixel_size(self) -> None:
        assert G3M678M.pixel_um == pytest.approx(2.0)


class TestGPCMOS02000KPA:
    def test_sensor(self) -> None:
        assert GPCMOS02000KPA.sensor == "IMX290"

    def test_no_conversion_gain(self) -> None:
        assert GPCMOS02000KPA.unity_gain_hcg is None
        assert GPCMOS02000KPA.unity_gain_lcg is None
        assert GPCMOS02000KPA.unity_gain_hdr is None

    def test_dimensions(self) -> None:
        assert GPCMOS02000KPA.width_px == 1920
        assert GPCMOS02000KPA.height_px == 1080


class TestProfileRegistry:
    def test_all_profiles_has_three_entries(self) -> None:
        assert len(ALL_PROFILES) == 3

    def test_get_profile_returns_known(self) -> None:
        assert get_profile("ATR585M") is ATR585M

    def test_get_profile_returns_none_for_unknown(self) -> None:
        assert get_profile("nonexistent") is None

    def test_all_profiles_indexed_by_model(self) -> None:
        for model, profile in ALL_PROFILES.items():
            assert profile.model == model


# ── OpticalTrainProfile pixel scale ───────────────────────────────────────────

class TestPixelScaleFormula:
    def test_c8_native_atr585m(self) -> None:
        # 2.9 um * 206.265 / 2030 mm ≈ 0.295 arcsec/px
        scale = OpticalTrainProfile.compute_scale(2.9, 2030.0)
        assert scale == pytest.approx(0.295, abs=0.001)

    def test_c8_reducer_atr585m(self) -> None:
        scale = OpticalTrainProfile.compute_scale(2.9, 1279.0)
        assert scale == pytest.approx(0.468, abs=0.001)

    def test_c8_native_678m(self) -> None:
        scale = OpticalTrainProfile.compute_scale(2.0, 2030.0)
        assert scale == pytest.approx(0.203, abs=0.001)

    def test_c8_reducer_678m(self) -> None:
        scale = OpticalTrainProfile.compute_scale(2.0, 1279.0)
        assert scale == pytest.approx(0.322, abs=0.001)

    def test_c8_barlow_678m(self) -> None:
        scale = OpticalTrainProfile.compute_scale(2.0, 4060.0)
        assert scale == pytest.approx(0.102, abs=0.001)

    def test_guidescope_imx290(self) -> None:
        scale = OpticalTrainProfile.compute_scale(2.9, 180.0)
        assert scale == pytest.approx(3.323, abs=0.01)


# ── OpticalTrainProfile constants ─────────────────────────────────────────────

class TestOpticalTrainProfiles:
    def test_all_trains_has_seven_entries(self) -> None:
        assert len(ALL_TRAINS) == 7

    def test_c8_native_atr585m_camera_model(self) -> None:
        assert C8_NATIVE_ATR585M.camera_model == "ATR585M"

    def test_c8_native_678m_camera_model(self) -> None:
        assert C8_NATIVE_678M.camera_model == "G3M678M"

    def test_guidescope_camera_model(self) -> None:
        assert GUIDESCOPE_IMX290.camera_model == "GPCMOS02000KPA"

    def test_oag_678m_camera_model(self) -> None:
        assert OAG_678M.camera_model == "G3M678M"

    def test_barlow_focal_length(self) -> None:
        assert C8_BARLOW_2X_678M.focal_mm == pytest.approx(4060.0)

    def test_guidescope_focal_length(self) -> None:
        assert GUIDESCOPE_IMX290.focal_mm == pytest.approx(180.0)

    def test_planetary_role(self) -> None:
        assert TrainRole.PLANETARY in C8_BARLOW_2X_678M.roles
        assert TrainRole.PLANETARY in C8_NATIVE_678M.roles

    def test_guiding_role(self) -> None:
        assert TrainRole.GUIDING in GUIDESCOPE_IMX290.roles
        assert TrainRole.GUIDING in OAG_678M.roles

    def test_dso_role(self) -> None:
        assert TrainRole.DSO in C8_REDUCER_063_ATR585M.roles
        assert TrainRole.DSO in C8_REDUCER_063_678M.roles

    def test_pixel_scale_stored_on_profile(self) -> None:
        expected = OpticalTrainProfile.compute_scale(2.9, 2030.0)
        assert C8_NATIVE_ATR585M.pixel_scale_arcsec == pytest.approx(expected)

    def test_get_train_returns_known(self) -> None:
        assert get_train("C8_NATIVE_ATR585M") is C8_NATIVE_ATR585M

    def test_get_train_returns_none_for_unknown(self) -> None:
        assert get_train("nonexistent") is None

    def test_all_trains_indexed_by_profile_id(self) -> None:
        for pid, train in ALL_TRAINS.items():
            assert train.profile_id == pid

    def test_oag_shares_scale_with_native(self) -> None:
        # OAG uses the same C8 optical path as native 678M
        assert OAG_678M.pixel_scale_arcsec == pytest.approx(C8_NATIVE_678M.pixel_scale_arcsec)
