# SmartTScope v0.1 — Release Notes

**Date:** 2026-05-19  
**Branch:** master  
**Head commit:** c525dd6  
**Test suite:** 2664 passed · 87.56 % coverage  

---

## Milestone Status

| Milestone | Name | Status |
|-----------|------|--------|
| M0 | Project Control Restored | ✅ Done |
| M1 | Hardware Safety Spine | ⚠ Pending hardware evidence |
| M2 | Smart Runtime and Jobs | ✅ Done |
| M3 | Smart Setup and Optical Train Truth | ✅ Done |
| M4 | Intent-Driven Smart Telescope UX | ✅ Done |
| M5 | Product Acceptance MVP | ⚠ Pending hardware demo |
| M6 | Field Reliability and Release Readiness | ⚠ Partial — 6 items hardware-blocked |
| COL | Collimation Assistant — C8 SCT | ✅ All phases wired |

---

## What's New

### Hardware Safety Spine (M1)

- **Hardware Command Coordinator (`R1`)** — All mount and focuser commands route through a central coordinator with explicit resource locking. STOP bypasses the coordinator and calls hardware directly, ensuring emergency stop always responds.
- **Device State Service (`R2`)** — Background polling thread updates mount/focuser/camera observed state every 2 s. UI labels follow observed hardware state, not command receipt. Stale-state detection at 10 s.
- **Shutdown sequence** — `RuntimeContext.shutdown()` stops focuser motion, then stops the mount, then disconnects serial in a fixed safe order. CTRL-C triggers this sequence.
- **Park/unpark state propagation** — `poll_now()` called immediately after park/unpark so the UI label reflects hardware state within one poll cycle.

### Smart Runtime and Jobs (M2)

- **Runtime Context (`R0`)** — All adapter references, session state, and job state live in a single `RuntimeContext` object created at FastAPI lifespan startup. No module-level globals.
- **Job Manager (`R3`)** — `JobManager` controls resource ownership (`"camera:N"`, `"mount"`, `"focuser"`). Session and autogain cannot claim the same camera; conflicts return HTTP 409. Autogain has a 300 s timeout.
- **Crash isolation** — A session thread crash releases the job manager; STOP and GoTo remain available on all other subsystems.
- **Fast autogain cancel** — Cancel latency ≤ 50 ms via `abort_capture()` abort-watcher pattern (resolves BUG-001).

### Smart Setup and Optical Train Truth (M3)

- **Optical Train Registry (`R4`)** — Telescopes and camera roles defined in `config.toml` under `[optical_trains]`. All UI selects show train names ("main — c8", "guide — guide_scope"), not camera indices. Focuser controls filtered to trains with `has_focuser = true`.
- **Config and Readiness Services (`R5`)** — `ReadinessService` checks config file, storage, ASTAP executable, ASTAP catalog, tilde-path expansion, and hardware mode. Each failed check carries a repair hint. `/api/readiness` returns a red/yellow/green summary plus `can_observe` flag.
- **Hardware mode badge** — Readiness page shows REAL / SIMULATOR / MOCK. `can_observe` is blocked for non-real modes, preventing accidental mock sessions.
- **Focuser connect retry** — `OnStepFocuser.connect()` and `OnStepMount.connect()` retry up to 3× with a 300 ms gap to handle stale ACK bytes left from the previous session (resolves BUG-010, BUG-013).

### Intent-Driven Smart Telescope UX (M4)

- **Ready to Observe screen** — Readiness card loads automatically on page open (Stage 1). Red/yellow/green items with repair guidance.
- **Guided pipeline UI** — Five-step progress strip (Connect → GoTo → Centre → Focus → Capture) updates live during a session. Recovery banner on failure with contextual Retry button.
- **Visible Tonight card** — Lists Messier objects visible above 20° altitude, sorted by altitude. Click any row to set it as the session target.
- **Advanced mode toggle** — "Advanced" button in the header hides manual mount controls (Home / Park / Unpark / Tracking) and focuser nudge in beginner mode. STOP is always visible.
- **Recovery-oriented errors** — `friendlyError()` maps raw hardware errors to `{message, hint}` pairs. Diagnostics link appended to every error banner.
- **Solar safety gate** — All GoTo entry points (direct GoTo, catalog launch, guided session) reject Sun coordinates with HTTP 403. `confirm_solar = true` bypass available.

### API Thinness and UI Consistency (R6)

- **Service extraction** — `CoolingService` and `MountOperations` extracted from API modules. API endpoints validate → call service → map response. No orchestration logic in API layer.
- **JS module split** — `index.html` reduced from 6216 to 1847 lines. 4376 lines of JS split into 8 focused modules: `api.js`, `app.js`, `mount.js`, `collimation.js`, `focuser.js`, `preview.js`, `session.js`, `setup.js`.
- **`FocusRunConfig` policy object** — Focus options (step size, frame count, timeout) carried in a single `FocusRunConfig` object; changes to focus policy touch only the focus domain.

### Operational Evidence and Release Gate (R7)

- **Milestone Dashboard** — `/api/milestones` returns milestone completion stats and a top-10 risk list. Dashboard card on Stage 1 shows color-coded progress bars.
- **Evidence Gap Report** — `/api/evidence-gaps` lists 8 items that are mock-tested only and require hardware evidence before release.
- **Release readiness documents** — `docs/operational-acceptance-checklist.md`, `docs/hardware-test-log-template.md`, `docs/release-checklist.md` in place.
- **Performance targets** — Defined in `domain/performance_targets.py`; see "Performance Targets" section below.

### M5 — Product Acceptance MVP (Partially Complete)

