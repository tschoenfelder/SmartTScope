/* ══════════════════════════════════════════════════════════════════════
     Cameras compare screen (M10-019)

     Shows every DETECTED camera live in parallel: the largest field of
     view on top, the other two side by side below. Two scale modes:
       fit     — each frame fills its panel (aspect preserved)
       angular — one shared arcsec-per-screen-pixel across all panels,
                 chosen so the largest FOV just fits its panel; the
                 narrow-field cameras then appear at true relative size.
     Top-right: stepwise mount jog at center rate via /api/mount/nudge
     with keep_tracking_state=true (terrestrial targets must not start
     sidereal tracking just because the user jogs).

     All preview sockets are closed when the user leaves the screen.
══════════════════════════════════════════════════════════════════════ */

let _mcActive     = false;
let _mcScaleMode  = 'fit';        // 'fit' | 'angular'
let _mcSockets    = {};           // role -> WebSocket
let _mcPanels     = {};           // role -> panel state (see _mcBuildPanel)
let _mcMountTimer = null;
let _mcFilterName = null;         // current wheel filter (M10-014 payload)
let _mcCoolingTimer   = null;     // TEC status poll (M10-029)
let _mcCoolingDefault = -10.0;    // config default target (from /api/cooling/status)

async function multicamEnter() {
    if (_mcActive) return;
    _mcActive = true;
    const grid = document.getElementById('multicam-grid');
    for (const p of Object.values(_mcPanels)) p.el.remove();
    _mcPanels = {};

    const statusEl = document.getElementById('mc-status');
    let cams = null;
    try {
      const state = await (await fetch('/api/observing/state')).json();
      cams = state.cameras;
    } catch (e) {
      statusEl.textContent = 'Could not load camera state: ' + (e.message || e);
    }
    if (!_mcActive) return;   // user left the screen while fetching

    const detected = [];
    if (cams && cams.roles) {
      for (const [role, cam] of Object.entries(cams.roles)) {
        if (cam.status === 'DETECTED') detected.push([role, cam]);
      }
    }
    _mcFilterName = (cams && cams.filter_wheel && cams.filter_wheel.filter_name) || null;

    statusEl.textContent = detected.length
      ? ''
      : 'No cameras detected — check the camera list on the Observe screen.';

    const slots = ['top', 'b1', 'b2'];
    detected.forEach(([role, cam], i) => _mcBuildPanel(grid, role, cam, slots[i] || 'b2'));
    detected.forEach(([role]) => _mcOpenSocket(role));
    _mcStartMountPoll();
    _mcStartCoolingPoll();
    _mcScheduleRepaint();
}

function multicamLeave() {
    if (!_mcActive) return;
    _mcActive = false;
    for (const ws of Object.values(_mcSockets)) { try { ws.close(); } catch {} }
    _mcSockets = {};
    if (_mcMountTimer) { clearInterval(_mcMountTimer); _mcMountTimer = null; }
    // Cooling itself deliberately keeps running on leave — it is hardware
    // state like tracking, not a per-view resource like the preview sockets.
    if (_mcCoolingTimer) { clearInterval(_mcCoolingTimer); _mcCoolingTimer = null; }
    for (const p of Object.values(_mcPanels)) {
      if (p.bitmap) { try { p.bitmap.close(); } catch {} p.bitmap = null; }
    }
}
window.addEventListener('beforeunload', () => multicamLeave());

/* ── panels ─────────────────────────────────────────────────────────── */

