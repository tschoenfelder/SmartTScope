
/* ══════════════════════════════════════════════════════════════════════
     Mount strip (compact status, stages 2–5)
══════════════════════════════════════════════════════════════════════ */
const _STRIP_DOT = {
    parked: 'dot-grey', unparked: 'dot-yellow', at_home: 'dot-yellow',
    tracking: 'dot-green', slewing: 'dot-green',
    at_limit: 'dot-red', unknown: 'dot-grey',
};

const _STATE_LABEL = {
    parked: 'Parked', unparked: 'Unparked', at_home: 'Home',
    tracking: 'Tracking', slewing: 'Slewing',
    at_limit: 'At Limit', unknown: 'Unknown',
};

function _fmtHA(h) {
    const sign = h < 0 ? '−' : '+';
    const abs  = Math.abs(h);
    const hh   = Math.floor(abs);
    const mm   = Math.floor((abs - hh) * 60);
    const ss   = Math.floor(((abs - hh) * 60 - mm) * 60);
    return `HA ${sign}${String(hh).padStart(2,'0')}h${String(mm).padStart(2,'0')}m`;
}

function _updateMountStrip(data) {
    const state  = data.state || 'unknown';
    const dotEl  = document.getElementById('ms-dot');
    const stEl   = document.getElementById('ms-state');
    const rdEl   = document.getElementById('ms-radec');
    const haEl   = document.getElementById('ms-haalt');
    const label = _STATE_LABEL[state] || state;
    if (dotEl) dotEl.className = 'dot ' + (_mountPendingCmd ? 'dot-yellow' : (_STRIP_DOT[state] || 'dot-grey'));
    if (stEl)  stEl.textContent = _mountPendingCmd ? `${_mountPendingCmd}…` : (data.stale ? `${label} ⚠` : label);
    if (rdEl)  rdEl.textContent = data.ra != null
      ? `${_formatRA(+data.ra)}  ${_formatDec(+data.dec)}`
      : '—';
    if (haEl)  haEl.textContent = data.ha != null
      ? `${_fmtHA(+data.ha)}  Alt ${(+data.alt).toFixed(1)}°`
      : '';

    // Keep Stage 1 limits card current values in sync
    const haLive  = document.getElementById('current-ha');
    const altLive = document.getElementById('current-alt');
    if (haLive)  haLive.textContent  = data.ha  != null ? _fmtHA(+data.ha)              : '—';
    if (altLive) altLive.textContent = data.alt != null ? (+data.alt).toFixed(1) + '°'  : '—';

    // Unlock navigation stages from mount state — covers page-reload with already-unparked mount.
    // Stage 4 (Collimation) is unlocked whenever the mount is responding (any known state),
    // because calibration frames and the Bahtinov preview don't require an unparked mount.
    // The collimation wizard auto-unparks internally if needed.
    if (state !== 'parked' && state !== 'unknown') {
        unlockStage(2);
    }
    if (state !== 'unknown') {
        unlockStage(4);
    }


    // Grey out movement buttons when parked — guide pulses and GoTo are no-ops on OnStep
    // while parked. UNPARK, HOME, STOP, and TRACK are intentionally excluded.
    const _parked = (state === 'parked');
    for (const id of ['s2-guide-pad', 's4-guide-pad', 's4-st-mount-btns']) {
        const el = document.getElementById(id);
        if (el) el.querySelectorAll('button').forEach(b => { b.disabled = _parked; });
    }
    const gotoBtn = document.getElementById('s2-goto-btn');
    if (gotoBtn && !_mountPendingCmd) gotoBtn.disabled = _parked;
}

function mountEmergencyStop() {
    // Stop both mount and focuser; bypass all API-level locks
    apiPost('/api/emergency_stop').then(() => refreshMount()).catch(() => {
      // Fallback: try individual stop if emergency endpoint fails
      apiPost('/api/mount/stop').catch(() => {});
    });
}

