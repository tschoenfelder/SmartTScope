# M5-001 Guided Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate the "Proceed to Alignment →" button on Stage 1 so it is only enabled after `connectAll()` confirms the mount is connected, preventing users from entering Stage 2 without a live mount.

**Architecture:** Three-file frontend fix. `index.html` adds `disabled` to the button's initial HTML. `setup.js`'s `connectAll()` enables/disables it based on the `mountOk` result. `mount.js`'s `s1Proceed()` drops its spurious `unlockStage(2)` call — Stage 2 is already unlocked by `connectAll()`, so the proceed function only needs `goToStage(2)`. A new smoke-test assertion verifies the button starts disabled in the served HTML. M5-003 and M5-004 are also closed: their backing software (readiness card UX1, Visible Tonight catalog M4-002) is fully in place.

**Tech Stack:** Vanilla JS frontend, Python/pytest smoke test (`tests/unit/api/test_smoke.py`).

---

## File Map

| File | Change |
|------|--------|
| `smart_telescope/static/index.html` | Add `disabled` to `s1-proceed-btn` (line 832) |
| `smart_telescope/static/js/setup.js` | Enable/disable `s1-proceed-btn` after `connectAll()` result |
| `smart_telescope/static/js/mount.js` | Remove `unlockStage(2)` from `s1Proceed()` |
| `tests/unit/api/test_smoke.py` | Assert `s1-proceed-btn` is `disabled` in the served HTML |
| `docs/todo.md` | Mark M5-001, M5-003, M5-004 done |
| `wiki/log.md` | Append log entry |

---

### Task 1: Gate the proceed button on mount connection

**Files:**
- Modify: `smart_telescope/static/index.html:832`
- Modify: `smart_telescope/static/js/setup.js` (inside `connectAll()`, near line 900)
- Modify: `smart_telescope/static/js/mount.js:258-261`
- Test: `tests/unit/api/test_smoke.py`

- [ ] **Step 1: Write the failing smoke test**

In `tests/unit/api/test_smoke.py`, find the `TestHTMLPage` class (it contains `test_index_html_loads`). Add this test inside that class:

```python
    def test_s1_proceed_btn_starts_disabled(self) -> None:
        resp = client.get("/")
        text = resp.text
        idx = text.find('id="s1-proceed-btn"')
        assert idx != -1, "s1-proceed-btn not found in index.html"
        tag_end = text.find('>', idx)
        button_tag = text[idx:tag_end]
        assert 'disabled' in button_tag, (
            "s1-proceed-btn must start disabled — Stage 2 is only unlocked after mount connects"
        )
```

- [ ] **Step 2: Run the test to confirm it fails**

```
cd C:\Users\tscho\Documents\Torsten\TSBrain
python -m pytest tests/unit/api/test_smoke.py::TestHTMLPage::test_s1_proceed_btn_starts_disabled -v
```

Expected: FAIL — `"s1-proceed-btn must start disabled"` assertion error, because the button currently has no `disabled` attribute.

- [ ] **Step 3: Add `disabled` to `s1-proceed-btn` in `index.html`**

In `smart_telescope/static/index.html`, find line 832:
```html
      <button id="s1-proceed-btn" onclick="s1Proceed()">Proceed to Alignment →</button>
```

Replace with:
```html
      <button id="s1-proceed-btn" onclick="s1Proceed()" disabled>Proceed to Alignment →</button>
```

- [ ] **Step 4: Run the test to verify it now passes**

```
python -m pytest tests/unit/api/test_smoke.py::TestHTMLPage::test_s1_proceed_btn_starts_disabled -v
```

Expected: PASS.

- [ ] **Step 5: Enable/disable the proceed button in `connectAll()` in `setup.js`**

In `smart_telescope/static/js/setup.js`, find these two lines inside `connectAll()`:

```javascript
      if (mountOk) unlockStage(2);
      if (camOk)   unlockStage(5);
```

Replace with:

```javascript
      if (mountOk) unlockStage(2);
      if (camOk)   unlockStage(5);
      const proceedBtn = document.getElementById('s1-proceed-btn');
      if (proceedBtn) proceedBtn.disabled = !mountOk;
```

