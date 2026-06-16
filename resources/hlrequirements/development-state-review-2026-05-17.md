# SmartTScope Development State Review

**Date:** 2026-05-17  
**Reviewer stance:** 10+ year software architect, MVP readiness and field-safety review  
**Primary source:** `docs/todo.md`  
**Code sampled:** FastAPI app/runtime/API, workflow runner/stages, readiness, hardware/job services, static UI modules, package metadata

## Executive Summary

SmartTScope has moved well past a prototype skeleton. The current codebase has a credible layered shape:

- FastAPI app with distinct API modules and static UI delivery.
- Runtime-owned adapters for camera, OnStep mount/focuser, solver, stacker, storage.
- Safety-relevant services for hardware command serialization, observed device state, job ownership, readiness, mount operations, and cooling.
- A guided single-target observing workflow: connect, initialize, align, goto, recenter, autofocus, preview, stack, save.
- Broad domain/service coverage for collimation, autogain, calibration, catalog, queue, polar alignment, guide monitoring, and image quality.

The MVP is functionally plausible, but I would not call it release-ready or field-safe yet. The biggest gap is not feature count; it is evidence. `docs/todo.md` says many implementation tasks are done, but the product acceptance milestone, safety regression checklist, and operational evidence items remain open. For a smart telescope, especially one that moves real hardware, "mock tests pass" is not equivalent to "safe MVP accepted."

## Verification Performed

What I could verify locally:

- `python -m compileall smart_telescope tests` completed successfully with the bundled Python runtime.
- JavaScript syntax checks passed for all files in `smart_telescope/static/js/*.js` using bundled Node `--check`.
- The source tree confirms the UI split and `StaticFiles` mount exist.

What I could not verify locally:

- The test suite did not run because `pytest` is not available on PATH.
- The bundled Python runtime also lacks `pytest`.
- Importing `smart_telescope.app` with the bundled Python failed because `pyserial` is missing: `ModuleNotFoundError: No module named 'serial'`.
- No `pyproject.toml` or `setup.py` exists in the workspace root, despite `docs/todo.md` saying `pyproject.toml` package data was updated.

This means the repo currently lacks a reproducible developer/test execution path in the checked-out workspace. The generated `smart_telescope.egg-info/PKG-INFO` lists dependencies, but the source packaging file that generated it is not present.

## Architecture Assessment

### Strengths

The architectural direction is good. The recent runtime refactor was the correct move: adapter ownership belongs in `RuntimeContext`, not scattered module globals. `RuntimeContext.shutdown()` stopping focuser and mount before disconnect is the right hardware-safety instinct.

The split between ports, adapters, domain, services, workflow, and API is mostly healthy. The best parts are the places where APIs have become thin and services own behavior: `JobManager`, `HardwareCommandCoordinator`, `DeviceStateService`, `ReadinessService`, and `mount_operations`.

The product shape is also improving. The UI now speaks in terms of readiness, optical trains, guided observation, beginner/advanced mode, and recovery-oriented errors. That is closer to "smart telescope" than "remote hardware control panel."

### Change Locality And Team Scalability

The codebase is now large enough that "understand everything before changing anything" will not scale across multiple developers. The current layering helps, but the team should make change locality an explicit architecture goal.

For normal feature work, a developer should usually be able to change one vertical area without reading large unrelated parts of the system. For example, adding a focus routine option should ideally touch only:

- focus domain/config model,
- focus service/workflow implementation,
- one API request/response shape if the option is user-facing,
- one focused UI control if exposed in the browser,
- tests for that focus option.

It should not require reading mount state management, readiness internals, collimation algorithms, preview WebSocket code, session storage, and hardware adapter details. If it does, the boundary is too leaky.

Recommended ownership boundaries:

- **Runtime and hardware lifecycle:** `runtime.py`, API deps, adapter construction, shutdown, reconnect. Few owners; high review bar.
- **Hardware motion safety:** mount/focuser APIs, `HardwareCommandCoordinator`, `DeviceStateService`, `mount_operations`, OnStep adapters. Few owners; hardware evidence required.
- **Observation workflow:** `api/session.py`, `workflow/runner.py`, `workflow/stages.py`, session domain log/state. Product-flow owners.
- **Focus/autofocus:** `domain/autofocus.py`, `workflow/autofocus.py`, focus-related stage wiring, focuser API/UI. This should become a clean sub-boundary.
- **Imaging pipeline:** camera capture, autogain, histogram/stretch, stacker/storage, frame quality.
- **Setup/readiness/config:** config parsing, readiness service, setup UI.
- **Collimation:** keep isolated as post-MVP unless explicitly pulled into the release path.

Where the current code still pushes too much knowledge onto contributors:

- `api/session.py` knows about catalog lookup, solar safety, calibration masters, job ownership, runner creation, static C8 profiles, camera dependencies, and query/UI options. This should be split into a `SessionService` plus smaller request mappers.
- `workflow/stages.py` owns many distinct concerns: connect, mount initialization, plate solving, centering, autofocus, preview, stacking, refocus, frame quality, save. It is readable, but adding options may still require understanding the whole file.
- The static UI is split into modules now, which is good, but the modules still share global variables. This is acceptable for MVP, but it makes cross-module reasoning harder as options grow.
- Optical train work is partly in place, but the session path still uses hard-coded camera/resource assumptions. That makes multi-camera changes more invasive than they should be.

Architectural rule for future changes:

> A normal feature option should have one obvious home. If a small option requires edits across five or more unrelated areas, pause and introduce or improve a boundary before implementing it.

For the focus example specifically, define a focus policy object such as `FocusRunConfig` or `AutofocusPlan` and let session/API/UI pass that object downward. The autofocus implementation should not need to know whether the option came from a query parameter, saved profile, optical train, or future UI preset.

### Main Architectural Risks

1. **Evidence gap for real hardware safety**

   `docs/todo.md` still has open P0/P1 items for STOP during mount slew, STOP during focuser movement, shutdown during motion, reconnect, and full workflow evidence. This is the top risk.

2. **Session workflow still bypasses some newer architecture**

   The session endpoint still hard-codes resource ownership as `{"camera:0", "mount", "focuser"}` and uses `deps.get_camera`, not optical-train role selection. This undermines the R4 optical train work for the main product workflow.

3. **MVP acceptance is not closed**

   M5 is entirely unchecked in `docs/todo.md`, including guided startup, connect all devices, GoTo/solve/recenter, focus/exposure, preview/stack, save, stop/recover, and reconnect/shutdown. Many pieces exist, but the acceptance checklist has not been proven end to end.

4. **Build and test reproducibility is weak**

   The workspace contains generated egg-info but no source packaging file. A new developer or CI agent cannot reliably install dependencies or run tests from the repo as checked out.

5. **Readiness semantics may be too permissive**

   Readiness reports `can_observe = overall != RED`. But missing real camera/mount currently produces YELLOW/mock states. That is acceptable for simulator mode, but dangerous if the UI/user interprets it as real observing readiness.

6. **Runtime/session lifecycle tension**

   `VerticalSliceRunner.run()` disconnects mount, camera, and focuser in `finally`. That can be correct for a single isolated session, but it may conflict with runtime-managed adapters, preview reuse, reconnect semantics, and post-session diagnostics.

7. **Open product-owner decisions block clean prioritization**

   POD-004, POD-005, POD-007, and POD-009 remain unanswered. These are not cosmetic; they define UI exposure, degradation policy, sign-off evidence, and performance targets.

## Findings

### P0/P1 Findings

1. **Safety is implemented in code but not accepted with hardware evidence**

   STOP bypasses coordinator locks and emergency stop catches subsystem failures, which is good. But `docs/todo.md` still lists real-hardware STOP and shutdown checks as open. For a motorized telescope, this blocks release-level MVP acceptance.

