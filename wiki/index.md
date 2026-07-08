# Wiki Index

Table of contents for the SmartTelescope knowledge base.

---

## Concepts

- [smart-telescope](smart-telescope.md) — Definition and seven defining traits of the smart telescope category
- [plate-solving](plate-solving.md) — Autonomous sky alignment by matching star patterns to a catalog
- [live-stacking](live-stacking.md) — Real-time frame integration for progressive deep-sky image improvement
- [autofocus](autofocus.md) — Automated focus optimization using star-size metrics and a motor focuser
- [bahtinov-analyzer](bahtinov-analyzer.md) — Diffraction spike detection algorithm: crossing-error metric, two-layer BahtinovAnalyzer/FocusController design

## Hardware and products

- [hardware-platform](hardware-platform.md) — Target build: Celestron C8 + Raspberry Pi 5 + OnStep V4
- [touptek-sdk](touptek-sdk.md) — ToupTek toupcam SDK: architecture, trigger/RAW/TEC/filter-wheel API, and adapter design
- [onstep-protocol](onstep-protocol.md) — Full LX200 command reference for OnStep V4: mount, focuser, park, tracking, with adapter implementation notes
- [OnStep adapter replacement requirements](../resources/hlrequirements/smarttscope_onstep_adapter_replacement_requirements.md) — Safety state machine (9 states), layered architecture, HOME/PARK confirmation, limit readback, LIMIT_HIT recovery; deferred pending external party + Q1–Q10 answers
- [OnStepAdapter external module](../SYNC.md) — External pip package tschoenfelder/OnStepAdapter (currently v0.3.0); migration plan ONS-MIGRATE-001..013 in `docs/todo.md` aims to reduce `smart_telescope/adapters/onstep/` to a ≤30-line MountPort shim; active SYNC-OVERRIDEs, upstream contribution requirements (REQ-1, REQ-2, REQ-ST-001..007), and upgrade procedure in SYNC.md
- [seestar-s50](seestar-s50.md) — ZWO Seestar S50 reference smart telescope
- [vaonis-vespera](vaonis-vespera.md) — Vaonis Vespera Pro reference smart telescope

## Planning

- [requirements](requirements.md) — Full MVP / MVP+ / Full requirement set for the C8 + Pi 5 + OnStep build (revised; §14 process requirements added 2026-04-30)
- [requirements-review](requirements-review.md) — External review: verdict, retagging rationale, and missing requirement areas
- [requirements-addon-20260430](requirements-addon-20260430.md) — Star catalog expansion, quickstart corrections, and process requirements (2026-04-30)
- [requirements-addon-20260501](requirements-addon-20260501.md) — First hardware test session bugs and mount safety requirements (2026-05-01)
- [requirements-addon-20260502b](requirements-addon-20260502b.md) — README update instructions + focuser always-expected policy, shared serial delegation, is_available (2026-05-02)
- [requirements-addon-20260506](requirements-addon-20260506.md) — Fix/update requirements: camera naming, Live Preview backend, histogram, exposure/gain UI, Startup polish (2026-05-06)
- [smarttscope-incident-requirements-v1-2](../resources/hlrequirements/smarttscope_incident_requirements_final_v1_2.md) — M8 source: runtime state model, operation gates, Stage 1 trust, command history, FITS diagnostics, click-to-center (v1.2, 2026-06-25; 18 DEC, 12 INC, ~40 REQ)
- [vertical-slice-mvp](vertical-slice-mvp.md) — End-to-end MVP slice: power-on → align → GoTo M42 → recenter → stack 10 frames → save
- [quickstart](quickstart.md) — First-time setup guide: Raspberry Pi OS Trixie (Debian 13), ToupTek camera, ASTAP, no libcamera

## Release readiness

- [release-notes-v0.1](../docs/release-notes-v0.1.md) — First MVP release notes: features, known issues, hardware-blocked items, deferred scope, install/upgrade path
- [operational-acceptance-checklist](../docs/operational-acceptance-checklist.md) — 10-step field checklist: connect → setup check → solar gate → GoTo → autofocus → STOP → stack → shutdown
- [hardware-test-log-template](../docs/hardware-test-log-template.md) — Append-only evidence log with six required items (E-001 to E-006) for R7-004 release gate
- [release-checklist](../docs/release-checklist.md) — Go/no-go gate: backlog, hardware evidence, acceptance, tests, clean install, performance, sign-off

## Guiding

