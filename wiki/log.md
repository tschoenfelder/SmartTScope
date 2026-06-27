# Wiki Log

Append-only record of all wiki operations.

---

## 2026-06-27 — DEVELOP — M8-016 (User-action log — 18 named actions; REQ-LOG-003)

**Structured user-action log for all 18 named UI interactions.**
- `smart_telescope/domain/user_action_log.py` (new): `USER_ACTIONS` 18-name tuple + `UserActionRecord` (action, timestamp, result, gate_reason); `to_json_line()`
- `smart_telescope/services/user_action_logger.py` (new): `UserActionLogger` with `_ACTION_SECTIONS` mapping; `log(action, result, gate_reason)` writes JSON line to the right section logger
- `smart_telescope/runtime.py` + `api/deps.py`: `user_action_logger` constructed on init + in `reset_for_tests()`; `get_user_action_logger()` injector
- Wired into 9 existing endpoints: `session_connect`, `mount_track` (track_requested/rejected), `mount_goto` (goto_requested/rejected/bright_star), `mount_sync_clock` (push_confirmed/rejected), `mount_confirm_time`, `run_autogain` (diagnostic), `focuser_autofocus`, `collimation_start`, `solver_solve`
- Tests: 17 unit tests in `tests/unit/services/test_user_action_logger.py`; suite: 3501 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-015 (Service-call logs per iteration; REQ-LOG-002)

**Structured per-iteration logging for auto-gain, plate-solve, and autofocus.**
- `smart_telescope/domain/service_call_log.py` (new): `ServiceCallRecord` dataclass — 11 required fields; `to_json_line()` serializes to one JSON line per call
- `smart_telescope/services/service_call_logger.py` (new): `ServiceCallLogger` + `_CallContext` context manager; status priority: `_explicit_error` → failed; `_cancelled` → cancelled; `exc_val` → failed; else → ok; `set_error()` for caught exceptions that exit early; `set_response()` for success; emits JSON line to section logger on `__exit__`
- `smart_telescope/api/autogain.py`: `_worker()` now wraps `AutoGainService.run_one_shot()` in `rt.service_call_logger.call("auto_gain", ...)` context manager; `set_error()` on caught exception, `set_response()` on success
- `smart_telescope/workflow/stages.py`: `StageContext` dataclass gains `service_call_logger: "ServiceCallLogger | None" = None`; `stage_align()`, `stage_recenter()`, `stage_autofocus()` each wrap their primary service call when logger is present
- `smart_telescope/workflow/runner.py`: `VerticalSliceRunner.__init__()` gains `service_call_logger=None` kwarg; stored and passed to `StageContext`
- `smart_telescope/api/session.py`: `session_run()` passes `service_call_logger=deps.get_service_call_logger()` to runner
- `smart_telescope/runtime.py` + `api/deps.py`: `ServiceCallLogger` constructed in `__init__` and `reset_for_tests()`; `get_service_call_logger()` injector
- Tests: 15 unit tests in `tests/unit/services/test_service_call_logger.py`; suite: 3484 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-014 (12 per-section log namespaces; REQ-LOG-001)

**Per-section log namespaces with session ID correlation.**
- `smart_telescope/services/section_logger.py` (new): `SectionLogger(session_id, log_dir)` — 12 named sections (startup, stage1_time_location, mount, camera, auto_gain, autofocus, collimation, plate_solve, goto, click_to_center, extended_setup_check, github_delivery); each section gets its own `Logger` under `smart_telescope.section.<name>` with `propagate=True`; optional `FileHandler` per section to `{log_dir}/{session_id[:8]}/{section}.log`; `_SectionAdapter` injects `session_id` and `section` into every log record; `get(section)` returns adapter, `get_paths()` returns `{section: path_or_None}`, `close()` removes file handlers
- `smart_telescope/api/logs.py` (new): `GET /api/logs` returns `{"logs": {section: path_or_null}}` for all 12 sections; depends on `SectionLogger` via `deps.get_section_logger()`
- `smart_telescope/config.py`: `LOG_DIR` from `[session].log_dir` (default `~/.SmartTScope/logs/`; env-var `LOG_DIR`)
- `templates/config.toml`: added `log_dir = ""` to `[session]` section
- `smart_telescope/runtime.py`: `self.section_logger = SectionLogger(session_id=self._app_session_id, log_dir=config.LOG_DIR)` in `__init__`; `SectionLogger(session_id=self._app_session_id)` (no log_dir) in `reset_for_tests()`; `self.section_logger.close()` in `shutdown()`
- `smart_telescope/api/deps.py`: added `get_section_logger() -> SectionLogger`
- `smart_telescope/app.py`: registered `logs_router`
- Tests: 14 `test_section_logger.py` (section names, paths, adapters, file creation, close) + 5 `test_logs.py`; suite: 3489 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-012 + M8-013 (Command history API + GoTo wiring; REQ-API-003, REQ-GOTO-001..003, INC-005)

**M8-012: `GET /api/commands` + UI panel**
- `smart_telescope/api/commands.py` (new): returns `CommandHistoryService.get_all()` as `{"commands": [...]}`
- `smart_telescope/app.py`: registered `commands_router`
- `smart_telescope/static/index.html`: "Command History" card at bottom of Stage 1 (last 50 cmds, scrollable, color-coded)
- `smart_telescope/static/js/setup.js`: `refreshCommandHistory()` + `_renderCommandHistory()` with status color map
- `smart_telescope/static/js/app.js`: initial call + 10 s interval

**M8-013: GoTo history recording + operation policy**
- `smart_telescope/api/mount.py`: `mount_goto` wires `CommandHistoryService` — REQUESTED → REJECTED (gate/solar/limit)/ISSUED → SUCCEEDED/FAILED; adds `?bright_star=true` param → `bright_star_goto` gate operation
- `smart_telescope/services/operation_gate.py`: `_evaluate_one` for `goto` op honors `allow_direct_radec_without_trust` flag; `gate_inputs_from_device_state()` reads config and includes the flag
- `smart_telescope/config.py`: `ALLOW_DIRECT_RADEC_GOTO_WITHOUT_RASPBERRY_TIME_TRUST = False` (env + TOML `[operation_policy]`)
- `templates/config.toml`: added `[operation_policy]` section with stub
- Tests: 6 `test_commands.py` + 5 `test_mount.py::TestGotoCommandHistory` + 4 `test_operation_gate.py::TestDirectRadecGotoPolicy`; 3470 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-011 (CommandHistoryService; REQ-CMD-001)

**Per-session JSONL command audit log.**
- `smart_telescope/domain/command_status.py` (new): `CommandStatus` enum — REQUESTED / REJECTED / ISSUED / RUNNING / SUCCEEDED / FAILED / CANCELLED
- `smart_telescope/services/command_history.py` (new): `CommandRecord` dataclass (12 REQ-CMD-001 fields) + `CommandHistoryService`; thread-safe `threading.Lock`; append-only JSONL (one line per `record()`/`update()` call); in-memory `dict[command_id, CommandRecord]` for query
- `smart_telescope/config.py`: `COMMAND_HISTORY_DIR` (default `~/.SmartTScope/commands/`; env-var + TOML `[session].command_history_dir`)
- `templates/config.toml`: added `command_history_dir = ""` stub to `[session]`
- `smart_telescope/runtime.py`: generates `_app_session_id` UUID per `RuntimeContext.__init__`; creates `self.command_history = CommandHistoryService(session_id, path)`; `reset_for_tests()` creates a no-file instance
- `smart_telescope/api/deps.py`: `get_command_history_service()`
- 19 new tests in `tests/unit/services/test_command_history.py`: record lifecycle, update, get_all, JSONL content, thread safety; 3435 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-010 (Stage 1 time/location UI panel; REQ-TIME-005, REQ-API-004, INC-009)

**New `GET /api/stage1/time-location` endpoint and Stage 1 UI card.**
- `smart_telescope/api/stage1.py` (new): returns 20-field consolidated time/location trust state; reads exclusively from DeviceStateService cache (no serial I/O)
- `smart_telescope/services/device_state.py`: 3 new fields (`_last_sync_status`, `_last_verification_at`, `_last_push_at`) + 5 accessors; `set_time_location_status(VERIFIED)` now records wall-clock `_last_verification_at`
- `smart_telescope/adapters/onstep/mount.py`: `get_sync_status()` extended with `onstep_time_local` and `master_time_local` ISO strings
- `smart_telescope/api/session.py`: caches `mount.get_sync_status()` result into `device_state.set_last_sync_status()` on connect
- `smart_telescope/api/mount.py`: `sync_clock` calls `device_state.set_last_push_at()` on success; new `POST /api/mount/confirm_time` sets USER_CONFIRMED trust
- `smart_telescope/app.py`: registered `stage1_router`
- `smart_telescope/static/index.html`: Stage 1 "Time / Location Verification" card (dot, badge, 20 param rows, 3 action buttons)
- `smart_telescope/static/js/setup.js`: `refreshStage1TL()`, `_renderStage1TL()`, `stage1PushClock()`, `stage1ConfirmTime()`
- `smart_telescope/static/js/app.js`: initial call + 15 s interval for `refreshStage1TL()`
- 25 new tests: `tests/unit/api/test_stage1.py` (19), `test_mount.py::TestMountConfirmTime` (2), `test_raspberry_time_trust.py` M8-010 block (4); 3416 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-009 (Trust session expiry; no cross-restart persistence)

**DEC-004, DEC-005 implemented.**
- `config.py`: `SESSION_TRUST_EXPIRY_MINUTES` read from `[time_location]` section (env override: `SESSION_TRUST_EXPIRY_MINUTES`); default 120
- `runtime.py`: added `from . import config`; both `__init__` and `reset_for_tests()` pass `session_trust_expiry_minutes=config.SESSION_TRUST_EXPIRY_MINUTES` to `RaspberryTimeTrustService`
- `templates/config.toml`: activated `[time_location]` section with `session_trust_expiry_minutes = 120` and `persist_trust_across_restart = false`
- 5 new M8-009 tests in `tests/unit/services/test_raspberry_time_trust.py`: fresh-service-no-trust, restart-clears-trust, custom-expiry-respected, 120-min-default, USER_CONFIRMED-expiry; 3391 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-008 (Meter-based location tolerance; UTF-8-safe logs)

**REQ-TIME-003, REQ-TIME-006 implemented. Addresses INC-002; TEST-002.**
- `adapters/onstep/safety.py`: added `onstep_time_tolerance_s: float = 10.0` and `onstep_location_tolerance_m: float = 100.0` fields to `OnStepSafetyConfig`
- `adapters/onstep/mount.py`: added `_haversine_m()` great-circle distance helper; `get_sync_status()` now uses `haversine_m` for `location_delta_m`, checks `location_delta_m <= onstep_location_tolerance_m` (replaces `lat_delta < 0.1 and lon_delta < 0.1`); uses `onstep_time_tolerance_s` for time check; adds `location_delta_m`, `location_tolerance_m`, `time_tolerance_s` to returned dict
- `api/session.py`: VERIFIED log uses `deg` not `°`; active tolerances logged in both VERIFIED and mismatch paths
- `services/readiness.py`: location issue string shows `{loc_m:.0f}m`; fallback uses `{max(lat_d,lon_d):.4f}deg`
- `config.py`: `ONSTEP_TIME_TOLERANCE_S` and `ONSTEP_LOCATION_TOLERANCE_M` read from `[mount]` section (env override supported); wired into `build_onstep_safety_config()`
- `templates/config.toml`: `[mount]` section with `onstep_time_tolerance_s = 10` and `onstep_location_tolerance_m = 100`
- 26 new tests in `tests/unit/adapters/onstep/test_get_sync_status.py`; 3386 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-007 (Raspberry Pi time trust sources: 5-state enum + evaluation service)

**REQ-TIME-002, REQ-TIME-004 implemented. Addresses INC-003, INC-009.**
- `domain/raspberry_time_trust.py`: `RaspberryTimeTrustSource` enum (GPSD_FIX | NTP | ONSTEP_COMPARISON | USER_CONFIRMED | NOT_TRUSTED) + module-level `is_trusted()` helper
- `services/raspberry_time_trust.py`: `RaspberryTimeTrustService` — priority chain GPSD_FIX > NTP > ONSTEP_COMPARISON > USER_CONFIRMED > NOT_TRUSTED; session expiry via monotonic timestamps; `_check_gpsd_fix()` + `_check_ntp_sync()` (silent fallback on non-Linux); DEC-006 trust chain documented in module docstring
- `services/device_state.py`: added `set_onstep_comparison_established()`, `get_onstep_comparison_established_at()`, `get_user_time_confirmed_at()` methods
- `services/operation_gate.py`: M8-007 path in `gate_inputs_from_device_state()`; isinstance guards prevent MagicMock leaking as float timestamps; M8-006 fallback when `raspberry_trust_svc=None`; gate check order: `TIME_LOCATION_UNVERIFIED` before `RASPBERRY_TIME_UNTRUSTED`
- `api/health.py`: `MountStateCategories` gains `raspberry_trust_source` field; `system_status` injects `RaspberryTimeTrustService`
- `api/mount.py`: 4 gated endpoints (`track`, `goto`, `sync`, `goto_and_center`) pass `raspberry_trust_svc`; `mount_sync_clock()` calls `device_state.set_onstep_comparison_established()` when master source is GPS_FIX or NTP
- `api/deps.py` + `runtime.py`: `get_raspberry_trust_service()` dep; `RuntimeContext.raspberry_trust_svc` singleton (reset in tests)
- 35 new tests in `tests/unit/services/test_raspberry_time_trust.py`; 3360 passed, 24 skipped

---

## 2026-06-26 — DEVELOP — M8-006 (Master time source selection: GPS > NTP > USER_CONFIRMED > FALLBACK)

**REQ-TIME-001 implemented.**
- `domain/master_time_source.py`: `MasterTimeSource` enum (GPS_FIX | NTP | USER_CONFIRMED | FALLBACK)
- `services/master_source.py`: `MasterSourceService.evaluate()` — priority chain; `_check_ntp_sync()` via `timedatectl` (silent fallback on non-Linux); FALLBACK = NOT_TRUSTED → mount automation blocked
- `services/device_state.py`: `is_user_time_confirmed()` / `set_user_time_confirmed()` flag for USER_CONFIRMED trust path
- `services/operation_gate.py`: `gate_inputs_from_device_state()` accepts optional `master_source_svc`; adds `master_time_source` to returned dict; `_evaluate_one()`, `evaluate_gate()`, `evaluate_all_gates()` accept `**_` to forward-compat extra inputs
- `api/health.py`: `MountStateCategories` gains `master_time_source` field; `system_status` injects `MasterSourceService`
- `api/mount.py` + `api/deps.py` + `runtime.py`: `MasterSourceService` wired as singleton; 4 gated endpoints pass it to `_gate_check()`
- 23 new tests; 3368 passed, 39 skipped

---

## 2026-06-26 — DEVELOP — M8-005 (Structured gate diagnostics for disabled UI controls and 409 responses)

**REQ-UI-001, REQ-GOTO-001 implemented; INC-003, INC-005 resolved.**
- `operation_gate.py`: added `gate_inputs_from_device_state()` and `evaluate_gate()` helpers
- `api/health.py`: `_build_mount_state_categories()` uses `gate_inputs_from_device_state()`; `raspberry_trust` stub changed to `TRUSTED` (M8-007 will do real trust determination)
- `api/mount.py`: replaced 4 ad-hoc TL checks with `_gate_check()` → structured HTTPException 409 (fields: `gate_blocked`, `reason_code`, `human_message`, `required_user_action`, `blocking_states`)
- `api/session.py`: `_session_thread` catches all exceptions (prevents pytest 9 `PytestUnhandledThreadExceptionWarning`)
- Frontend: `_applyGateStates()` in `app.js` disables GoTo/track/manual-move/autofocus buttons with gate `human_message` as tooltip; `setup.js` stores gate states from `/api/status`; `mount.js` shows `human_message` from gate-blocked 409s
- 11 new tests in `TestMountApiGatedResponses`; 3345 passed, 39 skipped

---

## 2026-06-26 — DEVELOP — M8-004 (Fix /api/mount/status connection fields)

**REQ-CONN-001 / REQ-CONN-002 implemented.** Added 6 new fields to `MountStatus` in `/api/mount/status`: `adapter_open` (is_started()), `health_check_ok` (None/True/False), `connected` (adapter_open AND health_ok), `park_state` (PARKED|UNPARKED|UNKNOWN), `tracking_state` (TRACKING|NOT_TRACKING|UNKNOWN), `last_error`. Made `POST /api/session/connect` idempotent: skips mount.connect() when DeviceStateService.is_started() is True, returning status="ok" without calling into managed.py again (avoids SYNC-OVERRIDE False-return contradiction). 22 new unit tests.

---

## 2026-06-26 — DEVELOP — M8-003 (OperationGateService — 13 gated operations)

**REQ-STATE-003 implemented.** `evaluate_all_gates()` in `smart_telescope/services/operation_gate.py` evaluates all 13 gated operations from the current system state strings. Gate result includes `allowed`, `reason_code`, `human_message`, `required_user_action`, `blocking_states`. `operation_gate_states` field in `/api/status → mount_states` now returns the full gate map (was stub `{}`). Priority ordering: ADAPTER_DISCONNECTED > ADAPTER_HEALTH_FAILED > ADAPTER_HEALTH_UNKNOWN > TIME_LOCATION_UNVERIFIED > RASPBERRY_TIME_UNTRUSTED > MOUNT_PARKED. Camera-only operations (camera_capture, plate_solve, collimation_preview) always allowed per DEC-009. 59 new unit tests in `tests/unit/services/test_operation_gate.py`, 106 total passing.

---

## 2026-06-26 — DEVELOP — M8-002 (MountReadinessState enum + derive function)

**REQ-STATE-002 implemented.** `mount_readiness` derived composite state added to `/api/status → mount_states`.

**New file:** `smart_telescope/domain/mount_readiness.py`
- `MountReadinessState` enum (7 values)
- `derive_mount_readiness(adapter_connection, adapter_health, onstep_time_location, raspberry_time_trust) → MountReadinessState` — pure function, priority chain top-to-bottom

