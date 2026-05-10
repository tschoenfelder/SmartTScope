# SmartTScope — Auto Gain / Calibration / Cooling — Task List

Source requirement: `resources/hlrequirements/SmartTScope_AutoGain_Requirements.md` v1.0  
Implementation phases follow section 16 of that document.

**Legend**
- `[ ]` pending &nbsp;·&nbsp; `[x]` done &nbsp;·&nbsp; `[~]` in progress
- Each task is scoped for roughly one session.
- *Depends:* lists task IDs that must be complete first.

---

## Phase 0 — Foundation and capability discovery ✅

### AGT-0-1 — Extend CameraPort and ToupcamCamera with full control API ✅
- [x] Add `get/set_exposure_ms()`, `get/set_gain()`, `get/set_black_level()`,
  `get/set_conversion_gain()` (HCG / LCG / HDR), `get_bit_depth()`,
  `get_temperature()` to `ports/camera.py` (abstract) and
  `adapters/touptek/camera.py` (real implementation).
- [x] Add `get_capabilities() → CameraCapabilities` dataclass:
  `min/max_gain`, `min/max_exposure_ms`, `supports_cooling`,
  `supports_hcg`, `supports_lcg`, `supports_hdr`, `bit_depth`,
  `pixel_size_um`, `sensor_width_px`, `sensor_height_px`.
- [x] Keep mock and simulator adapters in sync (stub values).
- [x] Unit tests covering capability query and each setter/getter path.

*Covers:* FR-AG-020 (app controls limits), Phase 0 steps 1–2  
*Depends:* —

---

### AGT-0-2 — Camera identity, CameraProfile, and OpticalTrainProfile models ✅
- [x] Add `serial_number` / `logical_name` to `CameraPort`; implement in
  ToupcamCamera via `Toupcam.EnumV2` device info.
- [x] Create `domain/camera_profile.py`:
  `CameraProfile` (model, sensor, pixels, pixel_um, max_gain, unity_gain_hcg,
  unity_gain_lcg, min_preview_exp_ms, max_preview_exp_ms, supports_cooling)
  for ATR585M, G3M678M, GPCMOS02000KPA.
- [x] Create `domain/optical_train.py`:
  `OpticalTrainProfile` (profile_id, focal_mm, camera_model, pixel_scale_arcsec,
  role) for all 7 profiles in §1.2.
- [x] Unit tests for each profile constant and pixel-scale derivation.

*Covers:* §1.1, §1.2, §1.3, Phase 0 steps 3–4  
*Depends:* AGT-0-1

---

### AGT-0-3 — Replay camera adapter for deterministic tests ✅
- [x] `adapters/replay/camera.py`: reads FITS files from a directory in
  order; wraps them as `FitsFrame`; supports `set_gain()` / `set_exposure()`
  stubs so auto-gain loops can run without hardware.
- [x] Register in `deps._build_adapters()` via `REPLAY_FITS_DIR` env var
  (lower priority than `SIMULATOR_FITS_DIR`).
- [x] Unit tests: auto-gain loop converges on a set of replay frames
  with known statistics.

*Covers:* Phase 0 step 5, NFR-007  
*Depends:* AGT-0-1

---

## Phase 1 — Storage model

### AGT-1-1 — App-state folder and image-root configuration ✅
- [x] `domain/storage_config.py`: `resolve_app_state_dir()` — checks
  `~/.SmartTScope` then `~/.smarttscope`, creates if absent (FR-STORE-001).
- [x] Add `IMAGE_ROOT` to `config.py` (env var + `smart_telescope.toml`).
- [x] `domain/session_folder.py`: `make_session_path(image_root, target, date)`
  → `image_root/YYYY-MM-DD_<sanitised_target>/` (FR-STORE-004).
- [x] Unit tests: folder resolution, sanitisation edge cases.

*Covers:* FR-STORE-001, FR-STORE-002, FR-STORE-003, FR-STORE-004  
*Depends:* —

---

