"""Collimation assistant REST API — Phase 1.3.

Endpoints:
  GET  /api/collimation/status   — current state + instruction
  POST /api/collimation/start    — begin session (IDLE → PRECHECK)
  POST /api/collimation/pause    — pause background work
  POST /api/collimation/resume   — resume after pause
  POST /api/collimation/cancel   — abort and reset to IDLE
  POST /api/collimation/next     — advance a USER_WAIT state with user input
  POST /api/collimation/retry    — reset after FAILED or COMPLETE
  GET  /api/collimation/overlay  — latest measurement for camera overlay
  GET  /api/collimation/report   — session summary
"""
from __future__ import annotations

import logging
import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .deps import get_camera, get_focuser, get_mount
from ..services.collimation.assistant import CollimationAssistant

_log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/collimation", tags=["collimation"])

_assistant: CollimationAssistant | None = None
_assistant_lock = threading.Lock()


def _get_assistant() -> CollimationAssistant:
    global _assistant
    if _assistant is None:
        with _assistant_lock:
            if _assistant is None:
                _assistant = CollimationAssistant(
                    camera=get_camera(),
                    mount=get_mount(),
                    focuser=get_focuser(),
                )
    return _assistant


# ── Request schemas ───────────────────────────────────────────────────────────

class NextPayload(BaseModel):
    """Payload for POST /next.

    For SELECT_STAR: provide ra + dec.
    For GUIDE_ROUGH/FINE: set finish=true to declare the phase done.
    For MASKLESS_VALIDATION: set accept=false to request more adjustment.
    """
    ra:     float | None = None
    dec:    float | None = None
    finish: bool = False
    accept: bool = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
def collimation_status() -> dict[str, Any]:
    return _get_assistant().status


@router.post("/start")
def collimation_start() -> dict[str, Any]:
    try:
        _get_assistant().start()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.post("/pause")
def collimation_pause() -> dict[str, Any]:
    try:
        _get_assistant().pause()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.post("/resume")
def collimation_resume() -> dict[str, Any]:
    try:
        _get_assistant().resume()
    except Exception as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.post("/cancel")
def collimation_cancel() -> dict[str, Any]:
    _get_assistant().cancel()
    return _get_assistant().status


@router.post("/next")
def collimation_next(payload: NextPayload = NextPayload()) -> dict[str, Any]:
    data: dict[str, Any] = {}
    if payload.ra is not None:
        data["ra"] = payload.ra
    if payload.dec is not None:
        data["dec"] = payload.dec
    if payload.finish:
        data["finish"] = True
    if not payload.accept:
        data["accept"] = False
    try:
        _get_assistant().advance(data)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.post("/retry")
def collimation_retry() -> dict[str, Any]:
    try:
        _get_assistant().retry()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return _get_assistant().status


@router.get("/overlay")
def collimation_overlay() -> dict[str, Any]:
    return _get_assistant().overlay


@router.get("/report")
def collimation_report() -> dict[str, Any]:
    return _get_assistant().report
