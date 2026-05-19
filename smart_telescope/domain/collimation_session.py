"""Tri-Bahtinov collimation session domain service."""
from __future__ import annotations

import asyncio
import dataclasses
import enum
from datetime import datetime, timezone

from .bahtinov import BahtinovAnalyzer, CrossingAnalysisResult
from ..ports.camera import CameraPort
from ..ports.mount import MountPort
from ..ports.solver import SolverPort
from ..workflow.goto_center import goto_and_center


_ANGLE_LABELS: tuple[str, ...] = ("0°", "120°", "240°")
_CAPTURE_EXPOSURE_S: float = 5.0


@dataclasses.dataclass(frozen=True)
class CollimationConfig:
    n_positions: int = 3
    focus_error_threshold_px: float = 1.5
    crossing_error_threshold_px: float = 3.0
    min_detection_confidence: float = 0.6


@dataclasses.dataclass(frozen=True)
class PositionResult:
    position_index: int
    angle_label: str
    analysis: CrossingAnalysisResult
    passed: bool
    captured_at: str  # ISO-8601


@dataclasses.dataclass(frozen=True)
class CollimationVerdict:
    passed: bool | None  # None until all positions are done
    positions_passed: int


class CollimationStatus(str, enum.Enum):
    IDLE = "IDLE"
    ACQUIRING_STAR = "ACQUIRING_STAR"
    WAITING_FOR_WHEEL = "WAITING_FOR_WHEEL"
    CAPTURING = "CAPTURING"
    ANALYSING = "ANALYSING"
    POSITION_DONE = "POSITION_DONE"
    ALL_DONE = "ALL_DONE"
    FAILED = "FAILED"


@dataclasses.dataclass
class CaptureOutcome:
    """Returned by CollimationSession.capture_position()."""
    low_confidence: bool = False
    result: PositionResult | None = None
    error: str | None = None


class CollimationSession:
    """Orchestrates a three-position Bahtinov collimation run.

    Typical lifecycle:
        await session.start(camera, mount, solver, ra, dec)   # ACQUIRING_STAR → WAITING_FOR_WHEEL
        outcome = await session.capture_position()            # → POSITION_DONE
        await session.next_position()                         # re-center → WAITING_FOR_WHEEL
        outcome = await session.capture_position()            # → POSITION_DONE
        await session.next_position()
        outcome = await session.capture_position()            # → ALL_DONE
        verdict  = session.verdict
    """

    def __init__(self, config: CollimationConfig | None = None) -> None:
        self._config = config or CollimationConfig()
        self._status = CollimationStatus.IDLE
        self._results: list[PositionResult] = []
        self._current_index: int = 0

        self._camera: CameraPort | None = None
        self._mount: MountPort | None = None
        self._solver: SolverPort | None = None
        self._star_ra: float = 0.0
        self._star_dec: float = 0.0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def config(self) -> CollimationConfig:
        return self._config

    @property
    def status(self) -> CollimationStatus:
        return self._status

    @property
    def results(self) -> list[PositionResult]:
        return list(self._results)

    @property
    def current_position_index(self) -> int:
        return self._current_index

    @property
    def current_angle_label(self) -> str:
        idx = self._current_index
        return _ANGLE_LABELS[idx] if idx < len(_ANGLE_LABELS) else ""

    @property
    def verdict(self) -> CollimationVerdict:
        n_passed = sum(1 for r in self._results if r.passed)
        if self._status == CollimationStatus.ALL_DONE:
            return CollimationVerdict(
                passed=(n_passed == self._config.n_positions),
                positions_passed=n_passed,
            )
        return CollimationVerdict(passed=None, positions_passed=n_passed)

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def start(
        self,
        camera: CameraPort,
        mount: MountPort,
        solver: SolverPort,
        star_ra: float,
        star_dec: float,
    ) -> bool:
        """Slew to the target star, plate-solve, and center.

        Transitions: IDLE → ACQUIRING_STAR → WAITING_FOR_WHEEL (success)
                                           → FAILED              (failure)
        Returns True on success.
        """
        self._camera = camera
        self._mount = mount
        self._solver = solver
        self._star_ra = star_ra
        self._star_dec = star_dec
        self._results = []
        self._current_index = 0
        self._status = CollimationStatus.ACQUIRING_STAR

        center = await goto_and_center(mount, camera, solver, star_ra, star_dec)
        if center.success:
            self._status = CollimationStatus.WAITING_FOR_WHEEL
            return True
        self._status = CollimationStatus.FAILED
        return False

    async def capture_position(self) -> CaptureOutcome:
        """Capture one frame for the current wheel position and analyse it.

        Valid in:  WAITING_FOR_WHEEL
        On low-confidence: stays in WAITING_FOR_WHEEL, returns CaptureOutcome(low_confidence=True).
        On success: stores PositionResult, advances index.
          - If more positions remain: → POSITION_DONE
          - If last position:         → ALL_DONE
        """
        if self._status != CollimationStatus.WAITING_FOR_WHEEL:
            raise RuntimeError(
                f"capture_position() called in state {self._status}; expected WAITING_FOR_WHEEL"
            )
        if self._camera is None:
            raise RuntimeError("No camera — call start() first")

        self._status = CollimationStatus.CAPTURING
        frame = await asyncio.to_thread(self._camera.capture, _CAPTURE_EXPOSURE_S)

        self._status = CollimationStatus.ANALYSING
        analyzer = BahtinovAnalyzer()
        try:
            analysis: CrossingAnalysisResult = await asyncio.to_thread(
                analyzer.analyze, frame.pixels
            )
        except ValueError as exc:
            self._status = CollimationStatus.WAITING_FOR_WHEEL
            return CaptureOutcome(low_confidence=True, error=str(exc))

        if analysis.detection_confidence < self._config.min_detection_confidence:
            self._status = CollimationStatus.WAITING_FOR_WHEEL
            return CaptureOutcome(low_confidence=True)

        passed = (
            abs(analysis.focus_error_px) <= self._config.focus_error_threshold_px
            and analysis.crossing_error_rms_px <= self._config.crossing_error_threshold_px
        )
        result = PositionResult(
            position_index=self._current_index,
            angle_label=_ANGLE_LABELS[self._current_index],
            analysis=analysis,
            passed=passed,
            captured_at=datetime.now(tz=timezone.utc).isoformat(),
        )
        self._results.append(result)
        self._current_index += 1

        if self._current_index >= self._config.n_positions:
            self._status = CollimationStatus.ALL_DONE
        else:
            self._status = CollimationStatus.POSITION_DONE

        return CaptureOutcome(result=result)

    async def recenter(self) -> bool:
        """Re-run plate-solve + correction. Returns True on success."""
        if self._mount is None or self._camera is None or self._solver is None:
            raise RuntimeError("No camera/mount/solver — call start() first")
        center = await goto_and_center(
            self._mount, self._camera, self._solver, self._star_ra, self._star_dec
        )
        return center.success

    async def next_position(self) -> bool:
        """Re-center the star and advance to WAITING_FOR_WHEEL for the next position.

        Valid in: POSITION_DONE
        Re-centering failure is non-fatal — warns but still advances.
        Returns True if re-centering succeeded.
        """
        if self._status != CollimationStatus.POSITION_DONE:
            raise RuntimeError(
                f"next_position() called in state {self._status}; expected POSITION_DONE"
            )
        success = await self.recenter()
        self._status = CollimationStatus.WAITING_FOR_WHEEL
        return success
