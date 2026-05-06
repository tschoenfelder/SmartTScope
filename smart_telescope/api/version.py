"""Application version endpoint."""
from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api")

_ROOT = Path(__file__).parent.parent.parent


def _git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
            cwd=_ROOT,
        ).decode().strip()
    except Exception:
        return ""


class VersionInfo(BaseModel):
    version: str
    git_hash: str


@router.get("/version", response_model=VersionInfo)
def get_version() -> VersionInfo:
    return VersionInfo(version="0.1.0", git_hash=_git_hash())
