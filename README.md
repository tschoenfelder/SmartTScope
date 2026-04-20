# SmartTScope

Autonomous telescope control software for a Celestron C8 OTA on a Raspberry Pi 5 with an OnStep V4 mount controller.

A user powers on, connects via an app, selects a target, and the system autonomously aligns, slews, centres, captures, stacks, and saves — with no manual astronomy steps required.

---

## Release state

**v0.1.0 — Walking skeleton (MVP vertical slice)**

The v0.1.0 release implements the core 9-stage pipeline end-to-end using deterministic mock adapters. A real ASTAP plate-solver adapter is included and activatable via FITS fixtures. Mount, camera, and live-stacking adapters are in development.

---

## Hardware requirements

| Component | Specification |
|---|---|
| Optical tube | Celestron C8 (2032 mm f/10 Schmidt-Cassegrain) |
| Compute | Raspberry Pi 5 |
| Mount controller | OnStep V4 (connected via USB or UART) |
| Imaging camera | ToupTek camera (INDI or ToupTek SDK) |

### Supported optical profiles

| Profile | Focal length | Field of view | Use case |
|---|---|---|---|
| C8 native | ~2032 mm | Narrow | Default — all DSO work |
| C8 + 0.63× reducer | ~1280 mm | Wider | Large nebulae and galaxies |
| C8 + 2× Barlow | ~4064 mm | Very narrow | Planetary and lunar |

---

## Software requirements

| Requirement | Minimum version |
|---|---|
| Python | 3.11 |
| pytest (test only) | 8.0 |
| ASTAP plate solver | Current release |
| ASTAP G17 star catalog | — |

No additional Python dependencies are required to run the core library. The `dev` extras install pytest for running the test suite.

### Operating system

The target deployment platform is **Raspberry Pi OS (64-bit)** running on a Raspberry Pi 5. Development and testing are also supported on Windows 11.

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-org>/smart-tscope.git
cd smart-tscope
```

### 2. Install the package

```bash
pip install -e .
```

To include test dependencies:

```bash
pip install -e ".[dev]"
```

### 3. (Optional) Install ASTAP for real plate-solver tests

1. Download ASTAP from [https://www.hnsky.org/astap.htm](https://www.hnsky.org/astap.htm).
2. Install to the default location:
   - **Windows**: `C:\Program Files\astap\`
   - **Linux**: follow the installer instructions; ensure `astap` is on `PATH`.
3. Download the **G17 star catalog** from the same page (recommended for C8 pixel scales).

---

## Running the tests

```bash
pytest tests/
```

Mock-based tests run immediately — no hardware or external tools required.

Real-solver tests skip automatically unless ASTAP and fixture FITS files are present.

### Activating real-solver tests

1. Install ASTAP with the G17 catalog (see above).
2. Place a single C8 native-focal-length frame of M42 at `tests/fixtures/c8_native_m42.fits`.
3. Place a blank or noise-only FITS frame (no stars) at `tests/fixtures/c8_native_blank.fits`.
4. Run `pytest tests/` — previously skipped tests will now execute.

See `tests/fixtures/README.md` for FITS acquisition guidance.

---

## What this release supports

### Session pipeline (fully mocked, end-to-end)

The v0.1.0 vertical slice runs the complete 9-stage session pipeline:

```
IDLE → CONNECTED → MOUNT_READY → ALIGNED → SLEWED → CENTERED
     → PREVIEWING → STACKING → STACK_COMPLETE → SAVED
```

Each stage is explicit. No stage is skipped. A failure surfaces a named error and halts the session rather than silently continuing.

| Stage | Description |
|---|---|
| Boot and connect | App connects; camera, mount, and focuser are checked |
| Mount initialisation | Unpark, enable sidereal tracking, verify no axis limits |
| Plate solve / align | Capture → solve → sync mount pointing model |
| GoTo target | Slew to M42 (RA 05h 35m 17.3s, Dec −05° 23′ 28″) |
| Recenter | Iterative plate-solve and correction slew (≤ 3 iterations, 2 arcmin tolerance) |
| Live preview | 5-second auto-stretched JPEG frames pushed to client |
| Live stacking | 10 × 30-second frames, registered and mean-stacked; client updated after each frame |
| Save | PNG output + JSON session log with full metadata |

### Real plate-solver adapter (ASTAP)

When ASTAP and fixture FITS files are present, the real solver adapter replaces the mock. Supports:

- Happy-path solve of a C8 M42 frame
- Failure detection on unsolvable (blank/noise) frames
- Pixel-scale hint passing (~0.38 arcsec/px for C8 native)

### Replay camera adapter

A FITS-replay camera adapter is included for integration testing without live hardware.

---

## What this release does not support

The following are planned for future milestones and are **not** implemented in v0.1.0:

- Real camera driver (ToupTek SDK / INDI)
- Real mount driver (OnStep LX200 serial protocol)
- Live stacking with real frame registration (astropy / ccdproc / astroalign)
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
  domain/       States, session log model
  ports/        Abstract interfaces — camera, mount, solver, stacker, storage
  workflow/     VerticalSliceRunner — linear 9-stage pipeline
  adapters/
    mock/       Deterministic fakes for all ports
    astap/      Real ASTAP plate-solver adapter
    replay/     FITS replay camera for integration testing
wiki/           Planning knowledge base (Markdown)
tests/
  integration/  Mock workflow and hybrid real-solver tests
  fixtures/     Place FITS frames here (see fixtures/README.md)
```

---

## Further reading

- [`wiki/vertical-slice-mvp.md`](wiki/vertical-slice-mvp.md) — full stage-by-stage specification
- [`wiki/requirements.md`](wiki/requirements.md) — complete MVP / MVP+ / Full requirement set
- [`wiki/hardware-platform.md`](wiki/hardware-platform.md) — hardware context and C8-specific constraints
- [`wiki/plate-solving.md`](wiki/plate-solving.md) — plate-solving design and rationale
- [`wiki/live-stacking.md`](wiki/live-stacking.md) — live-stacking design
