"""DiskStorage — persist stacked PNG and JSON session log to a local directory.

File naming spec:
  image : {YYYYMMDD}_{HHMMSS}Z_{session_id[:8]}.png
  log   : {YYYYMMDD}_{HHMMSS}Z_{session_id[:8]}_{target_slug}.json

Both timestamps are derived from `started_at` embedded in the log dict so
that the image and log always share the same stem when written in the same
session.  Falls back to UTC-now when started_at is absent.
"""

from __future__ import annotations

import io
import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from PIL import Image

from ...domain.stretch import auto_stretch
from ...ports.storage import StoragePort

_MIN_FREE_DEFAULT: int = 200 * 1024 * 1024  # 200 MB


class DiskStorage(StoragePort):
    def __init__(
        self,
        output_dir: Path,
        min_free_bytes: int = _MIN_FREE_DEFAULT,
    ) -> None:
        self._output_dir = output_dir
        self._min_free_bytes = min_free_bytes
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ── StoragePort interface ─────────────────────────────────────────────────

    def has_free_space(self) -> bool:
        usage = shutil.disk_usage(self._output_dir)
        return usage.free >= self._min_free_bytes

    def save_image(self, image_data: bytes, session_id: str) -> str:
        pixels = _fits_to_float32(image_data)
        stretched = auto_stretch(pixels)
        png_bytes = _to_png_bytes(stretched)
        stem = _make_stem(session_id)
        path = self._output_dir / f"{stem}.png"
        path.write_bytes(png_bytes)
        return str(path)

    def save_log(self, session_log: dict[str, Any], session_id: str) -> str:
        started_at = _parse_started_at(session_log)
        target_info = session_log.get("target") or {}
        target_name = (
            str(target_info.get("name", "unknown")) if isinstance(target_info, dict) else "unknown"
        )
        target_slug = _slugify(target_name)
        stem = _make_stem(session_id, started_at=started_at)
        path = self._output_dir / f"{stem}_{target_slug}.json"
        path.write_text(json.dumps(session_log, indent=2, default=str), encoding="utf-8")
        return str(path)

    # ── Convenience ───────────────────────────────────────────────────────────

    def free_bytes(self) -> int:
        return shutil.disk_usage(self._output_dir).free


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_stem(session_id: str, *, started_at: datetime | None = None) -> str:
    ts = (started_at or datetime.now(UTC)).strftime("%Y%m%d_%H%M%SZ")
    return f"{ts}_{session_id[:8]}"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", name).strip("_").lower()


def _parse_started_at(session_log: dict[str, Any]) -> datetime | None:
    raw = session_log.get("started_at")
    if isinstance(raw, str):
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            pass
    return None


def _fits_to_float32(data: bytes) -> np.ndarray[Any, np.dtype[Any]]:
    with fits.open(io.BytesIO(data)) as hdul:
        return np.array(hdul[0].data, dtype=np.float32)


def _to_png_bytes(pixels: np.ndarray[Any, np.dtype[np.uint8]]) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(pixels).save(buf, format="PNG")
    return buf.getvalue()
