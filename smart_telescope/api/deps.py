"""FastAPI dependency providers for mount and focuser ports.

By default, returns mock adapters so the UI works without hardware.
Set ONSTEP_PORT env var (e.g. /dev/ttyUSB_ONSTEP0) to use real hardware.
"""

from __future__ import annotations

import os

from ..adapters.mock.focuser import MockFocuser
from ..adapters.mock.mount import MockMount
from ..ports.focuser import FocuserPort
from ..ports.mount import MountPort

_mount: MountPort | None = None
_focuser: FocuserPort | None = None


def _build_adapters() -> tuple[MountPort, FocuserPort]:
    port = os.environ.get("ONSTEP_PORT", "")
    if port:
        from ..adapters.onstep.focuser import OnStepFocuser
        from ..adapters.onstep.mount import OnStepMount
        return OnStepMount(port), OnStepFocuser(port)
    return MockMount(), MockFocuser()


def get_mount() -> MountPort:
    global _mount
    if _mount is None:
        _mount, _ = _build_adapters()
    return _mount


def get_focuser() -> FocuserPort:
    global _focuser
    if _focuser is None:
        _, _focuser = _build_adapters()
    return _focuser


def reset() -> None:
    """Reset cached singletons (used in tests)."""
    global _mount, _focuser
    _mount = None
    _focuser = None
