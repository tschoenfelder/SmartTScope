"""Unit tests for /api/cooling endpoints (AGT-4-2)."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import cooling as cooling_mod
from smart_telescope.api import deps
from smart_telescope.app import app

client = TestClient(app)


# ── TEC-capable camera stub ───────────────────────────────────────────────────

class _TecCamera:
    """Minimal stand-in with TEC methods for cooling tests."""

    def __init__(self, temp_c: float = 20.0) -> None:
        self.temp_c = temp_c
        self.tec_enabled = False
        self.tec_target_c: float | None = None
        self.power_pct: float = 60.0

    def get_temperature(self) -> float:
        return self.temp_c

    def get_tec_power_pct(self) -> float:
        return self.power_pct

    def set_tec_enabled(self, on: bool) -> None:
        self.tec_enabled = on

    def set_tec_target_c(self, target_c: float) -> None:
        self.tec_target_c = target_c


@pytest.fixture(autouse=True)
def reset_state():
    """Ensure cooling state is clean before/after each test."""
    cooling_mod._reset()
    yield
    cooling_mod._reset()


# ── GET /api/cooling/status — idle ────────────────────────────────────────────

class TestStatusWhenIdle:
    def test_returns_200(self) -> None:
        r = client.get("/api/cooling/status")
        assert r.status_code == 200

    def test_enabled_is_false(self) -> None:
        r = client.get("/api/cooling/status")
        assert r.json()["enabled"] is False

    def test_all_fields_are_none_or_false(self) -> None:
        d = client.get("/api/cooling/status").json()
        assert d["current_temp_c"] is None
        assert d["target_c"] is None
        assert d["power_pct"] is None
        assert d["stable"] is False
        assert d["action"] is None


# ── GET /api/cooling/status — config-driven default target (M10-029) ─────────

class TestDefaultTarget:
    def test_status_includes_config_default_target(self) -> None:
        from types import SimpleNamespace

        from smart_telescope import config
        with patch.object(config, "COOLING", SimpleNamespace(default_target_c=-7.5)):
            d = client.get("/api/cooling/status").json()
        assert d["default_target_c"] == pytest.approx(-7.5)

    def test_default_target_present_when_idle(self) -> None:
        d = client.get("/api/cooling/status").json()
        assert isinstance(d["default_target_c"], float)


# ── POST /api/cooling/set_target — no TEC camera ─────────────────────────────

class TestSetTargetNoTec:
    def test_returns_409_when_camera_has_no_tec(self) -> None:
        from smart_telescope.adapters.mock.camera import MockCamera
        with patch.object(deps, "get_preview_camera", return_value=MockCamera()):
            r = client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
        assert r.status_code == 409

    def test_409_detail_mentions_tec(self) -> None:
        from smart_telescope.adapters.mock.camera import MockCamera
        with patch.object(deps, "get_preview_camera", return_value=MockCamera()):
            r = client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
        assert "TEC" in r.json()["detail"] or "tec" in r.json()["detail"].lower()


# ── POST /api/cooling/set_target — TEC camera ────────────────────────────────

class TestSetTarget:
    def test_returns_200(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            r = client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
        assert r.status_code == 200

    def test_response_ok_and_target(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            d = client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -5.0}).json()
        assert d["ok"] is True
        assert d["target_c"] == pytest.approx(-5.0)

    def test_enables_tec_on_camera(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
        assert cam.tec_enabled is True

    def test_sets_target_on_camera(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -8.0})
        assert cam.tec_target_c == pytest.approx(-8.0)

    def test_target_clamped_to_minus_10(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            d = client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0}).json()
        assert d["target_c"] == pytest.approx(-10.0)

    def test_target_above_max_rejected_by_schema(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            r = client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": 15.0})
        assert r.status_code == 422

    def test_target_below_min_rejected_by_schema(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            r = client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -15.0})
        assert r.status_code == 422


# ── POST /api/cooling/set_target — disable ───────────────────────────────────

class TestDisableCooling:
    def test_returns_200(self) -> None:
        r = client.post("/api/cooling/set_target", json={"enabled": False})
        assert r.status_code == 200

    def test_response_ok(self) -> None:
        d = client.post("/api/cooling/set_target", json={"enabled": False}).json()
        assert d["ok"] is True

    def test_status_is_disabled_after_disable(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
            client.post("/api/cooling/set_target", json={"enabled": False})
        assert client.get("/api/cooling/status").json()["enabled"] is False


# ── GET /api/cooling/status — after enabling ─────────────────────────────────

class TestStatusAfterEnable:
    def test_enabled_is_true(self) -> None:
        cam = _TecCamera(temp_c=15.0)
        cam.power_pct = 50.0
        with patch.object(deps, "get_preview_camera", return_value=cam):
            client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
            # Give poll thread a moment to run its first poll
            import time; time.sleep(0.2)
            d = client.get("/api/cooling/status").json()
        assert d["enabled"] is True

    def test_camera_index_matches_request(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
            import time; time.sleep(0.2)
            d = client.get("/api/cooling/status").json()
        assert d["camera_index"] == 0

    def test_target_c_matches_request(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -7.0})
            import time; time.sleep(0.2)
            d = client.get("/api/cooling/status").json()
        assert d["target_c"] == pytest.approx(-7.0)

    def test_current_temp_is_populated(self) -> None:
        cam = _TecCamera(temp_c=5.0)
        with patch.object(deps, "get_preview_camera", return_value=cam):
            client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
            import time; time.sleep(0.2)
            d = client.get("/api/cooling/status").json()
        assert d["current_temp_c"] is not None

    def test_seconds_remaining_is_populated(self) -> None:
        cam = _TecCamera()
        with patch.object(deps, "get_preview_camera", return_value=cam):
            client.post("/api/cooling/set_target", json={"camera_index": 0, "target_c": -10.0})
            import time; time.sleep(0.2)
            d = client.get("/api/cooling/status").json()
        assert d["seconds_remaining"] is not None
        assert d["seconds_remaining"] >= 0