/* ══════════════════════════════════════════════════════════════════════
     Mount — Stage 1 card
══════════════════════════════════════════════════════════════════════ */
const _MOUNT_DOT = {
    parked: 'dot-grey', unparked: 'dot-yellow', at_home: 'dot-yellow',
    tracking: 'dot-green', slewing: 'dot-green',
    at_limit: 'dot-red', unknown: 'dot-grey',
};

function mountCard(data) {
    const state  = data.state || 'unknown';
    const dotCls = _mountPendingCmd ? 'dot-yellow' : (_MOUNT_DOT[state] || 'dot-grey');
    const ra     = data.ra  != null ? _formatRA(+data.ra)   : '—';
    const dec    = data.dec != null ? _formatDec(+data.dec) : '—';
    const badge  = _mountConnected
      ? '<span style="font-size:0.68rem;color:var(--success);margin-left:0.25rem">● Connected</span>'
      : '';
    const stateBadge = _mountPendingCmd
      ? `<span class="state-badge state-pending"><span class="spin" style="display:inline-block;width:0.65em;height:0.65em;margin-right:0.3em;vertical-align:middle"></span>${_mountPendingCmd}…</span>`
      : data.stale
        ? `<span class="state-badge state-unknown" title="Status data may be outdated — serial poll delayed">⚠ ${_STATE_LABEL[state] || state}</span>`
        : `<span class="state-badge state-${state}">${_STATE_LABEL[state] || state}</span>`;
    const wdWarn = data.watchdog_warning
      ? `<div style="font-size:0.78rem;color:var(--warning);background:rgba(210,153,34,0.1);
              border:1px solid rgba(210,153,34,0.35);border-radius:4px;padding:0.35rem 0.6rem;
              margin-top:0.5rem">⚠ ${escHtml(data.watchdog_warning)}</div>`
      : '';
    return `
      <div class="card">
        <div class="card-title">
          <span class="dot ${dotCls}"></span>
          OnStep Mount
          ${stateBadge}
          ${badge}
        </div>
        ${wdWarn}
        <div class="params">
          <div class="param">
            <span class="param-label" style="color:var(--muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.04em">Current</span>
            <span></span>
          </div>
          <div class="param">
            <span class="param-label">RA</span>
            <span class="param-value mono">${escHtml(ra)}</span>
          </div>
          <div class="param">
            <span class="param-label">Dec</span>
            <span class="param-value mono">${escHtml(dec)}</span>
          </div>
          <div class="param" style="margin-top:0.35rem">
            <span class="param-label" style="color:var(--muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.04em">Home (HA=0, Dec 89°)</span>
            <span></span>
          </div>
          <div class="param">
            <span class="param-label">RA</span>
            <span class="param-value mono">${data.home_ra != null ? _formatRA(+data.home_ra) : '—'}</span>
          </div>
          <div class="param">
            <span class="param-label">Dec</span>
            <span class="param-value mono">${data.home_dec != null ? _formatDec(+data.home_dec) : '—'}</span>
          </div>
          <div class="param" style="margin-top:0.35rem">
            <span class="param-label" style="color:var(--muted);font-size:0.7rem;text-transform:uppercase;letter-spacing:0.04em">Park</span>
            <span></span>
          </div>
          <div class="param">
            <span class="param-label">RA</span>
            <span class="param-value mono">${data.park_ra != null ? _formatRA(+data.park_ra) : '—'}</span>
          </div>
          <div class="param">
            <span class="param-label">Dec</span>
            <span class="param-value mono">${data.park_dec != null ? _formatDec(+data.park_dec) : '—'}</span>
          </div>
        </div>
        <div class="controls">
          <span class="adv-only" style="display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;flex:1">
            ${state === 'tracking'
              ? `<button class="secondary" onclick="mountAction('disable_tracking')">Disable Tracking</button>`
              : `<button class="secondary" onclick="mountAction('track')">Enable Tracking</button>`}
            <span class="controls-spacer"></span>
            <span style="display:flex;gap:0.5rem;flex-wrap:nowrap;align-items:center">
              <button class="secondary" onclick="mountHome()"
                      title="Slew to home position (:hC#)">Home</button>
              <button class="secondary" onclick="mountSetPark()"
                      title="Save current position as park position (:hS#) — do this once after homing">Set Park</button>
              <button class="secondary" onclick="mountAction('unpark')"
                      title="Unpark mount">Unpark</button>
              <button class="secondary" onclick="mountAction('park')"
                      title="Park mount">Park</button>
            </span>
          </span>
          <button class="danger" onclick="mountEmergencyStop()"
                  title="Emergency stop — halts mount and focuser immediately">Stop</button>
        </div>
      </div>`;
}