### AGT-1-2 — Master calibration library and calibration index ✅
- [x] `domain/calibration_store.py`:
  - `master_path(image_root, camera_model, serial, cal_type, **meta)`
    → `image_root/masters/<model>_<serial>/biases|darks|flats/<filename>.fits`
    (FR-STORE-005, FR-STORE-006).
  - `CalibrationIndex` class: load / save `calibration_index.json` with
    relative paths (FR-STORE-009).
  - `find_best_match(index, cal_type, criteria)` → best entry or `None`
    with `MismatchDetail` (FR-CAL-060, FR-CAL-070).
- [x] `domain/last_good_settings.py`: load / save per-camera-profile
  last-good gain/exposure/offset/conversion-gain JSON in app-state folder
  (FR-STORE-008, FR-AG-010 step 4).
- [x] Unit tests: index round-trip, matching logic (exact/partial/mismatch).
  45 tests, all green. Suite: 1228 passed, 86.81% coverage.

*Covers:* FR-STORE-005–009, FR-CAL-060, FR-CAL-070, FR-STORE-008  
*Depends:* AGT-1-1

---

## Phase 2 — Histogram and frame statistics

### AGT-2-1 — HistogramAnalyzer domain service and REST endpoint ✅
- [x] `domain/histogram.py`:
  - `HistogramStats` dataclass: `p50`, `p95`, `p99`, `p99_5`, `p99_9`,
    `mean_frac`, `saturation_pct`, `zero_clipped_pct`, `black_level`,
    `effective_bit_depth`, `adc_max`.
  - `analyze(pixels, bit_depth) → HistogramStats`: normalise to effective
    bit-depth (FR-AG-060), compute all percentiles, saturation and
    zero-clipped pixel counts.
  - `histogram_bins(pixels, bit_depth, n_bins=512) → (counts, edges)`.
- [x] `POST /api/histogram/analyze` — accepts camera_index + exposure + gain,
  captures one frame, returns `HistogramStats` + bin data as JSON.
- [x] Unit tests: 8-bit, 12-bit-in-16, uniform / saturated / dark frames.
  38 tests, all green. Suite: 1266 passed, 87.03% coverage.

*Covers:* FR-AG-050, FR-AG-060, FR-AG-070  
*Depends:* AGT-0-1

---

### AGT-2-2 — Raw linear histogram UI widget ✅
- [x] Canvas-based histogram widget reusable across preview, polar, stack,
  and calibration panels.
- [x] Draws log-scale bar chart over linear raw-intensity bins (not stretch).
- [x] Overlays: black-level marker (blue), 75–80% target band (green),
  saturation marker at right edge (red).
- [x] Inline stats strip inside canvas: 0-clip %, p50, p99, sat %.
- [x] Full stats text line below canvas: p50/p95/p99/p99.5/p99.9/sat/0-clip.
- [x] Replaced existing JPEG-decode overlay histogram with this widget.
- [x] `showHistogram(canvasId, statsId, stats, binCounts, binEdges)` callable
  from any panel. Hist panel shows/hides cleanly; interval cleared on stop.
- [x] `_fetchAndDrawHistogram()` polls POST /api/histogram/analyze every 4 s
  when histogram is enabled. Suite: 1266 passed, 87% coverage (UI-only).

*Covers:* FR-AG-050, FR-UI-001  
*Depends:* AGT-2-1

---

## Phase 3 — Calibration master library

### AGT-3-1 — Bias preparation ✅
- [x] `domain/calibration_capture.py`: `prepare_bias(camera, n_frames, **meta)`
  — minimum exposure, configured gain/offset/conversion-gain, stacks N frames
  into master bias FITS, validates histogram is bias-compatible (FR-CAL-010).
- [x] `POST /api/calibration/bias` endpoint: starts async job, streams
  progress via `GET /api/calibration/status`.
- [x] Stage 4 (Collimation) UI: add "Prepare Bias" button with progress
  display and stored-path confirmation (FR-UI-001, FR-CAL-001).
- [x] Writes master FITS + updates `calibration_index.json` (FR-CAL-050).
- [x] Unit tests using replay camera.
  24 new tests. Suite: 1315 passed, 87.35% coverage.

*Covers:* FR-CAL-001, FR-CAL-010, FR-CAL-050, FR-STORE-005  
*Depends:* AGT-1-2, AGT-0-3

---

