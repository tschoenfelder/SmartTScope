"""DiagnosticFrameStore — FITS diagnostic frame storage (M8-017 / REQ-FRAME-001..003).

Stores captured frames as FITS files using the standardized filename pattern (REQ-FRAME-002)
and writes all 17 required FITS headers (REQ-FRAME-003).

Directory layout::

    {frame_dir}/{session_id[:8]}/{YYYYMMDDTHHMMSS}_session-{id}_...fits

Retention cleanup deletes session subdirectories older than retention_days,
skipping any that match an active session ID (REQ-FRAME-001).
"""
from __future__ import annotations

import io
import logging
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from ..domain.diagnostic_frame import DiagnosticFrameConfig, DiagnosticStoreMode

_log = logging.getLogger(__name__)


class DiagnosticFrameStore:
    """Saves FITS diagnostic frames and manages retention cleanup."""

    def __init__(self, config: DiagnosticFrameConfig) -> None:
        self._config = config

    # ── Public API ────────────────────────────────────────────────────────────

    def should_save(self, *, is_debug: bool = False, is_failure: bool = False) -> bool:
        """Return True if a frame should be persisted under the current store_mode.

        Args:
            is_debug:   True when the run is a debug/diagnostic run (e.g. diagnostic=true).
            is_failure: True when the service call produced status "failed".
        """
        if not self._config.enabled:
            return False
        mode = self._config.store_mode
        if mode == DiagnosticStoreMode.OFF:
            return False
        if mode == DiagnosticStoreMode.ALWAYS:
            return True
        if mode == DiagnosticStoreMode.DEBUG_ONLY:
            return is_debug
        if mode == DiagnosticStoreMode.FAILURE_ONLY:
            return is_failure
        if mode == DiagnosticStoreMode.DEBUG_OR_FAILURE:
            return is_debug or is_failure
        return False

    def save_frame(
        self,
        frame_data: "np.ndarray",
        *,
        session_id: str,
        section: str,
        run_id: str,
        iteration: int = 0,
        camera_id: str = "unknown",
        optical_train_id: str = "unknown",
        exposure_s: float,
        gain: int = 0,
        offset: int = 0,
        binx: int = 1,
        biny: int = 1,
        pixel_size_um: float | None = None,
        focal_length_mm: float | None = None,
        ra_hours: float | None = None,
        dec_deg: float | None = None,
        tracking: bool | None = None,
        timestamp: datetime | None = None,
    ) -> Path:
        """Save *frame_data* as a FITS file with all required headers.

        Returns the path to the saved file.
        """
        from astropy.io import fits as _fits

        ts = timestamp or datetime.now(UTC)
        filename = _make_filename(
            ts=ts,
            session_id=session_id,
            section=section,
            run_id=run_id,
            iteration=iteration,
            camera_id=camera_id,
            optical_train_id=optical_train_id,
            exposure_s=exposure_s,
            gain=gain,
            offset=offset,
            binx=binx,
            biny=biny,
            ra_hours=ra_hours,
            dec_deg=dec_deg,
        )
        dest_dir = Path(self._config.frame_dir) / session_id[:8]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / filename

        hdr = _fits.Header()
        hdr["SESSION"]  = (session_id[:8],                      "Session ID (first 8 chars)")
        hdr["SECTION"]  = (section,                             "Log section name")
        hdr["RUNID"]    = (run_id[:8],                          "Service-call run ID")
        hdr["ITER"]     = (iteration,                           "0-based iteration index")
        hdr["CAMERA"]   = (camera_id,                           "Camera identifier")
        hdr["OPTTRAIN"] = (optical_train_id,                    "Optical train identifier")
        hdr["EXPTIME"]  = (exposure_s,                          "Exposure time [s]")
        hdr["GAIN"]     = (gain,                                "Camera gain")
        hdr["OFFSET"]   = (offset,                              "Camera offset")
        hdr["BINX"]     = (binx,                                "X binning factor")
        hdr["BINY"]     = (biny,                                "Y binning factor")
        hdr["PIXSIZE"]  = (pixel_size_um if pixel_size_um is not None else -1.0,
                          "Pixel size [um]; -1 = unknown")
        hdr["FOCALLEN"] = (focal_length_mm if focal_length_mm is not None else -1.0,
                          "Focal length [mm]; -1 = unknown")
        hdr["RA"]       = (ra_hours * 15.0 if ra_hours is not None else -999.0,
                          "Right ascension [deg]; -999 = unknown")
        hdr["DEC"]      = (dec_deg if dec_deg is not None else -999.0,
                          "Declination [deg]; -999 = unknown")
        hdr["TRACKING"] = (bool(tracking) if tracking is not None else False,
                          "Mount tracking active")
        hdr["DATE-OBS"] = (ts.isoformat(),                      "Observation UTC timestamp")

        hdu = _fits.PrimaryHDU(data=frame_data.astype(np.float32), header=hdr)
        hdu.writeto(str(dest), overwrite=True)
        _log.debug("Saved diagnostic frame: %s", dest)
        return dest

    def cleanup_old_frames(self, active_session_ids: "set[str]") -> int:
        """Delete session subdirectories older than retention_days.

        Directories whose name (8-char session prefix) matches any active session ID
        are preserved even if they are old.

        Returns the number of directories deleted.
        """
        base = Path(self._config.frame_dir)
        if not base.exists():
            return 0
        cutoff = datetime.now(UTC) - timedelta(days=self._config.retention_days)
        active_prefixes = {sid[:8] for sid in active_session_ids}
        deleted = 0
        for subdir in base.iterdir():
            if not subdir.is_dir():
                continue
            if subdir.name in active_prefixes:
                continue
            mtime = datetime.fromtimestamp(subdir.stat().st_mtime, tz=UTC)
            if mtime < cutoff:
                import shutil
                try:
                    shutil.rmtree(str(subdir))
                    deleted += 1
                    _log.info("Deleted old diagnostic frame dir: %s", subdir)
                except Exception as exc:
                    _log.warning("Could not delete %s: %s", subdir, exc)
        return deleted


