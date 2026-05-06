"""Calibration master library — path conventions, index, and matching (FR-STORE-005–009).

Directory layout under image_root::

    image_root/
      masters/
        <model>_<serial>/
          biases/  master_bias_*.fits
          darks/   master_dark_*.fits
          flats/   master_flat_*.fits
        calibration_index.json   <- one file listing all masters
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CAL_TYPES = frozenset({"bias", "dark", "flat"})
_INDEX_NAME = "calibration_index.json"


# ── Domain objects ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CalibrationEntry:
    """One master calibration file in the index."""
    cal_type: str               # "bias" | "dark" | "flat"
    camera_model: str
    camera_serial: str
    gain: int
    offset: int
    conversion_gain: str        # "HCG" | "LCG" | "HDR" | "NONE"
    bit_depth: int
    frame_count: int
    relative_path: str          # relative to image_root
    created_at: str             # ISO-8601 UTC
    # type-specific optional fields
    exposure_ms: float | None = None   # dark only
    temperature_c: float | None = None  # dark/flat (ATR585M)
    optical_train: str | None = None   # flat only
    filter_id: str | None = None       # flat only

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CalibrationEntry:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})  # type: ignore[attr-defined]


@dataclass(frozen=True)
class MismatchDetail:
    """One field that prevented an exact match."""
    field: str
    expected: Any
    actual: Any


# ── Path helpers ──────────────────────────────────────────────────────────────

def master_dir(image_root: str | Path, camera_model: str, camera_serial: str, cal_type: str) -> Path:
    """Return the directory for masters of the given type (not created here)."""
    if cal_type not in _CAL_TYPES:
        raise ValueError(f"cal_type must be one of {_CAL_TYPES}, got {cal_type!r}")
    folder_map = {"bias": "biases", "dark": "darks", "flat": "flats"}
    key = f"{camera_model}_{camera_serial}".replace(" ", "_")
    return Path(image_root) / "masters" / key / folder_map[cal_type]


def master_path(
    image_root: str | Path,
    camera_model: str,
    camera_serial: str,
    cal_type: str,
    *,
    gain: int,
    offset: int,
    conversion_gain: str,
    bit_depth: int,
    frame_count: int,
    exposure_ms: float | None = None,
    temperature_c: float | None = None,
    optical_train: str | None = None,
    filter_id: str | None = None,
) -> Path:
    """Return the conventional FITS path for a master calibration frame.

    The filename encodes all matching criteria so the correct file can be
    identified without reading its header.  The path is **not** created.
    """
    parts: list[str] = [f"master_{cal_type}"]

    if cal_type == "dark":
        if exposure_ms is None:
            raise ValueError("exposure_ms is required for dark masters")
        parts.append(f"e{int(exposure_ms)}ms")

    parts += [f"g{gain}", f"o{offset}", conversion_gain.lower(), f"b{bit_depth}"]

    if temperature_c is not None:
        sign = "p" if temperature_c >= 0 else "m"
        parts.append(f"t{sign}{abs(int(temperature_c))}c")

    if cal_type == "flat":
        if optical_train:
            parts.append(optical_train.lower())
        if filter_id:
            parts.append(filter_id.lower())

    parts.append(f"n{frame_count}")
    filename = "_".join(parts) + ".fits"
    return master_dir(image_root, camera_model, camera_serial, cal_type) / filename


# ── Calibration index ─────────────────────────────────────────────────────────

class CalibrationIndex:
    """In-memory index of all master calibration files under *image_root*.

    Load from disk with :meth:`load`; persist with :meth:`save`.
    """

    def __init__(self, image_root: str | Path) -> None:
        self._root = Path(image_root)
        self._entries: list[CalibrationEntry] = []

    # ── mutation ──────────────────────────────────────────────────────────────

    def add(self, entry: CalibrationEntry) -> None:
        """Add or replace an entry (matched by relative_path)."""
        self._entries = [e for e in self._entries if e.relative_path != entry.relative_path]
        self._entries.append(entry)

    def remove(self, relative_path: str) -> bool:
        """Remove entry by relative path.  Returns True if found and removed."""
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.relative_path != relative_path]
        return len(self._entries) < before

    # ── queries ───────────────────────────────────────────────────────────────

    def entries(self, cal_type: str | None = None) -> list[CalibrationEntry]:
        """Return all entries, optionally filtered by *cal_type*."""
        if cal_type is None:
            return list(self._entries)
        return [e for e in self._entries if e.cal_type == cal_type]

    def __len__(self) -> int:
        return len(self._entries)

    # ── persistence ───────────────────────────────────────────────────────────

    def save(self) -> None:
        """Write the index to ``<image_root>/calibration_index.json``."""
        index_path = self._root / _INDEX_NAME
        index_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": [e.to_dict() for e in self._entries]}
        index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, image_root: str | Path) -> CalibrationIndex:
        """Load from ``<image_root>/calibration_index.json`` (empty if missing)."""
        idx = cls(image_root)
        index_path = Path(image_root) / _INDEX_NAME
        if not index_path.exists():
            return idx
        data = json.loads(index_path.read_text(encoding="utf-8"))
        for d in data.get("entries", []):
            idx._entries.append(CalibrationEntry.from_dict(d))
        return idx


# ── Matching ──────────────────────────────────────────────────────────────────

def find_best_match(
    index: CalibrationIndex,
    cal_type: str,
    criteria: dict[str, Any],
) -> tuple[CalibrationEntry | None, list[MismatchDetail]]:
    """Return (best_entry, mismatches) for the given calibration criteria.

    Returns the closest match among entries of *cal_type* that share the
    same ``camera_model`` and ``camera_serial``.  An empty mismatch list means
    an exact match.

    Matching priority (bias):
      exact: gain, offset, conversion_gain, bit_depth
    Matching priority (dark):
      exact: gain, offset, conversion_gain, bit_depth, exposure_ms
      tolerance: temperature_c ±5 °C
    Matching priority (flat):
      exact: optical_train, filter_id
      secondary: gain, offset, conversion_gain, bit_depth
    """
    candidates = [
        e for e in index.entries(cal_type)
        if e.camera_model == criteria.get("camera_model")
        and e.camera_serial == criteria.get("camera_serial")
    ]
    if not candidates:
        return None, []

    # Score each candidate: 0 = perfect, higher = worse
    def _score(entry: CalibrationEntry) -> tuple[int, list[MismatchDetail]]:
        mismatches: list[MismatchDetail] = []
        exact_fields = _exact_fields(cal_type)
        for f in exact_fields:
            expected = criteria.get(f)
            actual = getattr(entry, f, None)
            if expected is not None and actual != expected:
                mismatches.append(MismatchDetail(field=f, expected=expected, actual=actual))

        # Temperature tolerance (±5 °C) for dark frames
        if cal_type == "dark":
            exp_temp = criteria.get("temperature_c")
            if exp_temp is not None and entry.temperature_c is not None:
                if abs(entry.temperature_c - exp_temp) > 5.0:
                    mismatches.append(MismatchDetail("temperature_c", exp_temp, entry.temperature_c))

        return len(mismatches), mismatches

    scored = [(_score(e), e) for e in candidates]
    scored.sort(key=lambda x: x[0][0])
    best_score, best_entry = scored[0][0], scored[0][1]
    return best_entry, best_score[1]


def _exact_fields(cal_type: str) -> list[str]:
    base = ["gain", "offset", "conversion_gain", "bit_depth"]
    if cal_type == "dark":
        return base + ["exposure_ms"]
    if cal_type == "flat":
        return base + ["optical_train", "filter_id"]
    return base  # bias


# ── Factory helpers ───────────────────────────────────────────────────────────

def make_entry(
    image_root: str | Path,
    cal_type: str,
    camera_model: str,
    camera_serial: str,
    *,
    gain: int,
    offset: int,
    conversion_gain: str,
    bit_depth: int,
    frame_count: int,
    exposure_ms: float | None = None,
    temperature_c: float | None = None,
    optical_train: str | None = None,
    filter_id: str | None = None,
) -> CalibrationEntry:
    """Build a :class:`CalibrationEntry` with a conventional relative_path."""
    abs_path = master_path(
        image_root,
        camera_model,
        camera_serial,
        cal_type,
        gain=gain,
        offset=offset,
        conversion_gain=conversion_gain,
        bit_depth=bit_depth,
        frame_count=frame_count,
        exposure_ms=exposure_ms,
        temperature_c=temperature_c,
        optical_train=optical_train,
        filter_id=filter_id,
    )
    relative = str(abs_path.relative_to(Path(image_root)))
    return CalibrationEntry(
        cal_type=cal_type,
        camera_model=camera_model,
        camera_serial=camera_serial,
        gain=gain,
        offset=offset,
        conversion_gain=conversion_gain,
        bit_depth=bit_depth,
        frame_count=frame_count,
        relative_path=relative,
        created_at=datetime.now(timezone.utc).isoformat(),
        exposure_ms=exposure_ms,
        temperature_c=temperature_c,
        optical_train=optical_train,
        filter_id=filter_id,
    )
