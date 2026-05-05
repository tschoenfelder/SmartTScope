from dataclasses import replace
from pathlib import Path

from ...domain.camera_capabilities import CameraCapabilities, ConversionGain
from ...domain.frame import FitsFrame
from ...ports.camera import CameraPort

_REPLAY_CAPABILITIES = CameraCapabilities(
    min_gain=100,
    max_gain=3200,
    min_exposure_ms=0.1,
    max_exposure_ms=60_000.0,
    supports_cooling=False,
    supports_hcg=False,
    supports_lcg=False,
    supports_hdr=False,
    supports_black_level=False,
    bit_depth=16,
    pixel_size_um=2.4,
    sensor_width_px=3096,
    sensor_height_px=2080,
)


_FITS_GLOB = ("*.fits", "*.fit")


class ReplayCamera(CameraPort):
    """
    Camera adapter that serves prerecorded FITS files from disk.

    Cycles through the provided list of paths.  Useful for integration
    tests that need real image data without live hardware.
    """

    def __init__(self, fits_paths: list[str]) -> None:
        if not fits_paths:
            raise ValueError("ReplayCamera requires at least one FITS path")
        self._paths = [Path(p) for p in fits_paths]
        self._index = 0

    @classmethod
    def from_directory(cls, dir_path: str | Path) -> "ReplayCamera":
        """Discover all FITS files in *dir_path* (sorted) and create a ReplayCamera."""
        d = Path(dir_path)
        if not d.is_dir():
            raise ValueError(f"ReplayCamera.from_directory: not a directory: {d}")
        seen: set[Path] = set()
        for pattern in _FITS_GLOB:
            seen.update(d.glob(pattern))
        paths = sorted(seen)
        if not paths:
            raise ValueError(f"ReplayCamera.from_directory: no FITS files in {d}")
        return cls([str(p) for p in paths])
        self._exposure_ms: float = 2000.0
        self._gain: int = 100
        self._black_level: int = 0
        self._conversion_gain: ConversionGain = ConversionGain.LCG

    def connect(self) -> bool:
        missing = [p for p in self._paths if not p.exists()]
        return not missing

    def capture(self, exposure_seconds: float) -> FitsFrame:
        path = self._paths[self._index % len(self._paths)]
        self._index += 1
        frame = FitsFrame.from_fits_bytes(path.read_bytes())
        return replace(frame, exposure_seconds=exposure_seconds)

    def disconnect(self) -> None:
        pass

    def get_exposure_ms(self) -> float:
        return self._exposure_ms

    def set_exposure_ms(self, ms: float) -> None:
        self._exposure_ms = max(0.1, ms)

    def get_gain(self) -> int:
        return self._gain

    def set_gain(self, gain: int) -> None:
        self._gain = max(100, gain)

    def get_black_level(self) -> int:
        return self._black_level

    def set_black_level(self, level: int) -> None:
        self._black_level = max(0, level)

    def get_conversion_gain(self) -> ConversionGain:
        return self._conversion_gain

    def set_conversion_gain(self, mode: ConversionGain) -> None:
        self._conversion_gain = mode

    def get_bit_depth(self) -> int:
        return 16

    def get_temperature(self) -> float | None:
        return None

    def get_capabilities(self) -> CameraCapabilities:
        return _REPLAY_CAPABILITIES

    def get_serial_number(self) -> str:
        return ""

    def get_logical_name(self) -> str:
        return "ReplayCamera"
