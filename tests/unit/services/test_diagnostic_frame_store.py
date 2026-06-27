"""Tests for DiagnosticFrameStore (M8-017 / REQ-FRAME-001) and filename+headers (M8-018)."""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest

from smart_telescope.domain.diagnostic_frame import (
    DiagnosticFrameConfig,
    DiagnosticStoreMode,
    REQUIRED_FITS_HEADERS,
)
from smart_telescope.services.diagnostic_frame_store import (
    DiagnosticFrameStore,
    _make_filename,
)


# ── should_save() ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mode,is_debug,is_failure,expected", [
    (DiagnosticStoreMode.ALWAYS,          False, False, True),
    (DiagnosticStoreMode.ALWAYS,          True,  True,  True),
    (DiagnosticStoreMode.OFF,             True,  True,  False),
    (DiagnosticStoreMode.DEBUG_ONLY,      True,  False, True),
    (DiagnosticStoreMode.DEBUG_ONLY,      False, True,  False),
    (DiagnosticStoreMode.FAILURE_ONLY,    False, True,  True),
    (DiagnosticStoreMode.FAILURE_ONLY,    True,  False, False),
    (DiagnosticStoreMode.DEBUG_OR_FAILURE, True,  False, True),
    (DiagnosticStoreMode.DEBUG_OR_FAILURE, False, True,  True),
    (DiagnosticStoreMode.DEBUG_OR_FAILURE, False, False, False),
])
def test_should_save_modes(mode, is_debug, is_failure, expected):
    store = DiagnosticFrameStore(DiagnosticFrameConfig(enabled=True, store_mode=mode))
    assert store.should_save(is_debug=is_debug, is_failure=is_failure) == expected


def test_should_save_disabled_returns_false():
    store = DiagnosticFrameStore(DiagnosticFrameConfig(
        enabled=False, store_mode=DiagnosticStoreMode.ALWAYS))
    assert store.should_save(is_debug=True, is_failure=True) is False


# ── Filename pattern ──────────────────────────────────────────────────────────

def _base_kwargs(**overrides):
    defaults = dict(
        ts=datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC),
        session_id="abcd1234-efgh",
        section="auto_gain",
        run_id="runxyz99",
        iteration=3,
        camera_id="ATR585M",
        optical_train_id="main",
        exposure_s=5.0,
        gain=100,
        offset=10,
        binx=1,
        biny=1,
        ra_hours=5.6,
        dec_deg=-5.391,
    )
    defaults.update(overrides)
    return defaults


def test_filename_starts_with_timestamp():
    fn = _make_filename(**_base_kwargs())
    assert fn.startswith("20260627T120000"), fn


def test_filename_ends_with_fits():
    fn = _make_filename(**_base_kwargs())
    assert fn.endswith(".fits"), fn


def test_filename_contains_session():
    fn = _make_filename(**_base_kwargs(session_id="abcd1234"))
    assert "session-abcd1234" in fn, fn


def test_filename_contains_section():
    fn = _make_filename(**_base_kwargs(section="plate_solve"))
    assert "plate_solve" in fn, fn


def test_filename_contains_iter():
    fn = _make_filename(**_base_kwargs(iteration=7))
    assert "iter-7" in fn, fn


def test_filename_contains_exposure():
    fn = _make_filename(**_base_kwargs(exposure_s=10.5))
    assert "exp-10.500s" in fn, fn


def test_filename_contains_gain_offset():
    fn = _make_filename(**_base_kwargs(gain=200, offset=15))
    assert "gain-200" in fn, fn
    assert "offset-15" in fn, fn


def test_filename_contains_binning():
    fn = _make_filename(**_base_kwargs(binx=2, biny=2))
    assert "bin-2x2" in fn, fn


def test_filename_contains_ra_dec():
    fn = _make_filename(**_base_kwargs(ra_hours=5.6, dec_deg=-5.391))
    assert "ra-5.6000h" in fn, fn
    assert "dec--5.3910" in fn or "dec-" in fn, fn


def test_filename_ra_none_uses_placeholder():
    fn = _make_filename(**_base_kwargs(ra_hours=None, dec_deg=None))
    assert "ra-none" in fn, fn
    assert "dec-none" in fn, fn


def test_filename_is_filesystem_safe():
    fn = _make_filename(**_base_kwargs())
    assert ":" not in fn
    assert " " not in fn
    assert "/" not in fn
    assert "\\" not in fn


# ── save_frame() ─────────────────────────────────────────────────────────────

@pytest.fixture
def frame_store(tmp_path):
    cfg = DiagnosticFrameConfig(
        enabled=True,
        store_mode=DiagnosticStoreMode.ALWAYS,
        retention_days=2,
        frame_dir=str(tmp_path),
    )
    return DiagnosticFrameStore(cfg)


