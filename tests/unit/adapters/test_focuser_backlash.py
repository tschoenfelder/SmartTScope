"""Tests for OnStepFocuser backlash compensation (M7-004 / CFG-004 / AF-004)."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import pytest

from smart_telescope.adapters.onstep.focuser import OnStepFocuser
from smart_telescope.adapters.onstep.safety import OnStepSafetyConfig


def _safety() -> OnStepSafetyConfig:
    return OnStepSafetyConfig(
        observer_lat=50.0,
        observer_lon=8.0,
        min_alt_deg=10.0,
        max_alt_deg=88.0,
        ha_east_limit_h=-5.5,
        ha_west_limit_h=0.333,
    )


def _make_focuser(backlash_steps: int = 80, backlash_enabled: bool = True) -> tuple[OnStepFocuser, MagicMock]:
    bus = MagicMock()
    bus.send.return_value = "1"
    bus.send_fixed.return_value = "1"
    focuser = OnStepFocuser(
        bus=bus,
        safety_config=_safety(),
        backlash_steps=backlash_steps,
        backlash_enabled=backlash_enabled,
    )
    focuser._available = True
    focuser._max_position = 50_000
    return focuser, bus


# ── no reversal: no overshoot ─────────────────────────────────────────────────

def test_no_backlash_on_same_direction():
    """Moving in the same direction twice → no overshoot, single move command."""
    focuser, bus = _make_focuser()
    bus.send.return_value = "1000"   # current position

    focuser.move_absolute(2000)   # first move (no prior direction → no overshoot)
    bus.send.return_value = "2000"
    focuser.move_absolute(3000)   # same direction → no overshoot

    # Both calls should each send exactly one :FS move
    fs_calls = [c for c in bus.send_fixed.call_args_list if ":FS" in str(c)]
    # move to 2000 + move to 3000 = 2 :FS calls
    assert len(fs_calls) == 2
    assert ":FS2000#" in str(fs_calls[0])
    assert ":FS3000#" in str(fs_calls[1])


# ── reversal: overshoot then target ───────────────────────────────────────────

def test_backlash_overshoot_on_reversal():
    """Direction reversal triggers overshoot by backlash_steps before final move."""
    focuser, bus = _make_focuser(backlash_steps=80)
    bus.send.return_value = "1000"  # get_position

    focuser.move_absolute(2000)  # move inward (direction +1), no prior direction
    bus.send.return_value = "2000"
    focuser.move_absolute(1500)  # reverse direction (outward, direction -1)

    # Reversal: overshoot to 1500 + 80 = 1580 (outward overshoot adds backlash in reverse direction)
    # direction is -1 (outward), so overshoot = 1500 - 80 * (-1) = 1580
    fs_calls = [str(c) for c in bus.send_fixed.call_args_list if ":FS" in str(c)]
    assert len(fs_calls) == 3  # move to 2000 + overshoot + final move to 1500
    assert ":FS1580#" in fs_calls[1]   # overshoot
    assert ":FS1500#" in fs_calls[2]   # final target


# ── backlash disabled: no overshoot ───────────────────────────────────────────

def test_no_backlash_when_disabled():
    """When backlash_enabled=False, direction reversal produces no overshoot."""
    focuser, bus = _make_focuser(backlash_enabled=False)
    bus.send.return_value = "1000"
    focuser.move_absolute(2000)
    bus.send.return_value = "2000"
    focuser.move_absolute(1500)  # reversal but disabled

    fs_calls = [c for c in bus.send_fixed.call_args_list if ":FS" in str(c)]
    assert len(fs_calls) == 2  # no overshoot


# ── config roundtrip ──────────────────────────────────────────────────────────

def test_backlash_steps_zero_no_overshoot():
    """backlash_steps=0 with enabled=True produces no overshoot (zero overshoot)."""
    focuser, bus = _make_focuser(backlash_steps=0, backlash_enabled=True)
    bus.send.return_value = "1000"
    focuser.move_absolute(2000)
    bus.send.return_value = "2000"
    focuser.move_absolute(1500)

    fs_calls = [c for c in bus.send_fixed.call_args_list if ":FS" in str(c)]
    assert len(fs_calls) == 2   # no overshoot when steps == 0
