function focuserCard(data) {
    if (!data.available) {
      const required = data.required ?? false;
      return `
      <div class="card"${required ? ' style="border-color:var(--error)"' : ''}>
        <div class="card-title">
          <span class="dot ${required ? 'dot-red' : 'dot-yellow'}"></span>
          OnStep Focuser
          <span class="state-badge ${required ? 'state-error' : 'state-parked'}">Not found</span>
        </div>
        <p style="font-size:0.82rem;color:${required ? 'var(--error)' : 'var(--muted)'};margin:0.5rem 0 0">
          ${required
            ? 'Focuser not detected on the OnStep controller (:FA# = 0). Check focuser wiring and OnStep focuser configuration.'
            : 'No focuser detected on the OnStep controller (:FA# = 0). Autofocus is disabled — all other operations continue normally.'}${NL}        </p>
      </div>`;
    }
    const pos    = data.position ?? '—';
    const maxPos = data.max_position != null ? ` / ${data.max_position}` : '';
    const moving = data.moving ?? false;
    const dotCls = moving ? 'dot-yellow' : 'dot-green';
    const label  = moving ? 'Moving…' : 'Stopped';
    return `
      <div class="card">
        <div class="card-title">
          <span class="dot ${dotCls}" id="s4-focuser-dot"></span>
          OnStep Focuser
          <span class="state-badge ${moving ? 'state-slewing' : 'state-tracking'}"
                id="s4-focuser-badge">${label}</span>
        </div>
        <div class="params">
          <div class="param">
            <span class="param-label">Position (steps)</span>
            <span class="param-value mono" id="s4-focuser-pos">${pos}${maxPos}</span>
          </div>
        </div>
        <div class="controls">
          <span class="adv-only" style="display:flex;gap:0.5rem;flex-wrap:wrap;align-items:center;flex:1">
            <div class="nudge-group">
              <button class="secondary nudge" onclick="nudge(-1000)">−1000</button>
              <button class="secondary nudge" onclick="nudge(-100)">−100</button>
              <button class="secondary nudge" onclick="nudge(-10)">−10</button>
              <button class="secondary nudge" onclick="nudge(10)">+10</button>
              <button class="secondary nudge" onclick="nudge(100)">+100</button>
              <button class="secondary nudge" onclick="nudge(1000)">+1000</button>
            </div>
            <span class="controls-spacer"></span>
          </span>
          <button class="danger" onclick="focuserStop()">Stop</button>
        </div>
        <div class="input-row adv-only">
          <label>Move to</label>
          <input type="number" id="focuser-target" step="1" placeholder="steps" style="width:10ch">
          <button onclick="focuserMoveTo()">Move</button>
        </div>
        <div class="input-row"
             style="margin-top:0.75rem;padding-top:0.75rem;border-top:1px solid var(--border)">
          <label>Range ±</label>
          <input type="number" id="af-range" value="1000" min="100" max="10000" step="100"
                 style="width:7ch">
          <label>Step</label>
          <input type="number" id="af-step" value="100" min="10" max="1000" step="10"
                 style="width:6ch">
          <label>Exp</label>
          <input type="number" id="af-exposure" value="2" min="0.1" max="30" step="0.5"
                 style="width:6ch">
          <label>s</label>
          <button id="af-btn" onclick="runAutofocus()" style="margin-left:0.25rem">Autofocus</button>
        </div>
        <div id="af-result"
             style="font-size:0.8rem;color:var(--muted);margin-top:0.5rem;display:none"></div>
      </div>`;
}

async function loadFocuserCameras() {
    const sel = document.getElementById('s1-focuser-cam-select');
    if (!sel) return;
    try {
      const trains = await (await fetch('/api/optical_trains')).json();
      _opticalTrains = trains;
      const withFocuser = trains.filter(t => t.has_focuser);
      if (withFocuser.length === 0) {
        sel.innerHTML = '<option value="" disabled>No focuser configured</option>';
        return;
      }
      sel.innerHTML = withFocuser.map(t =>
        `<option value="${escHtml(t.name)}">${escHtml(t.name + ' — ' + t.telescope)}</option>`
      ).join('');
      const mainOpt = sel.querySelector('option[value="main"]');
      if (mainOpt) sel.value = 'main';
      _focusCamRole = sel.value;
      // Single-focuser setup: hide the dropdown and show as plain text — no choice to make.
      const row = document.getElementById('s1-focuser-cam-row');
      if (row) row.style.display = withFocuser.length <= 1 ? 'none' : '';
    } catch (_) {}
}

