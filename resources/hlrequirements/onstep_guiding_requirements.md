# Requirements Document: Guide-Camera Processing Pipeline for OnStep Corrections

## Overview

This document defines the requirements for a guide-camera processing subsystem running on a Raspberry Pi 5 that acquires frames through an existing camera adapter, tunes exposure and gain, reads offset from configuration, estimates guide-star error, and sends guide adjustments to OnStep through an existing mount adapter. OnStep supports pulse-guide commands in milliseconds, and common guiding stacks use pulse-style corrections while the mount maintains its own sidereal tracking internally.[cite:84][cite:92][cite:28]

The subsystem is intended to operate as an independent execution path so that guiding does not block or destabilize the main imaging and control workflow on the Raspberry Pi 5. Because the current camera adapter already manages multiple cameras in parallel, the design must minimize CPU load, avoid duplicate capture pipelines, and use bounded processing so that guiding remains cooperative with the rest of the system.[cite:28][cite:87][cite:95]

## Scope

The subsystem shall:

- Connect to a selected guide-capable camera through the existing camera adapter rather than opening device-specific camera drivers directly, so current multi-camera management remains the single authority for camera access.[cite:95]
- Read camera-tuning defaults and operational thresholds from configuration, including offset, gain limits, exposure bounds, cadence, and processing limits.[cite:28]
- Acquire frames or frame subsets suitable for guide-star measurement and transform those measurements into pulse-guide corrections sent through the existing OnStep adapter.[cite:84][cite:92]
- Run in a dedicated worker context that cannot block the main application event loop or overwhelm CPU resources on the Raspberry Pi 5.[cite:91][cite:87]

The subsystem shall not:

- Replace the existing camera adapter.
- Replace the existing OnStep adapter.
- Generate low-level motor step pulses directly from Python when the mount already supports pulse-guide style commands.[cite:84][cite:28]

## System Context

The operational model assumes the mount is already connected, aligned, and tracking sidereally before the guide subsystem becomes active. The guiding subsystem only measures residual drift and emits correction pulses of bounded duration, which is consistent with how pulse-guide control is used in common telescope-control systems and with OnStep’s documented pulse-guide command model.[cite:28][cite:84][cite:92]

The existing camera adapter currently handles multiple cameras in parallel. Therefore, the guide subsystem must behave as a client of that adapter and request a low-latency frame stream, snapshot stream, or ROI-capable stream rather than creating a second competing acquisition stack against the same hardware resource.[cite:95]

## Functional Requirements

### Camera connection

1. The subsystem shall select a camera by adapter-provided identifier, not by raw device path.
2. The subsystem shall verify camera availability, pixel format, frame dimensions, and whether ROI, binning, gain, exposure, and offset controls are supported before starting guiding.
3. The subsystem shall fail gracefully if the camera is unavailable, already exclusively locked, or not capable of the requested frame cadence.
4. The subsystem shall support monochrome and color sources, but the preferred processing path shall operate on a single luminance plane to minimize CPU load.

### Configuration

The subsystem shall load a configuration object or file before activation. The configuration shall include at least the following fields:

| Parameter | Purpose |
|---|---|
| `camera_id` | Selects the guide camera via the existing adapter. |
| `offset` | Black-level / offset value, read from configuration and applied if supported by the camera. |
| `gain_mode` | Manual or auto policy. |
| `gain_min`, `gain_max`, `gain_default` | Operational gain bounds. |
| `exposure_min_ms`, `exposure_max_ms`, `exposure_default_ms` | Exposure bounds and startup value. |
| `roi` | Optional region of interest for reduced processing load. |
| `binning` | Optional sensor or software binning. |
| `target_fps` or `target_cycle_ms` | Desired acquisition or control cadence. |
| `star_snr_min` | Minimum acceptable guide-star signal metric. |
| `star_peak_max` | Saturation avoidance threshold. |
| `deadband_px` | Error threshold below which no correction is sent. |
| `pulse_min_ms`, `pulse_max_ms` | Bounds for emitted guide pulses. |
| `guide_rate` | External configuration value corresponding to mount guide-rate assumptions. |
| `cpu_budget_pct` | Maximum intended CPU share for this subsystem. |
| `drop_frame_policy` | Whether to skip stale frames when the worker falls behind. |

The subsystem shall treat offset as a configuration-owned parameter and shall not attempt to auto-discover a new offset during normal guiding startup unless an explicit calibration mode is requested.[cite:28]

### Camera tuning