- **Dawn auto-park** — `DawnWatcher` background service polls sun altitude every 60 s; auto-parks when sun reaches −18° (astronomical dawn). `/api/dawn` returns current status.
- **Solar exclusion** — `is_solar_target()` enforced at every GoTo entry point (M5-005).
- **Storage-full handling** — `WorkflowError("save", "Disk full…")` raised cleanly when `has_free_space()` is False; partial saves preserve the image path if the log write fails.

### Collimation Assistant — C8 SCT

All 15 implementation phases are complete and wired into a live pipeline:

- **Phase 0–2:** Config model, domain models, reference-center abstraction, optical profiles, `CollimationStateMachine` (20 states), REST API, wizard UI with progress strip and overlay.
- **Phase 3:** Frame processing: `ProcessedFrame` normalization, display stretch, star detection, circle/ellipse fitting.
- **Phase 4–5:** Pulse-guide star centering, star acquisition (slew → detect → centre loop), rough focus search.
- **Phase 6–9:** Defocus controller, donut detection, screw identification by obstruction shadow, `ScrewResponseLearner`, `CollimationAdvisor` (dot-product screw selection), `LiveGuidanceMonitor`.
- **Phase 10–11:** Tri-Bahtinov spike detection, mask sector mapping, spike smoothing, fine focus/collimation decomposition, contradiction detection.
- **Phase 12–13:** Maskless validation, session report builder, replay frame provider for offline testing.
- **Phase 14:** Full acquisition → rough collimation → fine collimation pipeline wired and running in the wizard.

---

## Performance Targets

| Target | Value | Unit |
|--------|-------|------|
| Unattended session duration (M6-001) | 6 | hours |
| Preview frame latency (M6-002) | ≤ 2 | s |
| STOP response time (M6-003 / POD-002) | ≤ 500 | ms |
| Centering accuracy after plate-solve (M6-004) | ≤ 30 | arcsec RMS |
| Plate solve success rate (M6-005) | ≥ 90 | % |
| Raspberry Pi 5 thermal ceiling (M6-006) | ≤ 75 | °C |

These targets drive the M6 field reliability tests and feed the release go/no-go checklist.

---

## Known Issues

### Hardware Verification Required (Blocking)

These items are implemented in software and mock-tested but require evidence on real Pi hardware before the release gate opens (see `docs/release-checklist.md`):

| ID | Description | Priority |
|----|-------------|----------|
| R1-011 / M1-005 | STOP during mount slew — hardware evidence | P0 |
| M1-006 | STOP during focuser move — hardware evidence | P0 |
| M1-007 | Shutdown during active motion — hardware evidence | P0 |
| R7-004 | Six-item evidence log (E-001 through E-006) | P0 |
| M5-007 | GoTo, plate solve, recenter — hardware demo | P1 |
| M5-008 | Focus and optimize exposure — hardware demo | P1 |
| M5-011 | Stop/recover safely during full workflow | P0 |
| M5-012 | Reconnect and shutdown behavior | P1 |
| M6-007 | Long-session reliability test (6 h) | P1 |
| M6-008 | Pi thermal test under sustained load | P2 |
| M6-010 | Network reconnect simulation | P1 |
| M6-011 | Clean Pi install from scratch (Trixie 64) | P1 |

### Open Product-Owner Decisions

| ID | Decision needed |
|----|----------------|
| POD-004 | Is SDK camera index acceptable anywhere outside diagnostics? |
| POD-005 | Which failures may block the whole app, and which must degrade locally? |
| POD-010 | Should SDK camera indices be forbidden in API request bodies? |

### Open Software Items

| ID | Description | Priority |
|----|-------------|----------|
| M5-001 | Guided startup — integration verification | P1 |
| M5-002 | Connect all configured devices — integration verification | P1 |
| M5-003 | Show readiness dashboard — integration verification | P1 |
| M5-004 | Select target — integration verification | P1 |
| M5-006 | Validate mount limits — integration verification | P1 |
| M5-009 | Preview and stack — integration verification | P1 |
| M5-010 | Save output image and session log — integration verification | P1 |

---

## Deferred — Post-MVP

These items were explicitly deferred and are not part of the v0.1 scope:

| ID | Description | Priority |
|----|-------------|----------|
| BUG-006 | Extended setup check: focuser move test, RA/DEC 10° test, multi-camera plate solve, home return | P2 |
| BUG-007 | Frame types: bias, dark, flat, master frames, bad pixel maps | P2 |

In addition, the following product capabilities are deferred beyond MVP:

- ISS tracking
- Multi-target queue / automated target scheduling
- Advanced calibration frames wizard
- Full C8 collimation algorithm phases beyond the current wizard shell

---

## Install and Upgrade Path

**First install:** Follow `wiki/quickstart.md` — Raspberry Pi OS Trixie 64-bit, ToupTek camera drivers, ASTAP solver, and ASTAP catalog installation.

**Upgrade from development branch:**
```bash
git pull origin master
pip install -e .
```

No database migrations or config schema changes are required between development commits and this release candidate.

**Config file:** Copy `smart_telescope/templates/config.toml` to `~/.config/smart_telescope/config.toml` and fill in:
- `[telescopes]` — focal length and reducer factor for each optical train
- `[optical_trains]` — camera role, camera index, telescope name, and focuser association
- Storage paths and ASTAP executable path

---

## Running the Application

```bash
python -m smart_telescope
```

The web UI is served on `http://<pi-ip>:8000`. Stage 1 loads the readiness card automatically.

## Running Tests

```bash
python -m pytest
```

Required coverage threshold: 80 %. Current: 87.56 %.
