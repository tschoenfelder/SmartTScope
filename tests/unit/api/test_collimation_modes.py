"""Tests for GET /api/collimation/modes (M8-024 / REQ-UI-002..003)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.api import deps


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(deps, "get_device_state", lambda: MagicMock(
        is_started=lambda: False,
        get_mount_state=lambda: None,
        get_time_location_status=lambda: MagicMock(name="UNKNOWN"),
        is_user_time_confirmed=lambda: False,
        get_onstep_comparison_established_at=lambda: None,
        get_user_time_confirmed_at=lambda: None,
    ))
    monkeypatch.setattr(deps, "get_master_source_service", lambda: None)
    monkeypatch.setattr(deps, "get_raspberry_trust_service", lambda: None)
    return TestClient(app, raise_server_exceptions=False)


def test_modes_endpoint_returns_200(client):
    resp = client.get("/api/collimation/modes")
    assert resp.status_code == 200


def test_modes_has_two_modes(client):
    data = client.get("/api/collimation/modes").json()
    assert len(data["modes"]) == 2


def test_modes_names(client):
    data = client.get("/api/collimation/modes").json()
    names = [m["name"] for m in data["modes"]]
    assert "bahtinov_preview" in names
    assert "defocus_donut" in names


def test_modes_labels_correct_spelling(client):
    """Verify 'Bahtinov' (not 'Bathynov') and 'Defocus Donut' spelling."""
    data = client.get("/api/collimation/modes").json()
    labels = {m["name"]: m["label"] for m in data["modes"]}
    assert labels["bahtinov_preview"] == "Bahtinov Preview"
    assert labels["defocus_donut"] == "Defocus Donut"


def test_mode_has_preview_available_field(client):
    data = client.get("/api/collimation/modes").json()
    for mode in data["modes"]:
        assert "preview_available" in mode


def test_mode_has_slew_allowed_field(client):
    data = client.get("/api/collimation/modes").json()
    for mode in data["modes"]:
        assert "slew_allowed" in mode


def test_mode_has_centering_allowed_field(client):
    data = client.get("/api/collimation/modes").json()
    for mode in data["modes"]:
        assert "centering_allowed" in mode


def test_preview_unavailable_when_camera_fails(client, monkeypatch):
    """When camera.get_camera() raises, preview_available=False."""
    monkeypatch.setattr(deps, "get_camera",
                        lambda: (_ for _ in ()).throw(RuntimeError("No camera")))
    data = client.get("/api/collimation/modes").json()
    for mode in data["modes"]:
        assert mode["preview_available"] is False
        assert mode["preview_unavailable_reason"] is not None


def test_slew_blocked_without_time_trust(client):
    """Slew-to-target is blocked when adapter is disconnected."""
    data = client.get("/api/collimation/modes").json()
    # Adapter is CLOSED (device_state.is_started()=False) → slew gated
    for mode in data["modes"]:
        assert mode["slew_allowed"] is False


def test_centering_blocked_without_time_trust(client):
    data = client.get("/api/collimation/modes").json()
    for mode in data["modes"]:
        assert mode["centering_allowed"] is False


def test_slew_unavailable_reason_provided_when_gated(client):
    data = client.get("/api/collimation/modes").json()
    for mode in data["modes"]:
        if not mode["slew_allowed"]:
            assert mode["slew_unavailable_reason"] is not None
