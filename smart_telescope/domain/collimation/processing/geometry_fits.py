"""Circle / ellipse fitting primitives — Collimation Phase 3, Task 3.4.

Provides reusable geometry functions used by rough donut collimation (Phase 7)
and, later, optional OCAL-like daylight alignment (Phase 15).

All functions use NumPy only.  No scipy dependency.

Public API
----------
fit_circle(points)            → CircleEllipseFit
fit_ellipse(points)           → CircleEllipseFit
detect_clipping(fit, w, h)    → bool
compare_circle_centers(a, b)  → float   (Euclidean distance)
extract_edge_points(mask)     → np.ndarray  shape (N, 2)
"""
from __future__ import annotations

import numpy as np

from ....domain.collimation.models import CircleEllipseFit


# ── Circle fitting ─────────────────────────────────────────────────────────────

def fit_circle(points: np.ndarray) -> CircleEllipseFit:
    """Algebraic circle fit (Kasa / linear least-squares).

    Solves the over-determined system:
        2·cx·x + 2·cy·y + (r² − cx² − cy²) = x² + y²
    via NumPy lstsq.

    Args:
        points: (N, 2) float array of (x, y) edge coordinates.
                Needs at least 3 non-collinear points.

    Returns:
        CircleEllipseFit with radius_x == radius_y.
        confidence is 1 − (rms_residual / radius); 0 when degenerate.
    """
    if len(points) < 3:
        return _degenerate_circle()

    x = points[:, 0].astype(np.float64)
    y = points[:, 1].astype(np.float64)
    A = np.column_stack([2.0 * x, 2.0 * y, np.ones(len(x))])
    b = x ** 2 + y ** 2

    try:
        result, _, rank, _ = np.linalg.lstsq(A, b, rcond=None)
    except np.linalg.LinAlgError:
        return _degenerate_circle()

    if rank < 3:
        return _degenerate_circle()

    cx, cy = float(result[0]), float(result[1])
    r_sq = float(result[2]) + cx ** 2 + cy ** 2
    if r_sq <= 0.0:
        return _degenerate_circle()
    r = float(np.sqrt(r_sq))

    dist = np.sqrt((x - cx) ** 2 + (y - cy) ** 2)
    rms = float(np.sqrt(np.mean((dist - r) ** 2)))
    confidence = max(0.0, min(1.0, 1.0 - rms / max(r, 1.0)))

    return CircleEllipseFit(
        center_x=cx,
        center_y=cy,
        radius_x=r,
        radius_y=r,
        angle_deg=0.0,
        confidence=confidence,
    )


# ── Ellipse fitting ────────────────────────────────────────────────────────────

def fit_ellipse(points: np.ndarray) -> CircleEllipseFit:
    """Direct algebraic ellipse fit (Bookstein constraint).

    Fits the general conic  a·x² + b·x·y + c·y² + d·x + e·y + f = 0
    subject to  a + c = 1  (Bookstein constraint).

    At least 5 non-degenerate points are required.  Returns a low-confidence
    result when the fit is degenerate or yields a hyperbola / parabola.

    Args:
        points: (N, 2) float array of (x, y) edge coordinates.

    Returns:
        CircleEllipseFit with semi-axis and orientation.
        Falls back to fit_circle when N < 5 or the conic is non-elliptic.
    """
    if len(points) < 5:
        return fit_circle(points)

    x = points[:, 0].astype(np.float64)
    y = points[:, 1].astype(np.float64)

    # Design matrix for Bookstein-constrained conic:
    # F = a·x² + b·x·y + c·y² + d·x + e·y + f = 0, a+c=1
    # Substituting c = 1 - a:
    #   a·(x²-y²) + b·x·y + d·x + e·y + f = -y²
    A = np.column_stack([x ** 2 - y ** 2, x * y, x, y, np.ones(len(x))])
    b_vec = -y ** 2

    try:
        result, _, rank, _ = np.linalg.lstsq(A, b_vec, rcond=None)
    except np.linalg.LinAlgError:
        return fit_circle(points)

    if rank < 5:
        return fit_circle(points)

    a_coef = float(result[0])
    b_coef = float(result[1])
    c_coef = 1.0 - a_coef          # Bookstein: a + c = 1
    d_coef = float(result[2])
    e_coef = float(result[3])
    f_coef = float(result[4])

    # Check that the conic is a proper ellipse: discriminant B²−4AC < 0
    discriminant = b_coef ** 2 - 4.0 * a_coef * c_coef
    if discriminant >= 0.0:
        return fit_circle(points)

    # Convert general conic to standard ellipse parameters
    fit = _conic_to_ellipse(a_coef, b_coef, c_coef, d_coef, e_coef, f_coef)
    if fit is None:
        return fit_circle(points)

    # Residuals: distance of each point from the fitted ellipse boundary
    # Use algebraic residual as a proxy (fast, not geometric distance)
    alg_residuals = (
        a_coef * x ** 2 + b_coef * x * y + c_coef * y ** 2
        + d_coef * x + e_coef * y + f_coef
    )
    rms_alg = float(np.sqrt(np.mean(alg_residuals ** 2)))
    scale = max(fit.radius_x, fit.radius_y, 1.0)
    confidence = max(0.0, min(1.0, 1.0 - rms_alg / scale))

    return CircleEllipseFit(
        center_x=fit.center_x,
        center_y=fit.center_y,
        radius_x=fit.radius_x,
        radius_y=fit.radius_y,
        angle_deg=fit.angle_deg,
        confidence=confidence,
    )