- [guiding requirements](../resources/hlrequirements/onstep_guiding_requirements.md) — Guide-camera processing pipeline: frame acquisition, centroid, pulse-guide corrections, CPU budgeting, GUD-001..008 todo items
- [guiding pipeline plan](../docs/superpowers/plans/2026-05-23-guiding-pipeline.md) — 6-task MetaGuide-inspired implementation plan: FrameMailbox, GuideCentroidEstimator, GuideSourceSelector, MeasureOnlyGuideController, GuidingService, REST API, frontend card
- **GUD-002..007 done:** `FrameMailbox` + `ManagedCamera` (latest-frame drop mailbox, background capture thread); `GuideCentroidEstimator` (MAD noise, windowed centroid, saturation+SNR check); `GuideSourceSelector` (primary/fallback logic); `MeasureOnlyGuideController` (deadband, pulse clamping); `GuidingService` (TOCTOU-safe lifecycle, measure-only mode, real pulse path, `pause_pulses`/`resume_pulses`/`rebaseline`, `rms_px`/`last_pulse` in status); REST API (`POST /api/guiding/start|stop`, `GET /api/guiding/status`); Guide Monitor card in UI (advanced mode only)
- [collimation guiding integration plan](../docs/superpowers/plans/2026-05-24-collimation-guiding-integration.md) — 5-task plan: `GuidingService` pause/resume/rebaseline, `CollimationConfig` guiding fields, `CollimationAssistant` lifecycle + recentering, API factory wiring, wizard guide status row
- **Collimation guiding done:** `GuidingService` extended with `pause_pulses`/`resume_pulses`/`rebaseline` + `rms_px`/`last_pulse` on status; `CollimationConfig` gets `guiding_camera_role`/`guiding_exposure_s`/`guiding_cadence_s`; `CollimationAssistant` injects `GuidingService`, starts guiding after `AUTO_EXPOSURE`, stops in `finally`, calls `_with_guiding_paused(_recenter_star)` before each remeasure; `_get_assistant()` in `api/collimation.py` builds the guide service lazily (gracefully skips if guide camera absent); wizard card shows guide status row (locked/lost, RMS px, last pulse)

## Device handling

- [INDI/ToupTek steering pattern](../resources/hlrequirements/INDI_Steer_pattern.md) — One adapter per device, one SDK handle per adapter, callback routing; multi-camera architecture reference
- [ToupTek device ownership recommendation](../resources/hlrequirements/SmartTScope_ToupTek_Device_Handling_Recommendation.md) — Device state model (AVAILABLE/OWNED_BY_SMARTTSCOPE/EXTERNALLY_BUSY), three operating modes, FireCapture coexistence

## Infrastructure

- [Pi watchdog setup](../resources/hlrequirements/raspberry_pi5_trixie_watchdog_setup.md) — dtparam=watchdog=on, systemd RuntimeWatchdogSec, Type=notify service pattern
- [External heartbeat supervisor](../resources/hlrequirements/external_heartbeat_stop_supervisor.md) — Microcontroller-based STOP on Pi crash; heartbeat protocol; MicroPython examples
- **Deploy fix — stale wheel reinstall bug:** `scripts/astro_start.sh`/`scripts/install_pi.sh` rebuild a wheel and `pip install` it on every deploy, but `pyproject.toml`'s pinned `version = "0.1.0"` never changes, so the rebuilt wheel always has the same filename — pip saw "Requirement already satisfied" and silently skipped reinstalling, leaving the *first-ever-installed* package files (incl. `static/index.html`/`static/js/*.js`) on disk untouched even after a correct `git reset --hard` + restart (the version pill still showed the right git hash because `api/version.py` reads it from the live repo checkout, not the installed package). Fixed with `pip install --force-reinstall` (`--no-deps` in `astro_start.sh` to keep the frequent per-deploy path fast; full deps reconciled in `install_pi.sh`'s one-time/full setup path).

## Camera configuration

- [camera-id-mapping plan](../docs/superpowers/plans/2026-05-20-camera-id-mapping.md) — TDD plan: name-based `[cameras]` config + `[camera_serials]` verification; `CameraNameResolver` service; backward-compat with integer indices
- [camera-offset-config plan](../docs/superpowers/plans/2026-05-20-camera-offset-config.md) — TDD plan: `[camera_offsets]` TOML section; `CameraOffsetService`; auto-apply on connect and gain-mode change; defaults for G3M678M/ATR585M (150) and GPCMOS02000KPA (10)
- [camera-offset-estimation plan](../docs/superpowers/plans/2026-05-20-camera-offset-estimation.md) — TDD plan: bias-frame capture wizard; `BiasEstimationService`; offset sweep 0–200; Stage 6 wizard card with sweep table and TOML snippet
- [camera-adapter integration design](../docs/superpowers/specs/2026-05-22-camera-adapter-integration-design.md) — Copy-on-release model; ownership table; sync script design; merge steps for 2026-05-22 release
- [camera-adapter integration plan](../docs/superpowers/plans/2026-05-22-camera-adapter-integration.md) — 8-task implementation plan: new domain/tools files, camera.py replacement, config/runtime updates, sync infrastructure

