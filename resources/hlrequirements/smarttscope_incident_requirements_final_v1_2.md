# SmartTScope — Finalized Incident and Requirements Document

Version: 1.2  
Date: 2026-06-25  
Status: Finalized implementation draft  
Scope: Incident-driven runtime, UI, API, diagnostics, plate-solving, click-to-center and GitHub delivery requirements for SmartTScope.

---

## 1. Purpose

This document consolidates the SmartTScope incident observations into final, testable requirements.

The main problem pattern is not a single failing function. It is an inconsistent state and trust model around:

- OnStep adapter connection versus mount operational readiness;
- OnStep time/location verification versus Raspberry Pi time trust;
- operation gates for GoTo, sync, tracking, collimation, plate solving and click-to-center;
- insufficient Stage 1 visibility;
- weak diagnostics for auto-gain, autofocus, collimation and plate solving;
- missing command history;
- missing reproducibility through diagnostic FITS frames and structured logs;
- incomplete GitHub delivery visibility.

SmartTScope shall be able to explain every disabled function, rejected command and failed setup step directly in the UI and logs.

---

## 2. Finalized design decisions

### DEC-001 — Runtime state shall be explicit and split into separate concerns

SmartTScope shall not use a single generic `connected` or `ready` flag for mount behavior.

The following state categories shall be modeled separately:

1. adapter connection state;
2. adapter health-check state;
3. mount operational state;
4. OnStep time/location verification state;
5. Raspberry Pi time trust state;
6. operation-gate state per protected operation.

### DEC-002 — Stage 1 is mandatory for mount automation

Stage 1 time/location and trust evaluation shall be mandatory before:

- enabling tracking;
- GoTo;
- bright-star GoTo;
- automatic sync;
- plate-solve based mount correction;
- mount-assisted collimation target slewing.

Stage 1 shall not be mandatory for:

- camera-only preview;
- manual image inspection;
- collimation preview without mount movement;
- reviewing diagnostics and logs.

### DEC-003 — Raspberry Pi time trust is separate from OnStep verification

Raspberry Pi time trust and OnStep time/location verification are related but not identical.

Raspberry Pi time may be trusted through:

- NTP synchronization;
- GPS fix from `gpsd`;
- explicit user confirmation;
- comparison with an already trusted OnStep time source.

A successful push of Raspberry Pi time/location to OnStep shall **not** by itself make Raspberry Pi time trusted.

### DEC-004 — Raspberry Pi time trust shall not be blindly persisted

Raspberry Pi time trust shall be recalculated on application startup.

Trust evidence may be logged and persisted for diagnostics, but an old trust result shall not automatically make a new session trusted.

Within a running session, trust shall have a timestamp and source. If the trust source becomes stale, unavailable or contradicted, the trust state shall be recalculated.

Recommended default:

```toml
[time_trust]
persist_trust_across_restart = false
session_trust_expiry_minutes = 120
```

### DEC-005 — User-confirmed time may allow GoTo, but only with explicit warning

If NTP and GPS are unavailable, the user may manually confirm Raspberry Pi time.

Manual confirmation shall allow GoTo only after the UI displays a clear warning that local time is being trusted by user confirmation.

Manual confirmation shall be:

- logged;
- shown as trust source `USER_CONFIRMED`;
- valid only for the current session or until configured expiry;
- revocable by rerunning Stage 1.

### DEC-006 — OnStep comparison alone is not enough unless OnStep is trusted

A comparison between Raspberry Pi time and OnStep time can make Raspberry Pi time trusted only if OnStep time is already trusted or explicitly accepted by the user as reference.

Two unknown but matching clocks shall not automatically create a trusted state.

Allowed trust source:

```text
ONSTEP_COMPARISON
```

Condition:

```text
OnStep time must be trusted through GPS, NTP, previous verified Stage 1 result in current session, or explicit user acceptance.
```

### DEC-007 — GoTo requires Raspberry Pi time trust if SmartTScope calculates target visibility

Bright-star GoTo and object-selection GoTo shall require Raspberry Pi time trust because SmartTScope calculates local target visibility and target coordinates.

Direct RA/DEC GoTo may be allowed with explicit user override if:

- OnStep time/location is verified;
- mount is connected and unparked;
- the user accepts that SmartTScope is not validating target visibility locally.

Default policy:

```toml
[operation_policy]
allow_direct_radec_goto_without_raspberry_time_trust = false
```

### DEC-008 — Location tolerance shall be meter-based

The primary OnStep location tolerance shall be configured in meters.

Default:

```toml
[mount]
onstep_location_tolerance_m = 100
```

Degree-based tolerance may exist only as a backward-compatible fallback.

### DEC-009 — Collimation preview does not require trusted time

Camera-only collimation preview shall be allowed without trusted Raspberry Pi time.

Mount-assisted actions remain gated:

- slew to selected target star;
- click-to-center;
- tracking enable;
- automatic mount correction.

### DEC-010 — Click-to-center is allowed with tracking on or off

Click-to-center shall be available with tracking on and tracking off.

If tracking is off, SmartTScope shall display and log a drift warning.

