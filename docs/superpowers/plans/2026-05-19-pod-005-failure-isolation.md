# POD-005 Failure Isolation Policy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-feature capability flags (`can_preview`, `can_goto`, `can_solve`, `can_autofocus`, `can_save`) to the `/api/readiness` response so the UI and callers always know which features survive a partial device failure.

**Architecture:** A static helper `ReadinessService._capability_flags(items)` derives five boolean flags from the list of `ReadinessItem` objects already built by `check()`. The flags are added to `ReadinessReport`. The frontend readiness card gains a compact chip row showing blocked capabilities. This formalises the POD-005 decision without touching any other service.

**Tech Stack:** Python / Pydantic (backend model), pytest (tests), vanilla JS (frontend chip row).

---

## File Map

| File | Change |
|------|--------|
| `smart_telescope/services/readiness.py` | Add 5 fields to `ReadinessReport`; add `_capability_flags()` static method; call it in `check()` |
| `tests/unit/api/test_readiness.py` | Add `TestCapabilityFlags` class (11 tests); extend endpoint field check |
| `smart_telescope/static/js/setup.js` | Update `_renderReadiness()` to show capability chips |
| `docs/todo.md` | Mark POD-005 done |
| `wiki/index.md` + `wiki/log.md` | Standard update |

---

### Task 1: Extend `ReadinessReport` and add `_capability_flags()`

**Files:**
- Modify: `smart_telescope/services/readiness.py:43-48` (ReadinessReport model)
- Modify: `smart_telescope/services/readiness.py:52-80` (check method)

- [ ] **Step 1: Write the failing test**

Add a new class at the bottom of `tests/unit/api/test_readiness.py`:

```python
class TestCapabilityFlags:
    def _item(self, key: str, level: Level) -> ReadinessItem:
        return ReadinessItem(key=key, label=key, level=level, message="")

    def test_all_flags_true_when_no_red_items(self) -> None:
        items = [
            self._item("camera", Level.GREEN),
            self._item("mount", Level.GREEN),
            self._item("astap_exe", Level.GREEN),
            self._item("astap_catalog", Level.GREEN),
            self._item("focuser", Level.GREEN),
            self._item("storage", Level.GREEN),
        ]
        flags = ReadinessService._capability_flags(items)
        assert flags["can_preview"] is True
        assert flags["can_goto"] is True
        assert flags["can_solve"] is True
        assert flags["can_autofocus"] is True
        assert flags["can_save"] is True

    def test_camera_red_blocks_preview_not_goto(self) -> None:
        flags = ReadinessService._capability_flags([self._item("camera", Level.RED)])
        assert flags["can_preview"] is False
        assert flags["can_goto"] is True

    def test_mount_red_blocks_goto_not_preview(self) -> None:
        flags = ReadinessService._capability_flags([self._item("mount", Level.RED)])
        assert flags["can_goto"] is False
        assert flags["can_preview"] is True

    def test_astap_exe_red_blocks_solve(self) -> None:
        flags = ReadinessService._capability_flags([self._item("astap_exe", Level.RED)])
        assert flags["can_solve"] is False

    def test_astap_catalog_red_blocks_solve(self) -> None:
        flags = ReadinessService._capability_flags([self._item("astap_catalog", Level.RED)])
        assert flags["can_solve"] is False

    def test_focuser_yellow_does_not_block_autofocus(self) -> None:
        # YELLOW = focuser not found; autofocus degraded but not blocked
        flags = ReadinessService._capability_flags([self._item("focuser", Level.YELLOW)])
        assert flags["can_autofocus"] is True

    def test_focuser_red_blocks_autofocus(self) -> None:
        flags = ReadinessService._capability_flags([self._item("focuser", Level.RED)])
        assert flags["can_autofocus"] is False

    def test_storage_red_blocks_save(self) -> None:
        flags = ReadinessService._capability_flags([self._item("storage", Level.RED)])
        assert flags["can_save"] is False

    def test_astap_missing_blocks_solve_only(self) -> None:
        # POD-005: ASTAP missing → blocks observing only; preview + goto still available
        items = [
            self._item("astap_exe", Level.RED),
            self._item("astap_catalog", Level.RED),
            self._item("camera", Level.GREEN),
            self._item("mount", Level.GREEN),
        ]
        flags = ReadinessService._capability_flags(items)
        assert flags["can_solve"] is False
        assert flags["can_preview"] is True
        assert flags["can_goto"] is True

    def test_mount_fail_allows_camera_preview(self) -> None:
        # POD-005: mount serial failure → allows camera preview + diagnostics
        items = [self._item("mount", Level.RED), self._item("camera", Level.GREEN)]
        flags = ReadinessService._capability_flags(items)
        assert flags["can_goto"] is False
        assert flags["can_preview"] is True

    def test_camera_fail_allows_mount_controls(self) -> None:
        # POD-005: camera failure → allows mount controls + diagnostics
        items = [self._item("camera", Level.RED), self._item("mount", Level.GREEN)]
        flags = ReadinessService._capability_flags(items)
        assert flags["can_preview"] is False
        assert flags["can_goto"] is True
```

