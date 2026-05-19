"""Tests for CollimationFocuserControl — Collimation Phase 4, Task 4.2."""
from __future__ import annotations

import pytest

from smart_telescope.adapters.mock.focuser import MockFocuser
from smart_telescope.domain.collimation.config import (
    FocuserCollimationConfig,
    FocuserDirection,
)
from smart_telescope.services.collimation.focuser_control import (
    CollimationFocuserControl,
    FocuserMoveResult,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _cfg(
    increasing_value_direction: FocuserDirection = FocuserDirection.CLOCKWISE,
    final_approach_direction: FocuserDirection = FocuserDirection.CLOCKWISE,
    defocus_direction: FocuserDirection = FocuserDirection.CLOCKWISE,
    max_single_step: int = 500,
    fine_step: int = 25,
    coarse_step: int = 250,
    min_position: int = 0,
    max_position: int = 50000,
) -> FocuserCollimationConfig:
    return FocuserCollimationConfig(
        min_position=min_position,
        max_position=max_position,
        increasing_value_direction=increasing_value_direction,
        final_approach_direction=final_approach_direction,
        defocus_direction=defocus_direction,
        max_single_step=max_single_step,
        fine_step=fine_step,
        coarse_step=coarse_step,
    )


def _available_focuser(start_pos: int = 1000) -> MockFocuser:
    f = MockFocuser(available=True)
    f._position = start_pos
    return f


def _ctrl(
    focuser: MockFocuser | None = None,
    config: FocuserCollimationConfig | None = None,
) -> CollimationFocuserControl:
    return CollimationFocuserControl(
        focuser=focuser or _available_focuser(),
        config=config or _cfg(),
    )


# ── FocuserMoveResult ─────────────────────────────────────────────────────────

class TestFocuserMoveResult:
    def test_fields(self):
        r = FocuserMoveResult(
            steps_requested=100, steps_taken=100,
            position_before=1000, position_after=1100,
            clipped=False, reason="ok",
        )
        assert r.steps_requested == 100
        assert r.steps_taken == 100
        assert r.position_before == 1000
        assert r.position_after == 1100
        assert r.clipped is False
        assert r.reason == "ok"


# ── Unavailable focuser ────────────────────────────────────────────────────────

class TestUnavailableFocuser:
    def test_unavailable_returns_reason(self):
        f = MockFocuser(available=False)
        c = CollimationFocuserControl(focuser=f, config=_cfg())
        r = c.move_focus_relative(100)
        assert r.reason == "unavailable"
        assert r.steps_taken == 0

    def test_unavailable_clipped_true_when_nonzero(self):
        c = CollimationFocuserControl(focuser=MockFocuser(available=False), config=_cfg())
        r = c.move_focus_relative(50)
        assert r.clipped is True

    def test_unavailable_clipped_false_when_zero(self):
        c = CollimationFocuserControl(focuser=MockFocuser(available=False), config=_cfg())
        r = c.move_focus_relative(0)
        assert r.clipped is False


# ── move_focus_relative ────────────────────────────────────────────────────────

class TestMoveFocusRelative:
    def test_positive_steps_increase_position(self):
        f = _available_focuser(start_pos=1000)
        c = _ctrl(focuser=f)
        r = c.move_focus_relative(200)
        assert r.steps_taken == 200
        assert r.reason == "ok"
        assert r.clipped is False
        assert r.position_after == 1200   # MockFocuser.move sets position

    def test_negative_steps(self):
        f = _available_focuser(start_pos=2000)
        c = _ctrl(focuser=f)
        r = c.move_focus_relative(-150)
        assert r.steps_taken == -150
        assert r.position_before == 2000
        assert r.position_after == 1850

    def test_zero_steps_returns_ok(self):
        c = _ctrl()
        r = c.move_focus_relative(0)
        assert r.steps_taken == 0
        assert r.reason == "ok"
        assert r.clipped is False

    def test_records_position_before_and_after(self):
        f = _available_focuser(start_pos=5000)
        c = _ctrl(focuser=f)
        r = c.move_focus_relative(300)
        assert r.position_before == 5000
        assert r.position_after == 5300


# ── max_single_step clamp ─────────────────────────────────────────────────────

class TestMaxSingleStepClamp:
    def test_positive_step_clamped(self):
        cfg = _cfg(max_single_step=100)
        c = _ctrl(config=cfg)
        r = c.move_focus_relative(999)
        assert r.steps_taken == 100
        assert r.clipped is True

    def test_negative_step_clamped(self):
        cfg = _cfg(max_single_step=100)
        c = _ctrl(config=cfg)
        r = c.move_focus_relative(-999)
        assert r.steps_taken == -100
        assert r.clipped is True

    def test_within_limit_not_clamped(self):
        cfg = _cfg(max_single_step=500)
        c = _ctrl(config=cfg)
        r = c.move_focus_relative(300)
        assert r.steps_taken == 300
        assert r.clipped is False


# ── Soft position limits ───────────────────────────────────────────────────────

class TestSoftPositionLimits:
    def test_cannot_go_below_min(self):
        f = _available_focuser(start_pos=100)
        cfg = _cfg(min_position=0, max_position=50000, max_single_step=500)
        c = CollimationFocuserControl(focuser=f, config=cfg)
        r = c.move_focus_relative(-500)   # would go to -400
        assert r.steps_taken == -100      # clipped to reach 0
        assert r.clipped is True
        assert r.reason == "soft_limit"

    def test_cannot_go_above_max(self):
        f = _available_focuser(start_pos=49800)
        cfg = _cfg(min_position=0, max_position=50000, max_single_step=500)
        c = CollimationFocuserControl(focuser=f, config=cfg)
        r = c.move_focus_relative(500)   # would go to 50300
        assert r.steps_taken == 200      # clipped to reach 50000
        assert r.clipped is True

    def test_already_at_max_no_move(self):
        f = _available_focuser(start_pos=50000)
        cfg = _cfg(min_position=0, max_position=50000, max_single_step=500)
        c = CollimationFocuserControl(focuser=f, config=cfg)
        r = c.move_focus_relative(100)
        assert r.steps_taken == 0
        assert r.reason == "soft_limit"

    def test_already_at_min_no_move(self):
        f = _available_focuser(start_pos=0)
        cfg = _cfg(min_position=0, max_position=50000, max_single_step=500)
        c = CollimationFocuserControl(focuser=f, config=cfg)
        r = c.move_focus_relative(-100)
        assert r.steps_taken == 0
        assert r.reason == "soft_limit"


# ── Physical direction mapping ─────────────────────────────────────────────────

class TestDirectionMapping:
    """Test that CW/CCW physical directions map correctly given the config."""

    def test_cw_positive_when_increasing_is_cw(self):
        cfg = _cfg(increasing_value_direction=FocuserDirection.CLOCKWISE)
        c = _ctrl(config=cfg)
        r = c.move_focus_clockwise(100)
        assert r.steps_taken == 100  # positive = increasing = CW

    def test_cw_negative_when_increasing_is_ccw(self):
        cfg = _cfg(increasing_value_direction=FocuserDirection.COUNTER_CLOCKWISE)
        c = _ctrl(config=cfg)
        r = c.move_focus_clockwise(100)
        assert r.steps_taken == -100  # CW = decreasing when CCW is increasing

    def test_ccw_negative_when_increasing_is_cw(self):
        cfg = _cfg(increasing_value_direction=FocuserDirection.CLOCKWISE)
        c = _ctrl(config=cfg)
        r = c.move_focus_counterclockwise(100)
        assert r.steps_taken == -100

    def test_ccw_positive_when_increasing_is_ccw(self):
        cfg = _cfg(increasing_value_direction=FocuserDirection.COUNTER_CLOCKWISE)
        c = _ctrl(config=cfg)
        r = c.move_focus_counterclockwise(100)
        assert r.steps_taken == 100

    def test_cw_and_ccw_are_opposite(self):
        """The steps taken for CW and CCW of the same magnitude should sum to 0."""
        cfg = _cfg(increasing_value_direction=FocuserDirection.CLOCKWISE)
        c = _ctrl(config=cfg)
        r_cw = c.move_focus_clockwise(200)
        r_ccw = c.move_focus_counterclockwise(200)
        assert r_cw.steps_taken + r_ccw.steps_taken == 0


# ── Defocus and fine focus ────────────────────────────────────────────────────

class TestDefocusAndFineFocus:
    def test_defocus_uses_coarse_step_by_default(self):
        cfg = _cfg(
            defocus_direction=FocuserDirection.CLOCKWISE,
            increasing_value_direction=FocuserDirection.CLOCKWISE,
            coarse_step=250,
        )
        c = _ctrl(config=cfg)
        r = c.defocus()
        assert r.steps_taken == 250

    def test_defocus_custom_steps(self):
        c = _ctrl()
        r = c.defocus(steps=100)
        assert abs(r.steps_taken) == 100

    def test_defocus_direction_is_configurable(self):
        """When defocus_direction = CCW and increasing = CW, defocus should be negative."""
        cfg = _cfg(
            defocus_direction=FocuserDirection.COUNTER_CLOCKWISE,
            increasing_value_direction=FocuserDirection.CLOCKWISE,
            coarse_step=250,
        )
        c = _ctrl(config=cfg)
        r = c.defocus()
        assert r.steps_taken == -250   # CCW → negative

    def test_focus_fine_uses_fine_step_by_default(self):
        cfg = _cfg(fine_step=25)
        c = _ctrl(config=cfg)
        r = c.focus_fine()
        assert abs(r.steps_taken) == 25

    def test_focus_fine_custom_steps(self):
        c = _ctrl()
        r = c.focus_fine(steps=10)
        assert abs(r.steps_taken) == 10

    def test_focus_fine_uses_final_approach_direction(self):
        cfg = _cfg(
            final_approach_direction=FocuserDirection.COUNTER_CLOCKWISE,
            increasing_value_direction=FocuserDirection.CLOCKWISE,
            fine_step=25,
        )
        c = _ctrl(config=cfg)
        r = c.focus_fine()
        assert r.steps_taken == -25   # CCW → negative steps


# ── Clipped flag ──────────────────────────────────────────────────────────────

class TestClippedFlag:
    def test_not_clipped_when_within_limits(self):
        f = _available_focuser(start_pos=5000)
        c = _ctrl(focuser=f)
        r = c.move_focus_relative(100)
        assert r.clipped is False

    def test_clipped_when_max_step_exceeded(self):
        cfg = _cfg(max_single_step=50)
        c = _ctrl(config=cfg)
        r = c.move_focus_relative(200)
        assert r.clipped is True

    def test_clipped_when_soft_limit_hit(self):
        f = _available_focuser(start_pos=100)
        cfg = _cfg(min_position=0, max_position=50000, max_single_step=500)
        c = CollimationFocuserControl(focuser=f, config=cfg)
        r = c.move_focus_relative(-500)
        assert r.clipped is True
