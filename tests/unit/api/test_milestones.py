"""Unit tests for GET /api/milestones — milestone dashboard and risk view."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    from smart_telescope.api import deps
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


# ── HTTP contract ─────────────────────────────────────────────────────────────


class TestMilestonesEndpoint:
    def test_returns_200(self) -> None:
        r = client.get("/api/milestones")
        assert r.status_code == 200

    def test_response_has_milestones_and_top_risks_keys(self) -> None:
        body = client.get("/api/milestones").json()
        assert "milestones" in body
        assert "top_risks" in body

    def test_milestones_is_a_non_empty_list(self) -> None:
        body = client.get("/api/milestones").json()
        assert isinstance(body["milestones"], list)
        assert len(body["milestones"]) > 0

    def test_each_milestone_has_required_fields(self) -> None:
        required = {"id", "name", "total", "done", "open", "hardware_blocked", "status"}
        for m in client.get("/api/milestones").json()["milestones"]:
            assert required <= m.keys(), f"milestone {m.get('id')!r} missing fields"

    def test_done_plus_open_equals_total(self) -> None:
        for m in client.get("/api/milestones").json()["milestones"]:
            assert m["done"] + m["open"] == m["total"], (
                f"milestone {m['id']}: done+open != total"
            )

    def test_status_values_are_valid(self) -> None:
        valid = {"green", "yellow", "red"}
        for m in client.get("/api/milestones").json()["milestones"]:
            assert m["status"] in valid, f"milestone {m['id']}: bad status {m['status']!r}"

    def test_top_risks_at_most_ten(self) -> None:
        body = client.get("/api/milestones").json()
        assert len(body["top_risks"]) <= 10

    def test_top_risks_sorted_p0_before_p1(self) -> None:
        risks = client.get("/api/milestones").json()["top_risks"]
        priorities = [r["priority"] for r in risks]
        last_p0 = max((i for i, p in enumerate(priorities) if p == "P0"), default=-1)
        first_p1 = min((i for i, p in enumerate(priorities) if p == "P1"), default=len(priorities))
        assert last_p0 < first_p1 or first_p1 == len(priorities)

    def test_each_risk_has_required_fields(self) -> None:
        required = {"id", "priority", "description", "milestone", "tags"}
        for r in client.get("/api/milestones").json()["top_risks"]:
            assert required <= r.keys(), f"risk {r.get('id')!r} missing fields"
