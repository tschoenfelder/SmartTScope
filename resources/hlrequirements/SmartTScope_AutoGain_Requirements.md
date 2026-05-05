# SmartTScope Automatic Gain, Exposure, Cooling, and Calibration Requirements

Version: 1.0  
Scope: SmartTScope capture software enhancement for Touptek astronomy cameras  
Primary purpose: automatic gain/exposure support for live preview, recording start settings, guiding, and calibration-frame preparation

---

## 1. Context and hardware setup

### 1.1 Cameras

SmartTScope shall support automatic gain/exposure workflows for the following Touptek cameras:

| Camera | Sensor | Main use | Notes |
|---|---|---|---|
| ATR585M / ATR3CMOS08300KMA | Sony IMX585 mono | Main camera | Cooled camera; supports HCG, LCG, HDR; 12-bit ADC; 3840 x 2160; 2.9 um pixels |
| G3M678M / 678M | Sony IMX678 mono | Main camera or OAG camera | Passive cooling; supports HCG and LCG; 12-bit ADC; 3840 x 2160; 2.0 um pixels |
| GPCMOS02000KPA | Sony IMX290 | Guide-scope camera | 1920 x 1080; 12-bit; 2.9 um pixels; USB 2.0; used for guiding only |

### 1.2 Optical trains

| Profile | Scope | Camera | Optical train | Notes |
|---|---|---|---|---|
| `C8_NATIVE_ATR585M` | Celestron C8 SCT | ATR585M | Native f/10 | DSO / lunar / general |
| `C8_REDUCER_063_ATR585M` | Celestron C8 SCT | ATR585M | 0.63x reducer | DSO |
| `C8_NATIVE_678M` | Celestron C8 SCT | 678M | Native f/10 | Planetary / lunar |
| `C8_REDUCER_063_678M` | Celestron C8 SCT | 678M | 0.63x reducer | DSO / preview |
| `C8_BARLOW_2X_678M` | Celestron C8 SCT | 678M | 2x Barlow | Planetary only |
| `GUIDESCOPE_IMX290` | EYSDON 50 mm guide scope | GPCMOS02000KPA | 180 mm focal length | Guiding |
| `OAG_678M` | C8 optical path | 678M | OAG when ATR585M is main camera | Guiding / star acquisition |

### 1.3 Derived image scales

These values are not strict requirements for gain calculation, but they are useful for profile defaults, guiding tolerances, ROI decisions, and object detection.

| Profile | Approx. focal length | Pixel size | Approx. scale |
|---|---:|---:|---:|
| C8 native + ATR585M | 2030 mm | 2.9 um | 0.29 arcsec/px |
| C8 + 0.63 reducer + ATR585M | 1279 mm | 2.9 um | 0.47 arcsec/px |
| C8 native + 678M | 2030 mm | 2.0 um | 0.20 arcsec/px |
| C8 + 0.63 reducer + 678M | 1279 mm | 2.0 um | 0.32 arcsec/px |
| C8 + 2x Barlow + 678M | 4060 mm | 2.0 um | 0.10 arcsec/px |
| Guide scope + IMX290 | 180 mm | 2.9 um | 3.32 arcsec/px |

---

## 2. Goals and boundaries

### 2.1 Main goals

SmartTScope shall provide automatic gain/exposure support for:

1. Live preview.
2. Starting point for recordings.
3. Planetary capture, including planet plus moons where possible.
4. DSO preview.
5. Guided DSO acquisition preparation.
6. Guide-camera and OAG-camera setup.
7. Calibration-frame preparation for bias, dark, and flat frames.
8. Live stacking calibration support using master calibration FITS files.

### 2.2 MVP / MVP+ / later boundary

| Feature | MVP | MVP+ | Later |
|---|---|---|---|
| Main-camera auto gain | One-shot | Continuous convergence | More target-aware optimization |
| Exposure adjustment | Bounded | Bounded and adaptive | More advanced sky/object model |
| Driver-assisted auto exposure/gain | Yes, wrapped by app limits | Yes | Algorithmic optimization beyond driver |
| Full-frame histogram | Yes | Yes | Yes |
| ROI-linked histogram | No | No | Optional final-final enhancement |
| Planetary mode | Protect planet detail | Planet plus moons acquisition compromise | Moon-priority mode with explicit user choice |
| Guided DSO exposure options | Not required | 10 s / 30 s / 60 s | Dithering-aware capture plan |
| Guide-camera auto gain | One-shot before guiding | 5-minute configurable health check | Advanced guide-star quality model |
| Bias/dark/flat preparation buttons | Yes | Yes | Automated calibration planning |
| Master calibration library | Yes | Yes | Automatic SIRIL export/copy |
| Raw calibration subframes | Optional | Optional | Optional advanced retention policies |
| Cooling controller for ATR585M | Yes | Yes | More adaptive cooldown model |
| Prepare SIRIL folder | Not required | Optional | Recommended later |

---

## 3. Definitions

| Term | Meaning |
|---|---|
| Auto Gain | Combined automatic adjustment of gain, exposure, offset/black level, and conversion gain mode where supported. |
| Offset / black level | Camera baseline adjustment used to avoid clipping dark pixels at zero. |
| Conversion gain | Sensor/camera mode such as HCG, LCG, or HDR. |
| Last-good settings | Last successful auto-gain result stored per camera/profile/mode. |
| Master calibration file | Stacked master bias, dark, or flat FITS file. |
| Calibration subframes | Individual raw bias/dark/flat frames used to create a master. |
| Image root | User-configured root directory for lights, videos, and calibration master library. |
| App-state folder | Existing SmartTScope local state folder, e.g. `~/.smarttscope` or `~/.SmartTScope`. |
| Session folder | Target-specific folder below image root, named by date and object. |

---

## 4. Auto-gain functional requirements

### FR-AG-001 - Supported auto-setting modes

SmartTScope shall support these modes:

| Mode | Purpose | Adjustment behavior |
|---|---|---|
| `AUTO_GAIN_PREVIEW` | Main live preview | One-shot in MVP |
| `AUTO_GAIN_RECORDING_START` | Initial values for recording | One-shot |
| `AUTO_GAIN_PLANETARY` | Planetary preview/recording | One-shot in MVP, converging in MVP+ |
| `AUTO_GAIN_DSO_PREVIEW` | DSO live preview without long guided exposure | One-shot, bounded exposure |
| `AUTO_GAIN_DSO_GUIDED` | DSO with active guiding | MVP+ |
| `AUTO_GAIN_GUIDING` | Guide/OAG camera setup | One-shot in MVP |
| `CAL_PREP_BIAS` | Bias preparation | One-shot |
| `CAL_PREP_DARK` | Dark preparation | One-shot |
| `CAL_PREP_FLAT` | Flat preparation | One-shot |

