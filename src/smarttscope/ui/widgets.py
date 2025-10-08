from __future__ import annotations
from PySide6.QtCore import Qt, QObject, Signal, Slot, QTimer, QDateTime
from PySide6.QtGui import QImage, QPixmap, QKeyEvent, QPainter, QColor, QPen
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGraphicsView, QGraphicsScene, QToolButton, QMenu
)
import os
import numpy as np
from ..domain.ports import Camera, Frame
import time

class _FrameBridge(QObject):
    got = Signal(object)  # numpy array

class CameraView(QWidget):
    """Zeigt Frames (H,W,3 uint8) mit Zoom-Buttons und Scrollbars."""
    def __init__(self, cam: Camera, parent=None,
                 bg_color: str | QColor | None = None,
                 crosshair: bool = True,
                 crosshair_color: str | QColor = "#3CB371"):  # MediumSeaGreen
        

        super().__init__(parent)
        self._cam = cam
        self._scale = 1.0
        self._min_scale = 0.25
        self._max_scale = 4.0
        self._last_f_count = 0
        self._frames_this_sec = 0
        self._t0 = time.time()
        self._qimage = None  # Referenz halten, solange Pixmap lebt
        self._arr_ref = None # hält den numpy buffer life
        
        # --- UI: Top-Bar mit Zoom-Buttons + FPS ---
        self._btn_zoom_out = QToolButton(self)
        self._btn_zoom_out.setText("–")
        self._btn_zoom_out.setToolTip("Zoom out")

        self._btn_zoom_in = QToolButton(self)
        self._btn_zoom_in.setText("+")
        self._btn_zoom_in.setToolTip("Zoom in")

        self._btn_auto = QToolButton(self)
        self._btn_auto.setText("AUTO")
        self._btn_auto.setCheckable(True)
        self._btn_auto.setToolTip("Auto-Stretch: clip low/high (0.5%/99.5%) und auf 0–255 strecken")
        self._auto_lo = None
        self._auto_hi = None
        self._auto_alpha = 0.3   # 0..1

        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._last_qimg: QImage | None = None
        self._label = QLabel("Waiting for frames…")
        self._label.setAlignment(Qt.AlignCenter)
        self._fps = 0
        self._frames = 0
        self._fps_lbl = QLabel("0.0 FPS", self)
        self._fps_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        if cam and hasattr(cam, "name") and str(getattr(cam, "name")).startswith("MOCK"):
            self._fps_lbl.setStyleSheet("color:#888; font-style:italic;")
            self._fps_lbl.setText("MOCK – waiting…")
##        self._fps_lbl.setAttribute(Qt.WA_TransparentForMouseEvents)
##        self._fps_lbl.setStyleSheet("QLabel{background:rgba(0,0,0,120);color:white;padding:2px 6px;border-radius:6px;}")
        self._fps_lbl.setStyleSheet("color:#888; font-size:11px;")

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(6)
        top.addWidget(self._btn_zoom_out)
        top.addWidget(self._btn_zoom_in)
        top.addStretch(1)
        top.addWidget(self._fps_lbl)

        top.addWidget(self._btn_zoom_out)
        top.addWidget(self._btn_zoom_in)
        top.addWidget(self._btn_auto)      # <<< neu
        top.addStretch(1)
        top.addWidget(self._fps_lbl)

        # --- View mit Scrollbars ---
        self._scene = QGraphicsScene(self)
        self._pixitem = self._scene.addPixmap(QPixmap())
        self._view = QGraphicsView(self._scene, self)
        self._view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        layout.addLayout(top)
        layout.addWidget(self._view, 1)
##        layout.addWidget(self._label)
##        layout.addWidget(self._fps_lbl, alignment=Qt.AlignTop | Qt.AlignLeft)
        # Bridge: Frames thread-sicher in den GUI-Thread
        self._bridge = _FrameBridge(self)
        self._bridge.got.connect(self._on_frame, Qt.QueuedConnection)
