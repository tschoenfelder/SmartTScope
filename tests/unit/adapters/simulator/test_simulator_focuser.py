"""Unit tests for SimulatorFocuser."""
import time

import pytest

from smart_telescope.adapters.simulator.focuser import SimulatorFocuser

# ── constructor ────────────────────────────────────────────────────────────────


class TestConstructor:
    def test_default_move_time(self) -> None:
        f = SimulatorFocuser()
        assert f.get_position() == 0

    def test_custom_move_time_accepted(self) -> None:
        SimulatorFocuser(move_time_s=0.05)

    def test_negative_move_time_raises(self) -> None:
        with pytest.raises(ValueError, match="move_time_s"):
            SimulatorFocuser(move_time_s=-0.1)


# ── connect / disconnect ───────────────────────────────────────────────────────


class TestConnectDisconnect:
    def test_connect_returns_true(self) -> None:
        assert SimulatorFocuser().connect() is True

    def test_connect_idempotent(self) -> None:
        f = SimulatorFocuser()
        f.connect()
        assert f.connect() is True

    def test_disconnect_safe_before_connect(self) -> None:
        SimulatorFocuser().disconnect()

    def test_disconnect_safe_after_connect(self) -> None:
        f = SimulatorFocuser()
        f.connect()
        f.disconnect()


# ── move — instant (move_time_s=0) ────────────────────────────────────────────


class TestMoveInstant:
    def test_move_updates_position(self) -> None:
        f = SimulatorFocuser()
        f.move(1000)
        assert f.get_position() == 1000

    def test_not_moving_after_instant_move(self) -> None:
        f = SimulatorFocuser()
        f.move(500)
        assert f.is_moving() is False

    def test_initial_position_zero(self) -> None:
        assert SimulatorFocuser().get_position() == 0

    def test_move_to_zero(self) -> None:
        f = SimulatorFocuser()
        f.move(1000)
        f.move(0)
        assert f.get_position() == 0

    def test_move_absolute_not_relative(self) -> None:
        f = SimulatorFocuser()
        f.move(500)
        f.move(500)
        assert f.get_position() == 500


# ── move — timed ──────────────────────────────────────────────────────────────


class TestMoveTimed:
    def test_is_moving_during_move(self) -> None:
        f = SimulatorFocuser(move_time_s=0.1)
        f.move(1000)
        assert f.is_moving() is True

    def test_position_unchanged_while_moving(self) -> None:
        f = SimulatorFocuser(move_time_s=0.1)
        f.move(1000)
        assert f.get_position() == 0

    def test_position_updated_after_move_completes(self) -> None:
        f = SimulatorFocuser(move_time_s=0.1)
        f.move(1000)
        time.sleep(0.2)
        assert f.get_position() == 1000
        assert f.is_moving() is False

    def test_second_move_cancels_first(self) -> None:
        f = SimulatorFocuser(move_time_s=0.5)
        f.move(1000)
        f.move(2000)
        time.sleep(0.7)
        assert f.get_position() == 2000

    def test_second_move_does_not_settle_to_first_target(self) -> None:
        f = SimulatorFocuser(move_time_s=0.5)
        f.move(1000)
        time.sleep(0.05)
        f.move(2000)
        time.sleep(0.7)
        assert f.get_position() != 1000


# ── stop ───────────────────────────────────────────────────────────────────────


class TestStop:
    def test_stop_cancels_timed_move(self) -> None:
        f = SimulatorFocuser(move_time_s=0.5)
        f.move(1000)
        assert f.is_moving() is True
        f.stop()
        assert f.is_moving() is False

    def test_position_unchanged_after_stop(self) -> None:
        f = SimulatorFocuser(move_time_s=0.5)
        f.move(1000)
        f.stop()
        assert f.get_position() == 0

    def test_stop_safe_when_not_moving(self) -> None:
        f = SimulatorFocuser()
        f.move(500)
        f.stop()  # should not raise

    def test_disconnect_cancels_pending_move(self) -> None:
        f = SimulatorFocuser(move_time_s=0.5)
        f.move(1000)
        f.disconnect()
        assert f.is_moving() is False
        time.sleep(0.6)
        assert f.get_position() == 0  # timer was cancelled — position stays at 0