### FR-AG-010 - Per-camera Auto Gain button

Each active camera panel shall provide an **Auto Gain** button.

When pressed, SmartTScope shall:

1. Freeze the current selected camera role and optical profile.
2. Read current camera state: exposure, gain, offset/black level, bit depth, ROI, binning, conversion gain, and temperature if available.
3. Display or activate the raw live histogram.
4. Load last-good settings if available.
5. Load matching calibration statistics if available.
6. Run bounded driver-assisted auto exposure/gain.
7. Validate the result using application-side histogram and target-specific checks.
8. Apply final accepted settings.
9. Store the result as last-good settings.
10. Show final status and warnings.

### FR-AG-020 - Driver-assisted auto setting

The Touptek driver auto-exposure/auto-gain mechanism shall be used where available as the primary starting mechanism.

SmartTScope shall still remain responsible for:

1. Applying camera-profile limits.
2. Setting maximum exposure limits.
3. Selecting initial conversion gain mode.
4. Applying or validating offset/black level.
5. Interpreting the histogram.
6. Detecting no-signal cases.
7. Preventing runaway exposure.
8. Persisting final settings.
9. Reporting status to the user.

### FR-AG-030 - Exposure may be adjusted but must be bounded

Auto Gain shall be allowed to adjust exposure when gain alone is insufficient.

However, SmartTScope shall never keep increasing exposure indefinitely. It shall distinguish these cases:

| Situation | Required behavior |
|---|---|
| Faint but valid image | Increase exposure/gain within configured limits |
| Dust cap on | Stop and report no usable signal / possible dust cap |
| Strong defocus or pointing error | Stop and report possible focus or pointing problem |
| Target too bright | Reduce exposure and/or gain |
| Gain near optimal/unity and signal above 80% | Reduce exposure first |

### FR-AG-040 - Normal and diagnostic exposure limits

For MVP live preview:

| Limit type | Requirement |
|---|---|
| Normal preview exposure limit | 4-5 s |
| Diagnostic exposure limit | 10 s |
| MVP behavior beyond normal limit | Ask user before escalating |
| MVP+ behavior beyond normal limit | May escalate automatically if enabled |

The diagnostic limit is used only to classify conditions such as dust cap, pointing error, or severe defocus. It is not the normal preview target.

Example MVP prompt:

```text
No usable signal detected within normal preview exposure.
Run diagnostic exposure up to 10 seconds at high gain?
This may help distinguish dust cap, pointing error, or severe defocus.
```

### FR-AG-050 - Histogram display

The live histogram shall show the **linear raw intensity distribution**, not the display-stretched image.

For MVP and MVP+, the histogram shall be calculated from the **full frame**.

The histogram shall show:

| Marker / value | Purpose |
|---|---|
| Bias / black level | Show camera baseline |
| Lower clipping marker | Detect clipping at zero |
| 75-80% target marker | Main brightness target |
| Saturation marker | Show full-scale clipping |
| p50 / p95 / p99 / p99.5 / p99.9 | Robust statistics |
| Saturated-pixel percentage | Important for planets and bright stars |
| Exposure / gain / offset / conversion gain | Operator traceability |

A later final-final enhancement may allow linking histogram calculation to an ROI.

### FR-AG-060 - Effective bit-depth normalization

If the camera delivers 12-bit data in a 16-bit container, SmartTScope shall normalize histogram calculations to the effective bit depth.

For RAW12, the nominal white level shall be treated as 4095 unless the driver reports another effective range.

### FR-AG-070 - Offset / black-level handling

SmartTScope shall estimate or load offset/black-level information from bias or dark calibration data.

The offset requirement is:

> The raw dark/bias distribution shall be shifted high enough that the lower noise tail is not clipped at zero, while keeping the offset as low as practical.

Suggested default rules:

| Metric | Default |
|---|---:|
| Bias frames used to create master | 16 minimum, 32 recommended |
| p0.1 bias level | Greater than 0 ADU |
| Clipped zero pixels | Less than 0.01% |
| RAW12 black safety margin | Configurable, e.g. 8-32 ADU |

### FR-AG-080 - Conversion gain policy

MVP shall start with simple conversion gain rules:

| Use case | Initial conversion gain |
|---|---|
| DSO preview | HCG |
| DSO guided | HCG initially; later optimization may choose LCG/HDR |
| Planetary | LCG initially |
| Lunar | LCG initially |
| Guide/OAG | HCG initially |
| Bias/dark | Same as intended light frames |
| Flat | Same as intended light frames |

The algorithm may later override the simple rule if measured histogram and camera profile indicate a better setting.

The camera-specific optimal/unity-gain region shall not be a global number. It shall be part of the camera profile and conversion-gain mode.

### FR-AG-090 - Adjustment order

The auto-gain algorithm shall use this order:

```text
1. Read current camera state.
2. Select initial conversion gain mode from camera/profile rule.
3. Load last-good settings where useful.
4. Estimate/load offset from bias/dark reference.
5. Enable driver-assisted auto exposure/gain within strict bounds.
6. Evaluate full-frame histogram and target-specific object statistics.
7. If the lower end is clipped, correct offset first.
8. If signal is too weak, increase exposure up to the profile limit.
9. If exposure limit is reached, increase gain.
10. If signal is above 80% and gain is near optimal/unity, reduce exposure.
11. If signal is above 80% and exposure is already short enough, reduce gain.
12. Stop when target is reached, limits are reached, or the user cancels.
13. Store final accepted settings.
```

### FR-AG-100 - Status values

Auto Gain shall return one of these statuses:

