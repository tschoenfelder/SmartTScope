"""
Unit tests for OnStepMount — the real mount adapter for OnStep V4 via LX200 serial protocol.

TDD step: RED — these tests fail until smart_telescope/adapters/onstep/mount.py is implemented.

Design contract being tested:
  - OnStepMount implements MountPort; all abstract methods are present.
  - All serial I/O is isolated behind a serial.Serial object — tests use mocker to patch it.
  - Each LX200 command is sent as exact bytes; responses are parsed into domain types.
  - connect() opens the serial port with the configured parameters and returns True/False.
  - Connection errors (SerialException, OSError) are caught and return False, not raise.
  - get_state() reads OnStep's :GU# status flags and maps them to MountState.
  - goto() formats RA/Dec into LX200 sexagesimal strings before sending.
  - is_slewing() returns True only when OnStep reports an active slew in progress.
  - stop() sends the emergency-stop command unconditionally, regardless of state.

LX200 / OnStep V4 command reference (subset used by this adapter):
  :GU#    → status flags string (e.g. "n|T|0|0|0|0|0|0|0|0|0|0|0|0|0#")
  :hU#    → unpark
  :Te#    → enable sidereal tracking  → "1" on success
  :Td#    → disable tracking
  :GR#    → get RA  → "HH:MM:SS#"
  :GD#    → get Dec → "±DD*MM:SS#"
  :Sr<HH:MM:SS>#   → set target RA
  :Sd<±DD*MM:SS>#  → set target Dec
  :MS#    → slew to target  → "0" success, "1"/"2" failure
  :CM#    → sync to current pointing coordinates
  :Q#     → stop all motion (emergency stop)
  :D#     → slew indicator → "|" while slewing, "" when stopped
"""

import pytest
import serial

# These imports will fail (RED) until the adapter is implemented.
from smart_telescope.adapters.onstep.mount import OnStepMount
from smart_telescope.ports.mount import MountPort, MountPosition, MountState

# ── helpers ────────────────────────────────────────────────────────────────────

def _make_mount(
    port: str = "/dev/ttyUSB0",
    baud_rate: int = 9600,
    timeout: float = 2.0,
) -> OnStepMount:
    return OnStepMount(port=port, baud_rate=baud_rate, timeout=timeout)


def _configure_serial(mock_serial_cls, responses: list[bytes]) -> object:
    """Wire mock_serial_cls so that readline()/read() returns successive responses."""
    instance = mock_serial_cls.return_value.__enter__.return_value
    instance.readline.side_effect = responses
    return instance


# ── MountPort contract ─────────────────────────────────────────────────────────

class TestOnStepMountPortContract:
    def test_is_subclass_of_mount_port(self):
        assert issubclass(OnStepMount, MountPort)

    def test_all_abstract_methods_implemented(self):
        mount = _make_mount()
        abstract = {
            "connect", "disconnect", "get_state", "unpark",
            "enable_tracking", "get_position", "sync", "goto",
            "is_slewing", "stop", "park", "disable_tracking",
        }
        for method_name in abstract:
            assert hasattr(mount, method_name), f"Missing method: {method_name}"


# ── connect / disconnect ───────────────────────────────────────────────────────

