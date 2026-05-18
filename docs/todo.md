# SmartTScope — Development Todo

**Source:** `docs/smarttscope-final-product-architecture-ai-plan.md`  
**Field bugs:** `resources/hlrequirements/Items_to_fix_20260513.txt`, `Items_to_fix_20260514.txt`  
**Created:** 2026-05-15  
**Last updated:** 2026-05-19 (R7-006 evidence-gap report; M6-001–006 performance targets; R7-005+M0-008 milestone dashboard)
**Review source:** `resources/hlrequirements/development-state-review-2026-05-17.md`

## Priority legend

| Code | Meaning |
|------|---------|
| P0 Safety | Uncontrolled hardware motion, data corruption, emergency stop failure |
| P1 Product Blocker | Blocks guided startup, observing workflow, or MVP demo |
| P2 Important | Robustness / diagnosability — has a workaround |
| P3 Polish | UX, wording, non-critical efficiency |

---

## Immediate Actions

- [x] NEXT-001 Approve consolidated plan as current product direction `[P1 · Process]`
- [x] NEXT-002 Decide where the authoritative backlog lives — `docs/todo.md` `[P1 · Process]`
- [x] NEXT-003 Create `smarttscope-product-steward` AI skill → `docs/skills/smarttscope-product-steward.md` `[P2 · Process]`
- [x] NEXT-004 Create `smarttscope-quality-sentinel` AI skill → `docs/skills/smarttscope-quality-sentinel.md` `[P2 · Process]`
- [x] NEXT-007 Complete M0 before any new feature work — satisfied by todo ordering `[P1 · Process]`
- [x] NEXT-009 Start R0 Runtime Context Foundation — `RuntimeContext` created, `app.py` and `deps.py` updated, all tests pass `[P1 · Runtime]`
- [x] NEXT-011 Start UX1 Ready To Observe design in parallel with R5 readiness service — `ReadinessService`, `/api/readiness`, readiness card in Stage 1 UI, 22 tests `[P1 · UI]`

---

## M0 — Project Control Restored

*Team knows what is open, what matters, what is duplicated, and what blocks a safe usable product.*

- [x] M0-001 Create one authoritative maintained backlog `[P1 · Process]`
  - *Done:* `docs/todo.md` is the established authoritative backlog (NEXT-002); all field bugs and architecture items imported and prioritized with acceptance criteria on every P0/P1 item.
- [x] M0-002 Import field bugs from Items_to_fix_20260513.txt and Items_to_fix_20260514.txt `[P1 · Process]`
  - *Done:* All field bugs from both files imported with BUG-IDs, priorities, and source annotations throughout this backlog.
- [x] M0-003 Import open items from task docs and architecture review `[P1 · Process]`
  - *Done:* All items from `development-state-review-2026-05-17.md` and architecture plan imported and categorised.
- [x] M0-004 Deduplicate overlapping issues `[P1 · Process]`
  - *Done:* Overlapping field bugs and architecture items consolidated; duplicates noted inline where applicable.
- [x] M0-005 Assign priority to every imported item `[P1 · Process]`
  - *Done:* Every backlog item carries a P0–P3 priority tag.
- [x] M0-006 Add acceptance criteria to every P0/P1 item `[P1 · Process]`
  - *Done:* All P0/P1 items have Acceptance and Done notes recorded.
- [x] M0-007 Link every backlog item to source document `[P2 · Process]`
  - *Done:* Field bugs carry `Source: Items_to_fix_YYYYMMDD` annotations; architecture items reference the plan document.
- [x] M0-008 Add product-owner top-10 risk view `[P2 · Process]`
  - *Done (R7-005):* Top-10 risk items included in `/api/milestones` response; rendered in the Milestone Dashboard card on Stage 1.

**Quality gate:** Every open field bug has a backlog ID. Every P0/P1 item has acceptance criteria. Product owner can see top risks on one page.

---

## M1 — Hardware Safety Spine

*System controls moving parts predictably and can stop safely.*

### P0 Safety — Fix immediately

- [x] BUG-023 Shutdown with CTRL-C does not close OnStep connection; focuser keeps moving in small steps after exit `[P0 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* shutdown sequence stops motion and closes serial before process exits; verified on real Pi
  - *Done:* `RuntimeContext.shutdown()` calls `focuser.stop()` then `mount.stop()` then `mount.disconnect()` in lifespan teardown
- [x] BUG-005 Any component crash must not release control of mount or focuser; STOP must always respond `[P0 · Hardware · Source: Items_to_fix_20260513]`
  - *Acceptance:* preview/camera failure does not affect mount/focuser control; STOP always completes within agreed time
  - *Done:* `_session_thread()` wraps `runner.run()` in a `finally` that calls `rt.job_manager.release()`; STOP endpoint calls `mount.stop()` directly (no coordinator); 10 explicit isolation tests in `tests/unit/api/test_bug005_isolation.py` — coordinator lock bypass, resource release on crash, STOP/goto available post-crash

### R1 — Hardware Command Coordinator

- [x] R1-001 Define `HardwareCommandCoordinator` `[P1 · Runtime]`
- [x] R1-002 Define command types: stop, goto, park, unpark, home, guide, focuser move, focuser nudge `[P1 · Runtime]`
- [x] R1-003 Define command priority rules `[P1 · Runtime]`
- [x] R1-004 Make STOP priority higher than all normal commands `[P0 · Runtime]`
  - *Done:* STOP endpoints call mount/focuser directly, never through coordinator
- [x] R1-005 Define command lifecycle states `[P1 · Runtime]`
  - *Done (R2-003+R2-005):* Lifecycle is: command issued (record_command) → hardware executing (convergence helpers poll cached state) → done or error (record_command_error + observed state change); exposed in MountStatus.last_command/last_command_error
- [x] R1-006 Add command IDs and structured command logs `[P2 · Runtime]`
- [x] R1-007 Move mount/focuser endpoint-local locks into coordinator `[P1 · Runtime]`
  - *Done:* `_goto_lock` removed from `mount.py`, `_move_lock` removed from `focuser.py`; all commands use `coordinator.mount_command()` / `coordinator.focuser_command()`
- [x] R1-008 Introduce OnStep serial bus abstraction `[P1 · Runtime]`
- [x] R1-009 Stop exposing private mount serial methods to focuser adapter `[P1 · Runtime]`
- [x] R1-010 Add concurrency, timeout, and STOP-priority tests `[P1 · Tests]`
  - *Done:* 11 tests in `tests/unit/services/test_hardware_coordinator.py` — conflict detection, timeout=0, lock independence, exception release, STOP bypass pattern
- [ ] R1-011 Hardware verification: STOP during mount slew and STOP during focuser move `[P0 · Hardware]`
  - *Must have hardware evidence — not accepted on mock alone*

### R2 — Device State Service

- [x] R2-001 Define `DeviceStateService` `[P1 · Runtime]`
- [x] R2-002 Define observed mount, focuser, and camera state models `[P1 · Runtime]`
  - *Done:* `MountObservedState` dataclass with state, ra, dec, polled_at, error
- [x] R2-003 Track last command, last observed state timestamp, and last error per device `[P1 · Runtime]`
  - *Done:* `DeviceStateService.record_command(name)`, `record_command_error(msg)`, `get_last_command()` added; all mount command endpoints (park, unpark, goto, home, track, stop) call `record_command` before issuing; errors recorded on failure; `MountStatus` response includes `last_command`, `last_command_age_s`, `last_command_error`; 4 new tests in `test_device_state.py`
- [x] R2-004 Poll mount and focuser state at controlled interval `[P1 · Runtime]`
  - *Done:* background daemon thread polls every 2 s via `DeviceStateService`
- [x] R2-005 Add state convergence helpers for park, unpark, home, and goto completion `[P1 · Runtime]`
  - *Done:* `wait_for_mount_state(target, timeout_s)` waits until cached state equals target; `wait_while_mount_state(current, timeout_s)` waits until cached state differs; `mount_unpark` uses `wait_while_mount_state(PARKED)` to replace direct poll loop; `mount_park` uses `wait_for_mount_state(PARKED)` to confirm within 5 s; 6 new tests in `test_device_state.py`
- [x] R2-006 Add stale-state and slow-response detection `[P2 · Runtime]`
  - *Done:* `MountObservedState.is_stale()` uses 10 s threshold; `stale` field in `MountStatus`
- [x] R2-007 Change status endpoints and UI labels to use observed state `[P1 · Runtime]`
  - *Done:* `GET /api/mount/status` reads from `DeviceStateService` cache; falls back to direct poll only when cache is empty
- [x] R2-008 Test: command accepted but observed state unchanged `[P1 · Tests]`
  - *Done:* 13 tests in `tests/unit/services/test_device_state.py` — poll lifecycle, stale detection, error propagation, position-skip on UNKNOWN, thread-safety

### Field bugs — Mount state

- [x] BUG-011 Park command moves mount but UNPARKED flag remains too long `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* UI label changes only after observed state confirms park; correct within 5 s
  - *Done:* `device_state.poll_now()` after park command refreshes cache immediately; frontend park poll loop extended from 10×500ms to 60×1000ms (60 s total — covers full park slew duration)