- [ ] **Step 6: Remove `unlockStage(2)` from `s1Proceed()` in `mount.js`**

In `smart_telescope/static/js/mount.js`, find:

```javascript
function s1Proceed() {
    unlockStage(2);
    goToStage(2);
}
```

Replace with:

```javascript
function s1Proceed() {
    goToStage(2);
}
```

Rationale: Stage 2 is already unlocked by `connectAll()` when `mountOk`. Calling `unlockStage(2)` here would allow navigating to Stage 2 even if mount was never connected (the button is now disabled until mount connects, but belt-and-suspenders: the function should not bypass the lock).

- [ ] **Step 7: Run the full smoke suite**

```
python -m pytest tests/unit/api/test_smoke.py -v
```

Expected: all tests pass (was 43, now 44 with the new test).

- [ ] **Step 8: Commit**

```bash
git add smart_telescope/static/index.html smart_telescope/static/js/setup.js smart_telescope/static/js/mount.js tests/unit/api/test_smoke.py
git commit -m "fix: M5-001 — gate Proceed to Alignment on mount connection"
```

---

### Task 2: Mark M5-001, M5-003, M5-004 done and update wiki

**Files:**
- Modify: `docs/todo.md`
- Modify: `wiki/log.md`

- [ ] **Step 1: Update `docs/todo.md`**

Find:
```
- [ ] M5-001 Guided startup `[P1 · Product]`
```
Replace with:
```
- [x] M5-001 Guided startup `[P1 · Product]`
  - *Done:* `s1-proceed-btn` starts `disabled`; `connectAll()` enables it only when `mountOk`; `s1Proceed()` no longer bypasses `unlockStage(2)`. Guided flow: readiness card (auto-load) → Connect All → Proceed to Alignment.
```

Find:
```
- [ ] M5-003 Show readiness dashboard `[P1 · UI]`
```
Replace with:
```
- [x] M5-003 Show readiness dashboard `[P1 · UI]`
  - *Done (UX1):* Readiness card with red/yellow/green items, repair hints, hardware-mode badge, and capability chip row auto-loads on page open. Implemented across R5 / UX1 series.
```

Find:
```
- [ ] M5-004 Select target `[P1 · Product]`
```
Replace with:
```
- [x] M5-004 Select target `[P1 · Product]`
  - *Done (M4-002):* "Visible Tonight" card in Stage 5 lists Messier objects above 20° sorted by altitude; clicking any row sets the session target. Manual RA/Dec entry also available in the GoTo card.
```

Also update the **Last updated** line. Find:
```
**Last updated:** 2026-05-19 (BUG-002 autogain layout; R7-006 evidence-gap report; M6-001–006 performance targets; M6-012 release notes; POD-005 isolation policy)
```
Replace with:
```
**Last updated:** 2026-05-19 (BUG-002 autogain layout; R7-006 evidence-gap report; M6-001–006 performance targets; M6-012 release notes; POD-005 isolation policy; M5-001/003/004 guided startup)
```

- [ ] **Step 2: Prepend log entry to `wiki/log.md`**

Add immediately after the opening `---` separator (before the first existing `## ` entry):

```markdown
## 2026-05-19 — M5-001 — Guided startup

**What changed:**
- `smart_telescope/static/index.html`: `s1-proceed-btn` now starts `disabled`.
- `smart_telescope/static/js/setup.js`: `connectAll()` enables/disables `s1-proceed-btn` based on `mountOk`.
- `smart_telescope/static/js/mount.js`: `s1Proceed()` no longer calls `unlockStage(2)` — Stage 2 unlock belongs to `connectAll()` only.
- `tests/unit/api/test_smoke.py`: Added `test_s1_proceed_btn_starts_disabled`.
- `docs/todo.md`: M5-001, M5-003, M5-004 marked done.

**Tests:** 44 smoke tests pass

---
```

- [ ] **Step 3: Commit**

```bash
git add docs/todo.md wiki/log.md
git commit -m "docs: M5-001/003/004 done — guided startup, readiness dashboard, target selection"
```
