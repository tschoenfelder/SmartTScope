"""MountState cross-enum equality (ONS31-101).

The OnStep shim overrides get_state() to return SmartTScope's 7-state
MountState, but upstream onstep_adapter internals compare that result against
their own 6-state MountState enum (e.g. `state == MountState.TRACKING` inside
recovery_unpark_stop_tracking, `state_before == MountState.PARKED` inside
return_home_mechanical). Plain Enum members of different classes are never
equal, which would silently disable those upstream safety checks — including
the firmware auto-tracking stop that unpark_to_home_stop_tracking() exists
to perform (SAFETY-001).

SmartTScope's MountState therefore compares equal by member name to any other
Enum class that is itself named MountState. Enum.__hash__ is name-based, so
set membership (`state in {MountState.PARKED, MountState.TRACKING}`) works
consistently with this equality in both directions.
"""

from enum import Enum, auto

from onstep_adapter.mount import MountState as UpstreamMountState

from smart_telescope.ports.mount import MountState


class TestCrossEnumEquality:
    def test_same_name_members_are_equal(self):
        for member in UpstreamMountState:
            assert MountState[member.name] == member
            assert member == MountState[member.name]

    def test_different_name_members_are_not_equal(self):
        assert MountState.TRACKING != UpstreamMountState.PARKED
        assert MountState.AT_HOME != UpstreamMountState.TRACKING

    def test_at_home_has_no_upstream_counterpart(self):
        assert all(MountState.AT_HOME != m for m in UpstreamMountState)

    def test_membership_in_upstream_set(self):
        # exact shape used by upstream recovery_unpark_stop_tracking
        upstream_set = {UpstreamMountState.PARKED, UpstreamMountState.TRACKING}
        assert MountState.TRACKING in upstream_set
        assert MountState.PARKED in upstream_set
        assert MountState.UNPARKED not in upstream_set
        assert MountState.AT_HOME not in upstream_set

    def test_membership_in_local_set(self):
        local_set = {MountState.PARKED, MountState.TRACKING}
        assert UpstreamMountState.TRACKING in local_set
        assert UpstreamMountState.UNPARKED not in local_set

    def test_local_identity_semantics_unchanged(self):
        assert MountState.PARKED == MountState.PARKED
        assert MountState.PARKED != MountState.TRACKING
        assert len({MountState.PARKED, MountState.PARKED}) == 1

    def test_unrelated_enum_with_same_member_name_not_equal(self):
        class OtherState(Enum):
            TRACKING = auto()

        assert MountState.TRACKING != OtherState.TRACKING

    def test_not_equal_to_plain_values(self):
        assert MountState.TRACKING != "TRACKING"
        assert MountState.PARKED != 2