**Priority chain:** DISCONNECTED > ERROR > CONNECTED_HEALTH_UNKNOWN > CONNECTED_RESTRICTED (Stage 1 not run) > CONNECTED_TIME_LOCATION_UNVERIFIED > CONNECTED_RASPBERRY_TIME_UNTRUSTED > CONNECTED_READY

**INC-001 fix:** adapter open but Stage 1 not run → CONNECTED_RESTRICTED, not DISCONNECTED. Reconnect guidance only for DISCONNECTED/ERROR.

**Tests:** 9 domain tests (`test_mount_readiness.py`) + 6 API tests; exit 0 full suite.

---

## 2026-06-26 — DEVELOP — M8-001 (6 mount state categories in /api/status)

**REQ-STATE-001 implemented.** `/api/status` now exposes `mount_states` with all six separate state categories required by INC-001.

**Code changes:**
- `smart_telescope/services/device_state.py` — added `is_started() -> bool` (polling thread alive check)
- `smart_telescope/api/health.py` — added `MountStateCategories` Pydantic model; `_build_mount_state_categories(device_state)` helper; `device_state` dependency on `GET /api/status`

**New fields in `/api/status` → `mount_states`:**
- `adapter_connection_state`: OPEN (polling started) | CLOSED
- `adapter_health_state`: OK (no poll error) | FAILED (poll error) | UNKNOWN (no poll yet)
- `mount_operational_state`: mirrors `MountState` enum name
- `onstep_time_location_state`: from `DeviceStateService.get_time_location_status()`
- `raspberry_time_trust_state`: NOT_TRUSTED (stub; full impl M8-007)
- `operation_gate_states`: {} (stub; full impl M8-003)

**Tests:** 13 new tests in `TestMountStateCategories`; 3194 passed total.

---

## 2026-06-25 — INGEST — smarttscope_incident_requirements_final_v1_2.md v1.2

**Source:** `E:\Bilder\Astro\SmartTScopeReq\smarttscope_incident_requirements_final_v1_2.md`  
**Copied to:** `resources/hlrequirements/smarttscope_incident_requirements_final_v1_2.md`

**New milestone M8 added to `docs/todo.md`** (30 tasks, M8-001..M8-030):

- M8-001..005 (P1): Split runtime state into 6 categories; mount readiness enum (7 states); `OperationGateService` (13 gated ops); fix `/api/mount/status`; UI disabled-control reasons
- M8-006..010 (P1): Master source selection; 5 Raspberry time trust sources; meter-based location tolerance (100 m); UTF-8-safe logs; trust session expiry; Stage 1 UI panel (20 fields)
- M8-011..013 (P1): `CommandHistoryService` (JSONL, 7 statuses); `/api/commands`; GoTo gate-before-issue; bright-star preconditions
- M8-014..018 (P2): 12 per-section log namespaces; service-call logs per iteration; user-action log (18 actions); FITS diagnostic storage; FITS filename/header spec
- M8-019..023 (P2): Extended Setup Check per-camera report; plate-solve readiness pre-check; ASTAP logging; auto-gain 6 purpose modes; exposure capability test
- M8-024..028 (P2): Collimation modes (Bahtinov + Defocus Donut); click-to-center in 3 views; click refinement; calibration hard block + wizard; iterative bounded centering
- M8-029..030 (P3): `scripts/delivery_audit.py`; delivery log JSONL

**Key design decisions from grilling session:**
- Push Pi time → OnStep verified → ONSTEP_COMPARISON is intentional trust chain (clarify in code comment per DEC-006)
- REQ-AG-002 tracking quality = star elongation/FWHM from captured frames only (no plate-solve dependency)
- Click-to-center cold start = hard block + calibration wizard; no manual override
- REQ-GIT items tracked in todo.md as Priority 7

**Updated wiki pages:**
- `wiki/index.md` — new Planning entry for incident requirements v1.2

---

## 2026-06-24 — INGEST — smarttscope_additional_requirements.md v1.0

**Source:** `E:\Bilder\Astro\SmartTScopeReq\smarttscope_additional_requirements.md`

**New milestone M7 added to `docs/todo.md`** (12 tasks, M7-001..M7-012):

- M7-001/M7-002 (P0): Replace silent `ensure_time_location_synced()` auto-sync with interactive startup dialog; add `TimeLocationStatus {UNKNOWN, VERIFIED, UNVERIFIED}` as orthogonal flag in `DeviceStateService`; gate tracking/GoTo/sync on verification state
- M7-003 (P1): Lazy pixel-to-RA/DEC calibration service — controlled star displacement measurements; blocked-with-retry on failure; invalidated on optical train/binning/orientation change
- M7-004 (P1): Focuser backlash compensation — new `[focuser] backlash_steps` config key; direction-reversal overshoot in `move_relative()`
- M7-005 (P1): Common `ServiceFrame` input dataclass unifying frame metadata across all image-processing services
- M7-006 (P1): Stateful `PlateSolveService` wrapping existing `AstapSolver`; enforces auto-gain precondition before solve
- M7-007 (P1): Formalize `AutofocusService` after gap check against AF-001..AF-005
- M7-008 (P1): Add `circle_center_displacement_px` (raw pixel float) to collimation output; display in UI alongside arrow
- M7-009..M7-012 (P2): Shared image-analysis module audit; AG-003 tracking-off exposure cap; GPS fix age check; retry-limit verification

**Key design decisions recorded:**
- TimeLocationStatus is orthogonal to MountState (not merged)
- Bahtinov collimation method deferred post-MVP
- ASTAP solver wrapped, not replaced
- Collimation displacement in raw pixels

---

## 2026-06-24 — DEVELOP — M7-011 and M7-012 (GPS fix age; retry limits)

**M7-011:** `GpsdFix.fix_age_s` (computed from `gps_time` vs `datetime.now(UTC)`) + `is_fresh(max_age_minutes=60)` method; stale fix logs WARNING with suggestion to fall back to system/config; `GpsdStatusResponse` exposes `fix_age_s` and `is_fresh`; 6 new tests (18 total in suite).

**M7-012:** Gap: `PlateSolveService` had no retry cap. Added `max_retries: int = 5` parameter; `solve()` raises `PlateSolveError("retry limit reached …")` once `_retry_count >= max_retries`; `reset()` clears counter. `AutoGainService` (12 default), `AutofocusService` (20 samples), and collimation sub-services (`_max_iter`, `_max_steps`, `_max_frames`) were already bounded. Verified by 9-test audit file `test_retry_limits.py` + 2 new plate-solve tests.

---

## 2026-06-24 — DEVELOP — M7-003 through M7-010 (Formal Service Contracts & Safety Extension)

**M7-003:** `PixelCalibrationService` — lazy pixel-to-RA/DEC calibration via controlled star displacement (2 s exposures, 2 000 ms RA/DEC moves); stores `PixelCalibration` dataclass; 6 tests.

**M7-004:** Focuser backlash compensation — `FOCUSER_BACKLASH_STEPS` / `FOCUSER_BACKLASH_ENABLED` config; direction-reversal overshoot in `OnStepFocuser.move_absolute()`; 4 tests.

**M7-005:** `ServiceFrame` — common frozen dataclass unifying all image-processing service inputs; `validate()` raises `FrameValidationError` on missing mandatory fields; `from_fits_frame()` factory; 5 tests.

**M7-006:** `PlateSolveService` — stateful wrapper around `AstapSolver`; enforces auto-gain precondition (PS-001); exposes `SolveOutput` with focal-length and pixel-scale back-calculation; 6 tests.

**M7-007:** `AutofocusService` — frame-by-frame V-curve sampler; detects minimum when HFD rises on both sides; returns signed `focus_movement_steps` + pixel-space centroid offset (not RA/DEC); 6 tests.

**M7-008:** Collimation `circle_center_displacement_px` — alias for `error_magnitude_px` (Euclidean inner/outer center distance in pixels) added to `DonutOverlay`, assistant history, live output, and replay endpoint; 2 new tests (27 total in suite).

**M7-009:** `smart_telescope/services/image_analysis.py` — unified `analyze_frame()` returning `ImageAnalysisResult`; classifies uniform/no-signal frames as `FocusQualityLevel.UNKNOWN` via peak-vs-background check; 6 tests.

**M7-010:** AG-003 tracking-off exposure cap — added `tracking_on: bool = True` to `AutoGainService.run_one_shot()`; caps `exp_max_ms = min(exp_max_ms, 1000.0)` when False; API worker reads `MountState.TRACKING` and wires flag; 2 tests.

---

## 2026-06-24 — FIX — Pixel scale wrong for C8 + ATR585M; ASTAP failure logging (4 files)

**Root cause:** Pixel scale defaults assumed a different camera (~3.75 µm pixels) rather than ATR585M (2.9 µm). ASTAP only searches ±10% of the given scale, so 0.38 "/px ± 10% never covers the actual 0.295 "/px → `PLATESOLVED=F` on every solve attempt.

**Correct pixel scales for ATR585M (2.9 µm) on C8:**
- Native (2032 mm): 206.265 × 2.9 / 2032 = **0.295 "/px**
- 0.63× reducer (1280 mm): **0.468 "/px**
- 2× Barlow (4064 mm): **0.147 "/px**

**Changes:**
- `smart_telescope/workflow/_types.py`: C8_NATIVE 0.38 → 0.295, C8_REDUCER 0.60 → 0.468, C8_BARLOW2X 0.19 → 0.147
- `smart_telescope/config.py`: default `pixel_scale_arcsec` 0.38 → 0.295
- `smart_telescope/adapters/astap/solver.py`: log scale + radius before each solve; on PLATESOLVED=F log full ASTAP stdout, stderr, and .ini content for diagnosis
- `tests/unit/workflow/test_runner_stages.py`: updated pixel scale expectations to match corrected values

**Tests:** 3052/3053 pass (1 pre-existing skip); 12/12 for the directly affected tests.

---

## 2026-06-23 — FIX — Auto-gain overshoot and plate-solve 422 (4 files)

**Root cause:** ToupTek SDK `get_ExpoAGain()` returns the raw hardware AGC register, which can be stale from a previous session. This value was echoed back to the UI via `camera_info.effective_gain`, overwriting the intended gain in `preview-gain`. `previewSendParams()` then re-applied that stale value to the camera, causing subsequent solve requests to send e.g. gain=7001 which failed the `le=3200` validation with HTTP 422.

**Changes:**
- `smart_telescope/static/js/preview.js`: Removed the code that writes `camera_info.effective_gain` back into the `preview-gain` UI field. Hardware readback is unreliable for gain on ToupTek cameras; the intended gain is already set in the field.
- `smart_telescope/static/js/session.js`: Clamp gain to [100, 3200] before sending to `/api/solver/solve` as a safety net.
- `smart_telescope/domain/autogain_service.py`: Added sparse star field early exit: if `p99_9 ≥ 0.10` and no saturation risk, accept the frame rather than over-brightening until mean_frac reaches the target band. Prevents overshooting to 4 s/high gain when stars are already visible.
- `smart_telescope/domain/autogain.py`: Same sparse field guard in `AutoGainController.update()` used by the preview WebSocket autogain.

**Tests:** 99/99 pass.

---

## 2026-06-23 — FIX — Auto-sync OnStep time/location on Connect All and GPS apply (4 files)

**Changes:**
- `smart_telescope/api/session.py`: `session_connect()` now calls `mount.ensure_time_location_synced()` automatically after a successful mount connect. Failure is best-effort (logged, does not fail the Connect All response).
- `smart_telescope/adapters/onstep/mount.py`: `ensure_time_location_synced()` now reads `config.OBSERVER_LAT/LON` at call time (local import, same pattern as `_default_safety_config()`) instead of the stale `_safety_config` built at adapter-construction time. This ensures GPS-updated coordinates flow to OnStep without reconnecting.
- `smart_telescope/static/js/setup.js`: `applyGpsLocation()` now calls `POST /api/mount/sync_clock` after the observer location update (best-effort) so the GPS fix is immediately pushed into OnStep.
- `tests/unit/api/test_session.py`: 4 new tests — auto-sync on success, skipped on mount failure, sync exception doesn't fail connect, skip-when-exception variation.

**Root cause:** `session_connect()` connected the mount but never synced time/location, requiring a manual GoTo or button press to initialize the OnStep clock. The stale `_safety_config` also meant GPS updates weren't reaching OnStep.

---

## 2026-06-23 — FIX — Sync Clock button and API for onstep_clock_invalid (4 files)

**Changes:**
- `smart_telescope/api/mount.py`: `POST /api/mount/sync_clock` — pushes Pi time + configured lat/lon into OnStep (same as the auto-sync before every GoTo); clears `onstep_clock_invalid` safety lock on success. HTTP 500 with detail string on failure.
- `smart_telescope/static/js/mount.js`: Replaced dead "Click **Sync Clock** in the Setup panel" instruction with an actual inline `Sync Clock & Location` button that calls the new endpoint, shows "✓ Synced" / "✗ Failed", and refreshes the mount card.
- `smart_telescope/services/readiness.py`: Fixed misleading repair hint on `time_location_sync` RED item — Connect All does NOT trigger a time sync; updated to "Click 'Sync Clock & Location' in the mount card, or run a GoTo."
- `tests/unit/api/test_mount.py`: 3 new tests in `TestMountSyncClock` (200+ok, calls ensure_time_location_synced, 500 on RuntimeError).

**Root cause:** `onstep_clock_invalid` safety lock had no user-facing action. UI referenced a "Sync Clock" button that was never implemented. The auto-sync only fires inside `safe_goto()` and `track_sequence()` — not after Connect All — leaving users unable to clear an uninitialized OnStep RTC without issuing a GoTo first.

---

## 2026-06-23 — FIX — Pi config: removed duplicate [collimation.archive] section (Pi-side only)

**Change:** Duplicate `[collimation.archive]` table in `~/.SmartTScope/config.toml` on the Pi removed manually. The TOML parse error (line 246) caused the entire config to fail, falling back to `lat=0.0, lon=0.0`, which in turn caused the "Mount time/location" readiness item to show RED after Connect All. Removing the duplicate restores correct config parsing.

**Root cause:** The `[collimation.archive]` section was present twice — once inline under `[collimation]` and once as a standalone table added during an earlier config edit. TOML forbids duplicate table headers.

**Status:** Closed. No code change needed; config template (`templates/config.toml`) was already correct.

---

## 2026-06-23 — DOC — Operational acceptance checklist: UI naming and pre/post-connect steps (1 file)

**Changes:**
- `docs/operational-acceptance-checklist.md`: Split old §2 "Connect all devices" into three sections — new §2 (pre-connect System Readiness baseline), §3 (Connect All), §4 (post-connect System Readiness with time/location row). Fixed terminology: "System Readiness card" in Stage 1 (Startup tab) is always visible, not something to "open". Documented that the "Mount time/location" row is absent before connecting and explains GREEN/YELLOW/RED meanings. Renumbered §4–§10 → §5–§11.

**Motivation:** Hardware test R5-012 revealed the checklist used "open System Readiness Card" (implying a modal) and gave no pre/post-connect expectations for the time/location row.

---

## 2026-06-21 — CHORE — Coverage gate resolved at 80.01% (11 files)

**Changes:**
- `pyproject.toml`: Added `[tool.coverage.run] omit` for hardware-only files: `__main__.py`, `tools/*`, `adapters/touptek/managed.py`, `filter_wheel.py`, `camera.py` (all require ToupTek SDK DLL at runtime).
- New test files: `test_event_log.py`, `test_guide_monitor_api.py`, `test_gpsd_service.py`, `test_firmware_proof.py`, `test_serial_bus.py`, `test_mock_camera.py`, `test_onstep_focuser.py`.
- Extended: `test_visibility.py` (HorizonProfile, load_horizon, compute_ha), `test_guide_monitor.py` (lifecycle: start/stop/running/last_result/exception path), `test_cooling_service.py` (exception paths: TEC setup failure, disable failure, sensor exceptions).

**Result:** 80.01% coverage, 3103 passed, 24 skipped. Coverage gate (`--cov-fail-under=80`) now green.

---

## 2026-06-21 — FEAT — R5-012: Mount time/location sync in readiness card (4 files)

**Changes:**
- `smart_telescope/ports/mount.py`: `get_sync_status() -> dict | None` added as default no-op.
- `smart_telescope/adapters/onstep/mount.py`: `OnStepMount.get_sync_status()` implemented — calls `read_onstep_clock()` (`:GC#`/`:GL#`) and `read_onstep_site()` (`:Gt#`/`:Gg#`), compares OnStep values against Pi system time and `_safety_config.observer_lat/lon`; location threshold 0.1°.
- `smart_telescope/services/readiness.py`: `_check_time_location_sync()` added — returns `time_location_sync` `ReadinessItem` (GREEN/YELLOW/RED); skipped (returns `None`) when mount is not connected or adapter doesn't support sync status; wired into `check()` after mount/focuser check.
- `tests/unit/api/test_readiness.py`: 8 new tests in `TestTimeLLocationSyncCheck` covering all level transitions and None cases.

**Logic:** GREEN = both time and location within thresholds. YELLOW = mount not responding to queries. RED = clock off by > threshold_s OR site off by > 0.1°. Repair hint reminds user that GoTo auto-syncs before every slew.

---

## 2026-06-21 — CHORE — ONS3 upgrade complete; 4 pre-existing test failures fixed (5 files)

**Changes:**
- `smart_telescope/domain/collimation/config.py`: `ArchiveConfig.enabled` default corrected from `True` to `False` — matches `templates/config.toml` template; was causing `_get_archive()` to create an archive in test environments.
- `tests/unit/api/test_catalog.py`: patch `compute_ha` to `0.0` in `_get_stars()` helper — prevents time-dependent HA limit filtering from removing test stars.
- `tests/unit/api/test_mount.py` (`TestMountPark`): add `json={"confirmed": True}` to all park POST calls — endpoint added confirmation guard after these tests were written.
- `tests/unit/services/test_star_selector.py`: patch `compute_ha` alongside `compute_altaz` in every test that checks star selection — same time-dependent HA issue as catalog test.
- `tests/unit/domain/test_stretch.py`: `test_linear_range_maps_correctly` — removed `flat[-1] == 255` assertion; sigma-stretch does not guarantee max value maps to 255 (only percentile-stretch does).
- `docs/todo.md`: ONS3-002..006 marked complete.