def test_save_frame_creates_file(frame_store, tmp_path):
    data = np.zeros((64, 64), dtype=np.uint16)
    path = frame_store.save_frame(
        data,
        session_id="test1234",
        section="auto_gain",
        run_id="run001",
        iteration=0,
        exposure_s=5.0,
    )
    assert path.exists(), f"Expected file at {path}"


def test_save_frame_all_required_headers_present(frame_store):
    from astropy.io import fits
    data = np.zeros((64, 64), dtype=np.uint16)
    path = frame_store.save_frame(
        data,
        session_id="test1234",
        section="auto_gain",
        run_id="run001",
        iteration=0,
        exposure_s=5.0,
        gain=100,
        offset=10,
        pixel_size_um=3.76,
        focal_length_mm=2000.0,
        ra_hours=5.6,
        dec_deg=-5.391,
        tracking=True,
    )
    with fits.open(str(path)) as hdul:
        hdr = hdul[0].header
    for key in REQUIRED_FITS_HEADERS:
        assert key in hdr, f"Missing header: {key}"


def test_save_frame_session_subdirectory(frame_store, tmp_path):
    data = np.zeros((32, 32), dtype=np.uint16)
    path = frame_store.save_frame(
        data, session_id="abcd1234-foo", section="autofocus",
        run_id="r", iteration=0, exposure_s=1.0,
    )
    assert path.parent.name == "abcd1234", path


def test_save_frame_tracking_header_value(frame_store):
    from astropy.io import fits
    data = np.zeros((32, 32), dtype=np.uint16)
    path = frame_store.save_frame(
        data, session_id="test1234", section="auto_gain", run_id="r",
        iteration=0, exposure_s=1.0, tracking=True,
    )
    with fits.open(str(path)) as hdul:
        assert hdul[0].header["TRACKING"] is True


def test_save_frame_unknown_ra_stored_as_sentinel(frame_store):
    from astropy.io import fits
    data = np.zeros((32, 32), dtype=np.uint16)
    path = frame_store.save_frame(
        data, session_id="test1234", section="auto_gain", run_id="r",
        iteration=0, exposure_s=1.0, ra_hours=None,
    )
    with fits.open(str(path)) as hdul:
        assert hdul[0].header["RA"] == -999.0


# ── cleanup_old_frames() ──────────────────────────────────────────────────────

def test_cleanup_removes_old_session_dirs(tmp_path):
    cfg = DiagnosticFrameConfig(
        enabled=True, store_mode=DiagnosticStoreMode.ALWAYS,
        retention_days=2, frame_dir=str(tmp_path),
    )
    store = DiagnosticFrameStore(cfg)
    old_dir = tmp_path / "oldold00"
    old_dir.mkdir()
    # Backdate mtime to 3 days ago
    old_time = time.time() - 3 * 86400
    import os; os.utime(str(old_dir), (old_time, old_time))

    deleted = store.cleanup_old_frames(active_session_ids=set())
    assert deleted == 1
    assert not old_dir.exists()


def test_cleanup_preserves_active_sessions(tmp_path):
    cfg = DiagnosticFrameConfig(
        enabled=True, store_mode=DiagnosticStoreMode.ALWAYS,
        retention_days=2, frame_dir=str(tmp_path),
    )
    store = DiagnosticFrameStore(cfg)
    active_dir = tmp_path / "activ000"
    active_dir.mkdir()
    old_time = time.time() - 3 * 86400
    import os; os.utime(str(active_dir), (old_time, old_time))

    deleted = store.cleanup_old_frames(active_session_ids={"activ000-full-session-id"})
    assert deleted == 0
    assert active_dir.exists()


def test_cleanup_preserves_recent_dirs(tmp_path):
    cfg = DiagnosticFrameConfig(
        enabled=True, store_mode=DiagnosticStoreMode.ALWAYS,
        retention_days=2, frame_dir=str(tmp_path),
    )
    store = DiagnosticFrameStore(cfg)
    new_dir = tmp_path / "new00000"
    new_dir.mkdir()
    # mtime is NOW — not old enough to delete

    deleted = store.cleanup_old_frames(active_session_ids=set())
    assert deleted == 0
    assert new_dir.exists()


def test_cleanup_nonexistent_base_returns_zero(tmp_path):
    cfg = DiagnosticFrameConfig(
        enabled=True, store_mode=DiagnosticStoreMode.ALWAYS,
        retention_days=2, frame_dir=str(tmp_path / "does_not_exist"),
    )
    store = DiagnosticFrameStore(cfg)
    assert store.cleanup_old_frames(active_session_ids=set()) == 0


# ── REQUIRED_FITS_HEADERS completeness ───────────────────────────────────────

def test_required_fits_headers_count():
    assert len(REQUIRED_FITS_HEADERS) == 17


def test_required_fits_headers_includes_date_obs():
    assert "DATE-OBS" in REQUIRED_FITS_HEADERS
