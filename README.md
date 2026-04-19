# SmartTScope

Autonomous telescope control software for a Celestron C8 OTA on a Raspberry Pi 5 with an OnStep V4 mount controller.

## Goal

A user powers on, connects via an app, selects a target, and the system autonomously aligns, slews, centres, captures, stacks, and saves — with no manual astronomy steps.

## Hardware

| Component | Role |
|---|---|
| Celestron C8 (2032 mm, f/10) | Optical tube |
| Raspberry Pi 5 | Onboard compute |
| OnStep V4 | GoTo mount controller |
| ZWO ASI camera (TBD) | Imaging sensor |

## Current state

Walking skeleton — MVP vertical slice implemented with mock adapters.
Real plate-solver adapter (ASTAP) is ready; activate by providing FITS fixtures (see below).
Mount, camera, and stacking adapters are next.

## Project structure

```
smart_telescope/
  domain/       states, session log model
  ports/        abstract interfaces (camera, mount, solver, stacker, storage)
  workflow/     VerticalSliceRunner — linear 8-stage pipeline
  adapters/
    mock/       deterministic fakes for all ports
    astap/      real ASTAP plate-solver adapter
    replay/     FITS replay camera for integration testing
wiki/           planning knowledge base
tests/
  integration/  mock workflow + hybrid real-solver tests
  fixtures/     place FITS files here (see fixtures/README.md)
```

## Running the tests

```bash
pip install pytest
pytest tests/
```

Mock-based tests run immediately (no hardware or external tools required).
Real-solver tests skip automatically unless ASTAP and fixture FITS files are present.

## Activating real-solver tests

1. Install [ASTAP](https://www.hnsky.org/astap.htm) with the G17 star catalog.
2. Place a C8 native FITS frame of M42 at `tests/fixtures/c8_native_m42.fits`.
3. Place a blank/noise FITS (no stars) at `tests/fixtures/c8_native_blank.fits`.
4. Run `pytest tests/` — the 15 skipped tests will now execute.

## Vertical slice

The implemented slice: `IDLE → CONNECTED → MOUNT_READY → ALIGNED → SLEWED → CENTERED → PREVIEWING → STACKING → STACK_COMPLETE → SAVED`

Target: M42 (Orion Nebula), C8 native profile (0.38 arcsec/px), 10 × 30 s frames.

See [`wiki/vertical-slice-mvp.md`](wiki/vertical-slice-mvp.md) for the full spec.
