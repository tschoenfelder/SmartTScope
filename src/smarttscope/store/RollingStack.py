import numpy as np
from collections import deque

class RollingMeanStacker:
    """
    Rolling mean stack of the last N frames.
    Frames must have identical shape. Supports uint8/uint16 input.
    """
    def __init__(self, n: int):
        self.n = int(n)
        self.frames = deque(maxlen=self.n)
        self.sum = None  # uint32 accumulator

    def push(self, frame: np.ndarray) -> np.ndarray:
        if self.sum is None:
            self.sum = frame.astype(np.uint32, copy=True)
            self.frames.append(frame.copy())
            return frame

        if len(self.frames) == self.n:
            old = self.frames[0]
            self.sum -= old.astype(np.uint32, copy=False)

        self.frames.append(frame.copy())
        self.sum += frame.astype(np.uint32, copy=False)

        count = len(self.frames)
        mean = (self.sum / count).astype(frame.dtype, copy=False)
        return mean

def to_u8_preview(img: np.ndarray, black: int = 0, white: int = 65535) -> np.ndarray:
    # minmal und schnell
    img32 = img.astype(np.int32, copy=False)
    denom = max(1, white - black)
    out = (np.clip(img32 - black, 0, denom) * 255 // denom).astype(np.uint8)
    return out

def auto_levels_u16(img_u16: np.ndarray, lo=1.0, hi=99.5) -> tuple[int, int]:
    # robuster (percentil), evtl über 10 frames
    a = np.percentile(img_u16, lo)
    b = np.percentile(img_u16, hi)
    return int(a), int(max(a+1, b))
