"""Unit tests for catalog search API endpoints."""

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app

client = TestClient(app)


class TestCatalogSearch:
    def test_returns_200(self) -> None:
        assert client.get("/api/catalog/search?q=m42").status_code == 200

    def test_m42_in_results(self) -> None:
        data = client.get("/api/catalog/search?q=m42").json()
        names = [entry["name"] for entry in data]
        assert "M42" in names

    def test_first_result_is_exact_match(self) -> None:
        data = client.get("/api/catalog/search?q=M42").json()
        assert data[0]["name"] == "M42"

    def test_result_has_required_fields(self) -> None:
        data = client.get("/api/catalog/search?q=m13").json()
        entry = data[0]
        assert {"name", "common_name", "ra_hours", "dec_deg", "object_type", "magnitude"} <= entry.keys()

    def test_ra_hours_in_valid_range(self) -> None:
        data = client.get("/api/catalog/search?q=m42").json()
        for entry in data:
            assert 0.0 <= entry["ra_hours"] < 24.0

    def test_common_name_search(self) -> None:
        data = client.get("/api/catalog/search?q=orion").json()
        assert any(e["name"] == "M42" for e in data)

    def test_limit_parameter_respected(self) -> None:
        data = client.get("/api/catalog/search?q=m&limit=3").json()
        assert len(data) <= 3

    def test_missing_query_returns_422(self) -> None:
        assert client.get("/api/catalog/search").status_code == 422

    def test_empty_result_on_no_match(self) -> None:
        data = client.get("/api/catalog/search?q=XYZNOTFOUND").json()
        assert data == []

    def test_case_insensitive(self) -> None:
        lower = client.get("/api/catalog/search?q=m31").json()
        upper = client.get("/api/catalog/search?q=M31").json()
        assert [e["name"] for e in lower] == [e["name"] for e in upper]


class TestCatalogObjects:
    def test_returns_200(self) -> None:
        assert client.get("/api/catalog/objects").status_code == 200

    def test_returns_110_objects(self) -> None:
        data = client.get("/api/catalog/objects").json()
        assert len(data) == 110

    def test_all_have_name_field(self) -> None:
        data = client.get("/api/catalog/objects").json()
        assert all("name" in entry for entry in data)

    def test_first_is_m1(self) -> None:
        data = client.get("/api/catalog/objects").json()
        assert data[0]["name"] == "M1"

    def test_last_is_m110(self) -> None:
        data = client.get("/api/catalog/objects").json()
        assert data[-1]["name"] == "M110"
