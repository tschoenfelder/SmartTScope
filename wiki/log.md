# Wiki Log

Append-only record of all wiki operations.

---

## 2026-05-17 — BUG-019, BUG-022, R4-001..004

**What changed:**

- `api/focuser.py` (BUG-019): Moved the 300 ms started-check sleep outside
  `coordinator.focuser_command()` lock.  The lock is now held only for the
  serial exchange (~50-100 ms), so rapid nudge presses queue behind the command
  issuance rather than the check.  Removed the now-redundant
  `_check_focuser_started` background thread and the `threading` import.

- `static/index.html` (BUG-022):
  - Added `mountGotoAndCenter()` function — previously the GoTo card's
    Center button called this function which was never defined, causing a
    `ReferenceError` on every click.
  - Updated `onPreviewCamChange(idx)` to stop and restart the preview
    WebSocket when the camera is changed, preventing "WebSocket data transfer
    error" when autogain runs after a camera switch.

- `config.py` (R4-003): Added `focuser` and `pixel_scale_arcsec` fields to
  `OpticalTrainSpec`; updated `_parse_optical_trains` to read them.

- `services/optical_train_registry.py` (R4-001/002): New `OpticalTrain`
  dataclass and `OpticalTrainRegistry` class.  `from_config()` loads trains
  from the TOML config, validates telescope and camera-role references,
  computes effective focal length (telescope × reducer_factor), and derives
  pixel scale from camera model profiles or falls back to the global
  `PIXEL_SCALE_ARCSEC`.

- `runtime.py` + `api/deps.py` (R4-003): `RuntimeContext.get_optical_train_registry()`
  builds the registry lazily; `deps.get_optical_train_registry()` exposes it as
  a FastAPI dependency.

- `api/optical_trains.py` + `app.py` (R4-003): New `GET /api/optical_trains`
  and `GET /api/optical_trains/{name}` endpoints listing all configured trains.

- `templates/config.toml`: Documented `focuser` and `pixel_scale_arcsec` fields
  in the optical_trains example sections.

- `tests/unit/services/test_optical_train_registry.py`: 28 tests covering
  3-train and 2-train setups, reducer scaling, explicit vs computed pixel scale,
  validation errors (unknown telescope, unknown camera role, multiple errors),
  and all query methods.

---

## 2026-05-16 — Collimation Phase 13 — Replay and Test Infrastructure

**What changed:**

- `smart_telescope/services/collimation/frame_factories.py` (NEW): `gaussian_star(H, W, cx, cy, fwhm_px, peak_adu, bg_adu)` — Gaussian PSF at given centre/FWHM; `donut_ring(H, W, outer_cx, outer_cy, outer_r, inner_r, error_x, error_y, ...)` — bright ring with sigmoid-smoothed inner hole offset for collimation error simulation; `focus_sequence(...)` — helper to build a list of frames with varying FWHM.
- `smart_telescope/adapters/replay/camera.py` (UPDATED): Added `ReplayCameraAdapter(CameraPort)` alongside existing `ReplayCamera`. Serves in-memory NumPy float32 arrays as `FitsFrame` objects; supports `cycle=True/False`, `reset()`, `frame_index` property, all required `CameraPort` abstract methods.
- `smart_telescope/services/collimation/assistant.py` (UPDATED): `_handle_final_refocus` wired to real `FWHMFocusController` — captures frame, normalises, detects star FWHM, drives `CollimationFocuserControl.move_focus_relative`, records focus status in session report builder, transitions to `MASKLESS_VALIDATION` on convergence, `FAILED` on star lost.
- `tests/unit/services/test_frame_factories.py` (NEW): 17 tests — shape/dtype/peak-location/background for `gaussian_star`, shape/dtype/ring-brightness/background/error-offset/symmetry for `donut_ring`, length/element-type for `focus_sequence`, 3 round-trip tests: detect_star can detect gaussian frames, reports reasonable FWHM, reports correct position.
- `tests/unit/services/test_replay_camera.py` (NEW): 14 tests — empty-frames raises, connect, bit-depth; first-frame pixels, ordering, frame-index increment, exposure-seconds; cycling, exhaustion-raises, reset; exposure/gain setters, logical-name, serial, temperature.
- `tests/unit/services/test_state_machine.py` (NEW): 35 tests — initial state; all valid forward transitions (idle→precheck, precheck→select_star, rough→donut, final→validation, validation→complete/fine); invalid transitions (raises InvalidTransitionError, error message contents); pause/resume/reset (stores prev state, restores on resume, clears prev, raises in idle/terminal/non-paused); predicates (is_terminal, is_waiting_for_user, set membership); instruction text for all states.
- `tests/unit/services/test_assistant_replay.py` (NEW): 18 integration tests — initial idle state, start transitions, double-start raises, cancel resets, retry after complete; full flow reaches COMPLETE, state sequence through all USER_WAIT states, non-terminal during flow, report fields; advance from idle raises, missing coordinates stays in select_star, validation reject returns to fine; pause sets paused, resume restores, is_paused flag; final refocus records FWHM, reaches MASKLESS_VALIDATION.
- `docs/todo.md`: COL-130, COL-131 marked done; last-updated line updated.
- Test suite: 2358 tests, all pass, 87% coverage.

---

## 2026-05-16 — Collimation Phase 12 — Validation and Report

**What changed:**

- `smart_telescope/services/collimation/fwhm_focus.py` (NEW): `FWHMFocusController` implements maskless hill-climb refocus (COL-120). Algorithm: (1) Probe — try +coarse_step; if not improved try −coarse_step; if neither return "max_steps". (2) Coarse scan in improving direction until N consecutive non-improving steps. (3) Backtrack to best-FWHM position. (4) If scan direction ≠ `final_approach_direction`, insert one overshoot then one correction to eliminate backlash bias. Returns `MasklessFocusResult(reason, quality, initial_fwhm_px, best_fwhm_px, final_fwhm_px, steps_taken, frame_count)`. Quality tiers: "excellent" (≤excellent_fwhm_px), "good" (≤good_fwhm_px), "poor" (converged but above good), "failed" (non-converged).
- `smart_telescope/services/collimation/maskless_validator.py` (NEW): `MasklessValidator.assess(donut, jitter_px)` evaluates collimation quality after mask removal (COL-121). Computes `error_ratio = error_magnitude_px / mean(outer_ring.radius)`. Status: "complete" (ratio ≤ good), "acceptable_with_warning" (ratio ≤ fallback), "seeing_limited" (jitter above threshold), "failed" (above fallback or low confidence). Returns `ValidationReport(status, donut_error_px, donut_error_ratio, is_collimated, confidence, warnings)`.
- `smart_telescope/services/collimation/session_report.py` (NEW): `SessionReportBuilder` accumulates session data via `set_optical_train`, `set_camera`, `set_selected_star`, `record_rough_start/end`, `record_fine_start/end`, `record_focus_status`, `record_seeing`, `record_final_result`, `mark_cancelled`; `build()` returns immutable `CollimationSessionReport`. Report provides `to_dict()` (JSON-serialisable) and `to_text()` (human-readable ASCII summary). Overall status mapped from validation status (COL-122).
- `smart_telescope/services/collimation/assistant.py`: `CollimationAssistant.report` property now returns builder output merged with runtime state; `_new_report_builder()` helper initialises builder from config; builder reset on `start()`, cancelled on `cancel()`.
- `tests/unit/services/test_fwhm_focus.py` (NEW): 22 tests — result fields, star-lost (immediate/probe/scan), probe forward/backward direction, max_steps (no improving direction), cancellation, step/frame accounting, final-approach overshoot (inserted when direction differs) and no-overshoot (when direction matches), quality tiers (excellent/good/poor).
- `tests/unit/services/test_maskless_validator.py` (NEW): 22 tests — report fields, complete (below good ratio), acceptable_with_warning, failed (above fallback), low-confidence failure, seeing-limited status, seeing warning text, elliptical ring mean-radius calculation.
- `tests/unit/services/test_session_report.py` (NEW): 29 tests — all report fields, timing, focus fields, overall status mapping (all 5 variants), cancellation override, warnings propagation, to_dict keys, to_text content (status, profile, FWHM, star name), minimal builder defaults.
- `docs/todo.md`: COL-120, COL-121, COL-122 marked done; last-updated line updated.
- Test suite: 2267 tests, all pass, 84% coverage.

---

## 2026-05-16 — Collimation Phase 11 — Fine Focus and Fine Collimation

**What changed:**

- `smart_telescope/domain/collimation/processing/spike_decomposition.py` (NEW): `decompose_spike_errors(lines)` treats each of the 3 spike lines as the "middle" in turn, computing its signed distance from the intersection of the other two. Common focus error = mean of 3 sector errors. Per-sector residuals = error_i − common. Returns `SpikeErrorDecomposition(sector_errors_px, common_focus_error_px, residuals_px, max_residual_px, rms_residual_px)`. Key correctness insight: when three lines are concurrent at any point, all sector errors = 0 (models perfect focus at any reference position).
- `smart_telescope/services/collimation/fine_focus.py` (NEW): `FineFocusController` polls a `get_error: Callable[[], float | None]` callable (common focus error in px) and a `move_focuser: Callable[[int], None]` step function. Coarse steps until within `coarse_threshold_px`, then fine steps. At the coarse→fine transition, if the natural direction differs from `final_approach_direction`, one overshoot step is inserted so subsequent convergence comes from the correct side (backlash compensation). Returns `FineFocusResult(reason, initial_error_px, final_error_px, steps_taken, frame_count)`.
- `smart_telescope/services/collimation/fine_collimation_advisor.py` (NEW): `FineCollimationAdvisor.recommend(residuals_by_screw, smoothed)` selects the screw with the largest `|residual_px|`, determines CW/CCW direction from residual sign, and size (MEDIUM if ratio ≥ 1.5× target, else SMALL). Blocked if `seeing_limited` or `confidence < threshold` or all residuals within target. Also provides `align_residuals_to_screws(decomp, lines, calibration)` helper.
- `smart_telescope/services/collimation/contradiction_detector.py` (NEW): `ContradictionDetector.assess(smoothed, decomposition)` checks 4 indicators: (1) jitter > seeing_threshold, (2) |common_focus_error| > focus_target, (3) confidence < threshold, (4) max_residual increased since last call (stateful). Returns `ContradictionAssessment(has_contradiction, conflicting_indicators, stop_guidance, recommended_action, confidence)`. `.reset()` clears state for a new session.
- `tests/unit/domain/collimation/test_spike_decomposition.py` (NEW): 16 tests — fields, 3-value tuples, perfect collimation (zero errors/residuals/common), concurrent at non-origin (models pure defocus), single-sector shift (worst index, positive max_residual, rms ≤ max), residuals sum-to-zero invariant, residual = error − common, raises on wrong line count.
- `tests/unit/services/test_fine_focus.py` (NEW): 18 tests — result fields, convergence, initial error, star lost (first/mid), cancel, max steps, coarse/fine step usage, direction from error sign, final approach overshoot and no-overshoot.
- `tests/unit/services/test_fine_collimation_advisor.py` (NEW): 18 tests — no-recommendation (within target, seeing-limited, low confidence, empty), worst screw selection (positive/negative), turn direction, adjustment size (small/medium/never-large), confidence, reason string.
- `tests/unit/services/test_contradiction_detector.py` (NEW): 14 tests — no contradiction, seeing-limited, focus drift, low confidence, residuals worsening, no-worsening first call, reset, recommended action, confidence bounds.
- `docs/todo.md`: COL-110, COL-111, COL-112, COL-113 marked done.
- Test suite: 2194 tests, all pass.

---

## 2026-05-16 — Collimation Phase 10 — Tri-Bahtinov Fine Collimation Foundation

**What changed:**

