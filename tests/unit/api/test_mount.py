"""Unit tests for mount API endpoints — no hardware required."""

import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.raspberry_time_trust import RaspberryTimeTrustSource
from smart_telescope.domain.solar import SolarPosition
from smart_telescope.domain.time_location_status import TimeLocationStatus
from smart_telescope.ports.mount import MountPort, MountPosition, MountState
from smart_telescope.services.device_state import DeviceStateService, MountObservedState

client = TestClient(app)


def _mock_mount(
    state: MountState = MountState.TRACKING,
    ra: float = 5.58,
    dec: float = -5.39,
    unpark_ok: bool = True,
    track_ok: bool = True,
    goto_ok: bool = True,
    park_ok: bool = True,
    disable_tracking_ok: bool = True,
    slewing: bool = False,
) -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.get_state.return_value = state
    m.get_position.return_value = MountPosition(ra=ra, dec=dec)
    m.unpark.return_value = unpark_ok
    m.enable_tracking.return_value = track_ok
    if goto_ok:
        m.goto.return_value = True
    else:
        m.goto.side_effect = RuntimeError("GoTo rejected by OnStep: below horizon (:MS# = '1')")
    m.park.return_value = park_ok
    m.disable_tracking.return_value = disable_tracking_ok
    m.is_slewing.return_value = slewing
    return m


@pytest.fixture(autouse=True)
def _reset_deps() -> None:
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


def _verified_ds(state: MountState = MountState.TRACKING) -> MagicMock:
    """Return a mock DeviceStateService: adapter open, healthy, TL VERIFIED — passes all gates."""
    return _mock_ds_for_status(started=True, state=state, tl_status=TimeLocationStatus.VERIFIED)


def _inject_trusted_raspberry_svc() -> None:
    """Override the raspberry trust service so gated endpoints don't block on real GPSD/NTP."""
    mock_svc = MagicMock()
    mock_svc.evaluate.return_value = RaspberryTimeTrustSource.ONSTEP_COMPARISON
    mock_svc.is_trusted.return_value = True
    app.dependency_overrides[deps.get_raspberry_trust_service] = lambda: mock_svc


def _inject(mount: MagicMock, *, device_state: MagicMock | None = None) -> None:
    app.dependency_overrides[deps.get_mount] = lambda: mount
    if device_state is None:
        # Mirror mount mock's state/position into the device_state so mount_status uses
        # the cache path and returns the same state that was injected via _mock_mount().
        inferred_state = mount.get_state.return_value
        if mount.get_position.side_effect is not None:
            inferred_ra = inferred_dec = None
        else:
            pos = mount.get_position.return_value
            inferred_ra = pos.ra if pos is not None else None
            inferred_dec = pos.dec if pos is not None else None
        if inferred_state == MountState.UNKNOWN:
            inferred_ra = inferred_dec = None
        device_state = _mock_ds_for_status(
            started=True, state=inferred_state, tl_status=TimeLocationStatus.VERIFIED,
            ra=inferred_ra, dec=inferred_dec,
        )
    app.dependency_overrides[deps.get_device_state] = lambda: device_state
    _inject_trusted_raspberry_svc()


# ── GET /api/mount/status ──────────────────────────────────────────────────────


class TestMountStatus:
    def test_returns_200(self) -> None:
        _inject(_mock_mount())
        assert client.get("/api/mount/status").status_code == 200

    def test_state_field_is_lowercase_enum_name(self) -> None:
        _inject(_mock_mount(state=MountState.TRACKING))
        data = client.get("/api/mount/status").json()
        assert data["state"] == "tracking"

    def test_ra_and_dec_present_when_not_parked(self) -> None:
        _inject(_mock_mount(state=MountState.TRACKING, ra=5.58, dec=-5.39))
        data = client.get("/api/mount/status").json()
        assert data["ra"] == pytest.approx(5.58, abs=0.01)
        assert data["dec"] == pytest.approx(-5.39, abs=0.01)

    def test_ra_dec_present_when_parked(self) -> None:
        # PARKED mounts still report park position — RA/Dec are fetched and returned.
        m = _mock_mount(state=MountState.PARKED, ra=5.58, dec=-5.39)
        _inject(m)
        data = client.get("/api/mount/status").json()
        assert data["ra"] == pytest.approx(5.58, abs=0.01)
        assert data["dec"] == pytest.approx(-5.39, abs=0.01)

    def test_ra_dec_none_when_parked_position_fails(self) -> None:
        m = _mock_mount(state=MountState.PARKED)
        m.get_position.side_effect = RuntimeError("no pos")
        _inject(m)
        data = client.get("/api/mount/status").json()
        assert data["ra"] is None
        assert data["dec"] is None

    def test_ra_dec_none_when_unknown(self) -> None:
        m = _mock_mount(state=MountState.UNKNOWN)
        _inject(m)
        data = client.get("/api/mount/status").json()
        assert data["ra"] is None
        assert data["dec"] is None

    def test_unparked_state(self) -> None:
        _inject(_mock_mount(state=MountState.UNPARKED))
        data = client.get("/api/mount/status").json()
        assert data["state"] == "unparked"

    def test_slewing_state(self) -> None:
        _inject(_mock_mount(state=MountState.SLEWING))
        data = client.get("/api/mount/status").json()
        assert data["state"] == "slewing"


# ── GET /api/mount/status — M8-004 new fields ────────────────────────────────


def _mock_ds_for_status(
    started: bool = True,
    state: MountState = MountState.TRACKING,
    error: str | None = None,
    tl_status: TimeLocationStatus = TimeLocationStatus.VERIFIED,
    ra: float | None = 5.58,
    dec: float | None = -5.39,
) -> MagicMock:
    """Return a DeviceStateService mock configured for M8-004 status field tests."""
    observed = MountObservedState(
        state=state, ra=ra, dec=dec, polled_at=time.monotonic(), error=error
    ) if started else None
    m = MagicMock(spec=DeviceStateService)
    m.is_started.return_value = started
    m.get_mount_state.return_value = observed
    m.get_time_location_status.return_value = tl_status
    m.get_last_command.return_value = (None, None, None)
    m.get_watchdog_warning.return_value = None
    return m


