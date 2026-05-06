"""Unit tests for domain/calibration_store.py (AGT-1-2)."""
from __future__ import annotations

from pathlib import Path

import pytest

from smart_telescope.domain.calibration_store import (
    CalibrationEntry,
    CalibrationIndex,
    MismatchDetail,
    find_best_match,
    make_entry,
    master_dir,
    master_path,
)

MODEL = "ATR585M"
SERIAL = "SN001"
BASE_KWARGS = dict(gain=300, offset=10, conversion_gain="HCG", bit_depth=12, frame_count=20)


# ── master_dir ────────────────────────────────────────────────────────────────

class TestMasterDir:
    def test_bias_subdir(self, tmp_path: Path) -> None:
        p = master_dir(tmp_path, MODEL, SERIAL, "bias")
        assert p.name == "biases"
        assert "ATR585M_SN001" in str(p)

    def test_dark_subdir(self, tmp_path: Path) -> None:
        p = master_dir(tmp_path, MODEL, SERIAL, "dark")
        assert p.name == "darks"

    def test_flat_subdir(self, tmp_path: Path) -> None:
        p = master_dir(tmp_path, MODEL, SERIAL, "flat")
        assert p.name == "flats"

    def test_invalid_type_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="cal_type"):
            master_dir(tmp_path, MODEL, SERIAL, "junk")


# ── master_path ───────────────────────────────────────────────────────────────

class TestMasterPath:
    def test_bias_path_contains_metadata(self, tmp_path: Path) -> None:
        p = master_path(tmp_path, MODEL, SERIAL, "bias", **BASE_KWARGS)
        name = p.name
        assert name.startswith("master_bias_")
        assert "g300" in name
        assert "o10" in name
        assert "hcg" in name
        assert "b12" in name
        assert "n20" in name
        assert name.endswith(".fits")

    def test_dark_path_includes_exposure(self, tmp_path: Path) -> None:
        p = master_path(tmp_path, MODEL, SERIAL, "dark", exposure_ms=300000.0, **BASE_KWARGS)
        assert "e300000ms" in p.name

    def test_dark_without_exposure_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="exposure_ms"):
            master_path(tmp_path, MODEL, SERIAL, "dark", **BASE_KWARGS)

    def test_dark_positive_temperature(self, tmp_path: Path) -> None:
        p = master_path(tmp_path, MODEL, SERIAL, "dark", exposure_ms=1000.0, temperature_c=5.0, **BASE_KWARGS)
        assert "tp5c" in p.name

    def test_dark_negative_temperature(self, tmp_path: Path) -> None:
        p = master_path(tmp_path, MODEL, SERIAL, "dark", exposure_ms=1000.0, temperature_c=-10.0, **BASE_KWARGS)
        assert "tm10c" in p.name

    def test_flat_path_includes_optical_train(self, tmp_path: Path) -> None:
        p = master_path(tmp_path, MODEL, SERIAL, "flat", optical_train="C8_NATIVE_ATR585M", **BASE_KWARGS)
        assert "c8_native_atr585m" in p.name

    def test_flat_path_includes_filter(self, tmp_path: Path) -> None:
        p = master_path(tmp_path, MODEL, SERIAL, "flat", filter_id="Ha", **BASE_KWARGS)
        assert "ha" in p.name

    def test_path_not_created(self, tmp_path: Path) -> None:
        p = master_path(tmp_path, MODEL, SERIAL, "bias", **BASE_KWARGS)
        assert not p.exists()


# ── CalibrationEntry ──────────────────────────────────────────────────────────

class TestCalibrationEntry:
    def _entry(self, **overrides: object) -> CalibrationEntry:
        kwargs: dict = dict(
            cal_type="bias", camera_model=MODEL, camera_serial=SERIAL,
            gain=300, offset=10, conversion_gain="HCG", bit_depth=12,
            frame_count=20, relative_path="masters/ATR585M_SN001/biases/x.fits",
            created_at="2026-05-06T00:00:00+00:00",
        )
        kwargs.update(overrides)
        return CalibrationEntry(**kwargs)

    def test_round_trip_dict(self) -> None:
        e = self._entry()
        restored = CalibrationEntry.from_dict(e.to_dict())
        assert restored == e

    def test_optional_fields_none_by_default(self) -> None:
        e = self._entry()
        assert e.exposure_ms is None
        assert e.temperature_c is None
        assert e.optical_train is None
        assert e.filter_id is None


# ── CalibrationIndex ──────────────────────────────────────────────────────────