- `smart_telescope/domain/collimation/processing/spike_detection.py` (NEW): `detect_spikes(processed, ref_center, analyzer?)` wraps `BahtinovAnalyzer.analyze()` to produce a `SpikeDetectionResult`. Reasons: "ok" (3 lines found → `SpikeMeasurement` built), "too_few_spikes" (analyzer raised `ValueError`), "no_signal" (zero confidence). Accepts an optional `analyzer` argument for dependency injection in tests.
- `smart_telescope/services/collimation/sector_mapper.py` (NEW): `SectorMapper(sector_to_screw)` records which spike line disappears when each Tri-Bahtinov blade sector is closed. `observe(label, open_lines, closed_lines)` finds the missing angle using a 10° tolerance match. `build_calibration()` sorts the 3 observed angles and assigns `sector_0_deg` / `sector_120_deg` / `sector_240_deg` in the `MaskSectorCalibration`; returns None if any sector is missing or two sectors map to the same angle (orientation mismatch).
- `smart_telescope/services/collimation/spike_smoother.py` (NEW): `SpikeSmoother(window=7, min_confidence=0.3, seeing_limited_threshold_px=3.0)` maintains a sliding deque of accepted `SpikeMeasurement` frames. `compute()` returns `SmoothedSpikeResult` with: median focus_error_px (current), moving average of most-recent half (trend), population std-dev (jitter), seeing_limited flag (jitter > threshold), frame_count, mean confidence.
- `tests/unit/domain/collimation/test_spike_detection.py` (NEW): 11 tests — result fields, ok/too_few/no_signal reasons, measurement population, offset_from_ref, confidence, crossing point, ref center storage, default analyzer.
- `tests/unit/services/test_sector_mapper.py` (NEW): 13 tests — missing-line detection, tolerance matching, two-sector observation, full calibration (3 sectors), sorted screw assignment, missing sector returns None, ambiguous duplicate angle returns None, defaults calibrated_at.
- `tests/unit/services/test_spike_smoother.py` (NEW): 19 tests — empty/all-rejected, median odd/even/single, confidence filtering (excluded/count/threshold), jitter zero/nonzero/seeing-limited/not-limited, trend average-of-recent-half/single, window eviction, partial window, reset, mean confidence.
- `docs/todo.md`: COL-100, COL-101, COL-102 marked done.
- Test suite: 2128 tests, all pass.

---

## 2026-05-16 — Collimation Phase 9 — Rough Collimation Guidance

**What changed:**

- `smart_telescope/services/collimation/collimation_advisor.py` (NEW): `CollimationAdvisor` takes a list of `ScrewCalibration` and a `DonutMeasurement`; projects the desired correction vector (–error) onto each screw's response vector; picks the screw with the largest dot product; determines CW/CCW direction; caps size at MEDIUM (never LARGE); halves confidence when screw calibration is below threshold. Returns `CollimationRecommendation` or None when already collimated or no calibration available.
- `smart_telescope/services/collimation/live_guidance.py` (NEW): `LiveGuidanceMonitor` polls a `get_measurement()` callable each settle interval while the user turns a screw. Tracks best error seen; declares "converged" when error < green_fraction × outer_radius, "worsened" after N consecutive non-improvements, "star_lost", "cancelled", or "max_frames". Returns `LiveGuidanceResult(reason, initial_error_px, final_error_px, improvement_px, frame_count)`.
- `tests/unit/services/test_collimation_advisor.py` (NEW): 18 tests — no calibration, already collimated, screw selection (x/y/three-screw), turn direction (CW/CCW), adjustment size (small/medium/never-large), confidence, reason string, custom outer_radius.
- `tests/unit/services/test_live_guidance.py` (NEW): 15 tests — result fields, convergence (threshold/improvement/frame count), worsening (consecutive non-improvement/single bad frame), star lost, cancellation, max frames, initial error propagation.
- `docs/todo.md`: COL-090, COL-091 marked done.
- Test suite: 2085 tests, all pass, 83.66% coverage.

---

## 2026-05-16 — Collimation Phase 8 — Screw Identification and Response Learning

**What changed:**

- `smart_telescope/domain/collimation/models.py`: added `ScrewAngularPosition` dataclass (screw_id, angle_deg, confidence) for hand-touch calibration results.
- `smart_telescope/domain/collimation/processing/obstruction_detection.py` (NEW): `detect_obstruction(reference, current, cx, cy)` — computes diff (reference − current), thresholds at 5σ above diff background, finds brightness-weighted centroid of shadow region, computes angle from outer ring center. Returns `ObstructionResult(shadow_center_x, shadow_center_y, angle_deg, shadow_area_px, confidence)` or None if no shadow detected.
- `smart_telescope/services/collimation/screw_mapper.py` (NEW): `ScrewResponseLearner` — accumulates before/after `DonutMeasurement` pairs per screw; converts CCW observations to CW-equivalent; averages response vectors across all observations; confidence saturates to 1.0 at 5 samples. Returns `ScrewCalibration`.
- `tests/unit/domain/collimation/test_obstruction_detection.py` (NEW): 15 tests — result fields, no-shadow (identical frames, noise only, tiny shadow), shadow detected (area, center, confidence), angle accuracy (right/left/above/below), confidence bounds.
- `tests/unit/services/test_screw_mapper.py` (NEW): 22 tests — `ScrewAngularPosition` fields, initial state, CW/CCW single observations, multiple-observation averaging, confidence growth, get_calibration/get_all, Y-axis response, magnitude.
- `docs/todo.md`: COL-080, COL-081 marked done.
- Test suite: 2052 tests, all pass, 83.49% coverage.

---

## 2026-05-16 — Collimation Phase 7 — Rough Donut Collimation

**What changed:**

- `smart_telescope/domain/collimation/processing/donut_detection.py` (NEW): `DonutAnalyzer` detects outer bright ring and inner dark shadow of a defocused C8 star. Ring mask = 10% of peak-above-background (or 3σ minimum). Centroid of ring pixels → RMS radius as inner/outer edge split point (mathematically guaranteed to lie between inner_r and outer_r). Kasa circle fit to each edge set. Error vector = inner_center − outer_center. Returns `DonutAnalysisResult` with `DonutMeasurement` or reason ("no_signal" / "no_ring_shape" / "inner_hole_unclear" / "clipped").
- `smart_telescope/services/collimation/donut_overlay.py` (NEW): `build_donut_overlay(DonutMeasurement) → DonutOverlay`. Includes outer/inner circle parameters, error vector, traffic-light status (green <2%, yellow <10%, red ≥10% of outer radius), T1/T2/T3 screw markers at 1.25× outer radius at configurable angles (default 90°, 210°, 330°).
- `tests/unit/domain/collimation/test_donut_detection.py` (NEW): 17 tests — analysis result fields, no-signal, centered donut accuracy (radius, error, center), offset/miscollimated donut (positive error, direction), clipping, off-center frame, custom confidence threshold.
- `tests/unit/services/test_donut_overlay.py` (NEW): 25 tests — screw marker fields, all overlay fields, traffic-light thresholds (4 boundary tests), screw positions and geometry, error angle propagation.
- `docs/todo.md`: COL-070, COL-071, COL-072 marked done.
- Test suite: 2015 tests, all pass, 83.31% coverage.

---

## 2026-05-16 — Collimation Phase 6 — Focuser Algorithm

**What changed:**

- `smart_telescope/services/collimation/focus_search.py` (NEW): `FocusSearcher` performs image-based rough focus search using FWHM. Algorithm: initial measurement → probe (one coarse step each direction) → scan (bracket in improving direction, stop on 2 consecutive non-improvements) → backtrack to best position → final approach (overshoot + fine steps from configured direction). Result: `FocusSearchResult(success, reason, best_fwhm, net_steps)`.
- `smart_telescope/services/collimation/defocus_controller.py` (NEW): `DefocusController` moves focuser in defocus direction until the star donut reaches 25–50 % of the shorter frame dimension. Radius measured via brightness-weighted RMS second moment, restricted to pixels above 6σ background threshold to eliminate noise inflation. Clipping detected via 10%-of-peak bounding box. Result: `DefocusResult(success, reason, estimated_radius_px, target_min_px, target_max_px, net_steps)`.
- `tests/unit/services/test_focus_search.py` (NEW): 11 tests — result fields, star lost, search convergence, already in focus, cancellation, soft limits, max steps.
- `tests/unit/services/test_defocus_controller.py` (NEW): 12 tests — result fields, target radius (rectangular frames), at-target success, growing donut reaching target, clipping detection, star lost, max steps, cancellation.
- `docs/todo.md`: COL-060, COL-061 marked done.
- Test suite: 1973 tests, all pass, 83.15% coverage.

---

## 2026-05-16 — Bug fixes + optical trains config

**What changed:**

- `api/focuser.py`: `_safe_move` now sleeps 300 ms after issuing the move command and
  checks `is_moving()` / position change; returns `bool` (`started`). `focuser_nudge`
  response now includes `"started": bool` so the setup-check wizard can immediately
  report wiring problems without waiting 2.5 s.

- `api/mount.py`: `mount_unpark` now polls `get_state()` for up to 3 s after `:hU#` is
  sent, logging the final state.  The API no longer returns until the mount actually
  transitions away from PARKED (or times out with a warning).

- `workflow/goto_center.py`: `goto_and_center` now wraps `mount.goto()` in
  `try/except RuntimeError` — the previous `if not ok:` check was dead code because
  `OnStepMount.goto()` raises on rejection rather than returning False.

- `api/preview.py`: Low-range histogram changed from 100 to 200 bins (5 ADU/bin
  instead of 10 ADU/bin over the 0–1000 ADU pedestal panel).

- `static/index.html`:
  - Setup-check focuser step: checks `result.started` immediately after nudge;
    fails fast without the 2.5 s wait when the motor never started.
  - Setup-check unpark: removed the hardcoded 600 ms `setTimeout`; the API now
    blocks until state propagates.
  - Histogram tick spacing: replaced the `rawMajor <= 1000 → majorInt = 1000`
    forced-single-tick logic with a tiered lookup (50/100/200/500/1000/nearest-k);
    minor-tick spacing is now `max(10, majorInt/5)` so small ranges get
    readable tick grids.
  - Label updated from "10 ADU/bin" to "5 ADU/bin".

- `config.py`: Added `TelescopeSpec` and `OpticalTrainSpec` dataclasses plus
  `_parse_telescopes()` / `_parse_optical_trains()` functions.  Module-level
  `TELESCOPES` and `OPTICAL_TRAINS` dicts expose the parsed values.

- `templates/config.toml`: Added commented `[telescopes]` and `[optical_trains]`
  sections (C8 + guide scope; main / guide / OAG trains).

- `tests/unit/workflow/test_goto_center.py`: `_MockMount.goto()` now raises
  `RuntimeError` when `goto_ok=False`, matching the real `OnStepMount` behaviour.

---

## 2026-05-16 — Collimation Phase 5 — Star Selection and Acquisition

**What changed:**

- `smart_telescope/services/collimation/star_selector.py` (NEW) — `BrightStar`, `CollimationStarCandidate`, `StarSelectionResult` dataclasses; `CollimationStarSelector.select()` — picks brightest star above 60° altitude (fallback 45° with warning message in result); `select_by_name()` for manual override (case-insensitive, no altitude filtering); `load_bright_stars(path)` — parses stars.cfg TOML, returns only `type="star"` entries with a magnitude field; uses `compute_altaz()` from `domain/visibility.py`; observer lat/lon injected; `obs_time` injectable for deterministic tests.
- `smart_telescope/services/collimation/star_acquisition.py` (NEW) — `AcquisitionResult` dataclass (`success`, `reason`, `star_measurement`, `centering`); `StarAcquisition.acquire(candidate, cancel_check, dec_deg)` — slew via `mount.goto()`, wait for `is_slewing()` with 120 s timeout, enable tracking if not already, settle (`sleep`), capture + `normalize_frame()` + `detect_star()`, center via injected `PulseCenterer`; reasons: "ok" / "slew_failed" / "star_not_found" / "centering_failed" / "cancelled"; cancellation checked before slew, during slew poll, and after settle.
- `tests/unit/services/test_star_selector.py` (NEW) — 22 tests: dataclass fields (3), select() primary threshold (3), fallback (3), none_visible (3), select_by_name (5), load_bright_stars (4); `compute_altaz` patched for deterministic altitude control.
- `tests/unit/services/test_star_acquisition.py` (NEW) — 13 tests: result fields, successful acquisition (6), slew_failed (1), star_not_found (1), cancellation (3), centering_failed (1); 256×256 Gaussian PSF frames used to stay within 2 % blob-fraction limit.
- `docs/todo.md` — COL-050, COL-051 marked done.

**1950 tests pass (35 new). Coverage 83 %.**

---

## 2026-05-16 — Collimation Phase 4 — Mount and Focuser Control

**What changed:**

- `smart_telescope/services/collimation/mount_centering.py` (NEW) — `MountCorrectionResult` dataclass; `PulseCenterer.center(get_offset_px, cancel_check, dec_deg)` — iterative guide-pulse loop; per-iteration: measure offset → check tolerance → check divergence → choose dominant axis → convert px→arcsec→ms → clamp to max_pulse_ms → guide → settle; abort on star_lost / diverging (3 × 10 % grow) / cancelled / max_pulses; cos(dec) correction for RA guide rate.
- `smart_telescope/services/collimation/focuser_control.py` (NEW) — `FocuserMoveResult` dataclass; `CollimationFocuserControl` with `move_focus_relative()`, `move_focus_clockwise()`, `move_focus_counterclockwise()`, `defocus()`, `focus_fine()`; two-stage clamp (max_single_step → soft position limits); direction sign from `increasing_value_direction` config; `reason` = "ok" | "soft_limit" | "unavailable"; unavailable focuser handled gracefully.
- `smart_telescope/adapters/mock/focuser.py` — **Bug fix:** `MockFocuser.move(steps)` now does `self._position += steps` (relative) instead of `self._position = steps` (absolute), matching the OnStep adapter contract.
- `tests/unit/services/test_mount_centering.py` (NEW) — 19 tests: result fields, within-tolerance (no pulses), guide direction for all 4 axes, dominant-axis selection, pulse clamp, 1ms minimum, convergence, pulses counted, star_lost, star_lost after pulse, diverging, max_pulses, cancel_check immediate, cancel after pulse, dec correction.
- `tests/unit/services/test_focuser_control.py` (NEW) — 29 tests: result fields, unavailable (3), relative move (4), max_single_step clamp (3), soft limits (4), direction mapping (5), defocus/fine focus (6), clipped flag (3).
- `docs/todo.md` — COL-040, COL-041 marked done.

