"""Unit tests for OnStepFocuser — delegates serial I/O to OnStepMount."""

from unittest.mock import MagicMock

from smart_telescope.adapters.onstep.focuser import OnStepFocuser
from smart_telescope.adapters.onstep.mount import OnStepMount
from smart_telescope.ports.focuser import FocuserPort


def _make_mount(**kwargs: object) -> MagicMock:
    mount = MagicMock(spec=OnStepMount)
    mount._send.return_value = kwargs.get("send_return", "")
    mount._raw_send.return_value = kwargs.get("raw_send_return", b"")
    return mount


def _make_focuser(**kwargs: object) -> tuple[OnStepFocuser, MagicMock]:
    mount = _make_mount(**kwargs)
    return OnStepFocuser(mount), mount


# ── contract ──────────────────────────────────────────────────────────────────


class TestFocuserContract:
    def test_is_subclass_of_focuser_port(self) -> None:
        assert issubclass(OnStepFocuser, FocuserPort)

    def test_all_abstract_methods_implemented(self) -> None:
        mount = _make_mount()
        foc = OnStepFocuser(mount)
        for name in ("connect", "disconnect", "move", "get_position", "get_max_position",
                     "is_moving", "stop"):
            assert hasattr(foc, name), f"Missing: {name}"
        assert hasattr(type(foc), "is_available"), "Missing property: is_available"


# ── connect / is_available ────────────────────────────────────────────────────


class TestConnect:
    def test_connect_returns_true_when_focuser_active(self) -> None:
        foc, mount = _make_focuser()
        mount._send.side_effect = ["1", "5000"]  # :FA#, :FM#
        assert foc.connect() is True

    def test_connect_returns_true_when_focuser_not_active(self) -> None:
        foc, mount = _make_focuser()
        mount._send.return_value = "0"
        assert foc.connect() is True

    def test_connect_sets_available_true_when_FA_returns_1(self) -> None:
        foc, mount = _make_focuser()
        mount._send.side_effect = ["1", "5000"]
        foc.connect()
        assert foc.is_available is True

    def test_connect_sets_available_false_when_FA_returns_0(self) -> None:
        foc, mount = _make_focuser()
        mount._send.return_value = "0"
        foc.connect()
        assert foc.is_available is False

    def test_connect_fetches_max_position_via_FM_when_available(self) -> None:
        foc, mount = _make_focuser()
        mount._send.side_effect = ["1", "8000"]
        foc.connect()
        calls = [c[0][0] for c in mount._send.call_args_list]
        assert ":FA#" in calls
        assert ":FM#" in calls
        assert foc.get_max_position() == 8000

    def test_connect_does_not_fetch_max_when_not_available(self) -> None:
        foc, mount = _make_focuser()
        mount._send.return_value = "0"
        foc.connect()
        calls = [c[0][0] for c in mount._send.call_args_list]
        assert ":FM#" not in calls

    def test_disconnect_is_safe_noop(self) -> None:
        foc, _ = _make_focuser()
        foc.disconnect()  # must not raise


# ── is_available (pre-connect) ────────────────────────────────────────────────


class TestIsAvailableBeforeConnect:
    def test_is_available_false_before_connect(self) -> None:
        foc, _ = _make_focuser()
        assert foc.is_available is False


# ── get_position ───────────────────────────────────────────────────────────────


class TestGetPosition:
    def test_get_position_sends_FG_command(self) -> None:
        foc, mount = _make_focuser()
        mount._send.side_effect = ["1", "5000", "1000"]
        foc.connect()
        foc.get_position()
        calls = [c[0][0] for c in mount._send.call_args_list]
        assert ":FG#" in calls

    def test_get_position_returns_parsed_integer(self) -> None:
        foc, mount = _make_focuser()
        mount._send.side_effect = ["1", "5000", "1500"]
        foc.connect()
        assert foc.get_position() == 1500

    def test_get_position_returns_zero_on_invalid_reply(self) -> None:
        foc, mount = _make_focuser()
        mount._send.side_effect = ["1", "5000", ""]
        foc.connect()
        assert foc.get_position() == 0


# ── get_max_position ──────────────────────────────────────────────────────────


class TestGetMaxPosition:
    def test_get_max_position_returns_cached_value(self) -> None:
        foc, mount = _make_focuser()
        mount._send.side_effect = ["1", "9999"]
        foc.connect()
        assert foc.get_max_position() == 9999

    def test_get_max_position_returns_zero_before_connect(self) -> None:
        foc, _ = _make_focuser()
        assert foc.get_max_position() == 0

    def test_get_max_position_invalid_reply_treated_as_zero(self) -> None:
        foc, mount = _make_focuser()
        mount._send.side_effect = ["1", ""]
        foc.connect()
        assert foc.get_max_position() == 0


# ── move ───────────────────────────────────────────────────────────────────────


class TestMove:
    def test_move_sends_FS_command_with_steps_via_raw_send(self) -> None:
        foc, mount = _make_focuser()
        foc.move(2000)
        calls = [c[0][0] for c in mount._raw_send.call_args_list]
        assert ":FS2000#" in calls

    def test_move_to_zero(self) -> None:
        foc, mount = _make_focuser()
        foc.move(0)
        calls = [c[0][0] for c in mount._raw_send.call_args_list]
        assert ":FS0#" in calls


# ── is_moving ──────────────────────────────────────────────────────────────────


class TestIsMoving:
    def test_is_moving_sends_FT_command(self) -> None:
        foc, mount = _make_focuser()
        mount._send.return_value = "S"
        foc.is_moving()
        calls = [c[0][0] for c in mount._send.call_args_list]
        assert ":FT#" in calls

    def test_M_reply_means_moving(self) -> None:
        foc, mount = _make_focuser()
        mount._send.return_value = "M"
        assert foc.is_moving() is True

    def test_S_reply_means_stopped(self) -> None:
        foc, mount = _make_focuser()
        mount._send.return_value = "S"
        assert foc.is_moving() is False


# ── stop ───────────────────────────────────────────────────────────────────────


class TestStop:
    def test_stop_sends_FQ_command_via_raw_send(self) -> None:
        foc, mount = _make_focuser()
        foc.stop()
        calls = [c[0][0] for c in mount._raw_send.call_args_list]
        assert ":FQ#" in calls

    def test_stop_returns_none(self) -> None:
        foc, _ = _make_focuser()
        assert foc.stop() is None