##        self._bridge = _FrameBridge()
##        self._bridge.got.connect(self._on_frame)

        # Signals
        self._btn_zoom_in.clicked.connect(lambda: self._apply_zoom(1.15))
        self._btn_zoom_out.clicked.connect(lambda: self._apply_zoom(1/1.15))
        self._btn_auto.toggled.connect(self._on_auto_toggled)

        # Kamera-Frames abonnieren (Emitter!) und starten
        self._cam.subscribe(self._bridge.got.emit)
        self._cam.start()
        # FPS-Anzeige aktualisieren
        self._fps_timer = QTimer(self)
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(500)

        # Hintergrund (falls gewünscht)
        if bg_color is not None:
            col = QColor(bg_color) if isinstance(bg_color, str) else bg_color
            self._view.setBackgroundBrush(col)
            self._scene.setBackgroundBrush(col)

        # --- Fadenkreuz ---
        self._hline = None
        self._vline = None
        if crosshair:
            pen = QPen(QColor(crosshair_color) if isinstance(crosshair_color, str) else crosshair_color)
            pen.setWidth(2)
            pen.setCosmetic(True)  # Linienbreite bleibt bei Zoom konstant
            self._hline = self._scene.addLine(0, 0, 0, 0, pen)
            self._vline = self._scene.addLine(0, 0, 0, 0, pen)
            for it in (self._hline, self._vline):
                it.setZValue(10)   # über dem Bild

        # Auto-Stretch-Parameter (ggf. anpassen)
        self._auto_on = False
        self._auto_pct_low = 0.5      # Prozent
        self._auto_pct_high = 99.5    # Prozent
        self._auto_sample = 4         # Histogramm auf jedem n-ten Pixel



        ##        self._timer = QTimer(self)


