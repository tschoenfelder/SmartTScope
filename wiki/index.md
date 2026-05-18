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

- [operational-acceptance-checklist](../docs/operational-acceptance-checklist.md) — 10-step field checklist: connect → setup check → solar gate → GoTo → autofocus → STOP → stack → shutdown
- [hardware-test-log-template](../docs/hardware-test-log-template.md) — Append-only evidence log with six required items (E-001 to E-006) for R7-004 release gate
- [release-checklist](../docs/release-checklist.md) — Go/no-go gate: backlog, hardware evidence, acceptance, tests, clean install, performance, sign-off

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
