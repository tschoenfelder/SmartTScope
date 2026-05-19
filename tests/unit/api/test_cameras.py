"""Unit tests for GET /api/cameras — no hardware required."""
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app

client = TestClient(app)


# ── helpers ────────────────────────────────────────────────────────────────────


def _make_resolution(w: int, h: int) -> SimpleNamespace:
    return SimpleNamespace(width=w, height=h)


def _make_model(
    name: str = "Toupcam Mono",
    flag: int = 0,
    maxspeed: int = 2,
    preview: int = 2,
    still: int = 1,
    xpixsz: float = 2.9,
    ypixsz: float = 2.9,
    resolutions: list[SimpleNamespace] | None = None,
) -> SimpleNamespace:
    if resolutions is None:
        resolutions = [_make_resolution(3096, 2080), _make_resolution(1548, 1040)]
    return SimpleNamespace(
        name=name,
        flag=flag,
        maxspeed=maxspeed,
        preview=preview,
        still=still,
        maxfanspeed=0,
        xpixsz=xpixsz,
        ypixsz=ypixsz,
        res=resolutions,
    )


def _make_device(
    displayname: str = "Test Camera",
    cam_id: str = "CAM001",
    model: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        displayname=displayname,
        id=cam_id,
        model=model or _make_model(),
    )


def _make_toupcam_mock(devices: list[SimpleNamespace] | None = None) -> MagicMock:
    tc = MagicMock()
    tc.Toupcam.EnumV2.return_value = devices if devices is not None else [_make_device()]
    return tc


# ── /api/cameras ───────────────────────────────────────────────────────────────


class TestScanCamerasEndpoint:
    def test_returns_200(self) -> None:
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock()}):
            resp = client.get("/api/cameras")
        assert resp.status_code == 200

    def test_sdk_unavailable_when_import_fails(self) -> None:
        with patch.dict(sys.modules, {"toupcam": None}):
            data = client.get("/api/cameras").json()
        assert data["sdk_available"] is False
        assert data["cameras"] == []

    def test_sdk_available_with_installed_sdk(self) -> None:
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock()}):
            data = client.get("/api/cameras").json()
        assert data["sdk_available"] is True

    def test_empty_list_when_no_cameras(self) -> None:
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(devices=[])}):
            data = client.get("/api/cameras").json()
        assert data["cameras"] == []

    def test_camera_count_matches_devices(self) -> None:
        devices = [_make_device("Cam A", "ID1"), _make_device("Cam B", "ID2")]
        with patch.dict(sys.modules, {"toupcam": _make_toupcam_mock(devices)}):
            data = client.get("/api/cameras").json()
        assert len(data["cameras"]) == 2


class TestCameraFields:
    def _get_first(self, device: SimpleNamespace | None = None) -> dict:  # type: ignore[type-arg]
        tc = _make_toupcam_mock([device or _make_device()])
        with patch.dict(sys.modules, {"toupcam": tc}):
            return client.get("/api/cameras").json()["cameras"][0]

    def test_display_name(self) -> None:
        cam = self._get_first(_make_device(displayname="My Star Camera"))
        assert cam["display_name"] == "My Star Camera"

    def test_camera_id(self) -> None:
        cam = self._get_first(_make_device(cam_id="XYZ-999"))
        assert cam["id"] == "XYZ-999"

    def test_model_name(self) -> None:
        dev = _make_device(model=_make_model(name="AstroMono 3000"))
        cam = self._get_first(dev)
        assert cam["model_name"] == "AstroMono 3000"

    def test_pixel_size(self) -> None:
        dev = _make_device(model=_make_model(xpixsz=2.4, ypixsz=2.4))
        cam = self._get_first(dev)
        assert cam["pixel_size_um"] == pytest.approx([2.4, 2.4])

    def test_resolutions_list(self) -> None:
        res = [_make_resolution(3096, 2080), _make_resolution(1548, 1040)]
        dev = _make_device(model=_make_model(resolutions=res))
        cam = self._get_first(dev)
        assert cam["resolutions"] == [[3096, 2080], [1548, 1040]]

    def test_preview_count(self) -> None:
        dev = _make_device(model=_make_model(preview=3))
        cam = self._get_first(dev)
        assert cam["preview_count"] == 3

    def test_still_count(self) -> None:
        dev = _make_device(model=_make_model(still=2))
        cam = self._get_first(dev)
        assert cam["still_count"] == 2

    def test_max_speed(self) -> None:
        dev = _make_device(model=_make_model(maxspeed=4))
        cam = self._get_first(dev)
        assert cam["max_speed"] == 4


