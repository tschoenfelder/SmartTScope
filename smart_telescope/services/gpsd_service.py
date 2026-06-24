"""One-shot GPSD client — query local GPSD for a GPS fix via TCP JSON protocol."""
from __future__ import annotations

import json
import logging
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import atan2, cos, radians, sin, sqrt

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


class GpsdService:
    """One-shot TCP client for the GPSD JSON protocol (port 2947)."""

    def __init__(self, host: str = "127.0.0.1", port: int = 2947, timeout_s: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._timeout_s = timeout_s

    def get_fix(self) -> GpsdFix | None:
        """Connect to GPSD, request one poll, return the first TPV report or None."""
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
                        if obj.get("class") == "TPV":
                            gps_time = obj.get("time")
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
                                lat=float(obj.get("lat", 0.0)),
                                lon=float(obj.get("lon", 0.0)),
                                alt=float(obj["alt"]) if "alt" in obj else None,
                                gps_time=gps_time,
                                mode=int(obj.get("mode", 0)),
                                hdop=float(obj["hdop"]) if "hdop" in obj else None,
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
