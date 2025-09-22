import sys, logging
from PySide6.QtWidgets import QApplication
from .config import load_config
from .logging import setup_logging
from .factory import make_camera
from ..ui.widgets import CameraView

def main() -> None:
    setup_logging()
    cfg = load_config()
    logging.getLogger(__name__).info("Starting SmartTScope with camera adapter=%s", cfg.camera_adapter)

    app = QApplication(sys.argv)
    cam = make_camera(cfg.camera_adapter)  # mock/opencv/picamera2
    view = CameraView(cam)
    view.setWindowTitle("SmartTScope — Camera")
    view.resize(cfg.window_width, cfg.window_height)
    view.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
