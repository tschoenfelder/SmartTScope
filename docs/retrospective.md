# SmartTScope — Project Retrospective

**Date**: 2026-04-21
**Roles covered**: Lead Developer · Architect · Requirements Engineer · Tester
**Trigger**: Project sponsor dissatisfied with progress

---

## Verdict upfront

The project has produced a **technically sound walking skeleton** with clean architectural principles and good test habits. What it has not produced is **progress toward a shippable product**. The gap between the current artefacts and anything that could run on real hardware is larger than the commit history suggests. This retrospective names that gap honestly.

---

## 1. Lead Developer perspective

### What was built

| Artefact | Status | Quality |
|---|---|---|
| Hexagonal port/adapter structure | Complete | Good |
| VerticalSliceRunner (9 stages) | Complete (mock-driven) | Good |
| SessionLog domain model | Complete | Production-quality |
| AstapSolver adapter | Complete | Production-quality for its scope |
| ReplayCamera adapter | Complete | Adequate for testing |
| Mock adapters (all 5 ports) | Complete | Good |
| FastAPI session API | Not started | — |
| Real camera adapter (ToupTek) | Not started | — |
| Real mount adapter (OnStep) | Not started | — |
| Real stacker (frame registration) | Not started | — |
| WebSocket frame push | Not started | — |
| Target catalog | Not started | — |
| Autofocus | Not started | — |

The walking skeleton represents approximately **20% of the MVP code surface**. The remaining 80% — real hardware drivers, API layer, and computational imaging — is not started.

### Code quality issues

**1. Python version mismatch — active bug**

`pyproject.toml` declares `requires-python = ">=3.11"`. The pytest cache (`cpython-310`) proves tests are being run on Python 3.10. This means the declared minimum Python version has never been verified. Either the constraint is wrong or the development environment is wrong. This must be resolved before anyone sets up a new development machine or Pi.

**2. No logging**

There is not a single `logging` call in the entire codebase. A telescope pipeline that runs for 10 minutes in the field with no diagnostic output is undebuggable when it silently fails. Python's `logging` module is available at zero cost. Every stage transition, every plate solve attempt, every capture call, and every WorkflowError should emit a structured log line.

**3. `ReplayCamera` returns `width=0, height=0`**

```python
# adapters/replay/camera.py:31
return Frame(data=data, width=0, height=0, exposure_seconds=exposure_seconds)
```

The FITS file contains the real dimensions. Reading them back as zero is a silent lie in the type. When a real stacker receives a `Frame` with `width=0`, it will fail or produce garbage. The replay adapter should parse the FITS header and populate actual dimensions.

**4. All tuning constants are module globals, not configuration**

```python
# runner.py
CENTERING_TOLERANCE_ARCMIN = 2.0
MAX_RECENTER_ITERATIONS = 3
PREVIEW_FRAMES = 3
STACK_DEPTH = 10
SLEW_TIMEOUT_S = 120.0
```

These values cannot be overridden without editing source. There is no config file, no environment variable injection, no per-session parameter. The first field test where a slew takes 130 seconds will require a source edit and a deploy.

**5. M42 is hardcoded in the business logic**

`M42_RA` and `M42_DEC` live at module scope in `runner.py`. The runner is called `VerticalSliceRunner` — that name signals its temporary nature — but the class has no `target` parameter. Extending it to any other object requires rearchitecting the class signature.

**6. No package version string**

`pyproject.toml` declares `version = "0.1.0"` but there is no `__version__` attribute in `smart_telescope/__init__.py`. There is no way to confirm at runtime what version is deployed.

**7. No CI pipeline**

The `.github/` directory exists but is empty. No workflow file runs the tests on push. Code that has never been run in CI has no quality guarantee across different environments.

### Optimization potential (developer view)

