# Operational Acceptance Checklist

Run this checklist before every observing session to confirm the system is ready.
Record pass/fail and any notes in the hardware test log.

**System:** SmartTScope (Celestron C8 + Raspberry Pi 5 + OnStep V4)  
**App URL:** `http://smarttscope.local:8000` (or Pi IP on port 8000)

---

## 1. Power-on and connectivity

- [ ] Pi 5 powered on; SSH or browser accessible
- [ ] OnStep controller powered on and serial cable connected
- [ ] ToupTek camera USB cable connected and camera powered
- [ ] App starts without error (`uvicorn` process running, browser loads stage 1)

---

## 2. Before connecting — System Readiness card (pre-connect baseline)

Navigate to **Stage 1 (Startup tab)**. The **System Readiness** card is always visible
there; no separate "open" action is needed.

- [ ] System Readiness card is visible and shows items for config, storage, ASTAP, camera, mount
- [ ] **No "Mount time/location" row** — this row only appears after Connect All; its absence here is correct
- [ ] Config file item is **green** — if red, fix `~/.SmartTScope/config.toml` and restart before continuing
- [ ] Note any pre-existing yellow/red items so you can distinguish them from connect-triggered failures

---

## 3. Connect all devices

- [ ] Click **Connect All** (Stage 1 → Startup → Connect All button)
- [ ] Camera status: **ok**
- [ ] Mount status: **ok** — logs show `:GVP#` confirmed OnStep product
- [ ] Focuser status: **ok** or **not available** (acceptable if no focuser hardware)
- [ ] Solver status: **ok** — ASTAP executable and D80 catalog found

If any device shows **error**: follow the action text shown on screen, retry once, then
consult the hardware test log for prior failures on this component.

---

## 4. System Readiness card (post-connect)

- [ ] **System Readiness** card in Stage 1 (Startup) shows overall green (or yellow with known-acceptable warnings)
- [ ] **Mount time/location** row now appears with one of:
  - Green — "Time and location synced"
  - Yellow — "OnStep not responding to time/location queries" (mount connected but not answering `:GC#`/`:Gt#`)
  - Red — clock or location drift details (e.g. "clock off by 120 s" or "site off by 0.05°")
- [ ] Mount state is **TRACKING** or **PARKED** (not **UNKNOWN**)
- [ ] No stale-data warning (⚠) on mount state badge

---

## 5. Setup check

- [ ] Open **Setup & Diagnostics** → run **Setup Check**
- [ ] Mount RA moves: check passes (RA reading changes after short slew)
- [ ] Mount DEC moves: check passes
- [ ] Camera captures: check passes (frame returns within timeout)
- [ ] Focuser available: **pass** or explicitly **skipped** (if no focuser)
- [ ] All steps shown in green; no red failures

---

## 6. Solar safety gate

- [ ] Verify solar exclusion is active: attempt GoTo with Sun coordinates
  (RA ≈ current Sun RA, Dec ≈ current Sun Dec) without `confirm_solar=true`
- [ ] Expect HTTP **403** with `solar_exclusion` detail — do NOT proceed if accepted

---

## 7. GoTo a known bright star (alignment verification)

- [ ] Select a well-known bright star (e.g. Vega, Arcturus, Sirius) visible tonight
- [ ] Issue GoTo; slew completes within 2 minutes
- [ ] Plate solve succeeds after slew (camera captures, ASTAP returns solution)
- [ ] Mount syncs to solved position; centering offset < 5 arcmin

---

## 8. Autofocus

- [ ] Run autofocus from UI (Stage 4 or via `/api/focuser/autofocus`)
- [ ] Focuser sweeps, captures frames, and returns a best position
- [ ] `metric_gain` > 1.0 (focus improved relative to start)
- [ ] Focuser moves to best position and stops within 30 s

---

## 9. Emergency STOP

- [ ] While mount is slewing (or immediately after issuing a GoTo), press **STOP**
- [ ] Mount stops within **1 second** of STOP press
- [ ] Mount state transitions to **UNPARKED** or **TRACKING** (not stuck in SLEWING)
- [ ] Further GoTo commands are accepted normally after STOP

---

## 10. Preview and stack

- [ ] Start live preview (Stage 3); camera frames appear within 5 s
- [ ] Histogram is displayed and shows a reasonable distribution
- [ ] Start a short stack session (e.g. 3 frames × 10 s)
- [ ] Frames integrate; `frames_integrated` count increments in status
- [ ] Session completes and saves image + log to output directory

---

## 11. Shutdown

- [ ] Issue **Park** command; mount parks successfully
- [ ] Stop the app (`Ctrl-C` or `systemctl stop smarttscope`)
- [ ] Verify no mount or focuser motion after app exit (check hardware)
- [ ] Output FITS and session JSON log present in output directory

---

## Sign-off

| Field             | Value |
|-------------------|-------|
| Date              |       |
| Operator          |       |
| Pi serial / build |       |
| App version (git) |       |
| Overall result    | PASS / FAIL |
| Notes             |       |
