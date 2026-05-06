# Wiki Index

Table of contents for the SmartTelescope knowledge base.

---

## Concepts

- [smart-telescope](smart-telescope.md) — Definition and seven defining traits of the smart telescope category
- [plate-solving](plate-solving.md) — Autonomous sky alignment by matching star patterns to a catalog
- [live-stacking](live-stacking.md) — Real-time frame integration for progressive deep-sky image improvement
- [autofocus](autofocus.md) — Automated focus optimization using star-size metrics and a motor focuser
- [bahtinov-analyzer](bahtinov-analyzer.md) — Diffraction spike detection algorithm: crossing-error metric, two-layer BahtinovAnalyzer/FocusController design

## Hardware and products

- [hardware-platform](hardware-platform.md) — Target build: Celestron C8 + Raspberry Pi 5 + OnStep V4
- [touptek-sdk](touptek-sdk.md) — ToupTek toupcam SDK: architecture, trigger/RAW/TEC/filter-wheel API, and adapter design
- [onstep-protocol](onstep-protocol.md) — Full LX200 command reference for OnStep V4: mount, focuser, park, tracking, with adapter implementation notes
- [seestar-s50](seestar-s50.md) — ZWO Seestar S50 reference smart telescope
- [vaonis-vespera](vaonis-vespera.md) — Vaonis Vespera Pro reference smart telescope

## Planning

- [requirements](requirements.md) — Full MVP / MVP+ / Full requirement set for the C8 + Pi 5 + OnStep build (revised; §14 process requirements added 2026-04-30)
- [requirements-review](requirements-review.md) — External review: verdict, retagging rationale, and missing requirement areas
- [requirements-addon-20260430](requirements-addon-20260430.md) — Star catalog expansion, quickstart corrections, and process requirements (2026-04-30)
- [requirements-addon-20260501](requirements-addon-20260501.md) — First hardware test session bugs and mount safety requirements (2026-05-01)
- [requirements-addon-20260502b](requirements-addon-20260502b.md) — README update instructions + focuser always-expected policy, shared serial delegation, is_available (2026-05-02)
- [requirements-addon-20260506](requirements-addon-20260506.md) — Fix/update requirements: camera naming, Live Preview backend, histogram, exposure/gain UI, Startup polish (2026-05-06)
- [vertical-slice-mvp](vertical-slice-mvp.md) — End-to-end MVP slice: power-on → align → GoTo M42 → recenter → stack 10 frames → save
- [quickstart](quickstart.md) — First-time setup guide: Raspberry Pi OS Trixie (Debian 13), ToupTek camera, ASTAP, no libcamera