| Status | Meaning |
|---|---|
| `AUTO_GAIN_OK` | Target reached |
| `AUTO_GAIN_NO_SIGNAL` | No meaningful signal even at high gain and diagnostic exposure |
| `AUTO_GAIN_POSSIBLE_DUST_CAP` | Histogram remains compatible with dark/bias only |
| `AUTO_GAIN_POSSIBLE_FOCUS_OR_POINTING_ERROR` | Weak/non-structured signal at high gain and diagnostic exposure |
| `AUTO_GAIN_EXPOSURE_LIMIT_REACHED` | Signal exists but target cannot be reached within allowed exposure |
| `AUTO_GAIN_GAIN_LIMIT_REACHED` | Signal exists but target cannot be reached within allowed gain |
| `AUTO_GAIN_CLIPPING_RISK` | Target nearly reached but saturation remains too high |
| `AUTO_GAIN_CANCELLED` | User cancelled |
| `AUTO_GAIN_UNSUPPORTED` | Required camera/driver feature unavailable |

---

## 5. Planetary requirements

### FR-PLANET-001 - Planet detail priority

For planetary captures, SmartTScope shall preserve planet detail as the default priority.

The planet disk shall not be overexposed just to make moons visible.

### FR-PLANET-002 - Planet plus moons acquisition compromise

The algorithm shall try to optimize **raw acquisition settings**, not only display stretch, so that:

1. The planet disk remains below saturation.
2. Planet detail is preserved.
3. Moons remain detectable where physically possible.
4. Exposure remains suitable for frame rate where possible.

Allowed actions:

| Action | Allowed |
|---|---|
| Reduce exposure if planet is above 80% | Yes |
| Increase gain if moons are weak and planet remains protected | Yes |
| Increase exposure if FPS requirement still allows it | Yes |
| Overexpose planet to show moons | No by default |
| Use preview stretch to improve moon visibility | Yes |
| Report that moons are not achievable without planet overexposure | Yes |

### FR-PLANET-003 - Planetary modes

| Mode | Requirement |
|---|---|
| `PLANET_PROTECTED` | MVP default. Preserve planet detail. |
| `PLANET_WITH_MOONS` | MVP+. Try to keep moons detectable while still protecting the planet. |
| `MOON_VISIBILITY_PRIORITY` | Later optional mode. May sacrifice planet quality only after explicit user selection. |

### FR-PLANET-004 - Planet statistics source

For planets, the full-frame histogram remains visible, but exposure decisions should use object statistics from the capture software's detected planet/object area.

ROI-linked histogram remains a later enhancement.

---

## 6. DSO and guided DSO requirements

### FR-DSO-001 - DSO live-preview behavior

For DSO live preview without guided long exposure:

| Rule | Requirement |
|---|---|
| Normal exposure limit | 4-5 s |
| Diagnostic max | 10 s only for no-signal/focus/dust-cap classification |
| Target | Robust bright percentile around 75-80% |
| Stars | Some star saturation is acceptable but must be reported |
| Background | Must not be clipped to zero |
| Gain | May increase after exposure reaches limit |

### FR-DSO-002 - Guided DSO exposure options

For guided DSO mode, the user shall be able to select one of these exposure ceilings:

| Option | Use |
|---:|---|
| 10 s | Short guided exposure |
| 30 s | Default guided DSO option |
| 60 s | Longer guided DSO option |

Fine-grained exposure selection is not required initially, because later dithering support should be handled by a capture plan rather than arbitrary exposure tuning.

### FR-DSO-003 - Continuous convergence in MVP+

MVP+ continuous mode shall use damping and hysteresis:

```text
1. Observe several frames.
2. Estimate histogram stability.
3. Adjust exposure/gain in small steps.
4. Wait for the image stream to settle.
5. Stop adjusting when within tolerance.
6. Re-adjust only if brightness drifts outside hysteresis limits.
```

---

## 7. Guide-camera and OAG requirements

### FR-GUIDE-001 - Guide camera auto gain

The GPCMOS02000KPA / IMX290 guide-scope camera shall support auto gain even though it is used only for guiding.

Policy:

| Rule | Requirement |
|---|---|
| Purpose | Find stable guide-star visibility |
| Mode | One-shot setup in MVP |
| Target | Stars detectable without excessive saturation |
| Persistence | Reuse last successful guide settings next session |
| Active guiding | Do not change settings unless monitoring/adjustment is explicitly enabled |
| User editing | Settings may be shown but should not normally require modification |

The 678M used as OAG camera shall follow the same rule.

### FR-GUIDE-002 - MVP+ 5-minute guide monitoring

During active guiding, gain/exposure shall normally remain constant.

In MVP+, SmartTScope may check guide-camera brightness every 5 minutes by default. The interval shall be configurable.

The 5-minute check shall:

1. Inspect recent guide frames.
2. Detect whether guide stars are too weak, overexposed, or lost.
3. Avoid changing settings if guiding remains valid.
4. Apply only small bounded changes if needed.
5. Apply changes between guide exposures, not during an active exposure.
6. Log every change.
7. Prevent oscillation with hysteresis.

Suggested status values:

| Status | Meaning |
|---|---|
| `GUIDE_GAIN_OK` | Guide-star signal is stable |
| `GUIDE_GAIN_STAR_WEAK` | Stars are becoming too weak |
| `GUIDE_GAIN_STAR_SATURATED` | Guide stars are overexposed |
| `GUIDE_GAIN_ADJUSTED` | Small correction applied |
| `GUIDE_GAIN_NO_CHANGE_DURING_GUIDING` | MVP behavior: check disabled |
| `GUIDE_GAIN_DAWN_WARNING` | Brightness drift suggests dawn or sky brightening |

---

## 8. Calibration preparation requirements

### FR-CAL-001 - Calibration buttons

Each relevant camera panel shall provide calibration preparation buttons:

| Button | Applicability |
|---|---|
| Prepare Bias | Main, OAG, guide |
| Prepare Dark | Main, OAG, guide |
| Prepare Flat | Mainly main camera; optional for OAG/guide if needed |
| Store Calibration | All calibration types |

Calibration preparation shall be one-shot only. No continuous adjustment is required.

### FR-CAL-010 - Bias preparation

Bias preparation shall:

1. Select the shortest supported exposure.
2. Use selected or intended gain, offset, bit depth, and conversion gain.
3. Ask the user to cover the camera or scope.
4. Capture the configured number of bias frames.
5. Create a master bias FITS file.
6. Store it in the master calibration library.
7. Update the calibration index.

Bias metadata shall include:

```text
camera_serial
camera_model
gain
offset
bit_depth
conversion_gain
binning
roi_mode
temperature if cooled
created_at
```

Bias frames do not require optical-train metadata.

### FR-CAL-020 - Dark preparation

