from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
import sys, os
from smarttscope.app.factory import make_camera
from smarttscope.ui.widgets import CameraView

def main():
##    print("A:", os.getenv("SMARTTSCOPE_CAMERA_INDEX"))
##    print("B:", os.getenv("SMARTTSCOPE_CAMERA_B_INDEX"))
    
    app = QApplication(sys.argv)
    idx_a = int(os.getenv("SMARTTSCOPE_CAMERA_INDEX", "0"))   # 0 = imx290 bei dir
    idx_b = int(os.getenv("SMARTTSCOPE_CAMERA_B_INDEX", "1")) # 1 = imx477
    cam_a = make_camera(os.getenv("SMARTTSCOPE_CAMERA", "picamera2"), index=idx_a)
    cam_b = make_camera(os.getenv("SMARTTSCOPE_CAMERA_B", "picamera2"), index=idx_b)

    w = QWidget(); layout = QHBoxLayout(w)
    layout.addWidget(CameraView(cam_a))
    layout.addWidget(CameraView(cam_b))
    w.setWindowTitle("SmartTScope — Dual Camera"); w.resize(1280, 640); w.show()
    sys.exit(app.exec())
    
if __name__ == "__main__":
    main()