## Service Contracts (M7)

- **M7-003 done:** `PixelCalibrationService` — lazy pixel-to-RA/DEC calibration via RA/DEC star-displacement moves; stores `PixelCalibration(ra_vector_px, dec_vector_px, optical_train_id, binning, camera_orientation_deg)`; 6 tests
- **M7-004 done:** Focuser backlash compensation — `FOCUSER_BACKLASH_STEPS` / `FOCUSER_BACKLASH_ENABLED` config; overshoot-then-return in `OnStepFocuser.move_absolute()` on direction reversal; 4 tests
- **M7-005 done:** `ServiceFrame` common frozen dataclass with all mandatory/optional fields (IF-001); `validate()` raises `FrameValidationError`; `from_fits_frame()` factory; 5 tests
- **M7-006 done:** `PlateSolveService` — stateful wrapper around `AstapSolver`; enforces auto-gain precondition (PS-001); `SolveOutput` includes back-calculated focal length, pixel scale, field rotation; 6 tests
- **M7-007 done:** `AutofocusService` — V-curve sampler; returns `AutofocusRecommendation` with signed `focus_movement_steps` and pixel-space centroid offset (not RA/DEC per AF-005); 6 tests
- **M7-008 done:** Collimation `circle_center_displacement_px` — Euclidean inner/outer center distance added to `DonutOverlay`, assistant output, and replay API; 2 new tests
- **M7-009 done:** `smart_telescope/services/image_analysis.py` — `analyze_frame()` returning `ImageAnalysisResult`; uniform/no-signal frames → `FocusQualityLevel.UNKNOWN` via peak-vs-background check; 6 tests
- **M7-010 done:** AG-003 tracking-off exposure cap — `tracking_on: bool = True` parameter on `AutoGainService.run_one_shot()`; caps to 1 000 ms when False; API worker reads `MountState.TRACKING`; 2 tests
- **M7-011 done:** CFG-002 GPS fix age check — `GpsdFix.fix_age_s` + `is_fresh(max_age_minutes=60)`; stale fix logs WARNING; API response exposes `fix_age_s` / `is_fresh`; 6 tests
- **M7-012 done:** SAFE-004 retry limits audit — `PlateSolveService.max_retries=5` enforced; `AutoGainService.max_iterations`, `AutofocusService.max_samples`, collimation sub-service limits verified; 9+2 tests

## Architecture

