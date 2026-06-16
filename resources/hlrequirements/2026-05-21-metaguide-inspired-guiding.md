# SmartTScope MetaGuide-Inspired Guiding Tasklist

Goal: evolve SmartTScope guiding from classical single-exposure guide loops toward
a low-latency, video-aware guiding model inspired by MetaGuide, while staying
practical for the current Raspberry Pi 5 / Trixie 64 three-camera ToupTek setup.

This is not a plan to clone MetaGuide. It is a plan to adopt the key engineering
ideas that matter for SmartTScope: fast guide-camera cadence, low latency,
latest-frame semantics, live evidence about the guide star, and mount correction
logic that is measured against real results.

## Transcript Takeaways

MetaGuide differs from classical guiding and common PHD2-style usage in several
important ways:

- It treats guiding as a real-time video control loop, not as isolated guide
  exposures separated by long waits.
- It uses short video frames and stacks or averages recent frames to estimate
  the guide error with low latency.
- It emphasizes acting quickly on a recent measured error instead of waiting
  several seconds to avoid "chasing seeing".
- It keeps the user aware of the real guide star by showing a live guide-star
  view, not only a delayed guide graph.
- It rejects bad video frames from the measurement stack instead of blindly
  trusting every sample.
- It uses a hotspot/windowed centroid approach rather than assuming there is one
  universal centroid definition.
- It separates guide period from stack/integration time: corrections may happen
  every second while the centroid estimate is based on a shorter recent stack.
- It avoids overlapping measurement windows with active guide pulses, reducing
  self-induced feedback artifacts.
- It is designed to correct high-frequency gearbox errors that may matter more
  than slow periodic error on mid-range mounts.
- It provides immediate feedback for calibration, dithering, backlash, and mount
  responsiveness.
- It uses direct guide pulses and observes whether the mount actually responds
  promptly in RA and DEC.
- It supports off-axis guiding well, because OAG removes flexure and improves
  the relationship between guide star and imaging camera.
- It supports collimation using live in-focus star images, real-time stacking,
  Airy pattern inspection, and coma direction feedback.
- It values evidence-based tuning: evaluate the final image quality and measured
  guide behavior instead of following fixed folklore.

## Product Direction For SmartTScope

SmartTScope should add a "fast guiding" path beside the existing guide monitor:

- Default to native ToupTek camera adapters when SmartTScope starts all cameras.
- Use the already implemented latest-frame mailbox so stale guide frames are
  skipped instead of blocking the control loop.
- Support ATR585M as the long-exposure main camera while GPCMOS02000KPA and
  G3M678M guide/OAG streams continue at 0.5-1.0 s cadence.
- Allow G3M678M to act either as OAG/guide camera or as a planetary main camera.
- Add INDI only as a global fallback profile, not mixed with native in one run.
- Make all measurements observable in JSON/status APIs so Pi headless tests can
  prove behavior without a UI.
- Allow both `guide` and `oag` streams to run at the same time, but use only one
  as the active correction source at a time in normal operation.
- Allow automatic guide-source selection later: clouds or too few stars may
  temporarily favor the other guide source, while hardware/cable failures should
  stop and require user intervention.
- If `G3M678M` is configured as the main planetary camera, startup must fail or
  auto-disable any `oag` role that points to the same physical camera.
- Run autofocus/refocus for the main camera only between main exposure frames.
- Keep dithering out of the MVP and implement it as MVP+.
- First prove the guiding algorithm in measure-only mode before sending real
  OnStep guide pulses.

## Current Decisions

- `guide` and `oag` can both stream concurrently.
- Exactly one source is the active guiding source at a time for MVP.
- Source switching is allowed for transient quality issues such as clouds or
  insufficient stars, but physical camera failure should surface as an operator
  problem rather than silently hiding it.
- Duplicate physical camera use is detected by native SDK device ID. If the
  device ID is available, no additional model+serial fallback is needed for MVP.
