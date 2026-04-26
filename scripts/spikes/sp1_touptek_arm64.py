"""
SP-1 — ToupTek SDK on ARM64 / Pi OS
Timebox: 2 days
Question: Does libtoupcam.so load and can we call capture() on the camera?

Run on the Pi:
    python sp1_touptek_arm64.py
    python sp1_touptek_arm64.py --fits-out /tmp/frame.fits   # also writes captured frame

Outcomes:
    PASS — library loads, camera enumerates, capture() returns a valid FitsFrame
    PARTIAL — library loads but no camera connected; SDK is usable
    FAIL — library missing or wrong architecture; need INDI fallback

Download the ARM64 SDK from:
    https://www.touptek.com/download/showdownload.php?lang=en&id=37
    Extract libtoupcam.so to the same directory as this script (or /usr/lib).
"""

from __future__ import annotations

import argparse
import ctypes
import io
import platform
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PASS  = "✓ PASS"
FAIL  = "✗ FAIL"
SKIP  = "– SKIP"
INFO  = "  INFO"


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def check_platform() -> bool:
    section("1. Platform")
    machine = platform.machine()
    system  = platform.system()
    py_ver  = sys.version.split()[0]
    print(f"{INFO}  OS:      {system}")
    print(f"{INFO}  arch:    {machine}")
    print(f"{INFO}  Python:  {py_ver}")
    ok = machine in ("aarch64", "armv7l")
    if ok:
        print(f"{PASS}  ARM architecture confirmed")
    else:
        print(f"{FAIL}  Expected aarch64/armv7l, got {machine!r} — not running on Pi?")
    return ok