### AGT-3-2 — Dark preparation ✅
- [x] Extend `calibration_capture.py`: `prepare_dark(camera, exposure_ms,
  n_frames, **meta)` — matches intended light-frame settings, validates
  histogram is dark-compatible (floor + saturation), returns temperature
  warning string when applicable (FR-CAL-020, FR-TEMP-007).
- [x] `POST /api/calibration/dark` endpoint + UI button in Stage 4.
- [x] Writes master FITS + updates index.
- [x] 21 new unit tests. Suite: 1336 passed, 87.39% coverage.

*Covers:* FR-CAL-020, FR-CAL-050, FR-TEMP-007  
*Depends:* AGT-3-1

---

### AGT-3-3 — Flat preparation ✅
- [x] Extend `calibration_capture.py`: `prepare_flat(camera, optical_train,
  filter_id, n_frames, **meta)` — iterates exposure toward 50% median target
  (accept 40–60%, warn 35–40% / 60–70%, reject <35% / >70%); stacks master
  flat per optical-train + filter (FR-CAL-030, FR-CAL-040).
- [x] `POST /api/calibration/flat` endpoint + UI button.
- [x] Show informational note about rotation / focus user responsibility.
- [x] Writes master FITS + updates index.
- [x] Unit tests with a replay camera that has a known flat level.

*Covers:* FR-CAL-030, FR-CAL-040, FR-CAL-050  
*Depends:* AGT-3-1, AGT-0-2 (optical train profile)

---

### AGT-3-4 — Calibration matching service and mismatch warnings ✅
- [x] Implement `find_best_match()` properly (AGT-1-2 stub → production):
  bias, dark, flat criteria tables from §FR-CAL-060.
- [x] `GET /api/calibration/match` — returns MATCHED/PARTIAL/NOT_FOUND per
  type; `CalibrationMatchResult` + `CalibrationMatchResponse` Pydantic models.
- [x] UI: calibration match summary in Stage 4 (calibration card) and Stage 5
  (session setup); green/yellow/red badges; shows mismatch fields with "Use anyway?" hint.
- [x] Unit tests: exact match, partial mismatch, temperature tolerance (±5 °C),
  missing master, 503 when IMAGE_ROOT not configured.
  10 new tests. Suite: 1367 passed, 87.46% coverage.

*Covers:* FR-CAL-060, FR-CAL-070, FR-CAL-080 (precursor)  
*Depends:* AGT-3-1, AGT-3-2, AGT-3-3

---

## Phase 4 — ATR585M cooling controller

### AGT-4-1 — CoolingController domain service ✅
- [x] `domain/cooling.py`:
  - `CoolingConfig` dataclass: `target_c` (−10°C default, min clamp −10°C),
    `stable_power_limit_pct` (75), `warning_power_pct` (80),
    `stabilisation_timeout_s` (300), `relax_step_c` (1) (FR-TEMP-001–006).
  - `CoolingController.tick(current_temp_c, current_power_pct)` → action:
    `HOLD | RAISE_TARGET | WARN | STABLE`.
  - Stabilisation state machine: allow high power during cooldown; relax
    target step-wise after timeout if power remains above stable limit.
- [x] Unit tests: cooldown sequence, target-relaxation, clamp enforcement.
  27 new tests. Suite: 1399 passed, 85.39% coverage.

*Covers:* FR-TEMP-001–006  
*Depends:* AGT-0-1 (temperature capability)

---

### AGT-4-2 — Cooling REST endpoint and UI ✅
- [x] `POST /api/cooling/set_target`, `GET /api/cooling/status` →
  `CoolingStatus` (current_temp_c, target_c, power_pct, stable, warning_msg).
- [x] Stage 1 ATR585M camera card: target-temperature selector
  (−10°C to +10°C in 1°C steps, no lower than −10°C); power gauge;
  stabilisation countdown badge; warning when target is relaxed (FR-UI-003).
- [x] Background task polling `CoolingController.tick()` every 30s while
  cooling is enabled.
- [x] Unit tests for endpoint state machine.
  20 new tests. Suite: 1419 passed, 85.00% coverage.

*Covers:* FR-TEMP-001–007, FR-UI-003  
*Depends:* AGT-4-1

---

## Phase 5 — MVP one-shot Auto Gain (main camera)

