# SmartTScope C8 Collimation Assistant — Implementation Task Plan

## Scope Decisions Already Fixed

- Telescope: **Celestron C8 SCT**
- MVP optical train: **native f/10**
- Later profiles:
  - **2× Barlow validation profile**
  - **0.63× reducer profile**
- Cameras:
  - **Touptek G3M678M**
  - **Touptek ATR585M**
- MVP image mode:
  - **mono**
  - bit depth as delivered by `touptek.py`
- Mount:
  - **OnStep V4 via USB**
  - GoTo allowed for initial star selection
  - **pulse guide only** for centering corrections
- Focuser:
  - **OnStep-controlled**
  - relative movement preferred
  - absolute range may be queried as **0–50000**, but must not be fully trusted
  - direction must be configurable
  - default assumption: **higher focuser values = clockwise**
- Collimation screws:
  - manual only
  - user guidance via overlay and wizard
- Session calibration:
  - repeat screw and mask orientation calibration every run
  - stored calibration may be reused later only with explicit user choice
- OCAL-inspired daylight/mechanical alignment:
  - **not part of MVP**
  - may be added later as an optional rough pre-check mode
  - must never replace final star-based validation with the real imaging train

---

## OCAL-Inspired Design Lessons Added to the Plan

The OCAL 4.0 approach is useful because it demonstrates that **daylight mechanical alignment** can be supported with a dedicated camera and concentric overlay geometry. For SmartTScope, the main lesson is not to replace star-based SCT collimation, but to reuse the same ideas where they are safe: reference-center calibration, circle/ellipse fitting, clear overlays, and explicit confidence/contradiction handling.

Key design implications:

- Add a generic **reference center** abstraction instead of assuming that the image center is always the optical reference.
- Build reusable **circle/ellipse fitting** tools for donuts, reflections, and possible later mechanical alignment.
- Add **OCAL-like overlays**: center crosshair, concentric circles, detected centers, error vectors, and color-coded screw labels.
- Distinguish **mechanical concentricity** from **optical collimation**. SCT screws mainly adjust secondary tilt; visible mechanical circles can be eccentric without proving final optical alignment.
- Add **contradiction detection**: if donut symmetry, Tri-Bahtinov residuals, screw-response learning, focus stability, or star centering disagree, the assistant must stop giving screw-turn commands and remeasure.
- Add a later optional **Daylight / OCAL-like Mechanical Pre-Check Mode**, but keep the MVP focused on a real star, real main camera, and selected optical train.

---

## Phase 0 — Project Skeleton and Configuration

### Task 0.1 — Add collimation configuration model

Create a configuration section for the collimation assistant.

Example:

```yaml
collimation:
  telescope_profile: c8_f10
  camera_id: main
  mount_adapter: onstep
  focuser_adapter: onstep

  reference_center:
    # Default MVP behavior: use frame center.
    # Later this can store a calibrated optical/camera center offset.
    offset_x_px: 0.0
    offset_y_px: 0.0
    source: frame_center

  contradiction_detection:
    enabled: true
    stop_on_conflicting_indicators: true
    require_recenter_before_next_screw_hint: true
    require_refocus_before_final_fine_hint: true

  daylight_mechanical_alignment:
    enabled: false
    mode: optional_non_mvp
    camera_id: ocal_like_collimation_camera
    warning: "Mechanical concentricity is only a rough pre-check; final SCT collimation requires star validation."

  focuser:
    min_position: 0
    max_position: 50000
    increasing_value_direction: clockwise
    final_approach_direction: clockwise
    defocus_direction: clockwise
    max_single_step: 500
    fine_step: 25
    coarse_step: 250

  mount_centering:
    method: pulse_guide
    max_pulse_ms: 500
    settle_ms: 750
    initial_tolerance_px: 50
    rough_tolerance_px: 20
    fine_tolerance_px: 5

  rough_collimation:
    target_donut_diameter_ratio_min: 0.25
    target_donut_diameter_ratio_max: 0.50
    good_error_ratio: 0.02
    fallback_error_ratio: 0.05

  fine_collimation:
    moving_window_frames: 7
    target_residual_px: 2.0
    poor_seeing_residual_px: 3.0
```

**Acceptance criteria**

