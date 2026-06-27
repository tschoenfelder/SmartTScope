"""Click-to-center iterative centering loop — M8-028 / REQ-CLICK-004.

Algorithm per iteration:
  1. Capture a frame from the camera.
  2. Find the target via click refinement (star centroid / ring center).
  3. Compute pixel offset from the frame centre.
  4. Convert offset to angular move using CTCCalibration.
  5. Clamp to max_single_move_px; apply iteration fraction.
  6. Issue mount move; log result.
  7. Stop when within center_tolerance_px or max_iterations reached.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import asdict, dataclass, field

_log = logging.getLogger(__name__)


@dataclass
class CTCIterationLog:
    iteration: int
    target_raw_x: int
    target_raw_y: int
    target_refined_x: int
    target_refined_y: int
    offset_x_px: float          # pixels from frame centre (positive = right)
    offset_y_px: float          # pixels from frame centre (positive = down)
    offset_arcsec_ra: float
    offset_arcsec_dec: float
    move_dir_ra: str            # 'e' | 'w' | 'none'
    move_dir_dec: str           # 'n' | 's' | 'none'
    move_ms_ra: int
    move_ms_dec: int
    within_tolerance: bool
    refinement_method: str
    elapsed_s: float

    def to_json_line(self) -> str:
        return json.dumps({"event": "CTC_ITERATION", **asdict(self)})


@dataclass
class CTCLoopResult:
    completed: bool               # True when target centred within tolerance
    cancelled: bool
    iterations: list[CTCIterationLog] = field(default_factory=list)
    final_offset_px: tuple[float, float] | None = None
    stop_reason: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.final_offset_px is not None:
            d["final_offset_px"] = list(self.final_offset_px)
        return d


def _pixel_offset_to_move(
    offset_x_px: float,
    offset_y_px: float,
    arcsec_per_px_x: float,
    arcsec_per_px_y: float,
    rotation_deg: float,
    center_rate_arcsec_per_sec: float,
    fraction: float,
    max_px: float,
) -> tuple[float, float, str, str, int, int]:
    """Convert pixel offset to (arcsec_ra, arcsec_dec, dir_ra, dir_dec, ms_ra, ms_dec).

    Rotation is the angle from camera X to RA axis (counter-clockwise positive).
    Pixel convention: +x is right (East in a correctly-oriented image),
                      +y is down  (South).
    """
    # Clamp offset magnitude to max_px before conversion
    mag = math.sqrt(offset_x_px ** 2 + offset_y_px ** 2)
    if mag > max_px:
        scale = max_px / mag
        offset_x_px *= scale
        offset_y_px *= scale

    rad = math.radians(rotation_deg)
    cos_r, sin_r = math.cos(rad), math.sin(rad)

    # Project into RA/DEC axes
    ra_px  = offset_x_px * cos_r + offset_y_px * sin_r
    dec_px = -offset_x_px * sin_r + offset_y_px * cos_r

    arcsec_ra  = ra_px  * arcsec_per_px_x * fraction
    arcsec_dec = dec_px * arcsec_per_px_y * fraction

    ms_ra  = int(abs(arcsec_ra)  / center_rate_arcsec_per_sec * 1000)
    ms_dec = int(abs(arcsec_dec) / center_rate_arcsec_per_sec * 1000)

    dir_ra  = "w" if arcsec_ra > 0 else ("e" if arcsec_ra < 0 else "none")
    dir_dec = "n" if arcsec_dec < 0 else ("s" if arcsec_dec > 0 else "none")

    return arcsec_ra, arcsec_dec, dir_ra, dir_dec, ms_ra, ms_dec


def run_centering_loop(
    *,
    camera,
    mount,
    calibration,
    target_x_px: int,
    target_y_px: int,
    refinement_mode: str = "star_centroid",
    search_radius: int = 40,
    max_iterations: int = 5,
    center_tolerance_px: float = 20.0,
    max_single_move_px: float = 300.0,
    move_fraction: float = 0.5,
    center_rate_arcsec_per_sec: float = 120.0,
    allow_tracking_off: bool = True,
    cancellation_flag: threading.Event | None = None,
    exposure_s: float = 2.0,
    gain: int = 100,
) -> CTCLoopResult:
    """Run the iterative click-to-center loop.

    camera: CameraPort — used to capture frames for each iteration
    mount: MountPort — used to issue centering moves
    calibration: CTCCalibration — pixel-to-sky mapping
    target_x_px/y_px: initial target click position in image pixels
    """
    from ..domain.click_refinement import refine_click

    iterations: list[CTCIterationLog] = []
    _t_start = time.monotonic()

    for i in range(1, max_iterations + 1):
        if cancellation_flag and cancellation_flag.is_set():
            return CTCLoopResult(
                completed=False, cancelled=True, iterations=iterations,
                stop_reason="Cancelled by user.",
            )

        # Capture frame
        try:
            frame = camera.capture(exposure_s, gain=gain, offset=0)
        except Exception as exc:
            return CTCLoopResult(
                completed=False, cancelled=False, iterations=iterations,
                stop_reason=f"Camera capture failed on iteration {i}: {exc}",
            )

        h, w = frame.pixels.shape[:2]
        frame_cx, frame_cy = w // 2, h // 2

        # Refine target
        refined = refine_click(frame.pixels, target_x_px, target_y_px,
                               mode=refinement_mode, search_radius=search_radius)

        offset_x = float(refined.refined_x - frame_cx)
        offset_y = float(refined.refined_y - frame_cy)
        dist_px = math.sqrt(offset_x ** 2 + offset_y ** 2)

        within = dist_px <= center_tolerance_px

        arcsec_ra, arcsec_dec, dir_ra, dir_dec, ms_ra, ms_dec = _pixel_offset_to_move(
            offset_x, offset_y,
            calibration.arcsec_per_px_x,
            calibration.arcsec_per_px_y,
            calibration.rotation_deg,
            center_rate_arcsec_per_sec,
            move_fraction,
            max_single_move_px,
        )

        log_entry = CTCIterationLog(
            iteration=i,
            target_raw_x=refined.raw_x, target_raw_y=refined.raw_y,
            target_refined_x=refined.refined_x, target_refined_y=refined.refined_y,
            offset_x_px=offset_x, offset_y_px=offset_y,
            offset_arcsec_ra=arcsec_ra, offset_arcsec_dec=arcsec_dec,
            move_dir_ra=dir_ra, move_dir_dec=dir_dec,
            move_ms_ra=ms_ra, move_ms_dec=ms_dec,
            within_tolerance=within,
            refinement_method=refined.method,
            elapsed_s=round(time.monotonic() - _t_start, 2),
        )
        iterations.append(log_entry)
        _log.info(log_entry.to_json_line())

        if within:
            return CTCLoopResult(
                completed=True, cancelled=False, iterations=iterations,
                final_offset_px=(offset_x, offset_y),
                stop_reason=f"Centred in {i} iteration(s).",
            )

        # Execute moves
        if dir_ra != "none" and ms_ra > 0:
            try:
                mount.move(dir_ra, ms_ra)
            except Exception as exc:
                return CTCLoopResult(
                    completed=False, cancelled=False, iterations=iterations,
                    final_offset_px=(offset_x, offset_y),
                    stop_reason=f"Mount move failed: {exc}",
                )

        if cancellation_flag and cancellation_flag.is_set():
            return CTCLoopResult(
                completed=False, cancelled=True, iterations=iterations,
                final_offset_px=(offset_x, offset_y),
                stop_reason="Cancelled by user.",
            )

        if dir_dec != "none" and ms_dec > 0:
            try:
                mount.move(dir_dec, ms_dec)
            except Exception as exc:
                return CTCLoopResult(
                    completed=False, cancelled=False, iterations=iterations,
                    final_offset_px=(offset_x, offset_y),
                    stop_reason=f"Mount move failed: {exc}",
                )

        # Use frame centre as target for next iteration (object should now be closer to centre)
        target_x_px = frame_cx
        target_y_px = frame_cy

    final_offset = (offset_x, offset_y) if iterations else None  # type: ignore[possibly-undefined]
    return CTCLoopResult(
        completed=False, cancelled=False, iterations=iterations,
        final_offset_px=final_offset,
        stop_reason=f"Max iterations ({max_iterations}) reached without centering.",
    )
