# Requirements Addon 2026-05-06 — SmartTScope Fixes

**Summary**: Fix/update requirements for the SmartTScope capture software: camera naming, live preview backend, histogram, exposure/gain UI, and Startup tab polish.

**Sources**: `resources/hlrequirements/SmartTScope_Fixes_Requirements_20260506.md`

**Last updated**: 2026-05-06

---

## Scope

Version 1.1 of the SmartTScope addon requirements. Primary purpose: fix and update the current solution. All 13 tasks are to be added to the persistent SmartTScope tasklist **after** the current AutoGain implementation run completes.

Priority rule from the requirements:

> Add these items after finishing the current implementation/fix run. Do not interrupt the current run unless one of these issues blocks the current run.

---

## §0 Persistent Tasklist Handling

All items shall be added to the SmartTScope tasklist after the current run, each with: affected component, observed issue, expected behavior, verification criterion, and priority.

Priority summary:

| Priority | Area | Reason |
|---|---|---|
| P1 | Mount not moving despite connected state | Core functionality appears broken |
| P1 | Live Preview frame display | Core preview functionality appears broken |
| P1 | Exposure/gain parameter handling | Camera control appears unreliable |
| P1 | Camera selector consistency | Multi-camera operation depends on it |
| P2 | Histogram display | Required for preview and later Auto Gain |
| P2 | Version display | Needed for debugging and traceability |
| P2 | Custom target visibility | Important for session planning |
| P3 | Layout margins / mount limits visual bug | UI polish |

---

## §1 Global Camera Selection

### 1.1 Display by meaningful name

All camera selectors shall display cameras by model name, not by internal indexes such as `CAM0`.

Expected examples: `ATR585M`, `G3M678M`, `GPCMOS02000KPA`

If duplicate model names exist, disambiguate as `G3M678M (1)`, `G3M678M (2)`.

Later nice-to-have: `G3M678M (OAG)`, `GuideScope IMX290`.

### 1.2 Internal IDs

Internal IDs (`CAM0`, `CAM1`) may be used internally but shall not appear as the primary user-facing label.

### 1.3 Camera configuration persistence

Each camera shall be identifiable by model + serial. The user shall be able to assign a friendly alias per camera.

```yaml
cameras:
  - model: ATR585M
    serial: "..."
    role: main
    display_name: ATR585M
  - model: G3M678M
    serial: "..."
    role: oag
    display_name: G3M678M OAG
```

See [[touptek-sdk]] for SDK camera enumeration.

---

## §2 GoTo & Solve Tab

### 2.1 Layout margins

Left and right margins shall be reduced to better use available screen width.

### 2.2 Custom target visibility

Each custom target shall be classified as:

| State | Condition |
|---|---|
| Visible now | Altitude > usable horizon (default 10°) |
| Visible later tonight | Will cross above horizon before astronomical dawn |
| Not visible tonight | Will not rise before astronomical dawn |

Session night ends at astronomical dawn; fallback to sunrise if dawn cannot be calculated.

See [[requirements-addon-20260501]] for the existing observer location configuration.

### 2.3 Live Preview camera selection

The Live Preview camera selector shall list all connected cameras by user-facing name (same rules as §1.1). Currently only `CAM0` is offered.

### 2.4 Live Preview start availability

If no camera is detected, the Start Preview action shall be disabled or blocked with a clear UI message.

### 2.5 Exposure tooltip correctness

Exposure tooltip shall use the selected camera's actual driver-reported exposure range and stepping. Stale values from another camera shall not be shown.

### 2.6 Exposure display and unit handling

Adaptive formatting rules:

| Example value | Display |
|---|---|
| 0.001 s | `0.001 s` |
| 1.5 s | `1.5 s` |
| 621 s | `621 s` (not `621.00 s`) |

The displayed value shall match the value sent to the camera backend.

### 2.7 Gain display and range handling