### AGT-5-1 — Enhance AutoGainController with camera-profile limits ✅
- [x] Refactor `domain/autogain.py`:
  - Accept `CameraProfile` → derive `min_gain`, `max_gain`,
    `min_exp_ms`, `max_exp_ms` (replaces hardcoded constants).
  - Add `conversion_gain` selection: choose HCG/LCG/HDR from profile
    rules table (FR-AG-080, §FR-AG-090 steps 2–3).
  - Add `offset_adu` field: shift histogram baseline check to avoid
    zero-clipping (FR-AG-070, §FR-AG-090 steps 4, 7).
  - Effective bit-depth normalisation via `HistogramStats` (not raw mean).
- [x] Keep existing WebSocket autogain mode working; update to pass profile.
- [x] Unit tests: ATR585M HCG profile, G3M678M LCG planetary profile.
  34 new tests. Suite: 1453 passed, 85% coverage.

*Covers:* FR-AG-020, FR-AG-080, FR-AG-090 steps 1–4  
*Depends:* AGT-0-2, AGT-2-1

---

### AGT-5-2 — AutoGainService one-shot flow and status classification ✅
- [x] `domain/autogain_service.py`:
  - `AutoGainService.run_one_shot(camera, profile, mode, last_good,
    calibration_stats) → AutoGainResult`.
  - `AutoGainResult`: `status` (FR-AG-100 enum), `exposure_ms`, `gain`,
    `offset`, `conversion_gain`, `histogram_stats`, `warning_msg`.
  - Adjustment loop following §FR-AG-090 order (steps 5–13).
  - Dust-cap / no-signal detection: if mean < 2% at max gain and 4s
    → `AUTO_GAIN_NO_SIGNAL` / `AUTO_GAIN_POSSIBLE_DUST_CAP`.
- [x] Unit tests: OK path, no-signal path, dust-cap path, over-bright path,
  gain-limit path, cancellation, last-good, calibration stats, unsupported.
  21 tests all green.

*Covers:* FR-AG-010, FR-AG-030, FR-AG-090, FR-AG-100  
*Depends:* AGT-5-1, AGT-1-2 (last-good), AGT-2-1

---

### AGT-5-3 — Auto Gain REST endpoint, UI button, and last-good persistence ✅
- [x] `POST /api/autogain/run` — runs `AutoGainService.run_one_shot()` in background,
  returns 202; `GET /api/autogain/status` polls result; `POST /api/autogain/cancel`.
- [x] Preview section: **Auto Gain** button with spinner badge, result badge
  (OK/status), Apply button that copies exp/gain/offset into preview inputs.
- [x] On `AUTO_GAIN_OK`: persists `LastGoodSettings` to `~/.SmartTScope/last_good/`
  via `LastGoodStore`.
- [x] 20 unit tests: idle status, run/409/400/422, cancel, round-trip OK, camera
  error, last-good saved on OK / not saved on non-OK.

*Covers:* FR-AG-010, FR-UI-001, FR-STORE-008  
*Depends:* AGT-5-2, AGT-1-2

---

### AGT-5-4 — Diagnostic escalation (no-signal prompt) ✅
- [x] When `AUTO_GAIN_NO_SIGNAL` after 4s: show inline prompt
  "No usable signal within normal exposure. Run diagnostic up to 10 s?" (FR-AG-040).
- [x] API `diagnostic:bool` flag extends profile max_preview_exp_ms to 10 000 ms;
  service classifies `NO_SIGNAL`, `POSSIBLE_DUST_CAP`, or
  `POSSIBLE_FOCUS_OR_POINTING_ERROR` (tiny-signal heuristic: eff_mean in 0.001–0.02).
- [x] UI shows actionable message per FR-UI-002 for each classification.
- [x] Tests: all three classification branches + API diagnostic flag propagation
  and profile extension (5 new API tests, 2 new service tests).

*Covers:* FR-AG-030, FR-AG-040, FR-AG-100, FR-UI-002  
*Depends:* AGT-5-3

---

## Phase 6 — Calibration in live stacking

### AGT-6-1 — Calibration master selection at stack start ✅
- [x] `POST /api/session/run` accepts optional `bias_path`, `dark_path`,
  `flat_path` query params; validates each file exists and is readable FITS.
