"""Readiness API — GET /api/readiness.

Returns a synthesized red/yellow/green readiness report covering
config files, storage, ASTAP, camera, mount, and focuser.
"""

from fastapi import APIRouter

from ..services.readiness import ReadinessReport, ReadinessService

router = APIRouter()
_service = ReadinessService()


@router.get("/api/readiness", response_model=ReadinessReport)
def get_readiness() -> ReadinessReport:
    """Return a readiness report. Always HTTP 200."""
    return _service.check()
