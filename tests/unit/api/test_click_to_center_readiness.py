"""Tests for GET /api/click_to_center/readiness (M8-025 / REQ-CLICK-001)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.api import deps


def _make_device_state(
    *,
    is_started: bool = False,
    mount_state=None,
    tl_status_name: str = "UNKNOWN",
    user_time_confirmed: bool = False,
    oc_at=None,
    uc_at=None,
) -> MagicMock:
    tl_mock = MagicMock()
    tl_mock.name = tl_status_name
    ds = MagicMock()
    ds.is_started = lambda: is_started
    ds.get_mount_state = lambda: mount_state
    ds.get_time_location_status = lambda: tl_mock
    ds.is_user_time_confirmed = lambda: user_time_confirmed
    ds.get_onstep_comparison_established_at = lambda: oc_at
    ds.get_user_time_confirmed_at = lambda: uc_at
    return ds


@pytest.fixture()
def client_disconnected(monkeypatch):
    """Adapter disconnected — click_to_center must be blocked."""
    monkeypatch.setattr(deps, "get_device_state", lambda: _make_device_state(is_started=False))
    monkeypatch.setattr(deps, "get_master_source_service", lambda: None)
    monkeypatch.setattr(deps, "get_raspberry_trust_service", lambda: None)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def client_full_stage1(monkeypatch):
    """Full Stage 1 available, mount not parked — click_to_center must be allowed."""
    mount_state = MagicMock()
    mount_state.error = False
    mount_state.state = MagicMock()
    mount_state.state.name = "TRACKING"

    monkeypatch.setattr(deps, "get_device_state", lambda: _make_device_state(
        is_started=True,
        mount_state=mount_state,
        tl_status_name="VERIFIED",
        user_time_confirmed=True,
        oc_at=1000.0,
        uc_at=2000.0,
    ))
    monkeypatch.setattr(deps, "get_master_source_service", lambda: None)
    monkeypatch.setattr(deps, "get_raspberry_trust_service", lambda: None)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def client_parked(monkeypatch):
    """Full Stage 1 but mount PARKED — click_to_center must be blocked."""
    mount_state = MagicMock()
    mount_state.error = False
    mount_state.state = MagicMock()
    mount_state.state.name = "PARKED"

    monkeypatch.setattr(deps, "get_device_state", lambda: _make_device_state(
        is_started=True,
        mount_state=mount_state,
        tl_status_name="VERIFIED",
        user_time_confirmed=True,
        oc_at=1000.0,
        uc_at=2000.0,
    ))
    monkeypatch.setattr(deps, "get_master_source_service", lambda: None)
    monkeypatch.setattr(deps, "get_raspberry_trust_service", lambda: None)
    return TestClient(app, raise_server_exceptions=False)


# ── Basic structure ──────────────────────────────────────────────────────────

def test_endpoint_returns_200(client_disconnected):
    resp = client_disconnected.get("/api/click_to_center/readiness")
    assert resp.status_code == 200


def test_response_has_allowed_field(client_disconnected):
    data = client_disconnected.get("/api/click_to_center/readiness").json()
    assert "allowed" in data


def test_response_has_reason_field(client_disconnected):
    data = client_disconnected.get("/api/click_to_center/readiness").json()
    assert "reason" in data


def test_response_has_required_action_field(client_disconnected):
    data = client_disconnected.get("/api/click_to_center/readiness").json()
    assert "required_action" in data


# ── Blocked states ───────────────────────────────────────────────────────────

def test_blocked_when_adapter_disconnected(client_disconnected):
    data = client_disconnected.get("/api/click_to_center/readiness").json()
    assert data["allowed"] is False


def test_reason_provided_when_blocked(client_disconnected):
    data = client_disconnected.get("/api/click_to_center/readiness").json()
    assert data["reason"] is not None
    assert len(data["reason"]) > 0


def test_required_action_provided_when_blocked(client_disconnected):
    data = client_disconnected.get("/api/click_to_center/readiness").json()
    assert data["required_action"] is not None


def test_blocked_when_parked(client_parked):
    data = client_parked.get("/api/click_to_center/readiness").json()
    assert data["allowed"] is False


def test_parked_reason_mentions_unpark(client_parked):
    data = client_parked.get("/api/click_to_center/readiness").json()
    assert data["reason"] is not None
    reason_lower = data["reason"].lower()
    assert "park" in reason_lower


# ── Allowed state ────────────────────────────────────────────────────────────

def test_allowed_when_full_stage1_and_tracking(client_full_stage1):
    data = client_full_stage1.get("/api/click_to_center/readiness").json()
    assert data["allowed"] is True


def test_reason_none_when_allowed(client_full_stage1):
    data = client_full_stage1.get("/api/click_to_center/readiness").json()
    assert data["reason"] is None


def test_required_action_none_when_allowed(client_full_stage1):
    data = client_full_stage1.get("/api/click_to_center/readiness").json()
    assert data["required_action"] is None
