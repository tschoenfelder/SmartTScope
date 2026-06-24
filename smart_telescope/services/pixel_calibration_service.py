"""Pixel-to-RA/DEC calibration service (M7-003 / DD-004).

Triggered lazily on first image-space mount correction request.
Invalidated when optical train, binning, or camera orientation changes.
Failure blocks the requesting operation; user must retry manually.

Calibration procedure:
  1. Capture reference frame; detect brightest-star centroid.
  2. Move mount RA by _RA_MOVE_MS ms; capture; detect centroid; compute RA vector.
  3. Move mount back; move DEC by _DEC_MOVE_MS ms; capture; detect centroid; compute DEC vector.
  4. Move mount back; store PixelCalibration.
"""

from __future__ import annotations

import datetime
import logging
import threading
from typing import TYPE_CHECKING

import numpy as np

from ..domain.pixel_calibration import (
    PixelCalibration,
    PixelCalibrationError,
    PixelCalibrationState,
)

if TYPE_CHECKING:
    from ..ports.camera import CameraPort
    from ..ports.mount import MountPort

_log = logging.getLogger(__name__)

# Mount move duration used during calibration (ms)
_RA_MOVE_MS  = 2_000
_DEC_MOVE_MS = 2_000

# Minimum centroid displacement (pixels) required to accept a vector
_MIN_DISPLACEMENT_PX = 3.0

# Exposure used during calibration (seconds)
_CAL_EXPOSURE_S = 2.0


def _find_centroid(pixels: np.ndarray) -> tuple[float, float]:
    """Return (x, y) centroid of the brightest star using a 16×16 px window."""
    flat = pixels.astype(np.float32)
    if flat.ndim == 3:
        flat = flat[:, :, 0]
    peak_idx = int(np.argmax(flat))
    h, w = flat.shape
    py, px = divmod(peak_idx, w)

    roi = 8
    y0, y1 = max(0, py - roi), min(h, py + roi + 1)
    x0, x1 = max(0, px - roi), min(w, px + roi + 1)
    window = flat[y0:y1, x0:x1]

    total = float(window.sum())
    if total <= 0:
        raise PixelCalibrationError("No star signal found in frame — cannot calibrate")

    ys, xs = np.mgrid[y0:y1, x0:x1]
    cx = float((xs * window).sum() / total)
    cy = float((ys * window).sum() / total)
    return cx, cy


class PixelCalibrationService:
    """Manages pixel-to-RA/DEC calibration lifecycle.

    Thread-safe: all state is protected by a single lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = PixelCalibrationState.UNCALIBRATED
        self._calibration: PixelCalibration | None = None
        self._last_error: str | None = None

    # ── public API ────────────────────────────────────────────────────────────

    @property
    def state(self) -> PixelCalibrationState:
        with self._lock:
            return self._state

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    def get_calibration(self) -> PixelCalibration:
        """Return the current calibration or raise PixelCalibrationError if unavailable."""
        with self._lock:
            if self._state == PixelCalibrationState.CALIBRATED and self._calibration is not None:
                return self._calibration
            if self._state == PixelCalibrationState.FAILED:
                raise PixelCalibrationError(
                    f"Pixel calibration failed: {self._last_error} — retry to run again"
                )
            raise PixelCalibrationError(
                "Pixel calibration not available — run calibration first"
            )

    def invalidate(self, reason: str = "configuration changed") -> None:
        """Clear stored calibration (e.g. optical train, binning, or orientation changed)."""
        with self._lock:
            self._calibration = None
            self._state = PixelCalibrationState.UNCALIBRATED
            self._last_error = None
        _log.info("PixelCalibrationService: invalidated — %s", reason)

    def run(
        self,
        camera: "CameraPort",
        mount: "MountPort",
        optical_train_id: str,
        binning: int,
        camera_orientation_deg: float = 0.0,
    ) -> PixelCalibration:
        """Run the calibration procedure synchronously and store the result.

        Raises PixelCalibrationError on failure (no stars, insufficient displacement, etc.).
        Sets state to FAILED on error so subsequent get_calibration() calls surface the reason.
        """
        with self._lock:
            self._state = PixelCalibrationState.CALIBRATING
            self._last_error = None

        try:
            cal = self._run_procedure(
                camera, mount, optical_train_id, binning, camera_orientation_deg
            )
        except PixelCalibrationError as exc:
            with self._lock:
                self._state = PixelCalibrationState.FAILED
                self._last_error = exc.reason
            raise

        with self._lock:
            self._calibration = cal
            self._state = PixelCalibrationState.CALIBRATED
        _log.info(
            "PixelCalibration complete: ra_vec=(%.2f, %.2f) dec_vec=(%.2f, %.2f)",
            cal.ra_vector_px[0], cal.ra_vector_px[1],
            cal.dec_vector_px[0], cal.dec_vector_px[1],
        )
        return cal

    # ── internals ─────────────────────────────────────────────────────────────

    def _capture_centroid(self, camera: "CameraPort") -> tuple[float, float]:
        frame = camera.capture(_CAL_EXPOSURE_S)
        return _find_centroid(frame.pixels)

    def _run_procedure(
        self,
        camera: "CameraPort",
        mount: "MountPort",
        optical_train_id: str,
        binning: int,
        camera_orientation_deg: float,
    ) -> PixelCalibration:
        # Step 1: reference centroid
        _log.info("PixelCalibration: capturing reference frame")
        ref_x, ref_y = self._capture_centroid(camera)

        # Step 2: RA move — east then back
        _log.info("PixelCalibration: moving RA east %d ms", _RA_MOVE_MS)
        mount.move("e", _RA_MOVE_MS)
        ra_x, ra_y = self._capture_centroid(camera)
        mount.move("w", _RA_MOVE_MS)  # return

        ra_dx = ra_x - ref_x
        ra_dy = ra_y - ref_y
        ra_mag = float(np.hypot(ra_dx, ra_dy))
        if ra_mag < _MIN_DISPLACEMENT_PX:
            raise PixelCalibrationError(
                f"RA move produced only {ra_mag:.1f} px displacement "
                f"(min {_MIN_DISPLACEMENT_PX} px) — star may have drifted or mount not responding"
            )

        # Step 3: DEC move — north then back
        _log.info("PixelCalibration: moving DEC north %d ms", _DEC_MOVE_MS)
        mount.move("n", _DEC_MOVE_MS)
        dec_x, dec_y = self._capture_centroid(camera)
        mount.move("s", _DEC_MOVE_MS)  # return

        dec_dx = dec_x - ref_x
        dec_dy = dec_y - ref_y
        dec_mag = float(np.hypot(dec_dx, dec_dy))
        if dec_mag < _MIN_DISPLACEMENT_PX:
            raise PixelCalibrationError(
                f"DEC move produced only {dec_mag:.1f} px displacement "
                f"(min {_MIN_DISPLACEMENT_PX} px) — star may have drifted or mount not responding"
            )

        return PixelCalibration(
            ra_vector_px=(ra_dx, ra_dy),
            dec_vector_px=(dec_dx, dec_dy),
            optical_train_id=optical_train_id,
            binning=binning,
            camera_orientation_deg=camera_orientation_deg,
            calibrated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
