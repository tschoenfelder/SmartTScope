"""Unit tests for domain/collimation_session.py."""
from __future__ import annotations

import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

from smart_telescope.domain.bahtinov import CrossingAnalysisResult, SpikeLine
from smart_telescope.domain.collimation_session import (
    CaptureOutcome,
    CollimationConfig,
    CollimationSession,
    CollimationStatus,
    CollimationVerdict,
    PositionResult,
)
from smart_telescope.workflow.goto_center import CenterResult


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_analysis(
    focus_error_px: float = 0.5,
    crossing_error_rms_px: float = 1.0,
    detection_confidence: float = 0.9,
) -> CrossingAnalysisResult:
    spike = SpikeLine(a=1.0, b=0.0, c=0.0, angle_deg=0.0, confidence=0.9)
    return CrossingAnalysisResult(
        object_center_px=(100.0, 100.0),
        lines=[spike, spike, spike],
        common_crossing_point_px=(100.0, 100.0),
        pairwise_intersections_px=[(99.0, 99.0), (100.0, 101.0), (101.0, 100.0)],
        crossing_error_rms_px=crossing_error_rms_px,
        crossing_error_max_px=crossing_error_rms_px * 1.5,
        focus_error_px=focus_error_px,
        detection_confidence=detection_confidence,
    )


_CENTER_OK   = CenterResult(success=True,  final_ra=1.0, final_dec=10.0, iterations=1, offset_arcmin=0.5)
_CENTER_FAIL = CenterResult(success=False, final_ra=1.0, final_dec=10.0, iterations=3, offset_arcmin=999.0, error="solve failed")


@pytest.fixture
def camera():
    cam = MagicMock()
    cam.capture.return_value = MagicMock(pixels=np.zeros((64, 64), dtype=np.float32))
    return cam


@pytest.fixture
def mount():
    return MagicMock()


@pytest.fixture
def solver():
    return MagicMock()


# ── state machine: initial ────────────────────────────────────────────────────

def test_initial_state():
    session = CollimationSession()
    assert session.status == CollimationStatus.IDLE
    assert session.results == []
    assert session.current_position_index == 0
    assert session.verdict == CollimationVerdict(passed=None, positions_passed=0)


# ── start() ───────────────────────────────────────────────────────────────────

async def test_start_success(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    session = CollimationSession()
    ok = await session.start(camera, mount, solver, 1.0, 10.0)
    assert ok is True
    assert session.status == CollimationStatus.WAITING_FOR_WHEEL
    assert session.current_position_index == 0


async def test_start_failure(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_FAIL,
    )
    session = CollimationSession()
    ok = await session.start(camera, mount, solver, 1.0, 10.0)
    assert ok is False
    assert session.status == CollimationStatus.FAILED


async def test_start_resets_previous_results(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(analyze=MagicMock(return_value=_make_analysis())),
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)
    await session.capture_position()
    assert len(session.results) == 1

    # Second start — results cleared
    await session.start(camera, mount, solver, 1.0, 10.0)
    assert session.results == []
    assert session.current_position_index == 0


# ── capture_position() ────────────────────────────────────────────────────────

async def test_capture_wrong_state_raises(camera, mount, solver):
    session = CollimationSession()
    # Still IDLE — should raise
    with pytest.raises(RuntimeError, match="expected WAITING_FOR_WHEEL"):
        await session.capture_position()


async def _started_session(mocker, camera, mount, solver) -> CollimationSession:
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)
    return session


async def test_capture_position_done(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(analyze=MagicMock(return_value=_make_analysis())),
    )
    outcome = await session.capture_position()

    assert not outcome.low_confidence
    assert outcome.result is not None
    assert outcome.result.position_index == 0
    assert outcome.result.angle_label == "0°"
    assert outcome.result.passed is True
    assert session.status == CollimationStatus.POSITION_DONE
    assert session.current_position_index == 1
    assert len(session.results) == 1


async def test_capture_low_confidence_stays_waiting(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(
            analyze=MagicMock(return_value=_make_analysis(detection_confidence=0.3))
        ),
    )
    outcome = await session.capture_position()

    assert outcome.low_confidence is True
    assert outcome.result is None
    assert session.status == CollimationStatus.WAITING_FOR_WHEEL
    assert session.current_position_index == 0  # not advanced
    assert session.results == []


async def test_capture_bahtinov_valueerror_treated_as_low_confidence(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(
            analyze=MagicMock(side_effect=ValueError("fewer than 3 spikes"))
        ),
    )
    outcome = await session.capture_position()

    assert outcome.low_confidence is True
    assert outcome.error is not None
    assert session.status == CollimationStatus.WAITING_FOR_WHEEL


async def test_retry_after_low_confidence(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    analyzer_mock = MagicMock(analyze=MagicMock(
        side_effect=[
            _make_analysis(detection_confidence=0.2),  # first attempt: low confidence
            _make_analysis(detection_confidence=0.95),  # retry: OK
        ]
    ))
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=analyzer_mock,
    )
    outcome1 = await session.capture_position()
    assert outcome1.low_confidence is True

    outcome2 = await session.capture_position()
    assert not outcome2.low_confidence
    assert outcome2.result is not None
    assert session.status == CollimationStatus.POSITION_DONE


# ── angle labels ──────────────────────────────────────────────────────────────

async def test_angle_labels_cycle(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(analyze=MagicMock(return_value=_make_analysis())),
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)

    assert session.current_angle_label == "0°"
    await session.capture_position()
    assert session.current_angle_label == "120°"

    # advance to next
    session._status = CollimationStatus.POSITION_DONE  # fast-forward for label check
    await session.next_position()
    assert session.current_angle_label == "120°"


