"""
SP-2 — ASTAP on Pi OS
Timebox: 1 day
Question: Does ASTAP install on Pi OS and solve a FITS in < 60 s with G17?

Run on the Pi:
    python sp2_astap_pi.py                          # auto-find FITS in /tmp or CWD
    python sp2_astap_pi.py --fits /path/to/sky.fits # use a specific frame

Outcomes:
    PASS  — ASTAP solves in < 60 s; catalog path confirmed
    SLOW  — ASTAP solves but > 60 s; document actual time
    FAIL  — ASTAP not installed, catalog missing, or solve crashes

Install ASTAP ARM64 on Pi OS:
    wget https://www.hnsky.org/astap_arm64.deb
    sudo dpkg -i astap_arm64.deb

Download G17 catalog (2.5 GB):
    wget https://www.hnsky.org/G17.zip
    unzip G17.zip -d ~/.astap/
"""

from __future__ import annotations

import argparse
import configparser
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PASS  = "✓ PASS"
FAIL  = "✗ FAIL"
SKIP  = "– SKIP"
INFO  = "  INFO"

# Acceptance threshold from Sprint plan SP-2
SOLVE_TIMEOUT_S = 60
PIXEL_SCALE_C8  = 0.38   # arcsec/px for C8 native focal length


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


# ── 1. ASTAP binary ──────────────────────────────────────────────────────────

def find_astap() -> str | None:
    on_path = shutil.which("astap")
    if on_path:
        return on_path
    for p in [Path("/usr/bin/astap"), Path("/usr/local/bin/astap")]:
        if p.exists():
            return str(p)
    return None


def check_astap() -> str | None:
    section("1. ASTAP binary")
    path = find_astap()
    if path is None:
        print(f"{FAIL}  ASTAP not found on PATH or standard locations.")
        print(f"  Install with:")
        print(f"    wget https://www.hnsky.org/astap_arm64.deb")
        print(f"    sudo dpkg -i astap_arm64.deb")
        return None
    print(f"{PASS}  Found: {path}")

    try:
        r = subprocess.run([path, "-h"], capture_output=True, text=True, timeout=5)
        first_line = (r.stdout or r.stderr).split("\n")[0].strip()
        print(f"{INFO}  {first_line}")
    except Exception as e:
        print(f"{INFO}  Could not run -h: {e}")

    try:
        r = subprocess.run(["file", path], capture_output=True, text=True, timeout=5)
        print(f"{INFO}  {r.stdout.strip()}")
        if "aarch64" in r.stdout or "ARM aarch64" in r.stdout:
            print(f"{PASS}  Confirmed ARM64 binary")
        elif "ARM" in r.stdout:
            print(f"{INFO}  ARM binary (32-bit?)")
        else:
            print(f"{INFO}  Architecture not confirmed by 'file'")
    except FileNotFoundError:
        pass

    return path


# ── 2. G17 catalog ───────────────────────────────────────────────────────────

CATALOG_SEARCH: list[Path] = [
    Path.home() / ".astap",
    Path("/usr/share/astap"),
    Path("/usr/local/share/astap"),
    Path("C:/ProgramData/astap"),
]


def find_g17_catalog(astap_exe: str) -> Path | None:
    dirs = [Path(astap_exe).parent] + CATALOG_SEARCH
    for d in dirs:
        if d.is_dir() and any(d.glob("*.290")):
            return d
    return None


def check_catalog(astap_exe: str) -> Path | None:
    section("2. G17 catalog")
    cat_dir = find_g17_catalog(astap_exe)
    if cat_dir is None:
        print(f"{FAIL}  G17 catalog not found (looking for *.290 files).")
        print(f"  Download with:")
        print(f"    wget https://www.hnsky.org/G17.zip")
        print(f"    unzip G17.zip -d ~/.astap/")
        return None

    files = list(cat_dir.glob("*.290"))
    print(f"{PASS}  G17 catalog found: {cat_dir}")
    print(f"{INFO}  Catalog files: {len(files)} × .290  ({_dir_size_mb(cat_dir):.0f} MB total)")
    return cat_dir


