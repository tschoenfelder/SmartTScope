"""Camera scan API — enumerates connected Touptek cameras via the toupcam SDK."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api")

# Stable SDK flag constants (toupcam SDK protocol, will not change).
_FLAG_MONO          = 0x0000_0010
_FLAG_USB30         = 0x0000_0040
_FLAG_TEC           = 0x0000_0080
_FLAG_RAW16         = 0x0000_8000
_FLAG_FAN           = 0x0001_0000
_FLAG_TEC_ONOFF     = 0x0002_0000


class CameraInfo(BaseModel):
    display_name: str
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


@router.get("/cameras", response_model=CameraScanResult)
def scan_cameras() -> CameraScanResult:
    try:
        import toupcam  # type: ignore[import]
    except ImportError:
        return CameraScanResult(sdk_available=False, cameras=[])

    cameras: list[CameraInfo] = []
    for dev in toupcam.Toupcam.EnumV2():
        model = dev.model
        flag: int = int(model.flag)
        resolutions = [(int(r.width), int(r.height)) for r in model.res]
        cameras.append(
            CameraInfo(
                display_name=str(dev.displayname),
                id=str(dev.id),
                model_name=str(model.name),
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
