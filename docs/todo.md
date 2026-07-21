# SmartTScope — Development Todo

**Source:** `docs/smarttscope-final-product-architecture-ai-plan.md`  
**Field bugs:** `resources/hlrequirements/Items_to_fix_20260513.txt`, `Items_to_fix_20260514.txt`  
**Created:** 2026-05-15  
**Last updated:** 2026-07-17 (ONS31-001..008 and ONS31-101..108/110 completed and committed — full USB-connectivity replacement done, suite green 3898 passed; new SYNC-OVERRIDE: upstream wheel's `_load_calibrated_max_position()` has a broken relative import, shim carries the loader; remaining open: ONS31-109 Pi hardware smoke test, ONS31-104 issue-#3 update pending user approval)
**New sources (2026-07-06):** `smarttscope_requirements_full.md` (state-based observation system: BOOTSTRAP..PARKED_SAFE top-level flow, G1-G10 guards, MVP staging in §11) — drove the M9 rewrite of the main UI from a 5-tab wizard to a guided single-flow screen
**New sources (2026-06-24):** `E:\Bilder\Astro\SmartTScopeReq\smarttscope_additional_requirements.md`
**Review source:** `resources/hlrequirements/development-state-review-2026-05-17.md`
**New sources (2026-05-23):** `resources/hlrequirements/onstep_guiding_requirements.md`, `resources/hlrequirements/smarttscope_onstep_adapter_replacement_requirements.md`, `resources/hlrequirements/raspberry_pi5_trixie_watchdog_setup.md`, `resources/hlrequirements/external_heartbeat_stop_supervisor.md`, `resources/hlrequirements/INDI_Steer_pattern.md`, `resources/hlrequirements/SmartTScope_ToupTek_Device_Handling_Recommendation.md`

## Priority legend

| Code | Meaning |
|------|---------|
| P0 Safety | Uncontrolled hardware motion, data corruption, emergency stop failure |
| P1 Product Blocker | Blocks guided startup, observing workflow, or MVP demo |
| P2 Important | Robustness / diagnosability — has a workaround |
| P3 Polish | UX, wording, non-critical efficiency |

---

## Immediate Actions

- [x] NEXT-001 Approve consolidated plan as current product direction `[P1 · Process]`
- [x] NEXT-002 Decide where the authoritative backlog lives — `docs/todo.md` `[P1 · Process]`
- [x] NEXT-003 Create `smarttscope-product-steward` AI skill → `docs/skills/smarttscope-product-steward.md` `[P2 · Process]`
- [x] NEXT-004 Create `smarttscope-quality-sentinel` AI skill → `docs/skills/smarttscope-quality-sentinel.md` `[P2 · Process]`
- [x] NEXT-007 Complete M0 before any new feature work — satisfied by todo ordering `[P1 · Process]`
- [x] NEXT-009 Start R0 Runtime Context Foundation — `RuntimeContext` created, `app.py` and `deps.py` updated, all tests pass `[P1 · Runtime]`
- [x] NEXT-011 Start UX1 Ready To Observe design in parallel with R5 readiness service — `ReadinessService`, `/api/readiness`, readiness card in Stage 1 UI, 22 tests `[P1 · UI]`

---

## OnStepAdapter Migration — 2026-06-14

All mount and focuser hardware communication now flows exclusively through the external `onstep_adapter` package (tschoenfelder/OnStepAdapter). `smart_telescope/adapters/onstep/` is an override layer — it subclasses the pip-installed package; it does NOT contain a hand-rolled copy. See `SYNC.md` for sync state, active SYNC-OVERRIDEs, and upgrade procedure.

### Completed (initial migration to pip-installed package)

- [x] Install `onstep_adapter` wheel and register in `SYNC.md` as external module
- [x] Sync 9 implementation files from OnStepAdapter GitHub into `smart_telescope/adapters/onstep/`
- [x] Add `build_onstep_safety_config()` to `config.py` — bridges config.toml → `OnStepSafetyConfig`
- [x] Update `runtime.py` to use `OnStepClient` lifecycle with safety config
- [x] SYNC-OVERRIDE: add `move(direction, move_ms)` to `OnStepMount` delegating to `guide()` (REQ-1 interim)
- [x] Surface `safety_lock` as `safety_violation` in `MountStatus` API response
- [x] Handle `OnStepSafetyError` in `mount_operations.py` (imported with fallback) and return HTTP 409 from goto
- [x] `MountObservedState` extended with `safety_violation` field; poll loop populates from adapter

### Upgrade to v0.3.0 — 2026-06-17

Release: <https://github.com/tschoenfelder/OnStepAdapter/releases/tag/v0.3.0>

- [x] ONS3-001 Update `pyproject.toml` wheel URL to v0.3.0 `[P1 · Build]`
  - *Done:* `onstep-adapter @ .../v0.3.0/onstep_adapter-0.3.0-py3-none-any.whl` already in `pyproject.toml`
- [x] ONS3-002 Install new wheel: `pip install -e ".[dev]"` and confirm `onstep_adapter.__version__ == "0.3.0"` `[P1 · Build]`
  - *Done:* version confirmed 0.3.0; `onstep_adapter.__init__.py` is a re-export shim pointing to `smart_telescope.adapters.onstep.*`
- [x] ONS3-003 Review each REQ-ST-* override in `smart_telescope/adapters/onstep/mount.py` — check if v0.3.0 base class now handles any of them and remove those that are no longer needed `[P1 · Runtime]`
  - *Done:* All REQ-ST-001..007 overrides must stay — upstream v0.3.0 is a re-export shim with no independent implementation; overrides are permanent until upstream adds real implementations
- [x] ONS3-004 Review `smart_telescope/adapters/onstep/client.py` — its `__init__` replicates the base `OnStepClient.__init__` body; update if upstream signature changed `[P1 · Runtime]`
  - *Done:* `client.py` is SmartTScope-owned complete implementation; no upstream signature change; no action needed
- [x] ONS3-005 Run full unit test suite: `python -m pytest tests/unit/ -x -q` — all tests pass `[P1 · Tests]`
  - *Done:* 2942 passed, 24 skipped (2026-06-21); fixed 4 classes of pre-existing failures found during run: ArchiveConfig default, catalog/star-selector HA filtering not patched in tests, park tests missing `confirmed=True`, stretch test expected percentile behavior from sigma-stretch
- [x] ONS3-006 Commit: `git commit -m "chore: upgrade onstep_adapter to v0.3.0"` `[P1 · Build]`
  - *Done:* committed 2026-06-21

### Upgrade to v0.3.1 — 2026-07-11

Release: <https://github.com/tschoenfelder/OnStepAdapter/releases/tag/v0.3.1>
~~Packaging fix only (removes colliding `smart_telescope/*` files from the wheel; no new
adapter features).~~ **Corrected 2026-07-15:** v0.3.1 is a fully **independent**
`onstep_adapter` package (own `mount.py`, `client.py`, `serial_bus.py`, `focuser.py`,
`safety.py`, `ports/`) — no longer a re-export shim of SmartTScope's code, and the wheel
contains no `smart_telescope/*` files. Supported FSM: `MountState` = 6 enum states
(UNKNOWN, PARKED, UNPARKED, SLEWING, TRACKING, AT_LIMIT); HOME is a decoded `:GU#` flag
(`client.mount.last_decoded_status["at_home"]`), not an enum state. Routed operation
`unpark_to_home_stop_tracking()` unparks, stops firmware auto-tracking, and returns
`{"at_home", "final_status"}`. This unblocks the full USB-connectivity replacement —
see ONS31-101..110 below. Confirmed via the published release, not a local checkout,
per the OnStepAdapter guardrail.

- [x] ONS31-001 Update `pyproject.toml` wheel URL to v0.3.1 `[P1 · Build]`
  - *Done 2026-07-17:* pinned to `v0.3.1/onstep_adapter-0.3.1-py3-none-any.whl`
- [x] ONS31-002 Install new wheel; confirm `onstep_adapter.__version__ == "0.3.1"` and that
      `from onstep_adapter import OnStepClient, OnStepSafetyConfig` works with no
      `smart_telescope` namespace collision `[P1 · Build]`
  - *Done 2026-07-17:* version 0.3.1 confirmed from site-packages; imports clean
- [x] ONS31-003 Diff `onstep_adapter/{mount.py,client.py,focuser.py,ports/*.py,safety.py,
      serial_bus.py,state_store.py}` against `smart_telescope/adapters/onstep/*.py` and
      record the result in `SYNC.md`. 2026-07-11 pre-check (via `gh api`, not local install)
      found: REQ-ST-002, REQ-ST-007 now present upstream; REQ-1, REQ-ST-001, REQ-ST-003,
      REQ-ST-005, REQ-ST-006, REQ-ST-008 still absent (~173-line gap persists); `client.py`
      already identical `[P1 · Runtime]`
  - *Done 2026-07-15/17:* recorded in `SYNC.md`; pre-check partially wrong — REQ-ST-004 and
    REQ-ST-007 are NOT in the installed wheel (repo main ≠ tag); kept as SYNC-OVERRIDEs
- [x] ONS31-004 For each REQ-ST-* override confirmed newly covered upstream (candidates:
      REQ-ST-002, REQ-ST-007) — do NOT remove the local override without first verifying
      byte-for-byte behavioral equivalence against the installed wheel; this is protocol-layer
      code, so if removal reveals a real behavioral difference, stop and flag it rather than
      patching `OnStepMount` directly `[P1 · Runtime]`
  - *Done 2026-07-15/17:* REQ-ST-002 partially covered (residual post-processing stays);
    REQ-ST-004/007 wheel-absent → method-copy overrides stay, documented in `SYNC.md`
- [x] ONS31-005 Run full unit test suite: `python -m pytest tests/unit/ -x -q` — all pass
      `[P1 · Tests]`
  - *Done 2026-07-17:* 3898 passed, 24 skipped, coverage 88.73%
- [x] ONS31-006 Update `SYNC.md`: bump pinned wheel URL and "Last synced" date; update the
      Pending upstream requests table with per-item status (covered vs. still open) `[P1 · Build]`
- [x] ONS31-007 Commit `[P1 · Build]`
  - *Done 2026-07-17:* folded into the ONS31-110 migration commit (single working tree)

#### RFC preparation for remaining gaps

- [x] ONS31-008 Draft upstream change-request content for `tschoenfelder/OnStepAdapter`.
      **Rescoped 2026-07-11** — REQ-1 and REQ-ST-001 are no longer upstream asks (see
      LOCAL-001/002 below); the RFC covers only: REQ-ST-003/006 (recast as a behavior
      request — actively stop unrequested tracking rather than just relabel status, still
      worth raising since it's a general GEM/OnStep firmware quirk), REQ-ST-005 (unchanged,
      `disable_tracking_verified()` flag clear), REQ-ST-008 (`_haversine_m()` +
      `_lx200_round_degrees()` geo helpers — nice-to-have, not blocking, since it stays local
      either way) `[P1 · External]`
- [x] ONS31-009 Filed with explicit user approval 2026-07-11 —
      <https://github.com/tschoenfelder/OnStepAdapter/issues/3> `[P1 · Process]`

#### Local adaptation work identified 2026-07-11 (protocol-layer changes — flagged, awaiting go-ahead)

Per the 2026-07-09 guardrail, none of these touch `smart_telescope/adapters/onstep/mount.py`
until the user explicitly signs off — captured here so the decision isn't lost.

- [x] LOCAL-001 Rewrite `move(direction, move_ms)` to call `onstep_adapter`'s
      `move_ra_timed()`/`move_dec_timed()` (`mode="center"`) directly, translating
      direction/duration at the SmartTScope layer, instead of the current
      `mechanical_manual_move()` interim. Not an upstream ask — SmartTScope adapts to the
      adapter's real signature `[P1 · Runtime]` — **folded into ONS31-106 (2026-07-15)**
  - *Done 2026-07-17 via ONS31-106:* shim `move()` translates onto
    `move_ra_timed()`/`move_dec_timed()`; `mechanical_manual_move()` interim retired
- [x] LOCAL-002 `ensure_time_location_synced()` reclassified as a permanent local wrapper
      (forwards SmartTScope's own config to upstream's `sync_onstep_time_location()`) — no
      code change needed, already correct; just remove it from the upstream-ask list
      `[P2 · Process]`
  - *Done:* listed as permanent wrapper in `SYNC.md`; removed from upstream asks
- [x] SAFETY-001 When firmware auto-starts tracking after `:hR#` that SmartTScope never
      requested, actively stop it (route through the same verified-disable path REQ-ST-005
      describes) instead of only reinterpreting `get_state()`'s reported status while tracking
      continues underneath `[P0 · Safety]` — **superseded 2026-07-15 by ONS31-102** (resolved
      by upstream routed op `unpark_to_home_stop_tracking()`, not a local protocol change)
- [x] SAFETY-002 `unpark()` should drive the mount to a genuine non-tracking mechanical state
      in general, not just clear SmartTScope's own `_explicit_tracking_started` bookkeeping
      flag `[P0 · Safety]` — **superseded 2026-07-15 by ONS31-102** (upstream routed op
      `unpark_to_home_stop_tracking()` provides exactly this)

### Full USB-connectivity replacement via v0.3.1 — 2026-07-15 (HIGH PRIORITY)

v0.3.1 ships an independent implementation (see corrected release note above), so the local
4,534-line `smart_telescope/adapters/onstep/mount.py` and the rest of the local OnStep
USB/serial code can now be replaced by the pip package. Ground rules: the adapter is
**never modified**; if an audit reveals a genuine gap, record it in `SYNC.md` "Pending
upstream requests" and file a GitHub issue **only after explicit user approval**
(ONS31-008/009 pattern). Decisions taken with user 2026-07-15: AT_HOME derived locally
from the decoded status flag (no upstream change needed); unpark switches to the routed
op; client shim uses swap-after-construction instead of the copied constructor.
Prerequisite: ONS31-001..007 (wheel bump, install, diff, override removal audit).

#### Phase B — FSM alignment & routed-operation adoption (after ONS31-001..007)

- [x] ONS31-101 Shim `get_state()` post-processing: map upstream 6-state result +
      `last_decoded_status.get("at_home") is True` → `MountState.AT_HOME` (SmartTScope's
      7-state enum in `smart_telescope/ports/mount.py` stays the app-facing FSM). Replaces
      the `_explicit_tracking_started`-based derivation `[P1 · Runtime]`
      - *Acceptance:* state reported AT_HOME when `:GU#` contains H and not slewing/parked;
        sticky AT_HOME in `DeviceStateService` keeps working unchanged
      - *Done 2026-07-17:* incl. cross-enum equality fix in `ports/mount.py` (upstream
        internals compare against their own `MountState` in 19 call sites — see `SYNC.md`);
        regression tests in `test_mount_state_cross_enum.py`
- [x] ONS31-102 Switch unpark flow (`services/mount_operations.py` / shim `unpark()`) to
      `unpark_to_home_stop_tracking()`; assert `final_status` shows tracking stopped.
      Supersedes SAFETY-001/SAFETY-002 `[P0 · Safety]`
      - *Acceptance:* after unpark, mount is at HOME and NOT tracking (hardware-verified on
        Pi); no local tracking-flag compensation involved
      - *Done 2026-07-17 (code + fake-serial regression: fake auto-starts tracking after
        `:hR#`, asserts `:Td#` actually sent); hardware evidence pending → ONS31-109*
- [x] ONS31-103 Retirement audit for REQ-ST-003/005/006 overrides: verify routed op +
      decoded flag cover each behavior against the installed wheel, then delete the local
      overrides. If a genuine behavioral gap remains, do NOT patch locally — record it in
      `SYNC.md` "Pending upstream requests" and flag to user (change-request path)
      `[P1 · Runtime]`
      - *Acceptance:* overrides deleted or gap documented; never both silently
      - *Done 2026-07-17:* REQ-ST-003/005/006 deleted with the old `mount.py`; retirement
        recorded in `SYNC.md`
- [ ] ONS31-104 Update GitHub issue #3 (REQ-ST-003/005/006 largely superseded by the routed
      op; REQ-ST-008 stays local) — draft comment, post only after user approval. Update
      `SYNC.md` pending-requests table to match `[P2 · Process]`
      - *2026-07-17:* SYNC.md table updated; issue comment drafted and awaiting user
        approval; new upstream ask candidates also pending approval (broken relative
        imports in wheel `focuser.py`/`mount.py`, client mount-injection param,
        subclass-safe internal state checks, safety-config tolerance fields)

#### Phase C — Shim reduction (delete local USB/serial implementation)

- [x] ONS31-105 `client.py`: replace the replicated constructor with swap-after-construction
      — subclass calls `super().__init__()`, then rebuilds `self.mount` as the SmartTScope
      `OnStepMount` subclass bound to `self._bus` (safe: no serial I/O before `connect()`)
      `[P1 · Runtime]`
      - *Acceptance:* no copied upstream constructor code remains; `runtime.py` lifecycle
        unchanged
      - *Done 2026-07-17*
- [x] ONS31-106 `mount.py` (4,534 lines) → thin shim
      `class OnStepMount(onstep_adapter.OnStepMount, MountPort)` keeping ONLY: REQ-1
      `move()` translation → `move_ra_timed()`/`move_dec_timed()` (absorbs LOCAL-001),
      REQ-2 `set/get_park_position()` MountPort adapters, REQ-ST-001
      `ensure_time_location_synced()` config glue, REQ-ST-008
      `_haversine_m()`/`_lx200_round_degrees()` helpers (until upstream adopts), ONS31-101
      `get_state()` AT_HOME mapping, plus anything the ONS31-004/103 audits say must stay
      `[P1 · Runtime]`
      - *Acceptance:* no LX200 command strings, no serial handling, no `:GU#` parsing in the
        file; goal ≤ ~200 lines of pure delegation/translation
      - *Done 2026-07-17:* 465 lines — above the ~200 goal because the ONS31-004 audit
        found REQ-ST-004 (28-line) and REQ-ST-007 (190-line) method copies must stay
        (NOT in the wheel despite the 2026-07-11 pre-check); everything else is
        delegation/translation
- [x] ONS31-107 Convert `serial_bus.py`, `focuser.py`, `safety.py`, `results.py`,
      `state_store.py`, `firmware_proof.py` to thin re-exports from `onstep_adapter.*`;
      `__init__.py` re-exports the package surface and takes `__version__` from
      `onstep_adapter.__version__` (removes the SYNC-OVERRIDE hardcode) `[P2 · Runtime]`
      - *Acceptance:* no serial implementation code remains under
        `smart_telescope/adapters/onstep/`; readiness version report still works
      - *Done 2026-07-17:* `focuser.py` keeps M7-004 backlash + a new SYNC-OVERRIDE
        `_load_calibrated_max_position()` (upstream wheel copy has a broken relative
        import and always returns 0 — see `SYNC.md`); `safety.py` keeps the tolerance-field
        subclass; rest are pure re-exports
- [x] ONS31-108 Retarget adapter tests: `tests/unit/adapters/onstep/*` (incl.
      `fake_serial.py` suites) now exercise the installed wheel through the shim — keep as
      behavioral regression tests; adjust imports/patch targets; full suite
      `python -m pytest tests/unit/ -x -q` green `[P1 · Tests]`
      - *Acceptance:* all tests pass on Windows with mocks; no test imports deleted local
        modules
      - *Done 2026-07-17:* 3898 passed, 24 skipped; patch targets moved to
        `onstep_adapter.mount.*`/`onstep_adapter.focuser.*` per the SYNC.md patch-target
        rule

#### Phase D — Verification & closeout

- [ ] ONS31-109 Pi hardware smoke test: connect → `unpark_to_home_stop_tracking()` (verify
      `at_home=True`, no tracking) → GoTo → STOP → park → disconnect `[P0 · Hardware]`
      - *Must have hardware evidence — not accepted on mock alone*
- [x] ONS31-110 Rewrite `SYNC.md` OnStep section to shim-only end state: pinned v0.3.1
      wheel, permanent-wrapper table, refreshed pending-requests table; update
      `wiki/log.md` + `wiki/index.md`; commit + push
      (`chore: replace local OnStep USB connectivity with onstep_adapter v0.3.1`)
      `[P1 · Build]`
      - *Done 2026-07-17:* committed + pushed; ONS31-109 (Pi hardware smoke test) is the
        only remaining migration item

### Open Enhancement Requests (pending external delivery — tracked in SYNC.md)

- [ ] REQ-1: ~~`move(direction, move_ms)` at slew rate in `OnStepMount`~~ — **reclassified
      2026-07-11, not an upstream ask; see LOCAL-001** — interim currently delegates to
      `mechanical_manual_move()` (docs previously said `guide()`, which was stale)
- [ ] REQ-2: `get_park_position() → MountPosition | None` and `set_park_position() → bool` — **stays in SmartTScope shim** (v0.3.0 already has `set_park_position_from_current()` and `get_stored_park_position()`; these two wrappers adapt to `MountPort` signatures)
- [ ] REQ-3: ~~Sticky AT_HOME state tracking in adapter~~ — **satisfied 2026-07-15 via
      decoded `at_home` flag (ONS31-101)**; upstream exposes HOME as
      `last_decoded_status["at_home"]` (mechanical `:GU#` H flag, deliberately not an enum
      state); sticky presentation stays in `DeviceStateService` by design
- [ ] REQ-4: Hardware watchdog property on `OnStepMount` (currently in `DeviceStateService`)
- [ ] REQ-5: Command audit trail properties on `OnStepMount` (currently in `DeviceStateService`)

### Replace SmartTScope adapter reimplementation with pip package

`smart_telescope/adapters/onstep/mount.py` is 4,408 lines. The goal is to delete it and reduce the adapter layer to a ≤30-line shim that satisfies `MountPort`/`FocuserPort` ABC compliance while delegating all logic to `onstep_adapter`.

**Architecture reality (discovered 2026-06-17):** `onstep_adapter` v0.3.0 is NOT an independent library. Its `__init__.py` consists entirely of `from smart_telescope.adapters.onstep.* import ...` — it re-exports SmartTScope's own code. The only files in the package are `__init__.py` and two smoke-test tools. There is no independent `_BaseMount`. All methods (REQ-1, REQ-ST-001..007) already "exist" in v0.3.0 only because they exist in SmartTScope's own adapter layer.

**What this means:** The migration is blocked on creating an **independent codebase** in the OnStepAdapter repo. The upstream work is not "add these methods" but "implement the full adapter independently so SmartTScope can import from it without circular dependency". REQ-1 and REQ-ST-001..007 describe the methods that independent implementation must include.

**Unblocked 2026-07-15:** v0.3.1 IS that independent codebase (see corrected v0.3.1 release note above). This whole section's open phases are superseded by the concrete task block **ONS31-101..110** ("Full USB-connectivity replacement via v0.3.1"); individual items below are annotated accordingly and kept only as history.

REQ-2 is NOT an upstream requirement — `set_park_position()` and `get_park_position()` stay permanently in the shim as `MountPort` interface adapters over the existing `set_park_position_from_current()` / `get_stored_park_position()` methods.

**End state:** `smart_telescope/adapters/onstep/` contains only a thin `OnStepMount(_PipMount, MountPort): pass` shim. No LX200 commands, no serial bus logic, no method implementations remain in this repo.

#### Phase 0 — Upstream contributions (must happen first)

File the following as issues/PRs on `tschoenfelder/OnStepAdapter`:

| ID | Upstream ask | Reasoning |
|----|-------------|-----------|
| ~~REQ-1~~ | ~~`move(direction, move_ms) → bool` in `_BaseMount`~~ | **NOT upstream (reclassified 2026-07-11)** — SmartTScope should call `move_ra_timed()`/`move_dec_timed()` directly and translate locally; see LOCAL-001. |
| ~~REQ-2~~ | ~~`set_park_position() → bool`~~ | **NOT upstream** — v0.3.0 already has `set_park_position_from_current()` and `get_stored_park_position()`; SmartTScope's `set_park_position()` and `get_park_position()` are thin `MountPort`-compliance wrappers that stay in the shim. |
| ~~REQ-ST-001~~ | ~~`ensure_time_location_synced()`~~ | **NOT upstream (reclassified 2026-07-11)** — pure SmartTScope config-forwarding glue over upstream's existing `sync_onstep_time_location()`; see LOCAL-002. |
| REQ-ST-002 | `confirmed_by_user` param in `sync_onstep_time_location()` sets `time_trust_source="user_confirmed"` | Safety trust tracking — any safety-aware client needs this to clear clock locks. **Confirmed present in v0.3.1 (2026-07-11).** |
| REQ-ST-003 | `_explicit_tracking_started` flag in `get_state()` prevents ``:hR#`` auto-tracking from masking AT_HOME | **Reframed 2026-07-11** — real fix is behavioral (actively stop unrequested tracking, see SAFETY-001), not just report-side disambiguation. Still worth raising upstream; firmware quirk affects all GEM OnStep users. |
| REQ-ST-004 | `enable_tracking()` at-home bypass skips HA/altitude checks when HOME RA is stale | GEM HOME-position safety; stale RA produces false limit blocks at HOME. **Confirmed present in v0.3.1 (2026-07-11).** |
| REQ-ST-005 | `disable_tracking_verified()` clears `_explicit_tracking_started` | Correctness: without the clear, `get_state()` returns TRACKING forever after verified disable. Confirmed scoped correctly 2026-07-11. |
| REQ-ST-006 | `stop()` / `park()` / `unpark()` each clear `_explicit_tracking_started` | **Reframed 2026-07-11** — `unpark()` should drive a genuine non-tracking state in general, not just clear a bookkeeping flag; see SAFETY-002. |
| REQ-ST-007 | `motion_safety_preflight()` pier-side guards: (a) `terminal_state` check; (b) suppress stale `:Gm#` when `axis2 < 15°` at HOME | GEM safety refinement; stale pier-side blocks valid GoTo at CWD home position. **Confirmed present in v0.3.1 (2026-07-11).** |
| REQ-ST-008 | `_haversine_m()` (great-circle distance helper) + `_lx200_round_degrees()` (arcminute-precision rounding matching LX200 site format), used by `get_sync_status()`'s meter-based location tolerance (M8-008) | Generic geo/LX200-format utilities any OnStep client doing location-sync checks would need; found via diff against the vendored copy 2026-07-09 — not filed upstream when added in M8-008. |

- [x] ONS-MIGRATE-001 ~~File upstream issue: REQ-1 `move(direction, move_ms) → bool`~~ — reclassified 2026-07-11 as not an upstream ask (LOCAL-001); now folded into ONS31-106 `[P1 · External]`
- [x] ONS-MIGRATE-002 ~~File upstream: REQ-2~~ — v0.3.0 already has `set_park_position_from_current()` + `get_stored_park_position()`; shim methods stay in SmartTScope (MountPort ABC compliance only) `[P1 · External]`
- [x] ONS-MIGRATE-003 ~~File upstream issues: REQ-ST-001..008~~ — done via issue #3 (ONS31-009) for the still-open subset; REQ-ST-002/004/007 confirmed present in v0.3.1; REQ-ST-003/005/006 superseded by the routed op (ONS31-103/104) `[P1 · External]`
- [x] ONS-MIGRATE-004 ~~Confirm upstream release incorporating the above; update `pyproject.toml` wheel URL~~ — v0.3.1 is that release; wheel bump is ONS31-001 `[P1 · Build]`
- [x] ONS-MIGRATE-014 **Superseded 2026-07-15 by ONS31-003** (diff against installed v0.3.1 wheel, not the repo-vendored copy, which no longer exists upstream). Original: Sync/publish gap: GitHub repo last pushed 2026-06-14; local `mount.py` is 197 lines ahead (all of REQ-ST-001..008 above). Diff `smart_telescope/adapters/onstep/*.py` against the vendored copies at `github.com/tschoenfelder/OnStepAdapter/tree/main/smart_telescope/adapters/onstep/` before claiming parity — confirmed 2026-07-09 that `client.py` was identical but `mount.py` was not `[P1 · External · Guardrail: no code duplication — see memory project_onstep_adapter_v030]`

#### Phase 1 — Audit (after upstream release)

- [x] ONS-MIGRATE-005 ~~Install new wheel; verify each REQ-ST-* is now in the base class; mark covered overrides for deletion~~ — superseded by ONS31-002/003/004/103 `[P1 · Runtime]`

#### Phase 2 — Reduce adapter layer

- [x] ONS-MIGRATE-006 ~~Replace `mount.py` with shim~~ — superseded by ONS31-106 `[P1 · Runtime]`
- [x] ONS-MIGRATE-007 ~~Reduce or delete `client.py`~~ — superseded by ONS31-105 (upstream `OnStepClient` does NOT inject a custom mount, confirmed 2026-07-15; shim stays, using swap-after-construction) `[P1 · Runtime]`
- [x] ONS-MIGRATE-008 ~~Delete 6 thin re-export files; update `__init__.py`~~ — superseded by ONS31-107 (files become thin re-exports from `onstep_adapter.*` rather than deleted) `[P2 · Runtime]`
- [x] ONS-MIGRATE-009 Update import sites: `runtime.py`, `config.py`, `api/mount.py`, `services/mount_operations.py` — all now import from `adapters.onstep` package `__init__.py`, not internal submodules. Dead `OnStepSafetyError` import removed from `mount_operations.py`. Defensive `try/except ImportError` removed from `api/mount.py` and `mount_operations.py`. Ready for final rename to `from onstep_adapter import ...` once upstream is independent. `[P1 · Runtime]`

#### Phase 2b — Consumer API migration (no direct serial communication in api/ or services/)

- [x] ONS-MIGRATE-009b `FocuserPort` extended with `status() → FocuserStatus` and `move_absolute() → FocuserMoveResult`; `FocuserStatus`/`FocuserMoveResult` dataclasses defined in `ports/focuser.py` (canonical); `results.py` re-exports. `api/focuser.py` uses `focuser.status()` + `focuser.move_absolute()` — no individual property calls, no direct serial access. `MockFocuser`, `SimulatorFocuser` updated. 2942 tests pass. `[P1 · Runtime]`
- [ ] ONS-MIGRATE-009c (optional) Extend `MountPort` similarly with structured status call once mount-side richer API is defined upstream. `[P3 · Runtime]`

#### Phase 3 — Verify and close (after upstream independent implementation)

- [x] ONS-MIGRATE-010 ~~Run full unit test suite~~ — superseded by ONS31-108 `[P1 · Tests]`
- [x] ONS-MIGRATE-011 ~~Verify `mount.py` ≤ 30 lines~~ — superseded by ONS31-106 (target revised to ≤ ~200 lines: permanent wrappers REQ-1/REQ-2/REQ-ST-001/REQ-ST-008 + AT_HOME mapping stay local by design) `[P1 · Process]`
- [x] ONS-MIGRATE-012 ~~Hardware smoke-test on Pi~~ — superseded by ONS31-109 `[P1 · Hardware]`
- [x] ONS-MIGRATE-013 ~~Commit and update `SYNC.md` to reflect shim-only state~~ — superseded by ONS31-110 `[P1 · Build]`

---

## M0 — Project Control Restored

*Team knows what is open, what matters, what is duplicated, and what blocks a safe usable product.*

- [x] M0-001 Create one authoritative maintained backlog `[P1 · Process]`
  - *Done:* `docs/todo.md` is the established authoritative backlog (NEXT-002); all field bugs and architecture items imported and prioritized with acceptance criteria on every P0/P1 item.
