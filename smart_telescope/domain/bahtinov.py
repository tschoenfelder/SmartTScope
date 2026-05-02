"""Bahtinov mask focus analyzer — pure numpy, no hardware calls.

Two-layer design (see wiki/bahtinov-analyzer.md):
  BahtinovAnalyzer          image analysis only; never moves hardware
  CrossingAnalysisResult    output data structure

Algorithm summary
-----------------
1. Find brightest real star using Gaussian-blurred argmax + flux centroid.
2. Crop a square ROI around it.
3. Subtract background, blur, mask saturated core, threshold.
4. Weighted Hough transform to find 3 dominant spike angles.
5. Convert (theta, rho) peaks to normal-form lines ax + by + c = 0.
6. Compute pairwise intersections P12, P13, P23.
7. Measure crossing quality (RMS of distances from mean intersection).
8. Classify middle vs. outer spikes by angle order.
9. focus_error_px = signed distance from outer-spike intersection to middle line.
"""

from __future__ import annotations

import dataclasses
import math
from typing import NamedTuple

import numpy as np


class SpikeLine(NamedTuple):
    """One detected Bahtinov diffraction spike in normal form ax + by + c = 0."""

    a: float
    b: float
    c: float            # sqrt(a² + b²) == 1
    angle_deg: float    # orientation of the line direction (0–180°)
    confidence: float   # accumulated Hough weight


@dataclasses.dataclass(frozen=True)
class CrossingAnalysisResult:
    """Full result of a Bahtinov analysis pass."""

    object_center_px:           tuple[float, float]
    lines:                      list[SpikeLine]            # exactly 3
    common_crossing_point_px:   tuple[float, float]
    pairwise_intersections_px:  list[tuple[float, float]]  # P12, P13, P23
    crossing_error_rms_px:      float
    crossing_error_max_px:      float
    focus_error_px:             float   # primary Bahtinov metric; 0 = in focus
    detection_confidence:       float   # 0–1, min confidence over 3 lines

    def to_dict(self) -> dict[str, object]:
        return {
            "object_center_px": list(self.object_center_px),
            "lines": [
                {
                    "a": round(l.a, 6),
                    "b": round(l.b, 6),
                    "c": round(l.c, 4),
                    "angle_deg": round(l.angle_deg, 2),
                    "confidence": round(l.confidence, 1),
                }
                for l in self.lines
            ],
            "common_crossing_point_px": [
                round(self.common_crossing_point_px[0], 2),
                round(self.common_crossing_point_px[1], 2),
            ],
            "pairwise_intersections_px": [
                [round(p[0], 2), round(p[1], 2)]
                for p in self.pairwise_intersections_px
            ],
            "crossing_error_rms_px":  round(self.crossing_error_rms_px, 2),
            "crossing_error_max_px":  round(self.crossing_error_max_px, 2),
            "focus_error_px":         round(self.focus_error_px, 2),
            "detection_confidence":   round(self.detection_confidence, 3),
        }


