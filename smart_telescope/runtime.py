"""RuntimeContext — single supervised owner of all adapter state.

All adapter references, lifecycle methods, and shutdown logic live here.
API modules access adapters via the public functions in api/deps.py, which
delegate to the active RuntimeContext.
"""

from __future__ import annotations

import contextlib
import logging
import os
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .services.guiding_service import GuidingService
    from .services.observing_service import ObservingService

from . import config
from .ports.camera import CameraPort
from .ports.focuser import FocuserPort
from .ports.mount import MountPort
from .ports.solver import SolverPort
from .ports.stacker import StackerPort
from .ports.storage import StoragePort
from .services.camera_offset_service import CameraOffsetService
from .services.command_history import CommandHistoryService
from .services.section_logger import SectionLogger
from .services.service_call_logger import ServiceCallLogger
from .services.user_action_logger import UserActionLogger
from .services.diagnostic_frame_store import DiagnosticFrameStore
from .services.frame_analyzer import FrameAnalyzerProtocol, load_external_analyzer
from .services.hardware_coordinator import HardwareCommandCoordinator
from .services.cooling import CoolingService
from .services.dawn_watcher import DawnWatcher
from .services.device_state import DeviceStateService
from .services.master_source import MasterSourceService
from .services.raspberry_time_trust import RaspberryTimeTrustService
from .services.job_manager import JobManager

_log = logging.getLogger(__name__)


_MODE_RANK: dict[str, int] = {"mock": 2, "simulator": 1, "real": 0}


def _build_main_camera(ctx: RuntimeContext) -> CameraPort:
    """Select and connect the main camera adapter.

    Selection priority follows the same rules as the old deps._build_adapters():
      Camera: TOUPTEK_INDEX → [cameras] main → SIMULATOR_FITS_DIR →
              REPLAY_FITS_DIR → MockCamera

    M10-021: this can take many seconds on real hardware (SDK open, configure,
    startup settle, priming first-frame captures) and therefore runs decoupled
    from the mount build — never inside `_adapters_lock`.
    """
    from . import config
    from .adapters.mock.camera import MockCamera

    main_index_str = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
    sim_dir        = os.environ.get("SIMULATOR_FITS_DIR", "")
    replay_dir     = os.environ.get("REPLAY_FITS_DIR", "")

    camera: CameraPort
    cam_mode: str
    main_spec = getattr(config, "CAMERA_SPECS", {}).get("main")
    if main_spec is not None and main_spec.enabled and not os.environ.get("TOUPTEK_INDEX"):
        if main_spec.backend.lower() != "native":
            _log.error(
                "Configured camera backend '%s' is not available — falling back to MockCamera.",
                main_spec.backend,
            )
            camera = MockCamera()
            cam_mode = "mock"
        else:
            try:
                from .adapters.touptek.managed import SmartTouptekCamera
                camera = SmartTouptekCamera(
                    index=main_spec.index or 0,
                    camera_id=main_spec.camera_id or None,
                    model=main_spec.model or None,
                    name=main_spec.name or None,
                    capture_mode=main_spec.capture_mode,
                    setup_profile=main_spec.setup_profile,
                    startup_delay_s=main_spec.startup_delay_s,
                    startup_monitor_interval_s=main_spec.startup_monitor_interval_s,
                    prime_attempts=main_spec.prime_attempts,
                    prime_timeout_s=main_spec.prime_timeout_s,
                    prime_exposure_s=main_spec.prime_exposure_s,
                    bit_depth=main_spec.bit_depth,
                )
                # M10-024: measured (not estimated) connect+prime duration —
                # evidence for whether camera bring-up alone explains any
                # observed request stalls, vs. a GIL-held SDK call.
                _t0 = time.monotonic()
                connected = camera.connect()
                _elapsed = time.monotonic() - _t0
                _log.info(
                    "Camera connect+prime timing: role=main model=%s elapsed=%.2fs",
                    main_spec.model or "*", _elapsed,
                )
                if not connected:
                    raise RuntimeError(
                        f"Camera '{main_spec.model or main_spec.role}' failed to connect — no device found"
                    )
                camera.set_gain(main_spec.gain)
                if main_spec.offset_hcg or main_spec.offset_lcg:
                    camera.set_black_level(main_spec.offset_for("HCG"))
                cam_mode = "real"
                _log.warning(
                    "Adapter selected: SmartTouptekCamera(role=main, model=%s)", main_spec.model or "*"
                )
            except Exception as exc:
                _log.error(
                    "Camera init failed for model=%r: %s — falling back to MockCamera. "
                    "Check USB connection and [cameras] config.",
                    getattr(main_spec, "model", None), exc,
                )
                camera = MockCamera()
                cam_mode = "mock"
    elif main_index_str:
        try:
            from .adapters.touptek.camera import ToupcamCamera
            from .services.camera_name_resolver import CameraNameResolver
            sdk_index = CameraNameResolver().resolve(main_index_str, config.CAMERA_SERIALS)
            camera = ToupcamCamera(index=sdk_index)
            cam_mode = "real"
            role_label = "TOUPTEK_INDEX env" if os.environ.get("TOUPTEK_INDEX") else "[cameras] main"
            _log.warning("Adapter selected: ToupcamCamera(index=%s)  [%s]", sdk_index, role_label)
        except Exception as exc:
            _log.error(
                "Camera init failed for '%s': %s — falling back to MockCamera. "
                "Check USB connection and [cameras] config.",
                main_index_str, exc,
            )
            camera = MockCamera()
            cam_mode = "mock"
    elif sim_dir:
        from pathlib import Path
        from .adapters.simulator.camera import SimulatorCamera
        camera = SimulatorCamera(Path(sim_dir))
        cam_mode = "simulator"
        _log.warning("Adapter selected: SimulatorCamera(dir=%s)", sim_dir)
    elif replay_dir:
        from .adapters.replay.camera import ReplayCamera
        camera = ReplayCamera.from_directory(replay_dir)
        cam_mode = "simulator"
        _log.warning("Adapter selected: ReplayCamera(dir=%s)", replay_dir)
    else:
        _log.warning("Adapter selected: MockCamera  — no TOUPTEK_INDEX, SIMULATOR_FITS_DIR or REPLAY_FITS_DIR set")
        camera = MockCamera()
        cam_mode = "mock"

    ctx._cam_mode = cam_mode
    ctx._update_hardware_mode()
    return camera


