"""Unit tests for domain/cooling.py (AGT-4-1)."""
from __future__ import annotations

import pytest

from smart_telescope.domain.cooling import (
    CoolingAction,
    CoolingConfig,
    CoolingController,
)


# ── Helpers ────────────────────────────────────────────────────────────────────

class FakeClock:
    """Deterministic monotonic clock for tests."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def advance(self, seconds: float) -> None:
        self._t += seconds

    def __call__(self) -> float:
        return self._t


def _ctrl(
    target_c: float = -10.0,
    stable_pct: float = 75.0,
    warn_pct: float = 80.0,
    timeout_s: float = 300.0,
    relax_step: float = 1.0,
    clock: FakeClock | None = None,
) -> tuple[CoolingController, FakeClock]:
    clk = clock or FakeClock()
    cfg = CoolingConfig(
        target_c=target_c,
        stable_power_limit_pct=stable_pct,
        warning_power_pct=warn_pct,
        stabilisation_timeout_s=timeout_s,
        relax_step_c=relax_step,
    )
    return CoolingController(cfg, clock=clk), clk


# ── CoolingConfig ──────────────────────────────────────────────────────────────

class TestCoolingConfig:
    def test_defaults(self) -> None:
        cfg = CoolingConfig()
        assert cfg.target_c == pytest.approx(-10.0)
        assert cfg.stable_power_limit_pct == pytest.approx(75.0)
        assert cfg.warning_power_pct == pytest.approx(80.0)
        assert cfg.stabilisation_timeout_s == pytest.approx(300.0)
        assert cfg.relax_step_c == pytest.approx(1.0)

    def test_target_below_minimum_clamped(self) -> None:
        cfg = CoolingConfig(target_c=-20.0)
        assert cfg.target_c == pytest.approx(-10.0)

    def test_target_at_minimum_accepted(self) -> None:
        cfg = CoolingConfig(target_c=-10.0)
        assert cfg.target_c == pytest.approx(-10.0)

    def test_target_above_minimum_accepted(self) -> None:
        cfg = CoolingConfig(target_c=0.0)
        assert cfg.target_c == pytest.approx(0.0)

    def test_custom_values_stored(self) -> None:
        cfg = CoolingConfig(target_c=-5.0, relax_step_c=2.0, stabilisation_timeout_s=120.0)
        assert cfg.target_c == pytest.approx(-5.0)
        assert cfg.relax_step_c == pytest.approx(2.0)
        assert cfg.stabilisation_timeout_s == pytest.approx(120.0)


# ── STABLE ─────────────────────────────────────────────────────────────────────

class TestStable:
    def test_at_target_with_low_power(self) -> None:
        ctrl, _ = _ctrl(target_c=-10.0)
        assert ctrl.tick(-10.0, 50.0) == CoolingAction.STABLE

    def test_within_tolerance_below_target(self) -> None:
        # temp is 0.9°C above target (within 1°C tolerance)
        ctrl, _ = _ctrl(target_c=-10.0)
        assert ctrl.tick(-9.1, 60.0) == CoolingAction.STABLE

    def test_within_tolerance_above_target(self) -> None:
        ctrl, _ = _ctrl(target_c=-10.0)
        assert ctrl.tick(-10.9, 55.0) == CoolingAction.STABLE

    def test_exactly_at_stable_power_limit(self) -> None:
        ctrl, _ = _ctrl(target_c=-10.0, stable_pct=75.0)
        assert ctrl.tick(-10.0, 75.0) == CoolingAction.STABLE

    def test_stable_takes_priority_over_warn_threshold(self) -> None:
        # near target + power exactly at stable limit (not above) → STABLE
        ctrl, _ = _ctrl(target_c=-10.0, stable_pct=75.0, warn_pct=80.0)
        assert ctrl.tick(-10.0, 75.0) == CoolingAction.STABLE


# ── HOLD ───────────────────────────────────────────────────────────────────────

class TestHold:
    def test_far_from_target_normal_power(self) -> None:
        ctrl, _ = _ctrl(target_c=-10.0)
        assert ctrl.tick(20.0, 60.0) == CoolingAction.HOLD

    def test_near_target_power_just_above_stable(self) -> None:
        # Power at 76% (above stable 75% but below warn 80%) → HOLD
        ctrl, _ = _ctrl(target_c=-10.0, stable_pct=75.0, warn_pct=80.0)
        assert ctrl.tick(-10.0, 76.0) == CoolingAction.HOLD

    def test_within_timeout_no_warn(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, stable_pct=75.0, warn_pct=80.0, timeout_s=300.0)
        clk.advance(100.0)  # within timeout
        # Power above stable but below warning — HOLD
        assert ctrl.tick(5.0, 77.0) == CoolingAction.HOLD


# ── WARN ───────────────────────────────────────────────────────────────────────

class TestWarn:
    def test_power_above_warning_far_from_target(self) -> None:
        ctrl, _ = _ctrl(target_c=-10.0, warn_pct=80.0)
        assert ctrl.tick(20.0, 85.0) == CoolingAction.WARN

    def test_power_exactly_at_warning_threshold(self) -> None:
        ctrl, _ = _ctrl(target_c=-10.0, warn_pct=80.0)
        assert ctrl.tick(0.0, 80.0) == CoolingAction.WARN

    def test_warn_before_timeout(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, stable_pct=75.0, warn_pct=80.0, timeout_s=300.0)
        clk.advance(200.0)  # within timeout
        assert ctrl.tick(5.0, 90.0) == CoolingAction.WARN

    def test_not_warn_when_near_target_and_power_stable(self) -> None:
        # Should be STABLE, not WARN, even if power is above warning if power <= stable
        ctrl, _ = _ctrl(target_c=-10.0, stable_pct=75.0, warn_pct=70.0)
        # stable_pct > warn_pct is unusual but tests priority: STABLE still wins
        assert ctrl.tick(-10.0, 60.0) == CoolingAction.STABLE


# ── RAISE_TARGET ───────────────────────────────────────────────────────────────

class TestRaiseTarget:
    def test_raises_target_after_timeout(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, stable_pct=75.0, timeout_s=300.0, relax_step=1.0)
        clk.advance(300.0)
        assert ctrl.tick(5.0, 90.0) == CoolingAction.RAISE_TARGET

    def test_target_increases_by_relax_step(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, relax_step=1.0, timeout_s=300.0)
        clk.advance(300.0)
        ctrl.tick(5.0, 90.0)
        assert ctrl.current_target_c == pytest.approx(-9.0)

    def test_multiple_relax_steps_accumulate(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, relax_step=1.0, timeout_s=300.0)
        for _ in range(3):
            clk.advance(300.0)
            ctrl.tick(5.0, 90.0)
        assert ctrl.current_target_c == pytest.approx(-7.0)

    def test_timer_resets_after_raise(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, stable_pct=75.0, timeout_s=300.0)
        clk.advance(300.0)
        ctrl.tick(5.0, 90.0)  # RAISE_TARGET, timer reset
        # Advance only 100s — should not raise again yet
        clk.advance(100.0)
        action = ctrl.tick(5.0, 90.0)
        assert action != CoolingAction.RAISE_TARGET

    def test_raise_target_not_triggered_before_timeout(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, stable_pct=75.0, timeout_s=300.0)
        clk.advance(299.9)
        action = ctrl.tick(5.0, 90.0)
        assert action != CoolingAction.RAISE_TARGET

    def test_raise_target_takes_priority_over_warn(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, warn_pct=80.0, stable_pct=75.0, timeout_s=300.0)
        clk.advance(300.0)
        # Power is above both warn and stable limits, timeout exceeded
        assert ctrl.tick(5.0, 95.0) == CoolingAction.RAISE_TARGET

    def test_custom_relax_step(self) -> None:
        ctrl, clk = _ctrl(target_c=-10.0, relax_step=2.0, timeout_s=60.0)
        clk.advance(60.0)
        ctrl.tick(5.0, 90.0)
        assert ctrl.current_target_c == pytest.approx(-8.0)

    def test_initial_target_unchanged_before_timeout(self) -> None:
        ctrl, _ = _ctrl(target_c=-10.0)
        ctrl.tick(20.0, 90.0)
        assert ctrl.current_target_c == pytest.approx(-10.0)


# ── Cooldown sequence ──────────────────────────────────────────────────────────

class TestCooldownSequence:
    def test_full_successful_sequence(self) -> None:
        """High power during pulldown → WARN → eventually STABLE."""
        ctrl, clk = _ctrl(target_c=-10.0, stable_pct=75.0, warn_pct=80.0, timeout_s=300.0)

        # t=0: cooling starts, high power — first tick starts timer
        assert ctrl.tick(25.0, 90.0) == CoolingAction.WARN

        # t=60s: still cooling, power high
        clk.advance(60.0)
        assert ctrl.tick(10.0, 85.0) == CoolingAction.WARN

        # t=120s: approaching target, power coming down but still warning
        clk.advance(60.0)
        assert ctrl.tick(-5.0, 82.0) == CoolingAction.WARN

        # t=180s: near target, power below stable limit — STABLE
        clk.advance(60.0)
        assert ctrl.tick(-9.5, 65.0) == CoolingAction.STABLE

    def test_sequence_ends_in_raise_when_tec_cannot_reach_target(self) -> None:
        """TEC can't cool to target → RAISE_TARGET after timeout."""
        ctrl, clk = _ctrl(target_c=-10.0, stable_pct=75.0, warn_pct=80.0, timeout_s=300.0)

        clk.advance(100.0)
        assert ctrl.tick(2.0, 95.0) == CoolingAction.WARN

        clk.advance(200.0)  # total 300s elapsed
        action = ctrl.tick(2.0, 95.0)
        assert action == CoolingAction.RAISE_TARGET
        assert ctrl.current_target_c == pytest.approx(-9.0)
