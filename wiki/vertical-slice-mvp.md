# Vertical Slice — MVP Core

**Summary**: A single end-to-end scenario that exercises the full MVP promise of the SmartTelescope: from power-on to a saved stacked image, with no manual astronomy steps.

**Sources**: requirements.md, hardware-platform.md

**Last updated**: 2026-04-19

---

## Purpose

This slice is the first shippable proof-of-concept. It is not a demo and not a prototype — it is the real code path, intentionally narrowed to one target and one optical config. Every stage must work correctly, not just run. When this slice passes its acceptance criteria end-to-end, the MVP core is validated.

**Out of scope for this slice**: autofocus, target selection UI, optical profile switching, mosaic, guiding, meridian flip, error recovery UI, share/export. Those come after this works.

---

## Slice scenario

**Fixed inputs** (hardcoded for this slice):
- Optical config: C8 native (2032 mm, sensor pixel scale ~0.20 arcsec/px — exact value depends on camera)
- Target: M42 (Orion Nebula) — large, bright, always a good first target
- Sub-exposure: 30 seconds
- Stack depth: 10 frames
- Centering tolerance: 2 arcmin RMS

**Sequence**: Power on → connect devices → initialize mount → plate solve → GoTo M42 → recenter → live preview → stack 10 frames → save result + session log.

---

## Stages

### Stage 1 — Boot and device connect

**What happens**:
1. Pi boots. Application service starts automatically (systemd unit).
2. App (mobile/web client) connects to the Pi API via Wi-Fi.
3. App sends `POST /session/connect` — backend attempts connection to camera, OnStep mount, and focuser.
4. Backend returns device status: `{ camera: ok, mount: ok, focuser: ok }` or per-device error.
5. App displays connection status. Session cannot proceed until all three are `ok`.

**Acceptance criteria**:
- All three devices connect within 30 seconds under nominal conditions.
- If any device fails, the app names it and provides a retry action (not a generic error).
- Session state is `CONNECTED` after this stage.

**Key interfaces**:
- Camera: INDI or ASI SDK — `connect()`, `capture(exposure_sec)`, `get_image() → FITS`
- Mount: OnStep LX200 serial protocol over USB/UART — `connect()`, `get_state()`, `sync(ra, dec)`, `goto(ra, dec)`, `set_tracking(on)`
- Focuser: INDI or direct USB — `connect()`, `move(steps)`, `get_position()`

---

### Stage 2 — Mount initialization

**What happens**:
1. Backend reads mount state from OnStep: parked / unparked / slewing / at limit.
2. If parked → send unpark command and wait for completion.
3. Enable sidereal tracking.
4. Read current RA/Dec from mount.
5. Verify no axis limit is active.

**Acceptance criteria**:
- Mount reaches tracking state within 60 seconds of unpark command.
- Any limit violation stops the flow and surfaces a named error.
- Session state is `MOUNT_READY` after this stage.

**Key interfaces**:
- OnStep: `:hU#` (unpark), `:Te#` (enable tracking), `:GR#` / `:GD#` (read RA/Dec)

---

### Stage 3 — Plate solve / align

**What happens**:
1. Backend commands a 5-second capture at full resolution.
2. Image passed to plate solver (astrometry.net local index, or astap).
3. Solver returns RA/Dec of image center.
4. Backend sends sync command to OnStep with solved coordinates.
5. Mount pointing model updated.

**Acceptance criteria**:
- Solve succeeds within 60 seconds under nominal sky conditions.
- On failure: one automatic retry at 10-second exposure. If still failing: stop and surface error with suggested fix ("check polar alignment", "obstructed sky?").
- After sync, reported mount position matches solved position within 5 arcmin.
- Session state is `ALIGNED` after this stage.

**Key interfaces**:
- Plate solver: `solve(fits_image, pixel_scale_hint) → { ra, dec, pa, success }`
- OnStep: `:CM#` (sync to current target)

---

### Stage 4 — GoTo target

**What happens**:
1. Backend looks up M42 coordinates from bundled catalog: RA 05h 35m 17.3s, Dec −05° 23′ 28″.
2. Sends GoTo command to OnStep.
3. Polls mount state every 2 seconds until slewing stops.
4. Verifies mount is not at a limit after slew.

**Acceptance criteria**:
- Slew completes within 120 seconds (C8 on typical EQ mount).
- Mount reports target coordinates after slew (no timeout or stall).
- Session state is `SLEWED` after this stage.

**Key interfaces**:
- OnStep: `:Sr<ra>#`, `:Sd<dec>#`, `:MS#` (slew), `:D#` (slewing status)

