# Release Go/No-Go Checklist

Complete every item before tagging a release. Items marked **[BLOCKER]** must
be **PASS** — the release cannot proceed with any blocker open or deferred
without explicit product-owner sign-off and a written rationale.

---

## 1. Backlog gate

- [ ] **[BLOCKER]** All P0 items closed (done) or deferred with written rationale in `docs/todo.md`
- [ ] **[BLOCKER]** All P1 items closed or deferred with written rationale
- [ ] All P0/P1 items have acceptance criteria recorded in `docs/todo.md`
- [ ] No open field bugs without a backlog ID

**P0 items to verify closed:**
- BUG-005 crash isolation / STOP always responds
- BUG-023 shutdown closes OnStep connection
- R1-004 STOP priority higher than all normal commands
- R1-011 hardware verification: STOP during slew + focuser move
- M1-005 hardware evidence: STOP during slew
- M1-006 hardware evidence: STOP during focuser move
- M1-007 hardware evidence: shutdown during active motion
- M5-011 stop/recover safely
- R7-004 all six evidence items recorded

---

## 2. Hardware evidence gate (R7-004)

All six evidence items must have at least one **PASS** entry in
`docs/hardware-test-log-template.md`:

- [ ] **[BLOCKER]** E-001 STOP during mount slew — PASS recorded
- [ ] **[BLOCKER]** E-002 STOP during focuser move — PASS recorded
- [ ] **[BLOCKER]** E-003 Shutdown during active motion — PASS recorded
- [ ] **[BLOCKER]** E-004 Reconnect after power-cycle — PASS recorded
- [ ] E-005 Full setup check — PASS recorded
- [ ] **[BLOCKER]** E-006 Full observing workflow (GoTo → solve → focus → stack → save) — PASS recorded

---

## 3. Operational acceptance gate

- [ ] **[BLOCKER]** Operational acceptance checklist (`docs/operational-acceptance-checklist.md`) completed with **PASS** on real hardware
- [ ] Sign-off entry present (date, operator, app commit)

---

## 4. Test suite gate

- [ ] **[BLOCKER]** `python -m pytest` passes with ≥ 80 % total coverage on CI or local
- [ ] No skipped tests without a recorded reason
- [ ] Coverage report shows all P0/P1 code paths covered

---

## 5. Clean install gate

- [ ] **[BLOCKER]** M6-011: Clean Pi install from scratch completed (Trixie 64, fresh SD card)
- [ ] App starts on fresh install without manual intervention beyond documented steps
- [ ] `docs/wiki/quickstart.md` is accurate (no manual steps missing)

---

## 6. Performance targets

Verify against targets defined in M6-001 through M6-006 (to be filled when decided):

- [ ] Preview latency < [target from M6-002]
- [ ] STOP response time < 1 s (POD-002)
- [ ] Centering accuracy < [target from M6-004]
- [ ] Plate solve success rate > [target from M6-005]
- [ ] Pi CPU temperature < [target from M6-006] during a 30-min session

---

## 7. Documentation gate

- [ ] Release notes written (`docs/release-notes-vX.Y.md`) covering: new features, known issues, upgrade path
- [ ] `wiki/index.md` up to date
- [ ] `docs/quickstart.md` tested against clean install result
- [ ] All deferred items listed in known issues section of release notes

---

## 8. Product-owner sign-off

| Field             | Value |
|-------------------|-------|
| Release tag       |       |
| Date              |       |
| Signed off by     |       |
| Hardware evidence log commit | |
| Notes             |       |

**Decision:** GO / NO-GO

*Reason if NO-GO:*

---

## Deferred items register

Items deferred from this release (P0/P1 only require explicit rationale):

| Backlog ID | Item | Priority | Rationale for deferral | Target release |
|------------|------|----------|------------------------|----------------|
|            |      |          |                        |                |
