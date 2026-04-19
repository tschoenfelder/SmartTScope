import math
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional

from ..domain.session import SessionLog, StageTimestamp
from ..domain.states import SessionState
from ..ports.camera import CameraPort
from ..ports.mount import MountPort, MountState
from ..ports.solver import SolverPort
from ..ports.stacker import StackerPort, StackFrame
from ..ports.storage import StoragePort

# Target: M42 Orion Nebula
M42_RA = 5.5881   # hours  (05h 35m 17.3s)
M42_DEC = -5.391  # degrees (−05° 23′ 28″)

CENTERING_TOLERANCE_ARCMIN = 2.0
MAX_RECENTER_ITERATIONS = 3
SOLVE_MAX_ATTEMPTS = 2
PREVIEW_FRAMES = 3
STACK_DEPTH = 10
PREVIEW_EXPOSURE_S = 5.0
STACK_EXPOSURE_S = 30.0

StateCallback = Callable[[SessionState], None]


@dataclass
class OpticalProfile:
    name: str
    pixel_scale_arcsec: float  # hint passed to plate solver

# Built-in profiles for the C8 platform
C8_NATIVE   = OpticalProfile("C8-native",   pixel_scale_arcsec=0.38)
C8_REDUCER  = OpticalProfile("C8-reducer",  pixel_scale_arcsec=0.60)
C8_BARLOW2X = OpticalProfile("C8-barlow2x", pixel_scale_arcsec=0.19)


class WorkflowError(Exception):
    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason
        super().__init__(f"[{stage}] {reason}")


