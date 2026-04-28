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
from ..adapters.mock.stacker import MockStacker
from ..adapters.mock.storage import MockStorage
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort
from ..ports.stacker import StackerPort
from ..ports.storage import StoragePort

_camera: CameraPort | None = None
_mount: MountPort | None = None
_focuser: FocuserPort | None = None
_stacker: StackerPort | None = None
_storage: StoragePort | None = None
_adapters_built: bool = False


def _build_adapters() -> tuple[CameraPort, MountPort, FocuserPort]:
    touptek_index = os.environ.get("TOUPTEK_INDEX", "")
    onstep_port   = os.environ.get("ONSTEP_PORT", "")
    sim_dir       = os.environ.get("SIMULATOR_FITS_DIR", "")

    # Camera — selected independently of mount
    camera: CameraPort
    if touptek_index:
        from ..adapters.touptek.camera import ToupcamCamera
        camera = ToupcamCamera(index=int(touptek_index))
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
        return camera, OnStepMount(onstep_port), OnStepFocuser(onstep_port)
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
    global _camera, _mount, _focuser, _stacker, _storage, _adapters_built
    _camera = None
    _mount = None
    _focuser = None
    _stacker = None
    _storage = None
    _adapters_built = False
