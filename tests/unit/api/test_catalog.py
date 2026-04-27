"""Unit tests for catalog search API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app

client = TestClient(app)

# Deterministic altitude stubs so tests don't depend on the real clock
_ABOVE = (45.0, 180.0)   # altitude=45°, azimuth=180°
_BELOW = (-10.0, 90.0)   # altitude=-10° (below horizon)


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
        assert {"name", "common_name", "ra_hours", "dec_deg", "object_type", "magnitude",
                "altitude_deg", "azimuth_deg"} <= entry.keys()

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

    def test_altitude_deg_field_is_float(self) -> None:
        with patch("smart_telescope.api.catalog.compute_altaz", return_value=_ABOVE):
            data = client.get("/api/catalog/search?q=m42").json()
        assert isinstance(data[0]["altitude_deg"], float)

    def test_azimuth_deg_field_is_float(self) -> None:
        with patch("smart_telescope.api.catalog.compute_altaz", return_value=_ABOVE):
            data = client.get("/api/catalog/search?q=m42").json()
        assert isinstance(data[0]["azimuth_deg"], float)

    def test_min_altitude_excludes_below_horizon(self) -> None:
        with patch("smart_telescope.api.catalog.compute_altaz", return_value=_BELOW):
            data = client.get("/api/catalog/search?q=m42&min_altitude=20").json()
        assert data == []

    def test_min_altitude_passes_high_target(self) -> None:
        with patch("smart_telescope.api.catalog.compute_altaz", return_value=_ABOVE):
            data = client.get("/api/catalog/search?q=m42&min_altitude=20").json()
        assert any(e["name"] == "M42" for e in data)

    def test_min_altitude_negative_rejects_no_target(self) -> None:
        with patch("smart_telescope.api.catalog.compute_altaz", return_value=_ABOVE):
            data = client.get("/api/catalog/search?q=m42&min_altitude=-90").json()
        assert len(data) > 0

    def test_min_altitude_invalid_returns_422(self) -> None:
        assert client.get("/api/catalog/search?q=m42&min_altitude=91").status_code == 422


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

    def test_altitude_none_without_filter(self) -> None:
        data = client.get("/api/catalog/objects").json()
        assert data[0]["altitude_deg"] is None

    def test_altitude_present_with_min_altitude_filter(self) -> None:
        with patch("smart_telescope.api.catalog.compute_altaz", return_value=_ABOVE):
            data = client.get("/api/catalog/objects?min_altitude=0").json()
        assert data[0]["altitude_deg"] is not None

    def test_min_altitude_filters_objects_list(self) -> None:
        with patch("smart_telescope.api.catalog.compute_altaz", return_value=_BELOW):
            data = client.get("/api/catalog/objects?min_altitude=20").json()
        assert data == []
