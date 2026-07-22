"""Unit tests for domain/autogain.py (AGT-5-1)."""
from __future__ import annotations

import numpy as np
import pytest

from smart_telescope.domain.autogain import (
    AutoGainController,
    AutoGainMode,
    _EXP_MAX,
    _EXP_MIN,
    _GAIN_MAX,
    _GAIN_MIN,
    _HI,
    _LO,
    _TARGET,
)
from smart_telescope.domain.camera_capabilities import ConversionGain
from smart_telescope.domain.camera_profile import ATR585M, G3M678M, GPCMOS02000KPA


# ── Helpers ────────────────────────────────────────────────────────────────────

def _uniform(value_adu: float, bit_depth: int = 16, shape: tuple[int, int] = (64, 64)) -> np.ndarray:
    """Return a uniform frame at the given ADU level."""
    return np.full(shape, value_adu, dtype=np.float32)


def _target_adu(bit_depth: int = 16) -> float:
    """ADU level that produces mean_frac == _TARGET."""
    return _TARGET * float((1 << bit_depth) - 1)


def _sparse_star_frame(
    peak_adu: float, background_adu: float = 10.0,
    bit_depth: int = 16, shape: tuple[int, int] = (64, 64),
) -> np.ndarray:
    """A mostly-dark frame with a small bright patch — mimics a guide-star
    field where mean_frac stays near zero regardless of the star's
    brightness. Needs >= ~0.1% of pixels at peak_adu for the 99.9th
    percentile to actually reflect it (4096 px → at least 5 pixels)."""
    arr = np.full(shape, background_adu, dtype=np.float32)
    arr.flat[:10] = peak_adu
    return arr


# ── Default (no profile) — backward-compatible behaviour ─────────────────────

class TestDefaultLimits:
    def test_default_gain_min(self) -> None:
        ctrl = AutoGainController()
        assert ctrl._gain_min == _GAIN_MIN

    def test_default_gain_max(self) -> None:
        ctrl = AutoGainController()
        assert ctrl._gain_max == _GAIN_MAX

    def test_default_exp_min(self) -> None:
        ctrl = AutoGainController()
        assert ctrl._exp_min == pytest.approx(_EXP_MIN)

    def test_default_exp_max(self) -> None:
        ctrl = AutoGainController()
        assert ctrl._exp_max == pytest.approx(_EXP_MAX)

    def test_default_conversion_gain_is_lcg(self) -> None:
        ctrl = AutoGainController()
        assert ctrl.conversion_gain == ConversionGain.LCG

    def test_initial_exposure_clamped(self) -> None:
        ctrl = AutoGainController(exposure=0.0)
        assert ctrl.exposure == pytest.approx(_EXP_MIN)

    def test_initial_gain_clamped(self) -> None:
        ctrl = AutoGainController(gain=50)
        assert ctrl.gain == _GAIN_MIN

    def test_update_no_change_when_in_band(self) -> None:
        ctrl = AutoGainController(exposure=2.0, gain=100, bit_depth=16)
        pix = _uniform(_target_adu(16))
        ctrl.update(pix)
        assert ctrl.exposure == pytest.approx(2.0)
        assert ctrl.gain == 100

    def test_update_increases_exposure_when_too_dark(self) -> None:
        ctrl = AutoGainController(exposure=1.0, gain=100, bit_depth=16)
        pix = _uniform(1.0)  # essentially black
        ctrl.update(pix)
        assert ctrl.exposure > 1.0

    def test_update_decreases_exposure_when_too_bright(self) -> None:
        adc_max = float((1 << 16) - 1)
        ctrl = AutoGainController(exposure=2.0, gain=100, bit_depth=16)
        pix = _uniform(adc_max * 0.95)  # near saturation
        ctrl.update(pix)
        assert ctrl.exposure < 2.0


# ── Profile-derived limits ────────────────────────────────────────────────────

