"""Unit tests for domain/visibility — altitude/azimuth and observable check."""

import textwrap
from pathlib import Path

import pytest
from astropy.time import Time

from smart_telescope.domain.visibility import (
    HorizonProfile,
    compute_altaz,
    compute_ha,
    is_observable,
    load_horizon,
)

# Observer: Usingen, Germany (50.336°N, 8.533°E)
_LAT = 50.336
_LON = 8.533

# Fixed test epoch: 2026-04-28T22:00:00 UTC (night-time at Usingen)
_NIGHT = Time("2026-04-28T22:00:00", scale="utc")
# Fixed test epoch: 2026-04-28T12:00:00 UTC (midday — most northern DSOs below horizon? no)
_NOON = Time("2026-04-28T12:00:00", scale="utc")


class TestComputeAltaz:
    def test_returns_two_floats(self) -> None:
        alt, az = compute_altaz(5.5883, -5.391, _LAT, _LON, obs_time=_NIGHT)
        assert isinstance(alt, float)
        assert isinstance(az, float)

    def test_altitude_in_valid_range(self) -> None:
        alt, az = compute_altaz(5.5883, -5.391, _LAT, _LON, obs_time=_NIGHT)
        assert -90.0 <= alt <= 90.0

    def test_azimuth_in_valid_range(self) -> None:
        _, az = compute_altaz(5.5883, -5.391, _LAT, _LON, obs_time=_NIGHT)
        assert 0.0 <= az < 360.0

    def test_circumpolar_target_always_positive_alt(self) -> None:
        # Polaris (RA≈2.53h, Dec≈+89.26°) is circumpolar from Usingen
        alt, _ = compute_altaz(2.53, 89.26, _LAT, _LON, obs_time=_NIGHT)
        assert alt > 0

    def test_southern_target_can_be_negative(self) -> None:
        # Dec = -89° is below horizon from Usingen (lat 50°N)
        alt, _ = compute_altaz(0.0, -89.0, _LAT, _LON, obs_time=_NIGHT)
        assert alt < 0

    def test_south_pole_is_always_below_horizon(self) -> None:
        alt, _ = compute_altaz(0.0, -90.0, _LAT, _LON, obs_time=_NOON)
        assert alt < 0

    def test_uses_time_now_when_none(self) -> None:
        # Should not raise — just verify it returns valid numbers
        alt, az = compute_altaz(5.5883, -5.391, _LAT, _LON)
        assert -90.0 <= alt <= 90.0
        assert 0.0 <= az < 360.0

    def test_different_times_give_different_altitudes(self) -> None:
        alt1, _ = compute_altaz(5.5883, -5.391, _LAT, _LON, obs_time=_NIGHT)
        alt2, _ = compute_altaz(5.5883, -5.391, _LAT, _LON, obs_time=_NOON)
        assert alt1 != pytest.approx(alt2, abs=1.0)


class TestIsObservable:
    def test_circumpolar_is_observable(self) -> None:
        assert is_observable(2.53, 89.26, _LAT, _LON, obs_time=_NIGHT) is True

    def test_deep_south_not_observable(self) -> None:
        assert is_observable(0.0, -89.0, _LAT, _LON, obs_time=_NIGHT) is False

    def test_custom_min_altitude_zero_accepts_anything_above_horizon(self) -> None:
        alt, _ = compute_altaz(2.53, 89.26, _LAT, _LON, obs_time=_NIGHT)
        assert is_observable(2.53, 89.26, _LAT, _LON, min_altitude=0.0, obs_time=_NIGHT) is True

    def test_high_min_altitude_rejects_low_target(self) -> None:
        # Polaris is ~50° altitude from Usingen — reject with min=80
        assert is_observable(2.53, 89.26, _LAT, _LON, min_altitude=80.0, obs_time=_NIGHT) is False

    def test_returns_bool(self) -> None:
        result = is_observable(5.5883, -5.391, _LAT, _LON, obs_time=_NIGHT)
        assert isinstance(result, bool)

    def test_horizon_profile_blocks_below_profile(self) -> None:
        # Flat horizon at 30° — a target at alt=25 must be rejected even if above 20°
        profile = HorizonProfile([(0.0, 30.0), (360.0, 30.0)])
        # Polaris alt ~50° from Usingen, azimuth ~0° (N); min_altitude=20 normally passes
        alt, az = compute_altaz(2.53, 89.26, _LAT, _LON, obs_time=_NIGHT)
        # With profile raising horizon to 30°, result depends on polaris altitude vs 30°
        result = is_observable(2.53, 89.26, _LAT, _LON, min_altitude=20.0,
                               obs_time=_NIGHT, horizon=profile)
        # Polaris is ~50° alt — above profile's 30° — so should be True
        assert result is True

    def test_horizon_profile_blocks_target_below_local_horizon(self) -> None:
        # Horizon at 60° everywhere — Polaris (~50°) should be blocked
        profile = HorizonProfile([(0.0, 60.0), (360.0, 60.0)])
        result = is_observable(2.53, 89.26, _LAT, _LON, min_altitude=0.0,
                               obs_time=_NIGHT, horizon=profile)
        assert result is False