/* Shared helper: populate any <select> with optical trains from /api/optical_trains.
     Values are train names (strings). An optional filter(train) predicate narrows the list.
     Returns the populated select element (or null) so callers can read .value. */
async function _loadSelectFromTrains(selId, filter) {
    const sel = document.getElementById(selId);
    if (!sel) return null;
    try {
      const trains = await (await fetch('/api/optical_trains')).json();
      _opticalTrains = trains;
      const list = filter ? trains.filter(filter) : trains;
      if (list.length === 0) {
        sel.innerHTML = '<option value="main">main</option>';
        return sel;
      }
      sel.innerHTML = list.map(t =>
        `<option value="${escHtml(t.name)}">${escHtml(t.name + ' — ' + t.telescope)}</option>`
      ).join('');
    } catch (_) {
      sel.innerHTML = '<option value="main">main</option>';
    }
    return sel;
}

/* Resolve an optical train name to its SDK camera index (from the cached train list). */
function _trainCamIdx(trainName) {
    const t = _opticalTrains.find(t => t.name === (trainName || 'main'));
    return t ? t.camera_index : 0;
}

/* Adaptive exposure formatter: avoids pointless trailing zeros */
function fmtExp(s) {
    if (s >= 100)      return String(Math.round(s));
    if (s >= 10)       return parseFloat(s.toFixed(1)).toString();
    if (s >= 1)        return parseFloat(s.toFixed(2)).toString();
    if (s >= 0.1)      return parseFloat(s.toFixed(3)).toString();
    return parseFloat(s.toFixed(4)).toString();
}

/* Update Live Preview controls from camera capabilities (STS-ADDON-008/009) */
async function onPreviewCamChange(role) {
    const wasRunning = _reconnect && _ws !== null;
    if (wasRunning) previewStop();
    const idx = _trainCamIdx(role);
    try {
      const caps = await (await fetch(`/api/cameras/${idx}/capabilities`)).json();
      const expIn  = document.getElementById('preview-exposure');
      const gainIn = document.getElementById('preview-gain');
      if (expIn) {
        const capMax = Math.min(caps.max_exposure_s, 1000);
        expIn.min   = fmtExp(caps.min_exposure_s);
        expIn.max   = fmtExp(capMax);
        expIn.step  = 'any';
        expIn.title = `Exposure range: ${fmtExp(caps.min_exposure_s)}–${fmtExp(capMax)} s`;
        const cur = parseFloat(expIn.value) || 2.0;
        if (cur < caps.min_exposure_s) expIn.value = fmtExp(caps.min_exposure_s);
        if (cur > capMax) expIn.value = fmtExp(capMax);
      }
      if (gainIn) {
        gainIn.min   = caps.min_gain;
        gainIn.max   = caps.max_gain;
        gainIn.title = `Gain range: ${caps.min_gain}–${caps.max_gain}`;
        const curG = parseInt(gainIn.value, 10) || caps.min_gain;
        if (curG < caps.min_gain) gainIn.value = caps.min_gain;
        if (curG > caps.max_gain) gainIn.value = caps.max_gain;
      }
    } catch (_) { /* camera not reachable yet — keep current values */ }
    if (wasRunning) previewStart();
}

