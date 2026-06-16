# INDI/ToupTek Steering Pattern

## Purpose

This document summarizes the architectural pattern used by the INDI ToupTek/ToupBase driver family to operate multiple ToupTek cameras and filter wheels in parallel. The goal is not to reproduce INDI code, but to extract the design guideline for a Python adapter using `toupcam.py` / `touptec.py`.

The central idea is:

> **Do not switch one SDK object between devices. Create one driver/adapter instance per physical device, keep one SDK handle per instance, and route callbacks/events back to that instance.**

---

## Core Pattern

```text
EnumV2 / EnumerateV2
  -> identify all physical ToupTek devices
  -> classify by SDK flags: camera, filter wheel, focuser, etc.
  -> create one driver object per physical device
  -> open each device by its exact enumerated ID
  -> store one SDK handle per object
  -> start one callback/event stream per object
  -> never reuse one open handle to switch between devices
```

---

## What INDI Does Conceptually

### 1. Enumerate Devices First

INDI starts with SDK enumeration, typically through the SDK's `EnumV2`-style call.

The enumeration result is treated as the authoritative list of currently connected devices. Each device record contains:

- display name
- SDK device ID
- model information
- SDK flags
- device type information, indirectly through flags

The SDK ID is used for opening the currently enumerated device. However, it should not be treated as a stable long-term hardware identifier, because SDK IDs may change after reconnects or system restarts.

---

### 2. Classify Devices by Flags

ToupTek SDK devices are not all cameras. The same SDK family may expose:

- cameras
- filter wheels
- focusers
- other OEM devices

INDI separates these by checking SDK flags.

For the camera driver path, devices flagged as filter wheels or focusers are ignored. The filter wheel driver separately selects devices with the filter-wheel flag.

Guideline for SmartTScope / Python:

- Keep **camera discovery** separate from **filter wheel discovery**.
- Do not try to open a filter wheel through the camera adapter.
- Do not try to open a camera through the filter wheel adapter.
- Store each device category in a separate logical registry.

---

### 3. Open by Exact Enumerated Device ID

INDI does not rely on “first camera”, “second camera”, or implicit SDK defaults.

Instead, each driver object receives the specific device identity from enumeration and opens that exact device.

Guideline:

- Avoid `Open(None)` in multi-camera setups.
- Avoid relying on list index as a persistent identity.
- Avoid “open first matching device” except for quick diagnostics.
- Prefer opening by the exact ID returned by the most recent enumeration.
- If available, use a persistent serial number for configuration-level binding.

Recommended distinction:

| Identifier | Use |
|---|---|
| Enumeration index | Only for temporary UI selection |
| SDK device ID | Good for opening the device during the current run |
| Serial number | Best for persistent configuration |
| Display name | Good for UI, not sufficient for reliable identification |

---

### 4. One SDK Handle per Physical Device

INDI's effective model is:

```text
Camera 1 -> Driver object 1 -> SDK handle 1
Camera 2 -> Driver object 2 -> SDK handle 2
Wheel 1  -> Driver object 3 -> SDK handle 3
```

It does **not** use one global SDK handle and switch it between devices.

Guideline for Python:

Each `TouptekCameraAdapter` should own:

- its own SDK handle
- its own camera identity
- its own acquisition state
- its own buffers
- its own callback/event routing
- its own lifecycle state: opened, streaming, stopped, closed

Each `TouptekFilterWheelAdapter` should also own its own SDK handle and lifecycle.

---

### 5. Route Callbacks to the Correct Instance

INDI uses a device-object-oriented callback pattern. In C++, the SDK callback receives a context pointer such as `this`, so the callback can dispatch the event back to the correct driver object.

Python should follow the same idea.

Avoid callback designs that depend on module-global state such as:

```text
current_camera
current_handle
active_camera
last_frame
shared_frame_buffer
```

These designs often work with one camera but fail with two cameras.

Preferred Python concept:

```text
SDK callback/event
  -> bound adapter instance
  -> adapter-specific queue/buffer/event
  -> camera worker / processor
```

The callback should not need to know which device is globally active. It should already belong to the correct adapter instance.