class TestProfileLimits:
    def test_atr585m_gain_max(self) -> None:
        ctrl = AutoGainController(profile=ATR585M)
        assert ctrl._gain_max == ATR585M.max_gain

    def test_atr585m_exp_min_from_profile(self) -> None:
        ctrl = AutoGainController(profile=ATR585M)
        assert ctrl._exp_min == pytest.approx(ATR585M.min_preview_exp_ms / 1000.0)

    def test_atr585m_exp_max_from_profile(self) -> None:
        ctrl = AutoGainController(profile=ATR585M)
        assert ctrl._exp_max == pytest.approx(ATR585M.max_preview_exp_ms / 1000.0)

    def test_g3m678m_gain_max(self) -> None:
        ctrl = AutoGainController(profile=G3M678M)
        assert ctrl._gain_max == G3M678M.max_gain

    def test_gain_clamped_to_profile_max(self) -> None:
        ctrl = AutoGainController(gain=99999, profile=ATR585M)
        assert ctrl.gain == ATR585M.max_gain

    def test_exposure_clamped_to_profile_exp_max(self) -> None:
        ctrl = AutoGainController(exposure=9999.0, profile=ATR585M)
        assert ctrl.exposure == pytest.approx(ATR585M.max_preview_exp_ms / 1000.0)

    def test_exposure_clamped_to_profile_exp_min(self) -> None:
        ctrl = AutoGainController(exposure=0.0, profile=ATR585M)
        assert ctrl.exposure == pytest.approx(ATR585M.min_preview_exp_ms / 1000.0)

    def test_gain_does_not_exceed_profile_max_after_update(self) -> None:
        ctrl = AutoGainController(
            exposure=ATR585M.max_preview_exp_ms / 1000.0,  # at exp ceiling
            gain=ATR585M.max_gain,
            profile=ATR585M,
            bit_depth=12,
        )
        pix = _uniform(1.0, bit_depth=12)  # black → controller tries to brighten
        ctrl.update(pix)
        assert ctrl.gain <= ATR585M.max_gain

    def test_exp_does_not_exceed_profile_exp_max_after_update(self) -> None:
        ctrl = AutoGainController(exposure=1.0, gain=100, profile=ATR585M, bit_depth=12)
        pix = _uniform(1.0, bit_depth=12)  # black
        for _ in range(10):
            ctrl.update(pix)
        assert ctrl.exposure <= ATR585M.max_preview_exp_ms / 1000.0 + 1e-6


# ── Conversion gain selection (FR-AG-080) ─────────────────────────────────────

class TestConversionGain:
    def test_dso_mode_atr585m_selects_hcg(self) -> None:
        ctrl = AutoGainController(profile=ATR585M, mode=AutoGainMode.DSO)
        assert ctrl.conversion_gain == ConversionGain.HCG

    def test_dso_mode_g3m678m_selects_hcg(self) -> None:
        ctrl = AutoGainController(profile=G3M678M, mode=AutoGainMode.DSO)
        assert ctrl.conversion_gain == ConversionGain.HCG

    def test_guiding_mode_atr585m_selects_hcg(self) -> None:
        ctrl = AutoGainController(profile=ATR585M, mode=AutoGainMode.GUIDING)
        assert ctrl.conversion_gain == ConversionGain.HCG

    def test_planetary_mode_atr585m_selects_lcg(self) -> None:
        ctrl = AutoGainController(profile=ATR585M, mode=AutoGainMode.PLANETARY)
        assert ctrl.conversion_gain == ConversionGain.LCG

    def test_lunar_mode_atr585m_selects_lcg(self) -> None:
        ctrl = AutoGainController(profile=ATR585M, mode=AutoGainMode.LUNAR)
        assert ctrl.conversion_gain == ConversionGain.LCG

    def test_planetary_mode_g3m678m_selects_lcg(self) -> None:
        ctrl = AutoGainController(profile=G3M678M, mode=AutoGainMode.PLANETARY)
        assert ctrl.conversion_gain == ConversionGain.LCG

    def test_no_profile_always_lcg(self) -> None:
        for mode in AutoGainMode:
            ctrl = AutoGainController(mode=mode)
            assert ctrl.conversion_gain == ConversionGain.LCG

    def test_gpcmos_has_no_hcg_falls_back_to_lcg(self) -> None:
        # GPCMOS02000KPA has unity_gain_hcg=None
        ctrl = AutoGainController(profile=GPCMOS02000KPA, mode=AutoGainMode.GUIDING)
        assert ctrl.conversion_gain == ConversionGain.LCG


# ── Offset-aware histogram (FR-AG-070) ───────────────────────────────────────

