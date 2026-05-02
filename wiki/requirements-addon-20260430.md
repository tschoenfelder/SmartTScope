# Requirements Addon — 2026-04-30

**Summary**: Incremental requirements captured on 2026-04-30, covering target catalog expansion, quickstart documentation corrections, and formal process requirements for release traceability.

**Sources**: resources/hlrequirements/requirements_addon_20260430.txt

**Last updated**: 2026-05-02

---

## Star catalog expansion

The following targets were added to `stars.cfg` following this requirements file. All are now present.

**Deep-sky objects**: Jupiter (planet), Comet C/2025 R3, NGC 2359 (Thor's Helmet), M 51 (Whirlpool), Rosette Nebula (NGC 2237 + NGC 2244 cluster), NGC 3268, IC 5068 (Forsaken Nebula), M 63 (Sunflower), NGC 2024 (Flame Nebula), IC 434 (Horsehead Nebula), NGC 7380 (Wizard Nebula), NGC 6992 (Eastern Veil), NGC 3184, M 42 with narrowband filter note, M 45 with filter note, IC 405 (Flaming Star / Caldwell 31), NGC 281 (Pacman Nebula), NGC 2174 (Monkey Head Nebula), NGC 6960 (Western Veil / Cirrus), NGC 6543 (Cat's Eye Nebula).

**Multiple / triple stars** — chosen for C8 resolution test and visual reward from Frankfurt (Usingen, ~50° N):

| Star | Notes |
|---|---|
| 12 Lyncis | Triple: A/B 5.4/6.0 mag 1.8″, C 7.2 mag 8.6″. Dec +59° — culminates ~81° from Frankfurt. Good C8 challenge. |
| Iota Cassiopeiae | Triple: 4.6/6.9/9.1 mag. Dec +67° — culminates ~73°. Comfortable split. |
| Beta Monocerotis | Triple: 4.6/5.0/5.3 mag, 7″/3″ sep. Visually superb but Dec −7° — only ~33° altitude from Frankfurt. |

## Quickstart corrections

`quickstart.md` was confirmed to have been updated already:
- OS listed as **Debian 13 Trixie** (not Bullseye).
- `libcamera` explicitly marked as **not used** — ToupTek SDK over USB only.

## Process requirements (§14)

Two formal process requirements were added to [[requirements]] §14:

1. **Documentation gate** — a change is not considered done until documentation (wiki page, API contract, quickstart, or inline help) is updated.
2. **Release traceability** — each requirement carries "Planned for release" and "Implemented in release" fields, kept current.

> The requirement tables in §§1–13 of [[requirements]] do not yet carry release columns. Sprint log serves as interim tracking.

---

## Related pages

- [[requirements]]
- [[quickstart]]
- [[requirements-addon-20260501]]