/* Poll until mount leaves SLEWING state; updates the mount strip live.
     Resolves with final status data or undefined on timeout. */
async function watchSlew(statusId, label, timeout_s = 120) {
    const deadline = Date.now() + timeout_s * 1000;
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 2000));
      try {
        const data = await (await fetch('/api/mount/status')).json();
        _updateMountStrip(data);
        if (data.state !== 'slewing') {
          if (statusId) setStatus(statusId, (label ? label + ' — ' : '') + data.state);
          return data;
        }
      } catch { /* ignore transient network errors */ }
    }
    if (statusId) setStatus(statusId, (label ? label + ': ' : '') + 'slew timeout', true);
}

async function refreshMount() {
    try {
      const data = await (await fetch('/api/mount/status')).json();
      document.getElementById('s1-mount-card').innerHTML = mountCard(data);
      _updateMountStrip(data);
    } catch (err) {
      setStatus('s1-mount-status', String(err), true);
    }
}

async function mountAction(action) {
    setStatus('s1-mount-status', '');
    _mountPendingCmd = action;
    await refreshMount();  // show pending badge immediately
    try {
      await apiPost(`/api/mount/${action}`);
      const expectParked   = action === 'park';
      const expectUnparked = action === 'unpark';
      if (expectParked || expectUnparked) {
        // Park slews can take 30-60 s; unpark polls up to 15 s (server no longer blocks).
        const maxIter  = expectParked ? 60 : 30;
        const delayMs  = expectParked ? 1000 : 500;
        for (let i = 0; i < maxIter; i++) {
          await new Promise(r => setTimeout(r, i === 0 ? 300 : delayMs));
          const data = await (await fetch('/api/mount/status')).json();
          _updateMountStrip(data);
          const st = data.state;
          if (expectParked   && st === 'parked')  break;
          if (expectUnparked && st !== 'parked')  break;
        }
      } else {
        await new Promise(r => setTimeout(r, 450));
      }
      if (action === 'unpark' || action === 'track') {
        unlockStage(2);
        unlockStage(4);
      }
    } catch (err) {
      setStatus('s1-mount-status', `${action} failed: ${err.message}`, true);
    } finally {
      _mountPendingCmd = null;
      await refreshMount();  // render confirmed hardware state
    }
}

async function mountGoto() {
    const ra  = parseFloat(document.getElementById('goto-ra').value);
    const dec = parseFloat(document.getElementById('goto-dec').value);
    if (isNaN(ra) || isNaN(dec)) {
      setStatus('s3-status', 'Enter valid RA and Dec values first.', true);
      return;
    }
    setStatus('s3-status', '');
    _mountPendingCmd = 'goto';
    try {
      await apiPost('/api/mount/goto', { ra, dec });
      document.getElementById('s3-proceed-btn').disabled = false;
      document.getElementById('s3-proceed-btn').title = '';
      unlockStage(4);
      setStatus('s3-status', `Slewing to RA ${ra.toFixed(3)} h  Dec ${dec.toFixed(2)}°…`);
      await watchSlew('s3-status', `RA ${ra.toFixed(3)} Dec ${dec.toFixed(2)}`);
      _s3GotoData = { ra, dec };
      const arcBtn = document.getElementById('s3-arc-goto-btn');
      if (arcBtn && _s3ArchiveEnabled) arcBtn.disabled = false;
    } catch (err) {
      let msg = `GoTo failed: ${err.message}`;
      try {
        const d = JSON.parse(err.message);
        if (d?.error === 'solar_exclusion')
          msg = `Solar exclusion — target is only ${d.sun_separation_deg}° from the Sun.`;
        else if (d?.error === 'mount_limit')
          msg = `Mount limit (${d.reason}): alt ${d.altitude_deg?.toFixed(1) ?? '—'}° or HA ${d.ha_hours?.toFixed(2) ?? '—'} h.`;
      } catch {}
      setStatus('s3-status', msg, true);
    } finally {
      _mountPendingCmd = null;
    }
}