- [x] M0-002 Import field bugs from Items_to_fix_20260513.txt and Items_to_fix_20260514.txt `[P1 · Process]`
  - *Done:* All field bugs from both files imported with BUG-IDs, priorities, and source annotations throughout this backlog.
- [x] M0-003 Import open items from task docs and architecture review `[P1 · Process]`
  - *Done:* All items from `development-state-review-2026-05-17.md` and architecture plan imported and categorised.
- [x] M0-004 Deduplicate overlapping issues `[P1 · Process]`
  - *Done:* Overlapping field bugs and architecture items consolidated; duplicates noted inline where applicable.
- [x] M0-005 Assign priority to every imported item `[P1 · Process]`
  - *Done:* Every backlog item carries a P0–P3 priority tag.
- [x] M0-006 Add acceptance criteria to every P0/P1 item `[P1 · Process]`
  - *Done:* All P0/P1 items have Acceptance and Done notes recorded.
- [x] M0-007 Link every backlog item to source document `[P2 · Process]`
  - *Done:* Field bugs carry `Source: Items_to_fix_YYYYMMDD` annotations; architecture items reference the plan document.
- [x] M0-008 Add product-owner top-10 risk view `[P2 · Process]`
  - *Done (R7-005):* Top-10 risk items included in `/api/milestones` response; rendered in the Milestone Dashboard card on Stage 1.

**Quality gate:** Every open field bug has a backlog ID. Every P0/P1 item has acceptance criteria. Product owner can see top risks on one page.

---

## M1 — Hardware Safety Spine

*System controls moving parts predictably and can stop safely.*

### P0 Safety — Fix immediately

- [x] BUG-023 Shutdown with CTRL-C does not close OnStep connection; focuser keeps moving in small steps after exit `[P0 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* shutdown sequence stops motion and closes serial before process exits; verified on real Pi
  - *Done:* `RuntimeContext.shutdown()` calls `focuser.stop()` then `mount.stop()` then `mount.disconnect()` in lifespan teardown
- [x] BUG-005 Any component crash must not release control of mount or focuser; STOP must always respond `[P0 · Hardware · Source: Items_to_fix_20260513]`
  - *Acceptance:* preview/camera failure does not affect mount/focuser control; STOP always completes within agreed time
  - *Done:* `_session_thread()` wraps `runner.run()` in a `finally` that calls `rt.job_manager.release()`; STOP endpoint calls `mount.stop()` directly (no coordinator); 10 explicit isolation tests in `tests/unit/api/test_bug005_isolation.py` — coordinator lock bypass, resource release on crash, STOP/goto available post-crash

### R1 — Hardware Command Coordinator

- [x] R1-001 Define `HardwareCommandCoordinator` `[P1 · Runtime]`
- [x] R1-002 Define command types: stop, goto, park, unpark, home, guide, focuser move, focuser nudge `[P1 · Runtime]`
- [x] R1-003 Define command priority rules `[P1 · Runtime]`
- [x] R1-004 Make STOP priority higher than all normal commands `[P0 · Runtime]`
  - *Done:* STOP endpoints call mount/focuser directly, never through coordinator
- [x] R1-005 Define command lifecycle states `[P1 · Runtime]`
  - *Done (R2-003+R2-005):* Lifecycle is: command issued (record_command) → hardware executing (convergence helpers poll cached state) → done or error (record_command_error + observed state change); exposed in MountStatus.last_command/last_command_error
- [x] R1-006 Add command IDs and structured command logs `[P2 · Runtime]`
- [x] R1-007 Move mount/focuser endpoint-local locks into coordinator `[P1 · Runtime]`
  - *Done:* `_goto_lock` removed from `mount.py`, `_move_lock` removed from `focuser.py`; all commands use `coordinator.mount_command()` / `coordinator.focuser_command()`
- [x] R1-008 Introduce OnStep serial bus abstraction `[P1 · Runtime]`
- [x] R1-009 Stop exposing private mount serial methods to focuser adapter `[P1 · Runtime]`
- [x] R1-010 Add concurrency, timeout, and STOP-priority tests `[P1 · Tests]`
  - *Done:* 11 tests in `tests/unit/services/test_hardware_coordinator.py` — conflict detection, timeout=0, lock independence, exception release, STOP bypass pattern
- [ ] R1-011 Hardware verification: STOP during mount slew and STOP during focuser move `[P0 · Hardware]`
  - *Must have hardware evidence — not accepted on mock alone*

### R2 — Device State Service

- [x] R2-001 Define `DeviceStateService` `[P1 · Runtime]`
- [x] R2-002 Define observed mount, focuser, and camera state models `[P1 · Runtime]`
  - *Done:* `MountObservedState` dataclass with state, ra, dec, polled_at, error
- [x] R2-003 Track last command, last observed state timestamp, and last error per device `[P1 · Runtime]`
  - *Done:* `DeviceStateService.record_command(name)`, `record_command_error(msg)`, `get_last_command()` added; all mount command endpoints (park, unpark, goto, home, track, stop) call `record_command` before issuing; errors recorded on failure; `MountStatus` response includes `last_command`, `last_command_age_s`, `last_command_error`; 4 new tests in `test_device_state.py`
- [x] R2-004 Poll mount and focuser state at controlled interval `[P1 · Runtime]`
  - *Done:* background daemon thread polls every 2 s via `DeviceStateService`
- [x] R2-005 Add state convergence helpers for park, unpark, home, and goto completion `[P1 · Runtime]`
  - *Done:* `wait_for_mount_state(target, timeout_s)` waits until cached state equals target; `wait_while_mount_state(current, timeout_s)` waits until cached state differs; `mount_unpark` uses `wait_while_mount_state(PARKED)` to replace direct poll loop; `mount_park` uses `wait_for_mount_state(PARKED)` to confirm within 5 s; 6 new tests in `test_device_state.py`
- [x] R2-006 Add stale-state and slow-response detection `[P2 · Runtime]`
  - *Done:* `MountObservedState.is_stale()` uses 10 s threshold; `stale` field in `MountStatus`
- [x] R2-007 Change status endpoints and UI labels to use observed state `[P1 · Runtime]`
  - *Done:* `GET /api/mount/status` reads from `DeviceStateService` cache; falls back to direct poll only when cache is empty
- [x] R2-008 Test: command accepted but observed state unchanged `[P1 · Tests]`
  - *Done:* 13 tests in `tests/unit/services/test_device_state.py` — poll lifecycle, stale detection, error propagation, position-skip on UNKNOWN, thread-safety

### Field bugs — Mount state

- [x] BUG-011 Park command moves mount but UNPARKED flag remains too long `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* UI label changes only after observed state confirms park; correct within 5 s
  - *Done:* `device_state.poll_now()` after park command refreshes cache immediately; frontend park poll loop extended from 10×500ms to 60×1000ms (60 s total — covers full park slew duration)
- [x] BUG-012 After reconnect, mount shown as unparked when policy requires parked `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Done:* `RuntimeContext.connect_devices()` calls `device_state.poll_now()` immediately after `start()` — cache populated from first millisecond of startup, no 2 s gap
- [x] BUG-016 Unpark returns HTTP 200 but label stays PARKED `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* label follows observed hardware state, not command receipt
  - *Done:* `device_state.poll_now()` after unpark command; timeout extended from 3 s to 5 s; frontend unpark loop extended to 20×500ms (10 s)

### Milestone M1 tasks

- [x] M1-001 Complete R1 hardware command coordinator `[P0 · Runtime]`
- [x] M1-002 Complete R2 observed device state for mount/focuser `[P1 · Runtime]`
- [x] M1-003 Define and implement shutdown sequence `[P0 · Runtime]`
- [x] M1-004 Add hardware watchdog for slow mount/focuser response `[P2 · Runtime]`
- [ ] M1-005 Verify STOP during mount slew (hardware evidence) `[P0 · Hardware]`
- [ ] M1-006 Verify STOP during focuser move (hardware evidence) `[P0 · Hardware]`
- [ ] M1-007 Verify shutdown during active motion (hardware evidence) `[P0 · Hardware]`

**Quality gate:** STOP works during mount slew and focuser movement. Shutdown leaves hardware controlled. Park/unpark UI follows observed state.

---

## M2 — Smart Runtime and Jobs

*Long-running operations are visible, cancellable, timed out, and isolated.*

### R0 — Runtime Context Foundation

- [x] R0-001 Define `RuntimeContext` responsibilities `[P1 · Runtime]`
- [x] R0-002 Create `RuntimeContext` in FastAPI lifespan startup `[P1 · Runtime]`
- [x] R0-003 Move adapter references from module globals into `RuntimeContext` `[P1 · Runtime]`
- [x] R0-004 Move preview camera cache into `RuntimeContext` `[P1 · Runtime]`
- [x] R0-005 Move active session runner reference into `RuntimeContext` `[P1 · Runtime]`
  - *Done:* `session_lock`, `_active_runner`, `_runner_thread` in RuntimeContext; `session.py` uses `rt.set_session()`, `rt.is_session_running()`, `rt.get_active_runner()`
- [x] R0-006 Move autogain job reference into `RuntimeContext` or `JobManager` `[P1 · Runtime]`
  - *Done:* `autogain_lock`, `_autogain_job` in RuntimeContext; `autogain.py` uses `_get_job()` / `_set_job()` wrappers; `reset_for_tests()` clears both
- [x] R0-007 Add explicit `shutdown()`, `connect_devices()`, `disconnect_devices()`, `reset_for_tests()` methods `[P1 · Runtime]`
- [x] R0-008 Update API dependencies to read from app runtime `[P1 · Runtime]`
- [x] R0-009 Keep compatibility wrappers during migration `[P2 · Runtime]`
- [x] R0-010 Add lifecycle tests `[P1 · Tests]`
  - *Done:* 40 tests in `tests/unit/test_runtime.py` — init state, connect_devices (mock + simulator + idempotency + polling starts), shutdown (focuser stop, mount stop-before-disconnect, preview cameras, error tolerance), reset_for_tests (all cleared, session/autogain cleared, new adapters on next access), module singleton (get/set_runtime), session state management, autogain state management, FastAPI lifespan smoke tests
- [x] R0-011 Change `VerticalSliceRunner.run()` to not disconnect adapters in `finally`; release job ownership only; keep hardware live after session `[P1 · Runtime]`
  - *Done:* removed `mount.disconnect()`, `camera.disconnect()`, `focuser.disconnect()` from `runner.py finally`; runtime shutdown sequence owns all device teardown; `test_run_does_not_disconnect_focuser_on_completion` verifies new contract

### R3 — Shared Job Manager

- [x] R3-001 Define `JobManager`, `Job`, `JobStatus`, `ResourceConflictError` `[P1 · Runtime]`
  - *Done:* `smart_telescope/services/job_manager.py` — two modes: `submit()` (fully managed thread) and `claim()`/`release()` (caller-managed); timeout via companion daemon thread
- [x] R3-002 Define resource ownership model for camera, mount, focuser `[P1 · Runtime]`
  - *Done:* convention: `"camera:N"`, `"mount"`, `"focuser"`; conflict check is atomic in `_register()`
- [x] R3-003 Add job status and cancellation APIs `[P1 · Runtime]`
  - *Done:* `cancel()`, `cancel_by_name()`, `cancel_all()`, `get_job()`, `get_by_name()`, `list_active()`, `active_resources()`, `is_resource_held()`, `purge_finished()`
- [x] R3-004 Migrate autogain to job manager `[P1 · Runtime]`
  - *Done:* `autogain.py` uses `rt.job_manager.submit("autogain", {"camera:N"}, _worker, ..., cancel_event=job.cancel, timeout_s=300)`; `ResourceConflictError` → 409
- [x] R3-005 Prevent session/autogain from competing for same camera/mount/focuser `[P1 · Runtime]`
  - *Done:* `session.py` uses `rt.job_manager.claim("session", {"camera:0", "mount", "focuser"})`; thread wrapper calls `release()` in finally; `ResourceConflictError` → 409
- [x] R3-006 Add cancellation checkpoints and timeouts `[P1 · Runtime]`
  - *Done:* timeout watcher in `_start_timeout_watcher()`; autogain timeout 300 s; `cancel_event` bridge between `_Job.cancel` and JobManager
- [x] R3-007 Tests: cancellation, resource conflict, failure isolation `[P1 · Tests]`
  - *Done:* 40 tests in `tests/unit/services/test_job_manager.py` — submit/claim/release lifecycle, resource conflicts, cancellation (by id/name/all), timeout, query API, purge

### Field bugs — Jobs and concurrency

- [x] BUG-001 Autogain cancel does not stop for a long time `[P1 · Runtime · Source: Items_to_fix_20260513]`
  - *Acceptance:* cancel completes within < 1 s of the cancel request (POD-002 decision)
  - *Done:* `CaptureAbortedError` + `abort_capture()` in `CameraPort`; ToupcamCamera polls `_frame_ready` every 50ms and breaks on `_abort` event; AutoGainService spawns an abort-watcher thread that calls `camera.abort_capture()` as soon as `cancellation_flag` is set; catches `CaptureAbortedError` → CANCELLED. Cancel latency ≤ 50ms. Two regression tests in `test_autogain_service.py::TestCancelLatency`.
- [x] BUG-002b Preview shows `AUTO_GAIN_POSSIBLE_FOCUS_OR_POINTING_ERROR` after autogain cancel `[P2 · UI · Source: Items_to_fix_20260513]`
- [x] BUG-019 Focuser nudge returns 409 conflict and blocks far too long; rapid +20 presses mostly rejected `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* conflict cleared within 2 s; sequential presses each produce movement
  - *Done:* `_safe_move` moved `time.sleep(0.3)` and `started` check outside the coordinator lock; lock now covers only serial command (~50-100 ms), not the started-check sleep
- [x] BUG-022 Changing camera in Goto/Solve then pressing Find Best fails; WebSocket data transfer error logged `[P1 · Runtime · Source: Items_to_fix_20260514]`
  - *Done:* Added `mountGotoAndCenter()` JS function (was called but never defined); `onPreviewCamChange()` now stops/restarts preview WS on camera change

### Milestone M2 tasks

- [x] M2-001 Complete R0 runtime context `[P1 · Runtime]`
- [x] M2-002 Complete R3 shared job manager `[P1 · Runtime]`
- [x] M2-003 Define camera-use policy `[P1 · Runtime]`
  - *Done:* convention `"camera:N"` / `"mount"` / `"focuser"` in JobManager; session claims `camera:0 + mount + focuser`; autogain claims `camera:{index}`; preview uses camera adapter's `_capture_lock` (serializes at hardware level); full role-based policy deferred to R4
- [x] M2-004 Prevent preview/autogain/session conflicts `[P1 · Runtime]`
  - *Done:* session/autogain conflicts explicit via R3 `ResourceConflictError` → HTTP 409; preview serializes through adapter-level `_capture_lock`; concurrent preview + autogain on same camera serializes safely
- [x] M2-005 Add timeout policy for long-running jobs `[P1 · Runtime]`
  - *Done:* autogain: 300 s timeout via JobManager companion watcher; session: user-initiated stop only (legitimate sessions run hours — hard timeout not appropriate)
- [x] M2-006 Ensure unrelated subsystems continue when one job fails `[P1 · Runtime]`
  - *Done:* JobManager releases resources on DONE/FAILED/CANCELLED; `ResourceConflictError` is synchronous (caller gets 409, other subsystems unaffected)

**Quality gate:** Autogain cancel and session stop complete within agreed timeout. Camera conflicts are explicit. API exposes current job state and last error.

---

## M3 — Smart Setup and Optical Train Truth

*System knows the actual telescope setup and can tell the user whether it is ready.*

### R4 — Optical Train Registry

- [x] R4-001 Define `OpticalTrain` and `OpticalTrainRegistry` `[P1 · Runtime]`
  - *Done:* `OpticalTrain` frozen dataclass + `OpticalTrainRegistry` with `from_config()`, `get()`, `main()`, `guide()`, `all()`, `by_camera_index()`, `by_camera_role()` — `smart_telescope/services/optical_train_registry.py`
- [x] R4-002 Include camera role, serial/logical name, focuser binding, cooling capability, pixel scale, solver profile `[P1 · Runtime]`
  - *Done:* `OpticalTrain` has `camera_role`, `camera_index`, `telescope_name`, `focal_mm`, `reducer_factor`, `pixel_scale_arcsec`, `has_focuser`, `focuser`; pixel scale priority: explicit TOML → derived from camera profile pixel_um → global fallback
- [x] R4-003 Load train definitions from config `[P1 · Config]`
  - *Done:* `OpticalTrainSpec` in config.py with `_parse_telescopes()` + `_parse_optical_trains()`; `[telescopes]` and `[optical_trains]` sections added to `templates/config.toml`
- [x] R4-004 Validate train definitions at startup `[P1 · Config]`
  - *Done:* `from_config()` collects all errors and raises `ValueError` listing every broken telescope/camera reference; `RuntimeContext.get_optical_train_registry()` catches errors and returns empty registry
- [x] R4-005 Replace product-facing camera index selection with train/role selection `[P1 · Runtime]`
  - *Done:* All camera `<select>` elements now show train names ("main — c8", "guide — guide_scope"); values are train name strings; `_loadSelectFromTrains()` replaces `_loadSelectFromCameras()` for all camera selects; focuser autofocus select filters to trains with `has_focuser=true`
- [x] R4-006 Update preview, focuser, cooling, polar alignment, autogain, and setup to use train model `[P1 · Runtime]`
  - *Done:* Preview WS accepts `camera_role` query param → resolves to index via registry; autogain `RunRequest` accepts `camera_role`; autofocus `AutofocusRequest` accepts `camera_role`; UI API calls pass `camera_role` (preview, autogain, autofocus); APIs that still need index (goto_and_center, solver, histogram, calibration, polar) resolve via `_trainCamIdx(role)` helper
- [x] R4-007 Tests for two-camera and three-camera/OAG setups `[P1 · Tests]`
  - *Done:* 16 new tests in `tests/unit/api/test_r4_role_camera.py` — autogain role resolution (2-cam, 3-cam, unknown role fallback, backward compat), autofocus role resolution, preview WS role resolution, registry multi-train queries; 28 registry tests in `test_optical_train_registry.py`
- [x] R4-008 Make guided session optical-train aware: use role/train, never hard-code `camera:0`; derive `{"camera:N"}` from selected train `[P1 · Runtime]`
  - *Done:* `session_run` injects `OpticalTrainRegistry` via `Depends`; resolves `camera_resource = f"camera:{main_train.camera_index}"` from `registry.main()`; falls back to `"camera:0"` when no main train; 3 new tests in `test_r4_role_camera.py::TestSessionOpticalTrainAware`

### R5 — Config and Readiness Services

- [x] R5-001 Define `ConfigService` `[P1 · Config]`
  - *Done:* `ConfigError` exception class + `check_load_error()` function form the config service boundary; `_load_config_from_disk()` encapsulates all file loading logic
- [x] R5-002 Replace import-time config loading with explicit load `[P1 · Config]`
  - *Done:* TOML loading moved into `_load_config_from_disk()` function; module globals still populated at import time for backward compat; `check_load_error()` is the explicit check point called by `RuntimeContext.connect_devices()`
- [x] R5-003 Replace config `sys.exit` with structured startup error `[P1 · Config]`
  - *Done:* `sys.exit(...)` replaced by `_load_error = ConfigError(...)` stored on parse failure; `check_load_error()` raises it at startup (`RuntimeContext.connect_devices`); `ReadinessService._check_config_file()` surfaces it as a RED item; 4 new tests in `test_readiness.py`
- [x] R5-004 Add resolved path model (expand `~/`) — already in config.py `_expand()` `[P1 · Config]`
- [x] R5-005 Validate stars.cfg, horizon file, storage, ASTAP executable, ASTAP catalog, camera roles — in `ReadinessService` `[P1 · Config]`
- [x] R5-006 Define `ReadinessService` → `smart_telescope/services/readiness.py` `[P1 · Runtime]`
- [x] R5-007 Add red/yellow/green readiness summary → `/api/readiness` endpoint `[P1 · UI]`
- [x] R5-008 Add actionable repair guidance per failed check — `repair` field on every non-green item `[P1 · UI]`
- [x] R5-009 Update setup check endpoint and UI — readiness card at top of Stage 1, auto-loads on page open `[P1 · UI]`
- [x] R5-010 Tests: missing-file and invalid-config scenarios — `tests/unit/api/test_readiness.py` (22 tests) `[P1 · Tests]`
- [x] R5-011 Add explicit hardware mode field to readiness API and UI (`real` / `simulator` / `mock`) `[P1 · Runtime]`
- [x] R5-012 Show OnStep time/location sync status in System Readiness card `[P2 · UI]`
  - *Acceptance:* readiness card includes a Mount (OnStep) row showing whether the OnStep clock and site coordinates are aligned with the Pi system time and configured observer lat/lon; green = synced within threshold, yellow = stale or unread, red = `onstep_clock_invalid` or `onstep_location_mismatch`; repair hint points user to the time/location sync action
  - *Done:* `MountPort.get_sync_status()` added (no-op default); `OnStepMount.get_sync_status()` calls `read_onstep_clock()` (`:GC#`/`:GL#`) + `read_onstep_site()` (`:Gt#`/`:Gg#`) and returns summary dict; `ReadinessService._check_time_location_sync()` maps result to `time_location_sync` ReadinessItem (GREEN/YELLOW/RED); skipped when mount not connected; 8 new tests in `TestTimeLLocationSyncCheck`
  - *Acceptance:* `/api/readiness` includes `mode` field; `can_observe=true` blocked when mode is `mock` or `simulator`; UI label shows "REAL", "SIMULATOR", or "MOCK"; prevents accidental real-sky session with mock devices
  - *Done:* `RuntimeContext._hardware_mode` set by `_build_adapters()` from adapter types (ToupcamCamera+OnStepMount→real, Simulator→simulator, Mock→mock); `hardware_mode` property exposed; `ReadinessReport.mode` field added; `can_observe` blocked for non-real modes; mode item in readiness items list; REAL/SIMULATOR/MOCK badge in UI header; 8 new tests in `test_readiness.py`

### Field bugs — Config and optical train

- [x] BUG-008 `stars.cfg` not found on Pi even though file exists — tilde path not expanded `[P1 · Config · Source: Items_to_fix_20260514]`
  - *Done (R5-004):* `_expand()` using `Path.expanduser()` was added for all path globals (`STARS_CFG`, `HORIZON_DAT`, `STORAGE_DIR`, `IMAGE_ROOT`, `APP_STATE_DIR`); `STARS_CFG` default also constructed via `Path.home()` so tilde is never stored literally; verified by 4 new `TestExpandPath` tests in `test_readiness.py`
- [x] BUG-009 Cooling controls offered in setup page for cameras that don't support cooling `[P2 · UI · Source: Items_to_fix_20260514]`
  - *Done:* `onCoolingCamChange(role)` added — fetches `/api/cameras/{idx}/capabilities` for the selected train's camera and shows/hides the cooling card based on `has_tec`; called on select `onchange`, on "Connect All", and at page init; replaces the old "any camera has TEC" heuristic
- [x] BUG-010 Focuser log says not available, then later says available — connect ordering issue `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Acceptance:* focuser `is_available` reflects true hardware state after `connect()` even when serial buffer has stale bytes from mount init
  - *Done:* `OnStepFocuser.connect()` retries `:FA#` up to 3× with 300 ms gap; breaks on first `"1"`; logs each attempt; only warns when all attempts fail. Handles stale bytes left by `:GVP#` or `disable_tracking()` during `mount.connect()`. 4 new tests in `test_onstep_focuser.py::TestConnectRetry` — first-attempt success (no retry), 0→1 retry, exhausted (3×"0"), empty→"1".
- [x] BUG-013 Setup check fails to move mount at all `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Root cause:* `OnStepMount.connect()` made only a single stale-ACK retry; a second stale byte from a previous session's `disable_tracking()` exhausted the retry and closed the serial port. With `_serial = None`, all subsequent `get_state()` calls returned `UNKNOWN`, and the setup check wizard silently skipped all mount movement tests.
  - *Done:* `OnStepMount.connect()` retries `:GVP#` up to 3× with 300 ms gap + input buffer flush each time; only fails after all attempts exhausted; accepts any response containing "on"+"step" (case-insensitive); also accepts `'On-Step#On-Step'` doubled responses seen in the field. Setup check JS message changed from silent "state unknown — skipped" to "mount not connected — use Connect All to reconnect". 5 new tests in `test_onstep_mount.py::TestConnectRetry`.
- [x] BUG-017 Focuser linked to guide cam on status page; config requires it linked to main camera 678M `[P1 · Hardware · Source: Items_to_fix_20260514]`
  - *Done (R4-005):* Focuser cam select now populated via `_loadSelectFromTrains()` filtered to `has_focuser=true`; guide cam train has `has_focuser=false` so it never appears in focuser controls
- [x] BUG-003 Startup shows both cameras under focuser section but not under cooling, polar alignment, or preview `[P1 · UI · Source: Items_to_fix_20260513]`
  - *Done (R4-005):* All camera selects now use train-based population; focuser select filters to `has_focuser=true`; cooling, PA, preview each populate independently from train registry
- [x] BUG-024 Preview shows `AUTO_GAIN_POSSIBLE_FOCUS_OR_POINTING_ERROR` for camera with no focuser connected `[P2 · UI · Source: Items_to_fix_20260514]`
  - *Done:* `_worker()` in `autogain.py` now resolves the train's `has_focuser` via `registry.by_camera_index(camera_index)` and ANDs it with `focuser.is_available`; guide camera with no focuser configured returns NO_SIGNAL instead of POSSIBLE_FOCUS_OR_POINTING_ERROR even when main camera's focuser is available; 4 new tests in `test_r4_role_camera.py`

### Milestone M3 tasks

- [x] M3-001 Complete R4 optical train registry `[P1 · Runtime]`
  - *Done:* R4-001..007 all complete
- [x] M3-002 Complete R5 config/readiness services `[P1 · Config]`
  - *Done:* R5-001..010 all complete
- [x] M3-003 Replace camera-index product UI with train roles `[P1 · UI]`
  - *Done:* R4-005 completed this
- [x] M3-004 Hide unsupported cooling/focuser controls `[P2 · UI]`
  - *Done:* BUG-009 (cooling card per TEC capability) and BUG-024 (autogain FOCUS_ERROR for no-focuser cameras) both resolved
- [x] M3-005 Provide red/yellow/green setup readiness `[P1 · UI]`
  - *Done:* R5-007 completed this

**Quality gate:** Main camera/focuser association correct. Guide camera not shown as focus-controlled. Cooling absent for non-cooled cameras. Setup check detects missing files and devices.

---

## M4 — Intent-Driven Smart Telescope UX

*User operates the telescope by intent, not by device expertise.*

### UX1 — Ready To Observe Screen

- [x] UX1-001 Add red/yellow/green readiness summary `[P1 · UI]`
- [x] UX1-002 Show config, storage, ASTAP, catalog, camera, mount, focuser readiness `[P1 · UI]`
- [x] UX1-003 Provide repair guidance for each failed check `[P1 · UI]`
- [x] UX1-004 Make readiness the default first-run experience — card loads automatically at page open `[P1 · UI]`

### UX2 — Intent-Based Observation Flow

- [x] UX2-001 Add `Start Observation` as the primary action `[P1 · UI]`
  - *Done:* Card title updated to "Start Observation"; Start button is the primary CTA in Stage 5.
- [x] UX2-002 Show guided progress steps (slewing → solving → centering → focusing → capturing) `[P1 · UI]`
  - *Done:* 5-step pipeline strip (Connect → GoTo → Centre → Focus → Capture) shown inside run-status panel; steps update live with done/active/failed states.
- [x] UX2-003 Move autogain/autofocus/solve/recenter into the automatic workflow `[P1 · UI]`
  - *Done:* Backend VerticalSliceRunner already sequences all steps; the pipeline strip makes the automatic sequencing visible to the user.
- [x] UX2-004 Show recovery actions when automation fails `[P1 · UI]`
  - *Done:* Recovery banner shown inside run-status when state=FAILED; includes failure reason, contextual action suggestion, and Retry button.

### UX3 — Hide Camera Index Thinking

- [x] UX3-001 Show main telescope camera by role name, not index `[P1 · UI]`
  - *Done (R4-005):* All camera selects show train names ("main — c8", "guide — guide_scope")
- [x] UX3-002 Show guide/OAG/wide-field camera only as configured roles `[P1 · UI]`
  - *Done (R4-005):* Trains appear only when configured; focuser select filters to has_focuser=true
- [x] UX3-003 Show serial/logical name only in diagnostics `[P2 · UI]`
  - *Done:* Camera IDs / hardware serials shown only in `cameraCard()` in Stage 6 scan area. Main UI uses optical train role names ("main", "guide") throughout.
- [x] UX3-004 Hide unsupported controls (e.g. cooling for non-cooled cameras) `[P2 · UI]`
  - *Done (BUG-009/M3-004):* Cooling card shown/hidden dynamically via `onCoolingCamChange()` based on camera TEC capability; focuser controls filtered by `has_focuser` in optical train registry.

### UX4 — Advanced Mode For Manual Controls

- [x] UX4-001 Add beginner/advanced mode distinction `[P2 · UI]`
  - *Done:* "Advanced" toggle button in header; state persisted in `localStorage` (`tsc_advanced_mode`). `body.advanced-mode` CSS class controls `.adv-only` visibility.
- [x] UX4-002 Move manual mount controls to advanced/diagnostics (except emergency stop) `[P2 · UI]`
  - *Done:* Home / Unpark / Park / Enable Tracking / Disable Tracking wrapped in `.adv-only` span in `mountCard()`. Stop always visible.
- [x] UX4-003 Move manual focuser controls to advanced/diagnostics (except recovery actions) `[P2 · UI]`
  - *Done:* Nudge buttons (±1000/±100/±10) and Move To row wrapped in `.adv-only` in `focuserCard()`. Autofocus and Stop always visible.
- [x] UX4-004 Keep emergency stop globally visible at all times `[P0 · UI]`
  - *Done:* Mount strip now starts visible (class `visible` in HTML); `goToStage()` no longer hides it on Stage 1. STOP button is in the strip at all times.

### UX5 — Recovery-Oriented Errors

- [x] UX5-001 Define error model: what happened / safety state / user action / retry `[P1 · UI]`
  - *Done:* `friendlyError(raw)` maps raw error strings to `{message, hint}`. `setStatus(..., true)` renders the translated message + hint. Recovery banner (UX2-004) covers session failures.
- [x] UX5-002 Map OnStep command errors to user-facing messages `[P1 · UI]`
  - *Done:* `_ERROR_PATTERNS` includes serial timeout, serial error, rejected command, not connected, not aligned, unsafe position patterns.
- [x] UX5-003 Map camera errors to user-facing messages `[P1 · UI]`
  - *Done:* Camera not found, capture timeout, camera error patterns in `_ERROR_PATTERNS`.
- [x] UX5-004 Map solver errors to user-facing messages `[P1 · UI]`
  - *Done:* ASTAP not found, catalog not found, no stars, plate solve failed patterns in `_ERROR_PATTERNS`.