**ONS3 architecture note:** `onstep_adapter` v0.3.0 is a re-export shim — its `__init__.py` imports everything from `smart_telescope.adapters.onstep.*`. All REQ-ST-001..007 overrides in `mount.py` are therefore permanent (no upstream independent implementation exists).

**Test result:** 2942 passed, 24 skipped.

---

## 2026-06-21 — FIX — Tracking not active after goto; solve failure visibility (3 files)

**Changes:**
- `smart_telescope/static/js/mount.js`: after `watchSlew()` confirms slew complete, auto-enable tracking via `/api/mount/track` if mount state is not already `tracking`.
- `smart_telescope/services/collimation/assistant.py`: `_handle_acquire_star()` now waits up to 90 s for any in-progress slew to finish, then enables tracking if needed — prevents star trailing in MEASURE_DONUT/FINE_FOCUS/MEASURE_SPIKES.
- `smart_telescope/static/js/session.js`: solve failure/error message now also shown in the `solve-result` div (next to the Solve button), not only in the status banner at the top of the stage.

**Storage locations confirmed (no code change):**
- Session/alignment logs: `~/.SmartTScope/sessions/` (empty if no imaging session completed yet)
- Collimation frame archive: `~/.SmartTScope/frame_archive/<session_id>/` (archiving must be enabled via `[collimation.archive] enabled = true` in config.toml)
- Collimation report and polar alignment state: in-memory only, not persisted
- Plate solve frames and results: not persisted (temp dir deleted after ASTAP runs)

---

## 2026-06-20 — FEAT — GPSD connector, Bathinov preview fix, storage paths (8 files)

**Changes:**

- `smart_telescope/services/gpsd_service.py` (NEW): One-shot TCP client for the GPSD JSON protocol (port 2947). Sends `?WATCH+?POLL`, waits for first `TPV` class response (5 s timeout), returns `GpsdFix(lat, lon, alt, gps_time, mode, hdop)` or `None` when GPSD is unavailable. `haversine_m(lat1, lon1, lat2, lon2)` computes great-circle distance in metres.
- `smart_telescope/api/gpsd.py` (NEW): `GET /api/gpsd/status` queries GPSD and returns fix mode, coordinates, distance from configured observer position. `POST /api/observer/location` updates `config.OBSERVER_LAT`/`OBSERVER_LON` in memory and patches `~/.SmartTScope/config.toml` `[observer]` section via regex replacement (no external dep).
- `smart_telescope/app.py`: Registered `gpsd_router` under `/api`.
- `smart_telescope/api/health.py`: Added `GET /api/status/storage` returning absolute paths for session stacks (`~/.SmartTScope/sessions`) and collimation frame archive (`~/.SmartTScope/frame_archive`).
- `smart_telescope/static/js/preview.js`: `_connectWs(camRoleOverride?)` and `previewStart(camRoleOverride?)` accept optional camera role override so callers can hardcode a role without touching `preview-cam-select`.
- `smart_telescope/static/js/setup.js`: `s4PreviewStart()` now mirrors offset and autogain controls from Stage 4 into the shared preview state and calls `previewStart('main')` — Bathinov preview always uses the main imaging camera. Added `checkGpsStatus()` (called on page load) and `applyGpsLocation()` for GPS location notification + one-click apply.
- `smart_telescope/static/js/app.js`: `checkGpsStatus()` called alongside `initSiteConfig()` on DOMContentLoaded.
- `smart_telescope/static/js/session.js`: `s5LoadStoragePaths()` fetches `/api/status/storage` and shows sessions directory in Stage 5.
- `smart_telescope/static/index.html`: Stage 1 — GPS notification banner (shown when distance > 100 m) + GPS distance row + Apply button in Observer & Time tile. Stage 4 — Offset input and Auto-gain checkbox added to Bathinov preview controls. Stage 5 — Storage path row below Start Session button.

---

## 2026-06-20 — FIX — Field-test bug sprint (11 files, commit ce022fb)

**Bugs fixed**
- Preview stretch now uses asinh so faint stars stay visible at low signal (mean_adu=9)
- Frame archive enabled by default — Save FITS / AF buttons no longer greyed out
- CollimationStarSelector filters by HA limits before altitude; Sirius at HA 8.8h no longer offered
- Polar alignment step 3 falls back to east-side alternate RA when west HA limit is exceeded
- Park API now requires `confirmed:true`; mount card shows browser confirm() dialog before parking
- Auto-gain: `force:true` flag bypasses POSSIBLE_FOCUS_OR_POINTING_ERROR; "Try Anyway" button in UI
- Mount status card shows explicit clock-sync banner when `onstep_clock_invalid` safety lock is active
- Plate solver fix (MissingSectionHeaderError) was already in origin/main — Pi needs git reset --hard
- Collimation camera selector was already wired in HTML/JS (s4-wiz-camera-role) — Pi needs update

---

## 2026-06-18 — FIX + FEATURE — Night sky session: solver, HA filtering, dark-sky stretch, camera select, step-3 preview, Bahtinov zoom

**Bugs fixed**

1. **Solver MissingSectionHeaderError** (`adapters/astap/solver.py`): ASTAP writes `.ini` files without a `[section]` header; `configparser` raised `MissingSectionHeaderError`. Fixed in `_parse_ini()`: read file as text, prepend `[Solution]\n` if the first non-blank line is not a section header, then use `cfg.read_string()`. Unblocks "Save solve FITS" and "AF frames" buttons.

2. **Alignment star list shows stars beyond mount HA limits** (`api/catalog.py`, `domain/visibility.py`): `/api/catalog/stars` returned all visible stars without checking if HA was within `MOUNT_HA_WEST_LIMIT_H` / `MOUNT_HA_EAST_LIMIT_H`. Added `compute_ha()` to `domain/visibility.py` (LST − RA via astropy) and filter stars in `catalog_stars()`. Stars past the meridian limit are excluded.

3. **Collimation "use best star" → meridian limit error**: `loadCollimStars()` (in `mount.js`) fetches `/api/catalog/stars` and `collimUseBestStar()` picks the first item. Same catalog HA filter as #2 prevents inaccessible stars from appearing; the "use best star" now always picks a reachable star.

4. **Preview stretch maps noise to mid-grey** (`domain/stretch.py`, `api/preview.py`): The 0.5–99.5 percentile stretch sets lo/hi from the full signal range, making the sky background appear mid-grey in dark conditions. Replaced with a background-subtracted, MAD-based sigma stretch: background = median, sigma = MAD/0.6745, lo = max(0, bg − 1.5σ), hi = bg + 10σ. Falls back to percentile stretch when sigma < 0.5 (uniform/mock frames). Applied per-channel in `_auto_stretch_color()` for colour cameras.

**Features added**

5. **Collimation camera selection** (`api/collimation.py`, `static/index.html`, `static/js/collimation.js`): Added `StartPayload` with `camera_role: str = "main"` to `POST /api/collimation/start`. The assistant singleton is reset when the requested role differs from the current one. A "Main camera" / "Guide camera" dropdown appears before the Start button; it hides once the wizard is active.

6. **Step-3 alignment live preview** (`static/js/setup.js`): After `watchSlew()` completes in `starGoto()`, `previewStart()` is called automatically so the camera feed is visible without a separate manual click.

7. **Bahtinov zoom** (`static/index.html`, `static/js/preview.js`): After a successful Bahtinov analyze, a "Zoom" toggle button appears. Clicking it shows a 180×180px picture-in-picture canvas (`s4-zoom-canvas`) in the top-right corner of the preview frame, cropped around the crossing point (radius ≈ 10% of the shorter image dimension) and scaled up for fine spike assessment.

---

## 2026-06-17 — FIX — Live Preview offset reset to 0 on Start

**Symptom**: Setting offset to 2000 and pressing Start reset the UI field to 0.

**Root cause**: `preview.py` reads back `eff_offset = camera.get_black_level()` after
`set_black_level(offset)`. The ToupTek SDK's `_try()` helper swallows all exceptions and returns
None, so `get_black_level()` falls through to `return 0` when the SDK call fails or the camera
silently rejects the value. This 0 was sent as `effective_offset` in the `camera_info` WebSocket
message, overwriting the user's field.

**Fix** (`smart_telescope/api/preview.py`): Only accept the readback value when it is non-zero or
zero was explicitly requested. A zero readback after a non-zero set is treated as a silent rejection
and the requested value is kept as `eff_offset`.

---

## 2026-06-17 — FIX — Disable Enable Tracking at HOME; improve pier_side log detail

**Symptoms reported**: Pressing "Enable Tracking" while mount is AT_HOME fails with
`pier_side_axis_inconsistent` (500 error). Log only showed the bare error code with no context.

**Root cause**: `enable_tracking()` has special at-home handling (skips positional checks), but
`_at_mechanical_home` is only set by `unpark_to_home_stop_tracking()`, not by the plain `unpark()`.
After a normal unpark the adapter's `_last_decoded_status` may not carry the `at_home` flag if
OnStep cleared the H flag before the next serial poll, so `at_home` evaluates to False and the code
falls through to `_check_target_safe` → `motion_safety_preflight` → `pier_side_axis_inconsistent`.

**Fix 1** (`smart_telescope/static/js/mount.js`): "Enable Tracking" button is now disabled (with
tooltip "Slew to a target before enabling tracking") when state is `at_home`. Tracking from HOME
serves no astronomical purpose — the user must slew to a target first.

**Fix 2** (`smart_telescope/adapters/onstep/mount.py`, `_check_target_safe`): Added a `WARNING`
log line immediately before the `OnStepSafetyError` raise that includes `pier_side`, `ha_hours`,
and `blockers` from the preflight dict, providing actionable diagnostics in the server log.

---

## 2026-06-17 — FINDING — onstep_adapter v0.3.0 is a re-export shim, not an independent library

`onstep_adapter` v0.3.0 package (`__init__.py` at Python 3.13 site-packages) contains only
`from smart_telescope.adapters.onstep.* import ...` re-exports and two smoke-test tools.
There is no independent implementation — the pip package re-exports SmartTScope's own code.
All REQ-1 and REQ-ST-001..007 methods already "exist" in v0.3.0 because they are in
SmartTScope's adapter layer. The ONS-MIGRATE migration is blocked on creating an independent
codebase in the OnStepAdapter repo (not on individual method additions). Updated `docs/todo.md`.

---

## 2026-06-17 — CORRECTION — REQ-2 removed from upstream requirements

`set_park_position() → bool` and `get_park_position() → MountPosition | None` are NOT
upstream requirements. v0.3.0 already provides `set_park_position_from_current()` and
`get_stored_park_position()`. The two SmartTScope methods are thin `MountPort` ABC
compliance wrappers that stay permanently in the shim. Updated: `docs/todo.md`,
`SYNC.md`, `smart_telescope/adapters/onstep/mount.py` comment.

---

## 2026-06-17 — PLAN — Replace adapter reimplementation with onstep_adapter pip package

Migration plan ONS-MIGRATE-001..013 added to `docs/todo.md` under the OnStepAdapter Migration section.
Goal: reduce `smart_telescope/adapters/onstep/mount.py` (4,408 lines) to a ≤30-line MountPort shim.
Blocked by upstream adoption of REQ-1, REQ-2, and REQ-ST-001..007 in tschoenfelder/OnStepAdapter.
Phase 0 (upstream contributions) must happen first; remaining phases execute after new wheel release.
Wiki index updated to reference the migration plan.

---

## 2026-06-17 — IMPLEMENTATION — OnStepAdapter migration finalized: no direct serial communication outside adapter layer

All serial/LX200 communication is now confined to `smart_telescope/adapters/onstep/` (focuser.py, mount.py).
No `api/` or `services/` code sends any serial commands directly.

Import path cleanup: all references to onstep_adapter types now go through the adapter package
`__init__.py` rather than internal submodules:
- `config.py`: `from .adapters.onstep import OnStepSafetyConfig`
- `runtime.py`: `from .adapters.onstep import OnStepClient`
- `api/mount.py`: `from ..adapters.onstep import OnStepSafetyError` (try/except removed)
- `services/mount_operations.py`: dead `OnStepSafetyError` import removed entirely

When an independent upstream `onstep_adapter` ships, the final rename is a single search-and-replace:
`from .adapters.onstep import X` → `from onstep_adapter import X`.

---

## 2026-06-17 — IMPLEMENTATION — Focuser API migrated to onstep_adapter public API

`FocuserStatus` and `FocuserMoveResult` dataclasses moved to `smart_telescope/ports/focuser.py`
(canonical location); `adapters/onstep/results.py` re-exports them for backward compatibility.
`FocuserPort` ABC extended with two new abstract methods: `status() → FocuserStatus` and
`move_absolute(steps) → FocuserMoveResult`. All concrete implementations updated:
`OnStepFocuser` (already had both), `MockFocuser`, `SimulatorFocuser`.

`smart_telescope/api/focuser.py` now uses the onstep_adapter public API surface:
- `GET /api/focuser/status` calls `focuser.status()` (single combined status call)
- `POST /api/focuser/move` and `/nudge` use `focuser.status()` + `focuser.move_absolute(target)`
- `_safe_move()` captures `result.start_position` from `FocuserMoveResult` (no separate `get_position` before move)

Tests updated: `tests/unit/api/test_focuser.py`, `tests/unit/api/test_smoke.py`.
Full unit suite: 2940 passed (before fix), all passing after.

---

## 2026-06-17 — TASK — OnStepAdapter v0.3.0 upgrade tracked

Added upgrade tasks ONS3-001..006 to `docs/todo.md` under the OnStepAdapter Migration section.
`pyproject.toml` already points to the v0.3.0 wheel (ONS3-001 done). Remaining steps:
install wheel, review REQ-ST-* overrides in `adapters/onstep/mount.py` and `client.py`,
run tests, commit. Wiki index updated to reference v0.3.0 and clarify the override-layer architecture.

---

## 2026-06-16 — FIX — pier_side_axis_inconsistent after disable→re-enable tracking

Two bugs fixed:

**1. Unpark shows TRACKING unexpectedly (regression)**

- `get_state()` was changed in a previous session to check `tracking` before `at_home`
  so that explicit `enable_tracking()` from home would clear the stuck AT_HOME state.
- Side effect: OnStep auto-starts sidereal tracking after `:hR#` (unpark) on some
  firmware versions, setting both H and T flags in `:GU#`. With the new priority
  order, `get_state()` returned TRACKING immediately after unpark instead of AT_HOME.
- Fix: added `_explicit_tracking_started` flag (set by `enable_tracking()`, cleared by
  `disable_tracking_verified()`, `stop()`, `park()`, `unpark()`). Tracking only wins
  over `at_home` when the flag is set. Auto-tracking after unpark falls through to the
  `at_home` branch, so AT_HOME is shown as expected.

**2. pier_side_axis_inconsistent when re-enabling tracking after disable**

- `:Gm#` retains the last GoTo session's pier side across unpark/reboot in OnStep
  firmware. It is not reset when the mount returns to home.
- When home is confirmed (`_home_confirmed=True`) and the mount has not done a GoTo
  (axis2 ≈ 0°), the axis-derived pier side ("east" for CWD) is correct, but `:Gm#`
  may still report "west" from the previous session → `pier_side_axis_inconsistent`.
- Fix: in `motion_safety_preflight()`, when `_home_confirmed` is True and axis2 < 15°,
  treat the derived value as authoritative and skip the inconsistency check.

---

## 2026-06-16 — FIX — State stays AT_HOME after enable_tracking (root cause)

- Previous fix (clear `_at_mechanical_home` in `enable_tracking()`) was undone on the
  very next background poll: `get_state()` saw `at_home=True` still in `:GU#` (OnStep
  keeps the H flag while tracking from home) and re-set `_at_mechanical_home = True`.
- Root cause: `tracking` was checked AFTER `at_home` in `get_state()`.
- Fix: check `decoded["tracking"]` first. If OnStep reports tracking, clear
  `_at_mechanical_home` and return `TRACKING` immediately — `at_home` branch is skipped
  entirely.  The SYNC-OVERRIDE order (at_home before slewing) is preserved for the
  non-tracking case.

---

## 2026-06-16 — FIX — State stays AT_HOME after enable_tracking

- `get_state()` returns `AT_HOME` when `_at_mechanical_home` is True, regardless
  of `:GU#` flags.  After a successful `:Te#`, the flag was never cleared, so the
  mount stayed stuck in AT_HOME even while OnStep reported `tracking=True`.
- `enable_tracking()` now sets `_at_mechanical_home = False` on `:Te#` success.

---

## 2026-06-16 — FIX — Track fails: hour_angle_east after home

- After going home, OnStep's RA readback is stale (last tracked or park position RA).
  `LST − stale_RA` can produce an HA far east of the -5.5h limit, blocking
  `enable_tracking()` with `hour_angle_east` even though the mount is mechanically safe.
- `enable_tracking()` now detects `_at_mechanical_home` flag; if at home it only runs
  `_raise_if_locked` and `_raise_if_not_astronomy_ready` (safety lock + time trust),
  skipping the RA/Dec/HA positional limit checks which are meaningless until the
  first plate-solve sync establishes a valid pointing model.

---

## 2026-06-16 — FIX — Track fails: pier_side_axis_inconsistent after home

- At the CWD home position (axis2 ≈ 0°) `_instrument_to_mount_axes` derives
  pier_side="east", but OnStep's `:Gm#` can report "west" — a meridian-point
  ambiguity inherent to CWD position.
- `pier_side_axis_inconsistent` was added to blockers unconditionally; but
  `pier_side_unavailable` and `hour_angle_unavailable` already use `not terminal_state`
  guard.  Applied the same guard to `pier_side_axis_inconsistent` in
  `motion_safety_preflight()`.  In terminal state (parked or at-home) pier side
  ambiguity is expected and harmless.

---

## 2026-06-16 — FIX — Track fails: firmware_limits_broad

- OnStep defaults to broad firmware limits (horizon ≤ -5°, overhead ≥ 89.5°).
  `allow_broad_onstep_limits` defaulted to `False`, blocking all motion.
- SmartTScope enforces its own tighter limits (min 10°, max 88°) at the API
  layer via `_check_mount_limits()` before any command reaches the hardware,
  so the firmware limit check is redundant.
- Set `allow_broad_onstep_limits=True` in the `OnStepSafetyConfig` created by
  `config.py`.

---

## 2026-06-16 — FIX — Track fails: raspberry_time_plausible_not_trusted

