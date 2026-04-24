"""Unit tests for OnStepFocuser — LX200 F-commands over pyserial."""

import pytest
import serial

from smart_telescope.adapters.onstep.focuser import OnStepFocuser
from smart_telescope.ports.focuser import FocuserPort


def _make_focuser(port: str = "/dev/ttyUSB0") -> OnStepFocuser:
    return OnStepFocuser(port=port)


# ── contract ──────────────────────────────────────────────────────────────────


class TestFocuserContract:
    def test_is_subclass_of_focuser_port(self) -> None:
        assert issubclass(OnStepFocuser, FocuserPort)

    def test_all_abstract_methods_implemented(self) -> None:
        foc = _make_focuser()
        for method in ("connect", "disconnect", "move", "get_position", "is_moving", "stop"):
            assert hasattr(foc, method), f"Missing: {method}"


# ── connect / disconnect ───────────────────────────────────────────────────────


class TestConnect:
    def test_connect_returns_true_when_focuser_active(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        mock_serial.return_value.readline.return_value = b"1"
        assert _make_focuser().connect() is True

    def test_connect_sends_FA_command(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"1"
        foc = _make_focuser()
        foc.connect()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":FA#" in sent

    def test_connect_returns_false_when_focuser_not_active(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        mock_serial.return_value.readline.return_value = b"0"
        assert _make_focuser().connect() is False

    def test_connect_returns_false_on_serial_exception(self, mocker: pytest.MonkeyPatch) -> None:
        mocker.patch(
            "smart_telescope.adapters.onstep.focuser.serial.Serial",
            side_effect=serial.SerialException("no port"),
        )
        assert _make_focuser().connect() is False

    def test_connect_returns_false_on_os_error(self, mocker: pytest.MonkeyPatch) -> None:
        mocker.patch(
            "smart_telescope.adapters.onstep.focuser.serial.Serial",
            side_effect=OSError("permission denied"),
        )
        assert _make_focuser().connect() is False

    def test_disconnect_closes_serial(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"1"
        foc = _make_focuser()
        foc.connect()
        foc.disconnect()
        instance.close.assert_called_once()

    def test_disconnect_is_safe_when_not_connected(self) -> None:
        _make_focuser().disconnect()


# ── get_position ───────────────────────────────────────────────────────────────


class TestGetPosition:
    def test_get_position_sends_FG_command(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"1", b"1000#"]
        foc = _make_focuser()
        foc.connect()
        foc.get_position()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":FG#" in sent

    def test_get_position_returns_integer(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"1", b"1500#"]
        foc = _make_focuser()
        foc.connect()
        assert foc.get_position() == 1500

    def test_get_position_returns_zero_on_invalid_reply(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"1", b"#"]
        foc = _make_focuser()
        foc.connect()
        assert foc.get_position() == 0

    def test_get_position_when_not_connected_returns_zero(self) -> None:
        assert _make_focuser().get_position() == 0


# ── move ───────────────────────────────────────────────────────────────────────


class TestMove:
    def test_move_sends_FS_command_with_position(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"1", b"1"]
        foc = _make_focuser()
        foc.connect()
        foc.move(2000)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":FS2000#" in sent

    def test_move_to_zero(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"1", b"1"]
        foc = _make_focuser()
        foc.connect()
        foc.move(0)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":FS0#" in sent

    def test_move_when_not_connected_is_safe(self) -> None:
        _make_focuser().move(500)


# ── is_moving ──────────────────────────────────────────────────────────────────


class TestIsMoving:
    def test_is_moving_sends_FT_command(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"1", b"S#"]
        foc = _make_focuser()
        foc.connect()
        foc.is_moving()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":FT#" in sent

    def test_M_reply_means_moving(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"1", b"M#"]
        foc = _make_focuser()
        foc.connect()
        assert foc.is_moving() is True

    def test_S_reply_means_stopped(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"1", b"S#"]
        foc = _make_focuser()
        foc.connect()
        assert foc.is_moving() is False

    def test_is_moving_when_not_connected_returns_false(self) -> None:
        assert _make_focuser().is_moving() is False


# ── stop ───────────────────────────────────────────────────────────────────────


class TestStop:
    def test_stop_sends_FQ_command(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"1"
        foc = _make_focuser()
        foc.connect()
        foc.stop()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":FQ#" in sent

    def test_stop_when_not_connected_is_safe(self) -> None:
        _make_focuser().stop()

    def test_stop_returns_none(self, mocker: pytest.MonkeyPatch) -> None:
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.focuser.serial.Serial")
        mock_serial.return_value.readline.return_value = b"1"
        foc = _make_focuser()
        foc.connect()
        assert foc.stop() is None