class TestOffsetAdu:
    def test_offset_zero_no_effect(self) -> None:
        ctrl1 = AutoGainController(exposure=1.0, gain=100, offset_adu=0, bit_depth=12)
        ctrl2 = AutoGainController(exposure=1.0, gain=100, offset_adu=0, bit_depth=12)
        pix = _uniform(50.0, bit_depth=12)
        ctrl1.update(pix)
        ctrl2.update(pix)
        assert ctrl1.exposure == pytest.approx(ctrl2.exposure)

    def test_offset_shifts_baseline_prevents_false_signal(self) -> None:
        # 150 ADU on 12-bit → mean_frac ≈ 0.037 (below _LO 0.12 → too dark)
        # but if offset_adu=150 that's pure pedestal; after subtraction ≈ 0.0
        # Controller should try to increase exposure
        ctrl = AutoGainController(exposure=1.0, gain=100, offset_adu=150, bit_depth=12)
        pix = _uniform(150.0, bit_depth=12)
        exp_before = ctrl.exposure
        ctrl.update(pix)
        # Mean ≈ 0.037, offset_frac ≈ 0.037 → mean_frac ≈ 0 → still too dark → increase exp
        assert ctrl.exposure > exp_before

    def test_without_offset_shallow_signal_looks_in_band(self) -> None:
        # At 0% offset, 1800 ADU on 12-bit → mean_frac ≈ 0.44 (inside [0.12, 0.45])
        ctrl = AutoGainController(exposure=1.0, gain=100, offset_adu=0, bit_depth=12)
        pix = _uniform(1800.0, bit_depth=12)
        exp_before = ctrl.exposure
        ctrl.update(pix)
        assert ctrl.exposure == pytest.approx(exp_before)  # no change

    def test_offset_clamped_to_zero(self) -> None:
        ctrl = AutoGainController(offset_adu=-100)
        assert ctrl._offset_adu == 0


# ── Bit-depth normalisation ───────────────────────────────────────────────────

class TestBitDepthNormalisation:
    def test_12bit_mid_signal_in_band(self) -> None:
        # 1800 ADU in 12-bit (4095 max) → mean_frac ≈ 0.44 — inside band
        ctrl = AutoGainController(exposure=1.0, gain=100, bit_depth=12)
        pix = _uniform(1800.0, bit_depth=12)
        ctrl.update(pix)
        assert ctrl.exposure == pytest.approx(1.0)

    def test_16bit_same_adu_looks_dark(self) -> None:
        # 1800 ADU in 16-bit (65535 max) → mean_frac ≈ 0.027 — below _LO
        ctrl = AutoGainController(exposure=1.0, gain=100, bit_depth=16)
        pix = _uniform(1800.0, bit_depth=16)
        ctrl.update(pix)
        assert ctrl.exposure > 1.0  # increased because signal looks too dark

    def test_12bit_black_frame_darkens_exposure(self) -> None:
        ctrl = AutoGainController(exposure=2.0, gain=100, bit_depth=12)
        pix = _uniform(0.0, bit_depth=12)
        ctrl.update(pix)
        assert ctrl.exposure > 2.0


# ── Guiding-mode signal metric (M10-040) ──────────────────────────────────────
#
# AutoGainController.update() previously always used mean_frac regardless of
# `mode`, even though a guide camera stares at a mostly-dark sparse field
# where the mean stays near zero no matter how well-exposed the one guide
# star is. That drove exposure/gain to their ceiling forever for the guide
# role specifically, while DSO-mode cameras on the same preview screen
# correctly settled — matching a real user report (2026-07-22): "two cameras
# adjust exposure, one doesn't: guide ... 4.00s gain 400".

