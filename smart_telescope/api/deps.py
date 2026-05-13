"""FastAPI dependency providers for camera, mount, and focuser ports.

Adapter selection priority (highest first):

  Camera:
    [cameras] main configured  → ToupcamCamera(index=CAMERAS["main"])
    TOUPTEK_INDEX env var       → ToupcamCamera(index=int(TOUPTEK_INDEX))  (legacy)
    SIMULATOR_FITS_DIR          → SimulatorCamera
    REPLAY_FITS_DIR             → ReplayCamera.from_directory
    (none of the above)         → MockCamera (unit-test default)

  Named camera roles (config [cameras] section):
    main  — primary imaging camera at the C8
    guide — guide camera on the 180×50 guide scope
    atr   — ATR585M at the C8 (optional; when present, main/678M acts as OAG)

  Mount + Focuser:
    ONSTEP_PORT set    → OnStepMount + OnStepFocuser (real hardware)
    SIMULATOR_FITS_DIR → SimulatorMount + SimulatorFocuser
    (neither)          → MockMount + MockFocuser (unit-test default)
"""

from __future__ import annotations

import logging
import os

_log = logging.getLogger(__name__)

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
    # TOUPTEK_INDEX env var is a legacy override for the "main" camera index.
    main_index_str = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
    onstep_port    = os.environ.get("ONSTEP_PORT")   or config.ONSTEP_PORT
    sim_dir        = os.environ.get("SIMULATOR_FITS_DIR", "")
    replay_dir     = os.environ.get("REPLAY_FITS_DIR", "")

    # Camera — selected independently of mount
    camera: CameraPort
    if main_index_str:
        from ..adapters.touptek.camera import ToupcamCamera
        camera = ToupcamCamera(index=int(main_index_str))
        role_label = "TOUPTEK_INDEX env" if os.environ.get("TOUPTEK_INDEX") else "[cameras] main"
        _log.warning("Adapter selected: ToupcamCamera(index=%s)  [%s]", main_index_str, role_label)
    elif sim_dir:
        from pathlib import Path

        from ..adapters.simulator.camera import SimulatorCamera
        camera = SimulatorCamera(Path(sim_dir))
        _log.warning("Adapter selected: SimulatorCamera(dir=%s)", sim_dir)
    elif replay_dir:
        from ..adapters.replay.camera import ReplayCamera
        camera = ReplayCamera.from_directory(replay_dir)
        _log.warning("Adapter selected: ReplayCamera(dir=%s)", replay_dir)
    else:
        _log.warning("Adapter selected: MockCamera  — no TOUPTEK_INDEX, SIMULATOR_FITS_DIR or REPLAY_FITS_DIR set")
        camera = MockCamera()

    # Mount + Focuser
    if onstep_port:
        from ..adapters.onstep.focuser import OnStepFocuser
        from ..adapters.onstep.mount import OnStepMount
        _log.info("Adapter selected: OnStepMount+OnStepFocuser on port %s", onstep_port)
        mount = OnStepMount(onstep_port)
        if not mount.connect():
            _log.error("OnStepMount.connect() failed on port %s — mount will be unavailable", onstep_port)
        else:
            _log.info("OnStepMount: connected on %s — REAL HARDWARE", onstep_port)
        focuser = OnStepFocuser(mount)
        focuser.connect()
        _log.info(
            "OnStepFocuser: connected, available=%s — %s",
            focuser.is_available,
            "REAL HARDWARE" if focuser.is_available else "focuser not available (check wiring)",
        )
        return camera, mount, focuser
    if sim_dir:
        from pathlib import Path

        from ..adapters.simulator.focuser import SimulatorFocuser
        from ..adapters.simulator.mount import SimulatorMount
        _log.info("Adapter selected: SimulatorMount+SimulatorFocuser (SIMULATOR_FITS_DIR=%s)", sim_dir)
        return camera, SimulatorMount(), SimulatorFocuser()
    _log.warning(
        "Adapter selected: MockMount+MockFocuser — no ONSTEP_PORT or SIMULATOR_FITS_DIR set"
    )
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
    """Return a camera for live preview/capture at the given SDK index.

    If *index* matches the configured main camera it returns the primary
    singleton.  All other indices open a dedicated ToupcamCamera handle and
    cache it.  When no cameras are configured at all, auto-detect via SDK.
    """
    _ensure_adapters()
    main_index_str = os.environ.get("TOUPTEK_INDEX") or config.TOUPTEK_INDEX
    _log.info(
        "get_preview_camera(%d): main_index=%r cached=%s primary=%s",
        index,
        int(main_index_str) if main_index_str else None,
        list(_preview_cameras.keys()),
        type(_camera).__name__,
    )

    if main_index_str:
        main_index = int(main_index_str)
        if index == main_index:
            _log.info("get_preview_camera(%d): returning primary camera (%s)", index, type(_camera).__name__)
            assert _camera is not None
            return _camera
        # Secondary camera (guide / atr / ...) — open a dedicated handle
        if index not in _preview_cameras:
            _log.info("get_preview_camera(%d): opening secondary ToupcamCamera", index)
            from ..adapters.touptek.camera import ToupcamCamera
            cam = ToupcamCamera(index=index)
            if not cam.connect():
                raise RuntimeError(f"Camera {index} failed to connect")
            _preview_cameras[index] = cam
            _log.info("get_preview_camera(%d): connected → %s", index, cam.get_logical_name())
        return _preview_cameras[index]

    # No cameras configured — attempt SDK auto-detection by index
    if index not in _preview_cameras:
        _log.info("get_preview_camera(%d): no [cameras] config — trying SDK auto-detect", index)
        try:
            from ..adapters.touptek.camera import ToupcamCamera
            cam = ToupcamCamera(index=index)
            if not cam.connect():
                raise RuntimeError(f"Camera {index}: connect() returned False")
            _preview_cameras[index] = cam
            _log.info("get_preview_camera(%d): auto-detect connected → %s", index, cam.get_logical_name())
        except (ImportError, RuntimeError) as exc:
            _log.warning("get_preview_camera(%d): SDK unavailable (%s) — falling back to %s",
                         index, exc, type(_camera).__name__)
            assert _camera is not None
            return _camera
    return _preview_cameras[index]


def get_camera_by_role(role: str) -> CameraPort:
    """Return the camera configured under *role* in [cameras].

    Raises RuntimeError if the role is not defined in config.
    """
    from fastapi import HTTPException
    if role not in config.CAMERAS:
        configured = list(config.CAMERAS.keys()) or ["(none)"]
        raise HTTPException(
            status_code=503,
            detail=f"Camera role '{role}' not configured. Configured roles: {', '.join(configured)}. "
                   f"Add it to [cameras] in smart_telescope.toml.",
        )
    return get_preview_camera(config.CAMERAS[role])


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
