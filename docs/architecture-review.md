# SmartTScope — Architecture Review

**Reviewer**: Senior Architect (10+ years embedded/distributed systems)
**Review date**: 2026-04-21
**Scope**: v0.1.0 codebase, wiki requirements, and hardware platform design

---

## Executive summary

The software skeleton is clean. The hexagonal (Ports & Adapters) structure is well-applied, the state machine is explicit and correct, and the session log model is production-quality. These are genuine strengths for a walking skeleton.

However, the current design has **five critical gaps** that will block a real deployment on the Raspberry Pi 5 before the next adapter layer is added. None of them require a rewrite — all five have clear resolution paths — but they must be addressed before writing real camera or mount drivers. A further **six significant issues** are architectural decisions that are currently deferred but need an explicit answer rather than an implicit default.

---

## Critical issues (block real hardware integration)

### C1 — No concurrency model

**Location**: `smart_telescope/workflow/runner.py`

The entire pipeline runs synchronously in a single thread. `_wait_for_slew()` blocks with `time.sleep()`. A 120-second slew means 120 seconds of total silence from the application — no state updates pushed to the client, no watchdog, no ability to accept an emergency stop command.

On Raspberry Pi 5, FastAPI is the planned API layer. FastAPI runs an asyncio event loop. Blocking the event loop for 120 seconds with `time.sleep()` in a request handler will lock the entire server.

**Concrete impact**:
- Preview loop (`_stage_preview`) captures frames sequentially but has no push mechanism — "push via WebSocket" is a comment, not code.
- Stacking loop captures 10 × 30-second frames = minimum 300 seconds of blocking execution.
- No ability to receive an emergency stop signal during any blocking stage.

**Resolution path**: Move the pipeline to a background thread or asyncio task. Expose a `cancel()` method via a threading `Event` checked at each blocking point. The port interface layer should use async where I/O-bound (camera, mount, solver). This is not a small change — plan it before writing real adapters.

---

### C2 — `Frame.data: bytes` is an opaque contract

**Location**: `smart_telescope/ports/camera.py`, `smart_telescope/ports/stacker.py`

`Frame.data` is typed as `bytes`. The stacker receives bytes and is expected to register and co-add them as pixel arrays. The solver receives bytes and must parse them as FITS. The stretcher (not yet implemented) must do the same.

Every real adapter will need to independently agree on what format those bytes are in. There is no enforcement mechanism. This is a latent type-safety failure that will surface as a runtime error in the first real adapter.

**Resolution path**: Introduce a `FitsFrame` type in the domain layer that carries both the raw bytes *and* parsed header metadata (pixel scale, exposure time, gain, temperature). Ports accept `FitsFrame`. Adapters produce and consume `FitsFrame`. The format contract is in the type, not in implicit agreement.

---

### C3 — ASTAP is a CLI subprocess with no Linux path

**Location**: `smart_telescope/adapters/astap/solver.py:14-21`

```python
_ASTAP_DEFAULT = Path("C:/Program Files/astap/astap.exe")
```

The default path is Windows-only. The deployment target is a Raspberry Pi 5 running Linux. On Linux, ASTAP must be on `PATH`. There is no default Linux path, no star catalog path configured, and no validation that the G17 catalog is present.

Additionally, each `solve()` call spawns a new `subprocess.run()`. ASTAP startup time (catalog index loading) can dominate solve latency on cold starts. At the C8's narrow FOV this is the worst case: blind solve with a cold ASTAP on an underpowered board.

**Resolution path**:
1. Add a Linux default path (typically `/usr/local/bin/astap` or `~/astap/`).
2. Add a `validate()` method that confirms the executable and at least one catalog index file are present before the session starts, not at the first solve attempt.
3. Document that catalog files must be co-located with the executable on Pi OS.

---

### C4 — Resource contention on Pi 5 is unaddressed

**Location**: Requirements §12 (performance targets all marked TBD), `wiki/live-stacking.md`

The Pi 5 has 4 ARM Cortex-A76 cores and up to 8 GB RAM. The concurrent workload for a live stacking session is:
- Camera USB driver thread (frame DMA from ToupTek)
- ASTAP solve subprocess (CPU-bound, single process)
- NumPy frame registration and stacking (CPU-bound)
- JPEG encoding and WebSocket push (I/O + CPU)
- FastAPI event loop