async function mountHome() {
    setStatus('s1-mount-status', '');
    _mountPendingCmd = 'home';
    const btn = document.querySelector('button[onclick="mountHome()"]');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Homing…'; }
    await refreshMount();  // show pending badge immediately
    try {
      await apiPost('/api/mount/home');
      setStatus('s1-mount-status', 'Slewing to OnStep home position…');
    } catch (err) {
      setStatus('s1-mount-status', `Home failed: ${err.message}`, true);
    } finally {
      _mountPendingCmd = null;
      if (btn) { btn.disabled = false; btn.innerHTML = 'Home'; }
      await refreshMount();  // render confirmed hardware state
    }
}

async function mountSetPark() {
    setStatus('s1-mount-status', '');
    const btn = document.querySelector('button[onclick="mountSetPark()"]');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Setting…'; }
    try {
      await apiPost('/api/mount/set-park');
      setStatus('s1-mount-status', 'Park position saved — Park button will now work.');
    } catch (err) {
      setStatus('s1-mount-status', `Set park failed: ${err.message}`, true);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = 'Set Park'; }
    }
}

function s1Proceed() {
    goToStage(2);
}

/* ══════════════════════════════════════════════════════════════════════
     Stage 2 — Star Alignment
══════════════════════════════════════════════════════════════════════ */
const _align = { numStars: 1, currentStar: 0 };
/* shared guide-pad state — only one active at a time across all stages */
let _guideTimer = null;

function guideStart(dir, msInputId) {
    if (_guideTimer) return;
    const ms = parseInt(document.getElementById(msInputId).value) || 500;
    const body = JSON.stringify({ direction: dir, duration_ms: ms });
    // Use /nudge (center rate) instead of /guide (guide rate) — center rate is
    // always visually observable; guide rate depends on OnStep configuration.
    const send = () => fetch('/api/mount/nudge', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body,
    });
    send();
    _guideTimer = setInterval(send, ms + 100);
}

function guideStop() {
    if (_guideTimer) { clearInterval(_guideTimer); _guideTimer = null; }
}

async function s2Home() {
    const btn = document.getElementById('s2-home-btn');
    const st  = document.getElementById('s2-home-status');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Slewing…';
    st.textContent = '';
    try {
      await apiPost('/api/mount/home');
      st.textContent = '→ Slewing to OnStep home…';
      st.style.color = 'var(--success)';
      await refreshMount();
    } catch (err) {
      st.textContent = String(err);
      st.style.color = 'var(--danger)';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Slew to Home';
    }
}

async function s2StartAlign() {
    const n = parseInt(document.querySelector('input[name="s2-nstars"]:checked').value);
    _align.numStars = n;
    _align.currentStar = 1;
    const btn = document.getElementById('s2-start-btn');
    const st  = document.getElementById('s2-setup-status');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Starting…';
    st.textContent = '';
    try {
      await apiPost('/api/mount/align/start', { num_stars: n });
      st.textContent = `${n}-star alignment started`;
      st.style.color = 'var(--success)';
      document.getElementById('s2-setup-dot').className = 'dot dot-green';
      await _s2ShowStarCard();
    } catch (err) {
      st.textContent = String(err);
      st.style.color = 'var(--danger)';
      btn.disabled = false;
      btn.innerHTML = 'Start Alignment';
    }
}