- Main-camera autofocus is scheduled between imaging frames, never during an
  active main exposure.
- Dither is MVP+.
- First delivery is measure-only guiding: centroid, star quality, frame age,
  source selection, and would-be pulse output, but no actual mount movement.

## Phase 0 - Baseline And Contracts

- [x] Confirm native three-camera load on Raspberry Pi 5:
  `ATR585M` at 60 s, `GPCMOS02000KPA` at 0.5 s, `G3M678M` at 0.5 s.
- [x] Establish latest-frame mailbox semantics for camera streams.
- [x] Establish role-based camera config for `main`, `guide`, and `oag`.
- [x] Define a `GuideFrame` data contract:
  - role/camera identity
  - sequence number
  - captured timestamp and received timestamp
  - exposure time
  - frame shape/dtype
  - dropped-frame count at capture time
  - optional ROI crop metadata
- [x] Define a `GuideMeasurement` data contract:
  - centroid position in pixels
  - centroid confidence/quality
  - peak value and saturation flag
  - background/noise estimate
  - FWHM or HFD estimate
  - bad-frame rejection reason if rejected
  - measurement latency

## Phase 1 - Fast Guide Stream

- [ ] Add a `GuideCameraStream` service built on `ManagedCamera`.
- [ ] Allow guide stream config per role:
  - exposure time
  - cadence
  - ROI size
  - gain
  - offset
  - conversion gain
  - max frame age before discard
- [ ] Ensure each guide camera owns its own capture worker and camera lock.
- [ ] Guarantee no global camera lock blocks guide/OAG frames while the main
  camera is exposing for 30-60 s.
- [ ] Add stream status API:
  - running/stopped
  - latest sequence
  - captured count
  - dropped stale count
  - rejected bad-frame count
  - latest frame age
  - capture interval min/avg/max
- [ ] Extend `camera_loadtest` or add `guide_loadtest` to report frame-age and
  latency distributions, not only frame counts.
- [x] Add duplicate physical camera detection before opening configured roles:
  - resolve all native camera selectors to SDK device IDs
  - fail startup if two active roles map to the same device ID
  - allow explicit disable of `guide` or `oag` role when a camera is repurposed
    as main planetary camera.

## Phase 1.5 - Dual Guide Source Selection

- [x] Add `GuideSourceState` for each guide-capable role:
  - role
  - running/stopped
  - latest frame age
  - star detected
  - centroid confidence
  - saturation/too-faint flags
  - transient quality state
  - hard failure state
- [x] Add `GuideSourceSelector` service:
  - consume quality telemetry from `guide` and `oag`
  - choose one active source
  - prefer configured primary source while it is healthy
  - switch to secondary source on transient low-quality/no-star conditions
  - do not hide hard camera failures; report them clearly.
- [x] Add config:
  - `guiding.primary_role = "guide" | "oag"`
  - `guiding.allow_fallback = true`
  - `guiding.fallback_after_bad_frames = N`
  - `guiding.max_frame_age_s`
- [ ] Add status API fields:
  - available guide sources
  - active guide source
  - fallback reason
  - source health summary.

## Phase 2 - Centroid And Quality Measurement

- [ ] Implement a first centroid estimator suitable for small guide stars:
  - local background subtraction
  - thresholded/windowed centroid
  - configurable centroid ROI radius
  - saturation detection
- [ ] Add a hotspot/windowed centroid variant inspired by MetaGuide:
  - locate brightest guide-star core
  - center a small measurement window around that core
  - compute centroid only inside the guide-star core window
- [ ] Add bad-frame rejection:
  - no star detected
  - saturated star
  - peak too weak
  - shape too wide or split
  - centroid jump beyond configured sanity limit
- [ ] Add short-stack measurement:
  - keep recent accepted guide frames in a small rolling buffer
  - stack or average only frames within a configured time window
  - compute guide error from the most recent stack
  - expose stack size and stack age in telemetry