- The `_wait_for_slew()` polling loop burns CPU at 2-second intervals for up to 120 seconds. On a Pi 5, this is trivial. On a production system with multiple concurrent sessions it would matter. A callback-based or interrupt-driven mount state change would eliminate the poll entirely, but requires the OnStep serial adapter to support it.
- `_angular_offset_arcmin()` uses a small-angle approximation. At the C8's narrow FOV and typical centering offsets (< 10 arcmin) this is accurate enough — but it should be documented as an approximation, not left as implicit.
- The mock solver's result cycling (`min(call_index, len-1)`) is a clever pattern that silently repeats the last result indefinitely. This is useful but fragile: a test that provides exactly the wrong number of results will not fail loudly; it will silently reuse the last one.

---

## 2. Architect perspective

### Design quality

The hexagonal architecture is applied correctly and consistently. The state machine is explicit with no implicit transitions. These are genuine strengths. The critical design gaps were documented in `architecture-review.md`; this section adds what was missed there.

### Missing port: FocuserPort

The vertical slice spec (`wiki/vertical-slice-mvp.md` Stage 1) explicitly states:

> "Backend attempts connection to camera, OnStep mount, and **focuser**."
> "Focuser: INDI or direct USB — `connect()`, `move(steps)`, `get_position()`"

There is no `FocuserPort` in `smart_telescope/ports/`. It was not mocked, not injected, not tested. The focuser is mentioned in the requirements, the spec, and the Stage 1 acceptance criteria — but it does not exist in the code. This is not a deferred item; it is a gap between the spec and the implementation.

### Interface design issues across all ports

| Port | Issue |
|---|---|
| `CameraPort` | `Frame.data: bytes` — no format contract. Width and height fields exist but ReplayCamera sets them to 0. |
| `MountPort` | No `stop()` method. Unsafe in error paths. No position read used by runner despite `get_position()` existing. |
| `SolverPort` | Accepts `bytes` directly — no separation of FITS parsing from solving logic. |
| `StackerPort` | `StackFrame.data: bytes` — same type erasure as camera. `get_current_stack()` has no frame-count parameter; caller cannot request a specific stack depth. |
| `StoragePort` | `has_free_space()` is binary with no threshold. No method to estimate storage required before starting. |
| `FocuserPort` | Does not exist. |

### Architecture decision log is absent

There is no ADR (Architecture Decision Record) for any of the significant choices made:
- Why ASTAP over astrometry.net?
- Why synchronous pipeline over async?
- Why bytes over typed FITS objects?
- Why no target parameter on the runner?
- Why is OpticalProfile defined in `runner.py` rather than `domain/`?

These decisions were made implicitly. When they need to be revisited (and they will be), there is no record of the original rationale.

### Concurrency model decision deferred past the safe point

The architecture review flagged this. The additional concern: the first real adapter (ToupTek camera) will use the ToupTek SDK, which issues callbacks from a background thread. That SDK callback model is fundamentally incompatible with the current synchronous runner design. The conflict will surface on the first day of camera integration and will require a non-trivial restructuring.

---

## 3. Requirements Engineer perspective

### Requirements chain

```
raw/SmartTelescope.md
    → wiki/smart-telescope.md
    → wiki/requirements.md          (revised: requirements-review.md)
    → wiki/vertical-slice-mvp.md    (implementation spec for MVP slice)
    → smart_telescope/ (code)
    → tests/ (verification)
```

The chain exists and is traceable by following wiki-links. This is better than most hobby projects. The gaps are in quality and completeness.

### Requirements quality audit

**R1 — No requirement IDs**

Not a single requirement has an identifier. `wiki/requirements.md` has section numbers (§1–§13) but no item-level IDs. This means:
- Tests cannot be traced to requirements
- A failing test cannot be linked to a specific requirement
- Requirements cannot be referenced in commit messages or PR descriptions
- The audit trail from requirement to implementation to test does not exist

Impact: **High.** Any external review, acceptance test, or handover is blocked by the absence of IDs.

**R2 — All performance targets are TBD**

Requirements §12 lists 8 performance targets. Every single value is marked TBD:

```
Time-to-first-image          — TBD seconds
Centering accuracy           — TBD arcmin RMS
Plate-solve success rate     — TBD %
Live preview latency         — TBD ms
Live stack refresh rate      — TBD seconds
Unguided tracking drift      — TBD arcsec/min
Session reliability          — TBD hours unattended
Pi 5 thermal ceiling         — TBD °C
```

These are not TBD because they are genuinely unknown. Target values can be derived from the Seestar S50 and Vespera specifications, from the C8 hardware constraints, and from the Pi 5 datasheet. TBD in a requirements document means "no one made a decision." Until these have concrete values, no performance test can pass or fail, and no acceptance criteria can be verified.

**R3 — Twenty-three items still marked "(needs AC)"**

Requirements marked `(needs AC)` cannot be tested. Twenty-three items carry this flag across §§1–13. Selected examples with concrete suggested values:

| Requirement | Status | Suggested concrete AC |
|---|---|---|
| Device connect within 30 s | needs AC | Camera, mount, focuser connect within 30 s on nominal hardware |
| Plate-solve retry strategy | needs AC | Max 2 attempts; exposure doubles on retry (5 s → 10 s); error names stage |
| Centering tolerance | needs AC | Target within 2 arcmin RMS after ≤ 3 correction iterations |
| Preview latency | needs AC | First JPEG visible in app within 15 s of PREVIEWING state |
| Storage-full behaviour | needs AC | Session aborts cleanly; no partial PNG written; error names stage |

**R4 — Solar safety gate has no architecture or implementation path**

Requirements §5 marks solar safety as **MVP** and "hard safety gap":

> "Solar observation requires confirmed filter interlock or explicit user-validated solar mode; Sun must not be slewed to without it."

There is:
- No `SolarSafetyPort` or equivalent
- No mention in the runner
- No test coverage
- No ADR on how this will be enforced (software gate? hardware interlock? UI confirmation dialog?)

For a product that includes the Sun in its target catalog, this is both a legal and a safety issue. It is not a deferred feature; it is a hard MVP requirement that is completely absent from the implementation.

**R5 — FocuserPort required by spec, missing from code**

(See Architect section above — also a requirements traceability failure.)

**R6 — Spec and code diverge on API contract**

`wiki/vertical-slice-mvp.md` Stage 1 specifies:

> "App sends `POST /session/connect` — backend attempts connection to camera, OnStep mount, and focuser."
> "Backend returns device status: `{ camera: ok, mount: ok, focuser: ok }` or per-device error."

The code has no API. The runner has an `on_state_change` callback. These are not the same thing. The spec was written as a product promise but the implementation addresses none of the API surface described in it.

### Requirements–implementation traceability matrix (partial)

| Requirement (wiki/requirements.md) | Tag | Implemented | Tested |
|---|---|---|---|
| Automatic plate solving | MVP | Yes (ASTAP adapter) | Yes |
| GoTo + centering | MVP | Yes (mocked) | Yes |
| Live stacking (DSO) | MVP | No (mock only) | No (mock only) |
| Emergency stop | MVP | **No** | **No** |
| Solar safety gate | MVP | **No** | **No** |
| FocuserPort / focuser connect | MVP | **No** | **No** |
| Wi-Fi provisioning | MVP | **No** | **No** |
| Session API (REST + WS) | MVP | **No** | **No** |
| Electronic autofocus | MVP (elevated) | **No** | **No** |
| Optical profiles (runtime switch) | MVP (elevated) | Partial (construction-time only) | No |
| Frame quality rejection | MVP+ | **No** | **No** |
| Session persistence (reconnect) | MVP | **No** | **No** |
| Save FITS subframes | MVP+ | **No** | **No** |

Of the 11 non-negotiable MVP core items listed in requirements §MVP core, **4 are not started and 2 more are only partially addressed**.

---

## 4. Tester perspective

### Test coverage summary