async function _s2ShowStarCard() {
    document.getElementById('s2-star-card').style.display = '';
    document.getElementById('s2-star-counter').textContent =
      `Star ${_align.currentStar} of ${_align.numStars}`;
    document.getElementById('s2-accept-status').textContent = '';
    document.getElementById('s2-goto-status').textContent = '';
    const sel = document.getElementById('s2-star-select');
    if (sel.options.length === 0) {
      try {
        const targets = await (await fetch('/api/catalog/stars')).json();
        sel.innerHTML = '';
        targets
          .filter(t => t.magnitude != null && t.magnitude <= 3.0 && t.type === 'star')
          .sort((a, b) => (a.magnitude ?? 99) - (b.magnitude ?? 99))
          .forEach(t => {
            const o = document.createElement('option');
            o.value = JSON.stringify({ ra: t.ra, dec: t.dec });
            const mag = t.magnitude != null ? (t.magnitude >= 0 ? '+' : '') + t.magnitude.toFixed(1) : '?';
            o.textContent = `${t.name}  (mag ${mag})`;
            sel.appendChild(o);
          });
        if (!sel.options.length) sel.innerHTML = '<option>No bright stars in stars.cfg (mag ≤ 3)</option>';
      } catch (e) {
        sel.innerHTML = '<option>Error loading targets</option>';
      }
    }
}

async function s2GotoStar() {
    if (!document.getElementById('s2-star-select').value) return;
    const pos = JSON.parse(document.getElementById('s2-star-select').value);
    const btn = document.getElementById('s2-goto-btn');
    const st  = document.getElementById('s2-goto-status');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Slewing…';
    st.textContent = '';
    try {
      await apiPost('/api/mount/goto', pos);
      st.textContent = 'Slewing — centre star with guide controls';
      st.style.color = 'var(--success)';
      await refreshMount();
    } catch (err) {
      st.textContent = String(err);
      st.style.color = 'var(--danger)';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'GoTo';
    }
}

function s2GuideStart(dir) { guideStart(dir, 's2-guide-ms'); }
function s2GuideStop()      { guideStop(); }

async function s2AcceptStar() {
    const btn = document.getElementById('s2-accept-btn');
    const st  = document.getElementById('s2-accept-status');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Accepting…';
    try {
      await apiPost('/api/mount/align/accept');
      st.textContent = `Star ${_align.currentStar} accepted ✓`;
      st.style.color = 'var(--success)';
      _align.currentStar++;
      if (_align.currentStar > _align.numStars) {
        document.getElementById('s2-star-card').style.display = 'none';
        document.getElementById('s2-save-card').style.display = '';
      } else {
        document.getElementById('s2-star-counter').textContent =
          `Star ${_align.currentStar} of ${_align.numStars}`;
        document.getElementById('s2-goto-status').textContent = '';
        document.getElementById('s2-accept-status').textContent = '';
      }
    } catch (err) {
      st.textContent = String(err);
      st.style.color = 'var(--danger)';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Accept Star';
    }
}

async function s2SaveAlign() {
    const btn = document.getElementById('s2-save-btn');
    const st  = document.getElementById('s2-save-status');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Saving…';
    try {
      await apiPost('/api/mount/align/save');
      st.textContent = 'Model saved ✓';
      st.style.color = 'var(--success)';
    } catch (err) {
      st.textContent = String(err);
      st.style.color = 'var(--danger)';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Save to EEPROM';
    }
}

function s2Done() {
    completeStage(2);
    unlockStage(3);
    unlockStage(5);
    goToStage(3);
}

/* ══════════════════════════════════════════════════════════════════════
     Polar Alignment Measurement (Stage 2)
══════════════════════════════════════════════════════════════════════ */

let _paTimer = null;

async function paConfirmChecklist() {
    const ids = ['pa-chk-home','pa-chk-north','pa-chk-clutch','pa-chk-camera',
                 'pa-chk-focus','pa-chk-cables','pa-chk-collision','pa-chk-stable','pa-chk-screws'];
    if (!ids.every(id => document.getElementById(id)?.checked)) {
      document.getElementById('pa-chk-status').textContent = 'All items must be checked.';
      document.getElementById('pa-chk-status').style.color = 'var(--error)';
      return;
    }
    const body = {
      mount_at_home:            true, telescope_points_north: true, clutches_locked:       true,
      camera_connected:         true, focus_ok:               true, cables_slack:          true,
      no_collision_risk:        true, mount_stable:           true, alt_az_screws_accessible: true,
    };
    try {
      const r = await apiPost('/api/polar/checklist', body);
      if (r.confirmed) {
        document.getElementById('pa-chk-dot').style.background = 'var(--success)';
        document.getElementById('pa-chk-status').textContent   = 'Confirmed — ready to measure.';
        document.getElementById('pa-chk-status').style.color   = 'var(--success)';
        document.getElementById('pa-chk-btn').disabled = true;
      }
    } catch (err) {
      document.getElementById('pa-chk-status').textContent = `Error: ${err}`;
      document.getElementById('pa-chk-status').style.color = 'var(--error)';
    }
}

