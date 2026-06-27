"""Tests for CTCCalibrationStore — M8-027 / REQ-CLICK-003."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from smart_telescope.domain.ctc_calibration import CTCCalibration
from smart_telescope.services.ctc_calibration_store import CTCCalibrationStore


@pytest.fixture()
def store(tmp_path):
    return CTCCalibrationStore(path=tmp_path / "ctc_calibration.json")


def _cal(optical_train="main", binning=1, **kwargs) -> CTCCalibration:
    defaults = dict(
        arcsec_per_px_x=1.2, arcsec_per_px_y=1.2, rotation_deg=0.0,
        optical_train=optical_train, binning=binning,
        measured_at=time.time(), max_age_hours=24.0,
    )
    defaults.update(kwargs)
    return CTCCalibration(**defaults)


def test_get_returns_none_when_empty(store):
    assert store.get("main", 1) is None


def test_put_and_get(store):
    cal = _cal()
    store.put(cal)
    retrieved = store.get("main", 1)
    assert retrieved is not None
    assert retrieved.arcsec_per_px_x == 1.2


def test_put_overwrites_existing(store):
    store.put(_cal(arcsec_per_px_x=1.0))
    store.put(_cal(arcsec_per_px_x=2.0))
    assert store.get("main", 1).arcsec_per_px_x == 2.0


def test_different_keys_independent(store):
    store.put(_cal(optical_train="main", binning=1, arcsec_per_px_x=1.0))
    store.put(_cal(optical_train="guide", binning=2, arcsec_per_px_x=3.0))
    assert store.get("main", 1).arcsec_per_px_x == 1.0
    assert store.get("guide", 2).arcsec_per_px_x == 3.0


def test_delete_removes_key(store):
    store.put(_cal())
    result = store.delete("main", 1)
    assert result is True
    assert store.get("main", 1) is None


def test_delete_returns_false_when_missing(store):
    assert store.delete("nonexistent", 1) is False


def test_all_returns_all_calibrations(store):
    store.put(_cal(optical_train="main", binning=1))
    store.put(_cal(optical_train="guide", binning=2))
    all_cals = store.all()
    assert len(all_cals) == 2


def test_persists_to_disk(tmp_path):
    path = tmp_path / "ctc.json"
    store1 = CTCCalibrationStore(path=path)
    store1.put(_cal(arcsec_per_px_x=1.7))
    store2 = CTCCalibrationStore(path=path)
    assert store2.get("main", 1).arcsec_per_px_x == 1.7


def test_empty_json_file_handled_gracefully(store, tmp_path):
    path = tmp_path / "empty.json"
    path.write_text("{}", encoding="utf-8")
    s = CTCCalibrationStore(path=path)
    assert s.get("main", 1) is None