1. The subsystem shall apply `offset` from configuration first, if the camera exposes offset/black-level control.
2. The subsystem shall start with configured default exposure and gain values.
3. The subsystem shall support optional startup tuning that adjusts exposure and gain to reach a usable guide-star signal without saturating the star core.
4. Startup tuning shall prioritize exposure changes before aggressive gain increases, because guiding needs a measurable centroid rather than maximum analog amplification alone.[cite:28]
5. Startup tuning shall stop when one or more candidate stars satisfy configured quality thresholds such as SNR, non-saturation, and size limits.
6. Startup tuning shall honor hard bounds for exposure and gain and abort with a clear status if no usable star can be found inside configured limits.

### Frame acquisition

1. The subsystem shall request frames from the existing camera adapter in a non-blocking manner.
2. The subsystem shall support one of the following acquisition modes: latest-frame polling, callback delivery, or bounded queue delivery.
3. The subsystem shall process only the most recent frame when lag occurs, discarding stale frames rather than building an unbounded backlog.
4. The subsystem should support ROI acquisition or post-crop processing around the selected guide star to reduce memory bandwidth and CPU use.
5. The subsystem should support optional frame decimation so that a high-rate camera stream does not force full-rate analysis when the CPU budget is lower than the raw stream rate.

### Guide-star selection and tracking

1. The subsystem shall detect one or more candidate stars in an initial acquisition phase.
2. The subsystem shall rank candidates using configurable criteria such as SNR, compactness, distance from frame edges, and non-saturation.
3. The subsystem shall lock onto one primary guide star for the first implementation unless multi-star guiding is explicitly enabled later.
4. The subsystem shall compute a centroid or equivalent hotspot position per processed frame.
5. The subsystem shall maintain a reference lock position and compute frame-to-frame or frame-to-reference error in pixels.
6. The subsystem shall detect loss of lock and transition into reacquisition mode without blocking the main application.

### Correction generation

1. The subsystem shall translate pixel error into mount-axis correction commands using calibration values provided by the existing system or an external calibration phase.
2. The subsystem shall apply deadband, hysteresis, and pulse-duration limits before sending a correction.
3. The subsystem shall support RA-only guiding and RA+Dec guiding modes.
4. The subsystem shall emit guide corrections as bounded pulse-guide commands through the existing OnStep adapter, not as direct motor step sequences.[cite:84][cite:92][cite:28]
5. The subsystem shall wait for adapter acknowledgment, timeout, or completion state according to the adapter contract before assuming a pulse has been accepted.[cite:85]
6. The subsystem shall record pulse direction, duration, timestamp, and resulting measured residual for diagnostics.

### OnStep integration

The existing mount adapter shall expose an interface equivalent to the following logical operations:

- `is_connected()`
- `is_tracking()`
- `get_guide_rate()` or configured guide-rate assumption
- `pulse_guide(direction, duration_ms)`
- `abort_guiding()`
- `get_mount_state()`

The guide subsystem shall require the mount to be tracking before active guiding begins. OnStep pulse-guide behavior is based on guide movement for a specified time in milliseconds, and the design shall assume the mount firmware handles the actual timed motion internally once the command is accepted.[cite:84][cite:92]

## Processing Pipeline

The required nominal processing sequence is:

1. Load configuration.
2. Bind to the selected guide camera via the existing adapter.
3. Apply offset from config, then default exposure/gain.
4. Optionally run startup tuning to find usable exposure/gain values.
5. Start bounded frame acquisition.
6. Detect and select a guide star.
7. Enter guide loop: retrieve latest frame, crop ROI, compute centroid, estimate pixel error, transform to axis correction, clamp pulse duration, send pulse through the existing OnStep adapter, log result, and repeat.[cite:28][cite:84][cite:92]

The system should support a control cadence where image analysis and pulse dispatch are temporally decoupled by a bounded queue or latest-sample cache so that temporary latency in command handling does not stall frame capture.

## Concurrency and CPU-Control Requirements

### Execution model

The guide subsystem shall execute in a dedicated worker context separate from the main control flow. This may be implemented as a dedicated thread for orchestration plus a bounded worker for image analysis, or as a dedicated process if Python GIL contention or image-processing load materially affects the rest of the application.[cite:91][cite:87]

The preferred architecture is:

- Main application thread: orchestration, UI, state management, and system coordination.
- Camera adapter thread(s): existing multi-camera acquisition responsibilities.
- Guide worker: consumes latest guide frames from the adapter, performs lightweight analysis, and produces guide commands.
- Mount command worker: serializes guide pulse submissions to the existing OnStep adapter.

### Non-blocking guarantees

1. The guide subsystem shall never block the main application event loop while waiting for a frame.
2. The guide subsystem shall never block camera acquisition while waiting for mount-command completion.
3. The guide subsystem shall use bounded queues or latest-frame caches to prevent unbounded memory growth.
4. The guide subsystem shall shed work under load by dropping stale frames, shrinking ROI, lowering processed frame rate, or temporarily increasing control interval.
5. The guide subsystem shall expose telemetry for loop duration, queue depth, dropped frames, pulse latency, and CPU consumption.