async function paMeasure() {
    const btn = document.getElementById('pa-measure-btn');
    btn.disabled = true;
    document.getElementById('pa-cancel-btn').disabled = false;
    document.getElementById('pa-results-card').style.display = 'none';
    document.getElementById('pa-coarse-card').style.display  = 'none';
    document.getElementById('pa-fallback-card').style.display = 'none';
    document.getElementById('pa-progress-wrap').style.display = '';
    document.getElementById('pa-warning-msg').style.display   = 'none';
    _paSetProgress(0, 'Starting…');
    const body = {
      ra_step_h:               parseFloat(document.getElementById('pa-ra-step').value)    || 1.0,
      exposure:                parseFloat(document.getElementById('pa-exposure').value)    || 5.0,
      gain:                    parseInt(document.getElementById('pa-gain').value, 10)      || 100,
      camera_index:            _trainCamIdx(document.getElementById('pa-cam-select')?.value || 'main'),
      target_precision_arcmin: parseFloat(document.getElementById('pa-precision').value)   || 2.0,
    };
    try {
      await apiPost('/api/polar/measure', body);
    } catch (err) {
      _paSetProgress(0, `Error: ${err}`, true);
      btn.disabled = false;
      document.getElementById('pa-cancel-btn').disabled = true;
      return;
    }
    clearInterval(_paTimer);
    _paTimer = setInterval(_paPoll, 2000);
}

async function paLive() {
    const btn = document.getElementById('pa-live-btn');
    btn.disabled = true;
    document.getElementById('pa-cancel-btn').disabled = false;
    document.getElementById('pa-live-label').textContent = 'Live adjustment running…';
    document.getElementById('pa-progress-wrap').style.display = '';
    _paSetProgress(100, 'Live adjustment…');
    try {
      await apiPost('/api/polar/live', {});
    } catch (err) {
      document.getElementById('pa-live-label').textContent = `Error: ${err}`;
      btn.disabled = false;
      return;
    }
    clearInterval(_paTimer);
    _paTimer = setInterval(_paPoll, 2500);
}

async function paRefine() {
    document.getElementById('pa-refine-btn').disabled = true;
    document.getElementById('pa-results-card').style.display = 'none';
    document.getElementById('pa-progress-wrap').style.display = '';
    _paSetProgress(0, 'Starting second run…');
    document.getElementById('pa-cancel-btn').disabled = false;
    try {
      await apiPost('/api/polar/refine', {});
    } catch (err) {
      _paSetProgress(0, `Error: ${err}`, true);
      document.getElementById('pa-refine-btn').disabled = false;
      return;
    }
    clearInterval(_paTimer);
    _paTimer = setInterval(_paPoll, 2000);
}

async function paFallback() {
    const camIdx = parseInt(document.getElementById('pa-fallback-cam').value, 10) || 1;
    document.getElementById('pa-fallback-btn').disabled = true;
    document.getElementById('pa-fallback-card').style.display = 'none';
    document.getElementById('pa-progress-wrap').style.display = '';
    _paSetProgress(0, 'Retrying with guide camera…');
    document.getElementById('pa-cancel-btn').disabled = false;
    try {
      await apiPost('/api/polar/use_fallback_camera', { camera_index: camIdx });
    } catch (err) {
      _paSetProgress(0, `Error: ${err}`, true);
      document.getElementById('pa-fallback-btn').disabled = false;
      document.getElementById('pa-fallback-card').style.display = '';
      return;
    }
    clearInterval(_paTimer);
    _paTimer = setInterval(_paPoll, 2000);
}

