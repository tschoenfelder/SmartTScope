# Wiki Log

Append-only record of all wiki operations.

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
