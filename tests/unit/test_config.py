"""Unit tests for smart_telescope.config — observer location defaults and overrides."""
import importlib

import pytest


def _reload_config(
    monkeypatch: pytest.MonkeyPatch,
    lat: str | None,
    lon: str | None,
    height: str | None = None,
):
    import smart_telescope.config as cfg_module
    if lat is not None:
        monkeypatch.setenv("OBSERVER_LAT", lat)
    else:
        monkeypatch.delenv("OBSERVER_LAT", raising=False)
    if lon is not None:
        monkeypatch.setenv("OBSERVER_LON", lon)
    else:
        monkeypatch.delenv("OBSERVER_LON", raising=False)
    if height is not None:
        monkeypatch.setenv("OBSERVER_HEIGHT_M", height)
    else:
        monkeypatch.delenv("OBSERVER_HEIGHT_M", raising=False)
    importlib.reload(cfg_module)
    return cfg_module


class TestObserverDefaults:
    def test_default_lat_is_usingen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, None)
        assert cfg.OBSERVER_LAT == pytest.approx(50.336)

    def test_default_lon_is_usingen(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, None)
        assert cfg.OBSERVER_LON == pytest.approx(8.533)

    def test_lat_overridden_by_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, "48.137", None)
        assert cfg.OBSERVER_LAT == pytest.approx(48.137)

    def test_lon_overridden_by_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, "11.576")
        assert cfg.OBSERVER_LON == pytest.approx(11.576)

    def test_lat_is_float(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, None)
        assert isinstance(cfg.OBSERVER_LAT, float)

    def test_lon_is_float(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, None)
        assert isinstance(cfg.OBSERVER_LON, float)


class TestObserverHeight:
    def test_default_height_is_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, None)
        assert cfg.OBSERVER_HEIGHT_M == pytest.approx(0.0)

    def test_height_overridden_by_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, None, "410.5")
        assert cfg.OBSERVER_HEIGHT_M == pytest.approx(410.5)

    def test_height_is_float(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, None)
        assert isinstance(cfg.OBSERVER_HEIGHT_M, float)


class TestObserverHomeAndActiveGlobals:
    def test_home_matches_observer_on_load(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, "48.0", "11.0", "300.0")
        assert cfg.OBSERVER_HOME_LAT == pytest.approx(cfg.OBSERVER_LAT)
        assert cfg.OBSERVER_HOME_LON == pytest.approx(cfg.OBSERVER_LON)
        assert cfg.OBSERVER_HOME_HEIGHT_M == pytest.approx(cfg.OBSERVER_HEIGHT_M)

    def test_active_location_defaults_to_config_file_home(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        cfg = _reload_config(monkeypatch, None, None)
        assert cfg.OBSERVER_LOCATION_SOURCE == "CONFIG_FILE"
        assert cfg.OBSERVER_LOCATION_NAME == "Home"

    def test_locations_library_defaults_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        cfg = _reload_config(monkeypatch, None, None)
        assert cfg.LOCATIONS == {}