Click-to-center shall be iterative, bounded and cancelable.

### DEC-011 — Click-to-center shall be blocked while parked

Click-to-center shall be blocked while the mount is parked.

Reason:

- centering requires mount movement;
- parked state shall remain a hard safety state;
- the user shall explicitly unpark before mount movement.

### DEC-012 — Initial click-to-center limits

Initial conservative defaults:

```toml
[click_to_center]
max_iterations = 5
center_tolerance_px = 20
max_single_move_px = 300
start_with_fraction_of_calculated_move = 0.5
```

SmartTScope may suggest updated values after calibration, but shall not write them to `config.toml` without user confirmation.

### DEC-013 — Diagnostic frame storage defaults to debug-or-failure

Diagnostic FITS frame storage shall default to storing frames in debug mode or on failures.

Default:

```toml
[diagnostics.frames]
enabled = true
store_mode = "debug_or_failure"
retention_days = 2
```

Successful setup frames shall not be stored outside debug mode by default.

### DEC-014 — ASTAP pre-check shall be configurable and non-blocking by default

The minimum local star count before ASTAP shall be configurable.

Recommended default:

```toml
[plate_solve]
min_detected_stars_before_solve = 15
allow_astap_below_min_star_count = true
```

Reason:

- SmartTScope’s local detector may undercount compared with ASTAP;
- ASTAP should still be allowed to try when metadata is valid;
- the local count shall be logged and used for diagnostics.

### DEC-015 — Plate-solve exposure capability test default sequence

SmartTScope shall provide a diagnostic exposure capability test for plate solving.

Default sequence:

```text
0.5 s, 1 s, 2 s, 4 s, 8 s
```

Default maximum exposure:

```toml
[plate_solve.exposure_capability_test]
max_exposure_s = 8
```

The test shall stop early if star elongation, FWHM/HFR degradation or saturation exceeds configured limits.

### DEC-016 — Active camera definition for Extended Setup Check

A camera is considered active for Extended Setup Check if:

- it is configured with `enabled = true`;
- it is assigned to an optical train or setup role;
- it is detected by the ToupTek SDK at runtime;
- it is not explicitly disabled in the UI.

Disconnected configured cameras shall be reported as disconnected, not failed.

### DEC-017 — GitHub delivery audit belongs to development workflow and CI

GitHub delivery completeness is a development-process requirement, not telescope runtime behavior.

It shall be implemented as:

- local development script;
- CI pipeline check;
- Codex/development workflow checklist.

It shall not be part of the SmartTScope runtime telescope-control application.

### DEC-018 — Keep this document together until incident closure

This document shall remain a single incident-driven requirements document until the current issue cluster is closed.

After closure, it may be split into:

- runtime requirements;
- UI/API requirements;
- diagnostics requirements;
- development delivery requirements.

---

## 3. Incident summary

### INC-001 — Mount connected but UI reports “Mount not connected”

Observed behavior:

- Backend reports that OnStep is already open.
- Focuser is already available.
- `/api/session/connect` returns HTTP 200.
- UI still reports:

```text
Mount not connected
Use Connect All on Stage 1 to reconnect
```

Required correction:

- UI shall distinguish disconnected from connected-but-restricted.
- Reconnect instructions shall be shown only when reconnecting can actually help.

---

### INC-002 — Time/location reports VERIFIED although deltas look too large

Observed behavior:

```text
Time/location check: within tolerance — VERIFIED
time_delta=1.3s lat_delta=0.0027° lon_delta=0.0337°
```

Required correction:

- Verification shall follow the numeric tolerance condition.
- Active tolerance shall be logged.
- Meter-based tolerance shall be used as primary check.
- Log encoding shall be valid UTF-8.

---

### INC-003 — GoTo fails with `raspberry_time_plausible_not_trusted`

Observed behavior:

```text
GoTo Altair failed: raspberry_time_plausible_not_trusted
POST /api/mount/goto HTTP/1.1" 409 Conflict
```

Required correction:

- Raspberry Pi time trust shall be visible.
- Trust source shall be visible.
- GoTo shall show a clear remedy.
- Blocked commands shall be recorded as rejected, not issued.

---

### INC-004 — Extended Setup Check reports `0/3 camera(s) solved`

Observed behavior:

```text
0/3 camera(s) solved
main: ✗
guide: ✗
oag: ✗
```

Required correction:

- Report per-camera details.
- Distinguish skipped, disconnected, inactive, blocked, capture failed, auto-gain failed, ASTAP failed and solved.
- Save and reference diagnostic FITS frames when relevant.

---

### INC-005 — Requested sequence is not visible

Observed behavior:

```text
command issued command_id=cmd-0004 command='goto ra=19.8463h dec=8.87°'
POST /api/mount/goto HTTP/1.1" 409 Conflict
```

Required correction:

- Every user-requested action shall appear in command history.
- Rejected commands shall be visible with rejection reason.
- Backend shall not log rejected pre-gate commands as issued.

---

### INC-006 — Collimation wizard blocked by Raspberry time trust

Required correction:

