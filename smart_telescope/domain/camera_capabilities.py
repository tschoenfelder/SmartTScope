"""Camera capability model — hardware-independent description of a camera's limits."""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ConversionGain(IntEnum):
    LCG = 0
    HCG = 1
    HDR = 2


@dataclass(frozen=True)
class CameraCapabilities:
    min_gain: int
    max_gain: int
    min_exposure_ms: float
    max_exposure_ms: float
    supports_cooling: bool
    supports_hcg: bool
    supports_lcg: bool
    supports_hdr: bool
    supports_black_level: bool
    bit_depth: int
    pixel_size_um: float
    sensor_width_px: int
    sensor_height_px: int
