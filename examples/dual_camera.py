from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
import sys, os
from smarttscope.app.factory import make_camera, make_camera_b
from smarttscope.ui.widgets import CameraView

def main():
##    print("A:", os.getenv("SMARTTSCOPE_CAMERA_INDEX"))
##    print("B:", os.getenv("SMARTTSCOPE_CAMERA_B_INDEX"))
    
    app = QApplication(sys.argv)
    idx_a = int(os.getenv("SMARTTSCOPE_CAMERA_INDEX", "0"))   # 0 = imx290 bei dir
    idx_b = int(os.getenv("SMARTTSCOPE_CAMERA_B_INDEX", "1")) # 1 = imx477
    cam_a = make_camera(index=idx_a)     # <— kein Name übergeben!
    cam_b = make_camera_b()              # <— holt Index/Adapter aus ENV/Profil
    
    w = QWidget(); layout = QHBoxLayout(w)
    layout.addWidget(CameraView(cam_a, crosshair_color="#2ecc71"))
    layout.addWidget(CameraView(cam_b, bg_color="red", crosshair_color="#2ecc71"))
    w.setWindowTitle("SmartTScope — Dual Camera")
    w.resize(1100, 600)
    w.show()
    sys.exit(app.exec())
    
if __name__ == "__main__":
    main()