- Collimation preview shall work if camera capture works.
- Slew-to-target and mount-assisted centering remain gated.

---

### INC-007 — Defocus collimation mode missing

Required correction:

- UI shall show both `Bahtinov Preview` and `Defocus Donut` modes.
- Correct spelling is `Bahtinov`.

---

### INC-008 — Auto-gain insufficient for ASTAP

Required correction:

- Plate-solve auto-gain shall optimize for detectable stars.
- Long exposure shall be limited by measured tracking quality.
- Failure diagnostics shall explain whether exposure, gain, saturation, focus, tracking blur, metadata or ASTAP caused failure.

---

### INC-009 — Stage 1 process not visible

Required correction:

- Stage 1 shall show master source, OnStep values, Raspberry trust, deltas, tolerances, push actions and verification result.

---

### INC-010 — Missing per-section logs and diagnostic frames

Required correction:

- Use per-section logs.
- Store service requests/responses.
- Store FITS frames for debug or failure cases.
- Reference frame filenames in logs.

---

### INC-011 — Missing click-to-center

Required correction:

- The user shall be able to click a star or donut in collimation, plate-solve and autofocus views.
- SmartTScope shall refine the click position and iteratively center the target if movement gates pass.

---

### INC-012 — GitHub source not pushed with implementation note

Required correction:

- Development delivery shall verify that source, tests and relevant documentation were committed and pushed.

---

## 4. State model requirements

### REQ-STATE-001 — Separate state categories

SmartTScope shall expose these states separately:

```text
adapter_connection_state
adapter_health_state
mount_operational_state
onstep_time_location_state
raspberry_time_trust_state
operation_gate_states
```

Acceptance criteria:

- `/api/status` exposes all categories.
- `/api/mount/status` exposes adapter and health state separately.
- UI does not use one generic mount-connected flag for all decisions.
- Connected-but-restricted state is shown as connected but restricted.

---

### REQ-STATE-002 — Derived mount readiness state

Allowed readiness states:

```text
DISCONNECTED
CONNECTED_HEALTH_UNKNOWN
CONNECTED_RESTRICTED
CONNECTED_READY
CONNECTED_TIME_LOCATION_UNVERIFIED
CONNECTED_RASPBERRY_TIME_UNTRUSTED
ERROR
```

Acceptance criteria:

- `Mount not connected` is shown only when adapter is closed or health check fails.
- Trust failures are shown as trust failures, not connection failures.
- Reconnect guidance is shown only when reconnecting can resolve the state.

---

### REQ-STATE-003 — Operation gate service

Every protected operation shall be checked through a common operation-gate service.

Minimum gated operations:

```text
camera_capture
manual_mount_move
tracking_enable
goto
bright_star_goto
sync
plate_solve
plate_solve_mount_correction
collimation_preview
collimation_slew_to_target
collimation_mount_centering
autofocus
click_to_center
```

Gate response:

```text
allowed
reason_code
human_message
required_user_action
blocking_states
```

Acceptance criteria:

- HTTP 409 responses use the gate result.
- Disabled UI controls show the gate result.
- Logs include gate input and output.
- Rejected commands are not logged as issued.

---

## 5. Stage 1 time/location and trust requirements

### REQ-TIME-001 — Master source selection

SmartTScope shall choose master source in this order:

1. GPS fix from `gpsd`, if available.
2. NTP-synchronized Raspberry Pi time plus configured site location.
3. User-confirmed Raspberry Pi time plus configured site location.
4. Configured fallback site location with untrusted time state, only for camera-only workflows.

Acceptance criteria:

- Master source is visible in UI and logs.
- GPS fix is used when available.
- Untrusted fallback time does not unlock mount automation.

---

### REQ-TIME-002 — Raspberry Pi time trust sources

Allowed Raspberry Pi time trust sources:

```text
NTP
GPSD_FIX
USER_CONFIRMED
ONSTEP_COMPARISON
NOT_TRUSTED
```

Rules:

- `NTP`: accepted if OS reports synchronized time.
- `GPSD_FIX`: accepted if `gpsd` reports a fix.
- `USER_CONFIRMED`: accepted only after explicit user confirmation.
- `ONSTEP_COMPARISON`: accepted only if OnStep time is itself trusted or user explicitly accepts OnStep as the reference.
- `NOT_TRUSTED`: default state.

Acceptance criteria:

- UI shows trust source.
- Logs show trust source and timestamp.
- Manual confirmation shows a warning.
- Pushing time to OnStep does not automatically create Raspberry time trust.

---

### REQ-TIME-003 — OnStep verification

OnStep time/location is `VERIFIED` only if all checks pass:

```text
abs(time_delta_s) <= onstep_time_tolerance_s
location_delta_m <= onstep_location_tolerance_m
```

Default config:

```toml
[mount]
onstep_time_tolerance_s = 10
onstep_location_tolerance_m = 100
```

Acceptance criteria:

- `lat_delta=0.0027°` fails at 100 m tolerance.
- `lon_delta=0.0337°` fails at 100 m tolerance.
- Active tolerances are logged.
- Boundary tests cover below, equal and above tolerance.

