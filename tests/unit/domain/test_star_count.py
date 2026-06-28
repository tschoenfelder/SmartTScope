"""Unit tests for domain/star_count.py — StarCountResult and FrameQuality."""
from __future__ import annotations

import pytest

from smart_telescope.domain.star_count import FrameQuality, StarCountResult


def _make(**kwargs) -> StarCountResult:
    defaults = dict(
        stars_found=10,
        image_quality="usable",
        suggested_exposure_s=None,
        suggested_gain=None,
        suggested_offset=None,
        focus_warning=False,
        notes=(),
        sources=(),
    )
    defaults.update(kwargs)
    return StarCountResult(**defaults)


class TestStarCountResult:
    def test_is_frozen(self) -> None:
        r = _make()
        with pytest.raises((AttributeError, TypeError)):
            r.stars_found = 99  # type: ignore[misc]

    def test_all_frame_quality_values_accepted(self) -> None:
        for q in ("usable", "too_dark", "too_bright", "stars_saturated"):
            r = _make(image_quality=q)
            assert r.image_quality == q

    def test_sources_accepts_arbitrary_tuple(self) -> None:
        sentinel = object()
        r = _make(sources=(sentinel, 42, "text"))
        assert r.sources[0] is sentinel
        assert r.sources[1] == 42

    def test_optional_fields_default_to_none(self) -> None:
        r = _make()
        assert r.suggested_exposure_s is None
        assert r.suggested_gain is None
        assert r.suggested_offset is None

    def test_suggested_fields_carry_values(self) -> None:
        r = _make(suggested_exposure_s=2.5, suggested_gain=200, suggested_offset=50)
        assert r.suggested_exposure_s == 2.5
        assert r.suggested_gain == 200
        assert r.suggested_offset == 50

    def test_focus_warning_true(self) -> None:
        r = _make(focus_warning=True)
        assert r.focus_warning is True

    def test_notes_tuple_preserved(self) -> None:
        r = _make(notes=("note one", "note two"))
        assert r.notes == ("note one", "note two")

    def test_equality(self) -> None:
        a = _make(stars_found=5)
        b = _make(stars_found=5)
        assert a == b

    def test_inequality_on_field_difference(self) -> None:
        a = _make(stars_found=5)
        b = _make(stars_found=6)
        assert a != b