function _mcBuildPanel(grid, role, cam, slot) {
    const el = document.createElement('div');
    el.className = 'mc-panel';
    el.dataset.slot = slot;

    const head   = document.createElement('div');
    head.className = 'mc-head';
    const roleEl = document.createElement('span');
    roleEl.className = 'mc-role';
    roleEl.textContent = role;
    const nameEl = document.createElement('span');
    nameEl.textContent = cam.display_name || '';
    const fovEl  = document.createElement('span');
    const infoEl = document.createElement('span');
    head.append(roleEl, nameEl, fovEl, infoEl);

    // M10-029: TEC cooling toggle — only on cameras whose hardware reports a
    // TEC (readiness `has_tec` from the enumeration flags; ATR585M here).
    let tecBtn = null, tecEl = null;
    if (cam.has_tec) {
      tecBtn = document.createElement('button');
      tecBtn.className = 'mc-tec-btn';
      tecBtn.textContent = '❄';
      tecBtn.title = `Cool to ${_mcCoolingDefault} °C`;
      tecBtn.onclick = () => _mcToggleCooling(role);
      tecEl = document.createElement('span');
      tecEl.className = 'mc-tec-status';
      head.append(tecBtn, tecEl);
    }

    const wrap   = document.createElement('div');
    wrap.className = 'mc-canvas-wrap';
    const canvas = document.createElement('canvas');
    canvas.className = 'mc-canvas';
    wrap.appendChild(canvas);
    el.append(head, wrap);
    grid.insertBefore(el, document.getElementById('mc-jog'));

    const optical = cam.optical || {};
    _mcPanels[role] = {
      el, canvas, ctx: canvas.getContext('2d'), nameEl, fovEl, infoEl,
      bitmap: null,
      jpegW: 0, jpegH: 0,
      // Colour previews are debayered at half resolution — each JPEG pixel
      // then covers 2 sensor pixels (set from the camera_info message).
      colorFactor: 1,
      scaleArcsec: +optical.pixel_scale_arcsec || 0,
      hasWheel: !!optical.filter_wheel,
      sdkIndex: cam.sdk_index,
      hasTec: !!cam.has_tec,
      tecBtn, tecEl,
      cooling: false,
      dirty: false,
    };
    if (_mcPanels[role].hasWheel && _mcFilterName) {
      nameEl.textContent += ' · ' + _mcFilterName;
    }
}

/* ── streaming ──────────────────────────────────────────────────────── */

function _mcOpenSocket(role) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws = new WebSocket(
      `${proto}://${location.host}/ws/preview?camera_role=${encodeURIComponent(role)}&autogain=true`);
    ws.binaryType = 'blob';
    _mcSockets[role] = ws;
    const p = _mcPanels[role];

    ws.onmessage = async (ev) => {
      if (typeof ev.data === 'string') {
        let msg = null;
        try { msg = JSON.parse(ev.data); } catch {}
        if (!msg) {
          if (ev.data.startsWith('camera_error') || ev.data.startsWith('capture_error')) {
            p.infoEl.textContent = ev.data;
          }
          return;
        }
        if (msg.type === 'camera_info') {
          p.colorFactor = msg.is_color ? 2 : 1;
          if (msg.name && !p.nameEl.textContent) p.nameEl.textContent = msg.name;
        } else if (msg.type === 'autogain') {
          p.infoEl.textContent = `${(+msg.exposure).toFixed(2)} s · gain ${msg.gain}`;
        } else if (msg.type === 'camera_busy') {
          p.infoEl.textContent = 'camera busy (background job)…';
        }
        return;
      }
      try {
        const bmp = await createImageBitmap(ev.data);
        if (!_mcActive) { bmp.close(); return; }
        if (p.bitmap) p.bitmap.close();
        p.bitmap = bmp;
        if (p.jpegW !== bmp.width || p.jpegH !== bmp.height) {
          p.jpegW = bmp.width;
          p.jpegH = bmp.height;
          _mcUpdateFovLabels();
          _mcAssignSlots();
        }
        p.dirty = true;
      } catch {}
    };
    ws.onclose = () => {
      if (_mcActive && _mcSockets[role] === ws && !p.infoEl.textContent) {
        p.infoEl.textContent = 'stream closed';
      }
    };
}

/* ── FOV math & panel ordering ──────────────────────────────────────── */

function _mcFov(p) {
    if (!p.jpegW || !p.scaleArcsec) return null;
    const sensorW = p.jpegW * p.colorFactor;
    const sensorH = p.jpegH * p.colorFactor;
    return {
      sensorW, sensorH,
      wArcsec: sensorW * p.scaleArcsec,
      hArcsec: sensorH * p.scaleArcsec,
    };
}

function _mcFmtAngle(arcsec) {
    if (arcsec >= 3600) return (arcsec / 3600).toFixed(2) + '°';
    if (arcsec >= 60)   return (arcsec / 60).toFixed(1) + '′';
    return arcsec.toFixed(0) + '″';
}

function _mcUpdateFovLabels() {
    for (const p of Object.values(_mcPanels)) {
      const f = _mcFov(p);
      p.fovEl.textContent = f
        ? `${f.sensorW}×${f.sensorH} px · ${_mcFmtAngle(f.wArcsec)} × ${_mcFmtAngle(f.hArcsec)}`
        : (p.jpegW ? `${p.jpegW}×${p.jpegH} px` : '');
    }
}

