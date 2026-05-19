"""Observation queue API — CRUD for the observation queue."""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..domain.queue import ObservationQueue, QueueEntry, QueueEntryStatus

router = APIRouter(prefix="/api/queue")

_queue_lock = threading.Lock()
_queue: ObservationQueue = ObservationQueue()

_VALID_PROFILES = frozenset({"c8_native", "c8_reducer", "c8_barlow2x"})


def _reset_queue() -> None:
    global _queue
    with _queue_lock:
        _queue = ObservationQueue()


def get_queue() -> ObservationQueue:
    return _queue


# ── Request model ─────────────────────────────────────────────────────────────


class AddEntryRequest(BaseModel):
    target_name:      str   = Field(min_length=1, max_length=64)
    target_ra:        float = Field(ge=0.0, lt=24.0)
    target_dec:       float = Field(ge=-90.0, le=90.0)
    profile:          str   = Field(default="c8_native")
    exposure:         float = Field(default=30.0, gt=0.0, le=3600.0)
    stack_depth:      int   = Field(default=10, ge=1, le=1000)
    min_altitude_deg: float = Field(default=20.0, ge=0.0, le=90.0)


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("", status_code=201)
def add_entry(req: AddEntryRequest) -> dict[str, object]:
    """Add an observation to the queue. Returns the created entry."""
    if req.profile not in _VALID_PROFILES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown profile '{req.profile}'. Valid: {sorted(_VALID_PROFILES)}",
        )
    entry = QueueEntry(
        target_name=req.target_name,
        target_ra=req.target_ra,
        target_dec=req.target_dec,
        profile=req.profile,
        exposure=req.exposure,
        stack_depth=req.stack_depth,
        min_altitude_deg=req.min_altitude_deg,
    )
    _queue.add(entry)
    return entry.to_dict()


@router.get("")
def list_entries(status: str | None = None) -> list[dict[str, object]]:
    """List all queue entries. Optional ?status= filter (PENDING, RUNNING, DONE, FAILED, SKIPPED)."""
    entries = _queue.all()
    if status is not None:
        try:
            s = QueueEntryStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=422, detail=f"Unknown status '{status}'")
        entries = [e for e in entries if e.status == s]
    return [e.to_dict() for e in entries]


@router.post("/clear", status_code=200)
def clear_completed() -> dict[str, int]:
    """Remove all DONE, FAILED, and SKIPPED entries. Returns count cleared."""
    before = len(_queue.all())
    _queue.clear_completed()
    after = len(_queue.all())
    return {"cleared": before - after}


@router.get("/{entry_id}")
def get_entry(entry_id: str) -> dict[str, object]:
    """Get a single queue entry by ID."""
    entry = _queue.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry.to_dict()


@router.delete("/{entry_id}", status_code=204)
def remove_entry(entry_id: str) -> None:
    """Remove a PENDING entry. 409 if the entry is not in PENDING state."""
    entry = _queue.get(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Entry not found")
    if entry.status != QueueEntryStatus.PENDING:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot remove entry with status '{entry.status.value}'",
        )
    _queue.remove(entry_id)
