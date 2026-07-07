"""Tests for services/ip_geolocation_service.py — one-shot IP geolocation lookup.

Tests cover:
- Success: well-formed JSON -> correct IpGeoResult
- URLError / timeout / connection-refused-style OSError -> None
- Malformed JSON -> None
- JSON missing latitude/longitude -> None
- Provider error-shape response ({"error": true, ...}) -> None
- Never raises for any of the above
"""
from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from smart_telescope.services.ip_geolocation_service import IpGeoResult, IpGeolocationService


def _service() -> IpGeolocationService:
    return IpGeolocationService(timeout_s=1.0)


def _response(payload: dict) -> MagicMock:
    """Return a mock context-manager response object yielding *payload* as JSON bytes."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode("utf-8")
    resp.__enter__ = lambda s: s
    resp.__exit__ = MagicMock(return_value=False)
    return resp


class TestIpGeolocationServiceLookup:
    def test_success_returns_result(self) -> None:
        payload = {
            "latitude": 50.1, "longitude": 8.6,
            "city": "Frankfurt", "country_name": "Germany", "ip": "1.2.3.4",
        }
        with patch("urllib.request.urlopen", return_value=_response(payload)):
            result = _service().lookup()
        assert isinstance(result, IpGeoResult)
        assert result.lat == pytest.approx(50.1)
        assert result.lon == pytest.approx(8.6)
        assert result.city == "Frankfurt"
        assert result.country == "Germany"
        assert result.ip == "1.2.3.4"

    def test_returns_none_on_url_error(self) -> None:
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("no network")):
            result = _service().lookup()
        assert result is None

    def test_returns_none_on_timeout(self) -> None:
        with patch("urllib.request.urlopen", side_effect=TimeoutError):
            result = _service().lookup()
        assert result is None

    def test_returns_none_on_connection_refused(self) -> None:
        with patch("urllib.request.urlopen", side_effect=ConnectionRefusedError):
            result = _service().lookup()
        assert result is None

    def test_returns_none_on_malformed_json(self) -> None:
        resp = MagicMock()
        resp.read.return_value = b"NOT JSON"
        resp.__enter__ = lambda s: s
        resp.__exit__ = MagicMock(return_value=False)
        with patch("urllib.request.urlopen", return_value=resp):
            result = _service().lookup()
        assert result is None

    def test_returns_none_on_missing_lat_lon(self) -> None:
        with patch("urllib.request.urlopen", return_value=_response({"city": "Nowhere"})):
            result = _service().lookup()
        assert result is None

    def test_returns_none_on_provider_error_shape(self) -> None:
        with patch(
            "urllib.request.urlopen",
            return_value=_response({"error": True, "reason": "rate limited"}),
        ):
            result = _service().lookup()
        assert result is None

    def test_never_raises_on_unexpected_exception(self) -> None:
        with patch("urllib.request.urlopen", side_effect=RuntimeError("boom")):
            result = _service().lookup()
        assert result is None
