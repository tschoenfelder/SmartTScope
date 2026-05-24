function collimSelect(ra, dec, name) {
    if (_collimState === 'select_star') {
      collimSelectStar(ra, dec);
      return;
    }
    document.getElementById('goto-ra').value  = ra.toFixed(4);
    document.getElementById('goto-dec').value = dec.toFixed(4);
}

async function collimGoto(ra, dec, name) {
    setStatus('s4-status', '');
    try {
      await apiPost('/api/mount/goto', { ra, dec });
      setStatus('s4-status', `Slewing to ${name} — use guide pad to centre, then focus`);
      await refreshMount();
    } catch (err) {
      setStatus('s4-status', `GoTo ${name} failed: ${err.message}`, true);
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Collimation Wizard (COL-020/021)
══════════════════════════════════════════════════════════════════════ */

let _collimState     = 'idle';
let _collimPollTimer = null;

const _COLLIM_PHASE_MAP = {
    precheck: 1, select_star: 1, slew_to_star: 1,
    acquire_star: 2, center_star: 2, auto_exposure: 2,
    rough_defocus: 3, map_screws_by_obstruction: 3,
    measure_donut: 3, guide_rough_collimation: 3,
    install_tribahtinov: 4, map_mask_sectors: 4,
    fine_focus: 4, measure_spikes: 4, guide_fine_collimation: 4, final_refocus: 4,
    maskless_validation: 5, complete: 5,
};

function _startCollimPoll() {
    if (_collimPollTimer) return;
    _collimPollTimer = setInterval(async () => {
      try {
        const s = await (await fetch('/api/collimation/status')).json();
        _updateCollimWizard(s);
        if (s.state !== 'idle' && !s.is_terminal) {
          const o = await (await fetch('/api/collimation/overlay')).json();
          _drawCollimOverlay(o);
        }
        if (s.state === 'idle' || s.is_terminal) _stopCollimPoll();
      } catch { /* ignore transient */ }
    }, 2000);
}

function _stopCollimPoll() {
    if (_collimPollTimer) { clearInterval(_collimPollTimer); _collimPollTimer = null; }
}

async function _refreshCollimWizardOnce() {
    try {
      const s = await (await fetch('/api/collimation/status')).json();
      _updateCollimWizard(s);
      if (s.state !== 'idle' && !s.is_terminal) _startCollimPoll();
    } catch { /* ignore */ }
}

function _wizBtn(id, show, label) {
    const el = document.getElementById(id);
    if (!el) return;
    el.style.display = show ? '' : 'none';
    if (show && label) el.textContent = label;
}

function _updateCollimWizard(s) {
    _collimState = s.state;
    const idle         = s.state === 'idle';
    const terminal     = s.is_terminal;
    const paused       = s.is_paused;
    const waiting      = s.is_waiting_for_user;
    const active       = !idle && !terminal && !paused;
    const selectStar   = s.state === 'select_star';
    const guideState   = s.state === 'guide_rough_collimation' || s.state === 'guide_fine_collimation';
    const validateState = s.state === 'maskless_validation';

    // Dot colour
    const dot = document.getElementById('s4-wiz-dot');
    if (dot) {
      dot.className = 'dot ' + (
        s.state === 'complete' ? 'dot-green' :
        s.state === 'failed'   ? 'dot-red'   :
        idle ? 'dot-grey' : paused ? 'dot-grey' : 'dot-yellow'
      );
    }

    // State badge
    const badge = document.getElementById('s4-wiz-badge');
    if (badge) {
      badge.textContent = s.state.replace(/_/g, ' ');
      badge.className = 'state-badge ' + (
        s.state === 'complete' ? 'state-tracking' :
        s.state === 'failed'   ? 'state-error'    :
        idle || paused ? 'state-unknown' : 'state-pending'
      );
    }

    // Phase strip
    const phase = _COLLIM_PHASE_MAP[s.state] || 0;
    for (let i = 1; i <= 5; i++) {
      const el = document.getElementById(`wiz-ph-${i}`);
      if (!el) continue;
      el.className = 'wiz-phase' + (
        s.state === 'failed' && i === phase ? ' wiz-fail' :
        i < phase ? ' wiz-done' :
        i === phase && !idle ? ' wiz-active' : ''
      );
    }

    // Instruction
    const instr = document.getElementById('s4-wiz-instruction');
    if (instr) {
      instr.textContent = s.instruction || '';
      instr.style.color = (s.state === 'select_star')
        ? 'var(--accent-hi)' : 'var(--text)';
    }

    // Recommendation
    const rec = s.current_recommendation;
    const recEl = document.getElementById('s4-wiz-recommendation');
    if (recEl && rec) {
      document.getElementById('s4-wiz-rec-screw').textContent = `Screw ${rec.screw_id}: `;
      document.getElementById('s4-wiz-rec-dir').textContent   = rec.direction === 'cw' ? 'Turn Clockwise' : 'Turn Counter-clockwise';
      document.getElementById('s4-wiz-rec-size').textContent  = `(${rec.size})`;
      document.getElementById('s4-wiz-rec-confidence').textContent = `${(rec.confidence * 100).toFixed(0)}% confidence`;
      recEl.style.display = '';
    } else if (recEl) {
      recEl.style.display = 'none';
    }

    // Error
    const errEl = document.getElementById('s4-wiz-error');
    if (errEl) {
      if (s.error) { errEl.textContent = s.error; errEl.style.display = ''; }
      else { errEl.style.display = 'none'; }
    }

    // Guide status row
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
                ? ` RMS ${g.rms_px.toFixed(1)} px` : '';
            const last = g.last_pulse
                ? ` last ${g.last_pulse[1] > 0 ? '+' : ''}${g.last_pulse[1]}ms ${g.last_pulse[0]}`
                : '';
            if (lbl) lbl.textContent = `Guide: ${locked ? 'locked' : 'lost'}${rms}${last}`;
        }
    }

    // Buttons
    _wizBtn('s4-wiz-start-btn',  idle);
    _wizBtn('s4-wiz-pause-btn',  (active || waiting) && !terminal);
    _wizBtn('s4-wiz-resume-btn', paused);
    _wizBtn('s4-wiz-cancel-btn', !idle && !terminal);
    _wizBtn('s4-wiz-retry-btn',  terminal);
    _wizBtn('s4-wiz-next-btn',   waiting && !selectStar && !validateState,
            guideState ? 'Remeasure' : 'Next');
    _wizBtn('s4-wiz-finish-btn', guideState,
            s.state === 'guide_rough_collimation' ? 'Finish Rough' : 'Finish Fine');
    _wizBtn('s4-wiz-accept-btn', validateState);
    _wizBtn('s4-wiz-more-btn',   validateState);
}

