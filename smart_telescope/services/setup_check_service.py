"""Extended setup check service — exercises hardware beyond static readiness checks.

Each method runs a short live test and returns a structured result dict.
Designed to be called from the API layer one step at a time (or all at once).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from ..ports.mount import MountState
from ..services.mount_operations import MountSlewingError, home_sequence
from ..services.hardware_coordinator import CommandConflictError


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
