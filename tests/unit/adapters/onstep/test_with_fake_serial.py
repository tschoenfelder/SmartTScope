"""
Integration tests for OnStepMount using FakeOnStepSerial.

These tests exercise complete command sequences against a stateful simulator
instead of mocker patches, giving higher confidence in protocol correctness.
No real hardware or serial port is used.
"""

import pytest

from smart_telescope.adapters.onstep.mount import OnStepMount
from smart_telescope.ports.mount import MountPosition, MountState

from .fake_serial import FakeOnStepSerial


def _mount(state: str = "parked", ra: float = 0.0, dec: float = 0.0) -> tuple[OnStepMount, FakeOnStepSerial]:
    fake = FakeOnStepSerial(initial_state=state, initial_ra=ra, initial_dec=dec)
    mount = OnStepMount(port="/dev/ttyUSB0")
    mount._serial = fake
    return mount, fake


# ── full init sequence ────────────────────────────────────────────────────────

class TestInitSequence:
    def test_initial_state_is_parked(self):
        mount, _ = _mount(state="parked")
        assert mount.get_state() == MountState.PARKED

    def test_unpark_transitions_from_parked(self):
        mount, _ = _mount(state="parked")
        result = mount.unpark()
        assert result is True
        assert mount.get_state() != MountState.PARKED

    def test_enable_tracking_after_unpark(self):
        mount, _ = _mount(state="parked")
        mount.unpark()
        result = mount.enable_tracking()
        assert result is True

    def test_full_init_sequence_ends_in_tracking(self):
        mount, _ = _mount(state="parked")
        mount.unpark()
        mount.enable_tracking()
        assert mount.get_state() == MountState.TRACKING

    def test_parked_flag_in_gu_response(self):
        mount, fake = _mount(state="parked")
        assert mount.get_state() == MountState.PARKED
        assert any(b":GU#" in c for c in fake.commands_received)


# ── goto / slew ───────────────────────────────────────────────────────────────

class TestGoto:
    def test_goto_returns_true_when_accepted(self):
        mount, _ = _mount(state="tracking")
        assert mount.goto(ra=5.5881, dec=-5.391) is True

    def test_goto_puts_mount_in_slewing_state(self):
        mount, _ = _mount(state="tracking")
        mount.goto(ra=5.5881, dec=-5.391)
        assert mount.is_slewing() is True

    def test_goto_sends_sr_sd_ms_commands(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=6.0, dec=45.5)
        cmds = b"".join(fake.commands_received)
        assert b":Sr" in cmds
        assert b":Sd" in cmds
        assert b":MS#" in cmds

    def test_goto_formats_ra_correctly(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=6.0, dec=0.0)
        cmds = b"".join(fake.commands_received)
        assert b"06:00:00" in cmds

    def test_goto_formats_positive_dec_correctly(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=6.0, dec=45.5)
        cmds = b"".join(fake.commands_received)
        assert b"+45*30:00" in cmds

    def test_goto_formats_negative_dec_correctly(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=5.5881, dec=-5.391)
        cmds = b"".join(fake.commands_received)
        assert b"-05*" in cmds


# ── position after settle ─────────────────────────────────────────────────────

class TestPositionAfterSettle:
    def test_position_matches_goto_target_after_settle(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=6.0, dec=45.5)
        fake.settle()
        pos = mount.get_position()
        assert pos.ra == pytest.approx(6.0, abs=0.01)
        assert pos.dec == pytest.approx(45.5, abs=0.01)

    def test_negative_dec_preserved_through_round_trip(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=5.5881, dec=-5.391)
        fake.settle()
        pos = mount.get_position()
        assert pos.dec < 0
        assert pos.dec == pytest.approx(-5.391, abs=0.02)

    def test_not_slewing_after_settle(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=6.0, dec=0.0)
        fake.settle()
        assert mount.is_slewing() is False

    def test_state_is_tracking_after_settle(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=6.0, dec=0.0)
        fake.settle()
        assert mount.get_state() == MountState.TRACKING


# ── sync ──────────────────────────────────────────────────────────────────────

class TestSync:
    def test_sync_updates_position_immediately(self):
        mount, _ = _mount(state="tracking", ra=0.0, dec=0.0)
        mount.sync(ra=6.0, dec=45.5)
        pos = mount.get_position()
        assert pos.ra == pytest.approx(6.0, abs=0.01)
        assert pos.dec == pytest.approx(45.5, abs=0.01)

    def test_sync_returns_true(self):
        mount, _ = _mount(state="tracking")
        assert mount.sync(ra=6.0, dec=45.5) is True

    def test_sync_sends_cm_command(self):
        mount, fake = _mount(state="tracking")
        mount.sync(ra=6.0, dec=45.5)
        cmds = b"".join(fake.commands_received)
        assert b":CM#" in cmds


# ── stop ──────────────────────────────────────────────────────────────────────

class TestStop:
    def test_stop_halts_active_slew(self):
        mount, _ = _mount(state="tracking")
        mount.goto(ra=6.0, dec=0.0)
        assert mount.is_slewing() is True
        mount.stop()
        assert mount.is_slewing() is False

    def test_stop_safe_before_connect(self):
        mount = OnStepMount(port="/dev/ttyUSB0")
        mount.stop()

    def test_stop_safe_when_not_slewing(self):
        mount, _ = _mount(state="tracking")
        mount.stop()

    def test_stop_sends_Q_command(self):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=6.0, dec=0.0)
        mount.stop()
        cmds = b"".join(fake.commands_received)
        assert b":Q#" in cmds


# ── position read-back ────────────────────────────────────────────────────────

class TestPositionReadback:
    def test_initial_position_is_zero(self):
        mount, _ = _mount(state="tracking", ra=0.0, dec=0.0)
        pos = mount.get_position()
        assert pos.ra == pytest.approx(0.0, abs=0.01)
        assert pos.dec == pytest.approx(0.0, abs=0.01)

    def test_returns_mount_position_type(self):
        mount, _ = _mount(state="tracking")
        pos = mount.get_position()
        assert isinstance(pos, MountPosition)

    @pytest.mark.parametrize("ra, dec", [
        (0.0, 0.0),
        (6.0, 45.5),
        (12.0, -30.0),
        (23.999, 89.99),
    ])
    def test_position_round_trips_via_fake(self, ra: float, dec: float):
        mount, fake = _mount(state="tracking")
        mount.goto(ra=ra, dec=dec)
        fake.settle()
        pos = mount.get_position()
        assert pos.ra == pytest.approx(ra, abs=0.02)
        assert pos.dec == pytest.approx(dec, abs=0.02)
