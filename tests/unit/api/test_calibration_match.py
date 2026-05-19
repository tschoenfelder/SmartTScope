"""Unit tests for GET /api/calibration/match (AGT-3-4)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.adapters.mock.camera import MockCamera
from smart_telescope.api import calibration as cal_mod
from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.calibration_store import CalibrationIndex, make_entry

client = TestClient(app)

_MODEL = "MockCamera"
_SERIAL = ""

# Existing API: gain is required, always returns bias+dark+flat.
# conversion_gain defaults to "LCG", bit_depth defaults to 16.
_BASE = "gain=100&offset=0&conversion_gain=LCG&bit_depth=16"


def _write_index(tmp_path: Path, entries: list) -> None:
    idx = CalibrationIndex(tmp_path)
    for e in entries:
        idx.add(e)
    idx.save()


def _bias_entry(tmp_path: Path, **overrides):
    kw = dict(gain=100, offset=0, conversion_gain="LCG", bit_depth=16, frame_count=20)
    kw.update(overrides)
    return make_entry(tmp_path, "bias", _MODEL, _SERIAL, **kw)


def _dark_entry(tmp_path: Path, **overrides):
    kw = dict(gain=100, offset=0, conversion_gain="LCG", bit_depth=16,
              frame_count=20, exposure_ms=30_000.0)
    kw.update(overrides)
    return make_entry(tmp_path, "dark", _MODEL, _SERIAL, **kw)


def _flat_entry(tmp_path: Path, **overrides):
    kw = dict(gain=100, offset=0, conversion_gain="LCG", bit_depth=16,
              frame_count=15, optical_train="c8_native", filter_id="none")
    kw.update(overrides)
    return make_entry(tmp_path, "flat", _MODEL, _SERIAL, **kw)


def _get(url: str, tmp_path: Path) -> dict:
    """Execute a GET /api/calibration/match request with patched deps."""
    with patch.object(deps, "get_preview_camera", return_value=MockCamera()), \
         patch.object(cal_mod, "config") as cfg:
        cfg.IMAGE_ROOT = str(tmp_path)
        return client.get(url)


# ── bias matching ──────────────────────────────────────────────────────────────


class TestMatchBias:
    def test_exact_bias_match(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_bias_entry(tmp_path)])
        resp = _get(f"/api/calibration/match?{_BASE}", tmp_path)
        assert resp.status_code == 200
        assert resp.json()["bias"]["status"] == "MATCHED"

    def test_bias_not_found_returns_not_found(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [])
        resp = _get(f"/api/calibration/match?{_BASE}", tmp_path)
        assert resp.status_code == 200
        assert resp.json()["bias"]["status"] == "NOT_FOUND"

    def test_bias_gain_mismatch_returns_partial(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_bias_entry(tmp_path, gain=200)])
        resp = _get(f"/api/calibration/match?{_BASE}", tmp_path)
        assert resp.status_code == 200
        data = resp.json()
        assert data["bias"]["status"] == "PARTIAL"
        assert any(m["field"] == "gain" for m in data["bias"]["mismatches"])

    def test_bias_entry_returned_on_match(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_bias_entry(tmp_path)])
        resp = _get(f"/api/calibration/match?{_BASE}", tmp_path)
        entry = resp.json()["bias"]["entry"]
        assert entry is not None
        assert entry["cal_type"] == "bias"

    def test_no_image_root_returns_503(self, tmp_path: Path) -> None:
        with patch.object(deps, "get_preview_camera", return_value=MockCamera()), \
             patch.object(cal_mod, "config") as cfg:
            cfg.IMAGE_ROOT = ""
            resp = client.get(f"/api/calibration/match?{_BASE}")
        assert resp.status_code == 503

    def test_missing_required_gain_returns_422(self) -> None:
        resp = client.get("/api/calibration/match?offset=0")
        assert resp.status_code == 422


# ── dark matching ──────────────────────────────────────────────────────────────


class TestMatchDark:
    def test_dark_exact_match(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_dark_entry(tmp_path)])
        resp = _get(f"/api/calibration/match?{_BASE}&exposure_ms=30000", tmp_path)
        assert resp.status_code == 200
        assert resp.json()["dark"]["status"] == "MATCHED"

    def test_dark_not_found(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_bias_entry(tmp_path)])
        resp = _get(f"/api/calibration/match?{_BASE}&exposure_ms=30000", tmp_path)
        assert resp.json()["dark"]["status"] == "NOT_FOUND"

    def test_dark_exposure_mismatch(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_dark_entry(tmp_path, exposure_ms=10_000.0)])
        resp = _get(f"/api/calibration/match?{_BASE}&exposure_ms=30000", tmp_path)
        data = resp.json()
        assert data["dark"]["status"] == "PARTIAL"
        assert any(m["field"] == "exposure_ms" for m in data["dark"]["mismatches"])

    def test_dark_temperature_passed_via_query(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_dark_entry(tmp_path, temperature_c=-9.0)])
        # temperature within ±5 °C → no mismatch
        resp = _get(f"/api/calibration/match?{_BASE}&exposure_ms=30000&temperature_c=-10", tmp_path)
        assert resp.json()["dark"]["status"] == "MATCHED"


# ── flat matching ──────────────────────────────────────────────────────────────


class TestMatchFlat:
    def test_flat_exact_match(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_flat_entry(tmp_path)])
        resp = _get(
            f"/api/calibration/match?{_BASE}&optical_train=c8_native&filter_id=none",
            tmp_path,
        )
        assert resp.status_code == 200
        assert resp.json()["flat"]["status"] == "MATCHED"

    def test_flat_not_found(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [])
        resp = _get(f"/api/calibration/match?{_BASE}&optical_train=c8_native", tmp_path)
        assert resp.json()["flat"]["status"] == "NOT_FOUND"

    def test_flat_optical_train_mismatch(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_flat_entry(tmp_path, optical_train="c8_reducer")])
        resp = _get(f"/api/calibration/match?{_BASE}&optical_train=c8_native", tmp_path)
        data = resp.json()
        assert data["flat"]["status"] == "PARTIAL"
        assert any(m["field"] == "optical_train" for m in data["flat"]["mismatches"])

    def test_flat_filter_mismatch(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_flat_entry(tmp_path, filter_id="ha")])
        resp = _get(
            f"/api/calibration/match?{_BASE}&optical_train=c8_native&filter_id=none",
            tmp_path,
        )
        data = resp.json()
        assert data["flat"]["status"] == "PARTIAL"
        assert any(m["field"] == "filter_id" for m in data["flat"]["mismatches"])


# ── combined request ───────────────────────────────────────────────────────────


class TestMatchCombined:
    def test_all_matched(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [
            _bias_entry(tmp_path),
            _dark_entry(tmp_path),
            _flat_entry(tmp_path),
        ])
        resp = _get(
            f"/api/calibration/match?{_BASE}"
            "&exposure_ms=30000&optical_train=c8_native&filter_id=none",
            tmp_path,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["bias"]["status"] == "MATCHED"
        assert data["dark"]["status"] == "MATCHED"
        assert data["flat"]["status"] == "MATCHED"

    def test_message_populated_on_partial(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [_bias_entry(tmp_path, gain=200)])
        resp = _get(f"/api/calibration/match?{_BASE}", tmp_path)
        assert resp.json()["bias"]["message"] != ""

    def test_all_three_keys_always_present(self, tmp_path: Path) -> None:
        _write_index(tmp_path, [])
        resp = _get(f"/api/calibration/match?{_BASE}", tmp_path)
        data = resp.json()
        assert "bias" in data and "dark" in data and "flat" in data