---

### REQ-TIME-004 — User push to OnStep

If OnStep time/location exceed tolerance, the user shall be asked whether the selected master values shall be pushed to OnStep.

Acceptance criteria:

- Prompt shows OnStep values, master values, deltas and tolerances.
- Push uses the OnStep adapter library.
- Push result is logged.
- Verification is rerun after push.
- Push success verifies OnStep against the chosen master.
- Push success does not automatically make Raspberry Pi time trusted.

---

### REQ-TIME-005 — Stage 1 UI panel

Stage 1 shall show:

```text
OnStep adapter state
OnStep health state
Focuser state
Raspberry Pi time trust
Raspberry Pi trust source
GPS fix availability
selected master source
OnStep time
master time
time delta
OnStep location
master location
location delta in meters
active tolerances
verification result
last verification timestamp
last push timestamp
available actions
```

Acceptance criteria:

- User sees whether Stage 1 ran.
- User sees why it passed or failed.
- User can rerun the check.
- User can manually confirm Raspberry time if enabled.
- User can push time/location to OnStep if allowed.

---

### REQ-TIME-006 — UTF-8-safe logs

Logs shall use valid UTF-8.

Acceptance criteria:

- No mojibake such as `窶・`, `竊・` or `ﾂｰ` appears in logs.
- Degree values are logged as valid `°` or ASCII `deg`.
- Automated tests check representative log lines.

---

## 6. Connection and Connect All requirements

### REQ-CONN-001 — `Connect All` idempotency

`Connect All` shall be idempotent.

Acceptance criteria:

- Repeated calls reuse existing OnStep connection.
- Repeated calls reuse existing focuser connection.
- Repeated calls do not create contradictory UI state.
- Result changes only if hardware or health state changes.

---

### REQ-CONN-002 — Health-check based connected status

`/api/mount/status.connected` shall be true only if:

```text
adapter_open == true
health_check_ok == true
```

Acceptance criteria:

- Adapter-open but health-failed is reported explicitly.
- Workflow stage cannot override health-check result.
- UI derives mount connection from backend status, not local stale state.

---

### REQ-CONN-003 — Correct reconnect guidance

Reconnect guidance shall be shown only for actual connection or health failures.

Acceptance criteria:

- Connected-but-restricted state does not show reconnect prompt.
- Time trust failures show Stage 1 remedy.
- OnStep verification failures show Stage 1 remedy.

---

## 7. GoTo and command history requirements

### REQ-GOTO-001 — Gate before command issue

GoTo shall be gate-checked before it is marked as issued.

Acceptance criteria:

- Blocked GoTo is recorded as `REJECTED`.
- It is not logged as `ISSUED`.
- 409 response includes structured diagnostics.
- Command history records rejection.

---

### REQ-GOTO-002 — Bright-star GoTo preconditions

Bright-star GoTo shall require:

```text
mount_connected
mount_health_ok
raspberry_time_trusted
onstep_time_location_verified
mount_unparked
target_above_horizon
goto_gate_allowed
```

Acceptance criteria:

- Failed precondition is visible.
- Target RA/DEC and altitude are logged if calculated.
- If target visibility depends on Raspberry time, Raspberry time must be trusted.

---

### REQ-GOTO-003 — Direct RA/DEC GoTo policy

Direct RA/DEC GoTo shall follow policy:

```toml
[operation_policy]
allow_direct_radec_goto_without_raspberry_time_trust = false
```

Acceptance criteria:

- Default behavior blocks direct RA/DEC GoTo without Raspberry time trust.
- If policy is enabled, user receives explicit warning.
- OnStep time/location must still be verified.
- Mount must be connected, healthy and unparked.

---

### REQ-CMD-001 — Command history

SmartTScope shall provide command history for all requested, rejected, issued, completed, failed and cancelled commands.

Each record shall include:

```text
command_id
session_id
timestamp
user_action
operation
requested_parameters
status
reason_code
human_message
backend_response
related_log_file
related_frame_file_if_any
```

Valid statuses:

```text
REQUESTED
REJECTED
ISSUED
RUNNING
SUCCEEDED
FAILED
CANCELLED
```

Acceptance criteria:

- Rejected commands are visible in requested sequence.
- User can distinguish blocked commands from hardware failures.
- Command history is persisted per session as JSONL.

---

## 8. UI requirements

### REQ-UI-001 — Disabled controls show exact reason

Disabled controls shall show the reason returned by operation gates.

Applies to:

```text
goto
bright_star_goto
sync
tracking_enable
plate_solve
plate_solve_correction
collimation_slew_to_target
click_to_center
autofocus
```

Acceptance criteria:

- Each disabled control has visible reason or tooltip.
- Reason comes from backend gate result.
- UI refreshes after Stage 1 changes.
- Stale frontend state cannot keep controls disabled.

---

### REQ-UI-002 — Collimation modes

The collimation wizard shall expose:

```text
Bahtinov Preview
Defocus Donut
```

Acceptance criteria:

- `Bahtinov` is spelled correctly.
- Defocus mode is visible if optical train supports it.
- If unavailable, reason is shown.

---

### REQ-UI-003 — Collimation preview without time trust

Camera-only collimation preview shall work without Raspberry Pi time trust.

Acceptance criteria:

- Preview opens if camera capture works.
- Manual visual collimation remains possible.
- Slew-to-target remains gated.
- Mount-assisted centering remains gated.

---

## 9. Extended Setup Check and plate-solving requirements

### REQ-SETUP-001 — Active camera scope

Extended Setup Check shall evaluate all active cameras.

A camera is active if:

```text
enabled in config
assigned to an optical train or setup role
detected by ToupTek SDK
not disabled in UI
```

Acceptance criteria:

- Disconnected configured cameras are reported as `disconnected`.
- Inactive cameras are reported as `inactive` or skipped with reason.
- Active connected cameras are checked.

---

### REQ-SETUP-002 — Per-camera diagnostic report

For each checked camera/optical train, report:

```text
camera_id
role
optical_train_id
camera_connected
camera_active
frame_captured
frame_filename
auto_gain_attempted
auto_gain_finished
number_of_stars_detected
median_fwhm_px
median_hfr_px
astap_called
astap_input_filename
astap_exit_status
astap_message
solved
solved_coordinates
failure_reason
next_recommended_action
```

Acceptance criteria:

- `0/3 solved` includes per-camera reasons.
- A camera is `unsolved` only if ASTAP was attempted and failed.
- Possible statuses include:

```text
not_attempted
disconnected
inactive
capture_failed
auto_gain_failed
insufficient_stars
astap_failed
metadata_missing
operation_blocked
solved
```

---

### REQ-PS-001 — Plate-solving readiness check

Before ASTAP is called, check:

```text
frame_exists
frame_saved_as_fits
optical_train_metadata_available
pixel_size_available
focal_length_or_hint_available
star_count_measured
astap_available
operation_gate_allows_plate_solve
```

Acceptance criteria:

- Missing metadata gives specific failure reason.
- Missing ASTAP setup gives specific failure reason.
- Insufficient stars gives diagnostic warning or failure depending on config.
- Readiness result is logged.

---

### REQ-PS-002 — ASTAP backend

The already integrated ASTAP solver shall be used for MVP plate solving.

Acceptance criteria:

- ASTAP input FITS path is logged.
- ASTAP command/wrapper call is logged.
- ASTAP output and exit status are logged.
- Failure is converted into structured diagnostics.

---

### REQ-PS-003 — Local star threshold policy

Default config:

```toml
[plate_solve]
min_detected_stars_before_solve = 15
allow_astap_below_min_star_count = true
```

Acceptance criteria:

- If local star count is below threshold, UI/logs show warning.
- If `allow_astap_below_min_star_count = true`, ASTAP may still run.
- If false, plate solve is blocked with `insufficient_stars`.

---

## 10. Auto-gain requirements

### REQ-AG-001 — Reason-dependent auto-gain

Supported reasons:

```text
PLATE_SOLVE
DSO
PLANET
MOON
COLLIMATION
AUTOFOCUS
```

Acceptance criteria:

- `PLATE_SOLVE` optimizes for detectable stars.
- `PLANET` optimizes for short exposure and sufficient signal.
- `MOON` optimizes for low gain and avoiding saturation.
- `COLLIMATION` optimizes for stable star/donut geometry.
- `AUTOFOCUS` optimizes for focus metric reliability.

---

### REQ-AG-002 — Plate-solve strategy

For `PLATE_SOLVE`, auto-gain shall:

1. keep offset low while avoiding black clipping;
2. increase exposure only while tracking quality supports it;
3. increase gain earlier if tracking is off or stars blur;
4. stop when enough stars are detectable or limits are reached;
5. report why it stopped.

Acceptance criteria:

- Each iteration logs exposure, gain, offset and star count.
- Long exposure recommendations include tracking-blur diagnostics.
- Failure reports whether exposure, gain, offset, saturation, focus or tracking blur limited success.

---

### REQ-AG-003 — Exposure capability test

SmartTScope shall provide a diagnostic exposure capability test for plate solving.

Default sequence:

```text
0.5 s, 1 s, 2 s, 4 s, 8 s
```

Default config:

```toml
[plate_solve.exposure_capability_test]
enabled = true
exposures_s = [0.5, 1.0, 2.0, 4.0, 8.0]
max_exposure_s = 8.0
stop_on_star_elongation = true
```

Acceptance criteria:

- Test logs star count, FWHM, HFR and elongation.
- Test suggests max useful exposure for active optical train.
- Suggested values are not written to config without confirmation.
- ASTAP success is not required for this diagnostic test.

---

### REQ-AG-004 — Auto-gain diagnostics

Auto-gain shall return:

```text
number_of_stars_detected
background_median_adu
background_stddev_adu
saturated_pixel_ratio
black_clipped_pixel_ratio
median_fwhm_px
median_hfr_px
exposure_limit_reached
gain_limit_reached
offset_limit_reached
tracking_blur_suspected
reason_for_next_step
reason_for_stop
```

