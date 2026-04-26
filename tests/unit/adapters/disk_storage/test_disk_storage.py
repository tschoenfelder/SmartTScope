"""Unit tests for DiskStorage adapter."""

from __future__ import annotations

import io
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from PIL import Image

from smart_telescope.adapters.disk_storage.storage import DiskStorage, _make_stem, _slugify

_H, _W = 32, 48


def _fits_bytes(signal: float = 5000.0) -> bytes:
    pixels = np.full((_H, _W), signal, dtype=np.float32)
    hdu = fits.PrimaryHDU(data=pixels)
    buf = io.BytesIO()
    fits.HDUList([hdu]).writeto(buf)
    return buf.getvalue()


def _session_log(
    session_id: str = "abcd1234-0000-0000-0000-000000000000",
    target: str = "M42",
    started_at: str = "2026-04-26T21:00:00+00:00",
) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "target": {"name": target, "ra": 5.58, "dec": -5.39},
        "started_at": started_at,
        "final_state": "SAVED",
    }


# ── has_free_space ────────────────────────────────────────────────────────────


class TestHasFreeSpace:
    def test_returns_true_when_free_exceeds_threshold(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path, min_free_bytes=1)
        assert s.has_free_space() is True

    def test_returns_false_when_free_below_threshold(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path, min_free_bytes=999_999_999_999)
        assert s.has_free_space() is False

    def test_free_bytes_matches_shutil(self, tmp_path: Path) -> None:
        import shutil
        s = DiskStorage(tmp_path)
        assert s.free_bytes() == shutil.disk_usage(tmp_path).free


# ── save_image ────────────────────────────────────────────────────────────────


class TestSaveImage:
    def test_returns_path_string(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        result = s.save_image(_fits_bytes(), "sess-0001")
        assert isinstance(result, str)

    def test_file_exists_on_disk(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = s.save_image(_fits_bytes(), "sess-0001")
        assert Path(path).exists()

    def test_output_is_valid_png(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = Path(s.save_image(_fits_bytes(), "sess-0001"))
        img = Image.open(path)
        assert img.format == "PNG"

    def test_dimensions_match_fits_input(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = Path(s.save_image(_fits_bytes(), "sess-0001"))
        img = Image.open(path)
        assert img.size == (_W, _H)

    def test_filename_contains_session_id_prefix(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = s.save_image(_fits_bytes(), "abcd1234-xxxx")
        assert "abcd1234" in Path(path).name

    def test_filename_ends_with_png(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = s.save_image(_fits_bytes(), "sess-0001")
        assert path.endswith(".png")

    def test_filename_matches_naming_spec(self, tmp_path: Path) -> None:
        # Pattern: YYYYMMDD_HHMMSSZ_{8-char-id}.png
        s = DiskStorage(tmp_path)
        path = Path(s.save_image(_fits_bytes(), "abcd1234-rest"))
        assert re.match(r"\d{8}_\d{6}Z_abcd1234\.png", path.name)

    def test_output_dir_created_if_missing(self, tmp_path: Path) -> None:
        nested = tmp_path / "deep" / "nested"
        s = DiskStorage(nested)
        s.save_image(_fits_bytes(), "sess-0001")
        assert nested.exists()


# ── save_log ──────────────────────────────────────────────────────────────────


class TestSaveLog:
    def test_returns_path_string(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        result = s.save_log(_session_log(), "abcd1234-xxxx")
        assert isinstance(result, str)

    def test_file_exists_on_disk(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = s.save_log(_session_log(), "abcd1234-xxxx")
        assert Path(path).exists()

    def test_json_is_valid_and_matches_input(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        log = _session_log(target="M42")
        path = Path(s.save_log(log, "abcd1234-xxxx"))
        parsed = json.loads(path.read_text(encoding="utf-8"))
        assert parsed["target"]["name"] == "M42"
        assert parsed["final_state"] == "SAVED"

    def test_filename_contains_session_id_prefix(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = s.save_log(_session_log(), "abcd1234-xxxx")
        assert "abcd1234" in Path(path).name

    def test_filename_ends_with_json(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = s.save_log(_session_log(), "abcd1234-xxxx")
        assert path.endswith(".json")

    def test_filename_contains_target_slug(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        path = s.save_log(_session_log(target="Orion Nebula"), "abcd1234-xxxx")
        assert "orion_nebula" in Path(path).name

    def test_filename_uses_started_at_timestamp(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        log = _session_log(started_at="2026-04-26T21:00:00+00:00")
        path = Path(s.save_log(log, "abcd1234-xxxx"))
        assert "20260426_210000Z" in path.name

    def test_filename_matches_naming_spec(self, tmp_path: Path) -> None:
        # Pattern: YYYYMMDD_HHMMSSZ_{8-char-id}_{target_slug}.json
        s = DiskStorage(tmp_path)
        path = Path(s.save_log(_session_log(target="M42"), "abcd1234-xxxx"))
        assert re.match(r"\d{8}_\d{6}Z_abcd1234_m42\.json", path.name)

    def test_missing_started_at_falls_back_to_now(self, tmp_path: Path) -> None:
        s = DiskStorage(tmp_path)
        log: dict[str, Any] = {"final_state": "SAVED", "target": {"name": "M42"}}
        path = s.save_log(log, "abcd1234-xxxx")
        assert Path(path).exists()


# ── helpers ───────────────────────────────────────────────────────────────────


class TestHelpers:
    def test_make_stem_format(self) -> None:
        dt = datetime(2026, 4, 26, 21, 0, 0, tzinfo=UTC)
        stem = _make_stem("abcd1234-rest", started_at=dt)
        assert stem == "20260426_210000Z_abcd1234"

    def test_make_stem_uses_now_when_no_dt(self) -> None:
        stem = _make_stem("abcd1234-rest")
        assert re.match(r"\d{8}_\d{6}Z_abcd1234", stem)

    def test_slugify_lowercases(self) -> None:
        assert _slugify("M42") == "m42"

    def test_slugify_replaces_spaces(self) -> None:
        assert _slugify("Orion Nebula") == "orion_nebula"

    def test_slugify_strips_special_chars(self) -> None:
        assert _slugify("NGC-1499 (Calif.)") == "ngc_1499_calif"