class TestMountStatusM8004:
    def test_adapter_open_present_in_response(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status())
        data = client.get("/api/mount/status").json()
        assert "adapter_open" in data

    def test_adapter_open_true_when_poller_running(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(started=True))
        data = client.get("/api/mount/status").json()
        assert data["adapter_open"] is True

    def test_adapter_open_false_when_poller_not_started(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(started=False))
        data = client.get("/api/mount/status").json()
        assert data["adapter_open"] is False

    def test_health_check_ok_true_when_no_error(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(error=None))
        data = client.get("/api/mount/status").json()
        assert data["health_check_ok"] is True

    def test_health_check_ok_false_when_error(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(error="serial timeout"))
        data = client.get("/api/mount/status").json()
        assert data["health_check_ok"] is False

    def test_health_check_ok_none_when_no_observation(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(started=False))
        data = client.get("/api/mount/status").json()
        assert data["health_check_ok"] is None

    def test_connected_true_when_adapter_open_and_health_ok(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(started=True, error=None))
        data = client.get("/api/mount/status").json()
        assert data["connected"] is True

    def test_connected_false_when_adapter_closed(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(started=False))
        data = client.get("/api/mount/status").json()
        assert data["connected"] is False

    def test_connected_false_when_health_check_failed(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(error="hardware fault"))
        data = client.get("/api/mount/status").json()
        assert data["connected"] is False

    def test_park_state_parked(self) -> None:
        _inject(_mock_mount(state=MountState.PARKED), device_state=_mock_ds_for_status(state=MountState.PARKED))
        data = client.get("/api/mount/status").json()
        assert data["park_state"] == "PARKED"

    def test_park_state_unparked_when_unparked(self) -> None:
        _inject(_mock_mount(state=MountState.UNPARKED), device_state=_mock_ds_for_status(state=MountState.UNPARKED))
        data = client.get("/api/mount/status").json()
        assert data["park_state"] == "UNPARKED"

    def test_park_state_unparked_when_tracking(self) -> None:
        _inject(_mock_mount(state=MountState.TRACKING), device_state=_mock_ds_for_status(state=MountState.TRACKING))
        data = client.get("/api/mount/status").json()
        assert data["park_state"] == "UNPARKED"

    def test_park_state_unknown_when_mount_unknown(self) -> None:
        _inject(_mock_mount(state=MountState.UNKNOWN), device_state=_mock_ds_for_status(started=False))
        data = client.get("/api/mount/status").json()
        assert data["park_state"] == "UNKNOWN"

    def test_tracking_state_tracking(self) -> None:
        _inject(_mock_mount(state=MountState.TRACKING), device_state=_mock_ds_for_status(state=MountState.TRACKING))
        data = client.get("/api/mount/status").json()
        assert data["tracking_state"] == "TRACKING"

    def test_tracking_state_not_tracking_when_unparked(self) -> None:
        _inject(_mock_mount(state=MountState.UNPARKED), device_state=_mock_ds_for_status(state=MountState.UNPARKED))
        data = client.get("/api/mount/status").json()
        assert data["tracking_state"] == "NOT_TRACKING"

    def test_tracking_state_not_tracking_when_parked(self) -> None:
        _inject(_mock_mount(state=MountState.PARKED), device_state=_mock_ds_for_status(state=MountState.PARKED))
        data = client.get("/api/mount/status").json()
        assert data["tracking_state"] == "NOT_TRACKING"

    def test_tracking_state_unknown_when_mount_unknown(self) -> None:
        _inject(_mock_mount(state=MountState.UNKNOWN), device_state=_mock_ds_for_status(started=False))
        data = client.get("/api/mount/status").json()
        assert data["tracking_state"] == "UNKNOWN"

    def test_last_error_none_when_no_error(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(error=None))
        data = client.get("/api/mount/status").json()
        assert data["last_error"] is None

    def test_last_error_populated_when_error_in_observed_state(self) -> None:
        _inject(_mock_mount(), device_state=_mock_ds_for_status(error="serial timeout"))
        data = client.get("/api/mount/status").json()
        assert data["last_error"] == "serial timeout"


# ── POST /api/mount/unpark ─────────────────────────────────────────────────────


