"""Camera scan API — enumerates connected Touptek cameras via the toupcam SDK."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel

from . import deps

router = APIRouter(prefix="/api")

# Stable SDK flag constants (toupcam SDK protocol, will not change).
_FLAG_MONO          = 0x0000_0010
_FLAG_USB30         = 0x0000_0040
_FLAG_TEC           = 0x0000_0080
_FLAG_RAW16         = 0x0000_8000
_FLAG_FAN           = 0x0001_0000
_FLAG_TEC_ONOFF     = 0x0002_0000


class CameraInfo(BaseModel):
    display_label: str          # user-facing name; disambiguated when two cameras share a model
    sdk_index: int              # zero-based index into EnumV2() / used as camera_index
    display_name: str           # raw SDK displayname
    id: str
    model_name: str
    pixel_size_um: tuple[float, float]
    resolutions: list[tuple[int, int]]
    preview_count: int
    still_count: int
    max_speed: int
    has_tec: bool
    has_fan: bool
    usb3: bool
    has_raw16: bool
    has_mono: bool


class CameraScanResult(BaseModel):
    sdk_available: bool
    cameras: list[CameraInfo]


class CameraCapabilitiesResponse(BaseModel):
    min_gain: int
    max_gain: int
    min_exposure_s: float
    max_exposure_s: float
    bit_depth: int
    sensor_width_px: int
    sensor_height_px: int
    pixel_size_um: float


@router.get("/cameras", response_model=CameraScanResult)
def scan_cameras() -> CameraScanResult:
    try:
        import toupcam
    except ImportError:
        return CameraScanResult(sdk_available=False, cameras=[])

    raw: list[tuple[int, object]] = list(enumerate(toupcam.Toupcam.EnumV2()))

    # Count how many cameras share each model name for disambiguation
    from collections import Counter
    model_counts: Counter[str] = Counter(str(dev.model.name) for _, dev in raw)
    model_seen: dict[str, int] = {}

    cameras: list[CameraInfo] = []
    for i, dev in raw:
        model = dev.model
        model_name = str(model.name)
        flag: int = int(model.flag)
        resolutions = [(int(r.width), int(r.height)) for r in model.res]

        if model_counts[model_name] > 1:
            model_seen[model_name] = model_seen.get(model_name, 0) + 1
            display_label = f"{model_name} ({model_seen[model_name]})"
        else:
            display_label = model_name

        cameras.append(
            CameraInfo(
                display_label=display_label,
                sdk_index=i,
                display_name=str(dev.displayname),
                id=str(dev.id),
                model_name=model_name,
                pixel_size_um=(float(model.xpixsz), float(model.ypixsz)),
                resolutions=resolutions,
                preview_count=int(model.preview),
                still_count=int(model.still),
                max_speed=int(model.maxspeed),
                has_tec=bool(flag & (_FLAG_TEC | _FLAG_TEC_ONOFF)),
                has_fan=bool(flag & _FLAG_FAN),
                usb3=bool(flag & _FLAG_USB30),
                has_raw16=bool(flag & _FLAG_RAW16),
                has_mono=bool(flag & _FLAG_MONO),
            )
        )

    return CameraScanResult(sdk_available=True, cameras=cameras)


@router.get("/cameras/{index}/capabilities", response_model=CameraCapabilitiesResponse)
def camera_capabilities(index: int = Path(ge=0, le=7)) -> CameraCapabilitiesResponse:
    """Return live camera capabilities (gain range, exposure range, sensor info).

    Opens or reuses a camera handle at *index*. Falls back to MockCamera when
    the toupcam SDK is not installed.
    """
    try:
        camera = deps.get_preview_camera(index)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    caps = camera.get_capabilities()
    return CameraCapabilitiesResponse(
        min_gain=caps.min_gain,
        max_gain=caps.max_gain,
        min_exposure_s=caps.min_exposure_ms / 1000.0,
        max_exposure_s=caps.max_exposure_ms / 1000.0,
        bit_depth=caps.bit_depth,
        sensor_width_px=caps.sensor_width_px,
        sensor_height_px=caps.sensor_height_px,
        pixel_size_um=caps.pixel_size_um,
    )
