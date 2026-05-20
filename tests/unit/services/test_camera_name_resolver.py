import pytest
from smart_telescope.services.camera_name_resolver import CameraNameResolver

# Minimal device stub that mimics toupcam DeviceV2
class _Dev:
    def __init__(self, displayname: str, serial: str):
        self.displayname = displayname
        self._serial = serial


def _make_devices():
    return [
        _Dev("ATR585M",        "tp-4-1-10-0547-157c"),
        _Dev("G3M678M",        "tp-4-2-11-0547-14bc"),
        _Dev("GPCMOS02000KPA", "tp-3-4-23-0547-1367"),
    ]


SERIALS = {
    "G3M678M":        "tp-4-2-11-0547-14bc",
    "ATR585M":        "tp-4-1-10-0547-157c",
    "GPCMOS02000KPA": "tp-3-4-23-0547-1367",
}


def test_integer_string_returns_int():
    resolver = CameraNameResolver()
    devices = _make_devices()
    assert resolver.resolve("0", {}, devices=devices) == 0
    assert resolver.resolve("2", {}, devices=devices) == 2


def test_integer_value_returns_int():
    resolver = CameraNameResolver()
    assert resolver.resolve(0, {}, devices=_make_devices()) == 0
    assert resolver.resolve(1, {}, devices=_make_devices()) == 1


def test_model_name_matches_displayname():
    resolver = CameraNameResolver()
    devices = _make_devices()
    assert resolver.resolve("G3M678M", {}, devices=devices) == 1
    assert resolver.resolve("ATR585M", {}, devices=devices) == 0
    assert resolver.resolve("GPCMOS02000KPA", {}, devices=devices) == 2


def test_model_name_case_insensitive():
    resolver = CameraNameResolver()
    devices = _make_devices()
    assert resolver.resolve("g3m678m", {}, devices=devices) == 1


def test_model_name_with_serial_verification():
    resolver = CameraNameResolver()
    devices = _make_devices()
    assert resolver.resolve("G3M678M", SERIALS, devices=devices) == 1


def test_serial_mismatch_raises():
    resolver = CameraNameResolver()
    devices = _make_devices()
    wrong_serials = {"G3M678M": "tp-ff-ff-ff-ffff-ffff"}
    with pytest.raises(RuntimeError, match="serial"):
        resolver.resolve("G3M678M", wrong_serials, devices=devices)


def test_model_not_found_raises():
    resolver = CameraNameResolver()
    devices = _make_devices()
    with pytest.raises(RuntimeError, match="G3M999M"):
        resolver.resolve("G3M999M", {}, devices=devices)


def test_index_out_of_range_raises():
    resolver = CameraNameResolver()
    devices = _make_devices()
    with pytest.raises(RuntimeError, match="index"):
        resolver.resolve("5", {}, devices=devices)


def test_empty_devices_list_raises():
    resolver = CameraNameResolver()
    with pytest.raises(RuntimeError, match="no camera"):
        resolver.resolve("G3M678M", {}, devices=[])