Also extend `TestReadinessEndpoint.test_response_has_required_fields`:

```python
    def test_response_has_required_fields(self) -> None:
        d = client.get("/api/readiness").json()
        assert "overall" in d
        assert "can_observe" in d
        assert "can_preview" in d
        assert "can_goto" in d
        assert "can_solve" in d
        assert "can_autofocus" in d
        assert "can_save" in d
        assert "mode" in d
        assert "items" in d
        assert "checked_at" in d
```

- [ ] **Step 2: Run the tests to confirm they fail**

```
python -m pytest tests/unit/api/test_readiness.py::TestCapabilityFlags -v
```

Expected: FAIL — `ReadinessService` has no `_capability_flags` attribute.

- [ ] **Step 3: Add `_capability_flags()` to `ReadinessService` and new fields to `ReadinessReport`**

Replace the `ReadinessReport` model definition in `smart_telescope/services/readiness.py`:

```python
class ReadinessReport(BaseModel):
    overall:      Level
    can_observe:  bool
    can_preview:  bool
    can_goto:     bool
    can_solve:    bool
    can_autofocus: bool
    can_save:     bool
    mode:         str
    items:        list[ReadinessItem]
    checked_at:   str
```

Add this static method **inside** `ReadinessService`, before `check()`:

```python
    @staticmethod
    def _capability_flags(items: list[ReadinessItem]) -> dict[str, bool]:
        """Derive per-feature capability flags from readiness items.

        Only RED items block a capability; YELLOW = degraded but functional.
        """
        red = {i.key for i in items if i.level == Level.RED}
        return {
            "can_preview":    "camera"        not in red,
            "can_goto":       "mount"         not in red,
            "can_solve":      "astap_exe"     not in red and "astap_catalog" not in red,
            "can_autofocus":  "focuser"       not in red,
            "can_save":       "storage"       not in red,
        }
```

Update the `check()` return statement in `smart_telescope/services/readiness.py`. Replace the existing `return ReadinessReport(...)` block with:

```python
        flags = self._capability_flags(items)
        return ReadinessReport(
            overall=overall,
            can_observe=can_observe,
            can_preview=flags["can_preview"],
            can_goto=flags["can_goto"],
            can_solve=flags["can_solve"],
            can_autofocus=flags["can_autofocus"],
            can_save=flags["can_save"],
            mode=mode,
            items=items,
            checked_at=datetime.now(timezone.utc).isoformat(),
        )
```

- [ ] **Step 4: Run the new tests to verify they pass**

```
python -m pytest tests/unit/api/test_readiness.py -v
```

Expected: All tests in the file pass.

- [ ] **Step 5: Run the full suite to catch regressions**

```
python -m pytest --tb=short -q
```

Expected: same pass count as before (≥ 2664) plus the 12 new tests.

- [ ] **Step 6: Commit**

```bash
git add smart_telescope/services/readiness.py tests/unit/api/test_readiness.py
git commit -m "feat: POD-005 — capability flags in readiness API (can_preview/goto/solve/autofocus/save)"
```

---

### Task 2: Update frontend readiness card with capability chips

**Files:**
- Modify: `smart_telescope/static/js/setup.js` — `_renderReadiness()` function

- [ ] **Step 1: Add chip rendering to `_renderReadiness()`**

