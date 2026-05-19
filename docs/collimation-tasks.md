# SmartTScope — Tri-Bahtinov Collimation — Task List

Hardware context: 9-slot tri-Bahtinov mask with a rotating wheel that exposes one triplet
(3 spikes) at a time.  The user rotates the wheel through 3 positions (0° / 120° / 240°),
captures one frame per position, and the system analyses each frame with the existing
`BahtinovAnalyzer`.  No secondary-mirror guidance is generated — the user decides which
screw to turn.  The software's job is to show the deviation clearly and declare when all
three positions pass.

**Legend**
- `[ ]` pending · `[x]` done · `[~]` in progress
- Each task is scoped for roughly one session.
- *Depends:* lists task IDs that must be complete first.

---

## Phase 0 — Domain model

### COL-0-1 — CollimationSession domain service
- [x] `domain/collimation_session.py`:
  - `CollimationConfig(frozen=True)`:
    `n_positions=3`, `focus_error_threshold_px=1.5`,
    `crossing_error_threshold_px=3.0`, `min_detection_confidence=0.6`.
  - `PositionResult`:
    `position_index` (0–2), `angle_label` ("0°" / "120°" / "240°"),
    `analysis: CrossingAnalysisResult`, `passed: bool`,
    `captured_at: str` (ISO-8601).
  - `CollimationStatus` (str Enum):
    `IDLE`, `ACQUIRING_STAR`, `WAITING_FOR_WHEEL`,
    `CAPTURING`, `ANALYSING`, `POSITION_DONE`, `ALL_DONE`, `FAILED`.
  - `CollimationSession`:
    `start(camera, mount, star_ra, star_dec)` — slews and centers;
    `capture_position()` — takes one frame, runs `BahtinovAnalyzer`,
    stores `PositionResult`, auto-advances position index;
    `recenter()` — re-runs plate-solve + correction if star drifted;
    `status`, `results` (list of up to 3 `PositionResult`),
    `verdict` (`passed: bool | None`, `positions_passed: int`).
- [x] Unit tests: state transitions, verdict logic (all-pass / partial-fail / retry),
  threshold enforcement.

*Covers:* collimation session orchestration  
*Depends:* existing `BahtinovAnalyzer`, mount goto/center

---

### COL-0-2 — Overlay data extension
- [x] Extend `CrossingAnalysisResult.to_dict()` (or add `overlay_data()` method) to emit
  all data the UI needs to render the overlay without any further computation:
  - `spike_lines`: list of 3 `{x0, y0, x1, y1}` segments clipped to ROI bounds.
  - `crossing_point`: `{x, y}` — `common_crossing_point_px`.
  - `deviation_arrow`: `{x0, y0, dx, dy}` — origin at `P_outer` intersection,
    vector perpendicular to middle spike, magnitude = `focus_error_px` px (signed).
  - `spread_triangle`: `[{x,y}, {x,y}, {x,y}]` — `pairwise_intersections_px` (P12 P13 P23).
  - `roi_offset`: `{row, col}` — ROI top-left in full-frame coordinates so the UI
    can translate overlay coords back to image space.
- [x] Unit tests: `overlay_data()` keys present, `deviation_arrow` direction matches sign
  of `focus_error_px`, segment endpoints lie within ROI bounds.

*Covers:* UI overlay rendering contract  
*Depends:* COL-0-1

---

## Phase 1 — Star acquisition

### COL-1-1 — Bright-star selector and slew-to-center
- [ ] `domain/collimation_stars.py`:
  `COLLIMATION_STARS` — curated list of ≈ 30 stars suitable for Bahtinov work
  (magnitude 1–4, spread across the sky): name, RA, Dec, magnitude.
  `stars_above_horizon(lat_deg, lon_deg, min_alt_deg=30)` → filtered + sorted by altitude.
- [ ] `POST /api/collimation/start` validates the chosen star and triggers:
  1. `mount.goto(ra, dec)`
  2. Plate-solve (reuse existing solver) + recenter loop (≤ 3 iterations, ≤ 2 arcmin)
  3. Session transitions to `WAITING_FOR_WHEEL` on success; `FAILED` on repeated solve failure.
- [ ] Unit tests: star filtering by altitude, slew+center mocked, failure path returns `FAILED`.

*Covers:* star selection, autonomous centering  
*Depends:* COL-0-1, existing catalog + solver + mount goto

---

## Phase 2 — Three-position capture loop

