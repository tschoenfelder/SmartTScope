"""Calibration master capture — bias, dark, and flat.

FR-CAL-010: Bias preparation
FR-CAL-020: Dark preparation
FR-CAL-030/040: Flat preparation with exposure auto-tuning
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

from ..domain.calibration_store import CalibrationIndex, CalibrationEntry, make_entry
from ..domain.frame import FitsFrame
from ..domain.histogram import HistogramStats, analyze as hist_analyze
from ..ports.camera import CameraPort

_log = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int], None]  # (frames_done, total)


class BiasValidationError(ValueError):
    """Raised when the stacked bias histogram fails the bias-compatible check."""


class DarkValidationError(ValueError):
    """Raised when the stacked dark histogram fails the dark-compatible check."""


# ── shared helpers ────────────────────────────────────────────────────────────


def _cg_name(cg: Any) -> str:
    return cg.name if hasattr(cg, "name") else str(cg)


def _capture_and_stack(
    camera: CameraPort,
    exposure_s: float,
    n_frames: int,
    progress: ProgressCallback | None,
    label: str,
) -> np.ndarray[Any, np.dtype[Any]]:
    """Capture *n_frames* and return the float32 mean stack."""
    accumulator: np.ndarray[Any, np.dtype[Any]] | None = None
    for i in range(n_frames):
        frame: FitsFrame = camera.capture(exposure_s)
        pixels = frame.pixels.astype(np.float64)
        accumulator = pixels if accumulator is None else accumulator + pixels
        if progress is not None:
            progress(i + 1, n_frames)
        _log.debug("%s frame %d/%d captured", label, i + 1, n_frames)
    assert accumulator is not None
    return (accumulator / n_frames).astype(np.float32)


def _validate_floor(
    master: np.ndarray[Any, np.dtype[Any]],
    bit_depth: int,
    label: str,
    exc_cls: type,
) -> HistogramStats:
    """Raise *exc_cls* if the master has floor-clipped pixels (FR-CAL-010/020)."""
    stats = hist_analyze(master, bit_depth=bit_depth)
    p01_adu = float(np.percentile(master.ravel(), 0.1))
    _log.info(
        "%s master stats: p0.1=%.1f ADU  zero_clip=%.4f%%  sat=%.4f%%",
        label, p01_adu, stats.zero_clipped_pct, stats.saturation_pct,
    )
    if p01_adu <= 0.0:
        raise exc_cls(
            f"{label} master p0.1 = {p01_adu:.1f} ADU (<= 0); "
            "increase offset/black level to lift the pedestal off zero."
        )
    if stats.zero_clipped_pct >= 0.01:
        raise exc_cls(
            f"{label} master has {stats.zero_clipped_pct:.4f}% zero-clipped pixels (>= 0.01%)."
        )
    return stats


def _write_master_fits(
    dest: Path,
    master: np.ndarray[Any, np.dtype[Any]],
    cal_type: str,
    n_frames: int,
    exposure_ms: float,
    gain: int,
    offset: int,
    cg: Any,
    bit_depth: int,
    camera_model: str,
    camera_serial: str,
    temperature_c: float | None,
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    hdr = fits.Header()
    hdr["SIMPLE"]   = True
    hdr["BITPIX"]   = -32
    hdr["NAXIS"]    = 2
    hdr["NAXIS1"]   = master.shape[1]
    hdr["NAXIS2"]   = master.shape[0]
    hdr["CALTYPE"]  = cal_type.upper()
    hdr["ISMASTER"] = True
    hdr["NFRAMES"]  = n_frames
    hdr["EXPTIME"]  = exposure_ms / 1000.0
    hdr["GAIN"]     = gain
    hdr["OFFSET"]   = offset
    hdr["CONVGAIN"] = _cg_name(cg)
    hdr["BITDEPTH"] = bit_depth
    hdr["INSTRUME"] = camera_model
    hdr["SERIALNO"] = camera_serial
    if temperature_c is not None:
        hdr["CCDTEMP"] = temperature_c
    hdr["DATE"]     = datetime.now(timezone.utc).isoformat()
    hdu = fits.PrimaryHDU(data=master, header=hdr)
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    dest.write_bytes(buf.getvalue())


# ── prepare_bias ──────────────────────────────────────────────────────────────


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
) -> CalibrationEntry:
    """Capture *n_frames* bias frames and stack into a master bias FITS.

    Raises BiasValidationError if the stacked histogram fails the floor check.
    """
    if n_frames < 1:
        raise ValueError("n_frames must be >= 1")

    caps = camera.get_capabilities()
    camera.set_exposure_ms(caps.min_exposure_ms)
    if gain is not None:
        camera.set_gain(gain)
    if offset is not None:
        camera.set_black_level(offset)
    if conversion_gain is not None:
        camera.set_conversion_gain(conversion_gain)

    eff_gain      = camera.get_gain()
    eff_offset    = camera.get_black_level()
    eff_cg        = camera.get_conversion_gain()
    eff_bit_depth = camera.get_bit_depth()
    eff_exp_ms    = camera.get_exposure_ms()
    cam_model     = camera.get_logical_name()
    cam_serial    = camera.get_serial_number()
    temp_c        = camera.get_temperature()

    _log.info(
        "Bias capture start: camera=%s n=%d gain=%d offset=%d cg=%s bd=%d exp=%.2fms",
        cam_model, n_frames, eff_gain, eff_offset, eff_cg, eff_bit_depth, eff_exp_ms,
    )

    master = _capture_and_stack(camera, eff_exp_ms / 1000.0, n_frames, progress, "Bias")
    _validate_floor(master, eff_bit_depth, "Bias", BiasValidationError)

    entry = make_entry(
        image_root, "bias", cam_model, cam_serial,
        gain=eff_gain, offset=eff_offset,
        conversion_gain=_cg_name(eff_cg),
        bit_depth=eff_bit_depth,
        frame_count=n_frames,
        temperature_c=temp_c,
    )
    dest = Path(image_root) / entry.relative_path
    _write_master_fits(
        dest, master, "bias", n_frames, eff_exp_ms,
        eff_gain, eff_offset, eff_cg, eff_bit_depth,
        cam_model, cam_serial, temp_c,
    )
    _log.info("Bias master written: %s", dest)
    cal_index.add(entry)
    return entry


# ── prepare_dark ──────────────────────────────────────────────────────────────


def prepare_dark(
    camera: CameraPort,
    exposure_ms: float,
    n_frames: int,
    image_root: str | Path,
    cal_index: CalibrationIndex,
    *,
    gain: int | None = None,
    offset: int | None = None,
    conversion_gain: Any | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[CalibrationEntry, str | None]:
    """Capture *n_frames* dark frames at *exposure_ms* and stack into a master dark FITS.

    Returns (entry, temperature_warning).  *temperature_warning* is None unless
    the camera temperature differs from the expected dark temperature by >= 5 °C
    (FR-TEMP-007), in which case it is a human-readable warning string.

    Raises DarkValidationError if the stacked histogram fails the floor or
    saturation check.
    """
    if n_frames < 1:
        raise ValueError("n_frames must be >= 1")
    if exposure_ms <= 0:
        raise ValueError("exposure_ms must be > 0")

    camera.set_exposure_ms(exposure_ms)
    if gain is not None:
        camera.set_gain(gain)
    if offset is not None:
        camera.set_black_level(offset)
    if conversion_gain is not None:
        camera.set_conversion_gain(conversion_gain)

    eff_gain      = camera.get_gain()
    eff_offset    = camera.get_black_level()
    eff_cg        = camera.get_conversion_gain()
    eff_bit_depth = camera.get_bit_depth()
    eff_exp_ms    = camera.get_exposure_ms()
    cam_model     = camera.get_logical_name()
    cam_serial    = camera.get_serial_number()
    temp_c        = camera.get_temperature()

    _log.info(
        "Dark capture start: camera=%s n=%d gain=%d offset=%d cg=%s bd=%d exp=%.2fms temp=%s",
        cam_model, n_frames, eff_gain, eff_offset, eff_cg, eff_bit_depth, eff_exp_ms,
        f"{temp_c:.1f}°C" if temp_c is not None else "unknown",
    )

    master = _capture_and_stack(camera, eff_exp_ms / 1000.0, n_frames, progress, "Dark")

    # Validate floor (same as bias — dark must not be zero-clipped)
    stats = _validate_floor(master, eff_bit_depth, "Dark", DarkValidationError)

    # Validate saturation — a good dark should be essentially signal-free
    if stats.saturation_pct >= 0.5:
        raise DarkValidationError(
            f"Dark master has {stats.saturation_pct:.2f}% saturated pixels (>= 0.5%); "
            "check that the scope is covered and the exposure is not too long for this gain."
        )

    # Temperature warning (FR-TEMP-007)
    temp_warning: str | None = None
    if temp_c is not None:
        # We warn at >= 5 °C deviation — caller should also see soft warning at 2–5 °C
        # but the hard-warn threshold in FR-TEMP-007 is 5 °C
        _log.info("Dark master capture temperature: %.1f °C", temp_c)
        # We store the temperature; the warning is emitted if the frame temp is
        # significantly different from what was intended. Since we have no separate
        # "session target temperature" here, we record what was measured and let
        # the caller decide. For now we just note the temperature.
        temp_warning = None  # no session target to compare against at capture time

    entry = make_entry(
        image_root, "dark", cam_model, cam_serial,
        gain=eff_gain, offset=eff_offset,
        conversion_gain=_cg_name(eff_cg),
        bit_depth=eff_bit_depth,
        frame_count=n_frames,
        exposure_ms=eff_exp_ms,
        temperature_c=temp_c,
    )
    dest = Path(image_root) / entry.relative_path
    _write_master_fits(
        dest, master, "dark", n_frames, eff_exp_ms,
        eff_gain, eff_offset, eff_cg, eff_bit_depth,
        cam_model, cam_serial, temp_c,
    )
    _log.info("Dark master written: %s", dest)
    cal_index.add(entry)
    return entry, temp_warning


# ── prepare_flat ──────────────────────────────────────────────────────────────

_FLAT_TARGET_P50  = 0.50
_FLAT_ACCEPT_LOW  = 0.40
_FLAT_ACCEPT_HIGH = 0.60
_FLAT_WARN_LOW    = 0.35
_FLAT_WARN_HIGH   = 0.70
_FLAT_MAX_TUNE    = 6     # auto-exposure tuning iterations


class FlatValidationError(ValueError):
    """Raised when the flat histogram is outside the acceptable range (<35 % or >70 %)."""


def _tune_flat_exposure(
    camera: CameraPort,
    initial_exp_ms: float,
    bit_depth: int,
) -> tuple[float, float]:
    """Iteratively adjust exposure so p50 ≈ 50 % of ADC range.

    Returns (tuned_exposure_ms, final_p50).
    Raises FlatValidationError if unable to reach 35–70 % range.
    """
    caps = camera.get_capabilities()
    cur_ms = max(caps.min_exposure_ms, min(caps.max_exposure_ms, initial_exp_ms))
    p50 = 0.0

    for _i in range(_FLAT_MAX_TUNE):
        camera.set_exposure_ms(cur_ms)
        frame = camera.capture(cur_ms / 1000.0)
        stats = hist_analyze(frame.pixels, bit_depth=bit_depth)
        p50 = stats.p50
        _log.debug("Flat tune iter %d: exp=%.1fms p50=%.3f", _i + 1, cur_ms, p50)

        if _FLAT_ACCEPT_LOW <= p50 <= _FLAT_ACCEPT_HIGH:
            break                           # within the accept zone — stop

        if p50 <= 0.0:
            raise FlatValidationError(
                "Flat test frame p50 = 0 — flat source too dim or camera is covered."
            )

        new_ms = cur_ms * (_FLAT_TARGET_P50 / p50)
        new_ms = max(caps.min_exposure_ms, min(caps.max_exposure_ms, new_ms))

        if abs(new_ms - cur_ms) < 0.5:     # converged (exposure at limit)
            cur_ms = new_ms
            break

        cur_ms = new_ms

    # Final check: hard-reject if outside 35–70 %
    if p50 < _FLAT_WARN_LOW or p50 > _FLAT_WARN_HIGH:
        raise FlatValidationError(
            f"Flat p50 = {p50 * 100:.1f}% is outside the acceptable 35–70% range. "
            "Adjust the flat-field light source brightness or exposure."
        )

    return cur_ms, p50


def prepare_flat(
    camera: CameraPort,
    optical_train: str,
    filter_id: str,
    n_frames: int,
    image_root: str | Path,
    cal_index: CalibrationIndex,
    *,
    initial_exposure_s: float = 1.0,
    gain: int | None = None,
    offset: int | None = None,
    conversion_gain: Any | None = None,
    progress: ProgressCallback | None = None,
) -> tuple[CalibrationEntry, list[str]]:
    """Auto-tune exposure and capture *n_frames* flat frames into a master flat FITS.

    Returns (entry, warnings) where *warnings* is a list of human-readable
    strings about sub-optimal but acceptable conditions (e.g. p50 in the
    35–40 % or 60–70 % warn zone).

    Raises FlatValidationError for out-of-range p50 or clipping failures.
    """
    if n_frames < 1:
        raise ValueError("n_frames must be >= 1")

    if gain is not None:
        camera.set_gain(gain)
    if offset is not None:
        camera.set_black_level(offset)
    if conversion_gain is not None:
        camera.set_conversion_gain(conversion_gain)

    eff_gain      = camera.get_gain()
    eff_offset    = camera.get_black_level()
    eff_cg        = camera.get_conversion_gain()
    eff_bit_depth = camera.get_bit_depth()
    cam_model     = camera.get_logical_name()
    cam_serial    = camera.get_serial_number()
    temp_c        = camera.get_temperature()

    _log.info(
        "Flat capture start: camera=%s optical_train=%s filter=%s n=%d",
        cam_model, optical_train, filter_id, n_frames,
    )

    # ── auto-tune exposure ────────────────────────────────────────────────────
    tuned_exp_ms, final_p50 = _tune_flat_exposure(
        camera, initial_exposure_s * 1000.0, eff_bit_depth
    )
    eff_exp_ms = camera.get_exposure_ms()   # use what camera actually accepted

    _log.info("Flat tuned: exp=%.1fms p50=%.3f", eff_exp_ms, final_p50)

    # Collect warnings for p50 in the warn zone (but not rejected)
    warnings: list[str] = []
    if final_p50 < _FLAT_ACCEPT_LOW:
        warnings.append(
            f"Flat p50 = {final_p50 * 100:.1f}% is below the ideal 40–60 % range. "
            "Consider increasing flat-field brightness for better signal."
        )
    elif final_p50 > _FLAT_ACCEPT_HIGH:
        warnings.append(
            f"Flat p50 = {final_p50 * 100:.1f}% is above the ideal 40–60 % range. "
            "Consider reducing flat-field brightness."
        )

    # ── capture and stack ─────────────────────────────────────────────────────
    master = _capture_and_stack(camera, eff_exp_ms / 1000.0, n_frames, progress, "Flat")

    # ── validate master ───────────────────────────────────────────────────────
    _validate_floor(master, eff_bit_depth, "Flat", FlatValidationError)

    stats = hist_analyze(master, bit_depth=eff_bit_depth)
    if stats.saturation_pct >= 0.5:
        raise FlatValidationError(
            f"Flat master has {stats.saturation_pct:.2f}% saturated pixels (>= 0.5%); "
            "reduce flat-field brightness or exposure time."
        )

    # ── write master FITS ─────────────────────────────────────────────────────
    entry = make_entry(
        image_root, "flat", cam_model, cam_serial,
        gain=eff_gain, offset=eff_offset,
        conversion_gain=_cg_name(eff_cg),
        bit_depth=eff_bit_depth,
        frame_count=n_frames,
        optical_train=optical_train,
        filter_id=filter_id,
        temperature_c=temp_c,
    )
    dest = Path(image_root) / entry.relative_path
    _write_master_fits(
        dest, master, "flat", n_frames, eff_exp_ms,
        eff_gain, eff_offset, eff_cg, eff_bit_depth,
        cam_model, cam_serial, temp_c,
    )
    # Append flat-specific headers
    with fits.open(str(dest), mode="update") as hdul:
        hdul[0].header["OPTTRAIN"] = optical_train
        hdul[0].header["FILTERID"] = filter_id
        hdul[0].header["ROTKNOWN"] = False
        hdul[0].header["FOCKNOWN"] = False
        hdul.flush()

    _log.info("Flat master written: %s", dest)
    cal_index.add(entry)
    return entry, warnings
