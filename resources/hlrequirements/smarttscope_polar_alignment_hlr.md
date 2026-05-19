# SmartTScope Polar Alignment — High-Level Requirements

## 1. Scope

This document defines the high-level requirements for a SmartTScope polar alignment assistant for an equatorial OnStep mount.

The MVP focuses on:

- northern hemisphere only
- mechanical HOME start position
- RA-only measurement movement
- plate-solving-based polar error estimation
- passive ALT/AZ screw adjustment guidance
- clean architecture with hardware-independent algorithm logic

Southern hemisphere support is intentionally out of scope for the MVP.

---

## 2. MVP Assumptions

| Topic | Assumption |
|---|---|
| Hemisphere | Northern hemisphere only |
| Mount type | Equatorial mount |
| Mount controller | OnStep via application/mount adapter |
| Start position | Mechanical HOME |
| HOME convention | Counterweight shaft down, telescope roughly aimed toward the northern celestial pole |
| Absolute feedback | No absolute feedback devices |
| Primary camera | C8 main imaging camera |
| Supported C8 configurations | Native C8 focal length and C8 with 0.63× reducer |
| Fallback camera | Guide camera |
| Manual movement | Only for coarse setup and final ALT/AZ screw adjustment |
| Measurement movement | Controlled RA movement requested by the algorithm and executed by the caller |

---

## 3. Key Design Principles

### 3.1 Algorithm shall remain hardware-independent

The polar alignment algorithm shall not directly command OnStep, INDI, cameras, or plate solvers.

Instead, the algorithm shall return abstract actions to the caller, for example:

- request image capture
- request plate solving
- request RA movement
- request user confirmation
- request user coarse adjustment
- start live adjustment loop
- stop workflow

The application layer shall execute these actions through the configured adapters.

### 3.2 RA-only measurement

The precise polar measurement phase shall use controlled RA-axis rotation only.

DEC shall remain constant during the measurement sequence.

### 3.3 Manual adjustment boundary

Manual movement is allowed only in these phases:

1. Initial physical HOME setup
2. Coarse mechanical pre-alignment
3. Final ALT/AZ screw adjustment

Manual RA/DEC movement during the measurement sequence is out of scope for the MVP.

### 3.4 Main-camera-first strategy

The main C8 camera shall be used first.

If plate solving repeatedly fails, the workflow may offer guide-camera fallback.

Switching cameras shall restart the measurement run.

---

## 4. High-Level Workflow

```text
1. User puts mount mechanically into HOME.
2. System shows pre-start checklist.
3. User confirms and presses START.
4. System captures first HOME frame.
5. System plate solves HOME frame.
6. System checks whether rough coarse alignment is required.
7. If too far from the pole:
   - guide user through coarse adjustment
   - repeat HOME frame
8. If close enough:
   - plan safe RA measurement offsets
   - check safe movement envelope
   - check optional horizon profile
9. System requests RA movement from caller.
10. Caller commands OnStep through mount adapter.
11. System captures and solves next frame.
12. Repeat until at least three solved RA positions exist.
13. System estimates apparent RA-axis direction.
14. System compares apparent RA axis with true northern celestial pole.
15. System displays polar error and ALT/AZ correction.
16. User starts live fine adjustment.
17. System repeatedly captures and solves frames.
18. System continuously updates remaining correction.
19. Workflow ends when target precision is reached or user stops.
20. Optional second refinement run may be started.
```

---

## 5. High-Level Requirements

### HLR-PA-001 — Northern Hemisphere MVP

The system shall support polar alignment for northern-hemisphere equatorial mounts only.

Southern hemisphere support is out of scope for the MVP.

---

### HLR-PA-002 — Mechanical HOME Start

The system shall assume that the mount starts from mechanical HOME:

- counterweight shaft down
- telescope roughly aimed toward Polaris / northern celestial pole
- DEC near +90°
- RA axis roughly aimed north
- clutches locked

The system shall not assume that the mount is truly at HOME without user confirmation.

---

### HLR-PA-003 — Pre-Start Safety Checklist

Before starting polar alignment, the system shall display a checklist requiring the user to confirm:

- mount is mechanically in HOME
- telescope points roughly north / toward Polaris
- clutches are locked
- camera is connected
- focus is good enough for plate solving
- cables have enough slack
- no expected collision during planned RA movement
- tripod and mount head are mechanically stable
- ALT/AZ screws are usable for fine adjustment

The user shall explicitly confirm this checklist before the workflow starts.

---

### HLR-PA-004 — Hardware-Independent Algorithm

The polar alignment algorithm shall not directly call OnStep, INDI, camera drivers, or solver adapters.

The algorithm shall return abstract workflow actions to the caller.

The caller shall execute those actions using the configured SmartTScope adapters.

---

### HLR-PA-005 — Main C8 Camera First

The system shall first attempt polar alignment using the main C8 camera.

The system shall support at least these optical configurations:

- C8 native focal length
- C8 with 0.63× reducer

The selected optical configuration shall provide enough metadata for plate solving, including focal length, pixel size, and image dimensions where available.

---

### HLR-PA-006 — Guide Camera Fallback

