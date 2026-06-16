# SmartTScope Recommendation: Handling ToupTek Cameras and Filter Wheels

## Purpose

This document describes a recommended device-ownership and locking strategy for SmartTScope when using ToupTek cameras and a ToupTek electronic filter wheel (EFW).

The goal is to avoid conflicts between SmartTScope, INDI, FireCapture, ToupSky, N.I.N.A., SharpCap, or other software that may try to access the same physical USB device.

The central rule is:

> **The conflict is usually not caused by multiple programs loading the same `.so` or `.dll`. The conflict is caused when multiple programs try to open the same physical USB device at the same time.**

---

## Key Design Principle

SmartTScope should clearly separate:

```text
Device discovery
  -> "I can see this device exists."

Device ownership
  -> "I am allowed to open and control this device."
```

SmartTScope should not automatically open every detected ToupTek device just because it appears during discovery.

---

## Recommended Device States

SmartTScope should track each camera and filter wheel using an explicit runtime state.

| State | Meaning | Typical Action |
|---|---|---|
| `AVAILABLE` | Device is detected and not known to be in use | SmartTScope may open it if configuration allows |
| `OWNED_BY_SMARTTSCOPE` | SmartTScope has opened the device | SmartTScope controls it |
| `OWNED_BY_INDI` | Device is connected through the local INDI server | SmartTScope should interact via INDI, not direct SDK |
| `EXTERNALLY_BUSY` | Device is visible, but opening failed | Do not retry aggressively; probably used by another program |
| `RESERVED_EXTERNAL` | User/config says another application owns it | SmartTScope must not open it |
| `UNKNOWN` | Device status is unclear | Do not perform risky operations automatically |
| `DISABLED` | Device is intentionally ignored | Do not list as usable |

---

## Recommended Ownership Modes

Each device should have an ownership policy in the SmartTScope configuration.

| Ownership Mode | Meaning |
|---|---|
| `smarttscope` | SmartTScope is allowed to open and control the device |
| `indi` | Device is controlled through INDI |
| `external` | Device is reserved for another program |
| `external_allowed` | SmartTScope may use it only if it is not already busy |
| `disabled` | Ignore this device |

---

## Example Configuration

```yaml
devices:
  main_camera:
    type: touptek_camera
    alias: "Main Planetary Camera"
    model_hint: "G3M678M"
    ownership: external_allowed
    external_owner_hint: "FireCapture"

  guide_camera:
    type: touptek_camera
    alias: "Guide Camera"
    model_hint: "GPCMOS02000KPA"
    ownership: smarttscope

  filter_wheel:
    type: touptek_filter_wheel
    alias: "ToupTek EFW"
    ownership: smarttscope

  mount:
    type: indi_mount
    alias: "OnStep"
    ownership: indi
```

For identical cameras, persistent serial numbers should be preferred if the Python wrapper exposes them.

```yaml
devices:
  main_camera:
    type: touptek_camera
    alias: "Main Camera"
    serial_number: "..."
    ownership: smarttscope

  guide_camera:
    type: touptek_camera
    alias: "Guide Camera"
    serial_number: "..."
    ownership: smarttscope
```

Avoid persistent configuration based only on enumeration order:

```yaml
# Avoid this as a long-term configuration strategy
camera_index: 0
```

Enumeration order can change when USB devices are reconnected or when an EFW appears in the same SDK device list.

---

## Recommended Discovery Flow

SmartTScope should perform discovery without claiming ownership.

```text
1. Enumerate ToupTek SDK devices.
2. Read display name, SDK ID, model flags, and serial number if available.
3. Classify each device:
     - camera
     - filter wheel
     - other / unsupported
4. Match devices against configuration.
5. Assign initial state:
     - AVAILABLE
     - RESERVED_EXTERNAL
     - DISABLED
     - UNKNOWN
6. Do not open devices unless their ownership policy permits it.
```

Important:

> **Discovery should not be the same as opening the device.**

---

## Recommended Open Flow

When SmartTScope is allowed to use a device:

```text
1. Check ownership policy.
2. If ownership is `external` or `disabled`, do not open.
3. If ownership is `indi`, use INDI instead of direct SDK.
4. If ownership is `smarttscope` or `external_allowed`, try to open by exact SDK ID or serial number.
5. If opening succeeds:
     state = OWNED_BY_SMARTTSCOPE
6. If opening fails:
     state = EXTERNALLY_BUSY or UNKNOWN
7. Show a clear message in the UI.
```

Example UI message:

```text
Main Camera: externally busy, probably used by FireCapture.
SmartTScope will not access this device.
```

---

## Do Not Auto-Open Every Device

SmartTScope should not use this startup behavior:

```text
enumerate all devices
open every detected ToupTek device
decide later which ones are needed
```

This is risky because:

- it can block FireCapture from accessing the planetary camera
- it can interfere with ToupSky, SharpCap, N.I.N.A., or INDI
- it can accidentally open the filter wheel through the wrong adapter path
- it makes debugging multi-camera issues harder

Preferred behavior:

```text
enumerate devices
classify devices
apply ownership policy
open only devices assigned to SmartTScope
```

---

## Recommended Runtime Behavior

### If a Device Is Owned by SmartTScope

SmartTScope may:

- change camera options
- start/stop acquisition
- read frames
- control cooling, gain, offset, exposure, ROI
- move the filter wheel if the wheel is owned by SmartTScope

SmartTScope must:

- keep one SDK handle per physical device
- close only its own handle
- avoid global shared camera state
- route callbacks/events to the correct adapter instance

---

### If a Device Is Reserved for FireCapture

SmartTScope should:

- show the device as detected but reserved
- avoid opening the device
- avoid probing it repeatedly
- allow the user to release the reservation manually
- still control the mount if configured

Example:

```text
ATR585M: reserved for FireCapture
ToupTek EFW: reserved for FireCapture
OnStep Mount: controlled by SmartTScope via INDI
```

This is useful for planetary capture, where FireCapture owns high-FPS image acquisition while SmartTScope still provides mount control or target assistance.

---

### If a Device Is Externally Busy

If SmartTScope is allowed to use a device but opening fails:

```text
state = EXTERNALLY_BUSY
```

SmartTScope should not continuously retry.

Recommended behavior:

- show a warning
- provide a manual retry button
- optionally retry only after a user action
- do not spam the SDK with repeated open attempts

Example UI action:

```text
[Retry opening camera]
[Reserve for external application]
[Disable this device for this session]
```

---

## Recommended User Interface

SmartTScope should present device ownership clearly.

Example table:

| Device | Type | Status | Owner | Action |
|---|---|---|---|---|
| ATR585M | Camera | Reserved | FireCapture | Release / Ignore |
| G3M678M | Camera | Owned | SmartTScope | Stop / Disconnect |
| ToupTek EFW | Filter wheel | Available | None | Connect |
| OnStep | Mount | Connected | INDI | Control |

Recommended UI labels:

```text
Available
Connected by SmartTScope
Connected through INDI
Reserved for FireCapture
Busy in another application
Disabled
Unknown
```

Avoid vague labels such as:

```text
Error
Not working
Unavailable
```

The user should understand whether the problem is a hardware problem, a driver problem, or simply an ownership decision.

---

## Recommended Operating Modes

### 1. Full Smart Telescope Mode

SmartTScope owns the complete imaging chain.

```text
SmartTScope:
  - main camera
  - filter wheel
  - mount
  - plate solving
  - live stacking
  - target workflow
```

Recommended for:

- DSO imaging
- live stacking
- automated target workflows
- integrated smart telescope operation

Device policy:

```yaml
main_camera:
  ownership: smarttscope

filter_wheel:
  ownership: smarttscope

mount:
  ownership: indi
```

