"""API wiring tests for GET /api/observing/state and POST /api/observing/intent.

Only exercises request/response plumbing (dependency wiring, intent validation,
JSON shape) — engine-level behavior (polar align, focus, capture, safe-stop) is
covered by tests/unit/services/test_observing_service.py against mocked ports.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app

client = TestClient(app)


def _reset() -> None:
    deps.reset()


class TestObservingState:
    def test_initial_state_is_wait_context_confirmation(self) -> None:
        _reset()
        r = client.get("/api/observing/state")
        assert r.status_code == 200
        body = r.json()
        assert body["phase"] == "WAIT_CONTEXT_CONFIRMATION"
        assert body["primary_action"]["intent"] == "CONFIRM_CONTEXT"
        assert set(body) == {
            "phase", "guards", "busy", "detail", "fault_message",
            "primary_action", "secondary_actions", "readiness",
        }


class TestObservingIntent:
    def test_confirm_context_advances_phase(self) -> None:
        _reset()
        r = client.post("/api/observing/intent", json={"intent": "CONFIRM_CONTEXT"})
        assert r.status_code == 200
        body = r.json()
        assert body["phase"] == "WAIT_HOME_CONFIRMATION"
        assert body["guards"]["g1_context_confirmed"] is True

    def test_unknown_intent_returns_422(self) -> None:
        _reset()
        r = client.post("/api/observing/intent", json={"intent": "NOT_A_REAL_INTENT"})
        assert r.status_code == 422
        assert "Unknown intent" in r.json()["detail"]

    def test_confirm_home_then_polar_align(self) -> None:
        _reset()
        client.post("/api/observing/intent", json={"intent": "CONFIRM_CONTEXT"})
        r = client.post("/api/observing/intent", json={"intent": "CONFIRM_HOME"})
        body = r.json()
        assert body["phase"] == "POLAR_ALIGN"
        assert body["guards"]["g2_home_confirmed"] is True
