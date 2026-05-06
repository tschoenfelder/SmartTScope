# SmartTScope Addon Requirements

Version: 1.1  
Scope: SmartTScope capture software enhancement for Touptek astronomy cameras  
Primary purpose: Fix / update current solution  
Status: Draft requirements for issue/task creation

---

## 0. Persistent Tasklist Handling

All items in this document shall be added to the persistent SmartTScope tasklist.

Priority rule:

- Add these items **after finishing the current implementation/fix run**.
- Do not interrupt the current run unless one of these issues blocks the current run.
- Each item shall receive a traceable task ID.
- Each task shall reference:
  - affected tab/component,
  - observed issue,
  - expected behavior,
  - verification criterion,
  - priority.

Suggested priority:

| Priority | Area | Reason |
|---|---|---|
| P1 | Mount is stated to be connected, but doesn't move. Mock moutn connected? | Core functionality appears broken |
| P1 | Live Preview frame display | Core preview functionality appears broken |
| P1 | Exposure/gain parameter handling | Camera control appears unreliable |
| P1 | Camera selector consistency | Multi-camera operation depends on it |
| P2 | Histogram display | Required for preview and later Auto Gain |
| P2 | Version display | Needed for debugging and traceability |
| P2 | Custom target visibility | Important for session planning |
| P3 | Layout margins / mount limits visual bug | UI polish unless it hides relevant data |

---

## 1. Global Camera Selection Requirements

### 1.1 Camera display names

All camera selectors shall display cameras by meaningful camera names, not by internal indexes such as `CAM0`.

Expected examples:

```text
ATR585M
G3M678M
GPCMOS02000KPA
```

If multiple connected cameras have the same model name, SmartTScope shall disambiguate them as:

```text
G3M678M (1)
G3M678M (2)
```

Later nice-to-have:

```text
G3M678M (OAG)
G3M678M (Planetary)
GuideScope IMX290
```

### 1.2 Internal camera IDs

Internal camera IDs such as `CAM0`, `CAM1`, or driver indexes may still be used internally, but shall not be shown as the primary user-facing camera name.

### 1.3 Camera configuration persistence

The hardware setup is expected to be stable.

When a new camera is detected, SmartTScope may add it to the configuration or camera registry.

The user shall later be able to assign a friendly alias or “call sign” to each camera, especially when two cameras of the same model are connected.

Example configuration concept:

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

  - model: GPCMOS02000KPA
    serial: "..."
    role: guide
    display_name: GuideScope IMX290