# ── ALL_DONE and verdict ──────────────────────────────────────────────────────

async def _run_full_session(
    mocker,
    camera,
    mount,
    solver,
    analyses: list[CrossingAnalysisResult],
) -> CollimationSession:
    """Helper: start + capture 3 positions with given analyses."""
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(analyze=MagicMock(side_effect=analyses)),
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)

    for i in range(3):
        outcome = await session.capture_position()
        assert not outcome.low_confidence, f"position {i} unexpected low_confidence"
        if i < 2:
            assert session.status == CollimationStatus.POSITION_DONE
            await session.next_position()

    return session


async def test_all_done_after_three_captures(mocker, camera, mount, solver):
    session = await _run_full_session(
        mocker, camera, mount, solver,
        analyses=[_make_analysis()] * 3,
    )
    assert session.status == CollimationStatus.ALL_DONE
    assert len(session.results) == 3


async def test_verdict_all_pass(mocker, camera, mount, solver):
    session = await _run_full_session(
        mocker, camera, mount, solver,
        analyses=[_make_analysis(focus_error_px=0.3)] * 3,
    )
    v = session.verdict
    assert v.passed is True
    assert v.positions_passed == 3


async def test_verdict_partial_fail(mocker, camera, mount, solver):
    analyses = [
        _make_analysis(focus_error_px=0.3),            # pass
        _make_analysis(focus_error_px=5.0),             # fail (> 1.5 px threshold)
        _make_analysis(focus_error_px=0.3),             # pass
    ]
    session = await _run_full_session(mocker, camera, mount, solver, analyses=analyses)
    v = session.verdict
    assert v.passed is False
    assert v.positions_passed == 2


async def test_verdict_none_mid_run(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(analyze=MagicMock(return_value=_make_analysis())),
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)
    await session.capture_position()  # 1/3 done

    v = session.verdict
    assert v.passed is None
    assert v.positions_passed == 1


# ── threshold enforcement ─────────────────────────────────────────────────────

async def test_focus_error_above_threshold_fails(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    config = CollimationConfig(focus_error_threshold_px=1.5)
    session._config = config
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(
            analyze=MagicMock(return_value=_make_analysis(focus_error_px=2.0))
        ),
    )
    outcome = await session.capture_position()
    assert outcome.result is not None
    assert outcome.result.passed is False


async def test_focus_error_at_threshold_passes(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(
            analyze=MagicMock(return_value=_make_analysis(focus_error_px=1.5))
        ),
    )
    outcome = await session.capture_position()
    assert outcome.result is not None
    assert outcome.result.passed is True


async def test_crossing_error_above_threshold_fails(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(
            analyze=MagicMock(
                return_value=_make_analysis(focus_error_px=0.5, crossing_error_rms_px=4.0)
            )
        ),
    )
    outcome = await session.capture_position()
    assert outcome.result is not None
    assert outcome.result.passed is False


async def test_negative_focus_error_uses_abs(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(
            analyze=MagicMock(return_value=_make_analysis(focus_error_px=-2.0))
        ),
    )
    outcome = await session.capture_position()
    assert outcome.result is not None
    assert outcome.result.passed is False  # abs(-2.0) > 1.5


# ── recenter() / next_position() ─────────────────────────────────────────────

async def test_recenter_success(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)
    ok = await session.recenter()
    assert ok is True


async def test_recenter_failure(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        side_effect=[_CENTER_OK, _CENTER_FAIL],
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)
    ok = await session.recenter()
    assert ok is False


async def test_next_position_advances_to_waiting(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(analyze=MagicMock(return_value=_make_analysis())),
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)
    await session.capture_position()
    assert session.status == CollimationStatus.POSITION_DONE

    await session.next_position()
    assert session.status == CollimationStatus.WAITING_FOR_WHEEL


async def test_next_position_wrong_state_raises(mocker, camera, mount, solver):
    mocker.patch(
        "smart_telescope.domain.collimation_session.goto_and_center",
        new_callable=AsyncMock,
        return_value=_CENTER_OK,
    )
    session = CollimationSession()
    await session.start(camera, mount, solver, 1.0, 10.0)
    # Still in WAITING_FOR_WHEEL, not POSITION_DONE
    with pytest.raises(RuntimeError, match="expected POSITION_DONE"):
        await session.next_position()


# ── position result metadata ──────────────────────────────────────────────────

async def test_position_result_has_iso_timestamp(mocker, camera, mount, solver):
    session = await _started_session(mocker, camera, mount, solver)
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(analyze=MagicMock(return_value=_make_analysis())),
    )
    outcome = await session.capture_position()
    assert outcome.result is not None
    # ISO-8601 string: ends with +00:00 or Z
    ts = outcome.result.captured_at
    assert "T" in ts


async def test_position_result_stores_analysis(mocker, camera, mount, solver):
    analysis = _make_analysis(focus_error_px=0.8, crossing_error_rms_px=1.2)
    session = await _started_session(mocker, camera, mount, solver)
    mocker.patch(
        "smart_telescope.domain.collimation_session.BahtinovAnalyzer",
        return_value=MagicMock(analyze=MagicMock(return_value=analysis)),
    )
    outcome = await session.capture_position()
    assert outcome.result is not None
    assert outcome.result.analysis.focus_error_px == pytest.approx(0.8)
    assert outcome.result.analysis.crossing_error_rms_px == pytest.approx(1.2)
