"""Session folder naming helpers (FR-STORE-003, FR-STORE-004)."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

# Characters not allowed in file/folder names on Linux/macOS/Windows
_FORBIDDEN = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Collapse runs of non-alphanumeric characters to a single underscore
_COLLAPSE = re.compile(r'[^A-Za-z0-9]+')


def sanitize_target_name(target: str) -> str:
    """Return a filesystem-safe version of *target*.

    Spaces and punctuation are collapsed to underscores; forbidden characters
    are removed; leading/trailing underscores are stripped.

    Examples:
        "M42"               → "M42"
        "NGC 1234"          → "NGC_1234"
        "Andromeda (M31)"   → "Andromeda_M31"
        "  /bad\\name:  "   → "bad_name"
    """
    clean = _FORBIDDEN.sub("_", target)
    clean = _COLLAPSE.sub("_", clean)
    return clean.strip("_")


def make_session_path(image_root: str | Path, target: str, session_date: date | None = None) -> Path:
    """Return the session folder path for *target* under *image_root*.

    The folder name follows the pattern ``YYYY-MM-DD_<sanitized-target>/``.
    *session_date* defaults to today when not supplied.

    The path is returned but **not created** — the caller is responsible for
    creating it (allows testing without touching the filesystem).
    """
    d = session_date or date.today()
    safe_name = sanitize_target_name(target)
    if not safe_name:
        raise ValueError(f"Target name {target!r} produces an empty folder name after sanitization")
    folder_name = f"{d.strftime('%Y-%m-%d')}_{safe_name}"
    return Path(image_root) / folder_name
