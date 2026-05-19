"""SP-3: astroalign feasibility on synthetic C8-FOV star fields.

Run on any machine with astroalign + numpy + scipy installed.
Generates two synthetic 2080×3096 frames with a known pixel offset, aligns them,
and verifies registration accuracy.

Usage:
    python sp3_astroalign_feasibility.py

Exit codes:
    0 — all checks passed
    1 — one or more checks failed
"""

from __future__ import annotations

import sys
import time

import numpy as np

# ── 1. Import check ───────────────────────────────────────────────────────────

print("── Section 1: import astroalign ──────────────────────────────────────")
try:
    import astroalign as aa

    print(f"  astroalign {aa.__version__} imported OK")
except ImportError as e:
    print(f"  FAIL: {e}")
    print("  Install: pip install astroalign")
    sys.exit(1)

# ── 2. Synthetic star-field generator ─────────────────────────────────────────

print("\n── Section 2: generate synthetic C8-FOV frames ───────────────────────")

HEIGHT, WIDTH = 2080, 3096
N_STARS = 80
OFFSET_X, OFFSET_Y = 47, -31  # known pixel shift applied to source frame

rng = np.random.default_rng(42)

star_x = rng.uniform(50, WIDTH - 50, N_STARS)
star_y = rng.uniform(50, HEIGHT - 50, N_STARS)
star_brightness = rng.uniform(1000, 60000, N_STARS)


def _make_frame(
    xs: np.ndarray,
    ys: np.ndarray,
    brightness: np.ndarray,
    sigma: float = 2.5,
) -> np.ndarray:
    """Render stars as Gaussian PSFs on a sky-background array."""
    frame = rng.normal(800, 20, (HEIGHT, WIDTH)).astype(np.float32)
    yy, xx = np.mgrid[:HEIGHT, :WIDTH]
    for sx, sy, sb in zip(xs, ys, brightness, strict=False):
        r2 = (xx - sx) ** 2 + (yy - sy) ** 2
        mask = r2 < (5 * sigma) ** 2
        frame[mask] += sb * np.exp(-r2[mask] / (2 * sigma**2))
    return np.clip(frame, 0, 65535).astype(np.float32)


print(f"  Rendering reference frame ({HEIGHT}×{WIDTH}, {N_STARS} stars)...")
t0 = time.perf_counter()
ref_frame = _make_frame(star_x, star_y, star_brightness)
print(f"    done in {time.perf_counter()-t0:.1f}s")

print(f"  Rendering source frame (shifted by dx={OFFSET_X}, dy={OFFSET_Y})...")
t0 = time.perf_counter()
src_frame = _make_frame(star_x + OFFSET_X, star_y + OFFSET_Y, star_brightness)
print(f"    done in {time.perf_counter()-t0:.1f}s")

# ── 3. Alignment ──────────────────────────────────────────────────────────────

print("\n── Section 3: astroalign.register() ─────────────────────────────────")

t0 = time.perf_counter()
try:
    registered, footprint = aa.register(src_frame, ref_frame)
    elapsed = time.perf_counter() - t0
    print(f"  register() completed in {elapsed:.2f}s")
    REGISTER_OK = True
except Exception as exc:
    print(f"  FAIL: {exc}")
    REGISTER_OK = False
    elapsed = time.perf_counter() - t0

# ── 4. Accuracy check ─────────────────────────────────────────────────────────

print("\n── Section 4: registration accuracy ─────────────────────────────────")
ACCURACY_OK = False
if REGISTER_OK:
    try:
        transform, _ = aa.find_transform(src_frame, ref_frame)
        tx, ty = transform.translation
        print(f"  Detected translation: dx={tx:.2f}, dy={ty:.2f}")
        print(f"  Expected:             dx={-OFFSET_X:.2f}, dy={-OFFSET_Y:.2f}")
        err = ((tx - (-OFFSET_X)) ** 2 + (ty - (-OFFSET_Y)) ** 2) ** 0.5
        print(f"  Residual error: {err:.2f} px")
        ACCURACY_OK = err < 2.0
        if ACCURACY_OK:
            print("  PASS: residual < 2 px")
        else:
            print("  WARN: residual >= 2 px — check star density or frame quality")
    except Exception as exc:
        print(f"  FAIL find_transform: {exc}")
else:
    print("  Skipped (register failed)")

# ── 5. Performance verdict ────────────────────────────────────────────────────

print("\n── Section 5: performance verdict ───────────────────────────────────")
PERF_OK = elapsed < 30.0
print(f"  register() time: {elapsed:.2f}s  (threshold 30s)")
if PERF_OK:
    print("  PASS: within budget for 30-fps cadence")
else:
    print("  WARN: exceeds 30s — may need downsampling on Pi 5")

# ── Summary ───────────────────────────────────────────────────────────────────

print("\n── Summary ───────────────────────────────────────────────────────────")
checks = {
    "import": True,
    "register": REGISTER_OK,
    "accuracy": ACCURACY_OK,
    "performance": PERF_OK,
}
for name, ok in checks.items():
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")

if all(checks.values()):
    print("\nastroalign is viable for Sprint 6 frame registration.")
    sys.exit(0)
else:
    print("\nOne or more checks failed — review output above.")
    sys.exit(1)