- After a successful time/location sync the `_time_readiness()` check still returned
  `ready=False` because `time_trust_source` remained `"raspberry_plausible"` — not
  in `_TRUSTED_TIME_SOURCES` — so `trusted` was always `False`.
- `sync_onstep_time_location()` now also sets `time_trust_source="user_confirmed"`
  (which is in `_TRUSTED_TIME_SOURCES`) when called with `confirmed_by_user=True`.
  This promotes the trust level so subsequent `_time_readiness()` calls pass.

---

## 2026-06-16 — FIX — Enable Tracking fails: onstep_clock_invalid

- `track_sequence()` in `mount_operations.py` called `enable_tracking()` which calls
  `_check_target_safe()` — same safety gate that blocks GoTo when clock is unsynced.
- Added `mount.ensure_time_location_synced()` at the start of `track_sequence()`.

---

## 2026-06-16 — FIX — GoTo & Plate Solve Goto fails: onstep_clock_invalid

- `goto_and_center()` and plain `/goto` endpoint never synced time/location to OnStep before
  issuing the GoTo command. OnStep's safety system blocked all goto attempts with
  `onstep_clock_invalid` because the adapter's internal clock state was stale.
- Added `ensure_time_location_synced() -> None` to `MountPort` (default no-op).
- Implemented in `OnStepMount`: calls `sync_onstep_time_location()` with configured lat/lon/alt.
- Called before the GoTo loop in `workflow/goto_center.py` (Plate Solve Goto path).
- Called at the start of `services/mount_operations.safe_goto()` (plain GoTo path).
- Test mock `_MockMount` in `test_goto_center.py` updated with no-op `ensure_time_location_synced`.

---

## 2026-06-14 — FIX — CRITICAL: remove auto_set_park; home UI live status

- Removed `auto_set_park` from `park_sequence()` and park API endpoint. Pressing Park from
  AT_HOME was automatically calling `set_park_position()` (`:hS#`), overwriting the user's
  configured EEPROM park position. Park position must only be set by explicit user action.
- `park_sequence()` now always stops any active slew and issues `:hP#` without touching `:hS#`
- `mountHome()` JS: added 1 s `setInterval` status poll while the home API is blocking (up to
  60 s). Strip now shows "home…" with yellow dot pulsing live during home slew — same visual
  as park's rolling status badge

---

## 2026-06-14 — FIX — Unpark shows PARKED: remove auto-disable-tracking from unpark_sequence

`disable_tracking_verified()` sends `:Q#` (quit-move) after unpark. On the Pi's OnStep firmware
this causes GU# to briefly report parked → UI flickers to PARKED immediately after Unpark.
Removed auto-disable-tracking from `unpark_sequence()`. The Disable Tracking button works in
one click (has `poll_now()` after success). Tracking is expected to be on after unpark.

---

## 2026-06-14 — FIX — Home stays SLEWING: tight 0.5 s poll loop in home_sequence

Background poll (2 s) was too coarse — OnStep's 'H' (at_home) GU# flag clears in <1 s when
the mount is already near home, so the background thread always missed it.

Fix: `home_sequence()` now does a tight 0.5 s polling loop (up to 60 s) directly on
`mount.get_state()` after `go_home()`.  `get_state()` SYNC-OVERRIDE detects the 'H' flag
and calls `confirm_home_position()` on first observation, then returns AT_HOME.
The loop breaks immediately on AT_HOME; unexpected states (TRACKING, PARKED) also break early.

---

## 2026-06-14 — FIX — Park fails after Home; adapter version "?" in readiness

- `get_state()` SYNC-OVERRIDE: when GU# 'H' flag is first seen, call `confirm_home_position()`
  (sets `_home_confirmed=True`) so `set_park_position_from_current()` accepts the subsequent call;
  also split `at_home` / `_at_mechanical_home` branches so confirm is only called once
- `set_park_position()` SYNC-OVERRIDE: pass `allow_at_home=True` — our park-from-home
  workflow explicitly sets park position = home position, which the adapter refused by default
- Added `__version__ = "0.3.0"` back to `onstep/__init__.py` (stripped by external sync)
- Readiness: try `importlib.metadata` first, then `onstep.__version__` as fallback

---

## 2026-06-14 — FIX — Unpark tracking / disable_tracking double-click / readiness version

- `unpark_sequence()` now auto-disables tracking after `:hR#` (OnStep auto-starts tracking on unpark)
- `disable_tracking` API endpoint now calls `device_state.poll_now()` after success — state cache
  refreshes immediately so the UI reflects non-tracking without a second button press
- Readiness mount item now shows OnStep adapter version: "Connected (adapter v0.3.0) — state: …"

---

## 2026-06-14 — FIX — Home stuck in SLEWING after :hC# (REQ-3 partial)

Root cause: new adapter's `get_state()` checked `slewing` before `at_home` in priority chain.
During home travel OnStep keeps the goto-active flag set until the 'H' GU# flag appears,
so `get_state()` returned SLEWING indefinitely — the service AT_HOME state machine never fired.

Fix: SYNC-OVERRIDE of `get_state()` in `smart_telescope/adapters/onstep/mount.py` —
`at_home` (or `_at_mechanical_home`) now takes priority over `slewing`.
Service layer sticky-AT_HOME logic in `device_state.py` lines 274-277 now triggers correctly.
REQ-3 filed against upstream to adopt the priority order natively.

---

## 2026-06-14 — UPGRADE — OnStepAdapter v0.2.0 → v0.3.0

Upgraded onstep_adapter to v0.3.0 (branch `codex/release-0.3.0`).

- `get_park_position()` now reads from state store (REQ-2 fulfilled); undocumented `:GpA#`/`:GpD#` serial probe removed by upstream
- `set_park_position()` SYNC-OVERRIDE added: delegates to `set_park_position_from_current(confirmed_safe=True)` — now actually sends `:hQ#` and persists to state store
- `move()` SYNC-OVERRIDE upgraded: `mechanical_manual_move()` at center/slew rate replaces `guide()` delegation (faster, uses `:Me#`/`:Mw#` etc.)
- New public types: `SetParkPositionResult`, `AxisMotionResult`, `StoredParkPosition`, `OnStepMotionCalibration`
- REQ-3/4/5 remain open; 2943 passed, 24 skipped, 0 failed

---

## 2026-06-14 — ARCH — OnStepAdapter migration complete

Replaced hand-rolled `smart_telescope/adapters/onstep/{mount,focuser,serial_bus}.py` with the external `onstep_adapter` package (tschoenfelder/OnStepAdapter v0.2.0). All mount and focuser hardware communication now flows exclusively through `OnStepClient`.

**Files changed:**
- `smart_telescope/adapters/onstep/`: 9 files synced from GitHub source (mount.py, focuser.py, serial_bus.py, client.py, safety.py, results.py, state_store.py, firmware_proof.py, __init__.py)
- `smart_telescope/config.py`: added `build_onstep_safety_config()` factory
- `smart_telescope/runtime.py`: replaced direct adapter construction with `OnStepClient` lifecycle
- `smart_telescope/services/device_state.py`: added `safety_violation` to `MountObservedState`; poll loop reads `mount.safety_lock`
- `smart_telescope/services/mount_operations.py`: `OnStepSafetyError` imported with fallback
- `smart_telescope/api/mount.py`: `safety_violation` field in `MountStatus`; goto returns 409 on safety violation
- `SYNC.md`: OnStepAdapter registered as external module with REQ-1..5 enhancement requests

**SYNC-OVERRIDE active:**
- `mount.py`: `move(direction, move_ms)` added as concrete method delegating to `guide()` — satisfies abstract `MountPort.move()`; proper slew-rate variant tracked as REQ-1

**Enhancement requests raised** (tracked in SYNC.md): REQ-1 move() at slew rate, REQ-2 park position get/set, REQ-3 sticky AT_HOME, REQ-4 hardware watchdog, REQ-5 command audit trail.

---

## 2026-06-13 — FIX — Park: stop active slew before parking

**Problem**: Clicking Park while the mount was slewing (e.g. left slewing from a previous session) returned HTTP 409 "Mount is still slewing", blocking all park attempts.

**Fix**: `park_sequence` now sends `:Q#` (stop) + 300 ms settle when the mount is SLEWING and `auto_set_park=False`. Then `:hP#` is sent to the previously saved park position. The 409 guard is retained only for the rare race where `auto_set_park=True` (home slew still in mid-flight when Park is clicked) — parking mid-home-slew would store the wrong position.

## 2026-06-13 — FIX — Premature HOME display before home slew starts

**Problem**: `record_command("home")` set `_sticky_at_home=True` immediately. If the background poller ran before OnStep raised its 'S' (SLEWING) flag, it saw UNPARKED and promoted it to AT_HOME — so the mount tile showed "Home" before the slew even started. Clicking Park at that moment then failed because the mount was mid-slew.

**Fix**: Replaced the single `_sticky_at_home` flag with a two-phase gate: `_home_cmd_issued` (set on home command) + `_home_slew_seen` (set when SLEWING is polled after the command). UNPARKED is only promoted to AT_HOME after both flags are true — confirming the slew actually happened and ended. Hardware 'H' flag still sets sticky directly. Updated 12 tests in `TestStickyAtHome`; added `test_home_unparked_without_slewing_not_premature`.

## 2026-06-13 — FEAT — Auto set-park position on Home → Park (:hS# before :hP#)

**Problem**: OnStep requires `:hS#` to be called at least once before `:hP#` will be accepted. The "Set Park" button approach (reverted) required a manual extra step.

**Fix**: `park_sequence` receives `auto_set_park: bool` from the API. The API captures whether the device-state cache shows `AT_HOME` before calling `record_command("park")` (which clears the sticky flag). When `auto_set_park=True`, `park_sequence` sends `:hS#` (save park position = current home position) then `:hP#` — all automatically. Subsequent Park clicks (position already in EEPROM) use `auto_set_park=False` and send only `:hP#`. `MountPort.set_park_position()` added as a non-abstract default (`return False`); `OnStepMount` overrides with `:hS#`.

## 2026-06-13 — FEAT — AT_HOME mount state: sticky Home after homing slew

**Problem**: After `POST /api/mount/home`, the mount tile showed "Unparked" instead of "Home". OnStep sets the `'H'` flag in `:GU#` for less than one poll cycle (2 s), so the background poller always missed it, observing only SLEWING then UNPARKED.

**Fix**:
- Added `MountState.AT_HOME` to the enum; `OnStepMount.get_state()` returns it when `'H'` is in the `:GU#` response (belt-and-suspenders path).
- `DeviceStateService` gains `_sticky_at_home` flag set by `record_command("home")` — active before the first poll after the slew. When the poller sees UNPARKED and sticky is set, the cached state is promoted to AT_HOME.
- Sticky clears on `record_command("goto" | "park" | "track")`. SLEWING/TRACKING/PARKED are always shown as-is (not overridden).
- CSS `.state-at_home` (blue badge); JS `_STATE_LABEL` maps "at_home" → "Home"; dot colour = yellow (same as unparked).
- 11 new tests in `TestStickyAtHome`.
- Verified on hardware: "Home" persists after home slew and clears on next GoTo/Park/Track command.

## 2026-06-13 — FEAT — Nudge rate ×2, archive singleton fix, GoTo/Solve/AF archive tagging

**Nudge rate**: `OnStepMount.move()` now sends `:RM#` (move/slew rate) instead of `:RC#` (center rate), approximately doubling RA/Dec nudge speed in the Centre Star guide pad and Stage 4 collimation guide pad.

**Archive activation fix**: `_frame_archive` is now a separate singleton from `_assistant`, created by `_get_archive()` on the first archive API call. Previously, the archive was only created when a collimation session started (`_get_assistant()`), so visiting the archive endpoint before starting a wizard returned "disabled" even with `enabled = true` in config. Archive now activates on app start if `[collimation.archive] enabled = true` is set before launch.

**GoTo/Solve/AF archive tagging**:
- `CollimationFrameArchive.save_tag()` saves metadata-only JSON entries (no FITS) for GoTo, plate-solve, and AF operations. `list_sessions()` and `list_frames()` include these tag entries alongside FITS frames; `_arcFrameRow` shows "tag" label instead of Replay button for JSON-only entries.
- `POST /api/collimation/archive/tag` endpoint accepts `tag_type` + `data`; default session = `s3_YYYY-MM-DD`.
- Stage 3 UI: 📁 buttons added next to GoTo, Solve, and AF buttons. Buttons enable after a successful operation when archive is active. Collapsible "Session Archive" browser added to Stage 3.
- Archive status checked automatically when entering Stage 3 (`_s3CheckArchiveEnabled()`).

## 2026-06-13 — FIX — Park error surfacing and idempotency

**Problem**: `POST /api/mount/park` returned HTTP 500 "Park failed" when `:hP#` returned `b'0'`, with no indication of the mount's pre-park state or why OnStep rejected the command. Debugging required reading server logs.

**Fixes**:
- `park_sequence()` now calls `get_state()` before attempting park; if already PARKED, returns immediately (idempotent). If `:hP#` is rejected, error message includes pre-state name and actionable hint: "verify park position is set (:hS# from home) and mount is aligned".
- `mount_park()` endpoint passes `{exc}` through to HTTP detail instead of generic "Park failed".
- Same pattern applied to `mount_unpark()`, `mount_guide()`, `mount_nudge()` error messages.
- 1 new test: `test_park_sequence_skips_park_when_already_parked`.

**Why park failed**: `:hP#` returns `0` when the park position was not set in OnStep (`:hS#` must be called from the desired park position during initial mount setup) or when the mount is not aligned.

## 2026-06-13 — FIX — Mount selftest + Centre Star guide pad: use center rate for observable movement

**Root cause (round 2)**: Guide pulses (`:Mg...#`) use OnStep's configurable guide rate. If the guide rate is unconfigured or very slow, even 2000 ms pulses produce no observable movement. The focuser selftest works because it uses absolute steps — the mount equivalent is center rate (`:RC#` + `:Mn#` → sleep → `:Q#`), which is always configured for visible manual centering.

**Fix**:
- Added `move(direction, move_ms)` abstract method to `MountPort`, implemented in `OnStepMount` using `write_bypass` (same pattern as `stop()` since rate/move commands have no response bytes), `SimulatorMount`, and `MockMount`.
- Added `POST /api/mount/nudge` endpoint — same state checks as `/guide` but calls `mount.move()`.
- `selftest_mount` now calls `mount.move()` instead of `mount.guide()`. Button group greys out during the 2-second test (like focuser), result shows `"N 2 s — moved"`.
- Stage 2 Centre Star guide pad (`guideStart()`) switched from `/api/mount/guide` to `/api/mount/nudge` — hold-and-repeat pattern is identical but now uses center rate.
- 11 new tests for `TestMountNudge`.

## 2026-06-13 — FIX — Mount selftest: guide pulses now measure arcsec shift

**Root cause**: A 2000 ms guide pulse at typical OnStep guide rates (0.5–1× sidereal = 7–15″/s) produces only 14–30 arcseconds of physical movement — invisible to the naked eye at any viewing distance. The selftest previously reported "ok" with no way to verify movement actually occurred.

**Fix**:
- `selftest_mount` now captures position (`:GD#`/`:GR#`) before and after the pulse, sleeps for `duration_ms + 300 ms`, then returns `delta_arcsec` in the response body.
- Default `duration_ms` raised 500 → 2000 ms to improve detection signal.
- `selftestMount()` JS now shows the shift: `N pulse 2000 ms — ok (+29.9″ shift)` or warns `no position shift — check OnStep guide rate`.
- 2 new tests: `test_north_pulse_returns_delta_arcsec`, `test_south_pulse_returns_negative_delta`.

## 2026-06-11 — FIX — Histogram comb pattern from 12-bit-in-16-bit camera data

**Root cause**: ToupTek SDK in 16-bit mode stores 12-bit ADC data MSB-aligned (left-shifted 4 bits). Values are 0, 16, 32, …, 65520. The focused histogram with ~7 ADU bins produced a comb pattern (every 2–3 bins was empty because valid values are 16 ADU apart). Additionally the histogram API was incorrectly normalising by `adc_max=4095` (bit_depth=12 default) while pixels were in 16-bit container range, giving signal fractions 16× too high.

**Fix** (`fb60f73`):
- `camera.py` / `managed.py`: lazily detect pixel shift on first captured frame (`_detect_pixel_shift`); right-shift pixels to native 12-bit range (0–4095); write `BITDEPTH=12` in FITS header. `get_bit_depth()` now returns the sensor depth.
- `autogain_service.py`: re-derives `bit_depth` and `adc_max` from the frame `BITDEPTH` header after each capture.
- `histogram.py API`: reads `bit_depth` from frame header instead of query-param default.
- `SYNC.md`: documents new SYNC-OVERRIDEs for both adapter files.

---

## 2026-06-09 — FIX — HOME uses OnStep :hC#; focuser selftest relative moves; tile refresh

**Bug 1 — HOME position overrun**
`home_sequence()` was computing RA = current LST, Dec = 85° and issuing a GoTo.  This ignored
OnStep's stored home position (set with `:hF#` during initial alignment) and could overrun the
mount's meridian limits or HA limits near the pole.

**Root cause:** SmartTScope invented its own HOME coordinates instead of delegating to OnStep.

**Fix:**
- `smart_telescope/ports/mount.py` — added `go_home()` abstract method to `MountPort`
- `smart_telescope/adapters/onstep/mount.py` — `go_home()` sends `:hC#` (Move to home)
- `smart_telescope/adapters/mock/mount.py` — stub: sets state to TRACKING
- `smart_telescope/adapters/simulator/mount.py` — stub: calls `goto(0, 89.0)`
- `smart_telescope/services/mount_operations.py` — `home_sequence()` now calls `mount.go_home()`
  instead of computing LST+85°; removed astropy/config imports no longer needed; returns `None`
- `smart_telescope/api/mount.py` — HOME endpoint response simplified to `{"ok": True}`
- `smart_telescope/services/setup_check_service.py` — callers updated; message updated
- `smart_telescope/api/setup_check.py` — docstring updated
- `smart_telescope/static/js/mount.js` — status messages no longer display invented coordinates
- `smart_telescope/static/js/setup.js` — wizard prompt updated

