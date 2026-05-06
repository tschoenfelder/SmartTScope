"""Calibration master capture — bias, dark (future), flat (future).

FR-CAL-010: Bias preparation
  - minimum exposure, configured gain/offset/conversion-gain
  - stacks N frames via mean
  - validates p0.1 > 0 ADU (bias-compatible histogram)
  - writes master FITS + updates calibration_index.json
"""
from __future__ import annotations

import io
import logging
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits

from ..domain.calibration_store import CalibrationIndex, make_entry
from ..domain.frame import FitsFrame
from ..domain.histogram import analyze as hist_analyze
from ..ports.camera import CameraPort

_log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]  # (frames_done, total)


class BiasValidationError(ValueError):
    """Raised when the stacked bias histogram fails the bias-compatible check."""


def prepare_bias(
    camera: CameraPort,
    n_frames: int,
    image_root: str | Path,
    cal_index: CalibrationIndex,
    *,
    gain: int | None = None,
    offset: int | None = None,
    conversion_gain: Any | None = None,
    progress: ProgressCallback | None = None,
) -> "CalibrationEntry":  # noqa: F821
    """Capture *n_frames* bias frames and stack into a master bias FITS.

    The master is written to image_root/masters/.../biases/ and the entry
    is added to *cal_index* (caller must call cal_index.save() if desired,
    or pass persist=True to also save automatically — default is not to save
    so callers can batch multiple operations).

    Parameters
    ----------
    camera:
        Connected camera adapter.  Exposure is set to the minimum supported.
    n_frames:
        Number of bias frames to capture and stack (16 minimum per FR-CAL-010).
    image_root:
        Root directory for all captured data.
    cal_index:
        CalibrationIndex to add the new entry to.
    gain / offset / conversion_gain:
        Override camera settings.  If None, the camera's current values are used.
    progress:
        Optional callback invoked after each frame: ``progress(frames_done, n_frames)``.

    Returns
    -------
    CalibrationEntry
        The entry that was added to *cal_index*.

    Raises
    ------
    BiasValidationError
        If the stacked master histogram fails the bias-compatible check
        (p0.1 must be > 0 ADU, zero-clipped pixels < 0.01 %).
    """
    from ..domain.calibration_store import CalibrationEntry  # local import avoids circular

    if n_frames < 1:
        raise ValueError("n_frames must be >= 1")

    # ── configure camera ──────────────────────────────────────────────────────
    caps = camera.get_capabilities()
    camera.set_exposure_ms(caps.min_exposure_ms)

    if gain is not None:
        camera.set_gain(gain)
    if offset is not None:
        camera.set_black_level(offset)
    if conversion_gain is not None:
        camera.set_conversion_gain(conversion_gain)

    eff_gain       = camera.get_gain()
    eff_offset     = camera.get_black_level()
    eff_cg         = camera.get_conversion_gain()
    eff_bit_depth  = camera.get_bit_depth()
    eff_exp_ms     = camera.get_exposure_ms()
    camera_model   = camera.get_logical_name()
    camera_serial  = camera.get_serial_number()
    temperature_c  = camera.get_temperature()  # None if no cooling

    _log.info(
        "Bias capture start: camera=%s serial=%s n=%d gain=%d offset=%d cg=%s bd=%d exp=%.2fms",
        camera_model, camera_serial, n_frames,
        eff_gain, eff_offset, eff_cg, eff_bit_depth, eff_exp_ms,
    )

    # ── capture frames and accumulate ────────────────────────────────────────
    accumulator: np.ndarray[Any, np.dtype[Any]] | None = None

    for i in range(n_frames):
        frame: FitsFrame = camera.capture(eff_exp_ms / 1000.0)
        pixels = frame.pixels.astype(np.float64)
        if accumulator is None:
            accumulator = pixels
        else:
            accumulator = accumulator + pixels
        if progress is not None:
            progress(i + 1, n_frames)
        _log.debug("Bias frame %d/%d captured", i + 1, n_frames)

    assert accumulator is not None
    master_pixels: np.ndarray[Any, np.dtype[Any]] = (accumulator / n_frames).astype(np.float32)

    # ── validate histogram (FR-CAL-010) ──────────────────────────────────────
    stats = hist_analyze(master_pixels, bit_depth=eff_bit_depth)
    p01_adu = float(np.percentile(master_pixels.ravel(), 0.1))

    _log.info(
        "Bias master stats: p0.1=%.1f ADU  zero_clip=%.4f%%  black_level=%.4f",
        p01_adu, stats.zero_clipped_pct, stats.black_level,
    )

    if p01_adu <= 0.0:
        raise BiasValidationError(
            f"Bias master p0.1 = {p01_adu:.1f} ADU (<= 0); "
            "check that the camera is not clipping to zero (increase offset/black level)."
        )
    if stats.zero_clipped_pct >= 0.01:
        raise BiasValidationError(
            f"Bias master has {stats.zero_clipped_pct:.4f}% zero-clipped pixels (>= 0.01%); "
            "increase offset/black level to lift bias off the floor."
        )

    # ── write master FITS ─────────────────────────────────────────────────────
    entry: CalibrationEntry = make_entry(
        image_root,
        "bias",
        camera_model,
        camera_serial,
        gain=eff_gain,
        offset=eff_offset,
        conversion_gain=str(eff_cg.name) if hasattr(eff_cg, "name") else str(eff_cg),
        bit_depth=eff_bit_depth,
        frame_count=n_frames,
        temperature_c=temperature_c,
    )

    dest = Path(image_root) / entry.relative_path
    dest.parent.mkdir(parents=True, exist_ok=True)

    hdr = fits.Header()
    hdr["SIMPLE"]   = True
    hdr["BITPIX"]   = -32           # float32
    hdr["NAXIS"]    = 2
    hdr["NAXIS1"]   = master_pixels.shape[1]
    hdr["NAXIS2"]   = master_pixels.shape[0]
    hdr["CALTYPE"]  = "BIAS"
    hdr["ISMASTER"] = True
    hdr["NFRAMES"]  = n_frames
    hdr["EXPTIME"]  = eff_exp_ms / 1000.0
    hdr["GAIN"]     = eff_gain
    hdr["OFFSET"]   = eff_offset
    hdr["CONVGAIN"] = str(eff_cg.name) if hasattr(eff_cg, "name") else str(eff_cg)
    hdr["BITDEPTH"] = eff_bit_depth
    hdr["INSTRUME"] = camera_model
    hdr["SERIALNO"] = camera_serial
    if temperature_c is not None:
        hdr["CCDTEMP"] = temperature_c
    hdr["DATE"]     = datetime.now(timezone.utc).isoformat()

    hdu = fits.PrimaryHDU(data=master_pixels, header=hdr)
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    dest.write_bytes(buf.getvalue())

    _log.info("Bias master written: %s", dest)

    # ── update index ──────────────────────────────────────────────────────────
    cal_index.add(entry)

    return entry