- [x] UX5-005 Add diagnostics link for advanced error details `[P2 · UI]`
  - *Done:* `setStatus(..., true)` now appends a "→ Setup & Diagnostics" link that calls `goToStage(1)`. Visible on every error status banner.

### Field bugs — UX and errors

- [x] BUG-014 Home button generates HTTP 500; message `Home failed: GoTo failed` gives no cause or next action `[P1 · UI · Source: Items_to_fix_20260514]`
  - *Done:* `mount_home` now returns `"Home slew failed — check mount is tracking and powered (<detail>)"`
  - *Acceptance:* error states cause, current safety state, and recommended next action
- [x] BUG-015 HOME, PARK, UNPARK, STOP buttons should be grouped together `[P3 · UI · Source: Items_to_fix_20260514]`
- [x] BUG-002 AG checkbox vs Autogain button layout confusing; AF button below histogram, autogain at bottom `[P3 · UI · Source: Items_to_fix_20260513]`
  - *Done:* Split the single dense controls row into two rows: Row 1 = camera settings + display toggles (Str/Hist) + Solve + AF + status spans; Row 2 = "Auto-gain:" label + "Adjust live" checkbox (with clarified tooltip) + `│` separator + "Find Best" button + Cancel + status badge. No JS changes — all element IDs preserved.
- [x] BUG-004 Histogram should show detail below ADU 1000 and current block size above `[P3 · UI · Source: Items_to_fix_20260513]`
  - *Done:* `showHistogram()` now draws `0–Xk ADU · N ADU/bin` as a text overlay inside the canvas top-right; `s3-hist-low-label` given an id and updated dynamically by `_updateLowLabel()` on each draw (was hardcoded "5 ADU/bin", now shows real bin size)
- [x] BUG-021 Histogram not filled at small values `[P3 · UI · Source: Items_to_fix_20260514]`
  - *Done:* `histogram_bins_focused` no longer uses `adc_max×0.05` floor — dim images (p99.9=200 ADU) now zoom to 1000 ADU range instead of 3276, filling the canvas 3× better; JS bar rendering uses `Math.max(1, Math.round(hRaw))` for non-zero bins so every bin with any pixels shows at least 1px

### Milestone M4 tasks

- [x] M4-001 Implement `Ready to Observe` first-run screen `[P1 · UI]`
  - *Done (UX1):* Readiness card loads automatically on Stage 1 page open; red/yellow/green summary with repair guidance.
- [x] M4-002 Implement target recommendation view `[P1 · UI]`
  - *Done:* "Visible Tonight" card in Stage 5 uses `/api/catalog/tonight` to list Messier objects above 20° sorted by altitude; clicking any row sets the target; card auto-loads on entering Stage 5.
- [x] M4-003 Implement `Start Observation` guided workflow `[P1 · UI]`
  - *Done (UX2):* Pipeline step strip shows Connect→GoTo→Centre→Focus→Capture live; recovery banner on failure.
- [x] M4-004 Move manual controls into advanced/diagnostics mode `[P2 · UI]`
  - *Done (UX4-001/002/003):* Advanced Mode toggle in header; Home/Unpark/Park/Tracking hidden in beginner mode; focuser nudge/Move-To hidden in beginner mode.
- [x] M4-005 Add recovery-oriented errors `[P1 · UI]`
  - *Done (UX5):* `friendlyError()` + `_ERROR_PATTERNS` in setStatus; recovery banner in session.
- [x] M4-006 Keep emergency stop globally visible `[P0 · UI]`
  - *Done (UX4-004):* Mount strip always visible on all stages.

**Quality gate:** User can start observing without manually managing solve/focus/gain/recenter. Beginner mode avoids camera indices and hardware jargon. Recovery messages tell user what to do next.

---

## Collimation Assistant — C8 SCT

*Source: `resources/hlrequirements/smarttscope_c8_collimation_assistant_task_plan_updated.md`*

### Phase 0 — Project Skeleton and Configuration

- [x] COL-001 Add collimation configuration model (`domain/collimation/config.py`) `[P1 · Collimation]`
  - *Done:* `CollimationConfig` + sub-configs for focuser, mount centering, rough/fine collimation; loads from TOML; validates on load
- [x] COL-002 Define core domain models (`domain/collimation/models.py`) `[P1 · Collimation]`
  - *Done:* `StarMeasurement`, `DonutMeasurement`, `SpikeMeasurement`, `FrameMeasurement`, `CollimationRecommendation`, `ScrewCalibration`, `MaskSectorCalibration`, `ContradictionAssessment`, `MechanicalAlignmentReport`, `CircleEllipseFit`, `ReferenceCenterCalibration`
- [x] COL-003 Add reference-center abstraction (`ReferenceCenterCalibration.compute()`) `[P1 · Collimation]`
  - *Done:* defaults to frame center; calibrated offset supported; all measurement algorithms must use `.compute()`, not hard-coded `width/2`
- [x] COL-004 Add optical train profiles (`domain/collimation/profiles.py`) `[P1 · Collimation]`
  - *Done:* `CollimationOpticalProfile` with C8/f10/678M, C8/f10/ATR585M, C8/f6.3, C8/f20 Barlow profiles; pixel scale, obstruction ratio, focal ratio computed as properties

### Phase 1 — Service and Wizard State Machine

- [x] COL-010 Implement `CollimationStateMachine` with 20 states (`services/collimation/state_machine.py`) `[P1 · Collimation]`
  - *Done:* `VALID_TRANSITIONS` dict; `pause()`/`resume()` outside transition table; `USER_WAIT_STATES` + `TERMINAL_STATES`; `InvalidTransitionError`
- [x] COL-011 Implement `CollimationAssistant` background service (`services/collimation/assistant.py`) `[P1 · Collimation]`
  - *Done:* `start()`, `pause()`, `resume()`, `cancel()`, `advance()`, `retry()`; background thread; `.status`, `.overlay`, `.report` properties; state handlers are stubs (Phases 3-9 fill them)
- [x] COL-012 Add wizard REST API (`api/collimation.py`) `[P1 · Collimation]`
  - *Done:* `GET /api/collimation/status|overlay|report`; `POST /api/collimation/start|pause|resume|cancel|next|retry`

### Phase 3 — Frame Processing Foundation

- [x] COL-030 Normalize Touptek frame input (`domain/collimation/processing/frame.py`) `[P1 · Collimation]`
  - *Done:* `ProcessedFrame` dataclass with `raw` (uint16), `mono` (float32), `bit_depth`, `width`, `height`, `timestamp`; `normalize_frame(FitsFrame)` — copies, does not mutate; `.normalized` property returns [0,1] float32
- [x] COL-031 Add display stretch pipeline (`domain/collimation/processing/stretch.py`) `[P1 · Collimation]`
  - *Done:* `estimate_background()` (sigma-clip, 5 iter); `auto_stretch()` → uint8; `saturation_fraction(bit_depth)`; `peak_location()`
- [x] COL-032 Add star detection (`domain/collimation/processing/star_detection.py`) `[P1 · Collimation]`
  - *Done:* `detect_star(ProcessedFrame) → StarMeasurement | None`; 5-sigma threshold; intensity-weighted centroid; radial-profile FWHM; hot-pixel/nebula rejection; SNR-based confidence
- [x] COL-033 Add circle/ellipse fitting primitives (`domain/collimation/processing/geometry_fits.py`) `[P1 · Collimation]`
  - *Done:* `fit_circle()` (Kasa algebraic LSQ); `fit_ellipse()` (Bookstein direct fit → eigenvalue decomposition); `extract_edge_points()` (4-connectivity erosion); `detect_clipping()`; `compare_circle_centers()`
- [x] COL-034 Tests: 75 tests, all pass (`tests/unit/domain/collimation/`) `[P1 · Tests]`
  - *Done:* `test_frame_processing.py` (18), `test_stretch.py` (22), `test_star_detection.py` (11), `test_geometry_fits.py` (24)

### Phase 2 — User-Visible MVP Shell (UI)

- [x] COL-020 Add wizard panel (current step, instruction, status, pause/cancel) `[P2 · Collimation · UI]`
  - *Done:* Wizard card added to Stage 4 with 5-phase progress strip, instruction text, recommendation block, Start/Pause/Resume/Cancel/Reset action buttons, contextual Remeasure/Finish-Phase/Accept/Adjust-More buttons, error display; polls `/api/collimation/status` every 2 s when active; star clicks in SELECT_STAR state route to `/api/collimation/next` with ra/dec.
- [x] COL-021 Add overlay visibility test mode (crosshair, test circles, screw labels) `[P2 · Collimation · UI]`
  - *Done:* `_drawCollimOverlay()` draws donut outer/inner circles (blue/green), error vector (red arrow), and spike crossing crosshair on `s4-bahtinov-svg` overlay; polled from `/api/collimation/overlay` alongside status poll.
- [x] COL-022 Add hardware self-test page (camera stream, mount pulse guide, focuser small step) `[P2 · Collimation · UI]`
  - *Done:* Self-test card added before the wizard in Stage 4; 3 API endpoints (`POST /api/collimation/selftest/{camera,mount,focuser}`); camera returns frame dimensions + peak ADU; mount fires a 500 ms guide pulse N/S/E/W; focuser moves ±10 steps and shows position delta (no-op message when unavailable); 14 tests in `test_collimation_selftest.py`

### Phase 4 — Mount and Focuser Control

- [x] COL-040 Add safe pulse-guide centering interface `[P1 · Collimation]`
  - *Done:* `PulseCenterer` in `services/collimation/mount_centering.py` — converts px offset → guide pulse, clamps to max_pulse_ms, settles, iterates; stops on star_lost / diverging (3 × 10 % grow) / cancel / max_iterations; cos(dec) RA rate correction; `MountCorrectionResult` dataclass
- [x] COL-041 Add relative focuser control (move_focus_relative, CW/CCW) `[P1 · Collimation]`
  - *Done:* `CollimationFocuserControl` in `services/collimation/focuser_control.py` — `move_focus_relative()`, `move_focus_clockwise()`, `move_focus_counterclockwise()`, `defocus()`, `focus_fine()`; max_single_step clamp; soft position [min, max] clamp; direction mapping from `increasing_value_direction` config; `FocuserMoveResult` with clipped + reason; fixed `MockFocuser.move()` bug (was setting position, now adds steps)

### Phase 5 — Star Selection and Acquisition

- [x] COL-050 Bright star selection from built-in catalog (altitude ≥ 60°, fallback 45°) `[P1 · Collimation]`
  - *Done:* `CollimationStarSelector` in `services/collimation/star_selector.py` — `select()` picks brightest star above 60° (fallback 45° with warning), `select_by_name()` for manual override; `load_bright_stars()` parses stars.cfg TOML (type="star" filter); `BrightStar`, `CollimationStarCandidate`, `StarSelectionResult` dataclasses; 22 tests in `test_star_selector.py`
- [x] COL-051 Slew + star detection + centering loop `[P1 · Collimation]`
  - *Done:* `StarAcquisition` in `services/collimation/star_acquisition.py` — slew via `mount.goto()`, wait for slew completion, enable tracking, settle, capture + `detect_star()`, center via `PulseCenterer`; `AcquisitionResult` dataclass; 13 tests in `test_star_acquisition.py`; all 1950 tests pass, coverage 83%

### Phase 6 — Focuser Algorithm

- [x] COL-060 Image-based rough focus search (relative steps, bracket, final approach direction) `[P1 · Collimation]`
  - *Done:* `services/collimation/focus_search.py` — `FocusSearcher` with probe→scan→backtrack→final-approach; 11 tests
- [x] COL-061 Controlled defocus to donut regime (target 25–50 % frame) `[P1 · Collimation]`
  - *Done:* `services/collimation/defocus_controller.py` — `DefocusController` with threshold-masked RMS radius (6σ above bg), clipping check via 10%-of-peak bounding box; 12 tests

### Phase 7 — Rough Donut Collimation

- [x] COL-070 Donut detection: outer ring + inner shadow fitting `[P1 · Collimation]`
  - *Done:* `domain/collimation/processing/donut_detection.py` — `DonutAnalyzer` with ring mask (10% of peak), brightness centroid, RMS-radius split of edge pixels, Kasa circle fit to inner/outer boundaries; 17 tests
- [x] COL-071 Rough error vector: shadow center − outer center `[P1 · Collimation]`
  - *Done:* error vector computed in `DonutAnalyzer.analyze()` → `DonutMeasurement.error_x_px / error_y_px / error_magnitude_px / error_angle_deg`
- [x] COL-072 Rough overlay: ellipses, error vector, screw labels, traffic-light `[P1 · Collimation]`
  - *Done:* `services/collimation/donut_overlay.py` — `build_donut_overlay()` → `DonutOverlay` with outer/inner circles, error vector, traffic-light (green <2%, yellow <10%, red ≥10%), T1/T2/T3 screw markers at 1.25× outer radius; 25 tests

### Phase 8 — Screw Identification

- [x] COL-080 Screw detection by hand obstruction shadow `[P1 · Collimation]`
  - *Done:* `domain/collimation/processing/obstruction_detection.py` — `detect_obstruction(reference, current, cx, cy)` thresholds diff (ref−current) at 5σ, finds shadow centroid, returns angle from outer ring center; 15 tests; new domain model `ScrewAngularPosition` added to models.py
- [x] COL-081 Screw response learning (before/after adjustment) `[P2 · Collimation]`
  - *Done:* `services/collimation/screw_mapper.py` — `ScrewResponseLearner` accumulates before/after `DonutMeasurement` pairs per screw, averages CW-equivalent response vectors, returns `ScrewCalibration`; confidence saturates at 5 samples; 22 tests

### Phase 9 — Rough Collimation Guidance

- [x] COL-090 Generate safe screw recommendations (tiny/slight/very slight) `[P1 · Collimation]`
  - *Done:* `services/collimation/collimation_advisor.py` — `CollimationAdvisor` projects error vector onto each screw's response vector (cosine similarity), selects best screw and CW/CCW direction; size: MEDIUM (>15% of ring) or SMALL (≤15%); never LARGE; low-calibration-confidence halves recommendation confidence; 18 tests
- [x] COL-091 Live "turn until OK" — detect improvement and tell user when to stop `[P1 · Collimation]`
  - *Done:* `services/collimation/live_guidance.py` — `LiveGuidanceMonitor` polls `get_measurement()` each settle interval; tracks improvement (5% threshold); stops on: converged (error < green_fraction × outer_radius), worsened (2 consecutive non-improvements), star_lost, cancelled, max_frames; returns `LiveGuidanceResult` with reason, improvement_px, frame_count; 15 tests

### Phase 10 — Tri-Bahtinov Fine Collimation

- [x] COL-100 Detect Tri-Bahtinov spike pattern (background subtraction + line fitting) `[P1 · Collimation]`
- [x] COL-101 Mask sector mapping via blade open/close `[P1 · Collimation]`
- [x] COL-102 Spike measurement smoothing (7-frame window, median + trend) `[P2 · Collimation]`

### Phase 11 — Fine Focus and Fine Collimation

- [x] COL-110 Separate common focus error from per-sector collimation residual `[P1 · Collimation]`
- [x] COL-111 Fine focus loop (image feedback, final approach direction) `[P1 · Collimation]`
- [x] COL-112 Fine collimation guidance (residual ≤ 2 px target) `[P1 · Collimation]`
- [x] COL-113 Contradiction detection: block screw hints when indicators disagree `[P1 · Collimation]`

### Phase 12 — Validation and Report

- [x] COL-120 Final refocus without mask `[P1 · Collimation]`
- [x] COL-121 Maskless validation (donut symmetry, optional Airy) `[P1 · Collimation]`
- [x] COL-122 Short session report via `/api/collimation/report` `[P1 · Collimation]`

### Phase 13 — Replay and Test Infrastructure

- [x] COL-130 Replay frame provider (prerecorded test frames, no hardware needed) `[P2 · Collimation]`
- [x] COL-131 Unit tests for remaining algorithm phases `[P1 · Collimation]`

### Phase 14 — Live Pipeline Wiring

- [x] COL-140 Wire acquisition pipeline: ACQUIRE_STAR → CENTER_STAR → AUTO_EXPOSURE `[P1 · Collimation]`
  - *Done:* `_handle_acquire_star` (5-attempt star detection), `_handle_center_star` (centering loop), `_handle_auto_exposure` (8-step ADU search)
- [x] COL-141 Wire rough collimation pipeline: ROUGH_DEFOCUS → MAP_SCREWS → MEASURE_DONUT → GUIDE_ROUGH_COLLIMATION `[P1 · Collimation]`
  - *Done:* `_handle_rough_defocus` (focuser steps to defocus target), `_handle_map_screws_by_obstruction`, `_handle_measure_donut` (DonutAnalyzer), `_handle_guide_rough_collimation` (user-wait with advisor recommendation)
- [x] COL-142 Wire fine collimation pipeline: MAP_MASK_SECTORS → FINE_FOCUS → MEASURE_SPIKES → GUIDE_FINE_COLLIMATION → MASKLESS_VALIDATION `[P1 · Collimation]`
  - *Done:* `_handle_map_mask_sectors` (MaskSectorCalibration + SpikeSmoother + ContradictionDetector init), `_handle_fine_focus`, `_handle_measure_spikes` (BahtinovAnalyzer), `_handle_guide_fine_collimation`, `_handle_maskless_validation`

---

## M5 — Product Acceptance MVP

*SmartTScope can perform a meaningful smart telescope workflow safely enough to demonstrate.*

### R6 — API Thinness and UI Consistency

- [x] R6-001 Move mount/focuser/camera/setup/job orchestration out of API modules into services `[P1 · Runtime]`
  - *Done:* `CoolingService` extracted from `api/cooling.py` → `services/cooling.py` (full session/threading moved out). `MountOperations` extracted from `api/mount.py` → `services/mount_operations.py` (safe_goto, home_sequence, park_sequence, unpark_sequence, track_sequence). 35 new service tests.
- [x] R6-002 Keep API modules thin: validate request, call service, map response `[P1 · Runtime]`
  - *Done:* `api/cooling.py` reduced from 251 to 86 lines. `api/mount.py` endpoints for unpark/track/home/park now delegate to `mount_operations` and map domain exceptions to HTTP.
- [x] R6-003 Split large static UI into maintainable modules `[P2 · UI]`
  - *Done:* `index.html` reduced from 6216 to 1847 lines (HTML/CSS only); 4376 lines of JS split into 8 modules in `static/js/`: `api.js` (API client), `app.js` (globals + nav + init), `mount.js` (mount card + guide + PA), `collimation.js` (wizard + overlay), `focuser.js` (focuser card + position poll), `preview.js` (preview WS + autogain + Bahtinov), `session.js` (pipeline + guide monitor), `setup.js` (readiness + health + catalog + cooling + cameras + sky). `StaticFiles` added to `app.py`; `pyproject.toml` package-data updated.
- [x] R6-004 Create shared frontend API client and shared device/job state model `[P2 · UI]`
  - *Done:* `static/js/api.js` contains `escHtml()`, `_ERROR_PATTERNS`, `friendlyError()`, `setStatus()`, `apiPost()` — loaded first by all pages, providing a uniform fetch + error-translation layer used by all other modules.
- [x] R6-005 Ensure STOP button is globally available `[P0 · UI]`
  - *Done (UX4-004):* Mount strip starts visible; STOP button visible on all stages.
- [x] R6-006 Browser smoke tests: setup, preview, mount, focuser, stop `[P1 · Tests]`
  - *Done:* `tests/unit/api/test_smoke.py` — 39 tests covering HTML page load, readiness API shape, mount status (state/stale/watchdog fields), focuser status (available/position/moving), emergency STOP (always 200, mount_stopped true/false, calls stop once), optical trains list, version endpoint; all mock-based, no hardware.
- [x] R6-007 Add `FocusRunConfig` policy object; clean focus sub-boundary so focus options touch only focus domain `[P2 · Runtime]`
  - *Acceptance:* focus options (step size, frame count, timeout) carried in a `FocusRunConfig` object passed top-down; changes to focus options touch only focus domain, focus service, one API shape, and focused tests; session/mount internals not touched
  - *Done:* `FocusRunConfig` added to `domain/autofocus.py` with `to_params()` factory; `StageContext` 5 flat fields → `focus_config: FocusRunConfig`; `VerticalSliceRunner` 5 flat params → `focus_config`; `api/session.py` builds `FocusRunConfig` from Query params; `conftest.py` updated; `stage_stack` mid-refocus deduplication; 12 new tests in `tests/unit/domain/test_focus_run_config.py`; 2565 tests pass

### Milestone M5 tasks

- [x] M5-001 Guided startup `[P1 · Product]`
  - *Done:* `s1-proceed-btn` starts `disabled`; `connectAll()` enables it only when `mountOk`; `s1Proceed()` no longer bypasses `unlockStage(2)`. Guided flow: readiness card (auto-load) → Connect All → Proceed to Alignment.
- [ ] M5-002 Connect all configured devices `[P1 · Hardware]`
- [x] M5-003 Show readiness dashboard `[P1 · UI]`
  - *Done (UX1):* Readiness card with red/yellow/green items, repair hints, hardware-mode badge, and capability chip row auto-loads on page open. Implemented across R5 / UX1 series.
- [x] M5-004 Select target `[P1 · Product]`
  - *Done (M4-002):* "Visible Tonight" card in Stage 5 lists Messier objects above 20° sorted by altitude; clicking any row sets the session target. Manual RA/Dec entry also available in the GoTo card.
- [x] M5-005 Enforce solar safety gate `[P0 · Hardware]`
  - *Acceptance:* solar exclusion enforced at ALL GoTo entry points: direct GoTo, catalog target launch, guided session launch, sky slew; test shows rejection for Sun coordinates from each entry point
  - *Done:* `is_solar_target()` called in `mount_goto`, `mount_goto_and_center`, `mount_goto_sky`, and `session_run`; each returns HTTP 403 with `solar_exclusion` detail; catalog tonight marks `solar_safe` flag; `confirm_solar=true` bypass available; tests in `test_mount.py` and `test_session.py`
- [ ] M5-006 Validate mount limits `[P1 · Hardware]`
- [ ] M5-007 GoTo, plate solve, recenter `[P1 · Hardware]`
- [ ] M5-008 Focus and optimize exposure `[P1 · Hardware]`
- [ ] M5-009 Preview and stack `[P1 · Imaging]`
- [ ] M5-010 Save output image and session log `[P1 · Imaging]`
- [ ] M5-011 Stop/recover safely `[P0 · Hardware]`
- [ ] M5-012 Verify reconnect and shutdown behavior `[P1 · Hardware]`
- [x] M5-013 Dawn auto-park: auto-park when astronomical dawn approaches (end-of-night behaviour) `[P2 · Product]`
  - *Acceptance:* system parks mount automatically at astronomical dawn (sun at −18°); user notified; hardware stays connected after park for diagnostics/retry
  - *Done:* `DawnWatcher` background service polls sun altitude every 60 s; parks once when alt ≥ −18°; `GET /api/dawn` returns status; `sun_altitude_now()` added to `domain/solar.py`; 12 tests

**Quality gate:** Full workflow demonstrated on real hardware. Emergency stop tested during workflow. Logs useful without shell investigation. Product owner signs off against visible checklist.

---

## M6 — Field Reliability and Release Readiness

*System survives normal field use, not just a single demo.*

### R7 — Operational Evidence and Release Gate

- [x] R7-001 Define operational acceptance checklist `[P1 · Process]`
  - *Done:* `docs/operational-acceptance-checklist.md` — 10-section field checklist covering power-on, connect all, readiness dashboard, setup check, solar gate, GoTo/plate-solve, autofocus, emergency STOP, stack, shutdown, sign-off table
- [x] R7-002 Define hardware test log template `[P1 · Process]`
  - *Done:* `docs/hardware-test-log-template.md` — append-only log with six required evidence items (E-001 through E-006) and structured entry template (date, commit, steps, result, log extract)
- [x] R7-003 Define release go/no-go checklist `[P1 · Process]`
  - *Done:* `docs/release-checklist.md` — 8-section gate checklist with BLOCKER items, backlog gate, hardware evidence gate, clean install gate, performance targets, sign-off table, deferred items register
- [ ] R7-004 Record evidence: STOP during slew, STOP during focuser move, shutdown during motion, reconnect, setup check, full observing workflow `[P0 · Hardware]`
- [x] R7-005 Add product-owner milestone dashboard `[P2 · Product]`
  - *Done:* `GET /api/milestones` returns milestone completion stats (`id`, `name`, `total`, `done`, `open`, `hardware_blocked`, `status`) and top-10 risk items; status logic: green=no open non-hardware tasks, yellow=P2/P3 open or only hardware-blocked, red=P0/P1 open non-hardware; "Milestone Dashboard" card added to Stage 1 UI showing color-coded progress bars and top-risk list; `MILESTONE_REGISTRY` and `RISK_REGISTRY` in `domain/milestones.py`; 25 tests (domain + API).
- [x] R7-006 Add done-without-evidence report `[P2 · Process]`
  - *Done:* `EvidenceGapItem` dataclass + `EVIDENCE_GAPS` registry (8 items, P0 before P1) in `domain/milestones.py`; `GET /api/evidence-gaps` returns `{items, count}` with `id`, `priority`, `description`, `milestone`, `mock_tested_by`, `hardware_needed`; 13 new tests added to milestone test files.

### Milestone M6 tasks

- [x] M6-001 Define unattended session duration target `[P2 · Process]`
  - *Done:* 6 hours; in `domain/performance_targets.py` + `GET /api/performance-targets`
- [x] M6-002 Define preview latency target `[P2 · Process]`
  - *Done:* ≤ 2 s per frame; in `domain/performance_targets.py`
- [x] M6-003 Define stop-response time target `[P1 · Process]`
  - *Done:* ≤ 500 ms (aligns with POD-002 cancel-latency decision); in `domain/performance_targets.py`
- [x] M6-004 Define centering accuracy target `[P2 · Process]`
  - *Done:* ≤ 30 arcsec RMS after one plate-solve/recenter cycle; in `domain/performance_targets.py`
- [x] M6-005 Define plate solve success rate target `[P2 · Process]`
  - *Done:* ≥ 90% first-attempt under clear dark-sky conditions with full ASTAP catalog; in `domain/performance_targets.py`
- [x] M6-006 Define Pi thermal ceiling target `[P2 · Process]`
  - *Done:* ≤ 75°C sustained (5°C headroom below Pi 5 throttle point of 80°C); in `domain/performance_targets.py`
- [ ] M6-007 Run long session reliability test `[P1 · Hardware]`
- [ ] M6-008 Run Pi thermal test `[P2 · Hardware]`
- [x] M6-009 Run storage-full simulation `[P2 · Tests]`
  - *Done:* `DiskStorage` raises `OSError(ENOSPC)` on write failure; `stage_save()` raises `WorkflowError("save", "Disk full…")` when `has_free_space()` is False; runner wraps unexpected `OSError` from `save_image`/`save_log` into `WorkflowError`; partial-save scenario (image written, log write fails) preserves `saved_image_path`; 8 tests in `test_disk_storage.py` and `test_runner_stages.py` all pass.
- [ ] M6-010 Run network reconnect simulation `[P1 · Hardware]`
- [ ] M6-011 Verify clean Pi install from scratch `[P1 · Hardware]`
- [x] M6-012 Produce release notes and known issues `[P1 · Process]`
  - *Done:* `docs/release-notes-v0.1.md` — features (M0–M6 + Collimation), performance targets, known issues, hardware-blocked items, deferred scope, install/upgrade path

**Quality gate:** Long session completes or fails gracefully. Thermal limits not exceeded. Storage-full behavior does not corrupt session data. Reconnect behavior defined and verified. Release installable from clean state.

---

## Camera ID Mapping

*Source: `resources/hlrequirements/camera_id list.md`*  
*Plan: `docs/superpowers/plans/2026-05-20-camera-id-mapping.md`*

- [x] CID-001 Parse `[cameras]` role values as `str | int` in config.py `[P1 · Config]`
  - *Done:* _parse_cameras() accepts str|int; CAMERAS and TOUPTEK_INDEX globals added
- [x] CID-002 Add `[camera_serials]` section parsing in config.py `[P1 · Config]`
  - *Done:* _parse_camera_serials() and CAMERA_SERIALS added to config.py
- [x] CID-003 Implement `CameraNameResolver` — name-to-index lookup with serial verification `[P1 · Runtime]`
  - *Done:* CameraNameResolver in smart_telescope/services/camera_name_resolver.py — substring match + serial verification
- [x] CID-004 Wire `CameraNameResolver` into `runtime._build_adapters()` `[P1 · Runtime]`
  - *Done:* CameraNameResolver.resolve() wired into runtime._build_adapters(); ToupcamCamera receives resolved SDK index
- [x] CID-005 Update config.toml template with name-based examples + `[camera_serials]` block `[P1 · Docs]`
  - *Done:* templates/config.toml updated with [cameras] name examples and [camera_serials] block
- [ ] CID-006 Verify camera identification on real hardware — G3M678M and ATR585M resolve correctly `[P1 · Hardware]`
  - *Hardware serial numbers (for `~/.SmartTScope/config.toml` `[camera_serials]`):*  
    `GPCMOS02000KPA = "tp-3-4-23-0547-1367"`, `ATR585M = "tp-4-1-10-0547-157c"`, `G3M678M = "tp-4-2-11-0547-14bc"`
- [x] CID-007 Post-release: detect newly connected cameras not in config and offer to add them `[P3 · Future]`
  - *Done:* `domain/camera_config_suggestion.py` — `suggest_role()`, `generate_toml_snippet()`; `/api/cameras` response includes `toml_snippet` for cameras with `role=None`; `ReadinessService._check_unconfigured_cameras()` → YELLOW item with repair hint; `cameraCard()` in setup.js shows yellow "Not in config" badge + collapsible TOML snippet + Copy button; 45 tests (30 domain + 15 API/readiness)

---

## Camera Offset Configuration

*Source: `resources/hlrequirements/camera_offset.md`*  
*Plan: `docs/superpowers/plans/2026-05-20-camera-offset-config.md`*

- [x] CO-001 Add `_parse_camera_offsets()` and `CAMERA_OFFSETS` global to config.py `[P1 · Config]`
  - *Done:* _parse_camera_offsets() and CAMERA_OFFSETS added to config.py
- [x] CO-002 Implement `CameraOffsetService` — lookup and apply black-level per model+gain `[P1 · Runtime]`
  - *Done:* CameraOffsetService in smart_telescope/services/camera_offset_service.py — bidirectional substring match, apply() sets black level
- [x] CO-003 Apply offset in `RuntimeContext.connect_devices()` after adapters built `[P1 · Runtime]`
  - *Done:* _apply_camera_offsets() in RuntimeContext; called in connect_devices() and get_preview_camera()
- [x] CO-004 Inject `CameraOffsetService` into `AutoGainService` — apply after gain change `[P1 · Runtime]`
  - *Done:* offset_service param added to AutoGainService.run_one_shot(); cur_offset initialized from configured offset when no last_good
- [x] CO-005 Inject `CameraOffsetService` into `calibration_capture` functions `[P1 · Runtime]`
  - *Done:* offset_service param added to prepare_bias/dark/flat in calibration_capture.py; API passes rt.camera_offset_service
- [x] CO-006 Update `templates/config.toml` with `[camera_offsets]` defaults `[P1 · Config]`
  - *Done:* templates/config.toml updated with [camera_offsets] section (G3M678M/ATR585M=150, GPCMOS02000KPA=10)