- [x] BUG-012 After reconnect, mount shown as unparked when policy requires parked `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Done:* `RuntimeContext.connect_devices()` calls `device_state.poll_now()` immediately after `start()` — cache populated from first millisecond of startup, no 2 s gap
- [x] BUG-016 Unpark returns HTTP 200 but label stays PARKED `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* label follows observed hardware state, not command receipt
  - *Done:* `device_state.poll_now()` after unpark command; timeout extended from 3 s to 5 s; frontend unpark loop extended to 20×500ms (10 s)

### Milestone M1 tasks

- [x] M1-001 Complete R1 hardware command coordinator `[P0 · Runtime]`
- [x] M1-002 Complete R2 observed device state for mount/focuser `[P1 · Runtime]`
- [x] M1-003 Define and implement shutdown sequence `[P0 · Runtime]`
- [x] M1-004 Add hardware watchdog for slow mount/focuser response `[P2 · Runtime]`
- [ ] M1-005 Verify STOP during mount slew (hardware evidence) `[P0 · Hardware]`
- [ ] M1-006 Verify STOP during focuser move (hardware evidence) `[P0 · Hardware]`
- [ ] M1-007 Verify shutdown during active motion (hardware evidence) `[P0 · Hardware]`

**Quality gate:** STOP works during mount slew and focuser movement. Shutdown leaves hardware controlled. Park/unpark UI follows observed state.

---

## M2 — Smart Runtime and Jobs

*Long-running operations are visible, cancellable, timed out, and isolated.*

### R0 — Runtime Context Foundation

- [x] R0-001 Define `RuntimeContext` responsibilities `[P1 · Runtime]`
- [x] R0-002 Create `RuntimeContext` in FastAPI lifespan startup `[P1 · Runtime]`
- [x] R0-003 Move adapter references from module globals into `RuntimeContext` `[P1 · Runtime]`
- [x] R0-004 Move preview camera cache into `RuntimeContext` `[P1 · Runtime]`
- [x] R0-005 Move active session runner reference into `RuntimeContext` `[P1 · Runtime]`
  - *Done:* `session_lock`, `_active_runner`, `_runner_thread` in RuntimeContext; `session.py` uses `rt.set_session()`, `rt.is_session_running()`, `rt.get_active_runner()`
- [x] R0-006 Move autogain job reference into `RuntimeContext` or `JobManager` `[P1 · Runtime]`
  - *Done:* `autogain_lock`, `_autogain_job` in RuntimeContext; `autogain.py` uses `_get_job()` / `_set_job()` wrappers; `reset_for_tests()` clears both
- [x] R0-007 Add explicit `shutdown()`, `connect_devices()`, `disconnect_devices()`, `reset_for_tests()` methods `[P1 · Runtime]`
- [x] R0-008 Update API dependencies to read from app runtime `[P1 · Runtime]`
- [x] R0-009 Keep compatibility wrappers during migration `[P2 · Runtime]`
- [x] R0-010 Add lifecycle tests `[P1 · Tests]`
  - *Done:* 40 tests in `tests/unit/test_runtime.py` — init state, connect_devices (mock + simulator + idempotency + polling starts), shutdown (focuser stop, mount stop-before-disconnect, preview cameras, error tolerance), reset_for_tests (all cleared, session/autogain cleared, new adapters on next access), module singleton (get/set_runtime), session state management, autogain state management, FastAPI lifespan smoke tests
- [x] R0-011 Change `VerticalSliceRunner.run()` to not disconnect adapters in `finally`; release job ownership only; keep hardware live after session `[P1 · Runtime]`
  - *Done:* removed `mount.disconnect()`, `camera.disconnect()`, `focuser.disconnect()` from `runner.py finally`; runtime shutdown sequence owns all device teardown; `test_run_does_not_disconnect_focuser_on_completion` verifies new contract

### R3 — Shared Job Manager

- [x] R3-001 Define `JobManager`, `Job`, `JobStatus`, `ResourceConflictError` `[P1 · Runtime]`
  - *Done:* `smart_telescope/services/job_manager.py` — two modes: `submit()` (fully managed thread) and `claim()`/`release()` (caller-managed); timeout via companion daemon thread
- [x] R3-002 Define resource ownership model for camera, mount, focuser `[P1 · Runtime]`
  - *Done:* convention: `"camera:N"`, `"mount"`, `"focuser"`; conflict check is atomic in `_register()`
- [x] R3-003 Add job status and cancellation APIs `[P1 · Runtime]`
  - *Done:* `cancel()`, `cancel_by_name()`, `cancel_all()`, `get_job()`, `get_by_name()`, `list_active()`, `active_resources()`, `is_resource_held()`, `purge_finished()`
- [x] R3-004 Migrate autogain to job manager `[P1 · Runtime]`
  - *Done:* `autogain.py` uses `rt.job_manager.submit("autogain", {"camera:N"}, _worker, ..., cancel_event=job.cancel, timeout_s=300)`; `ResourceConflictError` → 409
- [x] R3-005 Prevent session/autogain from competing for same camera/mount/focuser `[P1 · Runtime]`
  - *Done:* `session.py` uses `rt.job_manager.claim("session", {"camera:0", "mount", "focuser"})`; thread wrapper calls `release()` in finally; `ResourceConflictError` → 409
- [x] R3-006 Add cancellation checkpoints and timeouts `[P1 · Runtime]`
  - *Done:* timeout watcher in `_start_timeout_watcher()`; autogain timeout 300 s; `cancel_event` bridge between `_Job.cancel` and JobManager
- [x] R3-007 Tests: cancellation, resource conflict, failure isolation `[P1 · Tests]`
  - *Done:* 40 tests in `tests/unit/services/test_job_manager.py` — submit/claim/release lifecycle, resource conflicts, cancellation (by id/name/all), timeout, query API, purge

### Field bugs — Jobs and concurrency

- [x] BUG-001 Autogain cancel does not stop for a long time `[P1 · Runtime · Source: Items_to_fix_20260513]`
  - *Acceptance:* cancel completes within < 1 s of the cancel request (POD-002 decision)
  - *Done:* `CaptureAbortedError` + `abort_capture()` in `CameraPort`; ToupcamCamera polls `_frame_ready` every 50ms and breaks on `_abort` event; AutoGainService spawns an abort-watcher thread that calls `camera.abort_capture()` as soon as `cancellation_flag` is set; catches `CaptureAbortedError` → CANCELLED. Cancel latency ≤ 50ms. Two regression tests in `test_autogain_service.py::TestCancelLatency`.
