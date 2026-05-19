# SmartTScope Final Product, Architecture, And AI Operating Plan

Date: 2026-05-15

Status: Consolidated planning document

Sources consolidated:

- `docs/product-stewardship-task-list.md`
- `docs/ai-agent-setup.md`
- `docs/operational-architecture-refactor-tasks.md`
- architecture scan findings
- field issue scan findings
- smart telescope product direction discussion

Purpose: define how SmartTScope becomes a real smart telescope product, not a device-control panel with astronomy features.

---

## 1. Product Principle

SmartTScope must relieve the user from in-depth astronomy, camera, mount, focuser, plate solving, and calibration knowledge.

The product must move from:

```text
User controls devices.
```

to:

```text
User states observing intent. System manages devices.
```

The user should not need to understand:

- SDK camera indices
- OnStep command details
- park/unpark timing
- plate solver profiles
- pixel scale
- optical train internals
- gain/offset tuning
- focuser state races
- ASTAP catalog paths
- WebSocket failure modes

The system should guide the user from power-on to image capture:

```text
Open app
-> Check setup
-> Ready to observe
-> Choose target
-> Start observation
-> System slews, solves, centers, focuses, optimizes exposure, previews, stacks, and saves
```

Everything else is diagnostics or advanced mode.

---

## 2. Product Experience Target

### First Screen

The first screen should offer intent-level actions:

- Check Setup
- Start Observation
- Preview Sky
- Resume Session
- Emergency Stop

Manual hardware control should not be the dominant first impression.

### Normal Observing Flow

The normal user flow should be:

1. Check readiness.
2. Choose a target.
3. Review smart recommendation.
4. Start observation.
5. Watch progress.
6. See live image improve.
7. Save, continue, or stop.

### Guided Progress Steps

The system should show understandable progress:

```text
1. Checking setup
2. Checking target visibility
3. Preparing mount
4. Slewing
5. Solving sky position
6. Centering target
7. Focusing
8. Optimizing exposure
9. Capturing and stacking
10. Saving session
```

### Beginner And Advanced Modes

Beginner mode:

- readiness
- target choice
- observation progress
- live image
- clear warnings
- emergency stop

Advanced mode:

- manual mount controls
- manual focuser controls
- manual camera settings
- solver diagnostics
- calibration tools
- raw logs

Emergency stop must always remain visible.

---

## 3. Major Operational Requirements

### O1. Safe Hardware Control

The system must always keep mount and focuser motion under control.

Requirements:

- Emergency stop interrupts mount and focuser motion.
- Shutdown stops moving hardware before closing serial or camera connections.
- No new mount/focuser movement starts until previous movement is complete, stopped, failed, or timed out.
- Park, unpark, home, stop, and tracking state are based on observed hardware state.
- Hardware commands timeout and report actionable errors.

### O2. Reliable Startup And Setup Check

The user must know whether the system is ready.

Requirements:

- Load config predictably.
- Resolve `stars.cfg`, horizon file, storage path, ASTAP path, and ASTAP catalog.
- Detect configured cameras.
- Detect mount and focuser.
- Check camera capabilities such as cooling.
- Run safe setup check.
- Show red/yellow/green readiness with repair guidance.

### O3. Device Lifecycle And Reconnect

The system must behave predictably when hardware or network state changes.

Requirements:

- Defined reconnect behavior after browser/app drop.
- Defined behavior after Pi reboot.
- Defined behavior after USB/device reconnect.
- Safe state after failed mount/focuser/camera connection.
- Clear connection states: connecting, connected, unavailable, failed, recovering.

### O4. Long-Running Job Management

Observing operations are long-running and must be supervised.

Requirements:

- Sessions, autogain, autofocus, calibration, preview, solving, and stacking expose job status.
- Jobs are cancellable.
- Cancellation completes within agreed timeout.
- One failed job does not crash unrelated functionality.
- Camera ownership and conflicts are explicit.

### O5. Optical Train And Device Role Correctness

The app must know which hardware belongs together.

Requirements:

- Camera roles are stable: main, guide, OAG, wide-field, planetary, etc.
- Focuser is linked to the correct optical train.
- Cooling controls only appear for cameras that support cooling.
- Pixel scale and solver profile follow the active optical train.
- UI screens show the same device model consistently.

### O6. Observing Workflow Reliability

The core smart telescope workflow must be operationally dependable.