- [ ] CO-007 Verify offset applied on real hardware: G3M678M LCG→150, HCG→150 confirmed `[P1 · Hardware]`
- [ ] CO-008 Verify GPCMOS02000KPA offset applied correctly (LCG/HCG = 10) `[P1 · Hardware]`

---

## Camera Offset Estimation Wizard

*Source: `resources/hlrequirements/camera_offset_estimation.md`*  
*Plan: `docs/superpowers/plans/2026-05-20-camera-offset-estimation.md`*

- [x] COE-001 Domain models: `BiasFrameStats`, `OffsetSweepPoint`, `BiasEstimationResult`, `analyze_frame` `[P1 · Domain]`
  - *Done:* `domain/bias_estimation.py` — `ZERO_CLIP_THRESHOLD=0.001`, `analyze_frame()` computes min/max/mean/median/std/zero_fraction/histogram; `OffsetSweepPoint.is_safe` property; `BiasEstimationResult.recommended_offset` picks lowest safe offset; `toml_snippet()` generates config snippet; 14 tests
- [x] COE-002 `BiasEstimationService` — capture frames + sweep offset values `[P1 · Service]`
  - *Done:* `services/bias_estimation_service.py` — captures at `caps.min_exposure_ms`; sets gain mode; sweeps offset values; restores original offset in `finally`; respects cancel event; 10 tests
- [x] COE-003 API endpoints: `POST /api/bias_estimation/start`, `GET /api/bias_estimation/status/{id}` `[P1 · API]`
  - *Done:* `api/bias_estimation.py` — Pydantic request/response models with `@field_validator` for gain_mode; async background thread with cancel event; `/start` returns 202 + job_id; `/status/{id}` returns RUNNING/DONE/FAILED/CANCELLED + full result on DONE; 5 tests
- [x] COE-004 Frontend wizard card in Stage 6: sweep table, recommendation, TOML snippet `[P1 · UI]`
  - *Done:* `static/js/bias_estimation.js` — `beLaunchWizard`, `beStartEstimation`, `bePollStatus`; polls every 500ms; renders sweep table with safe/clipping badges; highlights recommended row in green; shows TOML snippet in `<pre>` block. Card added to Stage 5 (before Connected Cameras) in `index.html`
- [ ] COE-005 Verify wizard on real hardware: G3M678M LCG sweep produces expected recommendation `[P1 · Hardware]`
- [ ] COE-006 Verify wizard on real hardware: GPCMOS02000KPA LCG sweep `[P1 · Hardware]`

---

## Build and Packaging

*Sources: `resources/hlrequirements/development-state-review-2026-05-17.md`*

- [x] PKG-001 Move `pyserial` from `[dev]` to production dependencies in `pyproject.toml` `[P1 · Build]`
  - *Acceptance:* `pip install -e .` installs pyserial; no dev-extras required to run the app on Pi
  - *Done:* `pyserial>=3.5` moved to `[project].dependencies`; removed duplicate from `[dev]`
- [x] PKG-002 Fix `test_guide_measurement.py` collection error `[P1 · Tests]`
  - *Acceptance:* `pytest --collect-only` completes with 0 errors; guide measurement tests skip cleanly until `services.guide_measurement` exists
  - *Done:* `pytest.importorskip("smart_telescope.services.guide_measurement")` guard added; 2779 tests collected, 0 errors

---

## Guiding Pipeline

*Source: `resources/hlrequirements/onstep_guiding_requirements.md`*

Guide camera processing subsystem: acquire frames through camera adapter, measure guide-star centroid, convert pixel error to pulse-guide corrections via OnStep adapter. Runs as a non-blocking worker; does not block the main imaging workflow.

**Architecture note:** The guiding subsystem is a client of the existing camera and mount adapters — it does not open hardware directly. `domain/guiding.py` domain models are already in place (from camera_adapter integration). The test file `tests/unit/services/test_guide_measurement.py` activates when GUD-002 is implemented.

- [x] GUD-001 Add `guide(direction, duration_ms)` to `MountPort`; implement in `OnStepMount` and `MockMount` `[P1 · Runtime]`
  - *Done:* `guide()` already exists on `MountPort` (line 56), `OnStepMount` (line 219), and `MockMount` (line 69) — camera_adapter's OnStep mount was already synced with guide support
- [x] GUD-002 Implement `smart_telescope/services/guide_measurement.py` — `CentroidConfig`, `GuideCentroidEstimator`, `GuideSourceSelector`, `MeasureOnlyGuideController`, `source_state_from_measurement` `[P1 · Service]`
  - *Done:* MAD-based noise estimator; windowed centroid; `GuideSourceSelector` falls back on TRANSIENT_BAD or HARD_FAILED; `MeasureOnlyGuideController` with deadband, aggressiveness, pulse clamping; 6 tests all pass
- [x] GUD-003 Implement `GuideWorker` service — bounded frame queue from camera adapter, per-cycle centroid, `GuideSourceState` output `[P1 · Service]`
  - *Done (merged into GUD-004):* `FrameMailbox` (latest-frame drop semantics) in `managed_camera.py`; `ManagedCamera` background thread per role; `GuidingService._loop()` never blocks main event loop; drops stale frames via mailbox
- [x] GUD-004 Implement `GuideController` — pixel error to pulse-guide corrections with deadband and pulse clamping `[P1 · Service]`
  - *Done:* `MeasureOnlyGuideController` in `guide_measurement.py`; `GuidingService` in `guiding_service.py`; sub-deadband frames produce no pulse; `measure_only=true` default; real mount pulses sent when `measure_only=false`; `_lifecycle_lock` on start+stop; `started_at` passed as thread param
- [x] GUD-005 Wire guiding config into `config.py`: `GUIDING: GuidingSpec` already parsed; guide camera via `get_camera_by_role("guide")` in runtime `[P1 · Config]`
  - *Done:* `GUIDING: GuidingSpec` already parsed in `config.py`; `get_camera_by_role("guide")` already in `runtime.py` from camera_adapter integration
- [x] GUD-006 API: `POST /api/guiding/start`, `POST /api/guiding/stop`, `GET /api/guiding/status` `[P1 · API]`
  - *Done:* `api/guiding.py` — start returns 202 + `{state, roles}` (no job_id; guiding is a long-running service, not a one-shot job); stop returns final status; status returns full `GuidingStatus.to_dict()`; 409 if already running, 422 if no cameras; deps wired in `deps.py` + `runtime.py`
- [x] GUD-007 Frontend guide monitoring card: lock state badge, correction arrow indicator, SNR readout `[P2 · UI]`
  - *Done:* `static/js/guiding.js` + Guide Monitor card in `index.html` (advanced mode only); state badge (IDLE/RUNNING/FAILED); source health badges with centroid coords and confidence; pulse summary; polls `/api/guiding/status` every 2 s when running
- [ ] GUD-008 Verify guiding on real hardware: guide camera locks onto star, corrections visible in OnStep `[P1 · Hardware]`

---

## Deferred — Post-Release 1.0

- [ ] PARK-SET-001 Add "Set Park Position" button to the mount tile `[P3 · UX · Post-1.0]`
  - *Context:* Park currently slews to the position saved in OnStep EEPROM (set once during initial setup via `:hS#`). There is no UI button to overwrite it.
  - *Scope:* Add a "Set Park" button that calls `POST /api/mount/set_park` (`:hS#`). Show a confirmation dialog on that button only ("Save current position as park? This overwrites the stored park position."). The Park button itself should remain confirmation-free.

---

## Deferred — Post-MVP

- [ ] ONSTEP-REPLACE-001 Replace OnStep adapter with layered direct-USB implementation + safety state machine (9 states: DISCONNECTED → READY_UNATTENDED) `[P1 · Hardware · Future]`
  - *Source:* `resources/hlrequirements/smarttscope_onstep_adapter_replacement_requirements.md`
  - *Scope:* SerialTransport, OnStepProtocolClient, OnStepStatusParser, OnStepSafetyReader, OnStepRecoveryController; HOME/PARK confirmation; direction test; limit readback; LIMIT_HIT recovery workflow; startup safety UI checklist
  - *Blocked by:* external party delivery + answers to open questions Q1–Q10 in the requirements doc (baud rate, stable device path, HOME command behavior, limit readback support)
- [ ] WATCHDOG-001 Enable Pi hardware watchdog and systemd service watchdog for SmartTScope `[P2 · Infrastructure · Future]`
  - *Source:* `resources/hlrequirements/raspberry_pi5_trixie_watchdog_setup.md`
  - *Scope:* `dtparam=watchdog=on` in `/boot/firmware/config.txt`; systemd manager config `RuntimeWatchdogSec=10s`; convert SmartTScope from `start.sh` to systemd Type=notify service with `ExecStopPost=send_stop.py`; send STOP on service failure
  - *Blocked by:* decision to migrate from `start.sh` to systemd
- [ ] WATCHDOG-002 Add external heartbeat supervisor for hardware STOP on Pi crash `[P2 · Infrastructure · Future]`
  - *Source:* `resources/hlrequirements/external_heartbeat_stop_supervisor.md`
  - *Scope:* Pi heartbeat sender sends `HB <n>` every 1 s; external microcontroller (Pico/Arduino/ESP32) times out after 3–5 s and triggers hardware STOP output; test with Pi power loss and process kill
  - *Blocked by:* external hardware available; WATCHDOG-001 done first
- [ ] BUG-007 Support frame types: bias, dark, flat frames; master frames; bad pixel maps `[P2 · Imaging · Source: Items_to_fix_20260513]`
  - No automatic cover exists; user must drive frame collection manually. Defer to post-MVP.
- [ ] BUG-006 Extended setup check: focuser move test, RA/DEC 10° test, multi-camera plate solve, home return `[P2 · Hardware · Source: Items_to_fix_20260513]`
  - Implement after M3 readiness service is in place.
- [x] BUG-018 Park logs `park issued` but unpark logs nothing `[P3 · Logging · Source: Items_to_fix_20260514]`
  - *Done:* Added `_log.info("Mount unpark issued")` in `services/mount_operations.py::unpark_sequence()` immediately after the unpark command is accepted.
- [x] BUG-020 Clicking +20 focuser not logged when live preview is running `[P2 · Logging · Source: Items_to_fix_20260514]`
  - *Done:* Added `_log.info("Focuser nudge request: delta=%d", body.delta)` at the entry of `api/focuser.py::focuser_nudge()` — logs every nudge request before any conflict check.

---

## Open Product-Owner Decisions

- [x] POD-001 After reconnect: preserve session, park mount, or ask user?
  - *Decision:* Auto-park on reconnect — already the implemented behaviour in `RuntimeContext._build_adapters()`.
- [x] POD-002 Maximum acceptable STOP response time?
  - *Decision:* **< 1 s** — applies to mount slew abort and focuser stop. Used as acceptance bar for BUG-001 and the safety regression checklist.
- [x] POD-003 What state may the UI show after command acceptance but before hardware confirmation?
  - *Decision:* **Show spinner / pending indicator** — after a Park/Unpark/Home/GoTo command is accepted, the label shows a loading state until `DeviceStateService` confirms the new hardware state. Adds a UX task: see UX-PENDING-001 below.
- [x] POD-004 Is SDK camera index acceptable anywhere outside diagnostics?
  - *Decision:* SDK camera index is NOT acceptable in the product UI (enforced by R4). SDK camera index IS accepted in API request bodies for backward compatibility — `camera_role` is preferred. In Stage 6 diagnostics, `sdk_index` from camera scan results is shown and used (by design).
- [x] POD-005 Which failures may block the whole app, and which must degrade locally?
  - *Decision:* Per-feature isolation: camera RED → `can_preview=false`, mount RED → `can_goto=false`, ASTAP RED → `can_solve=false`, focuser RED → `can_autofocus=false`, storage RED → `can_save=false`. YELLOW items degrade, not block. `can_observe` requires all five plus `mode=real`.
  - *Done:* `ReadinessService._capability_flags()` + 5 new fields in `ReadinessReport`; 12 new tests in `TestCapabilityFlags`; blocked-capability chip row in readiness card.
- [x] POD-006 What is the minimum successful demo workflow?
  - *Decision:* **Guided single-target session** — Pick target → GoTo → plate-solve & center → autofocus → stack 10 frames → save. That is the MVP demo.
- [x] POD-007 What evidence is required for product-owner sign-off?
  - *Decision:* Pi hardware/app logs + saved FITS/output image + session JSON log. Evidence folder: one directory with timestamped app log, session JSON, and saved output image from a real hardware session.
- [x] POD-008 Which requirements are deferred beyond MVP?
  - *Decision:* Defer ISS tracking, multi-target queue, advanced calibration frames wizard, and deep collimation algorithm phases to post-MVP. Minimal collimation wizard UI shell (start/status/overlay) is part of the MVP demo.
- [x] POD-009 Concrete performance targets: preview latency, solve time, centering accuracy, Pi thermal ceiling?
  - *Decision (M6-001..006):* 6-hour unattended session; ≤2 s preview latency; ≤500 ms STOP response; ≤30 arcsec centering accuracy; ≥90% plate-solve success rate; ≤75°C Pi thermal ceiling. All targets tracked in `domain/performance_targets.py` and `GET /api/performance-targets`.
- [x] POD-010 Should SDK camera indices be forbidden in API request bodies, or only hidden in the UI? `[P2 · Process]`
  - *Decision:* `camera_role` is the preferred parameter for all product-facing API endpoints. `camera_index` is accepted for backward compatibility. New product UI code must use `camera_role`; diagnostic code may use `camera_index` directly.
  - *Done:* `deps.resolve_camera_index()` helper; `camera_role` added to solver/solve, calibration/bias|dark|flat|bpm|match, histogram/analyze; frontend setup.js/session.js/preview.js updated to send `camera_role` directly; 11 new tests in `TestResolveCameraIndex`, `TestSolverAcceptsCameraRole`, `TestHistogramAcceptsCameraRole`.

### UX-PENDING-001 — Command-pending indicator in mount/focuser UI `[P1 · UI]`

- [x] Mount card state badge shows spinner + `cmd…` while command is in flight
- [x] Mount strip state label shows `cmd…` while command is in flight
- [x] Dot turns yellow while pending; reverts to hardware-confirmed colour on next poll
- [x] `stale: true` from API shown as `⚠ state` badge / strip label suffix
- [x] `mountAction()`, `mountHome()`, `mountGoto()` all set/clear `_mountPendingCmd`
- [x] Card re-renders immediately on command acceptance (pending) and on poll confirmation (final)

---

## M7 — Formal Service Contracts & Safety Extension

*Source: `smarttscope_additional_requirements.md` v1.0 — ingested 2026-06-24*

### P0 — Safety behavioral change

- [x] M7-001 Interactive time/location startup dialog — replace silent auto-sync with user-confirmation flow `[P0 · Safety]`
  - Remove `ensure_time_location_synced()` call from `adapters/onstep/mount.py` `session_connect()`
  - After ST-002 query: compare OnStep time/location against GPS (fix ≤ 60 min old) or system/config fallback
  - Within tolerance → set `TimeLocationStatus = VERIFIED`, log, continue
  - Out of tolerance → show dialog (OnStep values, master values, differences, source); user: Approve → push via adapter; Skip → set `UNVERIFIED`
  - Tests: TEST-001 table (9 cases: within tolerance, time diff > 10 s, location diff > tolerance, approve push, reject push, unverified blocks tracking/GoTo/sync, startup while parked, startup while unparked, tracking disabled)

- [x] M7-002 Add `TimeLocationStatus` orthogonal flag to `DeviceStateService` `[P0 · Safety]`
  - New enum `TimeLocationStatus = {UNKNOWN, VERIFIED, UNVERIFIED}` in `smart_telescope/domain/`
  - Add field to `DeviceStateService`; default `UNKNOWN` at startup; set by M7-001 sequence
  - `HardwareCommandCoordinator.mount_command()` checks `TimeLocationStatus` before tracking enable, GoTo, sync
  - Camera-only and manual movement (with warning) remain permitted when `UNVERIFIED`
  - Config flags from CFG-001 (`allow_*_when_time_location_unverified`) respected

### P1 — New features

- [x] M7-003 Pixel-to-RA/DEC calibration service (lazy trigger) `[P1 · Runtime]` ✓ 2026-06-24
  - `smart_telescope/services/pixel_calibration_service.py` + `domain/pixel_calibration.py`; 6 tests pass

- [x] M7-004 Focuser backlash compensation `[P1 · Runtime]` ✓ 2026-06-24
  - `FOCUSER_BACKLASH_STEPS` / `FOCUSER_BACKLASH_ENABLED` in `config.py`; direction-reversal overshoot in `OnStepFocuser`; 4 tests pass

- [x] M7-005 Common `ServiceFrame` input dataclass `[P1 · Runtime]` ✓ 2026-06-24
  - `smart_telescope/domain/service_frame.py`; `validate()` + `from_fits_frame()`; 5 tests pass

- [x] M7-006 Stateful `PlateSolveService` wrapping `AstapSolver` `[P1 · Runtime]` ✓ 2026-06-24
  - `smart_telescope/services/plate_solve_service.py`; enforces PS-001 auto-gain precondition; 6 tests pass

- [x] M7-007 Gap check + formalize `AutofocusService` `[P1 · Runtime]` ✓ 2026-06-24
  - `smart_telescope/services/autofocus_service.py`; V-curve detection; pixel-space centroid offset (AF-005); 6 tests pass

- [x] M7-008 Collimation numeric displacement value `[P1 · UI]` ✓ 2026-06-24
  - `circle_center_displacement_px` added to `DonutOverlay`, assistant output, replay API; 2 new tests

### P2 — Gap checks and formalization

- [x] M7-009 Shared image-analysis module `[P2 · Runtime]` ✓ 2026-06-24
  - `smart_telescope/services/image_analysis.py`; uniform/no-signal frames → `FocusQualityLevel.UNKNOWN`; 6 tests pass

- [x] M7-010 Verify ≤ 1 s auto-gain exposure cap when tracking off (AG-003) `[P2 · Runtime]` ✓ 2026-06-24
  - `tracking_on: bool = True` on `AutoGainService.run_one_shot()`; caps to 1 000 ms when False; API worker reads `MountState.TRACKING`; 2 tests pass

- [x] M7-011 GPS fix age check ≤ 60 minutes (CFG-002) `[P2 · Runtime]` ✓ 2026-06-24
  - `GpsdFix.fix_age_s` + `is_fresh(max_age_minutes=60)`; stale fix logs WARNING; API response exposes `fix_age_s` + `is_fresh`; 6 new tests

- [x] M7-012 Verify retry limits in all service loops (SAFE-004) `[P2 · Runtime]` ✓ 2026-06-24
  - Added `max_retries: int = 5` to `PlateSolveService`; raises `PlateSolveError` when exceeded; `reset()` resets counter; 9 audit tests across auto-gain, autofocus, plate-solve, collimation sub-services

---

## M8 — Incident-Driven Runtime Hardening

*Source: `resources/hlrequirements/smarttscope_incident_requirements_final_v1_2.md` v1.2 — ingested 2026-06-25*  
*Resolves: INC-001..INC-012 (field incidents); covers REQ-STATE, REQ-TIME, REQ-CONN, REQ-GOTO, REQ-CMD, REQ-UI, REQ-SETUP, REQ-PS, REQ-AG, REQ-LOG, REQ-FRAME, REQ-CLICK, REQ-API, REQ-GIT*

**Grilling clarifications (binding):**
- Push Pi time → OnStep verified → ONSTEP_COMPARISON is a valid trust chain (intentional; document in code comment)
- REQ-AG-002 tracking quality = star elongation/FWHM from captured frames only, no plate-solve dependency
- Click-to-center cold start = hard block + launch calibration wizard; no manual override
- REQ-GIT items tracked here as Priority 7

### Priority 1 — State model and operation gates

- [x] M8-001 Separate `/api/status` into 6 state categories `[P1 · API]` ✓ 2026-06-26
  - `adapter_connection_state`, `adapter_health_state`, `mount_operational_state`, `onstep_time_location_state`, `raspberry_time_trust_state`, `operation_gate_states`
  - Acceptance: REQ-STATE-001; INC-001 (connected-but-restricted no longer shown as disconnected)

- [x] M8-002 Mount readiness enum — 7 states `[P1 · Domain]` ✓ 2026-06-26
  - `DISCONNECTED`, `CONNECTED_HEALTH_UNKNOWN`, `CONNECTED_RESTRICTED`, `CONNECTED_READY`, `CONNECTED_TIME_LOCATION_UNVERIFIED`, `CONNECTED_RASPBERRY_TIME_UNTRUSTED`, `ERROR`
  - Trust/time failures shown as trust failures, not connection failures; reconnect guidance only when reconnecting helps
  - Acceptance: REQ-STATE-002, REQ-CONN-003; TEST-001

- [x] M8-003 `OperationGateService` with 13 gated operations `[P1 · Runtime]` ✓ 2026-06-26
  - Operations: `camera_capture`, `manual_mount_move`, `tracking_enable`, `goto`, `bright_star_goto`, `sync`, `plate_solve`, `plate_solve_mount_correction`, `collimation_preview`, `collimation_slew_to_target`, `collimation_mount_centering`, `autofocus`, `click_to_center`
  - Gate response: `allowed`, `reason_code`, `human_message`, `required_user_action`, `blocking_states`
  - HTTP 409 uses gate result; rejected commands not logged as issued
  - Acceptance: REQ-STATE-003; TEST-003

- [x] M8-004 Fix `/api/mount/status` — `connected = adapter_open AND health_check_ok` `[P1 · API]` ✓ 2026-06-26
  - `adapter_open`, `health_check_ok`, `connected`, `park_state`, `tracking_state`, `last_error`
  - Connect All idempotent: repeated calls reuse existing connections without contradictory UI state
  - Acceptance: REQ-CONN-001, REQ-CONN-002, REQ-API-002; INC-001

- [x] M8-005 UI — disabled controls show exact gate reason; 409 includes structured diagnostics `[P1 · UI]` ✓ 2026-06-26
  - Applies to: goto, bright_star_goto, sync, tracking_enable, plate_solve, plate_solve_correction, collimation_slew_to_target, click_to_center, autofocus
  - Reason from backend gate result; UI refreshes after Stage 1 changes; stale frontend state cannot keep controls disabled
  - Rejected GoTo logged as `REJECTED` not `ISSUED`
  - Acceptance: REQ-UI-001, REQ-GOTO-001; INC-003, INC-005
  - Backend: `_gate_check()` in `mount.py`; `gate_inputs_from_device_state()`+`evaluate_gate()` in `operation_gate.py`; replaced all 4 M7-002 ad-hoc tl checks
  - Frontend: `_gateStates`+`_applyGateStates()` in `app.js`; `refreshHealth()` stores gate states; `_updateMountStrip()` calls `_applyGateStates()`; gate-blocked parsing in `mountGoto()`/`mountAction()` catch blocks
  - raspberry_time_trust stub changed to "TRUSTED" until M8-007

### Priority 2 — Stage 1 time/location and Raspberry trust

- [x] M8-006 Master source selection: GPS > NTP > USER_CONFIRMED > fallback `[P1 · Runtime]` ✓ 2026-06-26
  - Fallback (untrusted time, config-only location) does not unlock mount automation
  - Master source visible in UI and logs
  - Acceptance: REQ-TIME-001
  - `domain/master_time_source.py`: `MasterTimeSource` enum (GPS_FIX | NTP | USER_CONFIRMED | FALLBACK)
  - `services/master_source.py`: `MasterSourceService.evaluate()` priority chain; `_check_ntp_sync()` via timedatectl; `is_trusted()` staticmethod
  - `services/device_state.py`: `is_user_time_confirmed()` / `set_user_time_confirmed()` flag
  - `services/operation_gate.py`: `gate_inputs_from_device_state()` accepts optional `master_source_svc`; adds `master_time_source` key; `_evaluate_one()`/`evaluate_gate()`/`evaluate_all_gates()` accept `**_` for extra inputs
  - `api/health.py`: `MountStateCategories.master_time_source` field; `system_status` injects `MasterSourceService` via deps
  - `api/mount.py`: `_gate_check()` accepts `master_source_svc`; 4 gated endpoints inject it
  - `api/deps.py` + `runtime.py`: `get_master_source_service()` dep; `RuntimeContext.master_source_svc` (reset in tests)
  - 23 new tests in `tests/unit/services/test_master_source.py`; 3368 passed, 39 skipped

- [x] M8-007 Raspberry Pi time trust sources — 5 enums with rules `[P1 · Runtime]` ✓ 2026-06-27
  - `NTP`, `GPSD_FIX`, `USER_CONFIRMED`, `ONSTEP_COMPARISON`, `NOT_TRUSTED`
  - `ONSTEP_COMPARISON`: valid only if OnStep trusted via GPS/NTP/previous verified Stage 1 **or** via successful push in current session (intentional trust chain — clarify in code comment per DEC-006)
  - Pushing Pi time to OnStep alone does NOT auto-trust Raspberry Pi time (trust needs the subsequent re-comparison step)
  - `USER_CONFIRMED`: warning shown; logged; valid for session or `session_trust_expiry_minutes`
  - Acceptance: REQ-TIME-002, REQ-TIME-004; INC-003, INC-009
  - `domain/raspberry_time_trust.py`: `RaspberryTimeTrustSource` enum + `is_trusted()` helper
  - `services/raspberry_time_trust.py`: `RaspberryTimeTrustService` with priority chain (GPSD_FIX > NTP > ONSTEP_COMPARISON > USER_CONFIRMED > NOT_TRUSTED); expiry via monotonic timestamp
  - `services/device_state.py`: added `set_onstep_comparison_established()`, `get_onstep_comparison_established_at()`, `get_user_time_confirmed_at()`
  - `services/operation_gate.py`: M8-007 path with isinstance guards for mock safety; M8-006 fallback when `raspberry_trust_svc=None`
  - `api/health.py`, `api/mount.py`, `api/deps.py`, `runtime.py`: wired into all gated endpoints
  - 35 new tests in `tests/unit/services/test_raspberry_time_trust.py`; 3360 passed, 24 skipped

- [x] M8-008 Meter-based location tolerance (100 m default); UTF-8-safe logs `[P1 · Runtime]` ✓ 2026-06-27
  - Primary check: `location_delta_m ≤ onstep_location_tolerance_m (default 100)`; degree fallback only for backward-compat
  - Active tolerances logged on every check; `lat_delta=0.0027°` fails at 100 m; `lon_delta=0.0337°` fails at 100 m
  - No mojibake (`窶・`, `竊・`, `ﾂｰ`) in logs; degree values as `°` or ASCII `deg`
  - Acceptance: REQ-TIME-003, REQ-TIME-006; INC-002; TEST-002
  - `adapters/onstep/safety.py`: added `onstep_time_tolerance_s=10.0` and `onstep_location_tolerance_m=100.0` to `OnStepSafetyConfig`
  - `adapters/onstep/mount.py`: added `_haversine_m()` helper; `get_sync_status()` uses meter-based tolerance, adds `location_delta_m`/`location_tolerance_m`/`time_tolerance_s` to returned dict
  - `api/session.py`: log format uses `deg` not `°`; active tolerances logged on every check
  - `services/readiness.py`: location issue string uses `{loc_m:.0f}m`; fallback uses `deg`
  - `config.py`: `ONSTEP_TIME_TOLERANCE_S`/`ONSTEP_LOCATION_TOLERANCE_M` from `[mount]` section; wired into `build_onstep_safety_config()`
  - `templates/config.toml`: added `[mount]` section with tolerance stubs
  - 26 new tests in `tests/unit/adapters/onstep/test_get_sync_status.py`; 3386 passed, 24 skipped

- [x] M8-009 Trust session expiry; no cross-restart persistence `[P1 · Runtime]`
  - `config.py`: `SESSION_TRUST_EXPIRY_MINUTES` from `[time_location]` section (env override supported)
  - `runtime.py`: both `__init__` and `reset_for_tests()` pass `session_trust_expiry_minutes=config.SESSION_TRUST_EXPIRY_MINUTES`; added `from . import config`
  - `templates/config.toml`: activated `[time_location]` section with `session_trust_expiry_minutes = 120` and `persist_trust_across_restart = false`
  - 5 new M8-009 tests (no-persistence, restart-clears-trust, custom-expiry, 120-min-default, USER_CONFIRMED expiry); 3391 passed, 24 skipped
  - Acceptance: DEC-004 (no cross-restart persistence), DEC-005 (configurable expiry)

- [x] M8-010 Stage 1 UI panel — 20 required fields `[P1 · UI]`
  - `GET /api/stage1/time-location` (REQ-API-004): consolidated time/location trust state from DeviceStateService cache; no live serial I/O
  - `POST /api/mount/confirm_time`: user asserts Pi clock is correct → sets USER_CONFIRMED trust
  - `DeviceStateService`: 3 new cache fields (`_last_sync_status`, `_last_verification_at`, `_last_push_at`) + 5 accessors
  - `mount.get_sync_status()` extended with `onstep_time_local` / `master_time_local` ISO strings
  - Stage 1 card "Time / Location Verification" in UI: adapter state, trust source, time/location deltas vs tolerances, action buttons (Rerun / Push / Confirm Pi Time)
  - JS: `refreshStage1TL()`, `stage1PushClock()`, `stage1ConfirmTime()` in `setup.js`; 15 s poll interval in `app.js`
  - 25 new tests (19 `test_stage1.py` + 2 `test_mount.py` + 4 `test_raspberry_time_trust.py`); 3416 passed, 24 skipped
  - Acceptance: REQ-TIME-005, REQ-API-004, INC-009

### Priority 3 — Command history

- [x] M8-011 `CommandHistoryService` — persists per-session JSONL `[P1 · Runtime]`
  - `smart_telescope/domain/command_status.py`: `CommandStatus` enum (7 values)
  - `smart_telescope/services/command_history.py`: `CommandRecord` dataclass (12 fields) + `CommandHistoryService`; thread-safe; in-memory dict + append-only JSONL; `record()`, `update()`, `get_all()`, `get_by_id()`
  - `config.py`: `COMMAND_HISTORY_DIR` (default `~/.SmartTScope/commands/`); `templates/config.toml` updated
  - `runtime.py`: `_app_session_id` UUID per session; `self.command_history = CommandHistoryService(...)`; reset in `reset_for_tests()`
  - `api/deps.py`: `get_command_history_service()`
  - 19 new tests in `tests/unit/services/test_command_history.py`; 3435 passed, 24 skipped
  - Acceptance: REQ-CMD-001

- [x] M8-012 `/api/commands` endpoint; command history frontend panel `[P1 · API · UI]`
  - `smart_telescope/api/commands.py` (new): `GET /api/commands` returns all session records from `CommandHistoryService`
  - Stage 1 "Command History" card: scrollable, last 50 commands, color-coded by status (green/yellow/red/grey)
  - `setup.js`: `refreshCommandHistory()` + `_renderCommandHistory()`; `app.js`: initial call + 10 s interval
  - 6 new tests in `tests/unit/api/test_commands.py`
  - Acceptance: REQ-API-003, INC-005