Acceptance criteria:

- Diagnostics are logged.
- FITS frame is referenced if stored.
- Plate-solve failures are actionable.

---

## 11. Diagnostic logging and frame storage

### REQ-LOG-001 — Per-section logs

Required log sections:

```text
startup
stage1_time_location
mount
camera
auto_gain
autofocus
collimation
plate_solve
goto
click_to_center
extended_setup_check
github_delivery
```

Acceptance criteria:

- Each workflow writes to its own log.
- A session ID links logs.
- Paths are available through diagnostics or API.

---

### REQ-LOG-002 — Service-call logs

For auto-gain, autofocus, collimation and plate solving, each call shall log:

```text
session_id
service_name
run_id
iteration
timestamp
input_frame_filename
request_payload
response_payload
duration_ms
status
error_if_any
```

Acceptance criteria:

- Calls can be reconstructed offline.
- Image data is referenced by filename, not embedded.
- Failed calls include errors.

---

### REQ-LOG-003 — User-action logs

Minimum logged user actions:

```text
connect_all_clicked
time_location_push_confirmed
time_location_push_rejected
raspberry_time_manually_confirmed
goto_requested
goto_rejected
bright_star_goto_requested
tracking_enable_requested
tracking_enable_rejected
plate_solve_requested
autofocus_started
autofocus_cancelled
collimation_started
collimation_mode_selected
click_to_center_requested
click_to_center_cancelled
diagnostic_exposure_test_started
github_push_requested
```

Acceptance criteria:

- Each action has timestamp.
- Each action is linked to backend result.
- Rejections include operation-gate reason.

---

### REQ-FRAME-001 — FITS diagnostic storage

Default config:

```toml
[diagnostics.frames]
enabled = true
base_dir = "diagnostics/frames"
retention_days = 2
store_mode = "debug_or_failure"
store_auto_gain = true
store_autofocus = true
store_collimation = true
store_plate_solve = true
```

Allowed store modes:

```text
always
debug_only
failure_only
debug_or_failure
off
```

Acceptance criteria:

- Failure frames are stored if diagnostics are enabled.
- Debug-mode frames are stored.
- Success frames are not stored outside debug mode by default.
- Retention cleanup preserves active-session files.

---

### REQ-FRAME-002 — FITS filename convention

Pattern:

```text
YYYYMMDDTHHMMSS_session-<session_id>_<section>_<run_id>_iter-<n>_<camera_id>_<optical_train_id>_exp-<exposure_s>s_gain-<gain>_offset-<offset>_bin-<x>x<y>_ra-<ra>_dec-<dec>.fits
```

Acceptance criteria:

- Filename includes section, run ID, iteration, camera, exposure, gain, offset and binning.
- RA/DEC included if known.
- Filename is Linux/Windows safe.
- Full path is logged.

---

### REQ-FRAME-003 — FITS headers

Required headers:

```text
SESSION
SECTION
RUNID
ITER
CAMERA
OPTTRAIN
EXPTIME
GAIN
OFFSET
BINX
BINY
PIXSIZE
FOCALLEN
RA
DEC
TRACKING
DATE-OBS
```

Acceptance criteria:

- Offline analysis can reconstruct context.
- ASTAP input frames contain useful metadata.
- Header-writing errors are logged.

---

## 12. Click-to-center requirements

### REQ-CLICK-001 — Availability

Click-to-center shall be available in:

```text
collimation view
plate-solve view
autofocus view
```

Acceptance criteria:

- User can click star or donut/circle.
- If unavailable, exact reason is shown.

---

### REQ-CLICK-002 — Target refinement

After a click, SmartTScope shall refine target position by context:

```text
star centroid
brightest local object near click
donut/circle center
raw click fallback
```

Acceptance criteria:

- Raw click is logged.
- Refined target is logged.
- If refinement fails, user can use raw click or cancel.
- Refined target is displayed.

---

### REQ-CLICK-003 — Calibration dependency

Click-to-center shall use calibrated pixel-to-RA/DEC movement.

Acceptance criteria:

- Missing calibration blocks movement and offers calibration.
- Stale calibration requires recalibration.
- Calibration is stored per optical train, camera orientation and binning.
- Mount is not moved without valid calibration unless explicitly allowed by manual fallback policy.

---

### REQ-CLICK-004 — Iterative bounded centering

Click-to-center loop:

1. capture frame;
2. detect/refine target;
3. compute offset from frame center;
4. finish if within tolerance;
5. convert offset to mount movement;
6. move conservatively;
7. capture next frame;
8. repeat until centered, cancelled or retry limit reached.

Default config:

```toml
[click_to_center]
max_iterations = 5
center_tolerance_px = 20
max_single_move_px = 300
start_with_fraction_of_calculated_move = 0.5
allow_when_tracking_off = true
allow_when_parked = false
```

Acceptance criteria:

- Works with tracking on.
- Works with tracking off with drift warning.
- Blocked while parked.
- User can cancel.
- Every iteration is logged.

---

## 13. API requirements

### REQ-API-001 — `/api/status`

