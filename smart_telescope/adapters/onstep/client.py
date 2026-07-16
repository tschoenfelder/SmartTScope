"""SmartTScope shim over ``onstep_adapter.client`` (see SYNC.md).

ONS31-105: upstream ``OnStepClient.__init__`` hard-instantiates its own
``OnStepMount``/``OnStepFocuser`` with no injection point, so this shim lets
the upstream constructor run and then swaps in the SmartTScope subclasses on
the same shared serial bus. Safe: no serial I/O happens before ``connect()``.
An upstream ``mount_cls``/factory parameter would remove this workaround —
candidate change request, tracked in SYNC.md.
"""
from __future__ import annotations

from onstep_adapter.client import OnStepClient as _BaseOnStepClient
from onstep_adapter.results import OnStepMotionCalibration

from .focuser import OnStepFocuser
from .mount import OnStepMount
from .safety import OnStepSafetyConfig
from .serial_bus import OnStepSerialBus


class OnStepClient(_BaseOnStepClient):
    """Own one serial bus and expose SmartTScope's mount and focuser shims."""

    def __init__(
        self,
        port: str,
        *,
        baud_rate: int = 9600,
        timeout: float = 2.0,
        safety_config: OnStepSafetyConfig | None = None,
        motion_calibration: OnStepMotionCalibration | None = None,
        serial_bus: OnStepSerialBus | None = None,
    ) -> None:
        super().__init__(
            port,
            baud_rate=baud_rate,
            timeout=timeout,
            safety_config=safety_config,
            motion_calibration=motion_calibration,
            serial_bus=serial_bus,
        )
        # Swap in the SmartTScope shims on the same bus (see module docstring).
        self.mount = OnStepMount(
            port,
            baud_rate=baud_rate,
            timeout=timeout,
            safety_config=safety_config,
            motion_calibration=motion_calibration,
            serial_bus=self._bus,
        )
        self.focuser = OnStepFocuser(
            self._bus,
            safety_config=self.mount.safety_config,
        )