class TestCameraFlags:
    _FLAG_MONO      = 0x0000_0010
    _FLAG_USB30     = 0x0000_0040
    _FLAG_TEC       = 0x0000_0080
    _FLAG_RAW16     = 0x0000_8000
    _FLAG_FAN       = 0x0001_0000
    _FLAG_TEC_ONOFF = 0x0002_0000

    def _cam_with_flags(self, flag: int) -> dict:  # type: ignore[type-arg]
        dev = _make_device(model=_make_model(flag=flag))
        tc = _make_toupcam_mock([dev])
        with patch.dict(sys.modules, {"toupcam": tc}):
            return client.get("/api/cameras").json()["cameras"][0]

    def test_has_mono_true(self) -> None:
        assert self._cam_with_flags(self._FLAG_MONO)["has_mono"] is True

    def test_has_mono_false(self) -> None:
        assert self._cam_with_flags(0)["has_mono"] is False

    def test_usb3_true(self) -> None:
        assert self._cam_with_flags(self._FLAG_USB30)["usb3"] is True

    def test_usb3_false(self) -> None:
        assert self._cam_with_flags(0)["usb3"] is False

    def test_has_tec_from_tec_flag(self) -> None:
        assert self._cam_with_flags(self._FLAG_TEC)["has_tec"] is True

    def test_has_tec_from_tec_onoff_flag(self) -> None:
        assert self._cam_with_flags(self._FLAG_TEC_ONOFF)["has_tec"] is True

    def test_has_tec_false(self) -> None:
        assert self._cam_with_flags(0)["has_tec"] is False

    def test_has_fan_true(self) -> None:
        assert self._cam_with_flags(self._FLAG_FAN)["has_fan"] is True

    def test_has_fan_false(self) -> None:
        assert self._cam_with_flags(0)["has_fan"] is False

    def test_has_raw16_true(self) -> None:
        assert self._cam_with_flags(self._FLAG_RAW16)["has_raw16"] is True

    def test_has_raw16_false(self) -> None:
        assert self._cam_with_flags(0)["has_raw16"] is False

    def test_combined_flags(self) -> None:
        flags = self._FLAG_TEC | self._FLAG_USB30 | self._FLAG_RAW16
        cam = self._cam_with_flags(flags)
        assert cam["has_tec"] is True
        assert cam["usb3"] is True
        assert cam["has_raw16"] is True
        assert cam["has_fan"] is False


# ── display_label and sdk_index ───────────────────────────────────────────────


class TestDisplayLabel:
    def _get_cameras(self, devices: list[SimpleNamespace]) -> list[dict]:  # type: ignore[type-arg]
        tc = _make_toupcam_mock(devices)
        with patch.dict(sys.modules, {"toupcam": tc}):
            return client.get("/api/cameras").json()["cameras"]

    def test_single_camera_label_is_model_name(self) -> None:
        dev = _make_device(model=_make_model(name="ATR585M"))
        cams = self._get_cameras([dev])
        assert cams[0]["display_label"] == "ATR585M"

    def test_single_camera_sdk_index_is_zero(self) -> None:
        cams = self._get_cameras([_make_device()])
        assert cams[0]["sdk_index"] == 0

    def test_two_different_models_no_suffix(self) -> None:
        devs = [
            _make_device(model=_make_model(name="ATR585M")),
            _make_device(model=_make_model(name="G3M678M")),
        ]
        cams = self._get_cameras(devs)
        assert cams[0]["display_label"] == "ATR585M"
        assert cams[1]["display_label"] == "G3M678M"

    def test_duplicate_models_get_numbered_suffix(self) -> None:
        devs = [
            _make_device(model=_make_model(name="G3M678M")),
            _make_device(model=_make_model(name="G3M678M")),
        ]
        cams = self._get_cameras(devs)
        assert cams[0]["display_label"] == "G3M678M (1)"
        assert cams[1]["display_label"] == "G3M678M (2)"

    def test_sdk_index_matches_enumeration_order(self) -> None:
        devs = [_make_device("A"), _make_device("B"), _make_device("C")]
        cams = self._get_cameras(devs)
        assert [c["sdk_index"] for c in cams] == [0, 1, 2]

    def test_mixed_models_only_duplicates_get_suffix(self) -> None:
        devs = [
            _make_device(model=_make_model(name="ATR585M")),
            _make_device(model=_make_model(name="G3M678M")),
            _make_device(model=_make_model(name="G3M678M")),
        ]
        cams = self._get_cameras(devs)
        assert cams[0]["display_label"] == "ATR585M"
        assert cams[1]["display_label"] == "G3M678M (1)"
        assert cams[2]["display_label"] == "G3M678M (2)"


# ── /api/cameras/{index}/capabilities ─────────────────────────────────────────


class TestCameraCapabilities:
    @pytest.fixture(autouse=True)
    def _reset(self) -> None:
        deps.reset()
        yield
        deps.reset()

    def test_returns_200_with_mock_camera(self) -> None:
        resp = client.get("/api/cameras/0/capabilities")
        assert resp.status_code == 200

    def test_response_has_gain_range(self) -> None:
        data = client.get("/api/cameras/0/capabilities").json()
        assert "min_gain" in data
        assert "max_gain" in data
        assert data["min_gain"] <= data["max_gain"]

    def test_response_has_exposure_range_in_seconds(self) -> None:
        data = client.get("/api/cameras/0/capabilities").json()
        assert "min_exposure_s" in data
        assert "max_exposure_s" in data
        assert data["max_exposure_s"] > data["min_exposure_s"]

    def test_response_has_sensor_info(self) -> None:
        data = client.get("/api/cameras/0/capabilities").json()
        assert data["sensor_width_px"] > 0
        assert data["sensor_height_px"] > 0
        assert data["bit_depth"] in (8, 12, 14, 16)

    def test_index_out_of_range_returns_422(self) -> None:
        resp = client.get("/api/cameras/8/capabilities")
        assert resp.status_code == 422

    def test_mock_camera_gain_range(self) -> None:
        data = client.get("/api/cameras/0/capabilities").json()
        assert data["min_gain"] == 100
        assert data["max_gain"] == 3200

    def test_mock_camera_max_exposure_is_60s(self) -> None:
        data = client.get("/api/cameras/0/capabilities").json()
        # MockCamera max_exposure_ms = 60_000 ms = 60 s
        assert data["max_exposure_s"] == pytest.approx(60.0)


# ── UI and health ──────────────────────────────────────────────────────────────


class TestAppRoutes:
    def test_ui_returns_200(self) -> None:
        assert client.get("/").status_code == 200

    def test_ui_returns_html(self) -> None:
        resp = client.get("/")
        assert "text/html" in resp.headers["content-type"]

    def test_ui_contains_scan_button(self) -> None:
        assert "scan" in client.get("/").text.lower()

    def test_health_still_works(self) -> None:
        assert client.get("/health").json() == {"status": "ok"}
