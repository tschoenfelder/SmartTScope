# OnStepAdapter Dependency

`onstep_adapter` is a **pip-installed package**, not a synced source copy.
Install URL (pinned): `https://github.com/tschoenfelder/OnStepAdapter/releases/download/v0.3.1/onstep_adapter-0.3.1-py3-none-any.whl`
Last synced/audited: 2026-07-15 (full USB-connectivity replacement, ONS31-101..110)

The directory `smart_telescope/adapters/onstep/` is **SmartTScope-owned** — do NOT sync
files from the OnStepAdapter GitHub repo into it. It is a **thin shim layer** that
subclasses the installed package (see "Shim layer" below).

## Migration complete (2026-07-15): shim-only state

v0.3.1 is a fully independent `onstep_adapter` package (own `mount.py`, `client.py`,
`serial_bus.py`, `focuser.py`, `safety.py`, `ports/`; the wheel ships no
`smart_telescope/*` files). The former 4,534-line local `mount.py` reimplementation was
deleted; the adapter layer now contains only delegation, documented SYNC-OVERRIDEs, and
permanent SmartTScope wrappers. FSM note: upstream `MountState` has 6 states — HOME is a
mechanical `:GU#` flag (`client.mount.last_decoded_status["at_home"]`), mapped by the
shim onto SmartTScope's 7-state enum (`smart_telescope/ports/mount.py` stays the
app-facing FSM). `unpark()` routes through upstream's
`unpark_to_home_stop_tracking()` (supersedes SAFETY-001/002 and the retired
`_explicit_tracking_started` compensation, REQ-ST-003/005/006).

### Shim layer (`smart_telescope/adapters/onstep/`)

| File | Content |
|------|---------|
| `__init__.py` | Re-exports; `__version__` taken from the installed wheel |
| `mount.py` | `OnStepMount(onstep_adapter.OnStepMount, MountPort)` — FSM mapping, routed unpark, SYNC-OVERRIDEs + permanent wrappers below; re-exports upstream module helpers for legacy imports |
| `client.py` | `OnStepClient(onstep_adapter.OnStepClient)` — swap-after-construction: lets upstream `__init__` run, then rebuilds `self.mount`/`self.focuser` as SmartTScope shims on the same serial bus (upstream has no injection parameter — candidate upstream ask) |
| `focuser.py` | `OnStepFocuser(onstep_adapter.OnStepFocuser, FocuserPort)` — M7-004 backlash compensation around `move_absolute()` (permanent SmartTScope feature) + SYNC-OVERRIDE `_load_calibrated_max_position()` (upstream copy broken, see below) |
| `safety.py` | Re-exports + `OnStepSafetyConfig` frozen-dataclass extension adding `onstep_time_tolerance_s`/`onstep_location_tolerance_m` (pending upstream request) |
| `results.py` | Re-exports upstream results; `FocuserStatus`/`FocuserMoveResult` stay canonical in `ports/focuser.py` (ONS-MIGRATE-009b) |
| `serial_bus.py`, `state_store.py`, `firmware_proof.py` | Pure re-exports |

### MountState cross-enum equality (ONS31-101 mechanics — found 2026-07-15)

Upstream internals compare `self.get_state()` results against upstream's own
`MountState` enum in 19 call sites (e.g. `state == MountState.TRACKING` inside
`recovery_unpark_stop_tracking`, the PARKED guard in `return_home_mechanical`).
Because the shim's `get_state()` override returns SmartTScope's 7-state enum,
plain cross-enum comparison is always False — which would have silently skipped
the firmware auto-tracking stop inside the routed unpark (the exact SAFETY-001
behavior ONS31-102 adopted it for). Fixed **app-side** (adapter untouched):
`smart_telescope/ports/mount.py MountState` compares equal by member name to any
other `Enum` class itself named `MountState`; `Enum.__hash__` is name-based, so
upstream set-membership checks stay consistent. Regression coverage:
`tests/unit/adapters/onstep/test_mount_state_cross_enum.py` plus
`TestRoutedUnpark` in `test_with_fake_serial.py` (fake auto-starts tracking
after `:hR#` like real firmware; asserts `:Td#` is actually sent).
Upstream ask candidate: subclass-safe internal state checks (compare decoded
flags, or an internal non-virtual accessor) — needs user approval to file.