class TestCalibrationIndex:
    def _bias_entry(self, tmp_path: Path, gain: int = 300) -> CalibrationEntry:
        return make_entry(
            tmp_path, "bias", MODEL, SERIAL,
            gain=gain, offset=10, conversion_gain="HCG",
            bit_depth=12, frame_count=20,
        )

    def test_empty_index(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        assert len(idx) == 0
        assert idx.entries() == []

    def test_add_entry(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        e = self._bias_entry(tmp_path)
        idx.add(e)
        assert len(idx) == 1

    def test_add_replaces_same_path(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        e = self._bias_entry(tmp_path)
        idx.add(e)
        idx.add(e)  # second add with same relative_path
        assert len(idx) == 1

    def test_remove_existing(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        e = self._bias_entry(tmp_path)
        idx.add(e)
        removed = idx.remove(e.relative_path)
        assert removed is True
        assert len(idx) == 0

    def test_remove_missing(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        assert idx.remove("non/existent.fits") is False

    def test_entries_filter_by_type(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        bias = self._bias_entry(tmp_path)
        dark = make_entry(tmp_path, "dark", MODEL, SERIAL, exposure_ms=300000.0,
                          gain=300, offset=10, conversion_gain="HCG", bit_depth=12, frame_count=20)
        idx.add(bias)
        idx.add(dark)
        assert len(idx.entries("bias")) == 1
        assert len(idx.entries("dark")) == 1
        assert len(idx.entries()) == 2

    def test_save_creates_json(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        idx.add(self._bias_entry(tmp_path))
        idx.save()
        assert (tmp_path / "calibration_index.json").exists()

    def test_round_trip_load(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        e = self._bias_entry(tmp_path)
        idx.add(e)
        idx.save()

        loaded = CalibrationIndex.load(tmp_path)
        assert len(loaded) == 1
        assert loaded.entries()[0] == e

    def test_load_missing_file_returns_empty(self, tmp_path: Path) -> None:
        idx = CalibrationIndex.load(tmp_path / "nonexistent")
        assert len(idx) == 0

    def test_multiple_entries_round_trip(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        for g in (200, 300, 400):
            idx.add(self._bias_entry(tmp_path, gain=g))
        idx.save()
        loaded = CalibrationIndex.load(tmp_path)
        assert len(loaded) == 3


# ── find_best_match ───────────────────────────────────────────────────────────

class TestFindBestMatch:
    _criteria = dict(
        camera_model=MODEL, camera_serial=SERIAL,
        gain=300, offset=10, conversion_gain="HCG", bit_depth=12,
    )

    def _index_with_bias(self, tmp_path: Path, **overrides: object) -> CalibrationIndex:
        kwargs = dict(gain=300, offset=10, conversion_gain="HCG", bit_depth=12, frame_count=20)
        kwargs.update(overrides)
        idx = CalibrationIndex(tmp_path)
        idx.add(make_entry(tmp_path, "bias", MODEL, SERIAL, **kwargs))
        return idx

    def test_exact_match_no_mismatches(self, tmp_path: Path) -> None:
        idx = self._index_with_bias(tmp_path)
        entry, mismatches = find_best_match(idx, "bias", self._criteria)
        assert entry is not None
        assert mismatches == []

    def test_no_candidates_returns_none(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        entry, mismatches = find_best_match(idx, "bias", self._criteria)
        assert entry is None
        assert mismatches == []

    def test_wrong_camera_excluded(self, tmp_path: Path) -> None:
        idx = self._index_with_bias(tmp_path)
        criteria = dict(self._criteria, camera_model="G3M678M")
        entry, _ = find_best_match(idx, "bias", criteria)
        assert entry is None

    def test_gain_mismatch_reported(self, tmp_path: Path) -> None:
        idx = self._index_with_bias(tmp_path, gain=200)
        entry, mismatches = find_best_match(idx, "bias", self._criteria)
        assert entry is not None
        fields = [m.field for m in mismatches]
        assert "gain" in fields

    def test_dark_exact_match(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        idx.add(make_entry(tmp_path, "dark", MODEL, SERIAL, exposure_ms=300000.0,
                           gain=300, offset=10, conversion_gain="HCG", bit_depth=12, frame_count=20))
        criteria = dict(self._criteria, exposure_ms=300000.0)
        entry, mismatches = find_best_match(idx, "dark", criteria)
        assert entry is not None
        assert mismatches == []

    def test_dark_exposure_mismatch_reported(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        idx.add(make_entry(tmp_path, "dark", MODEL, SERIAL, exposure_ms=10000.0,
                           gain=300, offset=10, conversion_gain="HCG", bit_depth=12, frame_count=20))
        criteria = dict(self._criteria, exposure_ms=300000.0)
        entry, mismatches = find_best_match(idx, "dark", criteria)
        assert entry is not None
        assert any(m.field == "exposure_ms" for m in mismatches)

    def test_dark_temperature_within_tolerance_no_mismatch(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        idx.add(make_entry(tmp_path, "dark", MODEL, SERIAL, exposure_ms=300000.0,
                           temperature_c=-8.0, gain=300, offset=10,
                           conversion_gain="HCG", bit_depth=12, frame_count=20))
        criteria = dict(self._criteria, exposure_ms=300000.0, temperature_c=-10.0)
        entry, mismatches = find_best_match(idx, "dark", criteria)
        assert entry is not None
        assert not any(m.field == "temperature_c" for m in mismatches)

    def test_dark_temperature_outside_tolerance_mismatch(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        idx.add(make_entry(tmp_path, "dark", MODEL, SERIAL, exposure_ms=300000.0,
                           temperature_c=0.0, gain=300, offset=10,
                           conversion_gain="HCG", bit_depth=12, frame_count=20))
        criteria = dict(self._criteria, exposure_ms=300000.0, temperature_c=-10.0)
        entry, mismatches = find_best_match(idx, "dark", criteria)
        assert any(m.field == "temperature_c" for m in mismatches)

    def test_best_match_chosen_by_score(self, tmp_path: Path) -> None:
        idx = CalibrationIndex(tmp_path)
        # One with wrong gain AND wrong offset, one with only wrong offset
        idx.add(make_entry(tmp_path, "bias", MODEL, SERIAL, gain=100, offset=99,
                           conversion_gain="HCG", bit_depth=12, frame_count=20))
        idx.add(make_entry(tmp_path, "bias", MODEL, SERIAL, gain=300, offset=99,
                           conversion_gain="HCG", bit_depth=12, frame_count=20))
        entry, mismatches = find_best_match(idx, "bias", self._criteria)
        assert entry is not None
        assert entry.gain == 300   # fewer mismatches
        assert len(mismatches) == 1
