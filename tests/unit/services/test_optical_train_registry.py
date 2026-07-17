"""Tests for OpticalTrainRegistry — R4-001..004."""
from __future__ import annotations

from unittest.mock import patch

import pytest

from smart_telescope.config import CameraSpec, OpticalTrainSpec, TelescopeSpec
from smart_telescope.services.optical_train_registry import OpticalTrain, OpticalTrainRegistry


# ── helpers ───────────────────────────────────────────────────────────────────

_TELESCOPES = {
    "c8": TelescopeSpec(aperture_mm=203.2, focal_mm=2032.0, type="sct", obstruction=0.36),
    "guide": TelescopeSpec(aperture_mm=50.0, focal_mm=180.0, type="refractor", obstruction=0.0),
}

_CAMERAS = {
    "main": 0,
    "guide": 1,
    "oag": 2,
}

_TRAINS_3 = {
    "main":  OpticalTrainSpec(telescope="c8",    camera="main",  reducer_factor=1.0, focuser="onstep"),
    "guide": OpticalTrainSpec(telescope="guide", camera="guide", reducer_factor=1.0, focuser=""),
    "oag":   OpticalTrainSpec(telescope="c8",    camera="oag",   reducer_factor=1.0, focuser="onstep"),
}

_TRAINS_1 = {
    "main": OpticalTrainSpec(telescope="c8", camera="main", reducer_factor=0.63, focuser="onstep"),
}


def _make_registry(trains=None, cameras=None, telescopes=None, camera_specs=None) -> OpticalTrainRegistry:
    import smart_telescope.config as cfg
    t = trains if trains is not None else _TRAINS_3
    c = cameras if cameras is not None else _CAMERAS
    cs = camera_specs if camera_specs is not None else {}
    te = telescopes if telescopes is not None else _TELESCOPES
    with patch.object(cfg, "OPTICAL_TRAINS", t), \
         patch.object(cfg, "CAMERAS", c), \
         patch.object(cfg, "CAMERA_SPECS", cs), \
         patch.object(cfg, "TELESCOPES", te), \
         patch.object(cfg, "PIXEL_SCALE_ARCSEC", 0.38):
        return OpticalTrainRegistry.from_config()


# ── OpticalTrain dataclass ─────────────────────────────────────────────────────

class TestOpticalTrainDataclass:
    def test_fields(self):
        t = OpticalTrain(
            name="main", camera_role="main", camera_index=0,
            telescope_name="c8", focal_mm=2032.0, reducer_factor=1.0,
            pixel_scale_arcsec=0.2, has_focuser=True, focuser="onstep",
        )
        assert t.name == "main"
        assert t.camera_index == 0
        assert t.has_focuser is True

    def test_frozen(self):
        t = OpticalTrain(
            name="x", camera_role="x", camera_index=0,
            telescope_name="c8", focal_mm=100.0, reducer_factor=1.0,
            pixel_scale_arcsec=1.0, has_focuser=False, focuser="",
        )
        with pytest.raises((AttributeError, TypeError)):
            t.name = "y"  # type: ignore[misc]


# ── M10-013: declared optical elements (filter wheel / reducer / barlow) ──────