---

### 6. Do Not Perform Heavy Operations Inside SDK Callbacks

The ToupTek SDK documentation warns against certain operations from inside callbacks, especially operations such as:

- closing the device
- stopping acquisition
- changing some options
- performing blocking operations

Reason:

- risk of deadlock
- wrong-thread errors
- resource conflicts
- unstable behavior with multiple devices

Guideline:

Use callbacks only to signal that something happened.

Example event flow:

```text
SDK callback reports "image available"
  -> adapter stores/queues event
  -> worker thread pulls image from SDK
  -> processor handles conversion/stacking/display
```

Do not close or reconfigure the camera directly from inside the SDK callback.

---

### 7. Stop and Close Per Handle

When disconnecting one device, only that device's handle should be stopped and closed.

Correct concept:

```text
stop camera A acquisition
close camera A handle
camera B continues running
```

Incorrect concept:

```text
close shared/global SDK state
reset global camera object
invalidate callback used by all cameras
```

Guideline:

- Stop acquisition before closing.
- Ensure callbacks/events are no longer processed after close.
- Do not tear down shared discovery state if other devices are still active.
- Make disconnect idempotent: calling disconnect twice should not crash.

---

## Filter Wheel Pattern

ToupTek filter wheels are controlled through the same SDK family, but they should be treated as separate logical devices.

Important options:

| SDK option | Meaning |
|---|---|
| `TOUPCAM_OPTION_FILTERWHEEL_SLOT = 0x48` | Number of wheel slots |
| `TOUPCAM_OPTION_FILTERWHEEL_POSITION = 0x49` | Current/target position |

Important behavior:

- SDK filter positions are usually **0-based**.
- User-facing filter slots should be **1-based**.
- A position value of `-1` can indicate moving or reset/homing behavior, depending on whether the option is read or written.
- A small settling delay after motion is useful before starting the next exposure.

Recommended abstraction:

```text
Physical slot 1 -> SDK position 0
Physical slot 2 -> SDK position 1
Physical slot 3 -> SDK position 2
...
```

Guideline:

- Expose 1-based slots in UI and configuration.
- Convert internally to 0-based SDK positions.
- Treat `-1` as moving/unknown when reading.
- Do not expose SDK raw positions directly to the user.

---

## Practical Guideline for SmartTScope

### Recommended Object Model

```text
DeviceDiscoveryService
  -> enumerates SDK devices
  -> classifies devices
  -> returns immutable device descriptors

TouptekCameraAdapter
  -> owns one camera descriptor
  -> owns one SDK handle
  -> owns acquisition state
  -> owns callback routing
  -> exposes camera operations

TouptekFilterWheelAdapter
  -> owns one wheel descriptor
  -> owns one SDK handle
  -> exposes slot count, current slot, move-to-slot

CameraWorker
  -> runs acquisition workflow for one camera
  -> receives events from exactly one camera adapter

CameraProcessor
  -> processes frames from one camera stream
```

---

### Recommended Device Descriptor

A useful internal descriptor should contain:

- display name
- SDK ID from current enumeration
- serial number, if available
- model name
- SDK flags
- detected device type
- optional user alias, for example `Main Camera`, `Guide Camera`, `Filter Wheel`

Example conceptual descriptor:

```text
TouptekDeviceDescriptor
  display_name: "G3M678M"
  sdk_id: "... current enumeration ID ..."
  serial_number: "... persistent if available ..."
  device_type: CAMERA
  flags: ...
  user_alias: "Guide Camera"
```

---

### Recommended Configuration Binding

For persistent configuration, prefer:

1. serial number, if available
2. model + serial number
3. user alias mapped to serial number
4. SDK ID only as fallback for the current run

Avoid persistent configuration like:

```yaml
camera_index: 0
```

Prefer configuration like:

```yaml
cameras:
  main:
    serial_number: "..."
    alias: "Main Camera"

  guide:
    serial_number: "..."
    alias: "Guide Camera"
```

If serial numbers are not exposed by the Python wrapper, a weaker but still usable approach is:

```yaml
cameras:
  main:
    model: "ATR585M"
    preferred_display_name: "Main Camera"

  guide:
    model: "G3M678M"
    preferred_display_name: "Guide Camera"
```

This is less robust when two identical cameras are connected.

---

## Likely Cause of “One Camera Works, Switching Fails”

If one camera works but switching to another fails, likely causes are:

### 1. Shared Global Handle

A single global handle is reused for both cameras.

Symptom:

- first camera opens correctly
- second camera fails or gets frames from the wrong camera
- closing one camera breaks the other

Guideline:

- one handle per camera instance

---

### 2. Callback Uses Global State

The callback writes to a global frame buffer or assumes one active camera.

Symptom:

- callbacks arrive but are assigned to the wrong camera
- second camera overwrites first camera state
- frames appear to freeze or mix

Guideline:

- callback must dispatch to the owning adapter instance

---

### 3. Opening by Index Instead of ID

The software assumes camera 0 or camera 1 remains stable.

Symptom:

- works after clean boot
- fails after reconnect
- fails when a filter wheel or other ToupTek device is connected
- opens the wrong device

Guideline:

- enumerate first
- open by current SDK ID or persistent serial number

---

### 4. Closing/Reconfiguring from Callback Thread

The software stops, closes, or changes options from inside the callback.

Symptom:

- deadlock
- wrong-thread error
- device busy/resource conflict
- unstable behavior with two devices

Guideline:

- callback only signals
- worker thread performs stop/close/configuration

---

### 5. Camera and Filter Wheel Mixed in One Discovery Path

The device list contains both cameras and filter wheels.

Symptom:

- software attempts to open the wheel as a camera
- device indices shift
- second camera appears missing
- wrong device gets selected

Guideline:

- classify by flags
- keep camera and wheel registries separate

---

## Recommended Lifecycle

### Camera Open

```text
enumerate devices
select camera descriptor
create camera adapter
open SDK handle for descriptor ID
initialize options
register callback/event handling
start acquisition only when requested
```

### Camera Acquisition

```text
start pull-mode/event-mode acquisition
callback signals frame availability
worker pulls frame
processor converts/stretches/stacks/displays frame
```

### Camera Stop

```text
request acquisition stop
wait until worker is idle
stop SDK acquisition
disable callback/event processing
keep handle open if camera remains connected
```

### Camera Close

```text
stop acquisition if still running
close this camera's SDK handle
mark adapter closed
do not affect other adapters
```

---

## Recommended Threading Rule

A safe mental model is:

```text
SDK callback thread:
  signal only

Camera worker thread:
  pull image
  handle exposure workflow
  coordinate stop/start

UI thread:
  request actions
  display state
  never block on long SDK calls
```

This fits well with SmartTScope's existing worker/processor architecture.

---

## Design Checklist

Before implementing or refactoring the Python adapter, check:

- [ ] Is there exactly one adapter instance per physical camera?
- [ ] Does each adapter own exactly one SDK handle?
- [ ] Is the device opened by enumerated SDK ID or serial number?
- [ ] Are camera, filter wheel, and focuser devices classified separately?
- [ ] Are callbacks routed to the owning adapter instance?
- [ ] Are there no module-global `current_camera` or `last_frame` variables?
- [ ] Does the callback avoid stop/close/reconfigure operations?
- [ ] Is stop/close performed per handle?
- [ ] Can one camera be closed while another continues running?
- [ ] Are filter wheel slots exposed as 1-based in the UI?
- [ ] Are SDK 0-based wheel positions hidden internally?
- [ ] Is disconnect idempotent?
- [ ] Is a small settling delay used after filter wheel movement?
- [ ] Does the UI show clear names such as `ATR585M`, `G3M678M (1)`, `G3M678M (2)`, or user aliases?

---

## Summary

The INDI/ToupTek approach is not based on switching one active SDK object between devices. It is based on a persistent object-per-device model.

For SmartTScope, the main guideline is:

> **Create one adapter object per physical ToupTek device, open each by exact enumerated identity, keep one SDK handle per adapter, and route callbacks/events back to that adapter instance.**

This pattern should be used for both cameras and filter wheels, while keeping their discovery and runtime control paths separate.
