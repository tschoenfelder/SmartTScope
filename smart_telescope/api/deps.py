"""FastAPI dependency providers for camera, mount, and focuser ports.

Adapter selection priority (highest first):

  Camera:
    TOUPTEK_INDEX set  → ToupcamCamera(index=int(TOUPTEK_INDEX))
    SIMULATOR_FITS_DIR → SimulatorCamera
    (neither)          → MockCamera (unit-test default)

  Mount + Focuser:
    ONSTEP_PORT set    → OnStepMount + OnStepFocuser (real hardware)
    SIMULATOR_FITS_DIR → SimulatorMount + SimulatorFocuser
    (neither)          → MockMount + MockFocuser (unit-test default)
"""

from __future__ import annotations

import os

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
    touptek_index = os.environ.get("TOUPTEK_INDEX", "")
    onstep_port   = os.environ.get("ONSTEP_PORT", "")
    sim_dir       = os.environ.get("SIMULATOR_FITS_DIR", "")

    # Camera — selected independently of mount
    camera: CameraPort
    if touptek_index:
        from ..adapters.touptek.camera import ToupcamCamera
        camera = ToupcamCamera(index=int(touptek_index))
        camera.connect()
    elif sim_dir:
        from pathlib import Path

        from ..adapters.simulator.camera import SimulatorCamera
        camera = SimulatorCamera(Path(sim_dir))
    else:
        camera = MockCamera()

    # Mount + Focuser
    if onstep_port:
        from ..adapters.onstep.focuser import OnStepFocuser
        from ..adapters.onstep.mount import OnStepMount
        mount = OnStepMount(onstep_port)
        focuser = OnStepFocuser(mount)
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

    Index 0 (or any index when TOUPTEK_INDEX is not set) shares the primary
    camera singleton.  Additional indices open a separate ToupcamCamera and
    cache it so the WS reconnect path doesn't create a new handle every time.
    """
    _ensure_adapters()
    touptek_env = os.environ.get("TOUPTEK_INDEX", "")
    main_index = int(touptek_env) if touptek_env else 0
    if index == main_index or not touptek_env:
        assert _camera is not None
        return _camera
    if index not in _preview_cameras:
        from ..adapters.touptek.camera import ToupcamCamera
        cam = ToupcamCamera(index=index)
        if not cam.connect():
            raise RuntimeError(f"Camera {index} failed to connect")
        _preview_cameras[index] = cam
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
        astap_path_env = os.environ.get("ASTAP_PATH", "")
        try:
            from ..adapters.astap.solver import AstapSolver, find_astap
            path = astap_path_env or find_astap()
            _solver = AstapSolver(astap_path=path) if path else MockSolver()
        except Exception:
            _solver = MockSolver()
    return _solver


def get_storage() -> StoragePort:
    global _storage
    if _storage is None:
        storage_dir = os.environ.get("STORAGE_DIR", "")
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
