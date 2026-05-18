"""Unit tests for GET /api/performance-targets."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app

client = TestClient(app)

_EXPECTED_KEYS = {
    "session_duration_hours",
    "preview_latency_s",
    "stop_response_ms",
    "centering_accuracy_arcsec",
    "plate_solve_success_pct",
    "pi_thermal_ceiling_c",
}

_TARGET_FIELDS = {"value", "unit", "rationale"}


@pytest.fixture(autouse=True)
def _reset():
    from smart_telescope.api import deps
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


class TestPerformanceTargetsEndpoint:
    def test_returns_200(self) -> None:
        assert client.get("/api/performance-targets").status_code == 200

    def test_response_has_all_six_keys(self) -> None:
        body = client.get("/api/performance-targets").json()
        assert _EXPECTED_KEYS <= body.keys()

    def test_each_target_has_value_unit_rationale(self) -> None:
        body = client.get("/api/performance-targets").json()
        for key in _EXPECTED_KEYS:
            assert _TARGET_FIELDS <= body[key].keys(), f"{key} missing fields"

    def test_all_values_are_positive_numbers(self) -> None:
        body = client.get("/api/performance-targets").json()
        for key in _EXPECTED_KEYS:
            val = body[key]["value"]
            assert isinstance(val, (int, float)) and val > 0, (
                f"{key}: value={val!r} is not a positive number"
            )

    def test_stop_response_ms_at_most_1000(self) -> None:
        body = client.get("/api/performance-targets").json()
        assert body["stop_response_ms"]["value"] <= 1000

    def test_plate_solve_success_pct_between_0_and_100(self) -> None:
        body = client.get("/api/performance-targets").json()
        pct = body["plate_solve_success_pct"]["value"]
        assert 0 < pct <= 100

    def test_all_units_are_non_empty_strings(self) -> None:
        body = client.get("/api/performance-targets").json()
        for key in _EXPECTED_KEYS:
            unit = body[key]["unit"]
            assert isinstance(unit, str) and unit, f"{key}: empty unit"
