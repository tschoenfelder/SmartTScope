from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
import sys, os
from smarttscope.app.factory import make_camera
from smarttscope.ui.widgets import CameraView

def main():
    app = QApplication(sys.argv)

    cam_a = make_camera(os.getenv("SMARTTSCOPE_CAMERA", "mock"))
    cam_b = make_camera(os.getenv("SMARTTSCOPE_CAMERA_B", "mock"))

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
