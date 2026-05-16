"""Tests for SectorMapper — Collimation Phase 10, COL-101."""
from __future__ import annotations

import math

import pytest

from smart_telescope.domain.bahtinov import SpikeLine
from smart_telescope.services.collimation.sector_mapper import SectorMapper


# ── Helpers ───────────────────────────────────────────────────────────────────

def _line(angle_deg: float, conf: float = 100.0) -> SpikeLine:
    theta = math.radians(angle_deg)
    return SpikeLine(a=math.cos(theta), b=math.sin(theta), c=0.0,
                     angle_deg=angle_deg, confidence=conf)


def _three_lines() -> list[SpikeLine]:
    return [_line(30.0), _line(90.0), _line(150.0)]


def _mapper() -> SectorMapper:
    return SectorMapper({"A": "T1", "B": "T2", "C": "T3"})


# ── observe() ────────────────────────────────────────────────────────────────

class TestObserve:
    def test_returns_angle_of_missing_line(self):
        m = _mapper()
        open_lines = _three_lines()
        closed_lines = [_line(90.0), _line(150.0)]  # 30° line gone
        angle = m.observe("A", open_lines, closed_lines)
        assert angle == pytest.approx(30.0)

    def test_stores_observation(self):
        m = _mapper()
        m.observe("A", _three_lines(), [_line(90.0), _line(150.0)])
        assert "A" in m.observed_sectors

    def test_returns_none_when_no_open_lines_missing(self):
        # closed_lines has same count as open_lines → no missing line
        m = _mapper()
        result = m.observe("A", _three_lines(), _three_lines())
        assert result is None

    def test_returns_none_when_open_lines_fewer_than_3(self):
        m = _mapper()
        result = m.observe("A", [_line(30.0), _line(90.0)], [_line(30.0)])
        assert result is None

    def test_angle_within_tolerance_counts_as_match(self):
        # 91° is within 10° of 90° → treated as the same line (90° not missing)
        # So only 30° is genuinely missing
        m = _mapper()
        open_lines = _three_lines()
        closed_with_shift = [_line(91.0), _line(150.0)]
        angle = m.observe("A", open_lines, closed_with_shift)
        assert angle == pytest.approx(30.0)

    def test_second_sector_observation_stored(self):
        m = _mapper()
        m.observe("A", _three_lines(), [_line(90.0), _line(150.0)])
        m.observe("B", _three_lines(), [_line(30.0), _line(150.0)])
        assert m.observed_sectors == {"A", "B"}


# ── build_calibration() ───────────────────────────────────────────────────────

class TestBuildCalibration:
    def _full_observe(self, m: SectorMapper) -> None:
        m.observe("A", _three_lines(), [_line(90.0), _line(150.0)])   # 30° gone → T1
        m.observe("B", _three_lines(), [_line(30.0), _line(150.0)])   # 90° gone → T2
        m.observe("C", _three_lines(), [_line(30.0), _line(90.0)])    # 150° gone → T3

    def test_returns_calibration_after_all_sectors(self):
        m = _mapper()
        self._full_observe(m)
        cal = m.build_calibration(calibrated_at="2026-01-01T00:00:00+00:00")
        assert cal is not None

    def test_calibrated_at_stored(self):
        m = _mapper()
        self._full_observe(m)
        cal = m.build_calibration(calibrated_at="2026-01-01T00:00:00+00:00")
        assert cal.calibrated_at == "2026-01-01T00:00:00+00:00"

    def test_screws_assigned_by_angle_order(self):
        # 30° < 90° < 150° → sector_0=T1, sector_120=T2, sector_240=T3
        m = _mapper()
        self._full_observe(m)
        cal = m.build_calibration(calibrated_at="t")
        assert cal.sector_0_deg == "T1"
        assert cal.sector_120_deg == "T2"
        assert cal.sector_240_deg == "T3"

    def test_returns_none_when_missing_sector(self):
        m = _mapper()
        m.observe("A", _three_lines(), [_line(90.0), _line(150.0)])
        m.observe("B", _three_lines(), [_line(30.0), _line(150.0)])
        # "C" never observed
        assert m.build_calibration() is None

    def test_returns_none_when_no_observations(self):
        m = _mapper()
        assert m.build_calibration() is None

    def test_calibrated_at_defaults_to_now_when_not_provided(self):
        m = _mapper()
        self._full_observe(m)
        cal = m.build_calibration()
        assert cal is not None
        assert cal.calibrated_at != ""


# ── Ambiguous / degenerate cases ─────────────────────────────────────────────

class TestAmbiguous:
    def test_returns_none_when_two_sectors_same_angle(self):
        m = _mapper()
        # Two sectors both map to ~30°
        m.observe("A", _three_lines(), [_line(90.0), _line(150.0)])   # 30° → T1
        m.observe("B", _three_lines(), [_line(91.0), _line(150.0)])   # 29° ≈ 30° → T2
        m.observe("C", _three_lines(), [_line(30.0), _line(90.0)])    # 150° → T3
        # A=30°, B=29° (same after 180% mod) → ambiguous
        cal = m.build_calibration(calibrated_at="t")
        assert cal is None