Requirements:

- Guided startup.
- Target selection.
- Solar safety gate.
- Mount limit checks.
- GoTo.
- Plate solve.
- Recenter.
- Preview.
- Histogram/stretch.
- Autogain/autofocus where available.
- Capture/stack.
- Save image and session log.
- Recover or stop safely on failure.

### O7. Diagnosability And Logging

Failures must be understandable without shell archaeology.

Requirements:

- User-facing errors are specific.
- Engineering logs include command, device, timing, result, and failure reason.
- Mount/focuser slow responses are logged.
- Session logs capture state transitions, warnings, solve attempts, centering results, frames, and saved artifacts.
- Field bugs are traceable to backlog IDs and fixes.

### O8. Data And Storage Robustness

The system must not casually lose or corrupt observing data.

Requirements:

- Storage path is checked before session start.
- Storage-full behavior is graceful.
- Session artifacts use deterministic naming.
- Session logs are saved.
- Calibration frames and bad-pixel maps have clear organization.
- Power-loss behavior is defined.

### O9. Pi Performance And Resource Control

The Pi must remain responsive under real workload.

Requirements:

- Preview latency target.
- Solve timeout target.
- Stack refresh target.
- Memory budget for camera frames, ASTAP, stacking, JPEG/WebSocket output.
- Thermal ceiling target.
- Controlled concurrency for CPU-heavy jobs.

### O10. Product Acceptance And Evidence

The team must prove readiness.

Requirements:

- P0/P1 tasks have acceptance criteria.
- Hardware-facing tasks have hardware evidence.
- Milestones have product-owner-visible quality gates.
- STOP, reconnect, shutdown, setup check, and observing workflow are verified before demo/release.

---

## 4. Target Architecture

The current architecture has useful feature abstractions, but operational responsibility is too spread out.

Target shape:

```text
FastAPI app
  |
  +-- RuntimeContext
        |
        +-- ConfigService
        +-- DeviceRegistry
        +-- HardwareCommandCoordinator
        +-- DeviceStateService
        +-- JobManager
        +-- OpticalTrainRegistry
        +-- StorageService
        +-- ReadinessService
```

Current pattern to reduce:

```text
API endpoint -> module global -> adapter -> private adapter method
```

Target pattern:

```text
API endpoint -> RuntimeContext service -> domain/port/adapter
```

Architecture principle:

API modules validate requests and map responses. They should not own hardware orchestration, long-running jobs, device identity, readiness, or state truth.

---

## 5. AI Operating Model

Use two AI skills.

### Skill 1: Product Steward

Name:

`smarttscope-product-steward`

Primary question:

```text
What should we do next, why does it matter, and how does it map to product milestones?
```

Responsibilities:

- maintain authoritative backlog
- convert field bugs into structured tasks
- deduplicate scattered task lists
- link tasks to requirements and defect sources
- define acceptance criteria
- keep milestones meaningful to product owner
- produce product-owner progress summaries
- flag stale or duplicated task sources

Outputs:

- consolidated backlog
- milestone plan
- top-10 risk list
- missing acceptance criteria report
- stale/duplicate task report
- product-owner summary

### Skill 2: Quality Sentinel

Name:

`smarttscope-quality-sentinel`

Primary question:

```text
Can we prove this is done, safe, tested, and ready to show?
```

Responsibilities:

- verify evidence for completed tasks
- flag done-without-test items
- flag done-without-hardware-evidence items
- check safety-critical regression coverage
- track P0/P1 defect status
- detect recurring bugs after claimed fixes
- produce milestone traffic-light status
- produce release go/no-go report

Outputs:

- milestone traffic-light report
- done-without-evidence warnings
- missing-test report
- hardware verification checklist
- regression-risk report
- release go/no-go report

### Why Two Skills

The Product Steward organizes the work.

The Quality Sentinel challenges whether progress is real.

Do not merge these roles too early. A single assistant that both plans work and judges completion is more likely to accept weak evidence.

---

## 6. Backlog Item Schema

Every maintained task should use this structure:

```text
ID:
Title:
Priority: P0 Safety | P1 Product Blocker | P2 Important | P3 Polish
Area: Runtime | Hardware | Imaging | UI | Config | Tests | Product | Process
Source:
Problem:
Product-owner meaning:
Acceptance criteria:
Implementation notes:
Test evidence:
Hardware evidence:
Status: Proposed | Ready | In Progress | Blocked | Done | Rejected
Owner:
Target milestone:
Fixed in release:
```

