# Test fixtures

Place prerecorded C8 FITS frames here for the real-solver replay tests.

## Required files

| File | Description |
|---|---|
| `c8_native_m42.fits` | Single frame of M42 taken with C8 native (2032mm, ~0.38"/px). Used for happy-path real-solver test. |
| `c8_native_blank.fits` | All-zero or noise-only frame — no stars. Used to test solve failure on unsolvable image. |

## How to acquire c8_native_m42.fits

Take a single 5–30s sub-frame with your C8 at native focal length pointing at M42.
Save as FITS. The solve test expects the result RA to be within ±1° of M42
(RA ≈ 83.82°, Dec ≈ −5.39°).

## ASTAP installation (Windows)

Download from https://www.hnsky.org/astap.htm
Install to the default path: `C:\Program Files\astap\`
Download at least one star catalog (G17 recommended for C8 pixel scales).

Tests skip automatically if ASTAP is not found or fixture files are missing.
