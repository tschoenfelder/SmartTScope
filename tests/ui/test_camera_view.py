import pytest
from PySide6.QtWidgets import QApplication, QLabel
from smarttscope.adapters.camera_mock import MockCamera
from smarttscope.ui.widgets import CameraView

@pytest.mark.qt
def test_camera_view_shows_frame(qtbot):
    cam = MockCamera(fps=120)
    w = CameraView(cam)
    qtbot.addWidget(w)
    w.show()
    # wait until a pixmap is set on the label
    def has_pixmap():
        lbl = w.findChild(type(w._label))
        return (lbl is not None) and (lbl.pixmap() is not None)
    qtbot.waitUntil(has_pixmap, timeout=3000)
    # Bonus: FPS-Label aktualisiert?
    assert "FPS:" in w.findChildren(QLabel)[-1].text()

    cam.stop()

    w.close()
    qtbot.wait(50)  # etwas Luft fürs Stoppen