async function paCancel() {
    clearInterval(_paTimer); _paTimer = null;
    try { await apiPost('/api/polar/cancel', {}); } catch (_) {}
    _paSetProgress(0, 'Cancelled');
    document.getElementById('pa-measure-btn').disabled = false;
    document.getElementById('pa-cancel-btn').disabled = true;
    document.getElementById('pa-progress-wrap').style.display = 'none';
    document.getElementById('pa-live-label').textContent = '';
    document.getElementById('pa-live-btn').disabled = false;
    document.getElementById('pa-refine-btn').disabled = false;
}

async function _paPoll() {
    try {
      const d = await (await fetch('/api/polar/status')).json();
      _paRender(d);
    } catch (_) {}
}

const _PA_STEP_LABELS = {
    idle:                    'Idle',
    slewing:                 'Slewing…',
    solving_1:               'Solving position 1…',
    solving_2:               'Solving position 2…',
    solving_3:               'Solving position 3…',
    computing:               'Computing pole…',
    done:                    'Done',
    refining:                'Refining…',
    live:                    'Live — adjusting screws…',
    coarse_required:         'Coarse alignment needed',
    camera_fallback_offered: 'Plate solve failed — fallback available',
    error:                   'Error',
};

function _paRender(d) {
    _paSetProgress(d.progress, _PA_STEP_LABELS[d.step] || d.step, d.step === 'error');

    const dot = document.getElementById('pa-dot');
    if (dot) dot.className = 'dot ' + (
      d.step === 'done' ? 'dot-green' : d.step === 'error' ? 'dot-red' :
      d.running ? 'dot-yellow' : 'dot-grey'
    );

    if (d.checklist_confirmed) {
      document.getElementById('pa-chk-dot').style.background = 'var(--success)';
      document.getElementById('pa-chk-status').textContent   = 'Confirmed';
      document.getElementById('pa-chk-status').style.color   = 'var(--success)';
      document.getElementById('pa-chk-btn').disabled = true;
    }

    const terminalSteps = new Set(['done','error','coarse_required','camera_fallback_offered']);
    if (!d.running && terminalSteps.has(d.step)) {
      clearInterval(_paTimer); _paTimer = null;
      document.getElementById('pa-measure-btn').disabled = false;
      document.getElementById('pa-cancel-btn').disabled  = true;
      document.getElementById('pa-live-btn').disabled    = false;
      document.getElementById('pa-refine-btn').disabled  = false;
    }

    // warning
    const warnEl = document.getElementById('pa-warning-msg');
    if (d.warning_msg) {
      warnEl.textContent = d.warning_msg;
      warnEl.style.display = '';
    } else {
      warnEl.style.display = 'none';
    }

    // coarse required
    document.getElementById('pa-coarse-card').style.display =
      d.step === 'coarse_required' ? '' : 'none';
    if (d.step === 'coarse_required') {
      const deg = d.coarse_error_deg != null ? d.coarse_error_deg.toFixed(1) : '?';
      document.getElementById('pa-coarse-msg').textContent =
        `Detected pole is ${deg}° from NCP — this is outside the fine-screw range. ` +
        `Manually reposition the tripod or mount head closer to the celestial pole, then press Measure again.`;
    }

    // camera fallback
    document.getElementById('pa-fallback-card').style.display =
      d.step === 'camera_fallback_offered' ? '' : 'none';

    // results / live
    if ((d.step === 'done' || d.step === 'live') && d.alt_error_arcmin != null) {
      document.getElementById('pa-results-card').style.display = '';
      document.getElementById('pa-pole-ra').textContent  =
        d.pole_ra  != null ? _formatRA(d.pole_ra)   : '—';
      document.getElementById('pa-pole-dec').textContent =
        d.pole_dec != null ? _formatDec(d.pole_dec) : '—';

      const altErr = d.alt_error_arcmin ?? 0;
      const azErr  = d.az_error_arcmin  ?? 0;
      const fmt    = v => (v >= 0 ? '+' : '') + v.toFixed(1) + '′';
      document.getElementById('pa-alt-error').innerHTML =
        `<span class="mono">${fmt(altErr)}</span>` +
        (d.correction_alt ? `<span style="color:var(--muted);font-size:0.78rem;margin-left:0.4rem">${d.correction_alt}</span>` : '');
      document.getElementById('pa-az-error').innerHTML =
        `<span class="mono">${fmt(azErr)}</span>` +
        (d.correction_az ? `<span style="color:var(--muted);font-size:0.78rem;margin-left:0.4rem">${d.correction_az}</span>` : '');
      document.getElementById('pa-total-error').textContent =
        d.total_error_arcmin != null ? d.total_error_arcmin.toFixed(1) + '′' : '—';
      document.getElementById('pa-quality').textContent = d.quality_label || '—';

      const verdict = document.getElementById('pa-verdict');
      if (d.target_reached) {
        verdict.style.color   = 'var(--success)';
        verdict.textContent   = `Target reached (${d.total_error_arcmin?.toFixed(1)}′ ≤ ${d.target_precision_arcmin}′)`;
      } else if (d.total_error_arcmin != null && d.total_error_arcmin <= 10) {
        verdict.style.color   = 'var(--warning)';
        verdict.textContent   = `Adjust screws, then Start Live Adjustment or Second Run`;
      } else {
        verdict.style.color   = 'var(--error)';
        verdict.textContent   = `Large error — use Coarse Adjustment then Measure again`;
      }

      if (d.step === 'live') {
        document.getElementById('pa-live-label').textContent = 'Live — updating…';
      } else {
        document.getElementById('pa-live-label').textContent = '';
      }
    } else if (d.step !== 'coarse_required' && d.step !== 'camera_fallback_offered') {
      document.getElementById('pa-results-card').style.display = 'none';
    }

    if (d.step === 'error' && d.error_msg) {
      setStatus('s2-status', `Polar alignment error: ${d.error_msg}`, true);
    }
}

