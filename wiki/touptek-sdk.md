# ToupTek SDK

**Summary**: The official Touptek Python SDK (`toupcam.py`) is a ctypes thin wrapper over a native shared library, providing camera enumeration, software-trigger RAW capture, TEC cooling control, and filter wheel support.

**Sources**: resources/touptek/toupcam.py, resources/touptek/samples/simplest.py

**Last updated**: 2026-04-23

---

## Architecture

`toupcam.py` does not contain any camera logic — it is a pure ctypes binding to:
- `toupcam.dll` on Windows
- `libtoupcam.so` on Linux (including Raspberry Pi ARM)
- `libtoupcam.dylib` on macOS

The native library is loaded from the directory of `toupcam.py` first, then from the system path. For the Raspberry Pi 5 deployment, the ARM64 `libtoupcam.so` must be placed alongside `toupcam.py`. The Python file alone is inert without it.

Version used: 59.29030.20250722

## Camera identity: SN vs camId

The SDK distinguishes two identifiers:

| Field | Stability | Use |
|---|---|---|
| `id` (camId) | Changes on reconnect or reboot | Pass to `Toupcam.Open(id)` |
| Serial Number (SN) | Permanent, fixed in hardware | Reference only, not used for Open |

Always call `Toupcam.EnumV2()` to obtain the current `id`, then open by that id. Do not cache camId across sessions.

## Image acquisition model

The SDK uses a **callback-driven pull model**:

1. `StartPullModeWithCallback(fun, ctx)` — registers a callback and starts the camera streaming or waiting.
2. The native library fires `fun(nEvent, ctx)` from an **internal native thread** when a frame is ready.
3. On `TOUPCAM_EVENT_IMAGE`, the handler calls `PullImageV4(buf, bStill, bits, rowPitch, pInfo)` to copy the frame into a pre-allocated buffer.

The callback must be fast and non-blocking; all heavy work should be done in the calling thread after signalling via `threading.Event`.

## Trigger modes

Set via `TOUPCAM_OPTION_TRIGGER`:

| Value | Mode |
|---|---|
| 0 | Continuous video streaming (default) |
| 1 | Software trigger — `Trigger(n)` fires n frames |
| 2 | External hardware trigger |

For controlled astronomy exposures, use mode 1 (software trigger) and call `Trigger(1)` once per capture.

## RAW mode and bit depth

Two options must both be set for unprocessed 16-bit sensor data:

```
TOUPCAM_OPTION_RAW = 1       # deliver raw Bayer data, bypass ISP
TOUPCAM_OPTION_BITDEPTH = 1  # 16-bit depth (vs 8-bit default)
```

In RAW mode, the `bits` parameter to `PullImageV4` is ignored. The row pitch for 16-bit RAW is `width * 2` bytes (use `rowPitch=-1` for explicit zero padding). Buffer size: `width * height * 2` bytes.

## Exposure control

- `put_ExpoTime(microseconds)` — sets exposure duration; unit is **microseconds**
- `put_AutoExpoEnable(False)` — must be called to disable auto-exposure before manual control
- `get_ExpoTime()` / `get_RealExpoTime()` — read commanded and actual values
- Exposure range: `get_ExpTimeRange()` returns `(min, max, default)` in microseconds

## TEC cooling

Relevant for long-exposure astrophotography to reduce thermal noise:

- `TOUPCAM_OPTION_TEC` → 0 = off, 1 = on
- `TOUPCAM_OPTION_TECTARGET` → target temperature in 0.1°C units (e.g. −50 = −5.0°C)
- `get_Temperature()` → current sensor temperature in 0.1°C units
- Fan speed: `TOUPCAM_OPTION_FAN` → 0 = off, 1–max = speed, −1 = default

The SDK also supports reading chamber humidity/temperature (`TOUPCAM_OPTION_CHAMBER_HT`) and environment conditions (`TOUPCAM_OPTION_ENV_HT`).

## Built-in correction pipeline

The library has built-in dark/flat/noise correction, distinct from our own pipeline:

| Correction | SDK name | Notes |
|---|---|---|
| Flat field | FFC | `FfcOnce()`, `FfcImport()`, `TOUPCAM_OPTION_FFC` |
| Dark frame | DFC | `DfcOnce()`, `DfcImport()`, `TOUPCAM_OPTION_DFC` |
| Fixed pattern noise | FPNC | `FpncOnce()`, `TOUPCAM_OPTION_FPNC` |

These are applied by the native library before the frame reaches our Python code. When `TOUPCAM_OPTION_RAW = -1` (negative one), FFC/DFC/FPNC and black balance are applied even in RAW mode. With `TOUPCAM_OPTION_RAW = 1`, they are **not** applied — raw Bayer values pass through unchanged.

Since our stacking pipeline handles calibration frame subtraction, keep `TOUPCAM_OPTION_RAW = 1` (bypass SDK corrections) and manage calibration ourselves.

## Filter wheel

If the camera has an integrated filter wheel:

- `TOUPCAM_OPTION_FILTERWHEEL_SLOT` — number of slots
- `TOUPCAM_OPTION_FILTERWHEEL_POSITION` — move to slot (0-based); set to −1 to calibrate; get returns −1 while moving

## Binning

`TOUPCAM_OPTION_BINNING` supports n×n modes (2×2 through 8×8) with three methods:
- Saturating add (default): `0x0n`
- Unsaturated add (RAW only, increases bit depth): `0x40 | n`
- Average (preserves bit depth): `0x80 | n`

Useful for switching between full-resolution capture and faster preview modes.

## HotPlug

`Toupcam.HotPlug(fun, ctx)` registers a callback for USB connect/disconnect events. Useful for production use where the camera may be plugged in after application start.

## Event constants relevant to astronomy

| Constant | Value | Meaning |
|---|---|---|
| `TOUPCAM_EVENT_IMAGE` | 0x0004 | Live frame ready — call PullImageV4 |
| `TOUPCAM_EVENT_STILLIMAGE` | 0x0005 | Snap frame ready |
| `TOUPCAM_EVENT_ERROR` | 0x0080 | Generic camera error |
| `TOUPCAM_EVENT_DISCONNECTED` | 0x0081 | Camera unplugged |
| `TOUPCAM_EVENT_NOFRAMETIMEOUT` | 0x0082 | No frame received within timeout |
| `TOUPCAM_EVENT_EXPO_START` | 0x4000 | Hardware: exposure started |
| `TOUPCAM_EVENT_EXPO_STOP` | 0x4001 | Hardware: exposure ended |

## Implementation in this project

`ToupcamCamera` in `smart_telescope/adapters/touptek/camera.py` wraps the SDK into the `CameraPort` interface:
- Imports `toupcam` lazily in `connect()` so the adapter can be imported without the SDK installed
- Uses `threading.Event` to bridge the native callback thread to the blocking `capture()` call
- Sets RAW-16 + software trigger on connect; issues one `Trigger(1)` per `capture()` call
- Converts the raw uint16 Bayer buffer to a float32 `FitsFrame` with a minimal FITS header

## Related pages

- [[hardware-platform]]
- [[requirements]]
- [[live-stacking]]
- [[autofocus]]