class BahtinovAnalyzer:
    """Analyze a star image for Bahtinov diffraction spikes.

    Parameters
    ----------
    roi_size : int
        Side length of the square ROI cropped around the brightest star (px).
    core_radius : int
        Radius of the saturated star core masked out before line detection (px).
    blur_sigma : float
        Gaussian sigma applied to the ROI before thresholding (px).
    n_angles : int
        Number of Hough angle bins sampled in [0, π).
    threshold_percentile : float
        Percentile of positive pixel values used as the spike-detection threshold.
    """

    def __init__(
        self,
        roi_size: int = 400,
        core_radius: int = 15,
        blur_sigma: float = 1.5,
        n_angles: int = 180,
        threshold_percentile: float = 90.0,
    ) -> None:
        self._roi_size = roi_size
        self._core_radius = core_radius
        self._blur_sigma = blur_sigma
        self._n_angles = n_angles
        self._threshold_percentile = threshold_percentile

    # ── public ───────────────────────────────────────────────────────────────

    def analyze(self, pixels: np.ndarray) -> CrossingAnalysisResult:
        """Run full Bahtinov analysis on a 2-D float pixel array.

        Raises ValueError if fewer than 3 spike lines are detected.
        """
        img = pixels.astype(np.float64)

        # 1 — find the brightest real star
        cx, cy = self._find_brightest_object(img)

        # 2 — crop ROI
        h = self._roi_size // 2
        r0y = max(0, int(cy) - h)
        r1y = min(img.shape[0], int(cy) + h)
        r0x = max(0, int(cx) - h)
        r1x = min(img.shape[1], int(cx) + h)
        roi = img[r0y:r1y, r0x:r1x]
        rcx = cx - r0x
        rcy = cy - r0y

        # 3 — preprocess
        processed = self._preprocess(roi, rcx, rcy)

        # 4-5 — detect 3 dominant lines
        lines = self._detect_lines(processed, rcx, rcy, offset=(r0x, r0y))
        if len(lines) < 3:
            raise ValueError(
                f"Detected {len(lines)} spike(s); need 3. "
                "Check mask placement and exposure."
            )

        # 6 — pairwise intersections
        P12 = _intersect(lines[0], lines[1])
        P13 = _intersect(lines[0], lines[2])
        P23 = _intersect(lines[1], lines[2])
        intersections: list[tuple[float, float]] = [P12, P13, P23]

        # 7 — crossing quality
        pcx = (P12[0] + P13[0] + P23[0]) / 3.0
        pcy = (P12[1] + P13[1] + P23[1]) / 3.0
        dists = [math.hypot(p[0] - pcx, p[1] - pcy) for p in intersections]
        rms = math.sqrt(sum(d * d for d in dists) / 3.0)
        mx  = max(dists)

        # 8-9 — classify spikes and compute focus error
        mid_i, out1_i, out2_i = _classify_bahtinov(lines)
        P_outer = _intersect(lines[out1_i], lines[out2_i])
        lm = lines[mid_i]
        focus_err = lm.a * P_outer[0] + lm.b * P_outer[1] + lm.c

        max_conf = max(l.confidence for l in lines) or 1.0
        confidence = min(1.0, min(l.confidence for l in lines) / max_conf)

        return CrossingAnalysisResult(
            object_center_px=(cx, cy),
            lines=list(lines),
            common_crossing_point_px=(pcx, pcy),
            pairwise_intersections_px=intersections,
            crossing_error_rms_px=rms,
            crossing_error_max_px=mx,
            focus_error_px=focus_err,
            detection_confidence=confidence,
        )

    # ── private ──────────────────────────────────────────────────────────────

    def _find_brightest_object(self, img: np.ndarray) -> tuple[float, float]:
        bg = float(np.median(img))
        corrected = np.clip(img - bg, 0.0, None)
        # Gaussian blur (σ=3) before argmax suppresses isolated hot pixels
        blurred = _gaussian_blur(corrected, sigma=3.0)
        peak_y, peak_x = np.unravel_index(int(np.argmax(blurred)), blurred.shape)
        # Flux-weighted centroid in a 50-px window around the peak
        hw = 50
        y0 = max(0, peak_y - hw); y1 = min(img.shape[0], peak_y + hw)
        x0 = max(0, peak_x - hw); x1 = min(img.shape[1], peak_x + hw)
        window = corrected[y0:y1, x0:x1]
        total = float(window.sum())
        if total <= 0.0:
            return float(peak_x), float(peak_y)
        rows, cols = np.indices(window.shape, dtype=np.float64)
        return (
            float((cols * window).sum() / total) + x0,
            float((rows * window).sum() / total) + y0,
        )

    def _preprocess(self, roi: np.ndarray, cx: float, cy: float) -> np.ndarray:
        bg = float(np.median(roi))
        work = np.clip(roi.astype(np.float64) - bg, 0.0, None)
        work = _gaussian_blur(work, self._blur_sigma).astype(np.float64)
        rr, cc = np.indices(roi.shape, dtype=np.float64)
        dist = np.sqrt((cc - cx) ** 2 + (rr - cy) ** 2)
        work[dist < self._core_radius] = 0.0
        return work.astype(np.float32)

    def _detect_lines(
        self,
        processed: np.ndarray,
        cx: float,
        cy: float,
        offset: tuple[int, int] = (0, 0),
    ) -> list[SpikeLine]:
        """Weighted Hough transform → 3 dominant spike lines in full-image coords."""
        pos = processed[processed > 0]
        if pos.size == 0:
            return []
        thresh = float(np.percentile(pos, self._threshold_percentile))
        ys, xs = np.where(processed > thresh)
        if len(xs) < 10:
            return []
        weights = processed[ys, xs].astype(np.float64)

        xs_c = xs.astype(np.float64) - cx
        ys_c = ys.astype(np.float64) - cy

        n = self._n_angles
        thetas = np.linspace(0.0, math.pi, n, endpoint=False)
        cos_t  = np.cos(thetas)
        sin_t  = np.sin(thetas)

        max_rho = int(math.hypot(processed.shape[1], processed.shape[0])) + 1
        n_rho   = 2 * max_rho + 1
        acc = np.zeros((n, n_rho), dtype=np.float64)

        chunk = 30
        for i0 in range(0, n, chunk):
            i1 = min(n, i0 + chunk)
            rhos = (
                np.outer(cos_t[i0:i1], xs_c)
                + np.outer(sin_t[i0:i1], ys_c)
            )
            rb = np.clip(np.round(rhos + max_rho).astype(int), 0, n_rho - 1)
            for j, i in enumerate(range(i0, i1)):
                np.add.at(acc[i], rb[j], weights)

        # Extract 3 peaks with ≥ 15° angular separation
        min_sep = max(1, int(round(15.0 / 180.0 * n)))
        lines: list[SpikeLine] = []
        acc_copy = acc.copy()
        ox, oy = offset

        for _ in range(3):
            ti, ri = np.unravel_index(int(np.argmax(acc_copy)), acc_copy.shape)
            conf = float(acc_copy[ti, ri])
            if conf <= 0.0:
                break
            rho_val = float(ri) - max_rho
            theta   = float(thetas[ti])
            a = math.cos(theta)
            b = math.sin(theta)
            # Normal-form line in full-image coordinates
            c = -(rho_val + a * (cx + ox) + b * (cy + oy))
            nrm = math.hypot(a, b)
            if nrm > 0.0:
                a, b, c = a / nrm, b / nrm, c / nrm
            lines.append(SpikeLine(
                a=a, b=b, c=c,
                angle_deg=math.degrees(theta) % 180.0,
                confidence=conf,
            ))
            # Suppress neighbouring angles (with wraparound)
            lo = ti - min_sep
            hi = ti + min_sep + 1
            acc_copy[max(0, lo):min(n, hi), :] = 0.0
            if lo < 0:
                acc_copy[n + lo:, :] = 0.0
            if hi > n:
                acc_copy[:hi - n, :] = 0.0

        return lines