Minimum response:

```json
{
  "session_id": "s042",
  "mount_connection": "CONNECTED",
  "mount_health": "OK",
  "onstep_time_location": "VERIFIED",
  "raspberry_time_trust": "TRUSTED",
  "raspberry_time_trust_source": "NTP",
  "mount_readiness": "CONNECTED_READY",
  "operation_gates": {
    "goto": {
      "allowed": true,
      "reason_code": null,
      "required_user_action": null
    }
  }
}
```

Acceptance criteria:

- Frontend can render accurate status from this endpoint.
- Operation gates are included.
- Connection and trust states are separate.

---

### REQ-API-002 — `/api/mount/status`

Minimum response:

```json
{
  "adapter_open": true,
  "health_check_ok": true,
  "connected": true,
  "park_state": "PARKED|UNPARKED|UNKNOWN",
  "tracking_state": "ON|OFF|UNKNOWN",
  "last_error": null
}
```

Acceptance criteria:

- Connected means adapter open and health check OK.
- False connected status includes reason.
- UI derives mount state from these fields.

---

### REQ-API-003 — `/api/commands`

`/api/commands` shall expose command history.

Acceptance criteria:

- Requested sequence is visible.
- Rejected commands are included.
- Each record contains status and reason.
- Records reference log/frame files when available.

---

### REQ-API-004 — `/api/stage1/time-location`

Minimum response:

```json
{
  "master_source": "GPSD|CONFIG|USER_CONFIRMED|SYSTEM",
  "raspberry_time_trust": "TRUSTED|NOT_TRUSTED",
  "raspberry_time_trust_source": "NTP|GPSD_FIX|USER_CONFIRMED|ONSTEP_COMPARISON|NOT_TRUSTED",
  "onstep_time_location": "VERIFIED|UNVERIFIED|UNKNOWN",
  "time_delta_s": 1.3,
  "time_tolerance_s": 10,
  "location_delta_m": 42.0,
  "location_tolerance_m": 100,
  "available_actions": ["rerun_check", "push_to_onstep"]
}
```

Acceptance criteria:

- Stage 1 UI does not infer hidden state.
- Active tolerances are visible.
- Available remedies are visible.

---

## 14. GitHub delivery requirements

### REQ-GIT-001 — Source, tests and notes delivered together

When a milestone or issue note claims implementation, corresponding source code and tests shall be committed and pushed with it.

Acceptance criteria:

- Documentation-only commits are not marked implementation-complete.
- Source changes are visible in GitHub.
- Relevant tests or validation changes are included where applicable.

---

### REQ-GIT-002 — Delivery audit

Delivery audit shall run in local development workflow and CI.

Minimum checks:

```text
git status --short
git diff --stat
git log -1 --stat
git branch --show-current
git remote -v
```

Acceptance criteria:

- Audit confirms branch and commit.
- Audit confirms source/test/doc file categories.
- Audit confirms push result.
- Push failures are visible.

---

### REQ-GIT-003 — Delivery log

Delivery log fields:

```text
timestamp
branch
commit_hash
commit_message
files_changed
source_files_changed
test_files_changed
docs_changed
push_result
remote_url
```

Acceptance criteria:

- User can verify what was pushed.
- Missing source-code changes are visible.
- Push failures are reported clearly.

---

## 15. Test requirements

### TEST-001 — Connection state

| Case | Expected result |
|---|---|
| Adapter already open and health check OK | mount connected true |
| Adapter already open but health check fails | connected false with reason |
| Connect All called repeatedly | stable state |
| Backend connected but workflow stage stale | UI does not show disconnected |
| Reconnect not useful | UI does not show reconnect message |

---

### TEST-002 — Time/location and Raspberry trust

| Case | Expected result |
|---|---|
| NTP synchronized | Raspberry time trusted via `NTP` |
| GPS fix exists | Raspberry time trusted via `GPSD_FIX` |
| user confirms time | Raspberry time trusted via `USER_CONFIRMED` |
| OnStep comparison against trusted OnStep | Raspberry time trusted via `ONSTEP_COMPARISON` |
| OnStep comparison against untrusted OnStep | Raspberry time remains not trusted |
| time pushed to OnStep only | Raspberry time not automatically trusted |
| location delta below 100 m | OnStep location passes |
| location delta above 100 m | OnStep location fails |
| `lat_delta=0.0027°` with 100 m tolerance | fails |
| `lon_delta=0.0337°` with 100 m tolerance | fails |
| log contains mojibake | test fails |

---

### TEST-003 — Operation gates

| Operation | Blocking state | Expected result |
|---|---|---|
| GoTo | Raspberry time not trusted | blocked with reason |
| Bright-star GoTo | target below horizon | blocked with reason |
| Sync | OnStep time/location unverified | blocked |
| Tracking enable | Stage 1 incomplete | blocked |
| Collimation preview | Raspberry time not trusted | allowed if camera works |
| Collimation slew to target | Raspberry time not trusted | blocked |
| Click-to-center | missing calibration | blocked with calibration reason |
| Click-to-center | mount parked | blocked |
| Click-to-center | tracking off | allowed with drift warning |
| Manual mount move | time/location unverified | allowed with warning if policy permits |

