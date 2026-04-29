"""GoTo + plate-solve + center workflow."""
from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass

from ..ports.camera import CameraPort
from ..ports.mount import MountPort
from ..ports.solver import SolverPort


def _sep_arcmin(ra1_h: float, dec1_deg: float, ra2_h: float, dec2_deg: float) -> float:
    """Great-circle separation in arcminutes."""
    ra1 = math.radians(ra1_h * 15.0)
    ra2 = math.radians(ra2_h * 15.0)
    d1  = math.radians(dec1_deg)
    d2  = math.radians(dec2_deg)
    cos_sep = (math.sin(d1) * math.sin(d2)
               + math.cos(d1) * math.cos(d2) * math.cos(ra1 - ra2))
    return math.degrees(math.acos(max(-1.0, min(1.0, cos_sep)))) * 60.0


@dataclass
class CenterResult:
    success:       bool
    final_ra:      float
    final_dec:     float
    iterations:    int
    offset_arcmin: float
    error:         str | None = None


async def goto_and_center(
    mount:  MountPort,
    camera: CameraPort,
    solver: SolverPort,
    target_ra:  float,
    target_dec: float,
    *,
    pixel_scale:       float = 0.38,
    exposure:          float = 5.0,
    tolerance_arcmin:  float = 2.0,
    max_iterations:    int   = 3,
    slew_timeout_s:    float = 120.0,
) -> CenterResult:
    last_ra,  last_dec    = target_ra, target_dec
    last_offset: float    = 999.0

    for iteration in range(1, max_iterations + 1):
        # ── 1. GoTo ───────────────────────────────────────────────────────────
        ok = await asyncio.to_thread(mount.goto, target_ra, target_dec)
        if not ok:
            return CenterResult(
                success=False, final_ra=last_ra, final_dec=last_dec,
                iterations=iteration, offset_arcmin=last_offset,
                error="GoTo rejected by mount",
            )

        # ── 2. Wait for slew to finish ────────────────────────────────────────
        loop     = asyncio.get_event_loop()
        deadline = loop.time() + slew_timeout_s
        while loop.time() < deadline:
            if not await asyncio.to_thread(mount.is_slewing):
                break
            await asyncio.sleep(2.0)
        else:
            return CenterResult(
                success=False, final_ra=last_ra, final_dec=last_dec,
                iterations=iteration, offset_arcmin=last_offset,
                error="Slew timeout",
            )

        # ── 3. Plate solve ────────────────────────────────────────────────────
        frame  = await asyncio.to_thread(camera.capture, exposure)
        result = await asyncio.to_thread(solver.solve, frame, pixel_scale)
        if not result.success:
            return CenterResult(
                success=False, final_ra=last_ra, final_dec=last_dec,
                iterations=iteration, offset_arcmin=last_offset,
                error=f"Plate solve failed: {result.error}",
            )

        last_ra, last_dec = result.ra, result.dec
        last_offset = round(_sep_arcmin(result.ra, result.dec, target_ra, target_dec), 2)

        # ── 4. Check convergence ──────────────────────────────────────────────
        if last_offset <= tolerance_arcmin:
            return CenterResult(
                success=True, final_ra=last_ra, final_dec=last_dec,
                iterations=iteration, offset_arcmin=last_offset,
            )

        # ── 5. Sync and refine ────────────────────────────────────────────────
        await asyncio.to_thread(mount.sync, result.ra, result.dec)

    return CenterResult(
        success=False, final_ra=last_ra, final_dec=last_dec,
        iterations=max_iterations, offset_arcmin=last_offset,
        error=f"Max iterations ({max_iterations}) reached, offset {last_offset:.1f}′",
    )