Dark preparation shall:

1. Use intended light-frame exposure, gain, offset, bit depth, and conversion gain.
2. Ask the user to cover the scope.
3. Capture the configured number of dark frames.
4. Create a master dark FITS file.
5. Store it in the master calibration library.
6. Validate that the histogram is compatible with a dark frame.
7. Update the calibration index.

Dark metadata shall include:

```text
camera_serial
camera_model
exposure_ms
gain
offset
bit_depth
conversion_gain
binning
roi_mode
temperature if cooled
created_at
```

Dark frames do not normally require optical-train metadata.

### FR-CAL-030 - Flat preparation

Flat preparation shall:

1. Use the intended light-frame gain, offset, bit depth, conversion gain, filter, and optical train.
2. Adjust exposure only where possible.
3. Target a flat histogram median of 50% of effective full scale.
4. Accept flats with median in the 40-60% range.
5. Warn for 35-40% or 60-70%.
6. Reject below 35% or above 70% unless user overrides.
7. Reject relevant clipping near black or white.
8. Create a master flat FITS file.
9. Store it in the master calibration library.
10. Update the calibration index.

Flat metadata shall include:

```text
camera_serial
camera_model
optical_train_profile
filter_id
gain
offset
bit_depth
conversion_gain
binning
roi_mode
temperature if cooled
created_at
rotation_known: false
focus_position_known: false
```

### FR-CAL-040 - Rotation and focus responsibility for flats

SmartTScope shall not require rotation or focus position to be known.

Rotation and focus are user responsibility. SmartTScope shall show an informational note:

```text
Flat quality depends on optical train, filter, camera orientation, dust position, and focus.
Rotation and focus are not tracked automatically.
Retake flats if the camera orientation, filter, reducer/barlow setup, or focus position changed significantly.
```

SmartTScope shall not reject a flat only because rotation or focus is unknown.

### FR-CAL-050 - Master-only default

SmartTScope shall store master calibration FITS files by default.

Individual calibration subframes shall be optional.

Default behavior:

1. Capture calibration subframes.
2. Stack them into a master calibration FITS file.
3. Validate the master.
4. Store the master under `image-root/masters/<camera>/...`.
5. Update the calibration index.
6. Discard individual calibration subframes unless raw retention is enabled.

Configuration:

```yaml
calibration:
  subframe_retention: master_only
  options:
    - master_only
    - keep_raw_and_master
    - ask_after_capture
```

### FR-CAL-060 - Calibration matching

SmartTScope shall select the best matching master calibration files before capture, live stacking, or SIRIL preparation.

| Calibration type | Required matching fields |
|---|---|
| Bias | camera serial, camera model, gain, offset, conversion gain, bit depth, binning, ROI, temperature if cooled |
| Dark | all bias fields plus exposure time |
| Flat | all bias fields plus optical train and filter |

Rotation and focus are not machine-checkable and shall be shown as user-responsibility notes.

### FR-CAL-070 - Calibration mismatch handling

If no exact match is available, SmartTScope shall either reject the match or show a warning with the mismatch reason.

Example:

```text
No exact master dark found for:
ATR585M, 30000 ms, gain 316, offset 64, HCG, -10 C.

Closest available:
ATR585M, 30000 ms, gain 316, offset 64, HCG, -5 C.

Use anyway?
```

### FR-CAL-080 - Live stacking calibration

If live stacking is enabled, SmartTScope shall:

1. Locate matching master calibration FITS files under `image-root/masters/`.
2. Load them into memory.
3. Apply master bias/dark subtraction where available.
4. Apply master flat correction where available.
5. Warn if metadata does not match current camera settings.
6. Continue uncalibrated only if the user accepts or a preference allows it.

Suggested statuses:

| Status | Meaning |
|---|---|
| `CALIBRATION_MATCHED` | Matching calibration masters loaded |
| `CALIBRATION_PARTIAL` | Some calibration masters available, some missing |
| `CALIBRATION_MISMATCH` | Existing masters do not match current settings |
| `CALIBRATION_NOT_FOUND` | No suitable master found |
| `CALIBRATION_DISABLED` | User disabled live calibration |

---

## 9. Cooling requirements for ATR585M

### FR-TEMP-001 - Coldest allowed target

SmartTScope shall not set the ATR585M cooling target below:

```text
-10 C
```

| Condition | Behavior |
|---|---|
| User selects -10 C | Allowed |
| User selects warmer than -10 C | Allowed |
| User selects colder than -10 C | Reject or clamp to -10 C |
| Stored profile contains colder value | Clamp to -10 C and warn |

### FR-TEMP-002 - Default target

The default ATR585M cooling target shall be:

```text
-10 C
```

### FR-TEMP-003 - Cooling power policy

Cooling down with temporarily higher power is allowed.

Stable operation shall prefer cooling power in the 70-80% range or below.

Default values:

| Setting | Default |
|---|---:|
| Stable cooling power limit | 75% |
| Warning power threshold | 80% |
| Initial cooldown above 80% | Allowed |
| Target relax step | 1 C |
| Default stabilization timeout | 5 min |
| Configurable stabilization options | 3 / 5 / 10 min |

### FR-TEMP-004 - Stabilization timeout

SmartTScope shall wait for a configurable stabilization timeout before deciding that the camera cannot hold the requested target within the stable power limit.

Default:

```yaml
cooling:
  ATR585M:
    default_target_temperature_c: -10
    minimum_allowed_target_temperature_c: -10
    stable_power_limit_percent: 75
    warning_power_percent: 80
    cooldown_allows_high_power: true
    cooldown_stabilization_timeout_s: 300
    cooldown_stabilization_timeout_min_s: 180
    cooldown_stabilization_timeout_max_s: 600
    target_relax_step_c: 1
    dark_temperature_warning_c: 5
```

### FR-TEMP-005 - Unable to hold -10 C

If the ATR585M cannot reach or hold -10 C with the configured stable cooling-power limit, SmartTScope shall:

1. Warn the user.
2. Stop trying to force -10 C at excessive cooling power.
3. Raise the target temperature stepwise until cooling power falls into the configured stable range.
4. Mark the final stable temperature as the active capture temperature.
5. Suggest recording additional matching master darks and bias frames if no suitable masters exist.

Example warning:

```text
ATR585M cannot hold -10 C within the configured cooling power limit.

Current camera temperature: -6 C
Cooling power: 88%
Configured stable limit: 75%

SmartTScope will relax the target temperature to keep cooling power within the safe operating range.
Please record matching master darks for this temperature if no suitable masters exist.
```

### FR-TEMP-006 - Cooling control fallback

If the Touptek driver supports a direct cooler-power limit, SmartTScope shall use it.

If the driver only supports target temperature control, SmartTScope shall approximate the limit by raising the target temperature until measured cooler power returns to the configured range.

Algorithm:

```text
1. Start with target temperature = -10 C.
2. Allow high power during initial cooldown.
3. Wait until the stabilization timeout expires.
4. If cooler power remains above the configured stable limit:
   a. Raise target temperature by 1 C.
   b. Wait for stabilization.
   c. Repeat until power is within limit.
5. Store final stable temperature in session metadata.
6. Use this temperature for calibration matching.
```

### FR-TEMP-007 - Calibration matching by stable temperature

Calibration matching shall use the actual stable capture temperature, not only the originally requested target.

| Difference between current/stable temperature and master | Behavior |
|---:|---|
| Less than 2 C | Accept without warning |
| 2-5 C | Accept with soft warning / quality note |
| 5 C or more | Clear warning and offer to record additional matching masters |

Bias temperature mismatch may be warned less severely than dark temperature mismatch.

---

## 10. Storage requirements

### FR-STORE-001 - Existing app-state folder

Last-good settings and app-local metadata shall be stored in the existing SmartTScope app-state folder.

Discovery order:

```text
1. Use explicitly configured app state directory, if configured.
2. Else detect existing known SmartTScope app folder.
3. If ~/.SmartTScope exists, use ~/.SmartTScope.
4. Else if ~/.smarttscope exists, use ~/.smarttscope.
5. Else create the project default app folder.
```

The software shall not create a second folder only because of different capitalization.

### FR-STORE-002 - Static YAML shall not store runtime values

Runtime values such as last-good gain, exposure, offset, and calibration choices shall not be stored in the static hardware YAML configuration.

The static YAML shall describe hardware and default optical profiles only.

### FR-STORE-003 - Image-root layout

The image root shall contain:

```text
image-root/
  masters/
  YYYY-MM-DD_TargetName/
```

There shall be no required intermediate `sessions/` folder.

Example:

```text
image-root/
  masters/
  2026-05-05_Pleiades/
  2026-05-05_Jupiter/
```

### FR-STORE-004 - Session folder naming

Session folders shall be named:

```text
YYYY-MM-DD_<sanitized-target-name>/
```

Examples:

```text
2026-05-05_Pleiades/
2026-05-05_Jupiter/
2026-05-05_Moon/
2026-05-05_M42/
```

### FR-STORE-005 - Master calibration library below image root

Reusable master calibration FITS files shall be stored below:

```text
image-root/masters/
```

The master library shall be grouped by physical camera identity:

```text
image-root/
  masters/
    ATR585M_<serial>/
      biases/
      darks/
      flats/
    G3M678M_<serial>/
      biases/
      darks/
      flats/
    GPCMOS02000KPA_<serial>/
      biases/
      darks/
```

### FR-STORE-006 - Detailed master structure

Recommended structure:

```text
masters/
  ATR585M_<serial>/
    biases/
      master_bias_gain316_offset64_hcg_12bit_minus10c.fits

    darks/
      master_dark_10000ms_gain316_offset64_hcg_12bit_minus10c.fits
      master_dark_30000ms_gain316_offset64_hcg_12bit_minus10c.fits
      master_dark_60000ms_gain316_offset64_hcg_12bit_minus10c.fits

    flats/
      C8_native/
        L/
          master_flat_L_gain316_offset64_hcg_12bit_minus10c.fits
      C8_reducer_063/
        L/
          master_flat_L_gain316_offset64_hcg_12bit_minus10c.fits
      C8_barlow_2x/
        L/
          master_flat_L_gain316_offset64_hcg_12bit_minus10c.fits
```

### FR-STORE-007 - Session folder contents

For DSO FITS captures:

```text
image-root/
  2026-05-05_Pleiades/
    lights/
    logs/
    session_metadata.json
```

For planetary captures:

```text
image-root/
  2026-05-05_Jupiter/
    videos/
    lights/
    logs/
    session_metadata.json
```

### FR-STORE-008 - Last-good settings

Last-good settings shall be stored in the app-state folder.

Recommended key fields:

```text
camera_serial
camera_model
camera_role
target_mode
optical_train_profile
filter_id if relevant
bit_depth
conversion_gain
exposure_ms
gain
offset
temperature_c if available
binning
roi_mode
created_at
```

Guide-camera last-good settings shall normally be reused automatically at the next session.

### FR-STORE-009 - Calibration index

SmartTScope shall maintain a user-visible calibration index under:

```text
image-root/masters/calibration_index.json
```

The app-state folder may keep a cache, but the image-root index is authoritative.

Relative paths are preferred where possible because the image root may be copied to a Windows machine.

Example entry:

```json
{
  "type": "master_dark",
  "file": "masters/ATR585M_12345/darks/master_dark_30000ms_gain316_offset64_hcg_12bit_minus10c.fits",
  "camera_model": "ATR585M",
  "camera_serial": "12345",
  "exposure_ms": 30000,
  "gain": 316,
  "offset": 64,
  "conversion_gain": "HCG",
  "bit_depth": 12,
  "temperature_c": -10,
  "binning": "1x1",
  "roi_mode": "full_frame",
  "created_at": "2026-05-05T22:15:00"
}
```

---

## 11. SIRIL compatibility requirements

### FR-SIRIL-001 - Folder names

SmartTScope shall use SIRIL-compatible folder names where relevant:

```text
biases/
darks/
flats/
lights/
```

The master library shall contain `biases/`, `darks/`, and `flats/`.

Session folders shall contain `lights/` for FITS light frames and `videos/` for planetary SER/video recordings.

### FR-SIRIL-002 - Manual copy first

Processing will happen on another machine, likely Windows.

For MVP, SmartTScope only needs to organize the master library so that the user can manually copy matching master files into the SIRIL working folder.

### FR-SIRIL-003 - No symlink dependency

If automatic SIRIL preparation is implemented later, it shall use real file copies, not symbolic links, because processing will happen on Windows.

### FR-SIRIL-004 - Future Prepare SIRIL Folder function

A later `Prepare SIRIL Folder` function may:

1. Select matching master bias/dark/flat files.
2. Copy them into the object session folder.
3. Create `biases/`, `darks/`, and `flats/` folders if missing.
4. Leave `lights/` unchanged.
5. Write `calibration_selection.json`.
6. Use real copies, not symlinks.

Example after preparation:

```text
image-root/
  2026-05-05_Pleiades/
    biases/
      master_bias_gain316_offset64_hcg_12bit_minus10c.fits
    darks/
      master_dark_30000ms_gain316_offset64_hcg_12bit_minus10c.fits
    flats/
      master_flat_L_gain316_offset64_hcg_12bit_minus10c.fits
    lights/
      Pleiades_0001.fits
      Pleiades_0002.fits
    calibration_selection.json
```

---

## 12. UI requirements

### FR-UI-001 - Camera panel controls

Each camera panel shall show:

| Element | Purpose |
|---|---|
| Auto Gain | One-shot auto setting |
| Continuous Auto | MVP+ only |
| Prepare Bias | Calibration setup |
| Prepare Dark | Calibration setup |
| Prepare Flat | Calibration setup |
| Histogram | Full-frame raw histogram |
| Status message | Result or warning |
| Last-good settings | Reuse/persist settings |
| Apply to recording | Copy preview settings to recording plan |

### FR-UI-002 - Safe failure messages

The user shall receive actionable messages:

| Condition | Message style |
|---|---|
| No signal at max gain and diagnostic exposure | Check dust cap, pointing, or focus |
| Very weak signal | Focus or pointing may be far off |
| High saturation | Target is overexposed; exposure reduced |
| Guide camera active | Settings are stable; adjustment blocked or monitored only |
| Missing calibration | Suggest preparing bias/dark/flat |
| Cooling cannot hold target | Warn and relax target temperature |
| Master mismatch | Explain mismatch and offer new master capture |

### FR-UI-003 - Cooling settings

The ATR585M cooling settings UI shall offer:

| Option | Default |
|---|---:|
| Target temperature | -10 C |
| Stable power limit | 75% |
| Warning threshold | 80% |
| Stabilization timeout | 5 min |
| Timeout options | 3 / 5 / 10 min |

The UI shall not offer target temperatures below -10 C for normal operation.

### FR-UI-004 - Guide monitoring interval

MVP+ guide monitoring interval shall be configurable, with 5 minutes as default.

---

## 13. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-001 | Auto Gain shall run asynchronously and shall not block the UI. |
| NFR-002 | The user shall be able to cancel Auto Gain. |
| NFR-003 | If cancelled or failed, SmartTScope shall keep last safe settings or restore previous settings. |
| NFR-004 | Histogram calculation shall be fast enough for live preview; frame skipping is allowed. |
| NFR-005 | All applied settings shall be logged. |
| NFR-006 | The algorithm shall be deterministic for replay/test frames. |
| NFR-007 | The algorithm shall be testable without physical cameras using replay frames. |
| NFR-008 | Unsupported camera features shall degrade gracefully. |
| NFR-009 | Calibration index paths should be relative where possible for portability to Windows. |
| NFR-010 | Storage layout shall avoid symlink dependency. |
| NFR-011 | Camera runtime IDs shall not be treated as stable identities; use serial number or assigned logical name. |
| NFR-012 | Driver feature availability shall be queried dynamically. |

---

## 14. Suggested architecture

```text
ui/
  AutoGainPanel
  HistogramWidget
  CalibrationPanel
  CoolingPanel

domain/
  CameraProfile
  OpticalTrainProfile
  AutoGainPolicy
  AutoGainResult
  HistogramStats
  BiasCalibration
  MasterCalibration
  CoolingPolicy
  SessionProfile

ports/
  CameraControlPort
    get_frame()
    get_exposure()
    set_exposure()
    get_gain()
    set_gain()
    get_black_level()
    set_black_level()
    get_conversion_gain()
    set_conversion_gain()
    get_capabilities()
    get_temperature()
    set_temperature_target()
    get_cooling_power()

services/
  AutoGainService
  HistogramAnalyzer
  BiasCalibrationService
  MasterCalibrationService
  CalibrationIndexService
  CoolingController
  CameraProfileRegistry
  SessionStorageService
  SirilPreparationService

adapters/
  TouptekCameraAdapter
  ReplayCameraAdapter
  FitsStorageAdapter
```

Architectural principle:

> Domain logic shall remain independent from the Touptek SDK. The Touptek adapter shall implement camera control; Auto Gain, calibration matching, cooling policy, and storage rules shall live in application/domain services.

---

## 15. Acceptance criteria

### AC-AG-001 - Show histogram when Auto Gain starts

```gherkin
Given a live camera stream is active
When the user presses "Auto Gain"
Then SmartTScope shall display a raw linear full-frame histogram
And the histogram shall show black level, target level, saturation level, and current gain/exposure/offset
```

### AC-AG-002 - Exposure can increase but must stop

```gherkin
Given Auto Gain is started
When the histogram shows no usable signal
Then SmartTScope may increase exposure and gain up to configured limits
But it shall stop no later than the diagnostic maximum exposure and maximum gain
And it shall report no usable signal, possible dust cap, focus error, or pointing error
```

### AC-AG-003 - Over-bright signal reduces exposure

```gherkin
Given the current histogram shows signal above 80% of full scale
And the current gain is near the camera-specific optimal or unity-gain region
When Auto Gain is executed
Then SmartTScope shall reduce exposure time before reducing gain
And it shall stop when the target signal is within the configured range
```

### AC-AG-004 - MVP one-shot behavior

```gherkin
Given Auto Gain is available in MVP
When the user presses Auto Gain
Then SmartTScope shall perform a bounded one-shot adjustment
And it shall not keep changing gain or exposure after completion
```

### AC-AG-005 - MVP+ continuous behavior

```gherkin
Given MVP+ continuous auto mode is enabled
When live preview brightness drifts outside the configured tolerance
Then SmartTScope shall adjust exposure and/or gain using damping
And it shall stop adjusting once the histogram has converged
```

### AC-AG-006 - MVP diagnostic prompt

```gherkin
Given MVP Auto Gain is running
And no usable signal is detected within the normal preview exposure limit
When diagnostic escalation would exceed the normal preview limit
Then SmartTScope shall ask the user before trying up to 10 seconds
```

### AC-PLANET-001 - Planet with moons