- [x] Calibration masters loaded into memory before runner thread starts.
- [x] `_apply_calibration()` helper wires masters into stacker via duck-typed
  `set_calibration()` call; logs which masters are applied.

*Covers:* FR-CAL-060, FR-CAL-070, FR-CAL-080  
*Depends:* AGT-3-4

---

### AGT-6-2 — Apply calibration frames during live stacking ✅
- [x] `NumpyStacker.set_calibration(bias, dark, flat)` — stores dark master
  (falls back to bias if no dark), normalised flat; calibration persists
  across `reset()` calls.
- [x] `NumpyStacker._calibrate()` — subtracts dark then divides by flat_norm
  before frames are accumulated.
- [x] `StackedImage.calibrated` flag set True whenever dark or flat active.
- [x] WebSocket `/ws/stack` sends `calibrated` in JSON metadata frame.
- [x] UI: "Calibrated" badge shown in stack info row when `calibrated=True`;
  hidden on `_s5ResetRunUI()`.
- [x] 16 new unit tests in `TestSetCalibration`, `TestDarkSubtraction`,
  `TestFlatDivision`, `TestDarkAndFlat`, `TestResetPreservesCalibration`.

*Covers:* FR-CAL-080, AC-CAL-007  
*Depends:* AGT-6-1

---

## Phase 7 — Guide and OAG camera auto gain

### AGT-7-1 — One-shot auto gain for guide / OAG cameras ✅
- [x] `OAG_678M` camera profile added (`camera_profile.py`): IMX678, HCG+LCG,
  max_preview_exp_ms = 5 000 ms (guide ceiling); `GPCMOS02000KPA` already existed.
- [x] `AutoGainService.run_one_shot()` GUIDING mode: uses `p99_9` (guide-star
  peak) instead of `mean_frac` as signal metric; target band 20–80 % vs 12–45 %;
  offset auto-raise skipped (dark background is expected); custom NO_SIGNAL message.
- [x] Guide Camera Auto Gain card in Stage 4 (Collimation): cam-idx + model
  selector, Auto Gain / Cancel buttons, result row with "Locked" badge and
  "Reuse" button after OK; JS: `guideAgRun()`, `guideAgCancel()`,
  `_guideAgPoll()`, `_guideAgShowResult()`.
- [x] 14 new unit tests: OK path, no-star, dust-cap, brightening/dimming
  convergence, offset suppression, CG selection, profile constants.

*Covers:* FR-GUIDE-001, AC-GUIDE-001  
*Depends:* AGT-5-3, AGT-0-2

---

### AGT-7-2 — MVP+ 5-minute guide monitoring
- [ ] Background task: every `guide_check_interval_s` (default 300, configurable)
  inspect recent guide frames via `HistogramAnalyzer`.
- [ ] Apply only small bounded adjustments (±10% gain, ±20% exposure max)
  with hysteresis (no change if within ±15% of target).
- [ ] Status values: `GUIDE_GAIN_OK / STAR_WEAK / STAR_SATURATED /
  ADJUSTED / DAWN_WARNING` (FR-GUIDE-002).
- [ ] Show last-check time + status badge in guide-camera panel.
- [ ] Unit tests: weak-star path, saturation path, dawn-drift path.

*Covers:* FR-GUIDE-002, AC-GUIDE-002  
*Depends:* AGT-7-1

---

## Phase 8 — Planetary auto gain

### AGT-8-1 — Planet detection and PLANET_PROTECTED mode
- [ ] `domain/planet_detection.py`: detect brightest real object
  (flux-weighted score = total_flux × √area, masks hot pixels);
  return `DetectedObject(center_px, radius_px, peak_frac, saturation_pct)`.
- [ ] `AutoGainService` `AUTO_GAIN_PLANETARY` mode: use `DetectedObject`
  saturation as brightness reference; ensure planet peak stays ≤ 80%
  full-scale; reduce exposure first before gain (FR-PLANET-001,
  FR-PLANET-003 `PLANET_PROTECTED`).
- [ ] Unit tests with synthetic planet frame.