A C8 native frame from a typical ToupTek sensor (e.g. 6.3 MP at 16-bit) is approximately 13 MB raw FITS. Ten frames in memory simultaneously = 130 MB minimum. Add the running stack, the reference frame, and the registration intermediate = 400–500 MB realistic peak. On a 4 GB Pi 5 this is manageable; on a 2 GB model it risks OOM during stacking.

ASTAP during a blind solve with G17 catalog loads several hundred MB of star index data. If this overlaps with a stacking operation, memory pressure can cause the kernel to page, destroying real-time performance.

**Resolution path**:
1. Establish a concrete memory budget per component in requirements §12.
2. Serialize solve and stack operations (do not run concurrently) or assign them to separate cores via process affinity.
3. Cap ASTAP memory via its `-maxstars` flag during plate solving.
4. Define a thermal ceiling test (Pi 5 throttles at 85 °C under sustained load) — requirements §12 lists this as TBD.

---

### C5 — No emergency stop path

**Location**: `smart_telescope/ports/mount.py`, `smart_telescope/workflow/runner.py`

`MountPort` has no `stop()` or `abort()` method. Requirements §9 marks emergency stop as **MVP** ("hard safety requirement"). The current architecture has no mechanism to halt mount motion from outside the pipeline — not from the API, not from a signal handler, not from the client.

Combined with C1 (blocking pipeline), the current design makes emergency stop structurally impossible: the pipeline owns the thread, and there is no interrupt point.

**Resolution path**:
1. Add `stop() -> bool` to `MountPort`.
2. Add a cancellation `Event` to `VerticalSliceRunner` checked at every `time.sleep()` and between stages.
3. Wire the API layer's emergency stop endpoint to set this event and call `mount.stop()`.

---

## Significant issues (require explicit decisions)

### S1 — M42 is hardcoded in the runner

**Location**: `runner.py:17-18`

```python
M42_RA = 5.5881
M42_DEC = -5.391
```

The target is a module-level constant. There is no target catalog, no target selection input, and no way to observe any other object without editing source code. This is appropriate for the vertical slice but will require a genuine target catalog integration before the product is usable.

**Decision needed**: Define the target catalog format and the API contract for target selection before writing the client UI. A simple JSON catalog (Messier + NGC/IC) is sufficient for MVP; the solar safety gate (requirements §5) is a hard constraint on the catalog layer.

---

### S2 — No session persistence or crash recovery

**Location**: `smart_telescope/domain/session.py`

`SessionLog` is an in-memory dataclass. If the Pi loses power during a 300-second stacking run (10 × 30 s frames), all captured data is lost. Requirements §13 marks power-loss handling as **MVP** ("file integrity after interruption").

**Decision needed**: Define a checkpoint strategy. The minimum viable approach is to write a partial session log and save each integrated FITS sub-frame to disk as it is captured, not only at the end. This also enables the multi-night continuation feature (requirements §9) with minimal additional work.

---

### S3 — Client/server topology is undefined

The wiki and requirements reference a "mobile/web client" and "FastAPI backend" but the network topology is not defined anywhere in the codebase or wiki:

- Does the Pi serve the client directly over its own Wi-Fi hotspot, or via the home network?
- Is TLS required? (It should be for any authentication.)
- What is the API authentication model?
- WebSocket vs. Server-Sent Events for frame push — the wiki mentions both.

**Decision needed**: Document the network model. The Pi-as-hotspot model (common in commercial smart telescopes) has different constraints than the home-network model (NAT traversal, mDNS discovery). This affects the Wi-Fi provisioning requirement (§2) significantly.

---

### S4 — MountPort `disconnect()` is unsafe in all error paths

**Location**: `runner.py:101`

```python
finally:
    self._mount.disconnect()
    self._camera.disconnect()
```

`disconnect()` is called unconditionally, including when the mount is mid-slew (e.g. a WorkflowError during the goto stage). Abruptly disconnecting a serial connection to OnStep while the mount is tracking or slewing is undefined behavior — the mount may continue moving with no host control, or it may fault.

**Resolution path**: `MountPort` should expose a `is_safe_to_disconnect() -> bool` and a `stop()` method. The finally block should call `stop()` first, wait for confirmation, then disconnect.

