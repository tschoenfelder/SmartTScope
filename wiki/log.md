# Wiki Log

Append-only record of all wiki operations.

---

## 2026-07-11 — RECLASSIFICATION — REQ-1/REQ-ST-001/003/006 reworked per user direction

Follow-up to the same day's v0.3.1 research entry (below). User gave concrete
direction on 4 of the 6 remaining gaps, changing them from "ask upstream" to
either "adapt SmartTScope locally" or "fix the actual behavior, not just the
status report":

- **REQ-1** — not an upstream ask. SmartTScope should call `onstep_adapter`'s
  real `move_ra_timed()`/`move_dec_timed()` directly and translate
  direction/duration locally, instead of asking upstream to add a method
  matching SmartTScope's own signature. Captured as `LOCAL-001`.
- **REQ-ST-001** — not an upstream ask. It's pure config-forwarding glue
  (SmartTScope's own `config.py` values pushed into upstream's existing
  `sync_onstep_time_location()`); no adapter feature is missing. Captured as
  `LOCAL-002`.
- **REQ-ST-003** — reframed. The original ask only relabeled `get_state()`'s
  report (AT_HOME instead of TRACKING) when firmware auto-starts tracking
  after `:hR#`. User: if the app didn't ask for tracking and it's tracking
  anyway, the real fix is to stop it, not just reinterpret the status while
  the mount keeps tracking underneath. Captured as `SAFETY-001`, P0.
- **REQ-ST-006** — reframed similarly: `unpark()` should drive the mount to
  a genuine non-tracking mechanical state in general, not just clear
  SmartTScope's own bookkeeping flag. Captured as `SAFETY-002`, P0.
- **REQ-ST-005** — confirmed scoped correctly as-is (stays an upstream ask;
  becomes the mechanism SAFETY-001 would call).
- **REQ-ST-008** — confirmed necessary regardless of upstream outcome ("so
  you need it") — already implemented locally, stays local either way;
  upstream adoption is a nice-to-have, not a blocker.

`SAFETY-001`/`SAFETY-002`/`LOCAL-001` all touch `OnStepMount` protocol-layer
code in `smart_telescope/adapters/onstep/mount.py`. Per the 2026-07-09
guardrail (below), none were implemented — captured as open `docs/todo.md`
items awaiting explicit go-ahead. `SYNC.md`'s Active SYNC-OVERRIDEs and
Pending upstream requests tables updated to match; `docs/todo.md`'s Phase 0
table and RFC-prep item (`ONS31-008`) rescoped to drop REQ-1/REQ-ST-001 and
reframe REQ-ST-003/006.

---

## 2026-07-11 — RESEARCH — OnStepAdapter v0.3.1 checked; upgrade task list added

User asked to check `tschoenfelder/OnStepAdapter` release v0.3.1 for its
supported FSM and plan fully moving OnStep USB connectivity onto that
adapter, without editing it directly (RFC only, if needed). Fetched the
release and source via `gh api` against the published tag — never a local
checkout, per the standing guardrail (see 2026-07-09 entries below,
`project_onstep_adapter_v030` memory).

**Findings:** v0.3.1 is a packaging fix only — it removes the colliding
top-level `smart_telescope/*` files that v0.3.0's wheel shipped, so
`onstep_adapter` is now importable standalone
(`from onstep_adapter import OnStepClient, OnStepSafetyConfig`) without
namespace collision risk. It does **not** close the feature gap that has
blocked the `ONS-MIGRATE-*` shrink-to-shim plan since 2026-06-17: diffing
upstream `mount.py` (4,329 lines) against local
`smart_telescope/adapters/onstep/mount.py` (4,502 lines) still shows a
~173-line delta. `REQ-ST-002` and `REQ-ST-007` are now present upstream;
`REQ-1`, `REQ-ST-001`, `REQ-ST-003/005/006`, and `REQ-ST-008` remain
absent. `client.py` is already byte-for-byte identical upstream vs local.

FSM confirmed: `MountState` enum (`UNKNOWN, PARKED, UNPARKED, SLEWING,
TRACKING, AT_LIMIT`) in `onstep_adapter/ports/mount.py`, derived
stateless-ly in `get_state()` from decoded `:GU#` flags. Focuser has no
state enum (`is_moving`/`is_available` booleans only). Connection FSM is
boolean-based (`OnStepConnectionResult`), never raises.

An Explore pass also reconfirmed direct USB/serial connectivity is already
100% consolidated in `smart_telescope/adapters/onstep/{mount,serial_bus}.py`
— no legacy/duplicate direct-serial code exists elsewhere in the repo.

**Action:** Added a new `### Upgrade to v0.3.1 — 2026-07-11` task block to
`docs/todo.md` (`ONS31-001..009`, all `P1`), mirroring the existing
`ONS3-001..006` v0.3.0-upgrade format: pin bump, install/verify, diff audit,
cautious override-removal review, test run, `SYNC.md` update, commit — plus
two RFC-prep items (draft upstream change-request text for the still-open
REQ items, but hold filing until the user explicitly approves, per the
2026-07-09 guardrail below). Did not touch `pyproject.toml`, `SYNC.md`, or
any `smart_telescope/adapters/onstep/*.py` file — those are the execution
steps the new task-list items describe, not part of this planning pass.

---

## 2026-07-09 — GUARDRAIL — never edit OnStepMount/OnStepClient directly

Follow-up to the prior entry's guardrail. User: "migrate to using the
library... don't 'If a fix belongs in OnStepMount/OnStepClient/etc., I
should just make the change there directly', but raise a request against
me." Asked two clarifying questions (which local folder counts as "the
library"; what "raise a request" should concretely mean).

Answers: **"Use the library from git only"** — neither local checkout
found on this machine (`Documents/Codex/CameraTest/OnStepAdapter`,
`Documents/Codex/SmartTScope/onstep_adapter`) is to be treated as an
editable working copy; the only canonical source is the published git
release. **"Just flag it to you directly in chat and wait"** — when a fix
belongs inside `OnStepMount`/`OnStepClient`/etc. (not SmartTScope's own
`services/`/`api/` code calling their existing public methods), stop,
describe it, and wait — no auto-editing, no auto-filing to SYNC.md, no
opening a GitHub issue unprompted.

This session's M9-023/025/026/027 fixes were all correctly scoped under
this rule already (all in `services/mount_operations.py` and
`services/observing_service.py`, consuming the adapter's existing public
methods, never touching `adapters/onstep/*.py`) — the rule formalizes and
protects that boundary going forward rather than correcting a violation.

Saved to `SYNC.md` (git-tracked, durable) and the
`project_onstep_adapter_v030.md` project memory.

---

## 2026-07-09 — GUARDRAIL — OnStepAdapter is the sole mount/focuser adapter

User restated an explicit, durable guardrail: only
https://github.com/tschoenfelder/OnStepAdapter/tree/main is to be used to
connect to focuser and mount. That repo was extracted from SmartTScope's
own code for reusability. SmartTScope must not contain duplicated
implementations of this code. When functionality is identical, that's
correct and expected (it was extracted from here); when gaps are observed,
they must be pointed out clearly as migration items rather than left as
silent local-only code.

This corrects an earlier overstatement in this same conversation, where I
described the OnStepAdapter repo as having "no independent implementation" —
checked directly (not from stale memory): the repo's vendored
`smart_telescope/` folder contains genuine, functioning code. `client.py`
was byte-identical to the local copy; `mount.py` was 197 lines behind,
missing `_haversine_m()`, `_lx200_round_degrees()`, `ensure_time_location_synced()`,
the `_explicit_tracking_started` flag, and the `time_trust_source`/
`confirmed_by_user` changes — all already tracked as REQ-ST-001..007 in
`docs/todo.md`'s ONS-MIGRATE section, except `_haversine_m`/
`_lx200_round_degrees` (added in M8-008, never filed upstream) — added now
as REQ-ST-008, plus a new ONS-MIGRATE-014 tracking the sync/publish gap
itself.

Saved as a project memory (`project_onstep_adapter_v030.md`) so this
guardrail and the "diff before claiming parity" lesson persist across
sessions.

---

## 2026-07-09 — FIX — M9-027: stop blindly resending :hP# on retry

User: "Via the Onstep UI I have always been able to request a move to
park! Don't you use the adapter to request move to park? You shouldn't
send :hP#" — pushing back on M9-026's fix, pointing out that OnStep's own
UI never has this problem.

Checked `wiki/onstep-protocol.md`'s hardware-confirmed behaviour notes:
`:hP#` is documented as fire-and-forget, ~10 ms reply, slew taking
30–120 s, with **no documented case of it ever returning a rejection**
(`'0'`) — unlike `:hR#` (unpark), whose own doc entry explicitly says it
can return `'0'` "if unpark is rejected (e.g. no alignment stored)". A
real `'0'` reply for `:hP#`, as seen in the M9-026 log, is therefore a
previously unobserved case.

Root cause: `_maybe_auto_advance()` re-spawns `_run_safe_stop()` (and
therefore `park_sequence()` → `mount.park()` → a fresh `:hP#`) on *every
single poll* (observing.js polls every 2.5 s) while `g8` stays False.
OnStep's own UI is driven by a human clicking "Park" once and watching —
it never hammers `:hP#` repeatedly while a previous attempt might still be
resolving. The M9-026 log's second, rejected `:hP#` is very likely exactly
this: a resend while the first (accepted) command was still in flight.

Fix: `ObservingService` now tracks `_park_command_issued_at` — set once
`park_sequence()` successfully issues `:hP#` without raising, cleared once
PARKED is actually observed. While set and within `_PARK_COMMAND_MAX_WAIT_S`
(120 s, matching the documented max slew time), `_run_safe_stop()` skips
calling `park_sequence()` again on subsequent auto-advance retries — it
just re-checks `device_state` instead of re-sending the command. Falls
back to resending only if genuinely stuck past 120 s.

New test `test_stop_safely_does_not_resend_park_command_on_retry` asserts
`mount.park()` is called at most once across repeated auto-advance retries
while the mount never reaches PARKED. 199 tests pass, 0 regressions.

---

## 2026-07-08 — FIX — M9-026 resolved: found the real bug from server logs

Follow-up to the M9-026 entry below. User supplied the actual server log
around the fault, which turned out to be conclusive:

```
park_sequence: pre-park state = AT_HOME
Mount park issued
Mount park slew started: state = AT_HOME
park_sequence: pre-park state = AT_HOME
OnStepMount.park(): OnStep did not accept :hP#; reply='0'
```

First `:hP#` was accepted (`reply='1'`) — but the state stayed `AT_HOME`
the entire time; it never actually moved. `park_sequence()`'s post-command
check called `device_state.poll_until_changed(MountState.UNPARKED,
timeout_s=5.0)` — a **hardcoded** baseline, not the mount's actual
`pre_state`. Since `AT_HOME != UNPARKED` is trivially true from the very
first poll iteration, this falsely reported "slew started" without any
real movement. Because the mount consequently never reached `PARKED`, a
*second* `park_sequence()` call followed shortly after (same
`pre-park state = AT_HOME`) — and that second `:hP#` is the one OnStep
genuinely rejected.

Fix: `poll_until_changed()` is now called with the mount's actual
`pre_state` as the baseline, not a hardcoded `MountState.UNPARKED` — so
this check works correctly whether parking is commanded from `AT_HOME`,
`TRACKING`, or any other state, not just the `UNPARKED` case the original
code implicitly assumed (i.e. parking from a normal tracking/observing
session, never previously exercised via the guided home→park path this
session introduced). Also fixed the accompanying warning log's hardcoded
"still UNPARKED" wording.

**Still open:** *why* the mount didn't actually progress after the first
accepted `:hP#` — a real mechanical/firmware question, possibly specific
to parking directly from the mechanical-HOME route, unconfirmed — and
whether `park_sequence()` should avoid blindly re-issuing `:hP#` on retry
if a previous attempt was already accepted but not yet confirmed complete.
New regression test added; 28 + 166 tests pass, 0 regressions.

---

## 2026-07-08 — OPEN — M9-026: real :hP# rejection, root cause not yet found

User hit "FAULT: :hP# rejected by OnStep — home the mount first to
establish the park position, then park" trying to park after homing. My
first read (M9-022-era) assumed no park position had ever been saved.
User corrected this directly: a park position *is* already saved in the
OnStep controller (set up outside this app — matches `park_sequence()`'s
own docstring: "The park position must be configured in OnStep directly —
this function never modifies it"). "Just return to the saved position...
It says move to park, not make current the new park" — i.e. the fix isn't
a way to set a new park position; `:hP#` (move to the *existing* saved
position) should simply be made to work.

Checked `_raise_if_locked()` — if a SmartTScope-side safety lock had
blocked this, a different, more specific error would have been raised
instead of the generic `park_sequence()` message. So this is a genuine
OnStep firmware rejection of `:hP#`, for a reason not yet identified.

Rather than guess again, corrected the misleading part: `park_sequence()`'s
`RuntimeError` no longer asserts a specific unverified cause — it points at
the server log instead, where `OnStepMount.park()` already logs the raw
OnStep reply (`reply=%r`) that would show the real reason. **Root cause
still open** — needs that logged reply value (or `collect_logs.sh` output)
from the user's actual hardware; not solvable from code-reading alone this
time.

---

## 2026-07-08 — SAFETY — M9-025: disable tracking immediately after unpark

User: "Tracking should be disabled directly after unpark to prevent
unwanted movements."

`home_sequence()` only disabled tracking if a *subsequent* `get_state()`
query reported `TRACKING` — but some OnStep firmware auto-starts sidereal
tracking immediately on `:hR#` (unpark), and that check races against the
firmware: there was a window where the mount could be tracking (moving)
before the home command was issued and before anything explicitly turned
tracking off.

Fix: call `mount.disable_tracking()` unconditionally right after a
successful `unpark()`, before the propagation sleep — not gated behind a
state re-check. Kept the existing conditional check afterward as-is (covers
the mount already being `TRACKING` on entry, not freshly unparked in this
call).

New test deliberately mocks the tracking-check query to return something
other than `TRACKING`, to prove the disable call happens unconditionally
rather than via that check. 27 targeted + 189 broader tests pass, 0
regressions.

---

## 2026-07-08 — FIX — M9-024: the actual root cause was the button label

After M9-021/022/023, user kept seeing the same shape of confusion and
pushed back sharply: "Confirm to home logically can only be pressed, if at
home! Should one confirm the location and time if they are not correct?"

That's the answer. `Intent.START_HOME`'s label was "Confirm HOME position"
— but clicking it doesn't confirm an already-true state, it *performs* the
unpark+slew-to-home action starting from wherever the mount currently is,
including PARKED. "Confirm X" implies X is already true and just needs
acknowledging — like the already-correctly-named "Accept — home confirmed"
step that appears *after* homing succeeds, or "Confirm Pi Time" elsewhere
in this app, which only asserts trust in an already-current clock rather
than changing it. A "confirm" action should never be the thing that makes
its own subject true. That single mislabeled string, sitting on a button
next to a mount-strip reading PARKED, is almost certainly what drove every
round of "why does it say confirm home while parked" this session — not a
defect in the underlying M9-021/022/023 fixes, which were all real and
correct on their own terms.

Fix: relabeled to "Home the mount" — matches the "Home" terminology already
used for this exact action elsewhere (Maintenance's "Home" button, the
mount-strip's own "HOME"/`AT_HOME` state label). The two-step start/accept
structure underneath (introduced in M9-007/M9-016) was already correct;
only the display string was wrong. No test asserted the old label. Verified
live: `primary_action.label` now reads "Home the mount" while the
mount-strip still shows PARKED and before any home action has run — no
semantic contradiction left on screen.

---

## 2026-07-08 — FIX — M9-023: mount-strip lagged behind HOME confirmation

User pushback: "the screen moves ... to asking for confirming home but
regardless staying at parked" — asked to check the state machine for a
logical weakness rather than just re-assert the fix was fine.

Found by comparing `_run_home()` against `_run_safe_stop()` (the park path):
`_run_safe_stop()` calls `deps.device_state.poll_now()` right after
`park_sequence()` — its own docstring: "Used after park/unpark commands to
refresh the cached state without waiting for the next background poll
interval (nominally 2 s)." `_run_home()` never had the equivalent call
after `home_sequence()`.

Net effect: the Observe screen's phase panel (`/api/observing/state`, polled
every 2.5s, reflects `ObservingService`'s in-memory guards immediately) and
the mount-strip (`/api/mount/status`, polled independently every 5s, backed
by `DeviceStateService`'s separately-cached state) could visibly disagree
for several seconds right after confirming HOME — phase panel already
showing "Accept — home confirmed" while the mount-strip still read PARKED.
Not a state-machine defect exactly (the FSM/guards were correct throughout)
but a real, user-visible inconsistency between two independently-polled
UI elements, caused by an asymmetry between two structurally-similar
service methods.

Fix: added `deps.device_state.poll_now()` to `_run_home()`, mirroring
`_run_safe_stop()` exactly. Also fixed a stale comment in the same method
still referencing the `api/mount.py` `set_park_position` endpoint removed
in the prior correction.

Verified live: `GET /api/mount/status` immediately after `START_HOME` (zero
sleep) now reads `"state": "at_home"` instead of stale data. 3924 tests
pass, same 4 pre-existing/unrelated failures, 0 new regressions.

---

## 2026-07-08 — CORRECTION — M9-022's "fix" removed too; scope check with user

Immediate follow-up to the previous entry. That correction reverted the
auto-set-park regression but then added a *new* "Set Park Position" button
+ `POST /api/mount/set_park_position` endpoint, reasoning that some explicit
way to set park position should exist since the 2026-06-14 removal left
none.

User clarified: the only documented requirement here (that same 2026-06-14
entry) says the app must never change the park position *automatically* —
it does not ask for a UI way to change it at all. Building that UI was
scope beyond the actual ask, decided unilaterally rather than requested.

Removed entirely: the endpoint (`api/mount.py`), the button and its JS
(`static/js/mount.js`), and the scaffolding added only to support them
(`MockMount.set_park_position()` override, the `mount_mock` fixture default,
and their tests in `test_mount.py`). Net result: `ObservingService._run_home()`
stays reverted (M9-021 shape, no park-position involvement at all — that
part of the correction was correct and stays). The underlying gap — nothing
in this app can save an OnStep park position, so `:hP#` will keep rejecting
on any hardware without one already configured — is confirmed real and left
open on purpose, not solved here. Setting it requires going outside this
app (e.g. OnStep's hand controller) until a real requirement asks for a
UI path.

3929+ tests pass, same 4 pre-existing/unrelated failures, 0 new regressions.

**Second lesson layered on the first:** finding a real gap (no way to set
park position) doesn't mean I should decide the fix and build UI for it in
the same breath — confirm the requirement actually calls for that capability
before adding it, especially for anything that writes to persisted hardware
state.

---

## 2026-07-08 — FIX — M9-022 corrected: undo an auto-set-park-position regression

User report: "the UI again shows confirm home position [while] parked...
should have been fixed two sessions ago!" Investigating turned up that my
own M9-022 fix (this session) was itself a regression of a previously-fixed
bug.

M9-022 added `mount.set_park_position()` as an automatic call inside
`ObservingService._run_home()`, right after every HOME confirmation, to fix
`:hP#` (park) rejections. But an entry already in this log from 2026-06-14,
"CRITICAL: remove auto_set_park; home UI live status", says:

> Removed `auto_set_park` from `park_sequence()` and park API endpoint.
> Pressing Park from AT_HOME was automatically calling `set_park_position()`
> (`:hS#`), overwriting the user's configured EEPROM park position. Park
> position must only be set by explicit user action.

M9-022 reintroduced exactly this anti-pattern via a different trigger (HOME
confirmation instead of the Park button) — I found `set_park_position()`
dangling with zero callers and an adapter-shim comment suggesting it should
be auto-called after HOME, and wired it in without searching this log for
prior art on the area first, which would have surfaced the 2026-06-14 entry
immediately.

Corrected:
- `ObservingService._run_home()` no longer touches `set_park_position()` at
  all — back to the M9-021 shape (`g2_home_confirmed` from `at_home` alone).
- Added the missing piece properly this time: a new, explicit, two-step-
  confirm `POST /api/mount/set_park_position` endpoint (`api/mount.py`,
  mirroring `mount_park`'s existing `{confirmed: bool}` pattern) and a "Set
  Park Position" button in the Maintenance mount-strip button group
  (`static/js/mount.js`), gated behind a native `confirm()` dialog since it
  overwrites a persisted EEPROM value. This is the deliberate, user-initiated
  action that should have existed since the 2026-06-14 removal but never
  did — which is the actual reason `:hP#` had nothing to park to in the
  first place (the M9-021/M9-022 investigation's real root cause).

3929 tests pass, same 4 pre-existing/unrelated `test_get_sync_status.py`
failures, 0 new regressions. Verified via direct API calls: HOME confirmation
no longer reports a `park_position_set` field at all; the new endpoint
requires explicit confirmation before calling `mount.set_park_position()`.

**Lesson for future sessions:** before wiring up a dangling/unused method
found via grep, search `wiki/log.md` for its name and its immediate
neighborhood — a prior fix or explicit removal in this exact area is a real
possibility in a codebase this actively debugged, and re-doing a reverted
change is worse than not touching it at all.

---

## 2026-07-08 — FIX — M9-022: "Stop safely" faulted right after a successful HOME confirmation

Immediately after fixing M9-021, real hardware testing hit a second, related
fault: "Stop safely" (park) raised `:hP# rejected by OnStep — home the mount
first to establish the park position, then park" — even though the mount had
just been correctly homed and the page showed HOME.

Root cause: OnStep firmware rejects `:hP#` (park) unless a park position was
previously saved via `:hS#`. `mount.set_park_position()` /
`set_park_position_from_current()` already existed on `MountPort` and the
OnStep adapter — the adapter shim's own comment even says "SmartTScope's
park workflow sets park = home position after a HOME slew" — but **nothing
in the application ever called it**: not `ObservingService._run_home()`, not
`api/mount.py`'s existing "HOME" button, not the Maintenance setup-check
wizard. The error's own suggested fix ("home the mount first") didn't
actually address the real missing step, since homing alone never saves a
park position. This had presumably always been broken; it only surfaced now
because M9-016/M9-017 (this session) are the first code to actually exercise
HOME → park end-to-end on real hardware via the guided flow.

Fix: `ObservingService._run_home()` now calls `deps.mount.set_park_position()`
right after confirming `AT_HOME` (never attempted if home wasn't actually
reached). Best-effort: a rejection is logged and recorded in
`detail["home"]["park_position_set"]` but doesn't invalidate
`g2_home_confirmed` — reaching home and saving a park position are different
things, and a genuine park failure will still surface on its own via the
later "Stop safely" attempt. `MockMount` gained a `set_park_position()`
returning `True` (previously silently inherited `MountPort`'s `False`
default); the shared `mount_mock` test fixture now pre-configures it too.

3925 tests pass, same 4 pre-existing/unrelated `test_get_sync_status.py`
failures, 0 new regressions. Verified end-to-end via direct API calls:
`START_HOME` → `detail.home.park_position_set: true` → `STOP_SAFELY` →
`PARKED_SAFE` with `g8_safe_stop_possible: true`.

---

## 2026-07-08 — FIX — M9-021: real-hardware AT_HOME transient-flag race

User report from real Pi/OnStep hardware testing (not reproducible against
`MockMount`): after confirming HOME successfully (mount physically parked/
homed correctly), the guided flow looped back to asking "Confirm HOME
position" again instead of continuing.

Root cause: `mount_operations.home_sequence()` (M9-016) returned `None`, and
`ObservingService._run_home()` determined success by calling
`deps.mount.get_state()` a *second*, independent time after `home_sequence()`
returned. But `AT_HOME` is documented in `home_sequence()`'s own tight-poll
comment as a brief OnStep status flag — "the slew completes and 'H' clears
before the next background poll fires." On real hardware it can clear before
that second query runs, so `_run_home()` could see some other state and set
`g2_home_confirmed=False` even though homing genuinely succeeded — sending
the flow back to "Confirm HOME position" while the mount itself was fine.
`MockMount`'s `AT_HOME` is a persistent mock state (doesn't clear), which is
why this passed all prior test and Playwright verification.

Fix: `home_sequence()` now returns `bool` — `True` only if its own tight poll
actually observed `AT_HOME` (the one well-timed, authoritative check).
`_run_home()` uses that return value directly for the guard instead of
re-querying; `get_state()` is still read once afterward, but now purely for
the informational `detail["home"]["mount_state"]` field, decoupled from the
success decision. Existing callers (`api/mount.py`'s "HOME" button,
`setup_check_service.py`'s setup-check wizard) already ignored the return
value entirely, so the signature change is source-compatible with both.

Two new `test_mount_operations.py` cases cover both outcomes explicitly.
Full sweep: 3557+ tests pass, same 4 pre-existing/unrelated
`test_get_sync_status.py` failures, 0 new regressions. Also confirmed the
Pi deploy scripts (`astro_pull_start.sh` → `astro_start.sh`) always pair a
`git reset --hard`/pull with a forced wheel reinstall and fresh process
start — so this wasn't a stale-deploy issue, and `/api/version`'s git hash
badge (computed live via `git rev-parse` on every request, per
`api/version.py`) only ever reflects what's checked out on disk, not
whether the running process has actually loaded it.

---

## 2026-07-08 — FIX — M9-017: safe-park available before POLAR_ALIGN; target-selection gap logged

Testing progressed past HOME confirmation to `POLAR_ALIGN`. Raised: how to
safely park if weather turns, given the always-visible "■ Stop" button only
halts (`/api/emergency_stop` → `mount.stop()`), and the real park path
("Stop safely") wasn't available during `WAIT_CONTEXT_CONFIRMATION`/
`WAIT_HOME_CONFIRMATION` — only from `POLAR_ALIGN` onward.

- Added a direct `STOP_SAFELY` check to `_on_wait_context()`/`_on_wait_home()`
  in `domain/observing_state.py`, ahead of their existing fallbacks —
  deliberately *not* added to `_ACTIVE_PHASES` wholesale, since `PAUSE` has
  no meaning when nothing is actively running yet (a new `_STOP_ONLY_PHASES`
  set in `observing_service.py` offers `STOP_SAFELY` alone for these two
  phases). Relabeled `STOP_SAFELY` to "Stop safely (park)" everywhere so the
  outcome is unambiguous.
- Confirmed via code reading that this is safe: `park_sequence()` already
  no-ops if the mount is already parked; `handle_intent()` already lets
  `STOP_SAFELY` bypass the busy-lock, so sending it while `_run_home` is
  mid-flight just queues the park until the current attempt finishes,
  rather than racing.
- 1113 tests pass (full domain/services/api/integration/vertical-slice
  sweep), 0 regressions. Verified live via Playwright from both wait phases,
  including hitting "Stop safely (park)" immediately after starting the home
  sequence — reaches `PARKED_SAFE` cleanly both times.

Investigating the underlying "can't observe Venus" question surfaced a much
bigger, previously undocumented gap: `api/observing.py:_build_deps()`
hardcodes `optical_profile=C8_NATIVE, target_ra=M42_RA, target_dec=M42_DEC` —
there is no way to select a different target from the guided Observe screen
at all. Logged as new backlog `M9-018` (target selection — decided to reuse
the existing "Visible Tonight" catalog rather than manual RA/Dec entry or a
new name-search/ephemeris picker), `M9-019` (skip-polar-alignment for
bright/planetary targets), and `M9-020` (camera/optical-train identity +
live preview in Observe) — none built this session, prioritized for later.

---

## 2026-07-08 — FIX — M9-016/M9-007: location-select revert bug + real HOME confirmation

Two bugs found using the guided Observe screen's Time & Location / HOME steps.

- **Location dropdown reverted mid-edit.** Picking "+ New location…" (or any
  saved location) cleared the panel's dirty flag instead of setting it, so the
  next background poll (every 2.5s in the Observe screen) silently reverted
  the in-progress name/lat/lon back to the active location before the user
  could click Confirm. Same bug in both `observing.js` and `setup.js` (copied
  code); far more visible in Observe due to continuous polling, but real in
  Maintenance too. Fixed: both `_obsOnLocationSelectChange()`/
  `onLocationSelectChange()` branches now mark the panel dirty on selection.
- **"Confirm HOME position" was a disconnected no-op (M9-007).** It set
  `g2_home_confirmed=True` unconditionally with no mount action — hence the
  mount-strip correctly kept reading PARKED, which is exactly what looked
  wrong. Wired to the existing `mount_operations.home_sequence()` (same code
  the Maintenance "HOME" button already uses: auto-unpark, disable tracking,
  slew to OnStep's stored home, poll for `AT_HOME` up to 60s) as a background
  action, matching the start/accept pattern already used for Polar
  Align/Focus/Target Acquire — new `Intent.START_HOME` spawns it
  (`ObservingService._run_home`), `CONFIRM_HOME` becomes the accept step
  gated on `g2_home_confirmed`. A hard failure (e.g. unpark rejected) faults
  the session same as any other engine; a 60s timeout without reaching
  `AT_HOME` just re-offers "Confirm HOME position" since the accept guard
  stays false — no extra retry logic needed. Confirmed with the user that the
  mechanical HOME route intentionally skips the general HA/altitude/meridian
  preflight `goto()` uses (it targets OnStep's own fixed home position, not a
  computed target) — unchanged, already-relied-on behavior, not a new risk.
- Along the way: `adapters/mock/mount.py`'s `go_home()` was setting `TRACKING`
  instead of `AT_HOME` (never let the poll succeed); fixing that then exposed
  that `goto()` never simulated OnStep firmware's `:MS#` auto-engaging
  tracking either — added, since a later stage's "tracking lost" check
  depends on it.
- Verified via Playwright against a live mock-adapter server: dropdown
  survives a >3.5s wait with edits intact; mount-strip changes from PARKED to
  HOME after confirming, detail JSON shows `{"home": {"mount_state":
  "AT_HOME"}}`, both guard chips turn green, Accept advances to POLAR_ALIGN.
  57 targeted + 307 broader workflow/vertical-slice/runtime + 296
  onstep-adapter/mount-API tests pass (same 4 pre-existing/unrelated
  `test_get_sync_status.py` failures).

---

## 2026-07-08 — FIX — M9-015: Time & Location panel follow-up

User report against the M9-014 panel: local time showed raw microseconds+no-space offset (`17:02:38.580558+02:00`), there was no way to see or change time-trust status, and a real config with `alt_m = 304.0` under `[observer]` still showed height 0m in the UI.

- **Timestamp:** `local_time_iso` now `isoformat(timespec="seconds")`; frontend `formatLocalTime()` (new, `api.js`) adds a space before the offset. Reads `2026-07-08 17:02:38 +02:00`.
- **Time trust badge + Confirm Pi Time:** `LocationStatusResponse.time_trust_source` exposes the existing gate value (`GPSD_FIX`/`NTP`/`ONSTEP_COMPARISON`/`USER_CONFIRMED`/`NOT_TRUSTED`); shown as a badge (green when trusted) next to local time in both the Observe and Maintenance panels. A "Confirm Pi Time" button (`POST /api/mount/confirm_time`) sits beside it — same endpoint the Maintenance screen's older `stage1ConfirmTime()` already used, now reachable from the location panel itself in both screens.
- **Root cause of the height bug:** `config.py` only read `[observer].height_m`; the user's config used `alt_m` (matching `OnStepSafetyConfig.observer_alt_m`'s own field name in `adapters/onstep/safety.py`), so it silently defaulted to `0.0`. `_parse_observer_height_m()` now tries `height_m` first, falls back to `alt_m`.
- **Second bug found while in there:** `build_onstep_safety_config()` never passed `observer_alt_m=OBSERVER_HEIGHT_M` to `OnStepSafetyConfig` at all — the configured elevation never reached the mount adapter (used by `ensure_time_location_synced()`'s OnStep site-altitude push and the altitude-consistency check in `get_sync_status()`), so OnStep was always told `0.0` regardless of config. Now wired through.
- **Home display name:** new `OBSERVER_HOME_NAME` (`[observer].name` in config.toml, e.g. "Usingen, HE") feeds `HomeLocation.name`, shown as the label of the location-select's Home option. The internal `"Home"` identity (`OBSERVER_LOCATION_NAME`, the confirm/select round-trip's `value === 'Home'` checks) is untouched — purely a display change.
- `templates/config.toml`: documented the `alt_m` alias and the new `name` key.
- 12 new/updated tests (`test_config.py`, `test_location.py`); full suite 3863+ passed, same 4 pre-existing/unrelated `test_get_sync_status.py` location-tolerance failures, 0 new regressions. Verified live via Playwright against a config using `alt_m = 304.0`: height correctly reads 304, dropdown shows "Usingen, HE", Confirm Pi Time flips the badge to green "USER CONFIRMED".

---

## 2026-07-08 — FIX — M9-014: Time & Location review panel in the guided Observe screen

User report: the Observe screen's `WAIT_CONTEXT_CONFIRMATION` step showed a plain "Confirm time & location" button with no way to see or change what would be confirmed — a regression against the Maintenance screen's existing "Confirm Time & Location" panel (`s1-tl-card`, commits `eeec8e3`/`23aea26`), which already offers a GPS-fix suggestion, saved-location/Home dropdown, and manual lat/lon/height entry against `/api/location/*`.

- `static/index.html`: new `#obs-context-card` in the Observe screen — same fields as `s1-tl-card`'s location section (local time, GPS badge, location select, lat/lon/height inputs, source badge, GPS-fix/IP-lookup/Confirm buttons), under new `obs-loc-*` ids (kept as a separate copy rather than sharing DOM nodes with `s1-tl-card`, since both screens can render independently — reusing ids across the two would collide). Shown only when `phase === WAIT_CONTEXT_CONFIRMATION`, replacing the generic primary button for that phase.
- `static/js/observing.js`: `_obs*` functions mirror `setup.js`'s existing `_renderLocationPanel`/`useGpsFix`/`lookupByIp`/`confirmTimeAndLocation` against the same `/api/location/status` and `/api/location/confirm` endpoints (no backend changes). Confirm posts the reviewed location, then sends `state.primary_action.intent` (`CONFIRM_CONTEXT`) to advance the FSM — same backend call the plain button used to make blindly.
- Fixed along the way: the Confirm button now starts `disabled` until the first `/api/location/status` fetch resolves. On this Windows dev box (no gpsd running), `GpsdService.get_fix()`'s TCP connect to `127.0.0.1:2947` takes ~2s to time out on every `/api/location/status` call, so clicking Confirm before that first fetch landed sent empty lat/lon and got HTTP 422. Should be near-instant on the Pi with real gpsd running, but the guard costs nothing either way.
- Verified via Playwright against a live mock-adapter server: panel populates with Home's lat/lon/height and `CONFIG_FILE` source badge; clicking Confirm advances `WAIT_CONTEXT_CONFIRMATION → WAIT_HOME_CONFIRMATION` with guard G1 turning green, zero console errors. Full existing suite (52 observing/location tests) still passes — backend untouched.

---

## 2026-07-07 — DEVELOP — M9-001..005: Guided Observing State Machine (Phase 1)

New source `smarttscope_requirements_full.md` (§6-7 state model, §11 MVP staging) drove a rewrite of the app's primary screen from a 5-tab wizard ("Startup/Alignment/GoTo&Solve/Collimation/Session", client-side `_stage` navigation) into a single guided flow backed by one authoritative backend state machine.

- `domain/observing_state.py` (new): `ObservingStateMachine` — pure, stateless transition table for `BOOTSTRAP → WAIT_CONTEXT_CONFIRMATION → WAIT_HOME_CONFIRMATION → POLAR_ALIGN → FOCUS_READYING → TARGET_ACQUIRE → GUIDE_READYING → CAPTURE_ACTIVE → SAFE_STOPPING → PARKED_SAFE` (+ `PAUSED_SAFE`/`FAULT`), gated by G1-G10. 32 tests.
- `services/observing_service.py` (new): `ObservingService` orchestrator — dispatches each Intent to the *existing* engines (`PolarAlignmentWorkflow`, `workflow/stages.py` functions via a shared `StageContext`, `GuidingService`, `mount_operations.park_sequence`) rather than reimplementing them; registered as a lazily-created singleton on `RuntimeContext.observing_service`. 17 tests.
- `api/observing.py` (new): `GET /api/observing/state` + `POST /api/observing/intent` — the only endpoint pair the new Observe screen calls to advance the phase (REQ-UX-004). 4 tests.
- `static/js/observing.js` (new) + `static/index.html` restructure: new `#top-view-bar` (Observe / Maintenance) is now the app's primary navigation. The entire former 5-tab UI was wrapped unchanged into `#maintenance-view`, reachable via the Maintenance nav entry (REQ-UX-006). Verified end-to-end via Playwright against a live mock-adapter server — zero console errors, primary-action click advances the phase correctly, Maintenance screen unchanged.
- `tests/integration/test_observing_flow.py` (new): full `BOOTSTRAP → PARKED_SAFE` walk against real mock adapters (`adapters/mock/*`).
- **Scope note:** Phase 1 only — `_stage`/`goToStage()` etc. in `app.js` were kept (not deleted) to drive the Maintenance screen's own internal sub-navigation, since rewriting the internals of `setup.js`/`mount.js`/`preview.js`/`collimation.js`/`session.js`/`focuser.js`/`bias_estimation.js`/`guiding.js`/`click_to_center.js` was out of scope for this pass. Phases 2-6 (unified readiness aggregation, real HOME confirmation + graceful safe-stop, dawn/meridian auto-stop enforcement, filter/object-profile + unified safety config, calibration/offset pre-session gating) are recorded as ordered backlog in `docs/todo.md` under milestone M9.

---

## 2026-06-28 — FIX — GoTo blocked MOUNT_PARKED after skip polar alignment (commit 1c5620d)

- `static/js/mount.js` `s2Done()`: now async; auto-unparks the mount if still parked before navigating to GoTo & Solve. Root cause: "Done / Skip →" on polar alignment only unlocked UI tabs but never issued an unpark command, so GoTo gate always rejected with `MOUNT_PARKED`. Source: session c7fa9811 goto.log — two `goto_rejected MOUNT_PARKED` entries after two Connect All clicks.
- Camera/donut preview darkness (0 stars, AUTO_GAIN_GAIN_LIMIT_REACHED at gain=3200): confirmed hardware/environment — no code bug.

---

## 2026-06-28 — TOOLING — Log collection script (commit 78b44d7)

- `scripts/collect_logs.sh`: bundles the last N lines (default 500) of all section logs (`mount`, `goto`, `stage1_time_location`, `camera`, etc.), `server.log`, and `config.toml` into `~/smarttscope_logs_<timestamp>.zip`. Run with `bash scripts/collect_logs.sh` after observing an error; send the zip for analysis.
- `scripts/astro_start.sh`: server stderr+stdout now tee'd to `$LOG_DIR/server.log` (default `~/.SmartTScope/logs/server.log`) so it is included in the bundle.

---

## 2026-06-28 — FIX — GoTo gate, LX200 location precision, proceed button reload (commit 9aeb3bb)

- `api/session.py` `session_connect()`: preserve `VERIFIED` time/location status across every Connect All call. LX200 `±DD*MM` format truncates to arcminute precision (~1852 m resolution), creating a systematic ~297 m residual that always exceeded the 100 m tolerance — causing every Connect All to reset `VERIFIED → UNKNOWN` and block all GoTo operations.
- `adapters/onstep/mount.py`: added `_lx200_round_degrees()`; `get_sync_status()` now compares the OnStep read-back against LX200-rounded reference coordinates (what was actually pushed) rather than exact config values — `location_ok` is now `True` after a successful push and `location_delta_m` displays the true protocol residual.
- `static/js/setup.js` `refreshHealth()`: re-enables `s1-proceed-btn` (Proceed to Alignment) and unlocks stages 2/4 whenever `/api/status` reports `mount.ok=true`, so the button survives page reload.

---

## 2026-06-28 — FIX — UI state issues after sync and page reload

**Four bugs fixed (commit b295209):**
- `services/device_state.py`: new `clear_mount_safety_violation(reason)` immediately drops a cached safety_violation without waiting for the 2 s background poller.
- `api/mount.py` `mount_sync_clock()`: calls `clear_mount_safety_violation("onstep_clock_invalid")` after a successful sync so the mount card warning disappears on the very next `/api/mount/status` poll; also calls `mount.get_sync_status()` and updates `last_sync_status` so the TL card shows green (post-push) location delta instead of the stale pre-sync red value.
- `services/readiness.py`: repair hint for "Mount time/location" mismatch now says "Use 'Push Time/Location' in the Time/Location Verification card" (that button is always visible when connected) instead of the removed-after-sync "Sync Clock & Location" mount-card button.
- `static/js/mount.js` `_updateMountStrip()`: stages 3 (GoTo & Solve) and 5 (Observation Session) are now unlocked together with stage 2 whenever the mount is unparked, so all tabs remain accessible after a page reload with a live mount. `mountSyncClock()` refresh delay raised from 1 s to 2.5 s as belt-and-suspenders behind the cache clear.

---

## 2026-06-28 — DEVELOP — M8-031 (Optional external frame analyzer integration)

**Pluggable external frame analyzer adapter — drop-in star counting with temporal context.**
- `smart_telescope/domain/star_count.py`: `StarCountResult` (frozen dataclass), `FrameQuality` literal (`"usable"/"too_dark"/"too_bright"/"stars_saturated"`)
- `smart_telescope/services/frame_analyzer.py`: `FrameAnalyzerProtocol` (Protocol + `@runtime_checkable`), `ExternalFrameAnalyzer` (stateless adapter), `load_external_analyzer()` (importlib + graceful fallback)
- `config.py` / `templates/config.toml`: new `[analysis] external_frame_analyzer_module = ""` key; env override `EXTERNAL_FRAME_ANALYZER_MODULE`
- `runtime.py`: `frame_analyzer: FrameAnalyzerProtocol | None` attribute; cleared in `reset_for_tests()`
- `api/deps.py`: `get_frame_analyzer()` dep
- `domain/autogain_service.py`: `frame_analyzer=` param in `run_one_shot()`; quality gates, clamped suggestions, focus_warning early return; bug fix: signal override stored in `_ext_signal_override` and applied after mode-based computation
- `api/autogain.py`: passes `rt.frame_analyzer` to `run_one_shot()`
- `services/setup_check_service.py`: `frame_analyzer=` param in `run_camera_diagnostic()`
- `api/setup_check.py`: passes `rt.frame_analyzer` to service call
- 30 new unit tests: `test_star_count.py`, `test_frame_analyzer.py`, `test_autogain_service.py::TestExternalFrameAnalyzerIntegration`
- Full suite: 3739 passed, 24 skipped

---

## 2026-06-28 — DEVELOP — M8-029 + M8-030 (Delivery audit script; REQ-GIT-001..003)

**Git delivery audit script with JSONL log and pre-push checklist.**
- `scripts/delivery_audit.py`: standalone script (no external deps); runs `git status --short`, `git diff-tree`, `git log`, `git branch --show-current`, `git remote -v`; categorises last-commit files into source/test/doc/other; fails on docs-only commits, uncommitted changes, or unpushed commits; `--push` flag pushes after audit; `--check` dry-run; pre-push checklist printed on every run
- JSONL delivery log: one record per run appended to `~/.SmartTScope/delivery_log.jsonl`; fields: `timestamp`, `branch`, `commit_hash`, `commit_message`, `files_changed`, `source_files_changed`, `test_files_changed`, `docs_changed`, `push_result`, `remote_url`, `audit_passed`, `docs_only_commit`
- Exit codes: 0 = passed, 1 = check failed, 2 = git error

---

## 2026-06-27 — DEVELOP — M8-028 (Iterative click-to-center loop; REQ-CLICK-004)

**Iterative centering loop: capture → refine → compute move → issue move → repeat until centred or max_iterations.**
- `smart_telescope/config.py`: 6 new `CTC_*` settings from `[click_to_center]` section
- `templates/config.toml`: `[click_to_center]` section with defaults + OPEN-002 comment
- `smart_telescope/services/ctc_loop_service.py`: `run_centering_loop()` — per-iteration camera capture, click refinement, pixel-to-angular conversion with rotation + max_px clamp + fraction; `mount.move()` for RA and DEC; cancellation via `threading.Event`; `CTCIterationLog.to_json_line()`; `CTCLoopResult.to_dict()`; `_pixel_offset_to_move()` helper
- `smart_telescope/api/click_to_center.py`: `POST /center` (synchronous, blocking until done/cancelled); `POST /cancel` (sets global Event)
- Tests: 14 service tests in `tests/unit/services/test_ctc_loop_service.py`; full suite: 3710 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-027 (Click-to-center calibration gate; REQ-CLICK-003)

**Missing or expired calibration hard-blocks click-to-center. File-backed store keyed per optical-train × binning.**
- `smart_telescope/domain/ctc_calibration.py`: `CTCCalibration` dataclass — fields: `arcsec_per_px_x/y`, `rotation_deg`, `optical_train`, `binning`, `measured_at`, `max_age_hours`; `is_valid()` (checks age), `age_hours()`, `to_dict()`/`from_dict()`; key = `"optical_train:binning"`
- `smart_telescope/services/ctc_calibration_store.py`: JSON file store at `~/.SmartTScope/ctc_calibration.json`; thread-safe; `get()`, `put()`, `delete()`, `all()`
- `smart_telescope/api/deps.py`: `get_ctc_calibration_store()` singleton
- `smart_telescope/api/click_to_center.py`: readiness updated — gate checked first, then calibration checked (missing → `required_action="run_ctc_calibration"`); `GET /calibration`, `POST /calibration`, `DELETE /calibration` endpoints
- `smart_telescope/static/js/click_to_center.js`: `ctcRefreshCalibrationStatus()` helper for per-stage calibration banners
- Tests: 9 domain + 9 store + 12 API; 3696 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-026 (Click refinement; REQ-CLICK-002)

**Star centroid and ring-center refinement on last preview frame; raw fallback when no feature found.**
- `smart_telescope/domain/click_refinement.py`: `refine_click(pixels, x, y, mode, search_radius)` → `RefinedClick`; two modes: `star_centroid` (tight threshold) and `ring_center` (low threshold for ring breadth); robust background via 25th-percentile + sub-median std; `RefinedClick.to_dict()` + `to_json_line()`
- `smart_telescope/api/preview.py`: `_last_preview_pixels` dict (keyed by camera_index) populated after each capture; `get_last_preview_pixels(idx)` accessor for refine endpoint
- `smart_telescope/api/click_to_center.py`: `POST /api/click_to_center/refine` — reads cached frame; applies refinement; returns `{raw_x/y, refined_x/y, method, confidence, fallback, fallback_reason}`
- `smart_telescope/static/js/click_to_center.js`: updated `ctcHandlePreviewClick()` calls refine endpoint, draws green marker at refined position or amber for fallback, shows centroid method + confidence in banner
- Tests: 15 domain tests in `tests/unit/domain/test_click_refinement.py`; 9 API tests in `tests/unit/api/test_click_to_center_refine.py`; full suite: 3666 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-025 (Click-to-center UI entry point; REQ-CLICK-001)

**Click handlers on three preview frames. Gate readiness shown inline; exact reason displayed when unavailable.**
- `smart_telescope/api/click_to_center.py`: `GET /api/click_to_center/readiness` — evaluates `click_to_center` OperationGate; returns `{allowed, reason, required_action}`
- `smart_telescope/app.py`: registered `click_to_center_router`
- `smart_telescope/static/index.html`: `onclick="ctcHandlePreviewClick(event,'...')"` + `cursor:crosshair` on `s3-preview-frame`, `s4-preview-frame`, `s4-donut-preview-frame`; CTC banners (`s3-ctc-banner`, `s4-ctc-banner`, `s4-donut-ctc-banner`) below each frame; `click_to_center.js` script tag added
- `smart_telescope/static/js/click_to_center.js`: `ctcHandlePreviewClick()` — checks readiness, places amber circle+crosshair marker, shows banner (error or confirmed pixel); `ctcGetLastClick()` for M8-026/028; `ctcClearBanner()`
- Tests: 12 unit tests in `tests/unit/api/test_click_to_center_readiness.py`

---

## 2026-06-27 — DEVELOP — M8-024 (Collimation modes UI; REQ-UI-002..003)

**Two collimation modes (Bahtinov Preview + Defocus Donut) visible in Stage 4 with per-mode availability.**
- `smart_telescope/api/collimation.py`: `GET /api/collimation/modes` — evaluates camera availability and OperationGate for `collimation_preview` (camera-only, always allowed), `collimation_slew_to_target`, `collimation_mount_centering`; returns two mode dicts with `preview_available`, `slew_allowed`, `centering_allowed` and human reasons
- `smart_telescope/static/index.html`: `s4-modes-card` with clickable Bahtinov Preview and Defocus Donut tiles; new `s4-donut-section` with Defocus Donut preview controls (initially hidden); Stage 4 comment corrected
- `smart_telescope/static/js/collimation.js`: `refreshCollimationModes()` fetches mode availability and updates tiles; `selectCollimationMode()` shows/hides sections; `s4DonutPreviewStart()` preview launcher
- `smart_telescope/static/js/app.js`: `goToStage(4)` now calls `refreshCollimationModes()`
- Tests: 11 unit tests in `tests/unit/api/test_collimation_modes.py`; full suite: 3630 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-023 (Exposure capability test; REQ-AG-003..004)

**5-step exposure sweep with 13-field per-step diagnostics. Advisory only — no config writes.**
- `smart_telescope/domain/exposure_capability.py` (new): `TEST_EXPOSURES_S=(0.5,1,2,4,8)`, `ExposureStepDiagnostics` (14 fields: 13 diagnostics + exposure_s), `ExposureCapabilityResult` (steps, recommended_exposure_s, stopped_early, stop_reason)
- `smart_telescope/services/exposure_capability_service.py` (new): `run_exposure_test()` — sweeps exposures; `_analyse_step()` computes star count (scipy), background median/stddev, saturation, black-clipping, FWHM, HFR; stops early on saturation (>1%) or blur (elongation ratio >2.0 AND grew >50%); cancellation_flag support
- `smart_telescope/api/autogain.py`: `POST /api/autogain/exposure_test` — async endpoint (up to ~40 s); returns `ExposureCapabilityResult.to_dict()`; logs `diagnostic_exposure_test_started` user action
- Tests: 17 unit tests in `tests/unit/services/test_exposure_capability_service.py`; full suite: 3619 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-022 (Auto-gain 6 purpose modes; REQ-AG-001..002)

**6 purpose modes for auto-gain with PLATE_SOLVE tracking-quality gate.**
- `smart_telescope/domain/autogain.py`: `AutoGainMode` extended to 9 values — purpose modes: `PLATE_SOLVE`, `DSO`, `PLANET`, `MOON`, `COLLIMATION`, `AUTOFOCUS`; legacy aliases: `PLANETARY`, `LUNAR`, `GUIDING` retained. `_HCG_MODES`/`_PLANET_MODES` sets for mode classification. `measure_elongation_ratio()` — gradient-anisotropy ratio metric (round stars ≈1.0, horizontal trailing >2.0, uniform frame returns 1.0). `_select_conversion_gain()` updated.
- `smart_telescope/domain/autogain_service.py`: `PLATE_SOLVE` mode forces `cur_offset=0`; per-frame elongation check caps exposure and returns `OK` with warning when ratio >2.0 AND grew >50% vs previous frame. `PLANET`/`MOON`/`PLANETARY`/`LUNAR` routed to planetary signal metric. `COLLIMATION`/`AUTOFOCUS` use DSO behavior.
- Tests: 18 unit tests in `tests/unit/domain/test_autogain_modes.py`; full suite: 3602 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-021 (ASTAP logging → structured diagnostics; REQ-PS-002..003)

**Structured ASTAP diagnostic record attached to every solve attempt.**
- `smart_telescope/domain/astap_diagnostic.py` (new): `AstapSolveRecord` (13 fields: fits_path, command, exit_code, stdout, stderr, duration_ms, star_count, min_stars_threshold, star_count_gate_passed, solve_success, ra_hours, dec_deg, error) with `to_dict()`/`to_json_line()`
- `smart_telescope/ports/solver.py`: `SolveResult.diagnostics: AstapSolveRecord | None` added (default None, backward-compatible)
- `smart_telescope/adapters/astap/solver.py`: `AstapSolver.solve()` builds and attaches `AstapSolveRecord` on success/timeout/launch-failure/no-ini; accepts `star_count`, `min_stars`, `allow_below_min_stars`; emits `ASTAP_DIAGNOSTIC` JSON-line to `_log`
- `smart_telescope/api/solver.py`: logs `result.diagnostics` to `plate_solve` section logger after solve
- `smart_telescope/config.py`: `MIN_DETECTED_STARS_BEFORE_SOLVE=15`, `ALLOW_ASTAP_BELOW_MIN_STAR_COUNT=True`
- `templates/config.toml`: `[plate_solve]` section with both thresholds
- Tests: 13 unit tests in `tests/unit/adapters/test_astap_diagnostic.py`; full suite: 3584 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-020 (Plate-solve readiness pre-check; REQ-PS-001)

**8-condition plate-solve readiness pre-check with per-condition failure reasons.**
- `smart_telescope/domain/plate_solve_readiness.py` (new): `READINESS_CONDITIONS` tuple (8 names), `ReadinessCondition` dataclass, `PlateSolveReadinessResult` with `first_failure` property, `to_dict()`, `to_json_line()`
- `smart_telescope/services/plate_solve_readiness.py` (new): `check_plate_solve_readiness()` — evaluates all 8 conditions in order (frame_exists, frame_saved_as_fits, optical_train_metadata_available, pixel_size_available, focal_length_or_hint_available, star_count_measured, astap_available, operation_gate_allows_plate_solve); logs JSON-line to `plate_solve` section logger
- `smart_telescope/api/solver.py`: `GET /api/solver/readiness` — static query (no live frame) for UI/tool polling; resolves optical train from registry if available
- Tests: 20 unit tests in `tests/unit/services/test_plate_solve_readiness.py`; full suite: 3571 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-019 (Per-camera diagnostic report; REQ-SETUP-001..002)

**Extended setup check — 19-field per-camera diagnostic with 10-status progression.**
- `smart_telescope/domain/camera_diagnostic.py` (new): `CameraDiagnosticStatus` enum (10 values: not_attempted/disconnected/inactive/operation_blocked/capture_failed/auto_gain_failed/insufficient_stars/metadata_missing/astap_failed/solved) + `CameraDiagnosticReport` dataclass (19 fields) + `to_dict()`/`to_json_line()`
- `smart_telescope/services/setup_check_service.py`: added `run_camera_diagnostic()` — iterates optical train registry; status progression: disconnected→operation_blocked→capture_failed→insufficient_stars→metadata_missing→astap_failed→solved; `_analyse_frame()` uses scipy.ndimage.label for star counting (numpy fallback); `MIN_STARS_BEFORE_SOLVE = 15`
- `smart_telescope/api/setup_check.py`: `POST /api/setup/camera_diagnostic` — returns `{cameras: [...], total, solved}`
- Tests: 17 unit tests in `tests/unit/services/test_camera_diagnostic.py`; suite: 3551 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-017 + M8-018 (FITS diagnostic frame storage; REQ-FRAME-001..003)

**FITS diagnostic frame storage with standardized filename pattern and 17 required headers.**
- `smart_telescope/domain/diagnostic_frame.py` (new): `DiagnosticStoreMode` enum (always/debug_only/failure_only/debug_or_failure/off), `DiagnosticFrameConfig`, `REQUIRED_FITS_HEADERS` (17 keys)
- `smart_telescope/services/diagnostic_frame_store.py` (new): `DiagnosticFrameStore` — `should_save(is_debug, is_failure)`, `save_frame()` creates `{frame_dir}/{session_id[:8]}/` + FITS with all 17 headers, `cleanup_old_frames(active_session_ids)` respects retention_days and active sessions; `_make_filename()` generates filesystem-safe YYYYMMDDTHHMMSS pattern
- `smart_telescope/config.py`: `DIAGNOSTIC_FRAMES_ENABLED/STORE_MODE/RETENTION_DAYS/DIR` from `[diagnostic_frames]` TOML + env vars
- `templates/config.toml`: `[diagnostic_frames]` section with defaults
- `smart_telescope/runtime.py` + `api/deps.py`: `diagnostic_frame_store` on runtime; `get_diagnostic_frame_store()` injector
- Tests: 33 unit tests in `tests/unit/services/test_diagnostic_frame_store.py`; suite: 3534 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-016 (User-action log — 18 named actions; REQ-LOG-003)

**Structured user-action log for all 18 named UI interactions.**
- `smart_telescope/domain/user_action_log.py` (new): `USER_ACTIONS` 18-name tuple + `UserActionRecord` (action, timestamp, result, gate_reason); `to_json_line()`
- `smart_telescope/services/user_action_logger.py` (new): `UserActionLogger` with `_ACTION_SECTIONS` mapping; `log(action, result, gate_reason)` writes JSON line to the right section logger
- `smart_telescope/runtime.py` + `api/deps.py`: `user_action_logger` constructed on init + in `reset_for_tests()`; `get_user_action_logger()` injector
- Wired into 9 existing endpoints: `session_connect`, `mount_track` (track_requested/rejected), `mount_goto` (goto_requested/rejected/bright_star), `mount_sync_clock` (push_confirmed/rejected), `mount_confirm_time`, `run_autogain` (diagnostic), `focuser_autofocus`, `collimation_start`, `solver_solve`
- Tests: 17 unit tests in `tests/unit/services/test_user_action_logger.py`; suite: 3501 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-015 (Service-call logs per iteration; REQ-LOG-002)

**Structured per-iteration logging for auto-gain, plate-solve, and autofocus.**
- `smart_telescope/domain/service_call_log.py` (new): `ServiceCallRecord` dataclass — 11 required fields; `to_json_line()` serializes to one JSON line per call
- `smart_telescope/services/service_call_logger.py` (new): `ServiceCallLogger` + `_CallContext` context manager; status priority: `_explicit_error` → failed; `_cancelled` → cancelled; `exc_val` → failed; else → ok; `set_error()` for caught exceptions that exit early; `set_response()` for success; emits JSON line to section logger on `__exit__`
- `smart_telescope/api/autogain.py`: `_worker()` now wraps `AutoGainService.run_one_shot()` in `rt.service_call_logger.call("auto_gain", ...)` context manager; `set_error()` on caught exception, `set_response()` on success
- `smart_telescope/workflow/stages.py`: `StageContext` dataclass gains `service_call_logger: "ServiceCallLogger | None" = None`; `stage_align()`, `stage_recenter()`, `stage_autofocus()` each wrap their primary service call when logger is present
- `smart_telescope/workflow/runner.py`: `VerticalSliceRunner.__init__()` gains `service_call_logger=None` kwarg; stored and passed to `StageContext`
- `smart_telescope/api/session.py`: `session_run()` passes `service_call_logger=deps.get_service_call_logger()` to runner
- `smart_telescope/runtime.py` + `api/deps.py`: `ServiceCallLogger` constructed in `__init__` and `reset_for_tests()`; `get_service_call_logger()` injector
- Tests: 15 unit tests in `tests/unit/services/test_service_call_logger.py`; suite: 3484 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-014 (12 per-section log namespaces; REQ-LOG-001)

**Per-section log namespaces with session ID correlation.**
- `smart_telescope/services/section_logger.py` (new): `SectionLogger(session_id, log_dir)` — 12 named sections (startup, stage1_time_location, mount, camera, auto_gain, autofocus, collimation, plate_solve, goto, click_to_center, extended_setup_check, github_delivery); each section gets its own `Logger` under `smart_telescope.section.<name>` with `propagate=True`; optional `FileHandler` per section to `{log_dir}/{session_id[:8]}/{section}.log`; `_SectionAdapter` injects `session_id` and `section` into every log record; `get(section)` returns adapter, `get_paths()` returns `{section: path_or_None}`, `close()` removes file handlers
- `smart_telescope/api/logs.py` (new): `GET /api/logs` returns `{"logs": {section: path_or_null}}` for all 12 sections; depends on `SectionLogger` via `deps.get_section_logger()`
- `smart_telescope/config.py`: `LOG_DIR` from `[session].log_dir` (default `~/.SmartTScope/logs/`; env-var `LOG_DIR`)
- `templates/config.toml`: added `log_dir = ""` to `[session]` section
- `smart_telescope/runtime.py`: `self.section_logger = SectionLogger(session_id=self._app_session_id, log_dir=config.LOG_DIR)` in `__init__`; `SectionLogger(session_id=self._app_session_id)` (no log_dir) in `reset_for_tests()`; `self.section_logger.close()` in `shutdown()`
- `smart_telescope/api/deps.py`: added `get_section_logger() -> SectionLogger`
- `smart_telescope/app.py`: registered `logs_router`
- Tests: 14 `test_section_logger.py` (section names, paths, adapters, file creation, close) + 5 `test_logs.py`; suite: 3489 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-012 + M8-013 (Command history API + GoTo wiring; REQ-API-003, REQ-GOTO-001..003, INC-005)

**M8-012: `GET /api/commands` + UI panel**
- `smart_telescope/api/commands.py` (new): returns `CommandHistoryService.get_all()` as `{"commands": [...]}`
- `smart_telescope/app.py`: registered `commands_router`
- `smart_telescope/static/index.html`: "Command History" card at bottom of Stage 1 (last 50 cmds, scrollable, color-coded)
- `smart_telescope/static/js/setup.js`: `refreshCommandHistory()` + `_renderCommandHistory()` with status color map
- `smart_telescope/static/js/app.js`: initial call + 10 s interval

**M8-013: GoTo history recording + operation policy**
- `smart_telescope/api/mount.py`: `mount_goto` wires `CommandHistoryService` — REQUESTED → REJECTED (gate/solar/limit)/ISSUED → SUCCEEDED/FAILED; adds `?bright_star=true` param → `bright_star_goto` gate operation
- `smart_telescope/services/operation_gate.py`: `_evaluate_one` for `goto` op honors `allow_direct_radec_without_trust` flag; `gate_inputs_from_device_state()` reads config and includes the flag
- `smart_telescope/config.py`: `ALLOW_DIRECT_RADEC_GOTO_WITHOUT_RASPBERRY_TIME_TRUST = False` (env + TOML `[operation_policy]`)
- `templates/config.toml`: added `[operation_policy]` section with stub
- Tests: 6 `test_commands.py` + 5 `test_mount.py::TestGotoCommandHistory` + 4 `test_operation_gate.py::TestDirectRadecGotoPolicy`; 3470 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-011 (CommandHistoryService; REQ-CMD-001)

**Per-session JSONL command audit log.**
- `smart_telescope/domain/command_status.py` (new): `CommandStatus` enum — REQUESTED / REJECTED / ISSUED / RUNNING / SUCCEEDED / FAILED / CANCELLED
- `smart_telescope/services/command_history.py` (new): `CommandRecord` dataclass (12 REQ-CMD-001 fields) + `CommandHistoryService`; thread-safe `threading.Lock`; append-only JSONL (one line per `record()`/`update()` call); in-memory `dict[command_id, CommandRecord]` for query
- `smart_telescope/config.py`: `COMMAND_HISTORY_DIR` (default `~/.SmartTScope/commands/`; env-var + TOML `[session].command_history_dir`)
- `templates/config.toml`: added `command_history_dir = ""` stub to `[session]`
- `smart_telescope/runtime.py`: generates `_app_session_id` UUID per `RuntimeContext.__init__`; creates `self.command_history = CommandHistoryService(session_id, path)`; `reset_for_tests()` creates a no-file instance
- `smart_telescope/api/deps.py`: `get_command_history_service()`
- 19 new tests in `tests/unit/services/test_command_history.py`: record lifecycle, update, get_all, JSONL content, thread safety; 3435 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-010 (Stage 1 time/location UI panel; REQ-TIME-005, REQ-API-004, INC-009)

**New `GET /api/stage1/time-location` endpoint and Stage 1 UI card.**
- `smart_telescope/api/stage1.py` (new): returns 20-field consolidated time/location trust state; reads exclusively from DeviceStateService cache (no serial I/O)
- `smart_telescope/services/device_state.py`: 3 new fields (`_last_sync_status`, `_last_verification_at`, `_last_push_at`) + 5 accessors; `set_time_location_status(VERIFIED)` now records wall-clock `_last_verification_at`
- `smart_telescope/adapters/onstep/mount.py`: `get_sync_status()` extended with `onstep_time_local` and `master_time_local` ISO strings
- `smart_telescope/api/session.py`: caches `mount.get_sync_status()` result into `device_state.set_last_sync_status()` on connect
- `smart_telescope/api/mount.py`: `sync_clock` calls `device_state.set_last_push_at()` on success; new `POST /api/mount/confirm_time` sets USER_CONFIRMED trust
- `smart_telescope/app.py`: registered `stage1_router`
- `smart_telescope/static/index.html`: Stage 1 "Time / Location Verification" card (dot, badge, 20 param rows, 3 action buttons)
- `smart_telescope/static/js/setup.js`: `refreshStage1TL()`, `_renderStage1TL()`, `stage1PushClock()`, `stage1ConfirmTime()`
- `smart_telescope/static/js/app.js`: initial call + 15 s interval for `refreshStage1TL()`
- 25 new tests: `tests/unit/api/test_stage1.py` (19), `test_mount.py::TestMountConfirmTime` (2), `test_raspberry_time_trust.py` M8-010 block (4); 3416 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-009 (Trust session expiry; no cross-restart persistence)

**DEC-004, DEC-005 implemented.**
- `config.py`: `SESSION_TRUST_EXPIRY_MINUTES` read from `[time_location]` section (env override: `SESSION_TRUST_EXPIRY_MINUTES`); default 120
- `runtime.py`: added `from . import config`; both `__init__` and `reset_for_tests()` pass `session_trust_expiry_minutes=config.SESSION_TRUST_EXPIRY_MINUTES` to `RaspberryTimeTrustService`
- `templates/config.toml`: activated `[time_location]` section with `session_trust_expiry_minutes = 120` and `persist_trust_across_restart = false`
- 5 new M8-009 tests in `tests/unit/services/test_raspberry_time_trust.py`: fresh-service-no-trust, restart-clears-trust, custom-expiry-respected, 120-min-default, USER_CONFIRMED-expiry; 3391 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-008 (Meter-based location tolerance; UTF-8-safe logs)

**REQ-TIME-003, REQ-TIME-006 implemented. Addresses INC-002; TEST-002.**
- `adapters/onstep/safety.py`: added `onstep_time_tolerance_s: float = 10.0` and `onstep_location_tolerance_m: float = 100.0` fields to `OnStepSafetyConfig`
- `adapters/onstep/mount.py`: added `_haversine_m()` great-circle distance helper; `get_sync_status()` now uses `haversine_m` for `location_delta_m`, checks `location_delta_m <= onstep_location_tolerance_m` (replaces `lat_delta < 0.1 and lon_delta < 0.1`); uses `onstep_time_tolerance_s` for time check; adds `location_delta_m`, `location_tolerance_m`, `time_tolerance_s` to returned dict
- `api/session.py`: VERIFIED log uses `deg` not `°`; active tolerances logged in both VERIFIED and mismatch paths
- `services/readiness.py`: location issue string shows `{loc_m:.0f}m`; fallback uses `{max(lat_d,lon_d):.4f}deg`
- `config.py`: `ONSTEP_TIME_TOLERANCE_S` and `ONSTEP_LOCATION_TOLERANCE_M` read from `[mount]` section (env override supported); wired into `build_onstep_safety_config()`
- `templates/config.toml`: `[mount]` section with `onstep_time_tolerance_s = 10` and `onstep_location_tolerance_m = 100`
- 26 new tests in `tests/unit/adapters/onstep/test_get_sync_status.py`; 3386 passed, 24 skipped

---

## 2026-06-27 — DEVELOP — M8-007 (Raspberry Pi time trust sources: 5-state enum + evaluation service)

**REQ-TIME-002, REQ-TIME-004 implemented. Addresses INC-003, INC-009.**
- `domain/raspberry_time_trust.py`: `RaspberryTimeTrustSource` enum (GPSD_FIX | NTP | ONSTEP_COMPARISON | USER_CONFIRMED | NOT_TRUSTED) + module-level `is_trusted()` helper
- `services/raspberry_time_trust.py`: `RaspberryTimeTrustService` — priority chain GPSD_FIX > NTP > ONSTEP_COMPARISON > USER_CONFIRMED > NOT_TRUSTED; session expiry via monotonic timestamps; `_check_gpsd_fix()` + `_check_ntp_sync()` (silent fallback on non-Linux); DEC-006 trust chain documented in module docstring
- `services/device_state.py`: added `set_onstep_comparison_established()`, `get_onstep_comparison_established_at()`, `get_user_time_confirmed_at()` methods
- `services/operation_gate.py`: M8-007 path in `gate_inputs_from_device_state()`; isinstance guards prevent MagicMock leaking as float timestamps; M8-006 fallback when `raspberry_trust_svc=None`; gate check order: `TIME_LOCATION_UNVERIFIED` before `RASPBERRY_TIME_UNTRUSTED`
- `api/health.py`: `MountStateCategories` gains `raspberry_trust_source` field; `system_status` injects `RaspberryTimeTrustService`
- `api/mount.py`: 4 gated endpoints (`track`, `goto`, `sync`, `goto_and_center`) pass `raspberry_trust_svc`; `mount_sync_clock()` calls `device_state.set_onstep_comparison_established()` when master source is GPS_FIX or NTP
- `api/deps.py` + `runtime.py`: `get_raspberry_trust_service()` dep; `RuntimeContext.raspberry_trust_svc` singleton (reset in tests)
- 35 new tests in `tests/unit/services/test_raspberry_time_trust.py`; 3360 passed, 24 skipped

---

## 2026-06-26 — DEVELOP — M8-006 (Master time source selection: GPS > NTP > USER_CONFIRMED > FALLBACK)

**REQ-TIME-001 implemented.**
- `domain/master_time_source.py`: `MasterTimeSource` enum (GPS_FIX | NTP | USER_CONFIRMED | FALLBACK)
- `services/master_source.py`: `MasterSourceService.evaluate()` — priority chain; `_check_ntp_sync()` via `timedatectl` (silent fallback on non-Linux); FALLBACK = NOT_TRUSTED → mount automation blocked
- `services/device_state.py`: `is_user_time_confirmed()` / `set_user_time_confirmed()` flag for USER_CONFIRMED trust path
- `services/operation_gate.py`: `gate_inputs_from_device_state()` accepts optional `master_source_svc`; adds `master_time_source` to returned dict; `_evaluate_one()`, `evaluate_gate()`, `evaluate_all_gates()` accept `**_` to forward-compat extra inputs
- `api/health.py`: `MountStateCategories` gains `master_time_source` field; `system_status` injects `MasterSourceService`
- `api/mount.py` + `api/deps.py` + `runtime.py`: `MasterSourceService` wired as singleton; 4 gated endpoints pass it to `_gate_check()`
- 23 new tests; 3368 passed, 39 skipped

---

## 2026-06-26 — DEVELOP — M8-005 (Structured gate diagnostics for disabled UI controls and 409 responses)

**REQ-UI-001, REQ-GOTO-001 implemented; INC-003, INC-005 resolved.**
- `operation_gate.py`: added `gate_inputs_from_device_state()` and `evaluate_gate()` helpers
- `api/health.py`: `_build_mount_state_categories()` uses `gate_inputs_from_device_state()`; `raspberry_trust` stub changed to `TRUSTED` (M8-007 will do real trust determination)
- `api/mount.py`: replaced 4 ad-hoc TL checks with `_gate_check()` → structured HTTPException 409 (fields: `gate_blocked`, `reason_code`, `human_message`, `required_user_action`, `blocking_states`)
- `api/session.py`: `_session_thread` catches all exceptions (prevents pytest 9 `PytestUnhandledThreadExceptionWarning`)
- Frontend: `_applyGateStates()` in `app.js` disables GoTo/track/manual-move/autofocus buttons with gate `human_message` as tooltip; `setup.js` stores gate states from `/api/status`; `mount.js` shows `human_message` from gate-blocked 409s
- 11 new tests in `TestMountApiGatedResponses`; 3345 passed, 39 skipped

---

## 2026-06-26 — DEVELOP — M8-004 (Fix /api/mount/status connection fields)

**REQ-CONN-001 / REQ-CONN-002 implemented.** Added 6 new fields to `MountStatus` in `/api/mount/status`: `adapter_open` (is_started()), `health_check_ok` (None/True/False), `connected` (adapter_open AND health_ok), `park_state` (PARKED|UNPARKED|UNKNOWN), `tracking_state` (TRACKING|NOT_TRACKING|UNKNOWN), `last_error`. Made `POST /api/session/connect` idempotent: skips mount.connect() when DeviceStateService.is_started() is True, returning status="ok" without calling into managed.py again (avoids SYNC-OVERRIDE False-return contradiction). 22 new unit tests.

---

## 2026-06-26 — DEVELOP — M8-003 (OperationGateService — 13 gated operations)

**REQ-STATE-003 implemented.** `evaluate_all_gates()` in `smart_telescope/services/operation_gate.py` evaluates all 13 gated operations from the current system state strings. Gate result includes `allowed`, `reason_code`, `human_message`, `required_user_action`, `blocking_states`. `operation_gate_states` field in `/api/status → mount_states` now returns the full gate map (was stub `{}`). Priority ordering: ADAPTER_DISCONNECTED > ADAPTER_HEALTH_FAILED > ADAPTER_HEALTH_UNKNOWN > TIME_LOCATION_UNVERIFIED > RASPBERRY_TIME_UNTRUSTED > MOUNT_PARKED. Camera-only operations (camera_capture, plate_solve, collimation_preview) always allowed per DEC-009. 59 new unit tests in `tests/unit/services/test_operation_gate.py`, 106 total passing.

---

## 2026-06-26 — DEVELOP — M8-002 (MountReadinessState enum + derive function)

**REQ-STATE-002 implemented.** `mount_readiness` derived composite state added to `/api/status → mount_states`.

**New file:** `smart_telescope/domain/mount_readiness.py`
- `MountReadinessState` enum (7 values)
- `derive_mount_readiness(adapter_connection, adapter_health, onstep_time_location, raspberry_time_trust) → MountReadinessState` — pure function, priority chain top-to-bottom

**Priority chain:** DISCONNECTED > ERROR > CONNECTED_HEALTH_UNKNOWN > CONNECTED_RESTRICTED (Stage 1 not run) > CONNECTED_TIME_LOCATION_UNVERIFIED > CONNECTED_RASPBERRY_TIME_UNTRUSTED > CONNECTED_READY

**INC-001 fix:** adapter open but Stage 1 not run → CONNECTED_RESTRICTED, not DISCONNECTED. Reconnect guidance only for DISCONNECTED/ERROR.

**Tests:** 9 domain tests (`test_mount_readiness.py`) + 6 API tests; exit 0 full suite.

---

## 2026-06-26 — DEVELOP — M8-001 (6 mount state categories in /api/status)

**REQ-STATE-001 implemented.** `/api/status` now exposes `mount_states` with all six separate state categories required by INC-001.

**Code changes:**
- `smart_telescope/services/device_state.py` — added `is_started() -> bool` (polling thread alive check)
- `smart_telescope/api/health.py` — added `MountStateCategories` Pydantic model; `_build_mount_state_categories(device_state)` helper; `device_state` dependency on `GET /api/status`

**New fields in `/api/status` → `mount_states`:**
- `adapter_connection_state`: OPEN (polling started) | CLOSED
- `adapter_health_state`: OK (no poll error) | FAILED (poll error) | UNKNOWN (no poll yet)
- `mount_operational_state`: mirrors `MountState` enum name
- `onstep_time_location_state`: from `DeviceStateService.get_time_location_status()`
- `raspberry_time_trust_state`: NOT_TRUSTED (stub; full impl M8-007)
- `operation_gate_states`: {} (stub; full impl M8-003)

**Tests:** 13 new tests in `TestMountStateCategories`; 3194 passed total.

---

## 2026-06-25 — INGEST — smarttscope_incident_requirements_final_v1_2.md v1.2

**Source:** `E:\Bilder\Astro\SmartTScopeReq\smarttscope_incident_requirements_final_v1_2.md`  
**Copied to:** `resources/hlrequirements/smarttscope_incident_requirements_final_v1_2.md`

**New milestone M8 added to `docs/todo.md`** (30 tasks, M8-001..M8-030):

- M8-001..005 (P1): Split runtime state into 6 categories; mount readiness enum (7 states); `OperationGateService` (13 gated ops); fix `/api/mount/status`; UI disabled-control reasons
- M8-006..010 (P1): Master source selection; 5 Raspberry time trust sources; meter-based location tolerance (100 m); UTF-8-safe logs; trust session expiry; Stage 1 UI panel (20 fields)
- M8-011..013 (P1): `CommandHistoryService` (JSONL, 7 statuses); `/api/commands`; GoTo gate-before-issue; bright-star preconditions
- M8-014..018 (P2): 12 per-section log namespaces; service-call logs per iteration; user-action log (18 actions); FITS diagnostic storage; FITS filename/header spec
- M8-019..023 (P2): Extended Setup Check per-camera report; plate-solve readiness pre-check; ASTAP logging; auto-gain 6 purpose modes; exposure capability test
- M8-024..028 (P2): Collimation modes (Bahtinov + Defocus Donut); click-to-center in 3 views; click refinement; calibration hard block + wizard; iterative bounded centering
- M8-029..030 (P3): `scripts/delivery_audit.py`; delivery log JSONL

**Key design decisions from grilling session:**
- Push Pi time → OnStep verified → ONSTEP_COMPARISON is intentional trust chain (clarify in code comment per DEC-006)
- REQ-AG-002 tracking quality = star elongation/FWHM from captured frames only (no plate-solve dependency)
- Click-to-center cold start = hard block + calibration wizard; no manual override
- REQ-GIT items tracked in todo.md as Priority 7

**Updated wiki pages:**
- `wiki/index.md` — new Planning entry for incident requirements v1.2

---

## 2026-06-24 — INGEST — smarttscope_additional_requirements.md v1.0

**Source:** `E:\Bilder\Astro\SmartTScopeReq\smarttscope_additional_requirements.md`

**New milestone M7 added to `docs/todo.md`** (12 tasks, M7-001..M7-012):

- M7-001/M7-002 (P0): Replace silent `ensure_time_location_synced()` auto-sync with interactive startup dialog; add `TimeLocationStatus {UNKNOWN, VERIFIED, UNVERIFIED}` as orthogonal flag in `DeviceStateService`; gate tracking/GoTo/sync on verification state
- M7-003 (P1): Lazy pixel-to-RA/DEC calibration service — controlled star displacement measurements; blocked-with-retry on failure; invalidated on optical train/binning/orientation change
- M7-004 (P1): Focuser backlash compensation — new `[focuser] backlash_steps` config key; direction-reversal overshoot in `move_relative()`
- M7-005 (P1): Common `ServiceFrame` input dataclass unifying frame metadata across all image-processing services
- M7-006 (P1): Stateful `PlateSolveService` wrapping existing `AstapSolver`; enforces auto-gain precondition before solve
- M7-007 (P1): Formalize `AutofocusService` after gap check against AF-001..AF-005
- M7-008 (P1): Add `circle_center_displacement_px` (raw pixel float) to collimation output; display in UI alongside arrow
- M7-009..M7-012 (P2): Shared image-analysis module audit; AG-003 tracking-off exposure cap; GPS fix age check; retry-limit verification

**Key design decisions recorded:**
- TimeLocationStatus is orthogonal to MountState (not merged)
- Bahtinov collimation method deferred post-MVP
- ASTAP solver wrapped, not replaced
- Collimation displacement in raw pixels

---

## 2026-06-24 — DEVELOP — M7-011 and M7-012 (GPS fix age; retry limits)

**M7-011:** `GpsdFix.fix_age_s` (computed from `gps_time` vs `datetime.now(UTC)`) + `is_fresh(max_age_minutes=60)` method; stale fix logs WARNING with suggestion to fall back to system/config; `GpsdStatusResponse` exposes `fix_age_s` and `is_fresh`; 6 new tests (18 total in suite).

**M7-012:** Gap: `PlateSolveService` had no retry cap. Added `max_retries: int = 5` parameter; `solve()` raises `PlateSolveError("retry limit reached …")` once `_retry_count >= max_retries`; `reset()` clears counter. `AutoGainService` (12 default), `AutofocusService` (20 samples), and collimation sub-services (`_max_iter`, `_max_steps`, `_max_frames`) were already bounded. Verified by 9-test audit file `test_retry_limits.py` + 2 new plate-solve tests.

---

## 2026-06-24 — DEVELOP — M7-003 through M7-010 (Formal Service Contracts & Safety Extension)

**M7-003:** `PixelCalibrationService` — lazy pixel-to-RA/DEC calibration via controlled star displacement (2 s exposures, 2 000 ms RA/DEC moves); stores `PixelCalibration` dataclass; 6 tests.

**M7-004:** Focuser backlash compensation — `FOCUSER_BACKLASH_STEPS` / `FOCUSER_BACKLASH_ENABLED` config; direction-reversal overshoot in `OnStepFocuser.move_absolute()`; 4 tests.

**M7-005:** `ServiceFrame` — common frozen dataclass unifying all image-processing service inputs; `validate()` raises `FrameValidationError` on missing mandatory fields; `from_fits_frame()` factory; 5 tests.

**M7-006:** `PlateSolveService` — stateful wrapper around `AstapSolver`; enforces auto-gain precondition (PS-001); exposes `SolveOutput` with focal-length and pixel-scale back-calculation; 6 tests.

**M7-007:** `AutofocusService` — frame-by-frame V-curve sampler; detects minimum when HFD rises on both sides; returns signed `focus_movement_steps` + pixel-space centroid offset (not RA/DEC); 6 tests.

**M7-008:** Collimation `circle_center_displacement_px` — alias for `error_magnitude_px` (Euclidean inner/outer center distance in pixels) added to `DonutOverlay`, assistant history, live output, and replay endpoint; 2 new tests (27 total in suite).

**M7-009:** `smart_telescope/services/image_analysis.py` — unified `analyze_frame()` returning `ImageAnalysisResult`; classifies uniform/no-signal frames as `FocusQualityLevel.UNKNOWN` via peak-vs-background check; 6 tests.

**M7-010:** AG-003 tracking-off exposure cap — added `tracking_on: bool = True` to `AutoGainService.run_one_shot()`; caps `exp_max_ms = min(exp_max_ms, 1000.0)` when False; API worker reads `MountState.TRACKING` and wires flag; 2 tests.

---

## 2026-06-24 — FIX — Pixel scale wrong for C8 + ATR585M; ASTAP failure logging (4 files)

**Root cause:** Pixel scale defaults assumed a different camera (~3.75 µm pixels) rather than ATR585M (2.9 µm). ASTAP only searches ±10% of the given scale, so 0.38 "/px ± 10% never covers the actual 0.295 "/px → `PLATESOLVED=F` on every solve attempt.

**Correct pixel scales for ATR585M (2.9 µm) on C8:**
- Native (2032 mm): 206.265 × 2.9 / 2032 = **0.295 "/px**
- 0.63× reducer (1280 mm): **0.468 "/px**
- 2× Barlow (4064 mm): **0.147 "/px**

**Changes:**
- `smart_telescope/workflow/_types.py`: C8_NATIVE 0.38 → 0.295, C8_REDUCER 0.60 → 0.468, C8_BARLOW2X 0.19 → 0.147
- `smart_telescope/config.py`: default `pixel_scale_arcsec` 0.38 → 0.295
- `smart_telescope/adapters/astap/solver.py`: log scale + radius before each solve; on PLATESOLVED=F log full ASTAP stdout, stderr, and .ini content for diagnosis
- `tests/unit/workflow/test_runner_stages.py`: updated pixel scale expectations to match corrected values

**Tests:** 3052/3053 pass (1 pre-existing skip); 12/12 for the directly affected tests.

---

## 2026-06-23 — FIX — Auto-gain overshoot and plate-solve 422 (4 files)

**Root cause:** ToupTek SDK `get_ExpoAGain()` returns the raw hardware AGC register, which can be stale from a previous session. This value was echoed back to the UI via `camera_info.effective_gain`, overwriting the intended gain in `preview-gain`. `previewSendParams()` then re-applied that stale value to the camera, causing subsequent solve requests to send e.g. gain=7001 which failed the `le=3200` validation with HTTP 422.

**Changes:**
- `smart_telescope/static/js/preview.js`: Removed the code that writes `camera_info.effective_gain` back into the `preview-gain` UI field. Hardware readback is unreliable for gain on ToupTek cameras; the intended gain is already set in the field.
- `smart_telescope/static/js/session.js`: Clamp gain to [100, 3200] before sending to `/api/solver/solve` as a safety net.
- `smart_telescope/domain/autogain_service.py`: Added sparse star field early exit: if `p99_9 ≥ 0.10` and no saturation risk, accept the frame rather than over-brightening until mean_frac reaches the target band. Prevents overshooting to 4 s/high gain when stars are already visible.
- `smart_telescope/domain/autogain.py`: Same sparse field guard in `AutoGainController.update()` used by the preview WebSocket autogain.

**Tests:** 99/99 pass.

---

## 2026-06-23 — FIX — Auto-sync OnStep time/location on Connect All and GPS apply (4 files)

**Changes:**
- `smart_telescope/api/session.py`: `session_connect()` now calls `mount.ensure_time_location_synced()` automatically after a successful mount connect. Failure is best-effort (logged, does not fail the Connect All response).
- `smart_telescope/adapters/onstep/mount.py`: `ensure_time_location_synced()` now reads `config.OBSERVER_LAT/LON` at call time (local import, same pattern as `_default_safety_config()`) instead of the stale `_safety_config` built at adapter-construction time. This ensures GPS-updated coordinates flow to OnStep without reconnecting.
- `smart_telescope/static/js/setup.js`: `applyGpsLocation()` now calls `POST /api/mount/sync_clock` after the observer location update (best-effort) so the GPS fix is immediately pushed into OnStep.
- `tests/unit/api/test_session.py`: 4 new tests — auto-sync on success, skipped on mount failure, sync exception doesn't fail connect, skip-when-exception variation.

**Root cause:** `session_connect()` connected the mount but never synced time/location, requiring a manual GoTo or button press to initialize the OnStep clock. The stale `_safety_config` also meant GPS updates weren't reaching OnStep.

---

## 2026-06-23 — FIX — Sync Clock button and API for onstep_clock_invalid (4 files)

**Changes:**
- `smart_telescope/api/mount.py`: `POST /api/mount/sync_clock` — pushes Pi time + configured lat/lon into OnStep (same as the auto-sync before every GoTo); clears `onstep_clock_invalid` safety lock on success. HTTP 500 with detail string on failure.
- `smart_telescope/static/js/mount.js`: Replaced dead "Click **Sync Clock** in the Setup panel" instruction with an actual inline `Sync Clock & Location` button that calls the new endpoint, shows "✓ Synced" / "✗ Failed", and refreshes the mount card.
- `smart_telescope/services/readiness.py`: Fixed misleading repair hint on `time_location_sync` RED item — Connect All does NOT trigger a time sync; updated to "Click 'Sync Clock & Location' in the mount card, or run a GoTo."
- `tests/unit/api/test_mount.py`: 3 new tests in `TestMountSyncClock` (200+ok, calls ensure_time_location_synced, 500 on RuntimeError).

**Root cause:** `onstep_clock_invalid` safety lock had no user-facing action. UI referenced a "Sync Clock" button that was never implemented. The auto-sync only fires inside `safe_goto()` and `track_sequence()` — not after Connect All — leaving users unable to clear an uninitialized OnStep RTC without issuing a GoTo first.

---

## 2026-06-23 — FIX — Pi config: removed duplicate [collimation.archive] section (Pi-side only)

**Change:** Duplicate `[collimation.archive]` table in `~/.SmartTScope/config.toml` on the Pi removed manually. The TOML parse error (line 246) caused the entire config to fail, falling back to `lat=0.0, lon=0.0`, which in turn caused the "Mount time/location" readiness item to show RED after Connect All. Removing the duplicate restores correct config parsing.

**Root cause:** The `[collimation.archive]` section was present twice — once inline under `[collimation]` and once as a standalone table added during an earlier config edit. TOML forbids duplicate table headers.

**Status:** Closed. No code change needed; config template (`templates/config.toml`) was already correct.

---

## 2026-06-23 — DOC — Operational acceptance checklist: UI naming and pre/post-connect steps (1 file)

**Changes:**
- `docs/operational-acceptance-checklist.md`: Split old §2 "Connect all devices" into three sections — new §2 (pre-connect System Readiness baseline), §3 (Connect All), §4 (post-connect System Readiness with time/location row). Fixed terminology: "System Readiness card" in Stage 1 (Startup tab) is always visible, not something to "open". Documented that the "Mount time/location" row is absent before connecting and explains GREEN/YELLOW/RED meanings. Renumbered §4–§10 → §5–§11.

**Motivation:** Hardware test R5-012 revealed the checklist used "open System Readiness Card" (implying a modal) and gave no pre/post-connect expectations for the time/location row.

---

## 2026-06-21 — CHORE — Coverage gate resolved at 80.01% (11 files)

**Changes:**
- `pyproject.toml`: Added `[tool.coverage.run] omit` for hardware-only files: `__main__.py`, `tools/*`, `adapters/touptek/managed.py`, `filter_wheel.py`, `camera.py` (all require ToupTek SDK DLL at runtime).
- New test files: `test_event_log.py`, `test_guide_monitor_api.py`, `test_gpsd_service.py`, `test_firmware_proof.py`, `test_serial_bus.py`, `test_mock_camera.py`, `test_onstep_focuser.py`.
- Extended: `test_visibility.py` (HorizonProfile, load_horizon, compute_ha), `test_guide_monitor.py` (lifecycle: start/stop/running/last_result/exception path), `test_cooling_service.py` (exception paths: TEC setup failure, disable failure, sensor exceptions).

**Result:** 80.01% coverage, 3103 passed, 24 skipped. Coverage gate (`--cov-fail-under=80`) now green.

---

## 2026-06-21 — FEAT — R5-012: Mount time/location sync in readiness card (4 files)

**Changes:**
- `smart_telescope/ports/mount.py`: `get_sync_status() -> dict | None` added as default no-op.
- `smart_telescope/adapters/onstep/mount.py`: `OnStepMount.get_sync_status()` implemented — calls `read_onstep_clock()` (`:GC#`/`:GL#`) and `read_onstep_site()` (`:Gt#`/`:Gg#`), compares OnStep values against Pi system time and `_safety_config.observer_lat/lon`; location threshold 0.1°.
- `smart_telescope/services/readiness.py`: `_check_time_location_sync()` added — returns `time_location_sync` `ReadinessItem` (GREEN/YELLOW/RED); skipped (returns `None`) when mount is not connected or adapter doesn't support sync status; wired into `check()` after mount/focuser check.
- `tests/unit/api/test_readiness.py`: 8 new tests in `TestTimeLLocationSyncCheck` covering all level transitions and None cases.

**Logic:** GREEN = both time and location within thresholds. YELLOW = mount not responding to queries. RED = clock off by > threshold_s OR site off by > 0.1°. Repair hint reminds user that GoTo auto-syncs before every slew.

---

## 2026-06-21 — CHORE — ONS3 upgrade complete; 4 pre-existing test failures fixed (5 files)

**Changes:**
- `smart_telescope/domain/collimation/config.py`: `ArchiveConfig.enabled` default corrected from `True` to `False` — matches `templates/config.toml` template; was causing `_get_archive()` to create an archive in test environments.
- `tests/unit/api/test_catalog.py`: patch `compute_ha` to `0.0` in `_get_stars()` helper — prevents time-dependent HA limit filtering from removing test stars.
- `tests/unit/api/test_mount.py` (`TestMountPark`): add `json={"confirmed": True}` to all park POST calls — endpoint added confirmation guard after these tests were written.
- `tests/unit/services/test_star_selector.py`: patch `compute_ha` alongside `compute_altaz` in every test that checks star selection — same time-dependent HA issue as catalog test.
- `tests/unit/domain/test_stretch.py`: `test_linear_range_maps_correctly` — removed `flat[-1] == 255` assertion; sigma-stretch does not guarantee max value maps to 255 (only percentile-stretch does).
- `docs/todo.md`: ONS3-002..006 marked complete.

**ONS3 architecture note:** `onstep_adapter` v0.3.0 is a re-export shim — its `__init__.py` imports everything from `smart_telescope.adapters.onstep.*`. All REQ-ST-001..007 overrides in `mount.py` are therefore permanent (no upstream independent implementation exists).

**Test result:** 2942 passed, 24 skipped.

---

## 2026-06-21 — FIX — Tracking not active after goto; solve failure visibility (3 files)

**Changes:**
- `smart_telescope/static/js/mount.js`: after `watchSlew()` confirms slew complete, auto-enable tracking via `/api/mount/track` if mount state is not already `tracking`.
- `smart_telescope/services/collimation/assistant.py`: `_handle_acquire_star()` now waits up to 90 s for any in-progress slew to finish, then enables tracking if needed — prevents star trailing in MEASURE_DONUT/FINE_FOCUS/MEASURE_SPIKES.
- `smart_telescope/static/js/session.js`: solve failure/error message now also shown in the `solve-result` div (next to the Solve button), not only in the status banner at the top of the stage.

**Storage locations confirmed (no code change):**
- Session/alignment logs: `~/.SmartTScope/sessions/` (empty if no imaging session completed yet)
- Collimation frame archive: `~/.SmartTScope/frame_archive/<session_id>/` (archiving must be enabled via `[collimation.archive] enabled = true` in config.toml)
- Collimation report and polar alignment state: in-memory only, not persisted
- Plate solve frames and results: not persisted (temp dir deleted after ASTAP runs)

---

## 2026-06-20 — FEAT — GPSD connector, Bathinov preview fix, storage paths (8 files)

**Changes:**

- `smart_telescope/services/gpsd_service.py` (NEW): One-shot TCP client for the GPSD JSON protocol (port 2947). Sends `?WATCH+?POLL`, waits for first `TPV` class response (5 s timeout), returns `GpsdFix(lat, lon, alt, gps_time, mode, hdop)` or `None` when GPSD is unavailable. `haversine_m(lat1, lon1, lat2, lon2)` computes great-circle distance in metres.
- `smart_telescope/api/gpsd.py` (NEW): `GET /api/gpsd/status` queries GPSD and returns fix mode, coordinates, distance from configured observer position. `POST /api/observer/location` updates `config.OBSERVER_LAT`/`OBSERVER_LON` in memory and patches `~/.SmartTScope/config.toml` `[observer]` section via regex replacement (no external dep).
- `smart_telescope/app.py`: Registered `gpsd_router` under `/api`.
- `smart_telescope/api/health.py`: Added `GET /api/status/storage` returning absolute paths for session stacks (`~/.SmartTScope/sessions`) and collimation frame archive (`~/.SmartTScope/frame_archive`).
- `smart_telescope/static/js/preview.js`: `_connectWs(camRoleOverride?)` and `previewStart(camRoleOverride?)` accept optional camera role override so callers can hardcode a role without touching `preview-cam-select`.
- `smart_telescope/static/js/setup.js`: `s4PreviewStart()` now mirrors offset and autogain controls from Stage 4 into the shared preview state and calls `previewStart('main')` — Bathinov preview always uses the main imaging camera. Added `checkGpsStatus()` (called on page load) and `applyGpsLocation()` for GPS location notification + one-click apply.
- `smart_telescope/static/js/app.js`: `checkGpsStatus()` called alongside `initSiteConfig()` on DOMContentLoaded.
- `smart_telescope/static/js/session.js`: `s5LoadStoragePaths()` fetches `/api/status/storage` and shows sessions directory in Stage 5.
- `smart_telescope/static/index.html`: Stage 1 — GPS notification banner (shown when distance > 100 m) + GPS distance row + Apply button in Observer & Time tile. Stage 4 — Offset input and Auto-gain checkbox added to Bathinov preview controls. Stage 5 — Storage path row below Start Session button.

---

## 2026-06-20 — FIX — Field-test bug sprint (11 files, commit ce022fb)

**Bugs fixed**
- Preview stretch now uses asinh so faint stars stay visible at low signal (mean_adu=9)
- Frame archive enabled by default — Save FITS / AF buttons no longer greyed out
- CollimationStarSelector filters by HA limits before altitude; Sirius at HA 8.8h no longer offered
- Polar alignment step 3 falls back to east-side alternate RA when west HA limit is exceeded
- Park API now requires `confirmed:true`; mount card shows browser confirm() dialog before parking
- Auto-gain: `force:true` flag bypasses POSSIBLE_FOCUS_OR_POINTING_ERROR; "Try Anyway" button in UI
- Mount status card shows explicit clock-sync banner when `onstep_clock_invalid` safety lock is active
- Plate solver fix (MissingSectionHeaderError) was already in origin/main — Pi needs git reset --hard
- Collimation camera selector was already wired in HTML/JS (s4-wiz-camera-role) — Pi needs update

---

## 2026-06-18 — FIX + FEATURE — Night sky session: solver, HA filtering, dark-sky stretch, camera select, step-3 preview, Bahtinov zoom

**Bugs fixed**

1. **Solver MissingSectionHeaderError** (`adapters/astap/solver.py`): ASTAP writes `.ini` files without a `[section]` header; `configparser` raised `MissingSectionHeaderError`. Fixed in `_parse_ini()`: read file as text, prepend `[Solution]\n` if the first non-blank line is not a section header, then use `cfg.read_string()`. Unblocks "Save solve FITS" and "AF frames" buttons.

2. **Alignment star list shows stars beyond mount HA limits** (`api/catalog.py`, `domain/visibility.py`): `/api/catalog/stars` returned all visible stars without checking if HA was within `MOUNT_HA_WEST_LIMIT_H` / `MOUNT_HA_EAST_LIMIT_H`. Added `compute_ha()` to `domain/visibility.py` (LST − RA via astropy) and filter stars in `catalog_stars()`. Stars past the meridian limit are excluded.

3. **Collimation "use best star" → meridian limit error**: `loadCollimStars()` (in `mount.js`) fetches `/api/catalog/stars` and `collimUseBestStar()` picks the first item. Same catalog HA filter as #2 prevents inaccessible stars from appearing; the "use best star" now always picks a reachable star.

4. **Preview stretch maps noise to mid-grey** (`domain/stretch.py`, `api/preview.py`): The 0.5–99.5 percentile stretch sets lo/hi from the full signal range, making the sky background appear mid-grey in dark conditions. Replaced with a background-subtracted, MAD-based sigma stretch: background = median, sigma = MAD/0.6745, lo = max(0, bg − 1.5σ), hi = bg + 10σ. Falls back to percentile stretch when sigma < 0.5 (uniform/mock frames). Applied per-channel in `_auto_stretch_color()` for colour cameras.

**Features added**

5. **Collimation camera selection** (`api/collimation.py`, `static/index.html`, `static/js/collimation.js`): Added `StartPayload` with `camera_role: str = "main"` to `POST /api/collimation/start`. The assistant singleton is reset when the requested role differs from the current one. A "Main camera" / "Guide camera" dropdown appears before the Start button; it hides once the wizard is active.

6. **Step-3 alignment live preview** (`static/js/setup.js`): After `watchSlew()` completes in `starGoto()`, `previewStart()` is called automatically so the camera feed is visible without a separate manual click.

7. **Bahtinov zoom** (`static/index.html`, `static/js/preview.js`): After a successful Bahtinov analyze, a "Zoom" toggle button appears. Clicking it shows a 180×180px picture-in-picture canvas (`s4-zoom-canvas`) in the top-right corner of the preview frame, cropped around the crossing point (radius ≈ 10% of the shorter image dimension) and scaled up for fine spike assessment.

---

## 2026-06-17 — FIX — Live Preview offset reset to 0 on Start

**Symptom**: Setting offset to 2000 and pressing Start reset the UI field to 0.

**Root cause**: `preview.py` reads back `eff_offset = camera.get_black_level()` after
`set_black_level(offset)`. The ToupTek SDK's `_try()` helper swallows all exceptions and returns
None, so `get_black_level()` falls through to `return 0` when the SDK call fails or the camera
silently rejects the value. This 0 was sent as `effective_offset` in the `camera_info` WebSocket
message, overwriting the user's field.

**Fix** (`smart_telescope/api/preview.py`): Only accept the readback value when it is non-zero or
zero was explicitly requested. A zero readback after a non-zero set is treated as a silent rejection
and the requested value is kept as `eff_offset`.

---

## 2026-06-17 — FIX — Disable Enable Tracking at HOME; improve pier_side log detail

**Symptoms reported**: Pressing "Enable Tracking" while mount is AT_HOME fails with
`pier_side_axis_inconsistent` (500 error). Log only showed the bare error code with no context.

**Root cause**: `enable_tracking()` has special at-home handling (skips positional checks), but
`_at_mechanical_home` is only set by `unpark_to_home_stop_tracking()`, not by the plain `unpark()`.
After a normal unpark the adapter's `_last_decoded_status` may not carry the `at_home` flag if
OnStep cleared the H flag before the next serial poll, so `at_home` evaluates to False and the code
falls through to `_check_target_safe` → `motion_safety_preflight` → `pier_side_axis_inconsistent`.

**Fix 1** (`smart_telescope/static/js/mount.js`): "Enable Tracking" button is now disabled (with
tooltip "Slew to a target before enabling tracking") when state is `at_home`. Tracking from HOME
serves no astronomical purpose — the user must slew to a target first.

**Fix 2** (`smart_telescope/adapters/onstep/mount.py`, `_check_target_safe`): Added a `WARNING`
log line immediately before the `OnStepSafetyError` raise that includes `pier_side`, `ha_hours`,
and `blockers` from the preflight dict, providing actionable diagnostics in the server log.

---

## 2026-06-17 — FINDING — onstep_adapter v0.3.0 is a re-export shim, not an independent library

`onstep_adapter` v0.3.0 package (`__init__.py` at Python 3.13 site-packages) contains only
`from smart_telescope.adapters.onstep.* import ...` re-exports and two smoke-test tools.
There is no independent implementation — the pip package re-exports SmartTScope's own code.
All REQ-1 and REQ-ST-001..007 methods already "exist" in v0.3.0 because they are in
SmartTScope's adapter layer. The ONS-MIGRATE migration is blocked on creating an independent
codebase in the OnStepAdapter repo (not on individual method additions). Updated `docs/todo.md`.

---

## 2026-06-17 — CORRECTION — REQ-2 removed from upstream requirements

`set_park_position() → bool` and `get_park_position() → MountPosition | None` are NOT
upstream requirements. v0.3.0 already provides `set_park_position_from_current()` and
`get_stored_park_position()`. The two SmartTScope methods are thin `MountPort` ABC
compliance wrappers that stay permanently in the shim. Updated: `docs/todo.md`,
`SYNC.md`, `smart_telescope/adapters/onstep/mount.py` comment.

---

## 2026-06-17 — PLAN — Replace adapter reimplementation with onstep_adapter pip package

Migration plan ONS-MIGRATE-001..013 added to `docs/todo.md` under the OnStepAdapter Migration section.
Goal: reduce `smart_telescope/adapters/onstep/mount.py` (4,408 lines) to a ≤30-line MountPort shim.
Blocked by upstream adoption of REQ-1, REQ-2, and REQ-ST-001..007 in tschoenfelder/OnStepAdapter.
Phase 0 (upstream contributions) must happen first; remaining phases execute after new wheel release.
Wiki index updated to reference the migration plan.

---

## 2026-06-17 — IMPLEMENTATION — OnStepAdapter migration finalized: no direct serial communication outside adapter layer

All serial/LX200 communication is now confined to `smart_telescope/adapters/onstep/` (focuser.py, mount.py).
No `api/` or `services/` code sends any serial commands directly.

Import path cleanup: all references to onstep_adapter types now go through the adapter package
`__init__.py` rather than internal submodules:
- `config.py`: `from .adapters.onstep import OnStepSafetyConfig`
- `runtime.py`: `from .adapters.onstep import OnStepClient`
- `api/mount.py`: `from ..adapters.onstep import OnStepSafetyError` (try/except removed)
- `services/mount_operations.py`: dead `OnStepSafetyError` import removed entirely

When an independent upstream `onstep_adapter` ships, the final rename is a single search-and-replace:
`from .adapters.onstep import X` → `from onstep_adapter import X`.

---

## 2026-06-17 — IMPLEMENTATION — Focuser API migrated to onstep_adapter public API

`FocuserStatus` and `FocuserMoveResult` dataclasses moved to `smart_telescope/ports/focuser.py`
(canonical location); `adapters/onstep/results.py` re-exports them for backward compatibility.
`FocuserPort` ABC extended with two new abstract methods: `status() → FocuserStatus` and
`move_absolute(steps) → FocuserMoveResult`. All concrete implementations updated:
`OnStepFocuser` (already had both), `MockFocuser`, `SimulatorFocuser`.

`smart_telescope/api/focuser.py` now uses the onstep_adapter public API surface:
- `GET /api/focuser/status` calls `focuser.status()` (single combined status call)
- `POST /api/focuser/move` and `/nudge` use `focuser.status()` + `focuser.move_absolute(target)`
- `_safe_move()` captures `result.start_position` from `FocuserMoveResult` (no separate `get_position` before move)

Tests updated: `tests/unit/api/test_focuser.py`, `tests/unit/api/test_smoke.py`.
Full unit suite: 2940 passed (before fix), all passing after.

---

## 2026-06-17 — TASK — OnStepAdapter v0.3.0 upgrade tracked

Added upgrade tasks ONS3-001..006 to `docs/todo.md` under the OnStepAdapter Migration section.
`pyproject.toml` already points to the v0.3.0 wheel (ONS3-001 done). Remaining steps:
install wheel, review REQ-ST-* overrides in `adapters/onstep/mount.py` and `client.py`,
run tests, commit. Wiki index updated to reference v0.3.0 and clarify the override-layer architecture.

---

## 2026-06-16 — FIX — pier_side_axis_inconsistent after disable→re-enable tracking

Two bugs fixed:

**1. Unpark shows TRACKING unexpectedly (regression)**

- `get_state()` was changed in a previous session to check `tracking` before `at_home`
  so that explicit `enable_tracking()` from home would clear the stuck AT_HOME state.
- Side effect: OnStep auto-starts sidereal tracking after `:hR#` (unpark) on some
  firmware versions, setting both H and T flags in `:GU#`. With the new priority
  order, `get_state()` returned TRACKING immediately after unpark instead of AT_HOME.
- Fix: added `_explicit_tracking_started` flag (set by `enable_tracking()`, cleared by
  `disable_tracking_verified()`, `stop()`, `park()`, `unpark()`). Tracking only wins
  over `at_home` when the flag is set. Auto-tracking after unpark falls through to the
  `at_home` branch, so AT_HOME is shown as expected.

**2. pier_side_axis_inconsistent when re-enabling tracking after disable**

- `:Gm#` retains the last GoTo session's pier side across unpark/reboot in OnStep
  firmware. It is not reset when the mount returns to home.
- When home is confirmed (`_home_confirmed=True`) and the mount has not done a GoTo
  (axis2 ≈ 0°), the axis-derived pier side ("east" for CWD) is correct, but `:Gm#`
  may still report "west" from the previous session → `pier_side_axis_inconsistent`.
- Fix: in `motion_safety_preflight()`, when `_home_confirmed` is True and axis2 < 15°,
  treat the derived value as authoritative and skip the inconsistency check.

---

## 2026-06-16 — FIX — State stays AT_HOME after enable_tracking (root cause)

- Previous fix (clear `_at_mechanical_home` in `enable_tracking()`) was undone on the
  very next background poll: `get_state()` saw `at_home=True` still in `:GU#` (OnStep
  keeps the H flag while tracking from home) and re-set `_at_mechanical_home = True`.
- Root cause: `tracking` was checked AFTER `at_home` in `get_state()`.
- Fix: check `decoded["tracking"]` first. If OnStep reports tracking, clear
  `_at_mechanical_home` and return `TRACKING` immediately — `at_home` branch is skipped
  entirely.  The SYNC-OVERRIDE order (at_home before slewing) is preserved for the
  non-tracking case.

---

## 2026-06-16 — FIX — State stays AT_HOME after enable_tracking

- `get_state()` returns `AT_HOME` when `_at_mechanical_home` is True, regardless
  of `:GU#` flags.  After a successful `:Te#`, the flag was never cleared, so the
  mount stayed stuck in AT_HOME even while OnStep reported `tracking=True`.
- `enable_tracking()` now sets `_at_mechanical_home = False` on `:Te#` success.

---

## 2026-06-16 — FIX — Track fails: hour_angle_east after home

- After going home, OnStep's RA readback is stale (last tracked or park position RA).
  `LST − stale_RA` can produce an HA far east of the -5.5h limit, blocking
  `enable_tracking()` with `hour_angle_east` even though the mount is mechanically safe.
- `enable_tracking()` now detects `_at_mechanical_home` flag; if at home it only runs
  `_raise_if_locked` and `_raise_if_not_astronomy_ready` (safety lock + time trust),
  skipping the RA/Dec/HA positional limit checks which are meaningless until the
  first plate-solve sync establishes a valid pointing model.

---

## 2026-06-16 — FIX — Track fails: pier_side_axis_inconsistent after home

- At the CWD home position (axis2 ≈ 0°) `_instrument_to_mount_axes` derives
  pier_side="east", but OnStep's `:Gm#` can report "west" — a meridian-point
  ambiguity inherent to CWD position.
- `pier_side_axis_inconsistent` was added to blockers unconditionally; but
  `pier_side_unavailable` and `hour_angle_unavailable` already use `not terminal_state`
  guard.  Applied the same guard to `pier_side_axis_inconsistent` in
  `motion_safety_preflight()`.  In terminal state (parked or at-home) pier side
  ambiguity is expected and harmless.

---

## 2026-06-16 — FIX — Track fails: firmware_limits_broad

- OnStep defaults to broad firmware limits (horizon ≤ -5°, overhead ≥ 89.5°).
  `allow_broad_onstep_limits` defaulted to `False`, blocking all motion.
- SmartTScope enforces its own tighter limits (min 10°, max 88°) at the API
  layer via `_check_mount_limits()` before any command reaches the hardware,
  so the firmware limit check is redundant.
- Set `allow_broad_onstep_limits=True` in the `OnStepSafetyConfig` created by
  `config.py`.

---

## 2026-06-16 — FIX — Track fails: raspberry_time_plausible_not_trusted

- After a successful time/location sync the `_time_readiness()` check still returned
  `ready=False` because `time_trust_source` remained `"raspberry_plausible"` — not
  in `_TRUSTED_TIME_SOURCES` — so `trusted` was always `False`.
- `sync_onstep_time_location()` now also sets `time_trust_source="user_confirmed"`
  (which is in `_TRUSTED_TIME_SOURCES`) when called with `confirmed_by_user=True`.
  This promotes the trust level so subsequent `_time_readiness()` calls pass.

---

## 2026-06-16 — FIX — Enable Tracking fails: onstep_clock_invalid

- `track_sequence()` in `mount_operations.py` called `enable_tracking()` which calls
  `_check_target_safe()` — same safety gate that blocks GoTo when clock is unsynced.
- Added `mount.ensure_time_location_synced()` at the start of `track_sequence()`.

---

## 2026-06-16 — FIX — GoTo & Plate Solve Goto fails: onstep_clock_invalid

- `goto_and_center()` and plain `/goto` endpoint never synced time/location to OnStep before
  issuing the GoTo command. OnStep's safety system blocked all goto attempts with
  `onstep_clock_invalid` because the adapter's internal clock state was stale.
- Added `ensure_time_location_synced() -> None` to `MountPort` (default no-op).
- Implemented in `OnStepMount`: calls `sync_onstep_time_location()` with configured lat/lon/alt.
- Called before the GoTo loop in `workflow/goto_center.py` (Plate Solve Goto path).
- Called at the start of `services/mount_operations.safe_goto()` (plain GoTo path).
- Test mock `_MockMount` in `test_goto_center.py` updated with no-op `ensure_time_location_synced`.

---

## 2026-06-14 — FIX — CRITICAL: remove auto_set_park; home UI live status

- Removed `auto_set_park` from `park_sequence()` and park API endpoint. Pressing Park from
  AT_HOME was automatically calling `set_park_position()` (`:hS#`), overwriting the user's
  configured EEPROM park position. Park position must only be set by explicit user action.
- `park_sequence()` now always stops any active slew and issues `:hP#` without touching `:hS#`
- `mountHome()` JS: added 1 s `setInterval` status poll while the home API is blocking (up to
  60 s). Strip now shows "home…" with yellow dot pulsing live during home slew — same visual
  as park's rolling status badge

---

## 2026-06-14 — FIX — Unpark shows PARKED: remove auto-disable-tracking from unpark_sequence

`disable_tracking_verified()` sends `:Q#` (quit-move) after unpark. On the Pi's OnStep firmware
this causes GU# to briefly report parked → UI flickers to PARKED immediately after Unpark.
Removed auto-disable-tracking from `unpark_sequence()`. The Disable Tracking button works in
one click (has `poll_now()` after success). Tracking is expected to be on after unpark.

---

## 2026-06-14 — FIX — Home stays SLEWING: tight 0.5 s poll loop in home_sequence

Background poll (2 s) was too coarse — OnStep's 'H' (at_home) GU# flag clears in <1 s when
the mount is already near home, so the background thread always missed it.

Fix: `home_sequence()` now does a tight 0.5 s polling loop (up to 60 s) directly on
`mount.get_state()` after `go_home()`.  `get_state()` SYNC-OVERRIDE detects the 'H' flag
and calls `confirm_home_position()` on first observation, then returns AT_HOME.
The loop breaks immediately on AT_HOME; unexpected states (TRACKING, PARKED) also break early.

---

## 2026-06-14 — FIX — Park fails after Home; adapter version "?" in readiness

- `get_state()` SYNC-OVERRIDE: when GU# 'H' flag is first seen, call `confirm_home_position()`
  (sets `_home_confirmed=True`) so `set_park_position_from_current()` accepts the subsequent call;
  also split `at_home` / `_at_mechanical_home` branches so confirm is only called once
- `set_park_position()` SYNC-OVERRIDE: pass `allow_at_home=True` — our park-from-home
  workflow explicitly sets park position = home position, which the adapter refused by default
- Added `__version__ = "0.3.0"` back to `onstep/__init__.py` (stripped by external sync)
- Readiness: try `importlib.metadata` first, then `onstep.__version__` as fallback

---

## 2026-06-14 — FIX — Unpark tracking / disable_tracking double-click / readiness version

- `unpark_sequence()` now auto-disables tracking after `:hR#` (OnStep auto-starts tracking on unpark)
- `disable_tracking` API endpoint now calls `device_state.poll_now()` after success — state cache
  refreshes immediately so the UI reflects non-tracking without a second button press
- Readiness mount item now shows OnStep adapter version: "Connected (adapter v0.3.0) — state: …"

---

## 2026-06-14 — FIX — Home stuck in SLEWING after :hC# (REQ-3 partial)

Root cause: new adapter's `get_state()` checked `slewing` before `at_home` in priority chain.
During home travel OnStep keeps the goto-active flag set until the 'H' GU# flag appears,
so `get_state()` returned SLEWING indefinitely — the service AT_HOME state machine never fired.

Fix: SYNC-OVERRIDE of `get_state()` in `smart_telescope/adapters/onstep/mount.py` —
`at_home` (or `_at_mechanical_home`) now takes priority over `slewing`.
Service layer sticky-AT_HOME logic in `device_state.py` lines 274-277 now triggers correctly.
REQ-3 filed against upstream to adopt the priority order natively.

---

## 2026-06-14 — UPGRADE — OnStepAdapter v0.2.0 → v0.3.0

Upgraded onstep_adapter to v0.3.0 (branch `codex/release-0.3.0`).

- `get_park_position()` now reads from state store (REQ-2 fulfilled); undocumented `:GpA#`/`:GpD#` serial probe removed by upstream
- `set_park_position()` SYNC-OVERRIDE added: delegates to `set_park_position_from_current(confirmed_safe=True)` — now actually sends `:hQ#` and persists to state store
- `move()` SYNC-OVERRIDE upgraded: `mechanical_manual_move()` at center/slew rate replaces `guide()` delegation (faster, uses `:Me#`/`:Mw#` etc.)
- New public types: `SetParkPositionResult`, `AxisMotionResult`, `StoredParkPosition`, `OnStepMotionCalibration`
- REQ-3/4/5 remain open; 2943 passed, 24 skipped, 0 failed

---

## 2026-06-14 — ARCH — OnStepAdapter migration complete

Replaced hand-rolled `smart_telescope/adapters/onstep/{mount,focuser,serial_bus}.py` with the external `onstep_adapter` package (tschoenfelder/OnStepAdapter v0.2.0). All mount and focuser hardware communication now flows exclusively through `OnStepClient`.

**Files changed:**
- `smart_telescope/adapters/onstep/`: 9 files synced from GitHub source (mount.py, focuser.py, serial_bus.py, client.py, safety.py, results.py, state_store.py, firmware_proof.py, __init__.py)
- `smart_telescope/config.py`: added `build_onstep_safety_config()` factory
- `smart_telescope/runtime.py`: replaced direct adapter construction with `OnStepClient` lifecycle
- `smart_telescope/services/device_state.py`: added `safety_violation` to `MountObservedState`; poll loop reads `mount.safety_lock`
- `smart_telescope/services/mount_operations.py`: `OnStepSafetyError` imported with fallback
- `smart_telescope/api/mount.py`: `safety_violation` field in `MountStatus`; goto returns 409 on safety violation
- `SYNC.md`: OnStepAdapter registered as external module with REQ-1..5 enhancement requests

**SYNC-OVERRIDE active:**
- `mount.py`: `move(direction, move_ms)` added as concrete method delegating to `guide()` — satisfies abstract `MountPort.move()`; proper slew-rate variant tracked as REQ-1

**Enhancement requests raised** (tracked in SYNC.md): REQ-1 move() at slew rate, REQ-2 park position get/set, REQ-3 sticky AT_HOME, REQ-4 hardware watchdog, REQ-5 command audit trail.

---

## 2026-06-13 — FIX — Park: stop active slew before parking

**Problem**: Clicking Park while the mount was slewing (e.g. left slewing from a previous session) returned HTTP 409 "Mount is still slewing", blocking all park attempts.

**Fix**: `park_sequence` now sends `:Q#` (stop) + 300 ms settle when the mount is SLEWING and `auto_set_park=False`. Then `:hP#` is sent to the previously saved park position. The 409 guard is retained only for the rare race where `auto_set_park=True` (home slew still in mid-flight when Park is clicked) — parking mid-home-slew would store the wrong position.

## 2026-06-13 — FIX — Premature HOME display before home slew starts

**Problem**: `record_command("home")` set `_sticky_at_home=True` immediately. If the background poller ran before OnStep raised its 'S' (SLEWING) flag, it saw UNPARKED and promoted it to AT_HOME — so the mount tile showed "Home" before the slew even started. Clicking Park at that moment then failed because the mount was mid-slew.

**Fix**: Replaced the single `_sticky_at_home` flag with a two-phase gate: `_home_cmd_issued` (set on home command) + `_home_slew_seen` (set when SLEWING is polled after the command). UNPARKED is only promoted to AT_HOME after both flags are true — confirming the slew actually happened and ended. Hardware 'H' flag still sets sticky directly. Updated 12 tests in `TestStickyAtHome`; added `test_home_unparked_without_slewing_not_premature`.

## 2026-06-13 — FEAT — Auto set-park position on Home → Park (:hS# before :hP#)

**Problem**: OnStep requires `:hS#` to be called at least once before `:hP#` will be accepted. The "Set Park" button approach (reverted) required a manual extra step.

**Fix**: `park_sequence` receives `auto_set_park: bool` from the API. The API captures whether the device-state cache shows `AT_HOME` before calling `record_command("park")` (which clears the sticky flag). When `auto_set_park=True`, `park_sequence` sends `:hS#` (save park position = current home position) then `:hP#` — all automatically. Subsequent Park clicks (position already in EEPROM) use `auto_set_park=False` and send only `:hP#`. `MountPort.set_park_position()` added as a non-abstract default (`return False`); `OnStepMount` overrides with `:hS#`.

## 2026-06-13 — FEAT — AT_HOME mount state: sticky Home after homing slew

**Problem**: After `POST /api/mount/home`, the mount tile showed "Unparked" instead of "Home". OnStep sets the `'H'` flag in `:GU#` for less than one poll cycle (2 s), so the background poller always missed it, observing only SLEWING then UNPARKED.

**Fix**:
- Added `MountState.AT_HOME` to the enum; `OnStepMount.get_state()` returns it when `'H'` is in the `:GU#` response (belt-and-suspenders path).
- `DeviceStateService` gains `_sticky_at_home` flag set by `record_command("home")` — active before the first poll after the slew. When the poller sees UNPARKED and sticky is set, the cached state is promoted to AT_HOME.
- Sticky clears on `record_command("goto" | "park" | "track")`. SLEWING/TRACKING/PARKED are always shown as-is (not overridden).
- CSS `.state-at_home` (blue badge); JS `_STATE_LABEL` maps "at_home" → "Home"; dot colour = yellow (same as unparked).
- 11 new tests in `TestStickyAtHome`.
- Verified on hardware: "Home" persists after home slew and clears on next GoTo/Park/Track command.

## 2026-06-13 — FEAT — Nudge rate ×2, archive singleton fix, GoTo/Solve/AF archive tagging

**Nudge rate**: `OnStepMount.move()` now sends `:RM#` (move/slew rate) instead of `:RC#` (center rate), approximately doubling RA/Dec nudge speed in the Centre Star guide pad and Stage 4 collimation guide pad.

**Archive activation fix**: `_frame_archive` is now a separate singleton from `_assistant`, created by `_get_archive()` on the first archive API call. Previously, the archive was only created when a collimation session started (`_get_assistant()`), so visiting the archive endpoint before starting a wizard returned "disabled" even with `enabled = true` in config. Archive now activates on app start if `[collimation.archive] enabled = true` is set before launch.

**GoTo/Solve/AF archive tagging**:
- `CollimationFrameArchive.save_tag()` saves metadata-only JSON entries (no FITS) for GoTo, plate-solve, and AF operations. `list_sessions()` and `list_frames()` include these tag entries alongside FITS frames; `_arcFrameRow` shows "tag" label instead of Replay button for JSON-only entries.
- `POST /api/collimation/archive/tag` endpoint accepts `tag_type` + `data`; default session = `s3_YYYY-MM-DD`.
- Stage 3 UI: 📁 buttons added next to GoTo, Solve, and AF buttons. Buttons enable after a successful operation when archive is active. Collapsible "Session Archive" browser added to Stage 3.
- Archive status checked automatically when entering Stage 3 (`_s3CheckArchiveEnabled()`).

## 2026-06-13 — FIX — Park error surfacing and idempotency

**Problem**: `POST /api/mount/park` returned HTTP 500 "Park failed" when `:hP#` returned `b'0'`, with no indication of the mount's pre-park state or why OnStep rejected the command. Debugging required reading server logs.

**Fixes**:
- `park_sequence()` now calls `get_state()` before attempting park; if already PARKED, returns immediately (idempotent). If `:hP#` is rejected, error message includes pre-state name and actionable hint: "verify park position is set (:hS# from home) and mount is aligned".
- `mount_park()` endpoint passes `{exc}` through to HTTP detail instead of generic "Park failed".
- Same pattern applied to `mount_unpark()`, `mount_guide()`, `mount_nudge()` error messages.
- 1 new test: `test_park_sequence_skips_park_when_already_parked`.

**Why park failed**: `:hP#` returns `0` when the park position was not set in OnStep (`:hS#` must be called from the desired park position during initial mount setup) or when the mount is not aligned.

## 2026-06-13 — FIX — Mount selftest + Centre Star guide pad: use center rate for observable movement

**Root cause (round 2)**: Guide pulses (`:Mg...#`) use OnStep's configurable guide rate. If the guide rate is unconfigured or very slow, even 2000 ms pulses produce no observable movement. The focuser selftest works because it uses absolute steps — the mount equivalent is center rate (`:RC#` + `:Mn#` → sleep → `:Q#`), which is always configured for visible manual centering.

**Fix**:
- Added `move(direction, move_ms)` abstract method to `MountPort`, implemented in `OnStepMount` using `write_bypass` (same pattern as `stop()` since rate/move commands have no response bytes), `SimulatorMount`, and `MockMount`.
- Added `POST /api/mount/nudge` endpoint — same state checks as `/guide` but calls `mount.move()`.
- `selftest_mount` now calls `mount.move()` instead of `mount.guide()`. Button group greys out during the 2-second test (like focuser), result shows `"N 2 s — moved"`.
- Stage 2 Centre Star guide pad (`guideStart()`) switched from `/api/mount/guide` to `/api/mount/nudge` — hold-and-repeat pattern is identical but now uses center rate.
- 11 new tests for `TestMountNudge`.

## 2026-06-13 — FIX — Mount selftest: guide pulses now measure arcsec shift

**Root cause**: A 2000 ms guide pulse at typical OnStep guide rates (0.5–1× sidereal = 7–15″/s) produces only 14–30 arcseconds of physical movement — invisible to the naked eye at any viewing distance. The selftest previously reported "ok" with no way to verify movement actually occurred.

**Fix**:
- `selftest_mount` now captures position (`:GD#`/`:GR#`) before and after the pulse, sleeps for `duration_ms + 300 ms`, then returns `delta_arcsec` in the response body.
- Default `duration_ms` raised 500 → 2000 ms to improve detection signal.
- `selftestMount()` JS now shows the shift: `N pulse 2000 ms — ok (+29.9″ shift)` or warns `no position shift — check OnStep guide rate`.
- 2 new tests: `test_north_pulse_returns_delta_arcsec`, `test_south_pulse_returns_negative_delta`.

## 2026-06-11 — FIX — Histogram comb pattern from 12-bit-in-16-bit camera data

**Root cause**: ToupTek SDK in 16-bit mode stores 12-bit ADC data MSB-aligned (left-shifted 4 bits). Values are 0, 16, 32, …, 65520. The focused histogram with ~7 ADU bins produced a comb pattern (every 2–3 bins was empty because valid values are 16 ADU apart). Additionally the histogram API was incorrectly normalising by `adc_max=4095` (bit_depth=12 default) while pixels were in 16-bit container range, giving signal fractions 16× too high.

**Fix** (`fb60f73`):
- `camera.py` / `managed.py`: lazily detect pixel shift on first captured frame (`_detect_pixel_shift`); right-shift pixels to native 12-bit range (0–4095); write `BITDEPTH=12` in FITS header. `get_bit_depth()` now returns the sensor depth.
- `autogain_service.py`: re-derives `bit_depth` and `adc_max` from the frame `BITDEPTH` header after each capture.
- `histogram.py API`: reads `bit_depth` from frame header instead of query-param default.
- `SYNC.md`: documents new SYNC-OVERRIDEs for both adapter files.

---

## 2026-06-09 — FIX — HOME uses OnStep :hC#; focuser selftest relative moves; tile refresh

**Bug 1 — HOME position overrun**
`home_sequence()` was computing RA = current LST, Dec = 85° and issuing a GoTo.  This ignored
OnStep's stored home position (set with `:hF#` during initial alignment) and could overrun the
mount's meridian limits or HA limits near the pole.

**Root cause:** SmartTScope invented its own HOME coordinates instead of delegating to OnStep.

**Fix:**
- `smart_telescope/ports/mount.py` — added `go_home()` abstract method to `MountPort`
- `smart_telescope/adapters/onstep/mount.py` — `go_home()` sends `:hC#` (Move to home)
- `smart_telescope/adapters/mock/mount.py` — stub: sets state to TRACKING
- `smart_telescope/adapters/simulator/mount.py` — stub: calls `goto(0, 89.0)`
- `smart_telescope/services/mount_operations.py` — `home_sequence()` now calls `mount.go_home()`
  instead of computing LST+85°; removed astropy/config imports no longer needed; returns `None`
- `smart_telescope/api/mount.py` — HOME endpoint response simplified to `{"ok": True}`
- `smart_telescope/services/setup_check_service.py` — callers updated; message updated
- `smart_telescope/api/setup_check.py` — docstring updated
- `smart_telescope/static/js/mount.js` — status messages no longer display invented coordinates
- `smart_telescope/static/js/setup.js` — wizard prompt updated

**Bug 2 — Focuser selftest moved to absolute position instead of relative**
`selftest_focuser()` in `collimation.py` called `focuser.move(steps)` with `steps=10`.
Since `FocuserPort.move()` is an **absolute** position command (`:FS[n]#`), this moved the
focuser to absolute step 10 from wherever it was (e.g. 5227 → 10), not +10 from current.
Same bug existed in `run_focuser_move()` in `setup_check_service.py`.

**Fix:**
- `smart_telescope/api/collimation.py` `selftest_focuser()` — computes `target = before + steps`
  then calls `focuser.move(target)`; waits for `is_moving()` to clear before reading `after`
- `smart_telescope/services/setup_check_service.py` `run_focuser_move()` — same relative→absolute
  fix; restore now calls `focuser.move(before)` instead of `focuser.move(-steps)`

**Bug 3 — OnStep focuser tile (s1-focuser-pos) not refreshing**
The Stage 1 focuser position tile was set only at `connectAll()` time and never updated when
nudge or selftest operations ran, so it showed the connect-time value (e.g. 25000/50000) even
as the focuser moved.

**Fix:**
- `smart_telescope/static/js/focuser.js` `_refreshFocuserPosition()` — now also updates
  `s1-focuser-pos` / `s1-focuser-pos-row` whenever Stage 4 position poll fires
- `smart_telescope/static/js/collimation.js` `selftestFocuser()` — calls `refreshFocuser()` and
  `_refreshS1FocuserPos()` in the `finally` block after each test

**Tests:**
- `tests/unit/services/test_mount_operations.py` — replaced LST-based home tests with
  `test_home_sequence_issues_go_home` and `test_home_sequence_does_not_goto`
- `tests/unit/api/test_setup_check.py` — `TestFocuserMove` updated: move calls now use
  absolute positions (before+steps, before); iterator provides 2 positions instead of 3
- All 2920 unit tests pass

---

## 2026-06-08 — FEAT(CID-007) — Detect newly connected cameras not in config

**What changed:**
- `smart_telescope/domain/camera_config_suggestion.py` (new) — `suggest_role()`, `_default_offset()`, `_default_capture_mode()`, `generate_toml_snippet()` — pure domain, no I/O
- `smart_telescope/api/cameras.py` — `CameraInfo.toml_snippet` field added; `_do_scan()` populates it for cameras with `role=None`; also resolves role via `CAMERA_SPECS` model/camera_id match (was only checking by index)
- `smart_telescope/services/readiness.py` — `_check_unconfigured_cameras()` returns YELLOW item when SDK cameras are connected but not matched by any configured CameraSpec; wired into `check()`
- `smart_telescope/static/js/setup.js` — `cameraCard()` shows yellow "Not in config" badge + collapsible TOML snippet + Copy button for unconfigured cameras; `csSnipcopy()` helper added
- `smart_telescope/static/index.html` — CSS added: `.card-warn`, `.badge-ok`, `.badge-warn`, `.snippet-details`, `.snippet-code`, `.btn-copy`
- `tests/unit/domain/test_camera_config_suggestion.py` (new) — 30 tests, 100% coverage of domain module
- `tests/unit/api/test_cid007.py` (new) — 15 tests covering API snippet generation and readiness YELLOW item
- `docs/todo.md` — CID-007 marked done

**Verified:** 2897 tests pass, 0 regressions.

---

## 2026-05-26 — FIX(UI) — Focuser selftest runaway + serial port auto-reconnect

**What changed:**

- `smart_telescope/static/index.html`: Added IDs `s4-st-focuser-plus` and `s4-st-focuser-minus` to the two focuser selftest buttons so they can be referenced by JavaScript.
- `smart_telescope/static/js/collimation.js` (`selftestFocuser`): Both buttons are disabled synchronously at the start of the function (before the first `await`), and re-enabled in a `finally` block after the API call completes. This prevents any additional browser events (second tap, touch+click double-fire) from queuing serial moves while one is in flight.
- `smart_telescope/services/device_state.py`: Added rate-limited `mount.connect()` call in `_poll_once` exception handler. When a serial I/O error leaves the serial bus broken (`_serial = None`), the poller now attempts reconnect at most once every 30 s. Previously, an I/O error (e.g. `[Errno 5] Input/output error` from USB disconnect/overload) would leave the mount permanently in UNKNOWN state until app restart.

**Root cause — runaway:** `selftestFocuser()` had no button locking. On a touchscreen a single physical tap can fire both a `touchend` and a `click` event; some browsers/tablets fire the `onclick` handler twice in rapid succession. Both calls reached the server before either completed, queueing multiple `:FS{steps}#` serial commands. The motor received alternating `+10` and `-10` (or repeated same-direction) moves with no time to settle, producing the observed runaway.

**Root cause — serial port death:** After rapid focuser moves caused an I/O error on the shared serial bus, `OnStepSerialBus.send()` set `self._serial = None` and raised, leaving the bus permanently broken. `DeviceStateService._poll_once` caught the exception and stored UNKNOWN state, but had no mechanism to recover the connection — the mount stayed UNKNOWN until the app was restarted.

---

## 2026-05-26 — FIX(UI) — Stage 4 proceed button: unlock on Connect All (no GoTo required)

**What changed:**

- `smart_telescope/static/js/app.js` (`unlockStage`): When Stage 4 is unlocked, `s3-proceed-btn` is now enabled immediately. Previously the button was only enabled after a successful GoTo slew completed, so after a "Connect All" that left the mount parked, the user had no way to advance to Stage 4.

**Root cause:** `s3-proceed-btn.disabled` was cleared only in the GoTo success path. Stage 4 unlock (triggered by any non-UNKNOWN mount state) never touched the button, leaving it disabled for users who skipped GoTo.

---

## 2026-05-26 — FIX(UI) — Stage 4 collimation button: start strip poll at page load

**What changed:**

- `smart_telescope/static/js/app.js`: Added `_startMountStripPoll()` call at page load alongside `refreshMount()`. The 5-second repeating mount-status poll now starts immediately, so Stage 4 unlocks within ≤5 s even if the single initial `refreshMount()` caught a transient UNKNOWN state (startup race between DeviceStateService poller and DawnWatcher's concurrent `poll_now()` call). Removed diagnostic console.log lines.
- `smart_telescope/static/js/mount.js`: Removed diagnostic console lines from `refreshMount` and `_updateMountStrip`; restored to original logic.
- Backend WARNING logs in `smart_telescope/api/mount.py` and `smart_telescope/services/device_state.py` retained for future diagnosis.

**Root cause:** `_startMountStripPoll()` was only called inside `goToStage()`. Stage 1 is the initial active stage and `goToStage(1)` is never called at startup, so no strip poll ran on Stage 1. If the one-shot `refreshMount()` at page load caught a transient UNKNOWN state (DawnWatcher + background poller both calling the serial bus simultaneously at startup), Stage 4 stayed locked with no recovery mechanism.

---

## 2026-05-26 — DBG — Diagnostic logs for Stage 4 collimation button unlock failure

**What changed:**

- `smart_telescope/static/js/app.js`: log at page load showing strip poll is NOT started at startup (only starts via `goToStage()`).
- `smart_telescope/static/js/app.js`: log in `_startMountStripPoll` when it fires.
- `smart_telescope/static/js/mount.js`: log in `refreshMount` showing state received, whether strip poll is running, whether Stage 4 is already unlocked.
- `smart_telescope/static/js/mount.js`: log in `_updateMountStrip` showing when Stage 4 is unlocked vs. why it stays locked (state='unknown').
- `smart_telescope/api/mount.py`: WARNING logs in `mount_status` when cache or direct query returns UNKNOWN state.
- `smart_telescope/services/device_state.py`: WARNING log in `_poll_once` when `get_state()` returns UNKNOWN, separate from poll exception.

**Root cause hypothesis:** The mount strip poll only starts when `goToStage()` is called. On page load, only one `refreshMount()` fires. If that one call gets state='unknown' (OnStep not yet ready), Stage 4 stays locked forever with no retry mechanism.

---

## 2026-05-26 — COL-ENH2 — Collimation UX polish: report, auto-remeasure, best-star

**What changed:**

- `smart_telescope/static/index.html` + `smart_telescope/static/js/collimation.js`:
  - **Session report panel**: when wizard reaches COMPLETE, fetches `/api/collimation/report` and shows overall status (colour-coded), duration, selected star, FWHM before/after, final donut error, and any warnings — all inline in the wizard card.
  - **Auto-remeasure**: guide phases (GUIDE_ROUGH_COLLIMATION / GUIDE_FINE_COLLIMATION) now show an "Auto every 5s" checkbox. When ticked, the wizard fires Remeasure automatically on a 5-second interval; cleared on cancel/stop.
  - **Use Best Star button**: when wizard enters SELECT_STAR state, a "Use Best Star" button appears that auto-picks the brightest star from the star list (mag-sorted) and submits it as the selected star without user needing to click the list.

---

## 2026-05-26 — COL-ENH — Collimation measurement metrics + archive browser UI

**What changed:**

- `smart_telescope/services/collimation/assistant.py` (`status` property): `last_measurement` now includes `measurement_type` ("donut"/"spikes"/"star"/None) and sub-dicts: `donut` (error_x_px, error_y_px, error_magnitude_px, error_fraction, outer_radius_px, is_collimated, confidence); `spikes` (focus_error_px, crossing_error_rms_px, offset_from_ref_px, is_in_focus, confidence); `star` (fwhm_px, snr). 4 new tests verify each measurement type.

- `smart_telescope/static/index.html` + `smart_telescope/static/js/collimation.js`: Measurement metrics panel added to wizard card — shows collimation error (px + % of outer ring, colour-coded green/yellow/red), spike focus error + RMS, star FWHM. Frame Archive Browser card added to Stage 4: lists past sessions (id, frame count, state breakdown, disk size); expanding a session loads its frame table; Replay button re-runs donut/spike analysis on the stored FITS frame and shows original vs replayed values side-by-side.

---

## 2026-05-26 — BUG-FIX — Stage 4 mount strip poll stopped on Stage 1

**What changed:**

- `smart_telescope/static/js/app.js` (`goToStage`): Removed `_stopMountStripPoll()` call when navigating to Stage 1.
  - Root cause: OnStep takes time to boot after power-on; the initial page-load `refreshMount()` sees UNKNOWN state. With the mount strip poll stopped on Stage 1, this UNKNOWN state was never corrected automatically, keeping Stage 4 locked until the user clicked "Connect All".
  - Fix: `goToStage()` now always calls `_startMountStripPoll()` on every stage, so `_updateMountStrip()` runs every 5 s and unlocks Stage 4 as soon as the mount reports a known state.

---

## 2026-05-24 — BUG-FIX — Preview camera and Stage 4 unlock fixes (rev 2)

**What changed:**

- `smart_telescope/api/preview.py`: Fixed preview WebSocket always using GPCMOS02000KPA (camera index 0) regardless of selected optical train.
  - Root cause: model-based camera config sets `CameraSpec.index = None`; registry defaults all trains to `camera_index = 0`, so every train opened the same physical camera.
  - Fix: after resolving the train from `camera_role`, call `deps.get_camera_by_role(train.camera_role)` (which uses model-matching to open the correct device) instead of `deps.get_preview_camera(camera_index=0)`. Falls back to index-based resolution on failure.
  - Rev 2: wrapped `get_camera_by_role` call in `asyncio.to_thread` — the first call blocks on USB SDK I/O (camera connect + configure); running it in a thread prevents stalling the WebSocket event loop.

- `smart_telescope/static/js/mount.js` (`_updateMountStrip`): Fixed Stage 4 (Collimation) tab remaining locked after the PARKED detection fix.
  - Root cause: the previous `get_state()` bug (`r[0] == "P"` check) always returned UNPARKED on real hardware, so `_updateMountStrip` always unlocked Stage 4. After the correct PARKED detection, Stage 4 was locked on page-load with mount parked, and only unlocked after unpark.
  - Fix: Stage 4 now unlocks for any *known* mount state (not just unparked), because calibration frames and Bahtinov preview don't require the mount to be unparked. The collimation wizard auto-unparks internally if needed. Stage 2 (Alignment) still requires unparked mount.

---

## 2026-05-24 — ONS — OnStep protocol documentation update

**What changed:**

- `wiki/onstep-protocol.md`: Updated with hardware-confirmed findings from direct serial probe (2026-05-24).
  - `:GU#` section: documents real compact wire format (`nNPEW260` parked, `NpeEW260` unparked); correct PARKED detection rule `"P" in r and "p" not in r`; wrong approaches listed explicitly.
  - Park commands section: `:hR#` confirmed as correct unpark command (~2 s synchronous, returns `b"1"`/`b"0"`); `:hU#` confirmed rejected by firmware; `:hP#` confirmed fire-and-forget (~10 ms, mount slews asynchronously).
  - Serial bus section: documents two-read-strategy table; `timeout_s` override mechanism for slow commands; rule against long global timeouts.
  - Commands table: updated `unpark()`, `get_state()`, `park()` rows with confirmed behaviour.

---

## 2026-05-24 — COL-ARC — Collimation frame archive

**What changed:**

- `smart_telescope/domain/collimation/config.py`: `ArchiveConfig` dataclass (`enabled`, `archive_dir`, `max_frames_per_session`); `CollimationConfig` gains `archive: ArchiveConfig` field

- `smart_telescope/services/collimation/frame_archive.py` (NEW): `CollimationFrameArchive` — `new_session()` creates `<archive_dir>/<session_id>/`; `save_frame()` writes FITS via `FitsFrame.to_fits_bytes()` + JSON sidecar with state/analysis/ref_x/ref_y/bit_depth; silently skips when `max_frames_per_session` reached; `list_sessions()` newest-first by mtime; `list_frames()` sorted by filename; `load_frame()` / `load_sidecar()` raise `FileNotFoundError` when absent; 7 tests in `tests/unit/services/test_frame_archive.py`

- `smart_telescope/services/collimation/assistant.py`: `__init__` accepts `frame_archive: CollimationFrameArchive | None`; `start()` generates `uuid4` session ID and calls `archive.new_session()`; `frame_archive` property; `_handle_measure_donut` saves raw frame + donut analysis dict after each accepted measurement; `_handle_measure_spikes` saves raw frame + spike analysis dict after each accepted measurement; 3 new tests in `test_collimation_guiding.py`

- `smart_telescope/api/collimation.py`: `_get_assistant()` builds `CollimationFrameArchive` from `col_cfg.archive` when `enabled=True`, passes to `CollimationAssistant`; `GET /api/collimation/archive` lists sessions; `GET /api/collimation/archive/{session_id}` lists frames; `POST /api/collimation/archive/{session_id}/{frame_stem}/replay` re-runs `DonutAnalyzer` or `detect_spikes` on stored frame; 6 tests in `tests/unit/api/test_collimation_archive_api.py`

- `templates/config.toml`: `[collimation.archive]` section added (disabled by default)

---

## 2026-05-24 — COL-GUD — Collimation guiding integration complete

**Source:** `docs/superpowers/plans/2026-05-24-collimation-guiding-integration.md`

**What changed:**

- `smart_telescope/services/guiding_service.py`: `GuidingStatus` gains `rms_px: float` and `last_pulse: tuple[str, int] | None`; `GuidingService` gains `pause_pulses()`, `resume_pulses()`, `rebaseline()`; `_loop()` honours pause flag, flushes error history on rebaseline, tracks rolling RMS (10-frame window), records last issued pulse direction+duration; `_lifecycle_lock` wraps `start()` and `stop()` to prevent TOCTOU; reset of pause/rebaseline on `start()`; 3 new tests in `test_guiding_service.py` (pause suppresses calls, resume restores, rebaseline stops cleanly)

- `smart_telescope/domain/collimation/config.py`: `CollimationConfig` dataclass gains `guiding_camera_role: str = "guide"`, `guiding_exposure_s: float = 2.0`, `guiding_cadence_s: float = 3.0`; `from_dict()` reads all three from TOML; 2 new tests in `test_collimation_guiding.py`

- `smart_telescope/services/collimation/assistant.py`: `__init__` accepts `guiding_service: GuidingService | None` and `guide_cameras: dict[str, CameraPort] | None`; `_guiding_status_dict()` returns `available/state/rms_px/last_pulse`; `status` property includes `"guiding"` key; `_start_guiding()` starts the service using collimation config fields; `_stop_guiding()` stops if running, called in `_run()` finally block; `_with_guiding_paused(fn)` pause→fn→rebaseline+resume wrapper; `_recenter_star()` PulseCenterer without state transition; `_handle_auto_exposure()` calls `_start_guiding()` before transitioning; `_dispatch_user_wait()` calls `_with_guiding_paused(_recenter_star)` before each Remeasure transition; 5 new tests in `test_collimation_guiding.py`

- `smart_telescope/api/collimation.py`: `_get_assistant()` now builds `GuidingService` lazily from collimation config (gracefully falls back to no guiding if guide camera role is absent); imports `get_camera_by_role` from deps

- `smart_telescope/static/index.html`: guide status row `<div id="s4-wiz-guide-row">` inserted after instruction div in wizard card (initially `display:none`)

- `smart_telescope/static/js/collimation.js`: `_updateCollimWizard(s)` renders guide row — shows/hides based on `s.guiding.available`; green/red dot for locked/lost; displays `rms_px` and `last_pulse` direction+duration

- `wiki/index.md`: Guiding section updated with collimation guiding integration plan link and completion summary; Collimation Assistant section unchanged

---

## 2026-05-23 — GUD-002..007 — Guiding pipeline complete

**What changed:**

- `smart_telescope/services/managed_camera.py` (GUD-003): `MailboxFrame` frozen dataclass; `FrameMailbox` with latest-frame drop semantics (`put()` drops unconsumed, `wait_latest()` with monotonic deadline, `dropped_count`); `ManagedCamera` (background daemon thread, `start_stream()` / `stop_stream()`, `pop_stream_error()`, `abort_capture()` on stop); 7 tests in `tests/unit/services/test_managed_camera.py`

- `smart_telescope/services/guide_measurement.py` (GUD-002/004): `CentroidConfig`, `GuideCentroidEstimator` (find-peak→ROI→MAD-noise→saturation→SNR→centroid), `GuideControllerConfig`, `MeasureOnlyGuideController` (deadband, aggressiveness, pulse clamp, sub-deadband suppression), `GuideSourceSelector` (primary/fallback logic, TRANSIENT_BAD + HARD_FAILED trigger fallback), `source_state_from_measurement`; 6 tests in `tests/unit/services/test_guide_measurement.py`

- `smart_telescope/services/guiding_service.py` (GUD-004): `GuidingStatus` (`to_dict()`), `GuidingService` with `from_config()` factory; `_lifecycle_lock` wrapping both `start()` and `stop()` for TOCTOU safety; `started_at` passed as arg to `_loop()`; `_estimator.measure()` wrapped in try/except; `latest is None` increments bad_count; real mount pulses sent when `measure_only=False` with exception swallowed; 6 tests in `tests/unit/services/test_guiding_service.py` (including 2 measure_only=False tests with mock mount)

- `smart_telescope/api/guiding.py` (GUD-006): `POST /api/guiding/start` (202, 409 if running, 422 if no cameras, `RuntimeError` caught on camera connect failure); `POST /api/guiding/stop`; `GET /api/guiding/status`; mount resolved via `rt.get_mount()` (with fallback to None); 4 tests in `tests/unit/api/test_guiding.py`

- `smart_telescope/api/deps.py`, `smart_telescope/runtime.py`: `get_guiding_service()` injectable; `runtime.guiding_service` property (lazy init from config); `shutdown()` and `reset_for_tests()` stop and clear `_guiding_service`

- `smart_telescope/app.py`: `guiding_router` registered after `bias_estimation_router`

- `templates/config.toml`: `[guiding]` section appended with 9 commented fields (primary_role, allow_fallback, fallback_after_bad_frames, max_frame_age_s, centroid_roi_px, min_peak_snr, saturation_fraction, measure_only=true)

- `smart_telescope/static/js/guiding.js`: Guide Monitor card polling JS — `guidingStart()`, `guidingStop()`, `_guidingPollStart()`, `_guidingPollStop()`, `_guidingPoll()`, `_guidingUpdateCard()`; polls every 2 s when running; state badge (IDLE/RUNNING/FAILED), source health badges, pulse summary

- `smart_telescope/static/index.html`: Guide Monitor card added before Connected Cameras section (advanced mode only, `adv-only` class); `guiding.js` loaded after `bias_estimation.js`

- `docs/todo.md`: GUD-002..007 marked done; GUD-008 remains (hardware verification)

- `wiki/index.md`: Guiding section updated with pipeline plan link and implementation summary

---

## 2026-05-23 — requirements ingest: guiding pipeline, OnStep replacement, watchdog, packaging fixes

**Sources:** 10 new files in `resources/hlrequirements/` (ingested 2026-05-23)

**What changed:**

- `pyproject.toml`: `pyserial>=3.5` moved from `[dev]` to production `[project].dependencies` — it is used in `adapters/onstep/mount.py` and `app.py` at runtime, not dev-only
- `tests/unit/services/test_guide_measurement.py`: `pytest.importorskip` guard added — test collection no longer errors when `services.guide_measurement` is absent; 2779 tests collected cleanly
- `docs/todo.md`: updated with serial numbers for all three cameras (CID-006 note); new PKG section (both items done); new GUD section (8 tasks, guiding pipeline); deferred ONSTEP-REPLACE-001 (OnStep adapter replacement, waiting for external party) and WATCHDOG-001/002 (Pi systemd + external heartbeat supervisor)

**New todo sections added:**
- `Build and Packaging` (PKG-001/002) — both complete
- `Guiding Pipeline` (GUD-001..008) — GUD-001..007 ready to implement, GUD-008 hardware-blocked
- `Deferred`: ONSTEP-REPLACE-001 (blocked on external party), WATCHDOG-001/002 (blocked on hardware + systemd migration decision)

**Architecture reference docs ingested (no code changes):**
- `INDI_Steer_pattern.md` — one-adapter-per-device, one-SDK-handle-per-adapter pattern
- `SmartTScope_ToupTek_Device_Handling_Recommendation.md` — device ownership model (AVAILABLE/OWNED_BY_SMARTTSCOPE/EXTERNALLY_BUSY), three operating modes (Full Smart Telescope / Planetary External / Hybrid Safe)

**Hardware serial numbers recorded (for Pi `~/.SmartTScope/config.toml`):**
- `GPCMOS02000KPA = "tp-3-4-23-0547-1367"`, `ATR585M = "tp-4-1-10-0547-157c"`, `G3M678M = "tp-4-2-11-0547-14bc"`

---

## 2026-05-22 — camera_adapter integration + Pi boot fix

**Source:** `resources/camera_adapter` (external module, first sync)

**What changed:**

- `smart_telescope/app.py`: catch-all `@app.exception_handler(Exception)` added — all unhandled 500 errors now return JSON instead of plain text (fixed browser `SyntaxError` on `/api/mount/status`)
- `smart_telescope/config.py`: `CameraSpec` + `CAMERA_SPECS` (dict-valued `[cameras]` TOML support); `CoolingSpec`, `FilterWheelSpec`, `GuidingSpec` dataclasses + parse functions + `COOLING`, `FILTER_WHEEL`, `GUIDING` constants; `_parse_cameras()` updated to handle dict-valued entries without crashing
- `smart_telescope/runtime.py`: `SmartTouptekCamera` code path added in `_build_adapters()` with try/except fallback to `MockCamera`; `_role_cameras`, `_filter_wheel` state; `_validate_camera_role_ownership()`; `get_camera_by_role()` upgraded to use `CAMERA_SPECS`; `get_filter_wheel()` added; shutdown/disconnect/reset updated
- `smart_telescope/adapters/touptek/managed.py`: new file — `SmartTouptekCamera` adapter with capture modes and setup profiles; `connect()` returns `False` (SYNC-OVERRIDE) instead of raising when no device found
- `smart_telescope/adapters/touptek/camera.py`: replaced with camera_adapter version (richer constructor: `camera_id`, `model`, `name`, `capture_mode`, `setup_profile` params)
- `smart_telescope/adapters/touptek/filter_wheel.py`: new — `TouptekFilterWheel` adapter
- `smart_telescope/domain/guiding.py`: new — `GuideFrame`, `GuideMeasurement`, `WouldGuidePulse`, `GuideSourceState`
- `smart_telescope/tools/camera_loadtest.py`, `guide_measuretest.py`: new CLI stress-test tools
- `tests/unit/services/test_guide_measurement.py`: new unit tests (skipped until `services.guide_measurement` is delivered by external party)
- `templates/config.toml`: `[cameras]` section migrated to `[cameras.<role>]` table format; `[camera_offsets]` removed (offsets now inline per camera)
- `scripts/sync_camera_adapter.sh`: new — copies external-owned files on each release, detects drift
- `SYNC.md`: new — tracks sync state, SYNC-OVERRIDEs, pending external requirements
- `docs/superpowers/specs/2026-05-22-camera-adapter-integration-design.md`: integration design spec
- `docs/superpowers/plans/2026-05-22-camera-adapter-integration.md`: implementation plan

**Pi fix:** `smart_telescope/config.py` at git `c525dd6` had `return {role: int(idx) for role, idx in section.items()}` which crashed on dict-valued `[cameras.main]` entries. Pi must `git reset --hard origin/main` then update `~/.SmartTScope/config.toml` to use `[cameras.main]` table format and restart via `bash ~/astro_sw/start.sh`.

---

## 2026-05-21 — COE-001..004 — Camera Offset Estimation Wizard complete

**What changed:**

- `smart_telescope/domain/bias_estimation.py` (COE-001): `ZERO_CLIP_THRESHOLD=0.001`, `BiasFrameStats`, `OffsetSweepPoint` (with `is_safe` property), `BiasEstimationResult` (`recommended_offset`, `safe`, `toml_snippet()`), `analyze_frame()`, `DEFAULT_SWEEP_OFFSETS=[0,5,10,20,30,50,75,100,125,150,200]`; 14 tests in `tests/unit/domain/test_bias_estimation.py`

- `smart_telescope/services/bias_estimation_service.py` (COE-002): `BiasEstimationService.estimate()` — sets gain mode, captures frames at minimum exposure, sweeps offset values, averages stats per offset, restores original offset in `finally`, respects cancel event; 10 tests in `tests/unit/services/test_bias_estimation_service.py`

- `smart_telescope/api/bias_estimation.py` (COE-003): `BiasEstimationRequest` with Pydantic `@field_validator` for gain_mode; `_JobState` registry with thread-safe dict; `POST /api/bias_estimation/start` (202, returns job_id); `GET /api/bias_estimation/status/{job_id}` (RUNNING/DONE/FAILED/CANCELLED + full result on DONE); 5 tests in `tests/unit/api/test_bias_estimation_api.py` (including runtime-restore fixture + optical train wiring); 422 for unknown camera role

- `smart_telescope/static/js/bias_estimation.js` (COE-004): `beLaunchWizard`, `beHideWizard`, `beResetState`, `beStartEstimation`, `bePollStatus`; polls every 500ms; builds sweep table with safe/clipping badges; highlights recommended offset row in green; shows TOML snippet in `<pre>` block on DONE; orange warning when no safe offset found

- `smart_telescope/static/index.html`: Sensor Offset Estimation card added to Stage 5 (before Connected Cameras); `<script src="/static/js/bias_estimation.js">` added

- `wiki/index.md`: "Camera configuration" section added with links to CID/CO/COE plans

- `docs/todo.md`: COE-001..004 marked done with acceptance notes

**Tests:** 44 smoke tests pass; 32 bias estimation tests pass (domain + service + API)

---

## 2026-05-20 — Camera ID Mapping / Camera Offset / Bias Estimation (CID/CO/COE)

**What changed:**
- `docs/todo.md`: Three new P1 sections added — CID (camera ID mapping), CO (camera offset config), COE (camera offset estimation wizard).
- `docs/superpowers/plans/2026-05-20-camera-id-mapping.md`: Full TDD plan for name-based camera config (CID-001..007).
- `docs/superpowers/plans/2026-05-20-camera-offset-config.md`: Full TDD plan for `[camera_offsets]` config + `CameraOffsetService` (CO-001..008).
- `docs/superpowers/plans/2026-05-20-camera-offset-estimation.md`: Full TDD plan for bias-frame offset estimation wizard in Stage 6 (COE-001..006).

**Source documents ingested:**
- `resources/hlrequirements/camera_id list.md`
- `resources/hlrequirements/camera_offset.md`
- `resources/hlrequirements/camera_offset_estimation.md`

---

## 2026-05-19 — POD-010 — Camera role resolution in API endpoints

**What changed:**
- `smart_telescope/api/deps.py`: Added `resolve_camera_index(camera_index, camera_role)` helper — returns `camera_index` when no role given; resolves role via `OpticalTrainRegistry` when provided; raises HTTP 422 for unknown roles.
- `smart_telescope/api/solver.py`: `SolveRequest` accepts optional `camera_role`.
- `smart_telescope/api/calibration.py`: `BiasRequest`, `DarkRequest`, `FlatRequest`, `BpmRequest` accept optional `camera_role`; `GET /api/calibration/match` accepts `camera_role` Query param.
- `smart_telescope/api/histogram.py`: `POST /api/histogram/analyze` accepts `camera_role` Query param.
- `smart_telescope/static/js/setup.js`: Calibration and histogram calls now send `camera_role` directly; `_calSharedParams()` returns `camRole` instead of `camIdx`.
- `smart_telescope/static/js/session.js`: `solveFrame()` sends `camera_role` directly.
- `smart_telescope/static/js/preview.js`: `_fetchAndDrawHistogram()` sends `camera_role` directly.
- `tests/unit/api/test_camera_role_resolution.py`: 11 new tests.
- `docs/todo.md`: POD-004, POD-009, POD-010 marked done.

**Tests:** ≥2688 passed

---

## 2026-05-19 — M5-001 — Guided startup

**What changed:**
- `smart_telescope/static/index.html`: `s1-proceed-btn` now starts `disabled`.
- `smart_telescope/static/js/setup.js`: `connectAll()` enables/disables `s1-proceed-btn` based on `mountOk`; catch block resets `proceedBtn.disabled = true` and `_mountConnected = false` on failure.
- `smart_telescope/static/js/mount.js`: `s1Proceed()` no longer calls `unlockStage(2)` — Stage 2 unlock belongs to `connectAll()` only.
- `tests/unit/api/test_smoke.py`: Added `test_s1_proceed_btn_starts_disabled` (regex-based).
- `docs/todo.md`: M5-001, M5-003, M5-004 marked done.

**Tests:** 44 smoke tests pass

---

## 2026-05-19 — POD-005 — Failure isolation policy

**What changed:**
- `smart_telescope/services/readiness.py`: Added `_capability_flags(items)` static method + 5 new fields to `ReadinessReport` (`can_preview`, `can_goto`, `can_solve`, `can_autofocus`, `can_save`). RED items block the relevant capability; YELLOW = degraded, functional. Updated module docstring and added inline comment to `can_observe` computation.
- `tests/unit/api/test_readiness.py`: Added `TestCapabilityFlags` (12 tests covering all POD-005 isolation scenarios and YELLOW-does-not-block cases).
- `smart_telescope/static/js/setup.js` + `index.html`: Blocked-capability chip row in readiness card; null guard in `_renderReadiness`; chip div hidden when all capabilities are available.
- `docs/todo.md`: POD-005 marked done with formal decision recorded.

**Tests:** 2676 passed

---

## 2026-05-19 — M6-012 — Release notes v0.1

**What changed:**
- Created `docs/release-notes-v0.1.md` covering: milestone status table (M0–M6 + Collimation), all implemented features by milestone, performance targets table, known issues (hardware-blocked and open software), deferred post-MVP scope, and install/upgrade path.
- `docs/todo.md`: marked M6-012 done.
- `wiki/index.md`: added release-notes-v0.1 link under Release readiness.

**Tests:** 2664 passed, 87.56% coverage

---

## 2026-05-19 — BUG-002 — Autogain layout clarification

**What changed:**
- `smart_telescope/static/index.html`: Split the Stage 3 Live Preview controls from one dense row into two rows. Row 1 retains camera settings (Cam/Exp/Gain/Off), display toggles (Str/Hist), Solve, AF, frame count, and camera adapter label. Row 2 is a dedicated "Auto-gain:" row with "Adjust live" checkbox (tooltip clarified), a vertical separator, "Find Best" button, Cancel, and status badge. All element IDs unchanged — no JS edits required.

**Tests:** 43 smoke tests pass

---

## 2026-05-19 — R7-006 — Done-without-evidence report

**What changed:**
- `smart_telescope/domain/milestones.py`: Added `EvidenceGapItem` frozen dataclass (`id`, `priority`, `description`, `milestone`, `mock_tested_by`, `hardware_needed`) and `EVIDENCE_GAPS` registry (8 items: BUG-023/005 P0, BUG-011/012/016/010/013/019 P1, sorted P0 first). Also updated `RISK_REGISTRY` replacing completed M6-003 with M6-012.
- `smart_telescope/api/milestones.py`: Added `GET /api/evidence-gaps` → `{items, count}`.
- `tests/unit/domain/test_milestones.py`: Added `TestEvidenceGaps` (6 tests).
- `tests/unit/api/test_milestones.py`: Added `TestEvidenceGapsEndpoint` (7 tests).

**Tests:** 38 pass

---

## 2026-05-19 — M6-001–006 — Performance targets defined

**What changed:**
- `smart_telescope/domain/performance_targets.py` (new): `PerformanceTarget` + `PerformanceTargets` frozen dataclasses; `TARGETS` singleton with all 6 targets — session duration (6 h), preview latency (≤ 2 s), STOP response (≤ 500 ms), centering accuracy (≤ 30 arcsec), plate-solve success rate (≥ 90%), Pi thermal ceiling (≤ 75°C).
- `smart_telescope/api/performance_targets.py` (new): `GET /api/performance-targets` returns each target as `{value, unit, rationale}`.
- `smart_telescope/app.py`: registered performance_targets router.
- `tests/unit/domain/test_performance_targets.py` (new): 12 tests — field presence, positive values, unit/rationale strings, safety sanity checks (STOP ≤ 1000 ms, Pi < 80°C).
- `tests/unit/api/test_performance_targets.py` (new): 7 tests — HTTP contract, all keys present, positive numbers, unit strings.

**Tests:** 19 pass

---

## 2026-05-19 — R7-005 + M0-008 — Milestone dashboard and risk view

**What changed:**
- `smart_telescope/domain/milestones.py` (new): `MilestoneSummary` frozen dataclass with computed `status` (green/yellow/red); `RiskItem` frozen dataclass; `MILESTONE_REGISTRY` (8 milestones M0–M6 + COL) and `RISK_REGISTRY` (10 open P0/P1 items, P0 first).
- `smart_telescope/api/milestones.py` (new): `GET /api/milestones` returns `{milestones, top_risks}`.
- `smart_telescope/app.py`: registered milestones router.
- `smart_telescope/static/index.html`: "Milestone Dashboard" card added to Stage 1 (below readiness).
- `smart_telescope/static/js/setup.js`: `_renderMilestones()` + `refreshMilestones()` — color-coded progress bars per milestone, top-risk list with priority badges.
- `smart_telescope/static/js/app.js`: `refreshMilestones()` called at page init.
- `tests/unit/domain/test_milestones.py` (new): 16 tests — status logic, registry invariants.
- `tests/unit/api/test_milestones.py` (new): 9 tests — HTTP contract, field presence, sorting.

**Tests:** 25 pass

---

## 2026-05-19 — M6-009 — Storage-full simulation tests

**What changed:**
- `smart_telescope/adapters/disk_storage/storage.py`: `save_image()` and `save_log()` propagate `OSError` (e.g. `ENOSPC`) from the underlying `write_bytes`/`write_text` call; no partial file is left on failure.
- `smart_telescope/workflow/stages.py`: `stage_save()` raises `WorkflowError("save", "Disk full…")` when `storage.has_free_space()` is False; unexpected `OSError` from save calls is wrapped by the runner into `WorkflowError`.
- `tests/unit/adapters/disk_storage/test_disk_storage.py`: Added `TestDiskFullWriteFailure` (3 tests) — ENOSPC propagation for image and log writes, and no-partial-file guarantee.
- `tests/unit/workflow/test_runner_stages.py`: Added `TestRunnerStorageFull` (5 tests) — disk-full failure stage/reason, no image path on disk-full, OSError from save_image wrapped into WorkflowError, partial-save image path preserved when log write fails.

**Tests:** 99 pass

---

## 2026-05-19 — COL-022 — Hardware self-test page

**What changed:**
- `smart_telescope/api/collimation.py`: 3 new endpoints under `/api/collimation/selftest/`: `POST /camera` (captures 1 frame, returns width/height/peak_adu or 503), `POST /mount` (fires guide pulse N/S/E/W 500 ms, validates direction, returns ok or 503), `POST /focuser` (moves ±steps, returns before/after position; returns `ok:false` message when focuser unavailable; 422 on zero steps).
- `smart_telescope/static/index.html`: New "Hardware Self-Test" card before the Collimation Wizard card in Stage 4 — table with Camera/Mount/Focuser rows, test buttons, and per-row result spans.
- `smart_telescope/static/js/collimation.js`: `selftestCamera()`, `selftestMount(dir)`, `selftestFocuser(steps)` async functions; `_stResult()` helper updates result span with green/red colouring; dot turns green on first success.
- `tests/unit/api/test_collimation_selftest.py` (new): 14 tests — 4 camera, 5 mount, 5 focuser; covers ok paths, error paths (503/422), unavailable focuser, and default-body acceptance.

**Tests:** 2599 pass (87% coverage)

---

## 2026-05-19 — M5-013 — Dawn auto-park

**What changed:**
- `smart_telescope/domain/solar.py`: Added `ASTRONOMICAL_DAWN_ALT_DEG = -18.0` constant and `sun_altitude_now(lat, lon)` function (calls `sun_position_now()` → `compute_altaz()`).
- `smart_telescope/services/dawn_watcher.py` (new): `DawnWatcher` background service; polls sun altitude every 60 s; issues `mount.park()` + `device_state.poll_now()` exactly once when alt ≥ −18°; exposes `get_status() → DawnStatus`; thread-safe `start()`/`stop()` lifecycle.
- `smart_telescope/runtime.py`: Added `dawn_watcher: DawnWatcher` field; started in `connect_devices()` using `config.OBSERVER_LAT/LON`; stopped in `shutdown()` and `reset_for_tests()`.
- `smart_telescope/api/dawn.py` (new): `GET /api/dawn` returns sun altitude, is_dawn flag, parked_at_dawn flag, and parked_at UTC timestamp.
- `smart_telescope/app.py`: Registered dawn router.
- `tests/unit/domain/test_solar.py`: Added `TestSunAltitudeNow` (3 tests) and import of `sun_altitude_now`.
- `tests/unit/services/test_dawn_watcher.py` (new): 9 tests covering status before start, park trigger, no-repark guard, stop, idle status, error isolation.

**Tests:** 2585 pass (87% coverage)

---

## 2026-05-19 — R7-001/002/003 — Release readiness checklists; M0 backlog audit

**What changed:**
- `docs/operational-acceptance-checklist.md` (new): 10-section field checklist covering power-on, connect all, readiness dashboard, setup check, solar safety gate, GoTo/plate-solve alignment, autofocus, emergency STOP (< 1 s), preview/stack, and shutdown; includes sign-off table
- `docs/hardware-test-log-template.md` (new): append-only evidence log defining six required evidence items (E-001 STOP during slew, E-002 STOP during focuser move, E-003 shutdown during motion, E-004 reconnect, E-005 setup check, E-006 full workflow); structured entry template with date, commit, steps, result, log extract
- `docs/release-checklist.md` (new): 8-section go/no-go gate with BLOCKER items; covers backlog gate (all P0/P1 closed or deferred), hardware evidence gate (all 6 E-items pass), operational acceptance, test suite (≥80% coverage), clean install, performance targets, documentation, product-owner sign-off table and deferred items register
- `wiki/index.md`: new "Release readiness" section linking all three documents
- `docs/todo.md`: R7-001/002/003 marked done; M0-002 through M0-007 marked done (backlog audit confirmed all work already completed)

---

## 2026-05-19 — BUG-004 + BUG-021 — Histogram zoom and bar rendering fixes

**What changed:**
- `smart_telescope/domain/histogram.py`: `histogram_bins_focused` no longer applies an `adc_max×0.05` floor to `adu_hi`. Minimum is now 1000 ADU (was up to 3276 for 12-bit-in-16-bit cameras). Dim images (p99.9 = 200 ADU) now get a 0–1000 ADU histogram instead of 0–3276, filling the canvas 3× better.
- `smart_telescope/static/js/preview.js`: `showHistogram()` draws `0–Xk ADU · N ADU/bin` as a small text overlay in the canvas top-right corner (BUG-004: block size above). Bar rendering now uses `Math.max(1, Math.round(hRaw))` when `binCounts[i] > 0` — every non-zero bin shows at least 1px (BUG-021). New `_updateLowLabel()` helper updates `s3-hist-low-label` element with the real bin size on each draw.
- `smart_telescope/static/index.html`: Low histogram label div given `id="s3-hist-low-label"`; hardcoded wrong "5 ADU/bin" text replaced with plain "pedestal detail" (JS fills in the real value).
- `tests/unit/domain/test_histogram.py`: 5 new tests in `TestHistogramBinsFocused` — return shape, dark frame minimum, dim frame tighter zoom, bright frame clips to adc_max, n_bins parameter.

**Tests:** 2570 pass (87% coverage)

---

## 2026-05-18 — R6-007 — FocusRunConfig policy object

**What changed:**
- `smart_telescope/domain/autofocus.py`: Added `FocusRunConfig` dataclass with fields `range_steps`, `step_size`, `exposure_s`, `backlash_steps`, `skip`; `to_params()` converts to `AutofocusParams`
- `smart_telescope/workflow/stages.py`: `StageContext` 5 flat autofocus fields replaced with `focus_config: FocusRunConfig`; `stage_autofocus` and `stage_stack` (mid-refocus) both call `ctx.focus_config.to_params()` — eliminating the duplicate `AutofocusParams` construction; 4 unused `_types.py` constant imports removed
- `smart_telescope/workflow/runner.py`: `VerticalSliceRunner.__init__()` 5 flat params replaced with `focus_config: FocusRunConfig | None = None`; refocus-tracker condition uses `focus_config.skip`
- `smart_telescope/api/session.py`: Imported `FocusRunConfig`; `session_run()` bundles 5 Query params into a `FocusRunConfig` before passing to runner (HTTP API shape unchanged)
- `tests/conftest.py`: `make_stage_ctx` and `make_unit_runner` accept `focus_config: FocusRunConfig | None = None` instead of 5 flat params
- `tests/unit/domain/test_focus_run_config.py`: 12 new tests — defaults, `to_params()` field mapping, `skip` exclusion, invalid step raises
- 2 updated tests in `test_runner_stages.py`: use `FocusRunConfig` instead of flat params

**Tests:** 2565 pass (87% coverage)

---

## 2026-05-18 — BUG-013 — Mount connect retry + setup check actionable message

**What changed:**
- `smart_telescope/adapters/onstep/mount.py`: `connect()` now retries `:GVP#` up to 3 times (300 ms + buffer flush each attempt) before concluding the port is not OnStep. Handles the field-observed failure pattern where a stale `'1'` ACK from `disable_tracking()` (left from a previous session) caused the old single-retry to exhaust and close the serial port, leaving `_serial = None` and all subsequent state queries returning `UNKNOWN`.
- `smart_telescope/static/js/setup.js`: Mount RA and DEC setup check steps now show "mount not connected — use Connect All to reconnect" instead of the cryptic "state is 'unknown' — skipped" when the mount is unavailable.
- `tests/unit/adapters/onstep/test_onstep_mount.py`: 5 new tests in `TestConnectRetry` — first-attempt success (no sleep), stale-ACK retry succeeds, all-retries-exhausted returns False, empty response accepted, doubled product string accepted.

**Source:** `resources/hlrequirements/Items_to_fix_20260514.txt` BUG-013

**Tests:** 2553 pass (87% coverage)

---

## 2026-05-18 — BUG-010 — Focuser connect retry (serial buffer stale bytes)

**What changed:**
- `smart_telescope/adapters/onstep/focuser.py`: `connect()` now retries `:FA#` up to 3 times (300 ms apart) before concluding focuser unavailable. Handles stale bytes left in the serial input buffer by `mount.connect()` (`:GVP#` product query + `disable_tracking()`) that caused the first `:FA#` reply to be garbled.
- `tests/unit/adapters/onstep/test_onstep_focuser.py`: 4 new tests in `TestConnectRetry` — first-attempt hit (no sleep), 0→1 retry, all-retries-exhausted, empty-reply→available.

**Source:** `resources/hlrequirements/Items_to_fix_20260514.txt` BUG-010

**Tests:** 2548 pass (87% coverage)

---

## 2026-05-18 — BUG-011/012/016 — Park/unpark state propagation fix

**What changed:**

- `smart_telescope/services/device_state.py`: Added `self._mount` attribute (set in `start()`, cleared in `stop()`). Added `poll_now()` — runs `_poll_once()` synchronously on demand; no-op before `start()` or after `stop()`.

- `smart_telescope/services/mount_operations.py`: `park_sequence()` calls `device_state.poll_now()` after issuing the park command, before `wait_for_mount_state`. `unpark_sequence()` calls `device_state.poll_now()` after `mount.unpark()`, before `wait_while_mount_state`; timeout extended from 3 s → 5 s.

- `smart_telescope/runtime.py`: `connect_devices()` calls `self.device_state.poll_now()` immediately after `device_state.start()` — initial cache populated from startup, eliminating the 2 s gap (BUG-012).

- `smart_telescope/static/js/mount.js`: Park poll loop extended from 10×500 ms to 60×1000 ms (60 s total). Unpark loop extended to 20×500 ms (10 s). Both loops use a single `maxIter`/`delayMs` variable so the change is readable.

- `tests/unit/services/test_device_state.py`: Added `TestPollNow` class (5 tests) — updates cache immediately, reflects state change, handles exception gracefully, no-op before start, no-op after stop.

**Test result:** 2544 passed, coverage 87%.

---

## 2026-05-18 — BUG-005 + M5-005 — Crash isolation tests + solar gate closure

**What changed:**

- `tests/unit/api/test_bug005_isolation.py` (new, 10 tests): Explicit proof of isolation invariants — `TestStopBypassesCoordinatorLock` (STOP calls `mount.stop()` directly while coordinator is locked by a background thread); `TestSessionCrashReleasesResources` (mount/focuser/camera resources released from JobManager when runner thread raises WorkflowError); `TestStopWorksAfterSessionCrash` (mount STOP and focuser STOP both return 200 after session crash); `TestMountCommandsAfterSessionCrash` (mount goto and new session start return non-409 after crash).

- `docs/todo.md`: BUG-005 marked done; M5-005 marked done (implementation already existed across all four GoTo entry points with tests in test_mount.py and test_session.py).

**Test result:** 2539 passed, coverage 87%.

---

## 2026-05-18 — R5-011 — Hardware mode in readiness API + UI

**What changed:**

- `smart_telescope/runtime.py`: Added `_hardware_mode: str = "mock"` attribute to `RuntimeContext.__init__`; `_MODE_RANK` dict and mode assignment in `_build_adapters()` — each adapter branch sets `cam_mode`/`mnt_mode` ("real", "simulator", "mock") and the overall mode is the worst of both (mock > simulator > real) via `max(..., key=_MODE_RANK)`; `hardware_mode` property added; `reset_for_tests()` resets to "mock".

- `smart_telescope/services/readiness.py`: `ReadinessReport` gains `mode: str` field; `_get_hardware_mode()` reads from `RuntimeContext.hardware_mode` with fallback to "mock"; `_check_mode(mode)` returns a `ReadinessItem` (GREEN for real, YELLOW for simulator/mock with repair guidance); `can_observe` now requires both `overall != RED` and `mode == "real"`.

- `smart_telescope/static/index.html`: Added `<span id="s1-readiness-mode">` badge element in the readiness card header (hidden by default, shown/colored by JS).

- `smart_telescope/static/js/setup.js`: `_renderReadiness()` now shows the mode badge (REAL/SIMULATOR/MOCK) with color-coded border next to the overall badge.

- `tests/unit/api/test_readiness.py`: Added `TestHardwareMode` class (8 tests — mode field in API, real mode allows observe, mock/simulator blocks can_observe, mode item in items list, repair guidance, RuntimeContext defaults, reset); updated `test_yellow_overall_if_no_red_but_some_yellow` to patch `_get_hardware_mode` to "real".

- `docs/todo.md`: R5-011 marked done.

**Test result:** 2529 passed, coverage 87%.

---

## 2026-05-18 — R0-011 / R4-008 — Runner lifecycle + session optical-train aware

**What changed:**

- `smart_telescope/workflow/runner.py`: Removed `mount.disconnect()`, `camera.disconnect()`, `focuser.disconnect()` from `VerticalSliceRunner.run()` `finally` block. Runtime shutdown sequence (`RuntimeContext.shutdown()`) now owns all adapter teardown. Hardware stays live after a session completes or fails, enabling post-session diagnostics, retry, and dawn auto-park (M5-013).

- `smart_telescope/api/session.py`: Replaced hard-coded `{"camera:0", "mount", "focuser"}` resource claim with optical-train-aware resolution. `session_run` now injects `OpticalTrainRegistry` via `Depends(deps.get_optical_train_registry)`, calls `registry.main()`, and derives `camera_resource = f"camera:{main_train.camera_index}"`. Falls back to `"camera:0"` when no main train is configured. Camera adapter resolved via `deps.get_camera_by_role(main_train.camera_role)`.

- `tests/unit/workflow/test_focuser.py`: Updated `test_run_disconnects_focuser_on_completion` → `test_run_does_not_disconnect_focuser_on_completion` to assert the new contract.

- `tests/unit/api/test_r4_role_camera.py`: Added `TestSessionOpticalTrainAware` with 3 tests (main train at index 1 conflicts on `camera:1`; `camera:0` pre-claim does not conflict with main-at-1; empty registry falls back to `camera:0`). Imports extended with `CatalogObject`, `MountPort`, `get_runtime`.

- `docs/todo.md`: R0-011 and R4-008 marked done.

**Test result:** 2521 passed, coverage 87%.

---

## 2026-05-17 — Architect review integrated into docs/todo.md

**Source:** `resources/hlrequirements/development-state-review-2026-05-17.md`

**What changed in `docs/todo.md`:**

- M0-001 marked done: `docs/todo.md` is the established authoritative backlog.
- R0-011 added: change `VerticalSliceRunner.run()` to not disconnect adapters in `finally`; keep hardware live post-session (P1 Runtime).
- R4-008 added: make guided session optical-train aware — derive `camera:N` from selected train, remove `camera:0` hard-code (P1 Runtime).
- R5-011 added: explicit hardware mode field (`real`/`simulator`/`mock`) in readiness API and UI; `can_observe=true` blocked for mock/simulator mode (P1 Runtime).
- R6-007 added: `FocusRunConfig` policy object; clean focus sub-boundary (P2 Runtime).
- M5-005 enhanced: acceptance criteria now require solar exclusion at ALL GoTo entry points (direct GoTo, catalog launch, guided session, sky slew).
- M5-013 added: dawn auto-park at astronomical dawn; hardware stays connected after park (P2 Product).
- POD-005 enhanced: guidance examples added (ASTAP missing → observing blocked only; mount serial fail → preview + diagnostics still available).
- POD-007 answered: Pi hardware/app logs + saved FITS + session JSON log.
- POD-008 updated: minimal collimation wizard UI shell is part of MVP demo; deep algorithm phases deferred.
- POD-010 added: camera index in API request bodies — policy decision pending.
- Review header and source reference added to `docs/todo.md`.

**Reviewer note:** P1-001 finding ("pyproject.toml missing") was a reviewer environment issue — `pyproject.toml` exists at workspace root and `pip install -e .[dev]` was not run in the reviewer's environment. Not added as an action item.

---

## 2026-05-17 — R6-003 / R6-004 — JS module split + shared API client

**What changed:**

- `smart_telescope/static/index.html`: reduced from 6216 to 1847 lines (HTML/CSS only). The 4376-line JavaScript block replaced with 8 `<script src="/static/js/...">` tags. No logic changed — same code, now in separate files.

- `smart_telescope/static/js/` (new directory, 8 files):
  - `api.js` (87 lines, R6-004): `escHtml`, `_ERROR_PATTERNS`, `friendlyError`, `setStatus`, `apiPost` — shared fetch/error-handling layer, loaded first.
  - `app.js` (179 lines): global state, advanced mode, stage navigation, clock, `initSiteConfig`, init block — loaded last so it can call all other modules.
  - `mount.js` (721 lines): mount strip, mount card, mount actions, guide controls, polar alignment.
  - `collimation.js` (274 lines): collimation wizard UI, overlay drawing.
  - `focuser.js` (375 lines): focuser card, focuser actions, exposure controls, camera/train loading.
  - `preview.js` (954 lines): preview WebSocket, histogram canvas, autogain, guide autogain, Bahtinov overlay.
  - `session.js` (496 lines): session pipeline strip, guide monitor, target selection.
  - `setup.js` (1305 lines): readiness, health card, catalog, calibration, cooling, setup check, cameras, sky elevation, camera card.

- `smart_telescope/app.py`: added `StaticFiles` mount at `/static`.
- `pyproject.toml`: package-data updated to include `static/js/*`.
- `tests/unit/api/test_smoke.py`: 4 new tests verifying all 8 JS modules are served (200) and index.html references them. 43 tests total pass.

---

## 2026-05-17 — R6-006 / UX3-004 — API smoke tests + unsupported-control confirmation

**What changed:**

- `tests/unit/api/test_smoke.py` (R6-006 — new, 39 tests):
  - `TestSetupSmoke` (8 tests): `GET /` returns 200 HTML with correct title; `/api/readiness` returns 200 with `overall`/`items` in valid colour.
  - `TestMountSmoke` (11 tests): `/api/mount/status` returns `state`/`stale`/`watchdog_warning`/`last_command*` fields; state serialised lowercase; stale=false for fresh observation; watchdog=null with no alert. `/api/mount/config` returns location fields.
  - `TestFocuserSmoke` (7 tests): `/api/focuser/status` returns `position`/`available`/`moving`/`max_position`; available=True → real position; available=False → zeros.
  - `TestEmergencyStopSmoke` (8 tests): `POST /api/emergency_stop` always 200; `mount_stopped` true/false on success/error; `session_stopped` false when idle; `mount.stop()` called once.
  - `TestPreviewSmoke` (4 tests): optical trains list endpoint, version endpoint, catalog endpoint all respond.

- `docs/todo.md`: R6-006 marked done; UX3-004 confirmed done (already implemented via BUG-009/M3-004).

---

## 2026-05-17 — M1-004 — Hardware watchdog for stuck SLEWING

**What changed:**

- `smart_telescope/services/device_state.py`:
  - Added `_WATCHDOG_SLEW_S = 120.0` and `_WATCHDOG_COOLDOWN_S = 30.0` module constants.
  - `DeviceStateService.__init__`: added `_watchdog_warning` and `_watchdog_fired_at` fields.
  - `record_command()`: clears `_watchdog_warning` and `_watchdog_fired_at` on every new command.
  - `get_watchdog_warning()`: new public accessor (thread-safe).
  - `_poll_once()`: calls `_check_watchdog_locked()` inside the lock block after updating state.
  - `_check_watchdog_locked()`: fires a warning if mount stays `SLEWING` beyond `_WATCHDOG_SLEW_S`; suppresses repeated logs within `_WATCHDOG_COOLDOWN_S`; clears automatically when state leaves `SLEWING`.

- `smart_telescope/api/mount.py`: Added `watchdog_warning: str | None = None` to `MountStatus`; populated from `device_state.get_watchdog_warning()` in `mount_status()`.

- `smart_telescope/static/index.html` (`mountCard()`): Added yellow warning banner rendered when `data.watchdog_warning` is non-null.

- `tests/unit/services/test_device_state.py`: 4 new watchdog tests — below-threshold (no warning), above-threshold (fires), clears on state change, clears on new command. All 34 tests pass.

- `docs/todo.md`: M1-004 marked done.

---

## 2026-05-17 — COL-020/021, BUG-018/020, M4-004, UX4/UX5 — Wizard UI and logging fixes

**What changed:**

- `static/index.html` — Collimation Wizard panel (COL-020):
  - Wizard card added to Stage 4 above the two-column layout: 5-phase strip (Prepare/Acquire/Rough/Fine/Validate), instruction text, recommendation block, state badge.
  - Contextual controls: Start → Pause/Resume/Cancel → Remeasure|Finish Phase|Next → Accept|Adjust More → Reset.
  - Star list click in `select_star` state routes to `collimSelectStar()` → `/api/collimation/next {ra, dec}`.
  - Status polled every 2 s via `_startCollimPoll()` when session is active; auto-stops when terminal.
  - `_refreshCollimWizardOnce()` called in `goToStage(4)` to restore wizard state after navigation.

- `static/index.html` — Collimation overlay drawing (COL-021):
  - `_drawCollimOverlay(d)` renders on `s4-bahtinov-svg`: donut outer ring (blue), inner hole (green), error-vector red arrow; Bahtinov crossing-point crosshair (red); overlay fetched from `/api/collimation/overlay` alongside status poll.

- `static/index.html` — Advanced Mode (UX4-001/002/003):
  - `.adv-only { display: none !important; }` / `body.advanced-mode .adv-only { display: flex !important; }`.
  - "Advanced" toggle in header; mount Home/Unpark/Park/Tracking and focuser nudge/Move-To hidden in beginner mode.

- `static/index.html` — Diagnostics link in errors (UX5-005):
  - `setStatus(..., true)` appends "→ Setup & Diagnostics" link on every error banner.

- `services/mount_operations.py` (BUG-018): Added `_log.info("Mount unpark issued")` in `unpark_sequence()`.
- `api/focuser.py` (BUG-020): Added `_log.info("Focuser nudge request: delta=%d", body.delta)` at entry of `focuser_nudge()`.
- `docs/todo.md`: M4-004, BUG-018, BUG-020, COL-020/021 marked done.

**Tests:** 2471 passed, 0 failed. Coverage 87%.

---

## 2026-05-17 — UX3-003, UX4-001/002/003, UX5-005 — Advanced mode and diagnostics link

**What changed:**

- `static/index.html` — Advanced Mode toggle (UX4-001/002/003):
  - Added `.adv-only { display: none; }` + `body.advanced-mode .adv-only { display: flex; }` CSS.
  - "Advanced" button in header toggles `body.advanced-mode` class; state persisted in `localStorage['tsc_advanced_mode']`.
  - `_applyAdvancedMode()` called at page init to restore prior session state.
  - `mountCard()`: Home / Unpark / Park / Enable Tracking / Disable Tracking wrapped in `.adv-only` span. Stop always visible.
  - `focuserCard()`: Nudge buttons (±1000/±100/±10) and Move To row wrapped in `.adv-only`. Autofocus and Stop always visible.

- `static/index.html` — Diagnostics link in errors (UX5-005):
  - `setStatus(id, msg, true)` now appends a "→ Setup & Diagnostics" link calling `goToStage(1)` after every error message.

- UX3-003 confirmed done: camera hardware IDs / serial numbers displayed only in `cameraCard()` (Stage 6 scan). All main UI selects and labels use optical train role names.

---

## 2026-05-17 — R6-001/002 Service extraction

**What changed:**

- `services/cooling.py` (new, R6-001): `CoolingService` extracted from
  `api/cooling.py`. Owns `_Session` dataclass, threading lock, polling loop,
  `_stop_session` (with lock-release during join to prevent deadlock).
  Public API: `start(camera, camera_index, target_c)`, `stop()`,
  `get_status() → CoolingStatus`.

- `api/cooling.py` (R6-002): Reduced from 251 → 86 lines. Now a thin wrapper:
  validate TEC capability, call `CoolingService`, map `CoolingStatus` to
  response model. `_reset()` delegates to `svc.stop()`.

- `services/mount_operations.py` (new, R6-001): Mount orchestration module with
  `MountSlewingError` exception and five sequence functions:
  `safe_goto`, `unpark_sequence`, `track_sequence`, `park_sequence`,
  `home_sequence`. Accepts domain-level objects; raises domain exceptions
  (no HTTP concerns).

- `api/mount.py` (R6-002): `_safe_goto`, `mount_unpark`, `mount_track`,
  `mount_home`, `mount_park` endpoints now delegate to `mount_operations` and
  map domain exceptions to HTTP. `Time` / `is_solar_target` imports kept at
  the API level to preserve existing test patch targets.

- `runtime.py`: `CoolingService` added to `__init__`, `shutdown()`, and
  `reset_for_tests()`.

- `api/deps.py`: Added `get_cooling_service()`.

- `tests/unit/services/test_cooling_service.py` (new): 21 tests covering
  idle state, start/stop lifecycle, restart, polling, and thread safety.

- `tests/unit/services/test_mount_operations.py` (new): 22 tests covering
  safe_goto, unpark_sequence, track_sequence, park_sequence, home_sequence —
  including domain exception propagation and coordinator conflict detection.

**Tests:** 2471 passed, 0 failed. Coverage 87%.

---

## 2026-05-17 — R1-006, R1-008/009, BUG-002b, BUG-015 (continued)

**What changed:**

- `services/device_state.py` (R1-006): `record_command()` now returns a
  sequential command ID (`cmd-NNNN` format). Added `_cmd_counter` and
  `_last_command_id` to `__init__`. Both `record_command()` and
  `record_command_error()` emit structured `key=value` log lines including the
  command ID for log correlation. New `get_last_command_id()` method exposes the
  last ID to callers.

- `tests/unit/services/test_device_state.py` (R1-006): 7 new tests covering
  ID format, uniqueness, sequential ordering, `get_last_command_id()` initial
  state and match, and caplog assertions for both `record_command` and
  `record_command_error`. All 30 device-state tests pass.

- `adapters/onstep/serial_bus.py` (R1-008): New `OnStepSerialBus` class owns
  the `serial.Serial` object and threading lock previously private to
  `OnStepMount`. Exposes `send()`, `raw_send()`, `write_bypass()`.

- `adapters/onstep/mount.py` (R1-009): Replaced `self._serial`/`self._lock`
  with `self._bus = OnStepSerialBus()`. Added `_serial` property (getter/setter)
  proxying to `self._bus._serial` for backward compatibility with existing tests.
  Added `serial_bus` property for consumers.

- `adapters/onstep/focuser.py` (R1-009): Constructor now accepts
  `OnStepSerialBus` instead of `OnStepMount`. All serial I/O goes through the
  bus directly — no access to mount private members.

- `runtime.py` (R1-009): Updated `OnStepFocuser(mount)` → `OnStepFocuser(mount.serial_bus)`.

- `api/autogain.py` (BUG-002b): `get_status()` now returns
  `AUTO_GAIN_CANCELLED` when `job.cancelling=True` even if the worker completed
  with a non-CANCELLED result before seeing the cancel flag (cancel race fix).

- `static/index.html` (BUG-015): Mount Home/Unpark/Park/Stop buttons wrapped
  in a `flex-wrap:nowrap` span to prevent wrapping into multiple rows on narrow
  viewports.

- `tests/unit/services/test_pipeline_wiring.py`: Added missing `_donut_camera()`
  helper (was referenced but never defined — pre-existing `NameError`).

**Tests:** 2436 passed, 0 failed.

---

## 2026-05-17 — BUG-019, BUG-022, R4-001..004

**What changed:**

- `api/focuser.py` (BUG-019): Moved the 300 ms started-check sleep outside
  `coordinator.focuser_command()` lock.  The lock is now held only for the
  serial exchange (~50-100 ms), so rapid nudge presses queue behind the command
  issuance rather than the check.  Removed the now-redundant
  `_check_focuser_started` background thread and the `threading` import.

- `static/index.html` (BUG-022):
  - Added `mountGotoAndCenter()` function — previously the GoTo card's
    Center button called this function which was never defined, causing a
    `ReferenceError` on every click.
  - Updated `onPreviewCamChange(idx)` to stop and restart the preview
    WebSocket when the camera is changed, preventing "WebSocket data transfer
    error" when autogain runs after a camera switch.

- `config.py` (R4-003): Added `focuser` and `pixel_scale_arcsec` fields to
  `OpticalTrainSpec`; updated `_parse_optical_trains` to read them.

- `services/optical_train_registry.py` (R4-001/002): New `OpticalTrain`
  dataclass and `OpticalTrainRegistry` class.  `from_config()` loads trains
  from the TOML config, validates telescope and camera-role references,
  computes effective focal length (telescope × reducer_factor), and derives
  pixel scale from camera model profiles or falls back to the global
  `PIXEL_SCALE_ARCSEC`.

- `runtime.py` + `api/deps.py` (R4-003): `RuntimeContext.get_optical_train_registry()`
  builds the registry lazily; `deps.get_optical_train_registry()` exposes it as
  a FastAPI dependency.

- `api/optical_trains.py` + `app.py` (R4-003): New `GET /api/optical_trains`
  and `GET /api/optical_trains/{name}` endpoints listing all configured trains.

- `templates/config.toml`: Documented `focuser` and `pixel_scale_arcsec` fields
  in the optical_trains example sections.

- `tests/unit/services/test_optical_train_registry.py`: 28 tests covering
  3-train and 2-train setups, reducer scaling, explicit vs computed pixel scale,
  validation errors (unknown telescope, unknown camera role, multiple errors),
  and all query methods.

---

## 2026-05-16 — Collimation Phase 13 — Replay and Test Infrastructure

**What changed:**

- `smart_telescope/services/collimation/frame_factories.py` (NEW): `gaussian_star(H, W, cx, cy, fwhm_px, peak_adu, bg_adu)` — Gaussian PSF at given centre/FWHM; `donut_ring(H, W, outer_cx, outer_cy, outer_r, inner_r, error_x, error_y, ...)` — bright ring with sigmoid-smoothed inner hole offset for collimation error simulation; `focus_sequence(...)` — helper to build a list of frames with varying FWHM.
- `smart_telescope/adapters/replay/camera.py` (UPDATED): Added `ReplayCameraAdapter(CameraPort)` alongside existing `ReplayCamera`. Serves in-memory NumPy float32 arrays as `FitsFrame` objects; supports `cycle=True/False`, `reset()`, `frame_index` property, all required `CameraPort` abstract methods.
- `smart_telescope/services/collimation/assistant.py` (UPDATED): `_handle_final_refocus` wired to real `FWHMFocusController` — captures frame, normalises, detects star FWHM, drives `CollimationFocuserControl.move_focus_relative`, records focus status in session report builder, transitions to `MASKLESS_VALIDATION` on convergence, `FAILED` on star lost.
- `tests/unit/services/test_frame_factories.py` (NEW): 17 tests — shape/dtype/peak-location/background for `gaussian_star`, shape/dtype/ring-brightness/background/error-offset/symmetry for `donut_ring`, length/element-type for `focus_sequence`, 3 round-trip tests: detect_star can detect gaussian frames, reports reasonable FWHM, reports correct position.
- `tests/unit/services/test_replay_camera.py` (NEW): 14 tests — empty-frames raises, connect, bit-depth; first-frame pixels, ordering, frame-index increment, exposure-seconds; cycling, exhaustion-raises, reset; exposure/gain setters, logical-name, serial, temperature.
- `tests/unit/services/test_state_machine.py` (NEW): 35 tests — initial state; all valid forward transitions (idle→precheck, precheck→select_star, rough→donut, final→validation, validation→complete/fine); invalid transitions (raises InvalidTransitionError, error message contents); pause/resume/reset (stores prev state, restores on resume, clears prev, raises in idle/terminal/non-paused); predicates (is_terminal, is_waiting_for_user, set membership); instruction text for all states.
- `tests/unit/services/test_assistant_replay.py` (NEW): 18 integration tests — initial idle state, start transitions, double-start raises, cancel resets, retry after complete; full flow reaches COMPLETE, state sequence through all USER_WAIT states, non-terminal during flow, report fields; advance from idle raises, missing coordinates stays in select_star, validation reject returns to fine; pause sets paused, resume restores, is_paused flag; final refocus records FWHM, reaches MASKLESS_VALIDATION.
- `docs/todo.md`: COL-130, COL-131 marked done; last-updated line updated.
- Test suite: 2358 tests, all pass, 87% coverage.

---

## 2026-05-16 — Collimation Phase 12 — Validation and Report

**What changed:**

- `smart_telescope/services/collimation/fwhm_focus.py` (NEW): `FWHMFocusController` implements maskless hill-climb refocus (COL-120). Algorithm: (1) Probe — try +coarse_step; if not improved try −coarse_step; if neither return "max_steps". (2) Coarse scan in improving direction until N consecutive non-improving steps. (3) Backtrack to best-FWHM position. (4) If scan direction ≠ `final_approach_direction`, insert one overshoot then one correction to eliminate backlash bias. Returns `MasklessFocusResult(reason, quality, initial_fwhm_px, best_fwhm_px, final_fwhm_px, steps_taken, frame_count)`. Quality tiers: "excellent" (≤excellent_fwhm_px), "good" (≤good_fwhm_px), "poor" (converged but above good), "failed" (non-converged).
- `smart_telescope/services/collimation/maskless_validator.py` (NEW): `MasklessValidator.assess(donut, jitter_px)` evaluates collimation quality after mask removal (COL-121). Computes `error_ratio = error_magnitude_px / mean(outer_ring.radius)`. Status: "complete" (ratio ≤ good), "acceptable_with_warning" (ratio ≤ fallback), "seeing_limited" (jitter above threshold), "failed" (above fallback or low confidence). Returns `ValidationReport(status, donut_error_px, donut_error_ratio, is_collimated, confidence, warnings)`.
- `smart_telescope/services/collimation/session_report.py` (NEW): `SessionReportBuilder` accumulates session data via `set_optical_train`, `set_camera`, `set_selected_star`, `record_rough_start/end`, `record_fine_start/end`, `record_focus_status`, `record_seeing`, `record_final_result`, `mark_cancelled`; `build()` returns immutable `CollimationSessionReport`. Report provides `to_dict()` (JSON-serialisable) and `to_text()` (human-readable ASCII summary). Overall status mapped from validation status (COL-122).
- `smart_telescope/services/collimation/assistant.py`: `CollimationAssistant.report` property now returns builder output merged with runtime state; `_new_report_builder()` helper initialises builder from config; builder reset on `start()`, cancelled on `cancel()`.
- `tests/unit/services/test_fwhm_focus.py` (NEW): 22 tests — result fields, star-lost (immediate/probe/scan), probe forward/backward direction, max_steps (no improving direction), cancellation, step/frame accounting, final-approach overshoot (inserted when direction differs) and no-overshoot (when direction matches), quality tiers (excellent/good/poor).
- `tests/unit/services/test_maskless_validator.py` (NEW): 22 tests — report fields, complete (below good ratio), acceptable_with_warning, failed (above fallback), low-confidence failure, seeing-limited status, seeing warning text, elliptical ring mean-radius calculation.
- `tests/unit/services/test_session_report.py` (NEW): 29 tests — all report fields, timing, focus fields, overall status mapping (all 5 variants), cancellation override, warnings propagation, to_dict keys, to_text content (status, profile, FWHM, star name), minimal builder defaults.
- `docs/todo.md`: COL-120, COL-121, COL-122 marked done; last-updated line updated.
- Test suite: 2267 tests, all pass, 84% coverage.

---

## 2026-05-16 — Collimation Phase 11 — Fine Focus and Fine Collimation

**What changed:**

- `smart_telescope/domain/collimation/processing/spike_decomposition.py` (NEW): `decompose_spike_errors(lines)` treats each of the 3 spike lines as the "middle" in turn, computing its signed distance from the intersection of the other two. Common focus error = mean of 3 sector errors. Per-sector residuals = error_i − common. Returns `SpikeErrorDecomposition(sector_errors_px, common_focus_error_px, residuals_px, max_residual_px, rms_residual_px)`. Key correctness insight: when three lines are concurrent at any point, all sector errors = 0 (models perfect focus at any reference position).
- `smart_telescope/services/collimation/fine_focus.py` (NEW): `FineFocusController` polls a `get_error: Callable[[], float | None]` callable (common focus error in px) and a `move_focuser: Callable[[int], None]` step function. Coarse steps until within `coarse_threshold_px`, then fine steps. At the coarse→fine transition, if the natural direction differs from `final_approach_direction`, one overshoot step is inserted so subsequent convergence comes from the correct side (backlash compensation). Returns `FineFocusResult(reason, initial_error_px, final_error_px, steps_taken, frame_count)`.
- `smart_telescope/services/collimation/fine_collimation_advisor.py` (NEW): `FineCollimationAdvisor.recommend(residuals_by_screw, smoothed)` selects the screw with the largest `|residual_px|`, determines CW/CCW direction from residual sign, and size (MEDIUM if ratio ≥ 1.5× target, else SMALL). Blocked if `seeing_limited` or `confidence < threshold` or all residuals within target. Also provides `align_residuals_to_screws(decomp, lines, calibration)` helper.
- `smart_telescope/services/collimation/contradiction_detector.py` (NEW): `ContradictionDetector.assess(smoothed, decomposition)` checks 4 indicators: (1) jitter > seeing_threshold, (2) |common_focus_error| > focus_target, (3) confidence < threshold, (4) max_residual increased since last call (stateful). Returns `ContradictionAssessment(has_contradiction, conflicting_indicators, stop_guidance, recommended_action, confidence)`. `.reset()` clears state for a new session.
- `tests/unit/domain/collimation/test_spike_decomposition.py` (NEW): 16 tests — fields, 3-value tuples, perfect collimation (zero errors/residuals/common), concurrent at non-origin (models pure defocus), single-sector shift (worst index, positive max_residual, rms ≤ max), residuals sum-to-zero invariant, residual = error − common, raises on wrong line count.
- `tests/unit/services/test_fine_focus.py` (NEW): 18 tests — result fields, convergence, initial error, star lost (first/mid), cancel, max steps, coarse/fine step usage, direction from error sign, final approach overshoot and no-overshoot.
- `tests/unit/services/test_fine_collimation_advisor.py` (NEW): 18 tests — no-recommendation (within target, seeing-limited, low confidence, empty), worst screw selection (positive/negative), turn direction, adjustment size (small/medium/never-large), confidence, reason string.
- `tests/unit/services/test_contradiction_detector.py` (NEW): 14 tests — no contradiction, seeing-limited, focus drift, low confidence, residuals worsening, no-worsening first call, reset, recommended action, confidence bounds.
- `docs/todo.md`: COL-110, COL-111, COL-112, COL-113 marked done.
- Test suite: 2194 tests, all pass.

---

## 2026-05-16 — Collimation Phase 10 — Tri-Bahtinov Fine Collimation Foundation

**What changed:**

- `smart_telescope/domain/collimation/processing/spike_detection.py` (NEW): `detect_spikes(processed, ref_center, analyzer?)` wraps `BahtinovAnalyzer.analyze()` to produce a `SpikeDetectionResult`. Reasons: "ok" (3 lines found → `SpikeMeasurement` built), "too_few_spikes" (analyzer raised `ValueError`), "no_signal" (zero confidence). Accepts an optional `analyzer` argument for dependency injection in tests.
- `smart_telescope/services/collimation/sector_mapper.py` (NEW): `SectorMapper(sector_to_screw)` records which spike line disappears when each Tri-Bahtinov blade sector is closed. `observe(label, open_lines, closed_lines)` finds the missing angle using a 10° tolerance match. `build_calibration()` sorts the 3 observed angles and assigns `sector_0_deg` / `sector_120_deg` / `sector_240_deg` in the `MaskSectorCalibration`; returns None if any sector is missing or two sectors map to the same angle (orientation mismatch).
- `smart_telescope/services/collimation/spike_smoother.py` (NEW): `SpikeSmoother(window=7, min_confidence=0.3, seeing_limited_threshold_px=3.0)` maintains a sliding deque of accepted `SpikeMeasurement` frames. `compute()` returns `SmoothedSpikeResult` with: median focus_error_px (current), moving average of most-recent half (trend), population std-dev (jitter), seeing_limited flag (jitter > threshold), frame_count, mean confidence.
- `tests/unit/domain/collimation/test_spike_detection.py` (NEW): 11 tests — result fields, ok/too_few/no_signal reasons, measurement population, offset_from_ref, confidence, crossing point, ref center storage, default analyzer.
- `tests/unit/services/test_sector_mapper.py` (NEW): 13 tests — missing-line detection, tolerance matching, two-sector observation, full calibration (3 sectors), sorted screw assignment, missing sector returns None, ambiguous duplicate angle returns None, defaults calibrated_at.
- `tests/unit/services/test_spike_smoother.py` (NEW): 19 tests — empty/all-rejected, median odd/even/single, confidence filtering (excluded/count/threshold), jitter zero/nonzero/seeing-limited/not-limited, trend average-of-recent-half/single, window eviction, partial window, reset, mean confidence.
- `docs/todo.md`: COL-100, COL-101, COL-102 marked done.
- Test suite: 2128 tests, all pass.

---

## 2026-05-16 — Collimation Phase 9 — Rough Collimation Guidance

**What changed:**

- `smart_telescope/services/collimation/collimation_advisor.py` (NEW): `CollimationAdvisor` takes a list of `ScrewCalibration` and a `DonutMeasurement`; projects the desired correction vector (–error) onto each screw's response vector; picks the screw with the largest dot product; determines CW/CCW direction; caps size at MEDIUM (never LARGE); halves confidence when screw calibration is below threshold. Returns `CollimationRecommendation` or None when already collimated or no calibration available.
- `smart_telescope/services/collimation/live_guidance.py` (NEW): `LiveGuidanceMonitor` polls a `get_measurement()` callable each settle interval while the user turns a screw. Tracks best error seen; declares "converged" when error < green_fraction × outer_radius, "worsened" after N consecutive non-improvements, "star_lost", "cancelled", or "max_frames". Returns `LiveGuidanceResult(reason, initial_error_px, final_error_px, improvement_px, frame_count)`.
- `tests/unit/services/test_collimation_advisor.py` (NEW): 18 tests — no calibration, already collimated, screw selection (x/y/three-screw), turn direction (CW/CCW), adjustment size (small/medium/never-large), confidence, reason string, custom outer_radius.
- `tests/unit/services/test_live_guidance.py` (NEW): 15 tests — result fields, convergence (threshold/improvement/frame count), worsening (consecutive non-improvement/single bad frame), star lost, cancellation, max frames, initial error propagation.
- `docs/todo.md`: COL-090, COL-091 marked done.
- Test suite: 2085 tests, all pass, 83.66% coverage.

---

## 2026-05-16 — Collimation Phase 8 — Screw Identification and Response Learning

**What changed:**

- `smart_telescope/domain/collimation/models.py`: added `ScrewAngularPosition` dataclass (screw_id, angle_deg, confidence) for hand-touch calibration results.
- `smart_telescope/domain/collimation/processing/obstruction_detection.py` (NEW): `detect_obstruction(reference, current, cx, cy)` — computes diff (reference − current), thresholds at 5σ above diff background, finds brightness-weighted centroid of shadow region, computes angle from outer ring center. Returns `ObstructionResult(shadow_center_x, shadow_center_y, angle_deg, shadow_area_px, confidence)` or None if no shadow detected.
- `smart_telescope/services/collimation/screw_mapper.py` (NEW): `ScrewResponseLearner` — accumulates before/after `DonutMeasurement` pairs per screw; converts CCW observations to CW-equivalent; averages response vectors across all observations; confidence saturates to 1.0 at 5 samples. Returns `ScrewCalibration`.
- `tests/unit/domain/collimation/test_obstruction_detection.py` (NEW): 15 tests — result fields, no-shadow (identical frames, noise only, tiny shadow), shadow detected (area, center, confidence), angle accuracy (right/left/above/below), confidence bounds.
- `tests/unit/services/test_screw_mapper.py` (NEW): 22 tests — `ScrewAngularPosition` fields, initial state, CW/CCW single observations, multiple-observation averaging, confidence growth, get_calibration/get_all, Y-axis response, magnitude.
- `docs/todo.md`: COL-080, COL-081 marked done.
- Test suite: 2052 tests, all pass, 83.49% coverage.

---

## 2026-05-16 — Collimation Phase 7 — Rough Donut Collimation

**What changed:**

- `smart_telescope/domain/collimation/processing/donut_detection.py` (NEW): `DonutAnalyzer` detects outer bright ring and inner dark shadow of a defocused C8 star. Ring mask = 10% of peak-above-background (or 3σ minimum). Centroid of ring pixels → RMS radius as inner/outer edge split point (mathematically guaranteed to lie between inner_r and outer_r). Kasa circle fit to each edge set. Error vector = inner_center − outer_center. Returns `DonutAnalysisResult` with `DonutMeasurement` or reason ("no_signal" / "no_ring_shape" / "inner_hole_unclear" / "clipped").
- `smart_telescope/services/collimation/donut_overlay.py` (NEW): `build_donut_overlay(DonutMeasurement) → DonutOverlay`. Includes outer/inner circle parameters, error vector, traffic-light status (green <2%, yellow <10%, red ≥10% of outer radius), T1/T2/T3 screw markers at 1.25× outer radius at configurable angles (default 90°, 210°, 330°).
- `tests/unit/domain/collimation/test_donut_detection.py` (NEW): 17 tests — analysis result fields, no-signal, centered donut accuracy (radius, error, center), offset/miscollimated donut (positive error, direction), clipping, off-center frame, custom confidence threshold.
- `tests/unit/services/test_donut_overlay.py` (NEW): 25 tests — screw marker fields, all overlay fields, traffic-light thresholds (4 boundary tests), screw positions and geometry, error angle propagation.
- `docs/todo.md`: COL-070, COL-071, COL-072 marked done.
- Test suite: 2015 tests, all pass, 83.31% coverage.

---

## 2026-05-16 — Collimation Phase 6 — Focuser Algorithm

**What changed:**

- `smart_telescope/services/collimation/focus_search.py` (NEW): `FocusSearcher` performs image-based rough focus search using FWHM. Algorithm: initial measurement → probe (one coarse step each direction) → scan (bracket in improving direction, stop on 2 consecutive non-improvements) → backtrack to best position → final approach (overshoot + fine steps from configured direction). Result: `FocusSearchResult(success, reason, best_fwhm, net_steps)`.
- `smart_telescope/services/collimation/defocus_controller.py` (NEW): `DefocusController` moves focuser in defocus direction until the star donut reaches 25–50 % of the shorter frame dimension. Radius measured via brightness-weighted RMS second moment, restricted to pixels above 6σ background threshold to eliminate noise inflation. Clipping detected via 10%-of-peak bounding box. Result: `DefocusResult(success, reason, estimated_radius_px, target_min_px, target_max_px, net_steps)`.
- `tests/unit/services/test_focus_search.py` (NEW): 11 tests — result fields, star lost, search convergence, already in focus, cancellation, soft limits, max steps.
- `tests/unit/services/test_defocus_controller.py` (NEW): 12 tests — result fields, target radius (rectangular frames), at-target success, growing donut reaching target, clipping detection, star lost, max steps, cancellation.
- `docs/todo.md`: COL-060, COL-061 marked done.
- Test suite: 1973 tests, all pass, 83.15% coverage.

---

## 2026-05-16 — Bug fixes + optical trains config

**What changed:**

- `api/focuser.py`: `_safe_move` now sleeps 300 ms after issuing the move command and
  checks `is_moving()` / position change; returns `bool` (`started`). `focuser_nudge`
  response now includes `"started": bool` so the setup-check wizard can immediately
  report wiring problems without waiting 2.5 s.

- `api/mount.py`: `mount_unpark` now polls `get_state()` for up to 3 s after `:hU#` is
  sent, logging the final state.  The API no longer returns until the mount actually
  transitions away from PARKED (or times out with a warning).

- `workflow/goto_center.py`: `goto_and_center` now wraps `mount.goto()` in
  `try/except RuntimeError` — the previous `if not ok:` check was dead code because
  `OnStepMount.goto()` raises on rejection rather than returning False.

- `api/preview.py`: Low-range histogram changed from 100 to 200 bins (5 ADU/bin
  instead of 10 ADU/bin over the 0–1000 ADU pedestal panel).

- `static/index.html`:
  - Setup-check focuser step: checks `result.started` immediately after nudge;
    fails fast without the 2.5 s wait when the motor never started.
  - Setup-check unpark: removed the hardcoded 600 ms `setTimeout`; the API now
    blocks until state propagates.
  - Histogram tick spacing: replaced the `rawMajor <= 1000 → majorInt = 1000`
    forced-single-tick logic with a tiered lookup (50/100/200/500/1000/nearest-k);
    minor-tick spacing is now `max(10, majorInt/5)` so small ranges get
    readable tick grids.
  - Label updated from "10 ADU/bin" to "5 ADU/bin".

- `config.py`: Added `TelescopeSpec` and `OpticalTrainSpec` dataclasses plus
  `_parse_telescopes()` / `_parse_optical_trains()` functions.  Module-level
  `TELESCOPES` and `OPTICAL_TRAINS` dicts expose the parsed values.

- `templates/config.toml`: Added commented `[telescopes]` and `[optical_trains]`
  sections (C8 + guide scope; main / guide / OAG trains).

- `tests/unit/workflow/test_goto_center.py`: `_MockMount.goto()` now raises
  `RuntimeError` when `goto_ok=False`, matching the real `OnStepMount` behaviour.

---

## 2026-05-16 — Collimation Phase 5 — Star Selection and Acquisition

**What changed:**

- `smart_telescope/services/collimation/star_selector.py` (NEW) — `BrightStar`, `CollimationStarCandidate`, `StarSelectionResult` dataclasses; `CollimationStarSelector.select()` — picks brightest star above 60° altitude (fallback 45° with warning message in result); `select_by_name()` for manual override (case-insensitive, no altitude filtering); `load_bright_stars(path)` — parses stars.cfg TOML, returns only `type="star"` entries with a magnitude field; uses `compute_altaz()` from `domain/visibility.py`; observer lat/lon injected; `obs_time` injectable for deterministic tests.
- `smart_telescope/services/collimation/star_acquisition.py` (NEW) — `AcquisitionResult` dataclass (`success`, `reason`, `star_measurement`, `centering`); `StarAcquisition.acquire(candidate, cancel_check, dec_deg)` — slew via `mount.goto()`, wait for `is_slewing()` with 120 s timeout, enable tracking if not already, settle (`sleep`), capture + `normalize_frame()` + `detect_star()`, center via injected `PulseCenterer`; reasons: "ok" / "slew_failed" / "star_not_found" / "centering_failed" / "cancelled"; cancellation checked before slew, during slew poll, and after settle.
- `tests/unit/services/test_star_selector.py` (NEW) — 22 tests: dataclass fields (3), select() primary threshold (3), fallback (3), none_visible (3), select_by_name (5), load_bright_stars (4); `compute_altaz` patched for deterministic altitude control.
- `tests/unit/services/test_star_acquisition.py` (NEW) — 13 tests: result fields, successful acquisition (6), slew_failed (1), star_not_found (1), cancellation (3), centering_failed (1); 256×256 Gaussian PSF frames used to stay within 2 % blob-fraction limit.
- `docs/todo.md` — COL-050, COL-051 marked done.

**1950 tests pass (35 new). Coverage 83 %.**

---

## 2026-05-16 — Collimation Phase 4 — Mount and Focuser Control

**What changed:**

- `smart_telescope/services/collimation/mount_centering.py` (NEW) — `MountCorrectionResult` dataclass; `PulseCenterer.center(get_offset_px, cancel_check, dec_deg)` — iterative guide-pulse loop; per-iteration: measure offset → check tolerance → check divergence → choose dominant axis → convert px→arcsec→ms → clamp to max_pulse_ms → guide → settle; abort on star_lost / diverging (3 × 10 % grow) / cancelled / max_pulses; cos(dec) correction for RA guide rate.
- `smart_telescope/services/collimation/focuser_control.py` (NEW) — `FocuserMoveResult` dataclass; `CollimationFocuserControl` with `move_focus_relative()`, `move_focus_clockwise()`, `move_focus_counterclockwise()`, `defocus()`, `focus_fine()`; two-stage clamp (max_single_step → soft position limits); direction sign from `increasing_value_direction` config; `reason` = "ok" | "soft_limit" | "unavailable"; unavailable focuser handled gracefully.
- `smart_telescope/adapters/mock/focuser.py` — **Bug fix:** `MockFocuser.move(steps)` now does `self._position += steps` (relative) instead of `self._position = steps` (absolute), matching the OnStep adapter contract.
- `tests/unit/services/test_mount_centering.py` (NEW) — 19 tests: result fields, within-tolerance (no pulses), guide direction for all 4 axes, dominant-axis selection, pulse clamp, 1ms minimum, convergence, pulses counted, star_lost, star_lost after pulse, diverging, max_pulses, cancel_check immediate, cancel after pulse, dec correction.
- `tests/unit/services/test_focuser_control.py` (NEW) — 29 tests: result fields, unavailable (3), relative move (4), max_single_step clamp (3), soft limits (4), direction mapping (5), defocus/fine focus (6), clipped flag (3).
- `docs/todo.md` — COL-040, COL-041 marked done.

**1915 tests pass (48 new). Coverage 83 %.**

---

## 2026-05-16 — Collimation Phase 3 — Frame Processing Foundation

**What changed:**

- `smart_telescope/domain/collimation/processing/__init__.py` (NEW) — package init
- `smart_telescope/domain/collimation/processing/frame.py` (NEW) — `ProcessedFrame` dataclass (`raw` uint16, `mono` float32, `bit_depth`, `width`, `height`, `timestamp`); `normalize_frame(FitsFrame, bit_depth=16)` — copies pixel data, does not mutate input; `.normalized` property returns [0, 1] float32.
- `smart_telescope/domain/collimation/processing/stretch.py` (NEW) — `estimate_background()` (sigma-clip, 5 iterations); `auto_stretch()` → uint8 percentile stretch; `saturation_fraction(bit_depth)`; `peak_location()`.
- `smart_telescope/domain/collimation/processing/star_detection.py` (NEW) — `detect_star(ProcessedFrame) → StarMeasurement | None`; 5σ threshold; intensity-weighted centroid; radial-profile FWHM; hot-pixel rejection (< 4 px blob) and nebula rejection (> 2 % frame area); SNR-based confidence with saturation penalty.
- `smart_telescope/domain/collimation/processing/geometry_fits.py` (NEW) — `fit_circle()` (Kasa algebraic least-squares, confidence = 1 − rms/r); `fit_ellipse()` (Bookstein direct fit, conic → eigenvalue decomposition, falls back to circle on non-elliptic conics); `extract_edge_points()` (4-connectivity erosion, returns float64 (N,2) array); `detect_clipping(fit, w, h)`; `compare_circle_centers()`.
- `tests/unit/domain/collimation/` (NEW) — 4 test files, 75 tests, all pass:
  - `test_frame_processing.py` (18 tests) — type, dimensions, float32/uint16 conversion, negative clamping, overflow, immutability, independence, bit depths, normalized property
  - `test_stretch.py` (22 tests) — background estimation with star ignored, sigma floor, stretch range+monotonicity+no-mutation, saturation fraction (8-bit and 16-bit), peak location
  - `test_star_detection.py` (11 tests) — dark frame None, Gaussian star detection, centroid accuracy ≤ 1 px, FWHM within 50 %, hot-pixel rejection, saturation penalty, edge star, noisy frame
  - `test_geometry_fits.py` (24 tests) — exact/noisy/small circle, partial arc, degenerate cases, ellipse axis-aligned and noisy, edge extraction from disc mask, circle-from-edge round-trip, clipping detection, center comparison
- `docs/todo.md` — Collimation section added (COL-001 through COL-131), Phases 0+1+3 marked done.

**1867 tests pass (75 new). Coverage 82 %.**

---

## 2026-05-16 — BUG-001 abort_capture + M2 milestone close

**What changed:**

- `smart_telescope/ports/camera.py` — Added `CaptureAbortedError` exception class and `abort_capture()` non-abstract default no-op method to `CameraPort`.
- `smart_telescope/adapters/mock/camera.py` — Added `capture_delay_s: float = 0.0` parameter and `threading.Event`-based `_abort`; `capture()` blocks for `capture_delay_s` seconds then checks abort; `abort_capture()` sets the event. Used for cancel-latency unit tests.
- `smart_telescope/adapters/touptek/camera.py` — Added `self._abort = threading.Event()`; replaced single `_frame_ready.wait(timeout)` with a 50ms polling loop that breaks on `_abort`; added `abort_capture()` that sets `_abort`; imports `CaptureAbortedError`.
- `smart_telescope/domain/autogain_service.py` — Added abort-watcher thread (starts before the main loop, waits for `cancellation_flag`, calls `camera.abort_capture()`); catches `CaptureAbortedError` before generic `Exception` and returns `CANCELLED` immediately. Cancel latency now ≤ 50ms (one poll interval).
- `tests/unit/domain/test_autogain_service.py` — Added `_SlowCamera` stub and `TestCancelLatency` (2 tests): verifies `CANCELLED` status and verifies elapsed time < 1 s.
- `docs/todo.md` — BUG-001 closed; M2-003/004/005/006 closed; M2 milestone complete.

**All 1792 tests pass (2 new).**

---

## 2026-05-16 — R3 Shared Job Manager

**What changed:**

- `smart_telescope/services/job_manager.py` (NEW) — `JobStatus`, `ResourceConflictError`, `Job` dataclass, `JobManager` class. Two submission modes: `submit()` (JobManager owns daemon thread, wraps fn with status update, optional timeout via companion watcher thread) and `claim()`/`release()` (caller owns thread). Atomic resource conflict detection in `_register()`. Query API: `get_job`, `get_by_name`, `list_active`, `active_resources`, `is_resource_held`, `purge_finished`. Cancellation: `cancel`, `cancel_by_name`, `cancel_all`.
- `smart_telescope/runtime.py` — Added `from .services.job_manager import JobManager`; `self.job_manager = JobManager()` in `__init__`; `self.job_manager.cancel_all()` at start of `shutdown()`; `self.job_manager = JobManager()` in `reset_for_tests()`.
- `smart_telescope/api/deps.py` — Added `get_job_manager() -> JobManager`.
- `smart_telescope/api/autogain.py` — Removed manual `threading.Thread` creation and old `j.running` 409 check; replaced with `rt.job_manager.submit("autogain", {"camera:N"}, _worker, ..., cancel_event=job.cancel, timeout_s=300)`. `_reset()` now also calls `rt.job_manager.cancel_by_name("autogain")` for test isolation.
- `smart_telescope/api/session.py` — Replaced `rt.session_lock` conflict check with `rt.job_manager.claim("session", {"camera:0", "mount", "focuser"})`; thread target wrapped in `_session_thread()` that calls `rt.job_manager.release()` in finally; `_reset_session()` also calls `rt.job_manager.cancel_by_name("session")`.
- `tests/unit/services/test_job_manager.py` (NEW) — 40 tests: `TestSubmit` (done/failed/conflict/resource-release/args/bridged-cancel), `TestClaimRelease` (hold/release/done/failed/noop/empty), `TestCancellation` (by-id/by-name/cancel-all), `TestTimeout` (cancelled after timeout, not cancelled when fn finishes first), `TestQuery` (get/get-by-name/list-active/active-resources/is-resource-held), `TestConflictDetection` (done-doesn't-block, non-overlapping ok, error names holder, cancelled-doesn't-block), `TestPurge` (removes finished, leaves active, returns count).
- `tests/unit/test_runtime.py` — Added `test_job_manager_is_fresh_instance` and `test_reset_installs_fresh_job_manager`.
- `docs/todo.md` — R3-001 through R3-007 marked complete; M2-001 and M2-002 marked complete.

**All 1790 tests pass (42 new).**

---

## 2026-05-16 — R0-010 lifecycle tests + UX-PENDING-001 mount pending indicator

**What changed:**

- `tests/unit/test_runtime.py` (NEW) — 40 tests: `TestRuntimeContextInit` (all slots None, coordinator/device_state fresh, session/autogain None), `TestConnectDevices` (mock mode, adapters_built flag, idempotency, polling starts, simulator env var), `TestShutdown` (device_state stops, focuser.stop called, mount stop-before-disconnect ordering, preview cameras closed, error tolerance), `TestResetForTests` (all adapters cleared, polling stopped, fresh coordinator/device_state, session+autogain cleared, new adapters on next access), `TestModuleSingleton` (get/set_runtime), `TestSessionState` (set/clear/is_running), `TestAutogainState` (set/get/clear), `TestLifespan` (FastAPI lifespan sets app.state.runtime, readiness endpoint live, polling thread dead after exit).
- `smart_telescope/static/index.html` — UX-PENDING-001 (POD-003):
  - CSS: `.state-pending` badge style (blue outline)
  - JS: `_mountPendingCmd` module variable (null or command name string)
  - `_updateMountStrip()`: dot turns yellow + label shows `cmd…` when pending; `⚠ state` suffix when `data.stale`
  - `mountCard()`: state badge replaced by spinner-badge when pending, or `⚠ state` badge when stale
  - `mountAction()`: sets `_mountPendingCmd` before API call, clears in `finally`; polls 10× at 500ms for park/unpark confirmation
  - `mountHome()`: sets/clears `_mountPendingCmd` in `finally`
  - `mountGoto()`: sets/clears `_mountPendingCmd` in `finally`
- `docs/todo.md` — R0-010 and UX-PENDING-001 marked complete.

**All 1791 tests pass (40 new).**

---

## 2026-05-15 — PO decisions: POD-001 / POD-002 / POD-003 / POD-006 / POD-008

**Decisions recorded:**

- **POD-001 (Reconnect):** Auto-park on reconnect — already implemented; no change needed.
- **POD-002 (STOP latency):** < 1 s maximum. Safety checklist and BUG-001 acceptance criteria updated.
- **POD-003 (UI state lag):** Spinner/pending indicator between command acceptance and hardware confirmation. New task UX-PENDING-001 added to backlog.
- **POD-006 (MVP demo):** Guided single-target session — Pick target → GoTo → plate-solve & center → autofocus → stack 10 frames → save.
- **POD-008 (Deferred):** ISS tracking, multi-target queue, advanced calibration wizard, collimation assistant are post-MVP.

**docs/todo.md updated:** POD-001/002/003/006/008 marked complete; BUG-001 acceptance criterion updated to < 1 s; safety checklist annotated with POD-002 target; UX-PENDING-001 task added.

---

## 2026-05-15 — R1-010 / R2-008 / R0-005 / R0-006: Tests + runtime state consolidation

**What changed:**

- `tests/unit/services/__init__.py` (NEW) — services test package.
- `tests/unit/services/test_hardware_coordinator.py` (NEW) — 11 tests: acquire/release, lock-released-on-exception, concurrent conflict, timeout=0 non-blocking, lock independence (mount ≠ focuser), two-coordinator isolation, STOP bypass pattern, informative error message.
- `tests/unit/services/test_device_state.py` (NEW) — 13 tests: initial None, start populates, idempotent start, stop halts polling, error stored as UNKNOWN state, flaky-poll reverts to UNKNOWN, UNKNOWN skips position query, position error doesn't crash poll, concurrent reads are safe, stale/not-stale MountObservedState.
- `smart_telescope/runtime.py` — `RuntimeContext` gains `session_lock`, `_active_runner`, `_runner_thread`, `autogain_lock`, `_autogain_job`; new methods `get_active_runner()`, `is_session_running()`, `set_session()`, `clear_session()`, `get_autogain_job()`, `set_autogain_job()`; `reset_for_tests()` clears all new state.
- `smart_telescope/api/session.py` — removed module-level `_session_lock`, `_active_runner`, `_runner_thread`; all references go through `_get_runtime()`.
- `smart_telescope/api/autogain.py` — removed module-level `_job`, `_lock`; replaced with `_get_job()` / `_set_job()` wrappers over RuntimeContext; all endpoints use `rt.autogain_lock`.
- `docs/todo.md` — marked R1-010, R2-008, R0-005, R0-006 complete.

**All 1751 tests pass (24 new).**

---

## 2026-05-15 — M1: Hardware Safety Spine (R1 coordinator + R2 device state)

**What changed:**

- `smart_telescope/services/hardware_coordinator.py` (NEW) — `HardwareCommandCoordinator` with `mount_command()` and `focuser_command()` context managers. `CommandConflictError` raised immediately on timeout. STOP bypasses this entirely.
- `smart_telescope/services/device_state.py` (NEW) — `DeviceStateService`: daemon thread polls mount state every 2 s. `MountObservedState` dataclass with `is_stale()` (10 s threshold). Injected via `deps.get_device_state()`.
- `smart_telescope/runtime.py` — integrates both services: `coordinator` and `device_state` in `__init__`; polling started in `connect_devices()`; `device_state.stop()` called first in `shutdown()` and `reset_for_tests()`.
- `smart_telescope/api/deps.py` — added `get_coordinator()` and `get_device_state()` wrappers.
- `smart_telescope/api/mount.py` — removed module-level `_goto_lock`; all motion endpoints (`goto`, `home`, `park`, `goto_sky`, `goto_and_center`) use `coordinator.mount_command()`; `mount_status` reads from `DeviceStateService` cache with direct-poll fallback; `MountStatus` gains `stale: bool` field; `mount_home` now returns specific "Home slew failed — check mount is tracking and powered" message (BUG-014).
- `smart_telescope/api/focuser.py` — removed module-level `_move_lock` and `_MOVE_TIMEOUT_S`; `_safe_move`, `focuser_move`, `focuser_nudge`, `focuser_autofocus` use `coordinator.focuser_command()`.
- `docs/todo.md` — marked BUG-023, BUG-014, R1-001/002/003/004/007, R2-001/002/004/006/007, M1-001/002/003 as complete.

**All 1727 tests pass.**

---

## 2026-05-15 — NEXT-011: R5 ReadinessService + UX1 Readiness Card

**What changed:**

- `smart_telescope/services/readiness.py` (NEW) — `ReadinessService` with 9 checks: config_file, stars_cfg (RED if missing), horizon_dat (YELLOW), storage (RED if missing/full), astap_exe (RED), astap_catalog (RED), camera (YELLOW if unconfigured), mount, focuser. Returns `ReadinessReport` with `overall` (green/yellow/red), `can_observe`, and `repair` guidance per item.
- `smart_telescope/api/readiness.py` (NEW) — `GET /api/readiness` endpoint, always HTTP 200.
- `smart_telescope/app.py` — readiness router registered.
- `smart_telescope/static/index.html` — System Readiness card added at top of Stage 1. Loads automatically on page open, refreshes every 30 s. Shows overall badge + per-item dot/message/repair. Refresh button for manual re-check.
- `tests/unit/api/test_readiness.py` (NEW) — 22 tests covering all checks, overall level rules, API response shape.

**All NEXT-001 through NEXT-011 complete. All 176 tests pass.**

---

## 2026-05-15 — Immediate Actions: R0 RuntimeContext + AI Skills

**What changed:**

- `smart_telescope/runtime.py` (NEW) — `RuntimeContext` class owns all adapter state: camera, mount, focuser, stacker, storage, solver, preview cameras. Methods: `connect_devices()` (lazy, thread-safe), `shutdown()` (stop motion before disconnect), `disconnect_devices()`, `reset_for_tests()`. Module-level `get_runtime()` / `set_runtime()` singleton for `deps.py` compatibility wrappers.
- `smart_telescope/app.py` — lifespan now creates `RuntimeContext`, registers it via `set_runtime()` and `app.state.runtime`, then calls `ctx.shutdown()`. Removed direct `deps._focuser / _mount / _preview_cameras` access from shutdown path.
- `smart_telescope/api/deps.py` — rewritten as thin compatibility wrappers. All public functions (`get_camera`, `get_mount`, `get_focuser`, `get_stacker`, `make_stacker`, `get_solver`, `get_storage`, `get_preview_camera`, `get_camera_by_role`, `reset`) delegate to `get_runtime()`. No module-level globals remain. All 154 existing tests pass unchanged.
- `docs/skills/smarttscope-product-steward.md` (NEW) — AI skill definition: maintains backlog, imports bugs, deduplicates, enforces acceptance criteria, produces Top-10 risk view.
- `docs/skills/smarttscope-quality-sentinel.md` (NEW) — AI skill definition: verifies task evidence, flags done-without-test, produces milestone traffic-light and release go/no-go report.
- `docs/todo.md` — NEXT-001 through NEXT-009 marked complete; R0-001 through R0-004, R0-007, R0-008, R0-009 marked complete.

**R0 remaining:** R0-005 (session runner into RuntimeContext), R0-006 (autogain job), R0-010 (lifecycle tests).
**Next:** NEXT-011 UX1 Ready To Observe, then M1 hardware safety spine.

---

## 2026-05-15 — Ingest: smarttscope-final-product-architecture-ai-plan.md

**Source ingested**: `docs/smarttscope-final-product-architecture-ai-plan.md`  
**Field bugs also ingested**: `resources/hlrequirements/Items_to_fix_20260513.txt`, `Items_to_fix_20260514.txt`

**New pages**:
- `docs/todo.md` — prioritized master backlog covering M0–M6 milestones, R0–R7 architecture refactors, UX1–UX5 UX refactors, 18 field bugs (BUG-005 through BUG-024), 9 open product-owner decisions, and a safety regression checklist.

**What changed**:
- Consolidated all open work from the architecture review, field bug files, and prior task lists into one authoritative todo.
- 2 P0 Safety items identified: BUG-023 (shutdown doesn't close OnStep, focuser keeps moving) and BUG-005 (system isolation — moving parts must stay controlled on any crash).
- Milestone order: M0 (project control) → M1 (hardware safety) → M2 (runtime/jobs) → M3 (optical train/config) → M4 (intent UX) → M5 (MVP demo) → M6 (field reliability).

---

## 2026-05-06 — Ingest: SmartTScope_Fixes_Requirements_20260506

**Source ingested**: `resources/hlrequirements/SmartTScope_Fixes_Requirements_20260506.md`

**New wiki pages**:
- `wiki/requirements-addon-20260506.md` — fix/update requirements v1.1: camera naming/registry (§1), Live Preview backend (§2.3–2.10), Polar Alignment selector (§3), Startup tab polish (§4). 13 tasks added to persistent SmartTScope tasklist (STS-ADDON-001 through STS-ADDON-013).

**Updated wiki pages**:
- `wiki/index.md` — new Planning entry

**Task snapshot**: STS-ADDON-001 completed (tasklist populated); 002–013 pending. P1 tasks: camera registry (002), camera name selectors (003, 004), Live Preview backend (005, 006). All 13 tasks to be executed after the current AutoGain (AGT) implementation run completes.

---

## 2026-05-03 — Sprint 45: TOML config file, tracking toggle, ASTAP + mount bug fixes

**What changed**:

- `smart_telescope.toml` (NEW) — project-root config template.  Sections: `[observer]` (lat/lon), `[hardware]` (onstep_port, touptek_index, gps_port, dew_control_port), `[astap]` (path, catalog_dir), `[mount_limits]`, `[session]`.  All hardware fields default to `""` (empty = mock/auto-detect); the Pi admin fills in real values.
- `smart_telescope/config.py` — rewritten: loads TOML from CWD or project root via `tomllib`; env vars override for observer/limits/session settings; hardware/ASTAP settings are TOML-only (env-var override is applied per-call in `deps.py` to preserve `monkeypatch` test behaviour).  New exports: `ONSTEP_PORT`, `TOUPTEK_INDEX`, `GPS_PORT`, `DEW_CONTROL_PORT`, `ASTAP_PATH`, `ASTAP_CATALOG_DIR`, `STORAGE_DIR`.
- `smart_telescope/api/deps.py` — `_build_adapters()` now reads `os.environ.get(key) or config.KEY` so live env vars always win; same pattern for `get_solver()` / `get_storage()`.  Fixes the false-positive "Connected" bug: previously `ONSTEP_PORT` absent → `MockMount` (always returns True); now the TOML supplies the port → `OnStepMount` → real serial failure reported correctly.
- `smart_telescope/adapters/astap/solver.py` — `find_catalog()` now accepts optional `catalog_dir` parameter (checked first); added Pi-specific search dirs `/var/lib/astap` and `/opt/astap`.  `AstapSolver.__init__` stores `catalog_dir` for future per-solve pass-through.
- `smart_telescope/api/session.py` — `_check_solver()` passes `catalog_dir=config.ASTAP_CATALOG_DIR` to `_find_catalog()`; mount hint updated to reference `smart_telescope.toml`.
- `smart_telescope/static/index.html` — `mountCard()` tracking buttons replaced with a single context-sensitive toggle: shows "Disable Tracking" when `state === 'tracking'`, otherwise "Enable Tracking".

**Tests** — no new test files; updated three existing tests:
- `tests/unit/api/test_session.py` — patched lambdas for `_find_catalog` updated to `lambda *a, **kw:` to accept new `catalog_dir` keyword argument.

**Suite result**: 1026 passed, 0 failures, 92% coverage

---

## 2026-05-03 — Sprint 44: "Best objects tonight" endpoint (M8)

**What changed**:

- `smart_telescope/api/catalog.py`:
  - Added `from datetime import UTC, datetime, timedelta` and `compute_visibility_window` import
  - New `VisibleEntry` Pydantic model — extends catalog fields with `rises_at`, `sets_at`, `peak_altitude`, `peak_time` (ISO8601 UTC strings), `is_observable`, `solar_safe`
  - New `GET /api/catalog/visible` endpoint:
    - Optional `?lat=` / `?lon=` to override observer position (defaults to `config.OBSERVER_LAT/LON`)
    - `?hours=` observation window length in hours (default 10, range 1–24)
    - `?min_altitude=` minimum peak altitude in degrees (default 20)
    - `?object_type=` comma-separated type filter (e.g. `GC,SG`)
    - `?max_magnitude=` upper magnitude bound
    - `?limit=` max results (default 20)
    - Calls `compute_visibility_window(..., sample_minutes=15)` for each catalog object
    - Filters to `is_observable=True`; adds `solar_safe` flag via `is_solar_target()`
    - Sorted by `peak_altitude` descending

**Tests** — added `TestCatalogVisible` class (15 tests) to `tests/unit/api/test_catalog.py`:
  - 200 response, empty when all non-observable, expected fields present, is_observable=True
  - Sorted by peak altitude descending
  - object_type filter, multi-type filter, max_magnitude filter, limit applied, default limit 20
  - solar_safe flag (blocked / not-blocked), lat/lon override forwarded, rounding, ISO8601 string format

**Suite result**: 1026 passed, 0 failures, 92% coverage

---

## 2026-05-03 — Sprint 43: Observation Queue REST API (M8)

**What changed**:

- `smart_telescope/api/queue.py` (NEW) — Full CRUD for the observation queue:
  - `POST /api/queue` → 201 + entry dict; validates profile against `{c8_native, c8_reducer, c8_barlow2x}`; validates RA [0, 24), Dec [−90, 90]
  - `GET /api/queue` → list all entries; optional `?status=` filter (PENDING / RUNNING / DONE / FAILED / SKIPPED); 422 on unknown status
  - `GET /api/queue/{entry_id}` → single entry; 404 if not found
  - `DELETE /api/queue/{entry_id}` → remove PENDING entry; 204 on success; 404 if not found; 409 if not PENDING
  - `POST /api/queue/clear` → remove all DONE/FAILED/SKIPPED entries; returns `{"cleared": N}`
  - Module-level `ObservationQueue` singleton with `_reset_queue()` for test isolation; `get_queue()` accessor
- `smart_telescope/app.py` — registered `queue_router`

**Tests**:
- `tests/unit/api/test_queue.py` (NEW) — 25 tests across 6 classes:
  - `TestAddEntry` (8 tests): 201 path, entry_id present, defaults, custom fields, invalid profile, RA/Dec validation, missing name, appears in list
  - `TestListEntries` (6 tests): empty, all entries, insertion order, status filter, case-insensitive filter, unknown status 422
  - `TestGetEntry` (2 tests): found, 404
  - `TestRemoveEntry` (5 tests): 204, gone after remove, 404, 409 on RUNNING, detail includes status
  - `TestClearCompleted` (3 tests): count returned, PENDING survives, zero when nothing to clear
  - `queue.py` at 100% coverage

**Suite result**: 1011 passed, 0 failures, 92% coverage

---

## 2026-05-03 — Sprint 42: System Health dashboard card (M5.1)

**What changed**:

- `smart_telescope/api/health.py`:
  - `CpuHealth(temp_c: float | None)` — new model; reads `/sys/class/thermal/thermal_zone0/temp` via `_read_cpu_temp()`; returns `None` gracefully on non-Linux / missing path
  - `StorageHealth` gains `frames_capacity: int | None` — computed as `int(free_gb * 1024 / 25)` (25 MB estimated float32 FITS frame for C8 native); `None` when no `STORAGE_DIR` is set
  - `SystemHealth` gains `cpu: CpuHealth` field
  - `system_status()` updated to populate both new fields
- `smart_telescope/static/index.html`:
  - New "System Health" card in Stage 1 (after the Focuser card): overall dot (green/yellow/red), last-updated timestamp
  - `_healthRow(label, level, value)` — renders one subsystem row with colored mini-dot
  - `_renderHealthCard(d)` — populates all 7 rows (Mount, Camera, Focuser, Solver, Storage, CPU temp, Session) with per-row color logic; updates overall dot
  - `refreshHealth()` — async fetch of `/api/status` + render
  - Init block: calls `refreshHealth()` on load; `setInterval(refreshHealth, 10_000)` for live updates

**Tests**:
- `tests/unit/api/test_health.py` — `test_response_has_all_top_level_fields` updated to include `"cpu"`
- `TestCpuHealth` (4 tests): field present, None on missing path, value returned when patched, rounding
- `TestStorageCapacity` (2 tests): `frames_capacity` computed from free_gb; None when no path set

**Suite result**: 986 passed, 0 failures, 92% coverage

---

## 2026-05-03 — Sprint 41: Bahtinov domain unit tests + `_intersect` bugfix

**Bug fixed**:
- `smart_telescope/domain/bahtinov.py` — `_intersect()` had wrong Cramer's rule signs: `x` used `/ (-d)` instead of `/ d`, and `y` numerator was `(a1·c2 − a2·c1)` instead of `(a2·c1 − a1·c2)`. Effect: intersections reflected through origin → `focus_error_px` wildly wrong (e.g. −656 px instead of ≈ 0). Fixed to standard Cramer's rule.

**Tests added**:
- `tests/unit/domain/test_bahtinov.py` — NEW: 43 tests covering `SpikeLine`, `CrossingAnalysisResult`, `_gaussian_blur`, `_intersect` (including regression for the Cramer's rule bug), `_classify_bahtinov`, `BahtinovAnalyzer.analyze()`, constructor params, `_find_brightest_object`

**Suite result**: 980 passed, 0 failures

---

## 2026-05-02 — Sprint 40: Bahtinov API + Stage 4 UI overlay

**Code changes**:
- `smart_telescope/api/bahtinov.py` — NEW: `POST /api/bahtinov/analyze`; captures one frame, runs `BahtinovAnalyzer`, returns `CrossingAnalysisResult` fields + `image_size_px`; 422 when fewer than 3 spikes detected
- `smart_telescope/app.py` — registered `bahtinov_router`
- `smart_telescope/static/index.html`:
  - Analyze button (enabled only when preview running, disabled when stopped)
  - SVG overlay element (`s4-bahtinov-svg`) absolutely positioned over preview image
  - Results card (focus_error_px with color + direction hint, crossing RMS, confidence)
  - `_clipLineToRect()` — clips a normal-form line to image bounds for SVG rendering
  - `_drawBahtinovOverlay(data)` — draws 3 spike lines (outer blue dashed, middle yellow solid), crossing-point ring (green/yellow/red by error magnitude), focus-direction arrow
  - `_clearBahtinovOverlay()` — clears SVG + hides results (called on preview stop)
  - `bahtinovAnalyze()` — async; posts to API, populates results, calls draw overlay
  - `_updatePreviewBtns()` — now also manages analyze button and clears overlay on stop

**Tests**:
- `tests/unit/api/test_bahtinov.py` — NEW: 12 tests (422 on zero-pixel image, success path with synthetic spike image, key validation, mocked analyzer path)

**Suite result**: 980 passed, 94.40% coverage

---

## 2026-05-02 — Sprint 39: Focuser availability + shared serial delegation

**Source ingested**: `resources/hlrequirements/requirements_addon_20260502b.txt`

**New wiki pages**:
- `wiki/requirements-addon-20260502b.md` — README update instructions + focuser always-expected policy

**Updated wiki pages**:
- `wiki/index.md` — new Planning entry

**Code changes**:
- `smart_telescope/ports/focuser.py` — added `get_max_position()` abstract method and `is_available` abstract property
- `smart_telescope/adapters/onstep/focuser.py` — refactored to delegate serial I/O to `OnStepMount`; no own serial handle; `connect()` sets `_available` from `:FA#`; fetches max position via `:FM#`
- `smart_telescope/adapters/mock/focuser.py` — added `is_available` and `get_max_position()` (returns 5000)
- `smart_telescope/adapters/simulator/focuser.py` — added `is_available` (True) and `get_max_position()` (5000)
- `smart_telescope/api/deps.py` — `OnStepFocuser(mount=mount)` shared serial; no separate focuser port open
- `smart_telescope/api/focuser.py` — status adds `available` + `max_position`; `POST /api/focuser/connect` (new); move/nudge/autofocus return 503 when not available; position clamped to `[0, max_position]`
- `smart_telescope/api/health.py` — focuser health uses `focuser.is_available`
- `smart_telescope/static/index.html` — Stage 1 focuser status card; `connectAll()` probes focuser; `focuserCard()` shows disabled banner when `available === false`
- `README.md` — new "Keeping up to date" section (git pull + pip install + systemctl restart)

**Tests**:
- `tests/unit/adapters/onstep/test_onstep_focuser.py` — rewritten for new delegating constructor (30 tests)
- `tests/unit/api/test_focuser.py` — updated for `available`/`max_position`; new connect endpoint tests; 503 tests (38 tests)

**Suite result**: 968 passed, 88.63% coverage

---

## 2026-05-02 — Ingest: requirements_addon_20260502 (Bahtinov analyzer)

**Source ingested**: `resources/hlrequirements/requirements_addon_20260502.txt`

**New pages**:
- `wiki/bahtinov-analyzer.md` — complete algorithm reference: brightest-object detection (flux score), ROI crop, core masking, Hough/RANSAC line detection, normal-form line fitting, pairwise intersection geometry, `focus_error_px` (primary Bahtinov metric), `crossing_error_rms_px` (quality guard), `SpikeLine` / `CrossingAnalysisResult` data structures, UI requirements

**Updated pages**:
- `wiki/autofocus.md` — added Bahtinov as the specified SmartTScope focus method, link to [[bahtinov-analyzer]]
- `wiki/requirements.md` — added Bahtinov collimation tool as MVP+ requirement in §4, linked to [[bahtinov-analyzer]]
- `wiki/index.md` — new Concepts entry

---

## 2026-05-02 — Sprint 38: Mount Limits display card in Stage 1

**What changed**:

- `smart_telescope/static/index.html` — new "Mount Limits" card in Stage 1, positioned after the mount control card:
  - Four param fields: Alt min (horizon), Alt max (zenith exclusion), HA east limit, HA west limit.
  - Populated by `initSiteConfig()` which already calls `GET /api/mount/config` on page load.
  - Footer note explains each value is controlled by an environment variable.
- No backend changes.

**Result**: UI-only change.

---

## 2026-05-02 — Ingest: requirements_addon_20260430 + requirements_addon_20260501

**Sources ingested**:
- `resources/hlrequirements/requirements_addon_20260430.txt`
- `resources/hlrequirements/requirements_addon_20260501.txt`

**New pages**:
- `wiki/requirements-addon-20260430.md` — star catalog expansion, quickstart corrections (Trixie, no libcamera), §14 process requirements
- `wiki/requirements-addon-20260501.md` — first hardware test session (2026-05-01): three bugs (serial race → 500, camera caching, WS silent close); new requirements for mount display, Home/Park, step-based movement, mount limits config

**Updated pages**:
- `wiki/onstep-protocol.md` — adapter implementation notes expanded: threading lock rationale, readline/`#` terminator behaviour, all commands now used by `OnStepMount` (including `disable_tracking`, `park`, `guide`, alignment), safe-movement rule (pulse guide only)
- `wiki/index.md` — two new planning entries added

---

## 2026-05-02 — Sprint 37: GoTo-Selected button + live mount-strip poll

**What changed**:

- `smart_telescope/static/index.html` — Custom Targets card (Stage 3):
  - Added GoTo and ⌖ buttons in the card header, initially disabled; enabled when a target row is clicked.
  - `starSelect()` now saves `_selectedStar`, highlights the clicked row (`.star-item.selected` CSS), and enables the header buttons.
  - `loadStars()` resets `_selectedStar` and disables the header buttons on reload.
  - `starGotoSelected()` / `starCenterSelected()` delegate to the existing per-row functions.
  - `data-star-name` attribute added to each star-item `<div>` so the selected row can be found by CSS.escape lookup.
- Mount strip (stages 2–5): 5 s `setInterval` poll (`_startMountStripPoll`) activates when navigating away from Stage 1; stops on return. Keeps RA/DEC and state badge live while the mount is tracking.

**Result**: UI-only — no backend changes, no tests affected.

---

## 2026-05-02 — Bug fixes: serial lock + camera connect guard

**What changed**:

- `smart_telescope/adapters/onstep/mount.py` — added `threading.Lock` (`self._lock`) to `OnStepMount`; `_raw_send` acquires the lock before each write/readline pair. Prevents concurrent HTTP requests from interleaving bytes on the serial port, which was the root cause of `POST /api/mount/disable_tracking` returning HTTP 500.
- `smart_telescope/api/deps.py` — `get_preview_camera()` now checks `cam.connect()` return value for secondary cameras; raises `RuntimeError` (not cached) on failure.
- `smart_telescope/api/preview.py` — `ws_preview` now accepts the WebSocket before attempting `get_preview_camera()`; on `RuntimeError` sends WS close code 1011 with the error reason instead of silently dropping the connection.

**Result**: 62 OnStep tests passing (pre-existing global coverage gate failure unrelated).

---

## 2026-05-02 — Sprint 36: Stage 5 live stack viewer

**What changed**:

- `smart_telescope/static/index.html` — Stage 5 "Run Observation" card gains a live stack preview panel:
  - `_s5ConnectStackWs()` opens `WS /ws/stack` immediately on session start
  - Text (JSON) frames: updates progress bar and frame/rejected counts directly, ahead of the 2 s REST poll
  - Binary (JPEG) frames: shown in a `<img id="s5-stack-img">` inside a `.preview-frame.large` container; panel fades in on first integrated frame
  - `_s5DisconnectStackWs()` called on terminal states (SAVED / STACK_COMPLETE / FAILED) and in `_s5ResetRunUI()` before next session; blob URLs revoked on each frame to prevent memory leaks

**Result**: 957 tests passing, 15 skipped, 94% coverage (unchanged — UI-only changes).

---

## 2026-05-02 — Sprint 35: Stage 5 observation session workflow UI

**What changed**:

- `smart_telescope/static/index.html` — Stage 5 "Run Observation" card added:
  - Target text input, profile dropdown (C8 Native / 0.63× reducer / 2× Barlow), exposure (s), stack depth (frames), skip-autofocus checkbox
  - ▶ Start Session button calls `POST /api/session/run` via URLSearchParams; ■ Stop button calls `POST /api/session/stop`
  - Live status section: phase badge (`state-badge` CSS, maps to all `SessionState` enum values), animated progress bar (frames_integrated / stack_depth, shown during STACKING → SAVED)
  - Detail rows for centring offset, rejected frames, refocus count — appear only when non-zero
  - Warnings list (colour: `--warning`); saved image path shown in green on SAVED
  - State polling every 2 s via `setInterval`; stops automatically on SAVED / STACK_COMPLETE / FAILED

**Result**: 956 tests passing, 15 skipped, 94% coverage.

---

## 2026-05-02 — OnStepMount: send :Td# (stop tracking) on connect

**What changed**:

- `smart_telescope/adapters/onstep/mount.py` — `connect()` now calls `disable_tracking()` immediately after opening the serial port, before returning `True`. Ensures the mount is never left tracking unexpectedly on first connection.
- `tests/unit/adapters/onstep/test_onstep_mount.py` — new `test_connect_sends_stop_tracking` verifies `:Td#` appears in serial write calls during connect. Four `TestGetPosition` tests updated: each side_effect list gains a leading `b""` to absorb the extra `readline()` call.

**Result**: 957 tests passing, 15 skipped, 94% coverage.

---

## 2026-05-02 — Sprint 34: Stage 3 GoTo slew watcher + centre button

**What changed**:

- `smart_telescope/static/index.html`:
  - `watchSlew(statusId, label, timeout_s)` — polls `GET /api/mount/status` every 2 s during slew, updates mount strip live, resolves when state leaves `slewing` (or on timeout)
  - Stage 3 manual GoTo now calls `watchSlew()` after slew is accepted, replacing the immediate `refreshMount()`
  - ⌖ Centre button on manual GoTo panel calls `mountGotoAndCenter()` → `POST /api/mount/goto_and_center`
  - ⌖ button added to each star-list row (`starGotoAndCenter()`) — centring result shown inline; unlocks Stage 4 on success

**Result**: 956 tests passing, 15 skipped, 94% coverage (unchanged — UI-only changes).

---

## 2026-04-30 — Requirements addon: catalog expansion + process requirements + quickstart

**Source**: requirements_addon_20260430.txt

**stars.cfg — 21 new entries added**:

- *Solar system*: Jupiter (planet, approx. Apr 2026 coords — update monthly), C/2025 R3 (comet placeholder — update from JPL Horizons)
- *Nebulae*: NGC 2359 (Thor's Helmet), NGC 2237 (Rosette Nebula proper; cluster NGC 2244 was already present), IC 5068 (Forsaken Nebula), NGC 2024 (Flame Nebula), IC 434 (Horsehead Nebula), NGC 7380 (Wizard Nebula), NGC 6992 (Eastern Veil), IC 405 (Flaming Star / Caldwell 31), NGC 281 (Pacman), NGC 2174 (Monkey Head), NGC 6960 (Western Veil / Cirrus, filter note), NGC 6543 (Cat's Eye)
- *Galaxies*: M 51 (Whirlpool), M 63 (Sunflower), NGC 3268 (Antlia), NGC 3184
- *Filter variants*: M 42 Filters (OIII + Ha), M 45 Filters (nebulosity)
- *Multiple stars*: 12 Lyncis (triple, A/B 1.8″, C 8.6″), Iota Cassiopeiae (triple, +67° dec), Beta Monocerotis (triple, low ~33° from Frankfurt)

*Note*: M51, M63, M42, M45 are already in the internal Messier catalog (`domain/catalog.py`) and GoTo-able by name. The stars.cfg entries make them visible in `GET /api/catalog/stars` and add filter-use variants.

**wiki/requirements.md — §14 Process requirements added (MVP)**:

- Documentation gate: a change is not done until documentation is updated
- Release traceability: each requirement tracks "Planned for" and "Implemented in" release

**wiki/quickstart.md — new page**:

- Correct platform: Raspberry Pi OS Trixie (Debian 13), not Bullseye
- Python 3.13 from main apt (no deadsnakes PPA needed on Trixie)
- Explicit note: libcamera is NOT used — ToupTek SDK over USB only
- Environment variables, custom targets (stars.cfg), systemd setup
- Bookworm → Trixie delta table

**wiki/index.md** — quickstart entry added; requirements entry updated.

---

## 2026-04-30 — Sprint 31: Queue domain model + visibility window (M8 start)

**What changed**:

- `smart_telescope/domain/queue.py` (NEW) — Observation queue domain objects:
  - `QueueEntryStatus` enum: PENDING / RUNNING / DONE / FAILED / SKIPPED
  - `QueueEntry` — one observation job: target name/RA/dec, profile, exposure, stack_depth, min_altitude_deg, auto-generated entry_id, status, timestamps (added_at, started_at, completed_at), session_id, failure_reason; `to_dict()` for serialisation
  - `ObservationQueue` — thread-safe ordered list of entries:
    - `add(entry)`, `remove(entry_id) → bool` (PENDING-only), `clear_completed()`
    - `get(entry_id)`, `next_pending()`, `all()`, `pending()`, `to_list()`
    - Protected by `threading.Lock`; RUNNING entries are immune to `remove()`
- `smart_telescope/domain/visibility.py` — added `VisibilityWindow` and `compute_visibility_window()`:
  - `VisibilityWindow(rises_at, sets_at, peak_altitude, peak_time, is_observable)` — frozen dataclass
  - `compute_visibility_window(ra_hours, dec_deg, lat, lon, night_start, night_end, min_altitude_deg=20.0, sample_minutes=5)` — samples altitude at regular intervals, returns the first/last sample above threshold plus peak; accurate to ±sample_minutes minutes; wraps `compute_altaz` so it's fully mockable
- `tests/unit/domain/test_queue.py` (NEW) — 21 tests across 2 classes:
  - `TestQueueEntry` — defaults, unique IDs, `to_dict()` keys/types/timestamps
  - `TestObservationQueue` — empty, add, pending/next_pending, get, remove (PENDING only, not RUNNING), clear_completed, to_list, insertion order, thread-safety (4 concurrent writers × 50 adds = 200 entries, no errors)
- `tests/unit/domain/test_visibility_window.py` (NEW) — 15 tests across 5 classes:
  - `TestVisibilityWindowDataclass` — frozen (attribute mutation raises)
  - `TestNeverObservable` — peak below threshold, None rises/sets, correct peak altitude/time
  - `TestAlwaysObservable` — rises_at = night_start, sets_at = night_end
  - `TestRisesDuringNight` — rises_at is first sample ≥ threshold
  - `TestSetsDuringNight` — sets_at is last sample ≥ threshold
  - `TestSamplingBehaviour` — 6-hour / 60-min → exactly 7 `compute_altaz` calls

**Result**: 923 tests passing, 15 skipped, 95% coverage.

---

## 2026-04-30 — Sprint 30: Frame quality log + integration tests (M7 close)

**What changed**:

- `smart_telescope/domain/frame_quality.py` — added `FrameQualityEntry` dataclass:
  - `{frame_number, snr, baseline_snr, accepted, reason}` — one record per stack frame for post-session review
- `smart_telescope/domain/session.py`:
  - `SessionLog` gains `frame_quality_log: list[FrameQualityEntry]` field
  - `to_dict()` serialises the log as `"frame_quality_log": [{frame, snr, baseline_snr, accepted, reason}, ...]`
- `smart_telescope/workflow/stages.py` — `stage_stack()` appends a `FrameQualityEntry` to `log.frame_quality_log` for every frame evaluated (accepted and rejected alike); entries added only when `frame_quality_filter` is active
- `smart_telescope/adapters/mock/camera.py` — `MockCamera` gains `return_bright: bool` and `dim_on_captures: frozenset[int]` parameters:
  - `return_bright=True` → returns 64×64 noisy star-field frames with measurable SNR (instead of zero frames) for quality-filter integration tests
  - `dim_on_captures={…}` → returns low-SNR (cloud-simulated) frames on the specified capture indices
  - Default behaviour (zeros) unchanged — all existing integration tests unaffected
- `tests/integration/test_vertical_slice.py` — `TestQualityFiltering` class (7 tests):
  - All-bright run: 10 integrated, 0 rejected
  - Dim frames on captures #20 and #21 → 2 rejected, 8 integrated
  - Session completes to SAVED despite rejections (non-fatal)
  - Rejection warning logged per rejected frame
  - `frame_quality_log` populated (10 entries, 2 rejected)
  - Serialised dict contains `frame_quality_log` with correct accepted/rejected flags

**M7 milestone gate status**: 
- Cloud-simulation test (dim captures): `frames_rejected` increments correctly, `frames_integrated` stays correct ✓
- Stack completes to SAVED despite rejections (non-fatal) ✓
- Per-frame SNR + accept/reject written to session JSON for post-session analysis ✓
- Configurable threshold and baseline depth via API query params ✓

**Result**: 887 tests passing, 15 skipped, 95% coverage.

---

## 2026-04-30 — Sprint 29: Frame quality filtering (M7 — It rejects bad frames)

**What changed**:

- `smart_telescope/domain/frame_quality.py` (NEW) — `FrameQualityConfig`, `FrameQualityResult`, `FrameQualityFilter`:
  - `FrameQualityConfig(min_snr_factor=0.3, baseline_frames=3)` — configurable rejection threshold and warmup depth
  - `min_snr_factor=0.0` disables rejection (all frames accepted); range [0.0, 1.0]
  - `FrameQualityFilter.evaluate(frame) → FrameQualityResult` — computes per-frame SNR and compares to rolling baseline
  - **SNR metric**: `(99.5th-percentile signal − sky_median) / sky_MAD` — robust sky-background model; resistant to outliers and hot pixels via MAD noise estimator
  - First `baseline_frames` frames always accepted (building the SNR baseline); baseline is a rolling median of the last N accepted SNRs
  - Rejected frames do NOT update the baseline; the baseline reflects only good frames
- `smart_telescope/workflow/_types.py` — 2 new constants: `FRAME_QUALITY_MIN_SNR_FACTOR = 0.3`, `FRAME_QUALITY_BASELINE_FRAMES = 3`
- `smart_telescope/workflow/stages.py`:
  - `StageContext` gains `frame_quality_filter: FrameQualityFilter | None = None` (None = accept all)
  - `stage_stack()` evaluates quality after each capture; rejected frames skip `stacker.add_frame()` and log a warning; `log.frames_rejected` accumulates both quality rejects and stacker registration rejects (astroalign failures)
  - Frame numbering to stacker uses `accepted_count` (1-indexed over accepted frames only), so the NumpyStacker's reference frame is always the first accepted frame
- `smart_telescope/workflow/runner.py` — gains `enable_frame_quality: bool = True`, `frame_quality_min_snr: float = 0.3`, `frame_quality_baseline_frames: int = 3`; creates `FrameQualityFilter` in `run()` when enabled
- `smart_telescope/api/session.py` — `POST /api/session/run` gains `enable_quality_filter`, `quality_min_snr` (0.0–1.0), `quality_baseline_frames` (1–20) query params
- `tests/unit/domain/test_frame_quality.py` (NEW) — 20 tests across 4 classes:
  - `TestFrameQualityConfig` — defaults, custom values, boundary/invalid validation
  - `TestFrameSnr` — zero/uniform frames return 0.0, noisy star-field returns positive SNR, brighter > dimmer
  - `TestBaselineBuilding` — warmup acceptance, baseline_snr None during warmup, set after warmup
  - `TestAcceptance` — bright accepted, dim rejected, disabled filter passes all, rejected frame skips baseline update, next bright frame still accepted after a reject

**Result**: 880 tests passing, 15 skipped, 95% coverage.

---

## 2026-04-30 — Sprint 28: Refocus triggers (elapsed / altitude / temperature)

**What changed**:

- `smart_telescope/domain/refocus.py` (NEW) — `RefocusConfig`, `RefocusTriggerResult`, `RefocusTracker`:
  - `RefocusConfig(temp_delta_c=1.0, altitude_delta_deg=5.0, elapsed_min=30.0)` — configurable thresholds
  - `RefocusTracker.record_focus(altitude, temperature?)` — snapshot taken immediately after every autofocus
  - `RefocusTracker.check(altitude, temperature?) → RefocusTriggerResult` — returns `{should_refocus, reason}` where reason is `"elapsed"`, `"altitude"`, or `"temperature"`; returns False if no baseline recorded
  - Priority: elapsed checked first (dominant), then altitude, then temperature
  - Temperature trigger skipped silently when either current or baseline temperature is None
- `smart_telescope/domain/session.py` — `SessionLog` gains `refocus_count: int = 0`; included in `to_dict()` under the "autofocus" key
- `smart_telescope/workflow/_types.py` — 3 new constants: `REFOCUS_TEMP_DELTA_C = 1.0`, `REFOCUS_ALT_DELTA_DEG = 5.0`, `REFOCUS_ELAPSED_MIN = 30.0`
- `smart_telescope/workflow/stages.py`:
  - `StageContext` gains `refocus_tracker: RefocusTracker | None = None` (None = triggers disabled)
  - `stage_autofocus()` calls `ctx.refocus_tracker.record_focus(altitude=alt)` after successful autofocus
  - `stage_stack()` checks triggers before each frame (i > 1); if fired: transitions to FOCUSING, runs `run_autofocus()`, records new baseline, increments `log.refocus_count`; autofocus failure is non-fatal (appended to warnings)
  - `_frame_temp(frame: FitsFrame) → float | None` — extracts CCD temperature from FITS header keys "CCD-TEMP", "CCDTEMP", "TEMP"
- `smart_telescope/workflow/runner.py` — gains `enable_refocus_triggers`, `refocus_temp_delta_c`, `refocus_alt_delta_deg`, `refocus_elapsed_min` init params; creates `RefocusTracker` in `run()` (disabled when `skip_autofocus=True` or `enable_refocus_triggers=False`)
- `smart_telescope/api/session.py` — `POST /api/session/run` gains `refocus_temp_delta`, `refocus_alt_delta`, `refocus_elapsed_min`, `enable_refocus` query params; `GET /api/session/status` response gains `refocus_count`
- `tests/unit/domain/test_refocus.py` (NEW) — 25 tests across 6 classes:
  - `TestRefocusConfig` — defaults and custom values
  - `TestNoBaseline` — check before record returns no-refocus
  - `TestElapsedTrigger` — no trigger within interval, triggers at/past threshold
  - `TestAltitudeTrigger` — no trigger within threshold, triggers at threshold, triggers on descent
  - `TestTemperatureTrigger` — no trigger within threshold, triggers at threshold, None-temp handling (both current and baseline)
  - `TestTriggerPriority` — elapsed wins over altitude; record_focus resets all triggers

**Result**: 860 tests passing, 15 skipped, 95% coverage.

---

## 2026-04-30 — Sprint 27: Autofocus backlash compensation

**What changed**:

- `smart_telescope/domain/autofocus.py` — `AutofocusParams` gains `backlash_steps: int = 0`:
  - Default 0 = disabled; any positive value enables backlash compensation
  - Validated ≥ 0 in `__post_init__`; negative value raises `ValueError`
- `smart_telescope/workflow/autofocus.py` — `run_autofocus()` gains backlash logic:
  - **Pre-load**: when `backlash_steps > 0`, moves focuser to `sweep_start − backlash_steps` before the sweep so the first real sweep move is upward (from below)
  - **Final approach**: moves to `best_pos − backlash_steps` then `best_pos`, ensuring the chosen position is always approached from below
  - Zero backlash: no pre-load move; final positioning remains a single `focuser.move(best_pos)` — identical to pre-Sprint-27 behaviour
- `smart_telescope/workflow/_types.py` — `AUTOFOCUS_BACKLASH_STEPS = 0` constant added
- `smart_telescope/workflow/stages.py` — `StageContext.autofocus_backlash_steps: int = 0` added; passed to `AutofocusParams`
- `smart_telescope/workflow/runner.py` — `VerticalSliceRunner.__init__` gains `autofocus_backlash_steps: int = 0`; passed to `StageContext`
- `smart_telescope/api/session.py` — `POST /api/session/run` gains `autofocus_backlash: int` query param (default 0, max 500)
- `tests/unit/workflow/test_autofocus.py` — 7 new tests in `TestBacklashCompensation`:
  - Pre-load move occurs before sweep when `backlash_steps > 0`
  - All sweep moves are ≥ pre-load position (always upward)
  - Final approach sequence is `[best_pos − backlash, best_pos]`
  - Zero backlash: first move equals `sweep_start` (no pre-load below it)
  - Zero backlash: last move is directly `best_pos` (no pre-load step)
  - Sample count is identical with and without backlash
  - Negative `backlash_steps` raises `ValueError`
- `tests/integration/test_vertical_slice.py` — fixed pre-existing state-sequence and capture-count gaps from Sprint 25:
  - `EXPECTED_HAPPY_PATH_STATES` now includes `FOCUSING` between `CENTERED` and `PREVIEWING`
  - `TestStackCaptureFails` updated from `fail_on_capture=6` to `fail_on_capture=17` (align #1 + recenter #2 + 11 autofocus samples + 3 preview = 16 captures before first stack frame)

**Result**: 844 tests passing, 95% coverage. Ruff clean (project sources). Mypy clean (project sources).

---

## 2026-04-26 — Sprint 6: NumpyStacker with astroalign registration

**What changed**:

- `smart_telescope/adapters/numpy_stacker/stacker.py` (NEW) — `NumpyStacker(StackerPort)`:
  - First frame stored as reference (no astroalign needed)
  - Subsequent frames: `astroalign.register(frame, reference)` → mean-stack on success
  - Registration failures: silently rejected, count incremented
  - `get_current_stack()` / `add_frame()` return FITS bytes of mean-stacked float32 array
  - `astroalign` imported at module level as `_aa`; gracefully set to `None` if not installed
  - `ImportError` raised only if second frame attempted without astroalign present
- `smart_telescope/api/deps.py` — `get_stacker()` added:
  - Returns `NumpyStacker` when astroalign available
  - Falls back to `MockStacker` if `ImportError` (tests, no-astroalign environments)
- `tests/unit/adapters/numpy_stacker/test_numpy_stacker.py` (NEW) — 17 tests:
  - `autouse` fixture patches module-level `_aa` → identity mock (no astroalign required on dev machine)
  - Tests cover reset, first-frame reference, registration success/failure, mean arithmetic, SNR improvement

**Result**: 497 tests passing. Ruff clean. Mypy clean.

---

## 2026-04-26 — Sprint 4: Solar exclusion gate (M2 safety)

**What changed**:

- `smart_telescope/domain/solar.py` (NEW) — Solar position + exclusion gate:
  - `sun_position_now() → SolarPosition` via astropy `get_sun(Time.now())`
  - `angular_separation_deg(ra1_h, dec1_d, ra2_h, dec2_d) → float` (degrees)
  - `is_solar_target(ra_h, dec_d, *, threshold_deg=10.0, sun=None) → (bool, float)`
  - Threshold default: 10° exclusion zone around the Sun
- `smart_telescope/api/mount.py` — Solar gate added to `POST /api/mount/goto`:
  - Calls `is_solar_target()` before every slew (unless `?confirm_solar=true`)
  - Returns HTTP 403 with `{"error": "solar_exclusion", "sun_separation_deg": N}` when blocked
  - `confirm_solar=true` bypasses gate entirely (explicit acknowledgement pattern)
- `scripts/spikes/sp3_astroalign_feasibility.py` (NEW) — SP-3 spike:
  - Generates synthetic 2080×3096 frames with 80 Gaussian PSF stars
  - Applies known pixel offset to source frame
  - Calls `astroalign.register()` + `find_transform()`; verifies residual < 2 px
  - Reports timing vs. 30 s budget; advises on downsampling if over budget
- `tests/unit/domain/test_solar.py` (NEW) — 14 solar domain tests
- `tests/unit/api/test_mount.py` — 7 new solar gate tests added to `TestMountGotoSolarGate`

**Result**: 480 tests passing. Ruff clean. Mypy clean.

---

## 2026-04-26 — Sprint 5: WebSocket live preview (M3 foundation)

**What changed**:

- `smart_telescope/domain/stretch.py` (NEW) — `auto_stretch(pixels) → uint8`:
  - 0.5th–99.5th percentile clip + linear scale to [0, 255]
  - Uniform/zero arrays return black (handles MockCamera gracefully)
- `smart_telescope/api/preview.py` (NEW) — `GET /ws/preview?exposure=<s>`:
  - Accepts WebSocket, loops: `capture → stretch → JPEG → send_bytes`
  - Uses `asyncio.to_thread` for the blocking camera call
  - Exposure validated: 0 < exposure ≤ 60 s; invalid values close with 403
  - Handles `WebSocketDisconnect` and abrupt `RuntimeError` cleanly
- `smart_telescope/app.py` — preview router included
- `smart_telescope/static/index.html` — Live Preview panel:
  - Start/Stop buttons with exposure input
  - `<img>` element updated via Blob URL on each binary WebSocket message
  - Frame counter + last-frame timestamp overlay
  - Auto-reconnect on abnormal close (3 s delay); no reconnect on user Stop
  - Connecting / Live / Stopped dot indicator
- `tests/unit/domain/test_stretch.py` (NEW) — 9 stretch tests
- `tests/unit/api/test_preview.py` (NEW) — 16 WebSocket endpoint tests

**Result**: 495 tests passing, 96% coverage. Ruff clean. Mypy clean (49 source files).

---

## 2026-04-26 — SP-1 + SP-2: hardware spike scripts

**What changed**:

- `scripts/spikes/sp1_touptek_arm64.py` — SP-1 spike: checks ARM64 platform, locates `libtoupcam.so`, imports the SDK, enumerates cameras, attempts software-trigger RAW-16 capture. Writes FITS if `--fits-out` path given. Reports PASS / PARTIAL (SDK ok, no camera) / FAIL.
- `scripts/spikes/sp2_astap_pi.py` — SP-2 spike: checks ASTAP binary (ARM64), locates G17 catalog (`.290` files), runs a timed full-sky solve on a provided FITS (or synthetic blank to verify the binary). Reports solve time vs. 60 s threshold. Reports memory snapshot via `free -h`.

**How to run on Pi 5**:
```
# SP-1 (camera must be connected for full PASS)
python scripts/spikes/sp1_touptek_arm64.py --fits-out /tmp/sp1_frame.fits

# SP-2 (sky FITS required for solve-time measurement)
python scripts/spikes/sp2_astap_pi.py --fits /tmp/sp1_frame.fits
```

**Prerequisities**:
- SP-1: place `libtoupcam.so` (ARM64) next to the script (download from ToupTek)
- SP-2: `sudo dpkg -i astap_arm64.deb`; G17 catalog in `~/.astap/`

---

## 2026-04-26 — S0-7: FitsFrame migration — typed domain object throughout pipeline

**What changed**:

- `smart_telescope/domain/frame.py` — added `to_fits_bytes()`:
  - Returns `self.data` if cached bytes are present (file-loaded frames)
  - Otherwise serializes `pixels+header` via astropy (hardware-captured frames, e.g. ToupcamCamera)
- `smart_telescope/ports/solver.py` — `solve(frame_data: bytes, ...)` → `solve(frame: FitsFrame, ...)`
- `smart_telescope/ports/stacker.py` — removed `StackFrame` dataclass; `add_frame(StackFrame)` → `add_frame(frame: FitsFrame, frame_number: int)`
- `smart_telescope/adapters/astap/solver.py` — writes `frame.to_fits_bytes()` to temp file
- `smart_telescope/adapters/mock/solver.py` — updated signature
- `smart_telescope/adapters/mock/stacker.py` — removed `StackFrame`; uses `_count` instead of `_frames` list
- `smart_telescope/workflow/stages.py` — removed `StackFrame` import; passes `frame` directly to solver and stacker; no more `.data` extraction
- `tests/unit/adapters/astap/test_subprocess.py` — updated to construct `FitsFrame` instead of passing raw bytes
- `tests/integration/test_real_solver_replay.py` — updated `solve()` calls; added missing `focuser=MockFocuser()`

**Result**: 473 tests passing, 96% coverage. Ruff clean. Mypy clean (47 source files). S0-7 complete.

---

## 2026-04-24 — M1 API complete: session/connect, solver validation, simulator wiring

**What changed**:

- `smart_telescope/api/session.py` (NEW) — `POST /api/session/connect`:
  - Returns `{camera, mount, focuser, solver}` per-device `{status, error, action}`
  - Always HTTP 200; named error + suggested action for each failed device
  - `solver` field checks ASTAP executable and G17 catalog presence
- `smart_telescope/api/solver.py` (NEW) — `GET /api/solver/status`:
  - Returns `{astap, catalog, ready}` — ASTAP path, catalog dir, boolean readiness
- `smart_telescope/adapters/astap/solver.py` — added `find_g17_catalog(astap_exe)`:
  - Searches executable directory first, then `~/.astap`, `/usr/share/astap`, `C:/ProgramData/astap`
  - Detects G17 catalog by presence of `.290` extension files
- `smart_telescope/api/deps.py` — added `SIMULATOR_FITS_DIR` env var:
  - Priority: `ONSTEP_PORT` → real hardware; `SIMULATOR_FITS_DIR` → SimulatorCamera + SimulatorMount + SimulatorFocuser; neither → mocks
- Tests: 437 passing, 89% coverage

**Result**: All three M1 API stories complete. Remaining M1 gate items require hardware (SP-1/SP-2 on Pi).

---

## 2026-04-24 — SimulatorMount and SimulatorFocuser

**What changed**:

- `smart_telescope/adapters/simulator/mount.py` (NEW) — `SimulatorMount(slew_time_s=0.0)`:
  - `connect()` always returns True
  - `goto()` immediately sets position; enters SLEWING → TRACKING via `threading.Timer` when `slew_time_s > 0`
  - `stop()` cancels pending timer and sets state to UNPARKED
  - `disconnect()` cancels pending timer and sets state to PARKED
  - Thread-safe (all state protected by `threading.Lock`)
- `smart_telescope/adapters/simulator/focuser.py` (NEW) — `SimulatorFocuser(move_time_s=0.0)`:
  - `move()` immediately updates position (instant) or enters moving state via timer
  - `stop()` cancels pending timer without changing position
  - `disconnect()` cancels pending timer and clears moving state
  - Thread-safe
- `tests/unit/adapters/simulator/test_simulator_mount.py` (NEW) — 24 tests
- `tests/unit/adapters/simulator/test_simulator_focuser.py` (NEW) — 20 tests

**Result**: 380 tests passing, 86.32% coverage. Ruff clean. Mypy clean.

---

## 2026-04-24 — OnStep focuser adapter, mount/focuser API + UI

**What changed**:

- `smart_telescope/ports/focuser.py` — added `is_moving() -> bool` and `stop() -> None` abstract methods
- `smart_telescope/adapters/mock/focuser.py` — implemented `is_moving()` (returns False) and `stop()` (no-op)
- `smart_telescope/adapters/onstep/focuser.py` (NEW) — `OnStepFocuser` implementing `FocuserPort`:
  - `connect()`: opens serial, sends `:FA#`, requires reply `"1"` (focuser active)
  - `get_position()`: `:FG#` → int
  - `move(steps)`: `:FS{steps}#` (absolute positioning)
  - `is_moving()`: `:FT#` → True if reply is `"M"`
  - `stop()`: `:FQ#` (no reply)
- `smart_telescope/api/deps.py` (NEW) — singleton dependency providers for mount and focuser; mocks by default; uses real OnStep adapters when `ONSTEP_PORT` env var is set
- `smart_telescope/api/mount.py` (NEW) — FastAPI router with: `GET /api/mount/status`, `POST /api/mount/unpark`, `/track`, `/stop`, `/goto`
- `smart_telescope/api/focuser.py` (NEW) — FastAPI router with: `GET /api/focuser/status`, `POST /api/focuser/move`, `/nudge`, `/stop`
- `smart_telescope/app.py` — includes mount and focuser routers
- `smart_telescope/static/index.html` — Mount panel (state badge, RA/Dec, Unpark/Track/Stop/GoTo) and Focuser panel (position, ±1000/±100/±10 nudge buttons, absolute move, Stop); both panels auto-refresh on load
- `tests/unit/adapters/onstep/test_onstep_focuser.py` (NEW) — 23 adapter tests
- `tests/unit/api/test_mount.py` (NEW) — 19 API tests
- `tests/unit/api/test_focuser.py` (NEW) — 22 API tests

**Result**: 333 tests passing, 87% coverage.

---

## 2026-04-24 — Ingest: OnStep Command Protocol (official wiki)

**Source**: https://onstep.groups.io/g/main/wiki/23755 (retrieved 2026-04-24)

**Pages created**:
- `onstep-protocol.md` — full LX200 command reference: slewing, tracking, park, sync, focuser (all F-commands), date/time, site, firmware; includes adapter implementation notes and two flagged discrepancies

**Pages updated**:
- `hardware-platform.md` — OnStep section now references the protocol page and notes shared serial port for mount + focuser
- `index.md` — added onstep-protocol entry

**Key findings**:
- **Absolute focuser position command confirmed**: `:FS[n]#` (e.g. `:FS1000#` → moves to step 1000, returns 0 or 1). This is what `OnStepFocuser.move(position)` must use.
- **Relative move also available**: `:FR[±n]#` (no reply) — useful for nudge operations.
- **Focuser motion status**: `:FT#` → `M#` (moving) or `S#` (stopped) — enables non-blocking polling.
- **Two discrepancies flagged** vs current `OnStepMount` adapter:
  1. Unpark: spec says `:hR#`, adapter uses `:hU#` — believed to be a V4 vs OnStepX version difference; needs verification on hardware.
  2. Slewing indicator: spec says reply is `0x7F` (DEL), adapter checks for `|` (0x7C) — also likely version-specific; verify on hardware.

---

## 2026-04-23 — Ingest: ToupTek SDK interface description + ToupcamCamera adapter

**Source**: resources/touptek/toupcam.py, resources/touptek/samples/simplest.py

**Pages created**:
- `touptek-sdk.md` — SDK architecture (ctypes wrapper), trigger modes, RAW-16 capture flow, TEC cooling, built-in correction pipeline, filter wheel, event constants, and project adapter design note

**Pages updated**:
- `hardware-platform.md` — expanded ToupTek Camera section: SDK driver choice, RAW-16 mode decision, adapter location
- `index.md` — added touptek-sdk entry

**Code created**:
- `smart_telescope/adapters/touptek/camera.py` — `ToupcamCamera` implementing `CameraPort`; software-trigger RAW-16 mode; threading.Event callback bridge; ctypes buffer; float32 FitsFrame output
- `tests/unit/adapters/touptek/test_touptek_camera.py` — 24 unit tests (connect, capture, disconnect), all green, no hardware required

**Key design decision**: SDK's built-in FFC/DFC corrections are bypassed (`TOUPCAM_OPTION_RAW = 1`); our stacking pipeline handles calibration frame subtraction.

---

## 2026-04-22 — Documentation update: Pi installer, reviewer corrections, Sprint 0 close

**What changed**:
- `README.md` — added Raspberry Pi 5 one-command install section; updated project structure to include `scripts/` and `hardware.yml`; clarified hardware tests live in `hardware.yml` (manual trigger only)
- `docs/agile-plan.md` — updated all Python version references from 3.11 → 3.13; removed deprecated `ANN101`/`ANN102` ruff ignore rules; corrected S0-6 (`asyncio.Event` → `threading.Event`); added `pytest-mock>=3.15` to example `pyproject.toml`; marked Sprint 0 stories S0-1 through S0-6, S0-8, S0-9 as done; updated Sprint 0 DoD checkboxes; noted S0-7 deferred to Sprint 1
- `wiki/vertical-slice-mvp.md` — corrected C8 native pixel scale from `~0.20 arcsec/px` to `0.38 arcsec/px` to match `C8_NATIVE` profile in `runner.py`
- `scripts/install_pi.sh` — new: automated installer for Raspberry Pi OS 64-bit (Bookworm); covers system packages, Python 3.13 via deadsnakes PPA, venv, `pip install -e .[dev]`, optional ASTAP ARM64, verification test run

**Source**: reviewer audit (2026-04-22), `runner.py:49` for pixel scale ground truth

---

## 2026-04-21 — Sprint 0 executed: dev pipeline + TDD foundation

**What changed**:
- `pyproject.toml` — Python version pin relaxed to >=3.10; ruff target-version py310; mypy python_version 3.10; ANN excluded from test files
- `smart_telescope/ports/focuser.py` — new `FocuserPort` ABC (connect, disconnect, move, get_position)
- `smart_telescope/ports/mount.py` — added `stop()` abstract method
- `smart_telescope/adapters/mock/focuser.py` — new `MockFocuser` (fail_connect, move, position)
- `smart_telescope/adapters/mock/mount.py` — implemented `stop()`
- `smart_telescope/workflow/runner.py` — added: structured logging (INFO per state transition), focuser wired into connect stage and cleanup, `stop()` + `threading.Event` cancellation, `_wait_for_slew` checks stop event, `run()` clears event on entry
- `tests/unit/workflow/test_logging.py` — 6 logging tests (TDD: RED → GREEN)
- `tests/unit/workflow/test_focuser.py` — 12 focuser tests (TDD: RED → GREEN)
- `tests/unit/workflow/test_cancellation.py` — 6 cancellation tests (TDD: RED → GREEN)
- `tests/unit/adapters/test_replay_camera.py` — 8 ReplayCamera unit tests
- `.github/workflows/ci.yml` — GitHub Actions: lint → typecheck → test + coverage gate on push/PR
- All source files ruff-clean and mypy-strict-clean

**Result**: 133 tests passing, 15 skipped (hardware), 98% coverage. Ruff clean. Mypy clean. CI configured.

---

## 2026-04-19 — Hardware update: camera changed to ToupTek

**Pages updated**:
- `hardware-platform.md` — added ToupTek camera section; updated summary
- `vertical-slice-mvp.md` — replaced ZWO ASI SDK references with ToupTek SDK
- `README.md` — updated hardware table

---

## 2026-04-19 — Walking skeleton implementation

**Source**: vertical-slice-mvp.md (spec), implementation

**What was built**:
- `smart_telescope/domain/` — `SessionState` enum, 8 typed result dataclasses, `SessionLog` with full `to_dict()` schema
- `smart_telescope/ports/` — abstract interfaces for camera, mount, solver, stacker, storage
- `smart_telescope/workflow/runner.py` — `VerticalSliceRunner`: linear 8-stage pipeline, `WorkflowError`, state machine with `on_state_change` callback
- `smart_telescope/adapters/mock/` — 5 mock adapters with configurable failure modes
- `tests/integration/test_vertical_slice.py` — 28 tests: happy path (11), plate-solve failure (4), recenter exceeded (4), stack failure (2), save failure (3), mount failures (4)

**Result**: 28/28 tests passing. One full `IDLE → SAVED` run executes in <1ms.

---

## 2026-04-19 — Vertical slice definition

**Source**: requirements.md, hardware-platform.md (internal synthesis)

**Pages created**:
- `vertical-slice-mvp.md` — full stage-by-stage spec for the MVP core slice: 8 stages, explicit state machine, acceptance criteria per stage, component map, and out-of-scope boundaries

**Pages updated**:
- `index.md` — added vertical-slice-mvp entry

---

## 2026-04-19 — Ingest: requirements review

**Source**: requirements-review (external analysis, 2026-04-19)

**Pages updated**:
- `requirements.md` — retagged 6 items to MVP (profiles, staged solve, autofocus, optical-train awareness, recentering, session persistence); promoted mosaic/scheduled/multi-night to MVP+; added 4 new sections (connectivity lifecycle, operational fallback, config validity, performance targets); added solar safety gate and emergency stop; marked ~15 items as needing acceptance criteria

**Pages created**:
- `requirements-review.md` — full review verdict, quality critique, retagging rationale, missing sections

---

## 2026-04-19 — Initial ingest: SmartTelescope.md

**Source**: raw/SmartTelescope.md

**Pages created**:
- `smart-telescope.md` — category definition and seven defining traits
- `seestar-s50.md` — ZWO Seestar S50 reference product
- `vaonis-vespera.md` — Vaonis Vespera Pro reference product
- `hardware-platform.md` — Celestron C8 + Raspberry Pi 5 + OnStep V4 platform details
- `plate-solving.md` — concept: autonomous sky alignment
- `live-stacking.md` — concept: real-time computational imaging
- `autofocus.md` — concept: automated focus with star-size metrics
- `requirements.md` — full MVP/MVP+/Full requirement set for the C8 build
- `index.md` — initial table of contents
- `log.md` — this file

---

## 2026-05-17 — BUG-009, BUG-024, M3-004

**What changed:**

- `api/autogain.py` (BUG-024): `_worker()` now resolves the optical train for the
  camera being processed and ANDs `train.has_focuser` with the global
  `focuser.is_available`.  Guide cameras configured without a focuser no longer
  receive `POSSIBLE_FOCUS_OR_POINTING_ERROR` from autogain when the main camera's
  OnStep focuser is connected.  Falls back to global availability when the camera
  index is not found in any train.

- `static/index.html` (BUG-009): Replaced the "any camera has TEC" heuristic for
  cooling card visibility with a per-selected-camera check.  New
  `onCoolingCamChange(role)` function fetches `/api/cameras/{idx}/capabilities` and
  shows or hides the cooling card based on `caps.has_tec`.  Called on
  `s1-cooling-cam-select` `onchange`, on "Connect All", and at page init.

- `tests/unit/api/test_r4_role_camera.py`: Four new tests in
  `TestAutogainHasFocuserPerTrain` covering: guide cam no focuser (even when global
  focuser available), main cam focuser present and available, main cam focuser
  configured but hardware unavailable, unknown camera index falls back to global.

**todo.md:** BUG-009, BUG-024, M3-004 marked complete.

---

## 2026-05-17 — R5-001..003, BUG-008

**What changed:**

- `config.py` (R5-001..003): Replaced bare module-level TOML loading + `sys.exit`
  with:
  - `ConfigError` exception class — structured parse failure type
  - `_load_config_from_disk()` — encapsulates all file reading logic (explicit load)
  - `_load_error` module variable — stores parse error without killing the process
  - `check_load_error()` — raises `ConfigError` if load failed; called from
    `RuntimeContext.connect_devices()` so bad configs surface at Connect All time

- `services/readiness.py`: `_check_config_file()` now checks `_load_error` first
  and returns a RED item with the parse error message and repair guidance.

- `tests/unit/api/test_readiness.py`: 8 new tests:
  - `TestConfigError`: check_load_error() no-op on no error, raises on error,
    readiness RED on parse error, overall RED on parse error
  - `TestExpandPath`: tilde expansion, empty string, absolute path, and verifies
    that `config.STARS_CFG` contains no literal `~` (BUG-008 regression guard)

- BUG-008 confirmed resolved by R5-004's `_expand()` — `STARS_CFG` is always
  expanded at module load time, never stored with `~`.

**todo.md:** R5-001..003, BUG-008, M3-002 marked complete.

---

## 2026-05-17 — R2-003, R2-005, M3 milestone cleanup

**What changed:**

- `services/device_state.py` (R2-003): Added `record_command(name)`,
  `record_command_error(msg)`, `get_last_command() → (name, at, err)` to
  `DeviceStateService`.

- `services/device_state.py` (R2-005): Added `wait_for_mount_state(target, timeout_s)`
  (polls until state equals target) and `wait_while_mount_state(current, timeout_s)`
  (polls until state differs from current).  Both use the background-poll cache for
  consistency with what the UI sees.

- `api/mount.py` (R2-003): All command endpoints — park, unpark, goto, home, track,
  stop — now call `device_state.record_command(name)` before issuing and
  `record_command_error(msg)` on failure.  `MountStatus` extended with
  `last_command`, `last_command_age_s`, `last_command_error`.

- `api/mount.py` (R2-005): `mount_unpark` now uses `wait_while_mount_state(PARKED)`
  (uses cached state, consistent with UI) instead of a direct hardware poll loop.
  `mount_park` waits up to 5 s for PARKED confirmation after issuing the command.

- `tests/unit/services/test_device_state.py`: 10 new tests — R2-003 command tracking
  (initial None, record clears error, error keeps name, overwrite), R2-005 convergence
  helpers (immediate match, timeout, transition detection for both helpers).

- `docs/todo.md`: M3-001, M3-003, M3-005, BUG-003, BUG-017 marked complete.
  R2-003, R2-005 marked complete.

---

## 2026-05-17 — UX2-001..004 (Intent-Based Observation Flow)

**What changed:**

- `smart_telescope/static/index.html`:
  - Stage 5 card title updated from "Run Observation" to "Start Observation" (UX2-001).
  - Added a 5-step pipeline strip inside the run-status panel (UX2-002):
    Connect → GoTo → Centre → Focus → Capture. Each step updates live to
    pending / active (blue) / done (green, ✓) / failed (red, ✗) as the session
    progresses through `SessionState` transitions.
  - Added recovery banner inside the run-status panel (UX2-004): shown when
    `state=FAILED`; displays failure reason, a contextual action suggestion keyed
    on `failure_stage`, and a ↺ Retry button that re-runs `s5StartSession()`.
  - `_s5UpdateSteps(data)`: new function mapping `SessionState` → active step and
    `failure_stage` → failed step; also drives the recovery banner.
  - `_s5ResetRunUI()`: extended to reset step strip and hide recovery banner on
    session start.
  - CSS: new `.s5-step`, `.s5-step-circle`, `.s5-step-label`, `.s5-step-line`
    classes with `.step-active`, `.step-done`, `.step-failed`, `.line-done` modifiers.
  - UX2-003 (automatic sequencing of autofocus/solve/recenter) is already
    implemented in `VerticalSliceRunner`; the pipeline strip now makes this visible.

- `docs/todo.md`: UX2-001, UX2-002, UX2-003, UX2-004 marked complete.

---

## 2026-05-17 — UX4-004, R6-005, UX5-001..004 (global STOP + error model)

**What changed:**

- `smart_telescope/static/index.html`:
  - Mount strip now carries `class="visible"` in HTML so it is shown from page
    load; `goToStage()` no longer removes `visible` when navigating to Stage 1.
    Emergency STOP button is now globally visible at all times (UX4-004 / R6-005).
  - Added `_ERROR_PATTERNS` array and `friendlyError(raw)` function (UX5-001):
    pattern-matches raw error strings to `{message, hint}` pairs in three
    categories — mount/OnStep (UX5-002), camera (UX5-003), solver (UX5-004).
  - `setStatus(..., isError=true)` now calls `friendlyError()` and renders the
    translated message with an optional hint in a smaller muted line beneath it.
    All existing error callsites benefit automatically (park, unpark, goto, home,
    connect, autofocus, etc.).

- `docs/todo.md`: UX4-004, R6-005, UX5-001..004 marked complete.

---

## 2026-05-17 — M4-002 (Visible Tonight target card)

**What changed:**

- `smart_telescope/static/index.html`:
  - Added "Visible Tonight" card to Stage 5 (M4-002): fetches
    `GET /api/catalog/tonight?min_altitude=20&limit=12` and renders a
    clickable list of Messier objects above 20° at the current time, sorted by
    altitude. Each row shows the object name, common name, type chip (e.g.
    "Galaxy", "Glob. Cluster"), altitude in degrees, and a ☀ warning icon for
    objects with `solar_safe=false`.
  - `s5LoadTargets()`: async function that drives the card; dot indicator shows
    yellow while loading, green on success, red on error, grey when list is empty.
  - `s5UseTarget(name)`: clicking a row copies the name into the target input and
    moves focus to the Start Session button with a brief status message.
  - `goToStage(5)` now calls `s5LoadTargets()` so the card auto-loads on entry.
  - CSS: `.tonight-row`, `.tonight-name`, `.tonight-type-chip`, `.tonight-alt`
    for list layout.

- `docs/todo.md`: M4-001..003, M4-005, M4-006 marked complete.

---

## 2026-05-17 — R1-008, R1-009 (OnStep serial bus abstraction)

**What changed:**

- `smart_telescope/adapters/onstep/serial_bus.py` (new): `OnStepSerialBus` owns
  the `serial.Serial` handle and `threading.Lock` that were previously private
  attributes of `OnStepMount`. Exposes three public methods:
  - `send(cmd) -> str` — locked write + readline, decoded and stripped.
  - `raw_send(cmd) -> bytes` — locked write + readline, raw bytes.
  - `write_bypass(data: bytes) -> None` — lockless write for emergency-stop
    commands (:Q#, :FQ#) that must interrupt an in-progress command.

- `smart_telescope/adapters/onstep/mount.py`:
  - Replaced `self._serial` + `self._lock` with `self._bus: OnStepSerialBus`.
  - Added a `_serial` property (getter + setter) so existing tests that inject
    `mount._serial = fake` continue to work without changes.
  - Added `serial_bus` public property for `OnStepFocuser` to consume.
  - `_raw_send` / `_send` now delegate to bus; `stop()` calls
    `self._bus.write_bypass(b":Q#")`.
  - `connect()` creates the `serial.Serial` object locally and assigns it to
    `self._bus._serial`; product check logic is unchanged.

- `smart_telescope/adapters/onstep/focuser.py`:
  - Constructor signature changed from `OnStepFocuser(mount: OnStepMount)` to
    `OnStepFocuser(bus: OnStepSerialBus)`. No more private-member access.
  - All `self._mount._send(...)` / `._raw_send(...)` / `._serial` calls replaced
    with `self._bus.send(...)` / `.raw_send(...)` / `.write_bypass(...)`.

- `smart_telescope/runtime.py`: Updated `OnStepFocuser(mount)` →
  `OnStepFocuser(mount.serial_bus)`.

- `tests/unit/adapters/onstep/test_onstep_focuser.py`:
  - Replaced `MagicMock(spec=OnStepMount)` with `MagicMock(spec=OnStepSerialBus)`.
  - `stop()` test now asserts `bus.write_bypass.assert_called_once_with(b":FQ#")`
    instead of reaching into a mock serial attribute.

- `tests/unit/adapters/onstep/test_onstep_mount.py`: no changes needed — the
  `"smart_telescope.adapters.onstep.mount.serial.Serial"` patch target is still
  valid because `connect()` still lives in mount.py.

- `tests/unit/adapters/onstep/test_with_fake_serial.py`: no changes needed — the
  `_serial` property setter makes `mount._serial = fake` transparently update the
  bus.

**Test result:** 2415 passed (pre-existing `test_frame_counter_increments_on_donut_measurement` excluded).

- `docs/todo.md`: R1-008, R1-009 marked complete.

---

## 2026-05-17 — BUG-002b, BUG-015 (autogain cancel + mount button grouping)

**What changed:**

- `smart_telescope/api/autogain.py` (BUG-002b):
  - `GET /api/autogain/status`: when `job.cancelling=True` and the result status
    is not `AUTO_GAIN_CANCELLED`, the endpoint now returns `AUTO_GAIN_CANCELLED`
    instead of the actual result. This prevents a race where the background
    worker finishes with `POSSIBLE_FOCUS_OR_POINTING_ERROR` just as the cancel
    request arrives, which would cause the UI to show the warning badge after
    the user clicked Cancel.

- `tests/unit/api/test_autogain.py`: added
  `test_status_returns_cancelled_when_job_completed_after_cancel_request` to
  `TestCancelEndpoint`, directly exercising the race scenario.

- `smart_telescope/static/index.html` (BUG-015):
  - `mountCard()`: wrapped the Home / Unpark / Park / Stop buttons in a
    `<span style="display:flex;gap:0.5rem;flex-wrap:nowrap">` so they are
    always visually grouped and never wrap independently onto separate lines
    when the controls row is narrow.

**Test result:** 2416 passed.

- `docs/todo.md`: BUG-002b, BUG-015 marked complete.

---

## 2026-05-21 — Camera ID Mapping + Camera Offset Configuration

**Sources:** `resources/hlrequirements/camera_id list.md`, `resources/hlrequirements/camera_offset.md`

**Camera ID Mapping (CID-001..005):**
- `config.py`: `_parse_cameras()` accepts `str|int`; `CAMERAS`, `TOUPTEK_INDEX`, `CAMERA_SERIALS` globals
- `CameraNameResolver`: case-insensitive substring + serial verification; wired into `runtime._build_adapters()`
- `templates/config.toml`: `[cameras]` now uses model name as default; `[camera_serials]` block added

**Camera Offset Configuration (CO-001..006):**
- `config.py`: `_parse_camera_offsets()` and `CAMERA_OFFSETS`
- `CameraOffsetService`: lookup by model+gain (bidirectional substring); `apply()` sets `set_black_level`
- `RuntimeContext`: `_apply_camera_offsets()` called in `connect_devices()` and `get_preview_camera()`
- `AutoGainService.run_one_shot()`: `offset_service` param; `cur_offset` seeded from configured value
- `calibration_capture.py`: `offset_service` param on `prepare_bias/dark/flat`; API passes `rt.camera_offset_service`
- `templates/config.toml`: `[camera_offsets]` section with defaults for G3M678M/ATR585M (150) and GPCMOS02000KPA (10)

---

## 2026-05-17 — Fix pre-existing test failure in test_pipeline_wiring.py

**What changed:**

- `tests/unit/services/test_pipeline_wiring.py`: added `_donut_camera()` helper
  (an alias for `_star_then_donut_camera()`) which was referenced by
  `TestFinePipeline::test_frame_counter_increments_on_donut_measurement` but
  never defined, causing a persistent `NameError` since the test was committed.

**Test result:** 2429 passed (all tests green, no exclusions needed).

---

## 2026-07-07 — Confirm Time & Location panel

**What changed:**

- `smart_telescope/domain/location_source.py` (new): `LocationSource` enum
  (`CONFIG_FILE | GPS_FIX | IP_LOOKUP | USER_ENTERED | SAVED_LOCATION`) +
  `is_valid()` helper, modeled on `domain/raspberry_time_trust.py`.
- `smart_telescope/services/ip_geolocation_service.py` (new):
  `IpGeolocationService` — one-shot, user-triggered-only IP-based geolocation
  lookup via stdlib `urllib.request` (no new pip dependency); catches every
  failure mode internally and never raises.
- `smart_telescope/config.py`: new `OBSERVER_HEIGHT_M` (`[observer].height_m`);
  `OBSERVER_HOME_LAT/LON/HEIGHT_M` (permanent Home baseline, independent of
  whatever location is currently active); `OBSERVER_LOCATION_SOURCE`/
  `OBSERVER_LOCATION_NAME` in-memory bookkeeping; `LocationSpec` dataclass +
  `_parse_locations()`/`LOCATIONS` parsed from a table-of-tables
  `[locations.<name>]` section (same convention as `[cameras.<role>]` /
  `[telescopes.<name>]` — no TOML array-of-tables precedent in this codebase).
- `smart_telescope/api/location.py` (new): `GET /api/location/status`
  (consolidated active/home/saved_locations/gps/local_time/`time_from_gps`),
  `GET /api/location/ip-lookup`, `POST /api/location/confirm`
  (`target=home` rewrites `[observer]`; `target=saved` upserts
  `[locations.<name>]`; either way updates in-memory active state, best-effort
  pushes to OnStep via `mount_sync_clock`, and always calls
  `mount_confirm_time` so one Confirm click also marks Pi time
  `USER_CONFIRMED`), `DELETE /api/location/saved/{name}`. Config-file writes
  use line-scanned section boundaries (`_find_section_lines`: a line only
  counts as a new section when `[` is the first non-whitespace character) so
  patching `[observer]` can never corrupt a `[locations.*]` block's own
  `lat =`/`lon =` lines (the old `api/gpsd.py` regex was an unscoped
  whole-document substitution — safe only while `lat =`/`lon =` appeared
  nowhere else in the file). Reuses `mount_sync_clock`/`mount_confirm_time`
  from `api/mount.py` directly as plain function calls — no shared helper, no
  circular import, `POST /api/mount/sync_clock`/`confirm_time` keep working
  standalone.
- `smart_telescope/api/gpsd.py`: removed `POST /api/observer/location`,
  `ObserverLocationRequest`, `update_observer_location` — superseded by
  `api/location.py`. `GET /api/gpsd/status` untouched.
- `smart_telescope/app.py`: registered `location_router`.
- `templates/config.toml`: `[observer].height_m` + documented example
  `[locations.<name>]` block.
- `smart_telescope/static/index.html`: removed the GPS-drift banner and the
  old read-only `Observer Lat`/`Observer Lon`/`Apply GPS Location` row;
  Observer & Time card gained a "Confirm Time & Location" subsection — local
  time + `GPS` badge (shown only when Pi time trust source is `GPSD_FIX`),
  a location `<select>` (Home / saved locations / "+ New location…"),
  always-editable lat/lon/height_m inputs, a source badge, "Use GPS fix" /
  "Look up by IP" quick-fill buttons (fill only, no auto-write), a delete
  button for saved locations, and the Confirm button.
- `smart_telescope/static/js/setup.js`: removed `checkGpsStatus()` /
  `applyGpsLocation()`; added `refreshLocationPanel()`, `_renderLocationPanel()`,
  `onLocationSelectChange()`, `useGpsFix()`, `lookupByIp()`,
  `confirmTimeAndLocation()`, `deleteSavedLocation()`. A `_locPanelDirty` flag
  stops the 15 s background poll from clobbering an in-progress edit.
- `smart_telescope/static/js/app.js`: init block now calls
  `refreshLocationPanel()` (15 s interval) instead of `checkGpsStatus()`;
  removed the now-dead `site-lat`/`site-lon` element writes in
  `initSiteConfig()`.

**Test result:** 61 new tests (15 domain + 8 service + 27 API + 6 config +
5 config-parse), all passing. Full suite: 3903 passed, 39 skipped (4
pre-existing, unrelated failures in `test_get_sync_status.py` confirmed via
`git stash` to predate this change). Manually verified live against the
running dev server: `GET /status`, `GET /ip-lookup` (real IP-geo lookup
succeeded), `POST /confirm` for both `home` and `saved` targets, and
`DELETE /saved/{name}` all behaved as designed; HTML/JS assets parse cleanly.

---

## 2026-07-07 — Confirm Time & Location panel: automatic-first revision

**What changed:** revision of the same-day earlier entry, after a requirements
re-check surfaced a gap.

- `raw/SmartTelescope.md` ("Automatic location/time acquisition — from phone,
  network, or GPS if available [MVP]") and `wiki/requirements.md` §9
  ("Automation-first UX — user does not manage mount sync… separately")
  meant the original manual-click "Use GPS fix" design was a regression from
  the old auto-polling GPS-drift banner it replaced. `docs/todo.md`
  M8-010/REQ-TIME-005 also already specifies a single Stage 1 "Time /
  Location Verification" panel — a second, separate confirm card fragmented
  that.
- `smart_telescope/api/location.py`: `GpsInfo.usable` (new field) = fresh
  fix with `mode >= 2` (mirrors `services/master_source.py`'s
  `_MIN_GPS_MODE = 2`) — single source of truth for "is this fix good enough
  to suggest", replacing `available` (true for any TPV report, including
  `mode < 2`) as the gate. 4 new tests in `tests/unit/api/test_location.py`.
- `smart_telescope/static/index.html`: moved the entire location panel
  (local time + GPS badge, select/name/lat/lon/height inputs, source badge,
  quick-fill buttons, Confirm button) out of the "Observer & Time" card
  (reverted to just UTC/LST) and into `#s1-tl-card` ("Time / Location
  Verification"), appended after the existing `s1-tl-status` line. The
  existing `s1-tl-params`/`s1-tl-controls` block (REQ-TIME-005's tested
  20-field contract) is untouched; "Confirm Pi Time" and "Confirm Time &
  Location" now coexist in the same card.
- `smart_telescope/static/js/setup.js`: `_renderLocationPanel()` now prefers
  `d.gps` over `d.active` on every non-dirty render when `d.gps.usable` is
  true — a fresh fix is suggested automatically (source badge → `GPS_FIX`,
  ready for one Confirm click) instead of requiring a manual "Use GPS fix"
  click first; falls back to `d.active` exactly as before when no usable fix
  exists. `useGpsFix()` and the `loc-gps-btn` disabled-gate switched from
  `gps.available` to `gps.usable` for consistency.
- OnStep's native 4-site memory (`:Wn#`/`:SM#`/`:SP#`, undocumented in any
  adapter code) was flagged as a possible integration point for the
  saved-location library but intentionally deferred — config.toml stays the
  source of truth for now.

**Test result:** 4 new tests (65 total for this feature area), full suite
3907 passed, 39 skipped (same 4 pre-existing unrelated `test_get_sync_status.py`
failures as before). Manually verified live: panel confirmed absent from
Observer & Time, present in `#s1-tl-card` with both Confirm buttons; `gps.usable`
present and `false` with no GPSD running; confirm(saved)/delete round-trip
re-verified.

---

## 2026-07-08 — Deploy fix: pip silently skipping reinstall of unchanged-version wheel

**What changed:** the "Confirm Time & Location" UI changes shipped in
commits `eeec8e3`/`23aea26` did not appear on the Pi after two deploys, even
though the version pill correctly showed the right git hash and the user
hard-refreshed the browser. Investigated via a from-scratch Explore agent
(markup/JS/script-order/static-serving all checked and found correct) plus
`git rev-parse` reasoning in `api/version.py`.

**Root cause:** `scripts/astro_start.sh` (and `scripts/install_pi.sh`) build
a fresh wheel from the repo on every deploy and install it with plain
`pip install "$WHEEL"`. Since `pyproject.toml`'s `version = "0.1.0"` is
never bumped, the rebuilt wheel is always named
`smart_telescope-0.1.0-py3-none-any.whl` — pip treats this as "Requirement
already satisfied" and silently skips overwriting the installed package
files (including the `static/` package-data), so the server kept running
the very first build indefinitely. The git-hash version pill was misleading
because it reads the live repo checkout (`cwd=_ROOT` in `api/version.py`),
not the installed package, so it always looked "correct" regardless of
whether the reinstall actually happened.

- `scripts/astro_start.sh:102`: `pip install --quiet "$WHEEL"` →
  `pip install --quiet --force-reinstall --no-deps "$WHEEL"` (`--no-deps`
  keeps the frequent per-deploy path fast; a future dependency change in
  `pyproject.toml` needs a full `install_pi.sh` run to be picked up — noted
  inline).
- `scripts/install_pi.sh:214`: `pip install --quiet "$wheel"` →
  `pip install --quiet --force-reinstall "$wheel"` (no `--no-deps` — this is
  the full/initial setup path).

**Test result:** `bash -n` syntax check on both scripts, passed. No Python
tests affected (shell-script-only fix). Not yet verified against a live Pi
deploy from this machine — ask the user to confirm on next
`astro_start.sh` run.

---

## 2026-07-15 — OnStepAdapter v0.3.1 FSM check + full USB-connectivity migration task list

**Request:** Check tschoenfelder/OnStepAdapter v0.3.1 for its supported FSM and plan the
full replacement of SmartTScope's local OnStep USB connectivity with that adapter — never
modifying the adapter; genuine gaps become change requests. Add the migration task list as
high-priority items to `docs/todo.md`.

**Research (against the published release, per guardrail — release page, GitHub API,
raw files at tag v0.3.1):**

- v0.3.1 is a fully **independent** `onstep_adapter` package (own `mount.py`, `client.py`,
  `serial_bus.py`, `focuser.py`, `safety.py`, `ports/`); wheel ships no `smart_telescope/*`
  files. The 2026-07-11 "packaging fix only" assessment was wrong — corrected in todo.md.
- Supported FSM: `MountState` = 6 enum states (UNKNOWN, PARKED, UNPARKED, SLEWING,
  TRACKING, AT_LIMIT). HOME is a mechanical `:GU#` flag, not an enum state, exposed as
  `client.mount.last_decoded_status["at_home"]` (clarified by user; canonical check is
  `get_state()` then `last_decoded_status.get("at_home") is True`).
- Routed op `unpark_to_home_stop_tracking()` unparks, stops firmware auto-tracking, and
  returns `{"at_home", "final_status"}` — natively covers the quirk SmartTScope compensates
  for locally (`_explicit_tracking_started`, REQ-ST-003/005/006, SAFETY-001/002).
- Upstream `OnStepClient.__init__` hard-instantiates its own `OnStepMount` (no injection
  parameter) — the reason local `client.py` replicates the constructor.

**User decisions:** unpark switches to the routed op (retires local compensation after
hardware verification); AT_HOME derived locally from the decoded flag (7-state enum in
`smart_telescope/ports/mount.py` stays the app-facing FSM, no upstream change request
needed); client shim uses swap-after-construction (deletes the copied constructor, no
change request needed). Any gap found during audits goes to SYNC.md "Pending upstream
requests" + GitHub issue only after explicit user approval.

**Changes:**

- `docs/todo.md`: corrected the v0.3.1 release note; added high-priority task block
  ONS31-101..110 (Phase B FSM alignment & routed-op adoption, Phase C shim reduction,
  Phase D hardware verification & closeout); annotated superseded items (LOCAL-001 →
  ONS31-106; SAFETY-001/002 → ONS31-102; REQ-3 satisfied via decoded at_home flag;
  ONS-MIGRATE-001/003/004/005/006/007/008/010/011/012/013/014 → ONS31-1xx equivalents);
  updated header.
- `wiki/index.md`: OnStepAdapter external-module entry rewritten (independent package,
  FSM/at_home/routed-op findings, migration unblocked).

No code changed; SYNC.md updates are themselves tasks (ONS31-104/110) executed during
the migration.

---

## 2026-07-15 — Working-tree cleanup: unsanctioned adapter WIP stashed, stale sync-status tests fixed

While committing the ONS31-101..110 task block, the working tree was found to
contain uncommitted changes from an earlier, unfinished session. Handled under
delegated authority ("smart_telescope is fully under your control"):

1. **Stashed (not deleted): partial SAFETY-001/LOCAL-001 implementation in the
   guardrail-protected adapter layer.** `smart_telescope/adapters/onstep/mount.py`
   had an uncommitted `_auto_stop_untracked_tracking()` branch in `get_state()`
   (+31 lines), and `tests/unit/adapters/onstep/{fake_serial.py,
   test_with_fake_serial.py}` had tests for BOTH that change AND a LOCAL-001
   `move()` rewrite that was never implemented (5 tests failing, incl.
   `test_mechanical_manual_move_removed`). The wiki log entry of 2026-07-11
   explicitly records these items as "none were implemented — awaiting explicit
   go-ahead", so this code was never sanctioned; it also implements exactly the
   local protocol-layer compensation that today's decision replaced with the
   upstream routed op (`unpark_to_home_stop_tracking()`, ONS31-102) and the
   `move_ra_timed()` translation (ONS31-106). Preserved recoverably:
   `git stash list` → "WIP SAFETY-001/LOCAL-001 in protected adapter layer …".
   Drop it once ONS31-102/106 land.

2. **Fixed 4 stale tests in `tests/unit/adapters/onstep/test_get_sync_status.py`
   (pre-existing failures at the committed state, unrelated to the stash).**
   Commit `9aeb3bb` ("LX200 precision delta") correctly changed
   `get_sync_status()` to compare the reported site against the
   arcminute-rounded config (`_lx200_round_degrees`; LX200 ±DD*MM stores only
   ~1852 m resolution — raw-config comparison showed a false ~300 m offset on a
   perfectly synced mount), but did not update the M8-008 tests (`daca95b`),
   which mocked OnStep reporting full-precision coordinates — impossible on
   real hardware. Tests now build the mocked site relative to
   `_REF_LAT/_REF_LON = _lx200_round_degrees(base)`. Test-only change;
   `get_sync_status()` untouched per the adapter guardrail. Result: full
   `tests/unit/adapters/onstep` suite green (156 passed, 24 skipped).

3. **Committed the legitimate leftover `SYNC.md` note** (issue #3 filed
   2026-07-11 — matches the already-committed ONS31-009 todo entry).

4. **`claude-skills/` added to `.gitignore`** — an unrelated cloned
   skills-marketplace repo sitting untracked at the project root; contents left
   in place, just excluded from git status.

**Addendum:** `claude-skills/` turned out to be committed as a bare gitlink
(mode 160000, no `.gitmodules`) — accidentally added in commit `e97034c`,
likely via `git add -A` with the nested clone present. A gitlink without
`.gitmodules` breaks clones and leaves an empty dir on the Pi after
`git reset --hard`. Removed from the index with `git rm --cached claude-skills`
(directory kept on disk); the `.gitignore` entry now applies.

---

## 2026-07-17 — ONS31 migration finished: local OnStep USB connectivity replaced by onstep_adapter v0.3.1 (committed)

Completed and committed the full USB-connectivity replacement that was implemented in
the working tree on 2026-07-15 (ONS31-001..008, ONS31-101..108, ONS31-110):

- `pyproject.toml` pinned to the v0.3.1 wheel; installed version verified 0.3.1,
  `from onstep_adapter import OnStepClient, OnStepSafetyConfig` clean (no
  `smart_telescope` namespace collision).
- `smart_telescope/adapters/onstep/` is now a thin shim layer: `mount.py` 465 lines
  (delegation + permanent wrappers + REQ-ST-004/007 method-copy SYNC-OVERRIDEs that the
  wheel turned out NOT to contain), `client.py` swap-after-construction, `focuser.py`
  M7-004 backlash + loader override (below), rest pure re-exports.
- Full unit suite green: **3898 passed, 24 skipped**, coverage 88.73%.

**New finding (2026-07-17): broken relative imports inside the v0.3.1 wheel.**
`onstep_adapter/focuser.py:170` and `onstep_adapter/mount.py:621` both contain
`from ... import config` — a leftover from when these files lived under
`smart_telescope/adapters/onstep/`. Inside the top-level `onstep_adapter` package the
import always raises and is swallowed:

1. `OnStepFocuser._load_calibrated_max_position()` always returns 0 → the calibrated
   focuser max position in `~/.SmartTScope/onstep_focuser_calibration.json` would be
   silently ignored. Surfaced by
   `tests/unit/adapters/test_onstep_focuser.py::test_load_calibrated_max_reads_json`.
   Handled with a shim SYNC-OVERRIDE in `smart_telescope/adapters/onstep/focuser.py`
   carrying the pre-migration loader (pure file/config glue, no serial logic — adapter
   itself untouched per the guardrail). Documented in SYNC.md.
2. `_default_safety_config()` in upstream `mount.py` can never reach
   `build_onstep_safety_config()` and falls back to a permissive default — **latent
   only** for SmartTScope, since `runtime.py` always passes an explicit safety config.
   No override; recorded in SYNC.md as an upstream ask candidate.

Both are upstream ask candidates — **not filed**; needs user approval per the
ONS31-008/009 pattern (together with: client mount-injection parameter, subclass-safe
internal state checks, safety-config tolerance fields).

Bookkeeping: `docs/todo.md` ONS31 items checked off with done-notes; `wiki/index.md`
OnStepAdapter entry rewritten to the completed state; SYNC.md extended with the
broken-import SYNC-OVERRIDE row. The 2026-07-15 stash ("WIP SAFETY-001/LOCAL-001 in
protected adapter layer") was dropped after the commit landed, as its own log entry
prescribed — dropped stash commit SHA `8cf8aa7b5fee6e2145ae17fd57b304530cba16b4`
(recoverable via `git checkout 8cf8aa7 -- <path>` while unreferenced objects persist).

**Remaining open:** ONS31-109 Pi hardware smoke test (connect →
`unpark_to_home_stop_tracking()` with `at_home=True` and no tracking → GoTo → STOP →
park → disconnect; P0, hardware evidence required) and ONS31-104 (issue #3 comment,
awaiting user approval).

---

## 2026-07-17 — Pi startup crash after v0.3.1 deploy: stale repo-root dirs + --no-deps pin skip; deploy hardened

First Pi start after the ONS31 migration failed with a circular
`ImportError` in `onstep_adapter/__init__.py`. Root causes (none in the new code):

1. A stale untracked `onstep_adapter/` directory (old v0.3.0 re-export shim) at the
   Pi repo root. `astro_start.sh` launches with CWD = repo root, so it shadowed the
   venv's site-packages → the shim's `from smart_telescope.adapters.onstep import ...`
   re-entered the partially initialized package. `git reset --hard` never removes
   untracked dirs, which is how it survived deploys.
2. `astro_start.sh` installs the rebuilt SmartTScope wheel with `--no-deps`, so the
   pyproject pin bump to onstep_adapter v0.3.1 was silently never installed on the Pi.
3. Bonus defect in the build: `[tool.setuptools.packages.find] include =
   ["smart_telescope*"]` also matches the stray `smart_telescope_old/` sitting on the
   Pi, baking it into the deployed wheel.

Hardening committed:

- `pyproject.toml`: package include tightened to `["smart_telescope",
  "smart_telescope.*"]` (verified with a decoy `smart_telescope_old/`: no strays).
- `scripts/astro_start.sh`: (a) stale-directory guard — refuses to start while
  `onstep_adapter/` or `smart_telescope_old/` exist at the repo root, with the `mv`
  command to run; (b) onstep_adapter version sync — after the `--no-deps` wheel
  install, compares `onstep_adapter.__version__` (imported from `/` to dodge CWD
  shadowing) against the version pinned in pyproject.toml and force-reinstalls the
  pinned wheel URL on mismatch.

One-time manual cleanup on the Pi (guard reports it): move `onstep_adapter/` and
`smart_telescope_old/` out of `~/astro_sw/SmartTScope/`, then rerun
`astro_pull_start.sh` — the version sync then pulls v0.3.1 automatically.

---

## 2026-07-17 — First Pi hardware session after ONS31 migration: deploy confirmed working; M9-028 filed

After the stale-directory cleanup and hardened start script, the server started
cleanly on the Pi with onstep_adapter v0.3.1. The user ran the guided flow through
time/location confirmation (WAIT_CONTEXT_CONFIRMATION) and then safe-parked from the
"Home the mount" step (WAIT_HOME_CONFIRMATION) — flow correctly reached PARKED_SAFE
with green READY. (Partial real-hardware evidence toward ONS31-109; the full smoke
test — unpark/home/GoTo/STOP/park — is still open.)

Gap found: PARKED_SAFE is terminal — safe-parking during setup leaves no way back
into the guided flow short of restarting. Filed as **M9-028** in `docs/todo.md`:
"Unpark & continue setup" secondary action on PARKED_SAFE returning to
WAIT_HOME_CONFIRMATION, plus a look at `_readiness()` reporting READY for a
never-homed mount. Backlog only — not implemented in this session.

---

## 2026-07-17 — M9-029 filed: mount-state badge in WAIT_CONTEXT_CONFIRMATION; connect-before-time-sync decision recorded

User request from the same Pi session as M9-028: show the observed mount state
(PARKED / AT_HOME / SLEWING / TRACKING / ...) next to the "LIMITED READY" readiness
badge on the WAIT_CONTEXT_CONFIRMATION page. Filed as **M9-029** in `docs/todo.md`
(P3 UI; backlog only, not implemented).

Decision recorded with it: **connecting to OnStep before time/location confirmation
is OK** (user, 2026-07-17) — mount-state display at that phase needs no gating on
context confirmation. The mount is in fact already connected at startup
(`RuntimeContext.connect_devices()`), and the global `#mount-strip` polls
`/api/mount/status` from page load; M9-029 only surfaces the same observed state
inside the phase panel via a `mount_state` field on `/api/observing/state`.

---

## 2026-07-17 — M9-029 implemented: mount-state badge in the Observe phase panel

`ObservingService.snapshot()` now includes a `mount_state` field — the name of the
`DeviceStateService` cached observed state (same source as `/api/mount/status`,
including the sticky-AT_HOME handling), `null` until the first poll lands or when
`snapshot()` is called without deps. Deliberately not gated on context confirmation
(user decision 2026-07-17: connecting to OnStep before time sync is OK).

Frontend: new grey pill `MOUNT: <STATE>` (`#obs-mount-state-badge`,
`.phase-readiness.MOUNT_STATE`) rendered directly next to the readiness badge by
`_renderObservingState()`; hidden while `mount_state` is null. Shown in all phases,
not only WAIT_CONTEXT_CONFIRMATION — the explicit ask was that page, and showing it
everywhere needs no special-casing.

Tests: 3 new snapshot tests (`TestSnapshotShape`) covering observed-state reporting,
null-before-first-poll, and null-without-deps; top-level-key assertions updated in
both the service and API test files. `test_observing_service.py` +
`tests/unit/api/` green (1034+ tests, incl. full api dir run).

---

## 2026-07-17 — M9-030 filed: mount-state pill same style as readiness badge, plain state name

User feedback on M9-029: the mount state should sit side by side with "LIMITED READY"
in the **same style** (equal prominence, not the muted grey), and read as the plain
state name — "PARKED", not "MOUNT: PARKED", and never conveyed by the
"Stop safely (park)" action button ("It's a state, not a button with action").
Filed as **M9-030** in `docs/todo.md` (P3 UI, backlog only).

---

## 2026-07-17 — M9-030 implemented: mount-state pill restyled as a peer of the readiness badge

Frontend-only change (no backend/tests touched). The Observe screen mount-state pill
now shows the plain state name ("PARKED", "AT HOME", ...) — "MOUNT:" prefix dropped —
side by side with the readiness badge at the same visual prominence. Per-state colors
mirror the global mount strip's `_STRIP_DOT` semantics (new `_OBS_MOUNT_PILL` map in
`observing.js`): TRACKING/SLEWING green, UNPARKED/AT_HOME yellow, AT_LIMIT red, and
PARKED/UNKNOWN accent-blue instead of the muted grey the user rejected. CSS: new
`.phase-readiness.MS-{green,yellow,red,blue}` classes in `index.html`;
`.MOUNT_STATE` keeps only the spacing. `node --check` clean.

---

## 2026-07-17 — M9-028 implemented: "Continue setup" from PARKED_SAFE back to the homing step

PARKED_SAFE is no longer strictly terminal. New `Intent.UNPARK_CONTINUE`
(`domain/observing_state.py _on_parked_safe`): PARKED_SAFE offers a secondary action
"Continue setup (back to homing)" that returns the flow to WAIT_HOME_CONFIRMATION.

**Design choice (deviates from the task's original acceptance wording):** the action is
a pure flow transition — it does NOT unpark the mount itself. `home_sequence()` already
auto-unparks a PARKED mount (with the M9-025 immediate tracking-disable and, post-ONS31,
the routed `unpark()`), so the physical unpark+home happens through that single hardened
path when the user presses "Home the mount". This avoids a second hardware code path and
never leaves the mount unparked-idle without a running action. The M9-030 state pill
showing PARKED next to "Home the mount" matches a fresh session start, so the UI stays
coherent.

Guard hygiene on the transition (`handle_intent` side effect): `g2_home_confirmed`
reset to False (previous home confirmation is void) and `g8_safe_stop_possible` reset
to False — a leftover True would let the next SAFE_STOPPING auto-advance to PARKED_SAFE
before the park actually completes, defeating the M9-027 single-`:hP#` protection.

Readiness fix folded in (flagged in the task): PARKED_SAFE now reports READY only when
g2 is True (park after a confirmed home / completed session, primary label "Session
complete — parked safe"); safe-parked straight out of setup shows LIMITED READY with
"Parked safe — setup not finished".

No frontend change needed — secondary actions render generically from the API payload.
Tests: 2 new/updated FSM tests (`TestParkedSafe`), 5 new service tests
(`TestUnparkContinue`: action offered, transition + guard resets, pure-transition
`unpark.assert_not_called()`, readiness both ways). 72 observing tests green.
Hardware walk-through pending the next Pi session (park from setup → continue →
Home the mount → mount unparks and homes).

---

## 2026-07-17 — M9-031 filed + implemented: state-aware label for the STOP_SAFELY action

User feedback on 3ec0d79: after park-at-home-step -> Continue setup, the page showed
the PARKED state pill with a button offering to park below it. The action must stay
(only graceful exit from setup to PARKED_SAFE, M9-017; completes without hardware
motion when already parked) but the label now adapts: observed mount state PARKED ->
"End session (mount already parked)", otherwise "Stop safely (park)" as before.

Implementation: new `_stop_safely_label(mount_state)` in
`services/observing_service.py`; `_secondary_actions()` takes the observed mount
state already computed by `snapshot()` for M9-029 and applies the label at all three
STOP_SAFELY emit sites (stoppable phases, stop-only wait phases, PAUSED_SAFE).
Intent values and FSM unchanged; no frontend change (labels render from the payload).
Tests: 3 new (`TestStopSafelyLabel` — parked, not parked, no observation yet);
75 observing tests green.

---

## 2026-07-17 — M9-032 filed: premature AT HOME during second home cycle (stale sticky), diagnosis

Hardware session (75db812 deployed): home #1 + confirm worked, safe-park worked,
Continue setup worked (real-hardware evidence for M9-028/030/031 and partial
ONS31-109). New bug: on the second "Home the mount", the state pill shows AT HOME
immediately while the mount is still slewing; STOP mid-slew leaves AT HOME displayed
and the flow asking for an impossible home confirmation.

Diagnosis (code-level, see M9-032 in docs/todo.md for full detail): stale
`DeviceStateService._sticky_at_home` from home #1. Only `record_command()`
("goto"/"park"/"track") clears the sticky, and only the `/api/mount/*` endpoints call
it — the guided flow (`_run_home`/`_run_safe_stop`) records nothing, so the park never
cleared the sticky and poll rule 4 (UNPARKED + sticky -> AT_HOME) mislabels the whole
second cycle. "home"/"unpark"/"stop" also missing from the clearing logic. Fix is
service-layer only. Separately noted as an upstream ask candidate (approval pending):
upstream `stop()` keeps `_at_mechanical_home` authority through a mid-slew STOP.

Backlog only — awaiting go-ahead to implement.

---

## 2026-07-17 — M9-032 implemented: stale sticky AT_HOME cleared by command lifecycle; guided flow records commands

Service-layer fix, adapter untouched:

1. `DeviceStateService.record_command()`: a `"home"` command now clears
   `_sticky_at_home` (the mount is not at home until this command's own slew
   confirms it — the promotion flags `_home_cmd_issued`/`_home_slew_seen` were
   already reset, only the sticky leaked); `"unpark"` and `"stop"` added to the
   goto/park/track clearing branch.
2. The guided Observe flow registers its commands (it bypasses the `/api/mount/*`
   endpoints, which were the only `record_command()` callers — the root of the
   stale sticky): `_run_home` records "home" before `home_sequence()`;
   `_run_safe_stop` records "park" before `park_sequence()`, only when actually
   issuing (inside the M9-027 no-resend window nothing is recorded). Bonus: the
   last-command telemetry in `/api/mount/status` is now correct for guided
   operations too.

Upstream ask candidate recorded in SYNC.md (NOT filed, needs approval): upstream
`stop()` keeps `_at_mechanical_home` authority through a mid-slew STOP;
`note_external_motion()` is the public API that should be called.

Tests: 4 new sticky-lifecycle tests in `test_device_state.py` (new-home clears
sticky, full second-cycle promotion regression, unpark/stop clearing) + 2 new
guided-flow recording tests in `test_observing_service.py`. 241 tests green
(device-state, observing service/API, mount API). Hardware re-test of the exact
report sequence (home -> park -> continue -> home, STOP mid-slew) pending the
next Pi session.

---

## 2026-07-17 — M9-033 filed + implemented: plain-language phase titles on the Observe screen

User report (after 92ff256 restart, mount correctly showing PARKED): the headline read
"WAIT CONTEXT CONFIRMATION" — a raw FSM name in exactly the place that should tell the
user what to do. `_obsPhaseLabel()` only swapped underscores for spaces. New
`_PHASE_TITLES` map in `static/js/observing.js` gives all 12 phases user-facing titles
(WAIT_CONTEXT_CONFIRMATION -> "Confirm time & location", WAIT_HOME_CONFIRMATION ->
"Home the mount", SAFE_STOPPING -> "Stopping safely...", PARKED_SAFE -> "Parked safe",
etc.), falling back to the old formatting for unknown values. JS-only change.

---

## 2026-07-17 — M9-034 filed + implemented: SAFE_STOPPING recovery after manual STOP; stale detail; goto lifecycle match

Hardware report (STOP pressed mid-park-slew): Detail panel still showed the previous
home action record (home: AT_HOME) reading as wrong live status; the flow offered no
way to continue parking or return to homing (M9-027 no-resend window silently blocks
a park retry for 120 s and SAFE_STOPPING had no secondary actions).

Three fixes (service/domain layer, adapter untouched):

1. **Stale detail:** `_spawn()` clears `_detail` at action start — detail describes
   the CURRENT action; `_run_safe_stop` now writes its own `safe_stop` record
   (`parked`, `mount_state`).
2. **SAFE_STOPPING recovery actions:** "Retry park now" (STOP_SAFELY while in
   SAFE_STOPPING clears `_park_command_issued_at` — an explicit user retry is
   exactly the case where re-issuing :hP# is right, the manual STOP killed the
   first one; automatic retries stay throttled per M9-027) and "Back to homing"
   (UNPARK_CONTINUE: FSM now allows SAFE_STOPPING -> WAIT_HOME_CONFIRMATION,
   intent checked before g8 so the explicit choice wins; side effect resets
   g2/g8 and abandons the park window — accepted from PARKED_SAFE and
   SAFE_STOPPING alike).
3. **Sticky lifecycle bug (bonus find):** the goto endpoint records
   "goto ra=...h dec=...deg", which never matched the literal "goto" in
   `record_command()`s clearing branch — API gotos silently kept the sticky
   AT_HOME. Matching is now on the first word.

Tests: TestSafeStoppingRecovery (actions offered, retry bypasses window with
park.call_count==2, back-to-homing transition, detail replacement), FSM
SAFE_STOPPING+UNPARK_CONTINUE, sticky-cleared-by-goto-with-args. 283 tests green
across domain/device-state/observing/mount suites. Hardware re-test of the STOP
mid-park scenario pending the next Pi session.

---

## 2026-07-17 — M9-034 reopened: Pi retest still shows AT HOME after STOP mid-park; transition diagnostic added

Retest on the Pi after 42a678f: STOP during the park slew still flips the state
directly to AT HOME, Detail panel empty, app blocked. The M9-032/034 cache-sticky
fixes are covered by tests and provably clear on this path, so the AT_HOME must
originate from `mount.get_state()` itself — candidates: OnStep genuinely reporting
the H flag after `:Q#` near home, or the shim/upstream `_at_mechanical_home`
authority flag being re-armed by a genuine H observation before the park began
(upstream `stop()` never clears it — the ask already recorded in SYNC.md).

Not guessing further: added a conclusive diagnostic instead.
`DeviceStateService._poll_once()` now logs every observed state transition at INFO
with the raw adapter-reported state (pre-promotion), decoded `:GU#` flags,
shim `_at_mechanical_home`, and the cache sticky/promotion flags. Next repro on the
Pi pins the faulty layer definitively. 100 device-state/observing tests green.

---

## 2026-07-17 — M9-034 evidence round 1: no transitions after home confirm; busy-gate escape fixed

First diagnostic capture from the Pi (repro: home -> confirm -> stop safely -> STOP):
the transition log ends at `SLEWING -> AT_HOME` (home slew completing, OnStep genuinely
reporting H — decoded at_home=True, raw GU# `nNpHEo260`). **No transition was ever
logged for the park slew or the manual STOP**, and `/api/observing/state` showed
`busy: true` with empty detail. `park_sequence()` logs pre-park state and "Mount park
issued" unconditionally — so either the safe-stop worker wedged BEFORE issuing :hP#
(only unbounded call on that path: `guiding_service.stop()`; the coordinator raises on
conflict, all serial calls have timeouts) or it never ran. The AT HOME pill was
therefore likely *true* this run (mount still at home, park never issued) — the
"blocked app" is the real defect.

Fixed now (service layer): UNPARK_CONTINUE added to the busy-gate bypass — it is the
escape hatch out of SAFE_STOPPING and was silently dropped while a worker was in
flight (which is most of the time, since _maybe_auto_advance spawns on every UI poll).
_run_safe_stop re-checks the phase before writing g8/detail so a late worker cannot
clobber the escape. 2 new tests; 84 observing tests green.

Still needed from the Pi: full log slice around the repro
(`grep -E "park|guiding|unpark|WARNING|ERROR" server.log | tail -50`) and whether
busy stays true persistently (re-curl after a minute) — that names the wedge line.

---

## 2026-07-17 — M9-034 resolved by evidence; M9-035: emergency stop halts SAFE_STOPPING auto re-park

Second Pi diagnostic capture settled M9-034 conclusively. Timeline from the
transition log: home slew -> genuine H flag (decoded at_home=True) -> `command
issued park` -> `Mount park issued` (:hP# accepted) -> `Emergency stop` seconds
later -> `state still AT_HOME after 5 s`. **The AT HOME pill was truthful** — the
mount never meaningfully left home; no false sticky promotion occurred anywhere.
The perceived "blocked app" was: (a) the busy gate silently dropping the escape
intent while _maybe_auto_advance kept a safe-stop worker in flight on nearly every
poll (fixed in 5b35b65), and (b) guiding stop + serial polling running on every
2.5 s retry pass (permanent "Working…" + repeated "GuidingService stopped" log
lines).

New P0 found in the same log: the emergency stop never informed the observing
flow — SAFE_STOPPING would have **auto re-issued :hP# ~120 s after the user
emergency-stopped the mount**. Fixed as M9-035:

- `/api/emergency_stop` now calls `ObservingService.on_emergency_stop()`:
  SAFE_STOPPING -> PAUSED_SAFE, park window cleared. "Resume" re-enters
  SAFE_STOPPING and re-issues the park immediately — as an explicit user
  decision, never automatically. No-op in other phases.
- Endpoint also records the "stop" command with DeviceStateService (R2-003 gap;
  clears sticky/home-promotion flags).
- `_run_safe_stop` stops guiding only when actually issuing the park.

Tests: TestEmergencyStopHaltsParkRetries (pause + window clear, resume re-park,
no-op outside SAFE_STOPPING, guiding stopped exactly once across retries).
63 observing/emergency tests green. Pi retest expected behavior: ■ Stop mid-park
-> phase "Paused" with Resume / Stop safely; no autonomous re-park; "Back to
homing" works even while busy.

---

## 2026-07-17 — M9-036: park slew showed AT HOME — shim get_state ordering fixed; stop() drops home authority

Hardware retest confirmed M9-035 works (Resume button after emergency stop) and
narrowed the last false display to the shim mapping layer: home slew shows SLEWING
correctly, but the park slew showed AT HOME for the entire travel.

Root cause (shim `get_state()`, ONS31-101 mapping): upstream `park()` clears the
`_at_mechanical_home` authority flag, but the first poll of the park slew still sees
OnStep''s genuine H flag (mount still inside the home zone) and re-arms it; the sticky
check sat ABOVE the motion check, so AT_HOME masked SLEWING from then on. This also
explains the earlier "Mount park: state still AT_HOME after 5 s" warning.

Fix (SmartTScope-owned shim only; upstream untouched):
1. `get_state()` ordering: decoded H > SLEWING > sticky authority > upstream state.
   The decoded-H-beats-SLEWING rule (M9-021: H appears while goto-active is still
   set at the end of a home slew) is preserved; only the STICKY flag can no longer
   override observed motion.
2. New shim `stop()` wrapper: `super().stop()` then upstream public
   `note_external_motion("manual_stop")` — a manual/emergency :Q# invalidates
   mechanical-home authority (upstream `stop()` does not clear the flag; that
   upstream ask remains recorded in SYNC.md). A mount genuinely at home re-arms
   from the next H observation.

Tests: `TestGetStateAuthorityFlagVsMotion` (5 tests) driving the shim with the real
GU# strings captured from the Pi transition log (`nNpHEo260`, `nphET260`,
`nNpeET260`): slewing beats stale flag, genuine H still beats slewing, stop clears
authority (idle then honest UNPARKED), re-arm when genuinely at home. 255
adapter+service tests green. SYNC.md permanent-wrapper table updated (get_state
ordering note + M9-036 stop() row).

Expected on next Pi run: park slew shows SLEWING; ■ Stop mid-way shows UNPARKED
with phase "Paused" (Resume / Stop safely); stopping while genuinely at home still
shows AT HOME.

---

## 2026-07-17 — M10 task block specified: parallel camera readiness via SmartTScopeLiveAnalysis

New milestone block M10-001..012 added to `docs/todo.md` from a planning session with
the user ("grill me"): after home confirmation the flow offered polar alignment, but
the system may be out of focus or on an empty star field. Solution: a camera-readiness
track running **in parallel** to the mount flow, starting while the user confirms
time/location — enumerate all connected ToupTek cameras, auto-tune exposure/gain via
the external SmartTScopeLiveAnalysis module (v0.1.0; module recommends, app applies,
app-side 70% histogram ceiling until it ships upstream), verify stars are detectable,
and coarse-focus focuser-equipped trains until plate-solvable.

Key decisions recorded (AskUserQuestion, 2026-07-17): parallel per-camera FSM instead
of a new mount-FSM phase (only automatic polar align gates on a READY camera); focus
algorithm is a separate, independently testable, **SCT-aware** component (donut
recognition) reused later for in-capture focus checks on each last long-exposure
frame; V-curve AutofocusService stays as the precision step; integration as pinned
pip dep with the OnStepAdapter guardrail.

Bookkeeping: SYNC.md gained a planned-dependency section with draft upstream asks
LA-REQ-1 (70% ceiling) / LA-REQ-2 (SCT donut + focus metric) — NOT filed, approval
required; `wiki/index.md` gained the external-module entry. Backlog only — no code.

---

## 2026-07-17 — M10-013 filed: per-train optical configuration (focuser/filterwheel/reducer/barlow)

User requirement folded into the M10 block: the app must know each identified
camera''s complete optical configuration — focuser, filter wheel, reducer, barlow —
config-file based for now. Gap analysis against the existing model
(`OpticalTrainSpec`/`OpticalTrainRegistry`/`[optical_trains.*]`): per-train focuser
and numeric `reducer_factor` already exist, but the `[filter_wheel]` section is
global with no per-camera linkage, and reducer vs. barlow are an anonymous factor,
not declared elements. M10-013 adds `filter_wheel`/`reducer`/`barlow` fields to the
train schema (labels; `reducer_factor` stays the numeric authority — backward
compatible), registry validation, template update, and wires the configuration into
the M10-002 identification payload and M10-008 camera card. Backlog only — no code.

---

## 2026-07-17 — M10-001 + M10-013 implemented: LiveAnalysis pinned; per-train optical configuration

**M10-001:** `smarttscope-live-analysis @ git+...SmartTScopeLiveAnalysis.git@v0.1.0`
added to pyproject.toml (distribution/import names verified against the upstream
pyproject: import `smarttscope_live_analysis`, `__version__ 0.1.0`,
`analyze_camera_frame` exposed; installed and verified on Windows).
`scripts/astro_start.sh` gained a second version-sync block (same rationale as the
onstep_adapter one: the Pi wheel install runs `--no-deps`, so pin bumps would be
silently skipped). SYNC.md section updated from "planned" to installed state with an
upgrade procedure; LA-REQ-1/2 upstream asks remain drafts pending approval.

**M10-013:** `OpticalTrainSpec`/`OpticalTrain` extended with `filter_wheel`
("touptek" | "", linking a train to the global `[filter_wheel]` device),
`reducer` and `barlow` (descriptive labels). `reducer_factor` stays the numeric
authority for focal/pixel-scale math — legacy configs load unchanged (all new fields
default to ""). Registry validation: unknown filter_wheel value or "touptek" without
`[filter_wheel] enabled = true` fails startup with a clear ValueError; a declared
element with factor 1.0 (or factor != 1.0 with nothing declared) logs a startup
warning, never crashes. New `OpticalTrain.optical_configuration()` provides the
serializable per-camera summary the M10-002 identification payload and M10-008
camera card will consume. `templates/config.toml` extended with the three fields on
all example trains.

Tests: 7 new in `test_optical_train_registry.py` (elements flow through, payload
shape, both validation failures, both mismatch warnings, legacy compatibility);
full services suite green (1173 passed). Bash syntax check clean on astro_start.sh.

---

## 2026-07-17 — M10-014 filed: filter-wheel slot naming with INDI names

While reviewing the user''s Pi config after M10-013: the `[filters]` section is
currently ignored (no parser in config.py; the ToupTek wheel adapter is numeric-slot
only; no INDI backend exists in the codebase). Filed **M10-014**: parse a slot->name
mapping using INDI-convention filter names (Red, Green, Blue, H_Alpha, SII, OIII,
LPR, Luminance) for interoperability, validate against the wheel''s slot count,
surface names in the filter-wheel API/UI; camera_adapter stays numeric-slot
(no external changes). Noted: user config has 7 lowercase entries vs the 8-name INDI
list (LPR extra) — reconcile at implementation. Backlog only.

Also flagged to the user in chat: their new `[optical_trains.oag] camera = "oag"`
will fail registry validation at startup unless an "oag" role is added to
`[cameras]` — comment the train out until the OAG camera exists.

---

## 2026-07-17 — M10-015 filed: pixel scale derived at runtime (driver pixel size × train × binning)

User requirement from the three-camera config review (main=ATR585M, guide=GPCMOS,
oag=G3M678M): `pixel_scale_arcsec` must not need manual configuration — the optical
train provides focal_mm × reducer_factor, the camera''s pixel size is readable (driver
preferred, model profile fallback), and binning scales the result, so a static config
number is wrong under binning anyway. Review also uncovered the actual defect:
`_derive_pixel_scale()` matches profile models against the ROLE name ("main"/"guide"/
"oag") — never matches — so every train silently uses the global 0.38 fallback, stale
for the ATR585M main camera. M10-015 specifies the runtime helper
(`effective_pixel_scale(train, binning)`), demotes the config value to an optional
override, migrates consumers (plate-solve hints, collimation, guiding), and fixes the
registry''s default-0 `camera_index` via `CameraNameResolver`. Backlog only.

Interim note given to the user: until M10-015 lands, explicit per-train
`pixel_scale_arcsec` overrides (0.29 / 3.32 / 0.20) remain advisable, since the
fallback (0.38) matches none of the current cameras.

---

## 2026-07-17 — M10-015 implemented: pixel scale derived at runtime (model/driver × train × binning)

`pixel_scale_arcsec` no longer needs configuring. Changes:

1. **Root-cause fix:** `_derive_pixel_scale()` now resolves the camera profile via
   the role''s configured `[cameras.<role>] model` — the old code matched profile
   names against the role name ("main"/"guide"/"oag"), never matched, and silently
   used the 0.38 global for every train. Legacy configs where the role IS the model
   name keep working.
2. **Binning-aware helper:** `OpticalTrain.effective_pixel_scale(binning,
   pixel_size_um)` — precedence: explicit config override > driver-reported pixel
   size (already exposed by the camera adapter''s public
   `get_capabilities().pixel_size_um` — no external-module change needed) >
   model-profile derivation. Binning multiplies the base. New
   `pixel_scale_overridden` flag records whether config set an explicit value.
3. **Real SDK indices:** `from_config(resolve_index=...)` + the runtime wires a
   CameraNameResolver-backed resolver (best-effort; SDK-less dev machines and
   unplugged cameras fall back to configured/default index) — removes the
   default-0-for-all `camera_index` ambiguity.
4. **Single API-side source:** new `deps.get_pixel_scale(camera_index, camera_role,
   binning)`; migrated the raw `config.PIXEL_SCALE_ARCSEC` fallbacks in
   `api/polar.py` (2 sites), `api/mount.py` goto-center, and `api/solver.py` solve.
   Remaining raw readers: the final fallback inside `get_pixel_scale()` itself and
   the pre-M9-018 hardcoded `OpticalProfile`s in `workflow/_types.py` (tracked by
   M9-018).

Tests: 6 new in `test_optical_train_registry.py` — acceptance numbers exact
(0.2944 / 3.3232 / 0.2030 at binning 1, doubled at binning 2 for the user''s
ATR585M/GPCMOS/G3M678M rig), driver-preferred, override-wins, legacy role
matching, resolver win + exception fallback. Registry/mount/solver/polar suites
green (282 tests). templates/config.toml comment updated (override-only).

User impact: the explicit per-train pixel_scale_arcsec overrides recommended
earlier today are now optional — derived values are correct for all three cameras.

---

## 2026-07-17 — M10-002 implemented (+ first M10-008 slice): parallel camera identification with Observe-screen card

New `services/camera_readiness.py` (`CameraReadinessService`): background thread
started by `RuntimeContext.connect_devices()` — running while the user confirms
time/location — enumerates connected ToupTek devices every 15 s and matches them
against the configured `[cameras.*]` roles. Matching is model-only via
`CameraNameResolver` (deliberately NO per-scan serial verification: reading a serial
requires opening the device, which must not happen against cameras in active use;
serial-verified resolution stays in the adapter build path). Per-role result:
DETECTED (with SDK index + display name) / MISSING (with reason) / DISABLED, plus an
unassigned-devices list and an sdk_available flag; each role is joined with its
optical train''s `optical_configuration()` (M10-013). SDK-less environments and
registry failures degrade gracefully; the service never blocks or raises into the
mount flow. Stopped in shutdown()/reset_for_tests().

API: `cameras` field added to `/api/observing/state` and intent responses at the
API layer (`_camera_readiness_payload()` — ObservingService itself stays
camera-agnostic; None when no runtime). New `deps.get_camera_readiness()`.

UI (M10-008 first slice): "Cameras" card on the Observe screen, visible from
WAIT_CONTEXT_CONFIRMATION onward — per role a status dot (green DETECTED /
red MISSING / grey DISABLED), display name or reason tooltip, and the optical
configuration summary (telescope · focal length · focuser · filter wheel ·
reducer · barlow · arcsec/px); plus a "connected but not configured" warning line.
Exposure/star/focus columns and the READY badge arrive with the M10-003 FSM.

Tests: 10 new (`test_camera_readiness.py` — all-detected, unplugged→MISSING,
disabled, SDK-unavailable, unassigned, optical join, provider-failure tolerance,
lifecycle); observing API shape updated (cameras key); runtime suite green
(56 tests in the targeted run). `node --check` clean. Pi verification pending
(M10-012).

---

## 2026-07-17 — M10-002/012 hardware evidence + filter-wheel recognition in the camera scan

Pi verification of the camera-identification slice succeeded: all three cameras
DETECTED with correct optical configurations and the M10-015-derived pixel scales
confirmed on hardware (0.2944 / 3.3232 / 0.203 arcsec/px for ATR585M/GPCMOS/G3M678M).
The "no cameras visible" report was browser cache — a hard refresh showed the card.
(Partial M10-012 evidence: identification leg done; tuning/star/focus legs pending
their implementation.)

Follow-up fix from the same session: the ToupTek filter wheel enumerates alongside
cameras (displayname "FILTERWHEEL") and was reported "connected but not configured".
`CameraReadinessService` now splits wheel devices out (marker match: FILTERWHEEL /
FILTER WHEEL / CFW), reports them in a new `filter_wheel` snapshot field
({configured (from [filter_wheel] enabled), detected, display_name}), and excludes
them from the unassigned-camera warning; camera sdk_index values still refer to the
full enumeration order. The Observe card shows a "wheel" row (green when configured +
detected, yellow on mismatch either way). 3 new tests; 17 targeted tests green.

## 2026-07-18 - M10-003/M10-004: per-camera setup FSM + LiveAnalysis shim

Implemented the camera-readiness backbone. `services/live_analysis_shim.py`
(M10-004) is the only place that knows the pinned SmartTScopeLiveAnalysis v0.1.0
call signature: `build_camera_info()` maps live camera state (exposure_s, gain,
offset, bit_depth, binning, raw_mode, conversion gain) with per-frame facts
winning (EXPTIME, BITDEPTH header from the adapter's pixel-shift detection), and
`analyze()` passes `FitsFrame.pixels` untouched - the ToupTek adapters already
right-shift to native ADC range.

`services/camera_setup_fsm.py` (M10-003): `CameraSetupService` watches the
M10-002 identification snapshot and, per DETECTED camera, submits a JobManager
job (`camera-setup:<role>`, resource `camera:<sdk_index>`) driving
IDLE -> TUNING -> STAR_CHECK -> FOCUSING (has_focuser trains only) -> READY |
DEGRADED(reason). A camera held by autogain/session stays IDLE ("camera busy")
and retries on the next tick - no resource conflicts by construction. TUNING
records module recommendations (clamped application is M10-005); STAR_CHECK
requires `star_count_min` stars; FOCUSING has an injectable `focus_fn` hook and
completes with a "pending (M10-006)" note until the SCT-aware algorithm lands.
New `[live_analysis]` config section (enabled, setup_exposure_s, tuning_frames,
star_check_frames, star_count_min) + templates/config.toml. Runtime starts the
service in connect_devices() and stops it before job cancel_all in shutdown.
Per-role state is merged into `cameras.roles.*.setup` on /api/observing/state;
the camera card shows phase / stars / exposure / gain (READY green, DEGRADED
amber with reason). 16 new tests (incl. a real round-trip against the pinned
package); 33 targeted tests green. Pi verification pending (M10-012).

## 2026-07-18 - M10-016/M10-017: static cache-busting + readable camera errors

Pi evidence for the "UI doesn't find cameras" report: the API payload was complete
(all three roles DETECTED, wheel detected, setup FSM results present) - the browser
was rendering stale cached JS for the third session in a row. M10-016: HTTP
middleware now serves `/` and `/static/*` with `Cache-Control: no-cache`
(ETag revalidation keeps it a cheap 304 on the LAN) - no more mandatory hard
refresh after deploys.

The same payload showed the setup FSM working as designed: main/oag captured and
analyzed 8 frames each, DEGRADED "only 0 star(s) detected" with image_quality
too_dark (correct - not looking at sky), module already recommending 2 s exposure.
The guide camera failed to open with bare HRESULT "-2147024726" = 0x800700AA
ERROR_BUSY (no indiserver running; holder identification pending via
`fuser -v /dev/bus/usb/003/009` - suspected in-process aliasing between
get_preview_camera and the role-camera path). M10-017: `_describe_camera_error()`
decodes known ToupTek HRESULTs (busy / access denied / device not functioning /
timeout) into the setup reason, and ERROR_BUSY is now retryable - the role stays
IDLE ("camera busy: ...") and the watcher retries until the holder releases,
instead of terminal DEGRADED. 4 new tests; 24 targeted tests green.

## 2026-07-18 - M10-018: single camera handle per physical device

Evidence closed: `fuser -v /dev/bus/usb/003/009` showed the SmartTScope process
itself (PID 3334) holding the guide camera. A UI poll had hit the legacy preview
path ("no [cameras] config - trying SDK auto-detect"), opening the GPCMOS02000KPA
as a raw preview handle; the setup FSM role path then got 0x800700AA ERROR_BUSY on
its second open of the same device.

SDK threading check (user question, from resources/touptek/toupcam.py
v59.29030.20250722): the ToupTek SDK fully supports multiple cameras in a single
app thread - each opened handle runs its own internal SDK thread for USB data
(TOUPCAM_OPTION_THREAD_PRIORITY) and delivers frames via per-handle
StartPullModeWithCallback callbacks; handles are usable from any thread. The
hard constraint is one Open per physical device. Our thread-per-camera FSM model
stays because the adapter capture() is blocking - app choice, not SDK need.

Fix: runtime._role_for_sdk_index() maps SDK index -> configured role without
opening devices (readiness snapshot first, resolver fallback pre-scan);
get_preview_camera routes role-owned indices to the shared role handle;
new _camera_open_lock serializes the check-then-open sections of both camera
paths (the parallel FSM launches had made the dict mutations racy); resolver
per-tick INFO logs demoted to DEBUG. 5 new tests; 88 targeted tests green.
Pi verification pending: guide should leave "waiting..." and tune normally.

## 2026-07-18 - M10-014 + M10-019: filter-in-place display, Cameras compare screen

M10-014: config._parse_filters() parses [filters] as a 1-based slot -> INDI-name
table (Luminance, Red, Green, Blue, H_Alpha, SII, OIII, LPR); the legacy
name = slot format is inverted with canonical entries winning, so the user's
current 7 lowercase entries keep loading until migrated. CameraReadinessService
takes a wheel_provider and adds position/filter_name to the filter_wheel
snapshot (best-effort; unnamed slots show "slot N"; a [filters] entry above the
wheel's reported slot count logs a one-time warning). Observe wheel row now
shows e.g. "FILTERWHEEL - H_Alpha". templates/config.toml gained the missing
[filter_wheel] stub plus commented [filters] INDI examples.

M10-019: new top-level "Cameras" view (static/js/multicam.js + #cameras-view in
index.html; showTopView generalized to three views). One
/ws/preview?camera_role=...&autogain=true socket per DETECTED camera, all closed
on leaving the view. Panels ordered by FOV (pixel_scale_arcsec x sensor px;
JPEG dims doubled for colour previews since debayer halves resolution), labeled
"WxH px - W' x H'". Scale toggle: fit-each-panel vs one shared
arcsec-per-screen-pixel. Top-right jog pad: timed center-rate steps
(0.2/0.5/1/2 s) via POST /api/mount/nudge with new keep_tracking_state=true
(NudgeRequest field, default false = old behavior) so terrestrial jogs no
longer force sidereal tracking on; red center button = mountEmergencyStop();
arrows disabled while parked.

M10-020 filed as an open task: main/oag footprint overlay in the guide panel,
radio button plate-solve (sky) vs frame-search (terrestrial); LA-REQ-3 remains
a candidate upstream request, to be filed only with user approval.

Tests: 13 new (filters parser 6, readiness merge 4, nudge flag 3); readiness +
filters + nudge + observing + config suites green (57 targeted). node --check
clean on multicam.js/app.js/observing.js.

## 2026-07-18 - M10-021..024 filed: Confirm Time & Location blocked by camera bring-up

Hardware observation: the Confirm Time & Location step stalls while cameras
connect and take first frames - violating the M10 quality gate. Code trace
(no fix yet, tasks filed): (1) connect_devices() holds _adapters_lock across
_build_adapters(), which connects the main camera (SDK open + settle + priming
captures) BEFORE the mount, so POST /api/location/confirm (Depends get_mount)
queues behind the whole camera bring-up. (2) api/observing.py _build_deps opens
the guide camera via get_camera_by_role on every 2.5 s state poll and on the
confirm intent, contending on _camera_open_lock held by setup-FSM workers for
each multi-second open. (3) Readiness EnumV2, the lazy filter-wheel open
(M10-014), and legacy ToupcamCamera.connect are outside both locks - concurrent
SDK/USB traffic during the connect storm. Open question (M10-024): whether the
toupcam binding holds the GIL through Open/EnumV2 (would stall ALL endpoints,
not just device ones). Fixes must stay app-side (managed.py external-owned).
Tasks M10-021 (decouple mount from camera build, P1), M10-022 (no inline camera
opens on hot observing paths, P1), M10-023 (one SDK serialization discipline,
P2), M10-024 (Pi evidence: lock-wait vs GIL freeze, P2) in docs/todo.md.

## 2026-07-18 - M10-025 filed: separate slewing from tracking

User request: slewing to a target and sidereal tracking must be independently
controllable - GoTo paths currently assume tracking on, and OnStep may
auto-start tracking when a slew completes, which is wrong for terrestrial
targets. Task M10-025 filed in docs/todo.md: extend goto/slew with a
keep-tracking-state option (same semantics as the M10-019 nudge flag), restore
the pre-slew tracking state after slew completion, app-side only (OnStep
adapter is external-owned; unsuppressible auto-track goes to SYNC.md).

## 2026-07-18 - M10-021/M10-022: mount flow decoupled from camera bring-up

Fix for the confirmed blocker (see previous entry): _build_adapters split into
_build_mount_focuser (first, alone, under _adapters_lock) and
_build_main_camera (background "main-camera-connect" thread spawned at the end
of connect_devices, serialized on _camera_open_lock, now an RLock). Requests
that genuinely need the main camera join the in-progress build via
_main_camera(); get_camera_by_role("main") routes there too, so no duplicate
main handle is possible. Hardware mode ignores the camera side until its build
lands (no false "mock" banner while a real camera connects).

API side: /api/observing/state and /api/observing/intent no longer Depends on
get_camera - a _LazyCamera proxy resolves the main camera on first attribute
access only (snapshot and early intents never touch it); the guide lookup in
_build_deps uses new peek_camera_by_role() which returns the already-open
handle or None and never takes _camera_open_lock. Guard tests patch
get_camera/get_camera_by_role to raise and assert both endpoints still answer.

M10-023 (SDK serialization discipline) and M10-024 (Pi lock-vs-GIL evidence)
remain open. 7 new tests; runtime + full API + camera service suites green
(1048). Pi acceptance pending: confirm time/location < 1 s while all three
cameras connect/prime.

## 2026-07-18 - M10-026: camera role cross-wiring fixed (Cameras screen)

Hardware evidence: covering the guide camera (GPCMOS02000KPA) changed the
frame in the OAG panel on the M10-019 Cameras screen - the OAG role was bound
to the guide camera's physical device instead of its own (G3M678M).

Root cause: SmartTouptekCamera._select_device() in
adapters/touptek/managed.py silently fell back to a positional index
(devices[self._index], default 0) whenever a configured model/name/camera_id
selector matched nothing, instead of reporting "not found". A role whose
selector fails to match (typo, SDK-reported name mismatch, disconnected
camera) then silently binds to whatever device happens to sit at that index -
here, the guide camera. resolve_device_id() (used by the startup
validate_unique_camera_roles() conflict check, same file) already treated a
failed selector match as "not found", so the startup check could never catch
this divergence between the two functions.

Fix (SYNC-OVERRIDE, tracked in SYNC.md - camera_adapter permits direct
overrides for this file, unlike OnStepAdapter's stricter flag-and-wait
policy): _select_device() now returns "not found" whenever a selector was
configured but didn't match, mirroring resolve_device_id(). Pure index-only
configs are unaffected. connect()'s existing SYNC-OVERRIDE (return False
instead of raising) surfaces this as a normal, readable "camera failed to
connect" per the M10-017 pattern, rather than a silent wrong-camera bind.

8 new tests (tests/unit/adapters/touptek/test_managed_select_device.py);
touptek/camera-service/runtime suites (152) and the full API suite (1013)
green. Still needed: Pi evidence on why [cameras.oag]'s model selector failed
to match in the first place (config typo vs SDK name mismatch vs a genuinely
disconnected G3M678M) - filed as the remaining open item under M10-026.

## 2026-07-18 - M10-023 done; M10-027 filed (at-home jog refusal)

M10-023 (SDK serialization discipline): legacy preview ToupcamCamera.connect
turned out already covered by _camera_open_lock. The two real gaps fixed:
CameraReadinessService now takes an injected open_lock (wired to
runtime._camera_open_lock) and does a non-blocking acquire at the top of
_scan_once() - skips the whole scan (not queues) when a camera open is in
progress, relying on the existing 15s retry. runtime.get_filter_wheel()'s
first Open() now sits inside _camera_open_lock too (double-checked, same
pattern as _connect_main_camera()); cached returns after that stay lock-free.
No adapters/touptek/*.py edits needed. 5 new tests; full API + touptek/camera
suites green (1093).

M10-027 (new hardware report, same session): the Cameras-screen jog pad
failed with a raw 500 "OnStepSafetyError: axis_motion_refused_at_home" when
pressed at mechanical HOME. Traced to onstep_adapter's _axis_motion(), which
unconditionally refuses any axis motion at home with no bypass parameter -
same family as the existing REQ-ST-004 enable_tracking() at-home bypass.
Local fix: mount_nudge() (api/mount.py) now catches OnStepSafetyError and
returns a clean 409 with the real reason, same pattern _safe_goto() already
uses. The underlying behavior gap (jog genuinely cannot move the mount at
home) needs an onstep_adapter change - recorded as draft candidate REQ-ST-009
in SYNC.md, NOT filed upstream, awaiting the same explicit approval gate as
REQ-ST-003/005/006/008. 1 new test.

## 2026-07-18 - M10-025: goto can now keep tracking off after the slew

New mount_operations.goto_sequence() wraps safe_goto() unchanged (exceptions
still propagate before any tracking logic) and adds an opt-in
keep_tracking_state flag, mirroring the M10-019 nudge flag. Default False is
a pure passthrough - zero extra mount I/O, no behavior change for existing
sky-target callers (setup wizard, collimation, mount test moves - none pass
the flag). When True and the mount was not tracking before the goto, it polls
get_state() (0.5s / 120s budget) until the slew ends and calls
disable_tracking() if firmware auto-re-enabled tracking, since some OnStep
firmware does this on/after a goto. Timeout or a mid-poll get_state() failure
is logged, never raised - the goto itself already succeeded. GotoRequest
gained keep_tracking_state; mount_goto_sky (elevation-based, always
astronomical) stays on the default. App-side only, no adapter touch.

10 new tests (7 service, 3 API); full mount/API suites green (1017).

## 2026-07-18 - M10-024: tooling for the lock-vs-GIL hardware evidence

M10-024 is a hardware-evidence task (does an in-progress camera SDK connect
stall unrelated requests, or is it only the runtime.py locks?), not a code
fix - implemented the means to gather that evidence on the Pi rather than
guessing.

runtime.py now logs "Camera connect+prime timing: role=<role> model=<model>
elapsed=<s>" at INFO around both camera.connect() call sites
(_build_main_camera for the main role, get_camera_by_role for guide/oag) -
a real measurement instead of the config-arithmetic estimate the task
originally proposed (startup_delay_s + prime_attempts x timeout + configure).

New scripts/check_connect_stall.sh <host> <duration_s>: run from a second
SSH session right after astro_start.sh, alternates curl against
/static/js/app.js (zero device dependency) and /api/location/status
(mount-only, no camera dependency post M10-021/022) every ~0.2s, prints
per-request latency plus a verdict - stalls on the static asset would mean
the toupcam binding holds the GIL through Open()/EnumV2() (file a SYNC.md
candidate); stalls only on location/status would mean the M10-021/022 locks
aren't the whole story; no stalls on either means those fixes are sufficient.

2 new tests confirming the timing log fires for both camera-open paths;
runtime + full API suites green (1019). Still needed: run the script on the
Pi during a real camera connect and record the verdict here.

## 2026-07-18 - M10-024 verdict + gpsd ?POLL fix (Pi evidence)

Ran check_connect_stall.sh during a real 3-camera connect (measured
connect+prime: main 1.28s, guide 1.05s, oag 41.84s from the new timing log).
Static asset stayed fast the whole 30s window (max 39ms) even while oag was
still connecting - rules out the toupcam SDK binding the GIL through
Open()/EnumV2(). M10-021/022/023's locks are structurally sound; no SYNC.md
external-requirement candidate needed.

Unexpected finding: /api/location/status was a flat ~780ms on every single
call throughout the window - not a stall-while-camera-opens pattern, so
unrelated to M10-021/022 despite that endpoint deliberately never touching a
camera. Root cause: GpsdService.get_fix() sent ?WATCH (subscribe to gpsd's
live stream) together with ?POLL; in the same request but only recognized a
bare "class":"TPV" line as an answer. gpsd actually answers ?POLL; with a
"class":"POLL" envelope nesting the already-cached fix in a "tpv" array,
answered instantly with no device wait - since that envelope was never
recognized, every call waited for the next naturally-streamed bare-TPV
report instead, i.e. the GPS receiver's own report cadence (~780ms, ~1Hz).

Fixed: new _extract_tpv() reads both the POLL-envelope and bare-TPV shapes;
GpsdService also gained a 2s TTL cache (mirrors api/cameras.py's
_scan_cache pattern) so the ~2.5s observing poll doesn't pay even the fixed
per-query cost every tick. App-side only, SmartTScope's own service code.

5 new tests; gpsd/location/master-source/raspberry-trust suites green (122);
full API+services regression green (2248). Still needed: Pi re-run of
check_connect_stall.sh to confirm /api/location/status latency drops.

## 2026-07-18 - M10-005: exposure/gain/offset auto-tune loop

LiveAnalysisSpec gained six clamp fields (max/min_tuning_exposure_s,
tuning_gain_min/max, tuning_offset_min/max, histogram_ceiling_frac=0.70);
templates/config.toml [live_analysis] documents all of them.

camera_setup_fsm.py's TUNING loop now tracks exposure/gain/offset across
frames: after each capture it takes the LiveAnalysis module's
recommended_exposure_s/gain/offset (the module itself already prefers
exposure over gain internally, per suggest_capture_adjustments()), clamps to
the config bounds, then applies an app-side ceiling on top - if the frame's
measured 99.5th-percentile signal (domain/histogram.py, same stats
AutoGainController already uses) exceeds histogram_ceiling_frac, exposure is
forced down first and gain only once exposure is already at its floor, since
the module has no ceiling parameter of its own yet (LA-REQ-1, still a draft
ask). Gain/offset are applied via set_gain/set_black_level between frames
(best-effort); exposure is a plain per-capture argument, so the tuned value
carries forward into STAR_CHECK too, which previously always used the
static setup_exposure_s regardless of what TUNING found.

9 new tests (6 auto-tune behavior, 3 config-parser); FSM + config + full
unit suite green (4042 passed). One unrelated pre-existing flaky test in
tests/unit/workflow/test_logging.py found during the full run - confirmed
order-dependent (passes standalone) and untouched by this change.

## 2026-07-19 - M10-028: manual jog now works at confirmed mechanical HOME

User decision: manual movement at confirmed home is legitimate (same spirit
as the allowed home->park move). Implemented as SYNC-OVERRIDE REQ-ST-009 in
the SmartTScope-owned shim (adapters/onstep/mount.py): move() opens a
_jog_bypass_active window (try/finally) around the move_*_timed delegation;
the REQ-ST-007 preflight override post-processes only the RETURNED at_home
to False for exactly the two jog preflight commands (move_ra_center /
move_dec_center) while the window is open. Internal at_home/terminal_state
stay truthful (pier/HA blockers must remain suppressed at home);
motion_refused and all mechanical blockers untouched (at-limit still refuses
under the window - tested); all other preflight consumers see the true
state. Latent hazard documented: safe only while runtime.py passes no
motion_calibration - otherwise upstream's projected-target validate_target
gate re-activates and needs the upstream fix.

Upstream ask filed with explicit approval:
https://github.com/tschoenfelder/OnStepAdapter/issues/5 (allow_at_home /
manual mode on the timed-axis API, skipping both at-home gates while
honoring every mechanical blocker). Delete the shim override when it ships.

8 new tests (test_jog_at_home.py, REAL motion_safety_preflight against
FakeOnStepSerial + new :GS# handler in the fake); onstep adapter suite green
(157). Pi verification pending: arrow jog at confirmed HOME moves the mount.

## 2026-07-19 — M10-030: onstep_adapter upgraded to v0.3.3, native manual jog at HOME

Upstream released v0.3.3 closing issue #5 (REQ-ST-009): move_ra_timed/
move_dec_timed accept mode="manual" - allowed at confirmed mechanical HOME,
skips projected-target validation (resolves the M10-028 latent
motion_calibration hazard), requires tracking OFF
(manual_jog_requires_tracking_off), keeps every mechanical blocker and the
motion lock.

Upgrade: pyproject pin + local install 0.3.1 -> 0.3.3 (Pi follows via
astro_start.sh version sync). Shim move() now selects the mode by tracking
state (tracking -> center, off -> manual); the M10-028 _jog_bypass_active
window and the preflight at_home post-process were deleted - preflight is
truthful for every consumer again.

Full override re-diff (SYNC.md updated): REQ-ST-003/005/006/008 shipped in
v0.3.2 (issue #3), including a tracking-authorization guard - get_state()
auto-disables tracking with no explicit request. The shim's REQ-ST-004
enable_tracking() copy therefore now sets _tracking_explicitly_requested=True
on success (otherwise the next poll would kill tracking enabled at home).
REQ-ST-004/007/002-residual remain local (upstream bodies unchanged, no copy
drift); _haversine_m/_lx200_round_degrees delegate to onstep_adapter.location.

Cameras-screen jog pad unchanged (nudge -> move() picks manual mode natively;
new refusal reason surfaces via the M10-027 409 path). test_jog_at_home.py
rewritten (8 tests incl. mode selection + truthful preflight); one fake-serial
test adapted to the v0.3.2 guard. onstep suite 157 passed; full unit suite
green (known test_logging order flake only). Pi verification pending.

## 2026-07-19 — M10-029: TEC cooling toggle on the Cameras screen

Only cooled cameras get the control (user decision: only the ATR585M has a
TEC). The readiness scan reports has_tec per role straight from the
enumeration flag bits (0x80 | 0x20000); /api/cooling/status now carries
default_target_c from the new [cooling] default_target_c config option
(templates/config.toml updated, default -10).

multicam.js: panels with has_tec get a snowflake toggle + status span in the
panel header; toggling calls the existing POST /api/cooling/set_target with
the panel's sdk_index and the config default target; a 10 s poll renders
current -> target (power %) on the active panel and re-derives a running
session on view enter. Cooling deliberately keeps running on view leave -
hardware state like tracking, unlike the per-view preview sockets. The
Stage-1 cooling card's target input prefills from default_target_c (config
single source; user edits win). CoolingService itself unchanged
(single-session stays sufficient).

Tests: readiness has_tec (3) + cooling default_target_c (2); readiness +
cooling suites 64 passed; node --check clean on multicam.js/setup.js.
Pi verification pending.

## 2026-07-19 — M10-031: larger jog step size while not tracking

Hardware feedback: mount jog at confirmed HOME works (M10-030) but even the
2s max step was far too small to walk the mount from home down to the
horizon. /api/mount/nudge now applies two duration ceilings mirroring the
shim's own move() mode split: a tracking centering correction stays capped
at 5000ms (unchanged); a not-tracking jog (confirmed HOME, or any terrestrial
jog with keep_tracking_state=True) may run up to 60000ms - well under
upstream's 120000ms hard limit for center/manual mode. The check uses the
mount's tracking state after any enable_tracking() side effect, so an
auto-enabled tracking correction stays capped tight regardless.

multicam.js: #mc-jog-dur gained 5/10/20/40/60s options; the existing 5s
mount-status poll now also reads tracking_state and disables (or clamps
back) options above 5000ms while tracking, so the UI reflects the server cap
instead of surfacing a 422.

5 new mount API tests; suite 154 passed. Pi verification pending.

## 2026-07-20 — M10-032: hardware-session bug fixes (guide-cam black frames, unverified home-solve, opaque asserts)

Hardware report 2026-07-19/20 bundled four symptoms: guide camera preview
goes black after one frame (4s exposure, gain 400) despite pointing at
bright sky; polar alignment's HOME solve failed via ASTAP; unclear which
camera ran; an AssertionError appeared in the log. Real Pi log wasn't
available yet, so three parallel Explore agents traced this from code
inspection alone — all three turned out to be real, independent bugs.

`adapters/touptek/managed.py`: `capture_mode="snap"` (only the guide camera
model, GPCMOS02000KPA) configured `TOUPCAM_OPTION_TRIGGER=0` (free-run video
mode, confirmed via resources/touptek/toupcam.py:125) and left it there
permanently, while `_capture_raw()` kept calling `Snap(0xFFFFFFFF)` per
capture as if it were a one-shot mode — the already-working main/oag path
instead settles then switches to `TRIGGER=1` (software trigger) and calls
`Trigger(1)`. Fixed by making "snap" mode follow the same
settle-then-switch-to-TRIGGER=1 sequence and use `Trigger(1)`, unifying it
with the proven main/oag flow. Cannot be verified from this Windows dev box
(no ToupTek SDK/hardware) — needs a Pi session.

Also replaced 4 bare `assert self._cam is not None and self._tc is not None`
in managed.py with explicit checks raising a descriptive RuntimeError — bare
asserts carry no message (`str(AssertionError())` is `""`), which is
consistent with "an AssertionError appeared in the log" being uninformative;
any of the four firing propagates through preview.py's generic exception
handler and permanently kills the preview stream regardless of which one
fired, so this is a real diagnostics improvement independent of the trigger
fix above.

`api/polar.py`: the safety checklist's `mount_at_home` field was a pure
client-side checkbox (`mount.js` `paConfirmChecklist()` hardcodes `true`
once every box is ticked) never cross-checked against real mount state —
`polar_measure()` now hard-blocks unless `DeviceStateService.get_mount_state()`
reports `MountState.AT_HOME`. Deliberately uses the device-state cache's
sticky-AT_HOME promotion, not a raw `mount.get_state()` call — per
`home_sequence()`'s own docstring, AT_HOME is a brief hardware flag that
clears within seconds on real OnStep hardware, so a raw call here would
almost always see it already cleared. `MeasureRequest`/`FallbackCameraRequest`
gained an optional `camera_role` field resolved via the existing
`deps.resolve_camera_index()` (same pattern as `api/solver.py`'s
`SolveRequest`) instead of only accepting a raw `camera_index`; `PolarStatus`
now reports `cam_index`/`cam_role` back (resolved via the optical-train
registry even when only a raw index was given) so it's always clear which
camera ran a solve.

New `tests/unit/api/test_polar.py` (7 cases). Touptek adapter suite (59) +
full unit suite (4068 passed, 24 skipped) green. Guide-cam trigger fix and
the AT_HOME gate both need Pi hardware verification — noted as pending in
`docs/todo.md` M10-032.

## 2026-07-19 — M10-020 (first approximation): FOV overlay on the Cameras screen

User request: show where each narrower-FOV camera's frame falls inside the
widest-FOV panel on the Cameras compare screen, as a lime-green rectangle.
User chose (via AskUserQuestion) the cheap geometric approximation already
scoped in M10-020's "first approximation" bullet over the harder plate-solve
half of that item, and one labeled rectangle per detected narrower-FOV
camera rather than just the single next-largest.

`_mcPaintFovOverlays()` (new, multicam.js) draws into the top panel's own
canvas right after its `ctx.drawImage(...)` call, only when
`_mcScaleMode === 'angular'` (the "same sky scale" mode) — fit mode scales
each panel independently, so there is no shared arcsec-per-pixel scale to
compute a sub-rectangle from, and the overlay simply doesn't appear there.
For every non-top panel it reuses `_mcPaint`'s own drawW/drawH formula
(`f.wArcsec / sharedScale * dpr`) so the sub-rectangle is on the same pixel
scale as the top image by construction, centers it on the top image's
center (the co-alignment assumption — no offset/rotation data exists
anywhere in the optical-train config model, confirmed by repo search), and
strokes it `limegreen` with a small role-name label. No backend changes.

No dirty-flag changes needed — the overlay is recomputed every top-panel
repaint, and everything that should invalidate the top panel already marks
it dirty (`_mcAssignSlots`, `multicamToggleScale`, canvas resize).

Verification: `node --check` clean. This Windows dev box has no ToupTek SDK,
so `CameraReadinessService` (real-hardware-only enumeration, no mock path)
never reports a camera as DETECTED here and the live Cameras screen shows
zero panels regardless of this change — not a regression, a pre-existing
M10-019 environment limit. Verified instead by executing the real
`_mcPaintFovOverlays()` in-browser against synthetic panel data shaped like
`_mcBuildPanel`'s output: no error across 1x/2x dpr and multiple non-top
panels, correctly skips the top panel, and the drawn rectangle's edge
lands (pixel-checked via `getImageData`) exactly where the FOV math
predicts. Pi/real-hardware verification pending.

## 2026-07-20 — M10-033: new Autofocus screen (main camera) + M10-034 jog-rate request drafted, not filed

Two pieces of hardware feedback in one request. User was explicitly asked
detailed clarifying questions before implementation ("grill me") given how
much was genuinely ambiguous or blocked on a project-process rule.

**M10-033 (done):** new top-level "Autofocus" tab, main camera only — guide
has no focuser, OAG shares the main focuser and is manually synced (user
confirmed out of scope). `app.js`'s `showTopView()` generalized from a
cameras-only `if/else` into a small per-view `_TOP_VIEW_STREAMS` dispatch so
Autofocus gets its own enter/leave lifecycle without disturbing Cameras'.
New `static/js/autofocus.js`: arrow buttons `+5/+1/-1/-5` call the existing
`POST /api/focuser/nudge`, which already clamps to `[0, max_position]` live
from OnStep (`:FM#`) — confirmed via the upstream focuser adapter, so no new
range-clamping logic was needed to satisfy "always stay in range... as
stated by OnStep." Live preview is a small self-contained `ws/preview`
client (same wire protocol `preview.js` uses) rather than reusing
`preview.js`'s singleton connection, which is tied to Stage 3/4-specific DOM
ids and would couple this screen's preview to whatever Stage 3/4 happens to
be configured with elsewhere. Terrestrial/sky toggle is a screen-local
checkbox — no such concept existed anywhere in the app; in sky mode a
periodic readout shows HFD (`domain/focus_metric.py`, the same metric the
existing best-focus search in `workflow/autofocus.py` already uses — there
is no true numeric FWHM anywhere in the repo, so this is honestly labeled
HFD, user-confirmed) plus `stars_found` from the external LiveAnalysis
module when installed.

New `api/autofocus_sequence.py`: `POST /api/autofocus/sequence` +
`GET /api/autofocus/sequence/status/{job_id}` capture a bracketed sequence
of individual (not stacked) raw FITS frames at different focuser positions
to support tuning autofocus later — distinct from the existing
`/api/focuser/autofocus`'s HFD-fit best-focus search, which doesn't persist
frames. Background job + status-polling pattern mirrors
`api/calibration.py`'s bias/dark/flat jobs; range/step validated against the
focuser's live `max_position` before the sweep starts (422 if it doesn't
fit). Filenames encode the position (`af-seq_pos-<position>_<index>.fits`),
plus a `FOCUSPOS` FITS header key. Also added `POST /api/autofocus/frame_metrics`
for the live HFD/star-count readout.

Verified via browser: new tab wires up correctly, live preview connects and
renders frames, arrow-nudge/sequence-capture calls surface server errors
correctly (this dev box's mock focuser/camera report unavailable/slow —
confirmed via direct curl calls that the endpoints themselves respond
correctly, e.g. `frame_metrics` with `camera_index=0` returned a real HFD +
LiveAnalysis result in ~4s; `sequence`/`nudge` correctly 503 when the mock
focuser is unavailable, matching unit-tested behavior). 10 new tests
(`tests/unit/api/test_autofocus_sequence.py`); full unit suite 4078 passed,
24 skipped (one `test_logging.py` order-dependent flake reproduced and
confirmed pre-existing/unrelated — passes in isolation). Pi verification
pending: live preview + arrow-nudge clamping + HFD/star-count readout
against real hardware.

**M10-034 (blocked, not implemented):** higher jog slew rate (16x default,
2x/4x/32x options) for the Cameras-screen jog pad. Investigation found no
rate-selection plumbing exists anywhere — not in SmartTScope, not in the
pinned `onstep_adapter` package, which hardcodes `:RG#`/`:RC#` only (LX200
actually supports 10 presets, `:R0#`-`:R9#`). Per this project's standing
rule (never patch OnStep protocol behavior locally — canonical source is
the published release only), user decided to file an upstream request
rather than adding a local protocol-level override. No code changed for
this half of the request.

**Update 2026-07-20 (same day):** user confirmed go-ahead — REQ-ST-010
filed as <https://github.com/tschoenfelder/OnStepAdapter/issues/7>
("Rate-selectable jog/move API (2x/4x/16x/32x sidereal presets)"),
requesting a rate-selectable variant of `move_ra_timed()`/`move_dec_timed()`
(or a new `set_jog_rate()`) accepting one of OnStep's `:Rn#` presets, with
existing mode-based safety gating unchanged. `SYNC.md`/`docs/todo.md`
updated to reference the open issue; M10-034 stays blocked pending upstream
response — no local implementation until it ships.

## 2026-07-21 — M10-034: OnStepAdapter 0.3.4 integrated — rate-selectable jog shipped

Upstream shipped v0.3.4 the same day, closing issue #7 / REQ-ST-010:
`move_ra_timed()`/`move_dec_timed()` now accept an optional
`rate_preset: int` (0–9), sending `:R<preset>#` instead of the mode's
default rate command (`:RG#` guide, `:RC#` center/manual). Confirmed by
reading the released source directly (not just the changelog) — safety
gating (tracking-off requirement for manual mode, mechanical blockers,
duration bounds, motion lock) is unchanged.

Upgrade: pin bumped 0.3.3→0.3.4 in `pyproject.toml`,
`pip install -e ".[dev]"`. Re-diffed the two overrides most likely to
interact with this change — `enable_tracking()` (REQ-ST-004) and
`motion_safety_preflight()` (REQ-ST-007) — both byte-identical to v0.3.3 in
the relevant sections; no drift, both overrides remain necessary.

Plumbed `rate_preset` end to end: `MountPort.move()` (`ports/mount.py`) and
all three adapters (`onstep`, `mock`, `simulator`) gained
`rate_preset: int | None = None`; the OnStep shim's `move()` forwards it
straight into `move_ra_timed`/`move_dec_timed`. `api/mount.py`'s
`NudgeRequest` gained `rate_preset` (0–9, schema-validated);
`mount_nudge()` rejects (422) any non-`None` `rate_preset` whenever the jog
would be a tracking correction (`will_track`, including the path where
tracking gets auto-enabled) — a custom rate is only accepted for a genuine
non-tracking jog, per the user's original "not-tracking jog only" decision.

UI: Cameras screen's `#mc-jog` gained a `#mc-jog-rate` select. Deliberately
offers only the 6 presets this repo has a documented multiplier for
(`wiki/onstep-protocol.md`: R0=0.25x, R2=1x, R4=4x, R5=8x, R7=24x, R9=60x) —
R1/R3/R6/R8 have no recorded value anywhere (confirmed: `onstep_adapter`
itself has no fixed multiplier table either — rate calibration is
explicitly skipped for manual mode, since the real multiplier is
OnStep-firmware-configurable, not a value this codebase can compute) and
were deliberately not guessed at. Default is R7 (24x), the closest
confirmed preset to the user's original "at least 16x" ask.
`multicam.js`'s existing M10-031 tracking-state poll extended with a
parallel clamp: while tracking, the rate select is forced back to "Mode
default" and every preset disabled, mirroring the duration select exactly.

Tests: 3 new shim-level cases (rate_preset forwards on both axes, defaults
to None) + 5 new nudge-endpoint cases (rejected while tracking / while
auto-enabling tracking / out-of-range; forwarded correctly for a genuine
non-tracking jog; omission defaults to None) + 4 existing assertions
updated for the new call signature. Full unit suite 4086 passed, 24
skipped.

Verified end-to-end against the mock mount + real browser (no OnStep
hardware on this Windows dev box): confirmed via direct API calls that
`/api/mount/nudge` 200s with `rate_preset` for a genuine non-tracking jog,
422s while tracking (both already-tracking and auto-enabled-tracking
paths) and for an out-of-range value; confirmed via the browser that the
rate select renders all 6 options + defaults to R7, and that the real
`_mcStartMountPoll()` function (not a hand-copied stand-in) correctly
clamps/re-enables it as the mount's reported tracking state changes, and
that `multicamJog()` sends the selected `rate_preset` in the nudge request
body. Pi verification pending (user): real mount actually moves noticeably
faster at the higher presets, and OnStep firmware accepts all 6 exposed
`:Rn#` commands as expected.

(Debugging note: initial browser/curl verification attempts silently hit a
stale uvicorn process left over from an earlier `pkill` that didn't
actually match the Windows python.exe command line — port 8123 had two
processes both partially bound. Diagnosed via
`Get-NetTCPConnection -LocalPort 8123`, force-killed both, restarted a
single clean instance, and re-verified against that before trusting any
result.)

---

## 2026-07-22 — Four bugs reported from a real Pi hardware test session

User ran an actual test session on the Pi and reported four issues in one
message. Root-caused via `systematic-debugging` before touching code;
two had a clear root cause and were fixed, two need more repro detail
from the user before a fix can be attempted (asked, not guessed).

1. **`IMAGE_ROOT is not configured`, `export IMAGE_ROOT='~'` didn't help.**
   Root cause: `config.py` has supported `IMAGE_ROOT` (env var or
   `[session].image_root` TOML key) since `docs/autogain-tasks.md`'s
   autogain work, but `templates/config.toml` was never updated with the
   key — violates this project's own "templates always in sync" rule. A
   shell-exported env var is also fragile across restarts/sessions
   compared to the persisted TOML file. Fixed: added
   `image_root = ""` to `templates/config.toml`'s `[session]` block with
   an explanatory comment. **User action still needed**: add the matching
   line to the actual `~/.SmartTScope/config.toml` on the Pi (that file
   lives outside git per this repo's Pi-deployment rule, so this fix alone
   doesn't reach it).

2. **Capture focus sequence: default start field looked off, and a
   400–600 step-5 sweep reportedly captured 1121 frames ending at position
   1608.** Investigated `api/autofocus_sequence.py`'s position math
   (`range(current+start_offset, current+end_offset+1, step)`) and
   `static/js/autofocus.js`'s `afStartSequence()`/`_afPollSequence()` —
   found nothing that reproduces a ~27x frame-count blowup from those
   inputs; the last-position math does check out if current position was
   ~1008. Not fixed — asked the user for the exact values/status text
   next time, since the numbers as reported don't match any bug found by
   inspection.

3. **Number input fields too narrow for 6-digit values.** No single field
   confirmed as the culprit, but the same "Capture focus sequence" card's
   start/end offset fields (`af-seq-start`/`af-seq-end`, 7ch) were the most
   likely candidate given a wide focuser sweep — widened to 9ch/7ch
   (`af-seq-step`). Flagged to the user in case a different field was
   meant.

4. **Polar alignment fails despite 20+ stars detected; UI doesn't show
   which camera is used.** The camera-identity gap was a confirmed, clear
   bug: `api/polar.py`'s `PolarStatus` has carried `cam_index`/`cam_role`
   since `_resolve_cam_role()` was added specifically so "PolarStatus
   always shows which camera ran" — but `static/js/mount.js`'s `_paRender()`
   never read either field. Fixed: added a `#pa-cam-label` span next to the
   step label in `index.html`, populated from `d.cam_role`/`d.cam_index` in
   `_paRender()`. The "fails despite stars detected" half is a different
   claim (star *detection* success doesn't imply plate-*solve* success) and
   needs the actual `error_msg`/step shown by the UI to root-cause — asked
   the user rather than guessing.

---

## 2026-07-22 — Follow-up: root cause found for polar-solve failure; other two confirmed/still open

User answered the three follow-up questions from the entry above:

- **Narrow field (#3):** confirmed as the Capture-focus-sequence
  Start/End/Step fields — no further action needed, the width fix already
  applied stands.
- **Polar failure (#4a):** confirmed as the "plate solve failed twice,
  guide-camera fallback offered" path — ruling out the AT_HOME gate or a
  coarse-alignment card. This let root-cause investigation actually
  finish: `api/polar.py`'s `_run_workflow_loop` `FAILED` handler, when
  `act.camera_fallback_suggested` is true, discarded `act.message` (the
  real per-attempt solver error assembled in `domain/polar_workflow.py`,
  e.g. `f"Solve 2 failed (with retry): {sr.error}"`) and replaced it with
  a hardcoded generic string — so the actual reason the solver couldn't
  match a 20+-star field was never visible anywhere, not even in
  `error_msg`. Fixed: the real message is now preserved in
  `_state.error_msg`; `static/js/mount.js` and a new
  `#pa-fallback-reason` element in `index.html` display it on the
  fallback-offered card. Tests: `tests/unit/api/test_polar.py` (7) +
  domain polar tests (52 total with `-k polar`) still green — nothing
  asserted the old generic string. Next Pi run will surface the actual
  solver error for the first time; that's the real next diagnostic step,
  not guessed at here.
- **Capture-sequence frame count (#2):** user clarified they never
  actually ran the ~1129-frame sequence — cancelled once the estimate
  appeared, because it would have taken too long. So this was never a
  wrong *completed* result, just a surprisingly large `n_frames` estimate
  from inputs described as "400 / 600 / step 5". The position math in
  `api/autofocus_sequence.py` (`range(current+start_offset,
  current+end_offset+1, step)`) doesn't reproduce ~1129 from those values
  under the documented "offsets relative to current position" semantics
  (expected ~41). Left open in `docs/todo.md` M10-035 — need the exact
  Start/End/Step values from a future run to tell a real off-by-N bug
  from a units mix-up (offset vs. absolute position).

---

## 2026-07-22 — M10-036: saturated multicam tile rendered black, not white

User reported the bottom-right camera tile going solid black after the
first frame, this time with a server log snippet attached — no guessing
needed, the log itself was the evidence:
`camera_index=3 ... mean_adu=4095 p99_adu=4095 sat=100.00%`, repeated
across captures. That's a fully **saturated** frame (every pixel at the
sensor's ADC max), not a dark one.

Root cause: both `domain/stretch.py`'s `auto_stretch()` and
`api/preview.py`'s `_auto_stretch_color()` (the Bayer/colour equivalent)
compute a MAD-based sigma stretch, then fall back to solid black whenever
the frame has no dynamic range (`hi <= lo` — true for both an all-zero
frame *and* an all-max/saturated one). The docstring even said this
fallback was written for "MockCamera, all-zero data" — the saturated case
was never considered, so a 100%-saturated tile rendered pixel-identical to
a dead/no-signal one.

Fixed: both functions now accept `adc_max` and map a uniform frame to flat
grey at its true `background / adc_max` brightness — 0 ADU still renders
black, `adc_max` now renders white, anything uniform in between renders
proportional grey. `api/preview.py`'s `_to_jpeg()` already computed the
real per-frame `adc_scale` from the `BITDEPTH` header for its non-stretch
path (confirmed this is why the log's `p99_adu=4095` exactly matched a
12-bit sensor, not the function's old 16-bit-shaped default) — now threads
that same value into both stretch calls.

Tests: `tests/unit/domain/test_stretch.py`'s `test_uniform_array_returns_black`
renamed to `test_uniform_low_array_returns_near_black` (a low uniform
value still renders near-black, just not bit-exact zero) plus a new
`test_uniform_saturated_array_returns_white`; `test_zero_array_returns_black`
left unchanged. Full unit suite run to confirm nothing else assumed the
old always-black uniform behavior.

Pi verification pending (user): deliberately overexpose the affected
camera and confirm the tile now shows white/bright instead of black.

---

## 2026-07-22 — M10-037: live-preview autogain permanently stuck at max exposure/gain

Follow-up to M10-036 above. User pushed back hard on the "just gain=400 too
high, nothing to fix" conclusion by pointing out `autogain=True` was on for
the OAG connection the whole time — if autogain were working, it shouldn't
sit saturated indefinitely. That was the right instinct; log correlation
(`grep -nE "Preview WS accepted: camera_index=3|Autogain (enabled|disabled|
update): camera_index=3"`) confirmed it: on both connections captured in the
log, exactly two `Autogain update:` lines fired (exposure 2.0→4.0, then gain
100→400) and then **nothing ever again**, even though many more saturated
frames were captured afterward.

Root cause: `api/preview.py` calls `camera.get_bit_depth()` and constructs
`AutoGainController(exposure, gain, bit_depth=cur_bit_depth)` *before* the
capture loop starts. `adapters/touptek/camera.py`'s `get_bit_depth()`
(lines 398-400) explicitly documents returning the stale default (16) until
the first capture completes, for sensors whose true native depth is only
known after lazy pixel-shift detection on frame 1. `AutoGainController`
fixes `self._bit_depth` at construction and never refreshes it — so for the
OAG (a real 12-bit sensor, G3M678M), it stayed wrongly locked to 16 for the
whole session. A genuinely saturated 12-bit frame (4095/4095) read against
the wrong `adc_max=65535` computes `mean_frac≈6%` — looks *dark*, not
saturated — so the controller kept "brightening" until exposure and gain
both hit their hardcoded ceilings (4.0s / 400 — no `CameraProfile` is passed
at this call site), then had nowhere left to go and went silent forever,
masking the real 100% saturation from the auto-gain loop the entire time.
The separately-tracked, correctly-per-frame-refreshed `cur_bit_depth` used
for the log's own `mean_adu`/`sat=` stats showed the true saturation the
whole time — which is exactly why the evidence looked self-contradictory
(real saturation stats + supposedly-active autogain) until this was traced.

Fixed: `domain/autogain.py`'s `AutoGainController.update()` gains an
optional `bit_depth` parameter that overrides `self._bit_depth` for that
call only (omitting it preserves the old behavior — fully backward
compatible for the one other test-only caller pattern); `api/preview.py`'s
autogain-update block now passes the already-correctly-refreshed
`cur_bit_depth` into every `ctrl.update()` call.

Tests: `tests/unit/domain/test_autogain.py`'s new
`TestPerFrameBitDepthOverride` — one case proving the override corrects a
would-be-stuck saturated frame, one proving omitting it preserves the
constructor's value, and one characterization test reproducing the exact
bug (no override → stuck at max exposure/gain on a genuinely saturated
12-bit frame) so a future refactor can't silently reintroduce it. Full unit
suite run to confirm nothing else broke.

Pi verification pending (user): confirm the OAG's live preview now actually
dims — exposure/gain visibly decrease and `Autogain update:` lines resume —
instead of sitting stuck at max once saturated.

(Also in this commit — M10-038: the Capture-focus-sequence card's Start/End
defaults, -500/+500, are offsets from the current focuser position but never
accounted for where that position actually is; near either end of a real
focuser's range (screenshot: position 15/50000) they're guaranteed
out-of-range. Fixed in `autofocus.js`'s existing position poll: clamps
Start/End to `[0, max_position]` the first time a real position is known,
then leaves user edits alone.)

---

## 2026-07-22 — M10-039: live preview hang during capture sequence + missing exp/gain feedback

Same user report as above, three more items. Two were root-caused and
fixed; one turned out not to be a bug.

**The hang** (multicam preview seems to freeze, only recovers after
navigating to Autofocus and back): traced to `api/autofocus_sequence.py`'s
`start_sequence()` starting its background capture loop via a raw
`threading.Thread(...).start()`, completely bypassing the shared
`JobManager` that `api/preview.py`'s live-preview websocket already checks
before every capture ("yield while a background job owns the camera",
sending `camera_busy` and backing off gracefully). Since the sequence job
never claimed `camera:{index}`, the preview had no way to know the camera
was busy — both sides fought over the ToupTek adapter's own low-level
per-camera `_capture_lock` instead, and the preview blocked silently for the
sequence's entire (potentially minutes-long, multi-position) run — reading
as a hang with no error and no automatic recovery. Fixed: `start_sequence()`
now submits via `JobManager.submit("autofocus_sequence", {"camera:{index}"},
...)`, mirroring `api/autogain.py`'s existing one-shot-job pattern, with a
generous `timeout_s` sized to the requested position count; a
`ResourceConflictError` now returns 409 instead of silently contending for
the hardware lock. Same-pattern gap also found in `api/calibration.py`'s
equivalent job — flagged but deliberately not touched here to keep this fix
targeted. This almost certainly also explains two more symptoms in the same
report (a stale white/bright preview frame sitting next to a correctly
"too_dark" metrics readout; Cameras-screen tiles looking stuck at extreme
exposure/gain) since the independent metrics poll isn't gated by the same
lock and kept reporting real data while the frozen preview just never got a
fresh frame — needs confirmation on the next Pi test now that this is
fixed, not assumed.

Tests: `tests/unit/api/test_autofocus_sequence.py` gained
`test_returns_409_when_camera_resource_already_held` and
`test_camera_resource_released_after_job_completes`; all 12 cases in that
file plus `tests/unit/services/test_job_manager.py` green (52 total).

**Missing exp/gain feedback on the Autofocus screen**: `api/preview.py`
already sends a `camera_info` message on every preview connection carrying
`effective_exposure`/`effective_gain`, but `autofocus.js`'s websocket
handler explicitly discarded every JSON message (`if
(!ev.data.startsWith('{')) ...; return;` before ever parsing it) — showing
nothing but raw error strings. Fixed: parses `camera_info` and displays it
in a new `#af-eff-settings` span next to the status text.

**Not a bug — clarified, not fixed**: capture-sequence Start defaulting to
`-15` at focuser position 15 is exactly correct, not a mistake — `-15` is
the offset that brings the sweep's lower bound to exactly `0` (the
focuser's minimum), per M10-038's own clamp (`max(-500, -position)`). The
field holds a relative offset, not an absolute position, so a negative
value near the current position is expected, not a red flag.

Full unit suite: 4092 passed, 0 failed, 24 skipped.

---

## 2026-07-22 — M10-040: guide camera's live-preview autogain never adjusted

After M10-037 shipped, the user reported main and OAG now adjust exposure
correctly on the Cameras screen, but guide stays pinned at `4.00s · gain
400` regardless of the actual light level. This is a real, different bug
from M10-037 — that fix was about a stale bit-depth locked at construction;
guide's sensor genuinely is 16-bit (matching the stale default), so it was
never affected by that specific mechanism.

Root cause: `AutoGainController.update()` (`domain/autogain.py`) always
computed its signal as `mean_frac`, regardless of the `mode` the controller
was constructed with — `mode` only ever selected conversion gain, never the
brightness metric. A guide camera stares at a mostly-dark sparse field
(background plus one guide star); the *mean* stays near zero no matter how
bright that one star actually is, so the controller always read the scene
as "too dark" and drove exposure/gain to their ceiling — and then, correctly
per its own logic but wrongly for the actual scene, just sat there forever
(this controller has no terminal NO_SIGNAL/GAIN_LIMIT_REACHED status the
way the one-shot `AutoGainService` does — that asymmetry is expected, not a
bug in itself). Compounding it, `api/preview.py` never selected
`AutoGainMode.GUIDING` for the guide role anyway — every camera's live
preview controller was constructed with the default DSO mode.

Fixed: `AutoGainController` now stores `self._is_guiding` and `update()`
branches its signal metric — `stats.p99_9` (the guide-star peak) against a
new `_GUIDE_LO`/`_GUIDE_HI`/`_GUIDE_TARGET` band (0.20/0.80/0.45, matching
`AutoGainService.run_one_shot()`'s existing one-shot GUIDING band in
`domain/autogain_service.py`) instead of `mean_frac` against the DSO band,
and skips the DSO-only sparse-field early-exit heuristic (not applicable —
GUIDING already targets the star peak directly, no need to guess from a
low mean). `api/preview.py` now resolves `mode=AutoGainMode.GUIDING`
whenever `camera_role == "guide"`, at both `AutoGainController`
construction sites.

Tests: new `TestGuidingModeSignalMetric` in `test_autogain.py` — a helper
`_sparse_star_frame()` needed at least ~10 bright pixels out of 4096 for
`np.percentile`'s 99.9th-percentile interpolation to actually reflect the
peak value (a single bright pixel doesn't reach that percentile rank —
caught this by an initial test failure, not assumed). 5 cases: DSO mode
still uses mean (regression); in-band guide star → no change; too faint →
brightens; too bright → dims; genuinely no star → still correctly hits the
ceiling. 95 tests green across the affected test files.

Also in this pass: the user flagged the M10-038 `-15` default again,
having apparently not seen (or not been convinced by) the chat explanation
that it's mathematically correct. Rather than just re-explain, added a
live `#af-seq-range` line under the Start/End/Step fields showing
"Absolute positions: X → Y (focuser range 0 – max)", recalculated on every
position poll and every Start/End edit — makes the offset math
self-evident instead of requiring an explanation.

Pi verification pending (user): confirm the guide camera's live preview
now actually reaches a stable, well-exposed setting instead of sitting at
4.0s/400 regardless of the real guide-star brightness; confirm the new
absolute-range line displays/updates correctly.

---

## 2026-07-22 — M10-041: exposure readout rounds to "0.00 s" at short exposures

User's very next report: guide still shows "4.00 s · gain 400" (no
apparent change) and OAG now shows "0.00 s · gain 100" — the latter a
genuine, separate, confirmed bug: `static/js/multicam.js`'s autogain-message
handler used a fixed `.toFixed(2)`, so any exposure below 5ms (the
controller's floor is 1ms) displays as indistinguishable-from-zero. Fixed
with a small `_mcFormatExposure()` helper scaling decimal precision to
magnitude.

The guide "no change" report and a re-submitted "sequence minimum-focus
bug" screenshot are more likely stale-deployment artifacts than new bugs:
the screenshot's filename/timestamp is identical to the one attached to
the original M10-038 report several turns ago, and M10-040 (the guide fix)
was only pushed this same session — asked the user to confirm the Pi has
actually been restarted with the latest pull before investigating either
further, rather than re-chasing already-fixed, already-tested code.

---

## 2026-07-22 — M10-042: focuser lock held for the whole sequence, blocking jog/nudge

`api/autofocus_sequence.py`'s `start_sequence()` background loop held
`coordinator.focuser_command()` around the *entire* multi-position run
instead of just each position's move+settle step — any jog/nudge request
elsewhere blocked for the sequence's full duration (potentially minutes)
before eventually 409ing, surfacing as unresponsive movement controls.
Fixed: the lock is now acquired and released per position, around
`focuser.move()` + `_wait_stopped()` only; `camera.capture()` runs with it
released. Positions are absolute, so a manual nudge landing between two
sequence steps doesn't corrupt anything — the next step still targets its
correct absolute position regardless of where the focuser sits when it
starts. New `test_focuser_lock_released_during_capture` asserts the lock
is acquirable (non-blocking) during every capture call in the sequence.

---

## 2026-07-22 — M10-043 (in progress): guide autogain still stuck — added instrumentation, not fixed yet

Confirmed the Pi is running v0.1.0 `2957aca` (includes M10-040's guiding-
mode fix), so "no change on guide" isn't a stale-deployment artifact —
worth investigating for real. `Autogain update: camera_index=0` showed the
same ramp-then-stuck pattern as before (2.0→4.0s, 100→400 gain, then
silence) — but this pattern alone can't distinguish "the fix isn't
engaging" from "genuinely no guide star in view" (a totally dark frame
drives *any* signal metric to the ceiling identically).

Asked for `Preview frame: camera_index=0` lines to break the tie:
`mean_adu=4094 p99_adu=4094 sat=0.00%` — mean exactly equals p99 (a
perfectly uniform frame, same signature as the M10-036 OAG bug), which is
genuinely ambiguous: whether 4094 means "nearly black" or "nearly fully
saturated" depends entirely on the per-frame bit depth actually used for
this camera, which was never logged anywhere. Rather than guess, added
`bit_depth=` and `p99_9_adu=` (the guiding-mode signal's exact value) to
the existing `Preview frame:` log line in `api/preview.py` — a pure
diagnostic addition, no behavior change. Full unit suite green (4098
passed); no test asserts this log line's format.

Left open in `docs/todo.md` as M10-043 — the next log capture with this
instrumentation will show conclusively whether guide's true bit depth
matches config (16, dark frame, correct behavior) or not (12 like the OAG,
genuinely saturated, real remaining bug). Not fixing anything further
until that data is in hand.

---

## 2026-07-22 — M10-043 continued: bit_depth confirmed 16, but the value never changes

The requested log line came back: `bit_depth=16 mean_adu=4094 p99_adu=4094
p99_9_adu=4094 sat=0.00%`. Taken alone, this is internally consistent —
4094/65535≈6% is below `_GUIDE_LO`, so the controller correctly reads it as
too dark and brightens. But across five captures spanning
`exp=2.0s/gain=100` through `exp=4.0s/gain=400` (an 8× combined
exposure×gain range), the value is **bit-for-bit identical every time**.
Real sensor data — dark current and read noise both scale with exposure
and gain — cannot plausibly stay perfectly constant across an 8× change.
This rules out "autogain logic is wrong" (already fixed, and its math is
correct given this input) and points at the capture path not actually
reflecting the requested exposure/gain at all.

Considered and ruled out one specific hypothesis before touching code:
that `_pull_pixels()`'s `still` flag for "snap" mode (always `False`, since
`TOUPCAM_EVENT_STILLIMAGE` never fires under the trigger-based capture both
modes now share) was wrong. `wiki/touptek-sdk.md` documents
`TOUPCAM_EVENT_IMAGE → PullImageV4` as the normal, expected path — not a
bug — so did not make a blind change to unverifiable SDK-parameter
semantics.

Found a more systemic, real risk instead: `managed.py`'s `_try()` wraps
*every* SDK call in this adapter (`set_gain`, `put_AutoExpoEnable`, RAW-mode
setup, gain range queries, ...) and silently swallowed any exception with
zero logging. If `put_AutoExpoEnable(0)` were silently rejected for this
specific camera, the sensor's own auto-exposure algorithm would keep
overriding every manual exposure/gain command and could converge on a
fixed reading regardless of what we request — which would look exactly
like what's observed, and would be completely invisible today.

Added instrumentation, not a fix: `_try()` now logs a warning (source
location + exception) on any SDK call failure; `api/preview.py`'s `Preview
frame:` log line gained `actual_exp_ms=`/`actual_gain=`, read back directly
from the camera, next to the requested `exp=`/`gain=` — the next capture
will show directly whether they diverge, and whether any SDK call is
silently failing. Tests: `test_preview.py` + full touptek adapter suite
(72) green; full unit suite 4098 passed, 0 failed, 24 skipped (same one
known flake, confirmed passing in isolation previously). Still not fixed —
waiting on the next log capture.

---

## 2026-07-23 — M10-043 continued: new capture points to "not a bug"

The next capture, with both diagnostics deployed, tells a different story
than the one that opened this investigation: `actual_exp_ms=`/
`actual_gain=` match the requested `exp=`/`gain=` exactly on every line
(2000.0/100, 4000.0/100, 4000.0/400), and zero `SDK call failed` warnings
appear — ruling out the silently-failing-`put_AutoExpoEnable` hypothesis
outright. The frame data isn't frozen either: `mean_adu=1` (a dark-current/
read-noise floor, not the earlier constant `4094`), with `p99_9_adu` going
3 → 4 → 14 as gain steps 100 → 100 → 400 — roughly the 4× scaling a 4× gain
bump should produce on a noise floor. Taken together this looks like a
genuinely dark FOV (no guide star in view) with autogain correctly
climbing to its ceiling looking for signal, not a capture-path bug. Sent
the open question back to the user — was a guide star actually visible
during this capture? — before closing M10-043 as "not a bug."

## 2026-07-23 — Five new bug reports logged (M10-044..048), no fixes yet

User ran a live hardware session (autofocus sequence, camera display,
polar-align) and reported five distinct symptoms in one message. Per
explicit instruction, this pass only records findings in `docs/todo.md` —
no code changes. Two research agents plus direct code reading pinned down
root causes for four of the five; one (frame-count mismatch) still needs
one more piece of evidence from the user.

- **M10-044** — a sequence run (start=-15, end=5500, step=50) reported
  "101 frames" but the code's own formula (and the naive hand calculation)
  both give 111. No clamping path in `start_sequence()` can silently drop
  10 positions from a successful run — formula and code agree with each
  other, just not with what was reported. Left open pending the user
  checking the actual file count in that run's output directory and the
  job's final status/error.
- **M10-045** — live frame display freezes for the whole duration of a
  running autofocus sequence (and by extension, nudge buttons feel
  unresponsive). Root cause: the sequence claims the camera resource via
  `JobManager` for the entire job (unlike the focuser lock, scoped
  per-position since M10-042), so the preview websocket just polls
  "camera busy" the whole time and the frontend silently drops that
  message instead of surfacing it.
- **M10-046** — the Autofocus screen's manual gain field is read for
  single-shot captures but never sent in the `/api/autofocus/sequence`
  request body, even though the backend already accepts and applies
  `gain`. A precisely located, small fix.
- **M10-047** — OAG/main's field-of-view overlay boxes sometimes render on
  the guide camera's tile instead of their own. Not a star-detection bug —
  it's the multicam FOV-box slot assignment (`_mcAssignSlots`)
  re-ranking panels by a computed sky area that depends on
  `pixel_scale_arcsec`, which defaults to 0.0 when an optical train isn't
  fully configured, making the ranking (and therefore which tile is
  "top") unstable.
- **M10-048** — polar-align's star-count gate (`setup_check_service.py`,
  `MIN_STARS_BEFORE_SOLVE=15`) uses a raw full-frame standard deviation
  for its brightness threshold, which rises with gain-dependent sensor
  noise — so at higher gain, real stars that are visible in the
  aggressively-stretched live JPEG fall below the raw-ADU threshold and
  never get counted, reporting 0 stars across all three cameras despite
  visible stars on screen.

Full details, file/line references, and recommended fix directions for
each are in `docs/todo.md`.

---

## 2026-07-24 — M10-045/046/047/048 implemented (M10-044 still open)

Implemented four of the five bugs logged the day before; M10-044 (frame-
count mismatch) still needs the user's file-count/log check before a fix
can even be attempted, so it's untouched.

- **M10-046** (gain ignored) — one-line fix: `afStartSequence()` in
  `static/js/autofocus.js` now reads `#af-gain` and includes it in the
  `/api/autofocus/sequence` request body.
- **M10-045** (frozen live frame) — `onmessage` now renders the previously
  silently-dropped `camera_busy` message as "Sequence running — live view
  paused"; nudge buttons (`.nudge`) are disabled for a sequence's duration,
  and `afNudge()` also no-ops defensively while a sequence job is running.
  Chose the smaller status-message fix over streaming real per-frame
  previews — nudging during an automated sequence doesn't make sense
  anyway, so the frozen-image confusion was the actual problem to solve.
- **M10-047** (FOV overlay on wrong tile) — `_mcAssignSlots()` in
  `static/js/multicam.js` now assigns tile slots by a fixed role order
  (`main` → `guide` → `oag`) instead of dynamically re-sorting by computed
  FOV area, so the overlay's reference tile (`'top'`) no longer depends on
  `pixel_scale_arcsec` being configured correctly. `pixel_scale_arcsec`
  itself still needs verifying in the Pi's config for the FOV boxes to be
  meaningful — this fix only stops the *slot* from moving.
- **M10-048** (polar-align 0 stars) — `_analyse_frame()` in
  `services/setup_check_service.py` now estimates noise via MAD (median
  absolute deviation × 1.4826) instead of raw `np.std()`. Full TDD cycle:
  wrote `test_analyse_frame_star_not_masked_by_its_own_outlier_inflation`
  (a synthetic 40×50 frame, background sigma=5, 30-pixel 6σ star blob),
  confirmed it failed against the pre-fix code for the right reason (the
  star was genuinely missed — a raw whole-frame std is inflated by the
  very star pixels it's supposed to help detect, pushing the naive
  threshold above the star's own peak even though it's unambiguously
  above the true background noise), then implemented MAD and confirmed
  green (18/18 in `test_camera_diagnostic.py`).

The two multicam/autofocus JS fixes have no JS test harness in this repo
(none exists anywhere in the project) — verified with `node --check` on
both files per established convention, Pi verification pending. Full
Python unit suite run after all four changes.

---

## 2026-07-24 — M10-044 resolved: not a bug

Two more data points closed this out. `ls .../autofocus_sequences/5721e35e/
| wc -l` confirmed 101 real FITS files (not a misread progress number),
and `grep "5721e35e" server.log` showed the job actually completed cleanly
(`status = "done"`, no exception) — ruling out a partial failure, since
the loop only reaches that log line after iterating every element of the
precomputed `positions` list with no early exits. That meant `positions`
genuinely had 101 elements at request time, contradicting the 111 the
formula gives for the reported start/end/step.

The filenames resolved the contradiction directly — they encode the exact
per-frame focuser position (`af-seq_pos-{pos}_{idx:03d}.fits`). idx
`000`→`001` (pos 485→535) and idx `099`→`100` (pos 5435→5485) both confirm
step=50, and 101 frames for idx 0-100. Working backward: first position
485 = `current + start_offset` with the reported `start_offset=-15` means
`current` was actually 500 at request time (not 15 — that number was from
an earlier, unrelated screenshot; the focuser had moved since). Last
position 5485 means the real `end_offset` this job ran with was ≈4985,
not 5500 — exactly accounting for the missing 10 frames (10 × step 50 =
500).

Conclusion: the code's frame-count formula was correct the whole time.
The gap was between the End value actually submitted for job `5721e35e`
and what was recalled when describing the run afterward, not a bug. No
code change made.

---

## 2026-07-24 — M10-043 real root cause found and fixed

The "not a bug" conclusion from the day before didn't survive contact with
the user's confirmation: guide stars were genuinely visible on the guide
camera's own live tile during that capture — not covered, not an empty
FOV. That reopened this as a real bug (consistent with this session's
recurring pattern — the user's skepticism of a quick "not a bug" call has
repeatedly uncovered a real, deeper issue underneath).

Root cause, found by reading `domain/histogram.py::analyze()`: `p99_9 =
np.percentile(normed, 99.9)` is computed over **every pixel in the whole
frame**. For the guide sensor's real resolution (1920×1080 =
2,073,600 px), the 99.9th percentile is roughly the 2,074th-brightest
pixel — a realistic guide star's PSF (tens of pixels, rarely a few
hundred even across several stars) is nowhere near sparse enough to move
that percentile at all. `p99_9` was silently reading background noise
this whole time, exactly matching the observed pattern (scaling with gain
like noise, 3→4→14 as gain rose 100→100→400) while the rendered JPEG (a
different, aggressive auto-stretch) showed the star fine. M10-040's
guiding-mode fix had picked a statistic that structurally cannot see a
sparse point source.

Strikingly, this was invisible to the existing unit tests: the
`_sparse_star_frame()` helper's synthetic frame is 64×64 = 4096 px, where
a 10-pixel star is ~0.24% of the frame — comfortably above the 0.1%
`p99_9` needs. The tests passed correctly at that scale while the real
sensor, over 500× larger, silently broke. A good reminder that a
synthetic test frame's *size* can itself hide a real scaling bug.

Confirmed with the user before implementing, since this changes real
guiding behavior on hardware: added `max_frac` (raw frame maximum,
normalised) to `HistogramStats`, sees a sparse point source at any
resolution. Switched `AutoGainController`'s guiding-mode signal from
`stats.p99_9` to `stats.max_frac`; existing `_GUIDE_LO/_HI/_TARGET`
thresholds stay valid since max is also normalised to [0,1].

TDD: `test_histogram.py` gained two cases proving `max_frac` sees what
`p99_9` misses (confirmed RED — `AttributeError` — before adding the
field). `test_autogain.py` gained
`test_guiding_mode_detects_star_at_realistic_sensor_resolution` using an
actual 1080×1920 synthetic frame; confirmed RED against the pre-fix code
(exposure changed instead of staying in-band, matching the real bug
exactly), confirmed GREEN after. `test_autogain_service.py`'s
`HistogramStats(...)` test helper updated for the new required field
(no behavior change). Full suite: 133 passed across the three affected
test files.

Not touched, flagged as **M10-049**: the sibling one-shot
`AutoGainService` (`domain/autogain_service.py`) has the identical
`p99_9`-for-guiding signal, explicitly documented as "kept in sync
manually" with the module just fixed — almost certainly has the same
blind spot, but has more call sites depending on `p99_9`'s exact
semantics (no-signal classification, final-signal reporting) that
deserve their own review rather than a silently bundled change. Also
flagged, not confirmed: `AutoGainController`'s own DSO-mode sparse-field
early exit relies on the same `p99_9`-sees-sparse-stars assumption and
may have an equivalent gap for DSO frames.

2026-07-24 — M10-049 fixed: `AutoGainService` guiding-mode blind spot

`domain/autogain_service.py`'s one-shot `run_one_shot()` had the identical
`signal = stats.p99_9` guiding-mode bug just fixed in `AutoGainController`
(M10-043) — same whole-frame-percentile blind spot to a sparse guide star
at real sensor resolution, at both the main-loop signal and the
loop-exhausted `signal_final`. Both switched to `stats.max_frac`.
`_GUIDE_LO/_HI/_TARGET/_GUIDE_NO_SIGNAL_THR` left unchanged (still valid
thresholds for either metric). Added
`TestGuidingModeRealisticResolution` to `test_autogain_service.py`
mirroring the M10-043 regression test (1080×1920 frame, 10-pixel star);
confirmed RED against pre-fix code (`EXPOSURE_LIMIT_REACHED` instead of
`OK`), GREEN after. Full `test_autogain_service.py`: 61 passed, no
regressions — existing GUIDING tests use 64×64 frames where 12 star
pixels (~0.29%) already exceed the 0.1% p99_9 needs, so their assertions
were numerically unaffected by the metric swap.

Found a third sibling while fixing this, not yet fixed — flagged as
**M10-050**: `domain/guide_monitor.py`'s `_check_once()` (the
FR-GUIDE-002 periodic guide monitor that runs continuously during a live
guiding session) has the exact same `signal = stats.p99_9` pattern. Not
fixed here because it also surfaces `p99_9` directly on an external API
response (`api/guide_monitor.py`), so the fix isn't just an internal
metric swap — needs its own confirmation before changing.

2026-07-24 — M10-050 fixed: `GuideMonitor` guiding-mode blind spot (third sibling)

`domain/guide_monitor.py`'s `_check_once()` — the FR-GUIDE-002 periodic
monitor that runs continuously during a live guiding session — had the
identical `signal = stats.p99_9` bug already fixed in `AutoGainController`
(M10-043) and `AutoGainService` (M10-049). Switched to `stats.max_frac`.
Since this field was also exposed externally, renamed
`GuideMonitorResult.p99_9` → `max_frac` and
`GuideMonitorStatusResponse.p99_9` → `max_frac` (`api/guide_monitor.py`)
rather than silently repurposing a misleadingly-named field — confirmed
first that `static/js/session.js`'s `_gmUpdateUI` never reads that field,
so the rename has no frontend impact.

Added `test_detects_star_at_realistic_sensor_resolution` to
`test_guide_monitor.py` (1080×1920 frame, 10-pixel star), mirroring the
M10-043/M10-049 regression tests; confirmed RED against pre-fix code
(`ADJUSTED` instead of `GUIDE_GAIN_OK`), GREEN after. Renamed
`test_p99_9_in_result` → `test_max_frac_in_result`. Updated
`test_guide_monitor_api.py`'s `GuideMonitorResult(...)` kwarg. Full
`test_guide_monitor.py` + `test_guide_monitor_api.py`: 44 passed, no
regressions.

This closes the third and (as far as repo-wide `grep p99_9` shows) last
sibling of the M10-043 bug class used as a guiding-decision signal. The
remaining `p99_9` references in the codebase (`histogram.py`,
`api/preview.py`, `static/js/preview.js`, `api/histogram.py`) expose it
as a raw diagnostic stat, not a guiding decision, so they're unaffected.
`AutoGainController`'s own DSO-mode `_SPARSE_P99_9_THR` sparse-field
early-exit remains unconfirmed/untouched, as previously flagged.

2026-07-24 — M10-051 found: autofocus HFD metric never isolates a star, doesn't converge on real data

Checked the autofocus sweep algorithm (`workflow/autofocus.py::run_autofocus()`)
against the real M10-044 hardware sequence (101 FITS frames,
`E:\Bilder\Astro\SmartTScope\autofocus_sequences\5721e35e`, ATR585M,
3840×2160, FOCUSPOS 485→5485) using the exact production
`half_flux_diameter()` call. Root cause confirmed with real data, not
hypothesis: the metric runs on the whole raw sensor frame with no star
isolation, so on a real multi-star field it just tracks frame-wide flux
spread — `corr(HFD, focuser position)=0.99`, `corr(HFD, background
median)=-0.99`, `corr(HFD, bright-pixel count)=0.87` — never forming a
V-curve. `_find_valley()` correctly reports `fitted=False` and falls back
to argmin, landing on the second sample of the whole 5000-step sweep —
not a real focus point.

Checked the SCT-donut concern specifically with a synthetic annular PSF
(34% obstruction, single isolated star): `half_flux_diameter` produced a
clean monotonic V-curve, parabola fit exact (error=0). So donuts are NOT
the problem — the metric itself is fine; it was just never validated
against a real multi-star, real-resolution frame, only against
`test_autofocus.py`'s single-star synthetic 64×64 Gaussian blobs. Same
"unrealistic synthetic test frame masks the bug" pattern as
M10-043/M10-049/M10-050, different mechanism (no star isolation, not a
sparse-source blind spot).

Found while investigating: `domain/collimation/processing/star_detection.py`'s
`detect_star()` already does proper single-star isolation (peak-search,
ROI crop, centroid, radial FWHM) but is only wired into collimation, not
autofocus. Also found `services/autofocus_service.py`'s `AutofocusService`
is entirely dangling — not referenced anywhere outside its own file — and
has the identical whole-frame-HFD issue plus an unpopulated
`number_of_stars_detected` field, but wasn't in the real-data analysis
since it's not on the active path.

Logged as **M10-051**, not fixed — needs a design decision (auto-detect
brightest star vs. reuse click-to-center position vs. require the user
to pre-centre the target) before implementing.

2026-07-24 — M10-051 fixed: multi-star HFD autofocus, plus fixture-realism sweep

Implemented multi_star_hfd() in domain/focus_metric.py per user direction
("algorithm should work on several stars that have been identified"):
repeatedly finds the brightest remaining peak above a MAD background
threshold, isolates it in a 65x65 local crop, measures that crop's HFD,
masks it out, repeats (up to 20 candidates), returns the median across
accepted stars. Wired into run_autofocus() and the live single-frame
readout endpoint (/api/autofocus/frame_metrics).

Found and fixed a real bug during implementation: the "reject oversized
blob" check compared an ROI-local pixel count against a whole-frame-relative
limit (copied from star_detection.py's convention) — wrong scale for any
real sensor frame (never binds) and wrong for small synthetic test frames
(over-rejects legitimate defocused stars). Fixed to be ROI-relative.

Contract change: multi_star_hfd() returns float | None — None when no
candidate survives the star-shape checks, rather than falling back to a
whole-frame measurement. Confirmed on real hardware that an isolated hot
pixel routinely outranks a heavily defocused real star, so a fallback
number would be actively misleading. run_autofocus() now skips None
samples instead of fitting a curve through them.

Real-hardware re-validation on the same 101 M10-044 frames: before,
corr(hfd, position)=0.99 with best-focus landing on the sweep's 2nd
sample; after, the algorithm correctly detects a star in only 5/101
frames (785, 1485, 1635, 2385, 3735) and returns None for the rest —
checked directly that lowering the threshold to 3-4 sigma doesn't recover
more (no genuinely contiguous blob exists in the skipped frames, just
noise). This looks like a real data-quality/SNR limit of that specific
diagnostic sweep (2s exposure across the *entire* -15..+5500 mechanical
range) rather than a residual bug. Pi verification with a brighter star
and a normal (narrower) sweep range is still an open follow-up.

Found the same "unrealistic synthetic test frame" trap in four more
places while fixing this (same pattern as M10-043/M10-049/M10-050, now in
test fixtures): test_autofocus.py's noiseless single-star 64x64 frame,
test_autofocus_sequence.py's and test_focuser.py's pure-noise mock
cameras, and the *shared* tests/conftest.py::make_frame() (used across
many service/observing tests via the camera_mock fixture) — all four
were blank/starless and are now fixed with a real synthetic star.

Also found and fixed a pre-existing, unrelated test bug: test_focuser.py's
TestFocuserAutofocus overrode app.dependency_overrides[deps.get_camera],
but the endpoint resolves its camera via a plain deps.get_preview_camera()
function call, not Depends() — the override never took effect, so these
tests were unknowingly running against the real default MockCamera
(also all-zero) the whole time. Fixed with patch.object(deps,
"get_preview_camera", ...), matching the working pattern already used in
test_autofocus_sequence.py.

Full unit suite green after all fixes (one known pre-existing
order-dependent flake in test_logging.py, confirmed passing in isolation).
