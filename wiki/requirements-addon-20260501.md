# Requirements Addon — 2026-05-01

**Summary**: Requirements and bug reports captured from the first real hardware test session on 2026-05-01 (Raspberry Pi 5 + OnStep V4 + ToupTek camera).

**Sources**: resources/hlrequirements/requirements_addon_20260501.txt

**Last updated**: 2026-05-02

---

## Hardware test session — 2026-05-01

First live test with real hardware (Pi 5 + OnStep V4 + ToupTek camera). Three bugs were observed in the server log and subsequently fixed.

### Bug 1 — `POST /api/mount/disable_tracking` → HTTP 500

```
POST /api/mount/disable_tracking HTTP/1.1  500 Internal Server Error
```

**Root cause**: `OnStepMount` had no threading lock. Concurrent HTTP requests (e.g. a UI poll alongside a mount action) could interleave bytes on the shared pyserial port, corrupting both the write and the following `readline()`. The resulting garbled response caused an unhandled exception in the endpoint.

**Fix** (Sprint 37 bugfix): Added `threading.Lock` (`self._lock`) to `OnStepMount`. `_raw_send()` acquires the lock for every write/readline pair. See [[onstep-protocol]] adapter notes.

### Bug 2 — Camera WebSocket silently closes after `connection open`

```
WebSocket /ws/preview?...camera_index=0  [accepted]
connection open
connection closed
```

**Root cause**: In `deps.get_preview_camera()`, if `cam.connect()` returned `False` for a secondary camera, the disconnected `ToupcamCamera` instance was cached and returned. Subsequent calls to `cam.capture()` raised `RuntimeError("Camera not connected")`, which was silently caught by the WebSocket handler's `except RuntimeError: pass` clause — causing the connection to drop without any client-visible error.

**Fix**: `get_preview_camera()` now raises `RuntimeError` (and does not cache) if `cam.connect()` returns `False`. `ws_preview` accepts the WebSocket first, then catches the error and sends close code 1011 with the reason string.

### Bug 3 — Only one camera connects (root cause same as Bug 2)

The same caching bug meant that a secondary camera index would permanently fail silently once a failed connection was cached. Fixed by the same change.

---

## New requirements from this session

### Mount field — position display

Current RA/DEC must be visible in the mount status area. **Status**: implemented — the mount card (Stage 1) and the compact mount strip (stages 2–5) both display live RA/DEC. The strip now polls `/api/mount/status` every 5 s while on stages 2–5 (Sprint 37).

### Mount field — Home and Park buttons

**Home**: slew to celestial pole (Dec 89°, HA 0) as a safe starting position. **Park**: slew to the configured park position. **Status**: both buttons exist in the Stage 1 mount card and the Stage 2 polar alignment card.

### Mount field — step-based movement (safety requirement)

> "move mount via OnStep by specifying steps only, not by 'move and I will say stop', as on a SmartTScope issue the mount may never get a stop command and become a mad mount."

Manual nudge movements must use timed pulse-guide commands (`:Mgdnnnn#`) with a fixed millisecond count, not the continuous move-start/move-stop pattern (`:Me#` / `:Qe#`). This applies to:
- Guide pad in Stage 3 (star centering) — **already uses pulse guide**
- Guide pad in Stage 4 (collimation/focus centering) — **already uses pulse guide**
- Any future manual-slew UI control

**Status**: guide pads in Stages 3 and 4 already use `:Mgdnnnn#`. The `:Me#`/`:Mw#`/`:Mn#`/`:Ms#` continuous-move commands are in the protocol table but must **not** be used in new UI controls.

### Mount field — limits configuration

> "add mount config for maximum mount positions: not directly up, not below horizon, not moving hour angle 360° around, don't get counterweight more than 5° above telescope, respect limits when moving mount."

Mount limit enforcement is already implemented in `_check_mount_limits()` (API layer, `mount.py`), enforced on every GoTo. The UI should expose the current limit values. **Status**: `GET /api/mount/config` returns the limit values (alt min/max, HA east/west limits); a settings display card in Stage 1 is a **pending UI item**.

### Custom targets — GoTo Selected button

A section-level GoTo button in the Custom Targets card should act on the currently selected (highlighted) row. **Status**: implemented in Sprint 37 — GoTo and ⌖ header buttons, row highlight with `.selected` CSS.

---

## Related pages

- [[requirements]]
- [[onstep-protocol]]
- [[requirements-addon-20260430]]
- [[touptek-sdk]]