---

### S5 — OpticalProfile has no runtime validation

**Location**: `runner.py:43-46`

```python
C8_NATIVE   = OpticalProfile("C8-native",   pixel_scale_arcsec=0.38)
C8_REDUCER  = OpticalProfile("C8-reducer",  pixel_scale_arcsec=0.60)
C8_BARLOW2X = OpticalProfile("C8-barlow2x", pixel_scale_arcsec=0.19)
```

Profiles are constants. Nothing prevents a caller from passing an arbitrary `OpticalProfile(name="custom", pixel_scale_arcsec=999.0)`. Requirements §11 specifies that the app must enforce valid optical train combinations. The architecture needs a profile registry with validation — not just Python constants.

---

### S6 — Storage port `has_free_space()` is a binary check

**Location**: `smart_telescope/ports/storage.py`

`has_free_space()` returns a `bool` with no threshold parameter. There is no watermark (warn at 10%, fail at 5%), no quota, and no estimate of how much space the current session will consume before it starts. Requirements §8 marks storage-full handling as **MVP**.

**Resolution path**: Change to `free_space_bytes() -> int` at the port level. The runner should estimate required space before starting a session (frames × estimated frame size) and refuse to start if insufficient space is available, rather than failing at the save stage after 300 seconds of imaging.

---

## What is working well

These are genuine architectural strengths that should be preserved:

1. **Hexagonal architecture is cleanly applied.** Domain, ports, and adapters are properly separated. The mock adapter set means the pipeline is fully testable without hardware. This is the right foundation.

2. **State machine is explicit and correct.** Every transition is intentional, `CENTERING_DEGRADED` is properly modelled as a non-fatal state, and `FAILED` is terminal. No implicit state transitions anywhere.

3. **SessionLog is production-quality.** Stage timestamps, centering iterations, plate solve attempt count, warnings list — this is the right data model for a real observability and debugging story. The `to_dict()` serialization is complete.

4. **WorkflowError carries stage context.** Errors are named and staged, which directly supports the requirements' mandate for named, actionable error messages rather than generic failures.

5. **OpticalProfile concept is correct.** Parameterizing the pixel scale hint through the profile and passing it to the solver is the right abstraction. It correctly anticipates the optical-train-awareness requirement.

6. **AstapSolver is production-ready for its scope.** Subprocess management, timeout, INI parsing, and RA conversion from degrees to hours are all correct. The `find_astap()` utility is a good pattern.

---

## Risk register

| ID | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | Blocking pipeline locks FastAPI event loop | High | Critical | Async pipeline or background thread before API layer |
| R2 | ASTAP not found on Pi OS at session start | High | High | Add `validate()` call at startup; add Linux default path |
| R3 | OOM during concurrent solve + stack on 4 GB Pi 5 | Medium | High | Serialize operations; define memory budget |
| R4 | Mount left moving after disconnect on error | Medium | High | Add `stop()` to MountPort; fix finally block |
| R5 | No emergency stop reachable from API | High | Critical | Cancellation Event + MountPort.stop() |
| R6 | Frame.data format mismatch between adapters | Medium | High | Introduce FitsFrame domain type |
| R7 | Power loss during stacking loses all data | Medium | Medium | Write sub-frames to disk per capture |
| R8 | C8 narrow FOV causes blind solve failure | High | Medium | Wide-field assist camera or staged solve (already in requirements) |

---

## Recommended next steps (priority order)

1. **Define the async/threading model** before writing any real adapter. Decision: async FastAPI with the pipeline in a `BackgroundTask`, or a dedicated thread with a queue-based event bus. Either is defensible; the current synchronous model is not.
2. **Add `stop()` to MountPort and a cancellation Event to the runner.** This unblocks emergency stop and fixes the unsafe disconnect.
3. **Introduce `FitsFrame` as a typed domain object.** Prevents format-contract bugs before they reach real hardware.
4. **Add Linux ASTAP path and a `validate()` pre-flight check.** Essential before any Pi 5 deployment.
5. **Set concrete values for all §12 performance targets.** Without measurable targets the Pi 5 thermal and resource story cannot be validated.

---

## Architecture diagrams

See [`architecture-diagram.md`](architecture-diagram.md) for full system, module, state machine, and deployment diagrams.