- Configuration can be loaded from YAML.
- Invalid values are rejected with clear errors.
- Focuser direction and defocus side are configurable.
- MVP profile `c8_f10` exists.
- Reference-center offset exists and defaults to image center.
- Daylight/mechanical alignment mode exists in configuration but is disabled for MVP.
- Contradiction detection can be enabled/disabled explicitly.

---

### Task 0.2 — Define core domain models

Add domain models for measurements and workflow state.

Suggested files:

```text
domain/collimation/models.py
domain/collimation/state.py
domain/collimation/profiles.py
```

Core models:

```python
CollimationSession
OpticalTrainProfile
FrameMeasurement
StarMeasurement
DonutMeasurement
SpikeMeasurement
ScrewCalibration
MaskSectorCalibration
CollimationRecommendation
ReferenceCenterCalibration
CircleEllipseFit
MechanicalCircleMeasurement
MechanicalAlignmentReport
ContradictionAssessment
```

**Acceptance criteria**

- Models are independent from UI and hardware.
- Geometry fields use image coordinates consistently.
- All measurements include a **confidence** value.
- All recommendations include:
  - screw identifier,
  - turn direction,
  - adjustment size class,
  - reason,
  - confidence.
- Reference center can be either frame center or calibrated offset.
- Mechanical alignment reports are explicitly marked as **rough pre-check only**.
- Contradiction assessments can stop screw guidance safely.

---

### Task 0.3 — Add reference-center abstraction

Do not hard-code the frame center as the only measurement reference. Instead, all measurements should use:

```python
reference_center = frame_center + configured_center_offset
```

Default MVP behavior:

```yaml
reference_center:
  offset_x_px: 0.0
  offset_y_px: 0.0
  source: frame_center
```

Later behavior:

```yaml
reference_center:
  offset_x_px: -3.5
  offset_y_px: 4.0
  source: calibrated
```

**Acceptance criteria**

- Existing star-centering logic can still use the frame center by default.
- Donut and spike measurements use the reference-center abstraction.
- UI can display both frame center and calibrated reference center if they differ.
- Reference-center offset is stored per optical train/camera profile if calibrated later.

---

## Phase 1 — Uvicorn Service and Wizard State Machine

### Task 1.1 — Create `CollimationAssistant` service

Suggested location:

```text
services/collimation/assistant.py
services/collimation/state_machine.py
```

The assistant should coordinate:

- camera frames,
- OnStep mount,
- OnStep focuser,
- image processing,
- overlay data,
- wizard state.

**Acceptance criteria**

- Service can be started/stopped from the main uvicorn server.
- Service exposes current state.
- Service exposes current recommendation.
- Service can run in hardware mode or replay/simulation mode.

---

### Task 1.2 — Implement explicit state machine

Initial state list:

```text
IDLE
PRECHECK
SELECT_STAR
SLEW_TO_STAR
ACQUIRE_STAR
CENTER_STAR
AUTO_EXPOSURE
ROUGH_DEFOCUS
MAP_SCREWS_BY_OBSTRUCTION
MEASURE_DONUT
GUIDE_ROUGH_COLLIMATION
INSTALL_TRIBAHTINOV
MAP_MASK_SECTORS
FINE_FOCUS
MEASURE_SPIKES
GUIDE_FINE_COLLIMATION
FINAL_REFOCUS
MASKLESS_VALIDATION
COMPLETE
FAILED
```

Optional non-MVP daylight/mechanical path:

```text
DAYLIGHT_MECHANICAL_PRECHECK
ACQUIRE_MECHANICAL_PATTERN
FIT_MECHANICAL_CIRCLES
CALIBRATE_REFERENCE_CENTER
MECHANICAL_ALIGNMENT_REPORT
PROCEED_TO_STAR_VALIDATION
```

**Acceptance criteria**

- Each state has:
  - entry action,
  - processing loop,
  - exit condition,
  - timeout/error handling.
- State transitions are unit-tested.
- Unsafe transitions are rejected.
- User can pause/resume/cancel.

---

### Task 1.3 — Add wizard API endpoints

Example endpoints:

```text
GET  /api/collimation/status
POST /api/collimation/start
POST /api/collimation/pause
POST /api/collimation/resume
POST /api/collimation/cancel
POST /api/collimation/next
POST /api/collimation/retry
GET  /api/collimation/overlay
GET  /api/collimation/report
```