function _paSetProgress(pct, label, isError = false) {
    const bar = document.getElementById('pa-progress-bar');
    if (bar) bar.style.width = pct + '%';
    const lbl = document.getElementById('pa-step-label');
    lbl.textContent = label;
    lbl.style.color = isError ? 'var(--error)' : 'var(--muted)';
}

/* ══════════════════════════════════════════════════════════════════════
     Stage 4 — Collimation helpers
══════════════════════════════════════════════════════════════════════ */
async function loadCollimStars() {
    const list = document.getElementById('s4-star-list');
    setStatus('s4-stars-status', '');
    try {
      const targets = await (await fetch('/api/catalog/stars')).json();
      const bright  = targets.filter(t => t.type === 'star' && t.magnitude != null && t.magnitude <= 3.0);
      if (!bright.length) {
        setStatus('s4-stars-status', 'No stars with magnitude ≤ 3 found in stars.cfg.');
        list.innerHTML = '';
        return;
      }
      bright.sort((a, b) => a.magnitude - b.magnitude);
      list.innerHTML = bright.map(t => {
        const ra  = t.ra.toFixed(3) + ' h';
        const dec = (t.dec >= 0 ? '+' : '') + t.dec.toFixed(1) + '°';
        return `
          <div class="star-item"
               onclick="collimSelect(${t.ra},${t.dec},'${escHtml(t.name)}')">
            <span class="si-name">${escHtml(t.name)}</span>
            <span class="si-common">${escHtml(t.common_name || '')}
              <span style="color:var(--warning);font-size:0.72rem"> m${t.magnitude}</span>
            </span>
            <span class="si-coords">${ra} ${dec}</span>
            <button class="secondary"
                    style="padding:0.15rem 0.45rem;font-size:0.72rem;flex-shrink:0"
                    onclick="collimGoto(${t.ra},${t.dec},'${escHtml(t.name)}');event.stopPropagation()"
                    title="Slew to ${escHtml(t.name)}">GoTo</button>
          </div>`;
      }).join('');
    } catch (err) {
      setStatus('s4-stars-status', 'Could not load targets: ' + err, true);
    }
}

