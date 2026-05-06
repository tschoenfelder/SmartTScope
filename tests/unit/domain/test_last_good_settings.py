"""Unit tests for domain/last_good_settings.py (AGT-1-2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from smart_telescope.domain.last_good_settings import (
    LastGoodSettings,
    LastGoodStore,
    make_last_good,
)

MODEL = "ATR585M"
SERIAL = "SN001"
MODE = "DSO_PREVIEW"

_BASE = dict(
    camera_model=MODEL, camera_serial=SERIAL, mode=MODE,
    gain=300, exposure_ms=2000.0, offset=10, conversion_gain="HCG",
)


def _settings(**overrides: object) -> LastGoodSettings:
    kw = dict(_BASE, saved_at="2026-05-06T00:00:00+00:00")
    kw.update(overrides)
    return LastGoodSettings(**kw)


# ── LastGoodSettings ──────────────────────────────────────────────────────────

class TestLastGoodSettings:
    def test_round_trip_dict(self) -> None:
        s = _settings()
        restored = LastGoodSettings.from_dict(s.to_dict())
        assert restored == s

    def test_make_factory_fills_saved_at(self) -> None:
        s = make_last_good(MODEL, SERIAL, MODE, gain=300, exposure_ms=2000.0, offset=10, conversion_gain="HCG")
        assert s.saved_at != ""
        assert "T" in s.saved_at  # ISO-8601


# ── LastGoodStore ─────────────────────────────────────────────────────────────

class TestLastGoodStore:
    def test_load_missing_returns_none(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        assert store.load(MODEL, SERIAL, MODE) is None

    def test_save_and_load(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        s = _settings()
        store.save(s)
        loaded = store.load(MODEL, SERIAL, MODE)
        assert loaded == s

    def test_save_creates_parent_dirs(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path / "state")
        store.save(_settings())
        assert (tmp_path / "state" / "last_good").is_dir()

    def test_overwrite_existing(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        store.save(_settings(gain=200))
        store.save(_settings(gain=400))
        loaded = store.load(MODEL, SERIAL, MODE)
        assert loaded is not None
        assert loaded.gain == 400

    def test_different_modes_are_independent(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        store.save(_settings(mode="DSO_PREVIEW", gain=300))
        store.save(_settings(mode="PLANETARY", gain=100))
        dso = store.load(MODEL, SERIAL, "DSO_PREVIEW")
        planet = store.load(MODEL, SERIAL, "PLANETARY")
        assert dso is not None and dso.gain == 300
        assert planet is not None and planet.gain == 100

    def test_delete_existing(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        store.save(_settings())
        deleted = store.delete(MODEL, SERIAL, MODE)
        assert deleted is True
        assert store.load(MODEL, SERIAL, MODE) is None

    def test_delete_missing_returns_false(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        assert store.delete(MODEL, SERIAL, MODE) is False

    def test_all_modes_empty_when_none_saved(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        assert store.all_modes(MODEL, SERIAL) == []

    def test_all_modes_returns_all_for_camera(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        for mode in ("DSO_PREVIEW", "PLANETARY", "GUIDE"):
            store.save(_settings(mode=mode))
        results = store.all_modes(MODEL, SERIAL)
        assert len(results) == 3
        modes = {s.mode for s in results}
        assert modes == {"DSO_PREVIEW", "PLANETARY", "GUIDE"}

    def test_all_modes_excludes_other_camera(self, tmp_path: Path) -> None:
        store = LastGoodStore(tmp_path)
        store.save(_settings(camera_serial="SN001", mode="DSO_PREVIEW"))
        store.save(_settings(camera_serial="SN002", mode="DSO_PREVIEW"))
        results = store.all_modes(MODEL, "SN001")
        assert len(results) == 1
        assert results[0].camera_serial == "SN001"