Definition of done:

- [ ] Acceptance criteria are explicit.
- [ ] Code is implemented.
- [ ] Automated tests pass where practical.
- [ ] Hardware evidence exists for hardware-facing behavior.
- [ ] Documentation/config notes are updated.
- [ ] Product owner can verify the result without reading code.

---

## 7. Priority Definitions

### P0 Safety

Can cause uncontrolled hardware motion, unsafe shutdown, loss of emergency stop, data corruption during active hardware work, or misleading state for moving hardware.

### P1 Product Blocker

Blocks guided startup, setup readiness, observing workflow, camera/mount/focuser usability, or MVP demonstration.

### P2 Important

Improves robustness, diagnosability, maintainability, performance, or UX consistency, but has a workaround.

### P3 Polish

Improves presentation, convenience, layout, wording, or non-critical workflow efficiency.

---

## 8. Product UX Refactor Priorities

### UX1. Ready To Observe Screen

Create a guided readiness screen that answers:

- Is the system ready?
- If not, what exactly is wrong?
- Is anything unsafe?
- What can the user do next?

Tasks:

- [ ] UX1-001 Add red/yellow/green readiness summary.
- [ ] UX1-002 Show config, storage, ASTAP, catalog, camera, mount, focuser, cooling, and solver readiness.
- [ ] UX1-003 Provide repair guidance for each failed check.
- [ ] UX1-004 Make readiness the default first-run experience.

Quality gate:

- [ ] A non-technical user can tell whether observing can start.
- [ ] Missing `stars.cfg` produces a clear fix instruction.
- [ ] Missing ASTAP catalog produces a clear fix instruction.

### UX2. Intent-Based Observation Flow

Create one main workflow:

```text
Choose target -> Start Observation -> system handles setup, slew, solve, center, focus, exposure, preview, stack, save
```

Tasks:

- [ ] UX2-001 Add `Start Observation` as primary action.
- [ ] UX2-002 Show guided progress steps.
- [ ] UX2-003 Move autogain/autofocus/solve/recenter into automatic workflow.
- [ ] UX2-004 Show recovery actions when automation fails.

Quality gate:

- [ ] User can start an observing session without manually invoking solve, focus, gain, or recenter.

### UX3. Hide Camera Index Thinking

Replace product-facing camera indices with optical train roles.

Tasks:

- [ ] UX3-001 Show main telescope camera.
- [ ] UX3-002 Show guide/OAG/wide-field camera only as configured roles.
- [ ] UX3-003 Show serial/logical name in diagnostics.
- [ ] UX3-004 Hide unsupported controls such as cooling for non-cooled cameras.

Quality gate:

- [ ] Normal user does not need to choose `camera_index`.
- [ ] Focuser/cooling controls follow selected optical train.

### UX4. Advanced Mode For Manual Controls

Manual controls remain available, but not dominant.

Tasks:

- [ ] UX4-001 Add beginner/advanced mode distinction.
- [ ] UX4-002 Move manual mount controls into advanced/diagnostics except emergency stop.
- [ ] UX4-003 Move manual focuser controls into advanced/diagnostics except required recovery actions.
- [ ] UX4-004 Keep emergency stop globally visible.

Quality gate:

- [ ] Beginner mode is safe and intent-driven.
- [ ] Advanced mode still supports field debugging.

### UX5. Recovery-Oriented Errors

Replace raw errors with guided recovery.

Bad:

```text
Home failed: GoTo failed
```

Target:

```text
Home failed because OnStep rejected the slew: tracking is off.
The system is safe and no motion is active.
Recommended action: unpark, enable tracking, retry home.
```

Tasks:

- [ ] UX5-001 Define error model: what happened, safety state, user action, retry action.
- [ ] UX5-002 Map OnStep command errors to user-facing messages.
- [ ] UX5-003 Map camera errors to user-facing messages.
- [ ] UX5-004 Map solver errors to user-facing messages.
- [ ] UX5-005 Add diagnostics link for advanced details.

Quality gate:

- [ ] Every P0/P1 workflow error tells the user what to do next.

---

## 9. Architecture Refactor Milestones

### R0. Runtime Context Foundation

Product-owner meaning: the app has one supervised runtime owner instead of hidden module-level state.

Tasks:

- [ ] R0-001 Define `RuntimeContext` responsibilities.
- [ ] R0-002 Create `RuntimeContext` in FastAPI lifespan startup.
- [ ] R0-003 Move adapter references from module globals into `RuntimeContext`.
- [ ] R0-004 Move preview camera cache into `RuntimeContext`.
- [ ] R0-005 Move active session runner reference into `RuntimeContext`.
- [ ] R0-006 Move autogain job reference into `RuntimeContext` or `JobManager`.
- [ ] R0-007 Add explicit `start()`, `shutdown()`, `connect_devices()`, `disconnect_devices()`, and `reset_for_tests()` methods.
- [ ] R0-008 Update API dependencies to read from app runtime.
- [ ] R0-009 Keep compatibility wrappers during migration.
- [ ] R0-010 Add lifecycle tests.

Quality gate:

- [ ] Runtime object owns adapter references.
- [ ] Tests can create isolated runtime contexts.
- [ ] Shutdown path can be tested without importing API globals.

### R1. Hardware Command Coordinator

Product-owner meaning: mount and focuser motion are coordinated through one safety-aware control point.

Tasks:

- [ ] R1-001 Define `HardwareCommandCoordinator`.
- [ ] R1-002 Define command types: stop, goto, park, unpark, home, guide, focuser move, focuser nudge.
- [ ] R1-003 Define command priority rules.
- [ ] R1-004 Make STOP priority higher than all normal commands.
- [ ] R1-005 Define command lifecycle states.
- [ ] R1-006 Add command IDs and structured command logs.
- [ ] R1-007 Move mount/focuser endpoint-local locks into coordinator.
- [ ] R1-008 Introduce OnStep serial bus abstraction.
- [ ] R1-009 Stop exposing private mount serial methods to focuser adapter.
- [ ] R1-010 Add concurrency, timeout, and STOP-priority tests.
- [ ] R1-011 Add real hardware verification for STOP during mount slew and focuser move.

Quality gate:

- [ ] No endpoint owns hardware command locks directly.
- [ ] STOP bypasses normal queue delay safely.
- [ ] Incompatible movement commands are rejected.
- [ ] Hardware STOP behavior is verified.

### R2. Device State Service

Product-owner meaning: UI shows what the hardware is actually doing, not what the last command hoped would happen.

Tasks:

- [ ] R2-001 Define `DeviceStateService`.
- [ ] R2-002 Define observed mount, focuser, and camera state models.
- [ ] R2-003 Track last command, last observed state timestamp, and last error per device.
- [ ] R2-004 Poll mount and focuser state at controlled interval.
- [ ] R2-005 Add state convergence helpers for park, unpark, home, and goto completion.
- [ ] R2-006 Add stale-state and slow-response detection.
- [ ] R2-007 Change status endpoints and UI labels to use observed state.
- [ ] R2-008 Add tests for accepted command but unchanged observed state.

Quality gate:

- [ ] Parked/unparked UI labels only change after observed state changes.
- [ ] Unknown/stale state is shown as such.
- [ ] Slow hardware response creates warning.

### R3. Shared Job Manager

Product-owner meaning: long-running actions can be monitored, cancelled, timed out, and explained consistently.

Tasks:

- [ ] R3-001 Define `JobManager`, `Job`, `JobStatus`, and `CancellationToken`.
- [ ] R3-002 Define resource ownership for camera, mount, focuser.
- [ ] R3-003 Add job status and cancellation APIs.
- [ ] R3-004 Migrate session, autogain, calibration, collimation, and preview ownership to job manager.
- [ ] R3-005 Prevent session/preview/autogain from silently competing for same camera.
- [ ] R3-006 Add cancellation checkpoints and timeouts.
- [ ] R3-007 Add tests for cancellation, conflict, failure isolation.

Quality gate:

- [ ] All long-running operations expose status.
- [ ] All cancellable jobs report cancelling/cancelled state.
- [ ] Failed job does not poison runtime.

### R4. Optical Train Registry

Product-owner meaning: the app consistently understands the real telescope setup.

Tasks:

- [ ] R4-001 Define `OpticalTrain` and `OpticalTrainRegistry`.
- [ ] R4-002 Include camera role, serial/logical name, focuser binding, cooling capability, pixel scale, solver profile, and optical profile.
- [ ] R4-003 Load train definitions from config.
- [ ] R4-004 Validate train definitions at startup.
- [ ] R4-005 Replace product-facing camera index selection with train/role selection.
- [ ] R4-006 Update preview, focuser, cooling, polar alignment, autogain, and setup to use train model.
- [ ] R4-007 Add tests for two-camera and three-camera/OAG setups.

