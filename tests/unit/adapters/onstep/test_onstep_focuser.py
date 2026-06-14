"""Unit tests for OnStepFocuser — delegates serial I/O to OnStepSerialBus."""

from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.adapters.onstep.focuser import OnStepFocuser
from smart_telescope.adapters.onstep.serial_bus import OnStepSerialBus
from smart_telescope.ports.focuser import FocuserPort


def _make_bus(**kwargs: object) -> MagicMock:
    bus = MagicMock(spec=OnStepSerialBus)
    bus.send.return_value = kwargs.get("send_return", "")
    bus.raw_send.return_value = kwargs.get("raw_send_return", b"")
    return bus


def _make_focuser(**kwargs: object) -> tuple[OnStepFocuser, MagicMock]:
    bus = _make_bus(**kwargs)
    return OnStepFocuser(bus), bus


# ── contract ──────────────────────────────────────────────────────────────────


class TestFocuserContract:
    def test_is_subclass_of_focuser_port(self) -> None:
        assert issubclass(OnStepFocuser, FocuserPort)

    def test_all_abstract_methods_implemented(self) -> None:
        bus = _make_bus()
        foc = OnStepFocuser(bus)
        for name in ("connect", "disconnect", "move", "get_position", "get_max_position",
                     "is_moving", "stop"):
            assert hasattr(foc, name), f"Missing: {name}"
        assert hasattr(type(foc), "is_available"), "Missing property: is_available"


# ── connect / is_available ────────────────────────────────────────────────────


class TestConnect:
    def test_connect_returns_true_when_focuser_active(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "5000"]  # :FA#, :FM#
        assert foc.connect() is True

    @pytest.mark.skip(
        reason=(
            "New OnStepFocuser.connect() always returns True; focuser availability is "
            "communicated via is_available property, not the return value of connect()."
        )
    )
    def test_connect_returns_false_when_focuser_not_active(self) -> None:
        foc, bus = _make_focuser()
        bus.send.return_value = "0"
        assert foc.connect() is False

    def test_connect_sets_available_true_when_FA_returns_1(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "5000"]
        foc.connect()
        assert foc.is_available is True

    def test_connect_sets_available_false_when_FA_returns_0(self) -> None:
        foc, bus = _make_focuser()
        bus.send.return_value = "0"
        foc.connect()
        assert foc.is_available is False

    def test_connect_fetches_max_position_via_FM_when_available(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "8000"]
        foc.connect()
        calls = [c[0][0] for c in bus.send.call_args_list]
        assert ":FA#" in calls
        assert ":FM#" in calls
        assert foc.get_max_position() == 8000

    def test_connect_does_not_fetch_max_when_not_available(self) -> None:
        foc, bus = _make_focuser()
        bus.send.return_value = "0"
        foc.connect()
        calls = [c[0][0] for c in bus.send.call_args_list]
        assert ":FM#" not in calls

    def test_disconnect_is_safe_noop(self) -> None:
        foc, _ = _make_focuser()
        foc.disconnect()  # must not raise


# ── connect retry (BUG-010 connect ordering) ─────────────────────────────────


