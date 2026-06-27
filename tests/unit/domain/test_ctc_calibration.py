"""Tests for CTCCalibration domain — M8-027 / REQ-CLICK-003."""
from __future__ import annotations

import json
import time

import pytest

from smart_telescope.domain.ctc_calibration import CTCCalibration


def _make_cal(**overrides) -> CTCCalibration:
    defaults = dict(
        arcsec_per_px_x=1.2,
        arcsec_per_px_y=1.2,
        rotation_deg=0.0,
        optical_train="main",
        binning=1,
        measured_at=time.time(),
        max_age_hours=24.0,
    )
    defaults.update(overrides)
    return CTCCalibration(**defaults)


# ── key ──────────────────────────────────────────────────────────────────────

def test_key_format():
    cal = _make_cal(optical_train="main", binning=2)
    assert cal.key == "main:2"


# ── validity ─────────────────────────────────────────────────────────────────

def test_fresh_calibration_is_valid():
    cal = _make_cal(measured_at=time.time())
    assert cal.is_valid()


def test_expired_calibration_is_invalid():
    old = time.time() - 25 * 3600  # 25 hours ago
    cal = _make_cal(measured_at=old, max_age_hours=24.0)
    assert not cal.is_valid()


def test_just_expired_calibration_is_invalid():
    # Exactly at max_age boundary
    t = time.time()
    measured = t - 24 * 3600 - 1  # 1 second past expiry
    cal = _make_cal(measured_at=measured, max_age_hours=24.0)
    assert not cal.is_valid(now=t)


def test_age_hours_computed_correctly():
    t = time.time()
    measured = t - 3 * 3600  # 3 hours ago
    cal = _make_cal(measured_at=measured)
    assert abs(cal.age_hours(now=t) - 3.0) < 0.01


# ── serialisation ────────────────────────────────────────────────────────────

def test_to_dict_includes_is_valid():
    cal = _make_cal()
    d = cal.to_dict()
    assert "is_valid" in d
    assert d["is_valid"] is True


def test_to_dict_includes_age_hours():
    cal = _make_cal(measured_at=time.time() - 3600)
    d = cal.to_dict()
    assert "age_hours" in d
    assert d["age_hours"] > 0


def test_to_dict_excludes_extra_keys():
    cal = _make_cal()
    d = cal.to_dict()
    assert "arcsec_per_px_x" in d
    assert "optical_train" in d
    assert "binning" in d


def test_from_dict_roundtrip():
    cal = _make_cal(arcsec_per_px_x=1.5, rotation_deg=45.0)
    raw = cal.to_dict()
    restored = CTCCalibration.from_dict(raw)
    assert restored.arcsec_per_px_x == 1.5
    assert restored.rotation_deg == 45.0
    assert restored.optical_train == cal.optical_train