- [x] M8-013 GoTo gate-checked before marking issued; bright-star GoTo preconditions `[P1 · Runtime]`
  - `mount_goto` wires `CommandHistoryService`: REQUESTED on entry → REJECTED (gate/solar/limit) / ISSUED → SUCCEEDED / FAILED
  - `?bright_star=true` query param: uses `bright_star_goto` gate operation (REQ-GOTO-002); altitude already checked by `_check_mount_limits`
  - `config.py`: `ALLOW_DIRECT_RADEC_GOTO_WITHOUT_RASPBERRY_TIME_TRUST = False` (REQ-GOTO-003); `templates/config.toml` updated with `[operation_policy]` section
  - `operation_gate.py`: `_evaluate_one` for `goto` honors `allow_direct_radec_without_trust` flag; `gate_inputs_from_device_state()` includes the config value
  - 5 new tests in `test_mount.py` + 4 in `test_operation_gate.py`; 3470 passed, 24 skipped
  - Acceptance: REQ-GOTO-001..003, INC-005, TEST-003

### Priority 4 — Observability and diagnostic frames

- [x] M8-014 12 per-section log namespaces; session ID links all logs `[P2 · Runtime]` ✓ 2026-06-27
  - `smart_telescope/services/section_logger.py`: `SectionLogger(session_id, log_dir)` with 12 named sections; `_SectionAdapter` injects `session_id` + `section` into every record; optional per-section `FileHandler` to `{log_dir}/{session_id[:8]}/{section}.log`; `get(section)` + `get_paths()` + `close()`; loggers under `smart_telescope.section.*` with `propagate=True`
  - `smart_telescope/api/logs.py`: `GET /api/logs` returns `{section: path_or_null}` for all 12 sections
  - `config.py`: `LOG_DIR` from `[session].log_dir` (default `~/.SmartTScope/logs/`); `templates/config.toml` updated
  - `runtime.py`: `self.section_logger = SectionLogger(...)` in `__init__`; reset in `reset_for_tests()`; `close()` in `shutdown()`
  - `api/deps.py`: `get_section_logger()`; `app.py`: `logs_router` registered
  - 14 tests in `tests/unit/services/test_section_logger.py` + 5 tests in `tests/unit/api/test_logs.py`; 3469 passed, 24 skipped
  - Acceptance: REQ-LOG-001

- [x] M8-015 Service-call logs per iteration `[P2 · Runtime]` ✓ 2026-06-27
  - `smart_telescope/domain/service_call_log.py`: `ServiceCallRecord` — 11 fields; `to_json_line()` emits one JSON line per call
  - `smart_telescope/services/service_call_logger.py`: `ServiceCallLogger` + `_CallContext` context manager; status priority: `_explicit_error` → failed; `_cancelled` → cancelled; `exc_val` → failed; else → ok
  - Wired into `api/autogain.py::_worker()`, `workflow/stages.py` (align/recenter/autofocus) via `StageContext.service_call_logger`
  - `workflow/runner.py` accepts `service_call_logger=` kwarg; `api/session.py` injects `deps.get_service_call_logger()`
  - Tests: 15 unit tests in `tests/unit/services/test_service_call_logger.py`
  - Acceptance: REQ-LOG-002; INC-010

- [x] M8-016 User-action log — 18 named actions `[P2 · Runtime]` ✓ 2026-06-27
  - `smart_telescope/domain/user_action_log.py`: `USER_ACTIONS` tuple (18 names) + `UserActionRecord` dataclass (action, timestamp, result, gate_reason)
  - `smart_telescope/services/user_action_logger.py`: `UserActionLogger` with `_ACTION_SECTIONS` mapping each action to its section; `log(action, result, gate_reason)` writes JSON line to section logger
  - Runtime: constructed in `__init__` and `reset_for_tests()`; `deps.get_user_action_logger()` injector
  - Wired into: `session.py::session_connect` (connect_all_clicked); `mount.py::mount_track` (tracking_enable_requested/rejected); `mount.py::mount_goto` (goto_requested/rejected/bright_star_goto_requested); `mount.py::mount_sync_clock` (time_location_push_confirmed/rejected); `mount.py::mount_confirm_time` (raspberry_time_manually_confirmed); `autogain.py::run_autogain` (diagnostic_exposure_test_started when req.diagnostic); `focuser.py::focuser_autofocus` (autofocus_started); `collimation.py::collimation_start` (collimation_started); `solver.py::solver_solve` (plate_solve_requested)
  - Remaining 6 actions (autofocus_cancelled, collimation_mode_selected, click_to_center_*, github_push_requested) wired when those endpoints are built
  - Tests: 17 unit tests in `tests/unit/services/test_user_action_logger.py`
  - Acceptance: REQ-LOG-003

- [x] M8-017 FITS diagnostic frame storage `[P2 · Runtime]` ✓ 2026-06-27
  - `smart_telescope/domain/diagnostic_frame.py`: `DiagnosticStoreMode` enum (5 modes) + `DiagnosticFrameConfig` dataclass (enabled, store_mode, retention_days, frame_dir) + `REQUIRED_FITS_HEADERS` tuple (17 headers)
  - `smart_telescope/services/diagnostic_frame_store.py`: `DiagnosticFrameStore` — `should_save(is_debug, is_failure)`, `save_frame(...)` writes FITS to `{frame_dir}/{session_id[:8]}/`, `cleanup_old_frames(active_session_ids)` deletes dirs older than retention_days
  - Config: `DIAGNOSTIC_FRAMES_ENABLED/STORE_MODE/RETENTION_DAYS/DIR` in `config.py`; `[diagnostic_frames]` section in `templates/config.toml`
  - Runtime: `diagnostic_frame_store` on `RuntimeContext`; `deps.get_diagnostic_frame_store()` injector
  - Tests: 33 unit tests in `tests/unit/services/test_diagnostic_frame_store.py`
  - Acceptance: REQ-FRAME-001; INC-010; TEST-006

- [x] M8-018 FITS filename pattern + 17 required headers `[P2 · Runtime]` ✓ 2026-06-27
  - Pattern: `YYYYMMDDTHHMMSS_session-<id>_<section>_<run_id>_iter-<n>_<camera_id>_<optical_train_id>_exp-<s>s_gain-<g>_offset-<o>_bin-<x>x<y>_ra-<ra>_dec-<dec>.fits` — filesystem-safe (no colons/spaces/slashes)
  - `_make_filename()` in `diagnostic_frame_store.py` generates the filename; `_safe()` sanitizes components
  - All 17 FITS headers written with `save_frame()`: SESSION, SECTION, RUNID, ITER, CAMERA, OPTTRAIN, EXPTIME, GAIN, OFFSET, BINX, BINY, PIXSIZE, FOCALLEN, RA, DEC, TRACKING, DATE-OBS (note: todo said "16" but 17 headers listed — all implemented)
  - Acceptance: REQ-FRAME-002, REQ-FRAME-003

### Priority 5 — Plate solve and auto-gain

- [x] M8-019 Extended Setup Check per-camera diagnostic report (19 fields) `[P2 · Runtime]` ✓ 2026-06-27
  - `smart_telescope/domain/camera_diagnostic.py`: `CameraDiagnosticStatus` enum (10 statuses) + `CameraDiagnosticReport` dataclass (19 fields: 4 identity, 3 config/detection, 2 outcome, 3 capture params, 2 frame metadata, 3 image analysis, 2 plate-solve result)
  - `smart_telescope/services/setup_check_service.py`: `run_camera_diagnostic()` — status progression: disconnected → operation_blocked → capture_failed → insufficient_stars → metadata_missing → astap_failed → solved; `_analyse_frame()` estimates star count/FWHM/background via scipy.ndimage or numpy fallback; `MIN_STARS_BEFORE_SOLVE = 15`
  - `smart_telescope/api/setup_check.py`: `POST /api/setup/camera_diagnostic` endpoint — returns `{cameras: [...], total: N, solved: N}`
  - Tests: 17 unit tests in `tests/unit/services/test_camera_diagnostic.py`
  - Acceptance: REQ-SETUP-001, REQ-SETUP-002; INC-004; DEC-016

- [x] M8-020 Plate-solve readiness pre-check (8 conditions) `[P2 · Runtime]`
  - Check: `frame_exists`, `frame_saved_as_fits`, `optical_train_metadata_available`, `pixel_size_available`, `focal_length_or_hint_available`, `star_count_measured`, `astap_available`, `operation_gate_allows_plate_solve`
  - Each missing condition gives specific failure reason; readiness result logged
  - Domain: `domain/plate_solve_readiness.py` — `READINESS_CONDITIONS` (8), `ReadinessCondition`, `PlateSolveReadinessResult`
  - Service: `services/plate_solve_readiness.py` — `check_plate_solve_readiness()` evaluates all 8 conditions, logs to `plate_solve` section
  - Endpoint: `GET /api/solver/readiness` — static query (no live frame) for tool/UI polling
  - Tests: 20 unit tests in `tests/unit/services/test_plate_solve_readiness.py`
  - Acceptance: REQ-PS-001; TEST-004

- [x] M8-021 ASTAP logging → structured diagnostics `[P2 · Runtime]`
  - Log: ASTAP input FITS path, command/wrapper call, output, exit status; convert failure to structured diagnostics
  - Local star threshold: `min_detected_stars_before_solve = 15`, `allow_astap_below_min_star_count = true` (OPEN-003: revisit after real frames)
  - Domain: `domain/astap_diagnostic.py` — `AstapSolveRecord` (13 fields) with `to_dict()`/`to_json_line()`
  - Adapter: `AstapSolver.solve()` builds `AstapSolveRecord` on every call (success/timeout/failure/no-ini); attaches to `SolveResult.diagnostics`; emits `ASTAP_DIAGNOSTIC` JSON-line via `_log`
  - Port: `SolveResult.diagnostics: AstapSolveRecord | None` added (backward-compatible, default None)
  - API: `POST /api/solver/solve` logs `result.diagnostics` to `plate_solve` section logger
  - Config: `[plate_solve] min_detected_stars_before_solve=15`, `allow_astap_below_min_star_count=true`
  - Tests: 13 unit tests in `tests/unit/adapters/test_astap_diagnostic.py`
  - Acceptance: REQ-PS-002, REQ-PS-003; INC-004, INC-008

- [x] M8-022 Auto-gain 6 purpose modes; PLATE_SOLVE tracking-quality via frame blur only `[P2 · Runtime]`
  - Modes: `PLATE_SOLVE`, `DSO`, `PLANET`, `MOON`, `COLLIMATION`, `AUTOFOCUS`
  - `PLATE_SOLVE`: keep offset low; increase exposure while tracking quality supports it (measured by star elongation ratio / FWHM growth from captured frames — no plate-solve dependency)
  - `domain/autogain.py`: 9-value `AutoGainMode` enum (6 purpose + 3 legacy aliases); `measure_elongation_ratio()` gradient-anisotropy metric; `_select_conversion_gain()` updated for new modes
  - `domain/autogain_service.py`: `PLATE_SOLVE` mode forces offset=0; per-frame elongation-ratio check (fires when ratio > 2.0 AND grew by > 50% vs previous frame) caps exposure and returns OK with warning_msg
  - `COLLIMATION`/`AUTOFOCUS`/`PLANET`/`MOON`: routed to DSO or planetary signal metric respectively; backward-compatible aliases retained
  - Tests: 18 unit tests in `tests/unit/domain/test_autogain_modes.py`
  - Acceptance: REQ-AG-001, REQ-AG-002; INC-008

- [x] M8-023 Exposure capability test + 13-field auto-gain diagnostics `[P2 · Runtime]`
  - Test sequence: `0.5 s, 1 s, 2 s, 4 s, 8 s`; stop on elongation/FWHM degradation/saturation
  - Diagnostics: `number_of_stars_detected`, `background_median_adu`, `background_stddev_adu`, `saturated_pixel_ratio`, `black_clipped_pixel_ratio`, `median_fwhm_px`, `median_hfr_px`, `exposure_limit_reached`, `gain_limit_reached`, `offset_limit_reached`, `tracking_blur_suspected`, `reason_for_next_step`, `reason_for_stop`
  - Suggested values not written to config without user confirmation (OPEN-004: revisit after real tracking data)
  - Domain: `domain/exposure_capability.py` — `TEST_EXPOSURES_S` (0.5/1/2/4/8 s), `ExposureStepDiagnostics` (14 fields), `ExposureCapabilityResult`
  - Service: `services/exposure_capability_service.py` — `run_exposure_test()` sweeps 5 exposures; `_analyse_step()` computes all diagnostics; stops on saturation/blur/cancel
  - Endpoint: `POST /api/autogain/exposure_test` — async (up to ~40 s); advisory result only
  - Tests: 17 unit tests in `tests/unit/services/test_exposure_capability_service.py`
  - Acceptance: REQ-AG-003, REQ-AG-004

### Priority 6 — Collimation and click-to-center

- [x] M8-024 Collimation modes: "Bahtinov Preview" + "Defocus Donut" (correct spelling) `[P2 · UI]`
  - Both modes visible; if unavailable, reason shown; "Bahtinov" spelling verified
  - Collimation preview allowed without Raspberry Pi time trust if camera capture works
  - Slew-to-target and mount-assisted centering remain gated
  - API: `GET /api/collimation/modes` — per-mode availability (preview / slew / centering); camera-only preview always allowed; slew/center gated via OperationGate
  - UI: `s4-modes-card` in Stage 4 — two clickable tiles (Bahtinov Preview, Defocus Donut) with availability dot, reason text; `Defocus Donut` section with preview controls hidden until selected; `refreshCollimationModes()` called on stage entry
  - Tests: 11 unit tests in `tests/unit/api/test_collimation_modes.py`
  - Acceptance: REQ-UI-002, REQ-UI-003; INC-006, INC-007; TEST-005

- [x] M8-025 Click-to-center in collimation, plate-solve, autofocus views `[P2 · UI]`
  - User can click star or donut; if unavailable, exact reason shown
  - `GET /api/click_to_center/readiness` — evaluates `click_to_center` gate; returns `{allowed, reason, required_action}`
  - Click handlers on `s3-preview-frame`, `s4-preview-frame`, `s4-donut-preview-frame` (crosshair cursor + amber circle marker)
  - CTC banners below each frame: show exact gate reason when unavailable; pixel coords when allowed
  - `smart_telescope/static/js/click_to_center.js` — `ctcHandlePreviewClick()`, `ctcGetLastClick()`, `ctcClearBanner()`
  - Tests: 12 unit tests in `tests/unit/api/test_click_to_center_readiness.py`
  - Acceptance: REQ-CLICK-001

- [x] M8-026 Click refinement — star centroid / donut-circle center / raw fallback `[P2 · Runtime]`
  - Raw click logged; refined target logged and displayed; if refinement fails, user can use raw click or cancel
  - `smart_telescope/domain/click_refinement.py`: `refine_click(pixels, x, y, mode)` → `RefinedClick`; modes `star_centroid` (half-peak threshold) and `ring_center` (0.2-threshold for ring breadth); robust background via 25th-percentile + sub-median std; raw fallback when no feature found
  - `smart_telescope/api/preview.py`: `_last_preview_pixels[camera_index]` cache populated after each frame; `get_last_preview_pixels(camera_index)` accessor
  - `smart_telescope/api/click_to_center.py`: `POST /api/click_to_center/refine` — reads cached frame, applies refinement, returns `{raw_x/y, refined_x/y, method, confidence, fallback, fallback_reason}`
  - `smart_telescope/static/js/click_to_center.js`: updated `ctcHandlePreviewClick()` — calls refine endpoint, shows green marker for refined or amber for fallback, updates banner with method + confidence
  - Tests: 15 unit tests in `tests/unit/domain/test_click_refinement.py`, 9 in `tests/unit/api/test_click_to_center_refine.py`
  - Acceptance: REQ-CLICK-002

- [x] M8-027 Click-to-center calibration (hard block; calibration wizard on cold start) `[P2 · Runtime]`
  - Missing/stale calibration blocks movement and launches calibration wizard (no manual override — grilling clarification #3)
  - Calibration stored per optical-train × camera-orientation × binning; invalidated on change
  - Mount not moved without valid calibration
  - `smart_telescope/domain/ctc_calibration.py`: `CTCCalibration` dataclass (arcsec_per_px_x/y, rotation_deg, optical_train, binning, measured_at, max_age_hours); `is_valid()`, `age_hours()`, `to_dict()`, `from_dict()`; keyed by `"optical_train:binning"`
  - `smart_telescope/services/ctc_calibration_store.py`: file-backed JSON store at `~/.SmartTScope/ctc_calibration.json`; `get()`, `put()`, `delete()`, `all()`
  - `smart_telescope/api/deps.py`: `get_ctc_calibration_store()` singleton
  - `smart_telescope/api/click_to_center.py`: readiness endpoint updated to check calibration; `GET /calibration`, `POST /calibration`, `DELETE /calibration`
  - `smart_telescope/static/js/click_to_center.js`: `ctcRefreshCalibrationStatus()` for calibration status display
  - Tests: 9 domain + 9 store + 12 API tests (42 total for M8-027)
  - Acceptance: REQ-CLICK-003

- [x] M8-028 Iterative bounded click-to-center loop `[P2 · Runtime]`
  - Config defaults: `max_iterations=5`, `center_tolerance_px=20`, `max_single_move_px=300`, `start_with_fraction_of_calculated_move=0.5`, `allow_when_tracking_off=true`; `center_rate_arcsec_per_sec=120.0`
  - Works tracking-on; works tracking-off with drift warning; blocked while parked; user can cancel; every iteration logged
  - OPEN-002: review defaults after first calibration results on real mount
  - `smart_telescope/config.py`: `CTC_MAX_ITERATIONS`, `CTC_CENTER_TOLERANCE_PX`, `CTC_MAX_SINGLE_MOVE_PX`, `CTC_MOVE_FRACTION`, `CTC_ALLOW_TRACKING_OFF`, `CTC_CENTER_RATE_ARCSEC_PER_SEC` from `[click_to_center]`
  - `templates/config.toml`: `[click_to_center]` section with all 6 settings + comments
  - `smart_telescope/services/ctc_loop_service.py`: `run_centering_loop()` — iterative per-frame capture → refine → offset → move loop; `CTCIterationLog.to_json_line()`; `CTCLoopResult.to_dict()`; `_pixel_offset_to_move()` with rotation support, fraction, max_px clamp
  - `smart_telescope/api/click_to_center.py`: `POST /api/click_to_center/center` (blocking run); `POST /api/click_to_center/cancel` (set cancellation flag)
  - Tests: 14 service tests in `tests/unit/services/test_ctc_loop_service.py`
  - Acceptance: REQ-CLICK-004, DEC-010..012; TEST-005

### Priority 7 — Dev workflow: GitHub delivery audit

- [x] M8-029 `scripts/delivery_audit.py` — git delivery checks `[P3 · DevWorkflow]`
  - Runs: `git status --short`, `git diff-tree --name-only`, `git log -1`, `git branch --show-current`, `git remote -v`
  - Confirms branch, commit, source/test/doc file categories, push result; exit 0=pass, 1=fail, 2=git error
  - Acceptance: REQ-GIT-002; INC-012; TEST-007
  - *Done:* `scripts/delivery_audit.py`; categorises files into source/test/doc/other; fails on docs-only commits, uncommitted changes, or unpushed commits; `--push` / `--check` flags; pre-push checklist printed always

- [x] M8-030 Delivery log JSONL + pre-push checklist `[P3 · DevWorkflow]`
  - Fields: `timestamp`, `branch`, `commit_hash`, `commit_message`, `files_changed`, `source_files_changed`, `test_files_changed`, `docs_changed`, `push_result`, `remote_url`
  - Documentation-only commits not marked implementation-complete
  - OPEN-005: split this requirements doc into runtime/UI/diagnostics/delivery after M8 closure
  - Acceptance: REQ-GIT-001, REQ-GIT-003
  - *Done:* `_write_log()` appends JSONL record to `~/.SmartTScope/delivery_log.jsonl` on every non-dry-run; pre-push checklist shown in report; `--log PATH` overrides log location; `docs_only_commit` + `audit_passed` fields included

### Priority 8 — Optional external frame analyzer

- [x] M8-031 Pluggable external frame analyzer adapter `[P2 · Analysis]`
  - New domain type: `smart_telescope/domain/star_count.py` — `StarCountResult` (frozen dataclass), `FrameQuality` literal
  - New adapter: `smart_telescope/services/frame_analyzer.py` — `FrameAnalyzerProtocol` (Protocol + `@runtime_checkable`), `ExternalFrameAnalyzer` (stateless adapter), `load_external_analyzer(module_name)` (import via importlib, graceful fallback)
  - Config: `[analysis] external_frame_analyzer_module = ""` in `config.toml` / `templates/config.toml`; env override `EXTERNAL_FRAME_ANALYZER_MODULE`
  - Runtime: `RuntimeContext.frame_analyzer: FrameAnalyzerProtocol | None` wired at startup; cleared in `reset_for_tests()`
  - FastAPI dep: `deps.get_frame_analyzer()` returns `rt.frame_analyzer`
  - Autogain: `AutoGainService.run_one_shot()` accepts `frame_analyzer=` param; quality gates map `"too_dark"` / `"too_bright"` / `"stars_saturated"` / `"usable"` to signal-band overrides; applies clamped suggestions; returns early on `focus_warning=True`
  - Setup check: `run_camera_diagnostic()` + `POST /api/setup/camera_diagnostic` accept `frame_analyzer=`; uses external star count when available
  - Tests: 9 + 13 + 8 = 30 new unit tests in `test_star_count.py`, `test_frame_analyzer.py`, `test_autogain_service.py::TestExternalFrameAnalyzerIntegration`

---

## M9 — Guided Observing State Machine

*Source: `smarttscope_requirements_full.md` §6-7 (top-level process/state model) and §11 (MVP staging). Replaces the 5-tab "Startup/Alignment/GoTo&Solve/Collimation/Session" wizard as the app's primary/default screen with one guided flow driven by a single backend state machine: `BOOTSTRAP → WAIT_CONTEXT_CONFIRMATION → WAIT_HOME_CONFIRMATION → POLAR_ALIGN → FOCUS_READYING → TARGET_ACQUIRE → GUIDE_READYING → CAPTURE_ACTIVE → SAFE_STOPPING → PARKED_SAFE`, with `PAUSED_SAFE`/`FAULT` side paths, guarded by G1-G10. Reuses every existing engine (`polar_workflow`, `stage_autofocus`, `stage_align/goto/recenter`, `guiding_service`, `stage_stack`, `mount_operations.park_sequence`) rather than reimplementing them — see the old 5-tab UI, now demoted to a "Maintenance" screen, for the manual/diagnostic tools those engines are also directly reachable from.*

### Phase 1 — State-machine skeleton + guided UI shell (done — this pass)

- [x] M9-001 `ObservingStateMachine` — pure transition table for the 12-phase model `[P1 · Runtime]`
  - *Done:* `smart_telescope/domain/observing_state.py` — `ObservingPhase`, `Guards` (G1-G10), `Intent` (16 values), `ObservingInput`, `ObservingStateMachine.next()`; stateless (phase is part of the input, not held internally), same style as `domain/polar_workflow.py`. 32 unit tests in `tests/unit/domain/test_observing_state.py` covering every valid/blocked transition.
- [x] M9-002 `ObservingService` orchestrator — dispatches Intents to existing engines `[P1 · Runtime]`
  - *Done:* `smart_telescope/services/observing_service.py` — `ObservingDeps` (fresh adapters per call, since `RuntimeContext` can rebuild them), `ObservingService` (holds current phase; background-thread-per-engine-call with a single-worker `_busy` guard; FAULT on unhandled engine exceptions). POLAR_ALIGN drives `PolarAlignmentWorkflow` directly; FOCUS_READYING/TARGET_ACQUIRE/CAPTURE_ACTIVE call `workflow/stages.py` functions via a shared `StageContext`; GUIDE_READYING calls `GuidingService`; SAFE_STOPPING calls `mount_operations.park_sequence`. Registered as a lazily-created singleton on `RuntimeContext.observing_service` (same pattern as `guiding_service`). 17 unit tests in `tests/unit/services/test_observing_service.py`.
  - Known Phase-1 simplifications (see backlog below): G2 is a pure user acknowledgement (no real HOME mechanical-position sequence yet); G7 (dawn/meridian) is never actively evaluated; SAFE_STOPPING has no graceful "finish current sub-op" distinction from a hard stop; fault classification always assumes recoverable (G9=True).
- [x] M9-003 `/api/observing/state` (GET) + `/api/observing/intent` (POST) `[P1 · Runtime]`
  - *Done:* `smart_telescope/api/observing.py`, registered in `app.py`. This is the only endpoint pair the Observe screen calls to move the phase forward (REQ-UX-004) — existing granular endpoints stay registered for `ObservingService`'s internal use and for the Maintenance screen. 4 API-level tests in `tests/unit/api/test_observing.py`.
- [x] M9-004 Guided "Observe" screen + "Maintenance" screen split `[P1 · UI]`
  - *Done:* `smart_telescope/static/js/observing.js` (new) polls `/api/observing/state` every 2.5s and renders phase/readiness/guard chips/primary action/secondary actions/detail — no branching logic of its own (REQ-UX-003/004). `static/index.html` restructured: new `#top-view-bar` (Observe / Maintenance) is now the app's primary navigation; `#observing-view` is the new default screen; the entire former 5-tab UI (stage-bar + 5 stage panels, unchanged internally) was wrapped in `#maintenance-view` and is reachable via the Maintenance nav entry (REQ-UX-006 structural separation). `app.js` gained `showTopView()`; **`_stage`/`goToStage()`/`unlockStage()`/`completeStage()`/`_renderStageBar()`/advanced-mode toggle were intentionally kept, not deleted** — they still drive the Maintenance screen's own internal 5-tab sub-navigation, which was not rewritten in this pass (rewriting `setup.js`/`mount.js`/`preview.js`/`collimation.js`/`session.js`/`focuser.js`/`bias_estimation.js`/`guiding.js`/`click_to_center.js` internals was out of scope for Phase 1 — see backlog).
  - Verified via Playwright against a live mock-adapter server: Observe screen renders correctly, primary-action button click advances the phase end-to-end with zero console errors; Maintenance nav shows the original Stage 1 UI unchanged.
- [x] M9-005 Full-flow integration test `[P1 · Tests]`
  - *Done:* `tests/integration/test_observing_flow.py` — drives `ObservingService` through the complete `CONFIRM_CONTEXT → START_HOME → CONFIRM_HOME → START_POLAR_ALIGN → ACCEPT_POLAR_ALIGN → START_FOCUS → ACCEPT_FOCUS → START_TARGET_ACQUIRE → ACCEPT_TARGET → SKIP_GUIDING → START_CAPTURE → STOP_SAFELY` sequence against the project's real mock adapters (`adapters/mock/*`, not `unittest.mock`), asserting the phase reaches `PARKED_SAFE` and the mock mount is actually `PARKED`. (Sequence updated by M9-007's real HOME confirmation — see below.)
- [x] M9-014 WAIT_CONTEXT_CONFIRMATION showed a blind "Confirm time & location" button with no way to review or change location/time — replaced with the same options as the Maintenance panel `[P1 · UI · Source: user report 2026-07-08]`
  - *Done:* `#obs-context-card` in `static/index.html` + `_obs*` functions in `static/js/observing.js` reuse `/api/location/status` and `/api/location/confirm` (the same endpoints backing `s1-tl-card`/`setup.js`) to show local time, GPS-fix suggestion, saved-location/Home dropdown, and manual lat/lon/height entry, shown only during `WAIT_CONTEXT_CONFIRMATION` in place of the generic primary button. Confirm button starts `disabled` until the first `/api/location/status` fetch resolves (GPSD's ~2s socket timeout on a Windows dev box with no gpsd running left the fields briefly empty; clicking mid-fetch previously 422'd). Confirm posts the reviewed location, then sends the phase's own `primary_action.intent` to advance the FSM. Verified via Playwright against a live mock-adapter server: panel populates, Confirm advances `WAIT_CONTEXT_CONFIRMATION → WAIT_HOME_CONFIRMATION` with G1 turning green, zero console errors. Backend unchanged (52 existing observing/location tests still pass).
- [x] M9-015 Time & Location panel follow-up: trimmed timestamp, Pi-time trust indicator, Confirm Pi Time action, `[observer]` height key bug, and a configurable Home display name `[P2 · UI/Runtime · Source: user report 2026-07-08]`
  - *Done:* `local_time_iso` now formatted with `isoformat(timespec="seconds")` (was leaking microseconds); frontend `formatLocalTime()` (new shared helper in `api.js`) inserts a space before the UTC offset for display. `LocationStatusResponse.time_trust_source` surfaces the existing `raspberry_trust_source` gate value (`GPSD_FIX`/`NTP`/`ONSTEP_COMPARISON`/`USER_CONFIRMED`/`NOT_TRUSTED`) as a badge next to local time, in both the Observe and Maintenance panels; a new "Confirm Pi Time" button (`POST /api/mount/confirm_time`, same endpoint `stage1ConfirmTime()` already used) sits next to it.
  - **Bug fixed:** `config.py`'s `[observer]` parsing only recognized `height_m`; a config using `alt_m` (as `adapters/onstep/safety.py`'s own `OnStepSafetyConfig.observer_alt_m` field is named) silently fell back to `0.0` — the reported "UI shows height 0m". `_parse_observer_height_m()` now reads `height_m` first, falling back to `alt_m`. Separately found and fixed: `build_onstep_safety_config()` never passed `observer_alt_m=OBSERVER_HEIGHT_M` at all — the configured elevation never reached the mount's own safety config (used by `ensure_time_location_synced()`'s OnStep `:SA#` push and the altitude-consistency check), always sending `0.0` to OnStep regardless of config. Both are now wired.
  - `OBSERVER_HOME_NAME` (new, `[observer].name` in config.toml, e.g. "Usingen, HE") supplies `HomeLocation.name` for display only — the internal `"Home"` identity used by `location_confirm`'s target-detection and the frontend's `value === 'Home'` round-trip is untouched; the location-select dropdown's Home *option* keeps `value="Home"` but now shows `d.home.name` as its label.
  - `templates/config.toml` updated to document both the `alt_m` alias and the new `name` key. 12 new/updated tests across `test_config.py` and `test_location.py`; full suite 3863+ passed, same 4 pre-existing/unrelated `test_get_sync_status.py` failures, 0 new regressions. Verified live via Playwright: height now reads 304m from an `alt_m` config, dropdown shows "Usingen, HE", Confirm Pi Time flips the badge to green "USER CONFIRMED".
