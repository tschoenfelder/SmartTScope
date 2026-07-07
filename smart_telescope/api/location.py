"""Confirm Time & Location API.

GET  /api/location/status       — consolidated read for the panel
GET  /api/location/ip-lookup    — one-shot, user-triggered IP geolocation
POST /api/location/confirm      — commit Home or a saved location + confirm Pi time
DELETE /api/location/saved/{name} — remove one saved-location library entry
"""
from __future__ import annotations

import contextlib
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..domain.location_source import is_valid as _is_valid_source
from ..ports.mount import MountPort
from ..services.device_state import DeviceStateService
from ..services.gpsd_service import GpsdService, haversine_m
from ..services.ip_geolocation_service import IpGeolocationService
from ..services.operation_gate import gate_inputs_from_device_state
from . import deps
from .mount import mount_confirm_time, mount_sync_clock

router = APIRouter(prefix="/api/location")

_gpsd = GpsdService()
_ip_geo = IpGeolocationService()
_CONFIG_PATH = Path.home() / ".SmartTScope" / "config.toml"

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_RESERVED_NAMES = {"home"}
_MIN_GPS_MODE = 2  # 2 = 2-D fix, 3 = 3-D fix; mirrors services/master_source.py's _MIN_GPS_MODE


# ── response / request models ────────────────────────────────────────────────

class LocationEntry(BaseModel):
    name: str
    lat: float
    lon: float
    height_m: float


class ActiveLocation(BaseModel):
    name: str
    lat: float
    lon: float
    height_m: float
    source: str


class HomeLocation(BaseModel):
    lat: float
    lon: float
    height_m: float


class GpsInfo(BaseModel):
    available: bool
    fresh: bool = False
    usable: bool = False
    lat: float = 0.0
    lon: float = 0.0
    alt_m: float | None = None
    distance_from_active_m: float | None = None


class LocationStatusResponse(BaseModel):
    active: ActiveLocation
    home: HomeLocation
    saved_locations: list[LocationEntry]
    gps: GpsInfo
    local_time_iso: str
    local_tz_name: str
    time_from_gps: bool


class IpLookupResponse(BaseModel):
    available: bool
    lat: float = 0.0
    lon: float = 0.0
    city: str = ""
    country: str = ""
    ip: str = ""


class ConfirmLocationRequest(BaseModel):
    target: Literal["home", "saved"]
    name: str | None = None
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    height_m: float = Field(ge=-500.0, le=9000.0)
    source: str


# ── status assembly ──────────────────────────────────────────────────────────

def _build_status(
    device_state: DeviceStateService,
    master_source_svc: object,
    raspberry_trust_svc: object,
) -> LocationStatusResponse:
    fix = _gpsd.get_fix()
    if fix is not None:
        dist = haversine_m(fix.lat, fix.lon, config.OBSERVER_LAT, config.OBSERVER_LON)
        fresh = fix.is_fresh()
        gps = GpsInfo(
            available=True, fresh=fresh, usable=fresh and fix.mode >= _MIN_GPS_MODE,
            lat=fix.lat, lon=fix.lon, alt_m=fix.alt, distance_from_active_m=round(dist, 1),
        )
    else:
        gps = GpsInfo(available=False)

    inputs = gate_inputs_from_device_state(
        device_state, master_source_svc=master_source_svc, raspberry_trust_svc=raspberry_trust_svc,
    )
    time_from_gps = inputs.get("raspberry_trust_source") == "GPSD_FIX"
    now_local = datetime.now().astimezone()

    return LocationStatusResponse(
        active=ActiveLocation(
            name=config.OBSERVER_LOCATION_NAME, lat=config.OBSERVER_LAT,
            lon=config.OBSERVER_LON, height_m=config.OBSERVER_HEIGHT_M,
            source=config.OBSERVER_LOCATION_SOURCE,
        ),
        home=HomeLocation(
            lat=config.OBSERVER_HOME_LAT, lon=config.OBSERVER_HOME_LON,
            height_m=config.OBSERVER_HOME_HEIGHT_M,
        ),
        saved_locations=[
            LocationEntry(name=n, lat=s.lat, lon=s.lon, height_m=s.height_m)
            for n, s in sorted(config.LOCATIONS.items())
        ],
        gps=gps,
        local_time_iso=now_local.isoformat(),
        local_tz_name=now_local.tzname() or "",
        time_from_gps=time_from_gps,
    )


# ── config.toml line-scanned section read/write ──────────────────────────────

def _find_section_lines(lines: list[str], header: str) -> tuple[int, int] | None:
    """Span [start, end) for `[header]`: start = header line, end = index of the
    next line whose first non-whitespace char is '[' (a new section), or len(lines)."""
    target = f"[{header}]"
    for i, line in enumerate(lines):
        if line.strip() == target:
            for j in range(i + 1, len(lines)):
                stripped = lines[j].lstrip()
                if stripped.startswith("["):
                    return i, j
            return i, len(lines)
    return None


def _patch_kv_line(lines: list[str], start: int, end: int, key: str, value: str) -> None:
    """Patch `key = ...` within lines[start:end] in place, inserting after the header if absent."""
    pattern = re.compile(rf"^(\s*{re.escape(key)}\s*=\s*).*$")
    for i in range(start, end):
        if pattern.match(lines[i]):
            lines[i] = f"{key} = {value}\n"
            return
    lines.insert(start + 1, f"{key} = {value}\n")