2. **The main observing session is still camera-index based internally**

   The session run endpoint claims `camera:0` and depends on `deps.get_camera`. This conflicts with the product direction of role/optical-train selection. If the main camera is not SDK index 0, or if multiple trains exist, the guided workflow can use the wrong camera or block the wrong resource.

3. **Packaging source is missing**

   `docs/todo.md` claims `pyproject.toml` was updated, but no `pyproject.toml` exists in the workspace root. Without source packaging metadata, dependency installation, static package inclusion, and CI reproducibility are fragile.

4. **Test pass claims are not currently reproducible from this checkout**

   The todo references 43 smoke tests and 1950 tests passing, but the local environment cannot run `pytest`. This does not mean tests are broken, but it does mean the repo is not self-verifying in its current state.

5. **Real/mock readiness boundary is not explicit enough**

   Using mock camera/mount can be fine for development and demo simulation. It should not be conflated with "ready to observe" unless the current mode is explicitly "simulator/mock." The UI and readiness API need a product-level distinction between "ready for simulated workflow" and "ready for real sky."

### P2 Findings

6. **Backlog status is internally inconsistent**

   `M0-001 Create one authoritative maintained backlog` is unchecked even though the top of `docs/todo.md` says the authoritative backlog decision is done. The document has become both a task log and a status report, but not yet a clean release dashboard.

7. **Open field bugs remain mixed with completed architecture work**

   BUG-010, BUG-011, BUG-012, BUG-013, BUG-016, BUG-002, BUG-004, and BUG-021 remain open. Some may be lower priority, but BUG-010/011/012/013/016 are hardware/state confidence issues and should not drift.

8. **Collimation assistant appears over-scoped for MVP**

   The codebase contains a surprisingly large collimation subsystem. It may be valuable, but `POD-008` says collimation assistant is deferred beyond MVP. Treat it as post-MVP unless it directly supports field acceptance.

9. **UI split improved maintainability but should get browser verification**

   JS syntax checks pass, but smoke tests are not a substitute for browser-level confirmation of the guided flow, mount strip, readiness card, camera role selects, and WebSocket preview behavior.

10. **Some change paths still require too much cross-system awareness**

   The code is modular in folders, but not all feature seams are equally strong. Session, workflow stages, and shared UI globals are the main places where a small option can still require broad code knowledge.

## Open Questions For You

Please clarify these before the team does more broad feature work:

1. **Product sign-off evidence:** What exact evidence do you want for MVP sign-off: video, hardware log, screenshots, saved FITS/image, session JSON log, or all of these?

2. **Real vs simulator MVP:** Is MVP allowed to be accepted in simulator/replay mode, or must the guided single-target session pass on the real Pi, OnStep mount, focuser, ToupTek camera, and ASTAP?

3. **Camera index exposure:** Should SDK camera indices be forbidden everywhere outside diagnostics, including API request bodies, or only hidden in the UI?

4. **Failure isolation policy:** Which failures are allowed to block the entire app? For example, should ASTAP missing block only observing, while mount serial failure still allows camera preview and diagnostics?

5. **Performance targets:** What are the MVP numbers for STOP response, preview latency, plate-solve time, centering accuracy, autofocus duration, stack duration, and Pi thermal ceiling?

6. **Session lifecycle:** After a session completes or fails, should hardware remain connected for diagnostics/retry, or should the runner disconnect everything as it does now?

7. **Collimation scope:** Is the collimation assistant truly post-MVP, or should a minimal collimation shell be part of the smart telescope demo?

## Recommended Direction

Freeze feature work except for acceptance blockers. The codebase has enough feature surface for MVP; what it needs now is a release spine:

- Restore reproducible install/test.
- Make the main observing workflow role/optical-train aware.
- Run and record hardware safety checks.
- Run and record the guided single-target workflow.
- Convert `docs/todo.md` from a historical task log into a shorter acceptance dashboard plus linked backlog.

## New Prioritized Todo List

### P0 - Safety And Release Blockers

