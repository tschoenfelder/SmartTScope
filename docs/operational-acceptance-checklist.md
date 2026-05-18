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

## 2. Connect all devices

- [ ] Click **Connect All** (Stage 1 → Setup & Diagnostics → Connect All)
- [ ] Camera status: **ok**
- [ ] Mount status: **ok** — logs show `:GVP#` confirmed OnStep product
- [ ] Focuser status: **ok** or **not available** (acceptable if no focuser hardware)
- [ ] Solver status: **ok** — ASTAP executable and D80 catalog found

If any device shows **error**: follow the action text shown on screen, retry once, then
consult the hardware test log for prior failures on this component.

---

## 3. Readiness dashboard

- [ ] Stage 1 readiness card shows all green (or yellow with known-acceptable warnings)
- [ ] Mount state is **TRACKING** or **PARKED** (not **UNKNOWN**)
- [ ] No stale-data warning (⚠) on mount state badge

---

## 4. Setup check

- [ ] Open **Setup & Diagnostics** → run **Setup Check**
- [ ] Mount RA moves: check passes (RA reading changes after short slew)
- [ ] Mount DEC moves: check passes
- [ ] Camera captures: check passes (frame returns within timeout)
- [ ] Focuser available: **pass** or explicitly **skipped** (if no focuser)
- [ ] All steps shown in green; no red failures

---

## 5. Solar safety gate

- [ ] Verify solar exclusion is active: attempt GoTo with Sun coordinates
  (RA ≈ current Sun RA, Dec ≈ current Sun Dec) without `confirm_solar=true`
- [ ] Expect HTTP **403** with `solar_exclusion` detail — do NOT proceed if accepted

---

## 6. GoTo a known bright star (alignment verification)

- [ ] Select a well-known bright star (e.g. Vega, Arcturus, Sirius) visible tonight
- [ ] Issue GoTo; slew completes within 2 minutes
- [ ] Plate solve succeeds after slew (camera captures, ASTAP returns solution)
- [ ] Mount syncs to solved position; centering offset < 5 arcmin

---

## 7. Autofocus

- [ ] Run autofocus from UI (Stage 4 or via `/api/focuser/autofocus`)
- [ ] Focuser sweeps, captures frames, and returns a best position
- [ ] `metric_gain` > 1.0 (focus improved relative to start)
- [ ] Focuser moves to best position and stops within 30 s

---

## 8. Emergency STOP

- [ ] While mount is slewing (or immediately after issuing a GoTo), press **STOP**
- [ ] Mount stops within **1 second** of STOP press
- [ ] Mount state transitions to **UNPARKED** or **TRACKING** (not stuck in SLEWING)
- [ ] Further GoTo commands are accepted normally after STOP

---

## 9. Preview and stack

- [ ] Start live preview (Stage 3); camera frames appear within 5 s
- [ ] Histogram is displayed and shows a reasonable distribution
- [ ] Start a short stack session (e.g. 3 frames × 10 s)
- [ ] Frames integrate; `frames_integrated` count increments in status
- [ ] Session completes and saves image + log to output directory

---

## 10. Shutdown

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
