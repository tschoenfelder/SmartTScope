"""API wiring tests for GET /api/observing/state and POST /api/observing/intent.

Only exercises request/response plumbing (dependency wiring, intent validation,
JSON shape) — engine-level behavior (polar align, focus, capture, safe-stop) is
covered by tests/unit/services/test_observing_service.py against mocked ports.
"""

from __future__ import annotations

import time
from unittest.mock import patch

from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.runtime import RuntimeContext

client = TestClient(app)


def _reset() -> None:
    deps.reset()


def _wait_idle(timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    body = client.get("/api/observing/state").json()
    while body["busy"]:
        if time.monotonic() > deadline:
            raise TimeoutError(f"Observing service did not finish; last detail={body['detail']}")
        time.sleep(0.02)
        body = client.get("/api/observing/state").json()
    return body


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
            "primary_action", "secondary_actions", "readiness", "mount_state",
            "cameras",
        }
        # M10-002: camera identification payload (None only when the runtime
        # service is unavailable; here it exists with the standard shape).
        if body["cameras"] is not None:
            assert set(body["cameras"]) == {
                "sdk_available", "scanned", "roles", "unassigned", "filter_wheel",
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
        client.post("/api/observing/intent", json={"intent": "START_HOME"})
        body = _wait_idle()
        assert body["guards"]["g2_home_confirmed"] is True

        r = client.post("/api/observing/intent", json={"intent": "CONFIRM_HOME"})
        body = r.json()
        assert body["phase"] == "POLAR_ALIGN"


class TestNoInlineCameraOpen:
    """M10-022: the hot observing endpoints must never open (or wait for) a
    camera — a stalled camera bring-up must not block confirm time/location."""

    def _forbid_camera(self):
        boom = AssertionError("camera opened on a hot observing path")
        return (
            patch.object(RuntimeContext, "get_camera", side_effect=boom),
            patch.object(RuntimeContext, "get_camera_by_role", side_effect=boom),
        )

    def test_state_never_touches_a_camera(self) -> None:
        _reset()
        p1, p2 = self._forbid_camera()
        with p1, p2:
            r = client.get("/api/observing/state")
        assert r.status_code == 200
        assert r.json()["phase"] == "WAIT_CONTEXT_CONFIRMATION"

    def test_confirm_context_never_touches_a_camera(self) -> None:
        _reset()
        p1, p2 = self._forbid_camera()
        with p1, p2:
            r = client.post("/api/observing/intent", json={"intent": "CONFIRM_CONTEXT"})
        assert r.status_code == 200
        assert r.json()["phase"] == "WAIT_HOME_CONFIRMATION"