**Acceptance criteria**

- UI can display the current wizard step.
- UI can display checklist and warnings.
- UI can show whether the assistant is waiting for:
  - star acquisition,
  - screw touch,
  - mask installation,
  - blade movement,
  - user screw turn.

---

## Phase 2 — User-Visible MVP Shell

This phase makes the feature visible early, even before the full algorithm is complete.

### Task 2.1 — Add wizard panel

The panel should show:

- current step,
- short instruction,
- current status,
- warnings,
- next automatic action,
- manual controls for test mode.

Example:

```text
Step: Center star
Status: Star detected, 37 px from center
Action: Pulse-guiding mount correction
Warning: none
```

**Acceptance criteria**

- User can see the workflow step-by-step.
- User can confirm visually that the assistant is alive.
- User can pause/cancel immediately.
- No real mount/focuser movement occurs unless enabled.

---

### Task 2.2 — Add overlay visibility test

Add a test overlay mode before real collimation starts.

Overlay should show:

- frame center crosshair,
- test circles,
- optional concentric OCAL-like reference circles,
- frame center and reference center if different,
- screw labels,
- traffic-light status area,
- contradiction/warning area,
- text area for recommendation.

**Acceptance criteria**

- User can verify that the overlay is visible.
- Overlay aligns correctly with the live image.
- Overlay updates at live frame rate or acceptable reduced rate.
- Overlay can be enabled/disabled.

---

### Task 2.3 — Add hardware self-test page

The user should be able to test:

- camera live image,
- overlay,
- mount pulse guide north/south/east/west,
- focuser small in/out movement,
- exposure control.

**Acceptance criteria**

- Mount test uses only short pulse-guide movements.
- Focuser test uses small relative steps.
- UI warns that focuser absolute position is not trusted.
- User can confirm:
  - “camera works”
  - “overlay visible”
  - “mount pulse guide works”
  - “focuser moves”
  - “exposure control works”

---

## Phase 3 — Frame Processing Foundation

### Task 3.1 — Normalize Touptek frame input

Create a processing entry point that accepts frames from the existing `touptek.py` adapter.

Suggested output:

```python
ProcessedFrame(
    raw=array,
    mono=array,
    bit_depth=8 | 16,
    width=int,
    height=int,
    timestamp=float,
)
```

**Acceptance criteria**

- Supports ATR585M mono frames.
- Supports G3M678M mono frames.
- Preserves bit depth.
- Provides normalized float view for processing.
- Does not mutate the original frame.

---

### Task 3.2 — Add display stretch pipeline

Suggested location:

```text
store/processing/stretch.py
```

Functions:

- auto stretch for display,
- background estimation,
- saturation detection,
- peak detection.

**Acceptance criteria**

- Overlay display remains usable for dim and bright stars.
- Measurement code can use raw/linear data, not only stretched data.
- Saturation warnings are available.

---

### Task 3.3 — Star detection

Suggested location:

```text
store/processing/star_detection.py
```

Detect:

- brightest object,
- centroid,
- approximate FWHM,
- saturation,
- confidence.

**Acceptance criteria**

- Finds bright star in normal frame.
- Rejects saturated blob if unusable.
- Rejects hot pixels or tiny artifacts.
- Provides center offset from frame center.

---

### Task 3.4 — Generic circle/ellipse fitting primitives

Create reusable geometry functions that can later serve both rough donut collimation and optional OCAL-like mechanical alignment.

Suggested location:

```text
store/processing/geometry_fits.py
```

Functions:

- fit circle from edge points,
- fit ellipse from edge points,
- estimate center/radius/axis lengths,
- detect clipping,
- compare two fitted centers,
- produce confidence score.

**Acceptance criteria**

- Donut detection can reuse these functions.
- Later daylight mechanical alignment can reuse these functions.
- Functions report unreliable geometry instead of returning misleading measurements.
- Functions support overlay rendering data.

---

## Phase 4 — OnStep Mount and Focuser Control

### Task 4.1 — Add safe mount-centering interface

Use existing OnStep adapter, but expose a collimation-safe method:

```python
pulse_center_star(offset_px: tuple[float, float]) -> MountCorrectionResult
```

Internally:

- convert pixel offset to short pulse guide corrections,
- apply max pulse duration,
- wait for settle,
- remeasure.

