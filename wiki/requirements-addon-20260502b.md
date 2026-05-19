# Requirements Addon 2026-05-02b

**Summary**: Two new requirements from the second addon file of 2026-05-02: README update instructions (git pull workflow) and focuser always-expected policy for the C8.

**Sources**: `resources/hlrequirements/requirements_addon_20260502b.txt`

**Last updated**: 2026-05-02

---

## New requirements

### 1. README update instructions

Add a section to the README explaining how to update the git repository to the newest version of the `master` branch.

Implemented: "Keeping up to date" section added to `README.md` covering:
- `git pull origin master` + `pip install -e .` + `sudo systemctl restart smarttscope` for Raspberry Pi
- The `pi_pull_and_test.sh` script as the recommended path
- Manual dev-machine update workflow

### 2. Focuser always expected on C8

The C8 build always has a motorised focuser connected via OnStep.  The focuser has **limits** (a maximum step count) and provides **no position feedback** (no encoder).  The OnStep `:FA#` command signals whether the focuser is active.

**Behaviour on `:FA#` = 0 (focuser not found)**:

- Autofocus is shown as **disabled** — the focuser card in Stage 4 displays a "Not found" banner.
- All other operations continue normally — no hard error, no blocked stages.
- Stage 1 "Connect All" probes the focuser via `POST /api/focuser/connect` and shows the status (green = active, yellow = not found) in a dedicated focuser row.

**Position / limit commands**:

| Command | Purpose |
|---|---|
| `:FA#` | Focuser active? (1 = yes) |
| `:FG#` | Get current position (steps) |
| `:FM#` | Get maximum position (steps) — used as the upper clamp for move/nudge |

The maximum position is fetched once during `connect()` and cached as `_max_position`. All `move` and `nudge` calls are clamped to `[0, max_position]`.

## Implementation notes

- `FocuserPort` gained `get_max_position() -> int` and `is_available: bool` (abstract property).
- `OnStepFocuser` was refactored to **delegate serial I/O to `OnStepMount`** — it holds no serial handle of its own. This eliminates the two-serial-handle conflict discovered during hardware testing.
- `connect()` on `OnStepFocuser` always returns `True`; `is_available` reflects the `:FA#` reply.
- `MockFocuser` and `SimulatorFocuser` both implement `is_available = True` and `get_max_position() = 5000`.
- `GET /api/focuser/status` now includes `available: bool` and `max_position: int | None`.
- `POST /api/focuser/connect` (new endpoint) probes the focuser and returns `{ok, available}`.
- `GET /api/status` (`health.py`) reports focuser `ok=False` with message "autofocus disabled" when `is_available` is False.

## Related pages

- [[requirements]]
- [[autofocus]]
- [[onstep-protocol]]
- [[hardware-platform]]