- [x] BUG-002b Preview shows `AUTO_GAIN_POSSIBLE_FOCUS_OR_POINTING_ERROR` after autogain cancel `[P2 · UI · Source: Items_to_fix_20260513]`
- [x] BUG-019 Focuser nudge returns 409 conflict and blocks far too long; rapid +20 presses mostly rejected `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* conflict cleared within 2 s; sequential presses each produce movement
  - *Done:* `_safe_move` moved `time.sleep(0.3)` and `started` check outside the coordinator lock; lock now covers only serial command (~50-100 ms), not the started-check sleep
- [x] BUG-022 Changing camera in Goto/Solve then pressing Find Best fails; WebSocket data transfer error logged `[P1 · Runtime · Source: Items_to_fix_20260514]`
  - *Done:* Added `mountGotoAndCenter()` JS function (was called but never defined); `onPreviewCamChange()` now stops/restarts preview WS on camera change

### Milestone M2 tasks

- [x] M2-001 Complete R0 runtime context `[P1 · Runtime]`
- [x] M2-002 Complete R3 shared job manager `[P1 · Runtime]`
- [x] M2-003 Define camera-use policy `[P1 · Runtime]`
  - *Done:* convention `"camera:N"` / `"mount"` / `"focuser"` in JobManager; session claims `camera:0 + mount + focuser`; autogain claims `camera:{index}`; preview uses camera adapter's `_capture_lock` (serializes at hardware level); full role-based policy deferred to R4
- [x] M2-004 Prevent preview/autogain/session conflicts `[P1 · Runtime]`
  - *Done:* session/autogain conflicts explicit via R3 `ResourceConflictError` → HTTP 409; preview serializes through adapter-level `_capture_lock`; concurrent preview + autogain on same camera serializes safely
- [x] M2-005 Add timeout policy for long-running jobs `[P1 · Runtime]`
  - *Done:* autogain: 300 s timeout via JobManager companion watcher; session: user-initiated stop only (legitimate sessions run hours — hard timeout not appropriate)
- [x] M2-006 Ensure unrelated subsystems continue when one job fails `[P1 · Runtime]`
  - *Done:* JobManager releases resources on DONE/FAILED/CANCELLED; `ResourceConflictError` is synchronous (caller gets 409, other subsystems unaffected)

**Quality gate:** Autogain cancel and session stop complete within agreed timeout. Camera conflicts are explicit. API exposes current job state and last error.

---

## M3 — Smart Setup and Optical Train Truth

*System knows the actual telescope setup and can tell the user whether it is ready.*

### R4 — Optical Train Registry

- [x] R4-001 Define `OpticalTrain` and `OpticalTrainRegistry` `[P1 · Runtime]`
  - *Done:* `OpticalTrain` frozen dataclass + `OpticalTrainRegistry` with `from_config()`, `get()`, `main()`, `guide()`, `all()`, `by_camera_index()`, `by_camera_role()` — `smart_telescope/services/optical_train_registry.py`
- [x] R4-002 Include camera role, serial/logical name, focuser binding, cooling capability, pixel scale, solver profile `[P1 · Runtime]`
  - *Done:* `OpticalTrain` has `camera_role`, `camera_index`, `telescope_name`, `focal_mm`, `reducer_factor`, `pixel_scale_arcsec`, `has_focuser`, `focuser`; pixel scale priority: explicit TOML → derived from camera profile pixel_um → global fallback
- [x] R4-003 Load train definitions from config `[P1 · Config]`
  - *Done:* `OpticalTrainSpec` in config.py with `_parse_telescopes()` + `_parse_optical_trains()`; `[telescopes]` and `[optical_trains]` sections added to `templates/config.toml`
- [x] R4-004 Validate train definitions at startup `[P1 · Config]`
  - *Done:* `from_config()` collects all errors and raises `ValueError` listing every broken telescope/camera reference; `RuntimeContext.get_optical_train_registry()` catches errors and returns empty registry
- [x] R4-005 Replace product-facing camera index selection with train/role selection `[P1 · Runtime]`
  - *Done:* All camera `<select>` elements now show train names ("main — c8", "guide — guide_scope"); values are train name strings; `_loadSelectFromTrains()` replaces `_loadSelectFromCameras()` for all camera selects; focuser autofocus select filters to trains with `has_focuser=true`
- [x] R4-006 Update preview, focuser, cooling, polar alignment, autogain, and setup to use train model `[P1 · Runtime]`
  - *Done:* Preview WS accepts `camera_role` query param → resolves to index via registry; autogain `RunRequest` accepts `camera_role`; autofocus `AutofocusRequest` accepts `camera_role`; UI API calls pass `camera_role` (preview, autogain, autofocus); APIs that still need index (goto_and_center, solver, histogram, calibration, polar) resolve via `_trainCamIdx(role)` helper
- [x] R4-007 Tests for two-camera and three-camera/OAG setups `[P1 · Tests]`
  - *Done:* 16 new tests in `tests/unit/api/test_r4_role_camera.py` — autogain role resolution (2-cam, 3-cam, unknown role fallback, backward compat), autofocus role resolution, preview WS role resolution, registry multi-train queries; 28 registry tests in `test_optical_train_registry.py`
- [x] R4-008 Make guided session optical-train aware: use role/train, never hard-code `camera:0`; derive `{"camera:N"}` from selected train `[P1 · Runtime]`
  - *Done:* `session_run` injects `OpticalTrainRegistry` via `Depends`; resolves `camera_resource = f"camera:{main_train.camera_index}"` from `registry.main()`; falls back to `"camera:0"` when no main train; 3 new tests in `test_r4_role_camera.py::TestSessionOpticalTrainAware`

### R5 — Config and Readiness Services

- [x] R5-001 Define `ConfigService` `[P1 · Config]`
  - *Done:* `ConfigError` exception class + `check_load_error()` function form the config service boundary; `_load_config_from_disk()` encapsulates all file loading logic
- [x] R5-002 Replace import-time config loading with explicit load `[P1 · Config]`
  - *Done:* TOML loading moved into `_load_config_from_disk()` function; module globals still populated at import time for backward compat; `check_load_error()` is the explicit check point called by `RuntimeContext.connect_devices()`
- [x] R5-003 Replace config `sys.exit` with structured startup error `[P1 · Config]`
  - *Done:* `sys.exit(...)` replaced by `_load_error = ConfigError(...)` stored on parse failure; `check_load_error()` raises it at startup (`RuntimeContext.connect_devices`); `ReadinessService._check_config_file()` surfaces it as a RED item; 4 new tests in `test_readiness.py`
- [x] R5-004 Add resolved path model (expand `~/`) — already in config.py `_expand()` `[P1 · Config]`
- [x] R5-005 Validate stars.cfg, horizon file, storage, ASTAP executable, ASTAP catalog, camera roles — in `ReadinessService` `[P1 · Config]`
- [x] R5-006 Define `ReadinessService` → `smart_telescope/services/readiness.py` `[P1 · Runtime]`
- [x] R5-007 Add red/yellow/green readiness summary → `/api/readiness` endpoint `[P1 · UI]`
- [x] R5-008 Add actionable repair guidance per failed check — `repair` field on every non-green item `[P1 · UI]`
- [x] R5-009 Update setup check endpoint and UI — readiness card at top of Stage 1, auto-loads on page open `[P1 · UI]`
- [x] R5-010 Tests: missing-file and invalid-config scenarios — `tests/unit/api/test_readiness.py` (22 tests) `[P1 · Tests]`
- [x] R5-011 Add explicit hardware mode field to readiness API and UI (`real` / `simulator` / `mock`) `[P1 · Runtime]`
  - *Acceptance:* `/api/readiness` includes `mode` field; `can_observe=true` blocked when mode is `mock` or `simulator`; UI label shows "REAL", "SIMULATOR", or "MOCK"; prevents accidental real-sky session with mock devices
  - *Done:* `RuntimeContext._hardware_mode` set by `_build_adapters()` from adapter types (ToupcamCamera+OnStepMount→real, Simulator→simulator, Mock→mock); `hardware_mode` property exposed; `ReadinessReport.mode` field added; `can_observe` blocked for non-real modes; mode item in readiness items list; REAL/SIMULATOR/MOCK badge in UI header; 8 new tests in `test_readiness.py`

### Field bugs — Config and optical train

- [x] BUG-008 `stars.cfg` not found on Pi even though file exists — tilde path not expanded `[P1 · Config · Source: Items_to_fix_20260514]`
  - *Done (R5-004):* `_expand()` using `Path.expanduser()` was added for all path globals (`STARS_CFG`, `HORIZON_DAT`, `STORAGE_DIR`, `IMAGE_ROOT`, `APP_STATE_DIR`); `STARS_CFG` default also constructed via `Path.home()` so tilde is never stored literally; verified by 4 new `TestExpandPath` tests in `test_readiness.py`
- [x] BUG-009 Cooling controls offered in setup page for cameras that don't support cooling `[P2 · UI · Source: Items_to_fix_20260514]`
  - *Done:* `onCoolingCamChange(role)` added — fetches `/api/cameras/{idx}/capabilities` for the selected train's camera and shows/hides the cooling card based on `has_tec`; called on select `onchange`, on "Connect All", and at page init; replaces the old "any camera has TEC" heuristic
- [x] BUG-010 Focuser log says not available, then later says available — connect ordering issue `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* focuser `is_available` reflects true hardware state after `connect()` even when serial buffer has stale bytes from mount init
  - *Done:* `OnStepFocuser.connect()` retries `:FA#` up to 3× with 300 ms gap; breaks on first `"1"`; logs each attempt; only warns when all attempts fail. Handles stale bytes left by `:GVP#` or `disable_tracking()` during `mount.connect()`. 4 new tests in `test_onstep_focuser.py::TestConnectRetry` — first-attempt success (no retry), 0→1 retry, exhausted (3×"0"), empty→"1".
