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
- [OnStepAdapter external module](../SYNC.md) — External package tschoenfelder/OnStepAdapter v0.2.0 replaces hand-rolled mount/focuser/serial_bus; active SYNC-OVERRIDEs and enhancement requests REQ-1..5 tracked here
- [seestar-s50](seestar-s50.md) — ZWO Seestar S50 reference smart telescope
- [vaonis-vespera](vaonis-vespera.md) — Vaonis Vespera Pro reference smart telescope

## Planning

- [requirements](requirements.md) — Full MVP / MVP+ / Full requirement set for the C8 + Pi 5 + OnStep build (revised; §14 process requirements added 2026-04-30)
- [requirements-review](requirements-review.md) — External review: verdict, retagging rationale, and missing requirement areas
- [requirements-addon-20260430](requirements-addon-20260430.md) — Star catalog expansion, quickstart corrections, and process requirements (2026-04-30)
- [requirements-addon-20260501](requirements-addon-20260501.md) — First hardware test session bugs and mount safety requirements (2026-05-01)
- [requirements-addon-20260502b](requirements-addon-20260502b.md) — README update instructions + focuser always-expected policy, shared serial delegation, is_available (2026-05-02)
- [requirements-addon-20260506](requirements-addon-20260506.md) — Fix/update requirements: camera naming, Live Preview backend, histogram, exposure/gain UI, Startup polish (2026-05-06)
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

## Camera configuration

- [camera-id-mapping plan](../docs/superpowers/plans/2026-05-20-camera-id-mapping.md) — TDD plan: name-based `[cameras]` config + `[camera_serials]` verification; `CameraNameResolver` service; backward-compat with integer indices
- [camera-offset-config plan](../docs/superpowers/plans/2026-05-20-camera-offset-config.md) — TDD plan: `[camera_offsets]` TOML section; `CameraOffsetService`; auto-apply on connect and gain-mode change; defaults for G3M678M/ATR585M (150) and GPCMOS02000KPA (10)
- [camera-offset-estimation plan](../docs/superpowers/plans/2026-05-20-camera-offset-estimation.md) — TDD plan: bias-frame capture wizard; `BiasEstimationService`; offset sweep 0–200; Stage 6 wizard card with sweep table and TOML snippet
- [camera-adapter integration design](../docs/superpowers/specs/2026-05-22-camera-adapter-integration-design.md) — Copy-on-release model; ownership table; sync script design; merge steps for 2026-05-22 release
- [camera-adapter integration plan](../docs/superpowers/plans/2026-05-22-camera-adapter-integration.md) — 8-task implementation plan: new domain/tools files, camera.py replacement, config/runtime updates, sync infrastructure

## Architecture

- [job-manager](job-manager.md) — `JobManager` service: resource ownership model, `submit()`/`claim()`/`release()` modes, cancellation, timeout policy

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