class VerticalSliceRunner:
    def __init__(
        self,
        camera: CameraPort,
        mount: MountPort,
        solver: SolverPort,
        stacker: StackerPort,
        storage: StoragePort,
        optical_profile: OpticalProfile = C8_NATIVE,
        on_state_change: Optional[StateCallback] = None,
    ) -> None:
        self._camera = camera
        self._mount = mount
        self._solver = solver
        self._stacker = stacker
        self._storage = storage
        self._profile = optical_profile
        self._on_state_change = on_state_change

    def run(self) -> SessionLog:
        log = SessionLog(
            session_id=str(uuid.uuid4()),
            target_name="M42",
            target_ra=M42_RA,
            target_dec=M42_DEC,
            optical_config=self._profile.name,
            started_at=datetime.utcnow(),
        )
        self._transition(log, SessionState.IDLE)

        try:
            for stage_name, stage_fn in self._stage_pipeline():
                try:
                    stage_fn(log)
                except WorkflowError:
                    raise
                except Exception as exc:
                    raise WorkflowError(stage_name, str(exc)) from exc
        except WorkflowError as err:
            log.failure_stage = err.stage
            log.failure_reason = err.reason
            self._transition(log, SessionState.FAILED)
        finally:
            log.completed_at = datetime.utcnow()
            self._mount.disconnect()
            self._camera.disconnect()

        return log

    # --- pipeline ---

    def _stage_pipeline(self) -> list:
        return [
            ("connect",          self._stage_connect),
            ("initialize_mount", self._stage_initialize_mount),
            ("align",            self._stage_align),
            ("goto",             self._stage_goto),
            ("recenter",         self._stage_recenter),
            ("preview",          self._stage_preview),
            ("stack",            self._stage_stack),
            ("save",             self._stage_save),
        ]

    # --- stages ---

    def _stage_connect(self, log: SessionLog) -> None:
        self._start_stage(log, "connect")
        if not self._camera.connect():
            raise WorkflowError("connect", "Camera failed to connect")
        if not self._mount.connect():
            raise WorkflowError("connect", "Mount failed to connect")
        self._finish_stage(log, "connect")
        self._transition(log, SessionState.CONNECTED)

    def _stage_initialize_mount(self, log: SessionLog) -> None:
        self._start_stage(log, "initialize_mount")
        state = self._mount.get_state()
        if state == MountState.AT_LIMIT:
            raise WorkflowError("initialize_mount", "Mount is at a hardware limit — resolve before continuing")
        if state == MountState.PARKED:
            if not self._mount.unpark():
                raise WorkflowError("initialize_mount", "Unpark command rejected by mount")
        if not self._mount.enable_tracking():
            raise WorkflowError("initialize_mount", "Could not enable sidereal tracking")
        self._finish_stage(log, "initialize_mount")
        self._transition(log, SessionState.MOUNT_READY)

    def _stage_align(self, log: SessionLog) -> None:
        self._start_stage(log, "align")
        exposures = [5.0, 10.0]
        for exposure in exposures[:SOLVE_MAX_ATTEMPTS]:
            log.plate_solve_attempts += 1
            frame = self._camera.capture(exposure)
            result = self._solver.solve(frame.data, self._profile.pixel_scale_arcsec)
            if result.success:
                if not self._mount.sync(result.ra, result.dec):
                    raise WorkflowError("align", "Mount sync after plate solve failed")
                self._finish_stage(log, "align")
                self._transition(log, SessionState.ALIGNED)
                return
        raise WorkflowError(
            "align",
            f"Plate solve failed after {SOLVE_MAX_ATTEMPTS} attempts — check sky conditions and polar alignment",
        )

    def _stage_goto(self, log: SessionLog) -> None:
        self._start_stage(log, "goto")
        if not self._mount.goto(M42_RA, M42_DEC):
            raise WorkflowError("goto", "GoTo command rejected by mount")
        if self._mount.is_slewing():
            raise WorkflowError("goto", "Mount stalled — slew did not complete")
        self._finish_stage(log, "goto")
        self._transition(log, SessionState.SLEWED)

    def _stage_recenter(self, log: SessionLog) -> None:
        self._start_stage(log, "recenter")
        for i in range(1, MAX_RECENTER_ITERATIONS + 1):
            log.centering_iterations = i
            frame = self._camera.capture(10.0)
            result = self._solver.solve(frame.data, self._profile.pixel_scale_arcsec)
            if not result.success:
                raise WorkflowError("recenter", f"Plate solve failed during recentering (iteration {i})")
            offset = _angular_offset_arcmin(result.ra, result.dec, M42_RA, M42_DEC)
            log.centering_offset_arcmin = round(offset, 2)
            if offset <= CENTERING_TOLERANCE_ARCMIN:
                self._finish_stage(log, "recenter")
                self._transition(log, SessionState.CENTERED)
                return
            if i < MAX_RECENTER_ITERATIONS:
                self._mount.goto(M42_RA, M42_DEC)

        # Tolerance not met — degrade gracefully, do not abort
        log.warnings.append(
            f"Centering: exceeded {MAX_RECENTER_ITERATIONS} iterations; "
            f"final offset {log.centering_offset_arcmin:.1f} arcmin — continuing in degraded mode"
        )
        self._finish_stage(log, "recenter")
        self._transition(log, SessionState.CENTERING_DEGRADED)

    def _stage_preview(self, log: SessionLog) -> None:
        self._start_stage(log, "preview")
        self._transition(log, SessionState.PREVIEWING)
        for _ in range(PREVIEW_FRAMES):
            self._camera.capture(PREVIEW_EXPOSURE_S)
            # Real implementation: auto-stretch and push via WebSocket
        self._finish_stage(log, "preview")

    def _stage_stack(self, log: SessionLog) -> None:
        self._start_stage(log, "stack")
        self._transition(log, SessionState.STACKING)
        self._stacker.reset()
        for i in range(1, STACK_DEPTH + 1):
            frame = self._camera.capture(STACK_EXPOSURE_S)
            stacked = self._stacker.add_frame(StackFrame(data=frame.data, frame_number=i))
            log.frames_integrated = stacked.frames_integrated
            log.frames_rejected = stacked.frames_rejected
            # Real implementation: push updated stack via WebSocket
        self._finish_stage(log, "stack")
        self._transition(log, SessionState.STACK_COMPLETE)

    def _stage_save(self, log: SessionLog) -> None:
        self._start_stage(log, "save")
        if not self._storage.has_free_space():
            raise WorkflowError("save", "Disk full — cannot save session artifacts")
        stacked = self._stacker.get_current_stack()
        # Transition before serialising so the stored log reflects the final state.
        self._transition(log, SessionState.SAVED)
        artifacts = self._storage.save(stacked.data, log.to_dict())
        log.saved_image_path = artifacts.image_path
        log.saved_log_path = artifacts.log_path
        self._finish_stage(log, "save")

    # --- helpers ---

    def _transition(self, log: SessionLog, state: SessionState) -> None:
        log.state = state
        if self._on_state_change:
            self._on_state_change(state)

    def _start_stage(self, log: SessionLog, name: str) -> None:
        log.stage_timestamps.append(StageTimestamp(stage=name, started_at=datetime.utcnow()))

    def _finish_stage(self, log: SessionLog, name: str) -> None:
        for ts in reversed(log.stage_timestamps):
            if ts.stage == name and ts.completed_at is None:
                ts.completed_at = datetime.utcnow()
                return


def _angular_offset_arcmin(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    """Approximate angular separation in arcminutes (small-angle, equatorial coords)."""
    dec_rad = math.radians((dec1 + dec2) / 2)
    dra_deg = (ra1 - ra2) * 15 * math.cos(dec_rad)
    ddec_deg = dec1 - dec2
    return math.sqrt(dra_deg ** 2 + ddec_deg ** 2) * 60
