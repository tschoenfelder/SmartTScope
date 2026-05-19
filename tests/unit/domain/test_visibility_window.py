"""Unit tests for compute_visibility_window."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import call, patch

import pytest

from smart_telescope.domain.visibility import VisibilityWindow, compute_visibility_window

# Fixed test night: 2026-04-30 21:00 UTC → 2026-05-01 03:00 UTC (6 hours)
_NIGHT_START = datetime(2026, 4, 30, 21, 0, 0, tzinfo=UTC)
_NIGHT_END   = datetime(2026, 5, 1,  3, 0, 0, tzinfo=UTC)
_LAT, _LON   = 50.336, 8.533
_RA,  _DEC   = 5.588, -5.391   # M42


def _window(altitudes: list[float], sample_minutes: int = 60) -> VisibilityWindow:
    """Run compute_visibility_window with mocked compute_altaz returning *altitudes* in order."""
    side_effects = [(alt, 180.0) for alt in altitudes]
    with patch("smart_telescope.domain.visibility.compute_altaz", side_effect=side_effects):
        return compute_visibility_window(
            _RA, _DEC, _LAT, _LON,
            night_start=_NIGHT_START,
            night_end=_NIGHT_END,
            min_altitude_deg=20.0,
            sample_minutes=sample_minutes,
        )


# ── VisibilityWindow dataclass ────────────────────────────────────────────────


class TestVisibilityWindowDataclass:
    def test_frozen(self) -> None:
        w = VisibilityWindow(rises_at=None, sets_at=None, peak_altitude=10.0, peak_time=None, is_observable=False)
        with pytest.raises((AttributeError, TypeError)):
            w.peak_altitude = 99.0  # type: ignore[misc]


# ── Never observable ──────────────────────────────────────────────────────────


class TestNeverObservable:
    def test_is_observable_false(self) -> None:
        # 7 samples (0,60,120,180,240,300,360 min), all below 20°
        alts = [5.0, 8.0, 10.0, 12.0, 10.0, 8.0, 5.0]
        w = _window(alts)
        assert w.is_observable is False

    def test_rises_at_none(self) -> None:
        w = _window([5.0, 8.0, 10.0, 12.0, 10.0, 8.0, 5.0])
        assert w.rises_at is None

    def test_sets_at_none(self) -> None:
        w = _window([5.0, 8.0, 10.0, 12.0, 10.0, 8.0, 5.0])
        assert w.sets_at is None

    def test_peak_altitude_correct(self) -> None:
        alts = [5.0, 8.0, 10.0, 12.0, 10.0, 8.0, 5.0]
        w = _window(alts)
        assert w.peak_altitude == 12.0

    def test_peak_time_at_midpoint(self) -> None:
        alts = [5.0, 8.0, 10.0, 12.0, 10.0, 8.0, 5.0]
        w = _window(alts)
        assert w.peak_time == _NIGHT_START + timedelta(hours=3)


# ── Always observable ─────────────────────────────────────────────────────────


class TestAlwaysObservable:
    def test_is_observable_true(self) -> None:
        alts = [25.0, 30.0, 45.0, 50.0, 45.0, 30.0, 25.0]
        w = _window(alts)
        assert w.is_observable is True

    def test_rises_at_night_start(self) -> None:
        alts = [25.0, 30.0, 45.0, 50.0, 45.0, 30.0, 25.0]
        w = _window(alts)
        assert w.rises_at == _NIGHT_START

    def test_sets_at_night_end(self) -> None:
        alts = [25.0, 30.0, 45.0, 50.0, 45.0, 30.0, 25.0]
        w = _window(alts)
        assert w.sets_at == _NIGHT_END

    def test_peak_altitude_and_time(self) -> None:
        alts = [25.0, 30.0, 45.0, 50.0, 45.0, 30.0, 25.0]
        w = _window(alts)
        assert w.peak_altitude == 50.0
        assert w.peak_time == _NIGHT_START + timedelta(hours=3)


# ── Rises during night ────────────────────────────────────────────────────────


class TestRisesDuringNight:
    def test_is_observable_true(self) -> None:
        alts = [5.0, 10.0, 25.0, 40.0, 35.0, 25.0, 20.0]
        w = _window(alts)
        assert w.is_observable is True

    def test_rises_at_is_first_above_threshold(self) -> None:
        alts = [5.0, 10.0, 25.0, 40.0, 35.0, 25.0, 20.0]
        w = _window(alts)
        assert w.rises_at == _NIGHT_START + timedelta(hours=2)

    def test_sets_at_is_last_above_threshold(self) -> None:
        alts = [5.0, 10.0, 25.0, 40.0, 35.0, 25.0, 20.0]
        w = _window(alts)
        assert w.sets_at == _NIGHT_END


# ── Sets during night ─────────────────────────────────────────────────────────


class TestSetsDuringNight:
    def test_sets_at_is_last_above_threshold(self) -> None:
        alts = [40.0, 35.0, 25.0, 20.0, 10.0, 5.0, 2.0]
        w = _window(alts)
        assert w.is_observable is True
        assert w.rises_at == _NIGHT_START
        assert w.sets_at == _NIGHT_START + timedelta(hours=3)


# ── Sample count ──────────────────────────────────────────────────────────────


class TestSamplingBehaviour:
    def test_correct_number_of_compute_altaz_calls(self) -> None:
        # 6-hour window, 60-min samples → 7 times: 21,22,23,00,01,02,03
        alts = [25.0] * 7
        with patch("smart_telescope.domain.visibility.compute_altaz",
                   side_effect=[(a, 0.0) for a in alts]) as mock_fn:
            compute_visibility_window(
                _RA, _DEC, _LAT, _LON,
                night_start=_NIGHT_START, night_end=_NIGHT_END,
                min_altitude_deg=20.0, sample_minutes=60,
            )
        assert mock_fn.call_count == 7
