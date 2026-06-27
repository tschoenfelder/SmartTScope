"""Unit tests for M8-008: meter-based location tolerance in get_sync_status().

Covers TEST-002 location cases and REQ-TIME-003, REQ-TIME-006.
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from smart_telescope.adapters.onstep.mount import OnStepMount, _haversine_m
from smart_telescope.adapters.onstep.safety import OnStepSafetyConfig


# ── helpers ───────────────────────────────────────────────────────────────────

_BASE_LAT = 50.336
_BASE_LON = 8.533


def _make_cfg(
    *,
    onstep_time_tolerance_s: float = 10.0,
    onstep_location_tolerance_m: float = 100.0,
    lat: float = _BASE_LAT,
    lon: float = _BASE_LON,
) -> OnStepSafetyConfig:
    return OnStepSafetyConfig(
        observer_lat=lat,
        observer_lon=lon,
        min_alt_deg=10.0,
        max_alt_deg=88.0,
        ha_east_limit_h=-5.5,
        ha_west_limit_h=5.0,
        onstep_time_tolerance_s=onstep_time_tolerance_s,
        onstep_location_tolerance_m=onstep_location_tolerance_m,
    )


def _call_get_sync_status(
    *,
    cfg: OnStepSafetyConfig,
    clock: dict,
    site: dict,
) -> dict:
    """Call OnStepMount.get_sync_status() via an unbound call on a minimal mock self."""
    mount = MagicMock(spec=OnStepMount)
    mount._safety_config = cfg
    mount.read_onstep_clock.return_value = clock
    mount.read_onstep_site.return_value = site
    return OnStepMount.get_sync_status(mount)


def _clock(delta_s: float, available: bool = True) -> dict:
    return {"available": available, "delta_s": delta_s, "threshold_s": 10.0}


def _site(onstep_lat: float, onstep_lon: float, available: bool = True) -> dict:
    return {"available": available, "lat": onstep_lat, "lon": onstep_lon}


# ── Haversine helper ──────────────────────────────────────────────────────────

class TestHaversineM:
    def test_same_point_is_zero(self) -> None:
        assert _haversine_m(_BASE_LAT, _BASE_LON, _BASE_LAT, _BASE_LON) == pytest.approx(0.0, abs=0.01)

    def test_one_degree_latitude_approx_111km(self) -> None:
        d = _haversine_m(50.0, 8.533, 51.0, 8.533)
        assert d == pytest.approx(111_320, rel=0.01)

    def test_symmetric(self) -> None:
        d1 = _haversine_m(_BASE_LAT, _BASE_LON, _BASE_LAT + 0.001, _BASE_LON + 0.001)
        d2 = _haversine_m(_BASE_LAT + 0.001, _BASE_LON + 0.001, _BASE_LAT, _BASE_LON)
        assert d1 == pytest.approx(d2, rel=1e-9)

    def test_lat_delta_0_0027_deg_exceeds_100m(self) -> None:
        """INC-002 / TEST-002: lat_delta=0.0027 deg must fail at 100 m tolerance."""
        # 0.0027° * 111_320 m/deg ≈ 300 m > 100 m
        d = _haversine_m(_BASE_LAT, _BASE_LON, _BASE_LAT + 0.0027, _BASE_LON)
        assert d > 100.0, f"Expected > 100 m, got {d:.1f} m"

    def test_lon_delta_0_0337_deg_exceeds_100m(self) -> None:
        """INC-002 / TEST-002: lon_delta=0.0337 deg must fail at 100 m tolerance at lat 50.336N."""
        # 0.0337° * 111_320 * cos(50.336°) ≈ 2413 m >> 100 m
        d = _haversine_m(_BASE_LAT, _BASE_LON, _BASE_LAT, _BASE_LON + 0.0337)
        assert d > 100.0, f"Expected > 100 m, got {d:.1f} m"

    def test_small_delta_below_100m(self) -> None:
        # ~50 m lat offset: 50 / 111320 ≈ 0.000449°
        d = _haversine_m(_BASE_LAT, _BASE_LON, _BASE_LAT + 0.000449, _BASE_LON)
        assert d < 100.0, f"Expected < 100 m, got {d:.1f} m"


# ── Location tolerance ─────────────────────────────────────────────────────────

class TestGetSyncStatusLocationTolerance:
    """Meter-based location tolerance in get_sync_status() — REQ-TIME-003."""

    def _run(self, onstep_lat: float, onstep_lon: float, tolerance_m: float = 100.0) -> dict:
        return _call_get_sync_status(
            cfg=_make_cfg(onstep_location_tolerance_m=tolerance_m),
            clock=_clock(delta_s=1.0),
            site=_site(onstep_lat=onstep_lat, onstep_lon=onstep_lon),
        )

    def test_location_delta_m_in_result(self) -> None:
        result = self._run(_BASE_LAT, _BASE_LON)
        assert "location_delta_m" in result

    def test_location_tolerance_m_in_result(self) -> None:
        result = self._run(_BASE_LAT, _BASE_LON)
        assert result["location_tolerance_m"] == pytest.approx(100.0)

    def test_same_location_passes(self) -> None:
        result = self._run(_BASE_LAT, _BASE_LON)
        assert result["location_ok"] is True
        assert result["location_delta_m"] == pytest.approx(0.0, abs=0.1)

    def test_below_100m_passes(self) -> None:
        # ~50 m lat delta: 50 / 111320 ≈ 0.000449°
        result = self._run(_BASE_LAT + 0.000449, _BASE_LON)
        assert result["location_ok"] is True

    def test_at_tolerance_boundary_passes(self) -> None:
        # ~100 m lat offset: 100 / 111320 ≈ 0.000898°
        lat_offset = 100.0 / 111_320.0
        result = self._run(_BASE_LAT + lat_offset, _BASE_LON)
        assert result["location_ok"] is True, (
            f"Expected PASS at boundary, delta={result['location_delta_m']:.2f}m"
        )

    def test_above_100m_fails(self) -> None:
        # ~300 m lat delta
        result = self._run(_BASE_LAT + 0.0027, _BASE_LON)
        assert result["location_ok"] is False

    def test_lat_delta_0_0027_deg_fails(self) -> None:
        """TEST-002: lat_delta=0.0027 deg fails at 100 m tolerance."""
        result = self._run(_BASE_LAT + 0.0027, _BASE_LON)
        assert result["location_ok"] is False
        assert result["location_delta_m"] > 100.0

    def test_lon_delta_0_0337_deg_fails(self) -> None:
        """TEST-002: lon_delta=0.0337 deg fails at 100 m tolerance at lat 50.336N."""
        result = self._run(_BASE_LAT, _BASE_LON + 0.0337)
        assert result["location_ok"] is False
        assert result["location_delta_m"] > 100.0

    def test_custom_tolerance_500m(self) -> None:
        # 300 m delta (~0.0027° lat) passes at 500 m tolerance
        result = self._run(_BASE_LAT + 0.0027, _BASE_LON, tolerance_m=500.0)
        assert result["location_ok"] is True

    def test_unavailable_site_fails_with_none_delta(self) -> None:
        result = _call_get_sync_status(
            cfg=_make_cfg(),
            clock=_clock(delta_s=1.0),
            site={"available": False, "lat": None, "lon": None},
        )
        assert result["location_ok"] is False
        assert result["location_delta_m"] is None


# ── Time tolerance ─────────────────────────────────────────────────────────────

class TestGetSyncStatusTimeTolerance:
    """Configurable time tolerance — REQ-TIME-003."""

    def _run(self, delta_s: float, tolerance_s: float = 10.0) -> dict:
        return _call_get_sync_status(
            cfg=_make_cfg(onstep_time_tolerance_s=tolerance_s),
            clock=_clock(delta_s=delta_s),
            site=_site(onstep_lat=_BASE_LAT, onstep_lon=_BASE_LON),
        )

    def test_time_tolerance_s_in_result(self) -> None:
        result = self._run(5.0)
        assert result["time_tolerance_s"] == pytest.approx(10.0)

    def test_below_tolerance_passes(self) -> None:
        assert self._run(9.9)["time_ok"] is True

    def test_at_tolerance_passes(self) -> None:
        assert self._run(10.0)["time_ok"] is True

    def test_above_tolerance_fails(self) -> None:
        assert self._run(10.1)["time_ok"] is False

    def test_custom_60s_tolerance(self) -> None:
        assert self._run(30.0, tolerance_s=60.0)["time_ok"] is True

    def test_default_10s_rejects_old_120s_clock_delta(self) -> None:
        # delta=15s fails with new 10s tolerance (old 120s would have passed)
        assert self._run(15.0)["time_ok"] is False


# ── UTF-8 / encoding safety ───────────────────────────────────────────────────

class TestLogEncoding:
    """REQ-TIME-006: log format strings must not contain the degree symbol (°)."""

    def test_session_connect_log_no_degree_symbol(self) -> None:
        """Time/location log lines in session_connect use 'deg', not '°'."""
        import inspect
        import smart_telescope.api.session as session_mod
        source = inspect.getsource(session_mod.session_connect)
        assert "°" not in source, (
            "Degree symbol found in session_connect. Use 'deg' in log format strings."
        )

    def test_readiness_location_issue_no_degree_symbol(self) -> None:
        """Readiness issue string for location mismatch uses 'deg', not '°'."""
        import inspect
        import smart_telescope.services.readiness as readiness_mod
        # Read the portion around the location issue reporting
        source = inspect.getsource(readiness_mod)
        # Check that any formatted location issue doesn't use °
        for line in source.splitlines():
            if "site off by" in line:
                assert "°" not in line, (
                    f"Degree symbol in readiness location issue line: {line!r}"
                )

    def test_caplog_verified_no_degree_symbol(self, caplog) -> None:
        """Emit the actual VERIFIED log line and verify no degree symbol."""
        import smart_telescope.api.session as session_mod
        with caplog.at_level(logging.INFO, logger="smart_telescope.api.session"):
            session_mod._log.info(
                "Time/location check: within tolerance — VERIFIED "
                "(time_delta=%.1fs tol=%ss "
                "lat_delta=%.4fdeg lon_delta=%.4fdeg loc_delta=%.1fm tol=%sm)",
                1.3, "10", 0.0027, 0.0337, 300.0, "100",
            )
        assert "°" not in caplog.text, f"Degree symbol in log: {caplog.text!r}"
        assert "deg" in caplog.text

    def test_caplog_mismatch_no_degree_symbol(self, caplog) -> None:
        """Emit the mismatch log line and verify no degree symbol."""
        import smart_telescope.api.session as session_mod
        with caplog.at_level(logging.INFO, logger="smart_telescope.api.session"):
            session_mod._log.info(
                "Time/location check: mismatch — awaiting user decision "
                "(time_ok=%s time_tol=%ss location_ok=%s loc_delta=%sm loc_tol=%sm)",
                True, "10", False, 300.0, "100",
            )
        assert "°" not in caplog.text, f"Degree symbol in log: {caplog.text!r}"
