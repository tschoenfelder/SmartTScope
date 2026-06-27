"""GET /api/logs — per-section log file paths (REQ-LOG-001)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from . import deps
from ..services.section_logger import SectionLogger

router = APIRouter(prefix="/api")


@router.get("/logs")
def list_log_paths(
    section_logger: SectionLogger = Depends(deps.get_section_logger),
) -> dict:
    """Return the file path for each log section.

    Values are ``null`` when ``LOG_DIR`` is not configured (in-memory only).
    """
    return {"logs": section_logger.get_paths()}