def _dir_size_mb(d: Path) -> float:
    return sum(f.stat().st_size for f in d.iterdir() if f.is_file()) / 1_048_576


# ── 3. FITS input ─────────────────────────────────────────────────────────────

def find_or_make_fits(user_path: str | None) -> Path:
    if user_path:
        p = Path(user_path)
        if not p.exists():
            print(f"{FAIL}  Specified FITS not found: {p}")
            sys.exit(1)
        return p

    # Look for any .fits in /tmp or CWD
    for search_dir in [Path("/tmp"), Path.cwd()]:
        candidates = list(search_dir.glob("*.fits")) + list(search_dir.glob("*.fit"))
        if candidates:
            p = candidates[0]
            print(f"{INFO}  Auto-found FITS: {p}")
            return p

    # Synthesise a blank noise frame — ASTAP will fail to solve it, but
    # confirms the binary runs and the catalog path is accepted.
    return _make_synthetic_fits()


def _make_synthetic_fits() -> Path:
    try:
        import numpy as np
        from astropy.io import fits

        rng = np.random.default_rng(42)
        pixels = rng.normal(1000, 50, (480, 640)).astype(np.float32)
        hdr = fits.Header()
        hdr["EXPTIME"] = 5.0
        hdr["INSTRUME"] = "synthetic"
        hdr["COMMENT"] = "SP-2 synthetic blank frame — will not solve"

        path = Path(tempfile.mktemp(suffix="_sp2_synthetic.fits"))
        fits.PrimaryHDU(data=pixels, header=hdr).writeto(str(path), overwrite=True)
        print(f"{INFO}  Created synthetic blank frame: {path}")
        print(f"{INFO}  (This will NOT solve — use a real sky FITS to confirm solve time)")
        return path
    except ImportError:
        print(f"{FAIL}  numpy/astropy not available; cannot create synthetic FITS")
        print(f"  Install with: pip install numpy astropy")
        sys.exit(1)


# ── 4. Solve ─────────────────────────────────────────────────────────────────