/* Update Polar Alignment controls from camera capabilities (STS-ADDON-008/009) */
async function onPaCamChange(role) {
    const idx = _trainCamIdx(role);
    try {
      const caps = await (await fetch(`/api/cameras/${idx}/capabilities`)).json();
      const expIn  = document.getElementById('pa-exposure');
      const gainIn = document.getElementById('pa-gain');
      if (expIn) {
        expIn.min   = fmtExp(caps.min_exposure_s);
        expIn.max   = fmtExp(caps.max_exposure_s);
        expIn.step  = 'any';
        expIn.title = `Exposure range: ${fmtExp(caps.min_exposure_s)}–${fmtExp(caps.max_exposure_s)} s`;
        const cur = parseFloat(expIn.value) || 5.0;
        if (cur < caps.min_exposure_s) expIn.value = fmtExp(caps.min_exposure_s);
        if (cur > caps.max_exposure_s) expIn.value = fmtExp(caps.max_exposure_s);
      }
      if (gainIn) {
        gainIn.min   = caps.min_gain;
        gainIn.max   = caps.max_gain;
        gainIn.title = `Gain range: ${caps.min_gain}–${caps.max_gain}`;
        const curG = parseInt(gainIn.value, 10) || caps.min_gain;
        if (curG < caps.min_gain) gainIn.value = caps.min_gain;
        if (curG > caps.max_gain) gainIn.value = caps.max_gain;
      }
    } catch (_) {}
}

/* Arrow-key handler for exposure input: 0.1 s steps ≤ 1 s, 1 s steps above.
     With step="any" browsers use a 1-unit implicit step and refuse to go below min
     when the result would be ≤ 0, so we replace the default behaviour entirely. */
function _expArrowHandler(ev) {
    if (ev.key !== 'ArrowUp' && ev.key !== 'ArrowDown') return;
    ev.preventDefault();
    const el  = ev.currentTarget;
    const cur = parseFloat(el.value) || 1.0;
    const step  = cur <= 1 ? 0.1 : 1.0;
    const delta = ev.key === 'ArrowUp' ? step : -step;
    const minV  = parseFloat(el.min) || 0.0001;
    const maxV  = parseFloat(el.max) || 1000;
    el.value = fmtExp(Math.max(minV, Math.min(maxV, cur + delta)));
    el.dispatchEvent(new Event('change'));
}

async function loadPreviewCameras() {
    const sel = await _loadSelectFromTrains('preview-cam-select');
    if (sel) onPreviewCamChange(sel.value || 'main');
    document.getElementById('preview-exposure')?.addEventListener('keydown', _expArrowHandler);
}

let _focuserMoveTimer = null;

async function refreshFocuser() {
    try {
      const data = await (await fetch('/api/focuser/status')).json();
      document.getElementById('s4-focuser-card').innerHTML = focuserCard(data);
    } catch (err) {
      setStatus('s4-focuser-status', String(err), true);
    }
}

/* Lightweight position-only update — doesn't rebuild the whole card. */
async function _refreshFocuserPosition() {
    try {
      const data = await (await fetch('/api/focuser/status')).json();
      const posEl   = document.getElementById('s4-focuser-pos');
      const dotEl   = document.getElementById('s4-focuser-dot');
      const badgeEl = document.getElementById('s4-focuser-badge');
      if (posEl && data.available) {
        const maxPos = data.max_position != null ? ` / ${data.max_position}` : '';
        posEl.textContent = `${data.position ?? '—'}${maxPos}`;
      }
      if (dotEl)   dotEl.className   = `dot ${data.moving ? 'dot-yellow' : 'dot-green'}`;
      if (badgeEl) {
        badgeEl.textContent = data.moving ? 'Moving…' : 'Stopped';
        badgeEl.className   = `state-badge ${data.moving ? 'state-slewing' : 'state-tracking'}`;
      }
      if (!data.moving) {
        clearInterval(_focuserMoveTimer);
        _focuserMoveTimer = null;
      }
    } catch (_) {}
}

function _startFocuserPositionPoll() {
    if (_focuserMoveTimer) return;  // already polling
    _focuserMoveTimer = setInterval(_refreshFocuserPosition, 500);
}

async function nudge(delta) {
    try {
      await apiPost('/api/focuser/nudge', { delta });
      await refreshFocuser();
      _startFocuserPositionPoll();
    } catch (err) {
      setStatus('s4-focuser-status', `Nudge failed: ${err.message}`, true);
    }
}

async function focuserMoveTo() {
    const pos = parseInt(document.getElementById('focuser-target').value, 10);
    if (isNaN(pos)) {
      setStatus('s4-focuser-status', 'Enter a valid step position first.', true);
      return;
    }
    try {
      await apiPost('/api/focuser/move', { position: pos });
      await refreshFocuser();
      _startFocuserPositionPoll();
    } catch (err) {
      setStatus('s4-focuser-status', `Move failed: ${err.message}`, true);
    }
}