**Bug 2 — Focuser selftest moved to absolute position instead of relative**
`selftest_focuser()` in `collimation.py` called `focuser.move(steps)` with `steps=10`.
Since `FocuserPort.move()` is an **absolute** position command (`:FS[n]#`), this moved the
focuser to absolute step 10 from wherever it was (e.g. 5227 → 10), not +10 from current.
Same bug existed in `run_focuser_move()` in `setup_check_service.py`.

**Fix:**
- `smart_telescope/api/collimation.py` `selftest_focuser()` — computes `target = before + steps`
  then calls `focuser.move(target)`; waits for `is_moving()` to clear before reading `after`
- `smart_telescope/services/setup_check_service.py` `run_focuser_move()` — same relative→absolute
  fix; restore now calls `focuser.move(before)` instead of `focuser.move(-steps)`

**Bug 3 — OnStep focuser tile (s1-focuser-pos) not refreshing**
The Stage 1 focuser position tile was set only at `connectAll()` time and never updated when
nudge or selftest operations ran, so it showed the connect-time value (e.g. 25000/50000) even
as the focuser moved.

**Fix:**
- `smart_telescope/static/js/focuser.js` `_refreshFocuserPosition()` — now also updates
  `s1-focuser-pos` / `s1-focuser-pos-row` whenever Stage 4 position poll fires
- `smart_telescope/static/js/collimation.js` `selftestFocuser()` — calls `refreshFocuser()` and
  `_refreshS1FocuserPos()` in the `finally` block after each test

**Tests:**
- `tests/unit/services/test_mount_operations.py` — replaced LST-based home tests with
  `test_home_sequence_issues_go_home` and `test_home_sequence_does_not_goto`
- `tests/unit/api/test_setup_check.py` — `TestFocuserMove` updated: move calls now use
  absolute positions (before+steps, before); iterator provides 2 positions instead of 3
- All 2920 unit tests pass

---

## 2026-06-08 — FEAT(CID-007) — Detect newly connected cameras not in config

**What changed:**
- `smart_telescope/domain/camera_config_suggestion.py` (new) — `suggest_role()`, `_default_offset()`, `_default_capture_mode()`, `generate_toml_snippet()` — pure domain, no I/O
- `smart_telescope/api/cameras.py` — `CameraInfo.toml_snippet` field added; `_do_scan()` populates it for cameras with `role=None`; also resolves role via `CAMERA_SPECS` model/camera_id match (was only checking by index)
- `smart_telescope/services/readiness.py` — `_check_unconfigured_cameras()` returns YELLOW item when SDK cameras are connected but not matched by any configured CameraSpec; wired into `check()`
- `smart_telescope/static/js/setup.js` — `cameraCard()` shows yellow "Not in config" badge + collapsible TOML snippet + Copy button for unconfigured cameras; `csSnipcopy()` helper added
- `smart_telescope/static/index.html` — CSS added: `.card-warn`, `.badge-ok`, `.badge-warn`, `.snippet-details`, `.snippet-code`, `.btn-copy`
- `tests/unit/domain/test_camera_config_suggestion.py` (new) — 30 tests, 100% coverage of domain module
- `tests/unit/api/test_cid007.py` (new) — 15 tests covering API snippet generation and readiness YELLOW item
- `docs/todo.md` — CID-007 marked done

**Verified:** 2897 tests pass, 0 regressions.

---

## 2026-05-26 — FIX(UI) — Focuser selftest runaway + serial port auto-reconnect

**What changed:**

- `smart_telescope/static/index.html`: Added IDs `s4-st-focuser-plus` and `s4-st-focuser-minus` to the two focuser selftest buttons so they can be referenced by JavaScript.
- `smart_telescope/static/js/collimation.js` (`selftestFocuser`): Both buttons are disabled synchronously at the start of the function (before the first `await`), and re-enabled in a `finally` block after the API call completes. This prevents any additional browser events (second tap, touch+click double-fire) from queuing serial moves while one is in flight.
- `smart_telescope/services/device_state.py`: Added rate-limited `mount.connect()` call in `_poll_once` exception handler. When a serial I/O error leaves the serial bus broken (`_serial = None`), the poller now attempts reconnect at most once every 30 s. Previously, an I/O error (e.g. `[Errno 5] Input/output error` from USB disconnect/overload) would leave the mount permanently in UNKNOWN state until app restart.

**Root cause — runaway:** `selftestFocuser()` had no button locking. On a touchscreen a single physical tap can fire both a `touchend` and a `click` event; some browsers/tablets fire the `onclick` handler twice in rapid succession. Both calls reached the server before either completed, queueing multiple `:FS{steps}#` serial commands. The motor received alternating `+10` and `-10` (or repeated same-direction) moves with no time to settle, producing the observed runaway.

**Root cause — serial port death:** After rapid focuser moves caused an I/O error on the shared serial bus, `OnStepSerialBus.send()` set `self._serial = None` and raised, leaving the bus permanently broken. `DeviceStateService._poll_once` caught the exception and stored UNKNOWN state, but had no mechanism to recover the connection — the mount stayed UNKNOWN until the app was restarted.

---

## 2026-05-26 — FIX(UI) — Stage 4 proceed button: unlock on Connect All (no GoTo required)

**What changed:**

- `smart_telescope/static/js/app.js` (`unlockStage`): When Stage 4 is unlocked, `s3-proceed-btn` is now enabled immediately. Previously the button was only enabled after a successful GoTo slew completed, so after a "Connect All" that left the mount parked, the user had no way to advance to Stage 4.

**Root cause:** `s3-proceed-btn.disabled` was cleared only in the GoTo success path. Stage 4 unlock (triggered by any non-UNKNOWN mount state) never touched the button, leaving it disabled for users who skipped GoTo.

---

## 2026-05-26 — FIX(UI) — Stage 4 collimation button: start strip poll at page load

**What changed:**

