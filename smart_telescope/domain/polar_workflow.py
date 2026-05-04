"""Hardware-independent polar alignment workflow (HLR-PA-004).

The workflow is a pure state machine that emits Action objects.
The caller (API layer) executes each action through hardware adapters
and feeds the result back via next_action().  No I/O, no config access,
no async code — only domain logic.

Typical driver loop::

    wf  = PolarAlignmentWorkflow(ra_step_h=1.0, observer_lat=50.3, ...)
    inp = WorkflowInput(lst=get_lst(), observer_lat=50.3)
    while True:
        act = wf.next_action(inp)
        if act.kind == "SLEW_TO_RA":
            ok  = mount.goto(act.ra_h, act.dec_deg)
            inp = WorkflowInput(slew_ok=ok, lst=get_lst(), observer_lat=50.3)
        elif act.kind == "CAPTURE_AND_SOLVE":
            r   = solver.solve(camera.capture())
            inp = WorkflowInput(solve_result=SolveResult(...), lst=get_lst(), ...)
        elif act.kind in ("DISPLAY_RESULT", "COARSE_REQUIRED", "FAILED"):
            break
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .polar_alignment import (
    Precision,
    SkyPoint,
    classify_alignment,
    compute_polar_error,
    correction_direction_alt,
    correction_direction_az,
    find_rotation_pole,
)
from .visibility import HorizonProfile, compute_altaz


# ── public data types ─────────────────────────────────────────────────────────

ActionKind = Literal[
    "SLEW_TO_RA",        # command: slew mount to (ra_h, dec_deg)
    "CAPTURE_AND_SOLVE", # command: capture one frame + plate-solve it
    "DISPLAY_RESULT",    # terminal: measurement complete; result in action.result
    "COARSE_REQUIRED",   # terminal: mount too far from NCP; manual reposition needed
    "FAILED",            # terminal: unrecoverable error
]


@dataclass(frozen=True)
class AlignmentResult:
    alt_error_arcmin:    float
    az_error_arcmin:     float
    total_error_arcmin:  float
    pole_ra:             float
    pole_dec:            float
    correction_alt:      str
    correction_az:       str
    quality_label:       str
    target_reached:      bool
    coarse_error_deg:    float | None = None
    warning_msg:         str   | None = None
    solve_retries:       int          = 0
    p1:                  SkyPoint | None = None
    p2:                  SkyPoint | None = None
    p3:                  SkyPoint | None = None


@dataclass(frozen=True)
class Action:
    kind:                     ActionKind
    ra_h:                     float | None          = None   # SLEW_TO_RA
    dec_deg:                  float                 = 89.0   # SLEW_TO_RA
    message:                  str   | None          = None
    result:                   AlignmentResult | None = None  # DISPLAY_RESULT
    camera_fallback_suggested: bool                 = False  # FAILED after consecutive misses
    coarse_error_deg:         float | None          = None   # COARSE_REQUIRED


@dataclass(frozen=True)
class SolveResult:
    success: bool
    ra:      float = 0.0
    dec:     float = 0.0
    error:   str   = ""


@dataclass(frozen=True)
class WorkflowInput:
    lst:          float              = 0.0   # local sidereal time in hours (from caller)
    observer_lat: float              = 0.0   # degrees (from caller)
    slew_ok:      bool | None        = None  # result of last SLEW_TO_RA
    solve_result: SolveResult | None = None  # result of last CAPTURE_AND_SOLVE
    user_stopped: bool               = False


# ── internal workflow states ──────────────────────────────────────────────────

_WS = Literal[
    "START",
    "WAIT_SLEW_1",  "WAIT_SOLVE_1",
    "WAIT_SLEW_2",  "WAIT_SOLVE_2",
    "WAIT_SLEW_2R", "WAIT_SOLVE_2R",  # position-2 retry
    "WAIT_SLEW_3",  "WAIT_SOLVE_3",
    "WAIT_SLEW_3R", "WAIT_SOLVE_3R",  # position-3 retry
    "DONE",
]


class PolarAlignmentWorkflow:
    """State machine for the 3-position polar measurement.

    Parameters
    ----------
    ra_step_h:
        RA rotation step in hours (default 1 h = 15°).
    target_precision_arcmin:
        Stop-criterion for target_reached flag.
    observer_lat/lon:
        Site coordinates in degrees, used for HA and horizon checks.
    ha_east_limit_h / ha_west_limit_h:
        Safe HA envelope; negative = east of meridian.
    horizon:
        Optional local horizon profile; positions below it are rejected.
    pos2_ra_override / pos3_ra_override:
        When set (refine mode), use these RAs instead of ra1 ± step.
    """

    def __init__(
        self,
        ra_step_h:               float               = 1.0,
        target_precision_arcmin: float               = Precision.GOOD_IMAGING,
        observer_lat:            float               = 0.0,
        observer_lon:            float               = 0.0,
        ha_east_limit_h:         float               = -5.5,
        ha_west_limit_h:         float               = 0.333,
        horizon:                 HorizonProfile | None = None,
        pos2_ra_override:        float | None        = None,
        pos3_ra_override:        float | None        = None,
    ) -> None:
        self._step_h   = ra_step_h
        self._prec     = target_precision_arcmin
        self._lat      = observer_lat
        self._lon      = observer_lon
        self._ha_e     = ha_east_limit_h
        self._ha_w     = ha_west_limit_h
        self._horizon  = horizon
        self._p2_ovr   = pos2_ra_override
        self._p3_ovr   = pos3_ra_override

        self._ws:          _WS              = "START"
        self._ra1:         float            = 0.0
        self._p1:          SkyPoint | None  = None
        self._p2:          SkyPoint | None  = None
        self._p3:          SkyPoint | None  = None
        self._coarse_err:  float | None     = None
        self._warning:     str   | None     = None
        self._retries:     int              = 0
        self._consec_fail: int              = 0

    # ── public ────────────────────────────────────────────────────────────────

    def next_action(self, inp: WorkflowInput) -> Action:
        if inp.user_stopped:
            self._ws = "DONE"
            return Action(kind="FAILED", message="Workflow stopped by user")
        match self._ws:
            case "START":         return self._on_start(inp)
            case "WAIT_SLEW_1":   return self._on_slew(inp, next_ws="WAIT_SOLVE_1",
                                    capture_msg="Capturing HOME frame")
            case "WAIT_SOLVE_1":  return self._on_solve_1(inp)
            case "WAIT_SLEW_2":   return self._on_slew(inp, next_ws="WAIT_SOLVE_2",
                                    capture_msg="Capturing position 2 frame")
            case "WAIT_SOLVE_2":  return self._on_solve_2(inp)
            case "WAIT_SLEW_2R":  return self._on_slew(inp, next_ws="WAIT_SOLVE_2R",
                                    capture_msg="Capturing position 2 retry")
            case "WAIT_SOLVE_2R": return self._on_solve_2r(inp)
            case "WAIT_SLEW_3":   return self._on_slew(inp, next_ws="WAIT_SOLVE_3",
                                    capture_msg="Capturing position 3 frame")
            case "WAIT_SOLVE_3":  return self._on_solve_3(inp)
            case "WAIT_SLEW_3R":  return self._on_slew(inp, next_ws="WAIT_SOLVE_3R",
                                    capture_msg="Capturing position 3 retry")
            case "WAIT_SOLVE_3R": return self._on_solve_3r(inp)
            case _:               return Action(kind="FAILED", message="Workflow in terminal state")

    @property
    def home_ra(self) -> float:
        """RA used for HOME position — available after first next_action() call."""
        return self._ra1

    # ── state handlers ────────────────────────────────────────────────────────

    def _on_start(self, inp: WorkflowInput) -> Action:
        self._ra1 = inp.lst % 24.0
        try:
            self._safe_slew(self._ra1, 89.0, inp.lst, "Position 1 (HOME)")
        except RuntimeError as e:
            return Action(kind="FAILED", message=str(e))
        self._ws = "WAIT_SLEW_1"
        return Action(kind="SLEW_TO_RA", ra_h=self._ra1, dec_deg=89.0,
                      message="Slewing to HOME position")

    def _on_slew(self, inp: WorkflowInput, *, next_ws: _WS, capture_msg: str) -> Action:
        if not inp.slew_ok:
            return Action(kind="FAILED", message="Slew failed or timed out")
        self._ws = next_ws
        return Action(kind="CAPTURE_AND_SOLVE", message=capture_msg)

    def _on_solve_1(self, inp: WorkflowInput) -> Action:
        sr = inp.solve_result
        if sr is None or not sr.success:
            self._consec_fail += 1
            return Action(kind="FAILED",
                          message=f"HOME solve failed: {sr.error if sr else 'no result'}",
                          camera_fallback_suggested=self._consec_fail >= 2)
        self._consec_fail = 0
        self._p1 = SkyPoint(ra=sr.ra, dec=sr.dec)

        coarse = abs(90.0 - self._p1.dec)
        self._coarse_err = round(coarse, 2)
        if coarse > 5.0:
            self._ws = "DONE"
            return Action(
                kind="COARSE_REQUIRED",
                coarse_error_deg=self._coarse_err,
                message=(
                    f"Mount is {coarse:.1f}° from the pole — "
                    "rough mechanical repositioning required"
                ),
            )
        if coarse > 1.0:
            self._warning = (
                f"Mount is {coarse:.1f}° from pole — "
                "may be outside fine azimuth screw range"
            )

        ra2 = self._p2_ovr if self._p2_ovr is not None \
              else (self._ra1 + self._step_h) % 24.0
        try:
            self._safe_slew(ra2, 89.0, inp.lst, "Position 2")
        except RuntimeError as e:
            return Action(kind="FAILED", message=str(e))
        self._ws = "WAIT_SLEW_2"
        return Action(kind="SLEW_TO_RA", ra_h=ra2, dec_deg=89.0,
                      message="Slewing to position 2")

    def _on_solve_2(self, inp: WorkflowInput) -> Action:
        sr = inp.solve_result
        if sr is None or not sr.success:
            self._consec_fail += 1
            self._retries += 1
            ra2r = (self._ra1 + 3 * self._step_h) % 24.0
            try:
                self._safe_slew(ra2r, 89.0, inp.lst, "Position 2 retry")
            except RuntimeError as e:
                return Action(kind="FAILED", message=str(e))
            self._ws = "WAIT_SLEW_2R"
            return Action(kind="SLEW_TO_RA", ra_h=ra2r, dec_deg=89.0,
                          message="Solve 2 failed — retrying at alternate RA")
        self._consec_fail = 0
        self._p2 = SkyPoint(ra=sr.ra, dec=sr.dec)
        return self._slew_to_3(inp.lst)

    def _on_solve_2r(self, inp: WorkflowInput) -> Action:
        sr = inp.solve_result
        if sr is None or not sr.success:
            self._consec_fail += 1
            self._ws = "DONE"
            return Action(kind="FAILED",
                          message=f"Solve 2 failed (with retry): {sr.error if sr else 'no result'}",
                          camera_fallback_suggested=self._consec_fail >= 2)
        self._consec_fail = 0
        self._p2 = SkyPoint(ra=sr.ra, dec=sr.dec)
        return self._slew_to_3(inp.lst)

    def _on_solve_3(self, inp: WorkflowInput) -> Action:
        sr = inp.solve_result
        if sr is None or not sr.success:
            self._consec_fail += 1
            self._retries += 1
            ra3r = (self._ra1 - self._step_h) % 24.0
            try:
                self._safe_slew(ra3r, 89.0, inp.lst, "Position 3 retry")
            except RuntimeError as e:
                return Action(kind="FAILED", message=str(e))
            self._ws = "WAIT_SLEW_3R"
            return Action(kind="SLEW_TO_RA", ra_h=ra3r, dec_deg=89.0,
                          message="Solve 3 failed — retrying at alternate RA")
        self._consec_fail = 0
        self._p3 = SkyPoint(ra=sr.ra, dec=sr.dec)
        return self._compute(inp.lst, inp.observer_lat)

    def _on_solve_3r(self, inp: WorkflowInput) -> Action:
        sr = inp.solve_result
        if sr is None or not sr.success:
            self._consec_fail += 1
            self._ws = "DONE"
            return Action(kind="FAILED",
                          message=f"Solve 3 failed (with retry): {sr.error if sr else 'no result'}",
                          camera_fallback_suggested=self._consec_fail >= 2)
        self._consec_fail = 0
        self._p3 = SkyPoint(ra=sr.ra, dec=sr.dec)
        return self._compute(inp.lst, inp.observer_lat)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _slew_to_3(self, lst: float) -> Action:
        ra3 = self._p3_ovr if self._p3_ovr is not None \
              else (self._ra1 + 2 * self._step_h) % 24.0
        try:
            self._safe_slew(ra3, 89.0, lst, "Position 3")
        except RuntimeError as e:
            return Action(kind="FAILED", message=str(e))
        self._ws = "WAIT_SLEW_3"
        return Action(kind="SLEW_TO_RA", ra_h=ra3, dec_deg=89.0,
                      message="Slewing to position 3")

    def _compute(self, lst: float, observer_lat: float) -> Action:
        assert self._p1 and self._p2 and self._p3, "not all three positions solved"
        try:
            pole = find_rotation_pole(self._p1, self._p2, self._p3)
            err  = compute_polar_error(pole, observer_lat, lst)
        except Exception as exc:
            return Action(kind="FAILED", message=f"Pole computation failed: {exc}")

        self._ws = "DONE"
        result = AlignmentResult(
            alt_error_arcmin   = err.alt_error_arcmin,
            az_error_arcmin    = err.az_error_arcmin,
            total_error_arcmin = err.total_error_arcmin,
            pole_ra            = pole.ra,
            pole_dec           = pole.dec,
            correction_alt     = correction_direction_alt(err.alt_error_arcmin),
            correction_az      = correction_direction_az(err.az_error_arcmin),
            quality_label      = classify_alignment(err.total_error_arcmin),
            target_reached     = err.total_error_arcmin <= self._prec,
            coarse_error_deg   = self._coarse_err,
            warning_msg        = self._warning,
            solve_retries      = self._retries,
            p1 = self._p1,
            p2 = self._p2,
            p3 = self._p3,
        )
        return Action(kind="DISPLAY_RESULT", result=result,
                      message="Measurement complete")

    def _safe_slew(self, ra_h: float, dec_deg: float, lst: float, label: str) -> None:
        """Raise RuntimeError if (ra_h, dec_deg) violates HA limits or horizon."""
        ha = (lst - ra_h + 12.0) % 24.0 - 12.0
        if ha < self._ha_e:
            raise RuntimeError(
                f"{label}: HA {ha:.2f}h east of limit {self._ha_e}h"
            )
        if ha > self._ha_w:
            raise RuntimeError(
                f"{label}: HA {ha:.2f}h west of limit {self._ha_w}h"
            )
        if self._horizon is not None:
            alt, az = compute_altaz(ra_h, dec_deg, self._lat, self._lon)
            if not self._horizon.is_visible(alt, az):
                min_alt = self._horizon.min_alt_at(az)
                raise RuntimeError(
                    f"{label} blocked by horizon profile "
                    f"(az {az:.0f}°, alt {alt:.1f}° < min {min_alt:.1f}°)"
                )
