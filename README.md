# SmartTScope

Autonomous telescope control software for a Celestron C8 OTA on a Raspberry Pi 5 with an OnStep V4 mount controller.

A user powers on, connects via an app, selects a target, and the system autonomously aligns, slews, centres, captures, stacks, and saves — with no manual astronomy steps required.

---

## Release state

**v0.1.0 — Sprint 10 complete**

616 unit tests, 91%+ coverage, CI green. The core 8-stage session pipeline runs end-to-end with stop-event cancel, tracking-lost guard, and periodic mid-stack recentering. Real hardware adapters for the OnStep mount, focuser, and ToupTek camera are complete and unit-tested (hardware validation pending full field test). A FastAPI REST + WebSocket layer with a static HTML control panel is live. Simulator adapters let the full app run without any hardware attached.

The Sky Shot MVP flow is end-to-end from a cold parked state: Connect All → GoTo Sky (auto-unparks, computes meridian RA/Dec from LST and observer latitude) → Snap → Park. The 110-object Messier catalog is bundled; type a designation or common name in the Target box to fill RA/Dec for GoTo. Observer location defaults to Usingen, Hesse (50.336°N 8.533°E) and is overridable via `OBSERVER_LAT` / `OBSERVER_LON` env vars.

---

## Hardware requirements

| Component | Specification |
|---|---|
| Optical tube | Celestron C8 (2032 mm f/10 Schmidt-Cassegrain) |
| Compute | Raspberry Pi 5 |
| Mount controller | OnStep V4 (connected via USB or UART) |
| Imaging camera | ToupTek camera (INDI or ToupTek SDK) |
| Focuser | Motorised focuser (INDI or direct USB) |

### Supported optical profiles

| Profile | Focal length | Field of view | Use case |
|---|---|---|---|
| C8 native | ~2032 mm | Narrow | Default — all DSO work |
| C8 + 0.63× reducer | ~1280 mm | Wider | Large nebulae and galaxies |
| C8 + 2× Barlow | ~4064 mm | Very narrow | Planetary and lunar |

---

## Software requirements

### Runtime

| Requirement | Minimum version | Notes |
|---|---|---|
| Python | 3.13 | Target deployment: Raspberry Pi OS 64-bit |
| astropy | 6.0 | Frame parsing, WCS, coordinate maths |
| numpy | 1.26 | Array operations for stacking and stretching |
| FastAPI | 0.111 | REST and WebSocket session API |
| uvicorn | 0.29 | ASGI server |
| Pillow | 10.0 | JPEG encoding for preview frames |

### Development

| Requirement | Minimum version | Purpose |
|---|---|---|
| pytest | 8.0 | Test runner |
| pytest-asyncio | 0.23 | Async endpoint tests |
| pytest-cov | 5.0 | Coverage reporting and gate |
| pytest-mock | 3.15 | Mock fixtures |
| httpx | 0.27 | FastAPI test client |
| ruff | 0.4 | Linting and formatting |
| mypy | 1.10 | Static type checking (strict mode) |
| pyserial | 3.5 | OnStep serial adapter |
| build | 1.0 | Wheel builder (`scripts/build_dist.py`) |

### Plate solver (optional — required for real-solver tests)

