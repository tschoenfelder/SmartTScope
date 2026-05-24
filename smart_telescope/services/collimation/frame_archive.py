"""CollimationFrameArchive — opt-in FITS frame + JSON sidecar storage."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ...domain.frame import FitsFrame

_log = logging.getLogger(__name__)


class CollimationFrameArchive:
    """Saves accepted collimation frames (FITS) and analysis sidecars (JSON).

    Directory layout::

        <archive_dir>/
            <session_id>/
                measure_donut_0001.fits
                measure_donut_0001.json
                measure_spikes_0002.fits
                measure_spikes_0002.json

    When max_frames_per_session is reached, further saves are silently skipped.
    """

    def __init__(self, archive_dir: Path, max_frames_per_session: int = 50) -> None:
        self._root = Path(archive_dir)
        self._max = max_frames_per_session
        self._lock = threading.Lock()

    def new_session(self, session_id: str) -> None:
        """Create the session subdirectory. Call once at CollimationAssistant.start()."""
        session_dir = self._root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        _log.info("CollimationFrameArchive: new session %s at %s", session_id, session_dir)

    def save_frame(
        self,
        session_id: str,
        state: str,
        frame_index: int,
        captured_at: str,
        exposure_s: float,
        gain: int,
        bit_depth: int,
        ref_x: float,
        ref_y: float,
        raw_frame: "FitsFrame",
        analysis: dict,
    ) -> str | None:
        """Save FITS + JSON sidecar. Returns frame_stem, or None if at cap."""
        session_dir = self._root / session_id
        with self._lock:
            existing = list(session_dir.glob("*.fits"))
            if len(existing) >= self._max:
                _log.debug(
                    "CollimationFrameArchive: session %s at cap (%d), skipping",
                    session_id, self._max,
                )
                return None

        frame_stem = f"{state}_{frame_index:04d}"
        fits_path = session_dir / f"{frame_stem}.fits"
        json_path = session_dir / f"{frame_stem}.json"

        try:
            fits_path.write_bytes(raw_frame.to_fits_bytes())
        except Exception as exc:
            _log.warning("CollimationFrameArchive: FITS write failed: %s", exc)
            return None

        sidecar = {
            "session_id": session_id,
            "state": state,
            "frame_index": frame_index,
            "captured_at": captured_at,
            "exposure_s": exposure_s,
            "gain": gain,
            "bit_depth": bit_depth,
            "ref_x": ref_x,
            "ref_y": ref_y,
            "analysis": analysis,
        }
        try:
            json_path.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
        except Exception as exc:
            _log.warning("CollimationFrameArchive: JSON write failed: %s", exc)

        _log.debug("CollimationFrameArchive: saved %s/%s", session_id, frame_stem)
        return frame_stem

    def list_sessions(self) -> list[dict]:
        """Return sessions sorted newest-first by directory mtime."""
        if not self._root.exists():
            return []
        sessions = []
        for session_dir in sorted(
            self._root.iterdir(),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            if not session_dir.is_dir():
                continue
            fits_files = list(session_dir.glob("*.fits"))
            state_counts: dict[str, int] = {}
            for f in fits_files:
                state = f.stem.rsplit("_", 1)[0]
                state_counts[state] = state_counts.get(state, 0) + 1
            size_bytes = sum(f.stat().st_size for f in session_dir.iterdir())
            sessions.append({
                "session_id": session_dir.name,
                "frame_count": len(fits_files),
                "state_counts": state_counts,
                "size_bytes": size_bytes,
            })
        return sessions

    def list_frames(self, session_id: str) -> list[dict]:
        """Return frames in session sorted by filename (= frame_index order)."""
        session_dir = self._root / session_id
        if not session_dir.exists():
            return []
        frames = []
        for fits_path in sorted(session_dir.glob("*.fits")):
            frame_stem = fits_path.stem
            json_path = session_dir / f"{frame_stem}.json"
            entry: dict = {
                "frame_stem": frame_stem,
                "size_bytes": fits_path.stat().st_size,
            }
            if json_path.exists():
                try:
                    sidecar = json.loads(json_path.read_text(encoding="utf-8"))
                    entry.update({
                        "state": sidecar.get("state"),
                        "frame_index": sidecar.get("frame_index"),
                        "captured_at": sidecar.get("captured_at"),
                        "exposure_s": sidecar.get("exposure_s"),
                        "gain": sidecar.get("gain"),
                    })
                except Exception:
                    pass
            frames.append(entry)
        return frames

    def load_frame(self, session_id: str, frame_stem: str) -> "FitsFrame":
        """Load a stored FITS frame. Raises FileNotFoundError if absent."""
        from ...domain.frame import FitsFrame
        fits_path = self._root / session_id / f"{frame_stem}.fits"
        if not fits_path.exists():
            raise FileNotFoundError(fits_path)
        return FitsFrame.from_fits_bytes(fits_path.read_bytes())

    def load_sidecar(self, session_id: str, frame_stem: str) -> dict:
        """Load JSON sidecar. Raises FileNotFoundError if absent."""
        json_path = self._root / session_id / f"{frame_stem}.json"
        if not json_path.exists():
            raise FileNotFoundError(json_path)
        return json.loads(json_path.read_text(encoding="utf-8"))