class TestOpticalElementDeclarations:
    def _registry(self, trains, fw_enabled: bool = False) -> OpticalTrainRegistry:
        import smart_telescope.config as cfg
        from smart_telescope.config import FilterWheelSpec
        with patch.object(cfg, "FILTER_WHEEL", FilterWheelSpec(enabled=fw_enabled)):
            return _make_registry(trains=trains)

    def test_declared_elements_flow_into_train(self):
        trains = {
            "main": OpticalTrainSpec(
                telescope="c8", camera="main", reducer_factor=0.63,
                focuser="onstep", filter_wheel="touptek",
                reducer="celestron_f6.3",
            ),
        }
        reg = self._registry(trains, fw_enabled=True)
        t = reg.main()
        assert t is not None
        assert t.filter_wheel == "touptek"
        assert t.reducer == "celestron_f6.3"
        assert t.barlow == ""

    def test_optical_configuration_payload(self):
        trains = {
            "main": OpticalTrainSpec(
                telescope="c8", camera="main", reducer_factor=2.0,
                focuser="onstep", barlow="2x",
            ),
        }
        cfg_payload = self._registry(trains).main().optical_configuration()
        assert cfg_payload["barlow"] == "2x"
        assert cfg_payload["reducer"] is None
        assert cfg_payload["filter_wheel"] is None
        assert cfg_payload["focuser"] == "onstep"
        assert cfg_payload["focal_mm"] == pytest.approx(4064.0)

    def test_unknown_filter_wheel_value_fails_validation(self):
        trains = {
            "main": OpticalTrainSpec(
                telescope="c8", camera="main", filter_wheel="zwo",
            ),
        }
        with pytest.raises(ValueError, match="filter_wheel 'zwo' unknown"):
            self._registry(trains)

    def test_touptek_reference_requires_enabled_global_section(self):
        trains = {
            "main": OpticalTrainSpec(
                telescope="c8", camera="main", filter_wheel="touptek",
            ),
        }
        with pytest.raises(ValueError, match=r"\[filter_wheel\] section is not enabled"):
            self._registry(trains, fw_enabled=False)

    def test_element_named_but_factor_one_warns_not_crashes(self, caplog):
        trains = {
            "main": OpticalTrainSpec(
                telescope="c8", camera="main", reducer_factor=1.0,
                reducer="celestron_f6.3",
            ),
        }
        with caplog.at_level("WARNING"):
            reg = self._registry(trains)
        assert reg.main() is not None  # loaded despite mismatch
        assert any("reducer_factor is 1.0" in r.message for r in caplog.records)

    def test_factor_without_element_warns_not_crashes(self, caplog):
        trains = {
            "main": OpticalTrainSpec(telescope="c8", camera="main", reducer_factor=0.63),
        }
        with caplog.at_level("WARNING"):
            reg = self._registry(trains)
        assert reg.main() is not None
        assert any("no reducer/barlow declared" in r.message for r in caplog.records)

    def test_legacy_config_without_element_fields_still_loads(self):
        # Backward compatibility: the pre-M10-013 specs in _TRAINS_3 have no
        # element declarations at all.
        reg = self._registry(_TRAINS_3)
        assert len(reg.all()) == 3
        assert reg.main().filter_wheel == ""


# ── M10-015: derived pixel scale (model-based, binning-aware) ─────────────────

class TestDerivedPixelScale:
    _SPECS = {
        "main":  CameraSpec(role="main",  model="ATR585M"),
        "guide": CameraSpec(role="guide", model="GPCMOS02000KPA"),
        "oag":   CameraSpec(role="oag",   model="G3M678M"),
    }
    _TELE = {
        "c8":    TelescopeSpec(aperture_mm=203.2, focal_mm=2032.0, type="sct", obstruction=0.36),
        "guide": TelescopeSpec(aperture_mm=50.0, focal_mm=180.0, type="refractor"),
    }
    _TRAINS = {
        "main":  OpticalTrainSpec(telescope="c8",    camera="main"),
        "guide": OpticalTrainSpec(telescope="guide", camera="guide"),
        "oag":   OpticalTrainSpec(telescope="c8",    camera="oag"),
    }

    def _registry(self, **kw) -> OpticalTrainRegistry:
        return _make_registry(
            trains=kw.get("trains", self._TRAINS),
            telescopes=self._TELE,
            camera_specs=kw.get("camera_specs", self._SPECS),
        )

    def test_scale_derived_from_configured_model_not_role_name(self):
        # M10-015 acceptance: no pixel_scale_arcsec configured anywhere —
        # main/guide/oag report their real scales, not the 0.38 global.
        reg = self._registry()
        assert reg.get("main").pixel_scale_arcsec == pytest.approx(0.2944, abs=1e-4)
        assert reg.get("guide").pixel_scale_arcsec == pytest.approx(3.3232, abs=1e-4)
        assert reg.get("oag").pixel_scale_arcsec == pytest.approx(0.2030, abs=1e-4)

    def test_binning_scales_effective_pixel_scale(self):
        t = self._registry().get("main")
        assert t.effective_pixel_scale(1) == pytest.approx(0.2944, abs=1e-4)
        assert t.effective_pixel_scale(2) == pytest.approx(0.5888, abs=1e-3)

    def test_driver_reported_pixel_size_preferred_over_profile(self):
        t = self._registry().get("main")
        # Driver says 2.0 µm (not the profile's 2.9): scale follows the driver.
        assert t.effective_pixel_scale(1, pixel_size_um=2.0) == pytest.approx(0.2030, abs=1e-4)

    def test_configured_override_beats_driver_and_profile(self):
        trains = {
            "main": OpticalTrainSpec(telescope="c8", camera="main", pixel_scale_arcsec=0.5),
        }
        t = self._registry(trains=trains).get("main")
        assert t.pixel_scale_overridden is True
        assert t.effective_pixel_scale(1, pixel_size_um=2.0) == pytest.approx(0.5)
        assert t.effective_pixel_scale(2) == pytest.approx(1.0)

    def test_legacy_role_named_after_model_still_matches(self):
        # Pre-M10-015 behavior: a role literally named like the model keeps working
        # even without a CameraSpec model entry.
        trains = {"main": OpticalTrainSpec(telescope="c8", camera="G3M678M")}
        cameras = {"G3M678M": 0}
        reg = _make_registry(trains=trains, telescopes=self._TELE, cameras=cameras, camera_specs={})
        assert reg.get("main").pixel_scale_arcsec == pytest.approx(0.2030, abs=1e-4)

    def test_resolve_index_callable_wins_and_failures_are_safe(self):
        import smart_telescope.config as cfg
        calls: list[str] = []

        def resolver(role: str):
            calls.append(role)
            if role == "guide":
                raise RuntimeError("no SDK")
            return {"main": 2, "oag": None}.get(role)

        with patch.object(cfg, "OPTICAL_TRAINS", self._TRAINS), \
             patch.object(cfg, "CAMERAS", _CAMERAS), \
             patch.object(cfg, "CAMERA_SPECS", self._SPECS), \
             patch.object(cfg, "TELESCOPES", self._TELE), \
             patch.object(cfg, "PIXEL_SCALE_ARCSEC", 0.38):
            reg = OpticalTrainRegistry.from_config(resolve_index=resolver)
        assert sorted(calls) == ["guide", "main", "oag"]
        assert reg.get("main").camera_index == 2      # resolver wins
        assert reg.get("guide").camera_index == 0     # exception → fallback
        assert reg.get("oag").camera_index == 0       # None → fallback


