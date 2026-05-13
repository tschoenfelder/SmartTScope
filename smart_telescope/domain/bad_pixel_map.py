"""Bad pixel map generation (FR-CAL-BPM-001).

Captures N bias frames and uses Welford's online algorithm to compute
per-pixel mean and variance without holding all frames in memory.
Flags hot, dead, and noisy pixels; writes a uint8 FITS mask (0=good, 1=bad).
"""
from __future__ import annotations

import io
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

from ..domain.calibration_store import CalibrationIndex, CalibrationEntry, make_entry
from ..ports.camera import CameraPort

_log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]


@dataclass
class BpmStats:
    n_hot: int
    n_dead: int
    n_noisy: int
    total_pixels: int

    @property
    def n_bad(self) -> int:
        return self.n_hot + self.n_dead + self.n_noisy

    @property
    def bad_pct(self) -> float:
        return 100.0 * self.n_bad / max(1, self.total_pixels)

    def to_dict(self) -> dict[str, Any]:
        return {
            "n_hot":        self.n_hot,
            "n_dead":       self.n_dead,
            "n_noisy":      self.n_noisy,
            "n_bad":        self.n_bad,
            "total_pixels": self.total_pixels,
            "bad_pct":      round(self.bad_pct, 4),
        }


class BpmValidationError(ValueError):
    """Raised when BPM generation parameters or results are invalid."""


def generate_bpm(
    camera: CameraPort,
    n_frames: int,
    image_root: str | Path,
    cal_index: CalibrationIndex,
    *,
    gain: int | None = None,
    offset: int | None = None,
    hot_sigma: float = 5.0,
    dead_sigma: float = 5.0,
    noisy_factor: float = 3.0,
    progress: ProgressCallback | None = None,
) -> tuple[CalibrationEntry, BpmStats]:
    """Capture *n_frames* bias frames and derive a per-camera bad pixel map.

    Uses Welford's online algorithm so only two float64 arrays (mean, M2)
    are kept in memory at once — no frame cube.

    Flags:
        HOT   — pixel mean > global_median + hot_sigma × global_MAD_sigma
        DEAD  — pixel mean < global_median − dead_sigma × global_MAD_sigma
        NOISY — pixel std  > noisy_factor × global_median_std
    """
    if n_frames < 5:
        raise BpmValidationError("Need at least 5 frames for reliable per-pixel statistics")

    caps = camera.get_capabilities()
    camera.set_exposure_ms(caps.min_exposure_ms)
    if gain is not None:
        camera.set_gain(gain)
    if offset is not None:
        camera.set_black_level(offset)

    eff_gain      = camera.get_gain()
    eff_offset    = camera.get_black_level()
    eff_cg        = camera.get_conversion_gain()
    eff_bit_depth = camera.get_bit_depth()
    eff_exp_ms    = camera.get_exposure_ms()
    cam_model     = camera.get_logical_name()
    cam_serial    = camera.get_serial_number()

    _log.info(
        "BPM capture: camera=%s n=%d gain=%d offset=%d bd=%d exp=%.2fms "
        "hot_sigma=%.1f dead_sigma=%.1f noisy_factor=%.1f",
        cam_model, n_frames, eff_gain, eff_offset, eff_bit_depth, eff_exp_ms,
        hot_sigma, dead_sigma, noisy_factor,
    )

    # Welford online mean + M2 (sum of squared deviations)
    mean_px: np.ndarray | None = None
    m2_px:   np.ndarray | None = None

    for i in range(n_frames):
        frame = camera.capture(eff_exp_ms / 1000.0)
        x = frame.pixels.astype(np.float64)
        if mean_px is None:
            mean_px = np.zeros_like(x)
            m2_px   = np.zeros_like(x)
        n = i + 1
        delta     = x - mean_px
        mean_px  += delta / n
        m2_px    += delta * (x - mean_px)
        if progress is not None:
            progress(n, n_frames)
        _log.debug("BPM frame %d/%d", n, n_frames)

    assert mean_px is not None and m2_px is not None
    std_px = np.sqrt(np.maximum(m2_px / (n_frames - 1), 0.0))

    # Global statistics via MAD for robustness against the outliers we're detecting
    global_median  = float(np.median(mean_px))
    mad            = float(np.median(np.abs(mean_px - global_median)))
    global_sigma   = mad * 1.4826 if mad > 0.0 else float(np.std(mean_px))
    global_noise   = float(np.median(std_px))

    hot   = mean_px > (global_median + hot_sigma  * global_sigma)
    dead  = mean_px < (global_median - dead_sigma * global_sigma)
    noisy = (std_px > noisy_factor * global_noise) if global_noise > 0.0 else np.zeros(mean_px.shape, dtype=bool)
    bad   = hot | dead | noisy

    stats = BpmStats(
        n_hot        = int(np.sum(hot)),
        n_dead       = int(np.sum(dead)),
        n_noisy      = int(np.sum(noisy & ~hot & ~dead)),
        total_pixels = int(mean_px.size),
    )
    _log.info(
        "BPM result: hot=%d dead=%d noisy=%d total_bad=%d (%.3f%%)",
        stats.n_hot, stats.n_dead, stats.n_noisy, stats.n_bad, stats.bad_pct,
    )

    cg_name = eff_cg.name if hasattr(eff_cg, "name") else str(eff_cg)
    entry   = make_entry(
        image_root, "bpm", cam_model, cam_serial,
        gain=eff_gain, offset=eff_offset,
        conversion_gain=cg_name,
        bit_depth=eff_bit_depth,
        frame_count=n_frames,
    )
    dest = Path(image_root) / entry.relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    hdr = fits.Header()
    hdr["SIMPLE"]    = True
    hdr["BITPIX"]    = 8
    hdr["NAXIS"]     = 2
    hdr["NAXIS1"]    = bad.shape[1]
    hdr["NAXIS2"]    = bad.shape[0]
    hdr["CALTYPE"]   = "BPM"
    hdr["ISBPM"]     = True
    hdr["NFRAMES"]   = n_frames
    hdr["EXPTIME"]   = eff_exp_ms / 1000.0
    hdr["GAIN"]      = eff_gain
    hdr["OFFSET"]    = eff_offset
    hdr["CONVGAIN"]  = cg_name
    hdr["BITDEPTH"]  = eff_bit_depth
    hdr["INSTRUME"]  = cam_model
    hdr["SERIALNO"]  = cam_serial
    hdr["HOTSIGMA"]  = hot_sigma
    hdr["DEADSIG"]   = dead_sigma
    hdr["NOISEFAC"]  = noisy_factor
    hdr["N_HOT"]     = stats.n_hot
    hdr["N_DEAD"]    = stats.n_dead
    hdr["N_NOISY"]   = stats.n_noisy
    hdr["DATE"]      = datetime.now(timezone.utc).isoformat()

    hdu = fits.PrimaryHDU(data=bad.astype(np.uint8), header=hdr)
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    dest.write_bytes(buf.getvalue())
    _log.info("BPM written: %s (%d bad pixels, %.3f%%)", dest, stats.n_bad, stats.bad_pct)

    cal_index.add(entry)
    return entry, stats
