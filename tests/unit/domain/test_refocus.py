"""Unit tests for the RefocusTracker domain object."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from smart_telescope.domain.refocus import RefocusConfig, RefocusTracker, RefocusTriggerResult


# ── helpers ───────────────────────────────────────────────────────────────────

def _tracker(
    temp_delta_c: float = 1.0,
    altitude_delta_deg: float = 5.0,
    elapsed_min: float = 30.0,
) -> RefocusTracker:
    return RefocusTracker(RefocusConfig(temp_delta_c, altitude_delta_deg, elapsed_min))


# ── RefocusConfig ─────────────────────────────────────────────────────────────

class TestRefocusConfig:
    def test_defaults(self) -> None:
        cfg = RefocusConfig()
        assert cfg.temp_delta_c == 1.0
        assert cfg.altitude_delta_deg == 5.0
        assert cfg.elapsed_min == 30.0

    def test_custom_values(self) -> None:
        cfg = RefocusConfig(temp_delta_c=2.0, altitude_delta_deg=3.0, elapsed_min=15.0)
        assert cfg.temp_delta_c == 2.0


# ── RefocusTracker — no baseline ──────────────────────────────────────────────

class TestNoBaseline:
    def test_check_before_record_returns_no_refocus(self) -> None:
        t = _tracker()
        result = t.check(altitude=45.0)
        assert result.should_refocus is False
        assert result.reason is None

    def test_check_with_temp_before_record_returns_no_refocus(self) -> None:
        t = _tracker()
        result = t.check(altitude=45.0, temperature=15.0)
        assert result.should_refocus is False


# ── Elapsed trigger ───────────────────────────────────────────────────────────

class TestElapsedTrigger:
    def test_no_trigger_within_interval(self) -> None:
        t = _tracker(elapsed_min=30.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base
            t.record_focus(altitude=45.0)
            mock_dt.now.return_value = base + timedelta(minutes=29)
            result = t.check(altitude=45.0)
        assert result.should_refocus is False

    def test_triggers_at_exact_interval(self) -> None:
        t = _tracker(elapsed_min=30.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base
            t.record_focus(altitude=45.0)
            mock_dt.now.return_value = base + timedelta(minutes=30)
            result = t.check(altitude=45.0)
        assert result.should_refocus is True
        assert result.reason == "elapsed"

    def test_triggers_well_past_interval(self) -> None:
        t = _tracker(elapsed_min=30.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base
            t.record_focus(altitude=45.0)
            mock_dt.now.return_value = base + timedelta(hours=2)
            result = t.check(altitude=45.0)
        assert result.should_refocus is True
        assert result.reason == "elapsed"


# ── Altitude trigger ──────────────────────────────────────────────────────────

class TestAltitudeTrigger:
    def _fresh_tracker_with_baseline(self, alt_at_focus: float) -> RefocusTracker:
        t = _tracker(altitude_delta_deg=5.0, elapsed_min=9999.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base
            t.record_focus(altitude=alt_at_focus)
        return t

    def test_no_trigger_within_threshold(self) -> None:
        t = self._fresh_tracker_with_baseline(alt_at_focus=50.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base + timedelta(minutes=1)
            result = t.check(altitude=54.9)
        assert result.should_refocus is False

    def test_triggers_at_threshold(self) -> None:
        t = self._fresh_tracker_with_baseline(alt_at_focus=50.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base + timedelta(minutes=1)
            result = t.check(altitude=55.0)
        assert result.should_refocus is True
        assert result.reason == "altitude"

    def test_triggers_on_descent(self) -> None:
        t = self._fresh_tracker_with_baseline(alt_at_focus=50.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base + timedelta(minutes=1)
            result = t.check(altitude=44.0)
        assert result.should_refocus is True
        assert result.reason == "altitude"


# ── Temperature trigger ───────────────────────────────────────────────────────

class TestTemperatureTrigger:
    def _fresh_tracker_with_baseline(self, temp_at_focus: float) -> RefocusTracker:
        t = _tracker(temp_delta_c=1.0, altitude_delta_deg=9999.0, elapsed_min=9999.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base
            t.record_focus(altitude=45.0, temperature=temp_at_focus)
        return t

    def test_no_trigger_within_threshold(self) -> None:
        t = self._fresh_tracker_with_baseline(temp_at_focus=10.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base + timedelta(minutes=1)
            result = t.check(altitude=45.0, temperature=10.9)
        assert result.should_refocus is False

    def test_triggers_at_threshold(self) -> None:
        t = self._fresh_tracker_with_baseline(temp_at_focus=10.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base + timedelta(minutes=1)
            result = t.check(altitude=45.0, temperature=11.0)
        assert result.should_refocus is True
        assert result.reason == "temperature"

    def test_no_trigger_when_temp_is_none(self) -> None:
        t = self._fresh_tracker_with_baseline(temp_at_focus=10.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base + timedelta(minutes=1)
            result = t.check(altitude=45.0, temperature=None)
        assert result.should_refocus is False

    def test_no_trigger_when_baseline_temp_is_none(self) -> None:
        t = _tracker(temp_delta_c=1.0, altitude_delta_deg=9999.0, elapsed_min=9999.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base
            t.record_focus(altitude=45.0, temperature=None)
            mock_dt.now.return_value = base + timedelta(minutes=1)
            result = t.check(altitude=45.0, temperature=15.0)
        assert result.should_refocus is False


# ── Priority order ────────────────────────────────────────────────────────────

class TestTriggerPriority:
    def test_elapsed_wins_over_altitude(self) -> None:
        """elapsed check runs first; altitude is not evaluated once elapsed fires."""
        t = _tracker(elapsed_min=1.0, altitude_delta_deg=5.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base
            t.record_focus(altitude=45.0)
            mock_dt.now.return_value = base + timedelta(minutes=2)
            result = t.check(altitude=55.0)  # both elapsed AND altitude would fire
        assert result.reason == "elapsed"

    def test_record_focus_resets_all_triggers(self) -> None:
        t = _tracker(elapsed_min=1.0)
        base = datetime(2026, 4, 30, 22, 0, 0, tzinfo=UTC)
        with patch("smart_telescope.domain.refocus.datetime") as mock_dt:
            mock_dt.now.return_value = base
            t.record_focus(altitude=45.0)
            mock_dt.now.return_value = base + timedelta(minutes=2)
            assert t.check(altitude=45.0).should_refocus is True
            # Re-record focus resets the baseline
            t.record_focus(altitude=45.0)
            result = t.check(altitude=45.0)
        assert result.should_refocus is False