Quality gate:

- [ ] Main camera and focuser association is correct.
- [ ] Guide camera is not incorrectly shown as focus-controlled.
- [ ] Cooling controls only appear for supported cameras.

### R5. Config And Readiness Services

Product-owner meaning: setup failures are found before observing starts, with clear repair guidance.

Tasks:

- [ ] R5-001 Define `ConfigService`.
- [ ] R5-002 Replace import-time config loading with explicit load.
- [ ] R5-003 Replace config `sys.exit` behavior with structured startup error.
- [ ] R5-004 Add resolved path model.
- [ ] R5-005 Validate `stars.cfg`, horizon file, storage, ASTAP executable, ASTAP catalog, camera roles, optical trains.
- [ ] R5-006 Define `ReadinessService`.
- [ ] R5-007 Add red/yellow/green readiness summary.
- [ ] R5-008 Add actionable repair guidance.
- [ ] R5-009 Update setup check endpoint and UI.
- [ ] R5-010 Add missing-file and invalid-config tests.

Quality gate:

- [ ] Config errors do not crash as unexplained process exits.
- [ ] Missing files produce actionable readiness errors.
- [ ] Setup readiness can be checked repeatedly.

### R6. API Thinness And UI Consistency

Product-owner meaning: features behave consistently because APIs delegate to the same runtime services.

Tasks:

- [ ] R6-001 Move mount/focuser/camera/setup/job orchestration out of API modules into services.
- [ ] R6-002 Keep API modules thin: validate request, call service, map response.
- [ ] R6-003 Split large static UI into maintainable modules.
- [ ] R6-004 Create shared frontend API client and shared device/job state model.
- [ ] R6-005 Ensure STOP button is globally available.
- [ ] R6-006 Add browser smoke tests for setup, preview, mount, focuser, and stop.

Quality gate:

- [ ] UI labels do not contradict status endpoints.
- [ ] Same service state feeds all relevant UI panels.

### R7. Operational Evidence And Release Gate

Product-owner meaning: the team can prove the system is ready, safe, and not merely coded.

Tasks:

- [ ] R7-001 Define operational acceptance checklist.
- [ ] R7-002 Define hardware test log template.
- [ ] R7-003 Define release go/no-go checklist.
- [ ] R7-004 Record STOP during mount slew, STOP during focuser move, shutdown during active motion, reconnect, setup check, and full observing workflow.
- [ ] R7-005 Add product-owner milestone dashboard.
- [ ] R7-006 Add done-without-evidence report.

Quality gate:

- [ ] No P0 safety item open.
- [ ] No milestone task marked done without evidence.
- [ ] Hardware-facing milestone tasks have hardware evidence.

---

## 10. Product Milestones

### M0. Project Control Restored

Product-owner meaning: the team knows what is open, what matters, what is duplicated, and what blocks a safe usable product.

Tasks:

- [ ] M0-001 Create one authoritative maintained backlog.
- [ ] M0-002 Import field bugs from current `resources/hlrequirements/Items_to_fix_*.txt`.
- [ ] M0-003 Import open items from task docs and architecture review.
- [ ] M0-004 Deduplicate overlapping issues.
- [ ] M0-005 Assign priority to every imported item.
- [ ] M0-006 Add acceptance criteria to every P0/P1 item.
- [ ] M0-007 Link every backlog item to source document.
- [ ] M0-008 Add product-owner top-10 risk view.

Quality gate:

- [ ] Every open field bug has a backlog ID.
- [ ] Every P0/P1 item has acceptance criteria.
- [ ] Product owner can see top risks in one page.

### M1. Hardware Safety Spine

Product-owner meaning: the system controls moving parts predictably and can stop safely.

Tasks:

- [ ] M1-001 Complete R1 hardware command coordinator.
- [ ] M1-002 Complete R2 observed device state for mount/focuser.
- [ ] M1-003 Define shutdown sequence.
- [ ] M1-004 Add hardware watchdog for slow mount/focuser response.
- [ ] M1-005 Verify STOP during mount slew.
- [ ] M1-006 Verify STOP during focuser move.
- [ ] M1-007 Verify shutdown during active motion.