class TestMountUnpark:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(unpark_ok=True))
        assert client.post("/api/mount/unpark").status_code == 200

    def test_returns_ok_true_on_success(self) -> None:
        _inject(_mock_mount(unpark_ok=True))
        assert client.post("/api/mount/unpark").json() == {"ok": True}

    def test_returns_200_regardless_of_mount_unpark_result(self) -> None:
        # :hU# is fire-and-forget; unpark() always returns True so 200 is always returned.
        _inject(_mock_mount(unpark_ok=False))
        assert client.post("/api/mount/unpark").status_code == 200

    def test_calls_unpark_on_mount(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/unpark")
        m.unpark.assert_called_once()


# ── POST /api/mount/track ──────────────────────────────────────────────────────


class TestMountTrack:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(track_ok=True))
        assert client.post("/api/mount/track").status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount(track_ok=True))
        assert client.post("/api/mount/track").json() == {"ok": True}

    def test_returns_500_when_tracking_fails(self) -> None:
        _inject(_mock_mount(track_ok=False))
        assert client.post("/api/mount/track").status_code == 500

    def test_calls_enable_tracking(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/track")
        m.enable_tracking.assert_called_once()

    def test_auto_unparks_when_parked(self) -> None:
        m = _mock_mount(state=MountState.PARKED)
        _inject(m)
        r = client.post("/api/mount/track")
        m.unpark.assert_called_once()
        assert r.status_code == 200

    def test_returns_500_when_auto_unpark_fails(self) -> None:
        m = _mock_mount(state=MountState.PARKED, unpark_ok=False)
        _inject(m)
        assert client.post("/api/mount/track").status_code == 500


# ── POST /api/mount/stop ───────────────────────────────────────────────────────


class TestMountStop:
    def test_returns_200(self) -> None:
        _inject(_mock_mount())
        assert client.post("/api/mount/stop").status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount())
        assert client.post("/api/mount/stop").json() == {"ok": True}

    def test_calls_stop_on_mount(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/stop")
        m.stop.assert_called_once()


# ── POST /api/mount/goto ───────────────────────────────────────────────────────


class TestMountGoto:
    @pytest.fixture(autouse=True)
    def _bypass_limits(self, monkeypatch):
        monkeypatch.setattr("smart_telescope.api.mount._check_mount_limits", lambda ra, dec: None)

    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(goto_ok=True))
        assert client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39}).status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount(goto_ok=True))
        data = client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39}).json()
        assert data == {"ok": True}

    def test_returns_500_when_goto_fails(self) -> None:
        _inject(_mock_mount(goto_ok=False))
        assert client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39}).status_code == 500

    def test_calls_goto_with_ra_dec(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39})
        m.goto.assert_called_once_with(
            pytest.approx(5.58, abs=0.01), pytest.approx(-5.39, abs=0.01)
        )

    def test_returns_422_when_body_missing(self) -> None:
        _inject(_mock_mount())
        assert client.post("/api/mount/goto", json={}).status_code == 422

    def test_returns_409_when_already_slewing(self) -> None:
        _inject(_mock_mount(slewing=True))
        assert client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39}).status_code == 409

    # ── M10-025: keep_tracking_state ─────────────────────────────────────────

    def test_keep_tracking_state_default_false_unchanged(self) -> None:
        m = _mock_mount(state=MountState.UNPARKED)
        _inject(m)
        r = client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39})
        assert r.status_code == 200
        m.get_state.assert_not_called()

    def test_keep_tracking_state_restores_tracking_off_after_slew(self) -> None:
        m = _mock_mount(state=MountState.UNPARKED)
        m.get_state.side_effect = [
            MountState.UNPARKED,  # pre-slew check
            MountState.TRACKING,  # poll: slew already done, firmware auto-tracked
        ]
        _inject(m)
        with patch("smart_telescope.services.mount_operations.time") as mock_time:
            mock_time.monotonic.side_effect = [0.0, 0.5]
            r = client.post("/api/mount/goto", json={
                "ra": 5.58, "dec": -5.39, "keep_tracking_state": True,
            })
        assert r.status_code == 200
        m.disable_tracking.assert_called_once()

    def test_keep_tracking_state_skips_restore_when_already_tracking(self) -> None:
        m = _mock_mount(state=MountState.TRACKING)
        _inject(m)
        r = client.post("/api/mount/goto", json={
            "ra": 5.58, "dec": -5.39, "keep_tracking_state": True,
        })
        assert r.status_code == 200
        m.disable_tracking.assert_not_called()


# ── Solar gate tests ───────────────────────────────────────────────────────────

_SUN_AT = SolarPosition(ra_hours=6.0, dec_deg=23.0)
_SOLAR_RA = 6.0
_SOLAR_DEC = 23.0
_SAFE_RA = 18.0   # 180° away — always safe


def _sun_mock(pos: SolarPosition = _SUN_AT):
    return patch("smart_telescope.api.mount.is_solar_target", wraps=_patched_is_solar(pos))


def _patched_is_solar(sun: SolarPosition):
    from smart_telescope.domain.solar import is_solar_target as _real

    def _inner(ra: float, dec: float, **kw):
        return _real(ra, dec, sun=sun, **kw)

    return _inner


class TestMountGotoSolarGate:
    @pytest.fixture(autouse=True)
    def _bypass_limits(self, monkeypatch):
        monkeypatch.setattr("smart_telescope.api.mount._check_mount_limits", lambda ra, dec: None)

    def test_solar_target_returns_403(self) -> None:
        _inject(_mock_mount())
        with patch(
            "smart_telescope.api.mount.is_solar_target",
            return_value=(True, 3.5),
        ):
            r = client.post("/api/mount/goto", json={"ra": _SOLAR_RA, "dec": _SOLAR_DEC})
        assert r.status_code == 403

    def test_solar_403_body_contains_error_key(self) -> None:
        _inject(_mock_mount())
        with patch(
            "smart_telescope.api.mount.is_solar_target",
            return_value=(True, 3.5),
        ):
            r = client.post("/api/mount/goto", json={"ra": _SOLAR_RA, "dec": _SOLAR_DEC})
        assert r.json()["detail"]["error"] == "solar_exclusion"

    def test_solar_403_body_contains_separation(self) -> None:
        _inject(_mock_mount())
        with patch(
            "smart_telescope.api.mount.is_solar_target",
            return_value=(True, 3.5),
        ):
            r = client.post("/api/mount/goto", json={"ra": _SOLAR_RA, "dec": _SOLAR_DEC})
        assert r.json()["detail"]["sun_separation_deg"] == pytest.approx(3.5, abs=0.01)

    def test_safe_target_passes_gate(self) -> None:
        _inject(_mock_mount())
        with patch(
            "smart_telescope.api.mount.is_solar_target",
            return_value=(False, 120.0),
        ):
            r = client.post("/api/mount/goto", json={"ra": _SAFE_RA, "dec": 0.0})
        assert r.status_code == 200

    def test_confirm_solar_bypasses_gate(self) -> None:
        _inject(_mock_mount())
        r = client.post(
            "/api/mount/goto?confirm_solar=true",
            json={"ra": _SOLAR_RA, "dec": _SOLAR_DEC},
        )
        assert r.status_code == 200

    def test_confirm_solar_skips_is_solar_target_call(self) -> None:
        _inject(_mock_mount())
        with patch("smart_telescope.api.mount.is_solar_target") as mock_gate:
            client.post(
                "/api/mount/goto?confirm_solar=true",
                json={"ra": _SOLAR_RA, "dec": _SOLAR_DEC},
            )
        mock_gate.assert_not_called()

    def test_goto_not_called_when_solar_blocked(self) -> None:
        m = _mock_mount()
        _inject(m)
        with patch(
            "smart_telescope.api.mount.is_solar_target",
            return_value=(True, 3.5),
        ):
            client.post("/api/mount/goto", json={"ra": _SOLAR_RA, "dec": _SOLAR_DEC})
        m.goto.assert_not_called()