**1915 tests pass (48 new). Coverage 83 %.**

---

## 2026-05-16 — Collimation Phase 3 — Frame Processing Foundation

**What changed:**

- `smart_telescope/domain/collimation/processing/__init__.py` (NEW) — package init
- `smart_telescope/domain/collimation/processing/frame.py` (NEW) — `ProcessedFrame` dataclass (`raw` uint16, `mono` float32, `bit_depth`, `width`, `height`, `timestamp`); `normalize_frame(FitsFrame, bit_depth=16)` — copies pixel data, does not mutate input; `.normalized` property returns [0, 1] float32.
- `smart_telescope/domain/collimation/processing/stretch.py` (NEW) — `estimate_background()` (sigma-clip, 5 iterations); `auto_stretch()` → uint8 percentile stretch; `saturation_fraction(bit_depth)`; `peak_location()`.
- `smart_telescope/domain/collimation/processing/star_detection.py` (NEW) — `detect_star(ProcessedFrame) → StarMeasurement | None`; 5σ threshold; intensity-weighted centroid; radial-profile FWHM; hot-pixel rejection (< 4 px blob) and nebula rejection (> 2 % frame area); SNR-based confidence with saturation penalty.
- `smart_telescope/domain/collimation/processing/geometry_fits.py` (NEW) — `fit_circle()` (Kasa algebraic least-squares, confidence = 1 − rms/r); `fit_ellipse()` (Bookstein direct fit, conic → eigenvalue decomposition, falls back to circle on non-elliptic conics); `extract_edge_points()` (4-connectivity erosion, returns float64 (N,2) array); `detect_clipping(fit, w, h)`; `compare_circle_centers()`.
- `tests/unit/domain/collimation/` (NEW) — 4 test files, 75 tests, all pass:
  - `test_frame_processing.py` (18 tests) — type, dimensions, float32/uint16 conversion, negative clamping, overflow, immutability, independence, bit depths, normalized property
  - `test_stretch.py` (22 tests) — background estimation with star ignored, sigma floor, stretch range+monotonicity+no-mutation, saturation fraction (8-bit and 16-bit), peak location
  - `test_star_detection.py` (11 tests) — dark frame None, Gaussian star detection, centroid accuracy ≤ 1 px, FWHM within 50 %, hot-pixel rejection, saturation penalty, edge star, noisy frame
  - `test_geometry_fits.py` (24 tests) — exact/noisy/small circle, partial arc, degenerate cases, ellipse axis-aligned and noisy, edge extraction from disc mask, circle-from-edge round-trip, clipping detection, center comparison
- `docs/todo.md` — Collimation section added (COL-001 through COL-131), Phases 0+1+3 marked done.

**1867 tests pass (75 new). Coverage 82 %.**

---

## 2026-05-16 — BUG-001 abort_capture + M2 milestone close

**What changed:**

- `smart_telescope/ports/camera.py` — Added `CaptureAbortedError` exception class and `abort_capture()` non-abstract default no-op method to `CameraPort`.
- `smart_telescope/adapters/mock/camera.py` — Added `capture_delay_s: float = 0.0` parameter and `threading.Event`-based `_abort`; `capture()` blocks for `capture_delay_s` seconds then checks abort; `abort_capture()` sets the event. Used for cancel-latency unit tests.
- `smart_telescope/adapters/touptek/camera.py` — Added `self._abort = threading.Event()`; replaced single `_frame_ready.wait(timeout)` with a 50ms polling loop that breaks on `_abort`; added `abort_capture()` that sets `_abort`; imports `CaptureAbortedError`.
- `smart_telescope/domain/autogain_service.py` — Added abort-watcher thread (starts before the main loop, waits for `cancellation_flag`, calls `camera.abort_capture()`); catches `CaptureAbortedError` before generic `Exception` and returns `CANCELLED` immediately. Cancel latency now ≤ 50ms (one poll interval).
- `tests/unit/domain/test_autogain_service.py` — Added `_SlowCamera` stub and `TestCancelLatency` (2 tests): verifies `CANCELLED` status and verifies elapsed time < 1 s.
- `docs/todo.md` — BUG-001 closed; M2-003/004/005/006 closed; M2 milestone complete.

**All 1792 tests pass (2 new).**

---

## 2026-05-16 — R3 Shared Job Manager

**What changed:**

- `smart_telescope/services/job_manager.py` (NEW) — `JobStatus`, `ResourceConflictError`, `Job` dataclass, `JobManager` class. Two submission modes: `submit()` (JobManager owns daemon thread, wraps fn with status update, optional timeout via companion watcher thread) and `claim()`/`release()` (caller owns thread). Atomic resource conflict detection in `_register()`. Query API: `get_job`, `get_by_name`, `list_active`, `active_resources`, `is_resource_held`, `purge_finished`. Cancellation: `cancel`, `cancel_by_name`, `cancel_all`.
- `smart_telescope/runtime.py` — Added `from .services.job_manager import JobManager`; `self.job_manager = JobManager()` in `__init__`; `self.job_manager.cancel_all()` at start of `shutdown()`; `self.job_manager = JobManager()` in `reset_for_tests()`.
- `smart_telescope/api/deps.py` — Added `get_job_manager() -> JobManager`.
- `smart_telescope/api/autogain.py` — Removed manual `threading.Thread` creation and old `j.running` 409 check; replaced with `rt.job_manager.submit("autogain", {"camera:N"}, _worker, ..., cancel_event=job.cancel, timeout_s=300)`. `_reset()` now also calls `rt.job_manager.cancel_by_name("autogain")` for test isolation.
- `smart_telescope/api/session.py` — Replaced `rt.session_lock` conflict check with `rt.job_manager.claim("session", {"camera:0", "mount", "focuser"})`; thread target wrapped in `_session_thread()` that calls `rt.job_manager.release()` in finally; `_reset_session()` also calls `rt.job_manager.cancel_by_name("session")`.
- `tests/unit/services/test_job_manager.py` (NEW) — 40 tests: `TestSubmit` (done/failed/conflict/resource-release/args/bridged-cancel), `TestClaimRelease` (hold/release/done/failed/noop/empty), `TestCancellation` (by-id/by-name/cancel-all), `TestTimeout` (cancelled after timeout, not cancelled when fn finishes first), `TestQuery` (get/get-by-name/list-active/active-resources/is-resource-held), `TestConflictDetection` (done-doesn't-block, non-overlapping ok, error names holder, cancelled-doesn't-block), `TestPurge` (removes finished, leaves active, returns count).
- `tests/unit/test_runtime.py` — Added `test_job_manager_is_fresh_instance` and `test_reset_installs_fresh_job_manager`.
- `docs/todo.md` — R3-001 through R3-007 marked complete; M2-001 and M2-002 marked complete.

**All 1790 tests pass (42 new).**

---

## 2026-05-16 — R0-010 lifecycle tests + UX-PENDING-001 mount pending indicator

**What changed:**

- `tests/unit/test_runtime.py` (NEW) — 40 tests: `TestRuntimeContextInit` (all slots None, coordinator/device_state fresh, session/autogain None), `TestConnectDevices` (mock mode, adapters_built flag, idempotency, polling starts, simulator env var), `TestShutdown` (device_state stops, focuser.stop called, mount stop-before-disconnect ordering, preview cameras closed, error tolerance), `TestResetForTests` (all adapters cleared, polling stopped, fresh coordinator/device_state, session+autogain cleared, new adapters on next access), `TestModuleSingleton` (get/set_runtime), `TestSessionState` (set/clear/is_running), `TestAutogainState` (set/get/clear), `TestLifespan` (FastAPI lifespan sets app.state.runtime, readiness endpoint live, polling thread dead after exit).
- `smart_telescope/static/index.html` — UX-PENDING-001 (POD-003):
  - CSS: `.state-pending` badge style (blue outline)
  - JS: `_mountPendingCmd` module variable (null or command name string)
  - `_updateMountStrip()`: dot turns yellow + label shows `cmd…` when pending; `⚠ state` suffix when `data.stale`
  - `mountCard()`: state badge replaced by spinner-badge when pending, or `⚠ state` badge when stale
  - `mountAction()`: sets `_mountPendingCmd` before API call, clears in `finally`; polls 10× at 500ms for park/unpark confirmation
  - `mountHome()`: sets/clears `_mountPendingCmd` in `finally`
  - `mountGoto()`: sets/clears `_mountPendingCmd` in `finally`
- `docs/todo.md` — R0-010 and UX-PENDING-001 marked complete.

**All 1791 tests pass (40 new).**

---

## 2026-05-15 — PO decisions: POD-001 / POD-002 / POD-003 / POD-006 / POD-008

**Decisions recorded:**

- **POD-001 (Reconnect):** Auto-park on reconnect — already implemented; no change needed.
- **POD-002 (STOP latency):** < 1 s maximum. Safety checklist and BUG-001 acceptance criteria updated.
- **POD-003 (UI state lag):** Spinner/pending indicator between command acceptance and hardware confirmation. New task UX-PENDING-001 added to backlog.
- **POD-006 (MVP demo):** Guided single-target session — Pick target → GoTo → plate-solve & center → autofocus → stack 10 frames → save.
- **POD-008 (Deferred):** ISS tracking, multi-target queue, advanced calibration wizard, collimation assistant are post-MVP.

**docs/todo.md updated:** POD-001/002/003/006/008 marked complete; BUG-001 acceptance criterion updated to < 1 s; safety checklist annotated with POD-002 target; UX-PENDING-001 task added.

---

## 2026-05-15 — R1-010 / R2-008 / R0-005 / R0-006: Tests + runtime state consolidation

**What changed:**

- `tests/unit/services/__init__.py` (NEW) — services test package.
- `tests/unit/services/test_hardware_coordinator.py` (NEW) — 11 tests: acquire/release, lock-released-on-exception, concurrent conflict, timeout=0 non-blocking, lock independence (mount ≠ focuser), two-coordinator isolation, STOP bypass pattern, informative error message.
- `tests/unit/services/test_device_state.py` (NEW) — 13 tests: initial None, start populates, idempotent start, stop halts polling, error stored as UNKNOWN state, flaky-poll reverts to UNKNOWN, UNKNOWN skips position query, position error doesn't crash poll, concurrent reads are safe, stale/not-stale MountObservedState.
- `smart_telescope/runtime.py` — `RuntimeContext` gains `session_lock`, `_active_runner`, `_runner_thread`, `autogain_lock`, `_autogain_job`; new methods `get_active_runner()`, `is_session_running()`, `set_session()`, `clear_session()`, `get_autogain_job()`, `set_autogain_job()`; `reset_for_tests()` clears all new state.
- `smart_telescope/api/session.py` — removed module-level `_session_lock`, `_active_runner`, `_runner_thread`; all references go through `_get_runtime()`.
- `smart_telescope/api/autogain.py` — removed module-level `_job`, `_lock`; replaced with `_get_job()` / `_set_job()` wrappers over RuntimeContext; all endpoints use `rt.autogain_lock`.
- `docs/todo.md` — marked R1-010, R2-008, R0-005, R0-006 complete.

**All 1751 tests pass (24 new).**

---

## 2026-05-15 — M1: Hardware Safety Spine (R1 coordinator + R2 device state)

**What changed:**