class TestGuidingModeSignalMetric:
    def test_dso_mode_uses_mean_not_p99_9(self) -> None:
        # A sparse-star DSO frame: mean is near zero (too dark by mean), so a
        # DSO-mode controller must still try to brighten — p99_9 alone isn't
        # the deciding signal outside the sparse-field early-exit heuristic.
        ctrl = AutoGainController(exposure=2.0, gain=100, mode=AutoGainMode.DSO, bit_depth=16)
        # Below the sparse-field p99_9 threshold too, so brightening proceeds.
        pix = _sparse_star_frame(peak_adu=0.05 * 65535, background_adu=1.0)
        ctrl.update(pix)
        assert ctrl.exposure > 2.0

    def test_guiding_mode_in_band_star_no_change(self) -> None:
        # mean_frac is near zero (would look "too dark" under DSO logic), but
        # the guide star peak (p99_9) sits mid-band — no change should occur.
        ctrl = AutoGainController(exposure=2.0, gain=100, mode=AutoGainMode.GUIDING, bit_depth=16)
        pix = _sparse_star_frame(peak_adu=0.45 * 65535)
        ctrl.update(pix)
        assert ctrl.exposure == pytest.approx(2.0)
        assert ctrl.gain == 100

    def test_guiding_mode_brightens_when_star_too_faint(self) -> None:
        ctrl = AutoGainController(exposure=1.0, gain=100, mode=AutoGainMode.GUIDING, bit_depth=16)
        pix = _sparse_star_frame(peak_adu=0.05 * 65535)
        ctrl.update(pix)
        assert ctrl.exposure > 1.0

    def test_guiding_mode_dims_when_star_too_bright(self) -> None:
        ctrl = AutoGainController(exposure=2.0, gain=100, mode=AutoGainMode.GUIDING, bit_depth=16)
        pix = _sparse_star_frame(peak_adu=0.95 * 65535)
        ctrl.update(pix)
        assert ctrl.exposure < 2.0

    def test_guiding_mode_no_signal_still_hits_ceiling(self) -> None:
        # No star at all: p99_9 stays near background — correctly keeps
        # trying to brighten, same terminal-at-ceiling behavior as DSO when
        # genuinely nothing is there (this controller has no NO_SIGNAL
        # status; it's the one-shot AutoGainService's job to report that).
        ctrl = AutoGainController(exposure=2.0, gain=100, mode=AutoGainMode.GUIDING, bit_depth=16)
        pix = _uniform(5.0, bit_depth=16)
        for _ in range(20):
            ctrl.update(pix)
        assert ctrl.exposure == pytest.approx(_EXP_MAX)
        assert ctrl.gain == _GAIN_MAX


# ── Per-frame bit-depth override (M10-037) ────────────────────────────────────
#
# CameraPort.get_bit_depth() documents returning a stale default (16) until the
# first frame is captured, for adapters that lazily detect the sensor's true
# native depth (see adapters/touptek/camera.py / managed.py). A controller
# constructed with that stale value before the first capture would otherwise
# stay wrong for the entire session, since __init__ never runs again.

class TestPerFrameBitDepthOverride:
    def test_update_bit_depth_overrides_constructor_value(self) -> None:
        # Constructed as if get_bit_depth() returned the stale pre-capture
        # default (16) for a sensor that is actually 12-bit.
        ctrl = AutoGainController(exposure=2.0, gain=100, bit_depth=16)
        # A fully saturated 12-bit frame (4095 max) — without the override this
        # would be read against adc_max=65535 (~6% → looks dark, not saturated).
        pix = _uniform(4095.0, bit_depth=12)
        ctrl.update(pix, bit_depth=12)
        assert ctrl.exposure < 2.0  # correctly recognised as too bright, dimmed
        assert ctrl._bit_depth == 12

    def test_update_without_bit_depth_keeps_constructor_value(self) -> None:
        ctrl = AutoGainController(exposure=1.0, gain=100, bit_depth=12)
        pix = _uniform(1800.0, bit_depth=12)
        ctrl.update(pix)  # no override — backward compatible
        assert ctrl._bit_depth == 12
        assert ctrl.exposure == pytest.approx(1.0)

    def test_stale_construction_bit_depth_gets_stuck_without_override(self) -> None:
        # Reproduces the actual bug (M10-037): constructed with the wrong
        # pre-capture default, then updated WITHOUT passing the real per-frame
        # bit_depth — the controller misreads real saturation as ~6% signal,
        # drives to max exposure/gain trying to "brighten", and gets stuck.
        ctrl = AutoGainController(exposure=4.0, gain=400, bit_depth=16)
        pix = _uniform(4095.0, bit_depth=12)  # genuinely saturated 12-bit frame
        ctrl.update(pix)  # bug reproduction: no bit_depth kwarg
        assert ctrl.exposure == pytest.approx(4.0)  # stuck at max — the bug
        assert ctrl.gain == 400  # stuck at max — the bug
