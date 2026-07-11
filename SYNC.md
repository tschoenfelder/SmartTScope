# OnStepAdapter Dependency

`onstep_adapter` is a **pip-installed package**, not a synced source copy.
Install URL (pinned): `https://github.com/tschoenfelder/OnStepAdapter/releases/download/v0.3.0/onstep_adapter-0.3.0-py3-none-any.whl`

The directory `smart_telescope/adapters/onstep/` is **SmartTScope-owned** — do NOT sync
files from the OnStepAdapter GitHub repo into it. It is an override layer that subclasses
the installed package.

## Current migration state (2026-06-17, corrected 2026-07-09)

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

## Active SYNC-OVERRIDEs (kept in `mount.py`)

These are original overrides that cannot be expressed as post-processing wrappers
because the upstream `OnStepMount` does not expose these signatures.

| ID | Method | Why kept in SmartTScope |
|----|--------|------------------------|
| REQ-1 | `move(direction, move_ms)` | **Reclassified 2026-07-11 — NOT an upstream ask.** User direction: SmartTScope should call `onstep_adapter`'s actual public API directly (`move_ra_timed()`/`move_dec_timed()`, `mode="center"`) and translate `direction`/`move_ms` into that signature locally, rather than asking upstream to add a method matching SmartTScope's `MountPort` shape. Stays in shim permanently as a translation wrapper, same treatment as REQ-2. |
| REQ-2 | `set_park_position() → bool` and `get_park_position() → MountPosition\|None` | `MountPort` ABC compliance; upstream already has `set_park_position_from_current()` and `get_stored_park_position()` — these two methods stay in shim permanently as interface adapters |
| REQ-ST-001 | `ensure_time_location_synced()` | **Reclassified 2026-07-11 — NOT an upstream ask.** It's pure config-forwarding glue (pulls `lat`/`lon`/`alt_m` from SmartTScope's own `config.py`, then calls upstream's existing `sync_onstep_time_location()`). SmartTScope's config has no reason to live in a generic adapter; stays a permanent local wrapper. |

## Pending upstream requests

These patches are currently in `mount.py`. They should be evaluated for adoption
into `onstep_adapter`; raise with the package maintainer.

| ID | Method | Reasoning for upstream adoption |
|----|--------|----------------------------------|
| REQ-ST-002 | `sync_onstep_time_location()` (confirmed_by_user extension) | Sets `time_trust_source="user_confirmed"`; base class leaves it unset. **Confirmed present in v0.3.1 upstream (2026-07-11) — pending removal audit, see `docs/todo.md` ONS31-004.** |
| REQ-ST-003 | `get_state()` `_explicit_tracking_started` flag | **Reframed 2026-07-11.** Original ask only disambiguated *reporting* (relabel as AT_HOME instead of TRACKING). User direction: the actual fix should be behavioral — if firmware auto-starts tracking after `:hR#` that SmartTScope never requested, actively stop it (e.g. call the same verified-disable path REQ-ST-005 uses), not just reinterpret status while the mount keeps tracking underneath. This is a protocol-layer behavior change to `OnStepMount` — flagged per the never-edit-adapter-directly guardrail, awaiting user go-ahead before implementation. Still worth raising upstream too, since any GEM OnStep host hits the same firmware quirk. |
| REQ-ST-004 | `enable_tracking()` at-home bypass | Positional limits unsound at CWD home (stale RA); safety lock still applies. **Confirmed present in v0.3.1 upstream (2026-07-11) — pending removal audit, see `docs/todo.md` ONS31-004.** |
| REQ-ST-005 | `disable_tracking_verified()` flag clear | Consistent flag lifecycle. Confirmed as scoped correctly (2026-07-11) — stays an upstream ask as-is; becomes the mechanism REQ-ST-003's active-stop behavior would call. |
| REQ-ST-006 | `stop()` / `park()` / `unpark()` flag clear | **Reframed 2026-07-11.** User direction: `unpark()` in general should drive the mount to a genuine non-tracking mechanical state, not just clear SmartTScope's own bookkeeping flag. Same protocol-layer-behavior-change status as REQ-ST-003 — flagged, awaiting go-ahead. |
| REQ-ST-007 | `motion_safety_preflight()` pier-side guards | (a) terminal_state; (b) axis2 < 15° stale `:Gm#` suppression. **Confirmed present in v0.3.1 upstream (2026-07-11) — pending removal audit, see `docs/todo.md` ONS31-004.** |
| REQ-ST-008 | `_haversine_m()` + `_lx200_round_degrees()` helpers, used by `get_sync_status()`'s meter-based location tolerance (M8-008) | Generic geo/LX200-format utilities any OnStep client doing location-sync checks would need; found via diff against the vendored copy 2026-07-09, never filed upstream when added. **Confirmed needed regardless of upstream outcome (2026-07-11) — stays local either way; upstream adoption is a nice-to-have, not a blocker.** |

## Upgrading onstep_adapter

1. Update the wheel URL in `pyproject.toml` to the new release.
2. Run `pip install -e ".[dev]"` to fetch the new wheel.
3. Review each REQ-ST-* override in `mount.py` — check if the base class now handles it.
4. Review `client.py` — its `__init__` replicates the base `__init__` body and must be
   updated if upstream `OnStepClient.__init__` changes.
5. Run: `python -m pytest tests/unit/ -x -q`
6. Commit: `git commit -m "chore: upgrade onstep_adapter to vX.Y.Z"`

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
