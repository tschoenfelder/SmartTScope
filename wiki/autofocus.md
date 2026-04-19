# Autofocus

**Summary**: Autofocus is the automated process of finding and maintaining the optimal focus position during an observing session, using star-size metrics to drive a motorized focuser.

**Sources**: SmartTelescope.md

**Last updated**: 2026-04-19

---

Focus quality is a prerequisite for everything else in an imaging session. At the focal length of the [[hardware-platform]] (C8 at f/10, ~2032 mm), the system is less forgiving of focus errors than wide-field smart telescopes — making autofocus near-mandatory even when formally tagged at a higher level.

## Role in smart telescopes

A product labeled "smart telescope" is strongly expected to support automated focusing. Manual-only focus assistance is acceptable for a prototype but not for a shipped product. (source: SmartTelescope.md)

## Requirements for the C8 + Pi 5 build

| Feature | Tag |
|---|---|
| Focus aid (live FWHM/HFR or Bahtinov feedback) | MVP |
| Electronic autofocus with star-size metric and backlash handling | MVP+ |
| Refocus triggers (temp drift, filter change, altitude, elapsed time) | Full |
| Optical train awareness (pixel scale changes per reducer/Barlow) | MVP+ |

(source: SmartTelescope.md)

Despite the MVP+ tag, the source explicitly elevates autofocus to near-mandatory for the C8:

> "For a C8, two things move up in importance: plate solving/reacquisition are harder, and focus quality matters much more because the system is less forgiving."

## Focus metrics

Common approaches for automated focus quality measurement:
- **FWHM** (Full Width at Half Maximum) — measures star size in pixels
- **HFR** (Half-Flux Radius) — similar, used by many open-source tools
- **Bahtinov mask analysis** — diffraction pattern-based, high precision, usually manual-assisted

A motorized focuser is required to run a fully automated focus routine. Without one, only assisted (not automated) focus is possible.

## Refocus triggers (Full tier)

Even after a good initial focus, these events should prompt a refocus:
- Temperature change (thermal expansion shifts focus)
- Filter change (different wavelengths focus at slightly different positions)
- Altitude change (flexure)
- Elapsed time threshold

## Related pages

- [[hardware-platform]]
- [[requirements]]
- [[plate-solving]]
- [[live-stacking]]
- [[smart-telescope]]
