"""Extended setup check service — exercises hardware beyond static readiness checks.

Each method runs a short live test and returns a structured result dict.
Designed to be called from the API layer one step at a time (or all at once).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from ..domain.camera_diagnostic import CameraDiagnosticReport, CameraDiagnosticStatus
from ..ports.mount import MountState
from ..services.mount_operations import MountSlewingError, home_sequence
from ..services.hardware_coordinator import CommandConflictError

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..services.frame_analyzer import FrameAnalyzerProtocol

_log = logging.getLogger(__name__)


# ── result models ────────────────────────────────────────────────────────────

@dataclass
class FocuserMoveResult:
    ok: bool
    before: int | None = None
    after: int | None = None
    delta: int | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "before": self.before, "after": self.after,
                "delta": self.delta, "message": self.message}


@dataclass
class MountSlewResult:
    ok: bool
    ra_before: float | None = None
    dec_before: float | None = None
    ra_after: float | None = None
    dec_after: float | None = None
    elapsed_s: float | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "ra_before": self.ra_before, "dec_before": self.dec_before,
                "ra_after": self.ra_after, "dec_after": self.dec_after,
                "elapsed_s": self.elapsed_s, "message": self.message}


@dataclass
class PerCameraSolveResult:
    role: str
    camera_index: int
    solved: bool
    ra: float | None = None
    dec: float | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"role": self.role, "camera_index": self.camera_index, "solved": self.solved,
                "ra": self.ra, "dec": self.dec, "error": self.error}


@dataclass
class PlateSolveResult:
    ok: bool
    per_camera: list[PerCameraSolveResult] = field(default_factory=list)
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "per_camera": [c.to_dict() for c in self.per_camera],
                "message": self.message}


@dataclass
class HomeResult:
    ok: bool
    elapsed_s: float | None = None
    state_after: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "elapsed_s": self.elapsed_s,
                "state_after": self.state_after, "message": self.message}


# ── individual step implementations ──────────────────────────────────────────

def run_focuser_move(focuser: Any, steps: int = 100) -> FocuserMoveResult:
    """Move focuser by *steps*, verify position changed, then restore."""
    if not focuser.is_available:
        return FocuserMoveResult(ok=False, message="Focuser not available")

    try:
        before = focuser.get_position()
        focuser.move(before + steps)      # absolute target = current + relative delta
        after = focuser.get_position()
        delta = after - before

        focuser.move(before)              # restore to original absolute position

        if delta == 0:
            return FocuserMoveResult(ok=False, before=before, after=after, delta=delta,
                                     message="Focuser did not move — check hardware connection")
        return FocuserMoveResult(ok=True, before=before, after=after, delta=delta,
                                 message=f"Moved {delta:+d} steps (requested {steps:+d})")
    except Exception as exc:
        return FocuserMoveResult(ok=False, message=f"Focuser error: {exc}")


def run_mount_slew(
    mount: Any,
    device_state: Any,
    offset_dec_deg: float = 5.0,
    timeout_s: float = 40.0,
) -> MountSlewResult:
    """GoTo (current RA, current Dec + offset), wait for TRACKING, return result."""
    try:
        state = mount.get_state()
    except Exception as exc:
        return MountSlewResult(ok=False, message=f"Cannot read mount state: {exc}")

    if state in (MountState.PARKED, MountState.UNKNOWN):
        return MountSlewResult(ok=False,
                               message=f"Mount is {state.name} — unpark and enable tracking first")

    try:
        pos = mount.get_position()
    except Exception as exc:
        return MountSlewResult(ok=False, message=f"Cannot read mount position: {exc}")

    ra_before  = pos.ra
    dec_before = pos.dec
    # Clamp target Dec to [-80, +80] to avoid polar singularities
    dec_target = max(-80.0, min(80.0, dec_before + offset_dec_deg))
    ra_target  = ra_before

    t0 = time.monotonic()
    try:
        ok = mount.goto(ra_target, dec_target)
    except Exception as exc:
        return MountSlewResult(ok=False, ra_before=ra_before, dec_before=dec_before,
                               message=f"GoTo command failed: {exc}")

    if not ok:
        return MountSlewResult(ok=False, ra_before=ra_before, dec_before=dec_before,
                               message="GoTo command rejected by mount")

    # Wait for SLEWING to start then finish (state → TRACKING)
    slew_started = device_state.wait_while_mount_state(state, timeout_s=5.0)
    if not slew_started:
        return MountSlewResult(ok=False, ra_before=ra_before, dec_before=dec_before,
                               message="Mount did not start slewing within 5 s")

    tracking_reached = device_state.wait_for_mount_state(MountState.TRACKING,
                                                          timeout_s=timeout_s)
    elapsed = round(time.monotonic() - t0, 1)

    if not tracking_reached:
        return MountSlewResult(ok=False, ra_before=ra_before, dec_before=dec_before,
                               elapsed_s=elapsed,
                               message=f"Slew did not complete within {timeout_s:.0f} s")

    try:
        pos2 = mount.get_position()
        ra_after  = pos2.ra
        dec_after = pos2.dec
    except Exception:
        ra_after = dec_after = None

    dec_moved = abs((dec_after or dec_before) - dec_before)
    if dec_moved < 1.0:
        return MountSlewResult(ok=False, ra_before=ra_before, dec_before=dec_before,
                               ra_after=ra_after, dec_after=dec_after, elapsed_s=elapsed,
                               message=f"Mount tracking but position barely changed ({dec_moved:.2f}°)")

    return MountSlewResult(ok=True, ra_before=ra_before, dec_before=dec_before,
                           ra_after=ra_after, dec_after=dec_after, elapsed_s=elapsed,
                           message=f"Slewed {dec_moved:.1f}° in {elapsed} s")


def run_plate_solve(
    registry: Any,
    runtime: Any,
    solver: Any,
    exposure_s: float = 3.0,
    timeout_s: float = 15.0,
) -> PlateSolveResult:
    """Capture from each configured train and attempt a plate solve."""
    trains = registry.all() if registry is not None else []
    if not trains:
        return PlateSolveResult(ok=False, message="No optical trains configured")

    results: list[PerCameraSolveResult] = []
    for train in trains:
        try:
            camera = runtime.get_camera_by_role(train.camera_role)
            frame  = camera.capture(exposure_s)
        except Exception as exc:
            results.append(PerCameraSolveResult(
                role=train.name, camera_index=train.camera_index,
                solved=False, error=f"Capture failed: {exc}",
            ))
            continue

        try:
            result = solver.solve(
                frame,
                pixel_scale_arcsec=train.pixel_scale_arcsec,
                timeout_s=timeout_s,
            )
            if result.solved:
                results.append(PerCameraSolveResult(
                    role=train.name, camera_index=train.camera_index,
                    solved=True, ra=result.ra_h, dec=result.dec_deg,
                ))
            else:
                results.append(PerCameraSolveResult(
                    role=train.name, camera_index=train.camera_index,
                    solved=False, error="No solution found — check pointing and focus",
                ))
        except Exception as exc:
            results.append(PerCameraSolveResult(
                role=train.name, camera_index=train.camera_index,
                solved=False, error=f"Solver error: {exc}",
            ))

    all_solved = all(r.solved for r in results)
    solved_count = sum(1 for r in results if r.solved)
    return PlateSolveResult(
        ok=all_solved,
        per_camera=results,
        message=f"{solved_count}/{len(results)} camera(s) solved",
    )


def run_home_return(
    mount: Any,
    device_state: Any,
    coordinator: Any,
    timeout_s: float = 90.0,
) -> HomeResult:
    """Slew mount to OnStep stored home position and wait for TRACKING."""
    try:
        state_before = mount.get_state()
    except Exception as exc:
        return HomeResult(ok=False, message=f"Cannot read mount state: {exc}")

    t0 = time.monotonic()
    try:
        home_sequence(mount, coordinator)
    except MountSlewingError as exc:
        return HomeResult(ok=False, message=f"Home rejected — {exc}")
    except CommandConflictError as exc:
        return HomeResult(ok=False, message=f"Home blocked — {exc}")
    except Exception as exc:
        return HomeResult(ok=False, message=f"Home command failed: {exc}")

    # Wait for slew to start
    device_state.wait_while_mount_state(state_before, timeout_s=5.0)
    # Wait for TRACKING (slew finished)
    reached = device_state.wait_for_mount_state(MountState.TRACKING, timeout_s=timeout_s)
    elapsed = round(time.monotonic() - t0, 1)

    try:
        state_after = mount.get_state().name
    except Exception:
        state_after = "UNKNOWN"

    if not reached:
        return HomeResult(ok=False, elapsed_s=elapsed, state_after=state_after,
                          message=f"Mount did not reach home within {timeout_s:.0f} s")

    return HomeResult(ok=True, elapsed_s=elapsed, state_after=state_after,
                      message=f"Homed to OnStep home in {elapsed} s")


# ── Per-camera diagnostic report (M8-019 / REQ-SETUP-001..002) ───────────────

# Minimum stars required before attempting ASTAP (OPEN-003).
MIN_STARS_BEFORE_SOLVE = 15


def run_camera_diagnostic(
    registry: Any,
    runtime: Any,
    solver: Any,
    device_state: Any,
    exposure_s: float = 3.0,
    solver_timeout_s: float = 15.0,
    gate_check_fn: "Any | None" = None,
    frame_analyzer: "FrameAnalyzerProtocol | None" = None,
) -> list[CameraDiagnosticReport]:
    """Run a per-camera extended diagnostic (REQ-SETUP-001).

    For each camera known to the optical train registry:
    1. Determine connectivity and assignment state.
    2. Optionally check operation gate (if gate_check_fn provided).
    3. Capture a frame (exposure_s).
    4. Estimate star count, median FWHM, and background ADU.
    5. Attempt a plate solve when star count >= MIN_STARS_BEFORE_SOLVE.
    6. Produce a 19-field CameraDiagnosticReport per camera.

    Args:
        registry:       OpticalTrainRegistry (may be None → empty report).
        runtime:        RuntimeContext — used to access cameras.
        solver:         SolverPort instance.
        device_state:   DeviceStateService — used to read connection state.
        exposure_s:     Capture exposure time.
        solver_timeout_s: ASTAP solve timeout.
        gate_check_fn:  Optional callable(camera_role) → None; raises HTTPException on block.
    """
    trains = registry.all() if registry is not None else []
    reports: list[CameraDiagnosticReport] = []

    for train in trains:
        rep = CameraDiagnosticReport(
            camera_id=str(getattr(train, "camera_id", "") or f"cam-{train.camera_index}"),
            camera_role=str(getattr(train, "camera_role", train.name)),
            optical_train_id=str(train.name),
            camera_index=int(train.camera_index),
            is_enabled_in_config=True,   # in registry → enabled
            is_assigned_to_train=True,   # in registry → assigned
            is_sdk_detected=True,        # updated below
            status=CameraDiagnosticStatus.NOT_ATTEMPTED,
        )

        # ── Check operation gate ─────────────────────────────────────────────
        if gate_check_fn is not None:
            try:
                gate_check_fn(train.camera_role)
            except Exception as exc:
                rep.status = CameraDiagnosticStatus.OPERATION_BLOCKED
                rep.status_detail = str(exc)
                reports.append(rep)
                continue

        # ── Capture frame ────────────────────────────────────────────────────
        try:
            camera = runtime.get_camera_by_role(train.camera_role)
        except Exception as exc:
            rep.is_sdk_detected = False
            rep.status = CameraDiagnosticStatus.DISCONNECTED
            rep.status_detail = f"Camera not accessible: {exc}"
            reports.append(rep)
            continue

        try:
            frame = camera.capture(exposure_s)
            rep.frame_captured_at = datetime.now(UTC).isoformat()
            rep.exposure_ms_used  = exposure_s * 1000.0
        except Exception as exc:
            rep.status = CameraDiagnosticStatus.CAPTURE_FAILED
            rep.status_detail = f"Capture error: {exc}"
            reports.append(rep)
            continue

        # ── Image analysis ───────────────────────────────────────────────────
        try:
            if frame_analyzer is not None:
                ext = frame_analyzer.analyze_frame(
                    frame.pixels,
                    exposure_s=exposure_s,
                    gain=None,
                    offset=None,
                )
                rep.star_count     = ext.stars_found
                rep.median_fwhm_px = None  # external analyzer does not expose FWHM
                rep.background_adu = None
            else:
                star_count, median_fwhm, background = _analyse_frame(frame.pixels)
                rep.star_count     = star_count
                rep.median_fwhm_px = median_fwhm
                rep.background_adu = background
        except Exception as exc:
            _log.debug("Frame analysis failed for %s: %s", train.name, exc)

        if (rep.star_count is not None) and (rep.star_count < MIN_STARS_BEFORE_SOLVE):
            rep.status = CameraDiagnosticStatus.INSUFFICIENT_STARS
            rep.status_detail = (
                f"Only {rep.star_count} star(s) detected "
                f"(min {MIN_STARS_BEFORE_SOLVE} required for plate solve)"
            )
            reports.append(rep)
            continue

        # ── Plate solve ──────────────────────────────────────────────────────
        pixel_scale = getattr(train, "pixel_scale_arcsec", None)
        if pixel_scale is None:
            rep.status = CameraDiagnosticStatus.METADATA_MISSING
            rep.status_detail = "pixel_scale_arcsec not set for this optical train"
            reports.append(rep)
            continue

        try:
            result = solver.solve(frame, pixel_scale, timeout_s=solver_timeout_s)
        except Exception as exc:
            rep.status = CameraDiagnosticStatus.ASTAP_FAILED
            rep.status_detail = f"Solver error: {exc}"
            reports.append(rep)
            continue

        if not result.success:
            rep.status = CameraDiagnosticStatus.ASTAP_FAILED
            rep.status_detail = "ASTAP: no solution found — check pointing, focus, and star catalog"
            reports.append(rep)
            continue

        rep.ra_hours = result.ra
        rep.dec_deg  = result.dec
        rep.status   = CameraDiagnosticStatus.SOLVED
        rep.status_detail = f"Solved: RA={result.ra:.4f}h Dec={result.dec:+.2f}°"
        reports.append(rep)

    return reports


def _analyse_frame(data: "np.ndarray") -> tuple[int, float | None, float]:
    """Estimate star count, median FWHM, and background ADU from a 2-D array.

    Uses a simple threshold approach (background + 5σ) and basic connected
    components to count star-like blobs.  Returns (count, fwhm_or_None, bg).
    FWHM is estimated as √area of detected blobs (rough approximation).
    """
    arr = np.asarray(data, dtype=np.float32)
    if arr.ndim == 3:
        arr = arr.mean(axis=2)

    background = float(np.median(arr))
    stddev = float(np.std(arr))
    threshold = background + 5.0 * stddev

    binary = (arr > threshold).astype(np.uint8)

    try:
        from scipy.ndimage import label
        labeled, n_blobs = label(binary)
    except ImportError:
        # Rough fallback: sum of above-threshold pixels / expected star area
        n_blobs = int(binary.sum() // 25)
        return n_blobs, None, background

    fwhm_values: list[float] = []
    valid_count = 0
    total_pixels = arr.size
    for i in range(1, n_blobs + 1):
        blob_pixels = int((labeled == i).sum())
        if blob_pixels < 4:
            continue  # hot pixel
        if blob_pixels > total_pixels * 0.02:
            continue  # too large — galaxy/nebula
        valid_count += 1
        fwhm_values.append(float(np.sqrt(blob_pixels)))  # rough FWHM

    median_fwhm = float(np.median(fwhm_values)) if fwhm_values else None
    return valid_count, median_fwhm, background