---

### 2. Planetary External Capture Mode

FireCapture owns the high-FPS capture hardware. SmartTScope remains responsible for mount intelligence.

```text
FireCapture:
  - main planetary camera
  - optionally filter wheel

SmartTScope:
  - mount
  - target position support
  - optional guide/aux camera if separate
```

Recommended for:

- Jupiter, Saturn, Mars, Moon
- high-FPS SER/AVI capture
- RGB planetary capture with FireCapture sequencing

Device policy:

```yaml
main_camera:
  ownership: external
  external_owner_hint: "FireCapture"

filter_wheel:
  ownership: external
  external_owner_hint: "FireCapture"

mount:
  ownership: indi
```

This mode is less integrated than Full Smart Telescope Mode, but it avoids camera conflicts and preserves high-FPS capture performance.

---

### 3. Hybrid Safe Mode

SmartTScope owns selected devices and leaves others untouched.

Example:

```text
FireCapture:
  - main camera

SmartTScope:
  - mount
  - guide camera
  - maybe filter wheel
```

Device policy:

```yaml
main_camera:
  ownership: external

guide_camera:
  ownership: smarttscope

filter_wheel:
  ownership: smarttscope_or_external

mount:
  ownership: indi
```

This mode is useful during development and troubleshooting.

---

## Filter Wheel Specific Recommendation

The ToupTek EFW is a separate USB device, but it uses the same SDK family.

SmartTScope should treat it as its own device type:

```text
TouptekFilterWheelAdapter
  -> owns one EFW SDK handle
  -> exposes slot count
  -> exposes current slot
  -> moves to user-facing slot number
```

User-facing filter slots should be 1-based:

```text
Filter slot 1 -> SDK position 0
Filter slot 2 -> SDK position 1
Filter slot 3 -> SDK position 2
```

Recommended behavior:

- expose slots as `1..N`
- hide SDK 0-based positions from the UI
- treat moving/unknown state explicitly
- use a small settling delay after movement
- avoid moving the filter wheel if FireCapture owns the RGB capture sequence

---

## Camera Specific Recommendation

The direct ToupTek camera adapter should follow the object-per-device pattern.

```text
TouptekCameraAdapter instance A
  -> physical camera A
  -> SDK handle A
  -> callback/event routing A
  -> frame buffer/queue A

TouptekCameraAdapter instance B
  -> physical camera B
  -> SDK handle B
  -> callback/event routing B
  -> frame buffer/queue B
```

Avoid:

```text
global current_camera
global active_handle
global last_frame
single shared callback target
single mutable camera object switched between devices
```

These patterns often work with one camera but fail with two.

---

## Direct SDK vs INDI Ownership

SmartTScope may support both direct ToupTek SDK access and INDI access.

Recommended abstraction:

```text
CameraPort
  -> TouptekDirectCameraAdapter
  -> IndiCameraAdapter

FilterWheelPort
  -> TouptekDirectFilterWheelAdapter
  -> IndiFilterWheelAdapter
```

Recommended usage:

| Use Case | Preferred Backend |
|---|---|
| DSO imaging | Direct SDK or INDI |
| High-FPS planetary imaging | Direct SDK or FireCapture |
| Simulator-based tests | INDI |
| Mount control | INDI |
| Filter wheel integrated with SmartTScope | Direct SDK or INDI |
| Broad hardware support | INDI |

Important:

> Do not open the same physical ToupTek camera through both direct SDK and INDI at the same time.

---

## Locking Strategy

SmartTScope cannot reliably query a universal cross-application lock registry for ToupTek devices.

Instead, use a layered strategy:

```text
1. Configuration-level ownership
2. Runtime open test
3. INDI state inspection if using INDI
4. Manual UI override
```

### Configuration-Level Ownership

This is the most important layer.

The user tells SmartTScope which devices it may own.

### Runtime Open Test