```
tests/integration/test_vertical_slice.py      — 23 test cases
tests/integration/test_real_solver_replay.py  — 16 test cases (15 skip without ASTAP)
Total executable without hardware             — 28 test cases
Total with ASTAP + fixtures                   — 39 test cases
```

### Coverage gaps — untested code paths

**Gap T1 — Slew timeout is never exercised**

`_wait_for_slew()` raises `WorkflowError` after 120 seconds. `MockMount.is_slewing()` always returns `False`. The timeout path has zero test coverage. A one-line change to `MockMount` (`fail_slew_timeout: bool = False` → `is_slewing()` returns `True` until flagged) would expose this path. Currently, if the timeout logic contains a bug, no test will catch it.

**Gap T2 — Unpark failure is not tested**

`MockMount` accepts `fail_unpark=True` but no test in the suite uses it. The `_stage_initialize_mount` handler for unpark failure exists and is wired correctly, but it is unverified.

**Gap T3 — Recenter solve failure is not tested**

The suite tests "solver always fails" (which fails at the align stage). There is no test for "align succeeds, recenter solve fails." This is a distinct code path in `_stage_recenter` that is reachable in the field — e.g. a cloud passes between alignment and recentering.

**Gap T4 — Stacker failure is not tested**

`MockStacker` has `fail_on_frame` but no test uses it. A stacker failure during the stacking loop is a realistic failure mode (OOM, corrupt FITS) with no test coverage.

**Gap T5 — `_angular_offset_arcmin` has no unit test**

This function contains astronomy logic. It is used to determine whether centering succeeds or degrades. It is not tested independently. A regression in this function would be invisible to the test suite until a full integration run behaved unexpectedly.

**Gap T6 — Happy path plate solve attempt count is not verified**

`TestPlateSolveFails.test_attempts_are_counted` verifies `plate_solve_attempts == 2` on failure. No test verifies the count is `1` on a clean solve. If the runner accidentally called solve twice on success, no test would fail.

**Gap T7 — No test verifies `disconnect()` is called on failure**

The `finally` block calls `disconnect()` on both camera and mount. If a future refactor breaks this, sessions could leak hardware connections with no failing test.

**Gap T8 — `SessionLog.to_dict()` has no standalone unit test**

`to_dict()` is tested indirectly via `test_session_log_serializes_to_dict` and `test_session_log_written_to_storage`, but these tests run through the full pipeline. A broken serialization that only manifests on specific field values would be hard to isolate.

### Test quality issues

**Issue TQ1 — Mock tests live under `tests/integration/`**

All 23 mock-based tests in `test_vertical_slice.py` are functionally unit tests: they test the runner's logic in isolation with deterministic fakes and cross no real system boundary. Placing them in `integration/` misrepresents their scope. A reader expecting integration tests will look for cross-component behavior; a reader expecting unit tests will not look here.

**Issue TQ2 — Tests hardcode mock implementation detail**

```python
# test_vertical_slice.py:69-70
assert log.saved_image_path == "/mock/session_result.png"
assert log.saved_log_path == "/mock/session_log.json"
```

The test verifies a string literal that is defined inside `MockStorage`. If `MockStorage` changes its return value, these tests fail for the wrong reason. The test should verify that a path was saved (not None), not what specific string the mock returns.

**Issue TQ3 — No parametrize for failure variants**

`TestMountFails` has four separate test methods that all share the same structure. Pytest `@pytest.mark.parametrize` would reduce duplication and make it easy to add new failure modes.

**Issue TQ4 — Hybrid tests expose a design gap**

`test_wrong_pixel_scale_fails_or_degrades` contains this:

```python
if result.success:
    # then check coords are implausible
```

A test that allows two completely different outcomes (success or failure) and considers both valid is not verifying behaviour — it is documenting uncertainty. The pixel-scale enforcement behaviour of ASTAP should be understood and tested with a definite expected outcome.

---

## 5. Cross-cutting findings

