# SmartTScope

Autonomous telescope control software for a Celestron C8 OTA on a Raspberry Pi 5 with an OnStep V4 mount controller.

A user powers on, connects via an app, selects a target, and the system autonomously aligns, slews, centres, captures, stacks, and saves — with no manual astronomy steps required.

---

## Release state

**v0.1.0 — Sprint 0 complete (foundation + TDD pipeline)**

The dev pipeline is fully operational on Python 3.13: lint (ruff), type checking (mypy strict), 133 unit and integration tests, 98% coverage, and GitHub Actions CI on every push. The core 8-stage session pipeline runs end-to-end using mock adapters. Real mount, camera, and live-stacking adapters are developed from Sprint 1.

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
| ruff | 0.4 | Linting and formatting |
| mypy | 1.10 | Static type checking (strict mode) |
| pyserial | 3.5 | OnStep serial adapter |

### Plate solver (optional — required for real-solver tests)

| Requirement | Notes |
|---|---|
| ASTAP | Current release — [hnsky.org/astap.htm](https://www.hnsky.org/astap.htm) |
| ASTAP G17 star catalog | Download from the same page; recommended for C8 pixel scales |

### Operating system

The target deployment platform is **Raspberry Pi OS (64-bit)** running on a Raspberry Pi 5. Development and testing are also supported on **Windows 11**.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/tschoenfelder/SmartTScope.git
cd SmartTScope
```

### 2. Install runtime dependencies

```bash
pip install -e .
```

### 3. Install development dependencies

```bash
pip install -e ".[dev]"
```

This installs the test runner, coverage tool, linter, type checker, and all supporting packages.

### 4. (Optional) Install ASTAP for real plate-solver tests

1. Download ASTAP from [https://www.hnsky.org/astap.htm](https://www.hnsky.org/astap.htm).
2. Install to the default location:
   - **Windows**: `C:\Program Files\astap\`
   - **Linux/Pi OS**: follow the installer; ensure `astap` is on `PATH`.
3. Download the **G17 star catalog** from the same page.

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

The coverage gate is configured in `pyproject.toml`. The suite fails if coverage drops below **80%** (currently 98%).

Hardware tests are excluded from the standard run and only execute when `HW_TESTS=1` is set:

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

### Session pipeline (fully mocked, end-to-end)

The v0.1.0 vertical slice runs the complete 8-stage session pipeline:

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

### Replay camera adapter

A FITS-replay camera adapter serves pre-recorded frames from disk, enabling integration tests without live hardware.

---

## What this release does not support

The following are planned for future milestones and are **not** implemented in v0.1.0:

- Real camera driver (ToupTek SDK / INDI)
- Real mount driver (OnStep LX200 serial protocol)
- Real focuser driver
- Live stacking with real frame registration (astroalign / ccdproc)
- `FitsFrame` typed domain object (deferred to Sprint 1)
- Autofocus
- Optical profile switching at runtime
- Multi-target or multi-night sessions
- Mosaic mode
- Meridian flip handling
- Error recovery beyond surface-and-halt
- Mobile or web client UI
- Scheduled observations
- Share / export workflow

---

## Project structure

```
smart_telescope/
  domain/       SessionState enum, SessionLog model
  ports/        Abstract interfaces
    camera.py   CameraPort — connect, capture, disconnect
    focuser.py  FocuserPort — connect, move, get_position, disconnect
    mount.py    MountPort — connect, goto, sync, stop, disconnect
    solver.py   SolverPort — solve(frame, pixel_scale) → SolveResult
    stacker.py  StackerPort — reset, add_frame, get_current_stack
    storage.py  StoragePort — save_image, save_log, has_free_space
  workflow/
    runner.py   VerticalSliceRunner — 8-stage pipeline, stop(), logging
  adapters/
    mock/       Deterministic fakes for all ports (camera, mount, focuser, …)
    astap/      Real ASTAP plate-solver adapter
    replay/     FITS replay camera for integration testing

tests/
  unit/         Stage-isolation tests — Mock(spec=Port), fast, no pipeline
    workflow/   Runner stage tests, logging tests, cancellation tests
    adapters/   Adapter unit tests (ASTAP subprocess, ReplayCamera)
    domain/     SessionLog serialisation tests
  integration/  Full pipeline tests with hand-rolled fakes
  hardware/     Real-hardware tests (skipped unless HW_TESTS=1)
  fixtures/     Place FITS frames here (see fixtures/README.md)

.github/
  workflows/
    ci.yml      Lint → type check → test + coverage on push / pull request

wiki/           Planning knowledge base (Markdown)
docs/           Architecture reviews, milestone plan, agile plan, test strategy
```

---

## Continuous integration

GitHub Actions runs on every push and pull request to `master`:

1. `ruff check smart_telescope/ tests/` — zero lint errors
2. `mypy smart_telescope/` — zero type errors (strict mode)
3. `pytest tests/unit/ tests/integration/` — all tests pass, coverage ≥ 80%

Hardware tests run on demand via `workflow_dispatch`.

---

## Further reading

- [`wiki/vertical-slice-mvp.md`](wiki/vertical-slice-mvp.md) — full stage-by-stage specification
- [`wiki/requirements.md`](wiki/requirements.md) — complete MVP / MVP+ / Full requirement set
- [`wiki/hardware-platform.md`](wiki/hardware-platform.md) — hardware context and C8-specific constraints
- [`wiki/plate-solving.md`](wiki/plate-solving.md) — plate-solving design and rationale
- [`wiki/live-stacking.md`](wiki/live-stacking.md) — live-stacking design
- [`docs/agile-plan.md`](docs/agile-plan.md) — sprint plan and milestone definitions
- [`docs/test-strategy.md`](docs/test-strategy.md) — testing pyramid and mock patterns
