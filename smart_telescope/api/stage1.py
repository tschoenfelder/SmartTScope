"""Stage 1 time/location panel API — GET /api/stage1/time-location.

REQ-API-004, REQ-TIME-005 (INC-009).
Returns a consolidated view of all Stage 1 time/location trust state without
making live serial calls — all data comes from the DeviceStateService cache.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import config as _cfg
from ..services.device_state import DeviceStateService
from ..services.operation_gate import gate_inputs_from_device_state
from . import deps

router = APIRouter(prefix="/api/stage1")


class Stage1TimeLocationResponse(BaseModel):
    # Trust state
    onstep_time_location: str       # VERIFIED | UNVERIFIED | UNKNOWN
    raspberry_time_trust: str       # TRUSTED | NOT_TRUSTED
    raspberry_trust_source: str     # GPSD_FIX | NTP | ONSTEP_COMPARISON | USER_CONFIRMED | NOT_TRUSTED | STUB
    master_source: str              # GPS_FIX | NTP | USER_CONFIRMED | FALLBACK | STUB

    # Adapter / device state
    adapter_connection_state: str   # OPEN | CLOSED
    adapter_health_state: str       # OK | FAILED | UNKNOWN

    # Time from last sync check (None when check has not yet run)
    onstep_time_local: str | None   # ISO local datetime string from OnStep
    master_time_local: str | None   # ISO local datetime string (Pi system clock)
    time_delta_s: float | None
    time_tolerance_s: float
    time_ok: bool | None

    # Location from last sync check
    onstep_lat: float | None
    onstep_lon: float | None
    master_lat: float
    master_lon: float
    location_delta_m: float | None
    location_tolerance_m: float
    location_ok: bool | None

    # Timestamps (ISO UTC, None if not yet run)
    last_verification_at_utc: str | None
    last_push_at_utc: str | None

    # Available actions (labels; UI maps to API calls)
    available_actions: list[str]


def _wall_to_utc_iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@router.get("/time-location", response_model=Stage1TimeLocationResponse)
def stage1_time_location(
    device_state:        DeviceStateService = Depends(deps.get_device_state),
    master_source_svc:   object             = Depends(deps.get_master_source_service),
    raspberry_trust_svc: object             = Depends(deps.get_raspberry_trust_service),
) -> Stage1TimeLocationResponse:
    """Return consolidated Stage 1 time/location trust state (REQ-API-004).

    No live serial I/O — reads from DeviceStateService cache populated by
    session_connect and sync_clock.
    """
    # ── Gate inputs give us adapter + trust state in one call ────────────────
    inputs = gate_inputs_from_device_state(
        device_state,
        master_source_svc=master_source_svc,
        raspberry_trust_svc=raspberry_trust_svc,
    )
    adapter_conn   = inputs["adapter_connection"]
    adapter_health = inputs["adapter_health"]
    tl_name        = inputs["onstep_time_location"]
    raspberry_trust = inputs["raspberry_time_trust"]
    raspberry_src   = inputs.get("raspberry_trust_source", "STUB")
    master_src      = inputs["master_time_source"]

    # ── Cached sync status from last session_connect / rerun ─────────────────
    sync = device_state.get_last_sync_status()

    # ── Active tolerances from config ─────────────────────────────────────────
    time_tol   = _cfg.ONSTEP_TIME_TOLERANCE_S
    loc_tol    = _cfg.ONSTEP_LOCATION_TOLERANCE_M

    # ── Available actions ─────────────────────────────────────────────────────
    actions: list[str] = ["rerun_check"]
    if adapter_conn == "OPEN":
        actions.append("push_to_onstep")
    if raspberry_src == "NOT_TRUSTED":
        actions.append("confirm_raspberry_time")

    return Stage1TimeLocationResponse(
        onstep_time_location=tl_name,
        raspberry_time_trust=raspberry_trust,
        raspberry_trust_source=raspberry_src,
        master_source=master_src,
        adapter_connection_state=adapter_conn,
        adapter_health_state=adapter_health,
        onstep_time_local=sync.get("onstep_time_local") if sync else None,
        master_time_local=sync.get("master_time_local") if sync else None,
        time_delta_s=sync.get("time_delta_s") if sync else None,
        time_tolerance_s=time_tol,
        time_ok=sync.get("time_ok") if sync else None,
        onstep_lat=sync.get("onstep_lat") if sync else None,
        onstep_lon=sync.get("onstep_lon") if sync else None,
        master_lat=_cfg.OBSERVER_LAT,
        master_lon=_cfg.OBSERVER_LON,
        location_delta_m=sync.get("location_delta_m") if sync else None,
        location_tolerance_m=loc_tol,
        location_ok=sync.get("location_ok") if sync else None,
        last_verification_at_utc=_wall_to_utc_iso(device_state.get_last_verification_at()),
        last_push_at_utc=_wall_to_utc_iso(device_state.get_last_push_at()),
        available_actions=actions,
    )