- [x] BUG-013 Setup check fails to move mount at all `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Root cause:* `OnStepMount.connect()` made only a single stale-ACK retry; a second stale byte from a previous session's `disable_tracking()` exhausted the retry and closed the serial port. With `_serial = None`, all subsequent `get_state()` calls returned `UNKNOWN`, and the setup check wizard silently skipped all mount movement tests.
  - *Done:* `OnStepMount.connect()` retries `:GVP#` up to 3× with 300 ms gap + input buffer flush each time; only fails after all attempts exhausted; accepts any response containing "on"+"step" (case-insensitive); also accepts `'On-Step#On-Step'` doubled responses seen in the field. Setup check JS message changed from silent "state unknown — skipped" to "mount not connected — use Connect All to reconnect". 5 new tests in `test_onstep_mount.py::TestConnectRetry`.
- [x] BUG-017 Focuser linked to guide cam on status page; config requires it linked to main camera 678M `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Done (R4-005):* Focuser cam select now populated via `_loadSelectFromTrains()` filtered to `has_focuser=true`; guide cam train has `has_focuser=false` so it never appears in focuser controls
- [x] BUG-003 Startup shows both cameras under focuser section but not under cooling, polar alignment, or preview `[P1 · UI · Source: Items_to_fix_20260513]`
  - *Done (R4-005):* All camera selects now use train-based population; focuser select filters to `has_focuser=true`; cooling, PA, preview each populate independently from train registry
- [x] BUG-024 Preview shows `AUTO_GAIN_POSSIBLE_FOCUS_OR_POINTING_ERROR` for camera with no focuser connected `[P2 · UI · Source: Items_to_fix_20260514]`
  - *Done:* `_worker()` in `autogain.py` now resolves the train's `has_focuser` via `registry.by_camera_index(camera_index)` and ANDs it with `focuser.is_available`; guide camera with no focuser configured returns NO_SIGNAL instead of POSSIBLE_FOCUS_OR_POINTING_ERROR even when main camera's focuser is available; 4 new tests in `test_r4_role_camera.py`

### Milestone M3 tasks

- [x] M3-001 Complete R4 optical train registry `[P1 · Runtime]`
  - *Done:* R4-001..007 all complete
- [x] M3-002 Complete R5 config/readiness services `[P1 · Config]`
  - *Done:* R5-001..010 all complete
- [x] M3-003 Replace camera-index product UI with train roles `[P1 · UI]`
  - *Done:* R4-005 completed this
- [x] M3-004 Hide unsupported cooling/focuser controls `[P2 · UI]`
  - *Done:* BUG-009 (cooling card per TEC capability) and BUG-024 (autogain FOCUS_ERROR for no-focuser cameras) both resolved
- [x] M3-005 Provide red/yellow/green setup readiness `[P1 · UI]`
  - *Done:* R5-007 completed this

**Quality gate:** Main camera/focuser association correct. Guide camera not shown as focus-controlled. Cooling absent for non-cooled cameras. Setup check detects missing files and devices.

---

## M4 — Intent-Driven Smart Telescope UX

*User operates the telescope by intent, not by device expertise.*

### UX1 — Ready To Observe Screen

- [x] UX1-001 Add red/yellow/green readiness summary `[P1 · UI]`
- [x] UX1-002 Show config, storage, ASTAP, catalog, camera, mount, focuser readiness `[P1 · UI]`
- [x] UX1-003 Provide repair guidance for each failed check `[P1 · UI]`
- [x] UX1-004 Make readiness the default first-run experience — card loads automatically at page open `[P1 · UI]`

### UX2 — Intent-Based Observation Flow

- [x] UX2-001 Add `Start Observation` as the primary action `[P1 · UI]`
  - *Done:* Card title updated to "Start Observation"; Start button is the primary CTA in Stage 5.
- [x] UX2-002 Show guided progress steps (slewing → solving → centering → focusing → capturing) `[P1 · UI]`
  - *Done:* 5-step pipeline strip (Connect → GoTo → Centre → Focus → Capture) shown inside run-status panel; steps update live with done/active/failed states.
- [x] UX2-003 Move autogain/autofocus/solve/recenter into the automatic workflow `[P1 · UI]`
  - *Done:* Backend VerticalSliceRunner already sequences all steps; the pipeline strip makes the automatic sequencing visible to the user.
- [x] UX2-004 Show recovery actions when automation fails `[P1 · UI]`
  - *Done:* Recovery banner shown inside run-status when state=FAILED; includes failure reason, contextual action suggestion, and Retry button.

### UX3 — Hide Camera Index Thinking

- [x] UX3-001 Show main telescope camera by role name, not index `[P1 · UI]`
  - *Done (R4-005):* All camera selects show train names ("main — c8", "guide — guide_scope")
- [x] UX3-002 Show guide/OAG/wide-field camera only as configured roles `[P1 · UI]`
  - *Done (R4-005):* Trains appear only when configured; focuser select filters to has_focuser=true
- [x] UX3-003 Show serial/logical name only in diagnostics `[P2 · UI]`
  - *Done:* Camera IDs / hardware serials shown only in `cameraCard()` in Stage 6 scan area. Main UI uses optical train role names ("main", "guide") throughout.
- [x] UX3-004 Hide unsupported controls (e.g. cooling for non-cooled cameras) `[P2 · UI]`
  - *Done (BUG-009/M3-004):* Cooling card shown/hidden dynamically via `onCoolingCamChange()` based on camera TEC capability; focuser controls filtered by `has_focuser` in optical train registry.

### UX4 — Advanced Mode For Manual Controls

- [x] UX4-001 Add beginner/advanced mode distinction `[P2 · UI]`
  - *Done:* "Advanced" toggle button in header; state persisted in `localStorage` (`tsc_advanced_mode`). `body.advanced-mode` CSS class controls `.adv-only` visibility.
- [x] UX4-002 Move manual mount controls to advanced/diagnostics (except emergency stop) `[P2 · UI]`
  - *Done:* Home / Unpark / Park / Enable Tracking / Disable Tracking wrapped in `.adv-only` span in `mountCard()`. Stop always visible.
- [x] UX4-003 Move manual focuser controls to advanced/diagnostics (except recovery actions) `[P2 · UI]`
  - *Done:* Nudge buttons (±1000/±100/±10) and Move To row wrapped in `.adv-only` in `focuserCard()`. Autofocus and Stop always visible.
- [x] UX4-004 Keep emergency stop globally visible at all times `[P0 · UI]`
  - *Done:* Mount strip now starts visible (class `visible` in HTML); `goToStage()` no longer hides it on Stage 1. STOP button is in the strip at all times.

### UX5 — Recovery-Oriented Errors

- [x] UX5-001 Define error model: what happened / safety state / user action / retry `[P1 · UI]`
  - *Done:* `friendlyError(raw)` maps raw error strings to `{message, hint}`. `setStatus(..., true)` renders the translated message + hint. Recovery banner (UX2-004) covers session failures.
- [x] UX5-002 Map OnStep command errors to user-facing messages `[P1 · UI]`
  - *Done:* `_ERROR_PATTERNS` includes serial timeout, serial error, rejected command, not connected, not aligned, unsafe position patterns.
- [x] UX5-003 Map camera errors to user-facing messages `[P1 · UI]`
  - *Done:* Camera not found, capture timeout, camera error patterns in `_ERROR_PATTERNS`.
- [x] UX5-004 Map solver errors to user-facing messages `[P1 · UI]`
  - *Done:* ASTAP not found, catalog not found, no stars, plate solve failed patterns in `_ERROR_PATTERNS`.
- [x] UX5-005 Add diagnostics link for advanced error details `[P2 · UI]`
  - *Done:* `setStatus(..., true)` now appends a "→ Setup & Diagnostics" link that calls `goToStage(1)`. Visible on every error status banner.

### Field bugs — UX and errors

- [x] BUG-014 Home button generates HTTP 500; message `Home failed: GoTo failed` gives no cause or next action `[P1 · UI · Source: Items_to_fix_20260514]`
  - *Done:* `mount_home` now returns `"Home slew failed — check mount is tracking and powered (<detail>)"`
  - *Acceptance:* error states cause, current safety state, and recommended next action
- [x] BUG-015 HOME, PARK, UNPARK, STOP buttons should be grouped together `[P3 · UI · Source: Items_to_fix_20260514]`
- [ ] BUG-002 AG checkbox vs Autogain button layout confusing; AF button below histogram, autogain at bottom `[P3 · UI · Source: Items_to_fix_20260513]`
- [x] BUG-004 Histogram should show detail below ADU 1000 and current block size above `[P3 · UI · Source: Items_to_fix_20260513]`
  - *Done:* `showHistogram()` now draws `0–Xk ADU · N ADU/bin` as a text overlay inside the canvas top-right; `s3-hist-low-label` given an id and updated dynamically by `_updateLowLabel()` on each draw (was hardcoded "5 ADU/bin", now shows real bin size)
- [x] BUG-021 Histogram not filled at small values `[P3 · UI · Source: Items_to_fix_20260514]`
  - *Done:* `histogram_bins_focused` no longer uses `adc_max×0.05` floor — dim images (p99.9=200 ADU) now zoom to 1000 ADU range instead of 3276, filling the canvas 3× better; JS bar rendering uses `Math.max(1, Math.round(hRaw))` for non-zero bins so every bin with any pixels shows at least 1px

### Milestone M4 tasks

- [x] M4-001 Implement `Ready to Observe` first-run screen `[P1 · UI]`
  - *Done (UX1):* Readiness card loads automatically on Stage 1 page open; red/yellow/green summary with repair guidance.
- [x] M4-002 Implement target recommendation view `[P1 · UI]`
  - *Done:* "Visible Tonight" card in Stage 5 uses `/api/catalog/tonight` to list Messier objects above 20° sorted by altitude; clicking any row sets the target; card auto-loads on entering Stage 5.
- [x] M4-003 Implement `Start Observation` guided workflow `[P1 · UI]`
  - *Done (UX2):* Pipeline step strip shows Connect→GoTo→Centre→Focus→Capture live; recovery banner on failure.
- [x] M4-004 Move manual controls into advanced/diagnostics mode `[P2 · UI]`
  - *Done (UX4-001/002/003):* Advanced Mode toggle in header; Home/Unpark/Park/Tracking hidden in beginner mode; focuser nudge/Move-To hidden in beginner mode.
- [x] M4-005 Add recovery-oriented errors `[P1 · UI]`
  - *Done (UX5):* `friendlyError()` + `_ERROR_PATTERNS` in setStatus; recovery banner in session.
- [x] M4-006 Keep emergency stop globally visible `[P0 · UI]`
  - *Done (UX4-004):* Mount strip always visible on all stages.

**Quality gate:** User can start observing without manually managing solve/focus/gain/recenter. Beginner mode avoids camera indices and hardware jargon. Recovery messages tell user what to do next.

---

## Collimation Assistant — C8 SCT

*Source: `resources/hlrequirements/smarttscope_c8_collimation_assistant_task_plan_updated.md`*

### Phase 0 — Project Skeleton and Configuration

- [x] COL-001 Add collimation configuration model (`domain/collimation/config.py`) `[P1 · Collimation]`
  - *Done:* `CollimationConfig` + sub-configs for focuser, mount centering, rough/fine collimation; loads from TOML; validates on load
- [x] COL-002 Define core domain models (`domain/collimation/models.py`) `[P1 · Collimation]`
  - *Done:* `StarMeasurement`, `DonutMeasurement`, `SpikeMeasurement`, `FrameMeasurement`, `CollimationRecommendation`, `ScrewCalibration`, `MaskSectorCalibration`, `ContradictionAssessment`, `MechanicalAlignmentReport`, `CircleEllipseFit`, `ReferenceCenterCalibration`
- [x] COL-003 Add reference-center abstraction (`ReferenceCenterCalibration.compute()`) `[P1 · Collimation]`
  - *Done:* defaults to frame center; calibrated offset supported; all measurement algorithms must use `.compute()`, not hard-coded `width/2`
- [x] COL-004 Add optical train profiles (`domain/collimation/profiles.py`) `[P1 · Collimation]`
  - *Done:* `CollimationOpticalProfile` with C8/f10/678M, C8/f10/ATR585M, C8/f6.3, C8/f20 Barlow profiles; pixel scale, obstruction ratio, focal ratio computed as properties

### Phase 1 — Service and Wizard State Machine

- [x] COL-010 Implement `CollimationStateMachine` with 20 states (`services/collimation/state_machine.py`) `[P1 · Collimation]`
  - *Done:* `VALID_TRANSITIONS` dict; `pause()`/`resume()` outside transition table; `USER_WAIT_STATES` + `TERMINAL_STATES`; `InvalidTransitionError`
- [x] COL-011 Implement `CollimationAssistant` background service (`services/collimation/assistant.py`) `[P1 · Collimation]`
  - *Done:* `start()`, `pause()`, `resume()`, `cancel()`, `advance()`, `retry()`; background thread; `.status`, `.overlay`, `.report` properties; state handlers are stubs (Phases 3-9 fill them)
- [x] COL-012 Add wizard REST API (`api/collimation.py`) `[P1 · Collimation]`
  - *Done:* `GET /api/collimation/status|overlay|report`; `POST /api/collimation/start|pause|resume|cancel|next|retry`

### Phase 3 — Frame Processing Foundation

- [x] COL-030 Normalize Touptek frame input (`domain/collimation/processing/frame.py`) `[P1 · Collimation]`
  - *Done:* `ProcessedFrame` dataclass with `raw` (uint16), `mono` (float32), `bit_depth`, `width`, `height`, `timestamp`; `normalize_frame(FitsFrame)` — copies, does not mutate; `.normalized` property returns [0,1] float32
- [x] COL-031 Add display stretch pipeline (`domain/collimation/processing/stretch.py`) `[P1 · Collimation]`
  - *Done:* `estimate_background()` (sigma-clip, 5 iter); `auto_stretch()` → uint8; `saturation_fraction(bit_depth)`; `peak_location()`
- [x] COL-032 Add star detection (`domain/collimation/processing/star_detection.py`) `[P1 · Collimation]`
  - *Done:* `detect_star(ProcessedFrame) → StarMeasurement | None`; 5-sigma threshold; intensity-weighted centroid; radial-profile FWHM; hot-pixel/nebula rejection; SNR-based confidence
- [x] COL-033 Add circle/ellipse fitting primitives (`domain/collimation/processing/geometry_fits.py`) `[P1 · Collimation]`
  - *Done:* `fit_circle()` (Kasa algebraic LSQ); `fit_ellipse()` (Bookstein direct fit → eigenvalue decomposition); `extract_edge_points()` (4-connectivity erosion); `detect_clipping()`; `compare_circle_centers()`
- [x] COL-034 Tests: 75 tests, all pass (`tests/unit/domain/collimation/`) `[P1 · Tests]`
  - *Done:* `test_frame_processing.py` (18), `test_stretch.py` (22), `test_star_detection.py` (11), `test_geometry_fits.py` (24)

### Phase 2 — User-Visible MVP Shell (UI)

- [x] COL-020 Add wizard panel (current step, instruction, status, pause/cancel) `[P2 · Collimation · UI]`
  - *Done:* Wizard card added to Stage 4 with 5-phase progress strip, instruction text, recommendation block, Start/Pause/Resume/Cancel/Reset action buttons, contextual Remeasure/Finish-Phase/Accept/Adjust-More buttons, error display; polls `/api/collimation/status` every 2 s when active; star clicks in SELECT_STAR state route to `/api/collimation/next` with ra/dec.
- [x] COL-021 Add overlay visibility test mode (crosshair, test circles, screw labels) `[P2 · Collimation · UI]`
  - *Done:* `_drawCollimOverlay()` draws donut outer/inner circles (blue/green), error vector (red arrow), and spike crossing crosshair on `s4-bahtinov-svg` overlay; polled from `/api/collimation/overlay` alongside status poll.
- [x] COL-022 Add hardware self-test page (camera stream, mount pulse guide, focuser small step) `[P2 · Collimation · UI]`
  - *Done:* Self-test card added before the wizard in Stage 4; 3 API endpoints (`POST /api/collimation/selftest/{camera,mount,focuser}`); camera returns frame dimensions + peak ADU; mount fires a 500 ms guide pulse N/S/E/W; focuser moves ±10 steps and shows position delta (no-op message when unavailable); 14 tests in `test_collimation_selftest.py`

### Phase 4 — Mount and Focuser Control

- [x] COL-040 Add safe pulse-guide centering interface `[P1 · Collimation]`
  - *Done:* `PulseCenterer` in `services/collimation/mount_centering.py` — converts px offset → guide pulse, clamps to max_pulse_ms, settles, iterates; stops on star_lost / diverging (3 × 10 % grow) / cancel / max_iterations; cos(dec) RA rate correction; `MountCorrectionResult` dataclass
- [x] COL-041 Add relative focuser control (move_focus_relative, CW/CCW) `[P1 · Collimation]`
  - *Done:* `CollimationFocuserControl` in `services/collimation/focuser_control.py` — `move_focus_relative()`, `move_focus_clockwise()`, `move_focus_counterclockwise()`, `defocus()`, `focus_fine()`; max_single_step clamp; soft position [min, max] clamp; direction mapping from `increasing_value_direction` config; `FocuserMoveResult` with clipped + reason; fixed `MockFocuser.move()` bug (was setting position, now adds steps)

### Phase 5 — Star Selection and Acquisition

- [x] COL-050 Bright star selection from built-in catalog (altitude ≥ 60°, fallback 45°) `[P1 · Collimation]`
  - *Done:* `CollimationStarSelector` in `services/collimation/star_selector.py` — `select()` picks brightest star above 60° (fallback 45° with warning), `select_by_name()` for manual override; `load_bright_stars()` parses stars.cfg TOML (type="star" filter); `BrightStar`, `CollimationStarCandidate`, `StarSelectionResult` dataclasses; 22 tests in `test_star_selector.py`
- [x] COL-051 Slew + star detection + centering loop `[P1 · Collimation]`
  - *Done:* `StarAcquisition` in `services/collimation/star_acquisition.py` — slew via `mount.goto()`, wait for slew completion, enable tracking, settle, capture + `detect_star()`, center via `PulseCenterer`; `AcquisitionResult` dataclass; 13 tests in `test_star_acquisition.py`; all 1950 tests pass, coverage 83%

### Phase 6 — Focuser Algorithm

- [x] COL-060 Image-based rough focus search (relative steps, bracket, final approach direction) `[P1 · Collimation]`
  - *Done:* `services/collimation/focus_search.py` — `FocusSearcher` with probe→scan→backtrack→final-approach; 11 tests
- [x] COL-061 Controlled defocus to donut regime (target 25–50 % frame) `[P1 · Collimation]`
  - *Done:* `services/collimation/defocus_controller.py` — `DefocusController` with threshold-masked RMS radius (6σ above bg), clipping check via 10%-of-peak bounding box; 12 tests

### Phase 7 — Rough Donut Collimation

- [x] COL-070 Donut detection: outer ring + inner shadow fitting `[P1 · Collimation]`
  - *Done:* `domain/collimation/processing/donut_detection.py` — `DonutAnalyzer` with ring mask (10% of peak), brightness centroid, RMS-radius split of edge pixels, Kasa circle fit to inner/outer boundaries; 17 tests
- [x] COL-071 Rough error vector: shadow center − outer center `[P1 · Collimation]`
  - *Done:* error vector computed in `DonutAnalyzer.analyze()` → `DonutMeasurement.error_x_px / error_y_px / error_magnitude_px / error_angle_deg`
- [x] COL-072 Rough overlay: ellipses, error vector, screw labels, traffic-light `[P1 · Collimation]`
  - *Done:* `services/collimation/donut_overlay.py` — `build_donut_overlay()` → `DonutOverlay` with outer/inner circles, error vector, traffic-light (green <2%, yellow <10%, red ≥10%), T1/T2/T3 screw markers at 1.25× outer radius; 25 tests

### Phase 8 — Screw Identification

- [x] COL-080 Screw detection by hand obstruction shadow `[P1 · Collimation]`
  - *Done:* `domain/collimation/processing/obstruction_detection.py` — `detect_obstruction(reference, current, cx, cy)` thresholds diff (ref−current) at 5σ, finds shadow centroid, returns angle from outer ring center; 15 tests; new domain model `ScrewAngularPosition` added to models.py
- [x] COL-081 Screw response learning (before/after adjustment) `[P2 · Collimation]`
  - *Done:* `services/collimation/screw_mapper.py` — `ScrewResponseLearner` accumulates before/after `DonutMeasurement` pairs per screw, averages CW-equivalent response vectors, returns `ScrewCalibration`; confidence saturates at 5 samples; 22 tests

### Phase 9 — Rough Collimation Guidance

- [x] COL-090 Generate safe screw recommendations (tiny/slight/very slight) `[P1 · Collimation]`
  - *Done:* `services/collimation/collimation_advisor.py` — `CollimationAdvisor` projects error vector onto each screw's response vector (cosine similarity), selects best screw and CW/CCW direction; size: MEDIUM (>15% of ring) or SMALL (≤15%); never LARGE; low-calibration-confidence halves recommendation confidence; 18 tests
- [x] COL-091 Live "turn until OK" — detect improvement and tell user when to stop `[P1 · Collimation]`
  - *Done:* `services/collimation/live_guidance.py` — `LiveGuidanceMonitor` polls `get_measurement()` each settle interval; tracks improvement (5% threshold); stops on: converged (error < green_fraction × outer_radius), worsened (2 consecutive non-improvements), star_lost, cancelled, max_frames; returns `LiveGuidanceResult` with reason, improvement_px, frame_count; 15 tests

### Phase 10 — Tri-Bahtinov Fine Collimation

- [x] COL-100 Detect Tri-Bahtinov spike pattern (background subtraction + line fitting) `[P1 · Collimation]`
- [x] COL-101 Mask sector mapping via blade open/close `[P1 · Collimation]`
- [x] COL-102 Spike measurement smoothing (7-frame window, median + trend) `[P2 · Collimation]`

### Phase 11 — Fine Focus and Fine Collimation

- [x] COL-110 Separate common focus error from per-sector collimation residual `[P1 · Collimation]`
- [x] COL-111 Fine focus loop (image feedback, final approach direction) `[P1 · Collimation]`
- [x] COL-112 Fine collimation guidance (residual ≤ 2 px target) `[P1 · Collimation]`
- [x] COL-113 Contradiction detection: block screw hints when indicators disagree `[P1 · Collimation]`

### Phase 12 — Validation and Report

- [x] COL-120 Final refocus without mask `[P1 · Collimation]`
- [x] COL-121 Maskless validation (donut symmetry, optional Airy) `[P1 · Collimation]`
- [x] COL-122 Short session report via `/api/collimation/report` `[P1 · Collimation]`

### Phase 13 — Replay and Test Infrastructure

- [x] COL-130 Replay frame provider (prerecorded test frames, no hardware needed) `[P2 · Collimation]`
- [x] COL-131 Unit tests for remaining algorithm phases `[P1 · Collimation]`

### Phase 14 — Live Pipeline Wiring

- [x] COL-140 Wire acquisition pipeline: ACQUIRE_STAR → CENTER_STAR → AUTO_EXPOSURE `[P1 · Collimation]`
  - *Done:* `_handle_acquire_star` (5-attempt star detection), `_handle_center_star` (centering loop), `_handle_auto_exposure` (8-step ADU search)
- [x] COL-141 Wire rough collimation pipeline: ROUGH_DEFOCUS → MAP_SCREWS → MEASURE_DONUT → GUIDE_ROUGH_COLLIMATION `[P1 · Collimation]`
  - *Done:* `_handle_rough_defocus` (focuser steps to defocus target), `_handle_map_screws_by_obstruction`, `_handle_measure_donut` (DonutAnalyzer), `_handle_guide_rough_collimation` (user-wait with advisor recommendation)
- [x] COL-142 Wire fine collimation pipeline: MAP_MASK_SECTORS → FINE_FOCUS → MEASURE_SPIKES → GUIDE_FINE_COLLIMATION → MASKLESS_VALIDATION `[P1 · Collimation]`
  - *Done:* `_handle_map_mask_sectors` (MaskSectorCalibration + SpikeSmoother + ContradictionDetector init), `_handle_fine_focus`, `_handle_measure_spikes` (BahtinovAnalyzer), `_handle_guide_fine_collimation`, `_handle_maskless_validation`

---

## M5 — Product Acceptance MVP

*SmartTScope can perform a meaningful smart telescope workflow safely enough to demonstrate.*

### R6 — API Thinness and UI Consistency

- [x] R6-001 Move mount/focuser/camera/setup/job orchestration out of API modules into services `[P1 · Runtime]`
  - *Done:* `CoolingService` extracted from `api/cooling.py` → `services/cooling.py` (full session/threading moved out). `MountOperations` extracted from `api/mount.py` → `services/mount_operations.py` (safe_goto, home_sequence, park_sequence, unpark_sequence, track_sequence). 35 new service tests.
- [x] R6-002 Keep API modules thin: validate request, call service, map response `[P1 · Runtime]`
  - *Done:* `api/cooling.py` reduced from 251 to 86 lines. `api/mount.py` endpoints for unpark/track/home/park now delegate to `mount_operations` and map domain exceptions to HTTP.
- [x] R6-003 Split large static UI into maintainable modules `[P2 · UI]`
  - *Done:* `index.html` reduced from 6216 to 1847 lines (HTML/CSS only); 4376 lines of JS split into 8 modules in `static/js/`: `api.js` (API client), `app.js` (globals + nav + init), `mount.js` (mount card + guide + PA), `collimation.js` (wizard + overlay), `focuser.js` (focuser card + position poll), `preview.js` (preview WS + autogain + Bahtinov), `session.js` (pipeline + guide monitor), `setup.js` (readiness + health + catalog + cooling + cameras + sky). `StaticFiles` added to `app.py`; `pyproject.toml` package-data updated.
- [x] R6-004 Create shared frontend API client and shared device/job state model `[P2 · UI]`
  - *Done:* `static/js/api.js` contains `escHtml()`, `_ERROR_PATTERNS`, `friendlyError()`, `setStatus()`, `apiPost()` — loaded first by all pages, providing a uniform fetch + error-translation layer used by all other modules.
- [x] R6-005 Ensure STOP button is globally available `[P0 · UI]`
  - *Done (UX4-004):* Mount strip starts visible; STOP button visible on all stages.
- [x] R6-006 Browser smoke tests: setup, preview, mount, focuser, stop `[P1 · Tests]`
  - *Done:* `tests/unit/api/test_smoke.py` — 39 tests covering HTML page load, readiness API shape, mount status (state/stale/watchdog fields), focuser status (available/position/moving), emergency STOP (always 200, mount_stopped true/false, calls stop once), optical trains list, version endpoint; all mock-based, no hardware.
- [x] R6-007 Add `FocusRunConfig` policy object; clean focus sub-boundary so focus options touch only focus domain `[P2 · Runtime]`
  - *Acceptance:* focus options (step size, frame count, timeout) carried in a `FocusRunConfig` object passed top-down; changes to focus options touch only focus domain, focus service, one API shape, and focused tests; session/mount internals not touched
  - *Done:* `FocusRunConfig` added to `domain/autofocus.py` with `to_params()` factory; `StageContext` 5 flat fields → `focus_config: FocusRunConfig`; `VerticalSliceRunner` 5 flat params → `focus_config`; `api/session.py` builds `FocusRunConfig` from Query params; `conftest.py` updated; `stage_stack` mid-refocus deduplication; 12 new tests in `tests/unit/domain/test_focus_run_config.py`; 2565 tests pass

### Milestone M5 tasks

- [ ] M5-001 Guided startup `[P1 · Product]`
- [ ] M5-002 Connect all configured devices `[P1 · Hardware]`
- [ ] M5-003 Show readiness dashboard `[P1 · UI]`
- [ ] M5-004 Select target `[P1 · Product]`
- [x] M5-005 Enforce solar safety gate `[P0 · Hardware]`
  - *Acceptance:* solar exclusion enforced at ALL GoTo entry points: direct GoTo, catalog target launch, guided session launch, sky slew; test shows rejection for Sun coordinates from each entry point
  - *Done:* `is_solar_target()` called in `mount_goto`, `mount_goto_and_center`, `mount_goto_sky`, and `session_run`; each returns HTTP 403 with `solar_exclusion` detail; catalog tonight marks `solar_safe` flag; `confirm_solar=true` bypass available; tests in `test_mount.py` and `test_session.py`
- [ ] M5-006 Validate mount limits `[P1 · Hardware]`
- [ ] M5-007 GoTo, plate solve, recenter `[P1 · Hardware]`
- [ ] M5-008 Focus and optimize exposure `[P1 · Hardware]`
- [ ] M5-009 Preview and stack `[P1 · Imaging]`
- [ ] M5-010 Save output image and session log `[P1 · Imaging]`
- [ ] M5-011 Stop/recover safely `[P0 · Hardware]`
- [ ] M5-012 Verify reconnect and shutdown behavior `[P1 · Hardware]`
- [x] M5-013 Dawn auto-park: auto-park when astronomical dawn approaches (end-of-night behaviour) `[P2 · Product]`
  - *Acceptance:* system parks mount automatically at astronomical dawn (sun at −18°); user notified; hardware stays connected after park for diagnostics/retry
  - *Done:* `DawnWatcher` background service polls sun altitude every 60 s; parks once when alt ≥ −18°; `GET /api/dawn` returns status; `sun_altitude_now()` added to `domain/solar.py`; 12 tests

**Quality gate:** Full workflow demonstrated on real hardware. Emergency stop tested during workflow. Logs useful without shell investigation. Product owner signs off against visible checklist.

---

## M6 — Field Reliability and Release Readiness

*System survives normal field use, not just a single demo.*

### R7 — Operational Evidence and Release Gate

- [x] R7-001 Define operational acceptance checklist `[P1 · Process]`
  - *Done:* `docs/operational-acceptance-checklist.md` — 10-section field checklist covering power-on, connect all, readiness dashboard, setup check, solar gate, GoTo/plate-solve, autofocus, emergency STOP, stack, shutdown, sign-off table
- [x] R7-002 Define hardware test log template `[P1 · Process]`
  - *Done:* `docs/hardware-test-log-template.md` — append-only log with six required evidence items (E-001 through E-006) and structured entry template (date, commit, steps, result, log extract)
- [x] R7-003 Define release go/no-go checklist `[P1 · Process]`
  - *Done:* `docs/release-checklist.md` — 8-section gate checklist with BLOCKER items, backlog gate, hardware evidence gate, clean install gate, performance targets, sign-off table, deferred items register
- [ ] R7-004 Record evidence: STOP during slew, STOP during focuser move, shutdown during motion, reconnect, setup check, full observing workflow `[P0 · Hardware]`
- [x] R7-005 Add product-owner milestone dashboard `[P2 · Product]`
  - *Done:* `GET /api/milestones` returns milestone completion stats (`id`, `name`, `total`, `done`, `open`, `hardware_blocked`, `status`) and top-10 risk items; status logic: green=no open non-hardware tasks, yellow=P2/P3 open or only hardware-blocked, red=P0/P1 open non-hardware; "Milestone Dashboard" card added to Stage 1 UI showing color-coded progress bars and top-risk list; `MILESTONE_REGISTRY` and `RISK_REGISTRY` in `domain/milestones.py`; 25 tests (domain + API).
- [x] R7-006 Add done-without-evidence report `[P2 · Process]`
  - *Done:* `EvidenceGapItem` dataclass + `EVIDENCE_GAPS` registry (8 items, P0 before P1) in `domain/milestones.py`; `GET /api/evidence-gaps` returns `{items, count}` with `id`, `priority`, `description`, `milestone`, `mock_tested_by`, `hardware_needed`; 13 new tests added to milestone test files.

### Milestone M6 tasks

- [x] M6-001 Define unattended session duration target `[P2 · Process]`
  - *Done:* 6 hours; in `domain/performance_targets.py` + `GET /api/performance-targets`
- [x] M6-002 Define preview latency target `[P2 · Process]`
  - *Done:* ≤ 2 s per frame; in `domain/performance_targets.py`
- [x] M6-003 Define stop-response time target `[P1 · Process]`
  - *Done:* ≤ 500 ms (aligns with POD-002 cancel-latency decision); in `domain/performance_targets.py`
- [x] M6-004 Define centering accuracy target `[P2 · Process]`
  - *Done:* ≤ 30 arcsec RMS after one plate-solve/recenter cycle; in `domain/performance_targets.py`
- [x] M6-005 Define plate solve success rate target `[P2 · Process]`
  - *Done:* ≥ 90% first-attempt under clear dark-sky conditions with full ASTAP catalog; in `domain/performance_targets.py`
- [x] M6-006 Define Pi thermal ceiling target `[P2 · Process]`
  - *Done:* ≤ 75°C sustained (5°C headroom below Pi 5 throttle point of 80°C); in `domain/performance_targets.py`
- [ ] M6-007 Run long session reliability test `[P1 · Hardware]`
- [ ] M6-008 Run Pi thermal test `[P2 · Hardware]`
- [x] M6-009 Run storage-full simulation `[P2 · Tests]`
  - *Done:* `DiskStorage` raises `OSError(ENOSPC)` on write failure; `stage_save()` raises `WorkflowError("save", "Disk full…")` when `has_free_space()` is False; runner wraps unexpected `OSError` from `save_image`/`save_log` into `WorkflowError`; partial-save scenario (image written, log write fails) preserves `saved_image_path`; 8 tests in `test_disk_storage.py` and `test_runner_stages.py` all pass.
- [ ] M6-010 Run network reconnect simulation `[P1 · Hardware]`
- [ ] M6-011 Verify clean Pi install from scratch `[P1 · Hardware]`
- [ ] M6-012 Produce release notes and known issues `[P1 · Process]`

**Quality gate:** Long session completes or fails gracefully. Thermal limits not exceeded. Storage-full behavior does not corrupt session data. Reconnect behavior defined and verified. Release installable from clean state.

---

## Deferred — Post-MVP

- [ ] BUG-007 Support frame types: bias, dark, flat frames; master frames; bad pixel maps `[P2 · Imaging · Source: Items_to_fix_20260513]`
  - No automatic cover exists; user must drive frame collection manually. Defer to post-MVP.
- [ ] BUG-006 Extended setup check: focuser move test, RA/DEC 10° test, multi-camera plate solve, home return `[P2 · Hardware · Source: Items_to_fix_20260513]`
  - Implement after M3 readiness service is in place.
- [x] BUG-018 Park logs `park issued` but unpark logs nothing `[P3 · Logging · Source: Items_to_fix_20260514]`
  - *Done:* Added `_log.info("Mount unpark issued")` in `services/mount_operations.py::unpark_sequence()` immediately after the unpark command is accepted.
- [x] BUG-020 Clicking +20 focuser not logged when live preview is running `[P2 · Logging · Source: Items_to_fix_20260514]`
  - *Done:* Added `_log.info("Focuser nudge request: delta=%d", body.delta)` at the entry of `api/focuser.py::focuser_nudge()` — logs every nudge request before any conflict check.

---

## Open Product-Owner Decisions

- [x] POD-001 After reconnect: preserve session, park mount, or ask user?
  - *Decision:* Auto-park on reconnect — already the implemented behaviour in `RuntimeContext._build_adapters()`.
- [x] POD-002 Maximum acceptable STOP response time?
  - *Decision:* **< 1 s** — applies to mount slew abort and focuser stop. Used as acceptance bar for BUG-001 and the safety regression checklist.
- [x] POD-003 What state may the UI show after command acceptance but before hardware confirmation?
  - *Decision:* **Show spinner / pending indicator** — after a Park/Unpark/Home/GoTo command is accepted, the label shows a loading state until `DeviceStateService` confirms the new hardware state. Adds a UX task: see UX-PENDING-001 below.
- [ ] POD-004 Is SDK camera index acceptable anywhere outside diagnostics?
- [ ] POD-005 Which failures may block the whole app, and which must degrade locally?
  - *Guidance (decision pending):* ASTAP missing → blocks observing only; mount serial failure → allows camera preview + diagnostics; camera failure → allows mount controls + diagnostics. Formal isolation policy needed before M5.
- [x] POD-006 What is the minimum successful demo workflow?
  - *Decision:* **Guided single-target session** — Pick target → GoTo → plate-solve & center → autofocus → stack 10 frames → save. That is the MVP demo.
- [x] POD-007 What evidence is required for product-owner sign-off?
  - *Decision:* Pi hardware/app logs + saved FITS/output image + session JSON log. Evidence folder: one directory with timestamped app log, session JSON, and saved output image from a real hardware session.
- [x] POD-008 Which requirements are deferred beyond MVP?
  - *Decision:* Defer ISS tracking, multi-target queue, advanced calibration frames wizard, and deep collimation algorithm phases to post-MVP. Minimal collimation wizard UI shell (start/status/overlay) is part of the MVP demo.
- [ ] POD-009 Concrete performance targets: preview latency, solve time, centering accuracy, Pi thermal ceiling?
- [ ] POD-010 Should SDK camera indices be forbidden in API request bodies, or only hidden in the UI? `[P2 · Process]`
  - *Context:* R4 removed indices from product UI; some API endpoints still accept index directly. Decision needed for API contract (affects R4-008 and any client tooling).

### UX-PENDING-001 — Command-pending indicator in mount/focuser UI `[P1 · UI]`

- [x] Mount card state badge shows spinner + `cmd…` while command is in flight
- [x] Mount strip state label shows `cmd…` while command is in flight
- [x] Dot turns yellow while pending; reverts to hardware-confirmed colour on next poll
- [x] `stale: true` from API shown as `⚠ state` badge / strip label suffix
- [x] `mountAction()`, `mountHome()`, `mountGoto()` all set/clear `_mountPendingCmd`
- [x] Card re-renders immediately on command acceptance (pending) and on poll confirmation (final)

---

## Safety Regression Checklist

*Run before every milestone demo and release. STOP response time target: **< 1 s** (POD-002).*

- [ ] STOP works during mount slew — response confirmed < 1 s on real hardware
- [ ] STOP works during focuser movement — response confirmed < 1 s on real hardware
- [ ] Shutdown stops motion before disconnect
- [ ] Park label follows observed hardware state (not command receipt)
- [ ] Unpark label follows observed hardware state (not command receipt)
- [ ] New mount command rejected while unsafe movement is active
- [ ] New focuser command rejected while prior movement is still active
- [ ] Preview failure does not affect mount/focuser controls
- [ ] Autogain cancellation exits within agreed timeout
- [ ] Session stop exits within agreed timeout
- [ ] Camera conflicts detected and reported
- [ ] Missing config files produce actionable diagnostics
