"""Dawn status — GET /api/dawn."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from ..runtime import get_runtime

router = APIRouter()


class DawnStatusResponse(BaseModel):
    sun_altitude_deg: float | None
    is_dawn: bool
    parked_at_dawn: bool
    parked_at_iso: str | None  # UTC ISO-8601 timestamp when park was issued, or null
    threshold_deg: float


@router.get("/api/dawn", response_model=DawnStatusResponse)
def get_dawn_status() -> DawnStatusResponse:
    """Return current Sun altitude and auto-park status."""
    from ..domain.solar import ASTRONOMICAL_DAWN_ALT_DEG

    status = get_runtime().dawn_watcher.get_status()
    if status is None:
        return DawnStatusResponse(
            sun_altitude_deg=None,
            is_dawn=False,
            parked_at_dawn=False,
            parked_at_iso=None,
            threshold_deg=ASTRONOMICAL_DAWN_ALT_DEG,
        )

    parked_at_iso: str | None = None
    if status.parked_at is not None:
        # Convert monotonic timestamp to approximate wall-clock UTC
        mono_offset = status.parked_at - time.monotonic()
        wall_ts = time.time() + mono_offset
        parked_at_iso = datetime.fromtimestamp(wall_ts, tz=timezone.utc).isoformat()

    return DawnStatusResponse(
        sun_altitude_deg=status.sun_altitude_deg,
        is_dawn=status.is_dawn,
        parked_at_dawn=status.parked_at_dawn,
        parked_at_iso=parked_at_iso,
        threshold_deg=ASTRONOMICAL_DAWN_ALT_DEG,
    )
