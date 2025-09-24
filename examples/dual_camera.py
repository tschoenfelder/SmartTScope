from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
import sys, os
from smarttscope.app.factory import make_camera
from smarttscope.ui.widgets import CameraView

def main():
    print("A:", os.getenv("SMARTTSCOPE_CAMERA_INDEX"))
    print("B:", os.getenv("SMARTTSCOPE_CAMERA_B_INDEX"))
    
    app = QApplication(sys.argv)

    os.environ.setdefault("SMARTTSCOPE_CAMERA", "picamera2")
    os.environ.setdefault("SMARTTSCOPE_CAMERA_B", "picamera2")
    # Indizes getrennt steuerbar
    os.environ.setdefault("SMARTTSCOPE_CAMERA_INDEX", "0")
    os.environ.setdefault("SMARTTSCOPE_CAMERA_B_INDEX", "1")
    # Adapter A
    cam_a = make_camera(os.getenv("SMARTTSCOPE_CAMERA", "mock"))
    # Adapter B -> Index-ENV temporär umbiegen
    prev_idx = os.getenv("SMARTTSCOPE_CAMERA_INDEX")
    os.environ["SMARTTSCOPE_CAMERA_INDEX"] = os.getenv("SMARTTSCOPE_CAMERA_B_INDEX", "1")
    cam_b = make_camera(os.getenv("SMARTTSCOPE_CAMERA_B", "mock"))
    if prev_idx is not None:
        os.environ["SMARTTSCOPE_CAMERA_INDEX"] = prev_idx

    w = QWidget()
    layout = QHBoxLayout(w)
    layout.addWidget(CameraView(cam_a))
    layout.addWidget(CameraView(cam_b))

    w.setWindowTitle("SmartTScope — Dual Camera")
    w.resize(1280, 600)
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