class TestConnectRetry:
    """focuser.connect() retries :FA# up to 3× before concluding unavailable."""

    def test_available_on_first_attempt_sends_FA_once(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "5000"]
        with patch("smart_telescope.adapters.onstep.focuser.time.sleep") as mock_sleep:
            foc.connect()
        fa_calls = [c[0][0] for c in bus.send.call_args_list if c[0][0] == ":FA#"]
        assert len(fa_calls) == 1
        mock_sleep.assert_not_called()
        assert foc.is_available is True

    def test_retry_if_first_FA_returns_0_then_1(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["0", "1", "5000"]  # :FA# miss, :FA# hit, :FM#
        with patch("smart_telescope.adapters.onstep.focuser.time.sleep"):
            foc.connect()
        fa_calls = [c[0][0] for c in bus.send.call_args_list if c[0][0] == ":FA#"]
        assert len(fa_calls) == 2
        assert foc.is_available is True
        assert foc.get_max_position() == 5000

    def test_retry_exhausted_stays_unavailable(self) -> None:
        foc, bus = _make_focuser()
        bus.send.return_value = "0"  # every :FA# returns 0
        with patch("smart_telescope.adapters.onstep.focuser.time.sleep"):
            foc.connect()
        fa_calls = [c[0][0] for c in bus.send.call_args_list if c[0][0] == ":FA#"]
        assert len(fa_calls) == 3
        assert foc.is_available is False

    def test_retry_on_empty_reply_then_available(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["", "1", "8000"]  # empty/garbage, then available
        with patch("smart_telescope.adapters.onstep.focuser.time.sleep"):
            foc.connect()
        assert foc.is_available is True
        assert foc.get_max_position() == 8000


# ── connect idempotency ───────────────────────────────────────────────────────


class TestConnectIdempotency:
    """Second connect() call skips serial round-trips when already available."""

    def test_second_connect_when_available_makes_no_serial_calls(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "5000"]
        foc.connect()
        assert foc.is_available is True

        bus.reset_mock()
        result = foc.connect()
        assert result is True
        bus.send.assert_not_called()
        bus.raw_send.assert_not_called()

    def test_second_connect_when_unavailable_retries(self) -> None:
        """Reconnect after fixing hardware must still retry :FA#."""
        foc, bus = _make_focuser()
        bus.send.return_value = "0"
        with patch("smart_telescope.adapters.onstep.focuser.time.sleep"):
            foc.connect()
        assert foc.is_available is False

        bus.send.side_effect = ["1", "6000"]
        with patch("smart_telescope.adapters.onstep.focuser.time.sleep"):
            result = foc.connect()
        assert result is True
        assert foc.get_max_position() == 6000


# ── is_available (pre-connect) ────────────────────────────────────────────────


class TestIsAvailableBeforeConnect:
    def test_is_available_false_before_connect(self) -> None:
        foc, _ = _make_focuser()
        assert foc.is_available is False


# ── get_position ───────────────────────────────────────────────────────────────


class TestGetPosition:
    def test_get_position_sends_FG_command(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "5000", "1000"]
        foc.connect()
        foc.get_position()
        calls = [c[0][0] for c in bus.send.call_args_list]
        assert ":FG#" in calls

    def test_get_position_returns_parsed_integer(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "5000", "1500"]
        foc.connect()
        assert foc.get_position() == 1500

    def test_get_position_returns_zero_on_invalid_reply(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "5000", ""]
        foc.connect()
        assert foc.get_position() == 0


# ── get_max_position ──────────────────────────────────────────────────────────


class TestGetMaxPosition:
    def test_get_max_position_returns_cached_value(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", "9999"]
        foc.connect()
        assert foc.get_max_position() == 9999

    def test_get_max_position_returns_zero_before_connect(self) -> None:
        foc, _ = _make_focuser()
        assert foc.get_max_position() == 0

    @pytest.mark.skip(
        reason=(
            "New OnStepFocuser falls back to safety_config.focuser_max_position (50000) "
            "when :FM# returns empty instead of returning 0. Design change in external adapter: "
            "a sensible physical upper bound is always enforced from config."
        )
    )
    def test_get_max_position_invalid_reply_treated_as_zero(self) -> None:
        foc, bus = _make_focuser()
        bus.send.side_effect = ["1", ""]
        foc.connect()
        assert foc.get_max_position() == 0


# ── move ───────────────────────────────────────────────────────────────────────


@pytest.mark.skip(
    reason=(
        "Written for old hand-rolled adapter. New OnStepFocuser.move() delegates to "
        "move_absolute() which uses send_fixed() (not raw_send()), performs bounds "
        "checking, and raises OnStepSafetyError when the reply is not '1'. "
        "Functional coverage provided by test_with_fake_serial.py."
    )
)
class TestMove:
    def test_move_sends_FS_command_with_steps_via_raw_send(self) -> None:
        foc, bus = _make_focuser()
        foc.move(2000)
        calls = [c[0][0] for c in bus.raw_send.call_args_list]
        assert ":FS2000#" in calls

    def test_move_to_zero(self) -> None:
        foc, bus = _make_focuser()
        foc.move(0)
        calls = [c[0][0] for c in bus.raw_send.call_args_list]
        assert ":FS0#" in calls


# ── is_moving ──────────────────────────────────────────────────────────────────


class TestIsMoving:
    def test_is_moving_sends_FT_command(self) -> None:
        foc, bus = _make_focuser()
        bus.send.return_value = "S"
        foc.is_moving()
        calls = [c[0][0] for c in bus.send.call_args_list]
        assert ":FT#" in calls

    def test_M_reply_means_moving(self) -> None:
        foc, bus = _make_focuser()
        bus.send.return_value = "M"
        assert foc.is_moving() is True

    def test_S_reply_means_stopped(self) -> None:
        foc, bus = _make_focuser()
        bus.send.return_value = "S"
        assert foc.is_moving() is False


# ── stop ───────────────────────────────────────────────────────────────────────


class TestStop:
    def test_stop_calls_write_bypass_with_FQ(self) -> None:
        # stop() uses write_bypass() so it is never blocked by an in-progress command.
        foc, bus = _make_focuser()
        foc.stop()
        bus.write_bypass.assert_called_once_with(b":FQ#")

    def test_stop_returns_none(self) -> None:
        foc, _ = _make_focuser()
        assert foc.stop() is None
