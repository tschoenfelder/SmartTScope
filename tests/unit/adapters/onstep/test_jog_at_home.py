"""Manual jog at confirmed mechanical HOME — upstream v0.3.3 (M10-030).

History: the Cameras-screen jog pad was refused with
``axis_motion_refused_at_home`` at mechanical HOME (M10-027/M10-028).
Upstream shipped REQ-ST-009 in v0.3.3 (closes issue #5): ``move_ra_timed``/
``move_dec_timed`` accept ``mode="manual"`` — allowed at home, skips
projected-target validation, requires tracking OFF, keeps every mechanical
blocker. The shim's M10-028 ``_jog_bypass_active`` window was deleted;
``move()`` now selects center mode while tracking and manual mode otherwise.

Unlike the other fake-serial suites, these tests deliberately use the REAL
``motion_safety_preflight`` — the stubbed one in ``test_with_fake_serial._mount``
returns no ``at_home`` key and would bypass the very gates under test.
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


class TestAtHomeRefusalForAstronomicalModes:
    def test_center_mode_still_refused_at_home(self):
        # Regression guard: only manual mode may run at home — the upstream
        # gate for guide/center corrections must still exist.
        mount, _ = _mount_real_preflight(state="home")
        with pytest.raises(OnStepSafetyError) as exc_info:
            mount.move_ra_timed("e", 50, mode="center")
        assert exc_info.value.violation.reason == "axis_motion_refused_at_home"


class TestManualJog:
    def test_move_succeeds_at_home(self):
        mount, fake = _mount_real_preflight(state="home")
        assert mount.move("n", 50) is True
        cmds = b"".join(fake.commands_received)
        assert b":RC#" in cmds   # center rate selected (manual jogs at :RC#)
        assert b":Mn#" in cmds   # the actual axis motion was commanded

    def test_move_succeeds_at_home_ra_axis(self):
        mount, fake = _mount_real_preflight(state="home")
        assert mount.move("e", 50) is True
        cmds = b"".join(fake.commands_received)
        assert b":Me#" in cmds

    def test_manual_mode_requires_tracking_off(self):
        # Upstream v0.3.3 pairing gate: a manual jog with tracking active is
        # refused. Sticky at-home keeps the pier/HA blockers suppressed so
        # the pairing gate (not an unrelated blocker) is what fires.
        mount, fake = _mount_real_preflight(state="home")
        mount.get_state()  # observe the genuine H → mechanical authority trusted
        fake._state = "tracking"  # tracking started while still at the home pose
        mount._at_mechanical_home = True
        mount._tracking_explicitly_requested = True  # keep the 0.3.2 guard quiet
        with pytest.raises(OnStepSafetyError) as exc_info:
            mount.move_dec_timed("n", 50, mode="manual")
        assert exc_info.value.violation.reason == "manual_jog_requires_tracking_off"

    def test_move_picks_center_mode_while_tracking(self):
        mount, _ = _mount_real_preflight(state="tracking")
        mount._tracking_explicitly_requested = True
        with patch.object(mount, "move_dec_timed") as timed:
            timed.return_value.ok = True
            assert mount.move("n", 50) is True
        assert timed.call_args.kwargs["mode"] == "center"

    def test_move_picks_manual_mode_when_not_tracking(self):
        mount, _ = _mount_real_preflight(state="home")
        with patch.object(mount, "move_ra_timed") as timed:
            timed.return_value.ok = True
            assert mount.move("w", 50) is True
        assert timed.call_args.kwargs["mode"] == "manual"

    def test_mechanical_blocker_still_refuses_manual_jog(self):
        # Manual mode only bypasses the at-home gate — a real mechanical
        # blocker (at-limit flag) must still refuse the jog, even at home.
        mount, _ = _mount_real_preflight(state="at_limit")
        mount._at_mechanical_home = True  # sticky at-home + limit condition
        with pytest.raises(OnStepSafetyError) as exc_info:
            mount.move("n", 50)
        # Refused with a mechanical motion_refused reason (at-limit state
        # both sets the at_limit blocker and untrusts position authority —
        # blockers[0] wins), never waved through via the manual mode.
        assert exc_info.value.violation.reason != "axis_motion_refused_at_home"
        assert exc_info.value.violation.reason in (
            "mechanical_position_authority_untrusted", "onstep_at_limit",
        )


class TestPreflightStaysTruthful:
    def test_preflight_reports_true_at_home_for_every_command(self):
        # The M10-028 shim post-process (at_home=False during a jog window)
        # is gone — preflight reports the truth even for jog command strings;
        # upstream skips the refusal via the mode check, not a lying preflight.
        mount, _ = _mount_real_preflight(state="home")
        for command in ("current_tracking_safety", "move_ra_center", "move_ra_manual"):
            result = mount.motion_safety_preflight(command=command, normal_motion=False)
            assert result["at_home"] is True, command
