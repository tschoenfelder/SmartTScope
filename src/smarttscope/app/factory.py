from __future__ import annotations
from typing import Literal
from ..domain.ports import Camera

Adapter = Literal["mock", "opencv", "picamera2"]

def make_camera(adapter: Adapter = "mock") -> Camera:
    if adapter == "mock":
        from ..adapters.camera_mock import MockCamera
        return MockCamera(fps=60, size=(480, 640, 3))
    if adapter == "opencv":
        from ..adapters.camera_opencv import OpenCVCamera
        return OpenCVCamera(index=0, fps=60)
    if adapter == "picamera2":
        from ..adapters.camera_picamera2 import Picamera2Camera
        return Picamera2Camera(index=0, size=(1280, 720))
    raise ValueError(f"Unknown camera adapter: {adapter}")