**Acceptance criteria**

- No normal slew is used for centering.
- Each correction is stepwise.
- Max pulse duration is enforced.
- Centering stops if star is lost.
- Centering stops if correction direction appears wrong repeatedly.

---

### Task 4.2 — Add relative focuser control

Expose methods:

```python
move_focus_relative(steps: int) -> FocuserMoveResult
move_focus_clockwise(steps: int) -> FocuserMoveResult
move_focus_counterclockwise(steps: int) -> FocuserMoveResult
```

Position handling:

- query position if available,
- respect configured **0–50000** soft range,
- do not assume position is physically accurate,
- never drive aggressively toward a limit.

**Acceptance criteria**

- Direction mapping is configurable.
- Final approach direction is configurable.
- Defocus direction is configurable.
- Movement is step-limited.
- UI can show last commanded movement.

---

## Phase 5 — Star Selection and Acquisition

### Task 5.1 — Bright star selection

Implement simple star selection first.

MVP:

- built-in list of bright stars,
- calculate altitude/azimuth for current time/location,
- select brightest star above **60°**,
- fallback to **45°** with warning.

**Acceptance criteria**

- Returns selected star and reason.
- Avoids stars below configured altitude.
- Provides target coordinates for OnStep GoTo.
- Can be overridden manually.

---

### Task 5.2 — Slew and acquire star

Process:

1. slew to selected star,
2. start tracking,
3. start camera stream,
4. auto exposure,
5. detect star,
6. center star.

**Acceptance criteria**

- Wizard shows selected star.
- Wizard shows slew/acquisition progress.
- If star is not found, assistant does not blindly move the mount.
- Optional later: small spiral search.

---

## Phase 6 — Focuser Algorithm

### Task 6.1 — Image-based rough focus search

Because absolute position is not trusted, focus must be image-based.

Algorithm:

1. start from current position,
2. take frame,
3. estimate star size/profile,
4. move relative step,
5. determine whether focus improves,
6. bracket focus,
7. approach final focus from configured direction.

**Acceptance criteria**

- Does not depend on absolute position.
- Uses relative steps.
- Enforces final approach direction.
- Stops if focus cannot be evaluated.
- Shows focus status in overlay.

---

### Task 6.2 — Controlled defocus for rough collimation

Goal:

- create donut large enough for analysis,
- keep donut inside frame,
- avoid excessive defocus.

Target:

```text
donut diameter = 25–50% of smaller frame dimension
```

**Acceptance criteria**

- Donut is detected.
- Donut is not clipped if possible.
- If donut is clipped, assistant recenters or reduces defocus.
- Defocus side is consistent.

---

## Phase 7 — Rough Donut Collimation

### Task 7.1 — Donut detection and fitting

Suggested location:

```text
store/processing/donut_detection.py
```

Detect:

- outer ring,
- inner secondary shadow,
- centers,
- ellipse axes,
- confidence.

Use:

- thresholding,
- radial profile,
- ellipse fit,
- fallback partial fit.

**Acceptance criteria**

- Works on centered donut.
- Works on moderately off-center donut.
- Works on partially clipped donut if enough structure remains.
- Reports low confidence if unreliable.

---

### Task 7.2 — Rough collimation measurement

Compute:

```python
rough_error_vector = shadow_center - outer_center
rough_error_ratio = norm(rough_error_vector) / outer_radius
```

Also compute brightness symmetry.

**Acceptance criteria**

- Combines geometric and brightness measurements.
- Can classify:
  - good,
  - needs adjustment,
  - unreliable,
  - star too far off frame,
  - donut too clipped.

---

### Task 7.3 — Rough overlay

Show:

- frame center,
- calibrated/reference center if available,
- outer ellipse,
- inner ellipse,
- concentric guide circles,
- fitted centers,
- error vector,
- screw labels,
- recommendation,
- confidence,
- contradiction warning if indicators disagree,
- traffic-light status.

**Acceptance criteria**

- User can visually understand the collimation error.
- Overlay updates live.
- Recommendation changes when the error changes.

---

## Phase 8 — Screw Identification and Response Learning

### Task 8.1 — Screw identification by hand obstruction

Workflow:

```text
Touch Screw 1
Touch Screw 2
Touch Screw 3
```

Detection:

- compare current frame to previous frame,
- find large local obstruction/shadow,
- derive image angle,
- assign screw label.

Recommended labels:

```text
Screw 1 / red
Screw 2 / green
Screw 3 / blue
```

**Acceptance criteria**

- Detects obstruction reliably.
- Stores image-angle per screw.
- Shows detected screw position on overlay.
- Repeats if confidence is low.

---

### Task 8.2 — Response learning

After each manual screw adjustment:

1. measure before,
2. user turns screw,
3. measure after,
4. compare error vector,
5. update screw response model.

**Acceptance criteria**

- Detects whether adjustment improved or worsened error.
- Can say “reverse direction”.
- Learns per-session response.
- Does not assume camera rotation is unchanged between sessions.

---

## Phase 9 — Rough Collimation Guidance

### Task 9.1 — Generate safe screw recommendations

Recommendation format:

```text
Turn Screw 2 / green very slightly clockwise.
```

Allowed sizes:

```text
tiny
very slight
slight
```

Do not recommend large movements.

**Acceptance criteria**

- Recommendation is based on measured error vector and screw map.
- Recommendation includes confidence.
- Recommendation avoids large turn instructions.
- If mapping is uncertain, assistant asks for recalibration.

---

### Task 9.2 — Live “turn until OK” behavior

The user should not need to press “done”.

Behavior:

```text
Turn Screw 2 / green very slightly clockwise.
Improving...
Improving...
OK — stop turning.
Recentering star...
```

**Acceptance criteria**

- Assistant detects improvement live.
- Assistant tells user when to stop.
- Assistant recenters automatically after adjustment.
- If error worsens, assistant warns and updates direction.

---

## Phase 10 — Tri-Bahtinov Fine Collimation Foundation

### Task 10.1 — Detect Tri-Bahtinov spike pattern

Suggested location:

```text
store/processing/spike_detection.py
```

Use classical image processing first:

- background subtraction,
- ROI extraction,
- Radon or Hough transform,
- line fitting,
- line grouping,
- confidence scoring.

**Acceptance criteria**

- Detects visible spike groups.
- Reports confidence per group.
- Handles moderate background light.
- Handles dimmer stars by using exposure control.
- Rejects unreliable measurements.

---

### Task 10.2 — Mask sector mapping with blade

Workflow:

```text
Open/close blade for Sector 1
Open/close blade for Sector 2
Open/close blade for Sector 3
```

The software detects which spike group remains or disappears.

**Acceptance criteria**

- Maps mask sectors to spike groups.
- Associates sectors with screw labels.
- Detects mismatch between mask orientation and screw orientation.
- Informs user to rotate/correct mask if needed.

---

### Task 10.3 — Spike measurement smoothing

Use:

```text
measurement window = 5–10 frames
recommended MVP = 7 frames
```

Recommended combination:

- median for current measurement,
- moving average for trend display.

**Acceptance criteria**

- Rejects low-confidence frames.
- Reports jitter.
- Shows seeing-limited warning if jitter exceeds tolerance.
- Does not chase unstable measurements.

---

## Phase 11 — Fine Focus and Fine Collimation

### Task 11.1 — Separate focus error from collimation residual

For three spike groups:

```python
common_focus_error = mean(error_1, error_2, error_3)
collimation_residual_i = error_i - common_focus_error
```

**Acceptance criteria**

- Common shift is treated as focus error.
- Differential shift is treated as collimation error.
- Assistant refocuses before interpreting fine collimation residuals.
- Assistant requests no screw change if seeing makes measurement unreliable.

---

### Task 11.2 — Fine focus loop

Use OnStep focuser.

Process:

1. measure common focus error,
2. move relative focuser step,
3. remeasure,
4. reduce step size near focus,
5. finish from configured final approach direction.

**Acceptance criteria**

- Focus loop uses image feedback.
- Final approach direction is enforced.
- Focus residual is shown in overlay.
- Focus is rechecked before final validation.

---

### Task 11.3 — Fine collimation guidance

Target:

```text
fine residual <= 2 px
poor seeing fallback <= 3 px
Barlow later target <= 1 px
```

Behavior:

```text
Fine residual strongest in Screw 3 / blue sector.
Turn Screw 3 / blue tiny counterclockwise.
```

**Acceptance criteria**