```gherkin
Given planetary mode with moon-aware acquisition is enabled
And the planet and moons are detectable in the frame
When Auto Gain is executed
Then SmartTScope shall select exposure and gain to preserve planet detail
And it shall try to keep moons detectable without exceeding the planet saturation threshold
And it shall report if moon visibility is not achievable without overexposing the planet
```

### AC-DSO-001 - Guided DSO exposure options

```gherkin
Given the user selects DSO guided mode
When the user opens the exposure limit selector
Then the available options shall be 10 s, 30 s, and 60 s
And Auto Gain shall not exceed the selected limit
```

### AC-GUIDE-001 - Do not disturb guiding in MVP

```gherkin
Given the guide-scope camera is actively guiding
When the user executes Auto Gain for the main camera
Then SmartTScope shall not change gain, exposure, offset, or conversion gain of the guide-scope camera
```

### AC-GUIDE-002 - Five-minute guide monitoring in MVP+

```gherkin
Given the guide camera is actively guiding
And MVP+ guide monitoring is enabled
When five minutes have passed since the last guide brightness check
Then SmartTScope shall evaluate recent guide frames
And keep gain and exposure unchanged if guide-star quality is still acceptable
And apply only small bounded corrections if guide-star signal is outside tolerance
```

### AC-CAL-001 - Bias preparation

```gherkin
Given a camera is selected
When the user presses Prepare Bias
Then SmartTScope shall select the shortest supported exposure
And use the selected gain, offset, bit depth, and conversion gain
And prompt the user to cover the camera
And store the resulting master bias FITS file in the master calibration library
```

### AC-CAL-002 - Flat preparation

```gherkin
Given a main camera, optical train, and filter are selected
When the user presses Prepare Flat
Then SmartTScope shall keep gain, offset, bit depth, and conversion gain compatible with the light frames
And adjust exposure until the flat median is near 50% of full scale
And accept flat preparation when the median is between 40% and 60% without clipping
```

### AC-CAL-003 - Master-only default

```gherkin
Given calibration capture is completed
When the master calibration FITS file has been created and validated
Then SmartTScope shall keep the master FITS file
And individual calibration subframes shall be discarded unless raw retention is enabled
```

### AC-CAL-004 - Store masters below image root

```gherkin
Given an image root is configured
When SmartTScope stores a master bias, dark, or flat
Then the master FITS file shall be stored below image-root/masters/
And it shall be grouped by physical camera identity
```

### AC-CAL-005 - Keep object lights separate from reusable masters

```gherkin
Given a target session is active
When light frames are captured
Then SmartTScope shall store the lights in the target session folder
And it shall not duplicate reusable master calibration files into that session by default
```

### AC-CAL-006 - Do not silently mix incompatible masters

```gherkin
Given a matching master calibration file is required
When the available master differs in camera serial, gain, offset, conversion gain, bit depth, binning, ROI, exposure for darks, or optical train/filter for flats
Then SmartTScope shall warn the user
And it shall not silently use the mismatched master
```

### AC-CAL-007 - Live stacking uses master calibration

```gherkin
Given live stacking is enabled
And matching master bias, dark, or flat FITS files exist
When new live frames are received
Then SmartTScope shall load the matching master calibration files into memory
And use them for live calibration before stacking
```

### AC-FLAT-001 - Unknown rotation and focus

```gherkin
Given a master flat is selected
And rotation or focus position is unknown
When SmartTScope validates flat compatibility
Then it shall not reject the flat only because rotation or focus is unknown
And it shall inform the user that flat validity depends on unchanged orientation and focus
```

### AC-TEMP-001 - Do not cool below -10 C

```gherkin
Given the ATR585M is selected
When the user configures cooling
Then SmartTScope shall not allow a cooling target below -10 C
And any colder stored target shall be clamped to -10 C
```

### AC-TEMP-002 - Allow high power during cooldown

```gherkin
Given the ATR585M target temperature is -10 C
When cooling has just started
Then SmartTScope may allow cooler power above 80% during the initial cooldown phase
And it shall continue monitoring whether the target can be held within the configured stable power limit
```

### AC-TEMP-003 - Configurable stabilization timeout

```gherkin
Given the ATR585M target temperature is -10 C
And the cooling stabilization timeout is configured to 5 minutes
When cooling starts
Then SmartTScope may allow cooling power above 80% during the first 5 minutes
And it shall not relax the target temperature before the timeout expires
```

### AC-TEMP-004 - Relax target after timeout

```gherkin
Given the ATR585M target temperature is -10 C
And the cooling stabilization timeout has expired
And cooling power is still above the configured stable limit
When SmartTScope evaluates cooling stability
Then it shall warn the user
And raise the target temperature stepwise until cooling power is within the configured limit
```

### AC-TEMP-005 - Suggest new masters after temperature change

```gherkin
Given SmartTScope relaxed the ATR585M cooling target
And no matching master dark exists for the stable temperature
When the user prepares capture or live stacking
Then SmartTScope shall warn that existing dark masters may not match
And it shall offer to record additional master darks at the current stable temperature
```

### AC-STORE-001 - Use existing app folder

```gherkin
Given the application has an existing local state folder
When Auto Gain stores last-good settings
Then SmartTScope shall use the existing application state folder
And it shall not create a second folder with different capitalization
```

### AC-STORE-002 - Direct image-root session folders

```gherkin
Given an image root is configured
And the user starts a capture session for Pleiades
When SmartTScope creates the session folder
Then it shall create image-root/YYYY-MM-DD_Pleiades/
And it shall not require an intermediate sessions/ folder
```

### AC-SIRIL-001 - Manual SIRIL preparation possible

```gherkin
Given matching master calibration files exist under image-root/masters/
And a session folder contains lights/
When the user wants to process the session in SIRIL
Then the folder names and master file organization shall make it possible to copy matching masters into biases/, darks/, and flats/
```

### AC-SIRIL-002 - Automatic SIRIL preparation uses copies

```gherkin
Given automatic SIRIL preparation is implemented
When the user selects Prepare SIRIL Folder
Then SmartTScope shall copy matching master FITS files into the session's biases, darks, and flats folders
And it shall not rely on symbolic links
```

---

## 16. Suggested implementation order

### Phase 0 - Foundation and capability discovery

Goal: make all later work testable and camera-independent.