### The "walking skeleton" framing is being used to defer too much

The walking skeleton pattern is legitimate: build the thinnest possible slice end-to-end, then flesh it out. The risk is that the skeleton phase extends indefinitely, and each new piece of mock code creates an illusion of progress without advancing toward real hardware operation.

At this point the skeleton is complete. The next commit should write real hardware code, not more mocks.

### Artefact quality is uneven

| Artefact | Quality |
|---|---|
| `wiki/vertical-slice-mvp.md` | High — detailed, staged, acceptance-criteria present |
| `wiki/requirements.md` | Medium — comprehensive but 23 items need AC, all perf targets TBD |
| `smart_telescope/domain/` | High — clean model, good serialization |
| `smart_telescope/ports/` | Medium — FocuserPort missing, Frame.data untyped |
| `smart_telescope/workflow/runner.py` | Medium — correct logic, hardcoded constants, no logging |
| `smart_telescope/adapters/astap/` | High — production-quality for its scope |
| `smart_telescope/adapters/mock/` | High — controllable, deterministic |
| `smart_telescope/adapters/replay/` | Low — width/height lie, no FITS header parsing |
| `tests/integration/test_vertical_slice.py` | Medium — good coverage, mislabelled, some fragility |
| `tests/integration/test_real_solver_replay.py` | Medium — good hybrid approach, one weak test |
| `docs/architecture-review.md` | High — thorough, honest |
| `docs/architecture-diagram.md` | High — six diagrams, all relevant |
| `README.md` | High — accurate, structured |
| `pyproject.toml` | Low — Python version claim unverified, no CI, no linting |

### What the sponsor is reacting to

The sponsor sees: weeks of work, 39 tests passing, architecture docs written, diagrams committed. What they do not see: nothing runs on real hardware, the API does not exist, 6 of the 11 MVP core items are not implemented, and the Python version claimed in the project metadata has never been used.

The gap is real.

---

## 6. Recommended actions (ranked by impact)

| Priority | Action | Owner | Effort |
|---|---|---|---|
| 1 | Fix Python version (use 3.11 consistently, update pyproject.toml or dev env) | Dev | 1h |
| 2 | Add FocuserPort to ports/ and mock; update runner to connect focuser | Dev | 1 day |
| 3 | Add Python logging to every stage transition and WorkflowError | Dev | 2h |
| 4 | Assign concrete values to all §12 performance targets | Req Eng | 1 day |
| 5 | Add tests for: slew timeout, unpark failure, recenter solve failure, stacker failure | Tester | 1 day |
| 6 | Add `stop()` to MountPort; wire cancellation Event into runner | Arch + Dev | 1 day |
| 7 | Replace `Frame.data: bytes` with typed `FitsFrame` domain object | Arch + Dev | 2 days |
| 8 | Create CI workflow (.github/workflows/test.yml) running pytest on Python 3.11 | Dev | 2h |
| 9 | Define solar safety gate architecture (software gate? UI confirmation?) | Arch + Req Eng | 1 day |
| 10 | Start OnStep serial adapter (real MountPort implementation) | Dev | 1 week |
| 11 | Start ToupTek camera adapter — this forces the async/threading decision | Dev + Arch | 1 week |
| 12 | Start FastAPI session API with session start endpoint | Dev | 3 days |

Items 1–9 address quality and completeness of existing artefacts. Items 10–12 are the first real product deliverables. Until item 10 or 11 exists, the project has not demonstrated it can control real hardware.

---

## Summary

The project foundation is sound. The hexagonal design, the state machine, the AstapSolver, and the test discipline are genuine assets. The problem is that the foundation has been polished rather than built upon. The MVP requires real hardware adapters, an API layer, and a target catalog — none of which exist. The requirements have 23 items without acceptance criteria and 8 performance targets with no values. Two MVP-mandatory safety features (emergency stop, solar gate) have no implementation path.

The walking skeleton is done. It is time to walk.
