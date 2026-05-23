# Collimation Wizard — Guiding Integration Design

## Goal

Integrate `GuidingService` into the collimation wizard so that the bright star stays centred in the C8 main camera FOV throughout long rough and fine collimation phases. The guide scope (GPCMOS02000KPA) provides continuous drift correction; `PulseCenterer` handles reactive recentering after each screw adjustment and tells the guiding service to adopt the new position as its reference baseline.

## Architecture

```
CollimationAssistant
  │
  ├─ owns ──► GuidingService (guide camera)
  │               pause_pulses() / resume_pulses()
  │               rebaseline()
  │               stop()
  │
  ├─ uses ──► PulseCenterer (main camera — recenters after screw turn)
  │
  └─ reports via ──► /api/collimation/status
                         { ..., "guiding": { available, state, rms_px, last_pulse } }
```

`CollimationAssistant` owns the full `GuidingService` lifecycle. No other code starts or stops it during a collimation session.

## Wizard Lifecycle vs Guiding State

| Wizard phase | GuidingService action |
|---|---|
| START → AUTO_EXPOSURE | Not running |
| AUTO_EXPOSURE exits → ROUGH_DEFOCUS | `start()` with guide camera, exposure, cadence, and mount |
| Remeasure / auto-recenter (rough or fine) | `pause_pulses()` → PulseCenterer → `rebaseline()` → `resume_pulses()` |
| PAUSED | Guiding keeps running — mount must keep tracking |
| COMPLETE, CANCEL, or FAILED | `stop()` |

Coordination during recentering is needed because both `GuidingService` and `PulseCenterer` send pulses to the same mount. While `PulseCenterer` is active, guiding pulses are suppressed. After `PulseCenterer` finishes, `rebaseline()` tells the guide loop that wherever the guide star currently is is the new zero-point, preventing a large correction burst.

## Fallback: No Guide Camera

If `guiding_service` is `None` (guide camera role not configured or connection failed), all guiding calls in the assistant are no-ops. The wizard starts normally. The guide status row shows "Guiding: unavailable." No wizard phases are blocked.

## Component Changes

### 1. `GuidingService` — new methods

**`pause_pulses()` / `resume_pulses()`**

A `_pulses_paused: bool` flag under `_status_lock`. The `_loop()` checks this flag before calling `mount.guide()`. When paused, the measurement loop continues (guide star remains tracked); pulse corrections are suppressed.

**`rebaseline()`**

Sets a `threading.Event` (`_rebaseline_requested`). On the next loop iteration where a good measurement arrives, the loop sets `target = measurement.centroid_px` and clears the event. This zeroes the error reference without stopping the loop.

**`GuidingStatus` additions**

Two new fields:
- `rms_px: float` — rolling RMS of correction magnitudes over the last 10 frames (0.0 when fewer than 2 frames available)
- `last_pulse: tuple[str, int] | None` — direction string (e.g. `"ra+"`) and milliseconds of the most recently issued pulse; `None` if no pulse has been issued or guiding is idle

Both fields are included in `status().to_dict()`.

### 2. `CollimationConfig` — new fields

Three new optional fields in `CollimationConfig` (loaded from `[collimation]` TOML section):

```toml
[collimation]
guiding_camera_role = "guide"   # must match a key in [cameras.*]
guiding_exposure_s  = 2.0
guiding_cadence_s   = 3.0
```

Defaults: `guiding_camera_role = "guide"`, `guiding_exposure_s = 2.0`, `guiding_cadence_s = 3.0`. If the named camera role is not present in the runtime camera map, guiding is silently skipped.

### 3. `CollimationAssistant` — lifecycle and coordination

**Constructor**

```python
def __init__(
    self,
    ...,
    guiding_service: Optional[GuidingService] = None,
    guide_cameras: dict[str, CameraPort] | None = None,
):
    self._guiding_service = guiding_service
    self._guide_cameras = guide_cameras or {}
```

**`_start_guiding()`** (private helper)

Called at the end of `_handle_auto_exposure()`. If `_guiding_service` is `None` or `_guide_cameras` is empty, returns immediately. Otherwise:

```python
self._guiding_service.start(
    self._guide_cameras,
    exposure_s=self._config.guiding_exposure_s,
    cadence_s=self._config.guiding_cadence_s,
    mount=self._mount,
)
```

**`_stop_guiding()`** (private helper)

Called in `_teardown()` (which runs on complete, cancel, and failed). If `_guiding_service` is not `None` and its state is `"running"`, calls `_guiding_service.stop()`.

**`_with_guiding_paused(fn)`** (private helper)

Wraps a callable with pause/rebaseline/resume:

```python
def _with_guiding_paused(self, fn: Callable) -> Any:
    if self._guiding_service is not None:
        self._guiding_service.pause_pulses()
    try:
        return fn()
    finally:
        if self._guiding_service is not None:
            self._guiding_service.rebaseline()
            self._guiding_service.resume_pulses()
```

Used in `_handle_guide_rough_collimation()` and `_handle_guide_fine_collimation()` around every `PulseCenterer.center()` call.

