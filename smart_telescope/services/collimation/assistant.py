"""CollimationAssistant service — Phase 1.2.

Drives the collimation state machine in a background thread.
Hardware handlers are stubs at this phase; algorithms are filled in Phases 3-9.
"""
from __future__ import annotations

import datetime
import logging
import threading
from typing import TYPE_CHECKING, Any, Callable

from ...config import get_collimation_config

if TYPE_CHECKING:
    from ...services.guiding_service import GuidingService
    from .frame_archive import CollimationFrameArchive
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
        guiding_service: "GuidingService | None" = None,
        guide_cameras: "dict[str, CameraPort] | None" = None,
        frame_archive: "CollimationFrameArchive | None" = None,
    ) -> None:
        self._camera = camera
        self._mount = mount
        self._focuser = focuser
        self._guiding_service = guiding_service
        self._guide_cameras: dict[str, CameraPort] = guide_cameras or {}
        self._frame_archive = frame_archive
        self._session_id: str = ""
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
        self._frame_counter: int = 0
        self._mask_calibration: Any = None  # MaskSectorCalibration | None
        self._spike_smoother: Any = None    # SpikeSmoother | None
        self._contradiction_detector: Any = None  # ContradictionDetector | None

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
            self._frame_counter = 0
            self._mask_calibration = None
            self._spike_smoother = None
            self._contradiction_detector = None
            import uuid
            self._session_id = str(uuid.uuid4())
            if self._frame_archive is not None:
                self._frame_archive.new_session(self._session_id)
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
                "guiding":              self._guiding_status_dict(),
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

    @property
    def frame_archive(self) -> "CollimationFrameArchive | None":
        return self._frame_archive

    def _guiding_status_dict(self) -> dict:
        if self._guiding_service is None:
            return {"available": False}
        s = self._guiding_service.status()
        return {
            "available": True,
            "state": s.state,
            "rms_px": s.rms_px,
            "last_pulse": list(s.last_pulse) if s.last_pulse else None,
        }

    def _start_guiding(self) -> None:
        if self._guiding_service is None or not self._guide_cameras:
            return
        try:
            self._guiding_service.start(
                self._guide_cameras,
                exposure_s=self._cfg.guiding_exposure_s,
                cadence_s=self._cfg.guiding_cadence_s,
                mount=self._mount,
            )
            _log.info("CollimationAssistant: guiding started")
        except Exception as exc:
            _log.warning("CollimationAssistant: guiding start failed: %s", exc)

    def _stop_guiding(self) -> None:
        if self._guiding_service is None:
            return
        try:
            if self._guiding_service.status().state == "running":
                self._guiding_service.stop()
                _log.info("CollimationAssistant: guiding stopped")
        except Exception as exc:
            _log.warning("CollimationAssistant: guiding stop failed: %s", exc)

    def _with_guiding_paused(self, fn: Callable) -> None:
        """Pause guide pulses, run fn(), rebaseline + resume regardless of fn outcome."""
        if self._guiding_service is not None:
            self._guiding_service.pause_pulses()
        try:
            fn()
        finally:
            if self._guiding_service is not None:
                self._guiding_service.rebaseline()
                self._guiding_service.resume_pulses()

    def _recenter_star(self) -> None:
        """Re-centre the main camera star via PulseCenterer (no state transition)."""
        from ...domain.collimation.models import ReferenceCenterCalibration
        from ...domain.collimation.processing.frame import normalize_frame
        from ...domain.collimation.processing.star_detection import detect_star
        from ...domain.collimation.profiles import get_profile
        from .mount_centering import PulseCenterer

        bit_depth  = self._camera.get_bit_depth()
        exposure_s = self._camera.get_exposure_ms() / 1000.0
        profile    = get_profile(self._cfg.telescope_profile)
        ref_cfg    = self._cfg.reference_center

        centerer = PulseCenterer(
            mount=self._mount,
            config=self._cfg.mount_centering,
            pixel_scale_arcsec=profile.pixel_scale_arcsec,
        )

        def _get_offset() -> tuple[float, float] | None:
            if self._cancel.is_set():
                return None
            try:
                raw = self._camera.capture(exposure_s)
            except Exception:
                return None
            processed = normalize_frame(raw, bit_depth=bit_depth)
            star = detect_star(processed)
            if star is None:
                return None
            ref = ReferenceCenterCalibration(
                offset_x_px=ref_cfg.offset_x_px,
                offset_y_px=ref_cfg.offset_y_px,
                source=ref_cfg.source.value,
            ).compute(processed.width, processed.height)
            return star.center_x - ref.x, star.center_y - ref.y

        result = centerer.center(
            get_offset_px=_get_offset,
            cancel_check=lambda: self._cancel.is_set(),
            dec_deg=self._target_dec or 0.0,
        )
        _log.info(
            "RECENTER: %s pulses=%d offset=%.1f px",
            result.reason, result.pulses_issued, result.final_offset_px,
        )

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
            self._stop_guiding()
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
                self._with_guiding_paused(self._recenter_star)
                self._do_transition(CollimationState.MEASURE_DONUT)

        elif state == CollimationState.INSTALL_TRIBAHTINOV:
            self._do_transition(CollimationState.MAP_MASK_SECTORS)

        elif state == CollimationState.GUIDE_FINE_COLLIMATION:
            if payload.get("finish"):
                self._do_transition(CollimationState.FINAL_REFOCUS)
            else:
                self._with_guiding_paused(self._recenter_star)
                self._do_transition(CollimationState.MEASURE_SPIKES)

        elif state == CollimationState.MASKLESS_VALIDATION:
            if payload.get("accept", True):
                self._do_transition(CollimationState.COMPLETE)
            else:
                self._do_transition(CollimationState.GUIDE_FINE_COLLIMATION)

    # ── State handlers (stubs — algorithms filled in Phases 3-9) ─────────────

    def _handle_precheck(self) -> None:
        _log.info("PRECHECK: verifying hardware readiness")
        from ...ports.mount import MountState
        try:
            state = self._mount.get_state()
            if not isinstance(state, MountState):
                self._fail(f"Mount not ready: unexpected state {state!r}")
                return
        except Exception as exc:
            self._fail(f"PRECHECK: mount check failed: {exc}")
            return
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
        from ...domain.collimation.processing.frame import normalize_frame
        from ...domain.collimation.processing.star_detection import detect_star

        bit_depth  = self._camera.get_bit_depth()
        exposure_s = self._camera.get_exposure_ms() / 1000.0

        for attempt in range(5):
            if self._cancel.is_set():
                return
            try:
                raw = self._camera.capture(exposure_s)
            except Exception as exc:
                _log.warning("ACQUIRE_STAR attempt %d: capture failed: %s", attempt + 1, exc)
                continue
            processed = normalize_frame(raw, bit_depth=bit_depth)
            star = detect_star(processed)
            if star is not None:
                _log.info(
                    "ACQUIRE_STAR: star at (%.1f, %.1f) FWHM=%.1f px",
                    star.center_x, star.center_y, star.fwhm_px,
                )
                self._do_transition(CollimationState.CENTER_STAR)
                return
            _log.warning("ACQUIRE_STAR: no star on attempt %d/5", attempt + 1)

        self._fail("ACQUIRE_STAR: no star detected after 5 attempts")

    def _handle_center_star(self) -> None:
        from ...domain.collimation.models import ReferenceCenterCalibration
        from ...domain.collimation.processing.frame import normalize_frame
        from ...domain.collimation.processing.star_detection import detect_star
        from ...domain.collimation.profiles import get_profile
        from .mount_centering import PulseCenterer

        bit_depth  = self._camera.get_bit_depth()
        exposure_s = self._camera.get_exposure_ms() / 1000.0
        profile    = get_profile(self._cfg.telescope_profile)
        ref_cfg    = self._cfg.reference_center

        centerer = PulseCenterer(
            mount=self._mount,
            config=self._cfg.mount_centering,
            pixel_scale_arcsec=profile.pixel_scale_arcsec,
        )

        def _get_offset() -> tuple[float, float] | None:
            if self._cancel.is_set():
                return None
            try:
                raw = self._camera.capture(exposure_s)
            except Exception:
                return None
            processed = normalize_frame(raw, bit_depth=bit_depth)
            star = detect_star(processed)
            if star is None:
                return None
            ref = ReferenceCenterCalibration(
                offset_x_px=ref_cfg.offset_x_px,
                offset_y_px=ref_cfg.offset_y_px,
                source=ref_cfg.source.value,
            ).compute(processed.width, processed.height)
            return star.center_x - ref.x, star.center_y - ref.y

        result = centerer.center(
            get_offset_px=_get_offset,
            cancel_check=lambda: self._cancel.is_set(),
            dec_deg=self._target_dec or 0.0,
        )
        if self._cancel.is_set():
            return
        _log.info(
            "CENTER_STAR: %s pulses=%d offset=%.1f px",
            result.reason, result.pulses_issued, result.final_offset_px,
        )
        self._do_transition(CollimationState.AUTO_EXPOSURE)

    def _handle_auto_exposure(self) -> None:
        import numpy as np
        from ...domain.collimation.processing.frame import normalize_frame
        from ...domain.collimation.processing.star_detection import detect_star

        bit_depth  = self._camera.get_bit_depth()
        max_adu    = float((1 << bit_depth) - 1)
        target     = 0.80
        exposure_s = self._camera.get_exposure_ms() / 1000.0

        for _ in range(8):
            if self._cancel.is_set():
                return
            try:
                raw = self._camera.capture(exposure_s)
            except Exception as exc:
                _log.warning("AUTO_EXPOSURE: capture failed: %s", exc)
                break
            processed = normalize_frame(raw, bit_depth=bit_depth)
            if detect_star(processed) is None:
                _log.warning("AUTO_EXPOSURE: no star detected")
                break
            fraction = float(np.max(processed.mono)) / max_adu
            if abs(fraction - target) < 0.10:
                break
            new_exp = max(0.001, min(30.0, exposure_s * (target / max(fraction, 0.01))))
            if abs(new_exp - exposure_s) < 0.001:
                break
            self._camera.set_exposure_ms(new_exp * 1000.0)
            exposure_s = new_exp

        _log.info("AUTO_EXPOSURE: final exposure=%.3f s", exposure_s)
        self._start_guiding()
        self._do_transition(CollimationState.ROUGH_DEFOCUS)

    def _handle_rough_defocus(self) -> None:
        from .defocus_controller import DefocusController
        from .focus_search import FocusSearcher
        from .focuser_control import CollimationFocuserControl

        bit_depth    = self._camera.get_bit_depth()
        exposure_s   = self._camera.get_exposure_ms() / 1000.0
        focuser_ctrl = CollimationFocuserControl(self._focuser, self._cfg.focuser)

        def _capture():
            return self._camera.capture(exposure_s)

        # Step 1: rough focus search
        searcher = FocusSearcher(
            focuser=focuser_ctrl,
            config=self._cfg.focuser,
            bit_depth=bit_depth,
            settle_seconds=0.0,
        )
        focus_result = searcher.search(
            capture_frame=_capture,
            cancel_check=lambda: self._cancel.is_set(),
        )
        if self._cancel.is_set():
            return
        if focus_result.reason == "star_lost":
            self._fail("ROUGH_DEFOCUS: star lost during focus search")
            return
        _log.info(
            "ROUGH_DEFOCUS focus: %s best_fwhm=%s",
            focus_result.reason,
            f"{focus_result.best_fwhm:.2f}" if focus_result.best_fwhm is not None else "n/a",
        )

        # Step 2: get frame dimensions then defocus to donut regime
        try:
            sample = _capture()
        except Exception as exc:
            self._fail(f"ROUGH_DEFOCUS: capture failed: {exc}")
            return
        if self._cancel.is_set():
            return

        defocuser = DefocusController(
            focuser=focuser_ctrl,
            focuser_cfg=self._cfg.focuser,
            rough_cfg=self._cfg.rough_collimation,
            bit_depth=bit_depth,
            settle_seconds=0.0,
        )
        defocus_result = defocuser.defocus(
            capture_frame=_capture,
            frame_width=sample.width,
            frame_height=sample.height,
            cancel_check=lambda: self._cancel.is_set(),
        )
        if self._cancel.is_set():
            return
        _log.info(
            "ROUGH_DEFOCUS defocus: %s radius=%s px",
            defocus_result.reason,
            f"{defocus_result.estimated_radius_px:.1f}"
            if defocus_result.estimated_radius_px is not None else "n/a",
        )
        self._do_transition(CollimationState.MAP_SCREWS_BY_OBSTRUCTION)

    def _handle_map_screws(self) -> None:
        # Full screw-response calibration requires per-screw user interaction
        # (physically touching each screw to detect the shadow shift) which is
        # not yet modelled in the state machine.  Proceed without calibration —
        # CollimationAdvisor will suppress recommendations when no ScrewCalibration
        # objects are available.
        _log.info("MAP_SCREWS_BY_OBSTRUCTION: no calibration — screw mapping skipped")
        self._do_transition(CollimationState.MEASURE_DONUT)

    def _handle_measure_donut(self) -> None:
        from ...domain.collimation.models import FrameMeasurement
        from ...domain.collimation.processing.donut_detection import DonutAnalyzer
        from ...domain.collimation.processing.frame import normalize_frame
        from .collimation_advisor import CollimationAdvisor

        bit_depth  = self._camera.get_bit_depth()
        exposure_s = self._camera.get_exposure_ms() / 1000.0
        analyzer   = DonutAnalyzer()
        advisor    = CollimationAdvisor(calibrations=[])  # no screw cal in MVP

        for attempt in range(5):
            if self._cancel.is_set():
                return
            try:
                raw = self._camera.capture(exposure_s)
            except Exception as exc:
                _log.warning("MEASURE_DONUT attempt %d: capture failed: %s", attempt + 1, exc)
                continue
            processed = normalize_frame(raw, bit_depth=bit_depth)
            result    = analyzer.analyze(processed)
            if result.reason == "ok" and result.measurement is not None:
                donut = result.measurement
                _log.info(
                    "MEASURE_DONUT: error=(%.1f, %.1f) mag=%.1f conf=%.2f",
                    donut.error_x_px, donut.error_y_px,
                    donut.error_magnitude_px, donut.confidence,
                )
                with self._lock:
                    self._frame_counter += 1
                    self._last_frame = FrameMeasurement(
                        frame_index=self._frame_counter,
                        captured_at=_now(),
                        exposure_s=exposure_s,
                        gain=self._camera.get_gain(),
                        donut=donut,
                    )
                    rec = advisor.recommend(donut)
                    if rec is not None:
                        self._last_recommendation = rec
                if self._frame_archive is not None:
                    self._frame_archive.save_frame(
                        session_id=self._session_id,
                        state="measure_donut",
                        frame_index=self._frame_counter,
                        captured_at=_now(),
                        exposure_s=exposure_s,
                        gain=self._camera.get_gain(),
                        bit_depth=bit_depth,
                        ref_x=raw.width / 2.0,
                        ref_y=raw.height / 2.0,
                        raw_frame=raw,
                        analysis={
                            "reason": "ok",
                            "error_x_px": donut.error_x_px,
                            "error_y_px": donut.error_y_px,
                            "error_magnitude_px": donut.error_magnitude_px,
                            "confidence": donut.confidence,
                        },
                    )
                self._do_transition(CollimationState.GUIDE_ROUGH_COLLIMATION)
                return
            _log.debug("MEASURE_DONUT attempt %d: %s", attempt + 1, result.reason)

        _log.warning("MEASURE_DONUT: no donut detected after 5 attempts — proceeding")
        self._do_transition(CollimationState.GUIDE_ROUGH_COLLIMATION)

    def _handle_map_mask_sectors(self) -> None:
        from ...domain.collimation.models import MaskSectorCalibration
        from .contradiction_detector import ContradictionDetector
        from .spike_smoother import SpikeSmoother

        # Full sector-blade calibration (user closes each blade to identify which
        # spike vanishes) is deferred; use a default T1/T2/T3 angular assignment.
        cal = MaskSectorCalibration(
            sector_0_deg="T1",
            sector_120_deg="T2",
            sector_240_deg="T3",
            calibrated_at=_now(),
        )
        smoother = SpikeSmoother(window=self._cfg.fine_collimation.moving_window_frames)
        detector = ContradictionDetector(
            focus_target_px=self._cfg.fine_collimation.target_residual_px,
        )
        with self._lock:
            self._mask_calibration  = cal
            self._spike_smoother    = smoother
            self._contradiction_detector = detector

        _log.info("MAP_MASK_SECTORS: default sector mapping T1/T2/T3")
        self._do_transition(CollimationState.FINE_FOCUS)

    def _handle_fine_focus(self) -> None:
        from ...domain.collimation.models import ReferenceCenterCalibration
        from ...domain.collimation.processing.frame import normalize_frame
        from ...domain.collimation.processing.spike_decomposition import decompose_spike_errors
        from ...domain.collimation.processing.spike_detection import detect_spikes
        from .fine_focus import FineFocusController
        from .focuser_control import CollimationFocuserControl

        bit_depth    = self._camera.get_bit_depth()
        exposure_s   = self._camera.get_exposure_ms() / 1000.0
        focuser_ctrl = CollimationFocuserControl(self._focuser, self._cfg.focuser)
        ref_cfg      = self._cfg.reference_center
        frame_w: list[int] = []  # populated on first capture

        def _get_error() -> float | None:
            if self._cancel.is_set():
                return None
            try:
                raw = self._camera.capture(exposure_s)
            except Exception:
                return None
            processed = normalize_frame(raw, bit_depth=bit_depth)
            if not frame_w:
                frame_w.append(processed.width)
                frame_w.append(processed.height)
            ref = ReferenceCenterCalibration(
                offset_x_px=ref_cfg.offset_x_px,
                offset_y_px=ref_cfg.offset_y_px,
                source=ref_cfg.source.value,
            ).compute(frame_w[0], frame_w[1])
            spike_result = detect_spikes(processed, ref)
            if spike_result.reason != "ok" or spike_result.raw_result is None:
                return None
            try:
                decomp = decompose_spike_errors(spike_result.raw_result.lines)
            except ValueError:
                return None
            return decomp.common_focus_error_px

        controller = FineFocusController(
            target_px=self._cfg.fine_collimation.target_residual_px,
            coarse_step=self._cfg.focuser.coarse_step,
            fine_step=self._cfg.focuser.fine_step,
            settle_seconds=0.0,
        )
        result = controller.focus(
            get_error=_get_error,
            move_focuser=lambda s: focuser_ctrl.move_focus_relative(s),
            cancel_check=lambda: self._cancel.is_set(),
        )
        if self._cancel.is_set():
            return
        _log.info(
            "FINE_FOCUS: %s initial=%.2f final=%s px steps=%d",
            result.reason, result.initial_error_px,
            f"{result.final_error_px:.2f}" if result.final_error_px is not None else "n/a",
            result.steps_taken,
        )
        self._do_transition(CollimationState.MEASURE_SPIKES)

    def _handle_measure_spikes(self) -> None:
        from ...domain.collimation.models import FrameMeasurement, ReferenceCenterCalibration
        from ...domain.collimation.processing.frame import normalize_frame
        from ...domain.collimation.processing.spike_decomposition import decompose_spike_errors
        from ...domain.collimation.processing.spike_detection import detect_spikes
        from .fine_collimation_advisor import FineCollimationAdvisor, align_residuals_to_screws

        bit_depth  = self._camera.get_bit_depth()
        exposure_s = self._camera.get_exposure_ms() / 1000.0
        ref_cfg    = self._cfg.reference_center

        with self._lock:
            smoother  = self._spike_smoother
            detector  = self._contradiction_detector
            mask_cal  = self._mask_calibration

        if smoother is None or detector is None or mask_cal is None:
            _log.warning("MEASURE_SPIKES: not initialised — transitioning without measurement")
            self._do_transition(CollimationState.GUIDE_FINE_COLLIMATION)
            return

        advisor = FineCollimationAdvisor(
            target_residual_px=self._cfg.fine_collimation.target_residual_px,
            seeing_limited_px=self._cfg.fine_collimation.poor_seeing_residual_px,
        )

        for attempt in range(5):
            if self._cancel.is_set():
                return
            try:
                raw = self._camera.capture(exposure_s)
            except Exception as exc:
                _log.warning("MEASURE_SPIKES attempt %d: capture failed: %s", attempt + 1, exc)
                continue
            processed = normalize_frame(raw, bit_depth=bit_depth)
            ref = ReferenceCenterCalibration(
                offset_x_px=ref_cfg.offset_x_px,
                offset_y_px=ref_cfg.offset_y_px,
                source=ref_cfg.source.value,
            ).compute(processed.width, processed.height)

            spike_result = detect_spikes(processed, ref)
            if spike_result.reason != "ok" or spike_result.measurement is None:
                _log.debug("MEASURE_SPIKES attempt %d: %s", attempt + 1, spike_result.reason)
                continue

            smoother.add(spike_result.measurement)
            smoothed = smoother.compute()
            if smoothed is None:
                continue

            raw_result = spike_result.raw_result
            if raw_result is None or len(raw_result.lines) != 3:
                continue

            try:
                decomp = decompose_spike_errors(raw_result.lines)
            except ValueError as exc:
                _log.warning("MEASURE_SPIKES: decompose failed: %s", exc)
                continue

            residuals     = align_residuals_to_screws(decomp, raw_result.lines, mask_cal)
            rec           = advisor.recommend(residuals, smoothed)
            contradiction = detector.assess(smoothed, decomp)

            with self._lock:
                self._frame_counter += 1
                self._last_frame = FrameMeasurement(
                    frame_index=self._frame_counter,
                    captured_at=_now(),
                    exposure_s=exposure_s,
                    gain=self._camera.get_gain(),
                    spike=spike_result.measurement,
                )
                if rec is not None and not contradiction.stop_guidance:
                    self._last_recommendation = rec
            if self._frame_archive is not None:
                self._frame_archive.save_frame(
                    session_id=self._session_id,
                    state="measure_spikes",
                    frame_index=self._frame_counter,
                    captured_at=_now(),
                    exposure_s=exposure_s,
                    gain=self._camera.get_gain(),
                    bit_depth=bit_depth,
                    ref_x=ref.x,
                    ref_y=ref.y,
                    raw_frame=raw,
                    analysis={
                        "reason": "ok",
                        "focus_error_px": spike_result.measurement.focus_error_px,
                        "offset_from_ref_px": spike_result.measurement.offset_from_ref_px,
                        "confidence": spike_result.measurement.confidence,
                    },
                )

            _log.info(
                "MEASURE_SPIKES: focus=%.2f px contradiction=%s",
                decomp.common_focus_error_px,
                contradiction.stop_guidance,
            )
            self._do_transition(CollimationState.GUIDE_FINE_COLLIMATION)
            return

        _log.warning("MEASURE_SPIKES: no spikes detected after 5 attempts — proceeding")
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

