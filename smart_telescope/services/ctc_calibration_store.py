"""CTCCalibrationStore — file-backed store for click-to-center calibrations.

Stores calibrations in ~/.SmartTScope/ctc_calibration.json.
Keyed by "optical_train:binning".
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from ..domain.ctc_calibration import CTCCalibration

_log = logging.getLogger(__name__)

_DEFAULT_PATH = Path.home() / ".SmartTScope" / "ctc_calibration.json"


class CTCCalibrationStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _DEFAULT_PATH
        self._lock = threading.Lock()
        self._cache: dict[str, CTCCalibration] | None = None

    def _load(self) -> dict[str, CTCCalibration]:
        if not self._path.exists():
            return {}
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            return {k: CTCCalibration.from_dict(v) for k, v in raw.items()}
        except Exception as exc:
            _log.warning("CTCCalibrationStore: failed to load %s: %s", self._path, exc)
            return {}

    def _save(self, data: dict[str, CTCCalibration]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({k: v.to_dict() for k, v in data.items()}, indent=2),
            encoding="utf-8",
        )

    def get(self, optical_train: str, binning: int) -> CTCCalibration | None:
        """Return calibration for this optical_train/binning, or None if absent."""
        with self._lock:
            data = self._load()
            key = f"{optical_train}:{binning}"
            return data.get(key)

    def put(self, cal: CTCCalibration) -> None:
        """Store (or overwrite) a calibration record."""
        with self._lock:
            data = self._load()
            data[cal.key] = cal
            self._save(data)
            _log.info("CTCCalibrationStore: saved %s", cal.key)

    def delete(self, optical_train: str, binning: int) -> bool:
        """Remove calibration for this key. Returns True if it existed."""
        key = f"{optical_train}:{binning}"
        with self._lock:
            data = self._load()
            if key not in data:
                return False
            del data[key]
            self._save(data)
            return True

    def all(self) -> dict[str, CTCCalibration]:
        with self._lock:
            return self._load()