1. **P0-001 Record real-hardware STOP evidence during mount slew**
   - Acceptance: STOP response is confirmed under 1 s; log includes timestamped command receipt and hardware stop observation.

2. **P0-002 Record real-hardware STOP evidence during focuser movement**
   - Acceptance: focuser stop response is confirmed under 1 s; no continued movement after process exit.

3. **P0-003 Verify shutdown during active motion**
   - Acceptance: CTRL-C/server shutdown stops focuser and mount before serial disconnect; evidence captured on Pi.

4. **P0-004 Separate real observing readiness from mock/simulator readiness**
   - Acceptance: readiness API/UI explicitly says `real`, `simulator`, or `mock`; real observing cannot be marked ready with mock mount/camera.

5. **P0-005 Complete solar safety acceptance**
   - Acceptance: all GoTo entry points, catalog target launch, guided session launch, and sky slews enforce solar exclusion unless an explicit safe confirmation path is used.

### P1 - MVP Product Acceptance

6. **P1-001 Restore reproducible project packaging**
   - Acceptance: root contains `pyproject.toml`; `pip install -e .[dev]` works; static files are included; app imports cleanly from a fresh environment.

7. **P1-002 Restore runnable local/CI test command**
   - Acceptance: documented command runs the suite; CI or local script reports test count and coverage; dependency setup is not hidden in generated egg-info.

8. **P1-003 Make session run optical-train aware**
   - Acceptance: guided session selects a train/role, claims the correct `camera:N`, uses the matching focuser binding, and never hard-codes `camera:0`.

9. **P1-004 Complete one real guided single-target session**
   - Acceptance: pick target -> GoTo -> solve/center -> autofocus -> stack 10 frames -> save image and session log on real hardware.

10. **P1-005 Verify reconnect behavior**
    - Acceptance: reconnect policy is tested: auto-park, state label follows observed hardware, and retry/diagnostics path is clear.

11. **P1-006 Close hardware state field bugs**
    - Scope: BUG-010, BUG-011, BUG-012, BUG-013, BUG-016.
    - Acceptance: mount/focuser labels and logs match observed hardware state on Pi.

12. **P1-007 Create MVP sign-off evidence packet**
    - Acceptance: one folder contains hardware logs, screenshots, saved output image, session log, safety checklist results, known issues, and app/version info.

### P2 - Reliability And Operability

13. **P2-001 Add browser-level smoke verification**
    - Acceptance: automated or manual browser checklist covers readiness, connect, preview, target selection, start observation, stop, and diagnostics.

14. **P2-002 Define performance targets**
    - Acceptance: preview latency, solve time, centering accuracy, autofocus duration, stop response, and Pi thermal ceiling are documented in `docs/todo.md`.

15. **P2-003 Add storage-full and low-disk simulations**
    - Acceptance: session fails gracefully before data corruption; UI tells user what to do.

16. **P2-004 Add network/browser reconnect scenario**
    - Acceptance: page reload or WebSocket drop does not orphan jobs; UI can recover current session state.

17. **P2-005 Decide session post-run lifecycle**
    - Acceptance: runner disconnect behavior is either kept intentionally or changed so runtime owns device lifecycle consistently.

18. **P2-006 Improve change locality for focus options**
    - Acceptance: add a focus policy/config object; focus routine options can be added by touching focus config, focus implementation, API/UI mapping, and focused tests only.

### P3 - UX Polish

19. **P3-001 Clean histogram/autogain layout**
    - Scope: BUG-002, BUG-004, BUG-021.
    - Acceptance: histogram is useful below ADU 1000; controls are grouped by task; no confusing checkbox/button split.

20. **P3-002 Reduce `docs/todo.md` into dashboard + backlog**
    - Acceptance: top section shows current release state, P0/P1 blockers, open decisions, and evidence links; historical completed detail moves to archival docs.

21. **P3-003 Keep collimation post-MVP unless explicitly pulled in**
    - Acceptance: collimation work does not consume MVP acceptance bandwidth unless product owner changes scope.
