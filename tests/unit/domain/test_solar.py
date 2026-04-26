"""Unit tests for solar exclusion gate."""

import pytest

from smart_telescope.domain.solar import (
    SOLAR_EXCLUSION_DEG,
    SolarPosition,
    angular_separation_deg,
    is_solar_target,
    sun_position_now,
)

_SUN = SolarPosition(ra_hours=6.0, dec_deg=23.0)  # fixed mock Sun


class TestAngularSeparationDeg:
    def test_same_point_is_zero(self) -> None:
        assert angular_separation_deg(6.0, 23.0, 6.0, 23.0) == pytest.approx(0.0, abs=1e-9)

    def test_pole_to_pole_is_180(self) -> None:
        sep = angular_separation_deg(0.0, 90.0, 0.0, -90.0)
        assert sep == pytest.approx(180.0, abs=1e-6)

    def test_known_separation(self) -> None:
        # Two points 5 h apart in RA on the equator ≈ 75 °
        sep = angular_separation_deg(0.0, 0.0, 5.0, 0.0)
        assert sep == pytest.approx(75.0, abs=0.01)

    def test_returns_float(self) -> None:
        assert isinstance(angular_separation_deg(0.0, 0.0, 1.0, 0.0), float)


class TestIsSolarTarget:
    def test_target_on_sun_is_blocked(self) -> None:
        blocked, sep = is_solar_target(_SUN.ra_hours, _SUN.dec_deg, sun=_SUN)
        assert blocked is True
        assert sep == pytest.approx(0.0, abs=1e-9)

    def test_target_5deg_away_is_blocked(self) -> None:
        # 5° below sun dec
        blocked, sep = is_solar_target(_SUN.ra_hours, _SUN.dec_deg - 5.0, sun=_SUN)
        assert blocked is True
        assert sep == pytest.approx(5.0, abs=0.01)

    def test_target_15deg_away_is_not_blocked(self) -> None:
        blocked, sep = is_solar_target(_SUN.ra_hours, _SUN.dec_deg - 15.0, sun=_SUN)
        assert blocked is False
        assert sep == pytest.approx(15.0, abs=0.01)

    def test_exactly_at_threshold_is_not_blocked(self) -> None:
        # exactly at threshold: sep == threshold → NOT blocked
        blocked, sep = is_solar_target(
            _SUN.ra_hours, _SUN.dec_deg - SOLAR_EXCLUSION_DEG, sun=_SUN
        )
        assert blocked is False

    def test_just_inside_threshold_is_blocked(self) -> None:
        blocked, _ = is_solar_target(
            _SUN.ra_hours, _SUN.dec_deg - (SOLAR_EXCLUSION_DEG - 0.1), sun=_SUN
        )
        assert blocked is True

    def test_custom_threshold_respected(self) -> None:
        # 5° separation; threshold 3° → not blocked
        blocked, _ = is_solar_target(
            _SUN.ra_hours, _SUN.dec_deg - 5.0, threshold_deg=3.0, sun=_SUN
        )
        assert blocked is False

    def test_returns_separation(self) -> None:
        _, sep = is_solar_target(_SUN.ra_hours, _SUN.dec_deg - 20.0, sun=_SUN)
        assert sep == pytest.approx(20.0, abs=0.01)


class TestSunPositionNow:
    def test_returns_solar_position(self) -> None:
        pos = sun_position_now()
        assert isinstance(pos, SolarPosition)

    def test_ra_within_24_hours(self) -> None:
        pos = sun_position_now()
        assert 0.0 <= pos.ra_hours < 24.0

    def test_dec_within_ecliptic_limits(self) -> None:
        pos = sun_position_now()
        assert -23.5 <= pos.dec_deg <= 23.5
