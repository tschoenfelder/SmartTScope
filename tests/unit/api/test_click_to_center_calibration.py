"""Tests for click-to-center calibration API endpoints — M8-027 / REQ-CLICK-003."""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.api import deps
from smart_telescope.domain.ctc_calibration import CTCCalibration
from smart_telescope.services.ctc_calibration_store import CTCCalibrationStore


@pytest.fixture()
def client(tmp_path, monkeypatch):
    store = CTCCalibrationStore(path=tmp_path / "ctc.json")
    monkeypatch.setattr(deps, "get_ctc_calibration_store", lambda: store)
    return TestClient(app, raise_server_exceptions=False)


def _fresh_cal(**kwargs) -> CTCCalibration:
    defaults = dict(
        arcsec_per_px_x=1.2, arcsec_per_px_y=1.2, rotation_deg=0.0,
        optical_train="default", binning=1,
        measured_at=time.time(), max_age_hours=24.0,
    )
    defaults.update(kwargs)
    return CTCCalibration(**defaults)


# ── GET /calibration ─────────────────────────────────────────────────────────

def test_get_calibration_200(client):
    assert client.get("/api/click_to_center/calibration").status_code == 200


def test_get_calibration_not_found(client):
    data = client.get("/api/click_to_center/calibration").json()
    assert data["found"] is False
    assert data["valid"] is False


def test_get_calibration_found_and_valid(client, tmp_path, monkeypatch):
    store = CTCCalibrationStore(path=tmp_path / "ctc2.json")
    store.put(_fresh_cal())
    monkeypatch.setattr(deps, "get_ctc_calibration_store", lambda: store)
    data = client.get("/api/click_to_center/calibration").json()
    assert data["found"] is True
    assert data["is_valid"] is True


def test_get_calibration_expired_shows_reason(tmp_path, monkeypatch):
    store = CTCCalibrationStore(path=tmp_path / "ctc3.json")
    store.put(_fresh_cal(measured_at=time.time() - 25 * 3600, max_age_hours=24.0))
    monkeypatch.setattr(deps, "get_ctc_calibration_store", lambda: store)
    client = TestClient(app, raise_server_exceptions=False)
    data = client.get("/api/click_to_center/calibration").json()
    assert data["is_valid"] is False
    assert data["reason"] is not None
    assert "expir" in data["reason"].lower()


# ── POST /calibration ────────────────────────────────────────────────────────

def test_set_calibration_200(client):
    resp = client.post("/api/click_to_center/calibration", json={
        "optical_train": "default", "binning": 1,
        "arcsec_per_px_x": 1.2, "arcsec_per_px_y": 1.2, "rotation_deg": 0.0,
    })
    assert resp.status_code == 200


def test_set_calibration_returns_ok(client):
    resp = client.post("/api/click_to_center/calibration", json={
        "optical_train": "default", "binning": 1,
        "arcsec_per_px_x": 1.5, "arcsec_per_px_y": 1.5, "rotation_deg": 5.0,
    })
    data = resp.json()
    assert data["ok"] is True
    assert data["key"] == "default:1"


def test_set_calibration_persists(client):
    client.post("/api/click_to_center/calibration", json={
        "optical_train": "default", "binning": 1,
        "arcsec_per_px_x": 1.8, "arcsec_per_px_y": 1.8, "rotation_deg": 0.0,
    })
    data = client.get("/api/click_to_center/calibration").json()
    assert data["found"] is True
    assert abs(data["arcsec_per_px_x"] - 1.8) < 0.01


# ── DELETE /calibration ──────────────────────────────────────────────────────

def test_delete_calibration_200(client):
    assert client.request("DELETE", "/api/click_to_center/calibration").status_code == 200


def test_delete_returns_false_when_missing(client):
    data = client.request("DELETE", "/api/click_to_center/calibration").json()
    assert data["deleted"] is False


def test_delete_removes_calibration(client):
    client.post("/api/click_to_center/calibration", json={
        "optical_train": "default", "binning": 1,
        "arcsec_per_px_x": 1.0, "arcsec_per_px_y": 1.0, "rotation_deg": 0.0,
    })
    client.request("DELETE", "/api/click_to_center/calibration")
    data = client.get("/api/click_to_center/calibration").json()
    assert data["found"] is False


# ── Readiness with calibration ───────────────────────────────────────────────

def _make_full_stage1_device_state():
    """Device state with full Stage 1 verified, mount tracking."""
    tl_mock = MagicMock()
    tl_mock.name = "VERIFIED"
    mount_mock = MagicMock()
    mount_mock.error = False
    mount_state = MagicMock()
    mount_state.name = "TRACKING"
    mount_mock.state = mount_state
    ds = MagicMock()
    ds.is_started = lambda: True
    ds.get_mount_state = lambda: mount_mock
    ds.get_time_location_status = lambda: tl_mock
    ds.is_user_time_confirmed = lambda: True
    ds.get_onstep_comparison_established_at = lambda: 1000.0
    ds.get_user_time_confirmed_at = lambda: 2000.0
    return ds


def test_readiness_blocked_when_no_calibration(monkeypatch, tmp_path):
    store = CTCCalibrationStore(path=tmp_path / "empty_ctc.json")
    monkeypatch.setattr(deps, "get_ctc_calibration_store", lambda: store)
    monkeypatch.setattr(deps, "get_device_state", _make_full_stage1_device_state)
    monkeypatch.setattr(deps, "get_master_source_service", lambda: None)
    monkeypatch.setattr(deps, "get_raspberry_trust_service", lambda: None)
    client = TestClient(app, raise_server_exceptions=False)
    data = client.get("/api/click_to_center/readiness").json()
    assert data["allowed"] is False
    assert data["required_action"] == "run_ctc_calibration"


def test_readiness_blocked_reason_mentions_calibration(monkeypatch, tmp_path):
    store = CTCCalibrationStore(path=tmp_path / "empty_ctc2.json")
    monkeypatch.setattr(deps, "get_ctc_calibration_store", lambda: store)
    monkeypatch.setattr(deps, "get_device_state", _make_full_stage1_device_state)
    monkeypatch.setattr(deps, "get_master_source_service", lambda: None)
    monkeypatch.setattr(deps, "get_raspberry_trust_service", lambda: None)
    client = TestClient(app, raise_server_exceptions=False)
    data = client.get("/api/click_to_center/readiness").json()
    assert "calibration" in data["reason"].lower()
