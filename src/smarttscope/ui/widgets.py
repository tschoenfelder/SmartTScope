from __future__ import annotations
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
from PySide6.QtGui import QImage, QPixmap, QKeyEvent
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QDateTime
import os
from PySide6.QtCore import Qt, QObject, Signal, QTimer, QElapsedTimer
import numpy as np
from ..domain.ports import Camera, Frame

class _FrameBridge(QObject):
    got = Signal(object)  # numpy array

class CameraView(QWidget):
    def __init__(self, cam: Camera):
        super().__init__()
        self._cam = cam
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._last_qimg: QImage | None = None
        self._label = QLabel("Waiting for frames…")
        self._label.setAlignment(Qt.AlignCenter)
        self._fps = 0
        self._frames = 0
        self._fps_lbl = QLabel("FPS: –")
        self._fps_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._fps_lbl.setStyleSheet("QLabel{background:rgba(0,0,0,120);color:white;padding:2px 6px;border-radius:6px;}")
        self._fps_lbl.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._fps_lbl, alignment=Qt.AlignTop | Qt.AlignLeft)
        self._bridge = _FrameBridge()
        self._bridge.got.connect(self._on_frame)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_fps)
        self._timer.start(1000)

        self._cam.subscribe(self._on_frame_threadsafe)
        self._cam.start()

    def closeEvent(self, e):
        # vom Kamerathread abmelden und Kamera stoppen
        try:
            self._cam.unsubscribe(self._on_frame_threadsafe)
        except Exception:
            pass
        try:
            self._cam.stop()
        except Exception:
            pass
        super().closeEvent(e)

    def _on_frame_threadsafe(self, frame: Frame):
        self._bridge.got.emit(frame)

    def _on_frame(self, frame: np.ndarray):
        self._frames += 1
        if frame.ndim == 2:
            h, w = frame.shape
            qimg = QImage(frame.data, w, h, w, QImage.Format_Grayscale8).copy()
        else:
            h, w, ch = frame.shape
            qimg = QImage(frame.data, w, h, ch*w, QImage.Format_RGB888).copy()
        self._last_qimg = qimg
        self._label.setPixmap(QPixmap.fromImage(qimg))


    def _update_fps(self):
        self._fps = self._frames
        self._frames = 0
        self._fps_lbl.setText(f"FPS: {self._fps}")

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key_S and self._last_qimg is not None:
            os.makedirs("snapshots", exist_ok=True)
            ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss_zzz")
            path = os.path.join("snapshots", f"frame_{ts}.png")
            self._last_qimg.save(path)
        super().keyPressEvent(e)