- Residuals are shown per sector.
- Recommendation includes confidence.
- User sees live feedback while turning.
- Assistant stops recommending changes when measurement is seeing-limited.

---

### Task 11.4 — Contradiction detection and safe stop

Before issuing any further screw-turn recommendation, compare available indicators:

- star centering stability,
- focus stability,
- donut symmetry trend,
- Tri-Bahtinov residual trend,
- learned screw response,
- image confidence / seeing jitter.

If the indicators disagree, the assistant should stop recommending screw movement and move into a remeasure/recenter/refocus action.

Example UI message:

```text
Collimation indicators disagree.
The spike residual improved, but the donut center moved away.
Recentering and refocusing before the next screw instruction.
```

**Acceptance criteria**

- Screw guidance is blocked when confidence is low or indicators conflict.
- The assistant explains why it stopped.
- The next automatic recovery action is visible in the UI.
- Recovery uses stepwise mount/focuser corrections only.
- User can retry measurement after recovery.

---

## Phase 12 — Final Validation and Report

### Task 12.1 — Final refocus

Before final validation:

- remove Tri-Bahtinov mask,
- focus again,
- enforce final approach direction.

**Acceptance criteria**

- Assistant reaches image-based focus.
- Overlay reports focus quality.
- If focus cannot be reached, report reason.

---

### Task 12.2 — Maskless validation

Validation options using the **actual selected imaging train**:

- slight defocus donut symmetry,
- in-focus star shape,
- Airy pattern only if seeing allows.

Mechanical/daylight concentricity, if implemented later, is not sufficient for final SCT validation.

**Acceptance criteria**

- Donut residual is measured.
- Airy validation is optional.
- Poor seeing warning is shown if needed.
- Final status is clear:
  - complete,
  - acceptable with warning,
  - failed,
  - seeing-limited.

---

### Task 12.3 — Short session report

MVP report should include:

```text
date/time
camera
optical train
selected star
rough residual start/end
fine residual start/end
focus status
seeing/confidence notes
final result
```

**Acceptance criteria**

- Report is available via API.
- Report is human-readable.
- No large image archive required for MVP.

---

## Phase 13 — Replay and Test Infrastructure

### Task 13.1 — Replay frame provider

Support prerecorded frames as input.

Use cases:

- centered donut,
- off-center donut,
- clipped donut,
- good Tri-Bahtinov spikes,
- weak spikes,
- saturated star,
- poor seeing simulation.

**Acceptance criteria**

- CollimationAssistant can run without hardware.
- State machine can be tested deterministically.
- UI can be demonstrated indoors.

---

### Task 13.2 — Unit tests

Use doctests for:

- vector math,
- residual calculation,
- screw angle mapping,
- recommendation logic.

Use pytest for:

- state transitions,
- safety limits,
- mount pulse limits,
- focuser movement limits,
- exposure warning states,
- response learning.

**Acceptance criteria**

- Tests run without hardware.
- Hardware tests are marked separately.
- Existing CI can run non-hardware tests.

---

## Phase 14 — User-Visible Milestones

These are useful checkpoints so the feature becomes visible and testable early.

### Milestone 1 — Wizard shell and overlay

User can:

- open collimation wizard,
- see live camera image,
- enable overlay,
- see center crosshair,
- see checklist.

**User confirmation goal**

```text
Overlay is visible and aligned with the image.
```

---

### Milestone 2 — Hardware self-test

User can test:

- camera stream,
- exposure adjustment,
- mount pulse guide,
- focuser relative movement.

**User confirmation goal**

```text
Mount and focuser are controllable without unsafe movement.
```

---

### Milestone 3 — Star acquisition and centering

Assistant can:

- select bright star,
- slew via OnStep,
- detect star,
- center with pulse guiding.

**User confirmation goal**

```text
Selected star is centered automatically.
```

---

### Milestone 4 — Rough defocus and donut overlay

Assistant can:

- defocus to donut,
- detect outer/inner donut,
- show rough collimation error.

**User confirmation goal**

```text
Donut detection and error overlay look plausible.
```

---

### Milestone 5 — Screw detection

Assistant can:

- ask user to touch screws,
- detect obstruction,
- label Screw 1/2/3 with colors.

**User confirmation goal**

```text
Screw labels match the physical screws.
```

