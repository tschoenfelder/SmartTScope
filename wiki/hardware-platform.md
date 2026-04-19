# Hardware Platform

**Summary**: The target hardware for the SmartTelescope application: a Celestron C8 OTA, Raspberry Pi 5 compute unit, and OnStep V4 mount controller.

**Sources**: SmartTelescope.md

**Last updated**: 2026-04-19

---

The SmartTelescope application is built around a specific hardware stack rather than a commercial all-in-one unit like the [[seestar-s50]] or [[vaonis-vespera]]. This gives more flexibility but requires the software to bridge the gap to match the smart telescope experience.

## Components

### Celestron C8
- 8-inch Schmidt-Cassegrain optical tube assembly
- Long focal length (~2032 mm at f/10, ~1280 mm with 0.63× reducer)
- Narrow field of view — makes [[plate-solving]] harder and reacquisition more challenging than wide-field smart telescopes
- Supports focal reducers (0.63×) and Barlows (2×) — optical train awareness required
- Focus quality is critical at this focal length; [[autofocus]] is near-mandatory

### Raspberry Pi 5
- Onboard compute for imaging, stacking, solving, and app serving
- Must maintain thermal and resource stability during concurrent stacking and solving workloads
- Local-first operation — no cloud dependency
- Target platform for all server-side application logic

### OnStep V4 Mount Controller
- Open-source GoTo mount controller
- Must be connected, initialized, unparked, and tracked via app at session start
- Handles slewing, tracking, and mount limits
- Meridian flip detection and execution falls to this layer (Full tier)

## C8-specific challenges

Two constraints elevate certain [[requirements]] compared with wide-field smart telescopes:

1. **Narrow FOV makes plate solving harder** — a wide-field assist camera or staged solve workflow is strongly recommended even if tagged MVP+
2. **Focus quality matters much more** — poor focus is less forgiving at f/10; autofocus should be treated as near-mandatory

These are noted explicitly in the source and influence prioritization in [[requirements]]. (source: SmartTelescope.md)

## Optical train configurations

The software must be aware of which configuration is active:

| Profile | Focal length | FOV | Notes |
|---|---|---|------|
| C8 native | ~2032 mm | Narrow | Default |
| C8 + 0.63× reducer | ~1280 mm | Wider | Good for larger DSO |
| C8 + 2× Barlow | ~4064 mm | Very narrow | Planetary/lunar |

(source: SmartTelescope.md)

## Related pages

- [[smart-telescope]]
- [[requirements]]
- [[plate-solving]]
- [[autofocus]]
- [[live-stacking]]