function _mcAssignSlots() {
    const entries = Object.values(_mcPanels);
    entries.sort((a, b) => {
      const fa = _mcFov(a), fb = _mcFov(b);
      return (fb ? fb.wArcsec * fb.hArcsec : 0) - (fa ? fa.wArcsec * fa.hArcsec : 0);
    });
    const slots = ['top', 'b1', 'b2'];
    entries.forEach((p, i) => {
      p.el.dataset.slot = slots[i] || 'b2';
      p.dirty = true;
    });
}

/* ── painting ───────────────────────────────────────────────────────── */

function _mcScheduleRepaint() {
    if (!_mcActive) return;
    requestAnimationFrame(() => { _mcPaintAll(); _mcScheduleRepaint(); });
}

function _mcPaintAll() {
    let sharedScale = 0;   // arcsec per CSS pixel (angular mode)
    if (_mcScaleMode === 'angular') {
      for (const p of Object.values(_mcPanels)) {
        if (p.el.dataset.slot !== 'top') continue;
        const f = _mcFov(p);
        const w = p.canvas.clientWidth, h = p.canvas.clientHeight;
        if (f && w && h) sharedScale = Math.max(f.wArcsec / w, f.hArcsec / h);
      }
    }
    for (const p of Object.values(_mcPanels)) _mcPaint(p, sharedScale);
}

function _mcPaint(p, sharedScale) {
    const cssW = p.canvas.clientWidth, cssH = p.canvas.clientHeight;
    if (!cssW || !cssH) return;
    const dpr = window.devicePixelRatio || 1;
    const bw = Math.round(cssW * dpr), bh = Math.round(cssH * dpr);
    if (p.canvas.width !== bw || p.canvas.height !== bh) {
      p.canvas.width = bw;
      p.canvas.height = bh;
      p.dirty = true;
    }
    if (!p.dirty) return;
    p.dirty = false;
    const ctx = p.ctx;
    ctx.fillStyle = '#000';
    ctx.fillRect(0, 0, bw, bh);
    if (!p.bitmap) return;
    let drawW, drawH;
    const f = _mcFov(p);
    if (_mcScaleMode === 'angular' && sharedScale > 0 && f) {
      drawW = f.wArcsec / sharedScale * dpr;
      drawH = f.hArcsec / sharedScale * dpr;
    } else {
      const fit = Math.min(bw / p.bitmap.width, bh / p.bitmap.height);
      drawW = p.bitmap.width * fit;
      drawH = p.bitmap.height * fit;
    }
    const offsetX = (bw - drawW) / 2, offsetY = (bh - drawH) / 2;
    ctx.drawImage(p.bitmap, offsetX, offsetY, drawW, drawH);
    // M10-020 (cheap approximation): overlay where each narrower-FOV camera's
    // frame falls within this (widest-FOV) panel. Only meaningful in angular
    // mode, where every panel shares the same arcsec-per-pixel scale — fit
    // mode scales each panel independently, so there is no common reference.
    if (p.el.dataset.slot === 'top' && _mcScaleMode === 'angular' && sharedScale > 0) {
      _mcPaintFovOverlays(ctx, sharedScale, dpr, offsetX, offsetY, drawW, drawH);
    }
}

function _mcPaintFovOverlays(ctx, sharedScale, dpr, topOffsetX, topOffsetY, topDrawW, topDrawH) {
    const centerX = topOffsetX + topDrawW / 2;
    const centerY = topOffsetY + topDrawH / 2;
    ctx.save();
    ctx.strokeStyle = 'limegreen';
    ctx.fillStyle = 'limegreen';
    ctx.lineWidth = Math.max(1, Math.round(dpr));
    ctx.font = `${Math.round(11 * dpr)}px sans-serif`;
    for (const [role, other] of Object.entries(_mcPanels)) {
      if (other.el.dataset.slot === 'top') continue;
      const f = _mcFov(other);
      if (!f) continue;
      // Co-alignment assumption (no measured offset/rotation between optical
      // trains exists in config) — center each smaller frame on the top
      // panel's own image center.
      const subW = f.wArcsec / sharedScale * dpr;
      const subH = f.hArcsec / sharedScale * dpr;
      const x = centerX - subW / 2, y = centerY - subH / 2;
      ctx.strokeRect(x, y, subW, subH);
      ctx.fillText(role, x + 3 * dpr, y + 12 * dpr);
    }
    ctx.restore();
}