- `smart_telescope/services/hardware_coordinator.py` (NEW) — `HardwareCommandCoordinator` with `mount_command()` and `focuser_command()` context managers. `CommandConflictError` raised immediately on timeout. STOP bypasses this entirely.
- `smart_telescope/services/device_state.py` (NEW) — `DeviceStateService`: daemon thread polls mount state every 2 s. `MountObservedState` dataclass with `is_stale()` (10 s threshold). Injected via `deps.get_device_state()`.
- `smart_telescope/runtime.py` — integrates both services: `coordinator` and `device_state` in `__init__`; polling started in `connect_devices()`; `device_state.stop()` called first in `shutdown()` and `reset_for_tests()`.
- `smart_telescope/api/deps.py` — added `get_coordinator()` and `get_device_state()` wrappers.
- `smart_telescope/api/mount.py` — removed module-level `_goto_lock`; all motion endpoints (`goto`, `home`, `park`, `goto_sky`, `goto_and_center`) use `coordinator.mount_command()`; `mount_status` reads from `DeviceStateService` cache with direct-poll fallback; `MountStatus` gains `stale: bool` field; `mount_home` now returns specific "Home slew failed — check mount is tracking and powered" message (BUG-014).
- `smart_telescope/api/focuser.py` — removed module-level `_move_lock` and `_MOVE_TIMEOUT_S`; `_safe_move`, `focuser_move`, `focuser_nudge`, `focuser_autofocus` use `coordinator.focuser_command()`.
- `docs/todo.md` — marked BUG-023, BUG-014, R1-001/002/003/004/007, R2-001/002/004/006/007, M1-001/002/003 as complete.

**All 1727 tests pass.**

---

## 2026-05-15 — NEXT-011: R5 ReadinessService + UX1 Readiness Card

**What changed:**

- `smart_telescope/services/readiness.py` (NEW) — `ReadinessService` with 9 checks: config_file, stars_cfg (RED if missing), horizon_dat (YELLOW), storage (RED if missing/full), astap_exe (RED), astap_catalog (RED), camera (YELLOW if unconfigured), mount, focuser. Returns `ReadinessReport` with `overall` (green/yellow/red), `can_observe`, and `repair` guidance per item.
- `smart_telescope/api/readiness.py` (NEW) — `GET /api/readiness` endpoint, always HTTP 200.
- `smart_telescope/app.py` — readiness router registered.
- `smart_telescope/static/index.html` — System Readiness card added at top of Stage 1. Loads automatically on page open, refreshes every 30 s. Shows overall badge + per-item dot/message/repair. Refresh button for manual re-check.
- `tests/unit/api/test_readiness.py` (NEW) — 22 tests covering all checks, overall level rules, API response shape.

**All NEXT-001 through NEXT-011 complete. All 176 tests pass.**

---

## 2026-05-15 — Immediate Actions: R0 RuntimeContext + AI Skills

**What changed:**

- `smart_telescope/runtime.py` (NEW) — `RuntimeContext` class owns all adapter state: camera, mount, focuser, stacker, storage, solver, preview cameras. Methods: `connect_devices()` (lazy, thread-safe), `shutdown()` (stop motion before disconnect), `disconnect_devices()`, `reset_for_tests()`. Module-level `get_runtime()` / `set_runtime()` singleton for `deps.py` compatibility wrappers.
- `smart_telescope/app.py` — lifespan now creates `RuntimeContext`, registers it via `set_runtime()` and `app.state.runtime`, then calls `ctx.shutdown()`. Removed direct `deps._focuser / _mount / _preview_cameras` access from shutdown path.
- `smart_telescope/api/deps.py` — rewritten as thin compatibility wrappers. All public functions (`get_camera`, `get_mount`, `get_focuser`, `get_stacker`, `make_stacker`, `get_solver`, `get_storage`, `get_preview_camera`, `get_camera_by_role`, `reset`) delegate to `get_runtime()`. No module-level globals remain. All 154 existing tests pass unchanged.
- `docs/skills/smarttscope-product-steward.md` (NEW) — AI skill definition: maintains backlog, imports bugs, deduplicates, enforces acceptance criteria, produces Top-10 risk view.
- `docs/skills/smarttscope-quality-sentinel.md` (NEW) — AI skill definition: verifies task evidence, flags done-without-test, produces milestone traffic-light and release go/no-go report.
- `docs/todo.md` — NEXT-001 through NEXT-009 marked complete; R0-001 through R0-004, R0-007, R0-008, R0-009 marked complete.

**R0 remaining:** R0-005 (session runner into RuntimeContext), R0-006 (autogain job), R0-010 (lifecycle tests).
**Next:** NEXT-011 UX1 Ready To Observe, then M1 hardware safety spine.

---

## 2026-05-15 — Ingest: smarttscope-final-product-architecture-ai-plan.md

**Source ingested**: `docs/smarttscope-final-product-architecture-ai-plan.md`  
**Field bugs also ingested**: `resources/hlrequirements/Items_to_fix_20260513.txt`, `Items_to_fix_20260514.txt`

**New pages**:
- `docs/todo.md` — prioritized master backlog covering M0–M6 milestones, R0–R7 architecture refactors, UX1–UX5 UX refactors, 18 field bugs (BUG-005 through BUG-024), 9 open product-owner decisions, and a safety regression checklist.

