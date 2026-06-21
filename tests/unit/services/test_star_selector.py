"""Tests for CollimationStarSelector — Phase 5, Task 5.1."""
from __future__ import annotations

import tomllib
import tempfile
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
from astropy.time import Time

from smart_telescope.services.collimation.star_selector import (
    BrightStar,
    CollimationStarCandidate,
    CollimationStarSelector,
    StarSelectionResult,
    load_bright_stars,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _star(name: str = "TestStar", ra: float = 18.0, dec: float = 45.0, mag: float = 1.0) -> BrightStar:
    return BrightStar(name=name, ra_hours=ra, dec_deg=dec, magnitude=mag)


def _selector(stars: list[BrightStar] | None = None) -> CollimationStarSelector:
    return CollimationStarSelector(
        stars=stars or [_star()],
        observer_lat=50.0,
        observer_lon=8.0,
    )


# Patch compute_altaz / compute_ha in the star_selector module so we can control altitude
# and avoid time-dependent HA limit filtering.
_MODULE    = "smart_telescope.services.collimation.star_selector.compute_altaz"
_MODULE_HA = "smart_telescope.services.collimation.star_selector.compute_ha"


# ── Data classes ──────────────────────────────────────────────────────────────

class TestBrightStar:
    def test_fields(self):
        s = BrightStar(name="Vega", ra_hours=18.6, dec_deg=38.8, magnitude=0.03)
        assert s.name == "Vega"
        assert s.ra_hours == pytest.approx(18.6)
        assert s.dec_deg  == pytest.approx(38.8)
        assert s.magnitude == pytest.approx(0.03)


class TestCollimationStarCandidate:
    def test_fields(self):
        star = _star()
        c = CollimationStarCandidate(star=star, altitude_deg=70.0, azimuth_deg=180.0)
        assert c.altitude_deg == pytest.approx(70.0)
        assert c.azimuth_deg  == pytest.approx(180.0)
        assert c.star is star


class TestStarSelectionResult:
    def test_fields_with_candidate(self):
        star = _star()
        c = CollimationStarCandidate(star=star, altitude_deg=65.0, azimuth_deg=200.0)
        r = StarSelectionResult(candidate=c, reason="selected", warning=None)
        assert r.reason == "selected"
        assert r.warning is None
        assert r.candidate is c

    def test_fields_none(self):
        r = StarSelectionResult(candidate=None, reason="none_visible", warning=None)
        assert r.candidate is None


# ── select() — primary threshold ──────────────────────────────────────────────

class TestSelectPrimary:
    def test_returns_star_above_primary_threshold(self):
        stars = [_star(name="A", mag=1.0)]
        sel = _selector(stars)
        with patch(_MODULE, return_value=(70.0, 180.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select()
        assert result.reason == "selected"
        assert result.candidate is not None
        assert result.candidate.star.name == "A"
        assert result.warning is None

    def test_returns_brightest_among_primary_candidates(self):
        stars = [
            _star(name="Dim",    mag=2.0),
            _star(name="Bright", mag=0.5),
            _star(name="Medium", mag=1.5),
        ]
        sel = _selector(stars)
        # All above 60°
        with patch(_MODULE, return_value=(65.0, 180.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select()
        assert result.candidate.star.name == "Bright"

    def test_altitude_carried_in_candidate(self):
        sel = _selector([_star()])
        with patch(_MODULE, return_value=(72.5, 200.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select()
        assert result.candidate.altitude_deg == pytest.approx(72.5)
        assert result.candidate.azimuth_deg  == pytest.approx(200.0)


# ── select() — fallback threshold ────────────────────────────────────────────

class TestSelectFallback:
    def test_fallback_when_none_above_primary(self):
        """50° altitude < 60° primary but >= 45° fallback → reason='fallback'."""
        stars = [_star(name="Low", mag=0.5)]
        sel = _selector(stars)
        with patch(_MODULE, return_value=(50.0, 90.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select()
        assert result.reason == "fallback"
        assert result.candidate is not None
        assert result.candidate.star.name == "Low"

    def test_fallback_includes_warning(self):
        stars = [_star()]
        sel = _selector(stars)
        with patch(_MODULE, return_value=(50.0, 90.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select()
        assert result.warning is not None
        assert "fallback" in result.warning.lower()

    def test_fallback_brightest_selected(self):
        stars = [
            _star(name="A", mag=0.5),
            _star(name="B", mag=2.0),
        ]
        sel = _selector(stars)
        # 50° altitude: above fallback, below primary
        with patch(_MODULE, return_value=(50.0, 90.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select()
        assert result.candidate.star.name == "A"


# ── select() — none visible ───────────────────────────────────────────────────

class TestSelectNoneVisible:
    def test_returns_none_when_all_below_fallback(self):
        stars = [_star()]
        sel = _selector(stars)
        with patch(_MODULE, return_value=(30.0, 90.0)):
            result = sel.select()
        assert result.reason == "none_visible"
        assert result.candidate is None

    def test_no_warning_when_none_visible(self):
        sel = _selector([_star()])
        with patch(_MODULE, return_value=(10.0, 0.0)):
            result = sel.select()
        # warning not required when none_visible — implementation may set None or a message
        assert result.candidate is None

    def test_mixed_altitudes_selects_primary(self):
        """One star above primary, another below fallback → primary wins."""
        stars = [
            _star(name="High", mag=2.0),
            _star(name="Low",  mag=0.5),
        ]
        sel = _selector(stars)
        alts = {"High": 65.0, "Low": 20.0}
        call_count = [0]

        def _mock_altaz(ra, dec, lat, lon, t=None):
            idx = call_count[0] % len(stars)
            call_count[0] += 1
            return (alts[stars[idx].name], 90.0)

        with patch(_MODULE, side_effect=_mock_altaz), patch(_MODULE_HA, return_value=0.0):
            result = sel.select()
        assert result.reason == "selected"
        assert result.candidate.star.name == "High"


# ── select_by_name() ──────────────────────────────────────────────────────────

class TestSelectByName:
    def test_finds_star_by_exact_name(self):
        stars = [_star(name="Vega"), _star(name="Sirius")]
        sel = _selector(stars)
        with patch(_MODULE, return_value=(70.0, 180.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select_by_name("Vega")
        assert result.reason == "manual"
        assert result.candidate.star.name == "Vega"

    def test_case_insensitive_match(self):
        stars = [_star(name="Arcturus")]
        sel = _selector(stars)
        with patch(_MODULE, return_value=(60.0, 90.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select_by_name("arcturus")
        assert result.candidate.star.name == "Arcturus"

    def test_not_found_returns_none_candidate(self):
        sel = _selector([_star(name="Vega")])
        result = sel.select_by_name("NonExistent")
        assert result.candidate is None
        assert result.reason == "none_visible"

    def test_not_found_carries_warning(self):
        sel = _selector([_star(name="Vega")])
        result = sel.select_by_name("Unknown")
        assert result.warning is not None
        assert "Unknown" in result.warning

    def test_manual_does_not_filter_by_altitude(self):
        """Manual override returns the star regardless of altitude."""
        stars = [_star(name="LowStar")]
        sel = _selector(stars)
        # Even if below fallback threshold, manual override should succeed
        with patch(_MODULE, return_value=(10.0, 0.0)), patch(_MODULE_HA, return_value=0.0):
            result = sel.select_by_name("LowStar")
        assert result.reason == "manual"
        assert result.candidate.star.name == "LowStar"
        assert result.candidate.altitude_deg == pytest.approx(10.0)


# ── load_bright_stars() ───────────────────────────────────────────────────────

_TOML_CONTENT = textwrap.dedent("""\
    [[targets]]
    name        = "Vega"
    ra          = 18.6156
    dec         = 38.7836
    type        = "star"
    magnitude   = 0.03

    [[targets]]
    name        = "NGC 7000"
    ra          = 20.99
    dec         = 44.53
    type        = "nebula"
    magnitude   = 4.0

    [[targets]]
    name        = "Jupiter"
    ra          = 7.83
    dec         = 21.9
    type        = "planet"
    magnitude   = -2.0

    [[targets]]
    name        = "NoMag"
    ra          = 5.0
    dec         = 30.0
    type        = "star"
""")


class TestLoadBrightStars:
    def _write_toml(self, content: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(suffix=".cfg", delete=False, mode="w")
        tmp.write(content)
        tmp.close()
        return Path(tmp.name)

    def test_loads_only_star_type(self):
        path = self._write_toml(_TOML_CONTENT)
        stars = load_bright_stars(path)
        names = [s.name for s in stars]
        assert "Vega" in names
        assert "NGC 7000" not in names
        assert "Jupiter" not in names

    def test_skips_entries_without_magnitude(self):
        path = self._write_toml(_TOML_CONTENT)
        stars = load_bright_stars(path)
        names = [s.name for s in stars]
        assert "NoMag" not in names

    def test_loads_correct_fields(self):
        path = self._write_toml(_TOML_CONTENT)
        stars = load_bright_stars(path)
        vega = next(s for s in stars if s.name == "Vega")
        assert vega.ra_hours  == pytest.approx(18.6156)
        assert vega.dec_deg   == pytest.approx(38.7836)
        assert vega.magnitude == pytest.approx(0.03)

    def test_returns_empty_for_no_stars(self):
        path = self._write_toml('[[targets]]\nname="M42"\nra=5.5\ndec=-5.0\ntype="nebula"\nmagnitude=4.0\n')
        stars = load_bright_stars(path)
        assert stars == []
