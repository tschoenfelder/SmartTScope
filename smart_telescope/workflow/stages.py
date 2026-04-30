"""Stage functions for the vertical-slice session pipeline.

Each stage is a pure function that takes a StageContext and a SessionLog.
Stages raise WorkflowError on non-recoverable failure.  The VerticalSliceRunner
in runner.py owns orchestration (timestamps, state transitions, error handling).
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime

from .. import config as _cfg
from ..domain.autofocus import AutofocusParams
from ..domain.frame import FitsFrame
from ..domain.frame_quality import FrameQualityEntry, FrameQualityFilter
from ..domain.refocus import RefocusConfig, RefocusTracker
from ..domain.session import SessionLog
from ..domain.states import SessionState
from ..domain.visibility import compute_altaz
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort, MountState
from ..ports.solver import SolverPort
from ..ports.stacker import StackerPort
from ..ports.storage import StoragePort
from .autofocus import run_autofocus
from ._types import (
    AUTOFOCUS_BACKLASH_STEPS,
    AUTOFOCUS_EXPOSURE_S,
    AUTOFOCUS_RANGE_STEPS,
    AUTOFOCUS_STEP_SIZE,
    CENTERING_TOLERANCE_ARCMIN,
    M42_DEC,
    M42_RA,
    MAX_RECENTER_ITERATIONS,
    PREVIEW_EXPOSURE_S,
    PREVIEW_FRAMES,
    RECENTER_EVERY_N_FRAMES,
    SLEW_POLL_INTERVAL_S,
    SLEW_TIMEOUT_S,
    SOLVE_MAX_ATTEMPTS,
    STACK_DEPTH,
    STACK_EXPOSURE_S,
    WIDE_FIELD_SEARCH_RADIUS_DEG,
    OpticalProfile,
    TransitionCallback,
    WorkflowError,
)


@dataclass
class StageContext:
    camera: CameraPort
    mount: MountPort
    solver: SolverPort
    stacker: StackerPort
    storage: StoragePort
    focuser: FocuserPort
    profile: OpticalProfile
    stop_event: threading.Event
    on_transition: TransitionCallback
    target_ra: float = M42_RA
    target_dec: float = M42_DEC
    stack_exposure_s: float = STACK_EXPOSURE_S
    stack_depth: int = STACK_DEPTH
    preview_exposure_s: float = PREVIEW_EXPOSURE_S
    preview_frames: int = PREVIEW_FRAMES
    wide_field_search_radius_deg: float = WIDE_FIELD_SEARCH_RADIUS_DEG
    autofocus_range_steps: int = AUTOFOCUS_RANGE_STEPS
    autofocus_step_size: int = AUTOFOCUS_STEP_SIZE
    autofocus_exposure_s: float = AUTOFOCUS_EXPOSURE_S
    autofocus_backlash_steps: int = AUTOFOCUS_BACKLASH_STEPS
    skip_autofocus: bool = False
    refocus_tracker: RefocusTracker | None = None        # None = triggers disabled
    frame_quality_filter: FrameQualityFilter | None = None  # None = accept all frames


# ── Stage functions ──────────────────────────────────────────────────────────


def stage_connect(ctx: StageContext, log: SessionLog) -> None:
    if not ctx.camera.connect():
        raise WorkflowError("connect", "Camera failed to connect")
    if not ctx.focuser.connect():
        raise WorkflowError("connect", "Focuser failed to connect")
    if not ctx.mount.connect():
        raise WorkflowError("connect", "Mount failed to connect")
    ctx.on_transition(log, SessionState.CONNECTED)


def stage_initialize_mount(ctx: StageContext, log: SessionLog) -> None:
    state = ctx.mount.get_state()
    if state == MountState.AT_LIMIT:
        raise WorkflowError(
            "initialize_mount",
            "Mount is at a hardware limit — resolve before continuing",
        )
    if state == MountState.PARKED and not ctx.mount.unpark():
        raise WorkflowError("initialize_mount", "Unpark command rejected by mount")
    if not ctx.mount.enable_tracking():
        raise WorkflowError("initialize_mount", "Could not enable sidereal tracking")
    ctx.on_transition(log, SessionState.MOUNT_READY)


def stage_align(ctx: StageContext, log: SessionLog) -> None:
    for i, exposure in enumerate([5.0, 10.0][:SOLVE_MAX_ATTEMPTS]):
        log.plate_solve_attempts += 1
        frame = ctx.camera.capture(exposure)
        radius = ctx.wide_field_search_radius_deg if i > 0 else None
        result = ctx.solver.solve(frame, ctx.profile.pixel_scale_arcsec, search_radius_deg=radius)
        if result.success:
            if not ctx.mount.sync(result.ra, result.dec):
                raise WorkflowError("align", "Mount sync after plate solve failed")
            ctx.on_transition(log, SessionState.ALIGNED)
            return
    raise WorkflowError(
        "align",
        f"Plate solve failed after {SOLVE_MAX_ATTEMPTS} attempts — "
        "check sky conditions and polar alignment",
    )


def stage_goto(ctx: StageContext, log: SessionLog) -> None:
    if not ctx.mount.goto(ctx.target_ra, ctx.target_dec):
        raise WorkflowError("goto", "GoTo command rejected by mount")
    _wait_for_slew(ctx, "goto")
    ctx.on_transition(log, SessionState.SLEWED)


def stage_recenter(ctx: StageContext, log: SessionLog) -> None:
    for i in range(1, MAX_RECENTER_ITERATIONS + 1):
        log.centering_iterations = i
        frame = ctx.camera.capture(10.0)
        result = ctx.solver.solve(frame, ctx.profile.pixel_scale_arcsec)
        if not result.success:
            raise WorkflowError(
                "recenter",
                f"Plate solve failed during recentering (iteration {i})",
            )
        offset = _angular_offset_arcmin(result.ra, result.dec, ctx.target_ra, ctx.target_dec)
        log.centering_offset_arcmin = round(offset, 2)
        if offset <= CENTERING_TOLERANCE_ARCMIN:
            log.centering_state = SessionState.CENTERED.name
            ctx.on_transition(log, SessionState.CENTERED)
            return
        if i < MAX_RECENTER_ITERATIONS:
            if not ctx.mount.goto(ctx.target_ra, ctx.target_dec):
                raise WorkflowError(
                    "recenter",
                    f"Correction slew rejected by mount (iteration {i})",
                )
            _wait_for_slew(ctx, "recenter")

    log.centering_state = SessionState.CENTERING_DEGRADED.name
    log.warnings.append(
        f"Centering: exceeded {MAX_RECENTER_ITERATIONS} iterations; "
        f"final offset {log.centering_offset_arcmin:.1f} arcmin — continuing in degraded mode"
    )
    ctx.on_transition(log, SessionState.CENTERING_DEGRADED)


def stage_autofocus(ctx: StageContext, log: SessionLog) -> None:
    if ctx.skip_autofocus:
        return
    ctx.on_transition(log, SessionState.FOCUSING)
    params = AutofocusParams(
        range_steps=ctx.autofocus_range_steps,
        step_size=ctx.autofocus_step_size,
        exposure=ctx.autofocus_exposure_s,
        backlash_steps=ctx.autofocus_backlash_steps,
    )
    try:
        result = run_autofocus(ctx.focuser, ctx.camera, params)
    except RuntimeError as exc:
        raise WorkflowError("autofocus", str(exc)) from exc
    log.autofocus_best_position = result.best_position
    log.autofocus_metric_gain = round(result.metric_gain, 2)
    if ctx.refocus_tracker is not None:
        alt, _ = compute_altaz(ctx.target_ra, ctx.target_dec, _cfg.OBSERVER_LAT, _cfg.OBSERVER_LON)
        ctx.refocus_tracker.record_focus(altitude=alt)


def stage_preview(ctx: StageContext, log: SessionLog) -> None:
    ctx.on_transition(log, SessionState.PREVIEWING)
    for _ in range(ctx.preview_frames):
        ctx.camera.capture(ctx.preview_exposure_s)


def stage_stack(ctx: StageContext, log: SessionLog) -> None:
    ctx.on_transition(log, SessionState.STACKING)
    ctx.stacker.reset()
    last_frame_temp: float | None = None
    quality_rejected: int = 0
    stacker_rejected: int = 0
    accepted_count: int = 0
    for i in range(1, ctx.stack_depth + 1):
        if ctx.stop_event.is_set():
            raise WorkflowError("stack", "Stack cancelled by stop request")

        mount_state = ctx.mount.get_state()
        if mount_state not in (MountState.TRACKING, MountState.SLEWING):
            raise WorkflowError(
                "stack",
                f"Tracking lost during frame {i} (mount state: {mount_state.name})",
            )

        if i > 1 and (i - 1) % RECENTER_EVERY_N_FRAMES == 0:
            stage_recenter(ctx, log)
            ctx.on_transition(log, SessionState.STACKING)

        if i > 1 and ctx.refocus_tracker is not None:
            alt, _ = compute_altaz(ctx.target_ra, ctx.target_dec, _cfg.OBSERVER_LAT, _cfg.OBSERVER_LON)
            trigger = ctx.refocus_tracker.check(altitude=alt, temperature=last_frame_temp)
            if trigger.should_refocus:
                ctx.on_transition(log, SessionState.FOCUSING)
                params = AutofocusParams(
                    range_steps=ctx.autofocus_range_steps,
                    step_size=ctx.autofocus_step_size,
                    exposure=ctx.autofocus_exposure_s,
                    backlash_steps=ctx.autofocus_backlash_steps,
                )
                try:
                    run_autofocus(ctx.focuser, ctx.camera, params)
                    ctx.refocus_tracker.record_focus(altitude=alt, temperature=last_frame_temp)
                    log.refocus_count += 1
                except RuntimeError as exc:
                    log.warnings.append(
                        f"Mid-stack refocus failed before frame {i} ({trigger.reason}): {exc}"
                    )
                ctx.on_transition(log, SessionState.STACKING)

        frame = ctx.camera.capture(ctx.stack_exposure_s)
        last_frame_temp = _frame_temp(frame)

        if ctx.frame_quality_filter is not None:
            quality = ctx.frame_quality_filter.evaluate(frame)
            log.frame_quality_log.append(FrameQualityEntry(
                frame_number=i,
                snr=quality.snr,
                baseline_snr=quality.baseline_snr,
                accepted=quality.accepted,
                reason=quality.reason,
            ))
            if not quality.accepted:
                quality_rejected += 1
                log.frames_rejected = quality_rejected + stacker_rejected
                log.warnings.append(f"Frame {i} rejected by quality filter: {quality.reason}")
                continue

        accepted_count += 1
        stacked = ctx.stacker.add_frame(frame, accepted_count)
        stacker_rejected = stacked.frames_rejected
        log.frames_integrated = stacked.frames_integrated
        log.frames_rejected = quality_rejected + stacker_rejected

    ctx.on_transition(log, SessionState.STACK_COMPLETE)


def stage_save(ctx: StageContext, log: SessionLog) -> None:
    if not ctx.storage.has_free_space():
        raise WorkflowError("save", "Disk full — cannot save session artifacts")
    stacked = ctx.stacker.get_current_stack()
    image_path = ctx.storage.save_image(stacked.data, log.session_id)
    log.saved_image_path = image_path
    ctx.on_transition(log, SessionState.SAVED)
    log.completed_at = datetime.now(UTC)
    log_path = ctx.storage.save_log(log.to_dict(), log.session_id)
    log.saved_log_path = log_path


# ── Private helpers ──────────────────────────────────────────────────────────


def _wait_for_slew(ctx: StageContext, stage: str) -> None:
    elapsed = 0.0
    while ctx.mount.is_slewing():
        if ctx.stop_event.is_set():
            raise WorkflowError(stage, "Slew cancelled by stop request")
        time.sleep(SLEW_POLL_INTERVAL_S)
        elapsed += SLEW_POLL_INTERVAL_S
        if elapsed >= SLEW_TIMEOUT_S:
            raise WorkflowError(stage, f"Slew timed out after {SLEW_TIMEOUT_S:.0f}s")


def _angular_offset_arcmin(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Approximate angular separation in arcminutes (small-angle, equatorial coords)."""
    dec_rad = math.radians((dec1 + dec2) / 2)
    dra_deg = (ra1 - ra2) * 15 * math.cos(dec_rad)
    ddec_deg = dec1 - dec2
    return math.sqrt(dra_deg ** 2 + ddec_deg ** 2) * 60


def _frame_temp(frame: FitsFrame) -> float | None:
    """Extract CCD temperature from a FITS frame header, or None if absent."""
    for key in ("CCD-TEMP", "CCDTEMP", "TEMP"):
        val = frame.header.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
    return None
