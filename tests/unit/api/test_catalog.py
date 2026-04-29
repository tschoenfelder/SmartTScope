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


# ── GET /api/catalog/tonight ──────────────────────────────────────────────────

_SOLAR_SAFE   = (False, 120.0)   # not blocked, 120° from Sun
_SOLAR_UNSAFE = (True,    1.5)   # blocked, 1.5° from Sun


def _patch_tonight(alt: float = 45.0, az: float = 180.0, solar_blocked: bool = False):
    """Patch both compute_altaz and is_solar_target for /tonight tests."""
    return (
        patch("smart_telescope.api.catalog.compute_altaz", return_value=(alt, az)),
        patch("smart_telescope.api.catalog.is_solar_target",
              return_value=(solar_blocked, 1.5 if solar_blocked else 120.0)),
    )


class TestCatalogTonight:
    def test_returns_200(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            assert client.get("/api/catalog/tonight").status_code == 200

    def test_response_is_list(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight").json()
        assert isinstance(data, list)

    def test_entries_have_solar_safe_field(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight").json()
        assert len(data) > 0
        assert "solar_safe" in data[0]

    def test_solar_safe_true_when_not_blocked(self) -> None:
        alt_patch, solar_patch = _patch_tonight(solar_blocked=False)
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight").json()
        assert all(e["solar_safe"] is True for e in data)

    def test_solar_safe_false_when_blocked(self) -> None:
        alt_patch, solar_patch = _patch_tonight(solar_blocked=True)
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight").json()
        assert all(e["solar_safe"] is False for e in data)

    def test_empty_when_nothing_above_min_altitude(self) -> None:
        alt_patch, solar_patch = _patch_tonight(alt=-5.0)
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight?min_altitude=20").json()
        assert data == []

    def test_all_results_have_altitude_deg(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight").json()
        assert all(e["altitude_deg"] is not None for e in data)

    def test_sorted_by_altitude_descending(self) -> None:
        # Give each call a slightly different altitude by cycling values
        altitudes = [70.0, 30.0, 50.0]
        call_count = 0

        def varying_altaz(ra, dec, lat, lon):
            nonlocal call_count
            alt = altitudes[call_count % len(altitudes)]
            call_count += 1
            return alt, 180.0

        with (
            patch("smart_telescope.api.catalog.compute_altaz", side_effect=varying_altaz),
            patch("smart_telescope.api.catalog.is_solar_target", return_value=_SOLAR_SAFE),
        ):
            data = client.get("/api/catalog/tonight?min_altitude=0").json()

        alts = [e["altitude_deg"] for e in data]
        assert alts == sorted(alts, reverse=True)

    def test_limit_parameter_respected(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight?limit=5").json()
        assert len(data) <= 5

    def test_object_type_filter_gc_only(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight?object_type=GC").json()
        assert all(e["object_type"] == "GC" for e in data)

    def test_object_type_filter_multiple_types(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight?object_type=GC,SG").json()
        assert all(e["object_type"] in ("GC", "SG") for e in data)

    def test_object_type_filter_unknown_type_returns_empty(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight?object_type=XYZTYPE").json()
        assert data == []

    def test_max_magnitude_excludes_faint_objects(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight?max_magnitude=5.0").json()
        assert all(e["magnitude"] <= 5.0 for e in data)

    def test_default_limit_is_twenty(self) -> None:
        alt_patch, solar_patch = _patch_tonight()
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight").json()
        assert len(data) <= 20

    def test_min_altitude_default_excludes_horizon(self) -> None:
        # Objects at exactly 19° should be excluded by default min_altitude=20
        alt_patch, solar_patch = _patch_tonight(alt=19.0)
        with alt_patch, solar_patch:
            data = client.get("/api/catalog/tonight").json()
        assert data == []