- [ ] Unit-test centroid behavior on synthetic stars:
  - clean Gaussian
  - noisy faint star
  - saturated core
  - hot pixel near star
  - elongated OAG star
  - two nearby stars
- [ ] Hardware-test centroid stability on the `GPCMOS02000KPA` and `G3M678M`
  streams at 0.5 s and 1.0 s cadence.

## Phase 3 - Low-Latency Mount Corrections

- [ ] Add a `GuideController` service that consumes `GuideMeasurement` and sends
  mount guide pulses.
- [ ] Separate guide period from measurement stack time:
  - guide period: how often corrections are sent
  - stack window: how much recent video contributes to each correction
- [ ] Ensure measurement windows do not overlap active guide pulses when that
  would contaminate the next measurement.
- [ ] Add correction knobs:
  - RA aggressiveness
  - DEC aggressiveness
  - max pulse length
  - min move threshold
  - DEC backlash handling mode
  - RA-only mode
- [ ] Add mount responsiveness probe:
  - send small RA pulse and measure observed guide-star shift
  - send opposite RA pulse and measure return
  - optionally probe DEC and report backlash/lag
- [ ] Add safety limits:
  - stop guiding if guide star is lost for N consecutive measurements
  - stop guiding if mount pulses saturate repeatedly
  - stop guiding if measured movement is opposite calibration
- [ ] Add API endpoints for start/stop/status of fast guiding.
- [ ] Log every correction with timestamp, measured error, pulse command, and
  resulting next error for later diagnosis.

## Phase 3A - Measure-Only Guiding MVP

Before real guide pulses are enabled, SmartTScope should run the full guiding
algorithm in dry-run mode.

- [x] Compute guide error relative to a locked target centroid.
- [x] Track RA/DEC calibration as unavailable until the mount probe is run.
- [x] Produce would-be correction commands without sending them to the mount:
  - direction
  - duration
  - reason
  - clipped/not clipped
- [x] Expose dry-run telemetry in API and JSON logs.
- [ ] Validate on Raspberry Pi:
  - both guide streams active
  - active source selected
  - no stale frames processed
  - guide error is stable on a tracked star
  - main 30-60 s exposures do not affect guide measurement cadence.

## Phase 3B - Real Guide Pulse Enablement

- [ ] Add explicit config/API flag to permit real mount guide pulses.
- [ ] Require successful mount responsiveness probe before real pulses.
- [ ] Pause guide pulses during:
  - goto
  - recenter
  - autofocus/refocus
  - manual slew
  - park/home
- [ ] Permit guide measurement to continue during paused-pulse periods, but mark
  corrections as suppressed.
- [ ] Add operator-visible state when guiding is measuring but not correcting.

## Phase 4 - Calibration, Dithering, And Settle

- [ ] Add guide calibration per camera role and mount orientation:
  - RA axis vector in image coordinates
  - DEC axis vector in image coordinates
  - arcsec-per-pixel or pixel-per-pulse estimate
  - pier side / rotator angle metadata if available
- [ ] Store calibration for the session and invalidate it when mount orientation
  changes in a way SmartTScope cannot model.
- [ ] Add dither support:
  - request dither vector
  - move guide target, not necessarily the physical mount first
  - keep guiding during dither recovery
  - report settle when error is below threshold for a configured duration
- [ ] Add API for imaging workflow integration:
  - `POST /api/guiding/dither`
  - `GET /api/guiding/settled`
  - `POST /api/guiding/pause`
  - `POST /api/guiding/resume`
- [ ] Ensure long main-camera exposures can request dither between frames while
  guide/OAG streams continue.
- [ ] Treat dither as MVP+; do not block first measure-only guiding delivery on
  dither support.

## Phase 5 - Live Evidence And UI

- [ ] Add a guide-star telemetry image endpoint:
  - cropped guide ROI
  - selected centroid point
  - target point
  - recent trail/error vector
  - accepted/rejected frame marker
