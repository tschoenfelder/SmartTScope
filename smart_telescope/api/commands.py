"""Command history API — GET /api/commands (REQ-API-003)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..services.command_history import CommandHistoryService
from . import deps

router = APIRouter(prefix="/api")


@router.get("/commands")
def list_commands(
    command_history: CommandHistoryService = Depends(deps.get_command_history_service),
) -> dict:
    """Return all command records for the current session in chronological order."""
    return {
        "commands": [r.to_dict() for r in command_history.get_all()],
    }