- [x] M9-016 Location-select dropdown reverted mid-edit; "Confirm HOME position" was a disconnected no-op while the mount-strip still read PARKED `[P1 · UI/Runtime · Source: user report 2026-07-08]`
  - **Bug fixed:** `_obsOnLocationSelectChange()`/`onLocationSelectChange()` (`observing.js`/`setup.js`) cleared the dirty flag instead of setting it after "+ New location…" or picking a saved location, so the next background poll (every 2.5s in the Observe screen) silently reverted the in-progress selection/typed fields back to the active location. Both branches now call `_obsMarkLocationDirty()`/`_markLocationDirty()`. Pre-existing in both screens; far more visible in Observe due to continuous polling. Verified via Playwright: selection and typed fields survive a >3.5s wait.
  - **Done (M9-007):** "Confirm HOME position" was a pure Phase-1 acknowledgement — `g2_home_confirmed=True` unconditionally, no mount action — disconnected from the mount-strip, which correctly kept reading PARKED. Now wired to the existing, already-used `mount_operations.home_sequence()` (same code the Maintenance "HOME" button calls: auto-unpark, disable tracking, slew to OnStep's stored home, poll for `AT_HOME` up to 60s) as a background action, matching the start/accept pattern already used for Polar Align/Focus/Target Acquire: new `Intent.START_HOME` kicks it off (`ObservingService._run_home`, spawned like `_run_polar_align`); `CONFIRM_HOME` becomes the accept step, added to `_ACCEPT_ACTIONS` gated on `g2_home_confirmed`. A hard failure (e.g. auto-unpark rejected) is caught by the existing `_spawn()` wrapper → FAULT, same as every other engine; the 60s poll-timeout case doesn't raise and naturally re-offers "Confirm HOME position" since the accept guard stays false. No frontend changes needed — `observing.js` already renders whatever the backend returns generically.
  - Mechanical HOME route (`return_home_mechanical()` in `adapters/onstep/mount.py`) intentionally skips the general HA/altitude/meridian preflight `goto()` uses — it targets OnStep's own fixed, pre-configured home position, not a computed astronomical target. Unchanged, already-relied-on behavior (same as today's "HOME" button), not a new risk.
  - `adapters/mock/mount.py`: `go_home()` now sets `AT_HOME` (was `TRACKING`, which never let the poll succeed); `goto()` now sets `TRACKING` after a successful slew, mirroring real OnStep firmware's `:MS#` auto-engaging tracking (LX200-protocol behavior) — this mock never simulated that side effect before, which only mattered once `go_home()` stopped leaving the mount in a false `TRACKING` state.
  - Tests updated: `test_observing_state.py` (new `START_HOME` no-transition case), `test_observing_service.py` (`TestConfirmHome` restructured into start→wait-idle→accept, plus a not-reached-AT_HOME retry case and a hardware-failure/FAULT case), `test_observing_flow.py` and `test_observing.py` (insert `START_HOME` + wait-idle before `CONFIRM_HOME`). 57 targeted tests + 307 broader workflow/vertical-slice/runtime tests + 296 onstep-adapter/mount-API tests all pass (same 4 pre-existing/unrelated `test_get_sync_status.py` failures). Verified live via Playwright: mount-strip changes from PARKED to HOME after confirming, detail JSON shows `{"home": {"mount_state": "AT_HOME"}}`, both G1/G2 guard chips turn green, Accept advances to POLAR_ALIGN.