**What changed**:
- Consolidated all open work from the architecture review, field bug files, and prior task lists into one authoritative todo.
- 2 P0 Safety items identified: BUG-023 (shutdown doesn't close OnStep, focuser keeps moving) and BUG-005 (system isolation — moving parts must stay controlled on any crash).
- Milestone order: M0 (project control) → M1 (hardware safety) → M2 (runtime/jobs) → M3 (optical train/config) → M4 (intent UX) → M5 (MVP demo) → M6 (field reliability).

---

## 2026-05-06 — Ingest: SmartTScope_Fixes_Requirements_20260506

**Source ingested**: `resources/hlrequirements/SmartTScope_Fixes_Requirements_20260506.md`

**New wiki pages**:
- `wiki/requirements-addon-20260506.md` — fix/update requirements v1.1: camera naming/registry (§1), Live Preview backend (§2.3–2.10), Polar Alignment selector (§3), Startup tab polish (§4). 13 tasks added to persistent SmartTScope tasklist (STS-ADDON-001 through STS-ADDON-013).

**Updated wiki pages**:
- `wiki/index.md` — new Planning entry

**Task snapshot**: STS-ADDON-001 completed (tasklist populated); 002–013 pending. P1 tasks: camera registry (002), camera name selectors (003, 004), Live Preview backend (005, 006). All 13 tasks to be executed after the current AutoGain (AGT) implementation run completes.

---

## 2026-05-03 — Sprint 45: TOML config file, tracking toggle, ASTAP + mount bug fixes

**What changed**:

- `smart_telescope.toml` (NEW) — project-root config template.  Sections: `[observer]` (lat/lon), `[hardware]` (onstep_port, touptek_index, gps_port, dew_control_port), `[astap]` (path, catalog_dir), `[mount_limits]`, `[session]`.  All hardware fields default to `""` (empty = mock/auto-detect); the Pi admin fills in real values.
- `smart_telescope/config.py` — rewritten: loads TOML from CWD or project root via `tomllib`; env vars override for observer/limits/session settings; hardware/ASTAP settings are TOML-only (env-var override is applied per-call in `deps.py` to preserve `monkeypatch` test behaviour).  New exports: `ONSTEP_PORT`, `TOUPTEK_INDEX`, `GPS_PORT`, `DEW_CONTROL_PORT`, `ASTAP_PATH`, `ASTAP_CATALOG_DIR`, `STORAGE_DIR`.
- `smart_telescope/api/deps.py` — `_build_adapters()` now reads `os.environ.get(key) or config.KEY` so live env vars always win; same pattern for `get_solver()` / `get_storage()`.  Fixes the false-positive "Connected" bug: previously `ONSTEP_PORT` absent → `MockMount` (always returns True); now the TOML supplies the port → `OnStepMount` → real serial failure reported correctly.
- `smart_telescope/adapters/astap/solver.py` — `find_catalog()` now accepts optional `catalog_dir` parameter (checked first); added Pi-specific search dirs `/var/lib/astap` and `/opt/astap`.  `AstapSolver.__init__` stores `catalog_dir` for future per-solve pass-through.
- `smart_telescope/api/session.py` — `_check_solver()` passes `catalog_dir=config.ASTAP_CATALOG_DIR` to `_find_catalog()`; mount hint updated to reference `smart_telescope.toml`.
- `smart_telescope/static/index.html` — `mountCard()` tracking buttons replaced with a single context-sensitive toggle: shows "Disable Tracking" when `state === 'tracking'`, otherwise "Enable Tracking".

**Tests** — no new test files; updated three existing tests:
- `tests/unit/api/test_session.py` — patched lambdas for `_find_catalog` updated to `lambda *a, **kw:` to accept new `catalog_dir` keyword argument.

**Suite result**: 1026 passed, 0 failures, 92% coverage

---

## 2026-05-03 — Sprint 44: "Best objects tonight" endpoint (M8)

**What changed**:

- `smart_telescope/api/catalog.py`:
  - Added `from datetime import UTC, datetime, timedelta` and `compute_visibility_window` import
  - New `VisibleEntry` Pydantic model — extends catalog fields with `rises_at`, `sets_at`, `peak_altitude`, `peak_time` (ISO8601 UTC strings), `is_observable`, `solar_safe`
  - New `GET /api/catalog/visible` endpoint:
    - Optional `?lat=` / `?lon=` to override observer position (defaults to `config.OBSERVER_LAT/LON`)
    - `?hours=` observation window length in hours (default 10, range 1–24)
    - `?min_altitude=` minimum peak altitude in degrees (default 20)
    - `?object_type=` comma-separated type filter (e.g. `GC,SG`)
    - `?max_magnitude=` upper magnitude bound
    - `?limit=` max results (default 20)
    - Calls `compute_visibility_window(..., sample_minutes=15)` for each catalog object
    - Filters to `is_observable=True`; adds `solar_safe` flag via `is_solar_target()`
    - Sorted by `peak_altitude` descending

**Tests** — added `TestCatalogVisible` class (15 tests) to `tests/unit/api/test_catalog.py`:
  - 200 response, empty when all non-observable, expected fields present, is_observable=True
  - Sorted by peak altitude descending
  - object_type filter, multi-type filter, max_magnitude filter, limit applied, default limit 20
  - solar_safe flag (blocked / not-blocked), lat/lon override forwarded, rounding, ISO8601 string format

**Suite result**: 1026 passed, 0 failures, 92% coverage

---

## 2026-05-03 — Sprint 43: Observation Queue REST API (M8)

**What changed**:

- `smart_telescope/api/queue.py` (NEW) — Full CRUD for the observation queue:
  - `POST /api/queue` → 201 + entry dict; validates profile against `{c8_native, c8_reducer, c8_barlow2x}`; validates RA [0, 24), Dec [−90, 90]
  - `GET /api/queue` → list all entries; optional `?status=` filter (PENDING / RUNNING / DONE / FAILED / SKIPPED); 422 on unknown status
  - `GET /api/queue/{entry_id}` → single entry; 404 if not found
  - `DELETE /api/queue/{entry_id}` → remove PENDING entry; 204 on success; 404 if not found; 409 if not PENDING
  - `POST /api/queue/clear` → remove all DONE/FAILED/SKIPPED entries; returns `{"cleared": N}`
  - Module-level `ObservationQueue` singleton with `_reset_queue()` for test isolation; `get_queue()` accessor
- `smart_telescope/app.py` — registered `queue_router`

**Tests**:
- `tests/unit/api/test_queue.py` (NEW) — 25 tests across 6 classes:
  - `TestAddEntry` (8 tests): 201 path, entry_id present, defaults, custom fields, invalid profile, RA/Dec validation, missing name, appears in list
  - `TestListEntries` (6 tests): empty, all entries, insertion order, status filter, case-insensitive filter, unknown status 422
  - `TestGetEntry` (2 tests): found, 404
  - `TestRemoveEntry` (5 tests): 204, gone after remove, 404, 409 on RUNNING, detail includes status
  - `TestClearCompleted` (3 tests): count returned, PENDING survives, zero when nothing to clear
  - `queue.py` at 100% coverage

**Suite result**: 1011 passed, 0 failures, 92% coverage

---

## 2026-05-03 — Sprint 42: System Health dashboard card (M5.1)

**What changed**:

- `smart_telescope/api/health.py`:
  - `CpuHealth(temp_c: float | None)` — new model; reads `/sys/class/thermal/thermal_zone0/temp` via `_read_cpu_temp()`; returns `None` gracefully on non-Linux / missing path
  - `StorageHealth` gains `frames_capacity: int | None` — computed as `int(free_gb * 1024 / 25)` (25 MB estimated float32 FITS frame for C8 native); `None` when no `STORAGE_DIR` is set
  - `SystemHealth` gains `cpu: CpuHealth` field
  - `system_status()` updated to populate both new fields
- `smart_telescope/static/index.html`:
  - New "System Health" card in Stage 1 (after the Focuser card): overall dot (green/yellow/red), last-updated timestamp
  - `_healthRow(label, level, value)` — renders one subsystem row with colored mini-dot
  - `_renderHealthCard(d)` — populates all 7 rows (Mount, Camera, Focuser, Solver, Storage, CPU temp, Session) with per-row color logic; updates overall dot
  - `refreshHealth()` — async fetch of `/api/status` + render
  - Init block: calls `refreshHealth()` on load; `setInterval(refreshHealth, 10_000)` for live updates

**Tests**:
- `tests/unit/api/test_health.py` — `test_response_has_all_top_level_fields` updated to include `"cpu"`
- `TestCpuHealth` (4 tests): field present, None on missing path, value returned when patched, rounding
- `TestStorageCapacity` (2 tests): `frames_capacity` computed from free_gb; None when no path set

**Suite result**: 986 passed, 0 failures, 92% coverage

---

## 2026-05-03 — Sprint 41: Bahtinov domain unit tests + `_intersect` bugfix

**Bug fixed**:
- `smart_telescope/domain/bahtinov.py` — `_intersect()` had wrong Cramer's rule signs: `x` used `/ (-d)` instead of `/ d`, and `y` numerator was `(a1·c2 − a2·c1)` instead of `(a2·c1 − a1·c2)`. Effect: intersections reflected through origin → `focus_error_px` wildly wrong (e.g. −656 px instead of ≈ 0). Fixed to standard Cramer's rule.

**Tests added**:
- `tests/unit/domain/test_bahtinov.py` — NEW: 43 tests covering `SpikeLine`, `CrossingAnalysisResult`, `_gaussian_blur`, `_intersect` (including regression for the Cramer's rule bug), `_classify_bahtinov`, `BahtinovAnalyzer.analyze()`, constructor params, `_find_brightest_object`

**Suite result**: 980 passed, 0 failures

---

## 2026-05-02 — Sprint 40: Bahtinov API + Stage 4 UI overlay

**Code changes**:
- `smart_telescope/api/bahtinov.py` — NEW: `POST /api/bahtinov/analyze`; captures one frame, runs `BahtinovAnalyzer`, returns `CrossingAnalysisResult` fields + `image_size_px`; 422 when fewer than 3 spikes detected
- `smart_telescope/app.py` — registered `bahtinov_router`
- `smart_telescope/static/index.html`:
  - Analyze button (enabled only when preview running, disabled when stopped)
  - SVG overlay element (`s4-bahtinov-svg`) absolutely positioned over preview image
  - Results card (focus_error_px with color + direction hint, crossing RMS, confidence)
  - `_clipLineToRect()` — clips a normal-form line to image bounds for SVG rendering
  - `_drawBahtinovOverlay(data)` — draws 3 spike lines (outer blue dashed, middle yellow solid), crossing-point ring (green/yellow/red by error magnitude), focus-direction arrow
  - `_clearBahtinovOverlay()` — clears SVG + hides results (called on preview stop)
  - `bahtinovAnalyze()` — async; posts to API, populates results, calls draw overlay
  - `_updatePreviewBtns()` — now also manages analyze button and clears overlay on stop

**Tests**:
- `tests/unit/api/test_bahtinov.py` — NEW: 12 tests (422 on zero-pixel image, success path with synthetic spike image, key validation, mocked analyzer path)

**Suite result**: 980 passed, 94.40% coverage

---

## 2026-05-02 — Sprint 39: Focuser availability + shared serial delegation

**Source ingested**: `resources/hlrequirements/requirements_addon_20260502b.txt`

**New wiki pages**:
- `wiki/requirements-addon-20260502b.md` — README update instructions + focuser always-expected policy

**Updated wiki pages**:
- `wiki/index.md` — new Planning entry

**Code changes**:
- `smart_telescope/ports/focuser.py` — added `get_max_position()` abstract method and `is_available` abstract property
- `smart_telescope/adapters/onstep/focuser.py` — refactored to delegate serial I/O to `OnStepMount`; no own serial handle; `connect()` sets `_available` from `:FA#`; fetches max position via `:FM#`
- `smart_telescope/adapters/mock/focuser.py` — added `is_available` and `get_max_position()` (returns 5000)
- `smart_telescope/adapters/simulator/focuser.py` — added `is_available` (True) and `get_max_position()` (5000)
- `smart_telescope/api/deps.py` — `OnStepFocuser(mount=mount)` shared serial; no separate focuser port open
- `smart_telescope/api/focuser.py` — status adds `available` + `max_position`; `POST /api/focuser/connect` (new); move/nudge/autofocus return 503 when not available; position clamped to `[0, max_position]`
- `smart_telescope/api/health.py` — focuser health uses `focuser.is_available`
- `smart_telescope/static/index.html` — Stage 1 focuser status card; `connectAll()` probes focuser; `focuserCard()` shows disabled banner when `available === false`
- `README.md` — new "Keeping up to date" section (git pull + pip install + systemctl restart)

**Tests**:
- `tests/unit/adapters/onstep/test_onstep_focuser.py` — rewritten for new delegating constructor (30 tests)
- `tests/unit/api/test_focuser.py` — updated for `available`/`max_position`; new connect endpoint tests; 503 tests (38 tests)

**Suite result**: 968 passed, 88.63% coverage

---

## 2026-05-02 — Ingest: requirements_addon_20260502 (Bahtinov analyzer)

**Source ingested**: `resources/hlrequirements/requirements_addon_20260502.txt`

**New pages**:
- `wiki/bahtinov-analyzer.md` — complete algorithm reference: brightest-object detection (flux score), ROI crop, core masking, Hough/RANSAC line detection, normal-form line fitting, pairwise intersection geometry, `focus_error_px` (primary Bahtinov metric), `crossing_error_rms_px` (quality guard), `SpikeLine` / `CrossingAnalysisResult` data structures, UI requirements

**Updated pages**:
- `wiki/autofocus.md` — added Bahtinov as the specified SmartTScope focus method, link to [[bahtinov-analyzer]]
- `wiki/requirements.md` — added Bahtinov collimation tool as MVP+ requirement in §4, linked to [[bahtinov-analyzer]]
- `wiki/index.md` — new Concepts entry

---

## 2026-05-02 — Sprint 38: Mount Limits display card in Stage 1

**What changed**:

- `smart_telescope/static/index.html` — new "Mount Limits" card in Stage 1, positioned after the mount control card:
  - Four param fields: Alt min (horizon), Alt max (zenith exclusion), HA east limit, HA west limit.
  - Populated by `initSiteConfig()` which already calls `GET /api/mount/config` on page load.
  - Footer note explains each value is controlled by an environment variable.
- No backend changes.

**Result**: UI-only change.

---

## 2026-05-02 — Ingest: requirements_addon_20260430 + requirements_addon_20260501

**Sources ingested**:
- `resources/hlrequirements/requirements_addon_20260430.txt`
- `resources/hlrequirements/requirements_addon_20260501.txt`

**New pages**:
- `wiki/requirements-addon-20260430.md` — star catalog expansion, quickstart corrections (Trixie, no libcamera), §14 process requirements
- `wiki/requirements-addon-20260501.md` — first hardware test session (2026-05-01): three bugs (serial race → 500, camera caching, WS silent close); new requirements for mount display, Home/Park, step-based movement, mount limits config

**Updated pages**:
- `wiki/onstep-protocol.md` — adapter implementation notes expanded: threading lock rationale, readline/`#` terminator behaviour, all commands now used by `OnStepMount` (including `disable_tracking`, `park`, `guide`, alignment), safe-movement rule (pulse guide only)
- `wiki/index.md` — two new planning entries added

---

## 2026-05-02 — Sprint 37: GoTo-Selected button + live mount-strip poll

**What changed**:

- `smart_telescope/static/index.html` — Custom Targets card (Stage 3):
  - Added GoTo and ⌖ buttons in the card header, initially disabled; enabled when a target row is clicked.
  - `starSelect()` now saves `_selectedStar`, highlights the clicked row (`.star-item.selected` CSS), and enables the header buttons.
  - `loadStars()` resets `_selectedStar` and disables the header buttons on reload.
  - `starGotoSelected()` / `starCenterSelected()` delegate to the existing per-row functions.
  - `data-star-name` attribute added to each star-item `<div>` so the selected row can be found by CSS.escape lookup.
- Mount strip (stages 2–5): 5 s `setInterval` poll (`_startMountStripPoll`) activates when navigating away from Stage 1; stops on return. Keeps RA/DEC and state badge live while the mount is tracking.

**Result**: UI-only — no backend changes, no tests affected.

---

## 2026-05-02 — Bug fixes: serial lock + camera connect guard

**What changed**:

- `smart_telescope/adapters/onstep/mount.py` — added `threading.Lock` (`self._lock`) to `OnStepMount`; `_raw_send` acquires the lock before each write/readline pair. Prevents concurrent HTTP requests from interleaving bytes on the serial port, which was the root cause of `POST /api/mount/disable_tracking` returning HTTP 500.
- `smart_telescope/api/deps.py` — `get_preview_camera()` now checks `cam.connect()` return value for secondary cameras; raises `RuntimeError` (not cached) on failure.
- `smart_telescope/api/preview.py` — `ws_preview` now accepts the WebSocket before attempting `get_preview_camera()`; on `RuntimeError` sends WS close code 1011 with the error reason instead of silently dropping the connection.

**Result**: 62 OnStep tests passing (pre-existing global coverage gate failure unrelated).

---

## 2026-05-02 — Sprint 36: Stage 5 live stack viewer

**What changed**:

- `smart_telescope/static/index.html` — Stage 5 "Run Observation" card gains a live stack preview panel:
  - `_s5ConnectStackWs()` opens `WS /ws/stack` immediately on session start
  - Text (JSON) frames: updates progress bar and frame/rejected counts directly, ahead of the 2 s REST poll
  - Binary (JPEG) frames: shown in a `<img id="s5-stack-img">` inside a `.preview-frame.large` container; panel fades in on first integrated frame
  - `_s5DisconnectStackWs()` called on terminal states (SAVED / STACK_COMPLETE / FAILED) and in `_s5ResetRunUI()` before next session; blob URLs revoked on each frame to prevent memory leaks

**Result**: 957 tests passing, 15 skipped, 94% coverage (unchanged — UI-only changes).

---

## 2026-05-02 — Sprint 35: Stage 5 observation session workflow UI

**What changed**:

- `smart_telescope/static/index.html` — Stage 5 "Run Observation" card added:
  - Target text input, profile dropdown (C8 Native / 0.63× reducer / 2× Barlow), exposure (s), stack depth (frames), skip-autofocus checkbox
  - ▶ Start Session button calls `POST /api/session/run` via URLSearchParams; ■ Stop button calls `POST /api/session/stop`
  - Live status section: phase badge (`state-badge` CSS, maps to all `SessionState` enum values), animated progress bar (frames_integrated / stack_depth, shown during STACKING → SAVED)
  - Detail rows for centring offset, rejected frames, refocus count — appear only when non-zero
  - Warnings list (colour: `--warning`); saved image path shown in green on SAVED
  - State polling every 2 s via `setInterval`; stops automatically on SAVED / STACK_COMPLETE / FAILED

**Result**: 956 tests passing, 15 skipped, 94% coverage.

---

## 2026-05-02 — OnStepMount: send :Td# (stop tracking) on connect

**What changed**:

- `smart_telescope/adapters/onstep/mount.py` — `connect()` now calls `disable_tracking()` immediately after opening the serial port, before returning `True`. Ensures the mount is never left tracking unexpectedly on first connection.
- `tests/unit/adapters/onstep/test_onstep_mount.py` — new `test_connect_sends_stop_tracking` verifies `:Td#` appears in serial write calls during connect. Four `TestGetPosition` tests updated: each side_effect list gains a leading `b""` to absorb the extra `readline()` call.

**Result**: 957 tests passing, 15 skipped, 94% coverage.

---

## 2026-05-02 — Sprint 34: Stage 3 GoTo slew watcher + centre button

**What changed**:

- `smart_telescope/static/index.html`:
  - `watchSlew(statusId, label, timeout_s)` — polls `GET /api/mount/status` every 2 s during slew, updates mount strip live, resolves when state leaves `slewing` (or on timeout)
  - Stage 3 manual GoTo now calls `watchSlew()` after slew is accepted, replacing the immediate `refreshMount()`
  - ⌖ Centre button on manual GoTo panel calls `mountGotoAndCenter()` → `POST /api/mount/goto_and_center`
  - ⌖ button added to each star-list row (`starGotoAndCenter()`) — centring result shown inline; unlocks Stage 4 on success

**Result**: 956 tests passing, 15 skipped, 94% coverage (unchanged — UI-only changes).

---

## 2026-04-30 — Requirements addon: catalog expansion + process requirements + quickstart

**Source**: requirements_addon_20260430.txt

**stars.cfg — 21 new entries added**:

- *Solar system*: Jupiter (planet, approx. Apr 2026 coords — update monthly), C/2025 R3 (comet placeholder — update from JPL Horizons)
- *Nebulae*: NGC 2359 (Thor's Helmet), NGC 2237 (Rosette Nebula proper; cluster NGC 2244 was already present), IC 5068 (Forsaken Nebula), NGC 2024 (Flame Nebula), IC 434 (Horsehead Nebula), NGC 7380 (Wizard Nebula), NGC 6992 (Eastern Veil), IC 405 (Flaming Star / Caldwell 31), NGC 281 (Pacman), NGC 2174 (Monkey Head), NGC 6960 (Western Veil / Cirrus, filter note), NGC 6543 (Cat's Eye)
- *Galaxies*: M 51 (Whirlpool), M 63 (Sunflower), NGC 3268 (Antlia), NGC 3184
- *Filter variants*: M 42 Filters (OIII + Ha), M 45 Filters (nebulosity)
- *Multiple stars*: 12 Lyncis (triple, A/B 1.8″, C 8.6″), Iota Cassiopeiae (triple, +67° dec), Beta Monocerotis (triple, low ~33° from Frankfurt)

*Note*: M51, M63, M42, M45 are already in the internal Messier catalog (`domain/catalog.py`) and GoTo-able by name. The stars.cfg entries make them visible in `GET /api/catalog/stars` and add filter-use variants.

**wiki/requirements.md — §14 Process requirements added (MVP)**:

- Documentation gate: a change is not done until documentation is updated
- Release traceability: each requirement tracks "Planned for" and "Implemented in" release

**wiki/quickstart.md — new page**:

- Correct platform: Raspberry Pi OS Trixie (Debian 13), not Bullseye
- Python 3.13 from main apt (no deadsnakes PPA needed on Trixie)
- Explicit note: libcamera is NOT used — ToupTek SDK over USB only
- Environment variables, custom targets (stars.cfg), systemd setup
- Bookworm → Trixie delta table

**wiki/index.md** — quickstart entry added; requirements entry updated.

---

## 2026-04-30 — Sprint 31: Queue domain model + visibility window (M8 start)

**What changed**:

- `smart_telescope/domain/queue.py` (NEW) — Observation queue domain objects:
  - `QueueEntryStatus` enum: PENDING / RUNNING / DONE / FAILED / SKIPPED
  - `QueueEntry` — one observation job: target name/RA/dec, profile, exposure, stack_depth, min_altitude_deg, auto-generated entry_id, status, timestamps (added_at, started_at, completed_at), session_id, failure_reason; `to_dict()` for serialisation
  - `ObservationQueue` — thread-safe ordered list of entries:
    - `add(entry)`, `remove(entry_id) → bool` (PENDING-only), `clear_completed()`
    - `get(entry_id)`, `next_pending()`, `all()`, `pending()`, `to_list()`
    - Protected by `threading.Lock`; RUNNING entries are immune to `remove()`
- `smart_telescope/domain/visibility.py` — added `VisibilityWindow` and `compute_visibility_window()`:
  - `VisibilityWindow(rises_at, sets_at, peak_altitude, peak_time, is_observable)` — frozen dataclass
  - `compute_visibility_window(ra_hours, dec_deg, lat, lon, night_start, night_end, min_altitude_deg=20.0, sample_minutes=5)` — samples altitude at regular intervals, returns the first/last sample above threshold plus peak; accurate to ±sample_minutes minutes; wraps `compute_altaz` so it's fully mockable
- `tests/unit/domain/test_queue.py` (NEW) — 21 tests across 2 classes:
  - `TestQueueEntry` — defaults, unique IDs, `to_dict()` keys/types/timestamps
  - `TestObservationQueue` — empty, add, pending/next_pending, get, remove (PENDING only, not RUNNING), clear_completed, to_list, insertion order, thread-safety (4 concurrent writers × 50 adds = 200 entries, no errors)
- `tests/unit/domain/test_visibility_window.py` (NEW) — 15 tests across 5 classes:
  - `TestVisibilityWindowDataclass` — frozen (attribute mutation raises)
  - `TestNeverObservable` — peak below threshold, None rises/sets, correct peak altitude/time
  - `TestAlwaysObservable` — rises_at = night_start, sets_at = night_end
  - `TestRisesDuringNight` — rises_at is first sample ≥ threshold
  - `TestSetsDuringNight` — sets_at is last sample ≥ threshold
  - `TestSamplingBehaviour` — 6-hour / 60-min → exactly 7 `compute_altaz` calls

**Result**: 923 tests passing, 15 skipped, 95% coverage.

---

## 2026-04-30 — Sprint 30: Frame quality log + integration tests (M7 close)

**What changed**:

- `smart_telescope/domain/frame_quality.py` — added `FrameQualityEntry` dataclass:
  - `{frame_number, snr, baseline_snr, accepted, reason}` — one record per stack frame for post-session review
- `smart_telescope/domain/session.py`:
  - `SessionLog` gains `frame_quality_log: list[FrameQualityEntry]` field
  - `to_dict()` serialises the log as `"frame_quality_log": [{frame, snr, baseline_snr, accepted, reason}, ...]`
- `smart_telescope/workflow/stages.py` — `stage_stack()` appends a `FrameQualityEntry` to `log.frame_quality_log` for every frame evaluated (accepted and rejected alike); entries added only when `frame_quality_filter` is active
- `smart_telescope/adapters/mock/camera.py` — `MockCamera` gains `return_bright: bool` and `dim_on_captures: frozenset[int]` parameters:
  - `return_bright=True` → returns 64×64 noisy star-field frames with measurable SNR (instead of zero frames) for quality-filter integration tests
  - `dim_on_captures={…}` → returns low-SNR (cloud-simulated) frames on the specified capture indices
  - Default behaviour (zeros) unchanged — all existing integration tests unaffected
- `tests/integration/test_vertical_slice.py` — `TestQualityFiltering` class (7 tests):
  - All-bright run: 10 integrated, 0 rejected
  - Dim frames on captures #20 and #21 → 2 rejected, 8 integrated
  - Session completes to SAVED despite rejections (non-fatal)
  - Rejection warning logged per rejected frame
  - `frame_quality_log` populated (10 entries, 2 rejected)
  - Serialised dict contains `frame_quality_log` with correct accepted/rejected flags

**M7 milestone gate status**: 
- Cloud-simulation test (dim captures): `frames_rejected` increments correctly, `frames_integrated` stays correct ✓
- Stack completes to SAVED despite rejections (non-fatal) ✓
- Per-frame SNR + accept/reject written to session JSON for post-session analysis ✓
- Configurable threshold and baseline depth via API query params ✓

**Result**: 887 tests passing, 15 skipped, 95% coverage.

---

## 2026-04-30 — Sprint 29: Frame quality filtering (M7 — It rejects bad frames)

**What changed**:

- `smart_telescope/domain/frame_quality.py` (NEW) — `FrameQualityConfig`, `FrameQualityResult`, `FrameQualityFilter`:
  - `FrameQualityConfig(min_snr_factor=0.3, baseline_frames=3)` — configurable rejection threshold and warmup depth
  - `min_snr_factor=0.0` disables rejection (all frames accepted); range [0.0, 1.0]
  - `FrameQualityFilter.evaluate(frame) → FrameQualityResult` — computes per-frame SNR and compares to rolling baseline
  - **SNR metric**: `(99.5th-percentile signal − sky_median) / sky_MAD` — robust sky-background model; resistant to outliers and hot pixels via MAD noise estimator
  - First `baseline_frames` frames always accepted (building the SNR baseline); baseline is a rolling median of the last N accepted SNRs
  - Rejected frames do NOT update the baseline; the baseline reflects only good frames
- `smart_telescope/workflow/_types.py` — 2 new constants: `FRAME_QUALITY_MIN_SNR_FACTOR = 0.3`, `FRAME_QUALITY_BASELINE_FRAMES = 3`
- `smart_telescope/workflow/stages.py`:
  - `StageContext` gains `frame_quality_filter: FrameQualityFilter | None = None` (None = accept all)
  - `stage_stack()` evaluates quality after each capture; rejected frames skip `stacker.add_frame()` and log a warning; `log.frames_rejected` accumulates both quality rejects and stacker registration rejects (astroalign failures)
  - Frame numbering to stacker uses `accepted_count` (1-indexed over accepted frames only), so the NumpyStacker's reference frame is always the first accepted frame
- `smart_telescope/workflow/runner.py` — gains `enable_frame_quality: bool = True`, `frame_quality_min_snr: float = 0.3`, `frame_quality_baseline_frames: int = 3`; creates `FrameQualityFilter` in `run()` when enabled
- `smart_telescope/api/session.py` — `POST /api/session/run` gains `enable_quality_filter`, `quality_min_snr` (0.0–1.0), `quality_baseline_frames` (1–20) query params
- `tests/unit/domain/test_frame_quality.py` (NEW) — 20 tests across 4 classes:
  - `TestFrameQualityConfig` — defaults, custom values, boundary/invalid validation
  - `TestFrameSnr` — zero/uniform frames return 0.0, noisy star-field returns positive SNR, brighter > dimmer
  - `TestBaselineBuilding` — warmup acceptance, baseline_snr None during warmup, set after warmup
  - `TestAcceptance` — bright accepted, dim rejected, disabled filter passes all, rejected frame skips baseline update, next bright frame still accepted after a reject

**Result**: 880 tests passing, 15 skipped, 95% coverage.

---

## 2026-04-30 — Sprint 28: Refocus triggers (elapsed / altitude / temperature)

**What changed**:

- `smart_telescope/domain/refocus.py` (NEW) — `RefocusConfig`, `RefocusTriggerResult`, `RefocusTracker`:
  - `RefocusConfig(temp_delta_c=1.0, altitude_delta_deg=5.0, elapsed_min=30.0)` — configurable thresholds
  - `RefocusTracker.record_focus(altitude, temperature?)` — snapshot taken immediately after every autofocus
  - `RefocusTracker.check(altitude, temperature?) → RefocusTriggerResult` — returns `{should_refocus, reason}` where reason is `"elapsed"`, `"altitude"`, or `"temperature"`; returns False if no baseline recorded
  - Priority: elapsed checked first (dominant), then altitude, then temperature
  - Temperature trigger skipped silently when either current or baseline temperature is None
- `smart_telescope/domain/session.py` — `SessionLog` gains `refocus_count: int = 0`; included in `to_dict()` under the "autofocus" key
- `smart_telescope/workflow/_types.py` — 3 new constants: `REFOCUS_TEMP_DELTA_C = 1.0`, `REFOCUS_ALT_DELTA_DEG = 5.0`, `REFOCUS_ELAPSED_MIN = 30.0`
- `smart_telescope/workflow/stages.py`:
  - `StageContext` gains `refocus_tracker: RefocusTracker | None = None` (None = triggers disabled)
  - `stage_autofocus()` calls `ctx.refocus_tracker.record_focus(altitude=alt)` after successful autofocus
  - `stage_stack()` checks triggers before each frame (i > 1); if fired: transitions to FOCUSING, runs `run_autofocus()`, records new baseline, increments `log.refocus_count`; autofocus failure is non-fatal (appended to warnings)
  - `_frame_temp(frame: FitsFrame) → float | None` — extracts CCD temperature from FITS header keys "CCD-TEMP", "CCDTEMP", "TEMP"
- `smart_telescope/workflow/runner.py` — gains `enable_refocus_triggers`, `refocus_temp_delta_c`, `refocus_alt_delta_deg`, `refocus_elapsed_min` init params; creates `RefocusTracker` in `run()` (disabled when `skip_autofocus=True` or `enable_refocus_triggers=False`)
- `smart_telescope/api/session.py` — `POST /api/session/run` gains `refocus_temp_delta`, `refocus_alt_delta`, `refocus_elapsed_min`, `enable_refocus` query params; `GET /api/session/status` response gains `refocus_count`
- `tests/unit/domain/test_refocus.py` (NEW) — 25 tests across 6 classes:
  - `TestRefocusConfig` — defaults and custom values
  - `TestNoBaseline` — check before record returns no-refocus
  - `TestElapsedTrigger` — no trigger within interval, triggers at/past threshold
  - `TestAltitudeTrigger` — no trigger within threshold, triggers at threshold, triggers on descent
  - `TestTemperatureTrigger` — no trigger within threshold, triggers at threshold, None-temp handling (both current and baseline)
  - `TestTriggerPriority` — elapsed wins over altitude; record_focus resets all triggers

**Result**: 860 tests passing, 15 skipped, 95% coverage.

---

## 2026-04-30 — Sprint 27: Autofocus backlash compensation

**What changed**:

- `smart_telescope/domain/autofocus.py` — `AutofocusParams` gains `backlash_steps: int = 0`:
  - Default 0 = disabled; any positive value enables backlash compensation
  - Validated ≥ 0 in `__post_init__`; negative value raises `ValueError`
- `smart_telescope/workflow/autofocus.py` — `run_autofocus()` gains backlash logic:
  - **Pre-load**: when `backlash_steps > 0`, moves focuser to `sweep_start − backlash_steps` before the sweep so the first real sweep move is upward (from below)
  - **Final approach**: moves to `best_pos − backlash_steps` then `best_pos`, ensuring the chosen position is always approached from below
  - Zero backlash: no pre-load move; final positioning remains a single `focuser.move(best_pos)` — identical to pre-Sprint-27 behaviour
- `smart_telescope/workflow/_types.py` — `AUTOFOCUS_BACKLASH_STEPS = 0` constant added
- `smart_telescope/workflow/stages.py` — `StageContext.autofocus_backlash_steps: int = 0` added; passed to `AutofocusParams`
- `smart_telescope/workflow/runner.py` — `VerticalSliceRunner.__init__` gains `autofocus_backlash_steps: int = 0`; passed to `StageContext`
- `smart_telescope/api/session.py` — `POST /api/session/run` gains `autofocus_backlash: int` query param (default 0, max 500)
- `tests/unit/workflow/test_autofocus.py` — 7 new tests in `TestBacklashCompensation`:
  - Pre-load move occurs before sweep when `backlash_steps > 0`
  - All sweep moves are ≥ pre-load position (always upward)
  - Final approach sequence is `[best_pos − backlash, best_pos]`
  - Zero backlash: first move equals `sweep_start` (no pre-load below it)
  - Zero backlash: last move is directly `best_pos` (no pre-load step)
  - Sample count is identical with and without backlash
  - Negative `backlash_steps` raises `ValueError`
- `tests/integration/test_vertical_slice.py` — fixed pre-existing state-sequence and capture-count gaps from Sprint 25:
  - `EXPECTED_HAPPY_PATH_STATES` now includes `FOCUSING` between `CENTERED` and `PREVIEWING`
  - `TestStackCaptureFails` updated from `fail_on_capture=6` to `fail_on_capture=17` (align #1 + recenter #2 + 11 autofocus samples + 3 preview = 16 captures before first stack frame)

**Result**: 844 tests passing, 95% coverage. Ruff clean (project sources). Mypy clean (project sources).

---

## 2026-04-26 — Sprint 6: NumpyStacker with astroalign registration

**What changed**:

- `smart_telescope/adapters/numpy_stacker/stacker.py` (NEW) — `NumpyStacker(StackerPort)`:
  - First frame stored as reference (no astroalign needed)
  - Subsequent frames: `astroalign.register(frame, reference)` → mean-stack on success
  - Registration failures: silently rejected, count incremented
  - `get_current_stack()` / `add_frame()` return FITS bytes of mean-stacked float32 array
  - `astroalign` imported at module level as `_aa`; gracefully set to `None` if not installed
  - `ImportError` raised only if second frame attempted without astroalign present
- `smart_telescope/api/deps.py` — `get_stacker()` added:
  - Returns `NumpyStacker` when astroalign available
  - Falls back to `MockStacker` if `ImportError` (tests, no-astroalign environments)
- `tests/unit/adapters/numpy_stacker/test_numpy_stacker.py` (NEW) — 17 tests:
  - `autouse` fixture patches module-level `_aa` → identity mock (no astroalign required on dev machine)
  - Tests cover reset, first-frame reference, registration success/failure, mean arithmetic, SNR improvement

**Result**: 497 tests passing. Ruff clean. Mypy clean.

---

## 2026-04-26 — Sprint 4: Solar exclusion gate (M2 safety)

**What changed**:

- `smart_telescope/domain/solar.py` (NEW) — Solar position + exclusion gate:
  - `sun_position_now() → SolarPosition` via astropy `get_sun(Time.now())`
  - `angular_separation_deg(ra1_h, dec1_d, ra2_h, dec2_d) → float` (degrees)
  - `is_solar_target(ra_h, dec_d, *, threshold_deg=10.0, sun=None) → (bool, float)`
  - Threshold default: 10° exclusion zone around the Sun
- `smart_telescope/api/mount.py` — Solar gate added to `POST /api/mount/goto`:
  - Calls `is_solar_target()` before every slew (unless `?confirm_solar=true`)
  - Returns HTTP 403 with `{"error": "solar_exclusion", "sun_separation_deg": N}` when blocked
  - `confirm_solar=true` bypasses gate entirely (explicit acknowledgement pattern)
- `scripts/spikes/sp3_astroalign_feasibility.py` (NEW) — SP-3 spike:
  - Generates synthetic 2080×3096 frames with 80 Gaussian PSF stars
  - Applies known pixel offset to source frame
  - Calls `astroalign.register()` + `find_transform()`; verifies residual < 2 px
  - Reports timing vs. 30 s budget; advises on downsampling if over budget
- `tests/unit/domain/test_solar.py` (NEW) — 14 solar domain tests
- `tests/unit/api/test_mount.py` — 7 new solar gate tests added to `TestMountGotoSolarGate`

**Result**: 480 tests passing. Ruff clean. Mypy clean.

---

## 2026-04-26 — Sprint 5: WebSocket live preview (M3 foundation)

**What changed**:

- `smart_telescope/domain/stretch.py` (NEW) — `auto_stretch(pixels) → uint8`:
  - 0.5th–99.5th percentile clip + linear scale to [0, 255]
  - Uniform/zero arrays return black (handles MockCamera gracefully)
- `smart_telescope/api/preview.py` (NEW) — `GET /ws/preview?exposure=<s>`:
  - Accepts WebSocket, loops: `capture → stretch → JPEG → send_bytes`
  - Uses `asyncio.to_thread` for the blocking camera call
  - Exposure validated: 0 < exposure ≤ 60 s; invalid values close with 403
  - Handles `WebSocketDisconnect` and abrupt `RuntimeError` cleanly
- `smart_telescope/app.py` — preview router included
- `smart_telescope/static/index.html` — Live Preview panel:
  - Start/Stop buttons with exposure input
  - `<img>` element updated via Blob URL on each binary WebSocket message
  - Frame counter + last-frame timestamp overlay
  - Auto-reconnect on abnormal close (3 s delay); no reconnect on user Stop
  - Connecting / Live / Stopped dot indicator
- `tests/unit/domain/test_stretch.py` (NEW) — 9 stretch tests
- `tests/unit/api/test_preview.py` (NEW) — 16 WebSocket endpoint tests

**Result**: 495 tests passing, 96% coverage. Ruff clean. Mypy clean (49 source files).

---

## 2026-04-26 — SP-1 + SP-2: hardware spike scripts

**What changed**:

- `scripts/spikes/sp1_touptek_arm64.py` — SP-1 spike: checks ARM64 platform, locates `libtoupcam.so`, imports the SDK, enumerates cameras, attempts software-trigger RAW-16 capture. Writes FITS if `--fits-out` path given. Reports PASS / PARTIAL (SDK ok, no camera) / FAIL.
- `scripts/spikes/sp2_astap_pi.py` — SP-2 spike: checks ASTAP binary (ARM64), locates G17 catalog (`.290` files), runs a timed full-sky solve on a provided FITS (or synthetic blank to verify the binary). Reports solve time vs. 60 s threshold. Reports memory snapshot via `free -h`.

**How to run on Pi 5**:
```
# SP-1 (camera must be connected for full PASS)
python scripts/spikes/sp1_touptek_arm64.py --fits-out /tmp/sp1_frame.fits

# SP-2 (sky FITS required for solve-time measurement)
python scripts/spikes/sp2_astap_pi.py --fits /tmp/sp1_frame.fits
```

**Prerequisities**:
- SP-1: place `libtoupcam.so` (ARM64) next to the script (download from ToupTek)
- SP-2: `sudo dpkg -i astap_arm64.deb`; G17 catalog in `~/.astap/`

---

## 2026-04-26 — S0-7: FitsFrame migration — typed domain object throughout pipeline

**What changed**:

- `smart_telescope/domain/frame.py` — added `to_fits_bytes()`:
  - Returns `self.data` if cached bytes are present (file-loaded frames)
  - Otherwise serializes `pixels+header` via astropy (hardware-captured frames, e.g. ToupcamCamera)
- `smart_telescope/ports/solver.py` — `solve(frame_data: bytes, ...)` → `solve(frame: FitsFrame, ...)`
- `smart_telescope/ports/stacker.py` — removed `StackFrame` dataclass; `add_frame(StackFrame)` → `add_frame(frame: FitsFrame, frame_number: int)`
- `smart_telescope/adapters/astap/solver.py` — writes `frame.to_fits_bytes()` to temp file
- `smart_telescope/adapters/mock/solver.py` — updated signature
- `smart_telescope/adapters/mock/stacker.py` — removed `StackFrame`; uses `_count` instead of `_frames` list
- `smart_telescope/workflow/stages.py` — removed `StackFrame` import; passes `frame` directly to solver and stacker; no more `.data` extraction
- `tests/unit/adapters/astap/test_subprocess.py` — updated to construct `FitsFrame` instead of passing raw bytes
- `tests/integration/test_real_solver_replay.py` — updated `solve()` calls; added missing `focuser=MockFocuser()`

**Result**: 473 tests passing, 96% coverage. Ruff clean. Mypy clean (47 source files). S0-7 complete.

---

## 2026-04-24 — M1 API complete: session/connect, solver validation, simulator wiring

**What changed**:

- `smart_telescope/api/session.py` (NEW) — `POST /api/session/connect`:
  - Returns `{camera, mount, focuser, solver}` per-device `{status, error, action}`
  - Always HTTP 200; named error + suggested action for each failed device
  - `solver` field checks ASTAP executable and G17 catalog presence
- `smart_telescope/api/solver.py` (NEW) — `GET /api/solver/status`:
  - Returns `{astap, catalog, ready}` — ASTAP path, catalog dir, boolean readiness
- `smart_telescope/adapters/astap/solver.py` — added `find_g17_catalog(astap_exe)`:
  - Searches executable directory first, then `~/.astap`, `/usr/share/astap`, `C:/ProgramData/astap`
  - Detects G17 catalog by presence of `.290` extension files
- `smart_telescope/api/deps.py` — added `SIMULATOR_FITS_DIR` env var:
  - Priority: `ONSTEP_PORT` → real hardware; `SIMULATOR_FITS_DIR` → SimulatorCamera + SimulatorMount + SimulatorFocuser; neither → mocks
- Tests: 437 passing, 89% coverage

**Result**: All three M1 API stories complete. Remaining M1 gate items require hardware (SP-1/SP-2 on Pi).

---

## 2026-04-24 — SimulatorMount and SimulatorFocuser

**What changed**:

- `smart_telescope/adapters/simulator/mount.py` (NEW) — `SimulatorMount(slew_time_s=0.0)`:
  - `connect()` always returns True
  - `goto()` immediately sets position; enters SLEWING → TRACKING via `threading.Timer` when `slew_time_s > 0`
  - `stop()` cancels pending timer and sets state to UNPARKED
  - `disconnect()` cancels pending timer and sets state to PARKED
  - Thread-safe (all state protected by `threading.Lock`)
- `smart_telescope/adapters/simulator/focuser.py` (NEW) — `SimulatorFocuser(move_time_s=0.0)`:
  - `move()` immediately updates position (instant) or enters moving state via timer
  - `stop()` cancels pending timer without changing position
  - `disconnect()` cancels pending timer and clears moving state
  - Thread-safe
- `tests/unit/adapters/simulator/test_simulator_mount.py` (NEW) — 24 tests
- `tests/unit/adapters/simulator/test_simulator_focuser.py` (NEW) — 20 tests

**Result**: 380 tests passing, 86.32% coverage. Ruff clean. Mypy clean.

---

## 2026-04-24 — OnStep focuser adapter, mount/focuser API + UI

**What changed**:

- `smart_telescope/ports/focuser.py` — added `is_moving() -> bool` and `stop() -> None` abstract methods
- `smart_telescope/adapters/mock/focuser.py` — implemented `is_moving()` (returns False) and `stop()` (no-op)
- `smart_telescope/adapters/onstep/focuser.py` (NEW) — `OnStepFocuser` implementing `FocuserPort`:
  - `connect()`: opens serial, sends `:FA#`, requires reply `"1"` (focuser active)
  - `get_position()`: `:FG#` → int
  - `move(steps)`: `:FS{steps}#` (absolute positioning)
  - `is_moving()`: `:FT#` → True if reply is `"M"`
  - `stop()`: `:FQ#` (no reply)
- `smart_telescope/api/deps.py` (NEW) — singleton dependency providers for mount and focuser; mocks by default; uses real OnStep adapters when `ONSTEP_PORT` env var is set
- `smart_telescope/api/mount.py` (NEW) — FastAPI router with: `GET /api/mount/status`, `POST /api/mount/unpark`, `/track`, `/stop`, `/goto`
- `smart_telescope/api/focuser.py` (NEW) — FastAPI router with: `GET /api/focuser/status`, `POST /api/focuser/move`, `/nudge`, `/stop`
- `smart_telescope/app.py` — includes mount and focuser routers
- `smart_telescope/static/index.html` — Mount panel (state badge, RA/Dec, Unpark/Track/Stop/GoTo) and Focuser panel (position, ±1000/±100/±10 nudge buttons, absolute move, Stop); both panels auto-refresh on load
- `tests/unit/adapters/onstep/test_onstep_focuser.py` (NEW) — 23 adapter tests
- `tests/unit/api/test_mount.py` (NEW) — 19 API tests
- `tests/unit/api/test_focuser.py` (NEW) — 22 API tests

**Result**: 333 tests passing, 87% coverage.

---

## 2026-04-24 — Ingest: OnStep Command Protocol (official wiki)

**Source**: https://onstep.groups.io/g/main/wiki/23755 (retrieved 2026-04-24)

**Pages created**:
- `onstep-protocol.md` — full LX200 command reference: slewing, tracking, park, sync, focuser (all F-commands), date/time, site, firmware; includes adapter implementation notes and two flagged discrepancies

**Pages updated**:
- `hardware-platform.md` — OnStep section now references the protocol page and notes shared serial port for mount + focuser
- `index.md` — added onstep-protocol entry

**Key findings**:
- **Absolute focuser position command confirmed**: `:FS[n]#` (e.g. `:FS1000#` → moves to step 1000, returns 0 or 1). This is what `OnStepFocuser.move(position)` must use.
- **Relative move also available**: `:FR[±n]#` (no reply) — useful for nudge operations.
- **Focuser motion status**: `:FT#` → `M#` (moving) or `S#` (stopped) — enables non-blocking polling.
- **Two discrepancies flagged** vs current `OnStepMount` adapter:
  1. Unpark: spec says `:hR#`, adapter uses `:hU#` — believed to be a V4 vs OnStepX version difference; needs verification on hardware.
  2. Slewing indicator: spec says reply is `0x7F` (DEL), adapter checks for `|` (0x7C) — also likely version-specific; verify on hardware.

---

## 2026-04-23 — Ingest: ToupTek SDK interface description + ToupcamCamera adapter

**Source**: resources/touptek/toupcam.py, resources/touptek/samples/simplest.py

**Pages created**:
- `touptek-sdk.md` — SDK architecture (ctypes wrapper), trigger modes, RAW-16 capture flow, TEC cooling, built-in correction pipeline, filter wheel, event constants, and project adapter design note

**Pages updated**:
- `hardware-platform.md` — expanded ToupTek Camera section: SDK driver choice, RAW-16 mode decision, adapter location
- `index.md` — added touptek-sdk entry

**Code created**:
- `smart_telescope/adapters/touptek/camera.py` — `ToupcamCamera` implementing `CameraPort`; software-trigger RAW-16 mode; threading.Event callback bridge; ctypes buffer; float32 FitsFrame output
- `tests/unit/adapters/touptek/test_touptek_camera.py` — 24 unit tests (connect, capture, disconnect), all green, no hardware required

**Key design decision**: SDK's built-in FFC/DFC corrections are bypassed (`TOUPCAM_OPTION_RAW = 1`); our stacking pipeline handles calibration frame subtraction.

---

## 2026-04-22 — Documentation update: Pi installer, reviewer corrections, Sprint 0 close

**What changed**:
- `README.md` — added Raspberry Pi 5 one-command install section; updated project structure to include `scripts/` and `hardware.yml`; clarified hardware tests live in `hardware.yml` (manual trigger only)
- `docs/agile-plan.md` — updated all Python version references from 3.11 → 3.13; removed deprecated `ANN101`/`ANN102` ruff ignore rules; corrected S0-6 (`asyncio.Event` → `threading.Event`); added `pytest-mock>=3.15` to example `pyproject.toml`; marked Sprint 0 stories S0-1 through S0-6, S0-8, S0-9 as done; updated Sprint 0 DoD checkboxes; noted S0-7 deferred to Sprint 1
- `wiki/vertical-slice-mvp.md` — corrected C8 native pixel scale from `~0.20 arcsec/px` to `0.38 arcsec/px` to match `C8_NATIVE` profile in `runner.py`
- `scripts/install_pi.sh` — new: automated installer for Raspberry Pi OS 64-bit (Bookworm); covers system packages, Python 3.13 via deadsnakes PPA, venv, `pip install -e .[dev]`, optional ASTAP ARM64, verification test run

**Source**: reviewer audit (2026-04-22), `runner.py:49` for pixel scale ground truth

---

## 2026-04-21 — Sprint 0 executed: dev pipeline + TDD foundation

**What changed**:
- `pyproject.toml` — Python version pin relaxed to >=3.10; ruff target-version py310; mypy python_version 3.10; ANN excluded from test files
- `smart_telescope/ports/focuser.py` — new `FocuserPort` ABC (connect, disconnect, move, get_position)
- `smart_telescope/ports/mount.py` — added `stop()` abstract method
- `smart_telescope/adapters/mock/focuser.py` — new `MockFocuser` (fail_connect, move, position)
- `smart_telescope/adapters/mock/mount.py` — implemented `stop()`
- `smart_telescope/workflow/runner.py` — added: structured logging (INFO per state transition), focuser wired into connect stage and cleanup, `stop()` + `threading.Event` cancellation, `_wait_for_slew` checks stop event, `run()` clears event on entry
- `tests/unit/workflow/test_logging.py` — 6 logging tests (TDD: RED → GREEN)
- `tests/unit/workflow/test_focuser.py` — 12 focuser tests (TDD: RED → GREEN)
- `tests/unit/workflow/test_cancellation.py` — 6 cancellation tests (TDD: RED → GREEN)
- `tests/unit/adapters/test_replay_camera.py` — 8 ReplayCamera unit tests
- `.github/workflows/ci.yml` — GitHub Actions: lint → typecheck → test + coverage gate on push/PR
- All source files ruff-clean and mypy-strict-clean

**Result**: 133 tests passing, 15 skipped (hardware), 98% coverage. Ruff clean. Mypy clean. CI configured.

---

## 2026-04-19 — Hardware update: camera changed to ToupTek

**Pages updated**:
- `hardware-platform.md` — added ToupTek camera section; updated summary
- `vertical-slice-mvp.md` — replaced ZWO ASI SDK references with ToupTek SDK
- `README.md` — updated hardware table

---

## 2026-04-19 — Walking skeleton implementation

**Source**: vertical-slice-mvp.md (spec), implementation

**What was built**:
- `smart_telescope/domain/` — `SessionState` enum, 8 typed result dataclasses, `SessionLog` with full `to_dict()` schema
- `smart_telescope/ports/` — abstract interfaces for camera, mount, solver, stacker, storage
- `smart_telescope/workflow/runner.py` — `VerticalSliceRunner`: linear 8-stage pipeline, `WorkflowError`, state machine with `on_state_change` callback
- `smart_telescope/adapters/mock/` — 5 mock adapters with configurable failure modes
- `tests/integration/test_vertical_slice.py` — 28 tests: happy path (11), plate-solve failure (4), recenter exceeded (4), stack failure (2), save failure (3), mount failures (4)

**Result**: 28/28 tests passing. One full `IDLE → SAVED` run executes in <1ms.

---

## 2026-04-19 — Vertical slice definition

**Source**: requirements.md, hardware-platform.md (internal synthesis)

**Pages created**:
- `vertical-slice-mvp.md` — full stage-by-stage spec for the MVP core slice: 8 stages, explicit state machine, acceptance criteria per stage, component map, and out-of-scope boundaries

**Pages updated**:
- `index.md` — added vertical-slice-mvp entry

---

## 2026-04-19 — Ingest: requirements review

**Source**: requirements-review (external analysis, 2026-04-19)

**Pages updated**:
- `requirements.md` — retagged 6 items to MVP (profiles, staged solve, autofocus, optical-train awareness, recentering, session persistence); promoted mosaic/scheduled/multi-night to MVP+; added 4 new sections (connectivity lifecycle, operational fallback, config validity, performance targets); added solar safety gate and emergency stop; marked ~15 items as needing acceptance criteria

**Pages created**:
- `requirements-review.md` — full review verdict, quality critique, retagging rationale, missing sections

---

## 2026-04-19 — Initial ingest: SmartTelescope.md

**Source**: raw/SmartTelescope.md

**Pages created**:
- `smart-telescope.md` — category definition and seven defining traits
- `seestar-s50.md` — ZWO Seestar S50 reference product
- `vaonis-vespera.md` — Vaonis Vespera Pro reference product
- `hardware-platform.md` — Celestron C8 + Raspberry Pi 5 + OnStep V4 platform details
- `plate-solving.md` — concept: autonomous sky alignment
- `live-stacking.md` — concept: real-time computational imaging
- `autofocus.md` — concept: automated focus with star-size metrics
- `requirements.md` — full MVP/MVP+/Full requirement set for the C8 build
- `index.md` — initial table of contents
- `log.md` — this file

---

## 2026-05-17 — BUG-009, BUG-024, M3-004

**What changed:**

- `api/autogain.py` (BUG-024): `_worker()` now resolves the optical train for the
  camera being processed and ANDs `train.has_focuser` with the global
  `focuser.is_available`.  Guide cameras configured without a focuser no longer
  receive `POSSIBLE_FOCUS_OR_POINTING_ERROR` from autogain when the main camera's
  OnStep focuser is connected.  Falls back to global availability when the camera
  index is not found in any train.

- `static/index.html` (BUG-009): Replaced the "any camera has TEC" heuristic for
  cooling card visibility with a per-selected-camera check.  New
  `onCoolingCamChange(role)` function fetches `/api/cameras/{idx}/capabilities` and
  shows or hides the cooling card based on `caps.has_tec`.  Called on
  `s1-cooling-cam-select` `onchange`, on "Connect All", and at page init.

- `tests/unit/api/test_r4_role_camera.py`: Four new tests in
  `TestAutogainHasFocuserPerTrain` covering: guide cam no focuser (even when global
  focuser available), main cam focuser present and available, main cam focuser
  configured but hardware unavailable, unknown camera index falls back to global.

**todo.md:** BUG-009, BUG-024, M3-004 marked complete.

---

## 2026-05-17 — R5-001..003, BUG-008

**What changed:**

- `config.py` (R5-001..003): Replaced bare module-level TOML loading + `sys.exit`
  with:
  - `ConfigError` exception class — structured parse failure type
  - `_load_config_from_disk()` — encapsulates all file reading logic (explicit load)
  - `_load_error` module variable — stores parse error without killing the process
  - `check_load_error()` — raises `ConfigError` if load failed; called from
    `RuntimeContext.connect_devices()` so bad configs surface at Connect All time

- `services/readiness.py`: `_check_config_file()` now checks `_load_error` first
  and returns a RED item with the parse error message and repair guidance.

- `tests/unit/api/test_readiness.py`: 8 new tests:
  - `TestConfigError`: check_load_error() no-op on no error, raises on error,
    readiness RED on parse error, overall RED on parse error
  - `TestExpandPath`: tilde expansion, empty string, absolute path, and verifies
    that `config.STARS_CFG` contains no literal `~` (BUG-008 regression guard)

- BUG-008 confirmed resolved by R5-004's `_expand()` — `STARS_CFG` is always
  expanded at module load time, never stored with `~`.

**todo.md:** R5-001..003, BUG-008, M3-002 marked complete.

---

## 2026-05-17 — R2-003, R2-005, M3 milestone cleanup

**What changed:**

- `services/device_state.py` (R2-003): Added `record_command(name)`,
  `record_command_error(msg)`, `get_last_command() → (name, at, err)` to
  `DeviceStateService`.

- `services/device_state.py` (R2-005): Added `wait_for_mount_state(target, timeout_s)`
  (polls until state equals target) and `wait_while_mount_state(current, timeout_s)`
  (polls until state differs from current).  Both use the background-poll cache for
  consistency with what the UI sees.

- `api/mount.py` (R2-003): All command endpoints — park, unpark, goto, home, track,
  stop — now call `device_state.record_command(name)` before issuing and
  `record_command_error(msg)` on failure.  `MountStatus` extended with
  `last_command`, `last_command_age_s`, `last_command_error`.

- `api/mount.py` (R2-005): `mount_unpark` now uses `wait_while_mount_state(PARKED)`
  (uses cached state, consistent with UI) instead of a direct hardware poll loop.
  `mount_park` waits up to 5 s for PARKED confirmation after issuing the command.

- `tests/unit/services/test_device_state.py`: 10 new tests — R2-003 command tracking
  (initial None, record clears error, error keeps name, overwrite), R2-005 convergence
  helpers (immediate match, timeout, transition detection for both helpers).

- `docs/todo.md`: M3-001, M3-003, M3-005, BUG-003, BUG-017 marked complete.
  R2-003, R2-005 marked complete.