async function collimStart() {
    const btn = document.getElementById('s4-wiz-start-btn');
    try {
      // Auto-unpark if mount is parked — collimation needs guide pulses
      const ms = await (await fetch('/api/mount/status')).json();
      if (ms.state === 'parked') {
        setStatus('s4-status', 'Unparking mount…');
        if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Unparking…'; }
        await apiPost('/api/mount/unpark');
        // Poll up to 15 s for state to leave PARKED
        let unparked = false;
        for (let i = 0; i < 30; i++) {
          await new Promise(r => setTimeout(r, 500));
          const d = await (await fetch('/api/mount/status')).json();
          _updateMountStrip(d);
          if (d.state !== 'parked') { unparked = true; break; }
        }
        if (!unparked) {
          setStatus('s4-status', 'Mount still parked — check OnStep (may need manual unpark or alignment)', true);
          return;
        }
        setStatus('s4-status', '');
      }
      if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Starting…'; }
      const s = await apiPost('/api/collimation/start');
      _updateCollimWizard(s);
      _startCollimPoll();
    } catch (err) {
      setStatus('s4-status', `Wizard start failed: ${err.message}`, true);
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = 'Start'; }
    }
}

async function collimPause() {
    try {
      const s = await apiPost('/api/collimation/pause');
      _updateCollimWizard(s);
    } catch (err) {
      setStatus('s4-status', `Pause failed: ${err.message}`, true);
    }
}

async function collimResume() {
    try {
      const s = await apiPost('/api/collimation/resume');
      _updateCollimWizard(s);
      _startCollimPoll();
    } catch (err) {
      setStatus('s4-status', `Resume failed: ${err.message}`, true);
    }
}

async function collimCancel() {
    try {
      const s = await apiPost('/api/collimation/cancel');
      _updateCollimWizard(s);
      _stopCollimPoll();
    } catch (err) {
      setStatus('s4-status', `Cancel failed: ${err.message}`, true);
    }
}

async function collimNext(finish = false) {
    try {
      const payload = finish ? { finish: true } : {};
      const s = await apiPost('/api/collimation/next', payload);
      _updateCollimWizard(s);
    } catch (err) {
      setStatus('s4-status', `Step failed: ${err.message}`, true);
    }
}

async function collimAccept(accepted) {
    try {
      const s = await apiPost('/api/collimation/next', { accept: accepted });
      _updateCollimWizard(s);
    } catch (err) {
      setStatus('s4-status', `Step failed: ${err.message}`, true);
    }
}

async function collimRetry() {
    try {
      const s = await apiPost('/api/collimation/retry');
      _updateCollimWizard(s);
      _stopCollimPoll();
    } catch (err) {
      setStatus('s4-status', `Reset failed: ${err.message}`, true);
    }
}

