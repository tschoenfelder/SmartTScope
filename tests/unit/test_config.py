"""Unit tests for smart_telescope.config — observer location defaults and overrides."""
import importlib

import pytest


def _reload_config(monkeypatch: pytest.MonkeyPatch, lat: str | None, lon: str | None):
    import smart_telescope.config as cfg_module
    if lat is not None:
        monkeypatch.setenv("OBSERVER_LAT", lat)
    else:
        monkeypatch.delenv("OBSERVER_LAT", raising=False)
    if lon is not None:
        monkeypatch.setenv("OBSERVER_LON", lon)
    else:
        monkeypatch.delenv("OBSERVER_LON", raising=False)
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
