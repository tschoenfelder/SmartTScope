"""One-shot IP-based geolocation lookup — user-triggered fallback location source."""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass

_log = logging.getLogger(__name__)


@dataclass
class IpGeoResult:
    lat: float
    lon: float
    city: str
    country: str
    ip: str


class IpGeolocationService:
    """One-shot HTTPS client for a free IP-geolocation JSON API (no API key)."""

    _DEFAULT_URL = "https://ipapi.co/json/"

    def __init__(self, url: str = _DEFAULT_URL, timeout_s: float = 5.0) -> None:
        self._url = url
        self._timeout_s = timeout_s

    def lookup(self) -> IpGeoResult | None:
        """Query the IP-geo API. Returns None on any error — never raises."""
        try:
            with urllib.request.urlopen(self._url, timeout=self._timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if not isinstance(data, dict) or data.get("error"):
                return None
            return IpGeoResult(
                lat=float(data["latitude"]),
                lon=float(data["longitude"]),
                city=str(data.get("city", "")),
                country=str(data.get("country_name", "")),
                ip=str(data.get("ip", "")),
            )
        except Exception as exc:
            _log.warning("IP geolocation lookup failed: %s", exc)
            return None