##        self._timer.timeout.connect(self._update_fps)
##        self._timer.start(1000)
##
##        self._cam.subscribe(self._on_frame_threadsafe)
##        self._cam.start()

    def _update_crosshair(self):
        if not (self._hline and self._vline):
            return
        rect = self._scene.sceneRect()
        w, h = rect.width(), rect.height()
        cx, cy = w * 0.5, h * 0.5
        self._hline.setLine(0, cy, w, cy)
        self._vline.setLine(cx, 0, cx, h)

    def closeEvent(self, e):
        try: self._cam.unsubscribe(self._bridge.got.emit)
        except Exception: pass
        try: self._cam.stop()
        except Exception: pass
        return super().closeEvent(e)

    def _on_frame_threadsafe(self, frame: Frame):
        self._bridge.got.emit(frame)

    @Slot(object)
    def _on_frame(self, frame: np.ndarray):
        """Erwartet (H,W,3) uint8 – bereits debayered (RGB888)."""


        if frame is None or frame.ndim != 3 or frame.shape[2] != 3:
            return

        # Auto-Stretch optional anwenden
        if self._auto_on:
            frame_use = self._apply_autostretch(frame)
        else:
            frame_use = frame

        h, w, _ = frame.shape
        self._arr_ref = frame
        # RGB888
        self._qimage = QImage(frame.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        # Pixmap setzen (Kopie)
        self._pixitem.setPixmap(QPixmap.fromImage(self._qimage))
        # Szene auf Bildgröße setzen
        self._scene.setSceneRect(0, 0, w, h)
        # set crosshair
        self._update_crosshair()
        # aktuelle Transformation anwenden
        self._update_view_transform()
        # FPS zählen
        self._frames_this_sec += 1
##        self._frames += 1
##        if frame.ndim == 2:
##            h, w = frame.shape
##            qimg = QImage(frame.data, w, h, w, QImage.Format_Grayscale8).copy()
##        else:
##            h, w, ch = frame.shape
##            qimg = QImage(frame.data, w, h, ch*w, QImage.Format_RGB888).copy()
##        self._last_qimg = qimg
##        self._label.setPixmap(QPixmap.fromImage(qimg))

    # --- Zoom-Logik ---
    def _apply_zoom(self, factor: float):
        self._scale = max(self._min_scale, min(self._max_scale, self._scale * factor))
        self._update_view_transform()

    def _update_view_transform(self):
        self._view.resetTransform()
        self._view.scale(self._scale, self._scale)
        
    def _on_auto_toggled(self, checked: bool):
        self._auto_on = checked
        # leichte optische Rückmeldung
        self._set_auto_button_style()
##        self._btn_auto.setStyleSheet("background:#e6ffe6;" if checked else "")

    def _set_auto_button_style(self):
        self._btn_auto.setStyleSheet("background:#e6ffe6;" if self._auto_on else "")

    def _set_autostretch(self, on: bool):
        self._auto_on = on
        # Button-UI konsistent halten
        self._btn_auto.blockSignals(True)
        self._btn_auto.setChecked(on)
        self._btn_auto.blockSignals(False)
        self._set_auto_button_style()

    def _set_autostretch_percentiles(self, low: float, high: float):
        self._auto_pct_low = low
        self._auto_pct_high = high
        self._set_autostretch(True)

    def _apply_autostretch(self, frame: np.ndarray) -> np.ndarray:
        """Percentile-Clipping anhand Luminanz, gleiches Mapping auf alle Kanäle."""
        if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[2] != 3:
            return frame

        # Downsample fürs Histogramm (schnell)
        s = self._auto_sample
        sub = frame[::s, ::s, :].astype(np.float32)

        # Luminanz (sRGB-ähnlich)
        lum = 0.2126 * sub[:, :, 0] + 0.7152 * sub[:, :, 1] + 0.0722 * sub[:, :, 2]

        lo = float(np.percentile(lum, self._auto_pct_low))
        hi = float(np.percentile(lum, self._auto_pct_high))

        # in _apply_autostretch nach lo/hi:
        if self._auto_lo is None:
            self._auto_lo, self._auto_hi = lo, hi
        else:
            self._auto_lo = (1-self._auto_alpha)*self._auto_lo + self._auto_alpha*lo
            self._auto_hi = (1-self._auto_alpha)*self._auto_hi + self._auto_alpha*hi
        lo, hi = self._auto_lo, self._auto_hi

        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            return frame

        scale = 255.0 / (hi - lo)
        arr = (frame.astype(np.float32) - lo) * scale
        # clip & zurück zu uint8 (neue Kopie – nicht in-place)
        return np.clip(arr, 0, 255).astype(np.uint8)

        # --- FPS-UI ---
    def _update_fps(self):
        t = time.time()
        dt = t - self._t0
        if dt >= 1.0:
            fps = self._frames_this_sec / dt
            self._fps_lbl.setText(f"{fps:.1f} FPS")
            self._frames_this_sec = 0
            self._t0 = t

##    def _update_fps(self):
##        self._fps = self._frames
##        self._frames = 0
##        self._fps_lbl.setText(f"FPS: {self._fps}")

    def keyPressEvent(self, e: QKeyEvent) -> None:
        if e.key() == Qt.Key_S and self._last_qimg is not None:
            os.makedirs("snapshots", exist_ok=True)
            ts = QDateTime.currentDateTime().toString("yyyyMMdd_hhmmss_zzz")
            path = os.path.join("snapshots", f"frame_{ts}.png")
            self._last_qimg.save(path)
        super().keyPressEvent(e)

    def contextMenuEvent(self, event):
        menu = QMenu(self)

        act_off = menu.addAction("Auto-Stretch: Off")
        menu.addSeparator()
        act_05 = menu.addAction("Auto-Stretch 0.5% / 99.5%")
        act_10 = menu.addAction("Auto-Stretch 1% / 99%")
        act_20 = menu.addAction("Auto-Stretch 2% / 98%")

        chosen = menu.exec(event.globalPos())
        if not chosen:
            return
        if chosen == act_off:
            self._set_autostretch(False)
        elif chosen == act_05:
            self._set_autostretch_percentiles(0.5, 99.5)
        elif chosen == act_10:
            self._set_autostretch_percentiles(1.0, 99.0)
        elif chosen == act_20:
            self._set_autostretch_percentiles(2.0, 98.0)

