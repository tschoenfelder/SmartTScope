# Live Stacking

**Summary**: Live stacking is the process of continuously aligning and co-adding incoming sub-frames to progressively improve a displayed image in real time — one of the defining computational imaging features of smart telescopes.

**Sources**: SmartTelescope.md

**Last updated**: 2026-04-19

---

Live stacking separates a smart telescope from a camera-on-a-mount setup. Rather than presenting a single raw frame, the system integrates each new exposure into a growing stack, improving signal-to-noise and revealing faint detail live, on the user's phone or tablet.

## Role in smart telescopes

Computational imaging — of which live stacking is the core technique — is one of the seven defining traits of the [[smart-telescope]] category. Both [[seestar-s50]] and [[vaonis-vespera]] use live stacking as their primary deep-sky observing mode. (source: SmartTelescope.md)

## Role in the C8 + Pi 5 build

Live stacking for deep-sky objects is tagged **MVP** in [[requirements]] — it is non-negotiable. The [[hardware-platform]] (Raspberry Pi 5) must handle concurrent stacking and solving workloads stably.

Related imaging requirements:

| Feature | Tag |
|---|---|
| Live view with stretch/histogram | MVP |
| Live stacking for DSO | MVP |
| Automatic stretch/color balance | MVP |
| Frame quality rejection | MVP+ |
| Dark-frame / bad-pixel calibration | MVP+ |
| Planetary/lunar lucky-imaging mode | MVP+ |
| Mosaic mode | Full |

(source: SmartTelescope.md)

## Frame rejection

Not all sub-frames are worth stacking. Frames affected by poor tracking, clouds, vibration, or bad star shapes should be rejected automatically. This is tagged **MVP+** and becomes more important at the C8's long focal length where tracking errors are amplified.

## Planetary mode distinction

Planetary and lunar imaging uses a different workflow ("lucky imaging" — selecting the sharpest frames from a high-frame-rate video). This is a separate mode from deep-sky live stacking and is tagged **MVP+** for the C8 build, where planetary targets are a natural use case. (source: SmartTelescope.md)

## Related pages

- [[smart-telescope]]
- [[hardware-platform]]
- [[requirements]]
- [[plate-solving]]
- [[autofocus]]