Quality gate:

- [ ] STOP works during mount slew.
- [ ] STOP works during focuser movement.
- [ ] Shutdown during active motion leaves hardware controlled.
- [ ] Park/unpark UI state follows observed state.

### M2. Smart Runtime And Jobs

Product-owner meaning: long-running operations are visible, cancellable, and isolated.

Tasks:

- [ ] M2-001 Complete R0 runtime context.
- [ ] M2-002 Complete R3 shared job manager.
- [ ] M2-003 Define camera-use policy.
- [ ] M2-004 Prevent preview/autogain/session conflicts.
- [ ] M2-005 Add timeout policy for long jobs.
- [ ] M2-006 Ensure unrelated subsystems continue when one job fails.

Quality gate:

- [ ] Autogain cancel completes within agreed timeout.
- [ ] Session stop completes within agreed timeout.
- [ ] Camera conflicts are explicit.
- [ ] API exposes current job state and last error.

### M3. Smart Setup And Optical Train Truth

Product-owner meaning: the system knows the actual telescope setup and can tell the user if it is ready.

Tasks:

- [ ] M3-001 Complete R4 optical train registry.
- [ ] M3-002 Complete R5 config/readiness services.
- [ ] M3-003 Replace camera-index product UI with train roles.
- [ ] M3-004 Hide unsupported cooling/focuser controls.
- [ ] M3-005 Provide red/yellow/green setup readiness.

Quality gate:

- [ ] Main camera/focuser association is correct.
- [ ] Guide camera is not shown as focus-controlled unless configured.
- [ ] Cooling is absent for non-cooled cameras.
- [ ] Setup check detects missing required files and devices.

### M4. Intent-Driven Smart Telescope UX

Product-owner meaning: the user can operate the telescope by intent, not by device expertise.

Tasks:

- [ ] M4-001 Implement `Ready to Observe` first-run screen.
- [ ] M4-002 Implement target recommendation view.
- [ ] M4-003 Implement `Start Observation` guided workflow.
- [ ] M4-004 Move manual controls into advanced/diagnostics mode.
- [ ] M4-005 Add recovery-oriented errors.
- [ ] M4-006 Keep emergency stop globally visible.

Quality gate:

- [ ] User can start observing without manually managing solve/focus/gain/recenter.
- [ ] Beginner mode avoids camera indices and hardware jargon.
- [ ] Recovery messages tell the user what to do next.

### M5. Product Acceptance MVP

Product-owner meaning: SmartTScope can perform a meaningful smart telescope workflow safely enough to demonstrate.

Tasks:

- [ ] M5-001 Guided startup.
- [ ] M5-002 Connect all configured devices.
- [ ] M5-003 Show readiness dashboard.
- [ ] M5-004 Select target.
- [ ] M5-005 Enforce solar safety gate.
- [ ] M5-006 Validate mount limits.
- [ ] M5-007 GoTo, solve, recenter.
- [ ] M5-008 Focus and optimize exposure.
- [ ] M5-009 Preview and stack.
- [ ] M5-010 Save output image and session log.
- [ ] M5-011 Stop/recover safely.
- [ ] M5-012 Verify reconnect and shutdown behavior.

Quality gate:

- [ ] Full workflow demonstrated on real hardware.
- [ ] Emergency stop tested during workflow.
- [ ] Logs are useful without shell investigation.
- [ ] Session output is saved predictably.
- [ ] Product owner signs off against visible checklist.

### M6. Field Reliability And Release Readiness

Product-owner meaning: the system is not just demoable once; it can survive normal field use.

Tasks:

- [ ] M6-001 Define unattended session duration target.
- [ ] M6-002 Define preview latency target.
- [ ] M6-003 Define stop-response target.
- [ ] M6-004 Define centering accuracy target.
- [ ] M6-005 Define solve success target.
- [ ] M6-006 Define Pi thermal ceiling target.
- [ ] M6-007 Run long session reliability test.
- [ ] M6-008 Run Pi thermal test.
- [ ] M6-009 Run storage-full simulation.
- [ ] M6-010 Run network reconnect simulation.
- [ ] M6-011 Verify clean Pi install.
- [ ] M6-012 Produce release notes and known issues.

Quality gate:

- [ ] Long session completes or fails gracefully.
- [ ] Thermal limits are not exceeded.
- [ ] Storage-full behavior does not corrupt session data.
- [ ] Reconnect behavior is defined and verified.
- [ ] Release can be installed from clean state.

---

## 11. Quality Sentinel Dashboard

The Quality Sentinel should produce this dashboard weekly and before milestone review:

```text
Milestone:
Status: Green | Yellow | Red
Confidence: High | Medium | Low

Completed with evidence:
Completed without evidence:
Open P0:
Open P1:
New field bugs:
Recurring bugs:
Suspected regressions:
Hardware tests passed:
Hardware tests missing:
Automated tests passed:
Automated tests missing:

Decision needed from product owner:
Recommended next action:
```

Traffic-light rules:

Green:

- no open P0 item
- no unreviewed P1 item
- completed milestone tasks have evidence
- required hardware checks passed
- no blocking product-owner decision outstanding

Yellow:

- no open P0 item
- at least one P1 item open or weakly evidenced
- some hardware evidence missing
- milestone may be demoable but not releasable

Red:

- open P0 item
- STOP/shutdown/reconnect behavior unverified
- completed tasks lack evidence
- field bug recurrence suggests regression
- hardware behavior is unknown or unsafe

---

## 12. Evidence Rules

A completed task must have at least one of:

- automated test evidence
- hardware test evidence
- manual verification note
- product-owner acceptance note

Hardware-facing tasks require hardware evidence unless explicitly classified as design-only or mock-only.

Tasks that must never be accepted without hardware evidence:

- emergency stop
- mount park/unpark/home
- focuser movement
- shutdown during active motion
- reconnect after device loss
- camera role and optical train mapping
- setup check on real Pi

Safety regression checklist:

- [ ] STOP works during mount slew.
- [ ] STOP works during focuser movement.
- [ ] Shutdown stops motion before disconnect.
- [ ] Park label follows observed hardware state.
- [ ] Unpark label follows observed hardware state.
- [ ] New mount command is rejected while unsafe movement is active.
- [ ] New focuser command is rejected while prior movement is active.
- [ ] Preview failure does not break mount/focuser controls.
- [ ] Autogain cancellation exits within agreed timeout.
- [ ] Session stop exits within agreed timeout.
- [ ] Camera conflicts are detected and reported.
- [ ] Missing config files produce actionable diagnostics.

---

## 13. Team Operating Rhythm

### Monday: Product Steward

- import new field reports
- deduplicate tasks
- update backlog priorities
- identify missing acceptance criteria
- produce top-10 risk list

### Wednesday: Quality Sentinel

- inspect tasks marked done
- check test evidence
- check hardware evidence
- flag weak completion claims
- update milestone traffic light

### Friday: Product Owner Review

- review traffic-light dashboard
- review top-10 risks
- decide whether to continue, stabilize, defer, or release
- record decisions in backlog

---

## 14. Product Owner Decisions Needed

- [ ] What must happen after reconnect: preserve session, park mount, or ask user?
- [ ] What is the maximum acceptable STOP response time?
- [ ] What state may the UI show after command acceptance but before hardware confirmation?
- [ ] Is SDK camera index acceptable anywhere outside diagnostics?
- [ ] Which failures may block the whole app, and which must degrade locally?
- [ ] What is the minimum successful demo workflow?
- [ ] What evidence is required for product-owner sign-off?
- [ ] Which requirements are deferred beyond MVP?
- [ ] What are the concrete performance targets for preview latency, solve time, centering accuracy, and thermal ceiling?

---

## 15. Immediate Next Actions

- [ ] NEXT-001 Approve this document as the current consolidated plan.
- [ ] NEXT-002 Decide where the authoritative backlog will live.
- [ ] NEXT-003 Create the `smarttscope-product-steward` skill.
- [ ] NEXT-004 Create the `smarttscope-quality-sentinel` skill.
- [ ] NEXT-005 Run Product Steward once against current docs and field bug files.
- [ ] NEXT-006 Run Quality Sentinel once against current completed-task claims.
- [ ] NEXT-007 Complete M0 Project Control Restored before new feature work.
- [ ] NEXT-008 Assign one technical owner for R0-R3.
- [ ] NEXT-009 Start R0 Runtime Context Foundation with compatibility wrappers.
- [ ] NEXT-010 Define hardware safety tests before changing command logic.
- [ ] NEXT-011 Start UX1 Ready To Observe design in parallel with R5 readiness service.