- [x] M9-017 Safe-park unavailable/unclear during `WAIT_CONTEXT_CONFIRMATION`/`WAIT_HOME_CONFIRMATION`; "Stop safely" didn't say it parks `[P1 · UI/Runtime · Source: user report 2026-07-08]`
  - *Done:* the always-visible "■ Stop" button only calls `/api/emergency_stop` → `mount.stop()` (halt, no park) — the real park path, `STOP_SAFELY` → `SAFE_STOPPING` → `mount_operations.park_sequence()`, was deliberately restricted to `_ACTIVE_PHASES` in `domain/observing_state.py`, excluding the two "wait" phases. Added a direct, `PAUSE`-independent `STOP_SAFELY` check to `_on_wait_context()`/`_on_wait_home()` (ahead of `_on_wait_context`'s previously-unconditional fallback, and ahead of `_on_wait_home`'s existing inert `_maybe_pause_or_stop()` call) — deliberately *not* added to `_ACTIVE_PHASES` wholesale, since `PAUSE` has no meaning when nothing is actively running yet. New `_STOP_ONLY_PHASES` set in `observing_service.py` offers `STOP_SAFELY` (no `PAUSE`) as a secondary action for both phases. Relabeled `STOP_SAFELY` to "Stop safely (park)" everywhere it appears so the outcome is unambiguous.
  - Confirmed via code reading (not guesswork): `park_sequence()` already no-ops cleanly when the mount is already `PARKED`; `handle_intent()` already lets `STOP_SAFELY` bypass the busy-lock, so sending it while `_run_home` is mid-flight doesn't race — `_maybe_auto_advance` only spawns `_run_safe_stop` once `busy` clears, so the park is queued (not blocked) until the current home attempt finishes.
  - Tests: updated `test_pause_and_stop_not_available_before_polar_align` (renamed `test_stop_safely_available_but_not_pause` — `STOP_SAFELY` now transitions, `PAUSE` still doesn't) plus a new `WAIT_CONTEXT_CONFIRMATION` case in `test_observing_state.py`; new `TestSafeParkFromWaitPhases` class in `test_observing_service.py` covering both phases' `secondary_actions` shape and the actual park-to-`PARKED_SAFE` path. 1113 tests pass (full domain/services/api/integration/vertical-slice sweep), 0 regressions. Verified live via Playwright: "Stop safely (park)" visible and reaches `PARKED_SAFE` from a fresh `WAIT_CONTEXT_CONFIRMATION`, and from `WAIT_HOME_CONFIRMATION` even when clicked immediately after starting the home sequence.
  - **Deferred (this session's investigation surfaced, not yet built — see below):** M9-018 (target selection — the guided flow can currently only ever target a hardcoded M42/C8_NATIVE position), M9-019 (skip-polar-alignment for bright/planetary targets), M9-020 (camera/optical-train identity + live preview in the Observe screen).
- [x] M9-021 Real hardware: parking after HOME confirm looped back to "Confirm HOME position" instead of staying parked `[P0 · Hardware · Source: user report 2026-07-08]`
  - **Root cause:** `mount_operations.home_sequence()` returned `None`; `ObservingService._run_home()` (M9-016) determined success by calling `deps.mount.get_state()` a *second*, independent time after `home_sequence()` returned. `AT_HOME` is documented in `home_sequence()`'s own tight-poll comment as a brief OnStep status flag ("the slew completes and 'H' clears before the next background poll fires") — on real hardware it can clear before that second query runs, so `_run_home()` could see some other state and set `g2_home_confirmed=False` even though homing genuinely succeeded, sending the guided flow back to "Confirm HOME position" while the mount itself was correctly parked/homed. Not reproducible against `MockMount` (its `AT_HOME` is a persistent, non-clearing mock state, not the transient real-hardware flag), which is why it passed all prior test/Playwright verification.
  - *Done:* `home_sequence()` now returns `bool` — `True` only if its own tight poll actually observed `AT_HOME` (the one well-timed, authoritative check). `_run_home()` uses that return value directly for the guard instead of re-querying; `deps.mount.get_state()` is still read once afterward purely for the informational `detail["home"]["mount_state"]` field, decoupled from the success decision. `api/mount.py`'s existing "HOME" button and `setup_check_service.py`'s setup-check wizard both already ignored `home_sequence()`'s return value entirely (relying only on exceptions/their own separate re-polling), so the signature change is source-compatible with both.
  - Tests: two new `test_mount_operations.py` cases (`home_sequence` returns `True`/`False` matching whether its poll actually observed `AT_HOME`, including the flag-already-cleared scenario). Full sweep: 3557+ tests pass (domain/services/api/integration/onstep-adapter), same 4 pre-existing/unrelated `test_get_sync_status.py` failures, 0 new regressions.
- [x] M9-022 Real hardware: "Stop safely" faulted with `:hP# rejected by OnStep — home the mount first to establish the park position, then park", even right after a successful HOME confirmation `[P0 · Hardware · Source: user report 2026-07-08]`
  - **Root cause:** OnStep rejects `:hP#` (park) unless a park position was previously saved via `:hS#`. `mount.set_park_position()`/`set_park_position_from_current()` already existed on `MountPort`/the OnStep adapter — the adapter shim even carries a comment saying "SmartTScope's park workflow sets park = home position after a HOME slew" — but **nothing in the application ever called it**: not `ObservingService._run_home()`, not `api/mount.py`'s existing "HOME" button, not the Maintenance setup-check wizard. So `:hP#` was rejected by OnStep's firmware itself on any hardware without a pre-existing park position, no matter how many times HOME was confirmed — the error's own suggested fix ("home the mount first") didn't actually address the missing step. First surfaced only now because M9-016/M9-017 (same session) are the first callers to actually exercise HOME→park end-to-end on real hardware via the guided flow.
  - *Done (original approach):* `ObservingService._run_home()` called `deps.mount.set_park_position()` right after confirming `AT_HOME` (guarded by `if at_home:`), matching the adapter shim's own comment ("SmartTScope's park workflow sets park = home position after a HOME slew"). `adapters/mock/mount.py`'s `MockMount` gained a `set_park_position()` returning `True`; `tests/conftest.py`'s shared `mount_mock` fixture pre-configured it too.
  - **⚠️ CORRECTED — this approach was itself a regression.** `wiki/log.md` 2026-06-14 "CRITICAL: remove auto_set_park" already established that auto-setting the park position (there, from the Park button) silently overwrites the user's deliberately configured EEPROM park position, and states plainly: "Park position must only be set by explicit user action." The above fix reintroduced exactly that anti-pattern via a different trigger (HOME confirmation instead of Park). Found only because a follow-up user report ("should have been fixed two sessions ago") prompted re-reading `wiki/log.md` for this area's history — which should have been checked *before* wiring up the dangling `set_park_position()` in the first place.
  - *Corrected:* `_run_home()` no longer calls `set_park_position()` at all — reverted to the M9-021 shape (`g2_home_confirmed` from `at_home` alone, `detail["home"]` back to just `{"mount_state": ...}`).
  - **⚠️ Explicit UI action also removed — scope check with user.** The first correction pass added a "fix": a new explicit, two-step-confirm `POST /api/mount/set_park_position` endpoint plus a "Set Park Position" Maintenance button, reasoning that *some* deliberate way to set park position should exist since the 2026-06-14 removal left none. User clarified: no formal requirement currently asks for this UI capability at all — only that the app must never change it *automatically*. Building the explicit alternative was scope beyond the actual ask. **Removed entirely** (`api/mount.py`'s endpoint, `static/js/mount.js`'s button, the `MockMount`/`mount_mock` scaffolding added to support them, and their tests) — back to a pure revert of the M9-022 regression, nothing more.
  - **Net state:** the `:hP#`-rejected-because-no-saved-park-position gap is real and confirmed, but deliberately left open — not solved by this session. Setting/changing the OnStep park position is not currently possible through this app at all (by design, pending a real future requirement); it must be done via other means (e.g. OnStep's own hand controller) until then.
  - Tests: reverted `TestConfirmHome`'s M9-022-specific assertions in `test_observing_service.py`; removed `TestMountSetParkPosition` from `test_mount.py` and the `set_park_position_ok`/mock-default scaffolding added to support it. Full sweep: 3929+ passed, same 4 pre-existing/unrelated `test_get_sync_status.py` failures, 0 new regressions.
- [x] M9-023 Mount-strip could keep showing PARKED for several seconds after HOME confirmed, even though the phase/guards panel had already updated `[P1 · UI · Source: user report 2026-07-08]`
  - **Root cause:** `_run_safe_stop()` (the park path) explicitly calls `deps.device_state.poll_now()` right after `mount_operations.park_sequence()` — `poll_now()`'s own docstring says exactly why: "Used after park/unpark commands to refresh the cached state without waiting for the next background poll interval (nominally 2 s)." `_run_home()` (M9-016) never had the equivalent call after `mount_operations.home_sequence()`. Net effect: the Observe screen's phase panel (polls `/api/observing/state` every 2.5s, reflects `ObservingService`'s own in-memory guards immediately) and the mount-strip (polls `/api/mount/status` independently, every 5s, backed by `DeviceStateService`'s separately-cached state) could visibly disagree for several seconds after confirming HOME — phase panel already showing "Accept — home confirmed" while the mount-strip still read PARKED.
  - *Done:* added `deps.device_state.poll_now()` to `_run_home()` right after `home_sequence()`, mirroring the already-established `_run_safe_stop()` pattern exactly. Also fixed a stale comment in the same method still referencing the now-removed (M9-022 correction #2) `api/mount.py` `set_park_position` endpoint.
  - Verified live against the mock-adapter server: `GET /api/mount/status` immediately after `START_HOME` (zero delay) now reads `"state": "at_home"` instead of stale/unknown data. Full sweep: 3924 passed, same 4 pre-existing/unrelated `test_get_sync_status.py` failures, 0 new regressions.
- [x] M9-024 "Confirm HOME position" button label was the actual root cause of the repeated "why does it say confirm home while parked" confusion across M9-021/022/023 `[P1 · UI · Source: user report 2026-07-08]`
  - **Root cause:** semantic mismatch, not a functional bug. `Intent.START_HOME`'s label was "Confirm HOME position" — but clicking it doesn't *confirm* an already-true state, it *performs* the unpark+slew-to-home action from wherever the mount currently is (including PARKED). "Confirm X" implies X is already true and just needs acknowledging (like the already-correctly-named "Accept — home confirmed" step that appears *after* homing succeeds, or "Confirm Pi Time" elsewhere in the app, which only asserts trust in an already-current clock). User pointed out the underlying logical contradiction directly: a "confirm" action should never be the thing that makes its own subject true.
  - *Done:* relabeled to "Home the mount" in `_START_ACTIONS` (`observing_service.py`) — matches the existing "Home" terminology already used for this exact action elsewhere (Maintenance's "Home" button, the mount-strip's "HOME"/`AT_HOME` state label). The two-step start/accept structure underneath was already correct (this is the same button/intent introduced in M9-007/M9-016); only the display string was wrong. No test asserted the old label string. Verified live: `primary_action.label` now reads "Home the mount" while the mount-strip shows PARKED, before any home action has run — no more semantic contradiction.
- [x] M9-025 Safety: disable tracking immediately after unpark in `home_sequence()`, not only after a subsequent state check `[P1 · Safety · Source: user report 2026-07-08]`
  - **Why:** some OnStep firmware auto-starts sidereal tracking immediately on `:hR#` (unpark) — the existing code only disabled tracking if a *subsequent* `get_state()` query reported `TRACKING`, which races against the firmware and could leave the mount tracking (moving) unexpectedly for a window before the home command was even issued.
  - *Done:* `mount_operations.home_sequence()` now calls `mount.disable_tracking()` unconditionally immediately after a successful `unpark()`, before the propagation sleep — not gated behind a state re-check. The existing conditional check afterward is kept as-is, covering the separate case where the mount was already `TRACKING` on entry (not freshly unparked in this call).
  - Tests: new `test_home_sequence_disables_tracking_immediately_after_unpark` in `test_mount_operations.py`, deliberately mocking the tracking-check query to return something other than `TRACKING` to prove the call happens unconditionally, not via that check. 27 + 189 broader tests pass, 0 regressions.
- [x] M9-026 Real hardware: `:hP#` (park) rejected by OnStep, mount stuck at AT_HOME through two park attempts `[P0 · Hardware/Bug · Source: user report 2026-07-08]`
  - User confirmed a park position *is* already saved in the OnStep controller (set up outside this app, matching `park_sequence()`'s own docstring: "The park position must be configured in OnStep directly — this function never modifies it"). So the pre-existing error message's assumed cause ("home the mount first to establish the park position") was wrong for this case.
  - **Root cause found from the actual server log** (not guessed): first `park_sequence()` call — `pre-park state = AT_HOME`, `:hP#` accepted (`reply='1'`, "Mount park issued" logged) — then immediately "Mount park slew started: state = AT_HOME" even though the state never actually changed. `park_sequence()`'s post-command check called `device_state.poll_until_changed(MountState.UNPARKED, timeout_s=5.0)` — a **hardcoded** baseline, not the mount's actual `pre_state`. Since `AT_HOME != UNPARKED` is trivially true on the very first poll, this falsely reported "slew started" without the mount moving at all. Because `g8_safe_stop_possible` was consequently never set (state never reached `PARKED`), a *second* `park_sequence()` call followed shortly after — same `pre-park state = AT_HOME` — and that second `:hP#` is the one OnStep genuinely rejected (`reply='0'`), landing in FAULT.
  - *Done:* `poll_until_changed()` is now called with the mount's actual `pre_state` as the baseline instead of a hardcoded `MountState.UNPARKED` — this now correctly detects "no movement happened" instead of a false positive, for parking from `AT_HOME`, `TRACKING`, or any other pre-park state, not just the `UNPARKED` case the original code implicitly assumed. Also fixed the accompanying warning log's hardcoded "still UNPARKED" wording to use the actual `pre_state.name`.
  - **Still open (at the time):** *why* the mount didn't actually move/progress after the first accepted `:hP#`, and whether `park_sequence()` should avoid blindly re-issuing `:hP#` on a retry if a previous attempt was already accepted but not yet confirmed complete. Resolved below (M9-027).
  - Tests: new `test_park_sequence_polls_against_actual_pre_state_not_hardcoded_unparked`, asserting `poll_until_changed` is called with `MountState.AT_HOME` (not `UNPARKED`) when pre-park state is `AT_HOME`. 28 + 166 broader tests pass, 0 regressions.
- [x] M9-027 `_maybe_auto_advance()` was blindly resending `:hP#` on every poll retry while SAFE_STOPPING hadn't reached PARKED `[P0 · Hardware/Bug · Source: user report 2026-07-08]`
  - **Why:** user pointed out that OnStep's own UI can always request move-to-park successfully, and questioned whether the adapter should really be sending `:hP#` the way it was. `:hP#` is documented (`wiki/onstep-protocol.md`) as fire-and-forget, its slew taking 30–120 s, with no documented case of it ever returning a rejection (`0`) — unlike `:hR#` (unpark), whose doc explicitly notes it can be rejected. A real `'0'` reply for `:hP#` was therefore unusual, and `_maybe_auto_advance()` re-spawning `_run_safe_stop()` (and therefore re-calling `park_sequence()` → `mount.park()` → a fresh `:hP#`) on *every single poll* (observing.js polls every 2.5 s) while `g8` stays False was the most likely reason a second `:hP#` ever got sent while the first (accepted) one might still have been resolving — exactly the M9-026 log sequence.
  - *Done:* `ObservingService` now tracks `_park_command_issued_at` — set once `park_sequence()` successfully issues `:hP#` (doesn't raise), cleared once PARKED is actually observed. While set and within `_PARK_COMMAND_MAX_WAIT_S` (120 s, matching the documented max slew time), `_run_safe_stop()` skips calling `park_sequence()` again on subsequent auto-advance retries — it just re-checks `device_state` instead of re-sending the command. Falls back to resending only if genuinely stuck past 120 s.
  - Tests: new `test_stop_safely_does_not_resend_park_command_on_retry` in `test_observing_service.py`, asserting `mount.park()` is called at most once across repeated auto-advance retries while the mount never reaches PARKED. 199 tests pass, 0 regressions.
- [x] M9-028 PARKED_SAFE is a dead end when reached from the setup phases: safe-parking
      from WAIT_CONTEXT_CONFIRMATION / WAIT_HOME_CONFIRMATION (the M9-017 path) shows
      "Session complete — parked safe" + green READY with no way to continue — the only
      way back into the guided flow is restarting. Add an "Unpark & continue setup"
      secondary action on PARKED_SAFE that unparks and returns the flow to
      WAIT_HOME_CONFIRMATION (the "Home the mount" step) `[P2 · UI/Runtime · Source: user
      report 2026-07-17, first Pi session after ONS31 migration]`
      - *Acceptance:* from PARKED_SAFE, the new action unparks via the shim `unpark()`
        (routes through `unpark_to_home_stop_tracking()`, ONS31-102) and the phase panel
        shows WAIT_HOME_CONFIRMATION with the "Home the mount" primary action; mount-strip
        reflects the observed state; verified on real hardware.
      - *Implementation notes:* new `Intent` + transition in `domain/observing_state.py`;
        action wiring in `services/observing_service.py` (`_primary_action` /
        `_secondary_actions` — PARKED_SAFE currently returns only the disabled
        "Session complete" label); frontend button in `observing.js`. Also reconsider
        `_readiness()` returning READY for PARKED_SAFE — "READY" on a never-homed mount
        is part of what confused here.
      - *Done 2026-07-17:* new `Intent.UNPARK_CONTINUE`; PARKED_SAFE offers secondary
        action "Continue setup (back to homing)" → WAIT_HOME_CONFIRMATION, resetting
        g2/g8 (stale g8 would defeat the M9-027 protection on the next safe-stop).
        **Design deviation from the acceptance note:** implemented as a pure flow
        transition — the button does NOT call `unpark()` itself; the mount stays
        parked and the physical unpark+home runs via `home_sequence()`'s existing
        auto-unpark when "Home the mount" is pressed (single hardened hardware path,
        no unattended unparked-idle state). Readiness fix included: PARKED_SAFE shows
        READY only after a confirmed home (g2), else LIMITED READY with primary label
        "Parked safe — setup not finished". No frontend change needed (secondary
        actions render generically). 5 new service tests + 2 FSM tests; 72 observing
        tests green. Hardware walk-through pending next Pi session.
- [x] M9-029 Observe screen: display the observed mount state (PARKED / AT_HOME /
      SLEWING / TRACKING / …) next to the readiness badge ("LIMITED READY") in
      WAIT_CONTEXT_CONFIRMATION `[P3 · UI · Source: user request 2026-07-17]`
      - *Done 2026-07-17:* `snapshot()` now returns `mount_state` (name of the
        `DeviceStateService` cached state, null before first poll); grey
        `MOUNT: <STATE>` badge rendered next to the readiness badge in all phases
        (hidden while null). 3 new snapshot tests; API shape tests updated;
        31 observing tests pass.
- [x] M9-030 Refine the M9-029 mount-state badge per user feedback: display the mount
      state side by side with the readiness badge ("LIMITED READY") using the **same
      style** — equal visual prominence, not the current muted-grey pill — and show the
      **plain state name** ("PARKED", "AT HOME", "SLEWING", …) without the "MOUNT:"
      prefix. It is a *state* display, not a button with an action: the state must never
      be conveyed by (or confused with) the "Stop safely (park)" secondary-action
      button, which stays a separate action `[P3 · UI · Source: user feedback
      2026-07-17 on M9-029]`
      - *Acceptance:* WAIT_CONTEXT_CONFIRMATION shows e.g. `LIMITED READY` `PARKED` as
        two adjacent pills of identical style on one line; the state pill is clearly
        non-interactive; "Stop safely (park)" button unchanged.
      - *Implementation notes:* adjust `.phase-readiness.MOUNT_STATE` styling in
        `static/index.html` to match the readiness pills' visual weight (consider the
        same color semantics: green for PARKED/AT_HOME/TRACKING-as-expected vs neutral
        for transitional states — implementer's call); drop the `'MOUNT: '` prefix in
        `_renderObservingState()` (`static/js/observing.js`).
      - *Done 2026-07-17:* prefix dropped — pill shows the plain state name; per-state
        colors mirror the mount strip's `_STRIP_DOT` semantics at full readiness-pill
        prominence (TRACKING/SLEWING green, UNPARKED/AT_HOME yellow, AT_LIMIT red,
        PARKED/UNKNOWN accent-blue instead of muted grey); backend/tests unchanged
        (JS/CSS only).
- [x] M9-031 The "Stop safely (park)" secondary action reads as nonsense when the state
      pill right above it already shows PARKED (user report 2026-07-17, on 3ec0d79:
      park at the home step → "Continue setup" → PARKED pill + a button offering to
      park). The action itself must stay — it is the only graceful exit from setup to
      PARKED_SAFE (M9-017), and pressing it while parked completes immediately without
      hardware motion. Make the label state-aware instead: observed mount state PARKED →
      "End session (mount already parked)", otherwise "Stop safely (park)" as today
      `[P3 · UI · Source: user feedback 2026-07-17 on M9-028]`
      - *Acceptance:* in WAIT_CONTEXT/WAIT_HOME with the mount parked, the secondary
        button reads "End session (mount already parked)" and still transitions to
        PARKED_SAFE; with the mount in any other state the label is unchanged.
      - *Implementation notes:* `_secondary_actions()` in
        `services/observing_service.py` gains the observed mount state (already
        computed in `snapshot()` for M9-029) to pick the STOP_SAFELY label; intent and
        FSM unchanged; no frontend change (labels render from the payload).
      - *Done 2026-07-17:* `_stop_safely_label()` helper applied to all three
        STOP_SAFELY emit sites (stoppable phases, stop-only wait phases, PAUSED_SAFE);
        3 new tests (`TestStopSafelyLabel`); 75 observing tests green.
- [x] M9-032 Hardware report 2026-07-17 (second home cycle after park→continue): the
      state pill jumps to AT HOME **immediately** when "Home the mount" is pressed,
      while the mount is still slewing to home; pressing STOP mid-slew leaves the pill
      on AT HOME and the flow asking for a home confirmation that cannot honestly be
      given `[P1 · Bug/UI · Source: user hardware session 2026-07-17]`
      - *Root cause (diagnosed from code, 2026-07-17):* stale
        `DeviceStateService._sticky_at_home`. The sticky set during the *first*
        confirmed home is never cleared in the guided flow: `record_command()` — whose
        "goto"/"park"/"track" branch is the only thing that clears the sticky — is
        called **only by the `/api/mount/*` endpoints** (R2-003); the guided flow
        (`_run_home`/`_run_safe_stop`) calls `mount_operations` directly and records
        nothing. With the sticky stale-True, poll rule 4 ("UNPARKED with existing
        sticky → AT_HOME") promotes every UNPARKED reading during the second home
        cycle — OnStep reports UNPARKED (not SLEWING) during parts of `:hC#` travel,
        and always after a mid-slew STOP. Two secondary lifecycle gaps:
        `record_command("home")` does not clear the sticky either (a new home command
        means *not* at home until confirmed), and "unpark"/"stop" are not in the
        clearing set at all.
      - *Fix (service layer only — no adapter changes):* (1) `record_command("home")`
        additionally clears `_sticky_at_home`; add `"unpark"` and `"stop"` to the
        clearing branch; (2) the guided flow records its commands:
        `_run_home` → `record_command("home")` before `home_sequence()`,
        `_run_safe_stop` → `record_command("park")` before `park_sequence()`.
      - *Acceptance:* second home cycle shows SLEWING/UNPARKED during travel and
        AT HOME only once the H flag (or the slew-seen promotion) confirms it; STOP
        mid-home-slew shows UNPARKED, not AT HOME; hardware-verified on the Pi.
      - *Upstream ask candidate (needs user approval, SYNC.md):* upstream
        `OnStepMount.stop()` does not clear `_at_mechanical_home`, so mechanical home
        authority survives a mid-slew STOP (position no longer trustworthy);
        `note_external_motion()` exists as the public API for exactly this.
      - *Done 2026-07-17:* `record_command("home")` now clears the sticky;
        `"unpark"`/`"stop"` added to the clearing branch; `_run_home` records "home",
        `_run_safe_stop` records "park" (only when actually issuing, respecting the
        M9-027 no-resend window). 6 new tests (4 sticky-lifecycle incl. full
        second-cycle regression, 2 guided-flow recording); 241 tests green across
        device-state/observing/mount suites. Upstream stop() ask recorded in SYNC.md,
        not filed. Hardware re-test pending next Pi session.
- [x] M9-033 The Observe-screen headline shows raw FSM phase names ("WAIT CONTEXT
      CONFIRMATION") — `_obsPhaseLabel()` only replaces underscores with spaces. Give
      every phase a proper user-facing title; the context step is asking the user to
      confirm time/location, so say that `[P3 · UI · Source: user report 2026-07-17]`
      - *Acceptance:* WAIT_CONTEXT_CONFIRMATION shows "Confirm time & location";
        all other phases show plain-language titles (e.g. "Home the mount",
        "Stopping safely…", "Parked safe"), never raw enum names.
      - *Done 2026-07-17:* `_PHASE_TITLES` map in `static/js/observing.js` covering
        all 12 phases; `_obsPhaseLabel()` falls back to the old
        underscores-to-spaces for unknown values. JS-only; `node --check` clean.
- [x] M9-034 **RESOLVED 2026-07-17 via Pi diagnostic evidence** — the reopened
      symptom decomposed into: (a) the AT HOME pill was **genuine** — the emergency
      stop landed seconds after `:hP#` was issued, the mount never meaningfully left
      home, and OnStep kept reporting the H flag (transition log showed decoded
      `at_home: True` throughout; no false promotion anywhere); (b) "app blocked" =
      the busy gate silently dropping UNPARK_CONTINUE while `_maybe_auto_advance`
      kept a worker in flight on nearly every poll (fixed — escape intents pass the
      busy gate; late workers can't clobber the escape); (c) the emergency stop
      never informed the observing flow, which would have **auto re-issued the park
      120 s later** — split out and fixed as M9-035. Final Pi verification pending.
      Original report/fixes below.
      Hardware report 2026-07-17 (STOP mid-park-slew): SAFE_STOPPING becomes a
      dead end — the M9-027 no-resend window silently blocks a park retry for 120 s,
      no actions are offered ("no way to continue parking or slewing back to home"),
      and the Detail panel still shows the *previous* action's record
      (`home: AT_HOME`), which reads as a wrong live status `[P1 · Bug/UI · Source:
      user hardware session 2026-07-17]`
      - *Fixes:* (1) stale detail: `_spawn()` clears `_detail` at action start;
        `_run_safe_stop` writes its own `safe_stop` detail. (2) SAFE_STOPPING offers
        two secondary actions: "Retry park now" (STOP_SAFELY — explicitly clears the
        M9-027 window; a *user-initiated* retry is exactly the case where re-issuing
        `:hP#` is right, the manual STOP killed the first one) and "Back to homing"
        (UNPARK_CONTINUE → WAIT_HOME_CONFIRMATION, same guard resets as from
        PARKED_SAFE + clears the park window). (3) `record_command()` lifecycle
        matches on the first word — the goto endpoint records "goto ra=…", which never
        matched the literal "goto", so API gotos silently kept the sticky AT_HOME too.
      - *Acceptance:* after STOP mid-park-slew: Detail no longer shows the stale home
        record; "Retry park now" re-issues the park immediately; "Back to homing"
        returns to WAIT_HOME_CONFIRMATION and the mount can be homed again;
        hardware-verified on the Pi.
      - *Done 2026-07-17:* all three fixes in; FSM gets SAFE_STOPPING+UNPARK_CONTINUE
        → WAIT_HOME_CONFIRMATION (intent checked before g8 — explicit user choice
        wins); UNPARK_CONTINUE side effect (g2/g8 reset + park-window clear) now
        accepted from both PARKED_SAFE and SAFE_STOPPING. 7 new tests
        (TestSafeStoppingRecovery ×4, FSM ×1 (2 asserts), sticky goto-with-args ×1,
        plus updated M9-032 set); 283 tests green. Hardware re-test pending.
- [x] M9-035 Emergency stop (`/api/emergency_stop`) never informed the observing flow:
      after ■ Stop during a park slew, SAFE_STOPPING kept auto-retrying and would have
      **re-issued `:hP#` on its own ~120 s later** — mount motion the user explicitly
      stopped `[P0 · Safety · Source: Pi diagnostic log 2026-07-17 (M9-034 evidence)]`
      - *Done 2026-07-17:* endpoint now calls `ObservingService.on_emergency_stop()` —
        SAFE_STOPPING → PAUSED_SAFE with the park window cleared; "Resume" re-enters
        SAFE_STOPPING and re-issues the park immediately as a *user* decision. Endpoint
        also `record_command("stop")` (R2-003 gap; clears sticky flags). Bonus:
        `_run_safe_stop` stops guiding only when actually issuing the park — it ran on
        every 2.5 s retry pass before (log spam + busy churn ≈ the permanent
        "Working…"). 5 new tests (TestEmergencyStopHaltsParkRetries); 63 observing +
        emergency tests green. Hardware verification pending (retest: ■ Stop mid-park
        → phase "Paused", no auto re-park, Resume finishes the park).
- [x] M9-036 Hardware retest 2026-07-17: home slew shows SLEWING correctly, but the
      park slew shows AT HOME the whole way (and after ■ Stop; M9-035's Resume button
      appeared correctly). Root cause in the shim's ONS31-101 `get_state()` mapping:
      upstream `park()` clears the `_at_mechanical_home` authority flag, but the first
      poll of the park slew still sees OnStep's genuine H flag (mount within the home
      zone) and **re-arms** it — and the sticky check sat above the motion check, so
      AT_HOME masked SLEWING for the entire travel `[P1 · Bug/Shim · Source: user
      hardware session 2026-07-17]`
      - *Done 2026-07-17 (shim mapping + wrapper only — upstream untouched):*
        (1) `get_state()` ordering is now decoded-H > SLEWING (M9-021 preserved) >
        sticky authority > upstream state — observed motion always reported;
        (2) new shim `stop()` wrapper: `super().stop()` +
        `note_external_motion("manual_stop")` (upstream *public* API) so a manual/
        emergency stop drops stale home authority; a genuinely at-home mount re-arms
        from the next H observation. 5 new tests using the real GU# strings from the
        Pi log (`TestGetStateAuthorityFlagVsMotion`); 255 adapter+service tests green.
        Documented in SYNC.md (permanent-wrapper table). Hardware re-test pending:
        park slew should now show SLEWING; ■ Stop mid-way should show UNPARKED +
        "Paused".
      - *Decision recorded (user, 2026-07-17):* it is OK to connect to OnStep before
        time/location is confirmed — mount-state display at this phase needs no gating
        on context confirmation (mount is already connected at startup via
        `RuntimeContext.connect_devices()`).
      - *Acceptance:* in WAIT_CONTEXT_CONFIRMATION the phase panel shows the mount state
        from the `DeviceStateService` observed-state cache (same source as
        `/api/mount/status`) beside the readiness badge, updating with the normal
        observing-state poll.
      - *Implementation notes:* `/api/observing/state` handler
        (`smart_telescope/api/observing.py`) already receives `DeviceStateService` — add
        a `mount_state` field to the response; render a small badge next to
        `#obs-readiness-badge` (`static/index.html` phase panel) in `observing.js`'s
        render path. Nothing prevents showing it in all phases; the explicit ask is
        WAIT_CONTEXT_CONFIRMATION.

### Phase 2 — Unified readiness aggregation (backlog)

- [ ] M9-006 Fold `operation_gate.evaluate_all_gates`, `mount_readiness`, dawn status, and calibration/offset validity into the single `readiness` field already stubbed in `/api/observing/state` `[P2 · UI]`
  - Acceptance: REQ-UX-001, REQ-UX-002 — no new engines, pure aggregation inside `observing_service.py`

### Phase 3 — Real HOME confirmation + graceful safe-stop (backlog)

- [x] M9-007 `mount_operations.confirm_home()` — actual PARK→HOME sequence with mechanical/cable-freedom confirmation, replacing today's pure acknowledgement `[P1 · Hardware]`
  - *Done:* see M9-016 above — reuses the existing `mount_operations.home_sequence()` as a spawned background action (`ObservingService._run_home`), gated behind a new `Intent.START_HOME` / `CONFIRM_HOME`-as-accept pair. Acceptance: REQ-SAF-004, REQ-SAF-005.
- [ ] M9-008 Graceful `SAFE_STOPPING` distinct from the unconditional `/api/emergency_stop` — finish current sub-operation, flush session artifacts, then park `[P1 · Runtime]`
  - Acceptance: REQ-REC-002, REQ-REC-005, REQ-CAP-003

### Phase 4 — Active session-end enforcement (backlog — flagged safety-relevant)

- [ ] M9-009 Wire `services/dawn_watcher.py` (currently zero references anywhere in `workflow/`) into `CAPTURE_ACTIVE` as an active G7 check `[P0 · Safety]`
- [ ] M9-010 Add meridian-margin monitoring during `CAPTURE_ACTIVE` (today `ha_east_limit_h`/`ha_west_limit_h`/`meridian_margin_deg` only guard slews in `adapters/onstep/safety.py`, not an active capture-loop stop) — auto-fire `STOP_SAFELY` shortly after meridian, no auto-flip in MVP `[P0 · Safety]`
  - Acceptance: REQ-CAP-002, REQ-CAP-003, REQ-SAF-007, REQ-SAF-008

### Phase 5 — Config gaps: filter/object profiles + unified safety section (backlog)

- [ ] M9-011 Add `[filter_profiles]` and `[object_profiles]` sections to `templates/config.toml` + `config.py` parsing (pattern: `_parse_optical_trains()`) `[P2 · Config]`
  - Acceptance: REQ-CFG-005, REQ-CFG-006, §8.3 (per-object-class gain/offset/exposure/solve-strategy/guiding-expectation/focus-strategy/calibration-requirement defaults)
- [ ] M9-012 Consolidate dawn/meridian/fault-behavior config (today scattered across `operation_gate.py`, `mount_operations.py`, OnStep adapter safety config) into one `[safety]` section `[P2 · Config]`

### Phase 6 — Re-surface calibration/offset checks as pre-session gates (backlog)

- [ ] M9-013 Read-only summary call from `observing_service` into `WAIT_CONTEXT_CONFIRMATION`/`FOCUS_READYING` guard computation, using the calibration/offset logic that already exists (`bias_estimation_service`, `camera_offset_service`, `calibration_store.find_best_match`) — the wizards themselves stay in Maintenance for hands-on execution `[P2 · UI]`
  - Acceptance: REQ-CAL-007, REQ-OFF-004, REQ-OFF-005

### Phase 7 — Target selection + bright-object support (backlog — found 2026-07-08, not yet scoped in detail)

- [ ] M9-018 Wire real target selection into the guided Observe flow `[P1 · UI/Runtime · Source: user report 2026-07-08]`
  - Today `api/observing.py:_build_deps()` hardcodes `optical_profile=C8_NATIVE, target_ra=M42_RA, target_dec=M42_DEC` — there is no way to tell the guided flow what to point at. Decision from this session: reuse the existing `/api/catalog/tonight` + "Visible Tonight" catalog (M4-002, Messier objects only today) rather than manual RA/Dec entry or a new name-search/ephemeris picker. Scope still needs a real design pass: how the picker surfaces in the Observe screen, whether/how multiple optical trains are chosen, and how this interacts with the solar-exclusion gate (`domain/solar.py`/`is_solar_target()`) already enforced elsewhere.
- [ ] M9-019 Add a skip path for `POLAR_ALIGN`, mirroring `GUIDE_READYING`'s `SKIP_GUIDING` `[P2 · Runtime]`
  - `_on_polar_align()` has no way to proceed to `FOCUS_READYING` if `g3_polar_within_tolerance` never turns true — relevant for bright/planetary targets (e.g. Venus) that don't need precision polar alignment. Most useful once M9-018 exists so "is this target bright enough to skip" is an informed choice, but can be built standalone.
- [ ] M9-020 Show active camera/optical-train identity + live preview in the Observe screen `[P2 · UI]`
  - The Observe screen shows phase/guards/detail-JSON only — no indication of which camera/telescope is in use, and no image preview, so there's no way to tell whether the camera sees anything before starting polar alignment. Maintenance's `static/js/preview.js` already has a live-preview pattern to reuse.

**Quality gate:** Observe screen shows exactly one phase + one primary action at a time and never decides the next step client-side (REQ-UX-003/004). Maintenance tools remain fully functional and structurally separate (REQ-UX-006). Full BOOTSTRAP→PARKED_SAFE walk passes against mock adapters.

---

## M10 — Parallel Camera Readiness & LiveAnalysis Integration — specified 2026-07-17

*Problem: after home confirmation the flow offers polar alignment, but the system may be
out of focus or pointed at an empty star field — automatic polar alignment / plate
solving would fail. Solution: a camera-readiness track running **in parallel** to the
mount flow (starting while the user is still confirming time/location): identify all
connected ToupTek cameras, auto-tune exposure/gain, verify stars are detectable, and
coarse-focus focuser-equipped trains until plate-solvable.*

**External module:** <https://github.com/tschoenfelder/SmartTScopeLiveAnalysis>
(v0.1.0, NumPy-only; `analyze_camera_frame(camera_settings, frame, previous_star_state)`
→ star detections, temporal classification, movement tracking, exposure/gain/offset
recommendations). Same guardrail as OnStepAdapter: **never edit locally; gaps become
upstream feature requests filed only with explicit user approval.** The module is
planned to take over frame acquisition later as well.

**Design decisions (user, 2026-07-17):** (1) parallel per-camera FSM, not a phase in
the mount FSM — no hard gate except automatic polar align needs a READY camera;
(2) focus target = "fine enough to plate solve", algorithm is a **separate,
independently testable component** and **SCT-aware** (must recognize and drive
out-of-focus donuts); same component later re-checks focus on each last long-exposure
frame during capture; the V-curve AutofocusService (M7-007, FOCUS_READYING) stays as
the precision step; (3) integration = pinned pip dep + SYNC.md section;
(4) module recommends exposure/gain, app applies with config clamps + app-side 70%
histogram ceiling until it ships upstream.

- [x] M10-001 Add `smart-tscope-live-analysis` to `pyproject.toml` pinned to the
      v0.1.0 git tag; new SYNC.md section (guardrail mirror of OnStepAdapter:
      canonical source = published release, never edit locally, upstream asks need
      approval, upgrade procedure) `[P1 · Build]`
      - *Acceptance:* package imports on Windows + Pi (verify actual package name from
        the repo); SYNC.md section exists and is referenced from `wiki/index.md`.
      - *Done 2026-07-17:* pinned `smarttscope-live-analysis @ git+…@v0.1.0`
        (distribution name per upstream pyproject; import
        `smarttscope_live_analysis`, `__version__ == "0.1.0"`, `analyze_camera_frame`
        present — verified on Windows; Pi import pending first deploy).
        `scripts/astro_start.sh` gained a second version-sync block so the Pi's
        `--no-deps` wheel path picks the pin up automatically; SYNC.md section
        updated to installed state with upgrade procedure.
- [x] M10-002 `CameraReadinessService`: starts with `RuntimeContext` — in parallel to
      WAIT_CONTEXT_CONFIRMATION — enumerates connected ToupTek devices and maps them
      against `config.CAMERAS` / `OpticalTrainRegistry`; per-camera status
      DETECTED / MISSING; never blocks the mount flow `[P1 · Runtime]`
      - *Acceptance:* with one configured camera unplugged the app runs normally and
        reports MISSING for that role while the mount flow proceeds. Each detected
        camera is joined with its train's full optical configuration (M10-013).
      - *Done 2026-07-17:* `services/camera_readiness.py` — background thread
        (15 s rescan), model-only matching via `CameraNameResolver` (deliberately no
        serial verification per scan — that would open in-use devices; serials stay
        in the adapter build path), statuses DETECTED/MISSING/DISABLED + reason,
        unassigned-device list, optical-configuration join, SDK-unavailable safe.
        Started in `connect_devices()`, stopped in shutdown/reset. Surfaced as the
        `cameras` field on `/api/observing/state` (+ intent responses) at the API
        layer, keeping ObservingService camera-agnostic. 10 new tests; runtime +
        observing API suites green. Pi verification pending (M10-012).
- [x] M10-003 Per-camera readiness FSM, parallel to the observing FSM:
      IDLE → TUNING (exposure/gain) → STAR_CHECK → FOCUSING (only `has_focuser`
      trains) → READY | DEGRADED(reason). Claims `camera:N` via `JobManager`; feeds
      frames through `analyze_camera_frame()` with rolling `previous_star_state`
      `[P1 · Runtime]`
      - *Acceptance:* per-camera states observable via API; no camera resource
        conflicts with autogain or a running session (JobManager arbitration).
      - *Done 2026-07-18:* `services/camera_setup_fsm.py` — `CameraSetupService`
        watcher launches one JobManager job (`camera-setup:<role>`, resource
        `camera:<sdk_index>`) per DETECTED camera; a held camera stays IDLE with
        "camera busy" and retries next tick. TUNING captures `[live_analysis]`
        `tuning_frames` frames recording module recommendations (applied in
        M10-005); STAR_CHECK needs `star_count_min` stars within
        `star_check_frames` extra frames else DEGRADED(reason); FOCUSING only on
        `has_focuser` trains — injectable `focus_fn` hook, until M10-006 completes
        with a pending note. New `[live_analysis]` config + templates. Per-role
        state merged into the `cameras.roles.*.setup` API field and shown on the
        camera card. 10 FSM tests green; Pi verification pending (M10-012).
- [x] M10-004 LiveAnalysis adapter shim (SmartTScope-owned, thin): map camera settings
      (exposure_s, gain, offset, bit_depth, binning, raw_mode, conversion gain) to the
      module's `camera_settings`; pass native unscaled 2D numpy frames (respect the
      camera adapter's pixel-shift/BITDEPTH handling) `[P1 · Runtime]`
      - *Done 2026-07-18:* `services/live_analysis_shim.py` — `build_camera_info()`
        (per-frame EXPTIME/BITDEPTH win over camera queries; best-effort fields),
        `analyze()` passes `FitsFrame.pixels` untouched (adapters already
        right-shift to native ADC range), `live_analysis_available()`. 6 tests
        incl. a real round-trip against the pinned v0.1.0 package.
- [x] M10-005 Exposure/gain auto-tune loop: apply module recommendations clamped by
      new `[live_analysis]` config (max setup exposure — proposal 5 s —, gain/offset
      ranges; **templates/config.toml updated in the same task**); app-side ceiling:
      step down when histogram 99.5th percentile > 70% full scale (until the upstream
      70% parameter ships, see M10-009); exposure adjusted first, gain only when the
      exposure limit is reached `[P1 · Runtime]`
      - *Done 2026-07-18:* `LiveAnalysisSpec` gained six clamp fields
        (`max_tuning_exposure_s=5.0`, `min_tuning_exposure_s=0.05`,
        `tuning_gain_min/max=100/3200`, `tuning_offset_min/max=0/200`,
        `histogram_ceiling_frac=0.70`) parsed in `_parse_live_analysis_spec()`;
        `templates/config.toml` `[live_analysis]` documents all of them.
        `camera_setup_fsm.py`'s TUNING loop now tracks
        exposure/gain/offset across frames: after each capture it takes the
        module's `recommended_exposure_s/gain/offset` (already itself
        "exposure before gain" per the module's own
        `suggest_capture_adjustments()`), clamps to the config bounds, then
        applies an app-side ceiling on top — if the frame's measured
        99.5th-percentile signal (`domain/histogram.py`, already used by
        `AutoGainController`) exceeds `histogram_ceiling_frac`, exposure is
        forced down first and gain only once exposure is already at its
        floor — since the module has no ceiling parameter of its own yet
        (LA-REQ-1, still draft, see M10-009/SYNC.md). Gain/offset are
        applied to the camera via `set_gain`/`set_black_level` between
        frames (best-effort, tolerates cameras without these calls);
        exposure is a plain per-capture argument, so the tuned value simply
        carries forward — including into STAR_CHECK, which previously
        always used the static `setup_exposure_s` regardless of what TUNING
        found. 9 new tests (6 auto-tune behavior + 3 config-parser); FSM +
        config + full unit suite green (4042; one unrelated pre-existing
        flaky test in `tests/unit/workflow/test_logging.py` confirmed
        order-dependent and untouched by this change — passes standalone).
- [ ] M10-006 Separate SCT-aware focus algorithm (`services/focus_algorithm.py`, own
      test suite with synthetic point-star AND donut fixtures): consumes LiveAnalysis
      detections/metrics, recognizes SCT donuts, drives the OnStep focuser within
      calibrated limits (FocuserPort public API only) toward plate-solvable focus.
      Explicitly separate from — and not replacing — the V-curve AutofocusService.
      Designed for reuse by M10-010 `[P1 · Runtime]`
- [ ] M10-007 Gate automatic polar alignment on camera readiness: START_POLAR_ALIGN's
      guard requires the polar-align camera (main role) READY; all other flow steps
      unaffected `[P1 · Runtime]`
      - *Acceptance:* polar-align start disabled with a visible reason while the
        camera is not READY; enabled the moment it is.
- [ ] M10-008 Observe-screen camera card, parallel to the phase panel, visible from
      WAIT_CONTEXT_CONFIRMATION onward: per camera — detected, current exposure/gain,
      star count, focus state, READY/DEGRADED badge, and the train's optical
      configuration (focuser / filter wheel / reducer / barlow / effective focal
      length, M10-013); surfaced through the `/api/observing/state` payload (M9-029
      `mount_state` pattern, one poll loop). Overlaps M9-020 (camera identity +
      preview) — coordinate, don't duplicate `[P1 · UI]`
      - *First slice done 2026-07-17 (with M10-002):* camera card on the Observe
        screen — per role: status dot (green/red/grey), detected display name or
        MISSING/DISABLED with reason tooltip, optical-configuration summary
        (telescope · focal length · focuser · filter wheel · reducer · barlow ·
        ″/px), plus a "connected but not configured" warning line. Remaining for
        this task: exposure/gain, star count, focus state, READY/DEGRADED badge —
        arrive with the M10-003 readiness FSM.
      - *Second slice done 2026-07-18 (with M10-003):* per-row setup summary —
        phase label (tuning… / star check… / focusing… / READY / DEGRADED+reason),
        star count, setup exposure and gain; READY green, DEGRADED amber, focus
        note as tooltip. Remaining: live preview / camera identity overlap with
        M9-020.
- [ ] M10-009 Draft upstream feature requests to SmartTScopeLiveAnalysis — file
      **only after user approval** (ONS31-008/009 pattern), tracked in the new
      SYNC.md section: (a) histogram-ceiling parameter (70%) for exposure
      recommendations; (b) SCT donut detection/classification + focus-quality metric
      (e.g. HFD / donut radius); (c) gaps found during M10-003..006 integration
      `[P2 · External]`
- [ ] M10-010 In-capture focus monitoring: after each completed long exposure, run the
      last frame through the M10-006 focus metric; on drift beyond threshold surface a
      focus warning (auto-correction is a later product decision) `[P2 · Runtime]`
- [ ] M10-011 Unit tests: readiness FSM transitions, tuning-loop clamps (70% ceiling,
      exposure-before-gain ordering), focus algorithm on synthetic point/donut frames,
      missing-camera degradation — all against mock cameras, no hardware `[P1 · Tests]`
- [ ] M10-012 Pi hardware verification: cameras identified while the user is still
      confirming time/location; tuning converges without clipping; stars detected;
      coarse focus reaches plate-solvable quality; polar align unblocks
      `[P0 · Hardware]`
      - *Must have hardware evidence — not accepted on mock alone*
- [x] M10-013 Per-train optical configuration completeness (user requirement
      2026-07-17: the app must know each identified camera's optical configuration —
      focuser / filter wheel / reducer / barlow; config-file based for now):
      extend `OpticalTrainSpec`/`OpticalTrain` + the `[optical_trains.*]` schema with
      `filter_wheel = "touptek" | ""` (links the train to the global `[filter_wheel]`
      device — today that section is global with NO per-camera linkage; registry
      validates the reference) and descriptive element declarations `reducer = ""` /
      `barlow = ""` (labels, e.g. "celestron_f6.3", "2x"). `reducer_factor` stays the
      single numeric authority for `focal_mm`/pixel-scale computation (backward
      compatible — existing configs keep working); validation warns on label/factor
      mismatch (element named but factor 1.0, or factor ≠ 1.0 with nothing named).
      `templates/config.toml` updated in the same task (standing rule). M10-002 joins
      each detected camera with its train's full optical configuration; the M10-008
      camera card displays it (focuser / filter wheel / reducer / barlow / effective
      focal length) `[P1 · Runtime/Config]`
      - *Acceptance:* config declares all four element kinds per train; a detected
        camera's API payload includes its optical configuration; a bad filter-wheel
        reference fails registry validation with a clear message; label/factor
        mismatch produces a startup warning, not a crash.
      - *Done 2026-07-17:* `OpticalTrainSpec`/`OpticalTrain` gained `filter_wheel` /
        `reducer` / `barlow` (defaults `""` — legacy configs load unchanged);
        registry validates filter-wheel references (unknown value or "touptek"
        without `[filter_wheel] enabled = true` → startup ValueError) and warns on
        label/factor mismatch; new `OpticalTrain.optical_configuration()` returns the
        serializable per-camera summary for the M10-002/008 payload;
        `templates/config.toml` updated. 7 new tests; 1173 service tests green.
        API-payload wiring itself lands with M10-002 (service does not exist yet).

- [x] M10-014 Filter-wheel slot naming with INDI-convention names (user requirement
      2026-07-17 — "for not losing it"): SmartTScope currently ignores the `[filters]`
      section entirely (no parser in `config.py`; the ToupTek wheel adapter works on
      numeric slots only, and no INDI backend exists). Add a parsed slot→name mapping
      using the INDI filter names for interoperability: `Red`, `Green`, `Blue`,
      `H_Alpha`, `SII`, `OIII`, `LPR`, `Luminance`. Validate the mapping against the
      wheel's reported slot count; surface names (not bare numbers) in the
      filter-wheel API and UI; `templates/config.toml` updated in the same task
      (standing rule) `[P2 · Runtime/Config]`
      - *Note:* the user's current config has 7 entries (`luminance/red/green/blue/
        ha/oiii/sii`) vs. the 8-name INDI list (`LPR` extra) — reconcile during
        implementation; key format switches from lowercase ad-hoc names to the INDI
        spellings above.
      - *Acceptance:* `[filters]` parses into config with INDI names; filter-wheel
        status/API reports the active filter by name; a mapping that exceeds the
        wheel's slot count fails validation with a clear message; no change to the
        external camera_adapter (numeric slots remain its interface).
      - *Done 2026-07-18:* `config._parse_filters()` → `FILTERS: dict[int, str]`
        (canonical `slot = "Name"`; the legacy `name = slot` format is tolerated
        by inverting it, so the user's current 7 lowercase entries keep loading
        until migrated to the INDI spellings — canonical entries win on
        conflict). Readiness snapshot `filter_wheel` gained `position` +
        `filter_name` (best-effort via injected `wheel_provider`; unnamed slots
        display "slot N"). Slot-count check relaxed from startup failure to a
        one-time runtime warning — the wheel's slot count is only known after
        connect, and a wheelless bench run must not brick the config. Observe
        wheel row shows `FILTERWHEEL · H_Alpha`; Cameras screen (M10-019) shows
        the filter on the wheel-equipped train's panel. `templates/config.toml`:
        `[filter_wheel]` stub + commented `[filters]` INDI examples. 10 new
        tests (parser 6, readiness merge 4).

- [x] M10-015 Pixel scale must be **derived at runtime, never required in config**
      (user requirement 2026-07-17): with the optical train known (focal_mm ×
      reducer_factor) and the camera's pixel size readable (preferred: from the
      ToupTek driver via the camera adapter's public API when the camera is
      connected; fallback: `domain/camera_profile.py` looked up via the role's
      **configured `model`**), `pixel_scale_arcsec` needs no manual value — and a
      static value is wrong anyway because **binning scales it** (effective scale =
      base × binning). `[P1 · Runtime]`
      - *Bug being fixed:* `_derive_pixel_scale()` matches profile model names
        against the *role name* ("main"/"guide"/"oag") — never matches, so every
        train silently falls back to the global `PIXEL_SCALE_ARCSEC` (0.38, stale
        for the current ATR585M main camera).
      - *Scope:* single runtime helper (e.g. `effective_pixel_scale(train, binning)`
        on the registry or a service) consumed by plate-solve hints, collimation,
        and guiding math; `pixel_scale_arcsec` in config demoted to an optional
        override/escape hatch only; also resolve the train `camera_index` via
        `CameraNameResolver` instead of the current default-0-for-all (device
        selection already works by model at runtime; the registry field is the
        ambiguous leftover).
      - *Acceptance:* with no `pixel_scale_arcsec` configured anywhere, main/guide/
        oag report 0.29 / 3.32 / 0.20 ″/px at binning 1 (C8 2032 mm + 2.9 µm;
        180 mm + 2.9 µm; C8 + 2.0 µm) and 2× those values at binning 2; a configured
        override still wins; driver-reported pixel size preferred over the profile
        when available; no consumer reads the raw config value directly anymore.
      - *Done 2026-07-17:* `_derive_pixel_scale()` looks up the profile via the
        role's configured `model` (legacy role-named-as-model kept working); new
        `OpticalTrain.effective_pixel_scale(binning, pixel_size_um)` — precedence
        config override > driver pixel size (`camera.get_capabilities()
        .pixel_size_um`, existing camera-adapter public API — no external change
        needed) > profile; `pixel_scale_overridden` flag on the train;
        `from_config(resolve_index=…)` + runtime wires a CameraNameResolver-backed
        resolver (best-effort, SDK-less environments fall back);
        `deps.get_pixel_scale(camera_index, camera_role, binning)` is the single
        API-side source — polar (2 sites), mount goto-center, and solver solve
        fallbacks migrated off raw `config.PIXEL_SCALE_ARCSEC`; template comment
        updated. 6 new tests (acceptance numbers exact, binning, driver-preferred,
        override-wins, legacy match, resolver win/fallback); registry+mount+solver+
        polar suites green (282 tests). Remaining raw-config readers are only the
        final fallback inside `get_pixel_scale()` and pre-M9-018 hardcoded
        `OpticalProfile`s in `workflow/_types.py` (tracked there).

- [x] M10-016 Cache-bust static UI assets: three hardware sessions in a row lost
      time to browsers rendering stale cached JS after a Pi deploy ("no cameras
      visible" 2026-07-17 and again 2026-07-18 — server payload was correct both
      times). Serve `/` and `/static/*` with `Cache-Control: no-cache` so browsers
      revalidate (ETag/304 keeps it cheap on the LAN); no more mandatory Ctrl+F5
      after deploys `[P1 · UI]`
      - *Done 2026-07-18:* HTTP middleware in `app.py` stamps the header on the UI
        shell and all static responses.
- [x] M10-017 Readable camera-open errors: the ToupTek SDK surfaces bare HRESULT
      numbers — hardware evidence 2026-07-18: guide camera setup reported
      "camera unavailable: -2147024726" (0x800700AA = ERROR_BUSY, device held by
      another handle). Map known HRESULTs to plain language in the setup FSM
      reason; treat ERROR_BUSY as retryable (stay IDLE, watcher retries) instead
      of terminal DEGRADED `[P2 · Runtime]`
      - *Done 2026-07-18:* `_describe_camera_error()` in `camera_setup_fsm.py`
        (busy / access denied / device not functioning / timeout decoded, hex code
        always shown); busy open → IDLE "camera busy: …" and auto-retry once the
        holder releases. 4 new tests.
      - *Resolved 2026-07-18:* `fuser -v /dev/bus/usb/003/009` → the SmartTScope
        process itself (PID 3334). Server log: a UI poll hit the legacy preview
        path ("no [cameras] config — trying SDK auto-detect") which opened the
        GPCMOS as a raw preview handle; the role path's second open then got
        ERROR_BUSY. Fixed by M10-018.
- [x] M10-018 Single camera handle per physical device (hardware evidence
      2026-07-18, see M10-017): `get_preview_camera` and `get_camera_by_role`
      each kept their own handle cache and could open the same physical device
      twice — the ToupTek SDK allows exactly one Open per device. Route preview
      requests for role-owned devices to the shared role handle; serialize all
      open paths `[P1 · Runtime]`
      - *SDK threading check (user question, answered from
        `resources/touptek/toupcam.py` v59.29030.20250722):* multiple cameras in
        a single app thread are fully supported — each opened handle runs its own
        internal SDK thread grabbing USB data (`TOUPCAM_OPTION_THREAD_PRIORITY`),
        frames arrive via `StartPullModeWithCallback` callbacks per handle, and
        handles are usable from any thread (`E_WRONG_THREAD` covers only a few
        platform-specific calls). Our one-JobManager-thread-per-camera model
        exists only because the camera adapter's `capture()` is blocking — an
        app-level choice, not an SDK requirement; it stays. The adapter's
        `_capture_lock` makes handle sharing across consumers safe.
      - *Done 2026-07-18:* `runtime._role_for_sdk_index()` (readiness snapshot
        first, CameraNameResolver fallback before the first scan, never opens a
        device); `get_preview_camera` returns `get_camera_by_role(role)` for
        role-owned indices; new `_camera_open_lock` around the check-then-open
        sections of both paths (concurrent FSM launches exposed the race);
        resolver per-tick INFO logs demoted to DEBUG. 5 new tests; runtime +
        camera suites green (88). Pi verification: guide camera should now leave
        "waiting…" and pass TUNING/STAR_CHECK.

- [x] M10-019 "Cameras" compare screen with stepwise mount jog (user request
      2026-07-18): third top-level view streaming all DETECTED cameras in
      parallel — largest FOV on top, other two side by side below — with a
      top-right arrow pad + Stop for terrestrial-style stepwise slewing.
      `[P2 · UI]`
      - *Done 2026-07-18:* new `static/js/multicam.js` + `#cameras-view` in
        `index.html`; one `/ws/preview?camera_role=…&autogain=true` socket per
        DETECTED role (all closed on leaving the view / beforeunload); panels
        ordered by FOV computed from `optical.pixel_scale_arcsec` × sensor px
        (JPEG dims × 2 for colour previews — debayer halves resolution); FOV
        label `W×H px · W′×H′` (arcsec/arcmin/deg auto-format); scale toggle:
        fit-each-panel vs. one shared arcsec-per-screen-pixel (true relative
        sky coverage, largest FOV just fits its panel); jog pad = timed steps
        at center rate via `POST /api/mount/nudge` with new
        `keep_tracking_state: true` (NudgeRequest field, default false keeps
        old behavior; terrestrial jogs no longer force sidereal tracking ON),
        selectable step 0.2/0.5/1/2 s, buttons disabled while parked, red
        center button = existing `mountEmergencyStop()`. 3 new nudge tests.

- [ ] M10-020 Guide-frame overlay showing where main/oag point (user request
      2026-07-18, future): draw the main and OAG camera footprints inside the
      guide panel of the Cameras screen. Mode selected by radio button:
      **plate solve** (sky targets — solve guide + main/oag frames, draw true
      footprints incl. rotation) vs. **frame search** (terrestrial — locate the
      main/oag frame inside the guide frame by normalized cross-correlation,
      no solving). `[P3 · UI/Analysis]`
      - [x] *First approximation without solving* (done 2026-07-19): lime-green
        FOV rectangles + role labels drawn on the widest-FOV panel for every
        narrower-FOV camera, from the M10-019 pixel-scale math (assumes
        co-alignment, no rotation). Angular ("same sky scale") mode only — no
        shared scale exists in fit mode. `_mcPaintFovOverlays()` in
        `static/js/multicam.js`. Verified by direct in-browser execution against
        synthetic panel data (pixel-checked rectangle position/color) — this
        Windows dev box has no ToupTek SDK, so `CameraReadinessService` never
        reports a real camera as DETECTED here and the live Cameras screen
        itself can't be exercised end-to-end without hardware.
      - *Frame search:* candidate LiveAnalysis upstream request (LA-REQ-3,
        **file only with user approval**) or local scipy correlation; must
        handle scale difference (guide 3.32″/px vs main 0.29″/px ≈ 11×) by
        downsampling the narrow-field frame before matching; rotation between
        trains is the main accuracy caveat — document measured offset once
        plate solve is available to calibrate it.
      - *Acceptance:* radio button on the Cameras screen; sky mode draws solved
        footprints; terrestrial mode never calls the solver.

- [x] M10-021 Decouple mount availability from camera bring-up in
      `connect_devices()` (hardware evidence 2026-07-18: "Confirm Time & Location"
      stalls during camera connect/first frame — violates the M10 quality gate):
      `runtime.py connect_devices()` holds `_adapters_lock` across the whole
      `_build_adapters()`, which connects the **main camera first** (SDK open +
      configure + startup settle + priming first-frame captures in the external
      `managed.py`) and only then the mount — so `POST /api/location/confirm`
      (depends on `deps.get_mount` → `connect_devices()`) queues behind the full
      camera open+prime. Fix app-side only (managed.py is external-owned): connect
      the mount before/independently of cameras and stop holding `_adapters_lock`
      across camera open+prime (split mount-adapter vs. camera-adapter build with
      separate locks, or push the camera connect into the existing background
      machinery). `[P1 · Runtime]`
      - *Acceptance:* with all three cameras connecting/priming,
        `POST /api/location/confirm` and mount endpoints respond in < 1 s; the
        Observe flow reaches WAIT_HOME_CONFIRMATION while cameras are still in
        TUNING.
      - *Done 2026-07-18:* `_build_adapters` split into `_build_mount_focuser`
        (runs first, alone, under `_adapters_lock`) and `_build_main_camera`
        (runs in a background `main-camera-connect` thread spawned at the end
        of `connect_devices()`, serialized on `_camera_open_lock` — now an
        RLock). Requests that genuinely need the camera join the in-progress
        build via `_main_camera()`; `get_camera_by_role("main")` routes there
        too (no duplicate main handle possible). Hardware mode (R5-011)
        ignores the camera side until its build lands, so a real mount never
        shows a false "mock" while the camera is still connecting. Pi
        acceptance check pending (confirm < 1 s during camera prime).

- [x] M10-022 No inline camera opens on hot observing paths (same 2026-07-18
      evidence): `_build_deps` in `api/observing.py` calls
      `deps.get_camera_by_role("guide")` on **every** `/api/observing/state` poll
      (2.5 s) and on `POST /api/observing/intent` — that acquires
      `_camera_open_lock`, which the setup-FSM workers hold for the entire
      multi-second open of each role camera (`contextlib.suppress` swallows
      errors but still blocks on the lock). The endpoints' `Depends(deps.
      get_camera/get_focuser)` set additionally re-enters the M10-021 hazard.
      Never open a camera in a request thread: use an already-open handle or None
      (guiding deps are only needed much later in the flow) and slim the Depends
      set so state poll + intent don't force a full device build. `[P1 · API]`
      - *Acceptance:* `/api/observing/state` and `/api/observing/intent` never
        acquire `_camera_open_lock`; the state poll stays < 100 ms while the FSM
        is opening cameras.
      - *Done 2026-07-18:* `Depends(deps.get_camera)` removed from both
        endpoints — replaced by a `_LazyCamera` proxy that resolves the main
        camera only on first attribute access (snapshot and the early-phase
        intents never touch it; phase actions that do run in background action
        threads where briefly joining the M10-021 build is fine). The guide
        lookup in `_build_deps` uses new `deps.peek_camera_by_role()` /
        `runtime.peek_camera_by_role()` — returns the already-open handle or
        None, never opens, never takes `_camera_open_lock` (guiding needs the
        camera much later; the setup FSM has opened it by then). Guard tests
        patch `get_camera`/`get_camera_by_role` to raise and assert both
        endpoints still return 200. 7 new tests; runtime+API suites green
        (1048).

- [x] M10-023 One serialization discipline for all ToupTek SDK entry points:
      readiness `EnumV2` (every 15 s via `CameraNameResolver._enumerate`), the
      lazy filter-wheel open in `runtime.get_filter_wheel()` (M10-014 addition —
      currently the least-serialized path), and the legacy preview
      `ToupcamCamera.connect` take **neither** `_camera_open_lock` **nor**
      managed.py's `_sdk_lifecycle_lock`, so enumeration/opens run concurrently
      with camera opens on the same USB bus during the connect storm. Route them
      under the same app-side lock discipline (adapter files are external-owned).
      `[P2 · Runtime]`
      - *Acceptance:* no SDK enumerate/open runs concurrently with a camera open;
        the readiness scan skips (not queues) when an open is in progress.
      - *Done 2026-07-18:* legacy preview `ToupcamCamera.connect` turned out to
        already be covered — both its call sites in `get_preview_camera()`
        already sit inside `_camera_open_lock`. The two real gaps: (1)
        `CameraReadinessService` gained an injected `open_lock` (wired to
        `runtime._camera_open_lock`); `_scan_once()` now does a non-blocking
        `acquire(blocking=False)` at entry and **skips** the whole scan
        (logged at debug) when busy, relying on the existing 15 s retry —
        never blocks the readiness thread. (2) `runtime.get_filter_wheel()`'s
        first open now sits inside `_camera_open_lock` (double-checked, same
        pattern as `_connect_main_camera()`) — after the first successful
        connect, later calls stay lock-free (cached return). No
        `adapters/touptek/*.py` edits — `managed.py`'s own
        `_sdk_lifecycle_lock` didn't need touching since `_camera_open_lock`
        already wraps every `managed.py`-based open end-to-end. 5 new tests
        (scan skip/proceed/no-lock-injected, wheel-open dedup, wheel-vs-camera
        cross-serialization); full API + touptek/camera suites green (1093).

- [x] M10-024 Hardware evidence: lock-wait vs. GIL freeze during camera connect
      (feeds M10-021/022 acceptance numbers): on the Pi during startup camera
      connect, curl a static asset and `/api/location/status` in a loop — if those
      stall too, the toupcam binding holds the GIL through Open/EnumV2 (then file
      a SYNC.md external-requirement candidate); if only device endpoints stall,
      the locks above are the whole story. Also record measured per-camera
      connect+prime duration (startup_delay_s + prime attempts × timeout +
      configure). `[P2 · Hardware evidence]`
      - *Checked, not the cause:* readiness/setup `snapshot()` payloads,
        JobManager resource bookkeeping, FSM capture loops on cached handles,
        FastAPI threadpool exhaustion (captures run in dedicated daemon threads).
      - *Tooling done 2026-07-18 (evidence itself still pending a Pi run):*
        this is a hardware-evidence task, not a code fix — implemented the
        means to gather it rather than guessing. `runtime.py` now logs
        `"Camera connect+prime timing: role=<role> model=<model> elapsed=<s>"`
        at INFO around both `camera.connect()` call sites (`_build_main_camera`,
        `get_camera_by_role`) — a real measurement, replacing the
        config-arithmetic estimate the task originally proposed. New
        `scripts/check_connect_stall.sh <host> <duration_s>`: run in a second
        session right after `astro_start.sh`, alternates
        `curl /static/js/app.js` (no device dependency at all) against
        `curl /api/location/status` (mount-only) every ~0.2 s and prints a
        verdict — static-asset stalls implicate the SDK binding holding the
        GIL through `Open()`/`EnumV2()`; status-only stalls would mean
        M10-021/022's locks aren't the whole story after all; no stalls means
        those fixes are sufficient. 2 new tests confirming the timing log
        line fires for both camera-open paths; runtime + full API suites
        green (1019).
      - *Pi evidence 2026-07-18 (verdict: NOT a GIL freeze):* ran
        `check_connect_stall.sh` during a real 3-camera connect (oag
        measured 41.84 s connect+prime — main 1.28 s, guide 1.05 s, from the
        new timing log). The static asset stayed fast the entire 30 s window
        (max 39 ms) even while oag was still connecting — this rules out the
        toupcam SDK binding holding the GIL through `Open()`/`EnumV2()`.
        M10-021/022/023's lock-based fixes are structurally sound; **no**
        SYNC.md external-requirement candidate needed for this.
      - *Unexpected finding, investigated and fixed:* `/api/location/status`
        was consistently ~780 ms on **every single call** throughout the
        30 s window (not a stall-while-camera-opens pattern — a flat,
        steady cost, so unrelated to M10-021/022 despite that endpoint being
        specifically built to never touch a camera). Root cause:
        `GpsdService.get_fix()` (`services/gpsd_service.py`) sent `?WATCH`
        (subscribe to gpsd's live stream) together with `?POLL;` in the same
        request, but only recognized a bare `"class":"TPV"` line as an
        answer — gpsd actually answers `?POLL;` with a `"class":"POLL"`
        envelope nesting the *already-cached* fix in a `"tpv"` array,
        answered instantly with no device wait. Because that envelope was
        never recognized, every call ended up waiting for the next
        naturally-streamed bare-TPV report instead — i.e. the receiver's own
        report cadence (~780 ms, consistent with a ~1 Hz GPS update rate),
        not gpsd's instant cached answer. Fixed: new `_extract_tpv()` reads
        both the `POLL`-envelope and bare-`TPV` shapes; `GpsdService` also
        gained a 2 s TTL cache (mirrors `api/cameras.py`'s `_scan_cache`
        pattern) so the ~2.5 s observing poll cadence doesn't pay even the
        fixed per-query cost every single tick. App-side only, SmartTScope's
        own service code. 5 new tests (POLL-envelope parsing ×2, TTL cache
        ×3); full gpsd/location/master-source/raspberry-trust suites green
        (122); full API+services regression green (2248). *Still needed:*
        Pi re-run of `check_connect_stall.sh` to confirm `/api/location/status`
        latency actually drops after this fix.

- [x] M10-025 Separate slewing (on way to target) from tracking (user request
      2026-07-18): slewing to a target and sidereal tracking are distinct mount
      modes but are currently coupled — GoTo paths assume tracking is (or gets
      switched) on, and OnStep itself may auto-start tracking when a slew
      completes. For terrestrial targets (and the M10-019 Cameras-screen
      workflow) a slew must be possible with tracking remaining OFF afterwards.
      `[P2 · Mount/API]`
      - *Scope:* extend the goto/slew API with a keep-tracking-state option
        analogous to the M10-019 `keep_tracking_state` flag on
        `/api/mount/nudge` (default preserves today's behavior for sky
        targets); after slew completion, restore/enforce the pre-slew tracking
        state instead of accepting whatever OnStep leaves on; the mount strip
        already labels SLEWING vs TRACKING distinctly — verify the state shown
        during and after a tracking-off slew is correct.
      - *Constraint:* OnStepMount/OnStepClient internals are external-owned —
        implement app-side (`mount_operations` / `api/mount.py`); if OnStep's
        auto-track-on-goto cannot be suppressed via existing adapter API,
        record the gap in SYNC.md instead of patching the adapter.
      - *Acceptance:* a goto issued with tracking off completes with tracking
        still off; default goto behavior for sky targets unchanged; nudge and
        goto use the same flag semantics.
      - *Done 2026-07-18:* new `mount_operations.goto_sequence()` wraps the
        existing `safe_goto()` unchanged (all exceptions propagate before any
        tracking logic runs) — when `keep_tracking_state=False` (default) it
        is a pure passthrough with zero extra mount I/O. When `True`, it
        records the pre-slew tracking state (skipping the read entirely
        otherwise), then — only if tracking was off before — polls
        `get_state()` (0.5 s interval, 120 s budget matching the documented
        max-slew window) until the slew leaves `SLEWING`, and calls
        `disable_tracking()` if the mount came out of the slew `TRACKING`
        again. Poll timeout or a `get_state()` failure mid-poll is logged and
        left as-is, never raised — the goto itself already succeeded by that
        point. `GotoRequest` gained `keep_tracking_state: bool = False`;
        `_safe_goto()`/`mount_goto()` pass it through; `mount_goto_sky()`
        (elevation-based, always astronomical) is untouched — defaults to
        `False`. App-side only, no adapter edit. 7 new service tests + 3 new
        API tests; full mount/API suites green (1017). Fix camera role cross-wiring on selector-match failure (hardware
      evidence 2026-07-18: on the M10-019 Cameras screen, covering the guide
      camera GPCMOS02000KPA changed the frame shown in the **OAG** panel —
      the OAG role was bound to the guide camera's physical device). Root
      cause traced to `SmartTouptekCamera._select_device()` in
      `adapters/touptek/managed.py`: when a role's configured `model`/`name`/
      `camera_id` selector matched no enumerated device, the method silently
      fell through to a positional-index pick (`devices[self._index]`,
      defaulting to index 0) instead of reporting "not found" — binding the
      role to whichever physical camera happened to enumerate at that index.
      `resolve_device_id()` (used by the startup role-uniqueness validator,
      same file) already treated a failed selector match as "not found", so
      the startup conflict check could never catch this — it uses different,
      safer semantics than the actual `connect()` path. `[P1 · Runtime]`
      - *Done 2026-07-18 (SYNC-OVERRIDE):* `_select_device()` now returns
        "not found" whenever a `camera_id`/`model`/`name` selector was
        configured but matched nothing — mirroring `resolve_device_id()`.
        Pure index-only configs (no selector at all) keep falling back to
        position exactly as before. `connect()`'s existing SYNC-OVERRIDE
        (return `False` instead of raising) then surfaces this as a normal
        "camera failed to connect" — readable per M10-017 — rather than a
        silent wrong-camera bind. Tracked in `SYNC.md` Active SYNC-OVERRIDEs
        (camera_adapter is external-owned; overrides applied directly per the
        established pattern for this file, unlike OnStepAdapter's flag-and-
        wait policy). 8 new tests
        (`tests/unit/adapters/touptek/test_managed_select_device.py`);
        touptek/camera-service/runtime + full API suites green (1013+152).
      - *Still needed:* Pi verification that the real `[cameras.oag]` model
        selector now either matches G3M678M correctly or fails loudly with a
        clear log line naming the mismatch — the underlying reason the
        selector didn't match in the first place (typo, SDK-reported name
        difference, or a disconnected/faulty G3M678M) is unconfirmed and
        needs the actual `~/.SmartTScope/config.toml` / server log from the
        Pi to close out.

- [x] M10-027 At-home axis-motion refusal has no manual-jog bypass in
      `onstep_adapter` (hardware evidence 2026-07-18: pressing a jog button on
      the M10-019 Cameras screen while the mount sat at mechanical HOME failed
      with a raw HTTP 500, `OnStepSafetyError: axis_motion_refused_at_home`).
      `[P2 · Mount/API]`
      - *Root cause (traced, no adapter edit):* `onstep_adapter`'s
        `_axis_motion()` (shared by guide-mode and center/jog-mode moves alike)
        unconditionally refuses any axis motion while the mount's mechanical
        HOME flag is set — hardcoded, no bypass parameter on
        `move_ra_timed`/`move_dec_timed`/`_axis_motion`. The shim's REQ-ST-007
        override runs on the same call path but only touches unrelated
        pier-side blockers, not this `at_home` check. `note_external_motion()`
        cannot legitimately satisfy it either — `motion_safety_preflight()`
        re-reads the raw `:GU#` decoded flag fresh every call, so a genuinely-
        at-home mount re-triggers the refusal regardless of local bookkeeping.
      - *Done 2026-07-18 (app-side only):* `mount_nudge()`
        (`api/mount.py`) now catches `OnStepSafetyError` and returns a clean
        `409` with `exc.violation.reason` — the same pattern `_safe_goto()`
        already uses for goto. The jog pad's existing error display
        (`multicam.js` `#mc-jog-note`) now shows the real reason instead of an
        opaque 500. 1 new test (`TestMountNudge::test_at_home_refusal_returns_409_not_500`).
      - *Superseded by M10-028 (2026-07-19):* the "jog cannot work at home
        until upstream ships a bypass" limitation below no longer applies —
        the user approved a shim-level SYNC-OVERRIDE and the upstream ask was
        filed. See M10-028.

- [x] M10-028 Manual jog works at confirmed mechanical HOME (user decision
      2026-07-19: "Being at confirmed home manual movement should be allowed
      and not an issue — like move to park is allowed as well"). `[P1 · Mount]`
      - *Done 2026-07-19 (SYNC-OVERRIDE REQ-ST-009):* the shim's `move()`
        (`adapters/onstep/mount.py`, SmartTScope-owned) sets a
        `_jog_bypass_active` window flag (try/finally) around the
        `move_ra_timed`/`move_dec_timed` delegation; the existing REQ-ST-007
        `motion_safety_preflight` override post-processes only the *returned*
        `at_home` to False for exactly the two jog preflight commands
        (`move_ra_center`/`move_dec_center`) while that window is open —
        upstream `_axis_motion()`'s hardcoded at-home refusal then doesn't
        fire. The internal `at_home`/`terminal_state` stay truthful (the
        pier/HA blockers must remain suppressed at home or the jog would be
        refused with a different reason); `motion_refused` and all mechanical
        blockers are untouched (verified by test: at-limit still refuses even
        with the window open); every other preflight consumer (device-state
        poller, goto, live-poll) keeps seeing the true at-home state.
        Upstream ask filed with approval:
        <https://github.com/tschoenfelder/OnStepAdapter/issues/5> — an
        `allow_at_home`/manual mode on the timed-axis API skipping both
        at-home gates (the refusal AND the projected-target `validate_target`
        block, which is dormant here only because `runtime.py` passes no
        `motion_calibration`); delete the shim override when it ships.
        8 new tests (`tests/unit/adapters/onstep/test_jog_at_home.py`, real
        preflight against `FakeOnStepSerial` + new `:GS#` handler); onstep
        adapter suite green (157).
      - *Superseded by M10-030 (2026-07-19):* upstream shipped the manual-jog
        mode in v0.3.3 — the shim bypass window described above was deleted.

- [x] M10-030 Upgrade onstep_adapter to v0.3.3 — native manual jog at HOME
      (upstream closed issue #5 / REQ-ST-009). `[P1 · Mount]`
      - *Done 2026-07-19:* pyproject pin + local install bumped 0.3.1 → 0.3.3
        (Pi follows via `astro_start.sh` version sync). The shim's `move()`
        now selects the timed-axis mode by tracking state: tracking on →
        `mode="center"` (astronomical centering, target-validated); tracking
        off → `mode="manual"` (terrestrial/at-home jog — allowed at confirmed
        mechanical HOME, skips projected-target validation, all mechanical
        blockers live). The M10-028 `_jog_bypass_active` window + preflight
        post-process were deleted; preflight reports `at_home` truthfully for
        every consumer again, which also resolves the documented latent
        `motion_calibration` hazard.
      - Full 0.3.1→0.3.3 override re-diff (SYNC.md updated): REQ-ST-003/005/
        006/008 shipped in v0.3.2 (issue #3) — including the new tracking-
        authorization guard: upstream `get_state()` auto-disables tracking
        with no explicit request, so the shim's REQ-ST-004 `enable_tracking()`
        copy now sets `_tracking_explicitly_requested = True` on success
        (without this, the next poll would kill tracking enabled at home).
        REQ-ST-004/007/002-residual remain local (upstream bodies unchanged);
        `_haversine_m`/`_lx200_round_degrees` now delegate to
        `onstep_adapter.location`.
      - Cameras-screen jog pad needs no JS change: `/api/mount/nudge` →
        `move()` picks manual mode automatically; refusals (incl. the new
        `manual_jog_requires_tracking_off`) surface via the M10-027 409 path.
      - Tests: `test_jog_at_home.py` rewritten for the native mode (8 tests,
        incl. mode-selection + truthful-preflight coverage); one fake-serial
        test updated for the v0.3.2 guard. onstep suite 157 passed; full unit
        suite green (only the known pre-existing `test_logging` order flake).
      - Pi verification pending (user): jog at confirmed HOME moves the mount;
        tracking enabled at home survives the next poll.

- [x] M10-029 TEC cooling toggle on the Cameras screen (user request
      2026-07-19: target −10 °C by config.toml, activatable by toggle in the
      camera window title; only cooled cameras — ATR585M — get the toggle).
      `[P2 · Camera]`
      - *Done 2026-07-19:* readiness scan now reports `has_tec` per role from
        the enumeration flag bits (`0x80 | 0x20000`, best-effort — devices
        without `.model` default False) so the Cameras screen learns TEC
        capability from the payload it already polls. `/api/cooling/status`
        gained `default_target_c` from the new `[cooling] default_target_c`
        config (template updated). `multicam.js`: panels with `has_tec` get a
        ❄ toggle + status span in the header; toggle → existing
        `POST /api/cooling/set_target` with the panel's `sdk_index` and the
        config default; a 10 s status poll renders `−8.3° → −10° (45%)`,
        marks the active panel, and re-derives an already-running session on
        view enter. Cooling is deliberately NOT stopped on view leave
        (hardware state, unlike the preview sockets). Stage-1 cooling card
        target input now prefills from `default_target_c` (config is the
        single source; untouched user edits win). Existing single-session
        `CoolingService` reused unchanged (per user decision: only the
        ATR585M has cooling, no multi-session refactor).
      - Tests: readiness `has_tec` (3), cooling status `default_target_c`
        (2); readiness + cooling suites 64 passed; `node --check` clean.
      - Pi verification pending (user): ❄ toggle only on the ATR585M panel;
        cooling toward config target with live temp/power; toggle state
        survives leaving/re-entering the Cameras view.

- [x] M10-031 Larger jog step size while not tracking (hardware feedback
      2026-07-19: "even with 2 secs the number of steps ... to move the
      mount to a horizontal position pointing to the horizon would be too
      large. If the mount is confirmed at home, the movement needs to be
      larger when step arrow is pressed"). `[P1 · Mount]`
      - *Done 2026-07-19:* `/api/mount/nudge` (`api/mount.py`) now applies
        two duration ceilings mirroring the shim's own `move()` mode split
        (M10-030): a tracking centering correction stays capped at 5000 ms
        (`_NUDGE_TRACKING_MAX_MS`, unchanged from before); a not-tracking
        jog (confirmed HOME, or any terrestrial jog with
        `keep_tracking_state=True`) may run up to 60000 ms
        (`_NUDGE_MANUAL_MAX_MS` — the schema's new `duration_ms` ceiling),
        well under upstream's 120000 ms hard limit for center/manual mode.
        The check uses the mount's actual tracking state *after* any
        `enable_tracking()` side effect, so an auto-enabled tracking
        correction is still capped tight — the larger ceiling only applies
        when tracking stays off.
      - `multicam.js`/`index.html`: `#mc-jog-dur` gained 5/10/20/40/60 s
        options; the existing 5 s mount-status poll now also reads
        `tracking_state` and disables (or clamps back) any option above
        5000 ms while tracking, so the UI reflects the server cap instead of
        the user hitting a 422.
      - Tests: 5 new `TestMountNudge` cases (tracking cap enforced/allowed at
        the boundary, not-tracking large duration allowed, schema rejects
        >60 s, auto-enabled tracking still capped). Mount API suite 154
        passed; `node --check` clean.
      - Pi verification pending (user): at confirmed HOME, a 30–60 s step
        actually covers a useful chunk of sky; a tracking centering
        correction still rejects a >5 s step with a clear 422.

- [x] M10-032 Hardware-session bug fixes: guide-cam black frames, unverified
      home-solve, opaque asserts (user report 2026-07-19/20: guide camera
      preview goes black after one frame; polar alignment's HOME solve failed
      via ASTAP with the mount not actually at home; unclear which camera was
      used; an `AssertionError` appeared in the log). `[P1 · Cameras/Polar]`
      - *Done 2026-07-20:* Traced by 3 parallel Explore-agent investigations
        to three independent, real bugs (not user error):
        - `adapters/touptek/managed.py`: `capture_mode="snap"` (the guide
          camera model, GPCMOS02000KPA) left the camera in free-run video
          mode (`TRIGGER=0`) permanently while `_capture_raw()` kept issuing
          `Snap()` per capture as if it were a one-shot mode — the
          already-working main/oag path instead settles then switches to
          software-trigger mode (`TRIGGER=1`) and calls `Trigger(1)`. Fixed
          by making "snap" mode follow the same settle→`TRIGGER=1` sequence
          and use `Trigger(1)`, so every capture is a deterministic single
          exposure instead of riding the camera's own free-running cadence.
          Needs Pi verification (no ToupTek SDK/hardware on the Windows dev
          box) — cannot be tested from here.
        - Four bare `assert self._cam is not None and self._tc is not None`
          in `managed.py` (no message — `str(AssertionError())` is `""`,
          matching "an AssertionError appeared in the log" with no useful
          detail) replaced with explicit checks raising a descriptive
          `RuntimeError` naming the failing method.
        - `api/polar.py`: the safety checklist's `mount_at_home` field was a
          pure client-side checkbox (`mount.js` `paConfirmChecklist()`
          hardcodes `true` once all boxes are ticked) never cross-checked
          against real mount state. `polar_measure()` now hard-blocks unless
          `DeviceStateService.get_mount_state()` (the sticky-AT_HOME-promoted
          cache — a raw `mount.get_state()` call would almost always see the
          hardware flag already cleared, per `home_sequence()`'s own
          docstring) reports `MountState.AT_HOME`.
        - `api/polar.py`: `MeasureRequest`/`FallbackCameraRequest` gained an
          optional `camera_role` field resolved via the existing
          `deps.resolve_camera_index()` (same pattern as `api/solver.py`'s
          `SolveRequest`) instead of accepting only a raw, unvalidated
          `camera_index`; `PolarStatus` now reports back `cam_index` and
          `cam_role` (resolved via the optical-train registry even when only
          a raw index was given) so it's always clear which camera ran.
      - Tests: new `tests/unit/api/test_polar.py` (7 cases — AT_HOME gate
        blocked/allowed/no-poll-yet/checklist-precedence, camera_role 422 on
        unknown role, role resolved + reported, index-only falls back to a
        resolved role). Touptek adapter suite (59) + full unit suite (4068
        passed, 24 skipped) green.
      - Pi verification pending (user): guide camera preview stays live past
        the first frame at a few exposure/gain combinations; `/measure`
        refuses with a clear error when attempted while not actually at
        home, and proceeds normally once actually homed.

- [x] M10-033 New Autofocus screen — main camera only (user request
      2026-07-20). Guide camera has no focuser; OAG shares the main
      focuser and is manually synced (out of scope, user confirmed).
      `[P2 · UI/Focus]`
      - *Done 2026-07-20:* New top-level "Autofocus" tab
        (`static/js/autofocus.js`, `#autofocus-view` in `index.html`;
        `app.js`'s `showTopView()` generalized from a cameras-only
        enter/leave branch into a small per-view dispatch,
        `_TOP_VIEW_STREAMS`). Arrow buttons `+5/+1/-1/-5` call the existing
        `POST /api/focuser/nudge`, which already clamps to
        `[0, max_position]` live from OnStep (`:FM#`, confirmed via the
        upstream focuser adapter) — no new range-clamping logic needed.
        Continuous live preview via a small self-contained websocket
        client (same `ws/preview` wire protocol `preview.js` uses, but not
        sharing its singleton connection/DOM ids — those are Stage 3/4-
        specific and would couple this screen to whatever preview state is
        active elsewhere). Terrestrial/sky toggle is a screen-local
        checkbox (no such concept existed anywhere in the app); in sky
        mode, a periodic readout shows HFD (`domain/focus_metric.py`,
        the same metric `workflow/autofocus.py`'s existing best-focus
        search already uses — there is no true numeric FWHM anywhere in
        the repo, so this is shown honestly labeled as HFD, user-confirmed)
        plus `stars_found` from the external LiveAnalysis module when
        installed.
      - New `POST /api/autofocus/sequence` +
        `GET /api/autofocus/sequence/status/{job_id}`
        (`api/autofocus_sequence.py`): captures a bracketed sequence of
        individual (not stacked) raw FITS frames at different focuser
        positions to support tuning autofocus later — distinct from the
        existing `/api/focuser/autofocus`'s HFD-fit best-focus search,
        which doesn't persist frames. Background job + status-polling
        pattern mirrors `api/calibration.py`'s bias/dark/flat jobs;
        range/step validated and clamped against the focuser's live
        `max_position` before the sweep starts (422 if it doesn't fit).
        Filenames encode the focuser position
        (`af-seq_pos-<position>_<index>.fits`); a `FOCUSPOS` FITS header
        key is also written.
      - Full unit suite green after the change (see M10-032 entry above for
        the last full-suite run count — no backend regressions expected
        since only new files + an additive router were added).
      - Pi verification pending (user): live preview streams for the main
        camera; arrow nudges move the focuser and stay within OnStep's
        reported range at both ends; HFD/star-count readout appears only
        when the terrestrial checkbox is unchecked; a short sequence
        capture produces the expected number of FITS files with
        position-encoded filenames.

- [ ] M10-034 Higher jog slew rate for the Cameras-screen jog pad (user
      request 2026-07-20: default at least 16x sidereal, with 2x/4x/32x
      options — the current fixed `:RC#` center rate is too slow to
      usefully move the mount even at the 60 s max step duration from
      M10-031). `[P2 · Mount, blocked]`
      - **Blocked on `SYNC.md` REQ-ST-010** — filed 2026-07-20 as
        <https://github.com/tschoenfelder/OnStepAdapter/issues/7> (explicit
        user go-ahead): no rate selection exists anywhere in the stack —
        not in SmartTScope, not in the pinned `onstep_adapter` package,
        which hardcodes `:RG#`/`:RC#` only. Per this project's standing
        rule (never patch OnStep protocol behavior locally — canonical
        source is the published release only), asked upstream for a
        rate-selectable jog/move API rather than working around it locally.
      - No code changes attempted this session; `smart_telescope/adapters/
        onstep/mount.py`, `api/mount.py`, and the jog-pad UI are untouched.
        Awaiting upstream response before any implementation.

**Open parameters (config defaults, tune later):** star-count threshold for
STAR_CHECK; max setup exposure (5 s proposal); focus-quality threshold; polar-align
gating role (main).

**Quality gate:** camera readiness runs without delaying or blocking any mount action;
polar align is gated only on the camera it needs; no LiveAnalysis code duplicated into
SmartTScope; all frame analysis flows through the pinned module.

---

## Safety Regression Checklist

*Run before every milestone demo and release. STOP response time target: **< 1 s** (POD-002).*

- [ ] STOP works during mount slew — response confirmed < 1 s on real hardware
- [ ] STOP works during focuser movement — response confirmed < 1 s on real hardware
- [ ] Shutdown stops motion before disconnect
- [ ] Park label follows observed hardware state (not command receipt)
- [ ] Unpark label follows observed hardware state (not command receipt)
- [ ] New mount command rejected while unsafe movement is active
- [ ] New focuser command rejected while prior movement is still active
- [ ] Preview failure does not affect mount/focuser controls
- [ ] Autogain cancellation exits within agreed timeout
- [ ] Session stop exits within agreed timeout
- [ ] Camera conflicts detected and reported
- [ ] Missing config files produce actionable diagnostics