def _build_mount_focuser(ctx: RuntimeContext) -> tuple[MountPort, FocuserPort]:
    """Select and connect mount and focuser adapters.

    Selection priority: ONSTEP_PORT → SIMULATOR_FITS_DIR → MockMount/MockFocuser.

    M10-021: built before and independently of any camera — camera bring-up
    must never delay mount/time/location availability.
    """
    from . import config
    from .adapters.mock.focuser import MockFocuser
    from .adapters.mock.mount import MockMount

    onstep_port = os.environ.get("ONSTEP_PORT") or config.ONSTEP_PORT
    sim_dir     = os.environ.get("SIMULATOR_FITS_DIR", "")

    mnt_mode: str
    if onstep_port:
        from . import config as _cfg
        from .adapters.onstep import OnStepClient
        from .ports.mount import MountState
        safety_config = _cfg.build_onstep_safety_config()
        _log.info("Adapter selected: OnStepClient on port %s", onstep_port)
        _onstep_client = OnStepClient(onstep_port, safety_config=safety_config)
        result = _onstep_client.connect()
        mount = _onstep_client.mount
        focuser = _onstep_client.focuser
        if not result.connected:
            _log.error("OnStepClient.connect() failed on port %s — mount will be unavailable", onstep_port)
        else:
            _log.info("OnStepClient: connected on %s — REAL HARDWARE", onstep_port)
            try:
                current_state = mount.get_state()
            except Exception as exc:
                _log.warning("OnStepMount.get_state() failed after connect: %s — skipping auto-park", exc)
                current_state = MountState.UNKNOWN
            if current_state == MountState.UNKNOWN:
                _log.info("Mount state unknown after connect — skipping auto-park")
            elif current_state != MountState.PARKED:
                _log.info("Auto-parking mount after connect (state was %s)", current_state.name)
                try:
                    mount.park()
                except Exception as exc:
                    _log.warning("Auto-park after connect failed: %s", exc)
            else:
                _log.info("Mount already parked after connect")
        _log.info(
            "OnStepFocuser: connected, available=%s — %s",
            focuser.is_available,
            "REAL HARDWARE" if focuser.is_available else "focuser not available (check wiring)",
        )
        mnt_mode = "real"
        ctx._mnt_mode = mnt_mode
        ctx._update_hardware_mode()
        return mount, focuser

    if sim_dir:
        from .adapters.simulator.focuser import SimulatorFocuser
        from .adapters.simulator.mount import SimulatorMount
        _log.info("Adapter selected: SimulatorMount+SimulatorFocuser (SIMULATOR_FITS_DIR=%s)", sim_dir)
        mnt_mode = "simulator"
        ctx._mnt_mode = mnt_mode
        ctx._update_hardware_mode()
        return SimulatorMount(), SimulatorFocuser()

    _log.warning("Adapter selected: MockMount+MockFocuser — no ONSTEP_PORT or SIMULATOR_FITS_DIR set")
    mnt_mode = "mock"
    ctx._mnt_mode = mnt_mode
    ctx._update_hardware_mode()
    return MockMount(), MockFocuser()


