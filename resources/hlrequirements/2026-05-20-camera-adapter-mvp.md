# Camera Adapter MVP Tasklist

Goal: make SmartTScope own three ToupTek cameras concurrently through a stable
adapter boundary, defaulting to the native SDK and allowing a global INDI switch
later.

## Decisions

- Native is the default backend.
- INDI is a global MVP switch, not mixed with native in the same run.
- Role names map to physical cameras by model/name, not SDK index.
- Existing `CameraPort.capture()` and `FitsFrame` stay stable.
- Each physical camera gets its own worker/lock; no global camera lock.
- Streaming consumers use a latest-frame mailbox. New frames replace stale
  uncollected frames.

## Implementation Tasks

- [x] Scan current camera, cooler, runtime, and config surfaces.
- [x] Add richer camera role config while preserving old SDK-index config.
- [x] Add a latest-frame managed camera worker for guide/preview producers.
- [x] Add role-based runtime camera construction.
- [x] Add a headless Raspberry Pi load-test CLI module.
- [ ] Port the full proven CameraTest native capture engine into SmartTScope.
- [ ] Add a production INDI backend behind the same `CameraPort` contract.
- [ ] Wire guide/autoguiding loops to latest-frame mailboxes.
- [ ] Run native three-camera load tests on Raspberry Pi 5 / Trixie 64.

## Maintained API Examples

See `docs/camera-runtime-api-examples.md` for curl examples covering cooling,
filter wheel selection, guide monitor streaming, and the headless Pi load test.

## Related Guiding Work

See `docs/tasklists/2026-05-21-metaguide-inspired-guiding.md` for the
MetaGuide-inspired fast-guiding tasklist. That plan builds on this camera
adapter work by using the role-based native cameras, latest-frame mailbox, and
headless Raspberry Pi load tests as the foundation for low-latency guiding.

## Hardware Defaults From CameraTest

- `ATR585M`: native `indi-stream-trigger`, `setup_profile=indi`, offset 150.
- `G3M678M`: native `indi-stream-trigger`, `setup_profile=indi`, startup delay
  40 s, offset 150.
- `GPCMOS02000KPA`: native `snap`, offset 10.
