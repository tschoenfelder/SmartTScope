"""CollimationAssistant service — Phase 1.2.

Drives the collimation state machine in a background thread.
Hardware handlers are stubs at this phase; algorithms are filled in Phases 3-9.
"""
from __future__ import annotations

import datetime
import logging
import threading
from typing import Any, Callable

from ...config import get_collimation_config
from ...domain.collimation.config import CollimationConfig
from ...domain.collimation.models import (
    CollimationRecommendation,
    FrameMeasurement,
)
from ...ports.camera import CameraPort
from ...ports.focuser import FocuserPort
from ...ports.mount import MountPort
from .session_report import SessionReportBuilder
from .state_machine import (
    TERMINAL_STATES,
    USER_WAIT_STATES,
    CollimationState,
    CollimationStateMachine,
    InvalidTransitionError,
)

_log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


class CollimationAssistant:
    """Background service driving the collimation wizard.

    One instance lives for the app lifetime (created lazily in the API layer).
    Call start() to begin a session, cancel() to abort, retry() to reset after
    FAILED/COMPLETE.  advance() unblocks USER_WAIT_STATES with user input.
    """

    def __init__(
        self,
        camera: CameraPort,
        mount: MountPort,
        focuser: FocuserPort,
    ) -> None:
        self._camera = camera
        self._mount = mount
        self._focuser = focuser
        self._cfg: CollimationConfig = get_collimation_config()
        self._sm = CollimationStateMachine()

        self._thread: threading.Thread | None = None
        self._cancel = threading.Event()
        self._user_event = threading.Event()

        self._lock = threading.Lock()
        self._error: str | None = None
        self._started_at: str | None = None
        self._updated_at: str = _now()

        self._last_frame: FrameMeasurement | None = None
        self._last_recommendation: CollimationRecommendation | None = None
        self._advance_payload: dict[str, Any] = {}
        self._target_ra: float | None = None
        self._target_dec: float | None = None
        self._report_builder: SessionReportBuilder = self._new_report_builder()

    # ── Control ───────────────────────────────────────────────────────────────

    def start(self) -> None:
        with self._lock:
            if self._sm.state != CollimationState.IDLE:
                raise RuntimeError(
                    f"Cannot start from state {self._sm.state.value!r}; call retry() first"
                )
            self._cancel.clear()
            self._user_event.clear()
            self._error = None
            self._last_frame = None
            self._last_recommendation = None
            self._advance_payload = {}
            self._target_ra = None
            self._target_dec = None
            self._started_at = _now()
            self._report_builder = self._new_report_builder()
            self._sm.transition(CollimationState.PRECHECK)
            self._updated_at = _now()

        self._thread = threading.Thread(
            target=self._run, daemon=True, name="collimation-assistant"
        )
        self._thread.start()
        _log.info("CollimationAssistant: session started")

    def pause(self) -> None:
        with self._lock:
            self._sm.pause()
            self._updated_at = _now()
        _log.info("CollimationAssistant: paused")

    def resume(self) -> None:
        with self._lock:
            self._sm.resume()
            self._updated_at = _now()
        self._user_event.set()
        _log.info("CollimationAssistant: resumed")

    def cancel(self) -> None:
        self._cancel.set()
        self._user_event.set()
        with self._lock:
            self._report_builder.mark_cancelled()
            self._sm.reset()
            self._updated_at = _now()
        _log.info("CollimationAssistant: cancelled")

    def advance(self, payload: dict[str, Any] | None = None) -> None:
        """Unblock a USER_WAIT_STATE and pass optional user data.

        SELECT_STAR expects {"ra": float, "dec": float}.
        GUIDE_ROUGH/FINE_COLLIMATION accept {"finish": true} to declare done.
        MASKLESS_VALIDATION accepts {"accept": false} to request more fine work.
        """
        state = self._sm.state
        if state not in USER_WAIT_STATES:
            raise RuntimeError(
                f"advance() not valid in state {state.value!r}"
            )
        with self._lock:
            self._advance_payload = payload or {}
        self._user_event.set()

    def retry(self) -> None:
        """Reset to IDLE after FAILED or COMPLETE."""
        with self._lock:
            if self._sm.state not in (
                CollimationState.FAILED, CollimationState.COMPLETE
            ):
                raise RuntimeError(
                    f"retry() only valid in FAILED or COMPLETE, not {self._sm.state.value!r}"
                )
            self._sm.reset()
            self._updated_at = _now()

    # ── Status / overlay / report ─────────────────────────────────────────────

    @property
    def status(self) -> dict[str, Any]:
        with self._lock:
            rec: dict | None = None
            if self._last_recommendation:
                r = self._last_recommendation
                rec = {
                    "screw_id":   r.screw_id,
                    "direction":  r.turn_direction.value,
                    "size":       r.adjustment_size.value,
                    "reason":     r.reason,
                    "confidence": r.confidence,
                }
            meas: dict | None = None
            if self._last_frame:
                f = self._last_frame
                meas = {
                    "frame_index":  f.frame_index,
                    "captured_at":  f.captured_at,
                    "confidence":   f.confidence,
                }
            return {
                "state":                self._sm.state.value,
                "instruction":          self._sm.instruction(),
                "is_waiting_for_user":  self._sm.is_waiting_for_user(),
                "is_paused":            self._sm.state == CollimationState.PAUSED,
                "is_terminal":          self._sm.is_terminal(),
                "current_recommendation": rec,
                "last_measurement":     meas,
                "error":                self._error,
                "started_at":           self._started_at,
                "updated_at":           self._updated_at,
            }

    @property
    def overlay(self) -> dict[str, Any]:
        with self._lock:
            f = self._last_frame
            if f is None:
                return {"available": False}
            out: dict[str, Any] = {"available": True}
            if f.reference_center:
                out["ref_offset_x"] = f.reference_center.offset_x_px
                out["ref_offset_y"] = f.reference_center.offset_y_px
                out["ref_source"]   = f.reference_center.source
            if f.donut:
                d = f.donut
                out["donut"] = {
                    "outer_cx":   d.outer_ring.center_x,
                    "outer_cy":   d.outer_ring.center_y,
                    "outer_r":    d.outer_ring.mean_radius,
                    "inner_cx":   d.inner_hole.center_x,
                    "inner_cy":   d.inner_hole.center_y,
                    "inner_r":    d.inner_hole.mean_radius,
                    "error_x":    d.error_x_px,
                    "error_y":    d.error_y_px,
                    "error_mag":  d.error_magnitude_px,
                    "confidence": d.confidence,
                }
            if f.spike:
                s = f.spike
                out["spike"] = {
                    "crossing_x":      s.crossing_point_x,
                    "crossing_y":      s.crossing_point_y,
                    "focus_error":     s.focus_error_px,
                    "offset_from_ref": s.offset_from_ref_px,
                    "confidence":      s.confidence,
                }
            return out

    @property
    def report(self) -> dict[str, Any]:
        with self._lock:
            built = self._report_builder.build().to_dict()
            built.update({
                "state":      self._sm.state.value,
                "updated_at": self._updated_at,
                "error":      self._error,
            })
            return built

    def _new_report_builder(self) -> SessionReportBuilder:
        b = SessionReportBuilder()
        b.set_optical_train(self._cfg.telescope_profile)
        b.set_camera(self._cfg.camera_id)
        return b

    # ── Background thread ─────────────────────────────────────────────────────

    def _run(self) -> None:
        _log.info("CollimationAssistant: worker thread starting")
        handlers = {
            CollimationState.PRECHECK:                  self._handle_precheck,
            CollimationState.SLEW_TO_STAR:              self._handle_slew_to_star,
            CollimationState.ACQUIRE_STAR:              self._handle_acquire_star,
            CollimationState.CENTER_STAR:               self._handle_center_star,
            CollimationState.AUTO_EXPOSURE:             self._handle_auto_exposure,
            CollimationState.ROUGH_DEFOCUS:             self._handle_rough_defocus,
            CollimationState.MAP_SCREWS_BY_OBSTRUCTION: self._handle_map_screws,
            CollimationState.MEASURE_DONUT:             self._handle_measure_donut,
            CollimationState.MAP_MASK_SECTORS:          self._handle_map_mask_sectors,
            CollimationState.FINE_FOCUS:                self._handle_fine_focus,
            CollimationState.MEASURE_SPIKES:            self._handle_measure_spikes,
            CollimationState.FINAL_REFOCUS:             self._handle_final_refocus,
        }
        try:
            while not self._cancel.is_set():
                state = self._sm.state

                if state in TERMINAL_STATES:
                    break

                if state == CollimationState.PAUSED:
                    self._user_event.wait()
                    self._user_event.clear()
                    continue

                if state in USER_WAIT_STATES:
                    self._user_event.wait()
                    self._user_event.clear()
                    if self._cancel.is_set():
                        break
                    self._dispatch_user_wait(state)
                    continue

                handler = handlers.get(state)
                if handler is None:
                    self._fail(f"No handler for state {state.value!r}")
                    break
                try:
                    handler()
                except Exception as exc:
                    _log.exception("CollimationAssistant: handler %s raised", state.value)
                    self._fail(str(exc))
                    break
        finally:
            _log.info(
                "CollimationAssistant: worker thread exiting in state %s",
                self._sm.state.value,
            )

    def _dispatch_user_wait(self, state: CollimationState) -> None:
        payload = self._advance_payload

        if state == CollimationState.SELECT_STAR:
            ra  = payload.get("ra")
            dec = payload.get("dec")
            if ra is None or dec is None:
                _log.warning("SELECT_STAR: advance missing ra/dec — staying")
                return  # stay in SELECT_STAR, wait again
            with self._lock:
                self._target_ra  = float(ra)
                self._target_dec = float(dec)
            self._do_transition(CollimationState.SLEW_TO_STAR)

        elif state == CollimationState.GUIDE_ROUGH_COLLIMATION:
            if payload.get("finish"):
                self._do_transition(CollimationState.INSTALL_TRIBAHTINOV)
            else:
                self._do_transition(CollimationState.MEASURE_DONUT)

        elif state == CollimationState.INSTALL_TRIBAHTINOV:
            self._do_transition(CollimationState.MAP_MASK_SECTORS)

        elif state == CollimationState.GUIDE_FINE_COLLIMATION:
            if payload.get("finish"):
                self._do_transition(CollimationState.FINAL_REFOCUS)
            else:
                self._do_transition(CollimationState.MEASURE_SPIKES)

        elif state == CollimationState.MASKLESS_VALIDATION:
            if payload.get("accept", True):
                self._do_transition(CollimationState.COMPLETE)
            else:
                self._do_transition(CollimationState.GUIDE_FINE_COLLIMATION)

    # ── State handlers (stubs — algorithms filled in Phases 3-9) ─────────────

    def _handle_precheck(self) -> None:
        _log.info("PRECHECK: verifying hardware readiness (stub)")
        # TODO Phase 2: check mount connected, camera present, focuser available
        self._do_transition(CollimationState.SELECT_STAR)

    def _handle_slew_to_star(self) -> None:
        ra  = self._target_ra
        dec = self._target_dec
        _log.info("SLEW_TO_STAR: RA=%.4f Dec=%.4f", ra or 0.0, dec or 0.0)
        if ra is None or dec is None:
            self._fail("No target star selected")
            return
        try:
            self._mount.goto(ra, dec)
        except Exception as exc:
            _log.warning("SLEW_TO_STAR: goto rejected (%s) — returning to star selection", exc)
            with self._lock:
                self._error = str(exc)
            self._do_transition(CollimationState.SELECT_STAR)
            return
        self._do_transition(CollimationState.ACQUIRE_STAR)

    def _handle_acquire_star(self) -> None:
        _log.info("ACQUIRE_STAR: stub → CENTER_STAR")
        # TODO Phase 3: capture frame, centroid, fail if SNR too low
        self._do_transition(CollimationState.CENTER_STAR)

    def _handle_center_star(self) -> None:
        _log.info("CENTER_STAR: stub → AUTO_EXPOSURE")
        # TODO Phase 3: pulse-guide loop until within fine_tolerance_px
        self._do_transition(CollimationState.AUTO_EXPOSURE)

    def _handle_auto_exposure(self) -> None:
        _log.info("AUTO_EXPOSURE: stub → ROUGH_DEFOCUS")
        # TODO Phase 3: bracket exposures, target ~80 % well depth
        self._do_transition(CollimationState.ROUGH_DEFOCUS)

    def _handle_rough_defocus(self) -> None:
        _log.info("ROUGH_DEFOCUS: stub → MAP_SCREWS_BY_OBSTRUCTION")
        # TODO Phase 4: move focuser until donut ratio in [min, max]
        self._do_transition(CollimationState.MAP_SCREWS_BY_OBSTRUCTION)

    def _handle_map_screws(self) -> None:
        _log.info("MAP_SCREWS_BY_OBSTRUCTION: stub → MEASURE_DONUT")
        # TODO Phase 5: nudge each screw, track obstruction shadow shift
        self._do_transition(CollimationState.MEASURE_DONUT)

    def _handle_measure_donut(self) -> None:
        _log.info("MEASURE_DONUT: stub → GUIDE_ROUGH_COLLIMATION")
        # TODO Phase 5: fit donut, compute error vector, build recommendation
        self._do_transition(CollimationState.GUIDE_ROUGH_COLLIMATION)

    def _handle_map_mask_sectors(self) -> None:
        _log.info("MAP_MASK_SECTORS: stub → FINE_FOCUS")
        # TODO Phase 7: identify Tri-Bahtinov sector orientation from spikes
        self._do_transition(CollimationState.FINE_FOCUS)

    def _handle_fine_focus(self) -> None:
        _log.info("FINE_FOCUS: stub → MEASURE_SPIKES")
        # TODO Phase 8: Bahtinov autofocus loop
        self._do_transition(CollimationState.MEASURE_SPIKES)

    def _handle_measure_spikes(self) -> None:
        _log.info("MEASURE_SPIKES: stub → GUIDE_FINE_COLLIMATION")
        # TODO Phase 8: analyse Tri-Bahtinov spikes, compute residuals
        self._do_transition(CollimationState.GUIDE_FINE_COLLIMATION)

    def _handle_final_refocus(self) -> None:
        _log.info("FINAL_REFOCUS: maskless FWHM hill-climb")
        from ...domain.collimation.processing.frame import normalize_frame
        from ...domain.collimation.processing.star_detection import detect_star
        from .focuser_control import CollimationFocuserControl
        from .fwhm_focus import FWHMFocusController

        bit_depth     = self._camera.get_bit_depth()
        exposure_s    = self._camera.get_exposure_ms() / 1000.0
        focuser_ctrl  = CollimationFocuserControl(self._focuser, self._cfg.focuser)

        def get_fwhm() -> float | None:
            if self._cancel.is_set():
                return None
            try:
                raw = self._camera.capture(exposure_s)
            except Exception as exc:
                _log.warning("FINAL_REFOCUS: capture failed: %s", exc)
                return None
            frame = normalize_frame(raw, bit_depth=bit_depth)
            star  = detect_star(frame)
            return star.fwhm_px if star is not None else None

        def move_focuser(steps: int) -> None:
            focuser_ctrl.move_focus_relative(steps)

        controller = FWHMFocusController(
            coarse_step=self._cfg.focuser.coarse_step,
            fine_step=self._cfg.focuser.fine_step,
            settle_seconds=0.0,
        )
        result = controller.focus(
            get_fwhm=get_fwhm,
            move_focuser=move_focuser,
            cancel_check=lambda: self._cancel.is_set(),
        )

        if result.reason == "cancelled":
            return

        if result.reason == "star_lost":
            self._fail("final refocus: star lost")
            return

        with self._lock:
            self._report_builder.record_focus_status(
                initial_fwhm=result.initial_fwhm_px,
                final_fwhm=result.final_fwhm_px,
            )

        _log.info(
            "FINAL_REFOCUS: %s quality=%s best_fwhm=%.2f px",
            result.reason, result.quality,
            result.best_fwhm_px if result.best_fwhm_px is not None else -1,
        )
        self._do_transition(CollimationState.MASKLESS_VALIDATION)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _do_transition(self, target: CollimationState) -> None:
        self._sm.transition(target)
        with self._lock:
            self._updated_at = _now()

    def _fail(self, reason: str) -> None:
        _log.error("CollimationAssistant FAILED: %s", reason)
        with self._lock:
            self._error = reason
            self._updated_at = _now()
        # Force to FAILED regardless of current state.
        current = self._sm.state
        if current not in TERMINAL_STATES:
            try:
                self._sm.transition(CollimationState.FAILED)
            except InvalidTransitionError:
                # Not a valid direct path — reset then re-enter FAILED via IDLE
                self._sm.reset()
                self._sm.transition(CollimationState.PRECHECK)
                self._sm.transition(CollimationState.FAILED)

