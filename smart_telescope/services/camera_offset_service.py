"""Apply camera-specific black-level (sensor offset) from config."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..ports.camera import CameraPort

from ..domain.camera_capabilities import ConversionGain

_log = logging.getLogger(__name__)


class CameraOffsetService:
    """Look up and apply configured sensor offsets by camera model + gain mode."""

    def __init__(self, offsets: dict[str, dict[str, int]]) -> None:
        # Normalise keys to lowercase for case-insensitive lookup.
        self._offsets = {k.lower(): v for k, v in offsets.items()}

    @classmethod
    def from_config(cls) -> "CameraOffsetService":
        from .. import config
        return cls(config.CAMERA_OFFSETS)

    def get_offset(self, model_name: str, gain_mode: ConversionGain) -> int | None:
        """Return configured offset or None if model/mode not in config."""
        mode_key = gain_mode.name.lower()  # "lcg", "hcg", "hdr"
        name_lower = model_name.lower()
        for config_key, modes in self._offsets.items():
            if config_key in name_lower or name_lower in config_key:
                return modes.get(mode_key)
        return None

    def apply(self, camera: "CameraPort") -> None:
        """Read camera's logical name and gain mode, apply offset if configured."""
        model = camera.get_logical_name()
        gain_mode = camera.get_conversion_gain()
        offset = self.get_offset(model, gain_mode)
        if offset is not None:
            camera.set_black_level(offset)
            _log.info(
                "Camera offset applied: model='%s' gain=%s offset=%d",
                model, gain_mode.name, offset,
            )
        else:
            _log.debug(
                "No configured offset for model='%s' gain=%s — keeping current offset",
                model, gain_mode.name,
            )