**`_guiding_status_dict()`** (private helper)

```python
def _guiding_status_dict(self) -> dict:
    if self._guiding_service is None:
        return {"available": False}
    s = self._guiding_service.status()
    return {
        "available": True,
        "state": s.state,
        "rms_px": s.rms_px,
        "last_pulse": list(s.last_pulse) if s.last_pulse else None,
    }
```

Merged into the existing `status()` dict under key `"guiding"`.

### 4. `runtime.py` — wiring

`runtime.py` creates `GuidingService` for the collimation assistant separately from any user-facing guiding session. At the point where `CollimationAssistant` is constructed:

```python
_collim_guiding_svc = GuidingService.from_config(
    primary_role=cfg.collimation.guiding_camera_role,
    allow_fallback=False,
    ...
)
_collim_assistant = CollimationAssistant(
    ...,
    guiding_service=_collim_guiding_svc,
    guide_cameras=_role_cameras,   # dict of role → CameraPort from existing camera map
)
```

If the guide camera role is absent from the camera map, `_collim_guiding_svc` is `None` and `_role_cameras` is `{}`.

### 5. `api/collimation.py` — no changes

The `"guiding"` key flows through `assistant.status()` automatically. No router changes needed.

### 6. `static/index.html` — guide status row

One new `<div>` inside the wizard card, between the instruction div and the recommendation block:

```html
<div id="s4-wiz-guide-row"
     style="display:none;font-size:0.82rem;color:var(--muted);
            margin-bottom:0.5rem;align-items:center;gap:0.4rem">
  <span class="dot dot-grey" id="s4-wiz-guide-dot"></span>
  <span id="s4-wiz-guide-label">Guide: —</span>
</div>
```

### 7. `static/js/collimation.js` — render guide row

Added to `_updateCollimWizard(s)`:

```javascript
const g = s.guiding;
const guideRow = document.getElementById('s4-wiz-guide-row');
if (guideRow) {
    if (!g || !g.available) {
        guideRow.style.display = 'none';
    } else {
        guideRow.style.display = 'flex';
        const dot    = document.getElementById('s4-wiz-guide-dot');
        const lbl    = document.getElementById('s4-wiz-guide-label');
        const locked = g.state === 'running';
        if (dot) dot.className = 'dot ' + (locked ? 'dot-green' : 'dot-red');
        const rms  = locked && g.rms_px != null
            ? `  RMS ${g.rms_px.toFixed(1)} px` : '';
        const last = g.last_pulse
            ? `  last ${g.last_pulse[1] > 0 ? '+' : ''}${g.last_pulse[1]}ms ${g.last_pulse[0]}`
            : '';
        if (lbl) lbl.textContent =
            `Guide: ${locked ? 'locked' : 'lost'}${rms}${last}`;
    }
}
```

The guide row is hidden (`g.available = false`) during phases before `ROUGH_DEFOCUS` because `_guiding_status_dict()` returns `available: false` until `_start_guiding()` has been called.

## Testing

**`tests/unit/services/test_guiding_service.py`** — new tests:
- `test_pause_pulses_suppresses_mount_calls` — mock mount, pause, verify `guide()` not called
- `test_resume_pulses_restores_mount_calls` — pause then resume, verify `guide()` called again
- `test_rebaseline_resets_target` — verify next good frame becomes new zero-point (error drops to ~0 on next iteration after rebaseline)

**`tests/unit/services/collimation/test_collimation_guiding.py`** — new file:
- `test_guiding_starts_after_auto_exposure` — mock assistant pipeline, verify `guiding_service.start()` called on AUTO_EXPOSURE exit
- `test_guiding_not_started_during_acquisition` — verify `start()` not called during CENTER_STAR
- `test_recenter_pauses_and_rebaselines_guiding` — mock PulseCenterer, verify pause → center → rebaseline → resume order
- `test_guiding_stops_on_cancel` — verify `guiding_service.stop()` called when wizard is cancelled
- `test_guiding_stops_on_complete` — verify `guiding_service.stop()` called on COMPLETE
- `test_no_guiding_service_does_not_crash` — run assistant with `guiding_service=None`, verify no exceptions
- `test_status_includes_guiding_dict` — verify `status()["guiding"]` present and has expected keys

## File Summary

| File | Change |
|---|---|
| `smart_telescope/services/guiding_service.py` | `pause_pulses`, `resume_pulses`, `rebaseline`, `rms_px`/`last_pulse` in status |
| `smart_telescope/domain/collimation/config.py` | 3 new guiding config fields with defaults |
| `smart_telescope/services/collimation/assistant.py` | Inject guiding service, lifecycle hooks, `_with_guiding_paused` helper |
| `smart_telescope/runtime.py` | Construct guiding service + pass to assistant |
| `smart_telescope/static/index.html` | Guide status row in wizard card |
| `smart_telescope/static/js/collimation.js` | Render guide row in `_updateCollimWizard` |
| `tests/unit/services/test_guiding_service.py` | 3 new tests |
| `tests/unit/services/collimation/test_collimation_guiding.py` | New file, 7 tests |