- `smart_telescope/static/js/app.js`: Added `_startMountStripPoll()` call at page load alongside `refreshMount()`. The 5-second repeating mount-status poll now starts immediately, so Stage 4 unlocks within ≤5 s even if the single initial `refreshMount()` caught a transient UNKNOWN state (startup race between DeviceStateService poller and DawnWatcher's concurrent `poll_now()` call). Removed diagnostic console.log lines.
- `smart_telescope/static/js/mount.js`: Removed diagnostic console lines from `refreshMount` and `_updateMountStrip`; restored to original logic.
- Backend WARNING logs in `smart_telescope/api/mount.py` and `smart_telescope/services/device_state.py` retained for future diagnosis.

**Root cause:** `_startMountStripPoll()` was only called inside `goToStage()`. Stage 1 is the initial active stage and `goToStage(1)` is never called at startup, so no strip poll ran on Stage 1. If the one-shot `refreshMount()` at page load caught a transient UNKNOWN state (DawnWatcher + background poller both calling the serial bus simultaneously at startup), Stage 4 stayed locked with no recovery mechanism.

---

## 2026-05-26 — DBG — Diagnostic logs for Stage 4 collimation button unlock failure

**What changed:**

- `smart_telescope/static/js/app.js`: log at page load showing strip poll is NOT started at startup (only starts via `goToStage()`).
- `smart_telescope/static/js/app.js`: log in `_startMountStripPoll` when it fires.
- `smart_telescope/static/js/mount.js`: log in `refreshMount` showing state received, whether strip poll is running, whether Stage 4 is already unlocked.
- `smart_telescope/static/js/mount.js`: log in `_updateMountStrip` showing when Stage 4 is unlocked vs. why it stays locked (state='unknown').
- `smart_telescope/api/mount.py`: WARNING logs in `mount_status` when cache or direct query returns UNKNOWN state.
- `smart_telescope/services/device_state.py`: WARNING log in `_poll_once` when `get_state()` returns UNKNOWN, separate from poll exception.

**Root cause hypothesis:** The mount strip poll only starts when `goToStage()` is called. On page load, only one `refreshMount()` fires. If that one call gets state='unknown' (OnStep not yet ready), Stage 4 stays locked forever with no retry mechanism.

---

## 2026-05-26 — COL-ENH2 — Collimation UX polish: report, auto-remeasure, best-star

**What changed:**

- `smart_telescope/static/index.html` + `smart_telescope/static/js/collimation.js`:
  - **Session report panel**: when wizard reaches COMPLETE, fetches `/api/collimation/report` and shows overall status (colour-coded), duration, selected star, FWHM before/after, final donut error, and any warnings — all inline in the wizard card.
  - **Auto-remeasure**: guide phases (GUIDE_ROUGH_COLLIMATION / GUIDE_FINE_COLLIMATION) now show an "Auto every 5s" checkbox. When ticked, the wizard fires Remeasure automatically on a 5-second interval; cleared on cancel/stop.
  - **Use Best Star button**: when wizard enters SELECT_STAR state, a "Use Best Star" button appears that auto-picks the brightest star from the star list (mag-sorted) and submits it as the selected star without user needing to click the list.

---

## 2026-05-26 — COL-ENH — Collimation measurement metrics + archive browser UI

**What changed:**

- `smart_telescope/services/collimation/assistant.py` (`status` property): `last_measurement` now includes `measurement_type` ("donut"/"spikes"/"star"/None) and sub-dicts: `donut` (error_x_px, error_y_px, error_magnitude_px, error_fraction, outer_radius_px, is_collimated, confidence); `spikes` (focus_error_px, crossing_error_rms_px, offset_from_ref_px, is_in_focus, confidence); `star` (fwhm_px, snr). 4 new tests verify each measurement type.

- `smart_telescope/static/index.html` + `smart_telescope/static/js/collimation.js`: Measurement metrics panel added to wizard card — shows collimation error (px + % of outer ring, colour-coded green/yellow/red), spike focus error + RMS, star FWHM. Frame Archive Browser card added to Stage 4: lists past sessions (id, frame count, state breakdown, disk size); expanding a session loads its frame table; Replay button re-runs donut/spike analysis on the stored FITS frame and shows original vs replayed values side-by-side.

---

## 2026-05-26 — BUG-FIX — Stage 4 mount strip poll stopped on Stage 1

**What changed:**

- `smart_telescope/static/js/app.js` (`goToStage`): Removed `_stopMountStripPoll()` call when navigating to Stage 1.
  - Root cause: OnStep takes time to boot after power-on; the initial page-load `refreshMount()` sees UNKNOWN state. With the mount strip poll stopped on Stage 1, this UNKNOWN state was never corrected automatically, keeping Stage 4 locked until the user clicked "Connect All".
  - Fix: `goToStage()` now always calls `_startMountStripPoll()` on every stage, so `_updateMountStrip()` runs every 5 s and unlocks Stage 4 as soon as the mount reports a known state.

---

## 2026-05-24 — BUG-FIX — Preview camera and Stage 4 unlock fixes (rev 2)

**What changed:**

- `smart_telescope/api/preview.py`: Fixed preview WebSocket always using GPCMOS02000KPA (camera index 0) regardless of selected optical train.
  - Root cause: model-based camera config sets `CameraSpec.index = None`; registry defaults all trains to `camera_index = 0`, so every train opened the same physical camera.
  - Fix: after resolving the train from `camera_role`, call `deps.get_camera_by_role(train.camera_role)` (which uses model-matching to open the correct device) instead of `deps.get_preview_camera(camera_index=0)`. Falls back to index-based resolution on failure.
  - Rev 2: wrapped `get_camera_by_role` call in `asyncio.to_thread` — the first call blocks on USB SDK I/O (camera connect + configure); running it in a thread prevents stalling the WebSocket event loop.

- `smart_telescope/static/js/mount.js` (`_updateMountStrip`): Fixed Stage 4 (Collimation) tab remaining locked after the PARKED detection fix.
  - Root cause: the previous `get_state()` bug (`r[0] == "P"` check) always returned UNPARKED on real hardware, so `_updateMountStrip` always unlocked Stage 4. After the correct PARKED detection, Stage 4 was locked on page-load with mount parked, and only unlocked after unpark.
  - Fix: Stage 4 now unlocks for any *known* mount state (not just unparked), because calibration frames and Bahtinov preview don't require the mount to be unparked. The collimation wizard auto-unparks internally if needed. Stage 2 (Alignment) still requires unparked mount.

---

## 2026-05-24 — ONS — OnStep protocol documentation update

**What changed:**

- `wiki/onstep-protocol.md`: Updated with hardware-confirmed findings from direct serial probe (2026-05-24).
  - `:GU#` section: documents real compact wire format (`nNPEW260` parked, `NpeEW260` unparked); correct PARKED detection rule `"P" in r and "p" not in r`; wrong approaches listed explicitly.
  - Park commands section: `:hR#` confirmed as correct unpark command (~2 s synchronous, returns `b"1"`/`b"0"`); `:hU#` confirmed rejected by firmware; `:hP#` confirmed fire-and-forget (~10 ms, mount slews asynchronously).
  - Serial bus section: documents two-read-strategy table; `timeout_s` override mechanism for slow commands; rule against long global timeouts.
  - Commands table: updated `unpark()`, `get_state()`, `park()` rows with confirmed behaviour.

---

## 2026-05-24 — COL-ARC — Collimation frame archive

**What changed:**

- `smart_telescope/domain/collimation/config.py`: `ArchiveConfig` dataclass (`enabled`, `archive_dir`, `max_frames_per_session`); `CollimationConfig` gains `archive: ArchiveConfig` field

- `smart_telescope/services/collimation/frame_archive.py` (NEW): `CollimationFrameArchive` — `new_session()` creates `<archive_dir>/<session_id>/`; `save_frame()` writes FITS via `FitsFrame.to_fits_bytes()` + JSON sidecar with state/analysis/ref_x/ref_y/bit_depth; silently skips when `max_frames_per_session` reached; `list_sessions()` newest-first by mtime; `list_frames()` sorted by filename; `load_frame()` / `load_sidecar()` raise `FileNotFoundError` when absent; 7 tests in `tests/unit/services/test_frame_archive.py`

- `smart_telescope/services/collimation/assistant.py`: `__init__` accepts `frame_archive: CollimationFrameArchive | None`; `start()` generates `uuid4` session ID and calls `archive.new_session()`; `frame_archive` property; `_handle_measure_donut` saves raw frame + donut analysis dict after each accepted measurement; `_handle_measure_spikes` saves raw frame + spike analysis dict after each accepted measurement; 3 new tests in `test_collimation_guiding.py`

- `smart_telescope/api/collimation.py`: `_get_assistant()` builds `CollimationFrameArchive` from `col_cfg.archive` when `enabled=True`, passes to `CollimationAssistant`; `GET /api/collimation/archive` lists sessions; `GET /api/collimation/archive/{session_id}` lists frames; `POST /api/collimation/archive/{session_id}/{frame_stem}/replay` re-runs `DonutAnalyzer` or `detect_spikes` on stored frame; 6 tests in `tests/unit/api/test_collimation_archive_api.py`

- `templates/config.toml`: `[collimation.archive]` section added (disabled by default)

---

## 2026-05-24 — COL-GUD — Collimation guiding integration complete

**Source:** `docs/superpowers/plans/2026-05-24-collimation-guiding-integration.md`

**What changed:**

- `smart_telescope/services/guiding_service.py`: `GuidingStatus` gains `rms_px: float` and `last_pulse: tuple[str, int] | None`; `GuidingService` gains `pause_pulses()`, `resume_pulses()`, `rebaseline()`; `_loop()` honours pause flag, flushes error history on rebaseline, tracks rolling RMS (10-frame window), records last issued pulse direction+duration; `_lifecycle_lock` wraps `start()` and `stop()` to prevent TOCTOU; reset of pause/rebaseline on `start()`; 3 new tests in `test_guiding_service.py` (pause suppresses calls, resume restores, rebaseline stops cleanly)

- `smart_telescope/domain/collimation/config.py`: `CollimationConfig` dataclass gains `guiding_camera_role: str = "guide"`, `guiding_exposure_s: float = 2.0`, `guiding_cadence_s: float = 3.0`; `from_dict()` reads all three from TOML; 2 new tests in `test_collimation_guiding.py`

- `smart_telescope/services/collimation/assistant.py`: `__init__` accepts `guiding_service: GuidingService | None` and `guide_cameras: dict[str, CameraPort] | None`; `_guiding_status_dict()` returns `available/state/rms_px/last_pulse`; `status` property includes `"guiding"` key; `_start_guiding()` starts the service using collimation config fields; `_stop_guiding()` stops if running, called in `_run()` finally block; `_with_guiding_paused(fn)` pause→fn→rebaseline+resume wrapper; `_recenter_star()` PulseCenterer without state transition; `_handle_auto_exposure()` calls `_start_guiding()` before transitioning; `_dispatch_user_wait()` calls `_with_guiding_paused(_recenter_star)` before each Remeasure transition; 5 new tests in `test_collimation_guiding.py`

- `smart_telescope/api/collimation.py`: `_get_assistant()` now builds `GuidingService` lazily from collimation config (gracefully falls back to no guiding if guide camera role is absent); imports `get_camera_by_role` from deps

- `smart_telescope/static/index.html`: guide status row `<div id="s4-wiz-guide-row">` inserted after instruction div in wizard card (initially `display:none`)

- `smart_telescope/static/js/collimation.js`: `_updateCollimWizard(s)` renders guide row — shows/hides based on `s.guiding.available`; green/red dot for locked/lost; displays `rms_px` and `last_pulse` direction+duration

- `wiki/index.md`: Guiding section updated with collimation guiding integration plan link and completion summary; Collimation Assistant section unchanged

---

## 2026-05-23 — GUD-002..007 — Guiding pipeline complete

**What changed:**

- `smart_telescope/services/managed_camera.py` (GUD-003): `MailboxFrame` frozen dataclass; `FrameMailbox` with latest-frame drop semantics (`put()` drops unconsumed, `wait_latest()` with monotonic deadline, `dropped_count`); `ManagedCamera` (background daemon thread, `start_stream()` / `stop_stream()`, `pop_stream_error()`, `abort_capture()` on stop); 7 tests in `tests/unit/services/test_managed_camera.py`

- `smart_telescope/services/guide_measurement.py` (GUD-002/004): `CentroidConfig`, `GuideCentroidEstimator` (find-peak→ROI→MAD-noise→saturation→SNR→centroid), `GuideControllerConfig`, `MeasureOnlyGuideController` (deadband, aggressiveness, pulse clamp, sub-deadband suppression), `GuideSourceSelector` (primary/fallback logic, TRANSIENT_BAD + HARD_FAILED trigger fallback), `source_state_from_measurement`; 6 tests in `tests/unit/services/test_guide_measurement.py`

- `smart_telescope/services/guiding_service.py` (GUD-004): `GuidingStatus` (`to_dict()`), `GuidingService` with `from_config()` factory; `_lifecycle_lock` wrapping both `start()` and `stop()` for TOCTOU safety; `started_at` passed as arg to `_loop()`; `_estimator.measure()` wrapped in try/except; `latest is None` increments bad_count; real mount pulses sent when `measure_only=False` with exception swallowed; 6 tests in `tests/unit/services/test_guiding_service.py` (including 2 measure_only=False tests with mock mount)

- `smart_telescope/api/guiding.py` (GUD-006): `POST /api/guiding/start` (202, 409 if running, 422 if no cameras, `RuntimeError` caught on camera connect failure); `POST /api/guiding/stop`; `GET /api/guiding/status`; mount resolved via `rt.get_mount()` (with fallback to None); 4 tests in `tests/unit/api/test_guiding.py`

- `smart_telescope/api/deps.py`, `smart_telescope/runtime.py`: `get_guiding_service()` injectable; `runtime.guiding_service` property (lazy init from config); `shutdown()` and `reset_for_tests()` stop and clear `_guiding_service`

- `smart_telescope/app.py`: `guiding_router` registered after `bias_estimation_router`

- `templates/config.toml`: `[guiding]` section appended with 9 commented fields (primary_role, allow_fallback, fallback_after_bad_frames, max_frame_age_s, centroid_roi_px, min_peak_snr, saturation_fraction, measure_only=true)

- `smart_telescope/static/js/guiding.js`: Guide Monitor card polling JS — `guidingStart()`, `guidingStop()`, `_guidingPollStart()`, `_guidingPollStop()`, `_guidingPoll()`, `_guidingUpdateCard()`; polls every 2 s when running; state badge (IDLE/RUNNING/FAILED), source health badges, pulse summary

- `smart_telescope/static/index.html`: Guide Monitor card added before Connected Cameras section (advanced mode only, `adv-only` class); `guiding.js` loaded after `bias_estimation.js`

- `docs/todo.md`: GUD-002..007 marked done; GUD-008 remains (hardware verification)

- `wiki/index.md`: Guiding section updated with pipeline plan link and implementation summary

---

## 2026-05-23 — requirements ingest: guiding pipeline, OnStep replacement, watchdog, packaging fixes

**Sources:** 10 new files in `resources/hlrequirements/` (ingested 2026-05-23)

**What changed:**

- `pyproject.toml`: `pyserial>=3.5` moved from `[dev]` to production `[project].dependencies` — it is used in `adapters/onstep/mount.py` and `app.py` at runtime, not dev-only
- `tests/unit/services/test_guide_measurement.py`: `pytest.importorskip` guard added — test collection no longer errors when `services.guide_measurement` is absent; 2779 tests collected cleanly
- `docs/todo.md`: updated with serial numbers for all three cameras (CID-006 note); new PKG section (both items done); new GUD section (8 tasks, guiding pipeline); deferred ONSTEP-REPLACE-001 (OnStep adapter replacement, waiting for external party) and WATCHDOG-001/002 (Pi systemd + external heartbeat supervisor)

**New todo sections added:**
- `Build and Packaging` (PKG-001/002) — both complete
- `Guiding Pipeline` (GUD-001..008) — GUD-001..007 ready to implement, GUD-008 hardware-blocked
- `Deferred`: ONSTEP-REPLACE-001 (blocked on external party), WATCHDOG-001/002 (blocked on hardware + systemd migration decision)

**Architecture reference docs ingested (no code changes):**
- `INDI_Steer_pattern.md` — one-adapter-per-device, one-SDK-handle-per-adapter pattern
- `SmartTScope_ToupTek_Device_Handling_Recommendation.md` — device ownership model (AVAILABLE/OWNED_BY_SMARTTSCOPE/EXTERNALLY_BUSY), three operating modes (Full Smart Telescope / Planetary External / Hybrid Safe)

**Hardware serial numbers recorded (for Pi `~/.SmartTScope/config.toml`):**
- `GPCMOS02000KPA = "tp-3-4-23-0547-1367"`, `ATR585M = "tp-4-1-10-0547-157c"`, `G3M678M = "tp-4-2-11-0547-14bc"`

---

## 2026-05-22 — camera_adapter integration + Pi boot fix

**Source:** `resources/camera_adapter` (external module, first sync)

**What changed:**

- `smart_telescope/app.py`: catch-all `@app.exception_handler(Exception)` added — all unhandled 500 errors now return JSON instead of plain text (fixed browser `SyntaxError` on `/api/mount/status`)
- `smart_telescope/config.py`: `CameraSpec` + `CAMERA_SPECS` (dict-valued `[cameras]` TOML support); `CoolingSpec`, `FilterWheelSpec`, `GuidingSpec` dataclasses + parse functions + `COOLING`, `FILTER_WHEEL`, `GUIDING` constants; `_parse_cameras()` updated to handle dict-valued entries without crashing
- `smart_telescope/runtime.py`: `SmartTouptekCamera` code path added in `_build_adapters()` with try/except fallback to `MockCamera`; `_role_cameras`, `_filter_wheel` state; `_validate_camera_role_ownership()`; `get_camera_by_role()` upgraded to use `CAMERA_SPECS`; `get_filter_wheel()` added; shutdown/disconnect/reset updated
- `smart_telescope/adapters/touptek/managed.py`: new file — `SmartTouptekCamera` adapter with capture modes and setup profiles; `connect()` returns `False` (SYNC-OVERRIDE) instead of raising when no device found
- `smart_telescope/adapters/touptek/camera.py`: replaced with camera_adapter version (richer constructor: `camera_id`, `model`, `name`, `capture_mode`, `setup_profile` params)
- `smart_telescope/adapters/touptek/filter_wheel.py`: new — `TouptekFilterWheel` adapter
- `smart_telescope/domain/guiding.py`: new — `GuideFrame`, `GuideMeasurement`, `WouldGuidePulse`, `GuideSourceState`
- `smart_telescope/tools/camera_loadtest.py`, `guide_measuretest.py`: new CLI stress-test tools
- `tests/unit/services/test_guide_measurement.py`: new unit tests (skipped until `services.guide_measurement` is delivered by external party)
- `templates/config.toml`: `[cameras]` section migrated to `[cameras.<role>]` table format; `[camera_offsets]` removed (offsets now inline per camera)
- `scripts/sync_camera_adapter.sh`: new — copies external-owned files on each release, detects drift
- `SYNC.md`: new — tracks sync state, SYNC-OVERRIDEs, pending external requirements
- `docs/superpowers/specs/2026-05-22-camera-adapter-integration-design.md`: integration design spec
- `docs/superpowers/plans/2026-05-22-camera-adapter-integration.md`: implementation plan

**Pi fix:** `smart_telescope/config.py` at git `c525dd6` had `return {role: int(idx) for role, idx in section.items()}` which crashed on dict-valued `[cameras.main]` entries. Pi must `git reset --hard origin/main` then update `~/.SmartTScope/config.toml` to use `[cameras.main]` table format and restart via `bash ~/astro_sw/start.sh`.

---

## 2026-05-21 — COE-001..004 — Camera Offset Estimation Wizard complete

**What changed:**

- `smart_telescope/domain/bias_estimation.py` (COE-001): `ZERO_CLIP_THRESHOLD=0.001`, `BiasFrameStats`, `OffsetSweepPoint` (with `is_safe` property), `BiasEstimationResult` (`recommended_offset`, `safe`, `toml_snippet()`), `analyze_frame()`, `DEFAULT_SWEEP_OFFSETS=[0,5,10,20,30,50,75,100,125,150,200]`; 14 tests in `tests/unit/domain/test_bias_estimation.py`

- `smart_telescope/services/bias_estimation_service.py` (COE-002): `BiasEstimationService.estimate()` — sets gain mode, captures frames at minimum exposure, sweeps offset values, averages stats per offset, restores original offset in `finally`, respects cancel event; 10 tests in `tests/unit/services/test_bias_estimation_service.py`

- `smart_telescope/api/bias_estimation.py` (COE-003): `BiasEstimationRequest` with Pydantic `@field_validator` for gain_mode; `_JobState` registry with thread-safe dict; `POST /api/bias_estimation/start` (202, returns job_id); `GET /api/bias_estimation/status/{job_id}` (RUNNING/DONE/FAILED/CANCELLED + full result on DONE); 5 tests in `tests/unit/api/test_bias_estimation_api.py` (including runtime-restore fixture + optical train wiring); 422 for unknown camera role

- `smart_telescope/static/js/bias_estimation.js` (COE-004): `beLaunchWizard`, `beHideWizard`, `beResetState`, `beStartEstimation`, `bePollStatus`; polls every 500ms; builds sweep table with safe/clipping badges; highlights recommended offset row in green; shows TOML snippet in `<pre>` block on DONE; orange warning when no safe offset found

- `smart_telescope/static/index.html`: Sensor Offset Estimation card added to Stage 5 (before Connected Cameras); `<script src="/static/js/bias_estimation.js">` added

- `wiki/index.md`: "Camera configuration" section added with links to CID/CO/COE plans

- `docs/todo.md`: COE-001..004 marked done with acceptance notes

**Tests:** 44 smoke tests pass; 32 bias estimation tests pass (domain + service + API)

---

## 2026-05-20 — Camera ID Mapping / Camera Offset / Bias Estimation (CID/CO/COE)

**What changed:**
- `docs/todo.md`: Three new P1 sections added — CID (camera ID mapping), CO (camera offset config), COE (camera offset estimation wizard).
- `docs/superpowers/plans/2026-05-20-camera-id-mapping.md`: Full TDD plan for name-based camera config (CID-001..007).
- `docs/superpowers/plans/2026-05-20-camera-offset-config.md`: Full TDD plan for `[camera_offsets]` config + `CameraOffsetService` (CO-001..008).
- `docs/superpowers/plans/2026-05-20-camera-offset-estimation.md`: Full TDD plan for bias-frame offset estimation wizard in Stage 6 (COE-001..006).

**Source documents ingested:**
- `resources/hlrequirements/camera_id list.md`
- `resources/hlrequirements/camera_offset.md`
- `resources/hlrequirements/camera_offset_estimation.md`

---

## 2026-05-19 — POD-010 — Camera role resolution in API endpoints

**What changed:**
- `smart_telescope/api/deps.py`: Added `resolve_camera_index(camera_index, camera_role)` helper — returns `camera_index` when no role given; resolves role via `OpticalTrainRegistry` when provided; raises HTTP 422 for unknown roles.
- `smart_telescope/api/solver.py`: `SolveRequest` accepts optional `camera_role`.
- `smart_telescope/api/calibration.py`: `BiasRequest`, `DarkRequest`, `FlatRequest`, `BpmRequest` accept optional `camera_role`; `GET /api/calibration/match` accepts `camera_role` Query param.
- `smart_telescope/api/histogram.py`: `POST /api/histogram/analyze` accepts `camera_role` Query param.
- `smart_telescope/static/js/setup.js`: Calibration and histogram calls now send `camera_role` directly; `_calSharedParams()` returns `camRole` instead of `camIdx`.
- `smart_telescope/static/js/session.js`: `solveFrame()` sends `camera_role` directly.
- `smart_telescope/static/js/preview.js`: `_fetchAndDrawHistogram()` sends `camera_role` directly.
- `tests/unit/api/test_camera_role_resolution.py`: 11 new tests.
- `docs/todo.md`: POD-004, POD-009, POD-010 marked done.

**Tests:** ≥2688 passed

---

## 2026-05-19 — M5-001 — Guided startup

**What changed:**
- `smart_telescope/static/index.html`: `s1-proceed-btn` now starts `disabled`.
- `smart_telescope/static/js/setup.js`: `connectAll()` enables/disables `s1-proceed-btn` based on `mountOk`; catch block resets `proceedBtn.disabled = true` and `_mountConnected = false` on failure.
- `smart_telescope/static/js/mount.js`: `s1Proceed()` no longer calls `unlockStage(2)` — Stage 2 unlock belongs to `connectAll()` only.
- `tests/unit/api/test_smoke.py`: Added `test_s1_proceed_btn_starts_disabled` (regex-based).
- `docs/todo.md`: M5-001, M5-003, M5-004 marked done.

**Tests:** 44 smoke tests pass

---

## 2026-05-19 — POD-005 — Failure isolation policy

**What changed:**
- `smart_telescope/services/readiness.py`: Added `_capability_flags(items)` static method + 5 new fields to `ReadinessReport` (`can_preview`, `can_goto`, `can_solve`, `can_autofocus`, `can_save`). RED items block the relevant capability; YELLOW = degraded, functional. Updated module docstring and added inline comment to `can_observe` computation.
- `tests/unit/api/test_readiness.py`: Added `TestCapabilityFlags` (12 tests covering all POD-005 isolation scenarios and YELLOW-does-not-block cases).
- `smart_telescope/static/js/setup.js` + `index.html`: Blocked-capability chip row in readiness card; null guard in `_renderReadiness`; chip div hidden when all capabilities are available.
- `docs/todo.md`: POD-005 marked done with formal decision recorded.

**Tests:** 2676 passed

---

## 2026-05-19 — M6-012 — Release notes v0.1

**What changed:**
- Created `docs/release-notes-v0.1.md` covering: milestone status table (M0–M6 + Collimation), all implemented features by milestone, performance targets table, known issues (hardware-blocked and open software), deferred post-MVP scope, and install/upgrade path.
- `docs/todo.md`: marked M6-012 done.
- `wiki/index.md`: added release-notes-v0.1 link under Release readiness.

**Tests:** 2664 passed, 87.56% coverage

---

## 2026-05-19 — BUG-002 — Autogain layout clarification

**What changed:**
- `smart_telescope/static/index.html`: Split the Stage 3 Live Preview controls from one dense row into two rows. Row 1 retains camera settings (Cam/Exp/Gain/Off), display toggles (Str/Hist), Solve, AF, frame count, and camera adapter label. Row 2 is a dedicated "Auto-gain:" row with "Adjust live" checkbox (tooltip clarified), a vertical separator, "Find Best" button, Cancel, and status badge. All element IDs unchanged — no JS edits required.

**Tests:** 43 smoke tests pass

---

## 2026-05-19 — R7-006 — Done-without-evidence report

**What changed:**
- `smart_telescope/domain/milestones.py`: Added `EvidenceGapItem` frozen dataclass (`id`, `priority`, `description`, `milestone`, `mock_tested_by`, `hardware_needed`) and `EVIDENCE_GAPS` registry (8 items: BUG-023/005 P0, BUG-011/012/016/010/013/019 P1, sorted P0 first). Also updated `RISK_REGISTRY` replacing completed M6-003 with M6-012.
- `smart_telescope/api/milestones.py`: Added `GET /api/evidence-gaps` → `{items, count}`.
- `tests/unit/domain/test_milestones.py`: Added `TestEvidenceGaps` (6 tests).
- `tests/unit/api/test_milestones.py`: Added `TestEvidenceGapsEndpoint` (7 tests).

**Tests:** 38 pass

---

## 2026-05-19 — M6-001–006 — Performance targets defined

**What changed:**
- `smart_telescope/domain/performance_targets.py` (new): `PerformanceTarget` + `PerformanceTargets` frozen dataclasses; `TARGETS` singleton with all 6 targets — session duration (6 h), preview latency (≤ 2 s), STOP response (≤ 500 ms), centering accuracy (≤ 30 arcsec), plate-solve success rate (≥ 90%), Pi thermal ceiling (≤ 75°C).
- `smart_telescope/api/performance_targets.py` (new): `GET /api/performance-targets` returns each target as `{value, unit, rationale}`.
- `smart_telescope/app.py`: registered performance_targets router.
- `tests/unit/domain/test_performance_targets.py` (new): 12 tests — field presence, positive values, unit/rationale strings, safety sanity checks (STOP ≤ 1000 ms, Pi < 80°C).
- `tests/unit/api/test_performance_targets.py` (new): 7 tests — HTTP contract, all keys present, positive numbers, unit strings.

**Tests:** 19 pass

---

## 2026-05-19 — R7-005 + M0-008 — Milestone dashboard and risk view

**What changed:**
- `smart_telescope/domain/milestones.py` (new): `MilestoneSummary` frozen dataclass with computed `status` (green/yellow/red); `RiskItem` frozen dataclass; `MILESTONE_REGISTRY` (8 milestones M0–M6 + COL) and `RISK_REGISTRY` (10 open P0/P1 items, P0 first).
- `smart_telescope/api/milestones.py` (new): `GET /api/milestones` returns `{milestones, top_risks}`.
- `smart_telescope/app.py`: registered milestones router.
- `smart_telescope/static/index.html`: "Milestone Dashboard" card added to Stage 1 (below readiness).
- `smart_telescope/static/js/setup.js`: `_renderMilestones()` + `refreshMilestones()` — color-coded progress bars per milestone, top-risk list with priority badges.
- `smart_telescope/static/js/app.js`: `refreshMilestones()` called at page init.
- `tests/unit/domain/test_milestones.py` (new): 16 tests — status logic, registry invariants.
- `tests/unit/api/test_milestones.py` (new): 9 tests — HTTP contract, field presence, sorting.

**Tests:** 25 pass

---

## 2026-05-19 — M6-009 — Storage-full simulation tests

**What changed:**
- `smart_telescope/adapters/disk_storage/storage.py`: `save_image()` and `save_log()` propagate `OSError` (e.g. `ENOSPC`) from the underlying `write_bytes`/`write_text` call; no partial file is left on failure.
- `smart_telescope/workflow/stages.py`: `stage_save()` raises `WorkflowError("save", "Disk full…")` when `storage.has_free_space()` is False; unexpected `OSError` from save calls is wrapped by the runner into `WorkflowError`.
- `tests/unit/adapters/disk_storage/test_disk_storage.py`: Added `TestDiskFullWriteFailure` (3 tests) — ENOSPC propagation for image and log writes, and no-partial-file guarantee.
- `tests/unit/workflow/test_runner_stages.py`: Added `TestRunnerStorageFull` (5 tests) — disk-full failure stage/reason, no image path on disk-full, OSError from save_image wrapped into WorkflowError, partial-save image path preserved when log write fails.

**Tests:** 99 pass

---

## 2026-05-19 — COL-022 — Hardware self-test page

**What changed:**
- `smart_telescope/api/collimation.py`: 3 new endpoints under `/api/collimation/selftest/`: `POST /camera` (captures 1 frame, returns width/height/peak_adu or 503), `POST /mount` (fires guide pulse N/S/E/W 500 ms, validates direction, returns ok or 503), `POST /focuser` (moves ±steps, returns before/after position; returns `ok:false` message when focuser unavailable; 422 on zero steps).
- `smart_telescope/static/index.html`: New "Hardware Self-Test" card before the Collimation Wizard card in Stage 4 — table with Camera/Mount/Focuser rows, test buttons, and per-row result spans.
- `smart_telescope/static/js/collimation.js`: `selftestCamera()`, `selftestMount(dir)`, `selftestFocuser(steps)` async functions; `_stResult()` helper updates result span with green/red colouring; dot turns green on first success.
- `tests/unit/api/test_collimation_selftest.py` (new): 14 tests — 4 camera, 5 mount, 5 focuser; covers ok paths, error paths (503/422), unavailable focuser, and default-body acceptance.

**Tests:** 2599 pass (87% coverage)

---

## 2026-05-19 — M5-013 — Dawn auto-park

**What changed:**
- `smart_telescope/domain/solar.py`: Added `ASTRONOMICAL_DAWN_ALT_DEG = -18.0` constant and `sun_altitude_now(lat, lon)` function (calls `sun_position_now()` → `compute_altaz()`).
- `smart_telescope/services/dawn_watcher.py` (new): `DawnWatcher` background service; polls sun altitude every 60 s; issues `mount.park()` + `device_state.poll_now()` exactly once when alt ≥ −18°; exposes `get_status() → DawnStatus`; thread-safe `start()`/`stop()` lifecycle.
- `smart_telescope/runtime.py`: Added `dawn_watcher: DawnWatcher` field; started in `connect_devices()` using `config.OBSERVER_LAT/LON`; stopped in `shutdown()` and `reset_for_tests()`.
- `smart_telescope/api/dawn.py` (new): `GET /api/dawn` returns sun altitude, is_dawn flag, parked_at_dawn flag, and parked_at UTC timestamp.
- `smart_telescope/app.py`: Registered dawn router.
- `tests/unit/domain/test_solar.py`: Added `TestSunAltitudeNow` (3 tests) and import of `sun_altitude_now`.
- `tests/unit/services/test_dawn_watcher.py` (new): 9 tests covering status before start, park trigger, no-repark guard, stop, idle status, error isolation.

**Tests:** 2585 pass (87% coverage)

---

## 2026-05-19 — R7-001/002/003 — Release readiness checklists; M0 backlog audit

**What changed:**
- `docs/operational-acceptance-checklist.md` (new): 10-section field checklist covering power-on, connect all, readiness dashboard, setup check, solar safety gate, GoTo/plate-solve alignment, autofocus, emergency STOP (< 1 s), preview/stack, and shutdown; includes sign-off table
- `docs/hardware-test-log-template.md` (new): append-only evidence log defining six required evidence items (E-001 STOP during slew, E-002 STOP during focuser move, E-003 shutdown during motion, E-004 reconnect, E-005 setup check, E-006 full workflow); structured entry template with date, commit, steps, result, log extract
- `docs/release-checklist.md` (new): 8-section go/no-go gate with BLOCKER items; covers backlog gate (all P0/P1 closed or deferred), hardware evidence gate (all 6 E-items pass), operational acceptance, test suite (≥80% coverage), clean install, performance targets, documentation, product-owner sign-off table and deferred items register
- `wiki/index.md`: new "Release readiness" section linking all three documents
- `docs/todo.md`: R7-001/002/003 marked done; M0-002 through M0-007 marked done (backlog audit confirmed all work already completed)

---

## 2026-05-19 — BUG-004 + BUG-021 — Histogram zoom and bar rendering fixes

**What changed:**
- `smart_telescope/domain/histogram.py`: `histogram_bins_focused` no longer applies an `adc_max×0.05` floor to `adu_hi`. Minimum is now 1000 ADU (was up to 3276 for 12-bit-in-16-bit cameras). Dim images (p99.9 = 200 ADU) now get a 0–1000 ADU histogram instead of 0–3276, filling the canvas 3× better.
- `smart_telescope/static/js/preview.js`: `showHistogram()` draws `0–Xk ADU · N ADU/bin` as a small text overlay in the canvas top-right corner (BUG-004: block size above). Bar rendering now uses `Math.max(1, Math.round(hRaw))` when `binCounts[i] > 0` — every non-zero bin shows at least 1px (BUG-021). New `_updateLowLabel()` helper updates `s3-hist-low-label` element with the real bin size on each draw.
- `smart_telescope/static/index.html`: Low histogram label div given `id="s3-hist-low-label"`; hardcoded wrong "5 ADU/bin" text replaced with plain "pedestal detail" (JS fills in the real value).
- `tests/unit/domain/test_histogram.py`: 5 new tests in `TestHistogramBinsFocused` — return shape, dark frame minimum, dim frame tighter zoom, bright frame clips to adc_max, n_bins parameter.

**Tests:** 2570 pass (87% coverage)

---

## 2026-05-18 — R6-007 — FocusRunConfig policy object

**What changed:**
- `smart_telescope/domain/autofocus.py`: Added `FocusRunConfig` dataclass with fields `range_steps`, `step_size`, `exposure_s`, `backlash_steps`, `skip`; `to_params()` converts to `AutofocusParams`
- `smart_telescope/workflow/stages.py`: `StageContext` 5 flat autofocus fields replaced with `focus_config: FocusRunConfig`; `stage_autofocus` and `stage_stack` (mid-refocus) both call `ctx.focus_config.to_params()` — eliminating the duplicate `AutofocusParams` construction; 4 unused `_types.py` constant imports removed
- `smart_telescope/workflow/runner.py`: `VerticalSliceRunner.__init__()` 5 flat params replaced with `focus_config: FocusRunConfig | None = None`; refocus-tracker condition uses `focus_config.skip`
- `smart_telescope/api/session.py`: Imported `FocusRunConfig`; `session_run()` bundles 5 Query params into a `FocusRunConfig` before passing to runner (HTTP API shape unchanged)
- `tests/conftest.py`: `make_stage_ctx` and `make_unit_runner` accept `focus_config: FocusRunConfig | None = None` instead of 5 flat params
- `tests/unit/domain/test_focus_run_config.py`: 12 new tests — defaults, `to_params()` field mapping, `skip` exclusion, invalid step raises
- 2 updated tests in `test_runner_stages.py`: use `FocusRunConfig` instead of flat params

**Tests:** 2565 pass (87% coverage)

---

## 2026-05-18 — BUG-013 — Mount connect retry + setup check actionable message

**What changed:**
- `smart_telescope/adapters/onstep/mount.py`: `connect()` now retries `:GVP#` up to 3 times (300 ms + buffer flush each attempt) before concluding the port is not OnStep. Handles the field-observed failure pattern where a stale `'1'` ACK from `disable_tracking()` (left from a previous session) caused the old single-retry to exhaust and close the serial port, leaving `_serial = None` and all subsequent state queries returning `UNKNOWN`.
- `smart_telescope/static/js/setup.js`: Mount RA and DEC setup check steps now show "mount not connected — use Connect All to reconnect" instead of the cryptic "state is 'unknown' — skipped" when the mount is unavailable.
- `tests/unit/adapters/onstep/test_onstep_mount.py`: 5 new tests in `TestConnectRetry` — first-attempt success (no sleep), stale-ACK retry succeeds, all-retries-exhausted returns False, empty response accepted, doubled product string accepted.

**Source:** `resources/hlrequirements/Items_to_fix_20260514.txt` BUG-013

**Tests:** 2553 pass (87% coverage)

---

## 2026-05-18 — BUG-010 — Focuser connect retry (serial buffer stale bytes)

**What changed:**
- `smart_telescope/adapters/onstep/focuser.py`: `connect()` now retries `:FA#` up to 3 times (300 ms apart) before concluding focuser unavailable. Handles stale bytes left in the serial input buffer by `mount.connect()` (`:GVP#` product query + `disable_tracking()`) that caused the first `:FA#` reply to be garbled.
- `tests/unit/adapters/onstep/test_onstep_focuser.py`: 4 new tests in `TestConnectRetry` — first-attempt hit (no sleep), 0→1 retry, all-retries-exhausted, empty-reply→available.

**Source:** `resources/hlrequirements/Items_to_fix_20260514.txt` BUG-010

**Tests:** 2548 pass (87% coverage)

---

## 2026-05-18 — BUG-011/012/016 — Park/unpark state propagation fix

**What changed:**

- `smart_telescope/services/device_state.py`: Added `self._mount` attribute (set in `start()`, cleared in `stop()`). Added `poll_now()` — runs `_poll_once()` synchronously on demand; no-op before `start()` or after `stop()`.

- `smart_telescope/services/mount_operations.py`: `park_sequence()` calls `device_state.poll_now()` after issuing the park command, before `wait_for_mount_state`. `unpark_sequence()` calls `device_state.poll_now()` after `mount.unpark()`, before `wait_while_mount_state`; timeout extended from 3 s → 5 s.

- `smart_telescope/runtime.py`: `connect_devices()` calls `self.device_state.poll_now()` immediately after `device_state.start()` — initial cache populated from startup, eliminating the 2 s gap (BUG-012).

- `smart_telescope/static/js/mount.js`: Park poll loop extended from 10×500 ms to 60×1000 ms (60 s total). Unpark loop extended to 20×500 ms (10 s). Both loops use a single `maxIter`/`delayMs` variable so the change is readable.

- `tests/unit/services/test_device_state.py`: Added `TestPollNow` class (5 tests) — updates cache immediately, reflects state change, handles exception gracefully, no-op before start, no-op after stop.

**Test result:** 2544 passed, coverage 87%.

---

## 2026-05-18 — BUG-005 + M5-005 — Crash isolation tests + solar gate closure

**What changed:**

- `tests/unit/api/test_bug005_isolation.py` (new, 10 tests): Explicit proof of isolation invariants — `TestStopBypassesCoordinatorLock` (STOP calls `mount.stop()` directly while coordinator is locked by a background thread); `TestSessionCrashReleasesResources` (mount/focuser/camera resources released from JobManager when runner thread raises WorkflowError); `TestStopWorksAfterSessionCrash` (mount STOP and focuser STOP both return 200 after session crash); `TestMountCommandsAfterSessionCrash` (mount goto and new session start return non-409 after crash).

- `docs/todo.md`: BUG-005 marked done; M5-005 marked done (implementation already existed across all four GoTo entry points with tests in test_mount.py and test_session.py).

**Test result:** 2539 passed, coverage 87%.

---

## 2026-05-18 — R5-011 — Hardware mode in readiness API + UI

**What changed:**

- `smart_telescope/runtime.py`: Added `_hardware_mode: str = "mock"` attribute to `RuntimeContext.__init__`; `_MODE_RANK` dict and mode assignment in `_build_adapters()` — each adapter branch sets `cam_mode`/`mnt_mode` ("real", "simulator", "mock") and the overall mode is the worst of both (mock > simulator > real) via `max(..., key=_MODE_RANK)`; `hardware_mode` property added; `reset_for_tests()` resets to "mock".

- `smart_telescope/services/readiness.py`: `ReadinessReport` gains `mode: str` field; `_get_hardware_mode()` reads from `RuntimeContext.hardware_mode` with fallback to "mock"; `_check_mode(mode)` returns a `ReadinessItem` (GREEN for real, YELLOW for simulator/mock with repair guidance); `can_observe` now requires both `overall != RED` and `mode == "real"`.

- `smart_telescope/static/index.html`: Added `<span id="s1-readiness-mode">` badge element in the readiness card header (hidden by default, shown/colored by JS).

- `smart_telescope/static/js/setup.js`: `_renderReadiness()` now shows the mode badge (REAL/SIMULATOR/MOCK) with color-coded border next to the overall badge.

- `tests/unit/api/test_readiness.py`: Added `TestHardwareMode` class (8 tests — mode field in API, real mode allows observe, mock/simulator blocks can_observe, mode item in items list, repair guidance, RuntimeContext defaults, reset); updated `test_yellow_overall_if_no_red_but_some_yellow` to patch `_get_hardware_mode` to "real".

- `docs/todo.md`: R5-011 marked done.

**Test result:** 2529 passed, coverage 87%.

---

## 2026-05-18 — R0-011 / R4-008 — Runner lifecycle + session optical-train aware

**What changed:**

- `smart_telescope/workflow/runner.py`: Removed `mount.disconnect()`, `camera.disconnect()`, `focuser.disconnect()` from `VerticalSliceRunner.run()` `finally` block. Runtime shutdown sequence (`RuntimeContext.shutdown()`) now owns all adapter teardown. Hardware stays live after a session completes or fails, enabling post-session diagnostics, retry, and dawn auto-park (M5-013).

- `smart_telescope/api/session.py`: Replaced hard-coded `{"camera:0", "mount", "focuser"}` resource claim with optical-train-aware resolution. `session_run` now injects `OpticalTrainRegistry` via `Depends(deps.get_optical_train_registry)`, calls `registry.main()`, and derives `camera_resource = f"camera:{main_train.camera_index}"`. Falls back to `"camera:0"` when no main train is configured. Camera adapter resolved via `deps.get_camera_by_role(main_train.camera_role)`.

- `tests/unit/workflow/test_focuser.py`: Updated `test_run_disconnects_focuser_on_completion` → `test_run_does_not_disconnect_focuser_on_completion` to assert the new contract.

- `tests/unit/api/test_r4_role_camera.py`: Added `TestSessionOpticalTrainAware` with 3 tests (main train at index 1 conflicts on `camera:1`; `camera:0` pre-claim does not conflict with main-at-1; empty registry falls back to `camera:0`). Imports extended with `CatalogObject`, `MountPort`, `get_runtime`.

- `docs/todo.md`: R0-011 and R4-008 marked done.

**Test result:** 2521 passed, coverage 87%.

---

## 2026-05-17 — Architect review integrated into docs/todo.md

**Source:** `resources/hlrequirements/development-state-review-2026-05-17.md`

**What changed in `docs/todo.md`:**

- M0-001 marked done: `docs/todo.md` is the established authoritative backlog.
- R0-011 added: change `VerticalSliceRunner.run()` to not disconnect adapters in `finally`; keep hardware live post-session (P1 Runtime).
- R4-008 added: make guided session optical-train aware — derive `camera:N` from selected train, remove `camera:0` hard-code (P1 Runtime).
- R5-011 added: explicit hardware mode field (`real`/`simulator`/`mock`) in readiness API and UI; `can_observe=true` blocked for mock/simulator mode (P1 Runtime).
- R6-007 added: `FocusRunConfig` policy object; clean focus sub-boundary (P2 Runtime).
- M5-005 enhanced: acceptance criteria now require solar exclusion at ALL GoTo entry points (direct GoTo, catalog launch, guided session, sky slew).
- M5-013 added: dawn auto-park at astronomical dawn; hardware stays connected after park (P2 Product).
- POD-005 enhanced: guidance examples added (ASTAP missing → observing blocked only; mount serial fail → preview + diagnostics still available).
- POD-007 answered: Pi hardware/app logs + saved FITS + session JSON log.
- POD-008 updated: minimal collimation wizard UI shell is part of MVP demo; deep algorithm phases deferred.
- POD-010 added: camera index in API request bodies — policy decision pending.
- Review header and source reference added to `docs/todo.md`.

**Reviewer note:** P1-001 finding ("pyproject.toml missing") was a reviewer environment issue — `pyproject.toml` exists at workspace root and `pip install -e .[dev]` was not run in the reviewer's environment. Not added as an action item.

---

## 2026-05-17 — R6-003 / R6-004 — JS module split + shared API client

**What changed:**

- `smart_telescope/static/index.html`: reduced from 6216 to 1847 lines (HTML/CSS only). The 4376-line JavaScript block replaced with 8 `<script src="/static/js/...">` tags. No logic changed — same code, now in separate files.

- `smart_telescope/static/js/` (new directory, 8 files):
  - `api.js` (87 lines, R6-004): `escHtml`, `_ERROR_PATTERNS`, `friendlyError`, `setStatus`, `apiPost` — shared fetch/error-handling layer, loaded first.
  - `app.js` (179 lines): global state, advanced mode, stage navigation, clock, `initSiteConfig`, init block — loaded last so it can call all other modules.
  - `mount.js` (721 lines): mount strip, mount card, mount actions, guide controls, polar alignment.
  - `collimation.js` (274 lines): collimation wizard UI, overlay drawing.
  - `focuser.js` (375 lines): focuser card, focuser actions, exposure controls, camera/train loading.
  - `preview.js` (954 lines): preview WebSocket, histogram canvas, autogain, guide autogain, Bahtinov overlay.
  - `session.js` (496 lines): session pipeline strip, guide monitor, target selection.
  - `setup.js` (1305 lines): readiness, health card, catalog, calibration, cooling, setup check, cameras, sky elevation, camera card.

- `smart_telescope/app.py`: added `StaticFiles` mount at `/static`.
- `pyproject.toml`: package-data updated to include `static/js/*`.
- `tests/unit/api/test_smoke.py`: 4 new tests verifying all 8 JS modules are served (200) and index.html references them. 43 tests total pass.

---

## 2026-05-17 — R6-006 / UX3-004 — API smoke tests + unsupported-control confirmation

**What changed:**

- `tests/unit/api/test_smoke.py` (R6-006 — new, 39 tests):
  - `TestSetupSmoke` (8 tests): `GET /` returns 200 HTML with correct title; `/api/readiness` returns 200 with `overall`/`items` in valid colour.
  - `TestMountSmoke` (11 tests): `/api/mount/status` returns `state`/`stale`/`watchdog_warning`/`last_command*` fields; state serialised lowercase; stale=false for fresh observation; watchdog=null with no alert. `/api/mount/config` returns location fields.
  - `TestFocuserSmoke` (7 tests): `/api/focuser/status` returns `position`/`available`/`moving`/`max_position`; available=True → real position; available=False → zeros.
  - `TestEmergencyStopSmoke` (8 tests): `POST /api/emergency_stop` always 200; `mount_stopped` true/false on success/error; `session_stopped` false when idle; `mount.stop()` called once.
  - `TestPreviewSmoke` (4 tests): optical trains list endpoint, version endpoint, catalog endpoint all respond.

- `docs/todo.md`: R6-006 marked done; UX3-004 confirmed done (already implemented via BUG-009/M3-004).

---

## 2026-05-17 — M1-004 — Hardware watchdog for stuck SLEWING

**What changed:**

- `smart_telescope/services/device_state.py`:
  - Added `_WATCHDOG_SLEW_S = 120.0` and `_WATCHDOG_COOLDOWN_S = 30.0` module constants.
  - `DeviceStateService.__init__`: added `_watchdog_warning` and `_watchdog_fired_at` fields.
  - `record_command()`: clears `_watchdog_warning` and `_watchdog_fired_at` on every new command.
  - `get_watchdog_warning()`: new public accessor (thread-safe).
  - `_poll_once()`: calls `_check_watchdog_locked()` inside the lock block after updating state.
  - `_check_watchdog_locked()`: fires a warning if mount stays `SLEWING` beyond `_WATCHDOG_SLEW_S`; suppresses repeated logs within `_WATCHDOG_COOLDOWN_S`; clears automatically when state leaves `SLEWING`.

- `smart_telescope/api/mount.py`: Added `watchdog_warning: str | None = None` to `MountStatus`; populated from `device_state.get_watchdog_warning()` in `mount_status()`.

- `smart_telescope/static/index.html` (`mountCard()`): Added yellow warning banner rendered when `data.watchdog_warning` is non-null.

- `tests/unit/services/test_device_state.py`: 4 new watchdog tests — below-threshold (no warning), above-threshold (fires), clears on state change, clears on new command. All 34 tests pass.

- `docs/todo.md`: M1-004 marked done.

---

## 2026-05-17 — COL-020/021, BUG-018/020, M4-004, UX4/UX5 — Wizard UI and logging fixes

**What changed:**

- `static/index.html` — Collimation Wizard panel (COL-020):
  - Wizard card added to Stage 4 above the two-column layout: 5-phase strip (Prepare/Acquire/Rough/Fine/Validate), instruction text, recommendation block, state badge.
  - Contextual controls: Start → Pause/Resume/Cancel → Remeasure|Finish Phase|Next → Accept|Adjust More → Reset.
  - Star list click in `select_star` state routes to `collimSelectStar()` → `/api/collimation/next {ra, dec}`.
  - Status polled every 2 s via `_startCollimPoll()` when session is active; auto-stops when terminal.
  - `_refreshCollimWizardOnce()` called in `goToStage(4)` to restore wizard state after navigation.

- `static/index.html` — Collimation overlay drawing (COL-021):
  - `_drawCollimOverlay(d)` renders on `s4-bahtinov-svg`: donut outer ring (blue), inner hole (green), error-vector red arrow; Bahtinov crossing-point crosshair (red); overlay fetched from `/api/collimation/overlay` alongside status poll.

- `static/index.html` — Advanced Mode (UX4-001/002/003):
  - `.adv-only { display: none !important; }` / `body.advanced-mode .adv-only { display: flex !important; }`.
  - "Advanced" toggle in header; mount Home/Unpark/Park/Tracking and focuser nudge/Move-To hidden in beginner mode.

- `static/index.html` — Diagnostics link in errors (UX5-005):
  - `setStatus(..., true)` appends "→ Setup & Diagnostics" link on every error banner.

- `services/mount_operations.py` (BUG-018): Added `_log.info("Mount unpark issued")` in `unpark_sequence()`.
- `api/focuser.py` (BUG-020): Added `_log.info("Focuser nudge request: delta=%d", body.delta)` at entry of `focuser_nudge()`.
- `docs/todo.md`: M4-004, BUG-018, BUG-020, COL-020/021 marked done.

**Tests:** 2471 passed, 0 failed. Coverage 87%.

---

## 2026-05-17 — UX3-003, UX4-001/002/003, UX5-005 — Advanced mode and diagnostics link

**What changed:**

- `static/index.html` — Advanced Mode toggle (UX4-001/002/003):
  - Added `.adv-only { display: none; }` + `body.advanced-mode .adv-only { display: flex; }` CSS.
  - "Advanced" button in header toggles `body.advanced-mode` class; state persisted in `localStorage['tsc_advanced_mode']`.
  - `_applyAdvancedMode()` called at page init to restore prior session state.
  - `mountCard()`: Home / Unpark / Park / Enable Tracking / Disable Tracking wrapped in `.adv-only` span. Stop always visible.
  - `focuserCard()`: Nudge buttons (±1000/±100/±10) and Move To row wrapped in `.adv-only`. Autofocus and Stop always visible.

- `static/index.html` — Diagnostics link in errors (UX5-005):
  - `setStatus(id, msg, true)` now appends a "→ Setup & Diagnostics" link calling `goToStage(1)` after every error message.

- UX3-003 confirmed done: camera hardware IDs / serial numbers displayed only in `cameraCard()` (Stage 6 scan). All main UI selects and labels use optical train role names.

---

## 2026-05-17 — R6-001/002 Service extraction

**What changed:**

- `services/cooling.py` (new, R6-001): `CoolingService` extracted from
  `api/cooling.py`. Owns `_Session` dataclass, threading lock, polling loop,
  `_stop_session` (with lock-release during join to prevent deadlock).
  Public API: `start(camera, camera_index, target_c)`, `stop()`,
  `get_status() → CoolingStatus`.

- `api/cooling.py` (R6-002): Reduced from 251 → 86 lines. Now a thin wrapper:
  validate TEC capability, call `CoolingService`, map `CoolingStatus` to
  response model. `_reset()` delegates to `svc.stop()`.

- `services/mount_operations.py` (new, R6-001): Mount orchestration module with
  `MountSlewingError` exception and five sequence functions:
  `safe_goto`, `unpark_sequence`, `track_sequence`, `park_sequence`,
  `home_sequence`. Accepts domain-level objects; raises domain exceptions
  (no HTTP concerns).

- `api/mount.py` (R6-002): `_safe_goto`, `mount_unpark`, `mount_track`,
  `mount_home`, `mount_park` endpoints now delegate to `mount_operations` and
  map domain exceptions to HTTP. `Time` / `is_solar_target` imports kept at
  the API level to preserve existing test patch targets.

- `runtime.py`: `CoolingService` added to `__init__`, `shutdown()`, and
  `reset_for_tests()`.

- `api/deps.py`: Added `get_cooling_service()`.

- `tests/unit/services/test_cooling_service.py` (new): 21 tests covering
  idle state, start/stop lifecycle, restart, polling, and thread safety.

- `tests/unit/services/test_mount_operations.py` (new): 22 tests covering
  safe_goto, unpark_sequence, track_sequence, park_sequence, home_sequence —
  including domain exception propagation and coordinator conflict detection.

**Tests:** 2471 passed, 0 failed. Coverage 87%.

---

## 2026-05-17 — R1-006, R1-008/009, BUG-002b, BUG-015 (continued)

**What changed:**

- `services/device_state.py` (R1-006): `record_command()` now returns a
  sequential command ID (`cmd-NNNN` format). Added `_cmd_counter` and
  `_last_command_id` to `__init__`. Both `record_command()` and
  `record_command_error()` emit structured `key=value` log lines including the
  command ID for log correlation. New `get_last_command_id()` method exposes the
  last ID to callers.

- `tests/unit/services/test_device_state.py` (R1-006): 7 new tests covering
  ID format, uniqueness, sequential ordering, `get_last_command_id()` initial
  state and match, and caplog assertions for both `record_command` and
  `record_command_error`. All 30 device-state tests pass.

- `adapters/onstep/serial_bus.py` (R1-008): New `OnStepSerialBus` class owns
  the `serial.Serial` object and threading lock previously private to
  `OnStepMount`. Exposes `send()`, `raw_send()`, `write_bypass()`.

- `adapters/onstep/mount.py` (R1-009): Replaced `self._serial`/`self._lock`
  with `self._bus = OnStepSerialBus()`. Added `_serial` property (getter/setter)
  proxying to `self._bus._serial` for backward compatibility with existing tests.
  Added `serial_bus` property for consumers.

- `adapters/onstep/focuser.py` (R1-009): Constructor now accepts
  `OnStepSerialBus` instead of `OnStepMount`. All serial I/O goes through the
  bus directly — no access to mount private members.

- `runtime.py` (R1-009): Updated `OnStepFocuser(mount)` → `OnStepFocuser(mount.serial_bus)`.

- `api/autogain.py` (BUG-002b): `get_status()` now returns
  `AUTO_GAIN_CANCELLED` when `job.cancelling=True` even if the worker completed
  with a non-CANCELLED result before seeing the cancel flag (cancel race fix).

- `static/index.html` (BUG-015): Mount Home/Unpark/Park/Stop buttons wrapped
  in a `flex-wrap:nowrap` span to prevent wrapping into multiple rows on narrow
  viewports.

- `tests/unit/services/test_pipeline_wiring.py`: Added missing `_donut_camera()`
  helper (was referenced but never defined — pre-existing `NameError`).

**Tests:** 2436 passed, 0 failed.

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

---

## 2026-05-17 — UX2-001..004 (Intent-Based Observation Flow)

**What changed:**

- `smart_telescope/static/index.html`:
  - Stage 5 card title updated from "Run Observation" to "Start Observation" (UX2-001).
  - Added a 5-step pipeline strip inside the run-status panel (UX2-002):
    Connect → GoTo → Centre → Focus → Capture. Each step updates live to
    pending / active (blue) / done (green, ✓) / failed (red, ✗) as the session
    progresses through `SessionState` transitions.
  - Added recovery banner inside the run-status panel (UX2-004): shown when
    `state=FAILED`; displays failure reason, a contextual action suggestion keyed
    on `failure_stage`, and a ↺ Retry button that re-runs `s5StartSession()`.
  - `_s5UpdateSteps(data)`: new function mapping `SessionState` → active step and
    `failure_stage` → failed step; also drives the recovery banner.
  - `_s5ResetRunUI()`: extended to reset step strip and hide recovery banner on
    session start.
  - CSS: new `.s5-step`, `.s5-step-circle`, `.s5-step-label`, `.s5-step-line`
    classes with `.step-active`, `.step-done`, `.step-failed`, `.line-done` modifiers.
  - UX2-003 (automatic sequencing of autofocus/solve/recenter) is already
    implemented in `VerticalSliceRunner`; the pipeline strip now makes this visible.

- `docs/todo.md`: UX2-001, UX2-002, UX2-003, UX2-004 marked complete.

---

## 2026-05-17 — UX4-004, R6-005, UX5-001..004 (global STOP + error model)

**What changed:**

- `smart_telescope/static/index.html`:
  - Mount strip now carries `class="visible"` in HTML so it is shown from page
    load; `goToStage()` no longer removes `visible` when navigating to Stage 1.
    Emergency STOP button is now globally visible at all times (UX4-004 / R6-005).
  - Added `_ERROR_PATTERNS` array and `friendlyError(raw)` function (UX5-001):
    pattern-matches raw error strings to `{message, hint}` pairs in three
    categories — mount/OnStep (UX5-002), camera (UX5-003), solver (UX5-004).
  - `setStatus(..., isError=true)` now calls `friendlyError()` and renders the
    translated message with an optional hint in a smaller muted line beneath it.
    All existing error callsites benefit automatically (park, unpark, goto, home,
    connect, autofocus, etc.).

- `docs/todo.md`: UX4-004, R6-005, UX5-001..004 marked complete.

---

## 2026-05-17 — M4-002 (Visible Tonight target card)

**What changed:**

- `smart_telescope/static/index.html`:
  - Added "Visible Tonight" card to Stage 5 (M4-002): fetches
    `GET /api/catalog/tonight?min_altitude=20&limit=12` and renders a
    clickable list of Messier objects above 20° at the current time, sorted by
    altitude. Each row shows the object name, common name, type chip (e.g.
    "Galaxy", "Glob. Cluster"), altitude in degrees, and a ☀ warning icon for
    objects with `solar_safe=false`.
  - `s5LoadTargets()`: async function that drives the card; dot indicator shows
    yellow while loading, green on success, red on error, grey when list is empty.
  - `s5UseTarget(name)`: clicking a row copies the name into the target input and
    moves focus to the Start Session button with a brief status message.
  - `goToStage(5)` now calls `s5LoadTargets()` so the card auto-loads on entry.
  - CSS: `.tonight-row`, `.tonight-name`, `.tonight-type-chip`, `.tonight-alt`
    for list layout.

- `docs/todo.md`: M4-001..003, M4-005, M4-006 marked complete.

---

## 2026-05-17 — R1-008, R1-009 (OnStep serial bus abstraction)

**What changed:**

- `smart_telescope/adapters/onstep/serial_bus.py` (new): `OnStepSerialBus` owns
  the `serial.Serial` handle and `threading.Lock` that were previously private
  attributes of `OnStepMount`. Exposes three public methods:
  - `send(cmd) -> str` — locked write + readline, decoded and stripped.
  - `raw_send(cmd) -> bytes` — locked write + readline, raw bytes.
  - `write_bypass(data: bytes) -> None` — lockless write for emergency-stop
    commands (:Q#, :FQ#) that must interrupt an in-progress command.

- `smart_telescope/adapters/onstep/mount.py`:
  - Replaced `self._serial` + `self._lock` with `self._bus: OnStepSerialBus`.
  - Added a `_serial` property (getter + setter) so existing tests that inject
    `mount._serial = fake` continue to work without changes.
  - Added `serial_bus` public property for `OnStepFocuser` to consume.
  - `_raw_send` / `_send` now delegate to bus; `stop()` calls
    `self._bus.write_bypass(b":Q#")`.
  - `connect()` creates the `serial.Serial` object locally and assigns it to
    `self._bus._serial`; product check logic is unchanged.

- `smart_telescope/adapters/onstep/focuser.py`:
  - Constructor signature changed from `OnStepFocuser(mount: OnStepMount)` to
    `OnStepFocuser(bus: OnStepSerialBus)`. No more private-member access.
  - All `self._mount._send(...)` / `._raw_send(...)` / `._serial` calls replaced
    with `self._bus.send(...)` / `.raw_send(...)` / `.write_bypass(...)`.

- `smart_telescope/runtime.py`: Updated `OnStepFocuser(mount)` →
  `OnStepFocuser(mount.serial_bus)`.

- `tests/unit/adapters/onstep/test_onstep_focuser.py`:
  - Replaced `MagicMock(spec=OnStepMount)` with `MagicMock(spec=OnStepSerialBus)`.
  - `stop()` test now asserts `bus.write_bypass.assert_called_once_with(b":FQ#")`
    instead of reaching into a mock serial attribute.

- `tests/unit/adapters/onstep/test_onstep_mount.py`: no changes needed — the
  `"smart_telescope.adapters.onstep.mount.serial.Serial"` patch target is still
  valid because `connect()` still lives in mount.py.

- `tests/unit/adapters/onstep/test_with_fake_serial.py`: no changes needed — the
  `_serial` property setter makes `mount._serial = fake` transparently update the
  bus.

**Test result:** 2415 passed (pre-existing `test_frame_counter_increments_on_donut_measurement` excluded).

- `docs/todo.md`: R1-008, R1-009 marked complete.

---

## 2026-05-17 — BUG-002b, BUG-015 (autogain cancel + mount button grouping)

**What changed:**

- `smart_telescope/api/autogain.py` (BUG-002b):
  - `GET /api/autogain/status`: when `job.cancelling=True` and the result status
    is not `AUTO_GAIN_CANCELLED`, the endpoint now returns `AUTO_GAIN_CANCELLED`
    instead of the actual result. This prevents a race where the background
    worker finishes with `POSSIBLE_FOCUS_OR_POINTING_ERROR` just as the cancel
    request arrives, which would cause the UI to show the warning badge after
    the user clicked Cancel.

- `tests/unit/api/test_autogain.py`: added
  `test_status_returns_cancelled_when_job_completed_after_cancel_request` to
  `TestCancelEndpoint`, directly exercising the race scenario.

- `smart_telescope/static/index.html` (BUG-015):
  - `mountCard()`: wrapped the Home / Unpark / Park / Stop buttons in a
    `<span style="display:flex;gap:0.5rem;flex-wrap:nowrap">` so they are
    always visually grouped and never wrap independently onto separate lines
    when the controls row is narrow.

**Test result:** 2416 passed.

- `docs/todo.md`: BUG-002b, BUG-015 marked complete.

---

## 2026-05-21 — Camera ID Mapping + Camera Offset Configuration

**Sources:** `resources/hlrequirements/camera_id list.md`, `resources/hlrequirements/camera_offset.md`

**Camera ID Mapping (CID-001..005):**
- `config.py`: `_parse_cameras()` accepts `str|int`; `CAMERAS`, `TOUPTEK_INDEX`, `CAMERA_SERIALS` globals
- `CameraNameResolver`: case-insensitive substring + serial verification; wired into `runtime._build_adapters()`
- `templates/config.toml`: `[cameras]` now uses model name as default; `[camera_serials]` block added

**Camera Offset Configuration (CO-001..006):**
- `config.py`: `_parse_camera_offsets()` and `CAMERA_OFFSETS`
- `CameraOffsetService`: lookup by model+gain (bidirectional substring); `apply()` sets `set_black_level`
- `RuntimeContext`: `_apply_camera_offsets()` called in `connect_devices()` and `get_preview_camera()`
- `AutoGainService.run_one_shot()`: `offset_service` param; `cur_offset` seeded from configured value
- `calibration_capture.py`: `offset_service` param on `prepare_bias/dark/flat`; API passes `rt.camera_offset_service`
- `templates/config.toml`: `[camera_offsets]` section with defaults for G3M678M/ATR585M (150) and GPCMOS02000KPA (10)

---

## 2026-05-17 — Fix pre-existing test failure in test_pipeline_wiring.py

**What changed:**

- `tests/unit/services/test_pipeline_wiring.py`: added `_donut_camera()` helper
  (an alias for `_star_then_donut_camera()`) which was referenced by
  `TestFinePipeline::test_frame_counter_increments_on_donut_measurement` but
  never defined, causing a persistent `NameError` since the test was committed.

**Test result:** 2429 passed (all tests green, no exclusions needed).
