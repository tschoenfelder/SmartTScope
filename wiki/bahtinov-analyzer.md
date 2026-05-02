# Bahtinov Analyzer

**Summary**: Algorithm and design specification for automated Bahtinov mask focus analysis — detects three diffraction spikes in a star image and measures how precisely they converge to a common crossing point.

**Sources**: resources/hlrequirements/requirements_addon_20260502.txt

**Last updated**: 2026-05-02

---

## Purpose and workflow position

The Bahtinov analyzer is a **collimation and focus support tool** placed in Stage 4 of the SmartTScope wizard (after mount connected, polar aligned, and initial focus achieved). The user places a Bahtinov mask over the telescope aperture; the system then:

1. Takes a live preview frame
2. Finds the brightest real star in the image
3. Crops a region of interest (ROI) around it
4. Detects the three diffraction spikes
5. Measures how far apart the spike intersections are
6. Displays the result as an arrow overlay
7. Asks the user to adjust the focuser and reconfirms; re-centres on star drift

---

## Two-layer design

The algorithm is deliberately split to keep image logic separate from hardware control:

```
BahtinovAnalyzer          — image only, no hardware calls
    ↓ returns CrossingAnalysisResult
FocusController           — calls BahtinovAnalyzer in a loop
    ↓ drives focuser       and stops when focus_error_px ≈ 0
```

`BahtinovAnalyzer` never moves the mount or focuser. It only reports metrics. `FocusController` decides how to react. See [[autofocus]] for the broader focus automation context.

---

## Output data structure

```python
@dataclass(frozen=True)
class SpikeLine:
    a: float           # normal-form line coefficient (a² + b² = 1)
    b: float
    c: float           # ax + by + c = 0
    angle_deg: float
    confidence: float

@dataclass(frozen=True)
class CrossingAnalysisResult:
    object_center_px:           tuple[float, float]
    lines:                      list[SpikeLine]        # always 3
    common_crossing_point_px:   tuple[float, float]
    pairwise_intersections_px:  list[tuple[float, float]]  # P12, P13, P23
    crossing_error_rms_px:      float
    crossing_error_max_px:      float
    focus_error_px:             float   # signed; primary Bahtinov metric
    detection_confidence:       float
```

**Primary focus metric**: `focus_error_px` — signed perpendicular distance from the outer-spike intersection to the middle spike line. Equals 0 when perfectly focused.

**Quality guard**: `crossing_error_rms_px` — RMS of the three pairwise intersection distances from their mean. Use this to reject results where spike detection was unreliable.

| `crossing_error_rms_px` | Interpretation |
|---|---|
| 0 px | Perfect geometric fit |
| 1–3 px | Very good |
| 3–10 px | Usable but not ideal |
| > 10 px | Likely out of focus, bad detection, or distorted spikes |

---

## Step-by-step algorithm

### Step 1 — Find the brightest real object

Do not use the raw maximum pixel (vulnerable to hot pixels / cosmic rays). Use a flux-weighted score:

```
score = total_flux × sqrt(area)
```

Process:
1. Convert to grayscale / luminance
2. Estimate and subtract background
3. Threshold significant bright regions
4. Find connected components
5. Select the component with the highest `score`

Output: `(x0, y0)` centroid, radius estimate.

### Step 2 — Crop ROI

```
roi_size = 6 × estimated_star_radius   (general)
roi_size = 200–600 px                  (telescope images, depending on resolution)
```

### Step 3 — Preprocess the ROI

Goal: preserve the three linear spike structures, suppress noise and the saturated star core.

1. Subtract local background
2. Apply mild Gaussian blur (σ ≈ 1.0)
3. Mask saturated central core (radius 5–20 px from centroid)
4. Normalize intensity
5. Threshold remaining bright structures

The core mask is essential for Bahtinov images because the star centre dominates and will otherwise corrupt line fitting.

### Step 4 — Detect candidate line pixels

**Option A — Hough transform** (good for clean, clear spikes):
```
edges = Canny(ROI)
lines = HoughLinesP(edges)
group by angle → 3 clusters
```

**Option B — Weighted RANSAC** (preferred for real telescope frames with noise, saturation, seeing blur):
```
candidate_pixels = all pixels above threshold
weight = pixel brightness
fit line using RANSAC
remove inliers
repeat until 3 dominant lines found
```

For SmartTScope, RANSAC or weighted Hough is preferred because real frames contain noise and imperfect spikes.

### Step 5 — Fit three lines in normal form

Represent each line as `ax + by + c = 0` with `√(a² + b²) = 1`. The perpendicular distance from any point `(x, y)` to the line is then simply `|ax + by + c|`.

Fit each of the three spike groups using weighted least squares or RANSAC.

### Step 6 — Compute pairwise intersections

For lines `L1` and `L2`:

```
D  = a1·b2 − a2·b1
x  = (b1·c2 − b2·c1) / D
y  = (c1·a2 − c2·a1) / D
```

If `|D| ≈ 0` the lines are nearly parallel — result is invalid, discard.

Compute `P12`, `P13`, `P23`.

### Step 7 — Measure crossing quality

```
Pc = mean(P12, P13, P23)

crossing_error_rms = sqrt(
    (dist(P12, Pc)² + dist(P13, Pc)² + dist(P23, Pc)²) / 3
)
```

### Step 8 — Identify the middle Bahtinov spike

Sort the three detected lines by angle. The middle spike is the one whose angle lies between the other two. The outer two spikes are symmetric about the middle.

### Step 9 — Calculate the primary focus metric

```
P_outer = intersection(L_outer_1, L_outer_2)
focus_error_px = a_mid · P_outer.x + b_mid · P_outer.y + c_mid
```

(Sign convention: positive = one direction, negative = other. User UI shows direction via arrow.)

---

## UI requirements

- Live image with overlay showing the three detected lines and an arrow from `P_outer` to the middle spike, scaled by `focus_error_px`.
- Display `focus_error_px` numerically and `crossing_error_rms_px` as a quality indicator.
- After each user focuser adjustment: re-acquire image, re-run analyzer, re-display.
- If the star drifts out of the ROI: re-centre using mount (pulse guide) and re-acquire.
- User flow: adjust → confirm in focus → proceed, or quit to manual.

---

## Related pages

- [[autofocus]]
- [[hardware-platform]]
- [[onstep-protocol]]
- [[requirements]]
