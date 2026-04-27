"""Unit tests for domain/visibility — altitude/azimuth and observable check."""

import pytest
from astropy.time import Time

from smart_telescope.domain.visibility import compute_altaz, is_observable

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