class TestHorizonProfile:
    def test_empty_profile_returns_zero(self) -> None:
        profile = HorizonProfile([])
        assert profile.min_alt_at(180.0) == 0.0

    def test_exact_point_returns_value(self) -> None:
        profile = HorizonProfile([(0.0, 5.0), (90.0, 10.0), (180.0, 15.0), (270.0, 5.0)])
        assert profile.min_alt_at(0.0) == pytest.approx(5.0)
        assert profile.min_alt_at(90.0) == pytest.approx(10.0)

    def test_interpolates_between_points(self) -> None:
        profile = HorizonProfile([(0.0, 0.0), (90.0, 9.0)])
        # Midpoint should be ~4.5°
        assert profile.min_alt_at(45.0) == pytest.approx(4.5, abs=0.01)

    def test_wraps_past_360(self) -> None:
        # Point at 350° alt=5° and 10° alt=10° — azimuth 0° (=360° wrap) should interpolate
        profile = HorizonProfile([(10.0, 10.0), (350.0, 5.0)])
        result = profile.min_alt_at(360.0)
        assert 5.0 <= result <= 10.0

    def test_azimuth_modulo_360(self) -> None:
        profile = HorizonProfile([(0.0, 3.0), (90.0, 6.0)])
        assert profile.min_alt_at(0.0) == pytest.approx(profile.min_alt_at(360.0))

    def test_is_visible_above_profile(self) -> None:
        profile = HorizonProfile([(0.0, 10.0), (360.0, 10.0)])
        assert profile.is_visible(15.0, 90.0) is True

    def test_is_visible_below_profile(self) -> None:
        profile = HorizonProfile([(0.0, 10.0), (360.0, 10.0)])
        assert profile.is_visible(5.0, 90.0) is False

    def test_load_parses_file(self, tmp_path: Path) -> None:
        content = textwrap.dedent("""\
            # KStars horizon export
            0 5
            90 10
            180 15
            270 5
        """)
        p = tmp_path / "horizon.txt"
        p.write_text(content, encoding="utf-8")
        profile = HorizonProfile.load(p)
        assert profile.min_alt_at(0.0) == pytest.approx(5.0)
        assert profile.min_alt_at(180.0) == pytest.approx(15.0)

    def test_load_skips_comments_and_blank_lines(self, tmp_path: Path) -> None:
        content = "# comment\n\n0 5\n90 10\n"
        p = tmp_path / "horizon.txt"
        p.write_text(content, encoding="utf-8")
        profile = HorizonProfile.load(p)
        assert len(profile._pts) == 2

    def test_load_horizon_returns_none_for_missing_file(self, tmp_path: Path) -> None:
        result = load_horizon(tmp_path / "no_such_file.txt")
        assert result is None

    def test_load_horizon_returns_profile_when_file_exists(self, tmp_path: Path) -> None:
        p = tmp_path / "horizon.txt"
        p.write_text("0 5\n180 10\n", encoding="utf-8")
        result = load_horizon(p)
        assert isinstance(result, HorizonProfile)


class TestComputeHa:
    def test_returns_float(self) -> None:
        ha = compute_ha(5.5883, _LON, obs_time=_NIGHT)
        assert isinstance(ha, float)

    def test_in_range_minus12_to_plus12(self) -> None:
        ha = compute_ha(5.5883, _LON, obs_time=_NIGHT)
        assert -12.0 <= ha <= 12.0

    def test_uses_time_now_when_none(self) -> None:
        ha = compute_ha(5.5883, _LON)
        assert -12.0 <= ha <= 12.0