def _conic_to_ellipse(
    a: float, b: float, c: float,
    d: float, e: float, f: float,
) -> CircleEllipseFit | None:
    """Convert general conic coefficients to ellipse center and semi-axes.

    Returns None if the conic cannot be expressed as a valid ellipse.
    """
    # Center: solve 2a·cx + b·cy + d = 0 and b·cx + 2c·cy + e = 0
    M = np.array([[2.0 * a, b], [b, 2.0 * c]])
    rhs = np.array([-d, -e])
    try:
        center = np.linalg.solve(M, rhs)
    except np.linalg.LinAlgError:
        return None

    cx, cy = float(center[0]), float(center[1])

    # Value of conic at center
    f_c = a * cx ** 2 + b * cx * cy + c * cy ** 2 + d * cx + e * cy + f
    if f_c == 0.0:
        return None

    # Eigenvalues of [[a, b/2],[b/2, c]] give inverse squared semi-axes
    eig_vals = np.linalg.eigvalsh(np.array([[a, b / 2.0], [b / 2.0, c]]))
    lam1, lam2 = float(eig_vals[0]), float(eig_vals[1])

    if lam1 <= 0.0 or lam2 <= 0.0:
        return None

    r1 = float(np.sqrt(abs(f_c) / lam1))
    r2 = float(np.sqrt(abs(f_c) / lam2))
    # Semi-major is the larger one
    r_major, r_minor = max(r1, r2), min(r1, r2)

    # Orientation: angle of major axis
    # Eigenvector corresponding to lam1 (smaller eigenvalue → larger semi-axis)
    _, eig_vecs = np.linalg.eigh(np.array([[a, b / 2.0], [b / 2.0, c]]))
    major_vec = eig_vecs[:, 0]  # eigenvector for smallest eigenvalue
    angle_rad = float(np.arctan2(float(major_vec[1]), float(major_vec[0])))
    angle_deg = float(np.degrees(angle_rad)) % 180.0

    return CircleEllipseFit(
        center_x=cx,
        center_y=cy,
        radius_x=r_major,
        radius_y=r_minor,
        angle_deg=angle_deg,
        confidence=0.0,  # caller fills in after residuals
    )


# ── Edge extraction ────────────────────────────────────────────────────────────

def extract_edge_points(mask: np.ndarray) -> np.ndarray:
    """Extract (x, y) edge coordinates from a boolean mask.

    An edge pixel is any True pixel that has at least one False neighbour
    in 4-connectivity.

    Args:
        mask: 2-D boolean array, shape (H, W).

    Returns:
        Float64 array of shape (N, 2) with columns [x (col), y (row)].
        Empty (0, 2) array when the mask is empty.
    """
    if not np.any(mask):
        return np.zeros((0, 2), dtype=np.float64)

    # Erode: interior pixels have all 4 neighbours True
    interior = np.zeros_like(mask)
    interior[1:-1, 1:-1] = (
        mask[1:-1, 1:-1]
        & mask[:-2, 1:-1]   # north
        & mask[2:, 1:-1]    # south
        & mask[1:-1, :-2]   # west
        & mask[1:-1, 2:]    # east
    )
    edge = mask & ~interior

    rows, cols = np.where(edge)
    return np.column_stack(
        [cols.astype(np.float64), rows.astype(np.float64)]
    )


# ── Utility ────────────────────────────────────────────────────────────────────

def detect_clipping(
    fit: CircleEllipseFit,
    frame_width: int,
    frame_height: int,
    margin_px: float = 2.0,
) -> bool:
    """Return True when the fitted circle/ellipse is clipped by the frame edge.

    Checks whether any point on the bounding box of the ellipse lies outside
    [margin, frame_size − margin].
    """
    r_max = max(fit.radius_x, fit.radius_y)
    return (
        fit.center_x - r_max < margin_px
        or fit.center_x + r_max > frame_width - margin_px
        or fit.center_y - r_max < margin_px
        or fit.center_y + r_max > frame_height - margin_px
    )


def compare_circle_centers(
    fit1: CircleEllipseFit,
    fit2: CircleEllipseFit,
) -> float:
    """Return Euclidean distance between the two fitted centers (pixels)."""
    dx = fit1.center_x - fit2.center_x
    dy = fit1.center_y - fit2.center_y
    return float(np.sqrt(dx ** 2 + dy ** 2))


# ── Private helpers ────────────────────────────────────────────────────────────

def _degenerate_circle() -> CircleEllipseFit:
    return CircleEllipseFit(
        center_x=0.0,
        center_y=0.0,
        radius_x=0.0,
        radius_y=0.0,
        angle_deg=0.0,
        confidence=0.0,
    )