function multicamToggleScale() {
    _mcScaleMode = _mcScaleMode === 'fit' ? 'angular' : 'fit';
    document.getElementById('mc-scale-btn').textContent =
      _mcScaleMode === 'fit' ? 'Scale: fit each panel' : 'Scale: same sky scale';
    for (const p of Object.values(_mcPanels)) p.dirty = true;
}

/* ── mount jog ──────────────────────────────────────────────────────── */

async function multicamJog(dir) {
    const dur  = parseInt(document.getElementById('mc-jog-dur').value) || 500;
    const note = document.getElementById('mc-jog-note');
    try {
      await apiPost('/api/mount/nudge',
        { direction: dir, duration_ms: dur, keep_tracking_state: true });
      note.textContent = '';
    } catch (e) {
      note.textContent = e.message || String(e);
    }
}

function multicamStop() {
    if (typeof mountEmergencyStop === 'function') mountEmergencyStop();
}

// M10-031: step sizes above this are a manual/terrestrial jog only (mirrors
// the server's _NUDGE_TRACKING_MAX_MS in api/mount.py) — while the mount is
// actively tracking, a centering correction stays capped tight so a step
// can't drag a framed target far off target.
const _MC_TRACKING_MAX_JOG_MS = 5000;

function _mcStartMountPoll() {
    if (_mcMountTimer) return;
    const durSel = document.getElementById('mc-jog-dur');
    const poll = async () => {
      let state = 'unknown';
      let tracking = false;
      try {
        const data = await (await fetch('/api/mount/status')).json();
        state = data.state || 'unknown';
        tracking = data.tracking_state === 'TRACKING';
      } catch {}
      const parked = state === 'parked';
      for (const btn of document.querySelectorAll('#mc-jog .mc-jog-btn')) {
        btn.disabled = parked;
      }
      if (parked) {
        document.getElementById('mc-jog-note').textContent = 'Mount is parked — unpark to jog.';
      }
      if (durSel) {
        for (const opt of durSel.options) {
          opt.disabled = tracking && parseInt(opt.value) > _MC_TRACKING_MAX_JOG_MS;
        }
        if (tracking && parseInt(durSel.value) > _MC_TRACKING_MAX_JOG_MS) {
          durSel.value = String(_MC_TRACKING_MAX_JOG_MS);
        }
      }
    };
    poll();
    _mcMountTimer = setInterval(poll, 5000);
}

/* ── TEC cooling (M10-029) ──────────────────────────────────────────────
     One shared CoolingService session backend-side; the ❄ toggle appears
     only on panels whose camera reports a TEC. The poll re-derives an
     already-running session on view enter (cooling survives view leave). */

async function _mcToggleCooling(role) {
    const p = _mcPanels[role];
    if (!p || !p.hasTec) return;
    const enable = !p.cooling;
    try {
      await apiPost('/api/cooling/set_target', {
        camera_index: p.sdkIndex, target_c: _mcCoolingDefault, enabled: enable,
      });
      p.infoEl.textContent = '';
    } catch (e) {
      p.infoEl.textContent = e.message || String(e);
    }
    _mcPollCooling();
}

async function _mcPollCooling() {
    if (!Object.values(_mcPanels).some(p => p.hasTec)) return;
    let d = null;
    try { d = await (await fetch('/api/cooling/status')).json(); } catch { return; }
    if (!_mcActive) return;
    if (typeof d.default_target_c === 'number') _mcCoolingDefault = d.default_target_c;
    for (const p of Object.values(_mcPanels)) {
      if (!p.hasTec) continue;
      const active = !!d.enabled && d.camera_index === p.sdkIndex;
      p.cooling = active;
      p.tecBtn.classList.toggle('active', active);
      p.tecBtn.title = active
        ? 'Cooling active — click to switch off'
        : `Cool to ${_mcCoolingDefault} °C`;
      if (active) {
        const cur = d.current_temp_c != null ? `${d.current_temp_c.toFixed(1)}°` : '—';
        const pow = d.power_pct != null ? ` (${d.power_pct.toFixed(0)}%)` : '';
        p.tecEl.textContent = `${cur} → ${d.target_c}°${pow}`;
      } else {
        p.tecEl.textContent = '';
      }
    }
}

function _mcStartCoolingPoll() {
    if (_mcCoolingTimer) return;
    if (!Object.values(_mcPanels).some(p => p.hasTec)) return;
    _mcPollCooling();
    _mcCoolingTimer = setInterval(_mcPollCooling, 10_000);
}
