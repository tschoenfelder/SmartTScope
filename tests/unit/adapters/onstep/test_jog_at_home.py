"""SYNC-OVERRIDE REQ-ST-009 — manual jog at confirmed mechanical HOME (M10-028).

Hardware evidence 2026-07-18/19: the Cameras-screen jog pad was refused with
``axis_motion_refused_at_home`` whenever the mount sat at mechanical HOME —
upstream ``_axis_motion()`` hardcodes that gate with no bypass parameter.
User decision (2026-07-19): manual movement at confirmed home is legitimate
(same spirit as the allowed home→park move). The shim's ``move()`` opens a
narrow window during which the shim's ``motion_safety_preflight`` override
reports ``at_home=False`` for exactly the two jog preflight commands; every
other consumer keeps seeing the truth and all mechanical blockers stay live.

Unlike the other fake-serial suites, these tests deliberately use the REAL
``motion_safety_preflight`` — the stubbed one in ``test_with_fake_serial._mount``
returns no ``at_home`` key and would bypass the very gate under test.
"""

from unittest.mock import patch

import pytest

from onstep_adapter.safety import OnStepSafetyError

from smart_telescope.adapters.onstep.mount import OnStepMount
from smart_telescope.adapters.onstep.safety import OnStepSafetyConfig

from .fake_serial import FakeOnStepSerial

_TEST_SAFETY_CFG = OnStepSafetyConfig(
    observer_lat=50.0, observer_lon=8.0,
    min_alt_deg=-90.0, max_alt_deg=90.0,
    ha_east_limit_h=-12.0, ha_west_limit_h=12.0,
    require_home_confirmation=False,
    time_trust_source="manual",
)


@pytest.fixture(autouse=True)
def _no_poll_sleep():
    with patch("onstep_adapter.mount.time.sleep"):
        yield


def _mount_real_preflight(state: str = "home") -> tuple[OnStepMount, FakeOnStepSerial]:
    """Mount with the REAL motion_safety_preflight (subject under test)."""
    fake = FakeOnStepSerial(initial_state=state)
    mount = OnStepMount(port="/dev/ttyUSB0", safety_config=_TEST_SAFETY_CFG)
    mount._bus._serial = fake
    mount._home_confirmed = True
    mount._raise_if_not_astronomy_ready = lambda cmd: None  # type: ignore[method-assign]
    return mount, fake


class TestAtHomeRefusalWithoutBypass:
    def test_direct_timed_move_still_refused_at_home(self):
        # M10-027 regression guard: the upstream gate itself must still exist —
        # only the shim's move() wrapper opens the bypass window.
        mount, _ = _mount_real_preflight(state="home")
        with pytest.raises(OnStepSafetyError) as exc_info:
            mount.move_ra_timed("e", 50, mode="center")
        assert exc_info.value.violation.reason == "axis_motion_refused_at_home"


class TestJogBypass:
    def test_move_succeeds_at_home(self):
        mount, fake = _mount_real_preflight(state="home")
        assert mount.move("n", 50) is True
        cmds = b"".join(fake.commands_received)
        assert b":RC#" in cmds   # center rate selected
        assert b":Mn#" in cmds   # the actual axis motion was commanded

    def test_move_succeeds_at_home_ra_axis(self):
        mount, fake = _mount_real_preflight(state="home")
        assert mount.move("e", 50) is True
        cmds = b"".join(fake.commands_received)
        assert b":Me#" in cmds

    def test_other_preflight_commands_still_see_at_home(self):
        # Scoping: while the window is open, the poller/goto/tracking
        # consumers (different command strings) keep the true at-home state.
        mount, _ = _mount_real_preflight(state="home")
        mount._jog_bypass_active = True
        try:
            result = mount.motion_safety_preflight(
                command="current_tracking_safety", normal_motion=False,
            )
        finally:
            mount._jog_bypass_active = False
        assert result["at_home"] is True

    def test_jog_preflight_command_reports_at_home_false_only_in_window(self):
        mount, _ = _mount_real_preflight(state="home")
        # Outside the window the jog command string sees the truth too.
        result = mount.motion_safety_preflight(command="move_ra_center")
        assert result["at_home"] is True
        mount._jog_bypass_active = True
        try:
            result = mount.motion_safety_preflight(command="move_ra_center")
        finally:
            mount._jog_bypass_active = False
        assert result["at_home"] is False

    def test_window_flag_cleared_after_move(self):
        mount, _ = _mount_real_preflight(state="home")
        mount.move("n", 50)
        assert getattr(mount, "_jog_bypass_active", False) is False

    def test_window_flag_cleared_when_move_raises(self):
        mount, _ = _mount_real_preflight(state="home")
        with patch.object(
            mount, "move_dec_timed", side_effect=RuntimeError("boom"),
        ), pytest.raises(RuntimeError):
            mount.move("n", 50)
        assert getattr(mount, "_jog_bypass_active", False) is False

    def test_mechanical_blocker_still_refuses_under_bypass(self):
        # The window only touches at_home — a real mechanical blocker
        # (at-limit flag) must still refuse the jog, even at home.
        mount, _ = _mount_real_preflight(state="at_limit")
        mount._at_mechanical_home = True  # sticky at-home + limit condition
        with pytest.raises(OnStepSafetyError) as exc_info:
            mount.move("n", 50)
        # Refused with a mechanical motion_refused reason (at-limit state
        # both sets the at_limit blocker and untrusts position authority —
        # blockers[0] wins), never waved through via the at_home bypass.
        assert exc_info.value.violation.reason != "axis_motion_refused_at_home"
        assert exc_info.value.violation.reason in (
            "mechanical_position_authority_untrusted", "onstep_at_limit",
        )