# ── POST /api/mount/park ───────────────────────────────────────────────────────


class TestMountPark:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(park_ok=True))
        assert client.post("/api/mount/park", json={"confirmed": True}).status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount(park_ok=True))
        assert client.post("/api/mount/park", json={"confirmed": True}).json() == {"ok": True}

    def test_returns_500_when_park_fails(self) -> None:
        _inject(_mock_mount(park_ok=False))
        assert client.post("/api/mount/park", json={"confirmed": True}).status_code == 500

    def test_calls_park_on_mount(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/park", json={"confirmed": True})
        m.park.assert_called_once()


# ── POST /api/mount/disable_tracking ──────────────────────────────────────────


class TestMountDisableTracking:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(disable_tracking_ok=True))
        assert client.post("/api/mount/disable_tracking").status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount(disable_tracking_ok=True))
        assert client.post("/api/mount/disable_tracking").json() == {"ok": True}

    def test_returns_500_when_disable_fails(self) -> None:
        _inject(_mock_mount(disable_tracking_ok=False))
        assert client.post("/api/mount/disable_tracking").status_code == 500

    def test_calls_disable_tracking_on_mount(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/disable_tracking")
        m.disable_tracking.assert_called_once()


# ── POST /api/mount/goto_sky ───────────────────────────────────────────────────

_FIXED_LST = 12.345  # hours — arbitrary but deterministic


def _mock_time(lst_hours: float = _FIXED_LST):
    """Return a patch context that makes Time.now().sidereal_time(...).hour == lst_hours."""
    mock_lst = MagicMock()
    mock_lst.hour = lst_hours
    mock_now = MagicMock()
    mock_now.sidereal_time.return_value = mock_lst
    return patch("smart_telescope.api.mount.Time") , mock_now


class TestMountGotoSky:
    def _inject_safe(self):
        m = _mock_mount()
        _inject(m)
        return m

    def test_returns_200_on_success(self) -> None:
        m = self._inject_safe()
        time_patch, mock_now = _mock_time()
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                r = client.post("/api/mount/goto_sky?elevation=80")
        assert r.status_code == 200

    def test_response_has_required_fields(self) -> None:
        m = self._inject_safe()
        time_patch, mock_now = _mock_time()
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                data = client.post("/api/mount/goto_sky?elevation=80").json()
        assert {"ra", "dec", "elevation_deg", "lst_hours"} <= data.keys()

    def test_lst_returned_in_response(self) -> None:
        m = self._inject_safe()
        time_patch, mock_now = _mock_time(_FIXED_LST)
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                data = client.post("/api/mount/goto_sky?elevation=80").json()
        assert data["lst_hours"] == pytest.approx(_FIXED_LST, abs=0.001)

    def test_dec_computed_from_lat_and_elevation(self) -> None:
        # Dec = OBSERVER_LAT - (90 - elevation) = 50.336 - 10 = 40.336 at elevation=80
        m = self._inject_safe()
        time_patch, mock_now = _mock_time()
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                data = client.post("/api/mount/goto_sky?elevation=80").json()
        assert data["dec"] == pytest.approx(50.336 - (90.0 - 80.0), abs=0.01)

    def test_elevation_below_60_returns_422(self) -> None:
        self._inject_safe()
        r = client.post("/api/mount/goto_sky?elevation=59")
        assert r.status_code == 422

    def test_elevation_above_89_returns_422(self) -> None:
        self._inject_safe()
        r = client.post("/api/mount/goto_sky?elevation=90")
        assert r.status_code == 422

    def test_calls_goto_on_mount(self) -> None:
        m = self._inject_safe()
        time_patch, mock_now = _mock_time(_FIXED_LST)
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                client.post("/api/mount/goto_sky?elevation=80")
        m.goto.assert_called_once()

    def test_solar_blocked_returns_403(self) -> None:
        self._inject_safe()
        time_patch, mock_now = _mock_time()
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(True, 4.0)):
                r = client.post("/api/mount/goto_sky?elevation=80")
        assert r.status_code == 403

    def test_goto_failure_returns_500(self) -> None:
        m = _mock_mount(goto_ok=False)
        _inject(m)
        time_patch, mock_now = _mock_time()
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                r = client.post("/api/mount/goto_sky?elevation=80")
        assert r.status_code == 500

    def test_auto_unparks_when_parked(self) -> None:
        m = _mock_mount(state=MountState.PARKED)
        _inject(m)
        time_patch, mock_now = _mock_time()
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                r = client.post("/api/mount/goto_sky?elevation=80")
        m.unpark.assert_called_once()
        assert r.status_code == 200

    def test_no_unpark_when_already_tracking(self) -> None:
        m = _mock_mount(state=MountState.TRACKING)
        _inject(m)
        time_patch, mock_now = _mock_time()
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                client.post("/api/mount/goto_sky?elevation=80")
        m.unpark.assert_not_called()

    def test_auto_unpark_failure_returns_500(self) -> None:
        m = _mock_mount(state=MountState.PARKED, park_ok=True, unpark_ok=False)
        _inject(m)
        time_patch, mock_now = _mock_time()
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                r = client.post("/api/mount/goto_sky?elevation=80")
        assert r.status_code == 500


# ── POST /api/mount/sync ──────────────────────────────────────────────────────


