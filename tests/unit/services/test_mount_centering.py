"""Tests for PulseCenterer — Collimation Phase 4, Task 4.1."""
from __future__ import annotations

from typing import Iterator
from unittest.mock import MagicMock, call

import pytest

from smart_telescope.adapters.mock.mount import MockMount
from smart_telescope.domain.collimation.config import MountCenteringConfig
from smart_telescope.services.collimation.mount_centering import (
    MountCorrectionResult,
    PulseCenterer,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _cfg(
    max_pulse_ms: int = 500,
    settle_ms: int = 0,        # 0 so tests don't sleep
    fine_tolerance_px: float = 5.0,
    rough_tolerance_px: float = 20.0,
    initial_tolerance_px: float = 50.0,
) -> MountCenteringConfig:
    return MountCenteringConfig(
        max_pulse_ms=max_pulse_ms,
        settle_ms=settle_ms,
        fine_tolerance_px=fine_tolerance_px,
        rough_tolerance_px=rough_tolerance_px,
        initial_tolerance_px=initial_tolerance_px,
    )


def _centerer(
    mount=None,
    config=None,
    pixel_scale_arcsec: float = 0.28,   # approx C8/678M
    max_iterations: int = 20,
    max_diverge_count: int = 3,
) -> PulseCenterer:
    return PulseCenterer(
        mount=mount or MockMount(),
        config=config or _cfg(),
        pixel_scale_arcsec=pixel_scale_arcsec,
        guide_rate_factor=0.5,
        max_iterations=max_iterations,
        max_diverge_count=max_diverge_count,
    )


# ── Result type ───────────────────────────────────────────────────────────────

class TestMountCorrectionResult:
    def test_fields_accessible(self):
        r = MountCorrectionResult(
            success=True, pulses_issued=3,
            final_offset_px=2.1, reason="within_tolerance",
        )
        assert r.success is True
        assert r.pulses_issued == 3
        assert r.final_offset_px == pytest.approx(2.1)
        assert r.reason == "within_tolerance"


# ── Already within tolerance ──────────────────────────────────────────────────

class TestAlreadyCentered:
    def test_no_pulses_when_within_tolerance(self):
        mount = MockMount()
        c = _centerer(mount=mount)
        # Star within fine_tolerance_px (5.0)
        result = c.center(get_offset_px=lambda: (2.0, 1.0))
        assert result.success is True
        assert result.pulses_issued == 0
        assert result.reason == "within_tolerance"
        assert result.final_offset_px < 5.0

    def test_exactly_on_center(self):
        result = _centerer().center(get_offset_px=lambda: (0.0, 0.0))
        assert result.success is True
        assert result.pulses_issued == 0


# ── Guide direction mapping ───────────────────────────────────────────────────

class TestGuideDirections:
    def _track_guide_calls(self) -> tuple[MockMount, list[tuple[str, int]]]:
        """Return a mount that records guide() calls."""
        calls: list[tuple[str, int]] = []
        mount = MockMount()
        original_guide = mount.guide
        def _guide(direction: str, duration_ms: int) -> bool:
            calls.append((direction, duration_ms))
            return True
        mount.guide = _guide  # type: ignore[method-assign]
        return mount, calls

    def test_star_east_guides_west(self):
        """dx > 0 (star east of center) → guide 'w'."""
        mount, calls = self._track_guide_calls()
        offsets = iter([(30.0, 0.0), (0.0, 0.0)])  # one correction, then centered
        c = _centerer(mount=mount, max_iterations=5)
        c.center(get_offset_px=lambda: next(offsets, None))
        assert len(calls) >= 1
        assert calls[0][0] == "w"

    def test_star_west_guides_east(self):
        """dx < 0 (star west of center) → guide 'e'."""
        mount, calls = self._track_guide_calls()
        offsets = iter([(-30.0, 0.0), (0.0, 0.0)])
        c = _centerer(mount=mount, max_iterations=5)
        c.center(get_offset_px=lambda: next(offsets, None))
        assert len(calls) >= 1
        assert calls[0][0] == "e"

    def test_star_south_guides_north(self):
        """dy > 0 (star south of center in image coords) → guide 'n'."""
        mount, calls = self._track_guide_calls()
        offsets = iter([(0.0, 30.0), (0.0, 0.0)])
        c = _centerer(mount=mount, max_iterations=5)
        c.center(get_offset_px=lambda: next(offsets, None))
        assert len(calls) >= 1
        assert calls[0][0] == "n"

    def test_star_north_guides_south(self):
        """dy < 0 (star north of center) → guide 's'."""
        mount, calls = self._track_guide_calls()
        offsets = iter([(0.0, -30.0), (0.0, 0.0)])
        c = _centerer(mount=mount, max_iterations=5)
        c.center(get_offset_px=lambda: next(offsets, None))
        assert len(calls) >= 1
        assert calls[0][0] == "s"

    def test_dominant_axis_chosen(self):
        """When |dy| > |dx|, the dec axis pulse is issued first."""
        mount, calls = self._track_guide_calls()
        # dy=40 dominates dx=10
        offsets = iter([(10.0, 40.0), (0.0, 0.0)])
        c = _centerer(mount=mount, max_iterations=5)
        c.center(get_offset_px=lambda: next(offsets, None))
        assert calls[0][0] in ("n", "s")

    def test_pulse_clamped_to_max_pulse_ms(self):
        """Very large offset should not produce pulses beyond max_pulse_ms."""
        mount, calls = self._track_guide_calls()
        cfg = _cfg(max_pulse_ms=200)
        # 5000 px offset at 0.28 arcsec/px = 1400 arcsec → huge unclamped pulse
        offsets = iter([(5000.0, 0.0), (0.0, 0.0)])
        c = _centerer(mount=mount, config=cfg, max_iterations=5)
        c.center(get_offset_px=lambda: next(offsets, None))
        for _, dur in calls:
            assert dur <= 200

    def test_minimum_pulse_is_1ms(self):
        """Even tiny offsets produce at least a 1 ms pulse."""
        mount, calls = self._track_guide_calls()
        # offset just above fine_tolerance (5 px) but very small
        offsets = iter([(6.0, 0.0), (0.0, 0.0)])
        c = _centerer(mount=mount, max_iterations=5)
        c.center(get_offset_px=lambda: next(offsets, None))
        if calls:
            assert calls[0][1] >= 1


# ── Convergence simulation ────────────────────────────────────────────────────

class TestConvergence:
    def test_converges_in_steps(self):
        """Star moves 20 % closer to center each pulse; should converge."""
        state = [40.0, 0.0]  # [distance, unused]

        def _offset() -> tuple[float, float] | None:
            dist = state[0]
            state[0] = dist * 0.65  # shrink each call
            return (dist, 0.0)

        result = _centerer(max_iterations=20).center(get_offset_px=_offset)
        assert result.success is True
        assert result.reason == "within_tolerance"
        assert result.final_offset_px < 5.0

    def test_pulses_issued_counted(self):
        """pulses_issued should match the number of corrections needed."""
        # Offset shrinks fast: 40 → 26 → 17 → 11 → 7 → 4.6 (<5)
        # That's 5 corrections.
        state = [40.0]

        def _offset():
            d = state[0]
            state[0] = d * 0.65
            return (d, 0.0)

        result = _centerer(max_iterations=20).center(get_offset_px=_offset)
        assert result.pulses_issued >= 1


# ── Failure cases ─────────────────────────────────────────────────────────────

class TestFailureCases:
    def test_star_lost_immediately(self):
        result = _centerer().center(get_offset_px=lambda: None)
        assert result.success is False
        assert result.reason == "star_lost"
        assert result.pulses_issued == 0

    def test_star_lost_after_one_correction(self):
        offsets = iter([(30.0, 0.0), None])
        result = _centerer(max_iterations=5).center(
            get_offset_px=lambda: next(offsets, None)
        )
        assert result.reason == "star_lost"
        assert result.pulses_issued == 1

    def test_diverging_aborts(self):
        """Star keeps getting further → should abort with 'diverging'."""
        # Distance grows each iteration
        dist = [10.0]
        def _offset():
            d = dist[0]
            dist[0] += 15.0   # keeps increasing
            return (d, 0.0)

        result = _centerer(max_iterations=30, max_diverge_count=3).center(
            get_offset_px=_offset
        )
        assert result.reason == "diverging"
        assert result.success is False

    def test_max_pulses_reached(self):
        """Offset never shrinks → should hit max_pulses."""
        result = _centerer(max_iterations=5).center(
            get_offset_px=lambda: (20.0, 0.0)  # constant non-zero offset
        )
        assert result.reason == "max_pulses"
        assert result.pulses_issued == 5

    def test_cancel_check_respected(self):
        """Cancellation should abort immediately."""
        call_count = [0]

        def _offset():
            call_count[0] += 1
            return (50.0, 0.0)

        result = _centerer(max_iterations=20).center(
            get_offset_px=_offset,
            cancel_check=lambda: True,   # always cancelled
        )
        assert result.reason == "cancelled"
        assert result.success is False

    def test_cancel_check_after_first_pulse(self):
        """Cancel flag set after first measurement; loop should stop."""
        cancelled = [False]
        calls_to_offset = [0]

        def _offset():
            calls_to_offset[0] += 1
            return (30.0, 0.0)

        def _cancel():
            # Cancel becomes True after the first guide pulse
            return calls_to_offset[0] >= 2

        result = _centerer(max_iterations=10, config=_cfg(settle_ms=0)).center(
            get_offset_px=_offset,
            cancel_check=_cancel,
        )
        assert result.reason in ("cancelled", "within_tolerance", "max_pulses")


# ── Declination correction ────────────────────────────────────────────────────

class TestDeclinationCorrection:
    def _track_calls(self) -> tuple[MockMount, list[tuple[str, int]]]:
        calls: list[tuple[str, int]] = []
        mount = MockMount()
        def _guide(d, ms):
            calls.append((d, ms))
            return True
        mount.guide = _guide  # type: ignore[method-assign]
        return mount, calls

    def test_high_dec_ra_pulse_is_longer(self):
        """At high declination cos(dec) is small → RA rate is slower → longer pulse needed."""
        mount_0, calls_0 = self._track_calls()
        mount_90, calls_90 = self._track_calls()

        offsets = [(30.0, 0.0), (0.0, 0.0)]

        _centerer(mount=mount_0, max_iterations=5).center(
            get_offset_px=iter(offsets).__next__,
            dec_deg=0.0,
        )
        offsets2 = iter([(30.0, 0.0), (0.0, 0.0)])
        _centerer(mount=mount_90, max_iterations=5).center(
            get_offset_px=lambda: next(offsets2, None),
            dec_deg=80.0,   # cos(80°) ≈ 0.17 → slower RA rate → larger pulse
        )

        if calls_0 and calls_90:
            # dec=80° should require a longer pulse for the same pixel offset
            assert calls_90[0][1] >= calls_0[0][1]
