from __future__ import annotations
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtCore import Qt, QObject, Signal
import numpy as np
from ..domain.ports import Camera, Frame

class _FrameBridge(QObject):
    got = Signal(object)  # numpy array

class CameraView(QWidget):
    def __init__(self, cam: Camera):
        super().__init__()
        self._cam = cam
        self._label = QLabel("Waiting for frames…")
        self._label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        self._bridge = _FrameBridge()
        self._bridge.got.connect(self._on_frame)

        self._cam.subscribe(self._on_frame_threadsafe)
        self._cam.start()

    def _on_frame_threadsafe(self, frame: Frame):
        self._bridge.got.emit(frame)

    def _on_frame(self, frame: np.ndarray):
        if frame.ndim == 2:
            h, w = frame.shape
            qimg = QImage(frame.data, w, h, w, QImage.Format_Grayscale8).copy()
        else:
            h, w, ch = frame.shape
            qimg = QImage(frame.data, w, h, ch*w, QImage.Format_RGB888).copy()
        self._label.setPixmap(QPixmap.fromImage(qimg))