### CPU budgeting

1. The subsystem shall target a configurable CPU budget and adapt its workload when the budget is exceeded.
2. The first mitigation step shall be frame decimation.
3. The second mitigation step shall be ROI reduction or simpler thresholding.
4. The third mitigation step shall be longer control intervals.
5. The subsystem shall avoid full-frame AI object detection by default because centroid-based star guiding is computationally lighter and more appropriate for this task than generic deep-learning inference on every frame.[cite:28][cite:87][cite:93]

## Performance Requirements

| Requirement | Target |
|---|---|
| Frame backlog | Must remain bounded; stale frames shall be droppable. |
| Memory growth | No unbounded growth during continuous operation. |
| Startup tuning duration | Configurable timeout; default should be finite and fail-safe. |
| Guide loop observability | Per-cycle timing and correction logging required. |
| Command latency handling | Adapter timeouts and delayed completions must be detectable.[cite:85] |
| Degraded mode | System shall continue main operation even if guiding is paused or disabled. |

The design shall favor deterministic bounded latency over maximum raw frame throughput. For guiding, the newest frame is more valuable than a complete history of delayed frames.[cite:28]

## Error Handling

The subsystem shall detect and report at least the following fault classes:

- Camera unavailable.
- Camera control unsupported for offset, gain, or exposure.
- No suitable guide star found within configured bounds.
- Guide-star lock lost.
- OnStep adapter disconnected.
- Pulse-guide timeout or adapter error.[cite:85]
- CPU budget exceeded for a sustained interval.

On recoverable errors, the subsystem should transition into a degraded state such as reacquire, pause guiding, or fall back to slower cadence rather than crashing the main application.

## Logging and Diagnostics

The subsystem shall write structured logs containing:

- Exposure, gain, and offset applied.
- Selected guide star metrics.
- Loop timing.
- Frame drop count.
- Current ROI.
- Pixel error and transformed axis error.
- Pulse direction and duration.
- Adapter response and timeout information.
- CPU and memory usage snapshots.

The subsystem should optionally expose a lightweight diagnostics channel for live inspection, such as current guide frame thumbnail, lock position, residual graph, and recent pulse history.

## Proposed Internal Interfaces

### Camera adapter contract

The existing camera adapter should expose a non-blocking interface similar to:

```python
class GuideFrameProvider:
    def open_stream(self, camera_id: str, mode: str, roi=None, binning=None): ...
    def set_controls(self, camera_id: str, exposure_ms=None, gain=None, offset=None): ...
    def get_capabilities(self, camera_id: str) -> dict: ...
    def get_latest_frame(self, camera_id: str): ...
```

### Guide worker contract

```python
class GuideWorker:
    def start(self): ...
    def stop(self): ...
    def pause(self): ...
    def resume(self): ...
    def get_status(self) -> dict: ...
```

### OnStep adapter contract

```python
class MountGuideAdapter:
    def is_connected(self) -> bool: ...
    def is_tracking(self) -> bool: ...
    def pulse_guide(self, direction: str, duration_ms: int) -> bool: ...
    def abort_guiding(self): ...
```

## Recommended Architecture Decision

The first implementation should use a dedicated guiding worker that consumes frames from the existing camera adapter through a latest-frame interface and emits pulse-guide commands through the existing OnStep adapter. This keeps the guider independent, avoids duplicate camera ownership, and aligns with OnStep’s millisecond pulse-guide model rather than low-level step generation.[cite:84][cite:92][cite:28]

If profiling shows that Python thread scheduling or image analysis materially impacts the rest of the Raspberry Pi 5 workload, the image-analysis stage should be isolated into a separate process while preserving the same adapter contracts. This approach contains CPU-heavy work, avoids blocking the main operation, and is compatible with the requirement that the current camera adapter already handles multiple cameras in parallel.[cite:91][cite:87][cite:95]

## Acceptance Criteria

The implementation shall be accepted when the following are true:

- The guide subsystem can attach to a configured camera via the existing adapter without breaking existing camera operations.
- Offset is read from configuration and applied when supported.
- Default exposure and gain are applied, and optional startup tuning converges or fails cleanly within configured bounds.
- The subsystem processes only the latest relevant frame under load and does not accumulate an unbounded backlog.
- Guide-star drift is converted into pulse-guide corrections sent through the existing OnStep adapter.
- Main application responsiveness remains acceptable while guiding is active on the Raspberry Pi 5.
- Disconnection, timeout, and loss-of-lock faults are surfaced without crashing the main application.[cite:84][cite:85][cite:92]