| Requirement | Notes |
|---|---|
| ASTAP | Current release — [hnsky.org/astap.htm](https://www.hnsky.org/astap.htm) |
| ASTAP G17 star catalog | Download from the same page; recommended for C8 pixel scales |

### Operating system

The target deployment platform is **Raspberry Pi OS (64-bit)** running on a Raspberry Pi 5. Development and testing are also supported on **Windows 11**.

---

## Installation

### Raspberry Pi 5 (one-command setup)

An automated installer handles Python 3.13, system libraries, the virtual environment, and package installation:

```bash
git clone https://github.com/tschoenfelder/SmartTScope.git
cd SmartTScope
bash scripts/install_pi.sh
```

To also install the ASTAP plate solver in the same step:

```bash
bash scripts/install_pi.sh --with-astap
```

The script verifies the installation by running the full unit and integration suite before exiting. See [`scripts/install_pi.sh`](scripts/install_pi.sh) for details.

### Install from a pre-built wheel (fastest)

A wheel ships all `smart_telescope` modules and registers the `smarttscope` CLI entry point. Build one with the build agent, then copy it to any target machine:

```bash
# On the development machine
python scripts/build_dist.py

# On the target machine (Pi or otherwise)
pip install dist/smart_telescope-0.1.0-py3-none-any.whl
```

The script also writes `requirements.txt` with the five runtime packages, useful for a clean venv:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install dist/smart_telescope-0.1.0-py3-none-any.whl
```

See `scripts/build_dist.py --help` for options (`--sdist`, `--check`).

---

### Manual installation (Windows / Linux / macOS)

#### 1. Clone the repository

```bash
git clone https://github.com/tschoenfelder/SmartTScope.git
cd SmartTScope
```

#### 2. Install runtime dependencies

```bash
pip install -e .
```

#### 3. Install development dependencies

```bash
pip install -e ".[dev]"
```

This installs the test runner, coverage tool, linter, type checker, mock library, and all supporting packages.

#### 4. (Optional) Install ASTAP for real plate-solver tests

1. Download ASTAP from [https://www.hnsky.org/astap.htm](https://www.hnsky.org/astap.htm).
2. Install to the default location:
   - **Windows**: `C:\Program Files\astap\`
   - **Linux/Pi OS**: follow the installer; ensure `astap` is on `PATH`.
3. Download the **G17 star catalog** from the same page.

---

## Starting the server

### Hardware mode (Raspberry Pi)

```bash
bash scripts/start.sh
```

The script auto-detects the virtual environment (`.venv/` or in-place venv), exports hardware configuration, creates the image storage directory, and starts uvicorn on `http://0.0.0.0:8000`.

Default configuration:

| Variable | Default | Description |
|---|---|---|
| `ONSTEP_PORT` | `/dev/ttyACM0` | Serial port for the OnStep mount controller |
| `TOUPTEK_INDEX` | `0` | Zero-based index into `Toupcam.EnumV2()` device list |
| `STORAGE_DIR` | `~/smarttscope_data` | Directory for saved PNG images and JSON session logs |

Any variable can be overridden by prefixing the command:

```bash
ONSTEP_PORT=/dev/ttyUSB0 bash scripts/start.sh          # different serial port
TOUPTEK_INDEX=1 bash scripts/start.sh                    # second camera
STORAGE_DIR=/mnt/ssd/astro bash scripts/start.sh         # external drive
```

The script prints a pre-flight summary before starting:

```
══════════════════════════════════════════════════
  SmartTScope  2026-04-27 21:03:00
══════════════════════════════════════════════════

  ·  Python   : Python 3.13.3
  ·  Project  : /home/astro/astro_sw/SmartTScope

  ✓  Mount    : OnStep  →  /dev/ttyACM0
  ✓  Camera   : ToupTek index 0
  ✓  Storage  : /home/astro/smarttscope_data

── Starting server ───────────────────────────────
```

If the serial device is not found, a warning is printed but the server still starts (the device may connect after the mount powers on).

### Simulator mode (no hardware required)

```bash
SIMULATOR_FITS_DIR=~/fits bash scripts/start.sh
```

Activates `SimulatorCamera`, `SimulatorMount`, and `SimulatorFocuser`. Provide a directory of `.fits` files for the camera to replay.

### Pi pull-and-test (update + verify before starting)

```bash
bash scripts/pi_pull_and_test.sh   # pull latest, reinstall deps, run unit tests
bash scripts/start.sh              # start once tests pass
```

---

## Running the dev pipeline

Run all three checks before committing. CI enforces the same sequence on every push.

### Lint

```bash
ruff check smart_telescope/ tests/
```

All rules must pass with zero errors. Auto-fixable issues can be resolved with `--fix`.

### Type check

```bash
mypy smart_telescope/
```

Strict mode. Zero errors required.

### Tests with coverage

```bash
pytest tests/unit/ tests/integration/
```

The coverage gate is configured in `pyproject.toml`. The suite fails if coverage drops below **80%** (currently 86%).

Hardware tests are excluded from the standard run. They live in a separate workflow (`hardware.yml`) triggered manually via `workflow_dispatch`, or can be run locally with:

```bash
HW_TESTS=1 pytest tests/hardware/
```

### Run everything at once

```bash
ruff check smart_telescope/ tests/ && mypy smart_telescope/ && pytest tests/unit/ tests/integration/
```

---

## Activating real plate-solver tests

Real-solver integration tests skip automatically unless ASTAP and FITS fixtures are present.

1. Install ASTAP with the G17 catalog (see above).
2. Place a C8 native-focal-length frame of M42 at `tests/fixtures/c8_native_m42.fits`.
3. Place a blank or noise-only FITS frame at `tests/fixtures/c8_native_blank.fits`.
4. Run the test suite — the previously skipped tests execute automatically.

See `tests/fixtures/README.md` for FITS acquisition guidance.

---

## What this release supports

### Session pipeline (end-to-end)

The complete 8-stage session pipeline runs with mock, simulator, or real hardware adapters:

```
IDLE → CONNECTED → MOUNT_READY → ALIGNED → SLEWED → CENTERED
     → PREVIEWING → STACKING → STACK_COMPLETE → SAVED
```

Each stage is explicit. No stage is skipped. A failure surfaces a named error and halts the session rather than silently continuing.

| Stage | Description |
|---|---|
| Boot and connect | Camera, focuser, and mount connected; named error on any failure |
| Mount initialisation | Unpark, enable sidereal tracking, verify no axis limits |
| Plate solve / align | Capture → solve → sync mount pointing model |
| GoTo target | Slew to M42 (RA 05h 35m 17.3s, Dec −05° 23′ 28″) |
| Recenter | Iterative plate-solve and correction slew (≤ 3 iterations, 2 arcmin tolerance) |
| Live preview | 5-second auto-stretched JPEG frames pushed to client |
| Live stacking | 10 × 30-second frames, registered and mean-stacked; client updated after each frame |
| Save | PNG output + JSON session log with full metadata |

### REST API and control panel

A FastAPI application (`app.py`) runs on uvicorn and provides:

| Endpoint | Description |
|---|---|
| `GET /` | Static HTML control panel (auto-refreshes on load) |
| `GET /api/mount/status` | RA, Dec, state |
| `POST /api/mount/unpark` / `track` / `stop` / `goto` | Mount commands |
| `POST /api/mount/park` / `disable_tracking` | Park and stop tracking |
| `POST /api/mount/goto_sky?elevation=80` | Slew to meridian at elevation (auto-unparks, solar gate applied) |
| `GET /api/focuser/status` | Position, moving flag |
| `POST /api/focuser/move` / `nudge` / `stop` | Focuser commands |
| `GET /api/cameras` | Enumerate connected ToupTek cameras via SDK |
| `POST /api/session/connect` | Connect all devices; returns per-device `{status, error, action}` |
| `GET /api/solver/status` | Check ASTAP executable and G17 catalog presence |
| `GET /api/catalog/search?q=m42` | Search the bundled 110-object Messier catalog |
| `GET /api/catalog/objects` | Full catalog list |
| `WS /ws/preview` | Stream live auto-stretched JPEG frames from the camera |
| `WS /ws/stack` | Stream the current mean stack as JPEG + frame-count metadata |

Adapter selection is controlled by environment variables (see [Starting the server](#starting-the-server)). Omit all hardware variables to fall back to mock adapters for development.

### Hardware adapters

| Adapter | Status |
|---|---|
| `OnStepMount` | Complete — LX200 serial protocol; connect, goto, sync, track, stop, park, disable_tracking |
| `OnStepFocuser` | Complete — F-command set; move (absolute), is_moving, stop |
| `ToupcamCamera` | Written and unit-tested; hardware validation pending hardware access |

### Simulator adapters

Three simulator adapters let the full app run without hardware attached. Each supports a configurable delay parameter so the app loop can be exercised in real time:

| Adapter | Constructor param | Behaviour |
|---|---|---|
| `SimulatorCamera(data_dir, speed=0.0)` | `speed` | Serves real FITS frames from disk; `speed=1.0` paces delivery to match exposure time |
| `SimulatorMount(slew_time_s=0.0)` | `slew_time_s` | Simulates SLEWING → TRACKING transition after the configured delay |
| `SimulatorFocuser(move_time_s=0.0)` | `move_time_s` | Simulates focuser travel; `is_moving()` returns True until the timer fires |

### Emergency stop

`runner.stop()` halts the mount immediately and cancels any active slew via a `threading.Event`. The session fails cleanly rather than hanging.

### Structured logging

Every state transition emits a named `INFO` log line via Python's standard `logging` module:

```
INFO smart_telescope.workflow.runner session=<uuid> state=CONNECTED
INFO smart_telescope.workflow.runner session=<uuid> state=MOUNT_READY
...
```

### Real plate-solver adapter (ASTAP)

When ASTAP and fixture FITS files are present, the real solver adapter replaces the mock. Supports:

- Happy-path solve of a C8 M42 frame
- Failure detection on unsolvable (blank/noise) frames
- Pixel-scale hint passing (~0.38 arcsec/px for C8 native)

### Simulator and replay camera adapters

- **SimulatorCamera** — serves real FITS frames from a directory; configurable delivery speed
- **ReplayCamera** — serves an explicit ordered list of frames for deterministic integration tests

---

## What this release does not support

The following are planned for future milestones and are **not** yet implemented:

- Live stacking with real frame registration (astroalign / ccdproc)
- Autofocus (electronic focus curve / V-curve)
- Optical profile switching at runtime
- Multi-target or multi-night sessions
- Mosaic mode
- Meridian flip handling
- Error recovery beyond surface-and-halt
- Native mobile client (iOS / Android)
- Scheduled observations
- Share / export workflow
- NGC / IC catalog (only Messier is bundled today)

---

## Project structure

```
smart_telescope/
  domain/         SessionState enum, FitsFrame, SessionLog, Messier catalog
  ports/          Abstract interfaces
    camera.py     CameraPort — connect, capture, disconnect
    focuser.py    FocuserPort — connect, move, get_position, is_moving, stop
    mount.py      MountPort — connect, goto, sync, stop, park, disable_tracking, disconnect
    solver.py     SolverPort — solve(frame, pixel_scale) → SolveResult
    stacker.py    StackerPort — reset, add_frame, get_current_stack
    storage.py    StoragePort — save_image, save_log, has_free_space
  workflow/
    _types.py     WorkflowError, OpticalProfile, constants
    stages.py     Pure stage functions (connect, align, goto, recenter, …)
    runner.py     VerticalSliceRunner — orchestration, stop(), logging
  adapters/
    mock/         Deterministic fakes for all ports (unit tests)
    simulator/    Time-simulated adapters — SimulatorCamera, SimulatorMount, SimulatorFocuser
    onstep/       Real OnStep V4 adapters — OnStepMount, OnStepFocuser (serial)
    touptek/      ToupcamCamera — ToupTek SDK, RAW-16, software trigger
    astap/        ASTAP plate-solver subprocess adapter
    replay/       FITS replay camera for integration testing
  api/
    deps.py       Singleton dependency providers; TOUPTEK_INDEX / ONSTEP_PORT / SIMULATOR_FITS_DIR
    mount.py      GET /api/mount/status, POST /api/mount/{unpark,track,stop,goto,park,disable_tracking,goto_sky}
    focuser.py    GET /api/focuser/status, POST /api/focuser/{move,nudge,stop}
    cameras.py    GET /api/cameras — ToupTek SDK camera enumeration
    catalog.py    GET /api/catalog/{search,objects} — bundled 110-object Messier catalog
    session.py    POST /api/session/connect — per-device {status, error, action}
    solver.py     GET /api/solver/status — ASTAP + G17 catalog presence check
    preview.py    WS /ws/preview — auto-stretched JPEG live preview
    stack.py      WS /ws/stack — live mean-stack JPEG + frame-count metadata
    event_log.py  Thread-safe circular log for serial command tracing
  app.py          FastAPI application factory
  static/
    index.html    Mount + focuser + live preview control panel

tests/
  unit/           Stage-isolation tests — fast, no real I/O
    workflow/     Runner, stage, logging, cancellation tests
    adapters/     Adapter unit tests (OnStep, ToupTek, simulator, replay)
    api/          FastAPI endpoint tests (httpx TestClient)
  integration/    Full pipeline tests with hand-rolled fakes
  hardware/       Real-hardware tests (skipped unless HW_TESTS=1)
  fixtures/       Place FITS frames here (see fixtures/README.md)

.github/
  workflows/
    ci.yml        Lint → type check → test + coverage on push / pull request
    hardware.yml  Hardware tests — manual trigger only (workflow_dispatch)

scripts/
  build_dist.py  Build agent — generates requirements.txt and wheel
  install_pi.sh  Automated installer for Raspberry Pi 5
  start.sh       Hardware startup script — activates venv, exports config, starts server
  pi_pull_and_test.sh  Pull latest code and run unit suite on the Pi

wiki/           Planning knowledge base (Markdown)
docs/           Architecture reviews, milestone plan, agile plan, test strategy
```

---

## Continuous integration

GitHub Actions runs on every push and pull request to `master` or `main`.

**`ci.yml`** — runs automatically:

1. `ruff check smart_telescope/ tests/` — zero lint errors
2. `mypy smart_telescope/` — zero type errors (strict mode)
3. `pytest tests/unit/ tests/integration/` — all tests pass, coverage ≥ 80%

**`hardware.yml`** — manual trigger only (`workflow_dispatch`):

4. `HW_TESTS=1 pytest tests/hardware/` — real-hardware tests on demand

---

## Further reading

- [`wiki/vertical-slice-mvp.md`](wiki/vertical-slice-mvp.md) — full stage-by-stage specification
- [`wiki/requirements.md`](wiki/requirements.md) — complete MVP / MVP+ / Full requirement set
- [`wiki/hardware-platform.md`](wiki/hardware-platform.md) — hardware context and C8-specific constraints
- [`wiki/plate-solving.md`](wiki/plate-solving.md) — plate-solving design and rationale
- [`wiki/live-stacking.md`](wiki/live-stacking.md) — live-stacking design
- [`docs/agile-plan.md`](docs/agile-plan.md) — sprint plan and milestone definitions
- [`docs/test-strategy.md`](docs/test-strategy.md) — testing pyramid and mock patterns
