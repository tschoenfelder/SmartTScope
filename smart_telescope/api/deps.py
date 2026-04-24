"""FastAPI dependency providers for camera, mount, and focuser ports.

By default returns mock adapters so the UI works without hardware.
Set ONSTEP_PORT (e.g. /dev/ttyUSB_ONSTEP0) to use real OnStep hardware.
"""

from __future__ import annotations

import os

from ..adapters.mock.camera import MockCamera
from ..adapters.mock.focuser import MockFocuser
from ..adapters.mock.mount import MockMount
from ..ports.camera import CameraPort
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort

_camera: CameraPort | None = None
_mount: MountPort | None = None
_focuser: FocuserPort | None = None


def _build_adapters() -> tuple[CameraPort, MountPort, FocuserPort]:
    port = os.environ.get("ONSTEP_PORT", "")
    if port:
        from ..adapters.onstep.focuser import OnStepFocuser
        from ..adapters.onstep.mount import OnStepMount
        return MockCamera(), OnStepMount(port), OnStepFocuser(port)
    return MockCamera(), MockMount(), MockFocuser()


def get_camera() -> CameraPort:
    global _camera
    if _camera is None:
        _camera, _, _ = _build_adapters()
    return _camera


def get_mount() -> MountPort:
    global _mount
    if _mount is None:
        _, _mount, _ = _build_adapters()
    return _mount


def get_focuser() -> FocuserPort:
    global _focuser
    if _focuser is None:
        _, _, _focuser = _build_adapters()
    return _focuser


def reset() -> None:
    """Reset cached singletons (used in tests)."""
    global _camera, _mount, _focuser
    _camera = None
    _mount = None
    _focuser = None