### Test patch-target rule

Patching `smart_telescope.adapters.onstep.mount.<helper>` does NOT affect
upstream-internal calls — tests must patch `onstep_adapter.mount.<name>` /
`onstep_adapter.focuser.<name>` instead (done 2026-07-15 for `serial` and `time`).
The upstream routed ops poll `:GU#` with real sleeps (45 s budget) —
`test_with_fake_serial.py` no-ops `onstep_adapter.mount.time.sleep` via an
autouse fixture and injects the fake at `mount._bus._serial` (the upstream
`OnStepSerialBus` holds the port; the old `mount._serial` attribute is dead).

## Historical migration state (2026-06-17, corrected 2026-07-09)

**Guardrail (restated by user 2026-07-09):** only `onstep_adapter`
(github.com/tschoenfelder/OnStepAdapter) is to be used to connect to
focuser and mount — SmartTScope must not duplicate this code. That repo
was extracted from SmartTScope's own code for reusability; matching code
is expected and correct, not a problem. Gaps must be tracked here as
REQ-ST-* items, not left as silent local-only code.

**Process rule: never edit adapter-layer code directly.** When a fix
belongs in `OnStepMount`/`OnStepClient`/etc. themselves (LX200 command
sends, status parsing, serial protocol logic) — as opposed to
SmartTScope's own `services/`/`api/` code that merely *calls* the
adapter's existing public methods — stop and flag it to the user directly,
don't implement it. This applies to `smart_telescope/adapters/onstep/*.py`
*and* any local checkout of the OnStepAdapter repo — the only canonical
source is the published git release (the pinned wheel URL above), not a
local working copy. Confirmed 2026-07-09: local checkouts exist at
`Documents/Codex/CameraTest/OnStepAdapter` and
`Documents/Codex/SmartTScope/onstep_adapter`, but neither is to be treated
as an editable target.

**Architecture reality**: `onstep_adapter` v0.3.0's `__init__.py` re-exports
from `smart_telescope.adapters.onstep.*`. The GitHub repo *also* vendors a
full copy of these files under its own `smart_telescope/` folder so the
package installs standalone — this vendored copy is genuine, functioning
code, not a stub. It is a **manual snapshot, not a live sync**: confirmed
2026-07-09 that the repo (last pushed 2026-06-14) has `client.py` identical
to the local copy, but `mount.py` 197 lines behind — missing everything
in REQ-ST-001..008 below, added locally since the last sync. Diff before
claiming parity: `gh api repos/tschoenfelder/OnStepAdapter/contents/<path>`
or `raw.githubusercontent.com/tschoenfelder/OnStepAdapter/main/<path>`.

**No direct serial communication outside the adapter layer**: All LX200/serial commands are
confined to `smart_telescope/adapters/onstep/focuser.py` and `mount.py`. No `api/` or
`services/` code sends serial commands directly.

**Import paths**: All non-adapter code now imports through `adapters.onstep.__init__` (the
package surface), not into internal submodules. The final migration step (when an independent
upstream exists) is a simple search-and-replace:
`from .adapters.onstep import X` → `from onstep_adapter import X`

**Consumer API**: `FocuserPort` now declares `status()` and `move_absolute()`. `api/focuser.py`
uses `focuser.status()` and `focuser.move_absolute(target)` — the onstep_adapter public API
pattern. Mount-side consumer API unchanged (MountPort covers it).

## Override files (`smart_telescope/adapters/onstep/`)

