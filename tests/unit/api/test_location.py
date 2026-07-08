"""Unit tests for /api/location/* endpoints — Confirm Time & Location panel."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope import config
from smart_telescope.api import deps
from smart_telescope.api import location as location_module
from smart_telescope.app import app
from smart_telescope.domain.raspberry_time_trust import RaspberryTimeTrustSource
from smart_telescope.ports.mount import MountPort
from smart_telescope.services.device_state import DeviceStateService
from smart_telescope.services.gpsd_service import GpsdFix

client = TestClient(app)

_OBSERVER_KEYS = [
    "OBSERVER_LAT", "OBSERVER_LON", "OBSERVER_HEIGHT_M",
    "OBSERVER_HOME_LAT", "OBSERVER_HOME_LON", "OBSERVER_HOME_HEIGHT_M", "OBSERVER_HOME_NAME",
    "OBSERVER_LOCATION_SOURCE", "OBSERVER_LOCATION_NAME",
]


@pytest.fixture(autouse=True)
def _reset_deps() -> None:
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


@pytest.fixture(autouse=True)
def _snapshot_observer_globals():
    snapshot = {k: getattr(config, k) for k in _OBSERVER_KEYS}
    locations_snapshot = dict(config.LOCATIONS)
    yield
    for k, v in snapshot.items():
        setattr(config, k, v)
    config.LOCATIONS.clear()
    config.LOCATIONS.update(locations_snapshot)


@pytest.fixture()
def cfg_path(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    monkeypatch.setattr(location_module, "_CONFIG_PATH", path)
    return path


def _mock_mount() -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.ensure_time_location_synced.return_value = None
    m.get_sync_status.return_value = None
    return m


def _mock_device_state() -> MagicMock:
    ds = MagicMock(spec=DeviceStateService)
    ds.is_started.return_value = True
    ds.get_mount_state.return_value = None
    ds.is_user_time_confirmed.return_value = False
    return ds


def _inject(
    *,
    mount: MagicMock | None = None,
    device_state: MagicMock | None = None,
    trust_source: RaspberryTimeTrustSource = RaspberryTimeTrustSource.NTP,
) -> None:
    app.dependency_overrides[deps.get_mount] = lambda: (mount or _mock_mount())
    app.dependency_overrides[deps.get_device_state] = lambda: (device_state or _mock_device_state())
    master_svc = MagicMock()
    master_svc.evaluate.return_value = MagicMock()
    app.dependency_overrides[deps.get_master_source_service] = lambda: master_svc
    trust_svc = MagicMock()
    trust_svc.evaluate.return_value = trust_source
    trust_svc.is_trusted.return_value = trust_source != RaspberryTimeTrustSource.NOT_TRUSTED
    app.dependency_overrides[deps.get_raspberry_trust_service] = lambda: trust_svc


# ── GET /api/location/status ───────────────────────────────────────────────────

class TestLocationStatus:
    def test_returns_200_with_expected_shape(self) -> None:
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            resp = client.get("/api/location/status")
        assert resp.status_code == 200
        body = resp.json()
        for field in ("active", "home", "saved_locations", "gps", "local_time_iso",
                      "local_tz_name", "time_from_gps", "time_trust_source"):
            assert field in body

    def test_active_reflects_config_globals(self) -> None:
        config.OBSERVER_LAT, config.OBSERVER_LON, config.OBSERVER_HEIGHT_M = 1.0, 2.0, 3.0
        config.OBSERVER_LOCATION_NAME = "Home"
        config.OBSERVER_LOCATION_SOURCE = "CONFIG_FILE"
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            body = client.get("/api/location/status").json()
        assert body["active"] == {
            "name": "Home", "lat": 1.0, "lon": 2.0, "height_m": 3.0, "source": "CONFIG_FILE",
        }

    def test_home_independent_of_active_after_saved_activation(self) -> None:
        config.OBSERVER_HOME_LAT, config.OBSERVER_HOME_LON, config.OBSERVER_HOME_HEIGHT_M = 50.0, 8.0, 100.0
        config.OBSERVER_LAT, config.OBSERVER_LON, config.OBSERVER_HEIGHT_M = 49.0, 9.0, 200.0
        config.OBSERVER_LOCATION_NAME = "Star Party"
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            body = client.get("/api/location/status").json()
        assert body["home"] == {"lat": 50.0, "lon": 8.0, "height_m": 100.0, "name": "Home"}
        assert body["active"]["name"] == "Star Party"

    def test_home_name_reflects_config(self) -> None:
        config.OBSERVER_HOME_NAME = "Usingen, HE"
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            body = client.get("/api/location/status").json()
        assert body["home"]["name"] == "Usingen, HE"

    def test_saved_locations_reflect_config_locations(self) -> None:
        config.LOCATIONS["foo"] = config.LocationSpec(name="foo", lat=1.0, lon=2.0, height_m=3.0)
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            body = client.get("/api/location/status").json()
        assert {"name": "foo", "lat": 1.0, "lon": 2.0, "height_m": 3.0} in body["saved_locations"]

    def test_gps_unavailable(self) -> None:
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            body = client.get("/api/location/status").json()
        assert body["gps"]["available"] is False

    def test_gps_available_with_fix(self) -> None:
        fix = GpsdFix(lat=50.1, lon=8.1, alt=200.0, gps_time=None, mode=3, hdop=1.0, fix_age_s=10.0)
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=fix):
            body = client.get("/api/location/status").json()
        assert body["gps"]["available"] is True
        assert body["gps"]["lat"] == pytest.approx(50.1)
        assert body["gps"]["alt_m"] == pytest.approx(200.0)

    def test_gps_usable_true_when_fresh_and_mode_at_least_2(self) -> None:
        fix = GpsdFix(lat=50.1, lon=8.1, alt=200.0, gps_time=None, mode=3, hdop=1.0, fix_age_s=10.0)
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=fix):
            body = client.get("/api/location/status").json()
        assert body["gps"]["usable"] is True

    def test_gps_usable_false_when_mode_below_2(self) -> None:
        fix = GpsdFix(lat=50.1, lon=8.1, alt=None, gps_time=None, mode=1, hdop=None, fix_age_s=10.0)
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=fix):
            body = client.get("/api/location/status").json()
        assert body["gps"]["available"] is True
        assert body["gps"]["usable"] is False

    def test_gps_usable_false_when_stale(self) -> None:
        fix = GpsdFix(lat=50.1, lon=8.1, alt=200.0, gps_time=None, mode=3, hdop=1.0, fix_age_s=999999.0)
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=fix):
            body = client.get("/api/location/status").json()
        assert body["gps"]["usable"] is False

    def test_gps_usable_false_when_no_fix(self) -> None:
        _inject()
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            body = client.get("/api/location/status").json()
        assert body["gps"]["usable"] is False

    def test_time_from_gps_true_when_raspberry_trust_is_gpsd_fix(self) -> None:
        _inject(trust_source=RaspberryTimeTrustSource.GPSD_FIX)
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            body = client.get("/api/location/status").json()
        assert body["time_from_gps"] is True

    def test_time_from_gps_false_when_raspberry_trust_is_ntp(self) -> None:
        _inject(trust_source=RaspberryTimeTrustSource.NTP)
        with patch.object(location_module._gpsd, "get_fix", return_value=None):
            body = client.get("/api/location/status").json()
        assert body["time_from_gps"] is False


# ── GET /api/location/ip-lookup ─────────────────────────────────────────────────

class TestIpLookup:
    def test_available_passthrough(self) -> None:
        from smart_telescope.services.ip_geolocation_service import IpGeoResult
        result = IpGeoResult(lat=50.1, lon=8.6, city="Frankfurt", country="Germany", ip="1.2.3.4")
        with patch.object(location_module._ip_geo, "lookup", return_value=result):
            body = client.get("/api/location/ip-lookup").json()
        assert body == {
            "available": True, "lat": 50.1, "lon": 8.6,
            "city": "Frankfurt", "country": "Germany", "ip": "1.2.3.4",
        }

    def test_unavailable_when_lookup_fails(self) -> None:
        with patch.object(location_module._ip_geo, "lookup", return_value=None):
            body = client.get("/api/location/ip-lookup").json()
        assert body["available"] is False


# ── POST /api/location/confirm — target=home ────────────────────────────────────

_OBSERVER_FILE = """[observer]
lat = 50.0
lon = 8.0