Gain controls shall respect the selected camera's driver-reported gain range. Invalid values shall not be offered.

### 2.8 Live Preview frame and histogram display

Observed issue: WebSocket preview requests are accepted, but no frames and no histogram appear.

Frame display rules:

| Camera type | Preview behavior |
|---|---|
| Monochrome | Display grayscale |
| Color | Display debayered image |
| Histogram | Derived from received frame data |

If no valid frame arrives, the UI shall show a reason (e.g. `No preview frames received.`).

### 2.9 Histogram source

- No ROI: full frame
- ROI selected: ROI only is acceptable
- No valid frame: empty/error state — stale histogram shall not persist

### 2.10 Exposure/gain backend application

The backend shall apply the exact exposure and gain values sent by the UI, or report a clear reason if the camera rejects or modifies them.

Required startup log example:
```text
Preview started:
camera=ATR585M   camera_index=0
requested_exposure_s=7.1   effective_exposure_s=7.1
requested_gain=3200   effective_gain=3200
format=RAW12   resolution=3840x2160
```

---

## §3 Alignment Tab

### 3.1 Polar Alignment camera selector

Polar Alignment Measure shall list all connected cameras by user-facing name. Default selection: main camera.

---

## §4 Startup Tab

### 4.1 Mount Limits tile rendering

The horizontal reference line in the Mount Limits tile shall render at the correct altitude position, not above `ALT MIN (HORIZON)`.

### 4.2 Version display

The application header shall show the SmartTScope version and short Git commit hash:
```text
SmartTScope v0.1 abc1234
```

Version source priority: package metadata → app version file → short git commit → dev fallback.

---

## §5 Suggested Implementation Order

| Phase | Focus | Priority |
|---|---|---|
| Phase 1 | Stabilize camera registry and selectors | P1 |
| Phase 2 | Fix Live Preview backend parameter handling | P1 |
| Phase 3 | Fix frame display and histogram | P1 / P2 |
| Phase 4 | Fix exposure/gain UI formatting | P1 / P2 |
| Phase 5 | Startup UI fixes | P2 / P3 |
| Phase 6 | Custom target visibility | P2 |

---

## §6 Issue-to-Task Mapping

| Task ID | Area | Summary | Priority |
|---|---|---|---|
| STS-ADDON-001 | Tasklist | Add all requirements to persistent tasklist after current run | P1 |
| STS-ADDON-002 | Camera registry | Centralize camera identity, naming, and alias support | P1 |
| STS-ADDON-003 | GoTo & Solve | Replace `CAM0` with camera names in Live Preview selector | P1 |
| STS-ADDON-004 | Alignment | Replace `Cam 0` with camera names in Polar Alignment selector | P1 |
| STS-ADDON-005 | Live Preview backend | Apply exposure/gain correctly and report effective values | P1 |
| STS-ADDON-006 | Live Preview backend | Fix missing frame delivery / blank frame issue | P1 |
| STS-ADDON-007 | Histogram | Display histogram from received frame data | P2 |
| STS-ADDON-008 | UI formatting | Adaptive exposure display and camera-specific gain range | P2 |
| STS-ADDON-009 | UI tooltip | Fix exposure tooltip to use selected camera capabilities | P2 |
| STS-ADDON-010 | Startup | Fix Mount Limits tile horizontal line rendering | P3 |
| STS-ADDON-011 | Version | Display app version and short Git hash in header | P2 |
| STS-ADDON-012 | GoTo & Solve | Reduce left/right margins | P3 |
| STS-ADDON-013 | Custom Targets | Highlight visible now / visible later / not visible tonight | P2 |

---

## No Open Clarifications

- "Visible later tonight" ends at **astronomical dawn**
- Version display uses the **short Git hash**

---

## Related pages

- [[touptek-sdk]]
- [[requirements-addon-20260501]]
- [[requirements-addon-20260502b]]
- [[requirements]]
