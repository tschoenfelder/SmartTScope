"""Domain models and pure analysis functions for bias-frame offset estimation."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ZERO_CLIP_THRESHOLD = 0.001  # 0.1 % zero pixels = clipping

DEFAULT_SWEEP_OFFSETS: list[int] = [0, 5, 10, 20, 30, 50, 75, 100, 125, 150, 200]


@dataclass
class BiasFrameStats:
    frame_index: int
    min_val: float
    max_val: float
    mean: float
    median: float
    std: float
    zero_count: int
    zero_fraction: float   # 0.0–1.0
    histogram: list[int]   # 256 bins across [0, max_val] range


@dataclass
class OffsetSweepPoint:
    offset: int
    zero_fraction: float
    min_val: float

    @property
    def is_safe(self) -> bool:
        return self.zero_fraction < ZERO_CLIP_THRESHOLD


@dataclass
class BiasEstimationResult:
    camera_model: str
    gain_mode_name: str        # "LCG", "HCG", "HDR"
    frame_count: int
    mean_stats: "BiasFrameStats | None"
    sweep: list[OffsetSweepPoint]

    @property
    def recommended_offset(self) -> int:
        """Return lowest safe offset (zero_fraction < ZERO_CLIP_THRESHOLD), or highest tested if none safe."""
        safe = [pt for pt in self.sweep if pt.is_safe]
        if safe:
            return min(safe, key=lambda pt: pt.offset).offset
        return max(self.sweep, key=lambda pt: pt.offset).offset if self.sweep else 0

    @property
    def safe(self) -> bool:
        return any(pt.is_safe for pt in self.sweep)

    def toml_snippet(self) -> str:
        offset = self.recommended_offset
        mode_key = self.gain_mode_name.lower()
        return (
            f"[camera_offsets.{self.camera_model}]\n"
            f"{mode_key} = {offset}\n"
        )


def analyze_frame(pixels: np.ndarray, frame_index: int = 0) -> BiasFrameStats:
    """Compute per-frame statistics for bias analysis."""
    flat = pixels.ravel().astype(np.float32)
    total = flat.size
    zero_count = int(np.sum(flat == 0))

    # 256-bin histogram from 0 to max (or 1.0 if all zero)
    max_val_f = float(flat.max()) if total > 0 else 0.0
    hist_max = max(max_val_f, 1.0)
    hist, _ = np.histogram(flat, bins=256, range=(0, hist_max))

    return BiasFrameStats(
        frame_index=frame_index,
        min_val=float(flat.min()) if total > 0 else 0.0,
        max_val=max_val_f,
        mean=float(flat.mean()) if total > 0 else 0.0,
        median=float(np.median(flat)) if total > 0 else 0.0,
        std=float(flat.std()) if total > 0 else 0.0,
        zero_count=zero_count,
        zero_fraction=zero_count / total if total > 0 else 0.0,
        histogram=hist.tolist(),
    )