---

### TEST-004 — Plate solving and auto-gain

| Case | Expected result |
|---|---|
| underexposed plate-solve frame | auto-gain increases exposure/gain |
| stars blur at long exposure | tracking blur suspected |
| enough stars detected | ASTAP is attempted |
| insufficient stars below threshold and ASTAP allowed | ASTAP attempted with warning |
| insufficient stars below threshold and ASTAP blocked | structured insufficient-stars result |
| ASTAP missing | structured failure reason |
| frame not saved | solve blocked or diagnostic error |
| metadata missing | solve blocked with metadata reason |

---

### TEST-005 — Collimation

| Case | Expected result |
|---|---|
| preview while Raspberry time untrusted | preview allowed |
| slew-to-target while Raspberry time untrusted | blocked |
| defocus mode supported | mode visible |
| Bahtinov label | spelling correct |
| clicked donut | refined circle center shown |
| click-to-center without calibration | blocked |
| click-to-center with calibration | iterative centering starts |
| click-to-center while parked | blocked |

---

### TEST-006 — Logging and frames

| Case | Expected result |
|---|---|
| auto-gain failure | request, response and FITS filename logged |
| plate-solve attempt | ASTAP input FITS stored and logged if debug/failure applies |
| collimation iteration | frame and geometry logged |
| rejected GoTo | command history shows rejection |
| debug mode off and success | no unnecessary frame storage |
| failure with diagnostics enabled | FITS frame stored |
| retention cleanup | old frames removed, active frames preserved |

---

### TEST-007 — GitHub delivery

| Case | Expected result |
|---|---|
| milestone says implemented but only docs changed | delivery audit fails |
| source changed but not pushed | delivery audit fails |
| source, tests and docs pushed | delivery audit passes |
| push fails | user sees push failure |
| delivery log opened | commit hash and changed files visible |

---

## 16. Implementation priorities

### Priority 1 — State and gates

Implement:

- separated state model;
- corrected `/api/status`;
- corrected `/api/mount/status`;
- operation-gate service;
- structured 409 responses;
- UI reasons for disabled controls.

### Priority 2 — Stage 1 time/location and Raspberry trust

Implement:

- visible Stage 1 panel;
- meter-based location tolerance;
- Raspberry time trust sources;
- manual time confirmation;
- active tolerance logging;
- UTF-8-safe logs.

### Priority 3 — Command history

Implement:

- persisted per-session command log;
- `/api/commands`;
- requested-sequence UI;
- rejected command visibility.

### Priority 4 — Observability and diagnostic frames

Implement:

- per-section logs;
- structured service request/response logging;
- FITS frame storage;
- 2-day default retention;
- debug/failure storage mode.

### Priority 5 — Plate solve and auto-gain

Implement:

- plate-solve auto-gain based on detectable stars;
- exposure capability test;
- per-camera setup diagnostics;
- ASTAP input/output logging.

### Priority 6 — Collimation and click-to-center

Implement:

- defocus donut mode UI;
- click target selection;
- target refinement;
- calibrated pixel-to-RA/DEC movement;
- bounded iterative centering.

### Priority 7 — GitHub delivery completeness

Implement:

- delivery audit;
- GitHub delivery log;
- source/test/doc push completeness checks.

---

## 17. Final acceptance target

After implementation, SmartTScope shall answer these questions directly in the UI:

1. Is the mount physically connected?
2. Is the OnStep adapter healthy?
3. Is OnStep time/location verified?
4. Is Raspberry Pi time trusted?
5. What made Raspberry Pi time trusted?
6. Why is GoTo disabled?
7. Why is plate solve disabled or failing?
8. Which commands were requested, rejected, issued or completed?
9. Which frame was used for auto-gain, autofocus, collimation or plate solving?
10. What did each service receive and return?
11. Why did ASTAP fail?
12. Can I click a star or donut and center it safely?
13. Was the claimed implementation actually pushed to GitHub with source code and tests?

---

## 18. Remaining open items

The major design questions are now resolved. The remaining items are implementation parameters, not blocking requirements questions.

### OPEN-001 — Confirm manual time confirmation warning text

Default warning text:

```text
Raspberry Pi time is being trusted by manual user confirmation. GoTo and visibility calculations depend on this time. Confirm only if the displayed date, time and timezone are correct.
```

### OPEN-002 — Confirm final click-to-center defaults after first calibration results

Initial defaults are defined in this document. They should be reviewed after real mount/camera calibration.

### OPEN-003 — Confirm ASTAP local star threshold after real frames

Initial default is `15`, with ASTAP allowed below the threshold. This should be adjusted after real SmartTScope frames are collected.

### OPEN-004 — Confirm exposure capability test sequence after real tracking data

Initial sequence is `0.5 s, 1 s, 2 s, 4 s, 8 s`. Adjust after real tracking/focus data.

### OPEN-005 — Split document after incident closure

Keep this document as one file until the incident cluster is closed. Split later if needed.