class TestMountSync:
    def test_returns_200(self) -> None:
        m = _mock_mount()
        m.sync.return_value = True
        _inject(m)
        assert client.post("/api/mount/sync", json={"ra": 5.5881, "dec": -5.391}).status_code == 200

    def test_returns_ok_true(self) -> None:
        m = _mock_mount()
        m.sync.return_value = True
        _inject(m)
        assert client.post("/api/mount/sync", json={"ra": 5.5881, "dec": -5.391}).json() == {"ok": True}

    def test_calls_sync_with_coordinates(self) -> None:
        m = _mock_mount()
        m.sync.return_value = True
        _inject(m)
        client.post("/api/mount/sync", json={"ra": 5.5881, "dec": -5.391})
        m.sync.assert_called_once_with(5.5881, -5.391)

    def test_returns_500_when_sync_fails(self) -> None:
        m = _mock_mount()
        m.sync.return_value = False
        _inject(m)
        assert client.post("/api/mount/sync", json={"ra": 5.5881, "dec": -5.391}).status_code == 500

    def test_returns_422_when_body_missing(self) -> None:
        m = _mock_mount()
        m.sync.return_value = True
        _inject(m)
        assert client.post("/api/mount/sync", json={}).status_code == 422


# ── POST /api/mount/sync_clock ───────────────────────────────────────────────


