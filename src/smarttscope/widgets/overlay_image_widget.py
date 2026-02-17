from PySide6 import QtCore, QtGui, QtWidgets

class OverlayImageWidget(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._qimage = None
        self._img_w = 1
        self._img_h = 1
        self.circles = []  # [(cx, cy, r), ...]

    def set_frame_u8(self, img_u8):
        # img_u8: numpy array (H,W) uint8
        h, w = img_u8.shape
        self._img_w, self._img_h = w, h
        # NOTE: tobytes() ist ok für den Anfang; später kann man zero-copy machen.
        self._qimage = QtGui.QImage(img_u8.tobytes(), w, h, w, QtGui.QImage.Format_Grayscale8)
        self.update()

    def paintEvent(self, ev):
        if self._qimage is None:
            p = QtGui.QPainter(self)
            p.fillRect(self.rect(), QtGui.QColor("#111"))
            p.setPen(QtGui.QColor("#aaa"))
            p.drawText(self.rect(), QtCore.Qt.AlignCenter, "No signal")
            return

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing, True)

        s = min(self.width() / self._img_w, self.height() / self._img_h)
        draw_w = self._img_w * s
        draw_h = self._img_h * s
        off_x = (self.width() - draw_w) / 2
        off_y = (self.height() - draw_h) / 2

        dst = QtCore.QRectF(off_x, off_y, draw_w, draw_h)
        src = QtCore.QRectF(0, 0, self._img_w, self._img_h)
        p.drawImage(dst, self._qimage, src)

        # Overlay in Bildkoordinaten
        p.save()
        p.translate(off_x, off_y)
        p.scale(s, s)
        pen = QtGui.QPen(QtGui.QColor(0, 255, 0, 200))
        pen.setWidthF(2.0 / s)
        p.setPen(pen)
        p.setBrush(QtCore.Qt.NoBrush)
        for cx, cy, r in self.circles:
            p.drawEllipse(QtCore.QPointF(cx, cy), r, r)
        p.restore()

