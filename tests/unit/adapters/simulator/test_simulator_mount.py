"""Unit tests for SimulatorMount."""
import time

import pytest

from smart_telescope.adapters.simulator.mount import SimulatorMount
from smart_telescope.ports.mount import MountState

# ── constructor ────────────────────────────────────────────────────────────────


class TestConstructor:
    def test_default_slew_time(self) -> None:
        m = SimulatorMount()
        assert m.get_state() == MountState.PARKED

    def test_custom_slew_time_accepted(self) -> None:
        SimulatorMount(slew_time_s=0.05)

    def test_negative_slew_time_raises(self) -> None:
        with pytest.raises(ValueError, match="slew_time_s"):
            SimulatorMount(slew_time_s=-0.1)


# ── connect ────────────────────────────────────────────────────────────────────


class TestConnect:
    def test_always_returns_true(self) -> None:
        assert SimulatorMount().connect() is True

    def test_idempotent(self) -> None:
        m = SimulatorMount()
        m.connect()
        assert m.connect() is True


# ── state transitions ──────────────────────────────────────────────────────────


class TestStateTransitions:
    def test_initial_state_parked(self) -> None:
        assert SimulatorMount().get_state() == MountState.PARKED

    def test_unpark_returns_true(self) -> None:
        assert SimulatorMount().unpark() is True

    def test_unpark_transitions_to_unparked(self) -> None:
        m = SimulatorMount()
        m.unpark()
        assert m.get_state() == MountState.UNPARKED

    def test_enable_tracking_returns_true(self) -> None:
        m = SimulatorMount()
        m.unpark()
        assert m.enable_tracking() is True

    def test_enable_tracking_transitions_to_tracking(self) -> None:
        m = SimulatorMount()
        m.unpark()
        m.enable_tracking()
        assert m.get_state() == MountState.TRACKING

    def test_disconnect_returns_to_parked(self) -> None:
        m = SimulatorMount()
        m.unpark()
        m.enable_tracking()
        m.disconnect()
        assert m.get_state() == MountState.PARKED


# ── position ───────────────────────────────────────────────────────────────────


class TestPosition:
    def test_initial_position_zero(self) -> None:
        pos = SimulatorMount().get_position()
        assert pos.ra == pytest.approx(0.0)
        assert pos.dec == pytest.approx(0.0)

    def test_sync_updates_position(self) -> None:
        m = SimulatorMount()
        assert m.sync(5.5, -5.4) is True
        pos = m.get_position()
        assert pos.ra == pytest.approx(5.5)
        assert pos.dec == pytest.approx(-5.4)


# ── goto — instant (slew_time_s=0) ────────────────────────────────────────────


class TestGotoInstant:
    def test_goto_returns_true(self) -> None:
        assert SimulatorMount().goto(5.5, -5.4) is True

    def test_goto_updates_position(self) -> None:
        m = SimulatorMount()
        m.goto(5.5, -5.4)
        pos = m.get_position()
        assert pos.ra == pytest.approx(5.5)
        assert pos.dec == pytest.approx(-5.4)

    def test_not_slewing_after_instant_goto(self) -> None:
        m = SimulatorMount()
        m.goto(5.5, -5.4)
        assert m.is_slewing() is False

    def test_state_tracking_after_instant_goto(self) -> None:
        m = SimulatorMount()
        m.goto(5.5, -5.4)
        assert m.get_state() == MountState.TRACKING


# ── goto — timed slew ─────────────────────────────────────────────────────────


class TestGotoTimed:
    def test_slewing_during_goto(self) -> None:
        m = SimulatorMount(slew_time_s=0.1)
        m.goto(5.5, -5.4)
        assert m.is_slewing() is True

    def test_state_slewing_during_goto(self) -> None:
        m = SimulatorMount(slew_time_s=0.1)
        m.goto(5.5, -5.4)
        assert m.get_state() == MountState.SLEWING

    def test_settles_to_tracking(self) -> None:
        m = SimulatorMount(slew_time_s=0.1)
        m.goto(5.5, -5.4)
        time.sleep(0.2)
        assert m.get_state() == MountState.TRACKING
        assert m.is_slewing() is False

    def test_position_set_immediately_on_goto(self) -> None:
        m = SimulatorMount(slew_time_s=0.1)
        m.goto(5.5, -5.4)
        pos = m.get_position()
        assert pos.ra == pytest.approx(5.5)

    def test_second_goto_cancels_first_slew(self) -> None:
        m = SimulatorMount(slew_time_s=0.5)
        m.goto(5.5, -5.4)
        m.goto(1.0, 10.0)
        pos = m.get_position()
        assert pos.ra == pytest.approx(1.0)
        time.sleep(0.7)
        assert m.get_state() == MountState.TRACKING


# ── stop ───────────────────────────────────────────────────────────────────────


class TestStop:
    def test_stop_cancels_slew(self) -> None:
        m = SimulatorMount(slew_time_s=0.5)
        m.goto(5.5, -5.4)
        assert m.is_slewing() is True
        m.stop()
        assert m.is_slewing() is False

    def test_stop_sets_state_unparked(self) -> None:
        m = SimulatorMount(slew_time_s=0.1)
        m.goto(5.5, -5.4)
        m.stop()
        assert m.get_state() == MountState.UNPARKED

    def test_stop_safe_when_not_slewing(self) -> None:
        m = SimulatorMount()
        m.unpark()
        m.enable_tracking()
        m.stop()  # should not raise
        assert m.get_state() == MountState.UNPARKED

    def test_disconnect_cancels_pending_slew(self) -> None:
        m = SimulatorMount(slew_time_s=0.5)
        m.goto(5.5, -5.4)
        m.disconnect()
        assert m.get_state() == MountState.PARKED
        assert m.is_slewing() is False
