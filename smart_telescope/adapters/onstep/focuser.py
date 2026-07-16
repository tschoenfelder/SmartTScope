"""SmartTScope shim over ``onstep_adapter.focuser`` (see SYNC.md).

All serial/LX200 protocol logic lives in the pip-installed ``onstep_adapter``
package. This shim adds the SmartTScope-specific M7-004 backlash
compensation (config-driven, applied around the upstream ``move_absolute()``)
and one SYNC-OVERRIDE (calibrated-max-position loader, see below).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from onstep_adapter.focuser import OnStepFocuser as _BaseOnStepFocuser

from ...ports.focuser import FocuserMoveResult, FocuserPort
from .safety import OnStepSafetyConfig, OnStepSafetyError
from .serial_bus import OnStepSerialBus

_log = logging.getLogger(__name__)


class OnStepFocuser(_BaseOnStepFocuser, FocuserPort):
    """Upstream OnStep focuser + M7-004 backlash compensation.

    Args:
        bus: OnStepSerialBus instance obtained from OnStepMount.serial_bus.
        backlash_steps: steps to overshoot on direction reversal (0 = disabled).
        backlash_enabled: master switch; overrides backlash_steps when False.
    """

    def __init__(
        self,
        bus: OnStepSerialBus,
        safety_config: OnStepSafetyConfig | None = None,
        backlash_steps: int | None = None,
        backlash_enabled: bool | None = None,
    ) -> None:
        super().__init__(bus, safety_config=safety_config)

        if backlash_enabled is None or backlash_steps is None:
            from ... import config as _cfg
            if backlash_enabled is None:
                backlash_enabled = _cfg.FOCUSER_BACKLASH_ENABLED
            if backlash_steps is None:
                backlash_steps = _cfg.FOCUSER_BACKLASH_STEPS

        # M7-004: backlash compensation
        self._backlash_steps: int = max(0, backlash_steps)
        self._backlash_enabled: bool = backlash_enabled
        self._last_direction: int = 0   # +1 = inward (larger pos), -1 = outward
        if self._backlash_enabled and self._backlash_steps == 0:
            _log.warning(
                "OnStepFocuser: backlash_compensation_enabled=true but backlash_steps=0 "
                "— compensation will have no effect; set [focuser] backlash_steps in config"
            )

    def move_absolute(self, steps: int) -> FocuserMoveResult:
        # M7-004: overshoot on direction reversal, then approach the target
        # from the same side as the previous move. Overshoot rejection is
        # logged, not raised — the final (validated) move decides the outcome.
        if self._backlash_enabled and self._backlash_steps > 0:
            start_position = self.get_position() if self._available else 0
            new_direction = (
                1 if steps > start_position else (-1 if steps < start_position else 0)
            )
            if (
                new_direction != 0
                and self._last_direction != 0
                and new_direction != self._last_direction
            ):
                min_pos = self._safety_config.focuser_min_position
                max_pos = self._max_position or self._safety_config.focuser_max_position
                overshoot = steps - self._backlash_steps * new_direction
                overshoot = max(min_pos, min(max_pos, overshoot))
                _log.info(
                    "OnStepFocuser: backlash reversal detected — overshoot to %d then return to %d",
                    overshoot, steps,
                )
                try:
                    super().move_absolute(overshoot)
                except OnStepSafetyError as exc:
                    _log.warning("OnStepFocuser: backlash overshoot move rejected (%s)", exc)
            if new_direction != 0:
                self._last_direction = new_direction
        return super().move_absolute(steps)

    def _load_calibrated_max_position(self) -> int:
        # SYNC-OVERRIDE: upstream v0.3.1 wheel contains this same method with
        # `from ... import config`, a relative import that climbs above the
        # top-level `onstep_adapter` package — it always raises and the
        # calibrated max position is silently never loaded. This copy of the
        # pre-migration SmartTScope implementation resolves the intended
        # target (`smart_telescope.config`) explicitly. Remove once upstream
        # ships a fixed loader (see SYNC.md "Pending upstream requests").
        try:
            from ... import config

            base = (
                Path(config.APP_STATE_DIR).expanduser()
                if config.APP_STATE_DIR
                else Path.home() / ".SmartTScope"
            )
            path = base / "onstep_focuser_calibration.json"
            if not path.exists():
                return 0
            data = json.loads(path.read_text(encoding="utf-8"))
            return int(data.get("max_position") or 0)
        except Exception:
            return 0