---

### Milestone 6 — Rough collimation guidance

Assistant can:

- recommend screw and direction,
- detect whether adjustment improves,
- tell user when to stop,
- recenter automatically.

**User confirmation goal**

```text
Rough collimation converges without manual recentering.
```

---

### Milestone 7 — Tri-Bahtinov spike detection

Assistant can:

- detect spike groups,
- show fitted spike lines,
- report focus/spike confidence.

**User confirmation goal**

```text
Spike overlay follows the real Tri-Bahtinov pattern.
```

---

### Milestone 8 — Fine focus and fine collimation

Assistant can:

- focus using spike common error,
- measure collimation residuals,
- guide tiny screw adjustments.

**User confirmation goal**

```text
Fine residual converges to acceptable tolerance.
```

---

### Milestone 9 — Final validation and report

Assistant can:

- refocus,
- validate without mask,
- produce short session report.

**User confirmation goal**

```text
The telescope is collimated and the result is documented.
```

---

### Optional Milestone 10 — Daylight mechanical pre-check

Assistant can:

- use a dedicated OCAL-like collimation camera,
- show concentric mechanical alignment overlays,
- fit visible internal circles/reflections,
- store a center-offset calibration,
- generate a rough mechanical alignment report,
- require later star-based validation.

**User confirmation goal**

```text
Mechanical pre-check completed; proceed to real-star collimation with the main camera.
```

---

## Phase 15 — Optional Non-MVP Daylight / OCAL-Like Mechanical Pre-Check Mode

This phase is intentionally **not MVP**. It should be implemented only after the real-star workflow is stable. The purpose is to learn from OCAL-style daytime alignment without confusing mechanical concentricity with final optical collimation.

### Task 15.1 — Add dedicated collimation-camera input

Support a separate camera profile for a dedicated OCAL-like collimation camera that replaces the normal imaging camera during daylight pre-check.

**Acceptance criteria**

- Mechanical mode clearly indicates that the main imaging camera is not installed.
- Mechanical mode cannot mark the telescope as finally collimated.
- The session report records that this was a pre-check only.

---

### Task 15.2 — Detect and fit mechanical reference circles

Use the generic circle/ellipse fitting primitives to identify visible internal structures and reflections.

**Acceptance criteria**

- User can manually select or confirm detected circles.
- Software fits center/radius/ellipse parameters.
- Overlay shows fitted circles and centers.
- Low-confidence or inconsistent rings are rejected.

---

### Task 15.3 — Calibrate reference center offset

Allow the user to store a center offset derived from a reliable mechanical/camera calibration.

**Acceptance criteria**

- Offset is stored separately from the default frame center.
- Offset is linked to camera/adapter/profile.
- UI shows when a non-zero calibrated center is active.
- User can reset the offset to zero.

---

### Task 15.4 — Generate mechanical pre-check report

Report should include:

```text
mechanical camera profile
visible fitted circles
center offsets
confidence
contradictions
warning: final star-based collimation required
```

**Acceptance criteria**

- Report cannot be mistaken for final collimation proof.
- Report recommends proceeding to star-based rough/fine collimation.
- If mechanical references disagree, the report says so explicitly.

---

## Suggested Implementation Order

```text
1. Configuration + domain models
2. Uvicorn service skeleton
3. Wizard shell + overlay test mode
4. Camera frame normalization
5. OnStep mount/focuser self-test
6. Star detection + pulse-guided centering
7. Image-based focuser search + controlled defocus
8. Donut detection + rough measurement
9. Screw obstruction mapping
10. Rough collimation guidance
11. Tri-Bahtinov spike detection
12. Mask sector mapping
13. Fine focus
14. Fine collimation
15. Final validation
16. Short report
17. Replay tests and CI hardening
```

This order gives usable intermediate results early and avoids building the full collimation logic before confirming that camera, overlay, mount, and focuser control behave correctly.

---

## Important Constraint Preserved from the OCAL Analysis

The assistant may learn from OCAL-style daylight alignment, especially for overlays and mechanical pre-checks. However, for a C8 SCT the final result must still be validated with:

- the **actual main camera**,
- the **selected optical train**,
- a **real star**,
- real focus behavior,
- and measured optical residuals.

Mechanical concentricity is useful, but it is not identical to final optical collimation.
