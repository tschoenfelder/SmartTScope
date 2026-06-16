# Release Notes v0.1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `docs/release-notes-v0.1.md` covering all implemented features, known issues, hardware-blocked items, and deferred scope for the first SmartTScope MVP release.

**Architecture:** Single Markdown document summarising milestones M0–M6, open backlog items, and install/upgrade path. No code changes required.

**Tech Stack:** Markdown, `docs/todo.md` as source of truth for completed and open items.

---

### Task 1: Write `docs/release-notes-v0.1.md`

**Files:**
- Create: `docs/release-notes-v0.1.md`

- [ ] **Step 1: Draft the document**

Content sections:
1. Header (version, date, commit range, milestone status)
2. What's new — features by milestone (M1–M6, Collimation, R-series)
3. Known issues — remaining open backlog items (priority, status)
4. Hardware-blocked items (require evidence on real Pi hardware)
5. Deferred scope (post-MVP items)
6. Install and upgrade path (from quickstart wiki)
7. Performance targets (from domain/performance_targets.py)

- [ ] **Step 2: Update `docs/todo.md` to mark M6-012 done**

In `docs/todo.md` find:
```
- [ ] M6-012 Produce release notes and known issues `[P1 · Process]`
```
Replace with:
```
- [x] M6-012 Produce release notes and known issues `[P1 · Process]`
  - *Done:* `docs/release-notes-v0.1.md` — features (M0–M6 + Collimation), known issues, hardware-blocked items, deferred scope, install path, performance targets
```

- [ ] **Step 3: Update `wiki/index.md` to add the release notes link**

Under `## Release readiness` add:
```
- [release-notes-v0.1](../docs/release-notes-v0.1.md) — First MVP release notes: features, known issues, deferred scope, install path
```

- [ ] **Step 4: Append to `wiki/log.md`**

```
## 2026-05-19 — M6-012 release notes v0.1
Source: docs/todo.md M6-012
Created docs/release-notes-v0.1.md covering all implemented milestones (M0–M6 + Collimation),
open known issues, hardware-blocked evidence items, deferred post-MVP scope, install/upgrade path,
and performance targets. Marked M6-012 done in todo.md. Updated wiki/index.md.
```

- [ ] **Step 5: Commit**

```bash
git add docs/release-notes-v0.1.md docs/todo.md wiki/index.md wiki/log.md
git commit -m "docs: M6-012 — release notes v0.1 (features, known issues, deferred scope)"
```
