"""Unit tests for CollimationFrameArchive."""
import json
import pytest
import numpy as np
from astropy.io import fits

from smart_telescope.domain.frame import FitsFrame
from smart_telescope.services.collimation.frame_archive import CollimationFrameArchive


def _frame(width: int = 100, height: int = 80) -> FitsFrame:
    pixels = np.zeros((height, width), dtype=np.float32)
    pixels[40, 50] = 1000.0
    return FitsFrame(pixels=pixels, header=fits.Header(), exposure_seconds=2.0)


def _save(archive: CollimationFrameArchive, session_id: str, idx: int = 1,
          state: str = "measure_donut") -> str | None:
    return archive.save_frame(
        session_id=session_id,
        state=state,
        frame_index=idx,
        captured_at="2026-01-01T00:00:00+00:00",
        exposure_s=2.0,
        gain=100,
        bit_depth=16,
        ref_x=50.0,
        ref_y=40.0,
        raw_frame=_frame(),
        analysis={"reason": "ok", "error_x_px": 1.5},
    )


def test_save_and_load_frame(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("s1")
    stem = _save(archive, "s1")
    assert stem == "measure_donut_0001"
    loaded = archive.load_frame("s1", stem)
    assert loaded.width == 100
    assert loaded.height == 80


def test_sidecar_content(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("s2")
    _save(archive, "s2")
    sidecar = archive.load_sidecar("s2", "measure_donut_0001")
    assert sidecar["state"] == "measure_donut"
    assert sidecar["analysis"]["error_x_px"] == 1.5
    assert sidecar["ref_x"] == 50.0
    assert sidecar["bit_depth"] == 16


def test_max_frames_cap(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=2)
    archive.new_session("s3")
    results = [_save(archive, "s3", idx=i + 1) for i in range(3)]
    assert results[0] is not None
    assert results[1] is not None
    assert results[2] is None   # over cap


def test_list_sessions(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    for sid in ["sess-a", "sess-b"]:
        archive.new_session(sid)
        _save(archive, sid)
    sessions = archive.list_sessions()
    assert len(sessions) == 2
    assert all("session_id" in s for s in sessions)
    assert all(s["frame_count"] == 1 for s in sessions)


def test_list_frames(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("s4")
    for i in range(3):
        _save(archive, "s4", idx=i + 1)
    frames = archive.list_frames("s4")
    assert len(frames) == 3
    assert frames[0]["frame_stem"] == "measure_donut_0001"
    assert frames[0]["state"] == "measure_donut"


def test_list_sessions_empty_dir(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    assert archive.list_sessions() == []


def test_load_missing_frame_raises(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("s5")
    with pytest.raises(FileNotFoundError):
        archive.load_frame("s5", "measure_donut_0099")


def test_save_tag_creates_json_only_entry(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    stem = archive.save_tag("s3_today", "goto", {"ra": 5.588, "dec": -5.39, "target": "M42"})
    assert stem is not None
    assert stem.startswith("goto_")
    json_path = tmp_path / "arc" / "s3_today" / f"{stem}.json"
    assert json_path.exists()
    sidecar = json.loads(json_path.read_text(encoding="utf-8"))
    assert sidecar["type"] == "goto"
    assert sidecar["ra"] == 5.588
    assert "tagged_at" in sidecar
    fits_path = tmp_path / "arc" / "s3_today" / f"{stem}.fits"
    assert not fits_path.exists()


def test_save_tag_appears_in_list_sessions(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.save_tag("s3_today", "solve", {"ra": 1.0, "dec": 2.0})
    sessions = archive.list_sessions()
    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "s3_today"
    assert sessions[0]["frame_count"] == 1
    assert "solve" in sessions[0]["state_counts"]


def test_save_tag_appears_in_list_frames(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    stem = archive.save_tag("s3_today", "af", {"best_position": 1234, "metric_gain": 5.2})
    frames = archive.list_frames("s3_today")
    assert len(frames) == 1
    assert frames[0]["frame_stem"] == stem
    assert frames[0]["has_fits"] is False
    assert frames[0]["state"] == "af"


def test_list_frames_has_fits_flag_for_fits_entries(tmp_path):
    archive = CollimationFrameArchive(tmp_path / "arc", max_frames_per_session=50)
    archive.new_session("mixed")
    _save(archive, "mixed", idx=1)
    archive.save_tag("mixed", "goto", {"ra": 0.0})
    frames = archive.list_frames("mixed")
    assert len(frames) == 2
    fits_entry = next(f for f in frames if f["has_fits"])
    tag_entry = next(f for f in frames if not f["has_fits"])
    assert fits_entry["state"] == "measure_donut"
    assert tag_entry["state"] == "goto"