# ── from_config — happy paths ─────────────────────────────────────────────────

class TestFromConfig:
    def test_three_train_setup(self):
        reg = _make_registry()
        assert len(reg.all()) == 3

    def test_main_train_fields(self):
        reg = _make_registry()
        main = reg.main()
        assert main is not None
        assert main.camera_index == 0
        assert main.telescope_name == "c8"
        assert main.focal_mm == pytest.approx(2032.0)
        assert main.reducer_factor == pytest.approx(1.0)
        assert main.has_focuser is True
        assert main.focuser == "onstep"

    def test_guide_train_no_focuser(self):
        reg = _make_registry()
        guide = reg.guide()
        assert guide is not None
        assert guide.camera_index == 1
        assert guide.has_focuser is False
        assert guide.focuser == ""

    def test_oag_train(self):
        reg = _make_registry()
        oag = reg.get("oag")
        assert oag is not None
        assert oag.camera_index == 2
        assert oag.has_focuser is True

    def test_reducer_scales_focal_length(self):
        reg = _make_registry(trains=_TRAINS_1, cameras={"main": 0})
        main = reg.main()
        assert main is not None
        assert main.focal_mm == pytest.approx(2032.0 * 0.63, rel=1e-3)

    def test_empty_config_returns_empty_registry(self):
        reg = _make_registry(trains={})
        assert reg.all() == []
        assert reg.main() is None


# ── pixel scale ───────────────────────────────────────────────────────────────

class TestPixelScale:
    def test_explicit_pixel_scale_used_when_set(self):
        trains = {"main": OpticalTrainSpec(
            telescope="c8", camera="main", reducer_factor=1.0,
            focuser="onstep", pixel_scale_arcsec=0.29,
        )}
        reg = _make_registry(trains=trains, cameras={"main": 0})
        assert reg.main().pixel_scale_arcsec == pytest.approx(0.29)

    def test_fallback_to_global_when_no_profile_match(self):
        trains = {"main": OpticalTrainSpec(
            telescope="c8", camera="unknownrole", reducer_factor=1.0,
        )}
        import smart_telescope.config as cfg
        with patch.object(cfg, "OPTICAL_TRAINS", trains), \
             patch.object(cfg, "CAMERAS", {"unknownrole": 0}), \
             patch.object(cfg, "TELESCOPES", _TELESCOPES), \
             patch.object(cfg, "PIXEL_SCALE_ARCSEC", 0.55):
            reg = OpticalTrainRegistry.from_config()
        assert reg.main().pixel_scale_arcsec == pytest.approx(0.55)

    def test_profile_match_computes_scale(self):
        # "atr585m" role → ATR585M profile with pixel_um=2.9
        trains = {"main": OpticalTrainSpec(telescope="c8", camera="atr585m", reducer_factor=1.0)}
        import smart_telescope.config as cfg
        with patch.object(cfg, "OPTICAL_TRAINS", trains), \
             patch.object(cfg, "CAMERAS", {"atr585m": 0}), \
             patch.object(cfg, "TELESCOPES", _TELESCOPES), \
             patch.object(cfg, "PIXEL_SCALE_ARCSEC", 0.38):
            reg = OpticalTrainRegistry.from_config()
        expected = round(2.9 * 206.265 / 2032.0, 4)
        assert reg.main().pixel_scale_arcsec == pytest.approx(expected, rel=1e-3)


