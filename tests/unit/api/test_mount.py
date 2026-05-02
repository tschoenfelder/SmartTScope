"""Unit tests for mount API endpoints — no hardware required."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from smart_telescope.api import deps
from smart_telescope.app import app
from smart_telescope.domain.solar import SolarPosition
from smart_telescope.ports.mount import MountPort, MountPosition, MountState

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
) -> MagicMock:
    m = MagicMock(spec=MountPort)
    m.get_state.return_value = state
    m.get_position.return_value = MountPosition(ra=ra, dec=dec)
    m.unpark.return_value = unpark_ok
    m.enable_tracking.return_value = track_ok
    m.goto.return_value = goto_ok
    m.park.return_value = park_ok
    m.disable_tracking.return_value = disable_tracking_ok
    return m


@pytest.fixture(autouse=True)
def _reset_deps() -> None:
    deps.reset()
    yield
    app.dependency_overrides.clear()
    deps.reset()


def _inject(mount: MagicMock) -> None:
    app.dependency_overrides[deps.get_mount] = lambda: mount


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

    def test_ra_dec_none_when_parked(self) -> None:
        m = _mock_mount(state=MountState.PARKED)
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


# ── POST /api/mount/unpark ─────────────────────────────────────────────────────


class TestMountUnpark:
    def test_returns_200_on_success(self) -> None:
        _inject(_mock_mount(unpark_ok=True))
        assert client.post("/api/mount/unpark").status_code == 200

    def test_returns_ok_true_on_success(self) -> None:
        _inject(_mock_mount(unpark_ok=True))
        assert client.post("/api/mount/unpark").json() == {"ok": True}

    def test_returns_500_when_unpark_fails(self) -> None:
        _inject(_mock_mount(unpark_ok=False))
        assert client.post("/api/mount/unpark").status_code == 500

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
        assert client.post("/api/mount/park").status_code == 200

    def test_returns_ok_true(self) -> None:
        _inject(_mock_mount(park_ok=True))
        assert client.post("/api/mount/park").json() == {"ok": True}

    def test_returns_500_when_park_fails(self) -> None:
        _inject(_mock_mount(park_ok=False))
        assert client.post("/api/mount/park").status_code == 500

    def test_calls_park_on_mount(self) -> None:
        m = _mock_mount()
        _inject(m)
        client.post("/api/mount/park")
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


# ── POST /api/mount/goto_and_center ──────────────────────────────────────────


def _inject_all(mount, camera=None, solver=None) -> None:
    from smart_telescope.adapters.mock.camera import MockCamera
    from smart_telescope.adapters.mock.solver import MockSolver
    app.dependency_overrides[deps.get_mount]  = lambda: mount
    app.dependency_overrides[deps.get_camera] = lambda: (camera or MockCamera())
    app.dependency_overrides[deps.get_solver] = lambda: (solver or MockSolver())


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
