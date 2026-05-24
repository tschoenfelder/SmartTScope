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