[locations.foo]
lat = 1.111
lon = 2.222
height_m = 3.333

[hardware]
onstep_port = ""
"""


class TestConfirmHome:
    def _body(self, **overrides) -> dict:
        body = {"target": "home", "lat": 51.5, "lon": 9.5, "height_m": 250.0, "source": "USER_ENTERED"}
        body.update(overrides)
        return body

    def test_updates_in_memory_active_and_home(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        resp = client.post("/api/location/confirm", json=self._body())
        assert resp.status_code == 200
        assert config.OBSERVER_LAT == pytest.approx(51.5)
        assert config.OBSERVER_HOME_LAT == pytest.approx(51.5)
        assert config.OBSERVER_LOCATION_NAME == "Home"
        assert config.OBSERVER_LOCATION_SOURCE == "USER_ENTERED"

    def test_writes_observer_block_without_touching_locations_block(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        client.post("/api/location/confirm", json=self._body())
        text = cfg_path.read_text(encoding="utf-8")
        assert "lat = 51.5" in text
        assert "lon = 9.5" in text
        assert "height_m = 250.0" in text
        # locations.foo block must be byte-identical to the original
        assert "[locations.foo]\nlat = 1.111\nlon = 2.222\nheight_m = 3.333" in text

    def test_confirm_time_always_called(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        ds = _mock_device_state()
        _inject(device_state=ds)
        client.post("/api/location/confirm", json=self._body())
        ds.set_user_time_confirmed.assert_called_once_with(True)

    def test_mount_sync_raising_does_not_500(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        mount = _mock_mount()
        mount.ensure_time_location_synced.side_effect = RuntimeError("no mount")
        _inject(mount=mount)
        resp = client.post("/api/location/confirm", json=self._body())
        assert resp.status_code == 200

    def test_invalid_source_returns_400(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        resp = client.post("/api/location/confirm", json=self._body(source="NOT_A_SOURCE"))
        assert resp.status_code == 400

    def test_out_of_range_lat_returns_422(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        resp = client.post("/api/location/confirm", json=self._body(lat=999.0))
        assert resp.status_code == 422


# ── POST /api/location/confirm — target=saved ───────────────────────────────────

class TestConfirmSaved:
    def _body(self, **overrides) -> dict:
        body = {
            "target": "saved", "name": "dark_sky_site",
            "lat": 49.9, "lon": 9.1, "height_m": 410.0, "source": "GPS_FIX",
        }
        body.update(overrides)
        return body

    def test_new_name_appends_block(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        resp = client.post("/api/location/confirm", json=self._body())
        assert resp.status_code == 200
        text = cfg_path.read_text(encoding="utf-8")
        assert "[locations.dark_sky_site]" in text
        assert "[locations.foo]" in text  # untouched existing block still present

    def test_existing_name_replaces_block(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        resp = client.post("/api/location/confirm", json=self._body(name="foo", lat=7.0, lon=8.0, height_m=9.0))
        assert resp.status_code == 200
        text = cfg_path.read_text(encoding="utf-8")
        assert "lat = 7.0" in text
        assert text.count("[locations.foo]") == 1

    def test_home_untouched(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        config.OBSERVER_HOME_LAT, config.OBSERVER_HOME_LON, config.OBSERVER_HOME_HEIGHT_M = 50.0, 8.0, 0.0
        _inject()
        client.post("/api/location/confirm", json=self._body())
        assert config.OBSERVER_HOME_LAT == pytest.approx(50.0)
        assert config.OBSERVER_HOME_LON == pytest.approx(8.0)

    def test_active_updated_to_saved_location(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        client.post("/api/location/confirm", json=self._body())
        assert config.OBSERVER_LAT == pytest.approx(49.9)
        assert config.OBSERVER_LOCATION_NAME == "dark_sky_site"

    def test_missing_name_returns_400(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        resp = client.post("/api/location/confirm", json=self._body(name=None))
        assert resp.status_code == 400

    def test_reserved_name_home_returns_400(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        resp = client.post("/api/location/confirm", json=self._body(name="Home"))
        assert resp.status_code == 400

    def test_invalid_characters_in_name_returns_400(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        _inject()
        resp = client.post("/api/location/confirm", json=self._body(name="my site!"))
        assert resp.status_code == 400


# ── DELETE /api/location/saved/{name} ───────────────────────────────────────────

class TestDeleteSaved:
    def test_removes_block_and_normalizes_blank_lines(self, cfg_path) -> None:
        text = (
            "[observer]\nlat = 1.0\nlon = 2.0\n\n"
            "[locations.a]\nlat = 1.0\nlon = 1.0\nheight_m = 0.0\n\n"
            "[locations.b]\nlat = 2.0\nlon = 2.0\nheight_m = 0.0\n\n"
            "[locations.c]\nlat = 3.0\nlon = 3.0\nheight_m = 0.0\n"
        )
        cfg_path.write_text(text, encoding="utf-8")
        config.LOCATIONS["a"] = config.LocationSpec(name="a", lat=1.0, lon=1.0, height_m=0.0)
        config.LOCATIONS["b"] = config.LocationSpec(name="b", lat=2.0, lon=2.0, height_m=0.0)
        config.LOCATIONS["c"] = config.LocationSpec(name="c", lat=3.0, lon=3.0, height_m=0.0)
        resp = client.delete("/api/location/saved/b")
        assert resp.status_code == 200
        after = cfg_path.read_text(encoding="utf-8")
        assert "[locations.b]" not in after
        assert "[locations.a]" in after
        assert "[locations.c]" in after
        assert "\n\n\n" not in after

    def test_404_when_not_found(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        resp = client.delete("/api/location/saved/does_not_exist")
        assert resp.status_code == 404

    def test_400_for_home(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        resp = client.delete("/api/location/saved/Home")
        assert resp.status_code == 400

    def test_deleting_active_saved_location_resets_to_home(self, cfg_path) -> None:
        cfg_path.write_text(_OBSERVER_FILE, encoding="utf-8")
        config.LOCATIONS["foo"] = config.LocationSpec(name="foo", lat=1.111, lon=2.222, height_m=3.333)
        config.OBSERVER_HOME_LAT, config.OBSERVER_HOME_LON, config.OBSERVER_HOME_HEIGHT_M = 50.0, 8.0, 0.0
        config.OBSERVER_LAT, config.OBSERVER_LON, config.OBSERVER_HEIGHT_M = 1.111, 2.222, 3.333
        config.OBSERVER_LOCATION_NAME = "foo"
        client.delete("/api/location/saved/foo")
        assert config.OBSERVER_LOCATION_NAME == "Home"
        assert config.OBSERVER_LAT == pytest.approx(50.0)
