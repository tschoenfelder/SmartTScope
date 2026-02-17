import numpy as np

class RollingMeanStacker:
    def __init__(self, n: int, shape: tuple[int, int], dtype=np.uint16):
        self.n = int(n)
        self.h, self.w = shape
        self.buf = np.empty((self.n, self.h, self.w), dtype=dtype)
        self.sum = np.zeros((self.h, self.w), dtype=np.uint32)
        self.idx = 0
        self.count = 0

    def push(self, frame: np.ndarray) -> np.ndarray:
        # frame: (H,W), dtype uint8/uint16, contiguous preferred
        if self.count < self.n:
            self.buf[self.idx] = frame
            np.add(self.sum, frame, out=self.sum, casting="unsafe")
            self.count += 1
        else:
            old = self.buf[self.idx]
            np.subtract(self.sum, old, out=self.sum, casting="unsafe")
            self.buf[self.idx] = frame
            np.add(self.sum, frame, out=self.sum, casting="unsafe")

        self.idx = (self.idx + 1) % self.n
        # mean in input dtype (uint16/uint8)
        mean = (self.sum // self.count).astype(frame.dtype, copy=False)
        return mean

##2) Für die Darstellung: sehr schneller 8-bit Preview-Pfad
##
##Auch wenn du intern uint16 stackst: Für UI reicht meist uint8. Linear skaliert:

def to_u8(img: np.ndarray, black: int, white: int) -> np.ndarray:
    img32 = img.astype(np.int32, copy=False)
    denom = max(1, white - black)
    return (np.clip(img32 - black, 0, denom) * 255 // denom).astype(np.uint8)

##
##black/white kannst du:
##
##fix setzen (schnell, stabil), oder
##
##alle z. B. 10 Frames per Perzentil neu bestimmen (robuster, etwas teurer).
##3) UI ohne Kopierorgie: QImage aus NumPy “zero-copy”
##
##Vermeide tobytes() pro Frame (das kopiert). Besser: QImage auf die NumPy-Daten zeigen lassen und das Array am Leben halten.
##
##Für uint8:

from PySide6 import QtGui

def qimage_from_u8(img_u8: np.ndarray) -> QtGui.QImage:
    img_u8 = np.ascontiguousarray(img_u8)  # falls nötig
    h, w = img_u8.shape
    bytes_per_line = img_u8.strides[0]
    qimg = QtGui.QImage(img_u8.data, w, h, bytes_per_line, QtGui.QImage.Format_Grayscale8)
    return qimg

##
##Wichtig: Du musst in deinem Widget/Viewer self._last_frame = img_u8 speichern, sonst kann das Array vom GC freigegeben werden, während Qt noch zeichnet.
##
##Optional: Wenn du wirklich 16-bit anzeigen willst, gibt es QImage.Format_Grayscale16 (Qt6). In der Praxis konvertiert die Anzeige oft trotzdem irgendwo; der u8-Preview ist meist schneller und kontrollierter.
##