# ── module helpers ────────────────────────────────────────────────────────────

def _gaussian_blur(arr: np.ndarray, sigma: float) -> np.ndarray:
    """Separable Gaussian blur (no scipy required)."""
    radius = max(1, int(3.0 * sigma + 0.5))
    x = np.arange(-radius, radius + 1, dtype=np.float64)
    kernel = np.exp(-0.5 * (x / sigma) ** 2)
    kernel /= kernel.sum()
    a = arr.astype(np.float64)

    padded = np.pad(a, [(0, 0), (radius, radius)], mode="edge")
    result = np.zeros_like(a)
    for k, w in enumerate(kernel):
        result += w * padded[:, k : k + a.shape[1]]

    padded = np.pad(result, [(radius, radius), (0, 0)], mode="edge")
    result2 = np.zeros_like(a)
    for k, w in enumerate(kernel):
        result2 += w * padded[k : k + a.shape[0], :]

    return result2.astype(np.float32)


def _intersect(l1: SpikeLine, l2: SpikeLine) -> tuple[float, float]:
    """Intersection of two normal-form lines. Returns (0, 0) for near-parallel.

    For lines  a1·x + b1·y + c1 = 0  and  a2·x + b2·y + c2 = 0
    Cramer's rule gives:
        D = a1·b2 − a2·b1
        x = (b1·c2 − b2·c1) / D
        y = (a2·c1 − a1·c2) / D
    """
    d = l1.a * l2.b - l2.a * l1.b
    if abs(d) < 1e-10:
        return (0.0, 0.0)
    x = (l1.b * l2.c - l2.b * l1.c) / d
    y = (l2.a * l1.c - l1.a * l2.c) / d
    return (x, y)


def _classify_bahtinov(lines: list[SpikeLine]) -> tuple[int, int, int]:
    """Return (middle_idx, outer1_idx, outer2_idx) sorted by line angle."""
    order = sorted(range(len(lines)), key=lambda i: lines[i].angle_deg)
    return order[1], order[0], order[2]