# ── Filename builder ──────────────────────────────────────────────────────────

def _safe(s: str, max_len: int = 32) -> str:
    """Replace filesystem-unsafe chars and truncate."""
    out = s.replace("/", "-").replace("\\", "-").replace(":", "-").replace(" ", "_")
    return out[:max_len]


def _make_filename(
    *,
    ts: datetime,
    session_id: str,
    section: str,
    run_id: str,
    iteration: int,
    camera_id: str,
    optical_train_id: str,
    exposure_s: float,
    gain: int,
    offset: int,
    binx: int,
    biny: int,
    ra_hours: float | None,
    dec_deg: float | None,
) -> str:
    """Build the standardized diagnostic FITS filename (REQ-FRAME-002).

    Pattern::

        YYYYMMDDTHHMMSS_session-<id>_<section>_<run_id>_iter-<n>_<camera_id>_<optical_train_id>
        _exp-<s>s_gain-<g>_offset-<o>_bin-<x>x<y>_ra-<ra>_dec-<dec>.fits
    """
    date_part = ts.strftime("%Y%m%dT%H%M%S")
    ra_part   = f"{ra_hours:.4f}h" if ra_hours is not None else "none"
    dec_part  = f"{dec_deg:+.4f}"  if dec_deg  is not None else "none"
    parts = [
        date_part,
        f"session-{_safe(session_id[:8])}",
        _safe(section),
        _safe(run_id[:8]),
        f"iter-{iteration}",
        _safe(camera_id),
        _safe(optical_train_id),
        f"exp-{exposure_s:.3f}s",
        f"gain-{gain}",
        f"offset-{offset}",
        f"bin-{binx}x{biny}",
        f"ra-{ra_part}",
        f"dec-{dec_part}",
    ]
    return "_".join(parts) + ".fits"