- [ ] Add guiding status panel:
  - RA/DEC error graph
  - RMS over recent window
  - correction pulses
  - frame cadence and latency
  - dropped/rejected frame counts
- [ ] Show a live guide-star view even when no correction is active.
- [ ] Make the graph update cadence independent from guide period so users see
  behavior continuously, not only after corrections.
- [ ] Add headless JSON telemetry for the same information, because the Pi test
  path must work without UI.

## Phase 6 - Collimation Path Inspired By MetaGuide

SmartTScope already has tri-Bahtinov collimation work. MetaGuide adds a separate
in-focus star/Airy-pattern style that may be valuable later.

- [ ] Add a research task for in-focus star collimation:
  - bright star near zenith
  - short exposure video stream
  - optional IR/red filter
  - real-time stacking of star core
  - Airy ring/profile visualization where sampling permits
- [ ] Add coma-direction feedback for SCT-style collimation:
  - estimate asymmetry around the star core
  - indicate direction of residual coma
  - avoid claiming screw-turn advice until calibrated per telescope
- [ ] Keep this separate from tri-Bahtinov MVP until guiding is stable.

## Phase 7 - Raspberry Pi Hardware Acceptance Tests

- [ ] 10-minute three-camera load test:
  - main `ATR585M`: 60 s exposure / 60 s cadence
  - guide `GPCMOS02000KPA`: 0.5 s exposure / 0.5 s cadence
  - oag `G3M678M`: 0.5 s exposure / 0.5 s cadence
  - expected: zero camera errors, no main-camera starvation, dropped guide frames
    counted but not blocking.
- [ ] 30-minute fast-guiding dry run with no mount corrections:
  - compute centroids and telemetry only
  - verify latency, frame-age, and centroid stability.
- [ ] Mount pulse responsiveness test:
  - RA positive/negative pulses
  - DEC positive/negative pulses
  - report motion, backlash, and latency.
- [ ] Closed-loop guiding test:
  - start guiding on guide camera
  - run main camera 60 s exposures
  - record guide RMS, correction rate, dropped frames, and final image FWHM/HFD.
- [ ] Dither-and-settle test between main frames.
- [ ] Failure tests:
  - cover guide camera
  - unplug guide camera
  - start with missing OAG role
  - simulate mount pulse failure
  - verify clear status and no process hang.

## Open Design Questions

- Which mount guide-pulse API should be the primary production path for OnStep:
  direct serial LX200 commands, existing mount adapter methods, or INDI when in
  all-INDI mode?
- What is the first acceptable centroid metric for "good enough" guiding:
  pixel RMS, arcsec RMS, final image FWHM, or a combined score?
- How much guide ROI cropping can be pushed into the ToupTek SDK for bandwidth
  and latency, versus cropping after full-frame capture?
- Should we support predictive/periodic-error correction later, or first prove
  that fast reactive correction is sufficient?

## Near-Term Implementation Order

1. Add duplicate camera ID detection for configured camera roles.
2. Add `GuideFrame` and `GuideMeasurement` models.
3. Build guide/OAG stream status on the existing latest-frame mailbox.
4. Implement and test centroid measurement on synthetic frames.
5. Add `GuideSourceSelector` for active `guide` vs `oag` selection.
6. Add measure-only guide controller and headless guide telemetry CLI.
7. Validate measure-only guiding on Raspberry Pi with main 30-60 s exposures.
8. Add mount responsiveness probe.
9. Enable real guide pulses behind explicit config/API.
10. Add dither/settle as MVP+.
11. Add UI/live guide-star evidence after the headless path is proven.

## Success Criteria

- SmartTScope can guide from a latest-frame stream without blocking any camera.
- Guide frames older than the configured max age are skipped, not processed late.
- The user can see or retrieve the guide star, centroid, frame age, and
  correction decisions.
- A 60 s main exposure sequence can run while guide/OAG cameras continue at
  0.5-1.0 s cadence.
- Closed-loop guiding is measured by real Pi hardware telemetry, not assumed.
