function _gmSetRunning(running) {
    document.getElementById('guide-mon-start-btn').style.display = running ? 'none' : '';
    document.getElementById('guide-mon-stop-btn').style.display  = running ? '' : 'none';
    const dot = document.getElementById('guide-mon-dot');
    if (dot) dot.className = running ? 'dot dot-yellow' : 'dot dot-grey';
}

function _gmStartPolling() {
    if (_gmPollTimer) clearInterval(_gmPollTimer);
    _gmPollTimer = setInterval(_gmPoll, 3000);
}

async function _gmPoll() {
    try {
      const d = await fetch('/api/guide_monitor/status').then(r => r.json());
      _gmUpdateUI(d);
    } catch {}
}

function _gmUpdateUI(d) {
    const dot     = document.getElementById('guide-mon-dot');
    const row     = document.getElementById('guide-mon-status-row');
    const badge   = document.getElementById('guide-mon-status-badge');
    const settings = document.getElementById('guide-mon-settings');
    const timeEl  = document.getElementById('guide-mon-time');
    const warnEl  = document.getElementById('guide-mon-warn');

    if (!d.running && d.status === null) {
      _gmSetRunning(false);
      if (_gmPollTimer) { clearInterval(_gmPollTimer); _gmPollTimer = null; }
      return;
    }

    _gmSetRunning(d.running);
    if (dot && d.status) dot.className = 'dot ' +
      (d.status === 'GUIDE_GAIN_OK' || d.status === 'ADJUSTED' ? 'dot-green' : 'dot-yellow');
    if (d.dawn_warning && dot) dot.className = 'dot dot-yellow';

    if (d.status) {
      row.style.display = '';
      badge.textContent = d.status.replace(/_/g, ' ');
      badge.style.background = _GM_STATUS_COLORS[d.status] || 'var(--muted)';

      if (d.exposure_ms != null) {
        settings.textContent = `Exp: ${d.exposure_ms.toFixed(0)} ms  Gain: ${d.gain ?? '—'}`;
      }

      if (d.checked_at) {
        const dt = new Date(d.checked_at);
        timeEl.textContent = 'Last check: ' + dt.toLocaleTimeString();
      }

      warnEl.style.display = d.warning_msg ? '' : 'none';
      warnEl.textContent   = d.warning_msg || '';
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Plate solving (Stage 3)
══════════════════════════════════════════════════════════════════════ */
async function solveFrame() {
    const btn      = document.getElementById('solve-btn');
    const result   = document.getElementById('solve-result');
    const exposure = parseFloat(document.getElementById('preview-exposure').value) || 5.0;
    const gain     = parseInt(document.getElementById('preview-gain').value, 10) || 100;
    const camRole  = document.getElementById('preview-cam-select')?.value || 'main';
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Solving…';
    result.style.display = 'none';
    result.style.color = '';
    setStatus('s3-status', '');
    try {
      const data = await apiPost('/api/solver/solve', { exposure, gain, camera_role: camRole });
      if (data.success) {
        result.style.display = '';
        result.innerHTML =
          `RA: <b>${_formatRA(data.ra)}</b> &nbsp; Dec: <b>${_formatDec(data.dec)}</b>` +
          ` &nbsp; PA: ${data.pa.toFixed(1)}° &nbsp; ` +
          `<span style="color:var(--muted)">${data.solve_time_s}s</span>` +
          ` &nbsp; <button onclick="syncMount(${data.ra},${data.dec})" id="sync-btn"` +
          ` style="padding:0.1rem 0.4rem;font-size:0.75rem">Sync Mount</button>`;
        _s3SolveData = { ra: data.ra, dec: data.dec, pa: data.pa, solve_time_s: data.solve_time_s, exposure_s: exposure, gain };
        const arcBtn = document.getElementById('s3-arc-solve-btn');
        if (arcBtn && _s3ArchiveEnabled) arcBtn.disabled = false;
      } else {
        const msg = data.error || 'unknown';
        setStatus('s3-status', `Solve failed: ${msg}`, true);
        result.style.display = '';
        result.style.color = 'var(--error, #e55)';
        result.textContent = `Solve failed: ${msg}`;
      }
    } catch (err) {
      const msg = String(err);
      setStatus('s3-status', `Solve error: ${msg}`, true);
      result.style.display = '';
      result.style.color = 'var(--error, #e55)';
      result.textContent = `Solve error: ${msg}`;
    } finally {
      btn.disabled  = false;
      btn.innerHTML = 'Solve';
    }
}

async function syncMount(ra, dec) {
    const btn = document.getElementById('sync-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Syncing…'; }
    try {
      await apiPost('/api/mount/sync', { ra, dec });
      if (btn) btn.innerHTML = '✓ Synced';
      await refreshMount();
    } catch (err) {
      setStatus('s3-status', `Sync failed: ${err.message}`, true);
      if (btn) { btn.disabled = false; btn.innerHTML = 'Sync Mount'; }
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Visible Tonight — target recommendations (M4-002)
══════════════════════════════════════════════════════════════════════ */
const _OBJ_TYPE_LABELS = {
    EN: 'Nebula', RN: 'Nebula', PN: 'Plan. Neb.', SNR: 'SNR',
    GC: 'Glob. Cluster', OC: 'Open Cluster',
    SG: 'Galaxy', EG: 'Galaxy', DS: 'Double Star',
    AST: 'Asterism', MSC: 'Star Cloud',
};

async function s5LoadStoragePaths() {
    try {
        const d = await (await fetch('/api/status/storage')).json();
        const el = document.getElementById('s5-storage-paths');
        if (el) el.textContent = `Sessions: ${d.sessions_dir}`;
    } catch (_) {}
}

async function s5LoadTargets() {
    s5LoadStoragePaths();
    const dot  = document.getElementById('s5-tonight-dot');
    const list = document.getElementById('s5-tonight-list');
    dot.className = 'dot dot-yellow';
    list.innerHTML = '<span style="color:var(--muted);font-size:0.8rem">Loading…</span>';
    setStatus('s5-tonight-status', '');
    try {
      const data = await (await fetch('/api/catalog/tonight?min_altitude=20&limit=12')).json();
      if (!Array.isArray(data) || data.length === 0) {
        list.innerHTML = '<span style="color:var(--muted);font-size:0.8rem">No Messier objects above 20° right now.</span>';
        dot.className = 'dot dot-grey';
        return;
      }
      list.innerHTML = data.map(t => {
        const label = _OBJ_TYPE_LABELS[t.object_type] || t.object_type;
        const cn    = t.common_name ? ` <span style="color:var(--muted)">${escHtml(t.common_name)}</span>` : '';
        const solar = !t.solar_safe ? ' <span style="color:var(--warning);font-size:0.68rem">☀</span>' : '';
        return `<div class="tonight-row" onclick="s5UseTarget('${escHtml(t.name)}')" title="Click to use ${escHtml(t.name)}">
          <span class="tonight-name">${escHtml(t.name)}${cn}</span>
          <span class="tonight-type-chip">${label}</span>
          <span class="tonight-alt">${t.altitude_deg != null ? t.altitude_deg.toFixed(0) : '?'}°</span>
          ${solar}
        </div>`;
      }).join('');
      dot.className = 'dot dot-green';
    } catch (err) {
      setStatus('s5-tonight-status', 'Failed to load: ' + err, true);
      list.innerHTML = '';
      dot.className = 'dot dot-red';
    }
}

function s5UseTarget(name) {
    document.getElementById('s5-target').value = name;
    document.getElementById('s5-start-btn').focus();
    setStatus('s5-session-status', `Target set to ${name} — adjust settings and press Start Session.`);
}

/* ══════════════════════════════════════════════════════════════════════
     Observation Session (Stage 5)
══════════════════════════════════════════════════════════════════════ */
let _s5PollTimer  = null;
let _s5StackWs    = null;
let _s5StackDepth = 10;

const _S5_STATE_CSS = {
    IDLE:               'state-parked',
    CONNECTED:          'state-unparked',
    MOUNT_READY:        'state-unparked',
    ALIGNED:            'state-unparked',
    SLEWED:             'state-unparked',
    CENTERED:           'state-unparked',
    CENTERING_DEGRADED: 'state-at_limit',
    FOCUSING:           'state-slewing',
    PREVIEWING:         'state-slewing',
    STACKING:           'state-tracking',
    STACK_COMPLETE:     'state-tracking',
    SAVED:              'state-tracking',
    FAILED:             'state-at_limit',
};

// UX2-002: state → which step is currently active (1..5); 6 = all done
const _S5_STATE_TO_STEP = {
    IDLE: 0, CONNECTED: 1, MOUNT_READY: 1,
    ALIGNED: 2, SLEWED: 2,
    CENTERED: 3, CENTERING_DEGRADED: 3,
    FOCUSING: 4,
    PREVIEWING: 5, STACKING: 5, STACK_COMPLETE: 5, SAVED: 6,
};

// UX2-004: failure stage → which step failed (1..5)
const _S5_STAGE_TO_STEP = {
    connect: 1, initialize_mount: 1,
    align: 2, goto: 2,
    recenter: 3,
    autofocus: 4,
    preview: 5, stack: 5, save: 5,
};

const _S5_RECOVERY_ACTIONS = {
    connect:           'Check USB and serial connections, then click Retry.',
    initialize_mount:  'Verify OnStep is powered and the port is set in smart_telescope.toml.',
    align:             'Check that the mount is levelled and alignment stars are correctly identified.',
    goto:              'Target may be below the horizon, or the mount slew was interrupted.',
    recenter:          'Plate solver could not centre the target — verify the ASTAP catalog is installed.',
    autofocus:         'Focuser failed to converge — try again with "Skip autofocus" checked.',
    preview:           'Camera capture failed — check the USB connection to the camera.',
    stack:             'Stacking failed — check available disk space in the storage directory.',
    save:              'Could not save the image — check storage directory permissions.',
};

// UX2-002: update the pipeline step strip and (UX2-004) recovery banner
function _s5UpdateSteps(data) {
    const state   = data.state || 'IDLE';
    const failed  = state === 'FAILED';
    const failStep  = failed ? (_S5_STAGE_TO_STEP[data.failure_stage] || 0) : 0;
    const activeStep = failed ? 0 : (_S5_STATE_TO_STEP[state] ?? 0);

    for (let i = 1; i <= 5; i++) {
      const el     = document.getElementById(`s5-step-${i}`);
      const circle = document.getElementById(`s5-sc-${i}`);
      if (!el || !circle) continue;

      const done = activeStep >= 6 || (!failed && i < activeStep) ||
                   (failed && i < failStep);
      const active = !failed && i === activeStep;
      const fail   = failed && i === failStep;

      el.className = 's5-step' + (fail ? ' step-failed' : done ? ' step-done' : active ? ' step-active' : '');
      circle.textContent = fail ? '✗' : done ? '✓' : String(i);
    }

    // connector lines: done if the step they lead TO is done
    const stepsDone = failed ? failStep - 1 : (activeStep >= 6 ? 5 : activeStep - 1);
    for (let i = 1; i <= 4; i++) {
      const line = document.getElementById(`s5-sl-${i}`);
      if (line) line.className = 's5-step-line' + (i <= stepsDone ? ' line-done' : '');
    }

    // recovery banner (UX2-004)
    const banner = document.getElementById('s5-recovery-banner');
    if (!banner) return;
    if (failed) {
      document.getElementById('s5-recovery-reason').textContent = data.failure_reason || '';
      document.getElementById('s5-recovery-action').textContent =
        _S5_RECOVERY_ACTIONS[data.failure_stage] || 'Check device connections and click Retry.';
      banner.style.display = '';
    } else {
      banner.style.display = 'none';
    }
}

function _s5ConnectStackWs() {
    if (_s5StackWs) { _s5StackWs.close(); _s5StackWs = null; }
    const proto  = location.protocol === 'https:' ? 'wss' : 'ws';
    const ws     = new WebSocket(`${proto}://${location.host}/ws/stack`);
    ws.binaryType = 'blob';
    _s5StackWs    = ws;
    const statusEl = document.getElementById('s5-stack-ws-status');

    ws.onopen = () => {
      if (statusEl) statusEl.innerHTML =
        '<span class="ws-dot ws-live"></span><span style="color:var(--muted)">connected</span>';
    };

    ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        try {
          const d = JSON.parse(ev.data);
          const n = d.frames_integrated || 0;
          if (n > 0) {
            document.getElementById('s5-stack-preview').style.display = '';
            document.getElementById('s5-frames-text').textContent =
              `${n} / ${_s5StackDepth} frames`;
            document.getElementById('s5-progress-bar-wrap').style.display = '';
            document.getElementById('s5-progress-bar').style.width =
              Math.min(100, Math.round((n / _s5StackDepth) * 100)) + '%';
            const rej = d.frames_rejected || 0;
            if (rej > 0) {
              document.getElementById('s5-rejected-row').style.display = '';
              document.getElementById('s5-rejected-val').textContent = String(rej);
            }
            if (d.calibrated) {
              document.getElementById('s5-calibrated-row').style.display = '';
            }
          }
        } catch {}
      } else {
        const img = document.getElementById('s5-stack-img');
        const ph  = document.getElementById('s5-stack-ph');
        if (img.src?.startsWith('blob:')) URL.revokeObjectURL(img.src);
        img.src = URL.createObjectURL(ev.data);
        img.style.display = 'block';
        if (ph) ph.style.display = 'none';
      }
    };

    ws.onclose = () => {
      if (_s5StackWs === ws) _s5StackWs = null;
      if (statusEl) statusEl.innerHTML = '';
    };

    ws.onerror = () => {
      if (statusEl) statusEl.innerHTML =
        '<span class="ws-dot ws-stopped"></span><span style="color:var(--danger)">error</span>';
    };
}

function _s5DisconnectStackWs() {
    if (_s5StackWs) { _s5StackWs.close(1000, 'session ended'); _s5StackWs = null; }
}

async function s5StartSession() {
    const target   = (document.getElementById('s5-target').value || 'M42').trim();
    const profile  = document.getElementById('s5-profile').value;
    const exposure = parseFloat(document.getElementById('s5-exposure').value) || 30;
    const depth    = parseInt(document.getElementById('s5-stack-depth').value, 10) || 10;
    const skipAf   = document.getElementById('s5-skip-af').checked;
    const startBtn = document.getElementById('s5-start-btn');
    const stopBtn  = document.getElementById('s5-stop-btn');

    _s5StackDepth = depth;
    startBtn.disabled = true;
    startBtn.innerHTML = '<span class="spin"></span>Starting…';
    setStatus('s5-session-status', '');

    const params = new URLSearchParams({
      target,
      profile,
      exposure:      String(exposure),
      stack_depth:   String(depth),
      skip_autofocus: String(skipAf),
    });

    try {
      const resp = await fetch(`/api/session/run?${params}`, { method: 'POST' });
      if (!resp.ok) {
        const txt = await resp.text();
        let msg = txt;
        try {
          const d = JSON.parse(txt);
          if (d?.detail) msg = typeof d.detail === 'string' ? d.detail : JSON.stringify(d.detail);
        } catch {}
        throw new Error(msg || `Server error ${resp.status}`);
      }
      stopBtn.disabled = false;
      document.getElementById('s5-run-status').style.display = '';
      document.getElementById('s5-session-dot').className = 'dot dot-yellow';
      _s5ResetRunUI();
      setStatus('s5-session-status', `Session started — ${target}`);
      _s5StartPolling();
      _s5ConnectStackWs();
    } catch (err) {
      setStatus('s5-session-status', 'Start failed: ' + err, true);
      startBtn.disabled  = false;
      startBtn.innerHTML = '&#x25B6;&nbsp;Start Session';
    }
}

async function s5StopSession() {
    const btn = document.getElementById('s5-stop-btn');
    btn.disabled  = true;
    btn.innerHTML = '<span class="spin"></span>Stopping…';
    try {
      const resp = await fetch('/api/session/stop', { method: 'POST' });
      if (!resp.ok && resp.status !== 404) throw new Error(`Server error ${resp.status}`);
      setStatus('s5-session-status', 'Stop requested — waiting for session to finish…');
    } catch (err) {
      setStatus('s5-session-status', 'Stop failed: ' + err, true);
      btn.disabled  = false;
      btn.innerHTML = '&#x25A0;&nbsp;Stop';
    }
}

function _s5ResetRunUI() {
    _s5DisconnectStackWs();
    document.getElementById('s5-progress-bar-wrap').style.display = 'none';
    document.getElementById('s5-progress-bar').style.width = '0%';
    document.getElementById('s5-frames-text').textContent = '';
    ['s5-centering-row','s5-rejected-row','s5-calibrated-row','s5-refocus-row'].forEach(id => {
      document.getElementById(id).style.display = 'none';
    });
    const wl = document.getElementById('s5-warnings-list');
    wl.innerHTML = '';
    wl.style.display = 'none';
    document.getElementById('s5-saved-path').style.display = 'none';
    const badge = document.getElementById('s5-state-badge');
    badge.textContent = '—';
    badge.className = 'state-badge state-unknown';
    const img = document.getElementById('s5-stack-img');
    if (img.src?.startsWith('blob:')) URL.revokeObjectURL(img.src);
    img.src = '';
    img.style.display = 'none';
    document.getElementById('s5-stack-ph').style.display = '';
    document.getElementById('s5-stack-preview').style.display = 'none';
    document.getElementById('s5-stack-ws-status').innerHTML = '';
    // reset step strip and recovery banner
    for (let i = 1; i <= 5; i++) {
      const el = document.getElementById(`s5-step-${i}`);
      if (el) el.className = 's5-step';
      const c = document.getElementById(`s5-sc-${i}`);
      if (c) c.textContent = String(i);
    }
    for (let i = 1; i <= 4; i++) {
      const l = document.getElementById(`s5-sl-${i}`);
      if (l) l.className = 's5-step-line';
    }
    const banner = document.getElementById('s5-recovery-banner');
    if (banner) banner.style.display = 'none';
}

function _s5StartPolling() {
    clearInterval(_s5PollTimer);
    _s5PollTimer = setInterval(_s5Poll, 2000);
}

async function _s5Poll() {
    try {
      const data = await (await fetch('/api/session/status')).json();
      _s5UpdateUI(data);
      const done = !data.running && data.state &&
        ['SAVED', 'FAILED', 'STACK_COMPLETE'].includes(data.state);
      if (done) {
        clearInterval(_s5PollTimer);
        _s5PollTimer = null;
        _s5DisconnectStackWs();
        document.getElementById('s5-stop-btn').disabled  = true;
        document.getElementById('s5-start-btn').disabled  = false;
        document.getElementById('s5-start-btn').innerHTML = '&#x25B6;&nbsp;Start Session';
      }
    } catch { /* ignore transient network errors */ }
}

function _s5UpdateUI(data) {
    const state = data.state || 'IDLE';

    _s5UpdateSteps(data);

    const badge = document.getElementById('s5-state-badge');
    badge.textContent = state.replace(/_/g, ' ');
    badge.className   = 'state-badge ' + (_S5_STATE_CSS[state] || 'state-unknown');

    const dot = document.getElementById('s5-session-dot');
    if (state === 'SAVED' || state === 'STACK_COMPLETE') dot.className = 'dot dot-green';
    else if (state === 'FAILED') dot.className = 'dot dot-red';
    else if (data.running) dot.className = 'dot dot-yellow';

    const integrated = data.frames_integrated || 0;
    if (integrated > 0 || state === 'STACKING') {
      document.getElementById('s5-frames-text').textContent =
        `${integrated} / ${_s5StackDepth} frames`;
    }

    if (['STACKING','STACK_COMPLETE','SAVED'].includes(state)) {
      document.getElementById('s5-progress-bar-wrap').style.display = '';
      const pct = Math.min(100, Math.round((integrated / _s5StackDepth) * 100));
      document.getElementById('s5-progress-bar').style.width = pct + '%';
    }

    const offset = data.centering_offset_arcmin || 0;
    if (offset > 0) {
      document.getElementById('s5-centering-row').style.display = '';
      document.getElementById('s5-centering-val').textContent = offset.toFixed(2) + ' arcmin';
    }

    const rejected = data.frames_rejected || 0;
    if (rejected > 0) {
      document.getElementById('s5-rejected-row').style.display = '';
      document.getElementById('s5-rejected-val').textContent = String(rejected);
    }

    const refocused = data.refocus_count || 0;
    if (refocused > 0) {
      document.getElementById('s5-refocus-row').style.display = '';
      document.getElementById('s5-refocus-val').textContent = String(refocused);
    }

    const warnings = data.warnings || [];
    const warnList = document.getElementById('s5-warnings-list');
    if (warnings.length > 0) {
      warnList.style.display = '';
      warnList.innerHTML = warnings.map(w => `<li>&#x26A0;&#xFE0F; ${escHtml(w)}</li>`).join('');
    }

    const savedBox = document.getElementById('s5-saved-path');
    if (data.saved_image_path) {
      savedBox.style.display = '';
      savedBox.textContent = '✓ Saved: ' + data.saved_image_path;
    }

    if (state === 'FAILED' && data.failure_reason) {
      setStatus('s5-session-status',
        `Failed at ${data.failure_stage || '?'}: ${data.failure_reason}`, true);
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Sky Shot (Stage 5)
══════════════════════════════════════════════════════════════════════ */
let _skyshotWs = null;