In `setup.js`, find the existing `_renderReadiness(r)` function. After the `items.innerHTML = rows.join('');` line (currently the last line before the closing `}`), add:

```javascript
    // Capability chip row (only shown when at least one flag is false)
    const chipEl = document.getElementById('s1-readiness-caps');
    if (chipEl) {
        const caps = [
            { key: 'can_preview',    label: 'Preview' },
            { key: 'can_goto',       label: 'GoTo' },
            { key: 'can_solve',      label: 'Solve' },
            { key: 'can_autofocus',  label: 'Autofocus' },
            { key: 'can_save',       label: 'Save' },
        ];
        const blocked = caps.filter(c => r[c.key] === false);
        if (blocked.length === 0) {
            chipEl.innerHTML = '';
        } else {
            chipEl.innerHTML =
                '<span style="font-size:0.72rem;color:var(--muted);margin-right:0.35rem">Blocked:</span>' +
                blocked.map(c =>
                    `<span style="font-size:0.72rem;background:var(--danger-bg,rgba(220,50,50,.12));` +
                    `color:var(--danger);border:1px solid var(--danger);border-radius:3px;` +
                    `padding:0 0.35rem;margin-right:0.25rem">${escHtml(c.label)}</span>`
                ).join('');
        }
    }
```

- [ ] **Step 2: Add the `s1-readiness-caps` element to the HTML**

In `smart_telescope/static/index.html`, find the readiness card section (look for `s1-readiness-items`). After the `<div id="s1-readiness-items">` element (the items container), add:

```html
<div id="s1-readiness-caps" style="padding-top:0.4rem;display:flex;flex-wrap:wrap;align-items:center"></div>
```

- [ ] **Step 3: Verify the smoke tests still pass**

```
python -m pytest tests/unit/api/test_smoke.py -v
```

Expected: all 39 pass.

- [ ] **Step 4: Commit**

```bash
git add smart_telescope/static/js/setup.js smart_telescope/static/index.html
git commit -m "feat: POD-005 — blocked-capability chip row in readiness card"
```

---

### Task 3: Mark POD-005 done and update wiki

**Files:**
- Modify: `docs/todo.md`
- Modify: `wiki/index.md`
- Modify: `wiki/log.md`

- [ ] **Step 1: Update `docs/todo.md`**

Find:
```
- [ ] POD-005 Which failures may block the whole app, and which must degrade locally?
  - *Guidance (decision pending):* ASTAP missing → blocks observing only; mount serial failure → allows camera preview + diagnostics; camera failure → allows mount controls + diagnostics. Formal isolation policy needed before M5.
```

Replace with:
```
- [x] POD-005 Which failures may block the whole app, and which must degrade locally?
  - *Decision:* Per-feature isolation: camera RED → `can_preview=false`, mount RED → `can_goto=false`, ASTAP RED → `can_solve=false`, focuser RED → `can_autofocus=false`, storage RED → `can_save=false`. YELLOW items degrade, not block. `can_observe` requires all five plus `mode=real`.
  - *Done:* `ReadinessService._capability_flags()` + 5 new fields in `ReadinessReport`; 11 new tests in `TestCapabilityFlags`; blocked-capability chip row in readiness card.
```

- [ ] **Step 2: Append to `wiki/log.md`**

```
## 2026-05-19 — POD-005 — Failure isolation policy

**What changed:**
- `smart_telescope/services/readiness.py`: Added `_capability_flags(items)` static method + 5 new fields to `ReadinessReport` (`can_preview`, `can_goto`, `can_solve`, `can_autofocus`, `can_save`). RED items block the relevant capability; YELLOW = degraded, functional.
- `tests/unit/api/test_readiness.py`: Added `TestCapabilityFlags` (11 tests covering POD-005 isolation scenarios).
- `smart_telescope/static/js/setup.js` + `index.html`: Blocked-capability chip row in readiness card.
- `docs/todo.md`: POD-005 marked done with formal decision recorded.

**Tests:** ≥ 2676 passed
```

- [ ] **Step 3: Commit**

```bash
git add docs/todo.md wiki/log.md
git commit -m "docs: POD-005 done — record isolation policy decision and update wiki log"
```
