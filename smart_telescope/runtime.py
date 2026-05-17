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

from .ports.camera import CameraPort
from .ports.focuser import FocuserPort
from .ports.mount import MountPort
from .ports.solver import SolverPort
from .ports.stacker import StackerPort
from .ports.storage import StoragePort
from .services.hardware_coordinator import HardwareCommandCoordinator
from .services.cooling import CoolingService
from .services.device_state import DeviceStateService
from .services.job_manager import JobManager

_log = logging.getLogger(__name__)


_MODE_RANK: dict[str, int] = {"mock": 2, "simulator": 1, "real": 0}


def _build_adapters(
    ctx: RuntimeContext,
) -> tuple[CameraPort, MountPort, FocuserPort]:
    """Select and connect camera, mount, and focuser adapters.

    Selection priority follows the same rules as the old deps._build_adapters():
      Camera: TOUPTEK_INDEX → [cameras] main → SIMULATOR_FITS_DIR →
              REPLAY_FITS_DIR → MockCamera
      Mount/Focuser: ONSTEP_PORT → SIMULATOR_FITS_DIR → MockMount/MockFocuser
    """
    from . import config
    from .adapters.mock.camera import MockCamera
    from .adapters.mock.focuser import MockFocuser
    from .adapters.mock.mount import MockMount

    main_index_str = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
    onstep_port    = os.environ.get("ONSTEP_PORT") or config.ONSTEP_PORT
    sim_dir        = os.environ.get("SIMULATOR_FITS_DIR", "")
    replay_dir     = os.environ.get("REPLAY_FITS_DIR", "")

    camera: CameraPort
    cam_mode: str
    if main_index_str:
        from .adapters.touptek.camera import ToupcamCamera
        camera = ToupcamCamera(index=int(main_index_str))
        cam_mode = "real"
        role_label = "TOUPTEK_INDEX env" if os.environ.get("TOUPTEK_INDEX") else "[cameras] main"
        _log.warning("Adapter selected: ToupcamCamera(index=%s)  [%s]", main_index_str, role_label)
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

    mnt_mode: str
    if onstep_port:
        from .adapters.onstep.focuser import OnStepFocuser
        from .adapters.onstep.mount import OnStepMount
        from .ports.mount import MountState
        _log.info("Adapter selected: OnStepMount+OnStepFocuser on port %s", onstep_port)
        mount = OnStepMount(onstep_port)
        mount_connected = mount.connect()
        if not mount_connected:
            _log.error("OnStepMount.connect() failed on port %s — mount will be unavailable", onstep_port)
        else:
            _log.info("OnStepMount: connected on %s — REAL HARDWARE", onstep_port)
            current_state = mount.get_state()
            if current_state == MountState.UNKNOWN:
                _log.info("Mount state unknown after connect — skipping auto-park")
            elif current_state != MountState.PARKED:
                _log.info("Auto-parking mount after connect (state was %s)", current_state.name)
                mount.park()
            else:
                _log.info("Mount already parked after connect")
        focuser = OnStepFocuser(mount.serial_bus)
        focuser.connect()
        _log.info(
            "OnStepFocuser: connected, available=%s — %s",
            focuser.is_available,
            "REAL HARDWARE" if focuser.is_available else "focuser not available (check wiring)",
        )
        mnt_mode = "real"
        ctx._hardware_mode = max([cam_mode, mnt_mode], key=lambda m: _MODE_RANK[m])
        return camera, mount, focuser

    if sim_dir:
        from pathlib import Path
        from .adapters.simulator.focuser import SimulatorFocuser
        from .adapters.simulator.mount import SimulatorMount
        _log.info("Adapter selected: SimulatorMount+SimulatorFocuser (SIMULATOR_FITS_DIR=%s)", sim_dir)
        mnt_mode = "simulator"
        ctx._hardware_mode = max([cam_mode, mnt_mode], key=lambda m: _MODE_RANK[m])
        return camera, SimulatorMount(), SimulatorFocuser()

    _log.warning("Adapter selected: MockMount+MockFocuser — no ONSTEP_PORT or SIMULATOR_FITS_DIR set")
    mnt_mode = "mock"
    ctx._hardware_mode = max([cam_mode, mnt_mode], key=lambda m: _MODE_RANK[m])
    return camera, MockMount(), MockFocuser()


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
        self._camera: CameraPort | None = None
        self._mount: MountPort | None = None
        self._focuser: FocuserPort | None = None
        self._stacker: StackerPort | None = None
        self._storage: StoragePort | None = None
        self._solver: SolverPort | None = None
        self._preview_cameras: dict[int, CameraPort] = {}
        self._adapters_built: bool = False
        self._adapters_lock: threading.Lock = threading.Lock()
        self.coordinator     = HardwareCommandCoordinator()
        self.cooling_service = CoolingService()
        self.device_state    = DeviceStateService()
        self.job_manager     = JobManager()
        self._optical_train_registry: object | None = None  # OpticalTrainRegistry
        # Session runner (R0-005)
        self.session_lock:    threading.Lock = threading.Lock()
        self._active_runner:  object | None  = None  # VerticalSliceRunner | None
        self._runner_thread:  object | None  = None  # threading.Thread | None
        # Autogain job (R0-006)
        self.autogain_lock:   threading.Lock = threading.Lock()
        self._autogain_job:   object | None  = None  # autogain._Job | None
        # Hardware mode (R5-011): set by _build_adapters; default "mock" until adapters built
        self._hardware_mode: str = "mock"

    @property
    def hardware_mode(self) -> str:
        """Return the current hardware mode: 'real', 'simulator', or 'mock'."""
        return self._hardware_mode

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
                self._camera, self._mount, self._focuser = _build_adapters(self)
                self._adapters_built = True
                assert self._mount is not None
                self.device_state.start(self._mount)

    def shutdown(self) -> None:
        """Stop moving hardware, stop polling, then close all connections.

        OnStep keeps executing a slew command even after the serial port
        closes, so stop commands must be sent first.
        """
        self.job_manager.cancel_all()
        self.cooling_service.stop()
        self.device_state.stop()
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
        if self._preview_cameras:
            _log.info("Shutdown: %d secondary camera handle(s) closed", len(self._preview_cameras))

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
        self._camera = None
        self._mount = None
        self._focuser = None
        self._preview_cameras = {}
        self._adapters_built = False

    def reset_for_tests(self) -> None:
        """Clear all cached singletons for test isolation."""
        self.device_state.stop()
        self._camera = None
        self._mount = None
        self._focuser = None
        self._stacker = None
        self._storage = None
        self._solver = None
        self._adapters_built = False
        self._hardware_mode = "mock"
        self._preview_cameras = {}
        self.coordinator     = HardwareCommandCoordinator()
        self.cooling_service = CoolingService()
        self.device_state    = DeviceStateService()
        self.job_manager     = JobManager()
        with self.session_lock:
            self._active_runner = None
            self._runner_thread = None
        with self.autogain_lock:
            self._autogain_job = None

    # ── camera access ─────────────────────────────────────────────────────────

    def get_camera(self) -> CameraPort:
        self.connect_devices()
        assert self._camera is not None
        return self._camera

    def get_preview_camera(self, index: int) -> CameraPort:
        from . import config

        self.connect_devices()
        main_index_str = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
        _log.info(
            "get_preview_camera(%d): main_index=%r cached=%s primary=%s",
            index,
            int(main_index_str) if main_index_str else None,
            list(self._preview_cameras.keys()),
            type(self._camera).__name__,
        )

        if main_index_str:
            main_index = int(main_index_str)
            if index == main_index:
                _log.info("get_preview_camera(%d): returning primary camera (%s)", index, type(self._camera).__name__)
                assert self._camera is not None
                return self._camera
            if index not in self._preview_cameras:
                _log.info("get_preview_camera(%d): opening secondary ToupcamCamera", index)
                from .adapters.touptek.camera import ToupcamCamera
                cam = ToupcamCamera(index=index)
                if not cam.connect():
                    raise RuntimeError(f"Camera {index} failed to connect")
                self._preview_cameras[index] = cam
                _log.info("get_preview_camera(%d): connected → %s", index, cam.get_logical_name())
            return self._preview_cameras[index]

        if index not in self._preview_cameras:
            _log.info("get_preview_camera(%d): no [cameras] config — trying SDK auto-detect", index)
            try:
                from .adapters.touptek.camera import ToupcamCamera
                cam = ToupcamCamera(index=index)
                if not cam.connect():
                    raise RuntimeError(f"Camera {index}: connect() returned False")
                self._preview_cameras[index] = cam
                _log.info("get_preview_camera(%d): auto-detect connected → %s", index, cam.get_logical_name())
            except (ImportError, RuntimeError) as exc:
                _log.warning("get_preview_camera(%d): SDK unavailable (%s) — falling back to %s",
                             index, exc, type(self._camera).__name__)
                assert self._camera is not None
                return self._camera
        return self._preview_cameras[index]

    def get_camera_by_role(self, role: str) -> CameraPort:
        from . import config
        from fastapi import HTTPException

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
            try:
                self._optical_train_registry = OpticalTrainRegistry.from_config()
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