# ── CAMERA_SPECS table-format (new [cameras.main] table syntax) ────────────────

class TestCameraSpecsTableFormat:
    """OpticalTrainRegistry must resolve cameras via CAMERA_SPECS when CAMERAS is empty."""

    def test_builds_train_from_camera_specs_with_index(self):
        trains = {"main": OpticalTrainSpec(telescope="c8", camera="main", focuser="onstep")}
        specs = {"main": CameraSpec(role="main", index=2)}
        reg = _make_registry(trains=trains, cameras={}, telescopes=_TELESCOPES, camera_specs=specs)
        t = reg.main()
        assert t is not None
        assert t.camera_index == 2
        assert t.has_focuser is True

    def test_builds_train_from_camera_specs_no_index_defaults_to_zero(self):
        trains = {"main": OpticalTrainSpec(telescope="c8", camera="main")}
        specs = {"main": CameraSpec(role="main", model="G3M678M", index=None)}
        reg = _make_registry(trains=trains, cameras={}, telescopes=_TELESCOPES, camera_specs=specs)
        t = reg.main()
        assert t is not None
        assert t.camera_index == 0

    def test_camera_specs_takes_priority_over_cameras(self):
        trains = {"main": OpticalTrainSpec(telescope="c8", camera="main")}
        specs = {"main": CameraSpec(role="main", index=3)}
        cameras = {"main": 7}  # legacy value — should be ignored when CAMERA_SPECS has the role
        reg = _make_registry(trains=trains, cameras=cameras, telescopes=_TELESCOPES, camera_specs=specs)
        assert reg.main().camera_index == 3

    def test_falls_back_to_cameras_when_not_in_camera_specs(self):
        trains = {"main": OpticalTrainSpec(telescope="c8", camera="main")}
        reg = _make_registry(trains=trains, cameras={"main": 5}, camera_specs={})
        assert reg.main().camera_index == 5

    def test_missing_in_both_raises_value_error(self):
        trains = {"main": OpticalTrainSpec(telescope="c8", camera="main")}
        with pytest.raises(ValueError, match="main"):
            _make_registry(trains=trains, cameras={}, camera_specs={})


# ── validation ────────────────────────────────────────────────────────────────

class TestValidation:
    def test_unknown_telescope_raises(self):
        trains = {"main": OpticalTrainSpec(telescope="nonexistent", camera="main")}
        with pytest.raises(ValueError, match="nonexistent"):
            _make_registry(trains=trains)

    def test_unknown_camera_role_raises(self):
        trains = {"main": OpticalTrainSpec(telescope="c8", camera="phantom")}
        with pytest.raises(ValueError, match="phantom"):
            _make_registry(trains=trains)

    def test_multiple_errors_reported_together(self):
        trains = {
            "main":  OpticalTrainSpec(telescope="bad_tele", camera="main"),
            "guide": OpticalTrainSpec(telescope="guide",    camera="no_cam"),
        }
        with pytest.raises(ValueError) as exc_info:
            _make_registry(trains=trains)
        msg = str(exc_info.value)
        assert "bad_tele" in msg
        assert "no_cam" in msg


# ── queries ───────────────────────────────────────────────────────────────────

class TestQueries:
    def test_get_by_name(self):
        reg = _make_registry()
        assert reg.get("main") is not None
        assert reg.get("missing") is None

    def test_by_camera_index(self):
        reg = _make_registry()
        assert reg.by_camera_index(0).name == "main"
        assert reg.by_camera_index(1).name == "guide"
        assert reg.by_camera_index(99) is None

    def test_by_camera_role(self):
        reg = _make_registry()
        assert reg.by_camera_role("main").name == "main"
        assert reg.by_camera_role("oag").name == "oag"
        assert reg.by_camera_role("unknown") is None

    def test_all_returns_all_trains(self):
        reg = _make_registry()
        names = {t.name for t in reg.all()}
        assert names == {"main", "guide", "oag"}

    def test_two_camera_setup(self):
        trains = {
            "main":  OpticalTrainSpec(telescope="c8",    camera="main",  focuser="onstep"),
            "guide": OpticalTrainSpec(telescope="guide", camera="guide"),
        }
        reg = _make_registry(trains=trains, cameras={"main": 0, "guide": 1})
        assert len(reg.all()) == 2
        assert reg.by_camera_index(0).has_focuser is True
        assert reg.by_camera_index(1).has_focuser is False