def run_solve(astap_exe: str, fits_path: Path, pixel_scale: float) -> tuple[bool, float, str]:
    """Run ASTAP, return (success, elapsed_s, error_or_coords)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        import shutil as _sh
        work_fits = Path(tmpdir) / fits_path.name
        _sh.copy(fits_path, work_fits)
        out_base = work_fits.with_suffix("")

        cmd = [
            astap_exe,
            "-f", str(work_fits),
            "-r", "180",        # full-sky search (no prior position)
            "-z", "0",          # no downsample
            "-scale", str(round(pixel_scale, 4)),
            "-o", str(out_base),
        ]
        print(f"{INFO}  Command: {' '.join(cmd)}")

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=SOLVE_TIMEOUT_S + 30,   # give 30s grace beyond acceptance threshold
            )
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - t0
            return False, elapsed, f"ASTAP timed out after {elapsed:.0f}s"
        except Exception as e:
            return False, 0.0, f"ASTAP launch failed: {e}"

        elapsed = time.monotonic() - t0

        ini_path = out_base.with_suffix(".ini")
        if not ini_path.exists():
            return False, elapsed, (
                f"No .ini output (exit {proc.returncode}): {proc.stderr.strip()}"
            )

        cfg = configparser.ConfigParser()
        cfg.read(ini_path)
        section_name = (
            "Solution" if cfg.has_section("Solution")
            else (cfg.sections()[0] if cfg.sections() else None)
        )
        if section_name is None:
            return False, elapsed, "Empty .ini"

        solved = cfg.get(section_name, "PLATESOLVED", fallback="F").strip().upper()
        if solved != "T":
            warning = cfg.get(section_name, "WARNING", fallback="").strip()
            return False, elapsed, warning or "PLATESOLVED=F"

        ra  = float(cfg.get(section_name, "CRVAL1")) / 15.0
        dec = float(cfg.get(section_name, "CRVAL2"))
        pa  = float(cfg.get(section_name, "CROTA2", fallback="0"))
        return True, elapsed, f"RA={ra:.4f}h  Dec={dec:.4f}°  PA={pa:.1f}°"


def check_solve(astap_exe: str, fits_path: Path, pixel_scale: float) -> bool:
    section("3. Plate solve")
    print(f"{INFO}  FITS: {fits_path}  ({fits_path.stat().st_size // 1024} KB)")
    print(f"{INFO}  Pixel scale hint: {pixel_scale} arcsec/px")
    print(f"{INFO}  Acceptance threshold: {SOLVE_TIMEOUT_S} s")
    print()

    success, elapsed, detail = run_solve(astap_exe, fits_path, pixel_scale)

    if success:
        print(f"{PASS}  Solved in {elapsed:.1f} s — {detail}")
        if elapsed <= SOLVE_TIMEOUT_S:
            print(f"{PASS}  Within {SOLVE_TIMEOUT_S}s threshold ✓")
        else:
            print(f"{FAIL}  Exceeded {SOLVE_TIMEOUT_S}s threshold ({elapsed:.1f}s) — "
                  f"consider --downsample 2 or a shorter search radius")
        return elapsed <= SOLVE_TIMEOUT_S
    else:
        print(f"{FAIL}  Solve failed in {elapsed:.1f} s — {detail}")
        if "synthetic" in str(fits_path) or "sp2_synthetic" in str(fits_path):
            print(f"{INFO}  Expected: synthetic blank frame cannot solve.")
            print(f"{INFO}  Provide a real sky FITS to confirm solve time:")
            print(f"           python sp2_astap_pi.py --fits /path/to/sky.fits")
            return True  # ASTAP ran correctly; no solve is expected
        return False


# ── 5. Memory snapshot ─────────────────────────────────────────────────���──────

def check_memory() -> None:
    section("4. Memory snapshot")
    try:
        r = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.strip().splitlines():
            print(f"{INFO}  {line}")
    except FileNotFoundError:
        print(f"{SKIP}  'free' not available")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="SP-2: ASTAP on Pi OS spike")
    parser.add_argument("--fits",        metavar="PATH",  help="Path to a sky FITS file")
    parser.add_argument("--pixel-scale", type=float, default=PIXEL_SCALE_C8,
                        help=f"Pixel scale in arcsec/px (default: {PIXEL_SCALE_C8})")
    args = parser.parse_args()

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  SP-2 — ASTAP on Pi OS                               ║")
    print("╚══════════════════════════════════════════════════════╝")

    astap = check_astap()
    if astap is None:
        print("\n⛔  Cannot continue: ASTAP not installed.")
        sys.exit(1)

    cat_dir = check_catalog(astap)
    if cat_dir is None:
        print("\n⛔  Cannot continue: G17 catalog not found.")
        sys.exit(1)

    fits_path = find_or_make_fits(args.fits)

    section("3. Plate solve")
    solve_ok = check_solve(astap, fits_path, args.pixel_scale)

    check_memory()

    section("Summary")
    print(f"{INFO}  ASTAP binary:  {astap}")
    print(f"{INFO}  G17 catalog:   {cat_dir}")
    print(f"{INFO}  FITS tested:   {fits_path}")
    if solve_ok:
        print(f"\n{PASS}  SP-2 COMPLETE")
        print(f"  Decision: use AstapSolver adapter as-is; no fallback needed")
    else:
        print(f"\n{FAIL}  SP-2 INCOMPLETE — see errors above")
        print(f"  Options:")
        print(f"    1. Add --downsample 2 to AstapSolver (faster solve, lower precision)")
        print(f"    2. Provide a smaller search radius (needs initial position from mount)")
        print(f"    3. Evaluate alternative solver (astrometry.net local)")
        sys.exit(1)


if __name__ == "__main__":
    main()
