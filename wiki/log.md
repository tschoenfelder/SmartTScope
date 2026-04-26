# Wiki Log

Append-only record of all wiki operations.

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
