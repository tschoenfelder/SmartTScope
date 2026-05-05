"""App-state folder discovery (FR-STORE-001).

Discovery order:
  1. Explicit path passed by caller (e.g. from APP_STATE_DIR config).
  2. ~/.SmartTScope exists → use it.
  3. ~/.smarttscope exists → use it.
  4. Neither → create ~/.SmartTScope.
"""
from __future__ import annotations

from pathlib import Path

_CANONICAL = Path.home() / ".SmartTScope"
_LOWERCASE = Path.home() / ".smarttscope"


def resolve_app_state_dir(explicit: str | Path | None = None) -> Path:
    """Return (and create if needed) the SmartTScope app-state folder.

    *explicit* is an override path (e.g. from APP_STATE_DIR config).
    The folder is created if it doesn't exist yet.
    """
    if explicit:
        path = Path(explicit)
        path.mkdir(parents=True, exist_ok=True)
        return path

    if _CANONICAL.exists():
        return _CANONICAL
    if _LOWERCASE.exists():
        return _LOWERCASE

    # Neither exists — create the canonical name
    _CANONICAL.mkdir(parents=True, exist_ok=True)
    return _CANONICAL
