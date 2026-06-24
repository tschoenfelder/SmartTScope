"""Tests for services/gpsd_service.py — GPSD TCP client and haversine."""

from __future__ import annotations

import json
import socket
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.services.gpsd_service import GpsdFix, GpsdService, haversine_m


class TestHaversine:
    def test_same_point_is_zero(self) -> None:
        assert haversine_m(50.0, 8.0, 50.0, 8.0) == pytest.approx(0.0, abs=1.0)

    def test_known_distance_bern_paris(self) -> None:
        # Bern (46.95, 7.45) to Paris (48.85, 2.35) ≈ 435 km (straight-line)
        d = haversine_m(46.95, 7.45, 48.85, 2.35)
        assert 420_000 < d < 450_000

    def test_returns_float(self) -> None:
        assert isinstance(haversine_m(0.0, 0.0, 1.0, 1.0), float)

    def test_symmetric(self) -> None:
        a = haversine_m(10.0, 20.0, 11.0, 21.0)
        b = haversine_m(11.0, 21.0, 10.0, 20.0)
        assert a == pytest.approx(b, rel=1e-9)


def _make_socket_with_data(lines: list[str]) -> MagicMock:
    """Return a mock socket that yields *lines* on recv() then EOF."""
    payload = "\n".join(lines) + "\n"
    data = payload.encode("utf-8")
    sock = MagicMock()
    # First recv returns data, second returns b"" (EOF)
    sock.recv.side_effect = [data, b""]
    sock.__enter__ = lambda s: s
    sock.__exit__ = MagicMock(return_value=False)
    return sock


class TestGpsdServiceGetFix:
    def _service(self) -> GpsdService:
        return GpsdService(host="127.0.0.1", port=2947, timeout_s=1.0)

    def test_returns_none_on_connection_refused(self) -> None:
        with patch("socket.create_connection", side_effect=ConnectionRefusedError):
            fix = self._service().get_fix()
        assert fix is None

    def test_returns_none_on_timeout(self) -> None:
        with patch("socket.create_connection", side_effect=TimeoutError):
            fix = self._service().get_fix()
        assert fix is None

    def test_returns_none_on_oserror(self) -> None:
        with patch("socket.create_connection", side_effect=OSError("network")):
            fix = self._service().get_fix()
        assert fix is None

    def test_returns_none_when_no_tpv(self) -> None:
        lines = [
            json.dumps({"class": "VERSION", "release": "3.22"}),
            json.dumps({"class": "DEVICES", "devices": []}),
        ]
        sock = _make_socket_with_data(lines)
        with patch("socket.create_connection", return_value=sock):
            fix = self._service().get_fix()
        assert fix is None

    def test_returns_fix_on_tpv_with_3d_mode(self) -> None:
        tpv = {
            "class": "TPV",
            "lat": 50.336,
            "lon": 8.533,
            "alt": 123.4,
            "time": "2026-06-21T21:00:00.000Z",
            "mode": 3,
            "hdop": 1.2,
        }
        sock = _make_socket_with_data([json.dumps(tpv)])
        with patch("socket.create_connection", return_value=sock):
            fix = self._service().get_fix()
        assert isinstance(fix, GpsdFix)
        assert fix.lat == pytest.approx(50.336)
        assert fix.lon == pytest.approx(8.533)
        assert fix.alt == pytest.approx(123.4)
        assert fix.mode == 3
        assert fix.hdop == pytest.approx(1.2)
        assert fix.gps_time == "2026-06-21T21:00:00.000Z"

    def test_returns_fix_with_no_alt(self) -> None:
        tpv = {"class": "TPV", "lat": 51.0, "lon": 9.0, "mode": 2}
        sock = _make_socket_with_data([json.dumps(tpv)])
        with patch("socket.create_connection", return_value=sock):
            fix = self._service().get_fix()
        assert fix is not None
        assert fix.alt is None
        assert fix.hdop is None
        assert fix.gps_time is None

    def test_skips_malformed_json_lines(self) -> None:
        tpv = {"class": "TPV", "lat": 50.0, "lon": 8.0, "mode": 3}
        sock = _make_socket_with_data(["NOT JSON", json.dumps(tpv)])
        with patch("socket.create_connection", return_value=sock):
            fix = self._service().get_fix()
        assert fix is not None
        assert fix.lat == pytest.approx(50.0)

    def test_returns_none_on_recv_timeout(self) -> None:
        sock = MagicMock()
        sock.recv.side_effect = socket.timeout
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=sock):
            fix = self._service().get_fix()
        assert fix is None


# ── CFG-002: fix age validation ───────────────────────────────────────────────

class TestGpsdFixAge:
    def _make_fix(self, age_minutes: float, gps_time: str | None = None) -> "GpsdFix":
        from datetime import datetime, timezone, timedelta
        if gps_time is None and age_minutes >= 0:
            ts = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
            gps_time = ts.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        fix_age_s = age_minutes * 60.0 if gps_time is not None else None
        return GpsdFix(
            lat=50.0, lon=8.0, alt=None,
            gps_time=gps_time, mode=3, hdop=1.0,
            fix_age_s=fix_age_s,
        )

    def test_fresh_fix_within_60_minutes(self) -> None:
        fix = self._make_fix(30.0)
        assert fix.is_fresh() is True

    def test_stale_fix_over_60_minutes(self) -> None:
        fix = self._make_fix(90.0)
        assert fix.is_fresh() is False

    def test_fix_exactly_at_boundary_is_fresh(self) -> None:
        fix = self._make_fix(60.0)
        assert fix.is_fresh() is True

    def test_no_gps_time_is_not_fresh(self) -> None:
        fix = GpsdFix(lat=50.0, lon=8.0, alt=None, gps_time=None, mode=3, hdop=None, fix_age_s=None)
        assert fix.is_fresh() is False

    def test_fix_age_computed_from_gps_time(self) -> None:
        import json
        from unittest.mock import patch
        from datetime import datetime, timezone, timedelta
        svc = GpsdService(host="127.0.0.1", port=2947, timeout_s=1.0)
        gps_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
        gps_time_str = gps_ts.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        tpv = {"class": "TPV", "lat": 51.0, "lon": 9.0, "mode": 3, "time": gps_time_str}
        payload = (json.dumps(tpv) + "\n").encode()
        sock = MagicMock()
        sock.recv.side_effect = [payload, b""]
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=sock):
            fix = svc.get_fix()
        assert fix is not None
        assert fix.fix_age_s is not None
        assert 590 <= fix.fix_age_s <= 620  # 10 min ± some tolerance

    def test_stale_fix_logs_warning(self) -> None:
        import json
        from unittest.mock import patch
        from datetime import datetime, timezone, timedelta
        import logging
        svc = GpsdService(host="127.0.0.1", port=2947, timeout_s=1.0)
        gps_ts = datetime.now(timezone.utc) - timedelta(minutes=90)
        gps_time_str = gps_ts.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        tpv = {"class": "TPV", "lat": 51.0, "lon": 9.0, "mode": 3, "time": gps_time_str}
        payload = (json.dumps(tpv) + "\n").encode()
        sock = MagicMock()
        sock.recv.side_effect = [payload, b""]
        sock.__enter__ = lambda s: s
        sock.__exit__ = MagicMock(return_value=False)
        with patch("socket.create_connection", return_value=sock):
            with patch("smart_telescope.services.gpsd_service._log") as mock_log:
                fix = svc.get_fix()
        assert fix is not None
        assert not fix.is_fresh()
        mock_log.warning.assert_called_once()