def find_library() -> Path | None:
    candidates = [
        SCRIPT_DIR / "libtoupcam.so",
        Path("/usr/lib/libtoupcam.so"),
        Path("/usr/local/lib/libtoupcam.so"),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def check_library() -> Path | None:
    section("2. Native library")
    lib_path = find_library()
    if lib_path is None:
        print(f"{FAIL}  libtoupcam.so not found.")
        print(f"  Download from https://www.touptek.com/download/showdownload.php?lang=en&id=37")
        print(f"  Extract libtoupcam.so (ARM64/aarch64) to: {SCRIPT_DIR}")
        return None
    print(f"{PASS}  Found: {lib_path}")

    try:
        result = subprocess.run(
            ["file", str(lib_path)], capture_output=True, text=True, timeout=5
        )
        print(f"{INFO}  {result.stdout.strip()}")
        if "aarch64" in result.stdout or "ARM aarch64" in result.stdout:
            print(f"{PASS}  Confirmed ARM64 (aarch64) binary")
        elif "ARM" in result.stdout:
            print(f"{INFO}  ARM binary (32-bit?); may work on 64-bit Pi OS in 32-bit mode")
        else:
            print(f"{FAIL}  Binary is not ARM — wrong download?")
            return None
    except FileNotFoundError:
        print(f"{INFO}  'file' command not available; skipping arch check")

    return lib_path


def check_sdk_import(lib_path: Path) -> object | None:
    section("3. SDK import")
    # Prefer toupcam.py copied here by setup_touptek_pi.sh; fall back to repo source
    for p in [SCRIPT_DIR, SCRIPT_DIR.parent.parent / "resources" / "touptek"]:
        if (p / "toupcam.py").exists() and str(p) not in sys.path:
            sys.path.insert(0, str(p))

    try:
        import toupcam  # type: ignore[import]
        print(f"{PASS}  import toupcam succeeded")
        return toupcam
    except OSError as e:
        print(f"{FAIL}  OSError loading native library: {e}")
        return None
    except Exception as e:
        print(f"{FAIL}  Unexpected import error: {e}")
        return None


def check_enumerate(toupcam: object) -> list:
    section("4. Camera enumeration")
    try:
        cameras = toupcam.Toupcam.EnumV2()  # type: ignore[attr-defined]
    except Exception as e:
        print(f"{FAIL}  EnumV2() raised: {e}")
        return []

    if not cameras:
        print(f"{SKIP}  No cameras found (connect the ToupTek camera and rerun)")
        print(f"{PASS}  SDK loaded and enumeration ran without error")
        return []

    for i, cam in enumerate(cameras):
        print(f"{PASS}  [{i}] {cam.displayname!r}  flags=0x{cam.model.flag:016x}")
        for res in cam.model.res:
            print(f"{INFO}       resolution: {res.width} × {res.height}")
    return list(cameras)


def check_capture(toupcam: object, cameras: list, fits_out: Path | None) -> bool:
    section("5. Open + capture")
    if not cameras:
        print(f"{SKIP}  No camera connected — skipping capture test")
        return True  # Not a failure of the SDK

    cam_info = cameras[0]
    hcam = None
    try:
        hcam = toupcam.Toupcam.Open(cam_info.id)  # type: ignore[attr-defined]
        if hcam is None:
            print(f"{FAIL}  Toupcam.Open() returned None")
            return False
        print(f"{PASS}  Camera opened: {cam_info.displayname!r}")

        # Switch to RAW-16 software-trigger mode (same as ToupcamCamera adapter)
        TOUPCAM_OPTION_RAW     = 0x04
        TOUPCAM_OPTION_TRIGGER = 0x08
        hcam.put_Option(TOUPCAM_OPTION_RAW, 1)
        hcam.put_Option(TOUPCAM_OPTION_TRIGGER, 1)

        width, height = hcam.get_Size()
        print(f"{INFO}  Frame size: {width} × {height}")

        # Allocate 16-bit buffer
        buf_type  = ctypes.c_uint16 * (width * height)
        frame_buf = buf_type()

        # Use threading.Event to bridge the callback
        frame_ready = threading.Event()

        def _cb(event: int, ctx: object = None) -> None:
            if event == toupcam.TOUPCAM_EVENT_IMAGE:  # type: ignore[attr-defined]
                frame_ready.set()

        hcam.StartPullModeWithCallback(_cb, None)

        # Fire software trigger
        exposure_ms = 5000
        hcam.put_ExpoTime(exposure_ms * 1000)  # microseconds
        hcam.Trigger(1)
        print(f"{INFO}  Triggered {exposure_ms} ms exposure — waiting …")

        t0 = time.monotonic()
        if not frame_ready.wait(timeout=exposure_ms / 1000 + 10):
            print(f"{FAIL}  Frame callback never fired (timeout)")
            return False
        elapsed = time.monotonic() - t0
        print(f"{INFO}  Frame callback received in {elapsed:.2f} s")

        info = toupcam.ToupcamFrameInfoV3()  # type: ignore[attr-defined]
        hcam.PullImageV4(
            ctypes.cast(frame_buf, ctypes.c_void_p),
            1,   # bStill=0 for video, 1 for still
            16,  # bits per pixel
            0,
            info,
        )
        print(f"{PASS}  PullImageV4 succeeded: {info.width} × {info.height}, flag={info.flag}")

        if fits_out:
            _write_fits(frame_buf, width, height, exposure_ms / 1000, fits_out)

        return True

    except toupcam.HRESULTException as e:  # type: ignore[attr-defined]
        print(f"{FAIL}  HRESULTException: hr=0x{e.hr & 0xffffffff:08x}")
        return False
    except Exception as e:
        print(f"{FAIL}  Unexpected error: {e}")
        return False
    finally:
        if hcam:
            hcam.Close()
            print(f"{INFO}  Camera closed")


def _write_fits(buf: object, width: int, height: int, exposure_s: float, path: Path) -> None:
    try:
        import numpy as np
        from astropy.io import fits

        pixels = np.frombuffer(buf, dtype=np.uint16).reshape(height, width).astype(np.float32)
        hdr = fits.Header()
        hdr["EXPTIME"] = exposure_s
        hdr["INSTRUME"] = "ToupTek"
        fits.PrimaryHDU(data=pixels, header=hdr).writeto(str(path), overwrite=True)
        print(f"{PASS}  FITS written: {path}  ({path.stat().st_size // 1024} KB)")
    except Exception as e:
        print(f"{FAIL}  Could not write FITS: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="SP-1: ToupTek SDK ARM64 spike")
    parser.add_argument("--fits-out", metavar="PATH", help="Write captured frame to this FITS path")
    args = parser.parse_args()

    fits_out = Path(args.fits_out) if args.fits_out else None

    print("\n╔══════════════════════════════════════════════════════╗")
    print("║  SP-1 — ToupTek SDK on ARM64 / Pi OS                ║")
    print("╚══════════════════════════════════════════════════════╝")

    platform_ok = check_platform()
    lib_path    = check_library()

    if lib_path is None:
        print("\n⛔  Cannot continue: native library not found.")
        print("    Download the ARM64 SDK from ToupTek and place libtoupcam.so here.")
        sys.exit(1)

    toupcam = check_sdk_import(lib_path)
    if toupcam is None:
        print("\n⛔  Cannot continue: SDK failed to load.")
        sys.exit(1)

    cameras = check_enumerate(toupcam)
    capture_ok = check_capture(toupcam, cameras, fits_out)

    section("Summary")
    if cameras and capture_ok:
        print(f"{PASS}  SP-1 COMPLETE — camera found and capture() returned a frame")
        print(f"  Decision: use ToupcamCamera adapter (no INDI fallback needed)")
    elif not cameras:
        print(f"{PASS}  SP-1 PARTIAL — SDK loads cleanly; connect camera to verify capture()")
        print(f"  Re-run with camera attached to complete the spike.")
    else:
        print(f"{FAIL}  SP-1 BLOCKED — see errors above")
        print(f"  Decision needed: evaluate INDI fallback (see agile-plan.md SP-1)")
        sys.exit(1)


if __name__ == "__main__":
    main()