class RuntimeContext:
    """Owns all adapter references and controls the application lifecycle.

    Lifecycle:
      startup  → RuntimeContext() created in FastAPI lifespan
      requests → connect_devices() called lazily on first access
      shutdown → shutdown() stops motion then closes connections

    Test isolation:
      reset_for_tests() clears all state so the next call rebuilds adapters.
    """

    def __init__(self) -> None:
        import uuid as _uuid
        from pathlib import Path
        self._camera: CameraPort | None = None
        self._mount: MountPort | None = None
        self._focuser: FocuserPort | None = None
        self._stacker: StackerPort | None = None
        self._storage: StoragePort | None = None
        self._solver: SolverPort | None = None
        self._preview_cameras: dict[int, CameraPort] = {}
        self._role_cameras: dict[str, CameraPort] = {}
        self._filter_wheel: object | None = None
        self._adapters_built: bool = False
        self._adapters_lock: threading.Lock = threading.Lock()
        # M10-018: the ToupTek SDK allows exactly one Open per physical device
        # (second open → 0x800700AA busy). Serialize all camera-open paths so
        # concurrent setup-FSM jobs / requests never race check-then-open.
        # RLock since M10-021: fallback paths inside a held section may route
        # to _connect_main_camera(), which takes the lock again.
        self._camera_open_lock: threading.RLock = threading.RLock()
        # M10-021: per-side adapter modes; camera side is None until its
        # (possibly background) build finishes so a real mount doesn't show a
        # false "mock hardware" mode while the camera is still connecting.
        self._cam_mode: str | None = None
        self._mnt_mode: str = "mock"
        self._app_session_id: str = str(_uuid.uuid4())
        self.coordinator         = HardwareCommandCoordinator()
        self.cooling_service     = CoolingService()
        self.device_state        = DeviceStateService()
        self.master_source_svc   = MasterSourceService()
        self.raspberry_trust_svc = RaspberryTimeTrustService()
        self.dawn_watcher        = DawnWatcher()
        self.job_manager         = JobManager()
        _cmd_dir = config.COMMAND_HISTORY_DIR
        self.command_history     = CommandHistoryService(
            session_id=self._app_session_id,
            path=Path(_cmd_dir) / f"{self._app_session_id[:8]}.jsonl" if _cmd_dir else None,
        )
        self.section_logger      = SectionLogger(
            session_id=self._app_session_id,
            log_dir=config.LOG_DIR,
        )
        self.service_call_logger = ServiceCallLogger(
            section_logger=self.section_logger,
            session_id=self._app_session_id,
        )
        self.user_action_logger = UserActionLogger(
            section_logger=self.section_logger,
            session_id=self._app_session_id,
        )
        from .domain.diagnostic_frame import DiagnosticFrameConfig, DiagnosticStoreMode
        self.diagnostic_frame_store = DiagnosticFrameStore(DiagnosticFrameConfig(
            enabled=config.DIAGNOSTIC_FRAMES_ENABLED,
            store_mode=DiagnosticStoreMode(config.DIAGNOSTIC_FRAMES_STORE_MODE),
            retention_days=config.DIAGNOSTIC_FRAMES_RETENTION_DAYS,
            frame_dir=config.DIAGNOSTIC_FRAMES_DIR,
        ))
        self.camera_offset_service: CameraOffsetService = CameraOffsetService.from_config()
        self._optical_train_registry: object | None = None  # OpticalTrainRegistry
        # M10-002: parallel camera identification (starts in connect_devices()).
        from .services.camera_readiness import CameraReadinessService
        self.camera_readiness: CameraReadinessService = CameraReadinessService(
            registry_provider=self.get_optical_train_registry,
            wheel_provider=self.get_filter_wheel,
            open_lock=self._camera_open_lock,
        )
        # M10-003: per-camera setup FSM (tuning/star-check/focus) — launches a
        # JobManager-arbitrated worker for each camera the identification scan
        # detects; starts alongside camera_readiness in connect_devices().
        from .services.camera_setup_fsm import CameraSetupService
        self.camera_setup: CameraSetupService = CameraSetupService(
            job_manager=self.job_manager,
            camera_provider=self.get_camera_by_role,
            readiness_snapshot=self.camera_readiness.snapshot,
            registry_provider=self.get_optical_train_registry,
        )
        # Optional external frame analyzer (loaded when configured in [analysis])
        self.frame_analyzer: FrameAnalyzerProtocol | None = (
            load_external_analyzer(config.EXTERNAL_FRAME_ANALYZER_MODULE)
            if config.EXTERNAL_FRAME_ANALYZER_MODULE else None
        )
        # Session runner (R0-005)
        self.session_lock:    threading.Lock = threading.Lock()
        self._active_runner:  object | None  = None  # VerticalSliceRunner | None
        self._runner_thread:  object | None  = None  # threading.Thread | None
        # Autogain job (R0-006)
        self.autogain_lock:   threading.Lock = threading.Lock()
        self._autogain_job:   object | None  = None  # autogain._Job | None
        # Hardware mode (R5-011): set by _build_adapters; default "mock" until adapters built
        self._hardware_mode: str = "mock"
        # Guiding service (GUD): lazily created on first access
        self._guiding_service: GuidingService | None = None
        # Top-level observing state machine orchestrator: lazily created on first access
        self._observing_service: ObservingService | None = None

    @property
    def hardware_mode(self) -> str:
        """Return the current hardware mode: 'real', 'simulator', or 'mock'."""
        return self._hardware_mode

    def _update_hardware_mode(self) -> None:
        """Recompute the combined mode (worst of camera/mount sides, R5-011)."""
        modes = [m for m in (self._cam_mode, self._mnt_mode) if m]
        self._hardware_mode = (
            max(modes, key=lambda m: _MODE_RANK[m]) if modes else "mock"
        )

    @property
    def guiding_service(self) -> GuidingService:
        """Return the lazily-created GuidingService (creates on first access)."""
        if self._guiding_service is None:
            from .services.guiding_service import GuidingService
            from .services.guide_measurement import CentroidConfig, GuideControllerConfig
            from . import config
            self._guiding_service = GuidingService.from_config(
                primary_role=config.GUIDING.primary_role,
                allow_fallback=config.GUIDING.allow_fallback,
                fallback_after_bad_frames=config.GUIDING.fallback_after_bad_frames,
                max_frame_age_s=config.GUIDING.max_frame_age_s,
                centroid_config=CentroidConfig(
                    roi_px=config.GUIDING.centroid_roi_px,
                    min_peak_snr=config.GUIDING.min_peak_snr,
                    saturation_fraction=config.GUIDING.saturation_fraction,
                ),
                controller_config=GuideControllerConfig(),
                measure_only=config.GUIDING.measure_only,
            )
        return self._guiding_service

    @property
    def observing_service(self) -> ObservingService:
        """Return the lazily-created ObservingService (creates on first access)."""
        if self._observing_service is None:
            from .services.observing_service import ObservingService
            self._observing_service = ObservingService()
        return self._observing_service

    # ── camera helpers ────────────────────────────────────────────────────────

    def _all_cameras(self) -> list:
        """Return list of all connected cameras (primary + preview)."""
        cams = []
        if self._camera is not None:
            cams.append(self._camera)
        cams.extend(self._preview_cameras.values())
        return cams

    def _apply_camera_offsets(self) -> None:
        """Apply configured black-level offsets to all connected cameras."""
        for cam in self._all_cameras():
            try:
                self.camera_offset_service.apply(cam)
            except Exception as exc:
                _log.warning("Camera offset apply failed: %s", exc, exc_info=True)

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def connect_devices(self) -> None:
        """Build and connect adapters (idempotent, thread-safe).

        Raises ConfigError immediately if the config file had a parse error,
        preventing further device connection on a broken installation.
        """
        from . import config as _config
        _config.check_load_error()
        if self._adapters_built:
            return
        with self._adapters_lock:
            if not self._adapters_built:
                self._validate_camera_role_ownership(_config.CAMERA_SPECS)
                # M10-021: mount + focuser connect first and alone — camera
                # bring-up (SDK open + prime frames, many seconds on real
                # hardware) must never delay mount/time/location endpoints.
                self._mount, self._focuser = _build_mount_focuser(self)
                self._adapters_built = True
                assert self._mount is not None
                self.device_state.start(self._mount)
                self.device_state.poll_now()  # BUG-012: populate cache immediately at startup
                # M10-002: camera identification runs in parallel with the
                # mount flow (user is typically still confirming time/location).
                self.camera_readiness.start()
                # M10-003: per-camera setup FSM follows the identification
                # results; a busy or missing camera never blocks the mount flow.
                self.camera_setup.start()
                from . import config as _cfg
                self.dawn_watcher.start(
                    self._mount,
                    self.device_state,
                    _cfg.OBSERVER_LAT,
                    _cfg.OBSERVER_LON,
                )
                # M10-021: main camera connects in the background; requests
                # that genuinely need it block in _main_camera() instead.
                threading.Thread(
                    target=self._connect_main_camera,
                    daemon=True, name="main-camera-connect",
                ).start()

    def _connect_main_camera(self) -> None:
        """Build + connect the main camera (idempotent, thread-safe, blocking).

        M10-021: runs in a background thread from connect_devices(); a request
        that genuinely needs the camera before that finishes calls it
        synchronously via _main_camera() and joins the in-progress build on
        _camera_open_lock.
        """
        if self._camera is not None:
            return
        with self._camera_open_lock:
            if self._camera is not None or not self._adapters_built:
                return
            camera = _build_main_camera(self)
            if not self._adapters_built:
                # reset_for_tests()/disconnect ran while we were building —
                # do not resurrect stale state.
                with contextlib.suppress(Exception):
                    camera.disconnect()
                return
            self._camera = camera
            try:
                self.camera_offset_service.apply(camera)
            except Exception as exc:
                _log.warning("Camera offset apply failed: %s", exc, exc_info=True)

    def _main_camera(self) -> CameraPort:
        """Return the main camera, connecting it now if the background build
        has not finished yet (M10-021)."""
        if self._camera is None:
            self._connect_main_camera()
        assert self._camera is not None
        return self._camera

    def _validate_camera_role_ownership(self, specs: dict[str, object]) -> None:
        if not specs:
            return
        try:
            from .adapters.touptek.managed import validate_unique_camera_roles
            validate_unique_camera_roles(specs)
        except ImportError:
            return

    def shutdown(self) -> None:
        """Stop moving hardware, stop polling, then close all connections.

        OnStep keeps executing a slew command even after the serial port
        closes, so stop commands must be sent first.
        """
        if self._guiding_service is not None:
            with contextlib.suppress(Exception):
                self._guiding_service.stop()
            self._guiding_service = None
        # Stop the setup watcher before cancel_all — a live watcher tick could
        # otherwise relaunch a camera job between cancellation and close.
        with contextlib.suppress(Exception):
            self.camera_setup.stop()
        self.job_manager.cancel_all()
        self.cooling_service.stop()
        self.dawn_watcher.stop()
        self.device_state.stop()
        with contextlib.suppress(Exception):
            self.camera_readiness.stop()
        with contextlib.suppress(Exception):
            self.section_logger.close()
        if self._focuser is not None:
            with contextlib.suppress(Exception):
                self._focuser.stop()
            _log.info("Shutdown: focuser stop sent")
        if self._mount is not None:
            with contextlib.suppress(Exception):
                self._mount.stop()
            _log.info("Shutdown: mount stop sent")
            with contextlib.suppress(Exception):
                self._mount.disconnect()
            _log.info("Shutdown: mount serial closed")
        for cam in list(self._preview_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        for cam in list(self._role_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        if self._filter_wheel is not None:
            with contextlib.suppress(Exception):
                self._filter_wheel.disconnect()  # type: ignore[attr-defined]
        if self._preview_cameras or self._role_cameras:
            _log.info(
                "Shutdown: %d preview + %d role camera handle(s) closed",
                len(self._preview_cameras), len(self._role_cameras),
            )

    def disconnect_devices(self) -> None:
        """Disconnect all adapters without stopping motion first.

        Prefer shutdown() for normal operation — this is for explicit
        disconnect-then-reconnect workflows.
        """
        if self._mount is not None:
            with contextlib.suppress(Exception):
                self._mount.disconnect()
        for cam in list(self._preview_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        for cam in list(self._role_cameras.values()):
            with contextlib.suppress(Exception):
                cam.disconnect()
        if self._filter_wheel is not None:
            with contextlib.suppress(Exception):
                self._filter_wheel.disconnect()  # type: ignore[attr-defined]
        self._camera = None
        self._mount = None
        self._focuser = None
        self._preview_cameras = {}
        self._role_cameras = {}
        self._filter_wheel = None
        self._adapters_built = False

    def reset_for_tests(self) -> None:
        """Clear all cached singletons for test isolation."""
        self.dawn_watcher.stop()
        self.device_state.stop()
        with contextlib.suppress(Exception):
            self.camera_setup.stop()
        with contextlib.suppress(Exception):
            self.camera_readiness.stop()
        if self._guiding_service is not None:
            with contextlib.suppress(Exception):
                self._guiding_service.stop()
            self._guiding_service = None
        self._observing_service = None
        self._camera = None
        self._mount = None
        self._focuser = None
        self._stacker = None
        self._storage = None
        self._solver = None
        self._adapters_built = False
        self._hardware_mode = "mock"
        self._cam_mode = None
        self._mnt_mode = "mock"
        self._preview_cameras = {}
        self._role_cameras = {}
        self._filter_wheel = None
        import uuid as _uuid
        from pathlib import Path
        self._app_session_id     = str(_uuid.uuid4())
        self.coordinator         = HardwareCommandCoordinator()
        self.cooling_service     = CoolingService()
        self.device_state        = DeviceStateService()
        self.master_source_svc   = MasterSourceService()
        self.raspberry_trust_svc = RaspberryTimeTrustService(
            session_trust_expiry_minutes=config.SESSION_TRUST_EXPIRY_MINUTES,
        )
        self.dawn_watcher        = DawnWatcher()
        self.job_manager         = JobManager()
        self.camera_offset_service = CameraOffsetService.from_config()
        self.command_history     = CommandHistoryService(session_id=self._app_session_id, path=None)
        self.section_logger      = SectionLogger(session_id=self._app_session_id)
        self.service_call_logger = ServiceCallLogger(
            section_logger=self.section_logger,
            session_id=self._app_session_id,
        )
        self.user_action_logger = UserActionLogger(
            section_logger=self.section_logger,
            session_id=self._app_session_id,
        )
        from .domain.diagnostic_frame import DiagnosticFrameConfig
        self.diagnostic_frame_store = DiagnosticFrameStore(DiagnosticFrameConfig())
        self.frame_analyzer: FrameAnalyzerProtocol | None = None
        with self.session_lock:
            self._active_runner = None
            self._runner_thread = None
        with self.autogain_lock:
            self._autogain_job = None

    # ── camera access ─────────────────────────────────────────────────────────

    def _role_for_sdk_index(self, index: int) -> str | None:
        """M10-018: map an SDK enumeration index to its configured enabled role.

        Never opens a device. Primary source is the readiness scan (already
        model-matched from enumeration); before the first scan, fall back to
        resolving each configured spec through CameraNameResolver.
        """
        from . import config
        scanned = False
        try:
            snap = self.camera_readiness.snapshot()
            scanned = bool(snap.get("scanned"))
            for role, entry in snap.get("roles", {}).items():
                if entry.get("status") == "DETECTED" and entry.get("sdk_index") == index:
                    return role
        except Exception:
            pass
        if scanned:
            return None  # scan ran and nobody owns this index
        from .services.camera_name_resolver import CameraNameResolver
        for role, spec in config.CAMERA_SPECS.items():
            if not spec.enabled:
                continue
            target = spec.index if spec.index is not None else (spec.model or None)
            if target is None:
                continue
            try:
                if CameraNameResolver().resolve(target, {}) == index:
                    return role
            except Exception:
                continue
        return None

    def get_camera(self) -> CameraPort:
        self.connect_devices()
        return self._main_camera()

    def peek_camera_by_role(self, role: str) -> CameraPort | None:
        """M10-022: the already-open camera for *role*, or None.

        Never connects a device and never takes _camera_open_lock — hot API
        paths (observing state poll, intent post) must not queue behind an
        in-progress camera open.
        """
        if role == "main":
            return self._camera
        return self._role_cameras.get(role)

    def get_preview_camera(self, index: int | str) -> CameraPort:
        from . import config

        # Old-style [cameras] config stores model names (e.g. "G3M678M") rather
        # than integer SDK indices.  Resolve to int before any comparison.
        if not isinstance(index, int):
            from .services.camera_name_resolver import CameraNameResolver
            index = CameraNameResolver().resolve(
                index, getattr(config, "CAMERA_SERIALS", {})
            )

        self.connect_devices()
        # M10-018: a configured role's device must never be opened twice — the
        # SDK allows one handle per device. Route preview requests for
        # role-owned devices to the shared role handle (hardware evidence
        # 2026-07-18: a preview auto-detect open of the guide camera starved
        # the role path with ERROR_BUSY).
        owner_role = self._role_for_sdk_index(index)
        if owner_role is not None:
            _log.info(
                "get_preview_camera(%d): device owned by role %r — sharing role handle",
                index, owner_role,
            )
            return self.get_camera_by_role(owner_role)
        main_index_str = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
        _log.info(
            "get_preview_camera(%d): main_index=%r cached=%s primary=%s",
            index,
            main_index_str or None,
            list(self._preview_cameras.keys()),
            type(self._camera).__name__,
        )

        if main_index_str:
            try:
                main_index = int(main_index_str)
            except ValueError:
                # main_index_str is a model name (e.g. "G3M678M") — resolve to SDK int.
                from .services.camera_name_resolver import CameraNameResolver
                try:
                    main_index = CameraNameResolver().resolve(
                        main_index_str, getattr(config, "CAMERA_SERIALS", {})
                    )
                except Exception:
                    main_index = -1  # unresolvable; skip primary-camera match
            if index == main_index:
                _log.info("get_preview_camera(%d): returning primary camera (%s)", index, type(self._camera).__name__)
                return self._main_camera()
            with self._camera_open_lock:
                if index not in self._preview_cameras:
                    _log.info("get_preview_camera(%d): opening secondary ToupcamCamera", index)
                    from .adapters.touptek.camera import ToupcamCamera
                    cam = ToupcamCamera(index=index)
                    if not cam.connect():
                        raise RuntimeError(f"Camera {index} failed to connect")
                    self._preview_cameras[index] = cam
                    _log.info("get_preview_camera(%d): connected → %s", index, cam.get_logical_name())
                    try:
                        self.camera_offset_service.apply(cam)
                    except Exception as exc:
                        _log.warning("Camera offset apply failed for preview camera: %s", exc, exc_info=True)
            return self._preview_cameras[index]

        with self._camera_open_lock:
            if index not in self._preview_cameras:
                _log.info("get_preview_camera(%d): no [cameras] config — trying SDK auto-detect", index)
                try:
                    from .adapters.touptek.camera import ToupcamCamera
                    cam = ToupcamCamera(index=index)
                    if not cam.connect():
                        raise RuntimeError(f"Camera {index}: connect() returned False")
                    self._preview_cameras[index] = cam
                    _log.info("get_preview_camera(%d): auto-detect connected → %s", index, cam.get_logical_name())
                    try:
                        self.camera_offset_service.apply(cam)
                    except Exception as exc:
                        _log.warning("Camera offset apply failed for preview camera: %s", exc, exc_info=True)
                except (ImportError, RuntimeError) as exc:
                    _log.warning("get_preview_camera(%d): SDK unavailable (%s) — falling back to %s",
                                 index, exc, type(self._camera).__name__)
                    # _camera_open_lock is an RLock — re-entering via
                    # _main_camera() from inside this held section is safe.
                    return self._main_camera()
        return self._preview_cameras[index]

    def get_camera_by_role(self, role: str) -> CameraPort:
        from . import config
        from fastapi import HTTPException

        if role in config.CAMERA_SPECS and config.CAMERA_SPECS[role].enabled:
            self.connect_devices()
            if role == "main":
                # M10-021: main is built by _connect_main_camera (possibly in
                # the background) — never open a second handle for it here.
                return self._main_camera()
            with self._camera_open_lock:
                if role not in self._role_cameras:
                    spec = config.CAMERA_SPECS[role]
                    if spec.backend.lower() != "native":
                        raise HTTPException(
                            status_code=501,
                            detail=(
                                f"Camera role '{role}' requests backend '{spec.backend}'. "
                                "The MVP runtime currently supports native cameras only."
                            ),
                        )
                    from .adapters.touptek.managed import SmartTouptekCamera
                    cam = SmartTouptekCamera(
                        index=spec.index or 0,
                        camera_id=spec.camera_id or None,
                        model=spec.model or None,
                        name=spec.name or None,
                        capture_mode=spec.capture_mode,
                        setup_profile=spec.setup_profile,
                        startup_delay_s=spec.startup_delay_s,
                        startup_monitor_interval_s=spec.startup_monitor_interval_s,
                        prime_attempts=spec.prime_attempts,
                        prime_timeout_s=spec.prime_timeout_s,
                        prime_exposure_s=spec.prime_exposure_s,
                        bit_depth=spec.bit_depth,
                    )
                    # M10-024: measured connect+prime duration per role camera.
                    _t0 = time.monotonic()
                    connected = cam.connect()
                    _elapsed = time.monotonic() - _t0
                    _log.info(
                        "Camera connect+prime timing: role=%s model=%s elapsed=%.2fs",
                        role, spec.model or "*", _elapsed,
                    )
                    if not connected:
                        raise RuntimeError(f"Camera role {role!r} failed to connect — no device found")
                    cam.set_gain(spec.gain)
                    if spec.offset_hcg or spec.offset_lcg:
                        cam.set_black_level(spec.offset_for("HCG"))
                    self._role_cameras[role] = cam
                    _log.info("get_camera_by_role(%s): connected %s", role, cam.get_logical_name())
            return self._role_cameras[role]

        if role not in config.CAMERAS:
            configured = list(config.CAMERAS.keys()) or ["(none)"]
            raise HTTPException(
                status_code=503,
                detail=(
                    f"Camera role '{role}' not configured. "
                    f"Configured roles: {', '.join(configured)}. "
                    f"Add it to [cameras] in smart_telescope.toml."
                ),
            )
        return self.get_preview_camera(config.CAMERAS[role])

    # ── mount / focuser ───────────────────────────────────────────────────────

    def get_mount(self) -> MountPort:
        self.connect_devices()
        assert self._mount is not None
        return self._mount

    def get_focuser(self) -> FocuserPort:
        self.connect_devices()
        assert self._focuser is not None
        return self._focuser

    def get_filter_wheel(self) -> object:
        from . import config

        if not config.FILTER_WHEEL.enabled:
            raise RuntimeError("Filter wheel is disabled in config")
        if self._filter_wheel is not None:
            return self._filter_wheel
        # M10-023: the wheel's first Open() shares _camera_open_lock with
        # every camera-open path — its EnumV2/Open must not race a camera's
        # SDK open on the same USB bus. One-time cost only: cached after.
        with self._camera_open_lock:
            if self._filter_wheel is not None:
                return self._filter_wheel
            spec = config.FILTER_WHEEL
            if spec.backend.lower() != "native":
                raise RuntimeError(f"Unsupported filter wheel backend: {spec.backend}")
            from .adapters.touptek.filter_wheel import TouptekFilterWheel
            wheel = TouptekFilterWheel(
                wheel_id=spec.wheel_id or None,
                model=spec.model or None,
                name=spec.name or None,
                settle_s=spec.settle_s,
            )
            if not wheel.connect():
                raise RuntimeError("ToupTek filter wheel failed to connect")
            self._filter_wheel = wheel
        return self._filter_wheel

    # ── auxiliary services ────────────────────────────────────────────────────

    def get_stacker(self) -> StackerPort:
        if self._stacker is None:
            try:
                from .adapters.numpy_stacker.stacker import NumpyStacker
                self._stacker = NumpyStacker()
            except ImportError:
                from .adapters.mock.stacker import MockStacker
                self._stacker = MockStacker()
        return self._stacker

    def make_stacker(self) -> StackerPort:
        """Create a fresh stacker instance (one per session)."""
        try:
            from .adapters.numpy_stacker.stacker import NumpyStacker
            return NumpyStacker()
        except ImportError:
            from .adapters.mock.stacker import MockStacker
            return MockStacker()

    def get_solver(self) -> SolverPort:
        if self._solver is None:
            from . import config
            astap_path  = os.environ.get("ASTAP_PATH") or config.ASTAP_PATH
            catalog_dir = os.environ.get("ASTAP_CATALOG_DIR") or config.ASTAP_CATALOG_DIR
            try:
                from .adapters.astap.solver import AstapSolver, find_astap
                from .adapters.mock.solver import MockSolver
                path = astap_path or find_astap()
                self._solver = AstapSolver(astap_path=path, catalog_dir=catalog_dir or None) if path else MockSolver()
            except Exception:
                from .adapters.mock.solver import MockSolver
                self._solver = MockSolver()
        return self._solver

    def get_storage(self) -> StoragePort:
        if self._storage is None:
            from . import config
            storage_dir = config.STORAGE_DIR
            if storage_dir:
                from pathlib import Path
                from .adapters.disk_storage.storage import DiskStorage
                self._storage = DiskStorage(Path(storage_dir))
            else:
                from .adapters.mock.storage import MockStorage
                self._storage = MockStorage()
        return self._storage

    # ── session runner (R0-005) ───────────────────────────────────────────────

    def get_active_runner(self) -> object | None:
        """Return the active VerticalSliceRunner, or None if not running."""
        return self._active_runner

    def is_session_running(self) -> bool:
        t = self._runner_thread
        return t is not None and t.is_alive()  # type: ignore[union-attr]

    def set_session(self, runner: object, thread: object) -> None:
        """Store runner + thread references (caller starts the thread)."""
        self._active_runner = runner
        self._runner_thread = thread

    def clear_session(self) -> None:
        self._active_runner = None
        self._runner_thread = None

    # ── autogain job (R0-006) ─────────────────────────────────────────────────

    def get_autogain_job(self) -> object | None:
        return self._autogain_job

    def set_autogain_job(self, job: object | None) -> None:
        self._autogain_job = job

    # ── optical train registry (R4) ───────────────────────────────────────────

    def get_optical_train_registry(self) -> object:
        """Return the OpticalTrainRegistry, building it lazily on first call."""
        if self._optical_train_registry is None:
            from .services.optical_train_registry import OpticalTrainRegistry

            def _resolve_index(role: str) -> int | None:
                # M10-015: give trains their real SDK enumeration index. Best
                # effort only — any failure (no SDK on Windows, camera not yet
                # plugged in) falls back to the configured/default index.
                try:
                    from .services.camera_name_resolver import CameraNameResolver
                    spec = config.CAMERA_SPECS.get(role)
                    if spec is not None and spec.index is not None:
                        target: str | int = spec.index
                    elif spec is not None and spec.model:
                        target = spec.model
                    elif role in config.CAMERAS:
                        target = config.CAMERAS[role]
                    else:
                        return None
                    return CameraNameResolver().resolve(target, config.CAMERA_SERIALS)
                except Exception as exc:
                    _log.debug("optical-train index resolution failed for '%s': %s", role, exc)
                    return None

            try:
                self._optical_train_registry = OpticalTrainRegistry.from_config(
                    resolve_index=_resolve_index,
                )
            except ValueError as exc:
                _log.error("OpticalTrainRegistry: %s", exc)
                self._optical_train_registry = OpticalTrainRegistry({})
        return self._optical_train_registry


# ── module-level singleton ────────────────────────────────────────────────────
# deps.py compatibility wrappers delegate here.  app.py creates the instance
# in the FastAPI lifespan and registers it via set_runtime().

_runtime: RuntimeContext | None = None


def get_runtime() -> RuntimeContext:
    """Return the active RuntimeContext, creating a default one if needed."""
    global _runtime
    if _runtime is None:
        _runtime = RuntimeContext()
    return _runtime


def set_runtime(ctx: RuntimeContext) -> None:
    """Register the application runtime context (called from FastAPI lifespan)."""
    global _runtime
    _runtime = ctx
