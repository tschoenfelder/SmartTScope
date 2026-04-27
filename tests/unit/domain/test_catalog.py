"""Unit tests for the Messier catalog domain module."""

import pytest

from smart_telescope.domain.catalog import CatalogObject, get_all, get_by_name, search


class TestCatalogData:
    def test_catalog_has_110_objects(self) -> None:
        assert len(get_all()) == 110

    def test_all_objects_have_valid_ra(self) -> None:
        for obj in get_all():
            assert 0.0 <= obj.ra_hours < 24.0, f"{obj.name} has invalid RA {obj.ra_hours}"

    def test_all_objects_have_valid_dec(self) -> None:
        for obj in get_all():
            assert -90.0 <= obj.dec_deg <= 90.0, f"{obj.name} has invalid Dec {obj.dec_deg}"

    def test_m42_coordinates(self) -> None:
        m42 = get_by_name("M42")
        assert m42 is not None
        assert m42.ra_hours == pytest.approx(5.5883, abs=0.01)
        assert m42.dec_deg == pytest.approx(-5.3911, abs=0.01)

    def test_m31_common_name(self) -> None:
        m31 = get_by_name("M31")
        assert m31 is not None
        assert "Andromeda" in m31.common_name

    def test_object_type_nonempty(self) -> None:
        for obj in get_all():
            assert obj.object_type, f"{obj.name} has empty object_type"


class TestGetByName:
    def test_exact_match_uppercase(self) -> None:
        assert get_by_name("M1") is not None

    def test_exact_match_lowercase(self) -> None:
        assert get_by_name("m42") is not None

    def test_exact_match_with_space(self) -> None:
        assert get_by_name("M 42") is not None

    def test_last_entry_m110(self) -> None:
        assert get_by_name("M110") is not None

    def test_nonexistent_returns_none(self) -> None:
        assert get_by_name("NGC1234") is None

    def test_returns_catalog_object(self) -> None:
        assert isinstance(get_by_name("M57"), CatalogObject)


class TestSearch:
    def test_exact_designation_returns_first(self) -> None:
        results = search("M42")
        assert results[0].name == "M42"

    def test_case_insensitive_designation(self) -> None:
        results = search("m42")
        assert any(obj.name == "M42" for obj in results)

    def test_designation_prefix_m4_returns_m4_first(self) -> None:
        results = search("M4")
        assert results[0].name == "M4"

    def test_designation_prefix_includes_m42(self) -> None:
        results = search("M4", limit=20)
        names = [obj.name for obj in results]
        assert "M42" in names

    def test_common_name_substring(self) -> None:
        results = search("orion")
        assert any("M42" == obj.name for obj in results)

    def test_common_name_partial(self) -> None:
        results = search("andromeda")
        assert any(obj.name == "M31" for obj in results)

    def test_limit_respected(self) -> None:
        results = search("M", limit=3)
        assert len(results) <= 3

    def test_empty_query_returns_empty(self) -> None:
        results = search("   ")
        assert results == []

    def test_no_match_returns_empty(self) -> None:
        results = search("XYZNOTFOUND")
        assert results == []

    def test_space_normalised(self) -> None:
        results = search("M 42")
        assert any(obj.name == "M42" for obj in results)