If the main C8 camera repeatedly fails to plate solve, the system shall offer guide-camera fallback.

The system shall indicate that this is less optimal but better than stopping the workflow.

If the guide camera is mounted in a separate guide scope, the system shall warn that mechanical flexure or misalignment may reduce final accuracy.

Preferred camera priority:

1. Main C8 camera
2. OAG guide camera
3. Separate guide scope camera

---

### HLR-PA-007 — One Camera per Measurement Run

The system shall use one selected camera and one optical configuration consistently throughout a measurement run.

If the user switches camera or optical configuration, the measurement sequence shall restart.

---

### HLR-PA-008 — First HOME Plate Solve

The system shall capture and plate solve the first image at HOME.

The first HOME solve shall be used to:

- verify that plate solving works
- estimate whether the telescope points close enough to the northern celestial pole
- detect gross polar alignment errors
- decide whether coarse pre-alignment is required

The first HOME solve shall not be treated as the final precise polar alignment measurement.

---

### HLR-PA-009 — Coarse Pre-Alignment Guidance

If the HOME plate solve shows that the telescope is far from the northern celestial pole, the system shall guide the user through coarse mechanical correction.

The coarse correction shall be clearly labelled as rough pre-alignment.

The system shall especially check whether the azimuth error is likely outside the practical range of the azimuth fine-adjustment screws.

Example classification:

| Error from NCP | Suggested interpretation |
|---:|---|
| > 5° | Rough tripod or mount-head repositioning recommended |
| 1°–5° | Likely outside fine azimuth adjustment comfort range |
| < 1° | Suitable for precise RA-axis measurement |

The system may also warn if altitude appears unusually far off, but altitude has a larger mechanical scale and is usually less critical for the rough phase.

---

### HLR-PA-010 — RA Movement Requested Through Caller

The algorithm shall request RA movements from the caller.

The caller shall command OnStep through the mount-control adapter.

The algorithm shall receive the movement result back from the caller.

The algorithm shall not directly command OnStep.

Example abstract action:

```text
REQUEST_RA_OFFSET(+15°)
```

---

### HLR-PA-011 — RA-Only Measurement Movement

The system shall acquire polar measurement frames by rotating the mount around the RA axis only.

DEC shall remain constant.

The default movement plan shall avoid large rotations such as +90°.

Suggested default movement plan:

```text
Frame 1: HOME
Frame 2: RA +15°
Frame 3: RA +30°
Optional frame 4: RA +45°
```

Alternative if the positive direction is unsafe or not configured:

```text
Frame 1: HOME
Frame 2: RA -15°
Frame 3: RA -30°
Optional frame 4: RA -45°
```

The exact direction and maximum RA offset shall be configurable.

---

### HLR-PA-012 — Safe Movement Envelope

Before each commanded RA movement, the system shall check a configured safe movement envelope.

The safe movement check shall consider at least:

- maximum allowed RA offset
- configured movement direction
- cable slack expectation
- mount/tripod collision risk as far as configured
- user-confirmed safety constraints

The system shall not infer collision safety from plate solving alone.

---

### HLR-PA-013 — Optional Horizon Profile

The system should optionally support a horizon or obstruction profile.

The horizon profile may define minimum usable altitude by azimuth.

The system should warn or reject measurement positions that point into known obstructions such as trees, houses, roof edges, or the ground.

Example profile format:

```csv
azimuth_deg,elevation_min_deg
0,25
30,20
60,35
90,40
120,30
```

The horizon profile is an obstruction check, not a physical collision model.

---

### HLR-PA-014 — Minimum Solved Frames

The system shall require at least three successful plate solves at different RA-axis positions.

If one of the first three solves fails, the system shall attempt at least one additional frame at another safe RA offset.

The system should support more than three solved frames to improve robustness and reject outliers.

---

### HLR-PA-015 — Polar Error Calculation

From the solved frame positions, the system shall estimate the apparent direction of the mount RA axis on the celestial sphere.

The system shall compare this apparent RA-axis direction with the true northern celestial pole.

The output shall include:

- total polar alignment error
- altitude correction component
- azimuth correction component
- qualitative alignment status

The result shall be displayed in degrees, arcminutes, or arcseconds as appropriate.

---

### HLR-PA-016 — User-Readable Correction Directions

The system shall display correction directions in mechanical polar-axis terms:

- raise polar axis
- lower polar axis
- move polar axis east
- move polar axis west

Mount-specific screw instructions may be added later through a configurable mount profile.

The MVP shall avoid assuming that “left screw” or “right screw” has a universal meaning.

---

### HLR-PA-017 — Passive Live Fine Adjustment

During ALT/AZ screw adjustment, the system shall not command RA or DEC slews.

The user physically adjusts the mount.

The system shall repeatedly:

1. capture image
2. plate solve image
3. recalculate remaining polar error
4. display updated correction

---

### HLR-PA-018 — User-Selected Target Precision

The user shall be able to select a target polar alignment precision.

Suggested presets:

| Preset | Target |
|---|---:|
| Rough visual | 30 arcmin |
| Basic tracking | 10 arcmin |
| Guided imaging | 5 arcmin |
| Good imaging | 2 arcmin |
| High precision | 1 arcmin |
| Very high precision | 30 arcsec |
| Custom | user-defined |

---

### HLR-PA-019 — Alignment Quality Classification

The system shall classify the current alignment quality.

Suggested classification:

| Remaining polar error | Status |
|---:|---|
| > 5° | Very far off; rough mechanical adjustment recommended |
| 1°–5° | Far off; probably outside fine screw comfort range |
| 15′–1° | Roughly aligned, needs correction |
| 5′–15′ | Moderate |
| 1′–5′ | Good |
| 30″–1′ | Very good |
| < 30″ | Excellent |

The system shall make clear that perfect `0.0000` alignment is not practically required.

---

### HLR-PA-020 — Optional Second Refinement Run

After one successful correction, the system shall offer a second measurement run.

The second run should use the corrected mount position as the new baseline.

The purpose is to improve final accuracy after the first rough-to-fine correction cycle.

---

### HLR-PA-021 — Failure Handling

The system shall handle at least these failure cases explicitly:

- first HOME plate solve fails
- too few stars detected
- main C8 camera plate solving repeatedly fails
- guide-camera fallback is unavailable
- RA movement request fails
- mount does not report movement completion
- fewer than three solved frames are available
- planned movement exceeds safe envelope
- planned position violates horizon profile
- residual error does not improve during adjustment
- correction direction appears inverted
- user stops the workflow manually

---

## 6. Suggested Workflow States

```text
IDLE
WAIT_FOR_HOME_CONFIRMATION
CAPTURE_HOME_FRAME
SOLVE_HOME_FRAME
CHECK_ROUGH_ALIGNMENT
REQUEST_USER_COARSE_AZ_ADJUSTMENT
PLAN_RA_MEASUREMENT_OFFSETS
REQUEST_RA_MOVE
CAPTURE_MEASUREMENT_FRAME
SOLVE_MEASUREMENT_FRAME
CHECK_SOLVE_COUNT
CALCULATE_POLAR_ERROR
SHOW_FINE_ADJUSTMENT_VECTOR
LIVE_PASSIVE_ADJUSTMENT
TARGET_REACHED
USER_STOPPED
OPTIONAL_SECOND_RUN
FAILED
```

---

## 7. Suggested Action-Based Architecture

The polar alignment workflow may be implemented as a command/result loop.

### Example Action Object

```python
from dataclasses import dataclass
from typing import Literal


PolarAlignmentActionKind = Literal[
    "REQUEST_USER_CONFIRMATION",
    "REQUEST_IMAGE_CAPTURE",
    "REQUEST_PLATE_SOLVE",
    "REQUEST_RA_OFFSET",
    "REQUEST_USER_COARSE_ADJUSTMENT",
    "START_LIVE_ADJUSTMENT",
    "DISPLAY_RESULT",
    "STOP",
    "FAILED",
]


@dataclass(frozen=True)
class PolarAlignmentAction:
    kind: PolarAlignmentActionKind
    offset_deg: float | None = None
    message: str | None = None
```

### Example Input Object

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class PolarAlignmentInput:
    user_confirmed: bool = False
    solved_frame: object | None = None
    mount_move_result: object | None = None
    user_stopped: bool = False
```

### Example Workflow Interface

```python
class PolarAlignmentWorkflow:
    def next_action(self, input_data: PolarAlignmentInput) -> PolarAlignmentAction:
        """Return the next required workflow action."""
        ...
```

### Example Application-Layer Usage

```python
action = workflow.next_action(input_data)

if action.kind == "REQUEST_RA_OFFSET":
    result = mount_port.move_ra_relative(action.offset_deg)
    input_data = PolarAlignmentInput(mount_move_result=result)

elif action.kind == "REQUEST_IMAGE_CAPTURE":
    frame = camera_port.capture_frame()
    input_data = PolarAlignmentInput(captured_frame=frame)

elif action.kind == "REQUEST_PLATE_SOLVE":
    solved = solver_port.solve(frame)
    input_data = PolarAlignmentInput(solved_frame=solved)
```

---

## 8. Responsibility Split

| Phase | Movement | Performed by |
|---|---|---|
| Initial HOME setup | Physical mount positioning | User |
| Coarse AZ correction | Rotate tripod or mount head | User |
| Measurement frame 2/3/4 | RA-axis movement | OnStep via caller |
| Fine ALT/AZ correction | Physical screws | User |
| Live adjustment imaging | No RA/DEC slew | System captures and solves only |
| Optional second run | RA-axis movement | OnStep via caller |

---

## 9. Final MVP Statement

The MVP shall provide a northern-hemisphere polar alignment assistant for an equatorial OnStep mount.

The user starts from mechanical HOME. The first HOME plate solve checks whether rough manual azimuth correction is needed. Once the mount is close enough, the workflow requests controlled RA-only movements through the caller, acquires at least three solved frames, estimates the mount RA-axis error, and guides the user through passive ALT/AZ screw adjustment using continuous plate solving.

The algorithm itself remains hardware-independent and communicates required mount movements as abstract actions.