*Covers:* FR-PLANET-001, FR-PLANET-003, FR-PLANET-004  
*Depends:* AGT-5-2, AGT-2-1

---

### AGT-8-2 — Moon visibility and PLANET_WITH_MOONS mode (MVP+)
- [ ] After `PLANET_PROTECTED` converges: estimate moon SNR by analysing
  pixels outside planet ROI; report if moons are detectable (FR-PLANET-002).
- [ ] `PLANET_WITH_MOONS` mode: if planet is protected, allow small gain
  increase until moons reach SNR threshold or planet reaches 90% cap; show
  trade-off message if moons remain undetectable (FR-PLANET-002,
  FR-PLANET-003 `PLANET_WITH_MOONS`).
- [ ] UI: moon-visibility indicator in planetary capture panel.
- [ ] Unit tests.

*Covers:* FR-PLANET-002, FR-PLANET-003  
*Depends:* AGT-8-1

---

## Phase 9 — Guided DSO (MVP+)

### AGT-9-1 — Guided DSO exposure ceiling and preconditions
- [ ] `AUTO_GAIN_DSO_GUIDED` mode in `AutoGainService`: add
  `max_guided_exp_ms` parameter; selectable ceiling (10s / 30s / 60s)
  shown in DSO recording-setup panel (FR-DSO-002).
- [ ] Precondition check: guiding must be active (stub: check guide-task
  state); warn if not guiding.
- [ ] Calibration matching for longer dark exposures (AGT-3-4 already
  supports this; add 30s / 60s dark options to calibration UI).
- [ ] Unit tests.

*Covers:* FR-DSO-001, FR-DSO-002, AC-DSO-001  
*Depends:* AGT-5-4, AGT-7-1

---

## Phase 10 — Continuous convergence (MVP+)

### AGT-10-1 — Continuous auto mode with damping and hysteresis
- [ ] `AutoGainController` continuous mode: after initial one-shot
  converges, enter monitoring loop; use rolling mean over last N frames
  to detect drift; apply updates only when outside hysteresis band (±10%
  of target) (FR-DSO-003).
- [ ] `autogain=continuous` WebSocket query parameter; stream metadata
  frame with current exposure/gain/status alongside JPEG.
- [ ] Safety: never change settings during a recording unless
  `allow_during_recording` flag is set; log every change (NFR-005).
- [ ] UI: "Continuous AG" toggle in preview controls (MVP+ badge).
- [ ] Unit tests: convergence, hysteresis, recording lock-out.

*Covers:* FR-DSO-003, AC-AG-005, NFR-005  
*Depends:* AGT-5-3, AGT-7-2

---

## Phase 11 — SIRIL compatibility

### AGT-11-1 — Prepare SIRIL Folder
- [ ] `domain/siril_prep.py`: `prepare_siril_folder(session_path, image_root,
  index, criteria)` — selects matching masters, copies them into
  `session/biases|darks|flats/`, writes `calibration_selection.json`;
  real file copies, no symlinks (FR-SIRIL-001–004).
- [ ] `POST /api/calibration/prepare_siril` endpoint.
- [ ] Session detail panel: **Prepare SIRIL Folder** button; shows copied
  files list and any mismatch warnings (AC-SIRIL-001, AC-SIRIL-002).
- [ ] Unit tests using temp directories.

*Covers:* FR-SIRIL-001–004, AC-SIRIL-001–002  
*Depends:* AGT-3-4

---

## Progress summary

| Phase | Tasks | Done |
|---|---:|---:|
| 0 — Foundation | 3 | 3 |
| 1 — Storage | 2 | 2 |
| 2 — Histogram | 2 | 2 |
| 3 — Calibration masters | 4 | 4 |
| 4 — Cooling | 2 | 2 |
| 5 — Auto Gain MVP | 4 | 4 |
| 6 — Live stacking calibration | 2 | 2 |
| 7 — Guide camera | 2 | 1 |
| 8 — Planetary | 2 | 0 |
| 9 — Guided DSO | 1 | 0 |
| 10 — Continuous convergence | 1 | 0 |
| 11 — SIRIL | 1 | 0 |
| **Total** | **26** | **19** |

---

*Last updated: 2026-05-10 — AGT-7-1 done (22/26)*