| File | Role |
|------|------|
| `__init__.py` | Re-exports installed package surface; local overrides (OnStepMount, OnStepClient) win |
| `mount.py` | `OnStepMount(_BaseMount)` — SmartTScope patches; see REQ-ST-* below |
| `client.py` | `OnStepClient(_BaseClient)` — injects SmartTScopeMount via replicated `__init__` |
| `safety.py` | Thin re-export from `onstep_adapter.safety` |
| `serial_bus.py` | Thin re-export from `onstep_adapter.serial_bus` |
| `focuser.py` | Thin re-export from `onstep_adapter.focuser` |
| `firmware_proof.py` | Thin re-export from `onstep_adapter.firmware_proof` |
| `results.py` | Thin re-export from `onstep_adapter.results` |
| `state_store.py` | Thin re-export from `onstep_adapter.state_store` |

## Active SYNC-OVERRIDEs and permanent wrappers (2026-07-15 shim)

**Permanent wrappers** (stay forever, not upstream asks):

| ID | Method | Why |
|----|--------|-----|
| REQ-1 / LOCAL-001 | `move(direction, move_ms)` | Translation onto upstream's public `move_ra_timed()`/`move_dec_timed()` (`mode="center"`) — implemented 2026-07-15, `mechanical_manual_move()` interim retired. |
| REQ-2 | `set_park_position() → bool`, `get_park_position() → MountPosition\|None` | `MountPort` ABC adapters over upstream `set_park_position_from_current()`/`get_park_position()` (+ conversion to the local `MountPosition` dataclass, also done by `get_position()`). |
| REQ-ST-001 | `ensure_time_location_synced()` | Pure config-forwarding glue (SmartTScope `config.py` → upstream `sync_onstep_time_location()`). |
| ONS31-101 | `get_state()` | FSM mapping: upstream 6-state + decoded `at_home` flag (+ sticky `_at_mechanical_home`, first-'H' `confirm_home_position()`) → SmartTScope's 7-state enum. **M9-036 ordering:** decoded H > SLEWING (M9-021) > sticky authority flag > upstream state — observed motion must never be masked by a stale/re-armed authority flag (park slew showed AT HOME throughout, hardware 2026-07-17). |
| ONS31-102 | `unpark()` | Routed through upstream `unpark_to_home_stop_tracking()`; returns whether `:hR#` was accepted; incomplete home/stop phase logged, never blind-resent (M9-027). |
| M9-036 | `stop()` | `super().stop()` then upstream public `note_external_motion("manual_stop")` — a manual/emergency `:Q#` invalidates mechanical-home authority (upstream `stop()` doesn't clear `_at_mechanical_home`; upstream ask below). Genuine at-home re-arms from the next H observation. |
| M7-004 | `OnStepFocuser.move_absolute()` backlash compensation | SmartTScope config-driven feature layered around upstream `move_absolute()` (public API only). |

**SYNC-OVERRIDEs pending upstream delivery** (each tagged in the shim source; remove
when upstream ships it — re-diff on every upgrade):

| ID | Where | Gap in upstream v0.3.1 wheel |
|----|-------|------------------------------|
| REQ-ST-004 | `mount.py enable_tracking()` (28-line method copy) | At-home bypass of positional checks missing. **2026-07-11 pre-check wrongly reported this as present in v0.3.1 — the installed wheel does NOT have it** (repo main ≠ tag). |
| REQ-ST-007 | `mount.py motion_safety_preflight()` (190-line method copy) | Pier-side guards missing: (a) stale `:Gm#` suppression at confirmed home with axis2 < 15°, (b) `pier_side_axis_inconsistent` suppressed in terminal state. **Same wrong pre-check as REQ-ST-004 — NOT in the wheel.** |
| REQ-ST-002 (residual) | `mount.py sync_onstep_time_location()` (post-process) | Upstream accepts `confirmed_by_user` but does not set `time_trust_source="user_confirmed"`; shim sets it post-hoc. |
| REQ-ST-008 | `mount.py` `_haversine_m()`, `_lx200_round_degrees()`, `get_sync_status()` | Stays local either way; upstream adoption nice-to-have. |
| (new) tolerance fields | `safety.py OnStepSafetyConfig` subclass | `onstep_time_tolerance_s`/`onstep_location_tolerance_m` absent upstream. |
| (new) client injection | `client.py` swap-after-construction | Upstream `OnStepClient.__init__` has no `mount_cls`/factory parameter. |
| (new) stop() keeps home authority | not overridden locally (display-side fixed app-side, M9-032) | Upstream `OnStepMount.stop()` does not clear `_at_mechanical_home`, so mechanical-home authority survives a mid-slew STOP even though the position is no longer trustworthy (`enable_tracking()` at-home bypass and `motion_safety_preflight()` terminal-state both consume it). `note_external_motion()` is the existing public API for exactly this. Found 2026-07-17 during M9-032; **not filed — needs user approval**. |
| (new) broken relative import — focuser loader | `focuser.py _load_calibrated_max_position()` (method copy) | Upstream v0.3.1 `focuser.py:170` does `from ... import config` — climbs above the top-level `onstep_adapter` package, always raises, swallowed by `except Exception: return 0` → calibrated focuser max position silently never loaded from `~/.SmartTScope/onstep_focuser_calibration.json` (leftover from when the file lived under `smart_telescope/adapters/onstep/`). Shim carries the pre-migration loader (found 2026-07-17 via test failure `tests/unit/adapters/test_onstep_focuser.py::test_load_calibrated_max_reads_json`). Same bug exists in upstream `mount.py:621` `_default_safety_config()` — **latent only** for SmartTScope: `runtime.py` always passes an explicit `safety_config`, so the broken fallback (permissive lat/lon 0, alt 0–90 default) never fires here; no override needed, but any consumer relying on the default gets no app-level safety config. Upstream ask candidate — needs user approval to file. |

**Known cosmetic deltas vs the retired local implementation** (accepted, not overridden):
upstream labels the firmware-proof `reference_source` as `"host_application"` (was
`"smart_telescope_application"`); the extra preflight-refusal warning log before
`OnStepSafetyError` is gone (upstream ask candidate).

**Retired 2026-07-15** (superseded by `unpark_to_home_stop_tracking()`):
REQ-ST-003/005/006 `_explicit_tracking_started` lifecycle — deleted with the old
`mount.py`; SAFETY-001/002 resolved by the routed op, pending Pi hardware verification
(ONS31-109).

## Pending upstream requests

These patches are currently in `mount.py`. They should be evaluated for adoption
into `onstep_adapter`; raise with the package maintainer.

**Filed 2026-07-11:** REQ-ST-003/005/006/008 raised as
<https://github.com/tschoenfelder/OnStepAdapter/issues/3> (explicit user approval).

| ID | Method | Reasoning for upstream adoption |
|----|--------|----------------------------------|
| REQ-ST-002 | `sync_onstep_time_location()` (confirmed_by_user extension) | Sets `time_trust_source="user_confirmed"`; base class leaves it unset. **Confirmed present in v0.3.1 upstream (2026-07-11) — pending removal audit, see `docs/todo.md` ONS31-004.** |
| REQ-ST-003 | `get_state()` `_explicit_tracking_started` flag | **Reframed 2026-07-11.** Original ask only disambiguated *reporting* (relabel as AT_HOME instead of TRACKING). User direction: the actual fix should be behavioral — if firmware auto-starts tracking after `:hR#` that SmartTScope never requested, actively stop it (e.g. call the same verified-disable path REQ-ST-005 uses), not just reinterpret status while the mount keeps tracking underneath. This is a protocol-layer behavior change to `OnStepMount` — flagged per the never-edit-adapter-directly guardrail, awaiting user go-ahead before implementation. Still worth raising upstream too, since any GEM OnStep host hits the same firmware quirk. |
| REQ-ST-004 | `enable_tracking()` at-home bypass | Positional limits unsound at CWD home (stale RA); safety lock still applies. **Confirmed present in v0.3.1 upstream (2026-07-11) — pending removal audit, see `docs/todo.md` ONS31-004.** |
| REQ-ST-005 | `disable_tracking_verified()` flag clear | Consistent flag lifecycle. Confirmed as scoped correctly (2026-07-11) — stays an upstream ask as-is; becomes the mechanism REQ-ST-003's active-stop behavior would call. |
| REQ-ST-006 | `stop()` / `park()` / `unpark()` flag clear | **Reframed 2026-07-11.** User direction: `unpark()` in general should drive the mount to a genuine non-tracking mechanical state, not just clear SmartTScope's own bookkeeping flag. Same protocol-layer-behavior-change status as REQ-ST-003 — flagged, awaiting go-ahead. |
| REQ-ST-007 | `motion_safety_preflight()` pier-side guards | (a) terminal_state; (b) axis2 < 15° stale `:Gm#` suppression. **Confirmed present in v0.3.1 upstream (2026-07-11) — pending removal audit, see `docs/todo.md` ONS31-004.** |
| REQ-ST-008 | `_haversine_m()` + `_lx200_round_degrees()` helpers, used by `get_sync_status()`'s meter-based location tolerance (M8-008) | Generic geo/LX200-format utilities any OnStep client doing location-sync checks would need; found via diff against the vendored copy 2026-07-09, never filed upstream when added. **Confirmed needed regardless of upstream outcome (2026-07-11) — stays local either way; upstream adoption is a nice-to-have, not a blocker.** |
| REQ-ST-009 (draft, **NOT filed** — needs approval) | `_axis_motion()` at-home refusal — no manual-jog bypass | Found 2026-07-18 (M10-027, hardware evidence: jog button 500 at mechanical HOME on the new Cameras screen). `_axis_motion()` (shared by guide-mode and center/jog-mode moves) unconditionally raises `axis_motion_refused_at_home` whenever the mount is at mechanical HOME — hardcoded, no bypass parameter, same family as REQ-ST-004's `enable_tracking()` at-home bypass. SmartTScope's M10-019 terrestrial-jog workflow deliberately wants tracking off and may legitimately need to move the mount while still at/near home. Local mitigation done: `api/mount.py mount_nudge()` now catches `OnStepSafetyError` and returns a clean 409 instead of a raw 500 — but the mount genuinely cannot move at home either way until upstream adds a bypass (e.g. an explicit "manual/non-astronomical jog" mode parameter). Not filed upstream — awaiting the same explicit user go-ahead as REQ-ST-003/005/006/008. |

## Upgrading onstep_adapter

1. Update the wheel URL in `pyproject.toml` to the new release.
2. Run `pip install -e ".[dev]"` to fetch the new wheel.
3. Review each REQ-ST-* override in `mount.py` — check if the base class now handles it.
4. Review `client.py` — its `__init__` replicates the base `__init__` body and must be
   updated if upstream `OnStepClient.__init__` changes.
5. Run: `python -m pytest tests/unit/ -x -q`
6. Commit: `git commit -m "chore: upgrade onstep_adapter to vX.Y.Z"`

---

# SmartTScopeLiveAnalysis Dependency

`smarttscope-live-analysis` is a **pip-installed package** (M10-001 done 2026-07-17).
Install pin: `smarttscope-live-analysis @ git+https://github.com/tschoenfelder/SmartTScopeLiveAnalysis.git@v0.1.0`
(import name `smarttscope_live_analysis`, `__version__ == "0.1.0"`, NumPy-only).
Provides star detection, temporal classification, and exposure/gain/offset
recommendations for the M10 camera-readiness track (`analyze_camera_frame()`).
Planned to take over frame acquisition later as well.
`scripts/astro_start.sh` auto-syncs the installed version against the pyproject pin
on every Pi start (the SmartTScope wheel install uses `--no-deps`).

## Upgrading smarttscope-live-analysis

1. Bump the git tag in the `pyproject.toml` pin.
2. `pip install -e ".[dev]"` (dev) — the Pi picks it up automatically via
   `astro_start.sh`'s version sync.
3. Re-check the pending-requests table below against the new release.
4. Commit: `chore: upgrade smarttscope-live-analysis to vX.Y.Z`.

**Guardrail (same as OnStepAdapter):** the canonical source is the published git
release only — never edit module code locally, in site-packages, or in any checkout.
Gaps become upstream feature requests, filed **only with explicit user approval**,
tracked here.

## Pending upstream requests (draft — NOT filed, see M10-009)

| ID | Ask | Status |
|----|-----|--------|
| LA-REQ-1 | Histogram-ceiling parameter (default 70% full scale) constraining exposure/gain recommendations | draft — app-side clamp until shipped (M10-005) |
| LA-REQ-2 | SCT donut detection/classification + focus-quality metric (e.g. HFD / donut radius) | draft — needed by the M10-006 focus algorithm |

SmartTScope-owned surface: only the thin adapter shim (camera_settings mapping, frame
handoff) from M10-004 and the focus/control loops that consume the module's results.

---

# camera_adapter Sync State

Last synced: 2026-05-22
Source commit: 03d5823a4e26172c55dfd3df4e18fd38e72dd8c0

## Owned files (copy verbatim from resources/camera_adapter/ on each release)

| Source (resources/camera_adapter/) | Destination (smart_telescope/) |
|---|---|
| adapters/touptek/camera.py | adapters/touptek/camera.py |
| adapters/touptek/managed.py | adapters/touptek/managed.py |
| adapters/touptek/filter_wheel.py | adapters/touptek/filter_wheel.py |
| domain/guiding.py | domain/guiding.py |
| tools/camera_loadtest.py | tools/camera_loadtest.py |
| tools/guide_measuretest.py | tools/guide_measuretest.py |
| tests/unit/services/test_guide_measurement.py | tests/unit/services/test_guide_measurement.py |

## Active SYNC-OVERRIDEs

| File | Override | Waiting for |
|---|---|---|
| smart_telescope/adapters/touptek/managed.py | `connect()` returns `False` instead of raising `RuntimeError` when no device is found | camera_adapter to ship the fix |
| smart_telescope/adapters/touptek/camera.py | Added `_FLAG_RAW16`, `_detect_pixel_shift()`, `self._pixel_shift`; `capture()` right-shifts MSB-aligned sub-16-bit data to native ADC range and writes `BITDEPTH` header; `get_bit_depth()` returns sensor native depth | camera_adapter to incorporate pixel-shift detection |
| smart_telescope/adapters/touptek/managed.py | Same pixel-shift detection as camera.py: `_FLAG_RAW16`, `_detect_pixel_shift()`, `self._pixel_shift`, right-shift in `capture()`, `BITDEPTH` header, updated `get_bit_depth()` | camera_adapter to incorporate pixel-shift detection |
| smart_telescope/adapters/touptek/camera.py | `_detect_pixel_shift` replaced with GCD-of-differences algorithm (robust to non-aligned black-level offsets); `set_black_level` resets `_pixel_shift=-1` | camera_adapter to incorporate GCD shift detection |
| smart_telescope/adapters/touptek/managed.py | Same GCD `_detect_pixel_shift` fix + `set_black_level` resets `_pixel_shift=-1` | camera_adapter to incorporate GCD shift detection |
| smart_telescope/adapters/touptek/managed.py | `_select_device()`: a configured `camera_id`/`model`/`name` selector that matches no enumerated device now returns "not found" instead of silently falling back to a positional index (M10-026, hardware evidence 2026-07-18: OAG role bound to the guide camera's physical device when its model selector failed to match). Mirrors the already-correct `resolve_device_id()` behavior in the same file. Pure index-only configs (no selector at all) are unaffected. | camera_adapter to align `_select_device()` with `resolve_device_id()` |

## Pending external requirements

_(none)_

## How to sync

```bash
bash scripts/sync_camera_adapter.sh --dry-run   # check for drift
bash scripts/sync_camera_adapter.sh              # apply update
# review diff, update this file if needed, then commit
```

## Smart_telescope-owned files that consume camera_adapter APIs

When camera_adapter changes API surface, manually update these:

| File | External APIs consumed |
|---|---|
| `smart_telescope/config.py` | `CameraSpec`, `CoolingSpec`, `FilterWheelSpec`, `GuidingSpec` shape |
| `smart_telescope/runtime.py` | `SmartTouptekCamera`, `TouptekFilterWheel`, `get_camera_by_role` pattern |
