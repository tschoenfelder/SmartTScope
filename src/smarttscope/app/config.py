from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Optional
import os, yaml

@dataclass
class AppConfig:
    camera_adapter: str = "mock"  # mock | opencv | picamera2
    window_width: int = 900
    window_height: int = 600

def load_config(path: Optional[str] = None) -> AppConfig:
    cfg = AppConfig()
    file_path = path or os.getenv("SMARTTSCOPE_CONFIG")
    if file_path and os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}
        app = data.get("app", {})
        adapters = data.get("adapters", {})
        cfg.window_width = int(app.get("window", {}).get("width", cfg.window_width))
        cfg.window_height = int(app.get("window", {}).get("height", cfg.window_height))
        cfg.camera_adapter = str(adapters.get("camera", cfg.camera_adapter))
    # ENV override
    cfg.camera_adapter = os.getenv("SMARTTSCOPE_CAMERA", cfg.camera_adapter)
    return cfg
