import os, sys, importlib.util
from typing import Any
from ..adapters import REGISTRY

def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None

def _is_rpi() -> bool:
    return sys.platform.startswith("linux") and _has_module("picamera2")

def _profile() -> str:
    p = os.getenv("SMARTTSCOPE_PROFILE", "auto").lower()
    if p == "auto":
        return "rpi" if _is_rpi() else "win-mock"
    return p

def make_camera(which: str|None=None, index: int|None=None, size=(1280,720)) -> Any:
    prof = _profile()
    cam_name = which or os.getenv("SMARTTSCOPE_CAMERA")
    if not cam_name:
        # auf RPi nur 'picamera2' wählen, wenn es auch wirklich importierbar ist
        if prof == "rpi" and "picamera2" in REGISTRY["camera"]:
            cam_name = "picamera2"
        else:
            cam_name = "mock"

    cls = REGISTRY["camera"].get(cam_name)
    if cls is None:
        available = ", ".join(REGISTRY["camera"].keys())
        raise ValueError(f"unknown camera adapter '{cam_name}'. Available: {available}")

    if index is None:
        index = int(os.getenv(
            "SMARTTSCOPE_CAMERA_INDEX",
            "0" if cam_name != "mock" else "0"
        ))
    try:
        return cls(index=index, size=size, name=f"{cam_name.upper()}-{index}")
    except TypeError:
        return cls()  # z.B. Mock ohne Args

def make_camera_b() -> Any:
    prof = _profile()
    cam_b = os.getenv("SMARTTSCOPE_CAMERA_B")
    if not cam_b:
        cam_b = "picamera2" if (prof == "rpi" and "picamera2" in REGISTRY["camera"]) else "mock"
    idx = int(os.getenv("SMARTTSCOPE_CAMERA_B_INDEX", "1" if cam_b == "picamera2" else "0"))
    return make_camera(which=cam_b, index=idx)
