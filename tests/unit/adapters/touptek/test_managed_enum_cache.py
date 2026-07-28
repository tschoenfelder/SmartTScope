"""EnumV2() must be called at most once per process (M10-058).

A real Pi crash traced to smart_telescope.adapters.touptek.managed calling
tc.Toupcam.EnumV2() fresh from two independent sites -- connect() (once per
camera instance: main/guide/oag) and enumerate_devices() (once at startup
for role-uniqueness validation) -- with no caching. Under Python 3.13,
toupcam.py's EnumV2()->__initlib() sets ctypes _fields_ unconditionally;
a second real call raises "AttributeError: _fields_ is final", and the
very next native SDK call after that segfaulted the whole process. These
tests pin the fix: EnumV2() must be invoked at most once, no matter how
many cameras/roles/enumeration calls happen.
"""
from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.adapters.touptek import managed as managed_mod
from smart_telescope.adapters.touptek.managed import SmartTouptekCamera

_WIDTH, _HEIGHT = 100, 80


def _make_toupcam_mock(num_devices: int = 1) -> MagicMock:
    tc = MagicMock()
    tc.TOUPCAM_OPTION_TRIGGER = 0x0B
    tc.TOUPCAM_OPTION_RAW = 0x04
    tc.TOUPCAM_OPTION_BITDEPTH = 0x06
    tc.TOUPCAM_OPTION_AUTOEXPO_TRIGGER = 0x5A
    tc.TOUPCAM_OPTION_RGB = 0x16

    device = MagicMock()
    device.model.flag = 0
    tc.Toupcam.EnumV2.return_value = [device for _ in range(num_devices)]

    hw = MagicMock()
    hw.get_Size.return_value = (_WIDTH, _HEIGHT)
    hw.get_ExpoAGain.return_value = 100
    hw.get_Option.return_value = 1
    tc.Toupcam.Open.return_value = hw
    return tc


@pytest.fixture(autouse=True)
def _reset_enum_cache():
    managed_mod._enum_devices_cache = None
    yield
    managed_mod._enum_devices_cache = None


class TestEnumDevicesCached:
    def test_enumerate_devices_called_twice_hits_sdk_once(self) -> None:
        tc = _make_toupcam_mock()
        with patch.dict(sys.modules, {"toupcam": tc}):
            SmartTouptekCamera.enumerate_devices()
            SmartTouptekCamera.enumerate_devices()
        assert tc.Toupcam.EnumV2.call_count == 1

    def test_two_camera_instances_connecting_hits_sdk_once(self) -> None:
        tc = _make_toupcam_mock()
        cam_a = SmartTouptekCamera(index=0)
        cam_b = SmartTouptekCamera(index=0)
        with patch.dict(sys.modules, {"toupcam": tc}):
            cam_a.connect()
            cam_b.connect()
        assert tc.Toupcam.EnumV2.call_count == 1

    def test_enumerate_then_connect_hits_sdk_once(self) -> None:
        tc = _make_toupcam_mock()
        cam = SmartTouptekCamera(index=0)
        with patch.dict(sys.modules, {"toupcam": tc}):
            SmartTouptekCamera.enumerate_devices()
            cam.connect()
        assert tc.Toupcam.EnumV2.call_count == 1

    def test_connect_then_enumerate_hits_sdk_once(self) -> None:
        tc = _make_toupcam_mock()
        cam = SmartTouptekCamera(index=0)
        with patch.dict(sys.modules, {"toupcam": tc}):
            cam.connect()
            SmartTouptekCamera.enumerate_devices()
        assert tc.Toupcam.EnumV2.call_count == 1
