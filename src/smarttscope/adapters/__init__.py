from .camera_mock import MockCamera

# optional / nur wenn installiert:
try:
    from .camera_picamera2 import Picamera2Camera  # benötigt 'picamera2'
except Exception:
    Picamera2Camera = None  # type: ignore

try:
    from .camera_opencv import OpenCVCamera  # benötigt 'opencv-python'
except Exception:
    OpenCVCamera = None  # type: ignore

from .gps_mock import GPSMock
from .telescope_mock import TelescopeMock

REGISTRY = {
    "camera": {
        "mock": MockCamera,
    },
    "gps": {
        "mock": GPSMock,
    },
    "telescope": {
        "mock": TelescopeMock,
    },
}

# nur hinzufügen, wenn verfügbar
if Picamera2Camera is not None:
    REGISTRY["camera"]["picamera2"] = Picamera2Camera

if OpenCVCamera is not None:
    REGISTRY["camera"]["opencv"] = OpenCVCamera