async function focuserStop() {
    if (_focuserMoveTimer) { clearInterval(_focuserMoveTimer); _focuserMoveTimer = null; }
    try {
      await apiPost('/api/focuser/stop');
      await refreshFocuser();
    } catch (err) {
      setStatus('s4-focuser-status', `Stop failed: ${err.message}`, true);
    }
}

async function runAutofocus() {
    const btn          = document.getElementById('af-btn');
    const res          = document.getElementById('af-result');
    const range_steps  = parseInt(document.getElementById('af-range').value, 10);
    const step_size    = parseInt(document.getElementById('af-step').value, 10);
    const exposure     = parseFloat(document.getElementById('af-exposure').value);
    res.style.display = 'none';
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Focusing…';
    try {
      const d = await apiPost('/api/focuser/autofocus', { range_steps, step_size, exposure, camera_role: _focusCamRole });
      const method = d.fitted ? 'parabola' : 'argmax';
      const gain   = d.metric_gain >= 0 ? `+${d.metric_gain.toFixed(1)}` : d.metric_gain.toFixed(1);
      res.style.display = 'block';
      res.textContent =
        `Best: ${d.best_position} steps  |  gain: ${gain}  |  ${method}  |  ${d.positions.length} samples`;
      await refreshFocuser();
    } catch (err) {
      setStatus('s4-focuser-status', `Autofocus failed: ${err.message}`, true);
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Autofocus';
    }
}


async function runPreviewAutofocus() {
    const btn     = document.getElementById('preview-af-btn');
    const camRole = document.getElementById('preview-cam-select')?.value || 'main';
    const wasRunning = _reconnect && _ws !== null;
    if (wasRunning) previewStop();
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>';
    try {
      const range = parseInt(document.getElementById('af-range')?.value, 10) || 1000;
      const step  = parseInt(document.getElementById('af-step')?.value, 10) || 100;
      const exp   = parseFloat(document.getElementById('preview-exposure')?.value) || 2.0;
      const d = await apiPost('/api/focuser/autofocus',
        { range_steps: range, step_size: step, exposure: exp, camera_role: camRole });
      const sign = d.metric_gain >= 0 ? '+' : '';
      setStatus('s3-status',
        `AF: pos ${d.best_position}  gain ${sign}${d.metric_gain.toFixed(1)}`);
    } catch (err) {
      setStatus('s3-status', `AF failed: ${err.message}`, true);
    } finally {
      btn.disabled = !_focuserOk;
      btn.innerHTML = 'AF';
      if (wasRunning) previewStart();
    }
}

async function _refreshS1FocuserPos() {
    try {
      const fs = await (await fetch('/api/focuser/status')).json();
      if (!fs.available) return;
      const posEl  = document.getElementById('s1-focuser-pos');
      const posRow = document.getElementById('s1-focuser-pos-row');
      if (posEl) posEl.textContent = fs.max_position
        ? `${fs.position} / ${fs.max_position} steps`
        : `${fs.position} steps`;
      if (posRow) posRow.style.display = '';
    } catch (_) {}
}

async function previewNudge(delta) {
    try {
      const result = await apiPost('/api/focuser/nudge', { delta });
      const pos = document.getElementById('s3-focus-pos');
      if (pos) pos.textContent = `→ ${result.target}`;
      // Optimistic update: show target immediately in Stage 1 while focuser moves
      const s1posEl = document.getElementById('s1-focuser-pos');
      if (s1posEl) s1posEl.textContent = `${result.target} steps (→)`;
      // Poll actual position after focuser has had time to complete the move
      setTimeout(_refreshS1FocuserPos, 1500);
      setStatus('s3-status', '');  // clear any previous nudge error
    } catch (err) {
      setStatus('s3-status', `Focus failed: ${err.message}`, true);
      // Auto-clear "try again shortly" message after 3 s so it doesn't linger
      setTimeout(() => {
        const el = document.getElementById('s3-status');
        if (el && el.textContent.includes('try again shortly')) setStatus('s3-status', '');
      }, 3000);
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Bahtinov analyzer (Stage 4)
══════════════════════════════════════════════════════════════════════ */