---

### Stage 5 — Recenter

**What happens**:
1. Backend captures a 10-second frame.
2. Runs plate solver on the frame.
3. Calculates angular offset: `Δra = solved_ra − target_ra`, `Δdec = solved_dec − target_dec`.
4. If offset > 2 arcmin RMS: sends a correction slew and repeats from step 1.
5. Maximum 3 iterations. If still off after 3: surface warning and continue (do not abort).

**Acceptance criteria**:
- Target centered within 2 arcmin RMS in ≤3 iterations under nominal conditions.
- If centering fails after 3 iterations, session continues with a logged warning. User sees "centering degraded" status.
- Session state is `CENTERED` after this stage.

---

### Stage 6 — Live preview

**What happens**:
1. Backend enters preview loop: capture 5-second frames continuously.
2. Each frame: apply auto-stretch (histogram-based, asinh or linear with midpoint lift).
3. Encode as JPEG and push to client via WebSocket or Server-Sent Events.
4. Client displays the stream in the app preview panel.

**Acceptance criteria**:
- First preview frame visible in app within 15 seconds of stage start.
- Subsequent frames arrive at least every 10 seconds.
- Stretch is applied (image is not a raw dark blob).
- Session state is `PREVIEWING` after this stage.

**Key interfaces**:
- Stretch: `auto_stretch(fits_image) → ndarray` — scale pixel values to [0,255], apply midpoint lift
- Transport: WebSocket frame or SSE event per JPEG

---

### Stage 7 — Live stacking

**What happens**:
1. Backend switches from 5-second preview exposures to 30-second stacking exposures.
2. Each frame registered (aligned to first frame via star matching or WCS).
3. Running sum maintained in memory; mean image computed after each frame.
4. Mean image stretched and pushed to client after each integration.
5. Continues until 10 frames accumulated.

**Acceptance criteria**:
- Stack of N frames visibly improves SNR compared to single frame (subjective validation on first run).
- All 10 frames integrate without crash.
- Client sees updated image after each frame (≤ exposure time + 5 seconds latency per update).
- Session state is `STACKING` during, `STACK_COMPLETE` after 10 frames.

**Key interfaces**:
- Registration: `align_frame(reference_fits, new_fits) → aligned_ndarray` — use astropy or ccdproc
- Stack: running `np.sum` over aligned frames, divide by N for mean

---

### Stage 8 — Save result and session log

**What happens**:
1. Backend writes the final stacked image to disk as PNG (auto-stretched, 16-bit if possible).
2. File name: `session_<ISO8601>_M42_10x30s.png`.
3. Backend writes a JSON session log alongside it with:
   - `session_id`, `start_time`, `end_time`
   - `target`: name, RA, Dec
   - `optical_config`: focal_length, pixel_scale
   - `frames`: count, exposure_sec, rejected_count
   - `centering_offset_arcmin`: final value
   - `plate_solve_attempts`: count
   - `warnings`: list of any non-fatal issues raised during session
4. API responds to client with file path and log summary.

**Acceptance criteria**:
- PNG file written without error.
- JSON log contains all listed fields.
- File name is deterministic and ISO8601-formatted.
- If disk is full: write fails gracefully, surfaces error, no partial or corrupt file.

---

## State machine summary

```
IDLE → CONNECTED → MOUNT_READY → ALIGNED → SLEWED → CENTERED
     → PREVIEWING → STACKING → STACK_COMPLETE → SAVED
```

Each stage transition is explicit. The backend never skips a state. A failure in any stage emits an error event to the client with stage name and human-readable message, and halts progress rather than silently continuing.

---

## Component map

| Component | Responsibility | Library candidate |
|---|---|---|
| Camera driver | capture FITS frames | INDI / ZWO ASI SDK |
| Mount driver | OnStep LX200 protocol | custom serial, or INDI |
| Plate solver | sky position from image | astap (local) or astrometry.net local |
| Stretcher | auto-stretch FITS for display | astropy, numpy |
| Frame registrar | align frames for stacking | astropy / ccdproc / astroalign |
| Stacker | running mean | numpy |
| Session API | REST + WebSocket backend | FastAPI (Python) |
| Client | preview + controls | React (web) or Flutter (mobile) |

---

## What this slice does NOT prove

- Error recovery beyond surface-and-halt
- Autofocus
- Optical profile switching
- Multi-target sessions
- Any MVP+ feature

Each of those is the next slice, built on top of this one passing.

---

## Related pages

- [[requirements]]
- [[hardware-platform]]
- [[plate-solving]]
- [[live-stacking]]
- [[autofocus]]