If SmartTScope is allowed to open a device and the SDK open call fails, mark the device as externally busy.

### INDI State Inspection

If the device is managed by INDI, use INDI properties as the source of truth.

### Manual Override

The UI should allow the user to:

- reserve device for external application
- release device to SmartTScope
- disable device for this session
- retry opening

---

## Recommended Error Handling

When opening fails, do not show only a generic error.

Better message:

```text
Could not open ATR585M.
The camera may already be used by FireCapture, ToupSky, INDI, or another application.
SmartTScope will mark it as externally busy.
```

For a filter wheel:

```text
Could not open ToupTek EFW.
The wheel may already be used by FireCapture, INDI, or another application.
```

For ambiguous cases:

```text
Device detected but ownership is unknown.
SmartTScope will not open it automatically.
```

---

## Recommended Safety Rules

- Do not auto-open all ToupTek devices.
- Do not use enumeration index as persistent identity.
- Do not assume display name is unique.
- Do not mix camera and filter wheel discovery paths.
- Do not use one SDK handle for multiple cameras.
- Do not use global callback state.
- Do not close a device from inside the SDK callback.
- Do not repeatedly retry opening an externally busy device.
- Do not control the filter wheel from SmartTScope while FireCapture is running an RGB sequence.
- Do not start the INDI ToupTek camera driver if FireCapture should own the same camera.

---

## Recommended Implementation Checklist

### Discovery

- [ ] Enumerate ToupTek devices without opening them.
- [ ] Capture SDK ID, display name, flags, model, and serial number if available.
- [ ] Classify cameras and filter wheels separately.
- [ ] Match devices against configuration.
- [ ] Assign initial ownership state.

### Camera Adapter

- [ ] One adapter instance per physical camera.
- [ ] One SDK handle per adapter.
- [ ] Open by exact SDK ID or serial number.
- [ ] No global active camera state.
- [ ] Callback/event routing belongs to the adapter instance.
- [ ] Stop/close affects only that handle.

### Filter Wheel Adapter

- [ ] One adapter instance per physical EFW.
- [ ] User-facing slots are 1-based.
- [ ] SDK positions are converted internally.
- [ ] Moving/unknown state is represented explicitly.
- [ ] Settling delay is configurable.

### UI

- [ ] Show detected devices.
- [ ] Show owner/status.
- [ ] Allow reserve/release/retry/disable actions.
- [ ] Clearly distinguish hardware errors from external ownership.
- [ ] Avoid automatic risky open attempts.

### INDI Integration

- [ ] Do not start INDI ToupTek camera driver if another program owns the same camera.
- [ ] Use INDI for mount control.
- [ ] Use INDI simulators for tests.
- [ ] Use INDI state as source of truth for INDI-owned devices.

---

## Recommended Default for SmartTScope

For the first robust implementation, use this default policy:

```text
Mount:
  controlled through INDI

Main camera:
  owned by SmartTScope in Full Smart Telescope Mode
  reserved external in Planetary External Capture Mode

Filter wheel:
  owned by SmartTScope in Full Smart Telescope Mode
  reserved external if FireCapture runs RGB capture

Guide/aux camera:
  owned by SmartTScope if physically separate
```

This keeps SmartTScope flexible:

- full integration for DSO and smart telescope workflows
- safe cooperation with FireCapture for high-FPS planetary workflows
- no accidental device conflicts
- clear path toward simulator-based testing through INDI

---

## Summary

SmartTScope should not try to solve ToupTek ownership purely by automatic locking. A better design is an explicit ownership model.

The recommended strategy is:

> **Discover all devices, classify them, apply a user/config ownership policy, and only open devices assigned to SmartTScope. If opening fails, mark the device as externally busy instead of retrying aggressively.**

This keeps SmartTScope usable both as a full smart telescope application and as a coordinated mount/control layer when a specialized external tool such as FireCapture owns the planetary camera.