class TestMountSyncClock:
    def test_returns_200_and_ok(self) -> None:
        m = _mock_mount()
        _inject(m)
        resp = client.post("/api/mount/sync_clock")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["time_location_status"] == "VERIFIED"

    def test_calls_ensure_time_location_synced(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/sync_clock")
        m.ensure_time_location_synced.assert_called_once()

    def test_returns_500_when_sync_raises(self) -> None:
        m = _mock_mount()
        m.ensure_time_location_synced.side_effect = RuntimeError("system clock not sane")
        _inject(m)
        assert client.post("/api/mount/sync_clock").status_code == 500


# ── POST /api/mount/confirm_time ─────────────────────────────────────────────


class TestMountConfirmTime:
    def test_confirm_time_returns_ok(self) -> None:
        _inject(_mock_mount())
        resp = client.post("/api/mount/confirm_time")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["raspberry_trust_source"] == "USER_CONFIRMED"

    def test_confirm_time_sets_user_confirmed(self) -> None:
        ds = _verified_ds()
        _inject(_mock_mount(), device_state=ds)
        client.post("/api/mount/confirm_time")
        ds.set_user_time_confirmed.assert_called_once_with(True)


# ── POST /api/mount/goto — command history (M8-013 / REQ-GOTO-001) ───────────


_LIMITS_PATH = "smart_telescope.api.mount._check_mount_limits"


def _inject_with_history(
    mount: MagicMock,
    *,
    device_state: MagicMock | None = None,
    svc: "CommandHistoryService | None" = None,
) -> "CommandHistoryService":
    from smart_telescope.services.command_history import CommandHistoryService as _CHS
    history = svc or _CHS(session_id="test")
    _inject(mount, device_state=device_state)
    app.dependency_overrides[deps.get_command_history_service] = lambda: history
    return history


class TestGotoCommandHistory:
    def test_successful_goto_recorded_issued_then_succeeded(self) -> None:
        from unittest.mock import patch
        history = _inject_with_history(_mock_mount())
        with patch(_LIMITS_PATH):
            client.post("/api/mount/goto", json={"ra": 5.5, "dec": -5.3})
        records = history.get_all()
        assert len(records) == 1
        assert records[0].status.value == "SUCCEEDED"

    def test_goto_initially_requested_then_updated(self) -> None:
        from unittest.mock import patch
        history = _inject_with_history(_mock_mount())
        with patch(_LIMITS_PATH):
            resp = client.post("/api/mount/goto", json={"ra": 5.5, "dec": -5.3})
        assert resp.status_code == 200
        rec = history.get_all()[0]
        assert rec.user_action == "goto"
        assert rec.requested_parameters["ra"] == 5.5

    def test_gate_blocked_goto_recorded_as_rejected(self) -> None:
        m = _mock_mount()
        ds = _mock_ds_for_status(started=False)  # adapter CLOSED → gate blocks
        history = _inject_with_history(m, device_state=ds)
        resp = client.post("/api/mount/goto", json={"ra": 5.5, "dec": -5.3})
        assert resp.status_code == 409
        rec = history.get_all()[0]
        assert rec.status.value == "REJECTED"
        assert rec.reason_code == "ADAPTER_DISCONNECTED"

    def test_mount_limit_rejection_recorded(self) -> None:
        from unittest.mock import patch
        from fastapi import HTTPException as _HTTPException
        m = _mock_mount()
        history = _inject_with_history(m)
        with patch(_LIMITS_PATH, side_effect=_HTTPException(status_code=400, detail={"reason": "below_horizon"})):
            resp = client.post("/api/mount/goto", json={"ra": 0.0, "dec": -89.0})
        assert resp.status_code == 400
        rec = history.get_all()[0]
        assert rec.status.value == "REJECTED"
        assert rec.reason_code == "MOUNT_LIMIT"

    def test_bright_star_uses_bright_star_goto_operation(self) -> None:
        from unittest.mock import patch
        history = _inject_with_history(_mock_mount())
        with patch(_LIMITS_PATH):
            client.post("/api/mount/goto?bright_star=true", json={"ra": 5.5, "dec": -5.3})
        rec = history.get_all()[0]
        assert rec.operation == "bright_star_goto"


# ── POST /api/mount/goto_and_center ──────────────────────────────────────────


def _inject_all(mount, camera=None, solver=None) -> None:
    from smart_telescope.adapters.mock.camera import MockCamera
    from smart_telescope.adapters.mock.solver import MockSolver
    app.dependency_overrides[deps.get_mount]  = lambda: mount
    app.dependency_overrides[deps.get_camera] = lambda: (camera or MockCamera())
    app.dependency_overrides[deps.get_solver] = lambda: (solver or MockSolver())
    app.dependency_overrides[deps.get_device_state] = lambda: _verified_ds()
    _inject_trusted_raspberry_svc()


class TestMountGotoAndCenter:
    @pytest.fixture(autouse=True)
    def _bypass_limits(self, monkeypatch):
        monkeypatch.setattr("smart_telescope.api.mount._check_mount_limits", lambda ra, dec: None)

    def test_returns_200_when_centered(self) -> None:
        from smart_telescope.adapters.mock.solver import MockSolver
        m = _mock_mount()
        m.is_slewing.return_value = False
        _inject_all(m, solver=MockSolver())
        with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
            r = client.post("/api/mount/goto_and_center",
                            json={"ra": 5.5881, "dec": -5.391})
        assert r.status_code == 200

    def test_response_has_required_fields(self) -> None:
        from smart_telescope.adapters.mock.solver import MockSolver
        m = _mock_mount()
        m.is_slewing.return_value = False
        _inject_all(m, solver=MockSolver())
        with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
            data = client.post("/api/mount/goto_and_center",
                               json={"ra": 5.5881, "dec": -5.391}).json()
        for key in ("success", "final_ra", "final_dec", "iterations", "offset_arcmin"):
            assert key in data

    def test_solar_exclusion_returns_403(self) -> None:
        m = _mock_mount()
        _inject_all(m)
        with patch("smart_telescope.api.mount.is_solar_target", return_value=(True, 2.0)):
            r = client.post("/api/mount/goto_and_center",
                            json={"ra": 5.5881, "dec": -5.391})
        assert r.status_code == 403

    def test_zero_exposure_returns_422(self) -> None:
        m = _mock_mount()
        _inject_all(m)
        r = client.post("/api/mount/goto_and_center",
                        json={"ra": 5.5881, "dec": -5.391, "exposure": 0})
        assert r.status_code == 422

    def test_iterations_above_5_returns_422(self) -> None:
        m = _mock_mount()
        _inject_all(m)
        r = client.post("/api/mount/goto_and_center",
                        json={"ra": 5.5881, "dec": -5.391, "max_iterations": 6})
        assert r.status_code == 422


# ── Mount position limits ──────────────────────────────────────────────────────
# Observer: lat=50.336°N. Tests use _mock_time() to fix LST for deterministic HA.
# sin(alt) = sin(lat)*sin(dec) + cos(lat)*cos(dec)*cos(HA*15°)

_LIMIT_LST = 6.0  # fixed sidereal time for limit tests


class TestMountLimits:
    def _post_goto(self, ra: float, dec: float):
        _inject(_mock_mount())
        time_patch, mock_now = _mock_time(_LIMIT_LST)
        with time_patch as mock_time_cls:
            mock_time_cls.now.return_value = mock_now
            with patch("smart_telescope.api.mount.is_solar_target", return_value=(False, 120.0)):
                return client.post("/api/mount/goto", json={"ra": ra, "dec": dec})

    def test_ha_east_limit_returns_400(self) -> None:
        # LST=6, RA=12 → HA = 6-12 = -6h < east limit of -5.5h
        r = self._post_goto(ra=12.0, dec=20.0)
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "mount_limit"
        assert r.json()["detail"]["reason"] == "hour_angle_east"

    def test_counterweight_up_returns_400(self) -> None:
        # LST=6, RA=5 → HA = 6-5 = 1h > west limit of 0.333h
        r = self._post_goto(ra=5.0, dec=20.0)
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "mount_limit"
        assert r.json()["detail"]["reason"] == "counterweight_up"

    def test_below_horizon_returns_400(self) -> None:
        # LST=6, RA=6 → HA=0; dec=-50° → alt ≈ -10.2° < MOUNT_MIN_ALT_DEG=10°
        r = self._post_goto(ra=6.0, dec=-50.0)
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "mount_limit"
        assert r.json()["detail"]["reason"] == "below_horizon"

    def test_zenith_exclusion_returns_400(self) -> None:
        # LST=6, RA=6 → HA=0; dec=50° → alt ≈ 89.7° > MOUNT_MAX_ALT_DEG=88°
        r = self._post_goto(ra=6.0, dec=50.0)
        assert r.status_code == 400
        assert r.json()["detail"]["error"] == "mount_limit"
        assert r.json()["detail"]["reason"] == "zenith_exclusion"

    def test_valid_target_passes(self) -> None:
        # LST=6, RA=6 → HA=0; dec=20° → alt ≈ 59.7° — well within all limits
        r = self._post_goto(ra=6.0, dec=20.0)
        assert r.status_code == 200


# ── GET /api/mount/config ──────────────────────────────────────────────────────


class TestMountConfig:
    def test_returns_200(self) -> None:
        assert client.get("/api/mount/config").status_code == 200

    def test_contains_observer_coords(self) -> None:
        data = client.get("/api/mount/config").json()
        assert "observer_lat" in data
        assert "observer_lon" in data

    def test_contains_all_limit_fields(self) -> None:
        data = client.get("/api/mount/config").json()
        for key in ("mount_min_alt_deg", "mount_max_alt_deg",
                    "mount_ha_east_limit_h", "mount_ha_west_limit_h"):
            assert key in data, f"missing field: {key}"

    def test_values_are_floats(self) -> None:
        data = client.get("/api/mount/config").json()
        for key, val in data.items():
            assert isinstance(val, float), f"{key} should be float, got {type(val)}"


# ── POST /api/mount/align/* ────────────────────────────────────────────────────


class TestMountAlign:
    def _inject_align_mount(
        self,
        start_ok: bool = True,
        accept_ok: bool = True,
        save_ok: bool = True,
    ) -> MagicMock:
        m = _mock_mount()
        m.start_alignment.return_value = start_ok
        m.accept_alignment_star.return_value = accept_ok
        m.save_alignment.return_value = save_ok
        _inject(m)
        return m

    def test_align_start_200(self) -> None:
        self._inject_align_mount()
        assert client.post("/api/mount/align/start", json={"num_stars": 2}).status_code == 200

    def test_align_start_passes_num_stars(self) -> None:
        m = self._inject_align_mount()
        client.post("/api/mount/align/start", json={"num_stars": 3})
        m.start_alignment.assert_called_once_with(3)

    def test_align_start_default_one_star(self) -> None:
        m = self._inject_align_mount()
        client.post("/api/mount/align/start", json={})
        m.start_alignment.assert_called_once_with(1)

    def test_align_start_500_on_failure(self) -> None:
        self._inject_align_mount(start_ok=False)
        assert client.post("/api/mount/align/start", json={"num_stars": 1}).status_code == 500

    def test_align_accept_200(self) -> None:
        self._inject_align_mount()
        assert client.post("/api/mount/align/accept").status_code == 200

    def test_align_accept_500_on_failure(self) -> None:
        self._inject_align_mount(accept_ok=False)
        assert client.post("/api/mount/align/accept").status_code == 500

    def test_align_accept_calls_mount(self) -> None:
        m = self._inject_align_mount()
        client.post("/api/mount/align/accept")
        m.accept_alignment_star.assert_called_once()

    def test_align_save_200(self) -> None:
        self._inject_align_mount()
        assert client.post("/api/mount/align/save").status_code == 200

    def test_align_save_500_on_failure(self) -> None:
        self._inject_align_mount(save_ok=False)
        assert client.post("/api/mount/align/save").status_code == 500

    def test_align_save_calls_mount(self) -> None:
        m = self._inject_align_mount()
        client.post("/api/mount/align/save")
        m.save_alignment.assert_called_once()


# ── POST /api/mount/guide ──────────────────────────────────────────────────────


class TestMountGuide:
    def _inject_guide_mount(
        self,
        state: MountState = MountState.TRACKING,
        guide_ok: bool = True,
        track_ok: bool = True,
    ) -> MagicMock:
        m = _mock_mount(state=state, track_ok=track_ok)
        m.guide.return_value = guide_ok
        _inject(m)
        return m

    def test_tracking_state_sends_pulse(self) -> None:
        m = self._inject_guide_mount(state=MountState.TRACKING)
        r = client.post("/api/mount/guide", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 200
        m.guide.assert_called_once_with("n", 500)

    def test_tracking_state_skips_enable_tracking(self) -> None:
        m = self._inject_guide_mount(state=MountState.TRACKING)
        client.post("/api/mount/guide", json={"direction": "n", "duration_ms": 500})
        m.enable_tracking.assert_not_called()

    def test_all_directions_accepted(self) -> None:
        for d in ("n", "s", "e", "w", "N", "S", "E", "W"):
            m = self._inject_guide_mount()
            r = client.post("/api/mount/guide", json={"direction": d, "duration_ms": 200})
            assert r.status_code == 200, f"direction {d!r} rejected"

    def test_unparked_auto_enables_tracking_then_guides(self) -> None:
        m = self._inject_guide_mount(state=MountState.UNPARKED, track_ok=True)
        r = client.post("/api/mount/guide", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 200
        m.enable_tracking.assert_called_once()
        m.guide.assert_called_once()

    def test_unparked_tracking_enable_failure_returns_503(self) -> None:
        m = self._inject_guide_mount(state=MountState.UNPARKED, track_ok=False)
        r = client.post("/api/mount/guide", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 503

    def test_parked_returns_409(self) -> None:
        m = self._inject_guide_mount(state=MountState.PARKED)
        r = client.post("/api/mount/guide", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 409
        assert "parked" in r.json()["detail"].lower()

    def test_slewing_returns_409(self) -> None:
        m = self._inject_guide_mount(state=MountState.SLEWING)
        r = client.post("/api/mount/guide", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 409
        assert "slewing" in r.json()["detail"].lower()

    def test_guide_failure_returns_500(self) -> None:
        m = self._inject_guide_mount(state=MountState.TRACKING, guide_ok=False)
        r = client.post("/api/mount/guide", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 500

    def test_invalid_direction_returns_422(self) -> None:
        self._inject_guide_mount()
        r = client.post("/api/mount/guide", json={"direction": "x", "duration_ms": 500})
        assert r.status_code == 422


class TestMountNudge:
    def _inject_nudge_mount(
        self,
        state: MountState = MountState.TRACKING,
        move_ok: bool = True,
        track_ok: bool = True,
    ) -> MagicMock:
        m = _mock_mount(state=state, track_ok=track_ok)
        m.move.return_value = move_ok
        _inject(m)
        return m

    def test_tracking_state_moves(self) -> None:
        m = self._inject_nudge_mount(state=MountState.TRACKING)
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 200
        m.move.assert_called_once_with("n", 500)

    def test_tracking_state_skips_enable_tracking(self) -> None:
        m = self._inject_nudge_mount(state=MountState.TRACKING)
        client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        m.enable_tracking.assert_not_called()

    def test_all_directions_accepted(self) -> None:
        for d in ("n", "s", "e", "w", "N", "S", "E", "W"):
            m = self._inject_nudge_mount()
            r = client.post("/api/mount/nudge", json={"direction": d, "duration_ms": 200})
            assert r.status_code == 200, f"direction {d!r} rejected"

    def test_unparked_auto_enables_tracking_then_moves(self) -> None:
        m = self._inject_nudge_mount(state=MountState.UNPARKED, track_ok=True)
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 200
        m.enable_tracking.assert_called_once()
        m.move.assert_called_once()

    def test_unparked_tracking_enable_failure_returns_503(self) -> None:
        m = self._inject_nudge_mount(state=MountState.UNPARKED, track_ok=False)
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 503

    def test_parked_returns_409(self) -> None:
        m = self._inject_nudge_mount(state=MountState.PARKED)
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 409
        assert "parked" in r.json()["detail"].lower()

    def test_slewing_returns_409(self) -> None:
        m = self._inject_nudge_mount(state=MountState.SLEWING)
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 409

    def test_move_failure_returns_500(self) -> None:
        m = self._inject_nudge_mount(state=MountState.TRACKING, move_ok=False)
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 500

    def test_invalid_direction_returns_422(self) -> None:
        self._inject_nudge_mount()
        r = client.post("/api/mount/nudge", json={"direction": "x", "duration_ms": 500})
        assert r.status_code == 422

    def test_duration_below_minimum_returns_422(self) -> None:
        self._inject_nudge_mount()
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 10})
        assert r.status_code == 422

    # ── M10-019: keep_tracking_state — terrestrial jog must not start
    #    sidereal tracking ───────────────────────────────────────────────

    def test_keep_tracking_state_skips_enable_tracking(self) -> None:
        m = self._inject_nudge_mount(state=MountState.UNPARKED)
        r = client.post("/api/mount/nudge", json={
            "direction": "n", "duration_ms": 500, "keep_tracking_state": True,
        })
        assert r.status_code == 200
        m.enable_tracking.assert_not_called()
        m.move.assert_called_once_with("n", 500)

    def test_keep_tracking_state_still_blocked_when_parked(self) -> None:
        self._inject_nudge_mount(state=MountState.PARKED)
        r = client.post("/api/mount/nudge", json={
            "direction": "n", "duration_ms": 500, "keep_tracking_state": True,
        })
        assert r.status_code == 409

    def test_default_behavior_unchanged_without_flag(self) -> None:
        m = self._inject_nudge_mount(state=MountState.UNPARKED, track_ok=True)
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 200
        m.enable_tracking.assert_called_once()

    # ── M10-027: at-home axis-motion refusal surfaces as a clean 409 ───────

    def test_at_home_refusal_returns_409_not_500(self) -> None:
        from onstep_adapter.safety import OnStepSafetyError, SafetyViolation
        m = self._inject_nudge_mount(state=MountState.TRACKING)
        m.move.side_effect = OnStepSafetyError(
            SafetyViolation(reason="axis_motion_refused_at_home", command="move")
        )
        r = client.post("/api/mount/nudge", json={"direction": "n", "duration_ms": 500})
        assert r.status_code == 409
        assert r.json()["detail"] == "axis_motion_refused_at_home"


# ── M8-005: Structured 409 gate responses ────────────────────────────────────


class TestMountApiGatedResponses:
    """Gate check returns structured 409 with reason_code/human_message (REQ-GOTO-001, INC-003/005)."""

    @pytest.fixture(autouse=True)
    def _bypass_checks(self, monkeypatch):
        monkeypatch.setattr("smart_telescope.api.mount._check_mount_limits", lambda ra, dec: None)
        monkeypatch.setattr("smart_telescope.api.mount.is_solar_target", lambda ra, dec: (False, 120.0))

    def _closed_ds(self) -> MagicMock:
        return _mock_ds_for_status(started=False, tl_status=TimeLocationStatus.VERIFIED)

    def _unverified_ds(self) -> MagicMock:
        return _mock_ds_for_status(started=True, tl_status=TimeLocationStatus.UNVERIFIED)

    # ── tracking_enable ───────────────────────────────────────────────────────

    def test_track_409_when_adapter_closed(self) -> None:
        _inject(_mock_mount(), device_state=self._closed_ds())
        r = client.post("/api/mount/track")
        assert r.status_code == 409

    def test_track_409_body_has_gate_blocked(self) -> None:
        _inject(_mock_mount(), device_state=self._closed_ds())
        r = client.post("/api/mount/track")
        assert r.json()["detail"].get("gate_blocked") is True

    def test_track_409_reason_code_adapter_disconnected(self) -> None:
        _inject(_mock_mount(), device_state=self._closed_ds())
        r = client.post("/api/mount/track")
        assert r.json()["detail"]["reason_code"] == "ADAPTER_DISCONNECTED"

    def test_track_409_has_human_message_and_action(self) -> None:
        _inject(_mock_mount(), device_state=self._closed_ds())
        detail = client.post("/api/mount/track").json()["detail"]
        assert detail["human_message"]
        assert detail["required_user_action"] == "run_connect_all"

    def test_track_409_when_tl_unverified(self) -> None:
        _inject(_mock_mount(), device_state=self._unverified_ds())
        r = client.post("/api/mount/track")
        assert r.status_code == 409
        assert r.json()["detail"]["reason_code"] == "TIME_LOCATION_UNVERIFIED"

    # ── goto ──────────────────────────────────────────────────────────────────

    def test_goto_409_when_adapter_closed(self) -> None:
        _inject(_mock_mount(), device_state=self._closed_ds())
        r = client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39})
        assert r.status_code == 409
        assert r.json()["detail"].get("gate_blocked") is True

    def test_goto_409_reason_adapter_disconnected(self) -> None:
        _inject(_mock_mount(), device_state=self._closed_ds())
        r = client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39})
        assert r.json()["detail"]["reason_code"] == "ADAPTER_DISCONNECTED"

    def test_goto_command_not_recorded_when_gate_blocks(self) -> None:
        ds = self._closed_ds()
        _inject(_mock_mount(), device_state=ds)
        r = client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39})
        assert r.status_code == 409
        ds.record_command.assert_not_called()

    def test_goto_409_when_tl_unverified(self) -> None:
        _inject(_mock_mount(), device_state=self._unverified_ds())
        r = client.post("/api/mount/goto", json={"ra": 5.58, "dec": -5.39})
        assert r.status_code == 409
        assert r.json()["detail"]["reason_code"] == "TIME_LOCATION_UNVERIFIED"

    # ── sync ──────────────────────────────────────────────────────────────────

    def test_sync_409_when_adapter_closed(self) -> None:
        m = _mock_mount()
        m.sync.return_value = True
        _inject(m, device_state=self._closed_ds())
        r = client.post("/api/mount/sync", json={"ra": 5.58, "dec": -5.39})
        assert r.status_code == 409
        assert r.json()["detail"].get("gate_blocked") is True

    def test_sync_409_when_tl_unverified(self) -> None:
        m = _mock_mount()
        m.sync.return_value = True
        _inject(m, device_state=self._unverified_ds())
        r = client.post("/api/mount/sync", json={"ra": 5.58, "dec": -5.39})
        assert r.status_code == 409
        assert r.json()["detail"]["reason_code"] == "TIME_LOCATION_UNVERIFIED"
