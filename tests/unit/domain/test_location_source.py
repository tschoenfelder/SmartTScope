"""LocationSource — where the currently active observer location came from.

Tests cover:
- All five members exist with the expected string values
- is_valid(): recognised member names return True, garbage/lowercase/empty return False
"""
from __future__ import annotations

import pytest

from smart_telescope.domain.location_source import LocationSource, is_valid


@pytest.mark.parametrize(
    "member,value",
    [
        (LocationSource.CONFIG_FILE, "CONFIG_FILE"),
        (LocationSource.GPS_FIX, "GPS_FIX"),
        (LocationSource.IP_LOOKUP, "IP_LOOKUP"),
        (LocationSource.USER_ENTERED, "USER_ENTERED"),
        (LocationSource.SAVED_LOCATION, "SAVED_LOCATION"),
    ],
)
def test_member_values(member, value):
    assert member.value == value


@pytest.mark.parametrize(
    "name",
    ["CONFIG_FILE", "GPS_FIX", "IP_LOOKUP", "USER_ENTERED", "SAVED_LOCATION"],
)
def test_is_valid_true_for_known_members(name):
    assert is_valid(name) is True


@pytest.mark.parametrize("name", ["", "config_file", "GARBAGE", "gps_fix", "NOT_A_SOURCE"])
def test_is_valid_false_for_unknown_names(name):
    assert is_valid(name) is False
