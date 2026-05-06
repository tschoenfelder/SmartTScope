"""FastAPI dependency providers for camera, mount, and focuser ports.

Adapter selection priority (highest first):

  Camera:
    TOUPTEK_INDEX set  → ToupcamCamera(index=int(TOUPTEK_INDEX))
    SIMULATOR_FITS_DIR → SimulatorCamera
    REPLAY_FITS_DIR    → ReplayCamera.from_directory (deterministic test frames)
    (neither)          → MockCamera (unit-test default)

  Mount + Focuser:
    ONSTEP_PORT set    → OnStepMount + OnStepFocuser (real hardware)
    SIMULATOR_FITS_DIR → SimulatorMount + SimulatorFocuser
    (neither)          → MockMount + MockFocuser (unit-test default)
"""

from __future__ import annotations

import os

from .. import config
from ..adapters.mock.camera import MockCamera
from ..adapters.mock.focuser import MockFocuser
from ..adapters.mock.mount import MockMount
from ..adapters.mock.solver import MockSolver
from ..adapters.mock.stacker import MockStacker
from ..adapters.mock.storage import MockStorage
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..ports.solver import SolverPort
from ..ports.stacker import StackerPort
from ..ports.storage import StoragePort

_camera: CameraPort | None = None
_mount: MountPort | None = None
_focuser: FocuserPort | None = None
_stacker: StackerPort | None = None
_storage: StoragePort | None = None
_solver: SolverPort | None = None
_adapters_built: bool = False
_preview_cameras: dict[int, CameraPort] = {}


def _build_adapters() -> tuple[CameraPort, MountPort, FocuserPort]:
    # env vars take priority over the TOML config file
    touptek_index = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
    onstep_port   = os.environ.get("ONSTEP_PORT")   or config.ONSTEP_PORT
    sim_dir       = os.environ.get("SIMULATOR_FITS_DIR", "")

    replay_dir = os.environ.get("REPLAY_FITS_DIR", "")

    # Camera — selected independently of mount
    camera: CameraPort
    if touptek_index:
        from ..adapters.touptek.camera import ToupcamCamera
        camera = ToupcamCamera(index=int(touptek_index))
    elif sim_dir:
        from pathlib import Path

        from ..adapters.simulator.camera import SimulatorCamera
        camera = SimulatorCamera(Path(sim_dir))
    elif replay_dir:
        from ..adapters.replay.camera import ReplayCamera
        camera = ReplayCamera.from_directory(replay_dir)
    else:
        camera = MockCamera()

    # Mount + Focuser
    if onstep_port:
        import logging
        from ..adapters.onstep.focuser import OnStepFocuser
        from ..adapters.onstep.mount import OnStepMount
        mount = OnStepMount(onstep_port)
        focuser = OnStepFocuser(mount)
        focuser.connect()
        if not focuser.is_available:
            logging.getLogger(__name__).error(
                "OnStep focuser not found (:FA# returned 0). "
                "Check focuser wiring and OnStep focuser configuration."
            )
        return camera, mount, focuser
    if sim_dir:
        from pathlib import Path

        from ..adapters.simulator.focuser import SimulatorFocuser
        from ..adapters.simulator.mount import SimulatorMount
        return camera, SimulatorMount(), SimulatorFocuser()
    return camera, MockMount(), MockFocuser()


def _ensure_adapters() -> None:
    global _camera, _mount, _focuser, _adapters_built
    if not _adapters_built:
        _camera, _mount, _focuser = _build_adapters()
        _adapters_built = True


def get_camera() -> CameraPort:
    _ensure_adapters()
    assert _camera is not None
    return _camera


def get_preview_camera(index: int) -> CameraPort:
    """Return a camera for live preview at the given SDK index.

    When TOUPTEK_INDEX is configured, index == main_index returns the primary
    singleton; other indices open a separate ToupcamCamera handle and cache it.

    When TOUPTEK_INDEX is NOT configured (empty TOML / no env var), we still
    try to open a real ToupcamCamera at *index* so that cameras connected on
    the Pi are accessible even without an explicit config.  Falls back to the
    primary singleton (MockCamera in dev) only if the SDK is unavailable or
    no camera exists at that index.
    """
    _ensure_adapters()
    touptek_env = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX

    if touptek_env:
        # Explicit TOUPTEK_INDEX configured
        main_index = int(touptek_env)
        if index == main_index:
            assert _camera is not None
            return _camera
        # Secondary camera — open a dedicated handle
        if index not in _preview_cameras:
            from ..adapters.touptek.camera import ToupcamCamera
            cam = ToupcamCamera(index=index)
            if not cam.connect():
                raise RuntimeError(f"Camera {index} failed to connect")
            _preview_cameras[index] = cam
        return _preview_cameras[index]

    # TOUPTEK_INDEX not configured — attempt SDK auto-detection by index
    if index not in _preview_cameras:
        try:
            from ..adapters.touptek.camera import ToupcamCamera
            cam = ToupcamCamera(index=index)
            if not cam.connect():
                # SDK not installed or no camera at this index
                raise RuntimeError(f"Camera {index}: SDK unavailable or connect() returned False")
            _preview_cameras[index] = cam
        except (ImportError, RuntimeError):
            # Fall back to primary adapter (MockCamera in dev / test environments)
            assert _camera is not None
            return _camera
    return _preview_cameras[index]


def get_mount() -> MountPort:
    _ensure_adapters()
    assert _mount is not None
    return _mount


def get_focuser() -> FocuserPort:
    _ensure_adapters()
    assert _focuser is not None
    return _focuser


def get_stacker() -> StackerPort:
    global _stacker
    if _stacker is None:
        try:
            from ..adapters.numpy_stacker.stacker import NumpyStacker
            _stacker = NumpyStacker()
        except ImportError:
            _stacker = MockStacker()
    return _stacker


def make_stacker() -> StackerPort:
    """Create a fresh stacker instance — used by the queue runner (one per session)."""
    try:
        from ..adapters.numpy_stacker.stacker import NumpyStacker
        return NumpyStacker()
    except ImportError:
        return MockStacker()


def get_solver() -> SolverPort:
    global _solver
    if _solver is None:
        astap_path = os.environ.get("ASTAP_PATH") or config.ASTAP_PATH
        catalog_dir = os.environ.get("ASTAP_CATALOG_DIR") or config.ASTAP_CATALOG_DIR
        try:
            from ..adapters.astap.solver import AstapSolver, find_astap
            path = astap_path or find_astap()
            _solver = AstapSolver(astap_path=path, catalog_dir=catalog_dir or None) if path else MockSolver()
        except Exception:
            _solver = MockSolver()
    return _solver


def get_storage() -> StoragePort:
    global _storage
    if _storage is None:
        storage_dir = config.STORAGE_DIR  # config already applies env-var override for this one
        if storage_dir:
            from pathlib import Path

            from ..adapters.disk_storage.storage import DiskStorage
            _storage = DiskStorage(Path(storage_dir))
        else:
            _storage = MockStorage()
    return _storage


def reset() -> None:
    """Reset cached singletons (used in tests)."""
    global _camera, _mount, _focuser, _stacker, _storage, _solver, _adapters_built, _preview_cameras
    _camera = None
    _mount = None
    _focuser = None
    _stacker = None
    _storage = None
    _solver = None
    _adapters_built = False
    _preview_cameras = {}
