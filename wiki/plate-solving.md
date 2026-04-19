# Plate Solving

**Summary**: Plate solving is the process of determining exactly where the telescope is pointing by matching star patterns in a captured image against a star catalog — a core enabler of autonomous alignment in smart telescopes.

**Sources**: SmartTelescope.md

**Last updated**: 2026-04-19

---

Plate solving replaces classical manual star alignment. The system captures an image of the sky, identifies star patterns, and matches them against a catalog to determine the telescope's precise pointing coordinates. The mount is then synchronized to this solution.

## Role in smart telescopes

Autonomous alignment via plate solving is one of the defining traits of the [[smart-telescope]] category. Without it, a device cannot qualify as truly self-aligning. Both the [[seestar-s50]] and [[vaonis-vespera]] use this approach. (source: SmartTelescope.md)

## Role in the C8 + Pi 5 build

Plate solving is tagged **MVP** in the [[requirements]] — it is non-negotiable for the "smart telescope" label. However, the [[hardware-platform]] introduces specific challenges:

- The C8's narrow field of view makes initial solving harder — fewer stars per frame, and small pointing errors can put the target completely outside the FOV
- Recovery from poor initial pointing is explicitly called out as **MVP+**
- A wide-field assist camera or staged "solve wide → solve narrow" workflow is recommended and treated as near-mandatory for the C8 despite its MVP+ tag

(source: SmartTelescope.md)

## Workflow

1. Capture an image with the main or assist camera
2. Extract star positions
3. Match against catalog (e.g. index files for astrometry.net or similar)
4. Compute RA/Dec of image center and rotation
5. Sync mount to solution
6. Repeat after GoTo slew to verify and recenter

Periodic solve-and-correct during long sessions ([[requirements]] §6) keeps drift under control.

## Related pages

- [[smart-telescope]]
- [[hardware-platform]]
- [[requirements]]
- [[autofocus]]
- [[live-stacking]]