class TestConnect:
    def test_connect_returns_true_on_success(self, mocker):
        mocker.patch("serial.Serial")
        mount = _make_mount()
        assert mount.connect() is True

    def test_connect_opens_serial_with_configured_port(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        mount = _make_mount(port="/dev/ttyAMA0", baud_rate=9600)
        mount.connect()
        mock_serial.assert_called_once()
        call_args = mock_serial.call_args
        assert call_args[0][0] == "/dev/ttyAMA0" or call_args[1].get("port") == "/dev/ttyAMA0"

    def test_connect_uses_configured_baud_rate(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        mount = _make_mount(baud_rate=19200)
        mount.connect()
        call_args = mock_serial.call_args
        assert 19200 in call_args[0] or call_args[1].get("baudrate") == 19200

    def test_connect_returns_false_on_serial_exception(self, mocker):
        mocker.patch(
            "smart_telescope.adapters.onstep.mount.serial.Serial",
            side_effect=serial.SerialException("port not found"),
        )
        mount = _make_mount()
        assert mount.connect() is False

    def test_connect_returns_false_on_os_error(self, mocker):
        mocker.patch(
            "smart_telescope.adapters.onstep.mount.serial.Serial",
            side_effect=OSError("permission denied"),
        )
        mount = _make_mount()
        assert mount.connect() is False

    def test_connect_does_not_raise_on_failure(self, mocker):
        mocker.patch(
            "smart_telescope.adapters.onstep.mount.serial.Serial",
            side_effect=serial.SerialException("no device"),
        )
        mount = _make_mount()
        # Must not raise — adapter absorbs the exception and returns False
        result = mount.connect()
        assert result is False

    def test_connect_sends_stop_tracking(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b""
        mount = _make_mount()
        mount.connect()
        written = [call.args[0] for call in instance.write.call_args_list]
        assert b":Td#" in written

    def test_disconnect_closes_serial_port(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        mount = _make_mount()
        mount.connect()
        mount.disconnect()
        instance.close.assert_called_once()

    def test_disconnect_is_safe_when_not_connected(self):
        mount = _make_mount()
        # disconnect() before connect() must not raise
        mount.disconnect()


# ── get_state ─────────────────────────────────────────────────────────────────

class TestGetState:
    def test_parked_flag_returns_parked_state(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        # :GU# response containing 'P' = parked
        instance.readline.return_value = b"P|N|0|0|0|0|0|0|0|0|0|0|0|0|0#"
        mount = _make_mount()
        mount.connect()
        assert mount.get_state() == MountState.PARKED

    def test_tracking_flag_returns_unparked_tracking_state(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        # 'n' = not parked, 'T' present = tracking active
        instance.readline.return_value = b"n|T|0|0|0|0|0|0|0|0|0|0|0|0|0#"
        mount = _make_mount()
        mount.connect()
        state = mount.get_state()
        assert state in (MountState.UNPARKED, MountState.TRACKING)

    def test_slewing_flag_returns_slewing_state(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        # 'S' flag = slewing
        instance.readline.return_value = b"n|S|0|0|0|0|0|0|0|0|0|0|0|0|0#"
        mount = _make_mount()
        mount.connect()
        assert mount.get_state() == MountState.SLEWING

    def test_limit_flag_returns_at_limit_state(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        # 'E' or 'W' = at hardware limit
        instance.readline.return_value = b"n|E|0|0|0|0|0|0|0|0|0|0|0|0|0#"
        mount = _make_mount()
        mount.connect()
        assert mount.get_state() == MountState.AT_LIMIT

    def test_unreadable_response_returns_unknown(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b""
        mount = _make_mount()
        mount.connect()
        assert mount.get_state() == MountState.UNKNOWN


# ── unpark ────────────────────────────────────────────────────────────────────

class TestUnpark:
    def test_unpark_sends_hU_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"#"
        mount = _make_mount()
        mount.connect()
        mount.unpark()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":hU#" in sent

    def test_unpark_returns_true_on_success(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"#"
        mount = _make_mount()
        mount.connect()
        assert mount.unpark() is True

    def test_unpark_returns_false_on_timeout(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b""  # empty = timeout
        mount = _make_mount()
        mount.connect()
        assert mount.unpark() is False


# ── enable_tracking ───────────────────────────────────────────────────────────

class TestEnableTracking:
    def test_enable_tracking_sends_Te_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"1"
        mount = _make_mount()
        mount.connect()
        mount.enable_tracking()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":Te#" in sent

    def test_enable_tracking_returns_true_when_acknowledged(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"1"
        mount = _make_mount()
        mount.connect()
        assert mount.enable_tracking() is True

    def test_enable_tracking_returns_false_when_rejected(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"0"
        mount = _make_mount()
        mount.connect()
        assert mount.enable_tracking() is False


# ── get_position ──────────────────────────────────────────────────────────────

class TestGetPosition:
    def test_get_position_returns_mount_position(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        # b"" absorbs the :Td# readline from connect(); then RA and Dec
        instance.readline.side_effect = [b"", b"05:35:17#", b"-05*23:28#"]
        mount = _make_mount()
        mount.connect()
        pos = mount.get_position()
        assert isinstance(pos, MountPosition)

    def test_get_position_ra_converted_to_decimal_hours(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"", b"06:00:00#", b"+00*00:00#"]
        mount = _make_mount()
        mount.connect()
        pos = mount.get_position()
        assert pos.ra == pytest.approx(6.0, abs=0.01)

    def test_get_position_dec_converted_to_decimal_degrees(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"", b"05:35:17#", b"+45*30:00#"]
        mount = _make_mount()
        mount.connect()
        pos = mount.get_position()
        assert pos.dec == pytest.approx(45.5, abs=0.01)

    def test_negative_dec_is_negative(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.side_effect = [b"", b"05:35:17#", b"-05*23:28#"]
        mount = _make_mount()
        mount.connect()
        pos = mount.get_position()
        assert pos.dec < 0


# ── sync ──────────────────────────────────────────────────────────────────────

class TestSync:
    def test_sync_sends_CM_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"M31 EX GAL MAG 3.5 SZ178.0'#"
        mount = _make_mount()
        mount.connect()
        mount.sync(ra=5.5881, dec=-5.391)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":CM#" in sent

    def test_sync_sets_target_ra_before_CM(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"#"
        mount = _make_mount()
        mount.connect()
        mount.sync(ra=5.5881, dec=-5.391)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":Sr" in sent

    def test_sync_returns_true_on_success(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"#"
        mount = _make_mount()
        mount.connect()
        assert mount.sync(ra=5.5881, dec=-5.391) is True


# ── goto ──────────────────────────────────────────────────────────────────────

class TestGoto:
    def test_goto_sends_MS_slew_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"0"
        mount = _make_mount()
        mount.connect()
        mount.goto(ra=5.5881, dec=-5.391)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":MS#" in sent

    def test_goto_sends_target_ra_before_slew(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"0"
        mount = _make_mount()
        mount.connect()
        mount.goto(ra=5.5881, dec=-5.391)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":Sr" in sent

    def test_goto_sends_target_dec_before_slew(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"0"
        mount = _make_mount()
        mount.connect()
        mount.goto(ra=5.5881, dec=-5.391)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":Sd" in sent

    def test_goto_ra_formatted_as_sexagesimal(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"0"
        mount = _make_mount()
        mount.connect()
        # RA = 6.0 hours → "06:00:00"
        mount.goto(ra=6.0, dec=0.0)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b"06:00:00" in sent

    def test_goto_dec_formatted_as_sexagesimal_positive(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"0"
        mount = _make_mount()
        mount.connect()
        # Dec = +45.5 degrees → "+45*30:00"
        mount.goto(ra=6.0, dec=45.5)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b"+45" in sent

    def test_goto_dec_formatted_with_minus_sign_when_negative(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"0"
        mount = _make_mount()
        mount.connect()
        mount.goto(ra=5.5881, dec=-5.391)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b"-05" in sent or b"-5" in sent

    def test_goto_returns_true_when_slew_accepted(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"0"
        mount = _make_mount()
        mount.connect()
        assert mount.goto(ra=5.5881, dec=-5.391) is True

    def test_goto_returns_false_when_slew_rejected(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        # "1" = slew not possible (object below horizon etc.)
        instance.readline.return_value = b"1"
        mount = _make_mount()
        mount.connect()
        assert mount.goto(ra=5.5881, dec=-5.391) is False


# ── is_slewing ────────────────────────────────────────────────────────────────

class TestIsSlewing:
    def test_pipe_character_means_slewing(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        # :D# returns "|" while a slew is in progress
        instance.readline.return_value = b"|#"
        mount = _make_mount()
        mount.connect()
        assert mount.is_slewing() is True

    def test_empty_response_means_not_slewing(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"#"
        mount = _make_mount()
        mount.connect()
        assert mount.is_slewing() is False

    def test_is_slewing_sends_D_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"#"
        mount = _make_mount()
        mount.connect()
        mount.is_slewing()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":D#" in sent


# ── stop ──────────────────────────────────────────────────────────────────────

class TestStop:
    def test_stop_sends_Q_emergency_stop_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        mount = _make_mount()
        mount.connect()
        mount.stop()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":Q#" in sent

    def test_stop_does_not_raise_when_not_connected(self):
        mount = _make_mount()
        # stop() must be unconditionally safe — emergency semantics
        mount.stop()

    def test_stop_returns_none(self, mocker):
        mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        mount = _make_mount()
        mount.connect()
        result = mount.stop()
        assert result is None


# ── park ──────────────────────────────────────────────────────────────────────


class TestPark:
    def test_park_sends_hP_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"#"
        mount = _make_mount()
        mount.connect()
        mount.park()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":hP#" in sent

    def test_park_returns_true(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"#"
        mount = _make_mount()
        mount.connect()
        assert mount.park() is True


# ── disable_tracking ──────────────────────────────────────────────────────────


class TestDisableTracking:
    def test_disable_tracking_sends_Td_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"1"
        mount = _make_mount()
        mount.connect()
        mount.disable_tracking()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":Td#" in sent

    def test_disable_tracking_returns_true_when_acknowledged(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b"1"
        mount = _make_mount()
        mount.connect()
        assert mount.disable_tracking() is True

    def test_disable_tracking_returns_true_regardless_of_response(self, mocker):
        # :Td# is fire-and-forget — returns True even when mount sends no ack
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b""
        mount = _make_mount()
        mount.connect()
        assert mount.disable_tracking() is True


# ── guide ──────────────────────────────────────────────────────────────────────


class TestGuide:
    def test_guide_sends_Mg_command(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b""
        mount = _make_mount()
        mount.connect()
        mount.guide("n", 500)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":Mgn0500#" in sent

    def test_guide_returns_true_for_valid_direction(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        mock_serial.return_value.readline.return_value = b""
        mount = _make_mount()
        mount.connect()
        for d in ("n", "s", "e", "w", "N", "S", "E", "W"):
            assert mount.guide(d, 200) is True

    def test_guide_returns_false_for_invalid_direction(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        mock_serial.return_value.readline.return_value = b""
        mount = _make_mount()
        mount.connect()
        assert mount.guide("x", 200) is False

    def test_guide_clamps_duration_to_valid_range(self, mocker):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = b""
        mount = _make_mount()
        mount.connect()
        mount.guide("e", 99999)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":Mge9999#" in sent


class TestAlignment:
    def _mount_with_response(self, mocker, response: bytes):
        mock_serial = mocker.patch("smart_telescope.adapters.onstep.mount.serial.Serial")
        instance = mock_serial.return_value
        instance.readline.return_value = response
        mount = _make_mount()
        mount.connect()
        return mount, instance

    def test_start_alignment_sends_A1_command(self, mocker):
        mount, instance = self._mount_with_response(mocker, b"1#")
        mount.start_alignment(1)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":A1#" in sent

    def test_start_alignment_sends_A3_for_three_stars(self, mocker):
        mount, instance = self._mount_with_response(mocker, b"1#")
        mount.start_alignment(3)
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":A3#" in sent

    def test_start_alignment_returns_true_on_success(self, mocker):
        mount, _ = self._mount_with_response(mocker, b"1#")
        assert mount.start_alignment(2) is True

    def test_start_alignment_returns_false_on_failure(self, mocker):
        mount, _ = self._mount_with_response(mocker, b"0#")
        assert mount.start_alignment(2) is False

    def test_accept_alignment_star_sends_Aplus_command(self, mocker):
        mount, instance = self._mount_with_response(mocker, b"1#")
        mount.accept_alignment_star()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":A+#" in sent

    def test_accept_alignment_star_returns_true_on_success(self, mocker):
        mount, _ = self._mount_with_response(mocker, b"1#")
        assert mount.accept_alignment_star() is True

    def test_accept_alignment_star_returns_false_on_failure(self, mocker):
        mount, _ = self._mount_with_response(mocker, b"0#")
        assert mount.accept_alignment_star() is False

    def test_save_alignment_sends_AW_command(self, mocker):
        mount, instance = self._mount_with_response(mocker, b"1#")
        mount.save_alignment()
        sent = b"".join(c[0][0] for c in instance.write.call_args_list)
        assert b":AW#" in sent

    def test_save_alignment_returns_true_on_success(self, mocker):
        mount, _ = self._mount_with_response(mocker, b"1#")
        assert mount.save_alignment() is True

    def test_save_alignment_returns_false_on_failure(self, mocker):
        mount, _ = self._mount_with_response(mocker, b"0#")
        assert mount.save_alignment() is False