async function collimSelectStar(ra, dec) {
    try {
      const s = await apiPost('/api/collimation/next', { ra, dec });
      _updateCollimWizard(s);
    } catch (err) {
      setStatus('s4-status', `Star selection failed: ${err.message}`, true);
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Hardware Self-Test (COL-022)
══════════════════════════════════════════════════════════════════════ */

function _stResult(id, ok, text) {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text;
    el.style.color = ok ? 'var(--green)' : 'var(--red, #f85149)';
    const dot = document.getElementById('s4-st-dot');
    if (dot && ok) dot.className = 'dot dot-green';
}

async function selftestCamera() {
    const el = document.getElementById('s4-st-camera-result');
    if (el) { el.textContent = 'capturing…'; el.style.color = 'var(--muted)'; }
    try {
      const r = await apiPost('/api/collimation/selftest/camera');
      _stResult('s4-st-camera-result', true,
        `${r.width}×${r.height} px  peak ${r.peak_adu} ADU`);
    } catch (err) {
      _stResult('s4-st-camera-result', false, err.message);
    }
}

async function selftestMount(dir) {
    const el = document.getElementById('s4-st-mount-result');
    if (el) { el.textContent = 'sending pulse…'; el.style.color = 'var(--muted)'; }
    try {
      const r = await apiPost('/api/collimation/selftest/mount',
                              { direction: dir, duration_ms: 500 });
      _stResult('s4-st-mount-result', true,
        `${dir.toUpperCase()} pulse ${r.duration_ms} ms — ok`);
    } catch (err) {
      _stResult('s4-st-mount-result', false, err.message);
    }
}

async function selftestFocuser(steps) {
    const el = document.getElementById('s4-st-focuser-result');
    if (el) { el.textContent = 'moving…'; el.style.color = 'var(--muted)'; }
    try {
      const r = await apiPost('/api/collimation/selftest/focuser', { steps });
      if (!r.ok) {
        _stResult('s4-st-focuser-result', false, r.message || 'not available');
        return;
      }
      const delta = r.position_after - r.position_before;
      _stResult('s4-st-focuser-result', true,
        `${r.position_before} → ${r.position_after}  (Δ${delta >= 0 ? '+' : ''}${delta})`);
    } catch (err) {
      _stResult('s4-st-focuser-result', false, err.message);
    }
}

/* Collimation overlay on s4-bahtinov-svg (COL-021) */
function _drawCollimOverlay(d) {
    const svg = document.getElementById('s4-bahtinov-svg');
    const img = document.getElementById('s4-preview-img');
    if (!svg || !d || !d.available) {
      if (svg) svg.style.display = 'none';
      return;
    }
    if (!img || img.style.display === 'none') return;
    const iw = img.naturalWidth  || 1280;
    const ih = img.naturalHeight || 960;
    svg.setAttribute('viewBox', `0 0 ${iw} ${ih}`);
    svg.style.cssText = 'position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none';
    svg.style.display = '';

    const arrowDef = `<defs><marker id="col-arr" markerWidth="6" markerHeight="6" refX="3" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6 Z" fill="rgba(248,81,73,0.9)"/></marker></defs>`;
    let body = '';

    if (d.donut) {
      const { outer_cx: ocx, outer_cy: ocy, outer_r: or_, inner_cx: icx, inner_cy: icy, inner_r: ir, error_x: ex, error_y: ey } = d.donut;
      body += `<circle cx="${ocx}" cy="${ocy}" r="${or_}" fill="none" stroke="rgba(56,139,253,0.8)" stroke-width="2"/>`;
      body += `<circle cx="${icx}" cy="${icy}" r="${ir}"  fill="none" stroke="rgba(63,185,80,0.8)"  stroke-width="2"/>`;
      body += `<line x1="${ocx}" y1="${ocy}" x2="${ocx+ex}" y2="${ocy+ey}" stroke="rgba(248,81,73,0.9)" stroke-width="2" marker-end="url(#col-arr)"/>`;
      const cs = or_ * 0.06;
      body += `<line x1="${ocx-cs}" y1="${ocy}" x2="${ocx+cs}" y2="${ocy}" stroke="rgba(255,255,255,0.5)" stroke-width="1"/>`;
      body += `<line x1="${ocx}" y1="${ocy-cs}" x2="${ocx}" y2="${ocy+cs}" stroke="rgba(255,255,255,0.5)" stroke-width="1"/>`;
    }

    if (d.spike) {
      const { crossing_x: cx, crossing_y: cy } = d.spike;
      const cs = 14;
      body += `<circle cx="${cx}" cy="${cy}" r="5" fill="none" stroke="rgba(248,81,73,0.9)" stroke-width="2"/>`;
      body += `<line x1="${cx-cs}" y1="${cy}" x2="${cx+cs}" y2="${cy}" stroke="rgba(248,81,73,0.9)" stroke-width="1.5"/>`;
      body += `<line x1="${cx}" y1="${cy-cs}" x2="${cx}" y2="${cy+cs}" stroke="rgba(248,81,73,0.9)" stroke-width="1.5"/>`;
    }

    svg.innerHTML = arrowDef + body;
}