### COL-2-1 — Position capture loop and drift re-centering
- [ ] `POST /api/collimation/capture`:
  - Asserts session is in `WAITING_FOR_WHEEL` state.
  - Transitions to `CAPTURING` → captures one frame → `ANALYSING` → runs `BahtinovAnalyzer`.
  - If `detection_confidence < min_detection_confidence`: returns `low_confidence` warning;
    does NOT advance position; user can retry.
  - Stores `PositionResult`; transitions to `POSITION_DONE`.
  - If this was the last position: evaluate overall verdict → `ALL_DONE`.
  - Otherwise: transitions to `WAITING_FOR_WHEEL` for the next position.
- [ ] `POST /api/collimation/next_position`:
  - Re-centers star (plate-solve + correction, max 2 arcmin) before advancing.
  - If re-center fails: warns but still advances (user can recenter manually).
  - Transitions back to `WAITING_FOR_WHEEL`.
- [ ] `POST /api/collimation/retry_position`:
  - Re-runs capture for the current position (star was already re-centered or user skipped).
- [ ] Unit tests: low-confidence retry, drift re-center called between positions,
  last-position → `ALL_DONE`, partial retry flow.

*Covers:* per-position capture, drift correction, low-confidence guard  
*Depends:* COL-0-1, COL-1-1

---

## Phase 3 — REST API

### COL-3-1 — Full collimation REST endpoint set
- [ ] `api/collimation.py` router, prefix `/api/collimation`:

  | Method | Path | Description |
  |---|---|---|
  | `POST` | `/start` | `{star_name, camera_index, config?}` → 202 / 409 / 400 |
  | `GET` | `/status` | Always 200; returns `CollimationStatusResponse` |
  | `POST` | `/capture` | Trigger capture for current wheel position |
  | `POST` | `/next_position` | Re-center + advance to next position |
  | `POST` | `/retry_position` | Retry capture at current position |
  | `POST` | `/stop` | Abort session; 200 always |

- [ ] `CollimationStatusResponse` (Pydantic):
  `status`, `current_position_index`, `current_angle_label`,
  `positions_done`, `positions_passed`, `verdict`,
  `last_result?: {focus_error_px, crossing_error_rms_px, detection_confidence,
  passed, overlay_data}`,
  `warning_msg?`.
- [ ] Wire router into `app.py`.
- [ ] Unit tests: idle status, start/409/400, low-confidence warning, all-done verdict,
  stop clears state.

*Covers:* REST surface for UI  
*Depends:* COL-2-1

---

## Phase 4 — UI

### COL-4-1 — Collimation UI in Stage 4
- [ ] Stage 4 collimation card (below or replacing the existing Bahtinov single-shot card):
  - **Star selector**: dropdown of `stars_above_horizon()`; shows name + altitude.
  - **Start** button → calls `POST /api/collimation/start`; spinner while slewing/centering.
  - **Position workflow** (repeats 3×):
    - Prompt: "Rotate wheel to position N (Xdeg) — then click Capture."
    - **Capture** button → `POST /api/collimation/capture`.
    - Image canvas showing:
      - Live captured frame (grayscale JPEG, same pipeline as preview).
      - Three spike lines drawn in colour.
      - `common_crossing_point_px` dot.
      - Deviation arrow at `P_outer`: origin dot + arrow tip, length ∝ `focus_error_px`;
        colour: green < 1.5 px, orange 1.5–4 px, red > 4 px.
      - Spread triangle: P12 P13 P23 dots connected by dashed lines.
    - Stats strip below image:
      `focus_error: ±X.X px` · `quality (rms): X.X px` · `confidence: X%`.
    - Position result badge: **PASS** (green) / **FAIL** (red) / **Low confidence — retry**.
  - **Next Position** button (after `POSITION_DONE`) → `POST /api/collimation/next_position`.
  - **Retry** button → `POST /api/collimation/retry_position`.
  - **Overall verdict** row (after all 3 positions):
    - `ALL PASS` → green banner "Collimation complete".
    - Any FAIL → yellow banner "Position(s) X failed — adjust secondary and repeat".
    - **Repeat Failed** button → re-runs only the failed positions from `WAITING_FOR_WHEEL`.

*Covers:* complete collimation UX  
*Depends:* COL-3-1

---

## Progress summary

| Phase | Tasks | Done |
|---|---:|---:|
| 0 — Domain model | 2 | 2 |
| 1 — Star acquisition | 1 | 0 |
| 2 — Capture loop | 1 | 0 |
| 3 — REST API | 1 | 0 |
| 4 — UI | 1 | 0 |
| **Total** | **6** | **2** |

---

*Last updated: 2026-05-10 — COL-0-2 done (overlay_data() + roi fields + _clip_line_to_rect + 20 new tests)*