```

### 1.4 Acceptance criteria

```gherkin
Given multiple cameras are connected
When the user opens any camera selector
Then all available cameras shall be listed by user-facing name
And internal names such as CAM0 shall not be shown as the primary label
```

```gherkin
Given two connected cameras have the same model name
When SmartTScope builds the camera display list
Then it shall disambiguate them as Model (1), Model (2), etc.
```

---

## 2. GoTo & Solve Tab

### 2.1 Layout margins

Observed issue:

- Left and right margins use too much screen space.

Requirement:

Reduce left and right margins to better utilize available screen width.

Verification:

```gherkin
Given the user opens the GoTo & Solve tab
When the tab is rendered
Then the left and right margins shall not waste significant screen width
And the available space shall be used for target lists, preview, and controls
```

---

### 2.2 Custom target visibility

Under **Custom Targets**, SmartTScope shall visually distinguish:

| Target state | Meaning |
|---|---|
| Visible now | Target is currently above the usable horizon |
| Visible later tonight | Target is not currently usable but will become usable later during the same night |
| Not visible tonight | Target will not become usable during the session night |

MVP rule:

- A target is considered visible if its altitude is above the usable horizon.
- If no horizon file is available, use a minimum altitude threshold of **10°**.
- If a horizon file is available, horizon data may be used.
- “Visible later tonight” means the target rises above the usable horizon later during the same night and may be a session target.
- The session night ends at **astronomical dawn**.
- If astronomical dawn cannot be calculated, use next sunrise as fallback.
- Edge cases such as Venus becoming visible after dawn may be classified according to the selected session/night definition.

Initial MVP simplification:

```text
visible_now = altitude > 10°
visible_later = altitude crosses above 10° before astronomical dawn
```

Verification:

```gherkin
Given custom targets are listed
And observer location and time are known
When the GoTo & Solve tab is opened
Then each target shall be marked as visible now, visible later tonight, or not visible tonight
And the default minimum altitude shall be 10° if no horizon file is available
And visible later tonight shall be evaluated up to astronomical dawn
```

---

### 2.3 Live Preview camera selection

Observed issue:

- Startup tab shows two cameras.
- GoTo & Solve / Live Preview only offers one camera as `CAM0`.
- All suitable connected cameras should be selectable by name.

Requirement:

```text
The Live Preview camera selector shall list all connected cameras by user-facing name.
```

Example:

```text
ATR585M
G3M678M
GPCMOS02000KPA
```

or, if duplicated:

```text
G3M678M (1)
G3M678M (2)
```

Verification:

```gherkin
Given multiple cameras are connected
When the user opens the Live Preview camera selector
Then all connected cameras shall be listed by user-facing name
And internal names such as CAM0 shall not be shown as the primary label
```

---

### 2.4 Live Preview start availability

Requirement:

```text
If no camera is detected or selected, the Start Preview button shall be disabled or shall show a clear reason why preview cannot start.
```

Expected UI message examples:

```text
No camera detected.
Preview cannot start because no camera is connected.
Preview cannot start because selected camera is unavailable.
```

Verification:

```gherkin
Given no camera is detected
When the user opens Live Preview
Then the Start Preview action shall be disabled or blocked
And the UI shall explain that no camera is available
```

---

### 2.5 Exposure tooltip correctness

Observed issue:

- Tooltip on exposure says next values are `1.6` and `2.1`.
- This does not match the selected camera.

Requirement:

```text
Exposure tooltips shall be calculated from the selected camera’s actual driver-reported exposure range, unit, and stepping behavior.
```

Verification:

```gherkin
Given a camera is selected
When the user hovers over the exposure control
Then the tooltip shall show values valid for that selected camera
And shall not reuse stale tooltip values from another camera
```

---

### 2.6 Exposure display and unit handling

Exposure display shall match the actual value sent to the camera.

Rules:

| Exposure value | Display rule |
|---:|---|
| Very short exposure | Preserve meaningful precision, e.g. `0.001 s` |
| Medium exposure | Use readable precision, e.g. `1.5 s` |
| Long exposure | Avoid pointless decimals, e.g. `621 s`, not `621.00 s` |

Requirement:

```text
Exposure shall use adaptive formatting. The UI value shall match the value sent to the camera.
```

Examples:

```text
0.001 s
0.01 s
0.1 s
1.5 s
7.1 s
621 s
```

Verification:

```gherkin
Given the camera supports exposure values up to 621 seconds
When the exposure is set to 621 seconds
Then the UI shall display 621 s
And the backend shall send 621 seconds to the camera
```

---

### 2.7 Gain display and range handling

Gain options are camera-specific.

Requirement:

```text
Gain controls shall respect the selected camera’s driver-reported gain range and format.
```

Expected behavior:

- Gain shall not be displayed with an invalid or misleading number format.
- Gain range shall use the camera’s valid values, for example from `100` to the camera-specific maximum.
- The UI shall not offer gain values outside the selected camera’s supported range.

Verification:

```gherkin
Given a camera reports a gain range from 100 to a camera-specific maximum
When the gain control is rendered
Then the displayed values shall respect that range
And the backend shall not send unsupported gain values
```

---

### 2.8 Live Preview frame and histogram display

Observed issue:

- Logs show WebSocket preview requests.
- No frames are displayed.
- No histogram is displayed.
- Exposure appears ignored.

Example observed log:

```text
INFO:     192.168.178.128:65516 - "GET /api/mount/status HTTP/1.1" 200 OK
INFO:     192.168.178.128:65481 - "WebSocket /ws/preview?exposure=20.1&gain=3200&camera_index=0" [accepted]
INFO:     connection open
```

Requirement:

```text
Live Preview shall display received camera frames and a histogram derived from the received frame data.
```

Frame display rules:

| Camera type | Preview behavior |
|---|---|
| Monochrome | Display grayscale |
| Color | Display debayered image |
| Stretch | User-selectable |
| Histogram | Derived from valid received frame data |

If no valid frame arrives, the UI shall show a reason.

Example messages:

```text
No preview frames received.
Camera did not return image data.
Preview stream disconnected.
Selected camera is unavailable.
Exposure/gain setting rejected by camera.
```

Verification:

```gherkin
Given Live Preview is started for a connected camera
When valid frames are received
Then the preview image shall update
And the histogram shall update from the received frame data
```

Failure verification:

```gherkin
Given Live Preview is started
And no valid frame data is received
When the timeout is reached
Then the UI shall show a reason
And the histogram shall show an empty or error state
And stale histogram data shall not be displayed
```

---

### 2.9 Histogram source

The histogram shall be calculated from the actual preview frame data.

Rules:

| Condition | Histogram source |
|---|---|
| No ROI selected | Full frame |
| ROI selected | ROI only is acceptable |
| No valid frame | Empty/error state |

Verification:

```gherkin
Given an ROI is selected
When preview frames are received
Then the histogram may be calculated from the selected ROI only
```

---

### 2.10 Exposure/gain backend application

Observed issue example:

```text
/ws/preview?exposure=7.1&gain=3200&camera_index=0
```

Observed behavior:

- Exposure is set to `7.1`.
- Frame count increases faster than expected.
- Frame is blank.
- No histogram data is shown.

Requirement:

```text
The backend shall apply the exposure and gain values requested by the UI, or report a clear reason if the camera rejects or modifies them.
```

Verification:

```gherkin
Given the user starts preview with exposure 7.1 s and gain 3200
When the backend opens the preview stream
Then it shall send exposure 7.1 s and gain 3200 to the selected camera
And it shall verify or report the effective camera settings
And frame cadence shall be consistent with the effective exposure unless the driver reports a different effective exposure
```

Additional logging requirement:

```text
Preview startup logs shall include selected camera name, internal camera ID, requested exposure, effective exposure, requested gain, effective gain, frame format, and resolution.
```

Example log:

```text
Preview started:
camera=ATR585M
camera_index=0
requested_exposure_s=7.1
effective_exposure_s=7.1
requested_gain=3200
effective_gain=3200
format=RAW12
resolution=3840x2160
```

---

## 3. Alignment Tab

### 3.1 Polar Alignment camera selector

Observed issue:

- Polar Alignment Measure shows only `Cam 0`.
- It should list all suitable connected cameras.

Requirement:

```text
The Polar Alignment camera selector shall list all connected cameras by user-facing name.
```

All connected cameras should be available because an alignment workflow may improve precision in stages:

1. guide-scope camera,
2. main camera,
3. OAG camera.

Default behavior:

```text
The selector shall start with the main camera selected if available.
```

Verification:

```gherkin
Given multiple cameras are connected
When the user opens the Polar Alignment Measure camera selector
Then all connected cameras shall be listed by user-facing name
And the main camera shall be selected by default if available
```

---

## 4. Startup Tab

### 4.1 Mount Limits tile rendering

Observed issue:

- Mount Limits tile shows a horizontal line wrongly above `ALT MIN (HORIZON)`.
- This appears to be a rendering bug.

Requirement:

```text
The Mount Limits tile shall render the horizontal reference line at the correct position relative to the displayed altitude scale and ALT MIN (HORIZON).
```

Verification:

```gherkin
Given the Startup tab is rendered
When the Mount Limits tile is displayed
Then the horizontal reference line shall align with the correct altitude reference
And it shall not be drawn above ALT MIN due to a rendering/layout error
```

---

### 4.2 Version display

Observed issue:

- Version number should update when source code is updated.
- Current version is `v0.1`.
- Header should show the GitHub-linked version and Git commit.

Requirement:

```text
The application header shall display the running SmartTScope version and short Git commit hash.
```

Recommended display:

```text
SmartTScope v0.1 abc1234
```

or:

```text
SmartTScope v0.1-dev+abc1234
```

Version source priority:

```text
1. package metadata / project version
2. app version file
3. short git commit hash from source checkout
4. development fallback
```

Verification:

```gherkin
Given SmartTScope is running from a Git checkout
When the application header is rendered
Then the header shall show the configured application version
And the current short Git commit hash
```

---

## 5. Suggested Implementation Order

### Phase 1 — Stabilize camera registry and selectors

Tasks:

1. Build or fix a central camera registry.
2. Store model name, internal camera index, serial if available, role, and optional user alias.
3. Replace `CAM0` labels in:
   - GoTo & Solve / Live Preview,
   - Alignment / Polar Alignment Measure.
4. Ensure duplicate models are displayed as `Model (1)`, `Model (2)`.
5. Ensure internal camera IDs remain available to the backend.

Verification focus:

```text
All connected cameras appear by name in all relevant selectors.
```

Priority: **P1**

---

### Phase 2 — Fix Live Preview backend parameter handling

Tasks:

1. Trace `/ws/preview` parameter parsing.
2. Verify exposure units.
3. Send exposure/gain to the selected camera.
4. Read back effective exposure/gain if the driver supports it.
5. Add diagnostic logging.
6. Ensure preview frame cadence matches exposure.
7. Report if the camera rejects or modifies requested values.

Verification focus:

```text
Exposure 7.1 s does not produce sub-second frame cadence unless the driver reports a shorter effective exposure.
```

Priority: **P1**

---

### Phase 3 — Fix frame display and histogram

Tasks:

1. Verify frame acquisition from the Touptek adapter.
2. Verify WebSocket frame encoding.
3. Display monochrome frames as grayscale.
4. Debayer color frames.
5. Add selectable preview stretch.
6. Calculate histogram from valid frame data.
7. Use full frame if no ROI is selected.
8. Use ROI histogram if ROI is selected.
9. Show error reason if frames are missing.

Verification focus:

```text
Preview image and histogram update for each selected camera.
```

Priority: **P1 / P2**

---

### Phase 4 — Fix exposure/gain UI formatting

Tasks:

1. Use camera-specific exposure range.
2. Use adaptive exposure formatting.
3. Use camera-specific gain range.
4. Fix exposure tooltip.
5. Prevent invalid values.
6. Ensure displayed values match backend-sent values.

Verification focus:

```text
The UI displays exactly the values that are sent to the camera.
```

Priority: **P1 / P2**

---

### Phase 5 — Startup UI fixes

Tasks:

1. Fix Mount Limits tile horizontal line rendering.
2. Add version and short Git commit to header.

Verification focus:

```text
Startup tab shows correct visual mount limits and traceable running version.
```

Priority: **P2 / P3**

---

### Phase 6 — Custom target visibility

Tasks:

1. Use observer location and current time.
2. Calculate current altitude.
3. Mark visible now if `ALT > 10°` or above horizon-file threshold.
4. Search later-night visibility until astronomical dawn.
5. Add horizon-file support if available.
6. Mark targets as visible now, visible later tonight, or not visible tonight.

Verification focus:

```text
Custom targets are visibly grouped or highlighted as visible now, visible later, or not visible tonight.
```

Priority: **P2**

---

## 6. Issue-to-Task Mapping

| Task ID | Area | Summary | Priority |
|---|---|---|---|
| STS-ADDON-001 | Tasklist | Add all requirements to persistent SmartTScope tasklist after current run | P1 |
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

## 7. No Open Clarifications

The remaining open points have been clarified:

- The session night for “visible later tonight” ends at **astronomical dawn**.
- The version display shall use the **short Git hash**.
