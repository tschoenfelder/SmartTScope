"""One-shot GPSD client — query local GPSD for a GPS fix via TCP JSON protocol."""
from __future__ import annotations

import json
import logging
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import atan2, cos, radians, sin, sqrt
from typing import Any

_log = logging.getLogger(__name__)

_MAX_FIX_AGE_MINUTES = 60  # CFG-002: reject fixes older than this


@dataclass
class GpsdFix:
    lat: float
    lon: float
    alt: float | None
    gps_time: str | None  # ISO-8601 UTC from GPS receiver
    mode: int             # 0=unknown, 1=no_fix, 2=2D_fix, 3=3D_fix
    hdop: float | None
    fix_age_s: float | None = field(default=None)  # seconds since GPS timestamp

    def is_fresh(self, max_age_minutes: int = _MAX_FIX_AGE_MINUTES) -> bool:
        """Return True if the GPS fix is younger than max_age_minutes (CFG-002)."""
        if self.fix_age_s is None:
            return False
        return self.fix_age_s <= max_age_minutes * 60.0


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two WGS-84 coordinates."""
    R = 6_371_000.0
    lat1, lat2, lon1, lon2 = map(radians, (lat1, lat2, lon1, lon2))
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _extract_tpv(obj: dict[str, Any]) -> dict[str, Any] | None:
    """Return the TPV payload from either a bare TPV line or a POLL envelope.

    M10-024 follow-up (hardware evidence 2026-07-18): gpsd answers `?POLL;`
    with a single `"class":"POLL"` object containing the daemon's *already
    cached* last-known fix(es) in a `"tpv"` array — answered immediately,
    without waiting for the device's next report. The previous code only
    recognized a bare `"class":"TPV"` line, which (with `?WATCH` also
    enabled in the same request) only arrives via the live streamed feed —
    so every call was actually waiting for the receiver's own report cadence
    instead of reading gpsd's instant cached answer. Measured on the Pi:
    ~780 ms per `/api/location/status` call, every call, matching a ~1 Hz
    GPS update interval. A bare `"class":"TPV"` line is still accepted too,
    for compatibility with older gpsd behavior.
    """
    cls = obj.get("class")
    if cls == "TPV":
        return obj
    if cls == "POLL":
        tpv_list = obj.get("tpv") or []
        if tpv_list:
            return tpv_list[0]
    return None


class GpsdService:
    """One-shot TCP client for the GPSD JSON protocol (port 2947).

    Caches the result for `cache_ttl_s` (default 2 s) — `/api/location/status`
    and similar callers poll every ~2.5 s; the GPS position/time does not
    change meaningfully at that cadence, and a fresh query pays the full
    connect+protocol round-trip every time (see `_extract_tpv` above).
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 2947,
        timeout_s: float = 5.0,
        cache_ttl_s: float = 2.0,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_s = timeout_s
        self._cache_ttl_s = cache_ttl_s
        self._cached_fix: GpsdFix | None = None
        self._cached_at: float | None = None

    def get_fix(self) -> GpsdFix | None:
        """Return the current GPS fix, from cache when still within TTL."""
        now = time.monotonic()
        if self._cached_at is not None and (now - self._cached_at) < self._cache_ttl_s:
            return self._cached_fix
        fix = self._query_fix()
        self._cached_fix = fix
        self._cached_at = now
        return fix

    def _query_fix(self) -> GpsdFix | None:
        """Connect to GPSD, request one poll, return the current fix or None."""
        try:
            with socket.create_connection((self._host, self._port), timeout=self._timeout_s) as sock:
                sock.sendall(b'?WATCH={"enable":true,"json":true};\n?POLL;\n')
                sock.settimeout(self._timeout_s)
                buf = ""
                while True:
                    try:
                        chunk = sock.recv(4096)
                    except socket.timeout:
                        break
                    if not chunk:
                        break
                    buf += chunk.decode("utf-8", errors="replace")
                    for line in buf.split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        tpv = _extract_tpv(obj)
                        if tpv is None:
                            continue
                        gps_time = tpv.get("time")
                        fix_age_s: float | None = None
                        if gps_time:
                            try:
                                gps_dt = datetime.fromisoformat(
                                    gps_time.replace("Z", "+00:00")
                                )
                                fix_age_s = (
                                    datetime.now(timezone.utc) - gps_dt
                                ).total_seconds()
                            except ValueError:
                                pass
                        fix = GpsdFix(
                            lat=float(tpv.get("lat", 0.0)),
                            lon=float(tpv.get("lon", 0.0)),
                            alt=float(tpv["alt"]) if "alt" in tpv else None,
                            gps_time=gps_time,
                            mode=int(tpv.get("mode", 0)),
                            hdop=float(tpv["hdop"]) if "hdop" in tpv else None,
                            fix_age_s=fix_age_s,
                        )
                        if fix.is_fresh():
                            _log.debug(
                                "GPS master source: GPSD fix age=%.0fs (fresh)",
                                fix_age_s,
                            )
                        else:
                            _log.warning(
                                "GPS fix is stale (age=%.0fs > %dm) — "
                                "falling back to system/config",
                                fix_age_s if fix_age_s is not None else -1,
                                _MAX_FIX_AGE_MINUTES,
                            )
                        return fix
        except (ConnectionRefusedError, TimeoutError, OSError):
            pass
        return None