1. Extend or define `CameraControlPort` with exposure, gain, black level, conversion gain, bit depth, frame acquisition, temperature, and cooling power methods.
2. Add capability discovery for Touptek cameras.
3. Ensure stable camera identity via serial number or user-assigned logical name.
4. Add `CameraProfile` and `OpticalTrainProfile` domain models.
5. Add replay-camera support for deterministic tests.

Deliverable:

- Camera capabilities can be queried and logged without changing settings.
- Replay frames can be used in tests.

### Phase 1 - Storage model

Goal: establish persistent paths before generating calibration or auto-gain data.

1. Implement app-state folder detection.
2. Implement image-root configuration.
3. Implement direct session folder naming: `image-root/YYYY-MM-DD_Target/`.
4. Implement `image-root/masters/` calibration library structure.
5. Implement calibration index skeleton with relative paths.
6. Implement last-good settings storage in app-state folder.

Deliverable:

- SmartTScope can create image-root, session folder, master folder, and app-state storage without camera hardware.

### Phase 2 - Histogram and frame-statistics service

Goal: create the measurement basis for Auto Gain and calibration validation.

1. Implement `HistogramAnalyzer`.
2. Normalize frames by effective bit depth.
3. Calculate p50, p95, p99, p99.5, p99.9, saturation percentage, clipped-zero percentage.
4. Add hot-pixel/outlier rejection support.
5. Add raw full-frame histogram UI widget.

Deliverable:

- Live or replay frames produce reliable histogram statistics and visual histogram display.

### Phase 3 - Calibration master library

Goal: make bias/dark/flat creation and reuse available before Auto Gain depends on it.

1. Implement Prepare Bias.
2. Implement Prepare Dark.
3. Implement Prepare Flat with 50% median target.
4. Implement master-only default.
5. Add optional raw subframe retention setting.
6. Write master FITS files under `image-root/masters/<camera>/...`.
7. Update `calibration_index.json`.
8. Add calibration matching and mismatch warnings.

Deliverable:

- Master calibration FITS files can be created, indexed, matched, and reused.

### Phase 4 - ATR585M cooling controller

Goal: stabilize temperature handling before dark matching and long exposures.

1. Implement -10 C minimum target clamp.
2. Add cooling target UI/config.
3. Add cooling power monitoring.
4. Allow high power during cooldown.
5. Add configurable stabilization timeout with 5-minute default.
6. Add target relaxation if power remains above stable limit.
7. Use stable temperature for session metadata and dark matching.

Deliverable:

- ATR585M cooling can be controlled safely and produces useful warnings/matching data.

### Phase 5 - MVP one-shot Auto Gain for main camera

Goal: deliver the main user-facing feature.

1. Implement `AutoGainService` one-shot flow.
2. Use driver-assisted auto exposure/gain within application limits.
3. Add conversion gain default rules.
4. Add offset correction from bias/dark statistics.
5. Add normal preview exposure limit of 4-5 s.
6. Add diagnostic prompt up to 10 s.
7. Add status classification.
8. Store last-good settings.
9. Add Apply-to-recording behavior.

Deliverable:

- Main-camera Auto Gain works for live preview and recording start values.

### Phase 6 - Calibration use in live stacking

Goal: use calibration masters during live processing.

1. Select matching calibration masters from index.
2. Load master bias/dark/flat into memory.
3. Apply calibration to live frames before stacking.
4. Warn on missing or mismatched masters.
5. Log selected calibration files in session metadata.

Deliverable:

- Live stacking can use master calibrations created by SmartTScope.

### Phase 7 - Guide and OAG auto gain

Goal: stabilize guide-star acquisition without disturbing guiding.

1. Implement one-shot guide-camera Auto Gain before guiding.
2. Reuse last-good guide settings.
3. Block changes during active guiding in MVP.
4. Add MVP+ 5-minute configurable health check.
5. Add small bounded corrections with hysteresis.

Deliverable:

- Guide and OAG cameras get stable settings with no unintended guiding disruption.

### Phase 8 - Planetary target-specific Auto Gain

Goal: improve planetary capture beyond simple full-frame histogram behavior.

1. Add planet/object statistics from capture software detection.
2. Implement `PLANET_PROTECTED` MVP behavior.
3. Add saturation protection for the planet disk.
4. Add moon visibility reporting.
5. Add MVP+ `PLANET_WITH_MOONS` acquisition compromise.

Deliverable:

- Planetary captures preserve planet detail and attempt moon visibility without overexposing the planet.

### Phase 9 - Guided DSO MVP+

Goal: support longer guided exposures with bounded auto settings.

1. Add guided DSO mode.
2. Add exposure ceiling options: 10, 30, 60 s.
3. Use stable guiding state as precondition.
4. Support longer calibration matching.
5. Prepare for later dithering integration.

Deliverable:

- Guided DSO auto settings can use controlled longer exposures.

### Phase 10 - MVP+ continuous convergence

Goal: move from one-shot to continuous adaptation.

1. Add continuous auto mode switch.
2. Add damping and hysteresis.
3. Add brightness-drift detection.
4. Avoid changes during recordings unless explicitly enabled.
5. Add safety limits and logging.

Deliverable:

- Live preview can keep converging to useful settings without oscillation.

### Phase 11 - SIRIL support improvements

Goal: simplify external Windows processing.

1. Add optional `Prepare SIRIL Folder` button.
2. Copy matching masters into session `biases/`, `darks/`, `flats/` folders.
3. Write `calibration_selection.json`.
4. Optionally generate a SIRIL script later.
5. Never rely on symlinks.

Deliverable:

- Sessions can be prepared for SIRIL processing with minimal manual copying.

---

## 17. Recommended first implementation slice

For a useful MVP without too much risk, implement these first:

1. Capability discovery and camera profiles.
2. App-state and image-root storage.
3. Full-frame histogram analyzer and UI.
4. Master calibration library with master-only default.
5. ATR585M cooling controller.
6. One-shot Auto Gain for main camera.
7. Last-good settings persistence.
8. Basic guide-camera one-shot Auto Gain.

This creates a coherent and testable foundation before adding continuous adjustment, planet-plus-moons optimization, guided DSO, and SIRIL automation.

---

## 18. Source documents considered

The requirements were derived from the conversation and the uploaded camera information:

- `ATR585M_en.pdf`
- `G3M678M.pdf`
- `toupcam.pytxt`
- User-provided IMX290 / GPCMOS02000KPA specifications

