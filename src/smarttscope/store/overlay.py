from PySide6 import QtCore, QtGui, QtWidgets

class OverlayImageWidget(QtWidgets.QWidget):
    """Praktischer Tipp: Setze die Stiftbreite invers zur Skalierung, damit die Kreislinie optisch konstant bleibt:

pen.setWidthF(2.0 / scale)"""
    
    def __init__(self):
        super().__init__()
        self._qimage = None
        self._img_w = 1
        self._img_h = 1
        self.circles = []  # [(cx, cy, r), ...]

    def set_frame_u8(self, img_u8: np.ndarray):
        # img_u8 shape: (H, W), dtype=uint8
        h, w = img_u8.shape
        self._img_w, self._img_h = w, h

        # QImage expects bytes; keep a copy owned by QImage
        self._qimage = QtGui.QImage(
            img_u8.tobytes(), w, h, w, QtGui.QImage.Format_Grayscale8
        )
        self.update()

    def paintEvent(self, ev):
        if self._qimage is None:
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)

        # Fit image into widget while keeping aspect ratio
        target = QtCore.QRectF(self.rect())
        src = QtCore.QRectF(0, 0, self._img_w, self._img_h)

        scaled = QtCore.QRectF(src)
        scaled = QtGui.QTransform().scale(
            target.width() / self._img_w,
            target.height() / self._img_h
        ).mapRect(scaled)

        # Keep aspect ratio: compute uniform scale + center
        s = min(target.width() / self._img_w, target.height() / self._img_h)
        draw_w = self._img_w * s
        draw_h = self._img_h * s
        off_x = (target.width() - draw_w) / 2
        off_y = (target.height() - draw_h) / 2
        dst = QtCore.QRectF(off_x, off_y, draw_w, draw_h)

        painter.drawImage(dst, self._qimage, src)

        # Map image coords -> widget coords
        painter.save()
        painter.translate(off_x, off_y)
        painter.scale(s, s)

        pen = QtGui.QPen(QtGui.QColor(0, 255, 0, 200))
        pen.setWidthF(2.0 / s)  # keep line visually ~2px regardless of zoom
        painter.setPen(pen)
        painter.setBrush(QtCore.Qt.NoBrush)

        for (cx, cy, r) in self.circles:
            painter.drawEllipse(QtCore.QPointF(cx, cy), r, r)

        painter.restore()
