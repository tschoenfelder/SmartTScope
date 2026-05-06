"""Last-good auto-gain settings persistence (FR-STORE-008, FR-AG-010 step 4).

Stores one JSON file per camera × mode in the app-state folder::

    ~/.SmartTScope/last_good/<model>_<serial>_<mode>.json
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LastGoodSettings:
    """Persisted result of a successful Auto Gain run."""
    camera_model: str
    camera_serial: str
    mode: str               # "DSO_PREVIEW" | "PLANETARY" | "GUIDE" | "DSO_GUIDED"
    gain: int
    exposure_ms: float
    offset: int
    conversion_gain: str    # "HCG" | "LCG" | "HDR" | "NONE"
    saved_at: str           # ISO-8601 UTC

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> LastGoodSettings:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})  # type: ignore[attr-defined]


def _settings_path(app_state_dir: Path, camera_model: str, camera_serial: str, mode: str) -> Path:
    key = f"{camera_model}_{camera_serial}_{mode}".replace(" ", "_")
    return app_state_dir / "last_good" / f"{key}.json"


class LastGoodStore:
    """Load and save last-good auto-gain settings per camera + mode."""

    def __init__(self, app_state_dir: str | Path) -> None:
        self._dir = Path(app_state_dir)

    def load(self, camera_model: str, camera_serial: str, mode: str) -> LastGoodSettings | None:
        """Return the stored settings, or None if not found."""
        path = _settings_path(self._dir, camera_model, camera_serial, mode)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return LastGoodSettings.from_dict(data)

    def save(self, settings: LastGoodSettings) -> None:
        """Persist *settings*, overwriting any previous value for the same key."""
        path = _settings_path(self._dir, settings.camera_model, settings.camera_serial, settings.mode)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")

    def delete(self, camera_model: str, camera_serial: str, mode: str) -> bool:
        """Delete stored settings.  Returns True if the file existed."""
        path = _settings_path(self._dir, camera_model, camera_serial, mode)
        if path.exists():
            path.unlink()
            return True
        return False

    def all_modes(self, camera_model: str, camera_serial: str) -> list[LastGoodSettings]:
        """Return all stored settings for a given camera (any mode)."""
        prefix = f"{camera_model}_{camera_serial}_".replace(" ", "_")
        results: list[LastGoodSettings] = []
        last_good_dir = self._dir / "last_good"
        if not last_good_dir.exists():
            return results
        for f in last_good_dir.glob("*.json"):
            if f.stem.startswith(prefix):
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    results.append(LastGoodSettings.from_dict(data))
                except (json.JSONDecodeError, TypeError):
                    pass
        return results


def make_last_good(
    camera_model: str,
    camera_serial: str,
    mode: str,
    *,
    gain: int,
    exposure_ms: float,
    offset: int,
    conversion_gain: str,
) -> LastGoodSettings:
    """Convenience factory that fills in saved_at automatically."""
    return LastGoodSettings(
        camera_model=camera_model,
        camera_serial=camera_serial,
        mode=mode,
        gain=gain,
        exposure_ms=exposure_ms,
        offset=offset,
        conversion_gain=conversion_gain,
        saved_at=datetime.now(timezone.utc).isoformat(),
    )