def _write_observer_block(lat: float, lon: float, height_m: float) -> None:
    if not _CONFIG_PATH.exists():
        return
    text = _CONFIG_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    span = _find_section_lines(lines, "observer")
    if span is None:
        return
    start, end = span
    _patch_kv_line(lines, start, end, "lat", str(lat))
    span = _find_section_lines(lines, "observer")
    start, end = span
    _patch_kv_line(lines, start, end, "lon", str(lon))
    span = _find_section_lines(lines, "observer")
    start, end = span
    _patch_kv_line(lines, start, end, "height_m", str(height_m))
    _CONFIG_PATH.write_text("".join(lines), encoding="utf-8")


def _render_location_block(name: str, lat: float, lon: float, height_m: float) -> list[str]:
    return [
        f"[locations.{name}]\n",
        f"lat = {lat}\n",
        f"lon = {lon}\n",
        f"height_m = {height_m}\n",
    ]


def _upsert_locations_block(name: str, lat: float, lon: float, height_m: float) -> None:
    if not _CONFIG_PATH.exists():
        return
    text = _CONFIG_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    span = _find_section_lines(lines, f"locations.{name}")
    block = _render_location_block(name, lat, lon, height_m)
    if span is not None:
        start, end = span
        lines[start:end] = block
    else:
        while lines and lines[-1].strip() == "":
            lines.pop()
        if lines:
            lines.append("\n")
        lines.extend(block)
    _CONFIG_PATH.write_text("".join(lines), encoding="utf-8")


def _delete_locations_block(name: str) -> bool:
    if not _CONFIG_PATH.exists():
        return False
    text = _CONFIG_PATH.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    span = _find_section_lines(lines, f"locations.{name}")
    if span is None:
        return False
    start, end = span
    del lines[start:end]
    new_text = re.sub(r"\n{3,}", "\n\n", "".join(lines))
    _CONFIG_PATH.write_text(new_text, encoding="utf-8")
    return True


def _validate_saved_name(name: str | None) -> str:
    if not name:
        raise HTTPException(status_code=400, detail="Saved location name is required")
    name = name.strip()
    if name.lower() in _RESERVED_NAMES:
        raise HTTPException(status_code=400, detail="'Home' is reserved and cannot be used as a saved-location name")
    if not _NAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Invalid name — use only letters, digits, underscores or hyphens (1-64 chars)",
        )
    return name


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=LocationStatusResponse)
def location_status(
    device_state: DeviceStateService = Depends(deps.get_device_state),
    master_source_svc: object = Depends(deps.get_master_source_service),
    raspberry_trust_svc: object = Depends(deps.get_raspberry_trust_service),
) -> LocationStatusResponse:
    return _build_status(device_state, master_source_svc, raspberry_trust_svc)


@router.get("/ip-lookup", response_model=IpLookupResponse)
def location_ip_lookup() -> IpLookupResponse:
    result = _ip_geo.lookup()
    if result is None:
        return IpLookupResponse(available=False)
    return IpLookupResponse(
        available=True, lat=result.lat, lon=result.lon,
        city=result.city, country=result.country, ip=result.ip,
    )


@router.post("/confirm", response_model=LocationStatusResponse)
def location_confirm(
    body: ConfirmLocationRequest,
    mount: MountPort = Depends(deps.get_mount),
    device_state: DeviceStateService = Depends(deps.get_device_state),
    master_source_svc: object = Depends(deps.get_master_source_service),
    raspberry_trust_svc: object = Depends(deps.get_raspberry_trust_service),
) -> LocationStatusResponse:
    if not _is_valid_source(body.source):
        raise HTTPException(status_code=400, detail=f"Unrecognized location source: {body.source}")

    if body.target == "home":
        _write_observer_block(body.lat, body.lon, body.height_m)
        config.OBSERVER_HOME_LAT = body.lat
        config.OBSERVER_HOME_LON = body.lon
        config.OBSERVER_HOME_HEIGHT_M = body.height_m
        config.OBSERVER_LAT = body.lat
        config.OBSERVER_LON = body.lon
        config.OBSERVER_HEIGHT_M = body.height_m
        config.OBSERVER_LOCATION_NAME = "Home"
    else:
        name = _validate_saved_name(body.name)
        _upsert_locations_block(name, body.lat, body.lon, body.height_m)
        config.LOCATIONS[name] = config.LocationSpec(
            name=name, lat=body.lat, lon=body.lon, height_m=body.height_m,
        )
        config.OBSERVER_LAT = body.lat
        config.OBSERVER_LON = body.lon
        config.OBSERVER_HEIGHT_M = body.height_m
        config.OBSERVER_LOCATION_NAME = name

    config.OBSERVER_LOCATION_SOURCE = body.source

    with contextlib.suppress(Exception):
        mount_sync_clock(mount=mount, device_state=device_state, master_source_svc=master_source_svc)
    mount_confirm_time(device_state=device_state, raspberry_trust_svc=raspberry_trust_svc)

    return _build_status(device_state, master_source_svc, raspberry_trust_svc)


@router.delete("/saved/{name}")
def location_delete_saved(name: str) -> dict[str, bool]:
    if name.strip().lower() in _RESERVED_NAMES:
        raise HTTPException(status_code=400, detail="Cannot delete the Home location")
    found_on_disk = _delete_locations_block(name)
    if not found_on_disk and name not in config.LOCATIONS:
        raise HTTPException(status_code=404, detail=f"Saved location '{name}' not found")
    config.LOCATIONS.pop(name, None)
    if config.OBSERVER_LOCATION_NAME == name:
        config.OBSERVER_LAT = config.OBSERVER_HOME_LAT
        config.OBSERVER_LON = config.OBSERVER_HOME_LON
        config.OBSERVER_HEIGHT_M = config.OBSERVER_HOME_HEIGHT_M
        config.OBSERVER_LOCATION_NAME = "Home"
        config.OBSERVER_LOCATION_SOURCE = "CONFIG_FILE"
    return {"ok": True}