- `smarttscope_requirements_full.md` (external source, not yet ingested into `raw/`) — State-based observation system spec: BOOTSTRAP..PARKED_SAFE top-level process, G1-G10 guards, MVP staging (§11); source for M9 in `docs/todo.md`
- **M9-001..005 done:** Guided Observing State Machine (Phase 1) — `domain/observing_state.py` (`ObservingStateMachine`, pure transition table), `services/observing_service.py` (orchestrator dispatching Intents to existing engines: `PolarAlignmentWorkflow`, `workflow/stages.py`, `GuidingService`, `mount_operations.park_sequence`), `api/observing.py` (`GET /api/observing/state`, `POST /api/observing/intent`), `static/js/observing.js` + new `#top-view-bar` (Observe/Maintenance) in `index.html` replacing the 5-tab wizard as the primary screen; `tests/integration/test_observing_flow.py` full-flow test. See `docs/todo.md` M9 for Phase 2-6 backlog (unified readiness, real HOME confirmation, dawn/meridian auto-stop, filter/object profiles, calibration pre-session gating).
- **M9-014 done:** `WAIT_CONTEXT_CONFIRMATION` in the Observe screen now shows a Time & Location review panel (`#obs-context-card`) instead of a blind confirm button — reuses the Maintenance screen's `/api/location/status`/`/api/location/confirm` endpoints for GPS-fix/saved-location/manual entry, same as `s1-tl-card`.
- **M9-015 done:** Time & Location panel follow-up — clean local-time format, a `time_trust_source` badge (GPS/NTP/USER_CONFIRMED/NOT_TRUSTED) + "Confirm Pi Time" button in both screens, `[observer]` height parsing now accepts `alt_m` as well as `height_m` (was silently defaulting to 0), `build_onstep_safety_config()` now actually wires elevation into `OnStepSafetyConfig`, and a configurable `OBSERVER_HOME_NAME` for the Home location's display label.
- **M9-016/M9-007 done:** location-select dropdown no longer reverts mid-edit (dirty-flag fix in `observing.js`/`setup.js`); "Confirm HOME position" now runs the real `mount_operations.home_sequence()` as a background action (new `Intent.START_HOME`, `CONFIRM_HOME` as the accept step) instead of a disconnected acknowledgement — mount-strip correctly moves from PARKED to HOME.
- **M9-017 done:** safe-park ("Stop safely (park)") now available from `WAIT_CONTEXT_CONFIRMATION`/`WAIT_HOME_CONFIRMATION`, not just from `POLAR_ALIGN` onward — the always-visible "■ Stop" button only halts, it doesn't park. See `docs/todo.md` M9-018/019/020 for the target-selection gap this investigation surfaced (guided flow is currently hardcoded to a fixed M42/C8_NATIVE target — no way to select Venus or anything else).
- **M9-021 done:** fixed a real-OnStep-hardware-only bug (never reproduced against `MockMount`) where confirming HOME could loop back to "Confirm HOME position" despite the mount being correctly parked/homed — `AT_HOME` is a brief status flag that can clear before a second `get_state()` query; `mount_operations.home_sequence()` now returns whether its own tight poll actually observed it, and `_run_home()` uses that instead of re-querying.
- **M9-022 done:** "Stop safely" was faulting right after a successful HOME confirmation with `:hP# rejected by OnStep — home the mount first...` — OnStep needs a park position saved via `:hS#` before `:hP#` (park) works, and nothing in the app ever called the existing `mount.set_park_position()` to do that. `_run_home()` now calls it right after confirming home (best-effort; a rejection doesn't invalidate the home confirmation itself).
- [job-manager](job-manager.md) — `JobManager` service: resource ownership model, `submit()`/`claim()`/`release()` modes, cancellation, timeout policy
- **M8-014 done (REQ-LOG-001):** `SectionLogger` — 12 named log sections (startup, stage1_time_location, mount, camera, auto_gain, autofocus, collimation, plate_solve, goto, click_to_center, extended_setup_check, github_delivery); each section gets its own `Logger` under `smart_telescope.section.<name>` with `propagate=True`; per-section `FileHandler` to `{LOG_DIR}/{session_id[:8]}/{section}.log` when configured; `_SectionAdapter` injects `session_id` + `section` into every record; `GET /api/logs` returns `{section: path_or_null}` for all 12; `config.LOG_DIR` from `[session].log_dir` (env `LOG_DIR`); 19 + 5 tests
- **Confirm Time & Location panel done (revised, automatic-first):** lives inside the existing "Time / Location Verification" card (`#s1-tl-card`, REQ-TIME-005/M8-010) rather than a separate card — local time (`GPS` badge shown only when Raspberry trust source is `GPSD_FIX`), an editable lat/lon/height_m location with a source badge (`CONFIG_FILE`/`GPS_FIX`/`IP_LOOKUP`/`USER_ENTERED`/`SAVED_LOCATION`), a "Home" baseline (`[observer]` in config.toml, drives real telescope math) plus a saved-location library (`[locations.<name>]` table-of-tables, never touches Home), and one "Confirm Time & Location" button (coexists with the existing "Confirm Pi Time" button) that persists the choice and marks Pi time `USER_CONFIRMED`. A fresh, valid GPS fix (`GpsInfo.usable` = fresh + `mode>=2`, mirrors `services/master_source.py`'s `_MIN_GPS_MODE`) is suggested automatically on every non-dirty render — no manual click needed to see it — per the product's automatic-first requirement (`raw/SmartTelescope.md`: "Automatic location/time acquisition… if available [MVP]"); manual quick-fill/edit remains available as the fallback/override path. New `domain/location_source.py` (`LocationSource` enum), `services/ip_geolocation_service.py` (user-triggered-only IP geolocation, stdlib `urllib`, never raises), `api/location.py` (`GET /api/location/status`, `GET /api/location/ip-lookup`, `POST /api/location/confirm`, `DELETE /api/location/saved/{name}`; line-scanned config.toml section read/write so `[locations.*]` blocks can't corrupt each other or `[observer]`; reuses `mount_sync_clock`/`mount_confirm_time` directly rather than duplicating OnStep-push/time-confirm logic). Replaces the old instant-write `POST /api/observer/location` (`api/gpsd.py`) and the old GPS-drift banner. OnStep's native 4-site memory (`:Wn#`/`:SM#`/`:SP#`) is documented but intentionally unused — config.toml is the location library for now. 65 tests across `tests/unit/domain/test_location_source.py`, `tests/unit/services/test_ip_geolocation_service.py`, `tests/unit/api/test_location.py`, `tests/unit/test_config.py`, `tests/unit/config/test_config_locations_parse.py`.

## Collimation Assistant

- [collimation-task-plan](../resources/hlrequirements/smarttscope_c8_collimation_assistant_task_plan_updated.md) — Full 15-phase implementation plan for C8 SCT collimation wizard
- **Phase 0 done:** config model, domain models, reference-center abstraction, optical profiles
- **Phase 1 done:** `CollimationStateMachine` (20 states), `CollimationAssistant` background service, REST API
- **Phase 3 done:** `ProcessedFrame` normalization, display stretch, star detection, circle/ellipse fitting
- **Phases 4–5 done:** mount centering, star acquisition, rough focus search
- **Phase 6 done:** defocus controller — threshold-masked RMS ring radius measurement
- **Phase 7 done:** donut detection — RMS-radius edge split, Kasa circle fit, traffic-light overlay
- **Phase 8 done:** obstruction detection (shadow angle → screw ID), `ScrewResponseLearner`
- **Phase 9 done:** `CollimationAdvisor` (dot-product screw selection), `LiveGuidanceMonitor`
- **Phase 10 done:** `detect_spikes` (BahtinovAnalyzer adapter), `SectorMapper` (blade closure mapping), `SpikeSmoother` (7-frame median + jitter + trend)
- **Phase 11 done:** `decompose_spike_errors` (3-way focus/residual decomposition), `FineFocusController` (coarse→fine loop + final approach direction), `FineCollimationAdvisor` (worst-residual screw pick), `ContradictionDetector` (blocks guidance on 4 indicator checks)
- **Phase 12 done:** `FWHMFocusController` (maskless hill-climb refocus, COL-120), `MasklessValidator` (donut error ratio assessment, COL-121), `SessionReportBuilder` + `CollimationSessionReport` (structured session summary, COL-122); `CollimationAssistant.report` wired to builder
- **Phase 13 done:** `frame_factories` (gaussian star + donut ring synthetic frames), `ReplayCameraAdapter` (in-memory array camera port), `CollimationStateMachine` test suite (35 tests), full assistant integration tests (18 tests); `_handle_final_refocus` wired to real `FWHMFocusController`
- **Frame archive done:** `CollimationFrameArchive` saves accepted FITS frames + JSON sidecars (state, analysis, ref, bit_depth) under `~/.SmartTScope/frame_archive/<session_id>/`; opt-in via `[collimation.archive] enabled = true`; `GET /api/collimation/archive`, `GET /api/collimation/archive/{session_id}`, `POST /api/collimation/archive/{session_id}/{frame_stem}/replay` (re-runs donut or spike analysis on stored frame); `save_tag()` for JSON-only metadata entries (GoTo/Solve/AF); archive singleton decoupled from `_assistant` — activates on first API call without requiring a wizard session
- **Stage 3 archive tagging done:** 📁 buttons next to GoTo, Solve, and AF in Stage 3; `POST /api/collimation/archive/tag` stores metadata-only JSON entries; Stage 3 includes a collapsible Archive Browser; tag entries shown with "tag" label (no Replay); `_s3CheckArchiveEnabled()` called on stage enter
- **Measurement metrics done:** `assistant.status` now exposes full donut/spike/star detail in `last_measurement` (error_magnitude_px, error_fraction, is_collimated, focus_error_px, crossing_error_rms_px, fwhm_px); wizard card shows a quantitative metrics row with colour-coded error %; Frame Archive Browser card in Stage 4 shows past sessions, frame tables, and side-by-side replay comparison
- **Mount AT_HOME + park flow done:** `MountState.AT_HOME`; two-phase sticky gate (`_home_cmd_issued` + `_home_slew_seen`) prevents premature HOME display — UNPARKED is only promoted to AT_HOME after SLEWING is observed then ends; `park_sequence` auto-sends `:hS#` + `:hP#` when AT_HOME (Home→Park with no extra steps); stops any active slew via `:Q#` before parking when not in home context; `MountPort.set_park_position()` non-abstract default; `OnStepMount` overrides with `:hS#`; blue "Home" badge; `_STATE_LABEL` display mapping in `mount.js`
