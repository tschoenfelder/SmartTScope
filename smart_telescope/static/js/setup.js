function _healthRow(label, level, value) {
    const dotCls = level === 'ok' ? 'dot-green' : level === 'warn' ? 'dot-yellow' : 'dot-red';
    return `<div class="param">
      <span class="param-label" style="display:flex;align-items:center;gap:0.35rem">
        <span class="dot ${dotCls}" style="width:7px;height:7px;flex-shrink:0"></span>${escHtml(label)}
      </span>
      <span class="param-value">${escHtml(String(value))}</span>
    </div>`;
}

function _renderHealthCard(d) {
    const params = document.getElementById('s1-health-params');
    if (!params) return;
    const rows = [];
    // Mount
    rows.push(_healthRow('Mount', d.mount.ok ? 'ok' : 'error',
      d.mount.ok ? (d.mount.state ?? 'Connected') : (d.mount.message ?? 'Error')));
    // Camera
    rows.push(_healthRow('Camera', d.camera.ok ? 'ok' : 'error',
      d.camera.ok ? 'Connected' : (d.camera.message ?? 'Error')));
    // Focuser — error when required (OnStep hardware) and not found; warn otherwise
    const focLevel = d.focuser.ok ? 'ok' : (d.focuser.required ? 'error' : 'warn');
    const focLabel = d.focuser.ok ? 'Active'
      : (d.focuser.required ? (d.focuser.message ?? 'Focuser not found — check OnStep config')
                             : 'Not found — autofocus disabled');
    rows.push(_healthRow('Focuser', focLevel, focLabel));
    // Solver
    const sLevel = d.solver.ok ? 'ok' : 'error';
    const sLabel = d.solver.ok
      ? `ASTAP ready — ${d.solver.catalog_path ?? 'catalog found'}`
      : !d.solver.astap_found ? 'ASTAP not found' : 'Star catalog (.290) not found';
    rows.push(_healthRow('Solver', sLevel, sLabel));
    // Storage
    let stLevel, stLabel;
    if (!d.storage.path) {
      stLevel = 'warn'; stLabel = 'No path configured';
    } else if (!d.storage.ok) {
      stLevel = 'error'; stLabel = d.storage.message ?? 'Error';
    } else {
      stLevel = d.storage.free_gb < 2 ? 'error' : d.storage.free_gb < 10 ? 'warn' : 'ok';
      stLabel = `${d.storage.free_gb} GB free`;
      if (d.storage.frames_capacity != null)
        stLabel += ` (~${d.storage.frames_capacity} frames)`;
    }
    rows.push(_healthRow('Storage', stLevel, stLabel));
    // CPU temperature
    if (d.cpu && d.cpu.temp_c != null) {
      const tLevel = d.cpu.temp_c > 80 ? 'error' : d.cpu.temp_c > 70 ? 'warn' : 'ok';
      rows.push(_healthRow('CPU temp', tLevel, `${d.cpu.temp_c} °C`));
    } else {
      rows.push(_healthRow('CPU temp', 'warn', '— (not available)'));
    }
    // Session
    rows.push(_healthRow('Session', d.session.running ? 'ok' : 'warn',
      d.session.running ? (d.session.state ?? 'Running') : 'Idle'));

    params.innerHTML = rows.join('');

    const dot = document.getElementById('s1-health-dot');
    if (dot) {
      const critical = d.mount.ok && d.camera.ok && d.solver.ok;
      const full     = critical && d.storage.ok;
      dot.className  = full ? 'dot dot-green' : critical ? 'dot dot-yellow' : 'dot dot-red';
    }
    const ts = document.getElementById('s1-health-ts');
    if (ts) ts.textContent = new Date().toLocaleTimeString();
}

/* ── Readiness panel (UX1) ─────────────────────────────────────────────── */

function _levelStyle(level) {
    if (level === 'green')  return { dot: 'dot-green',  color: 'var(--success)', label: 'Ready' };
    if (level === 'yellow') return { dot: 'dot-yellow', color: 'var(--warning)', label: 'Degraded' };
    return                         { dot: 'dot-red',    color: 'var(--danger)',  label: 'Not Ready' };
}

function _renderReadiness(r) {
    if (!r || !r.overall) return;
    const dot    = document.getElementById('s1-readiness-dot');
    const badge  = document.getElementById('s1-readiness-badge');
    const items  = document.getElementById('s1-readiness-items');
    if (!dot || !badge || !items) return;

    const ls = _levelStyle(r.overall);
    dot.className = `dot ${ls.dot}`;
    badge.textContent = ls.label;
    badge.style.color = ls.color;
    badge.style.borderColor = ls.color;

    const modeBadge = document.getElementById('s1-readiness-mode');
    if (modeBadge && r.mode) {
        const modeColor = r.mode === 'real' ? 'var(--success)'
                        : r.mode === 'simulator' ? 'var(--warning)'
                        : 'var(--muted)';
        modeBadge.textContent = r.mode.toUpperCase();
        modeBadge.style.color = modeColor;
        modeBadge.style.borderColor = modeColor;
        modeBadge.style.display = '';
    }

    const rows = r.items.map(item => {
      const s = _levelStyle(item.level);
      const repair = item.repair
        ? `<div style="font-size:0.75rem;color:var(--muted);margin-top:0.2rem;padding-left:1.1rem">
             ↳ ${escHtml(item.repair)}
           </div>`
        : '';
      return `<div style="padding:0.3rem 0;border-bottom:1px solid var(--border)">
        <div style="display:flex;align-items:center;gap:0.5rem">
          <span class="dot ${s.dot}" style="width:7px;height:7px;flex-shrink:0"></span>
          <span style="font-size:0.82rem;flex:1">${escHtml(item.label)}</span>
          <span style="font-size:0.78rem;color:var(--muted)">${escHtml(item.message)}</span>
        </div>${repair}
      </div>`;
    });
    items.innerHTML = rows.join('');

    // Capability chip row — only shown when at least one flag is false
    const chipEl = document.getElementById('s1-readiness-caps');
    if (chipEl) {
        const caps = [
            { key: 'can_preview',   label: 'Preview' },
            { key: 'can_goto',      label: 'GoTo' },
            { key: 'can_solve',     label: 'Solve' },
            { key: 'can_autofocus', label: 'Autofocus' },
            { key: 'can_save',      label: 'Save' },
        ];
        const blocked = caps.filter(c => r[c.key] === false);
        if (blocked.length === 0) {
            chipEl.innerHTML = '';
            chipEl.style.display = 'none';
        } else {
            chipEl.style.display = 'flex';
            chipEl.innerHTML =
                '<span style="font-size:0.72rem;color:var(--muted);margin-right:0.35rem">Blocked:</span>' +
                blocked.map(c =>
                    `<span style="font-size:0.72rem;background:var(--danger-bg,rgba(220,50,50,.12));` +
                    `color:var(--danger);border:1px solid var(--danger);border-radius:3px;` +
                    `padding:0 0.35rem;margin-right:0.25rem">${escHtml(c.label)}</span>`
                ).join('');
        }
    }
}

async function refreshReadiness() {
    try {
      const r = await (await fetch('/api/readiness')).json();
      _renderReadiness(r);
    } catch (_) {}
}

/* ── Milestone Dashboard (R7-005 / M0-008) ──────────────────────────────── */

function _milestoneDotCls(status) {
    if (status === 'green')  return 'dot-green';
    if (status === 'yellow') return 'dot-yellow';
    return 'dot-red';
}

function _renderMilestones(data) {
    const body = document.getElementById('s1-milestones-body');
    const dot  = document.getElementById('s1-milestones-dot');
    if (!body) return;

    // Overall dot: red if any red, yellow if any yellow, else green
    if (dot) {
        const hasRed    = data.milestones.some(m => m.status === 'red');
        const hasYellow = data.milestones.some(m => m.status === 'yellow');
        dot.className = 'dot ' + (hasRed ? 'dot-red' : hasYellow ? 'dot-yellow' : 'dot-green');
    }

    const rows = data.milestones.map(m => {
        const pct = m.total > 0 ? Math.round(100 * m.done / m.total) : 100;
        const barColor = m.status === 'green' ? 'var(--success)'
                       : m.status === 'yellow' ? 'var(--warning)' : 'var(--danger)';
        return `<div style="display:flex;align-items:center;gap:0.5rem;padding:0.3rem 0;border-bottom:1px solid var(--border)">
          <span class="dot ${_milestoneDotCls(m.status)}" style="width:7px;height:7px;flex-shrink:0"></span>
          <span style="font-size:0.82rem;width:2.8rem;flex-shrink:0;font-weight:600">${escHtml(m.id)}</span>
          <span style="font-size:0.80rem;flex:1;color:var(--muted)">${escHtml(m.name)}</span>
          <span style="font-size:0.78rem;color:var(--muted);width:4.5rem;text-align:right;flex-shrink:0">${m.done}/${m.total}</span>
          <div style="width:60px;height:6px;border-radius:3px;background:var(--border);flex-shrink:0;overflow:hidden">
            <div style="height:100%;width:${pct}%;background:${barColor};border-radius:3px"></div>
          </div>
        </div>`;
    });

    const riskPriBadge = p => {
        const c = p === 'P0' ? 'var(--danger)' : 'var(--warning)';
        return `<span style="font-size:0.68rem;font-weight:700;color:${c};border:1px solid ${c};
                             border-radius:3px;padding:0 0.3rem;flex-shrink:0">${escHtml(p)}</span>`;
    };
    const risks = data.top_risks.map(r =>
        `<div style="display:flex;align-items:flex-start;gap:0.4rem;padding:0.25rem 0;
                     border-bottom:1px solid var(--border);font-size:0.80rem">
          ${riskPriBadge(r.priority)}
          <span style="color:var(--muted);flex-shrink:0;min-width:4.5rem">${escHtml(r.id)}</span>
          <span style="flex:1">${escHtml(r.description)}</span>
        </div>`
    );

    body.innerHTML =
        `<div style="margin-bottom:0.4rem">${rows.join('')}</div>` +
        (risks.length
            ? `<div style="font-size:0.75rem;font-weight:600;color:var(--muted);
                          padding:0.3rem 0 0.2rem;letter-spacing:0.04em">TOP RISKS</div>` +
              risks.join('')
            : '');
}

async function refreshMilestones() {
    try {
        const d = await (await fetch('/api/milestones')).json();
        _renderMilestones(d);
    } catch (e) {
        const body = document.getElementById('s1-milestones-body');
        if (body) body.innerHTML =
            `<span style="color:var(--danger);font-size:0.82rem">Load failed: ${escHtml(String(e))}</span>`;
    }
}

async function refreshHealth() {
    try {
      const d = await (await fetch('/api/status')).json();
      _renderHealthCard(d);
      _focuserOk = d.focuser?.ok ?? false;
      _gateStates = d.mount_states?.operation_gate_states || {};
      // Re-enable proceed button if mount is already connected (survives page reload)
      if (d.mount?.ok) {
        _mountConnected = true;
        const proceedBtn = document.getElementById('s1-proceed-btn');
        if (proceedBtn) proceedBtn.disabled = false;
        unlockStage(2); unlockStage(4);
      }
      const afBtn = document.getElementById('preview-af-btn');
      if (afBtn) {
        afBtn.disabled = !_focuserOk;
        afBtn.title = _focuserOk ? 'Autofocus with preview camera' : 'Focuser not connected';
      }
      _applyGateStates();
      const focusRow = document.getElementById('s3-focus-row');
      if (focusRow) focusRow.style.display = _focuserOk ? 'flex' : 'none';
    } catch (_) {}
}

// UX5-001..004: pattern-matched error translation (mount, camera, solver, storage)

function s4PreviewStart() {
    const exp    = parseFloat(document.getElementById('s4-exposure').value) || 0.5;
    const gain   = parseInt(document.getElementById('s4-gain').value, 10)   || 100;
    const offset = parseInt(document.getElementById('s4-offset')?.value, 10) || 0;
    const ag     = document.getElementById('s4-autogain')?.checked || false;
    document.getElementById('preview-exposure').value = exp;
    document.getElementById('preview-gain').value     = gain;
    const offEl = document.getElementById('preview-offset');
    if (offEl) offEl.value = offset;
    const agEl = document.getElementById('preview-autogain-chk');
    if (agEl) agEl.checked = ag;
    // Bahtinov preview always uses the main imaging camera
    previewStart('main');
}

async function checkGpsStatus() {
    try {
        const g = await (await fetch('/api/gpsd/status')).json();
        const distRow = document.getElementById('gps-dist-row');
        const distEl  = document.getElementById('gps-dist-value');
        if (!g.available) return;
        if (g.fix_mode < 2) {
            if (distEl) distEl.textContent = 'Acquiring fix…';
            if (distRow) distRow.style.display = '';
            return;
        }
        const dist = Math.round(g.distance_m);
        if (distEl) { distEl.textContent = dist + ' m'; }
        if (distRow) distRow.style.display = '';
        if (dist > 100) {
            const applyRow = document.getElementById('gps-apply-row');
            const coords   = document.getElementById('gps-apply-coords');
            const banner   = document.getElementById('gps-banner');
            const bannerMsg = document.getElementById('gps-banner-msg');
            if (coords) coords.textContent = `${g.lat.toFixed(4)}°, ${g.lon.toFixed(4)}°`;
            if (applyRow) applyRow.style.display = '';
            if (bannerMsg) bannerMsg.textContent =
                `GPS fix: location is ${dist} m from configured observer position.`;
            if (banner) banner.style.display = 'flex';
        }
    } catch (_) {}
}

async function applyGpsLocation() {
    try {
        const g = await (await fetch('/api/gpsd/status')).json();
        if (!g.available || g.fix_mode < 2) {
            setStatus('s1-readiness-status', 'No GPS fix available', true);
            return;
        }
        await fetch('/api/observer/location', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({lat: g.lat, lon: g.lon}),
        });
        // Push the updated location (and current Pi time) to OnStep if mounted.
        // Best-effort: failure is logged but does not block the location update.
        try {
            await apiPost('/api/mount/sync_clock');
        } catch (_) {}
        await initSiteConfig();
        const banner = document.getElementById('gps-banner');
        if (banner) banner.style.display = 'none';
        const applyRow = document.getElementById('gps-apply-row');
        if (applyRow) applyRow.style.display = 'none';
        const distEl = document.getElementById('gps-dist-value');
        if (distEl) distEl.textContent = '< 1 m (applied)';
    } catch (err) {
        setStatus('s1-readiness-status', 'GPS location apply failed: ' + err.message, true);
    }
}

function s4Done() {
    completeStage(4);
    unlockStage(5);
    goToStage(5);
}

function _calSharedParams() {
    return {
      camRole: document.getElementById('preview-cam-select')?.value || 'main',
      gain   : parseInt(document.getElementById('s4-cal-gain').value,    10) || 100,
      offset : parseInt(document.getElementById('s4-cal-offset').value,  10) || 0,
    };
}

function _pollCalJob(jobId, btnId, progressId, statusId, label, resultDetail = null) {
    const btn      = document.getElementById(btnId);
    const progress = document.getElementById(progressId);
    const poll = setInterval(async () => {
      try {
        const s = await (await fetch(`/api/calibration/status/${jobId}`)).json();
        if (s.n_frames > 0) progress.textContent = `${s.frames_done} / ${s.n_frames}`;
        if (s.status === 'done') {
          clearInterval(poll);
          btn.disabled = false;
          btn.innerHTML = label;
          progress.textContent = '';
          const path  = s.result_path || '';
          const warns = (s.warnings || []).join(' ');
          const extra = resultDetail ? (resultDetail(s.result_entry) || '') : '';
          setStatus(statusId, `Saved: ${path}${extra}${warns ? ' — ' + warns : ''}`);
        } else if (s.status === 'failed') {
          clearInterval(poll);
          btn.disabled = false;
          btn.innerHTML = label;
          progress.textContent = '';
          setStatus(statusId, `${label} failed: ${s.error || 'unknown error'}`, true);
        }
      } catch (_) {}
    }, 1000);
}

async function prepareBias() {
    const btn = document.getElementById('s4-bias-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>…';
    document.getElementById('s4-bias-progress').textContent = '';
    setStatus('s4-bias-status', '');
    const { camRole, gain, offset } = _calSharedParams();
    const nFrames = parseInt(document.getElementById('s4-bias-nframes').value, 10) || 32;
    try {
      const { job_id } = await apiPost('/api/calibration/bias',
        { camera_role: camRole, n_frames: nFrames, gain, offset });
      _pollCalJob(job_id, 's4-bias-btn', 's4-bias-progress', 's4-bias-status', 'Prepare');
    } catch (err) {
      setStatus('s4-bias-status', `Failed to start: ${err}`, true);
      btn.disabled = false;
      btn.innerHTML = 'Prepare';
    }
}

async function prepareFlat() {
    const btn = document.getElementById('s4-flat-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>…';
    document.getElementById('s4-flat-progress').textContent = '';
    setStatus('s4-flat-status', '');
    const { camRole, gain, offset } = _calSharedParams();
    const nFrames  = parseInt(document.getElementById('s4-flat-nframes').value,    10) || 15;
    const initExpS = parseFloat(document.getElementById('s4-flat-init-exp').value) || 1.0;
    const train    = (document.getElementById('s4-flat-train').value  || '').trim();
    const filter   = (document.getElementById('s4-flat-filter').value || 'none').trim();
    if (!train) {
      setStatus('s4-flat-status', 'Optical train profile ID is required.', true);
      btn.disabled = false; btn.innerHTML = 'Prepare'; return;
    }
    try {
      const { job_id } = await apiPost('/api/calibration/flat', {
        camera_role: camRole, n_frames: nFrames,
        initial_exposure_s: initExpS,
        optical_train: train, filter_id: filter,
        gain, offset,
      });
      _pollCalJob(job_id, 's4-flat-btn', 's4-flat-progress', 's4-flat-status', 'Prepare');
    } catch (err) {
      setStatus('s4-flat-status', `Failed to start: ${err}`, true);
      btn.disabled = false;
      btn.innerHTML = 'Prepare';
    }
}

async function prepareDark() {
    const btn = document.getElementById('s4-dark-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>…';
    document.getElementById('s4-dark-progress').textContent = '';
    setStatus('s4-dark-status', '');
    const { camRole, gain, offset } = _calSharedParams();
    const nFrames   = parseInt(document.getElementById('s4-dark-nframes').value,  10) || 20;
    const expS      = parseFloat(document.getElementById('s4-dark-exp').value) || 120.0;
    const exposureMs = expS * 1000.0;
    try {
      const { job_id } = await apiPost('/api/calibration/dark',
        { camera_role: camRole, n_frames: nFrames, exposure_ms: exposureMs, gain, offset });
      _pollCalJob(job_id, 's4-dark-btn', 's4-dark-progress', 's4-dark-status', 'Prepare');
    } catch (err) {
      setStatus('s4-dark-status', `Failed to start: ${err}`, true);
      btn.disabled = false;
      btn.innerHTML = 'Prepare';
    }
}

async function prepareBpm() {
    const btn = document.getElementById('s4-bpm-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>…';
    document.getElementById('s4-bpm-progress').textContent = '';
    setStatus('s4-bpm-status', '');
    const { camRole, gain, offset } = _calSharedParams();
    const nFrames = parseInt(document.getElementById('s4-bpm-nframes').value, 10) || 20;
    const sigma   = parseFloat(document.getElementById('s4-bpm-sigma').value) || 5.0;
    try {
      const { job_id } = await apiPost('/api/calibration/bpm',
        { camera_role: camRole, n_frames: nFrames, gain, offset,
          hot_sigma: sigma, dead_sigma: sigma });
      _pollCalJob(job_id, 's4-bpm-btn', 's4-bpm-progress', 's4-bpm-status', 'Generate BPM',
        (result) => {
          if (!result?.n_bad) return '';
          return ` — ${result.n_bad} bad px (${result.n_hot} hot · ${result.n_dead} dead · ${result.n_noisy} noisy, ${result.bad_pct?.toFixed(3)}%)`;
        });
    } catch (err) {
      setStatus('s4-bpm-status', `Failed to start: ${err.message}`, true);
      btn.disabled = false;
      btn.innerHTML = 'Generate BPM';
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Calibration match check (FR-CAL-060 / FR-CAL-070)
══════════════════════════════════════════════════════════════════════ */
function _calMatchBadge(type, result) {
    if (!result) return '';   // not requested (e.g. dark badge when no exposure_ms)
    const colors = { MATCHED: 'var(--success)', PARTIAL: 'var(--warning)', NOT_FOUND: 'var(--danger)' };
    const labels = { MATCHED: '✓', PARTIAL: '~', NOT_FOUND: '✗' };
    const color = colors[result.status] || 'var(--muted)';
    const sym   = labels[result.status]  || '?';
    return `<span style="display:inline-flex;align-items:center;gap:0.2rem;border:1px solid ${color};
            border-radius:3px;padding:0.1rem 0.4rem;font-size:0.75rem;color:${color}">
              ${sym} ${type}
            </span>`;
}

async function checkCalibrationMatch() {
    const btn      = document.getElementById('s4-cal-match-btn');
    const rowEl    = document.getElementById('s4-cal-match-row');
    const badgesEl = document.getElementById('s4-cal-match-badges');
    const detailEl = document.getElementById('s4-cal-match-detail');

    btn.disabled = true;
    btn.textContent = '…';

    const { camRole, gain, offset } = _calSharedParams();
    const expS      = parseFloat(document.getElementById('s4-dark-exp').value) || 120.0;
    const train     = (document.getElementById('s4-flat-train').value  || '').trim() || null;
    const filter    = (document.getElementById('s4-flat-filter').value || 'none').trim() || null;

    const params = new URLSearchParams({ gain, offset, camera_role: camRole });
    if (expS)   params.set('exposure_ms', String(expS * 1000));
    if (train)  params.set('optical_train', train);
    if (filter) params.set('filter_id', filter);

    try {
      const resp = await fetch(`/api/calibration/match?${params}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const d = await resp.json();

      rowEl.innerHTML =
        _calMatchBadge('Bias', d.bias) +
        _calMatchBadge('Dark', d.dark) +
        _calMatchBadge('Flat', d.flat);
      badgesEl.style.display = '';

      const details = [];
      for (const [t, r] of [['Bias', d.bias], ['Dark', d.dark], ['Flat', d.flat]]) {
        if (r.status === 'PARTIAL') {
          const fields = r.mismatches.map(m =>
            `${m.field}: expected ${m.expected}, found ${m.actual}`).join('; ');
          details.push(`${t}: ${r.message} (${fields}) — <em>Use anyway?</em>`);
        } else if (r.status === 'NOT_FOUND') {
          details.push(`${t}: ${r.message}`);
        }
      }
      if (details.length) {
        detailEl.innerHTML = details.join('<br>');
        detailEl.style.display = '';
      } else {
        detailEl.style.display = 'none';
      }
    } catch (err) {
      rowEl.innerHTML = `<span style="color:var(--danger)">Error: ${escHtml(String(err))}</span>`;
      badgesEl.style.display = '';
      detailEl.style.display = 'none';
    } finally {
      btn.disabled = false;
      btn.textContent = 'Check';
    }
}

async function s5CheckCalibration() {
    const badgesEl = document.getElementById('s5-cal-badges');
    const detailEl = document.getElementById('s5-cal-detail');
    if (!badgesEl) return;

    const camRole = document.getElementById('preview-cam-select')?.value || 'main';
    const gain   = parseInt(document.getElementById('s4-cal-gain')?.value,  10) || 100;
    const offset = parseInt(document.getElementById('s4-cal-offset')?.value, 10) || 0;
    // Use the session exposure (science frame) for dark matching
    const expS   = parseFloat(document.getElementById('s5-exposure')?.value) || 30.0;
    // Use the session optical train profile for flat matching
    const train  = (document.getElementById('s5-profile')?.value || '').trim() || null;
    const filter = (document.getElementById('s4-flat-filter')?.value || 'none').trim() || null;

    const params = new URLSearchParams({ gain, offset, camera_role: camRole });
    if (expS)   params.set('exposure_ms', String(expS * 1000));
    if (train)  params.set('optical_train', train);
    if (filter) params.set('filter_id', filter);

    try {
      const resp = await fetch(`/api/calibration/match?${params}`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const d = await resp.json();

      badgesEl.innerHTML =
        _calMatchBadge('Bias', d.bias) +
        _calMatchBadge('Dark', d.dark) +
        _calMatchBadge('Flat', d.flat);

      const warnings = [];
      for (const [t, r] of [['Bias', d.bias], ['Dark', d.dark], ['Flat', d.flat]]) {
        if (r.status !== 'MATCHED') warnings.push(`${t}: ${r.message || r.status}`);
      }
      if (warnings.length) {
        detailEl.textContent = warnings.join(' | ');
        detailEl.style.display = '';
      } else {
        detailEl.style.display = 'none';
      }
    } catch (err) {
      badgesEl.innerHTML = `<span style="color:var(--danger);font-size:0.75rem">Check failed</span>`;
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Custom Targets — Stage 3
══════════════════════════════════════════════════════════════════════ */
const _TRACKING_LABEL = { sidereal: 'sidereal', lunar: 'lunar', satellite: 'sat' };

function starItem(t) {
    const ra  = t.ra.toFixed(4)  + ' h';
    const dec = (t.dec >= 0 ? '+' : '') + t.dec.toFixed(2) + '°';
    const mag = t.magnitude != null ? ` m${t.magnitude}` : '';
    const trk = t.tracking || 'sidereal';
    const altTxt = t.altitude_deg != null ? ` ${t.altitude_deg}°` : '';
    let visBadge = '';
    if      (t.visibility_state === 'visible_now')   visBadge = `<span class="vis-badge vis-now"  title="Currently above 10°${altTxt}">Now</span>`;
    else if (t.visibility_state === 'visible_later') visBadge = `<span class="vis-badge vis-later" title="Rises above 10° later tonight${altTxt}">Later</span>`;
    return `
      <div class="star-item" data-star-name="${escHtml(t.name)}"
           onclick="starSelect(${t.ra},${t.dec},'${escHtml(t.name)}','${escHtml(trk)}')">
        ${visBadge}
        <span class="si-name">${escHtml(t.name)}</span>
        <span class="si-common">${escHtml(t.common_name || '')}${mag}</span>
        <span class="si-coords">${ra} ${dec}</span>
        <span class="tracking-badge tracking-${trk}">${_TRACKING_LABEL[trk] || trk}</span>
        <button class="secondary"
                style="padding:0.15rem 0.45rem;font-size:0.72rem;flex-shrink:0"
                onclick="starGoto(${t.ra},${t.dec},'${escHtml(t.name)}');event.stopPropagation()"
                title="Slew mount to ${escHtml(t.name)}">GoTo</button>
        <button class="secondary"
                style="padding:0.15rem 0.45rem;font-size:0.72rem;flex-shrink:0"
                onclick="starGotoAndCenter(${t.ra},${t.dec},'${escHtml(t.name)}');event.stopPropagation()"
                title="GoTo + plate-solve until centred">&#x2316;</button>
      </div>`;
}

async function loadStars() {
    const list = document.getElementById('s3-star-list');
    setStatus('s3-stars-status', '');
    _selectedStar = null;
    document.getElementById('s3-star-goto-btn').disabled   = true;
    document.getElementById('s3-star-center-btn').disabled = true;
    try {
      const targets = await (await fetch('/api/catalog/stars')).json();
      if (!targets.length) {
        setStatus('s3-stars-status', 'stars.cfg is empty — add targets to stars.cfg.');
        list.innerHTML = '';
        return;
      }
      list.innerHTML = targets.map(starItem).join('');
    } catch (err) {
      setStatus('s3-stars-status', 'Could not load stars.cfg: ' + err, true);
    }
}

let _selectedStar = null;

function starSelect(ra, dec, name, tracking) {
    document.getElementById('goto-ra').value  = ra.toFixed(4);
    document.getElementById('goto-dec').value = dec.toFixed(4);
    const q = document.getElementById('catalog-query');
    if (q) q.value = name;
    if (tracking !== 'sidereal') {
      setStatus('s3-status',
        `Note: ${name} uses ${tracking} tracking — set mount rate manually after slew.`);
    }
    _selectedStar = { ra, dec, name, tracking };
    document.querySelectorAll('#s3-star-list .star-item').forEach(el => el.classList.remove('selected'));
    const row = document.querySelector(`#s3-star-list [data-star-name="${CSS.escape(name)}"]`);
    if (row) row.classList.add('selected');
    document.getElementById('s3-star-goto-btn').disabled   = false;
    document.getElementById('s3-star-center-btn').disabled = false;
}

function starGotoSelected() {
    if (!_selectedStar) return;
    starGoto(_selectedStar.ra, _selectedStar.dec, _selectedStar.name);
}

function starCenterSelected() {
    if (!_selectedStar) return;
    starGotoAndCenter(_selectedStar.ra, _selectedStar.dec, _selectedStar.name);
}

async function starGoto(ra, dec, name) {
    setStatus('s3-stars-status', '');
    setStatus('s3-status', '');
    try {
      await apiPost('/api/mount/goto', { ra, dec });
      document.getElementById('s3-proceed-btn').disabled = false;
      document.getElementById('s3-proceed-btn').title = '';
      unlockStage(4);
      setStatus('s3-stars-status', `Slewing to ${name}…`);
      await watchSlew('s3-stars-status', name);
      // Auto-start live preview so the user can see the star immediately after the slew.
      previewStart();
    } catch (err) {
      let msg = `GoTo ${name} failed: ${err.message}`;
      try {
        const d = JSON.parse(err.message);
        if (d?.error === 'solar_exclusion')
          msg = `${name} is too close to the Sun (${d.sun_separation_deg}° sep).`;
        else if (d?.error === 'mount_limit')
          msg = `${name} outside mount limits (${d.reason}).`;
      } catch {}
      setStatus('s3-stars-status', msg, true);
    }
}

async function mountGotoAndCenter() {
    const ra  = parseFloat(document.getElementById('goto-ra')?.value);
    const dec = parseFloat(document.getElementById('goto-dec')?.value);
    if (isNaN(ra) || isNaN(dec)) {
      setStatus('s3-center-status', 'Enter RA and Dec first', true);
      return;
    }
    const camIdx = _trainCamIdx(document.getElementById('preview-cam-select')?.value || 'main');
    const btn = document.getElementById('s3-center-btn');
    if (btn) btn.disabled = true;
    setStatus('s3-center-status', `Centring RA ${ra.toFixed(3)} h  Dec ${dec.toFixed(2)}°…`);
    try {
      const result = await apiPost('/api/mount/goto_and_center',
        { ra, dec, tolerance_arcmin: 2.0, max_iterations: 3, camera_index: camIdx });
      if (result.success) {
        setStatus('s3-center-status',
          `Centred ✓ — ${result.iterations} iter, offset ${result.offset_arcmin.toFixed(2)} arcmin`);
        document.getElementById('s3-proceed-btn').disabled = false;
        document.getElementById('s3-proceed-btn').title = '';
        unlockStage(4);
        await refreshMount();
      } else {
        setStatus('s3-center-status',
          `Centring failed — ${result.offset_arcmin.toFixed(2)} arcmin${result.error ? ': ' + result.error : ''}`, true);
      }
    } catch (err) {
      let msg = `Center failed: ${err.message}`;
      try {
        const d = JSON.parse(err.message);
        if (d?.error === 'solar_exclusion') msg = 'Too close to the Sun — choose a different target.';
        else if (d?.error === 'mount_limit') msg = `Outside mount limits (${d.reason}).`;
      } catch {}
      setStatus('s3-center-status', msg, true);
    } finally {
      if (btn) btn.disabled = false;
    }
}

async function starGotoAndCenter(ra, dec, name) {
    setStatus('s3-stars-status', `Centring ${name}…`);
    setStatus('s3-status', '');
    setStatus('s3-center-status', '');
    try {
      const camIdx = _trainCamIdx(document.getElementById('preview-cam-select')?.value || 'main');
      const result = await apiPost('/api/mount/goto_and_center',
        { ra, dec, tolerance_arcmin: 2.0, max_iterations: 3, camera_index: camIdx });
      if (result.success) {
        setStatus('s3-stars-status',
          `${name} centred ✓ — ${result.iterations} iter, offset ${result.offset_arcmin.toFixed(2)} arcmin`);
        document.getElementById('s3-proceed-btn').disabled = false;
        document.getElementById('s3-proceed-btn').title = '';
        unlockStage(4);
        await refreshMount();
      } else {
        setStatus('s3-stars-status',
          `${name} centring failed — offset ${result.offset_arcmin.toFixed(2)} arcmin${result.error ? ': ' + result.error : ''}`, true);
      }
    } catch (err) {
      let msg = `Center ${name} failed: ${err.message}`;
      try {
        const d = JSON.parse(err.message);
        if (d?.error === 'solar_exclusion') msg = `${name} too close to the Sun.`;
        else if (d?.error === 'mount_limit') msg = `${name} outside mount limits (${d.reason}).`;
      } catch {}
      setStatus('s3-stars-status', msg, true);
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Catalog search
══════════════════════════════════════════════════════════════════════ */
let _catalogTimer = null;

function catalogSearch() {
    clearTimeout(_catalogTimer);
    const q          = document.getElementById('catalog-query')?.value.trim();
    const observable = document.getElementById('catalog-observable')?.checked;
    const container  = document.getElementById('catalog-results');
    if (!q || q.length < 1) { if (container) container.innerHTML = ''; return; }
    _catalogTimer = setTimeout(async () => {
      try {
        let url = `/api/catalog/search?q=${encodeURIComponent(q)}&limit=8`;
        if (observable) url += '&min_altitude=20';
        const items = await (await fetch(url)).json();
        if (!items.length) {
          container.innerHTML = '<div class="catalog-dropdown"><div class="catalog-item" style="color:var(--muted)">No results</div></div>';
          return;
        }
        container.innerHTML = `<div class="catalog-dropdown">${
          items.map(it => {
            const altStr = it.altitude_deg !== null
              ? `<span style="font-size:0.72rem;color:${it.altitude_deg >= 20 ? 'var(--success)' : 'var(--warning)'}">↑${it.altitude_deg.toFixed(0)}°</span>`
              : '';
            return `
              <div class="catalog-item"
                   onclick="catalogSelect(${it.ra_hours},${it.dec_deg},'${escHtml(it.name)}')">
                <span class="ci-name">${escHtml(it.name)}</span>
                <span class="ci-common">${escHtml(it.common_name)}</span>
                <span class="ci-coords">${it.ra_hours.toFixed(3)}h ${it.dec_deg >= 0 ? '+' : ''}${it.dec_deg.toFixed(2)}°</span>
                ${altStr}
              </div>`;
          }).join('')
        }</div>`;
      } catch { if (container) container.innerHTML = ''; }
    }, 200);
}

function catalogSelect(ra, dec, name) {
    document.getElementById('goto-ra').value  = ra.toFixed(4);
    document.getElementById('goto-dec').value = dec.toFixed(4);
    const q = document.getElementById('catalog-query');
    if (q) q.value = name;
    document.getElementById('catalog-results').innerHTML = '';
}

document.addEventListener('click', (ev) => {
    if (!ev.target.closest('#catalog-results') && !ev.target.closest('#catalog-query')) {
      const c = document.getElementById('catalog-results');
      if (c) c.innerHTML = '';
    }
});

/* ══════════════════════════════════════════════════════════════════════
     Focuser — Stage 4
══════════════════════════════════════════════════════════════════════ */

function _coolingRenderStatus(d) {
    const dot        = document.getElementById('s1-cooling-dot');
    const badge      = document.getElementById('s1-cooling-badge');
    const tempEl     = document.getElementById('s1-cooling-temp');
    const fill       = document.getElementById('s1-cooling-power-fill');
    const pctEl      = document.getElementById('s1-cooling-power-pct');
    const countdown  = document.getElementById('s1-cooling-countdown');
    const warnRow    = document.getElementById('s1-cooling-warn-row');
    const warnMsg    = document.getElementById('s1-cooling-warn-msg');
    const enableBtn  = document.getElementById('s1-cooling-enable-btn');
    const disableBtn = document.getElementById('s1-cooling-disable-btn');
    if (!dot) return;

    if (!d.enabled) {
      dot.className = 'dot dot-grey';
      badge.textContent = '—';
      badge.style.borderColor = 'var(--border)';
      tempEl.textContent = '—';
      fill.style.width = '0%';
      pctEl.textContent = '—';
      if (countdown) countdown.style.display = 'none';
      if (warnRow) warnRow.style.display = 'none';
      if (enableBtn)  enableBtn.style.display = '';
      if (disableBtn) disableBtn.style.display = 'none';
      return;
    }

    // Temperature
    tempEl.textContent = d.current_temp_c !== null
      ? `${d.current_temp_c.toFixed(1)} °C` : '—';

    // Power gauge
    const pct = d.power_pct ?? 0;
    fill.style.width = `${Math.min(100, pct)}%`;
    pctEl.textContent = d.power_pct !== null ? `${pct.toFixed(0)}%` : '—';
    if (pct > 80)      fill.style.background = 'var(--danger)';
    else if (pct > 75) fill.style.background = 'var(--warning)';
    else               fill.style.background = 'var(--success)';

    // Action badge
    const action = d.action ?? '—';
    badge.textContent = action;
    if (d.stable) {
      dot.className = 'dot dot-green';
      badge.style.borderColor = 'var(--success)';
      badge.style.color = 'var(--success)';
    } else if (action === 'WARN' || action === 'RAISE_TARGET') {
      dot.className = 'dot dot-yellow';
      badge.style.borderColor = 'var(--warning)';
      badge.style.color = 'var(--warning)';
    } else {
      dot.className = 'dot dot-grey';
      badge.style.borderColor = 'var(--border)';
      badge.style.color = 'var(--text)';
    }

    // Countdown
    if (countdown) {
      if (!d.stable && d.seconds_remaining !== null && d.seconds_remaining > 0) {
        const mins = Math.floor(d.seconds_remaining / 60);
        const secs = Math.round(d.seconds_remaining % 60);
        countdown.textContent = mins > 0
          ? `Stabilising: ${mins}m ${secs}s remaining`
          : `Stabilising: ${secs}s remaining`;
        countdown.style.display = '';
      } else {
        countdown.style.display = 'none';
      }
    }

    // Warning message
    if (warnRow && warnMsg) {
      if (d.warning_msg) {
        warnMsg.textContent = d.warning_msg;
        warnRow.style.display = '';
      } else {
        warnRow.style.display = 'none';
      }
    }

    // Buttons
    if (enableBtn)  enableBtn.style.display  = 'none';
    if (disableBtn) disableBtn.style.display = '';
}

async function onCoolingCamChange(role) {
    const idx = _trainCamIdx(role);
    try {
      const caps = await (await fetch(`/api/cameras/${idx}/capabilities`)).json();
      const coolingCard = document.getElementById('s1-cooling-card');
      if (coolingCard) coolingCard.style.display = caps.has_tec ? '' : 'none';
    } catch (_) {}
}

async function coolingRefreshStatus() {
    try {
      const d = await (await fetch('/api/cooling/status')).json();
      _coolingRenderStatus(d);
    } catch (_) {}
}

async function coolingEnable() {
    const btn   = document.getElementById('s1-cooling-enable-btn');
    const camSel = document.getElementById('s1-cooling-cam-select');
    const tgtEl = document.getElementById('s1-cooling-target');
    const cameraIndex = camSel ? _trainCamIdx(camSel.value || 'main') : 0;
    const targetC     = tgtEl  ? parseFloat(tgtEl.value)    : -10.0;
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Enabling…'; }
    try {
      const r = await fetch('/api/cooling/set_target', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({camera_index: cameraIndex, target_c: targetC, enabled: true}),
      });
      if (!r.ok) {
        const err = await r.json().catch(() => ({detail: r.statusText}));
        alert(`Cooling error: ${err.detail ?? r.statusText}`);
        return;
      }
      if (_coolingPollInterval) clearInterval(_coolingPollInterval);
      _coolingPollInterval = setInterval(coolingRefreshStatus, 30_000);
      await coolingRefreshStatus();
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = 'Enable Cooling'; }
    }
}

async function coolingDisable() {
    const btn = document.getElementById('s1-cooling-disable-btn');
    if (btn) { btn.disabled = true; btn.innerHTML = '<span class="spin"></span>Disabling…'; }
    try {
      await fetch('/api/cooling/set_target', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: false}),
      });
      if (_coolingPollInterval) { clearInterval(_coolingPollInterval); _coolingPollInterval = null; }
      _coolingRenderStatus({enabled: false});
    } finally {
      if (btn) { btn.disabled = false; btn.innerHTML = 'Disable Cooling'; }
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Connect All (Stage 1)
══════════════════════════════════════════════════════════════════════ */
async function connectAll() {
    const btn  = document.getElementById('connect-all-btn');
    const dot  = document.getElementById('connect-dot');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Connecting…';
    try {
      const data = await apiPost('/api/session/connect');
      const grid = document.getElementById('connect-status-grid');
      // time_location_status/time_location_check aren't DeviceResult-shaped —
      // Stage 1's Time/Location Verification card is the live source of truth for those.
      const deviceEntries = Object.entries(data).filter(
        ([k]) => k !== 'time_location_status' && k !== 'time_location_check'
      );
      grid.innerHTML = deviceEntries.map(([device, info]) => {
        const ok  = info.status === 'ok';
        const msg = ok ? 'Connected' : (info.error || 'Failed');
        return `
          <div class="param">
            <span class="param-label" style="display:flex;align-items:center;gap:0.4rem">
              <span class="dot ${ok ? 'dot-green' : 'dot-red'}"
                    style="width:7px;height:7px"></span>${escHtml(device)}
            </span>
            <span class="param-value" style="font-size:0.8rem">${escHtml(msg)}</span>
          </div>`;
      }).join('');

      const mountOk = data['mount']?.status  === 'ok';
      const camOk   = data['camera']?.status === 'ok';
      _mountConnected = mountOk;

      if (dot) dot.className = (mountOk && camOk) ? 'dot dot-green' : 'dot dot-yellow';
      if (mountOk) { unlockStage(2); unlockStage(4); }
      if (camOk)   unlockStage(5);
      const scBtn = document.getElementById('setup-check-btn');
      if (scBtn) scBtn.disabled = !(mountOk && camOk);
      const proceedBtn = document.getElementById('s1-proceed-btn');
      if (proceedBtn) proceedBtn.disabled = !mountOk;

      // Probe focuser only when mount connected (focuser shares mount serial port)
      const focuserDot  = document.getElementById('s1-focuser-dot');
      const focuserText = document.getElementById('s1-focuser-status-text');
      if (!mountOk) {
        if (focuserDot)  focuserDot.className  = 'dot dot-grey';
        if (focuserText) focuserText.textContent = 'Mount not connected';
      } else {
        try {
          const fd = await apiPost('/api/focuser/connect');
          if (fd.available) {
            if (focuserDot)  focuserDot.className  = 'dot dot-green';
            if (focuserText) focuserText.textContent = 'Focuser active';
            // Show current position
            try {
              const fs = await (await fetch('/api/focuser/status')).json();
              const posRow = document.getElementById('s1-focuser-pos-row');
              const posEl  = document.getElementById('s1-focuser-pos');
              if (posRow) posRow.style.display = '';
              if (posEl)  posEl.textContent = fs.max_position
                ? `${fs.position} / ${fs.max_position} steps`
                : `${fs.position} steps`;
            } catch (_) {}
          } else {
            if (focuserDot)  focuserDot.className  = 'dot dot-yellow';
            if (focuserText) focuserText.textContent = 'Not found — autofocus disabled';
          }
        } catch (_) {
          if (focuserDot)  focuserDot.className  = 'dot dot-red';
          if (focuserText) focuserText.textContent = 'Focuser probe failed';
        }
        await loadFocuserCameras();
      }

      // Refresh all camera selects regardless of mount state — cameras are
      // independent of the mount and may enumerate correctly even without it.
      _loadSelectFromTrains('s1-cooling-cam-select').then(async sel => {
        if (sel) await onCoolingCamChange(sel.value || 'main');
      });
      loadPreviewCameras();
      _loadSelectFromTrains('pa-cam-select').then(sel => {
        if (sel) onPaCamChange(sel.value || 'main');
      });

      await refreshMount();
      await refreshReadiness();
    } catch (err) {
      if (dot) dot.className = 'dot dot-red';
      setStatus('s1-mount-status', 'Connect All failed: ' + err, true);
      const proceedBtn = document.getElementById('s1-proceed-btn');
      if (proceedBtn) proceedBtn.disabled = true;
      _mountConnected = false;
    } finally {
      btn.disabled  = false;
      btn.innerHTML = 'Connect All';
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Setup Check Wizard
══════════════════════════════════════════════════════════════════════ */
let _scRunning = false;

function _scStep(icon, text) {
    const div = document.createElement('div');
    div.style.cssText = 'display:flex;align-items:flex-start;gap:0.5rem;padding:0.2rem 0;border-bottom:1px solid var(--border)';
    div.innerHTML = `<span style="min-width:1.3rem;text-align:center;line-height:1.9">${icon}</span><span>${escHtml(text)}</span>`;
    document.getElementById('setup-check-steps').appendChild(div);
    return div;
}

function _scUpdate(div, icon, text) {
    div.innerHTML = `<span style="min-width:1.3rem;text-align:center;line-height:1.9">${icon}</span><span>${escHtml(text)}</span>`;
}

function _scConfirm(message) {
    return new Promise(resolve => {
      const div = document.createElement('div');
      div.style.cssText = 'padding:0.3rem 0 0.3rem 1.8rem;display:flex;align-items:center;gap:0.5rem;flex-wrap:wrap;background:var(--surface);border-radius:4px;margin:0.2rem 0';
      div.innerHTML = `<span style="font-size:0.82rem;flex:1">${escHtml(message)}</span>
        <button style="padding:0.18rem 0.6rem;font-size:0.8rem">Confirm</button>
        <button class="secondary" style="padding:0.18rem 0.6rem;font-size:0.8rem">Skip</button>`;
      document.getElementById('setup-check-steps').appendChild(div);
      div.querySelector('button:not(.secondary)').onclick = () => { div.remove(); resolve(true); };
      div.querySelector('button.secondary').onclick      = () => { div.remove(); resolve(false); };
      div.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
}

async function _scWaitSlew(maxMs = 120000) {
    const deadline = Date.now() + maxMs;
    while (Date.now() < deadline) {
      await new Promise(r => setTimeout(r, 1000));
      try {
        const ms = await (await fetch('/api/mount/status')).json();
        if (ms.state !== 'slewing') return ms;
      } catch {}
    }
    return null;
}

async function runSetupCheck() {
    if (_scRunning) return;
    _scRunning = true;
    const panel    = document.getElementById('setup-check-panel');
    const steps    = document.getElementById('setup-check-steps');
    const closeBtn = document.getElementById('setup-check-close');
    panel.style.display = 'block';
    steps.innerHTML = '';
    closeBtn.disabled = true;
    panel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    let pass = 0, fail = 0, warn = 0;
    const mark = icon => { if (icon==='✓') pass++; else if (icon==='✗') fail++; else warn++; return icon; };

    // ── 1. Focuser ──────────────────────────────────────────────────────────
    try {
      const fs = await (await fetch('/api/focuser/status')).json();
      if (!fs.available) {
        _scStep(mark('⚠'), 'Focuser: not connected — skipped');
      } else {
        const orig  = fs.position;
        const maxP  = fs.max_position || 50000;
        const delta = Math.min(500, Math.max(50, Math.round(maxP * 0.02)));
        const d = _scStep('⏳', `Focuser: nudging ±${delta} steps from position ${orig}…`);
        const r1 = await apiPost('/api/focuser/nudge', { delta });
        if (r1.started === false) {
          _scUpdate(d, mark('✗'), `Focuser: motor did not start — check OnStep focuser wiring`);
        } else {
          await new Promise(r => setTimeout(r, 2500));
          const fs2 = await (await fetch('/api/focuser/status')).json();
          if (Math.abs(fs2.position - orig) < 1) {
            _scUpdate(d, mark('✗'), `Focuser: did not move (still at ${fs2.position})`);
          } else {
            await apiPost('/api/focuser/nudge', { delta: -delta });
            await new Promise(r => setTimeout(r, 2500));
            const fs3 = await (await fetch('/api/focuser/status')).json();
            const ok  = Math.abs(fs3.position - orig) <= Math.max(5, delta * 0.05);
            _scUpdate(d, mark(ok ? '✓' : '⚠'),
              ok ? `Focuser: moved and returned ✓ (pos ${fs3.position})`
                 : `Focuser: returned to ${fs3.position} (expected ~${orig})`);
          }
        }
      }
    } catch (err) {
      _scStep(mark('✗'), `Focuser: ${err.message}`);
    }

    // ── 2. Mount RA ─────────────────────────────────────────────────────────
    try {
      let ms = await (await fetch('/api/mount/status')).json();
      if (!ms.ra || ms.state === 'unknown') {
        _scStep(mark('⚠'), 'Mount RA: mount not connected (state unknown) — use Connect All to reconnect');
      } else {
        if (ms.state === 'parked') {
          const doUnpark = await _scConfirm('Mount is parked. Unpark to test RA movement?');
          if (!doUnpark) {
            _scStep(mark('⚠'), 'Mount RA: mount is parked — skipped by user');
            ms = null;
          } else {
            try {
              await apiPost('/api/mount/unpark');
              ms = await (await fetch('/api/mount/status')).json();
            } catch (uErr) {
              _scStep(mark('✗'), `Mount RA: unpark failed — ${uErr.message}`);
              ms = null;
            }
            if (ms && ms.state === 'parked') {
              _scStep(mark('✗'), 'Mount RA: still parked after unpark — skipped');
              ms = null;
            }
          }
        }
        if (ms != null) {
          const go = await _scConfirm(
            'Mount RA test: will slew +40 arcmin east. Ensure telescope has clearance.');
          if (!go) {
            _scStep(mark('⚠'), 'Mount RA: skipped by user');
          } else {
            const origRA  = ms.ra;
            const origDec = ms.dec;
            const d = _scStep('⏳', 'Mount RA: slewing +40 arcmin…');
            try {
              await apiPost('/api/mount/goto', { ra: origRA + 40 / 60 / 15, dec: origDec });
              await _scWaitSlew();
              _scUpdate(d, '⏳', 'Mount RA: did the telescope move?');
              const back = await _scConfirm('Did the mount move visibly? Confirm to slew back to start.');
              if (!back) {
                _scUpdate(d, mark('✗'), 'Mount RA: user reports no visible movement');
              } else {
                _scUpdate(d, '⏳', 'Mount RA: returning to original position…');
                await apiPost('/api/mount/goto', { ra: origRA, dec: origDec });
                await _scWaitSlew();
                _scUpdate(d, mark('✓'), 'Mount RA: slewed and returned ✓');
              }
            } catch (gErr) {
              _scUpdate(d, mark('✗'), `Mount RA: ${gErr.message}`);
            }
          }
        }
      }
    } catch (err) {
      _scStep(mark('✗'), `Mount: ${err.message}`);
    }

    // ── 3. Mount DEC ────────────────────────────────────────────────────────
    try {
      let ms3 = await (await fetch('/api/mount/status')).json();
      if (!ms3.dec || ms3.state === 'unknown' || ms3.state === 'parked') {
        const _ms3Reason = ms3.state === 'unknown'
          ? 'mount not connected — use Connect All to reconnect'
          : `state is '${ms3.state}'`;
        _scStep(mark('⚠'), `Mount DEC: ${_ms3Reason} — skipped`);
      } else {
        const go3 = await _scConfirm(
          'Mount DEC test: will slew +40 arcmin north. Ensure telescope has clearance.');
        if (!go3) {
          _scStep(mark('⚠'), 'Mount DEC: skipped by user');
        } else {
          const origRA3  = ms3.ra;
          const origDec3 = ms3.dec;
          const d3 = _scStep('⏳', 'Mount DEC: slewing +40 arcmin north…');
          try {
            await apiPost('/api/mount/goto', { ra: origRA3, dec: origDec3 + 40 / 60 });
            await _scWaitSlew();
            _scUpdate(d3, '⏳', 'Mount DEC: did the telescope move?');
            const back3 = await _scConfirm('Did the mount move visibly in DEC? Confirm to slew back to start.');
            if (!back3) {
              _scUpdate(d3, mark('✗'), 'Mount DEC: user reports no visible movement');
            } else {
              _scUpdate(d3, '⏳', 'Mount DEC: returning to original position…');
              await apiPost('/api/mount/goto', { ra: origRA3, dec: origDec3 });
              await _scWaitSlew();
              _scUpdate(d3, mark('✓'), 'Mount DEC: slewed and returned ✓');
            }
          } catch (gErr3) {
            _scUpdate(d3, mark('✗'), `Mount DEC: ${gErr3.message}`);
          }
        }
      }
    } catch (err) {
      _scStep(mark('✗'), `Mount DEC: ${err.message}`);
    }

    // ── 4. Camera capture + plate solve ──────────────────────────────────────
    try {
      const solverSt = await (await fetch('/api/solver/status')).json();
      const hasSolver = !!solverSt.ready;
      const camData  = await (await fetch('/api/cameras')).json();
      if (!camData.sdk_available || !camData.cameras?.length) {
        _scStep(mark('⚠'), 'Cameras: none detected — skipped');
      } else {
        const solvedPositions = [];  // { label, ra, dec }
        for (const cam of camData.cameras) {
          const d = _scStep('⏳', `Camera ${cam.display_label}: capturing 2 s test frame…`);
          try {
            const r = await apiPost('/api/solver/solve',
              { exposure: 2.0, gain: 200, camera_index: cam.sdk_index });
            if (r.success) {
              solvedPositions.push({ label: cam.display_label, ra: r.ra, dec: r.dec });
              _scUpdate(d, mark('✓'),
                `Camera ${cam.display_label}: captured + solved — RA ${r.ra.toFixed(2)} h  Dec ${r.dec.toFixed(1)}°`);
            } else if (hasSolver) {
              _scUpdate(d, mark('⚠'),
                `Camera ${cam.display_label}: captured ✓ — plate solve failed (lens cap on?)`);
            } else {
              _scUpdate(d, mark('✓'),
                `Camera ${cam.display_label}: captured ✓ (no solver installed — install ASTAP for plate solve)`);
            }
          } catch (cErr) {
            _scUpdate(d, mark('✗'), `Camera ${cam.display_label}: ${cErr.message}`);
          }
        }
        // Cross-camera pointing consistency: if ≥2 cameras solved, check they agree within 5°
        if (solvedPositions.length >= 2) {
          const ref = solvedPositions[0];
          let allAgree = true;
          for (let i = 1; i < solvedPositions.length; i++) {
            const other = solvedPositions[i];
            const dRa  = Math.abs(ref.ra  - other.ra)  * 15;  // deg
            const dDec = Math.abs(ref.dec - other.dec);
            const sep  = Math.sqrt(dRa * dRa + dDec * dDec);
            if (sep > 5.0) {
              _scStep(mark('⚠'),
                `Camera pointing mismatch: ${ref.label} vs ${other.label} — separation ${sep.toFixed(1)}° (should be < 5°)`);
              allAgree = false;
            }
          }
          if (allAgree) {
            _scStep(mark('✓'), `Camera pointing consistent: all ${solvedPositions.length} cameras agree within 5°`);
          }
        }
      }
    } catch (err) {
      _scStep(mark('✗'), `Cameras: ${err.message}`);
    }

    // ── 5. Optional home ────────────────────────────────────────────────────
    const goHome = await _scConfirm(
      'Setup check complete. Move mount to OnStep home position?');
    if (goHome) {
      const d = _scStep('⏳', 'Mount: slewing to home…');
      try {
        await apiPost('/api/mount/home');
        await _scWaitSlew();
        _scUpdate(d, mark('✓'), 'Mount: at home position ✓');
      } catch (hErr) {
        _scUpdate(d, mark('✗'), `Mount home: ${hErr.message}`);
      }
    }

    // ── Summary ──────────────────────────────────────────────────────────────
    const icon = fail === 0 ? (warn === 0 ? '✓' : '⚠') : '✗';
    _scStep(icon,
      `Setup check done — ${pass} passed · ${fail} failed · ${warn} warning${warn !== 1 ? 's' : ''}`);
    closeBtn.disabled = false;
    _scRunning = false;
}

/* ══════════════════════════════════════════════════════════════════════
     RA / Dec formatters (shared)
══════════════════════════════════════════════════════════════════════ */
function _formatRA(hours) {
    const h = Math.floor(hours);
    const m = Math.floor((hours - h) * 60);
    const s = ((hours - h - m / 60) * 3600).toFixed(1);
    return `${h}h ${String(m).padStart(2,'0')}m ${String(s).padStart(4,'0')}s`;
}

function _formatDec(deg) {
    const sign = deg >= 0 ? '+' : '−';
    const abs  = Math.abs(deg);
    const d    = Math.floor(abs);
    const m    = Math.floor((abs - d) * 60);
    const s    = Math.round((abs - d - m / 60) * 3600);
    return `${sign}${d}° ${String(m).padStart(2,'0')}′ ${String(s).padStart(2,'0')}″`;
}

/* ══════════════════════════════════════════════════════════════════════
     Live Preview WebSocket (shared — feeds Stage 3 and Stage 4)
══════════════════════════════════════════════════════════════════════ */
let _ws             = null;
let _frameCount     = 0;
let _reconnect      = true;
let _reconnectTimer = null;
let _histEnabled    = false;
let _histInterval   = null;


function updateElevationLabel() {
    document.getElementById('elevation-label').textContent =
      ` °  →  Dec ≈ ${skyDec().toFixed(1)}°`;
}
function skyDec() {
    const el = parseFloat(document.getElementById('skyshot-elevation').value) || 80;
    return el - 90 + _observerLat;
}

async function skyGoto() {
    const el  = parseFloat(document.getElementById('skyshot-elevation').value) || 80;
    const btn = document.getElementById('skyshot-goto-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Slewing…';
    setStatus('s5-skyshot-status', '');
    try {
      const data = await (await fetch(`/api/mount/goto_sky?elevation=${el}`, { method: 'POST' })).json();
      if (data.error) throw new Error(JSON.stringify(data));
      document.getElementById('skyshot-ra').textContent  = data.ra.toFixed(4)  + ' h';
      document.getElementById('skyshot-dec').textContent = data.dec.toFixed(4) + ' °';
      document.getElementById('skyshot-dot').className = 'dot dot-green';
      document.getElementById('skyshot-frame').style.display = '';
      document.getElementById('skyshot-snap-btn').disabled = false;
      setStatus('s5-skyshot-status',
        `Slewing to RA ${data.ra.toFixed(3)} h  Dec ${data.dec.toFixed(2)}° — wait for mount to settle`);
      await refreshMount();
    } catch (err) {
      setStatus('s5-skyshot-status', 'GoTo sky failed: ' + err, true);
      document.getElementById('skyshot-dot').className = 'dot dot-red';
    } finally {
      btn.disabled  = false;
      btn.innerHTML = 'GoTo Sky';
    }
}

function skySnap() {
    if (_skyshotWs) { _skyshotWs.close(); _skyshotWs = null; }
    const btn = document.getElementById('skyshot-snap-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Snapping…';
    setStatus('s5-skyshot-status', '');
    const exposure = 2.0;
    const proto    = location.protocol === 'https:' ? 'wss' : 'ws';
    _skyshotWs = new WebSocket(`${proto}://${location.host}/ws/preview?exposure=${exposure}`);
    _skyshotWs.binaryType = 'blob';
    _skyshotWs.onmessage = (ev) => {
      if (typeof ev.data === 'string') return; // skip histogram JSON
      const img = document.getElementById('skyshot-img');
      const ph  = document.getElementById('skyshot-placeholder');
      if (img.src?.startsWith('blob:')) URL.revokeObjectURL(img.src);
      img.src = URL.createObjectURL(ev.data);
      img.style.display = 'block';
      ph.style.display  = 'none';
      document.getElementById('skyshot-snap-count').textContent = 'Frame captured';
      setStatus('s5-skyshot-status', 'Frame captured successfully.');
      _skyshotWs.close();
      _skyshotWs = null;
    };
    _skyshotWs.onerror = () => {
      setStatus('s5-skyshot-status', 'Snap failed — WebSocket error', true);
      btn.disabled  = false;
      btn.innerHTML = 'Snap';
    };
    _skyshotWs.onclose = () => {
      btn.disabled  = false;
      btn.innerHTML = 'Snap';
    };
}

async function skyPark() {
    const btn = document.getElementById('skyshot-park-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Parking…';
    try {
      await apiPost('/api/mount/park');
      setStatus('s5-skyshot-status', 'Mount parked.');
      document.getElementById('skyshot-dot').className = 'dot dot-grey';
      document.getElementById('skyshot-snap-btn').disabled = true;
      await refreshMount();
    } catch (err) {
      setStatus('s5-skyshot-status', 'Park failed: ' + err, true);
    } finally {
      btn.disabled  = false;
      btn.innerHTML = 'Park after Snap';
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Cameras (Stage 5)
══════════════════════════════════════════════════════════════════════ */
async function scan() {
    const btn  = document.getElementById('scan-btn');
    const grid = document.getElementById('s5-camera-grid');
    setStatus('s5-camera-status', '');
    grid.innerHTML = '';
    btn.disabled  = true;
    btn.innerHTML = '<span class="spin"></span>Scanning…';
    try {
      const resp = await fetch('/api/cameras');
      if (!resp.ok) throw new Error(`Server error ${resp.status}`);
      const data = await resp.json();
      if (!data.sdk_available) {
        setStatus('s5-camera-status',
          'ToupTek SDK not available. Download toupcam.py and the native library from touptek.com and place on the Python path.',
          true);
        return;
      }
      const n = data.cameras.length;
      if (n === 0) {
        setStatus('s5-camera-status', 'No cameras found. Check USB connections and try again.');
        return;
      }
      setStatus('s5-camera-status', `${n} camera${n !== 1 ? 's' : ''} found.`);
      grid.innerHTML = data.cameras.map(cameraCard).join('');
    } catch (err) {
      setStatus('s5-camera-status', String(err), true);
    } finally {
      btn.disabled  = false;
      btn.innerHTML = 'Scan';
    }
}

function cameraCard(cam) {
    const resStr  = cam.resolutions.map(r => `${r[0]}×${r[1]}`).join(', ');
    const [px, py] = cam.pixel_size_um;
    const pxStr   = px === py ? `${px.toFixed(2)} µm` : `${px.toFixed(2)}×${py.toFixed(2)} µm`;
    const idDisp  = cam.id.length > 24 ? cam.id.slice(0,24) + '…' : cam.id;
    const features = [
      cam.has_mono  ? 'Monochrome' : 'Colour',
      cam.usb3      ? 'USB 3.0'   : 'USB 2.0',
      cam.has_raw16   && 'RAW 16-bit',
      cam.has_tec     && 'TEC Cooler',
      cam.has_fan     && 'Cooling Fan',
    ].filter(Boolean).map(f => `<span class="badge">${f}</span>`).join('');

    const isNew    = !cam.role;
    const dotCls   = isNew ? 'dot-yellow' : 'dot-green';
    const roleBadge = isNew
        ? `<span class="badge badge-warn">Not in config</span>`
        : `<span class="badge badge-ok">Role: ${escHtml(cam.role)}</span>`;
    const snippetBlock = (isNew && cam.toml_snippet) ? `
        <details class="snippet-details">
          <summary>Suggested config snippet — click to expand</summary>
          <pre class="snippet-code">${escHtml(cam.toml_snippet)}</pre>
          <button class="btn-sm btn-copy" onclick="csSnipcopy(this)">Copy</button>
        </details>` : '';

    return `
      <div class="card${isNew ? ' card-warn' : ''}">
        <div class="card-title">
          <span class="dot ${dotCls}"></span>
          ${escHtml(cam.display_name)}
          ${roleBadge}
        </div>
        <div class="params">
          <div class="param">
            <span class="param-label">Model</span>
            <span class="param-value">${escHtml(cam.model_name)}</span>
          </div>
          <div class="param">
            <span class="param-label">Pixel size</span>
            <span class="param-value">${pxStr}</span>
          </div>
          <div class="param">
            <span class="param-label">Preview resolutions</span>
            <span class="param-value">${resStr || '—'}</span>
          </div>
          <div class="param">
            <span class="param-label">Camera ID</span>
            <span class="param-value mono">${escHtml(idDisp)}</span>
          </div>
        </div>
        <div class="features">${features}</div>
        ${snippetBlock}
      </div>`;
}

function csSnipcopy(btn) {
    const pre = btn.previousElementSibling;
    navigator.clipboard.writeText(pre.textContent).then(() => {
        btn.textContent = 'Copied!';
        setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
    }).catch(() => {
        btn.textContent = 'Copy failed';
        setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
    });
}

/* ── Extended Setup Check ─────────────────────────────────────────────── */

const _extStepLabels = {
    focuser_move: 'Focuser Move',
    mount_slew:   'Mount Slew',
    plate_solve:  'Plate Solve',
    home_return:  'Home Return',
};

function _extSetBusy(busy) {
    ['focuser', 'slew', 'solve', 'home'].forEach(k => {
        const btn = document.getElementById(`s1-ext-btn-${k}`);
        if (btn) btn.disabled = busy;
    });
    const allBtn = document.getElementById('s1-ext-check-all-btn');
    if (allBtn) allBtn.disabled = busy;
}

function _extRenderStep(key, data) {
    const ok    = data.ok;
    const dot   = ok ? 'dot-green' : 'dot-red';
    const label = _extStepLabels[key] || key;
    const msg   = escHtml(data.message || '');
    let detail  = '';
    if (key === 'focuser_move' && data.before != null) {
        detail = ` <span style="color:var(--muted);font-size:0.72rem">${data.before} → ${data.after} (Δ${data.delta > 0 ? '+' : ''}${data.delta})</span>`;
    } else if (key === 'mount_slew' && data.elapsed_s != null) {
        detail = ` <span style="color:var(--muted);font-size:0.72rem">${data.elapsed_s} s</span>`;
    } else if (key === 'plate_solve' && data.per_camera) {
        detail = ' ' + data.per_camera.map(c => {
            const cls = c.solved ? 'badge-ok' : 'badge-warn';
            return `<span class="badge ${cls}">${escHtml(c.role)}: ${c.solved ? '✓' : '✗'}</span>`;
        }).join(' ');
    } else if (key === 'home_return' && data.elapsed_s != null) {
        detail = ` <span style="color:var(--muted);font-size:0.72rem">${data.elapsed_s} s</span>`;
    }
    return `<div style="display:flex;align-items:center;gap:0.4rem;padding:0.25rem 0;font-size:0.82rem">
        <span class="dot ${dot}" style="flex-shrink:0"></span>
        <span style="min-width:7rem">${label}</span>
        <span>${msg}${detail}</span>
      </div>`;
}

async function extCheckStep(step) {
    _extSetBusy(true);
    setStatus('s1-ext-check-status', `Running ${_extStepLabels[step]}…`);
    try {
        const data = await apiPost(`/api/setup/${step}`, {});
        const box  = document.getElementById('s1-ext-check-results');
        // Replace or append the row for this step
        const id = `ext-row-${step}`;
        const html = `<div id="${id}">${_extRenderStep(step, data)}</div>`;
        const existing = document.getElementById(id);
        if (existing) existing.outerHTML = html;
        else box.insertAdjacentHTML('beforeend', html);
        setStatus('s1-ext-check-status', '');
        _updateExtDot();
    } catch (err) {
        setStatus('s1-ext-check-status', `${_extStepLabels[step]}: ${err}`, true);
    } finally {
        _extSetBusy(false);
    }
}

async function extCheckRunAll() {
    _extSetBusy(true);
    setStatus('s1-ext-check-status', 'Running all checks…');
    const box = document.getElementById('s1-ext-check-results');
    box.innerHTML = '';
    try {
        const data = await apiPost('/api/setup/run_all', {});
        for (const [key, result] of Object.entries(data.steps)) {
            box.insertAdjacentHTML('beforeend',
                `<div id="ext-row-${key}">${_extRenderStep(key, result)}</div>`);
        }
        const p = data.passed, t = data.total;
        setStatus('s1-ext-check-status', p === t
            ? `All ${t} checks passed`
            : `${p}/${t} checks passed — see details above`);
        _updateExtDot();
    } catch (err) {
        setStatus('s1-ext-check-status', String(err), true);
    } finally {
        _extSetBusy(false);
    }
}

function _updateExtDot() {
    const rows = document.querySelectorAll('#s1-ext-check-results [class*="dot-"]');
    const dot  = document.getElementById('s1-ext-check-dot');
    if (!dot || rows.length === 0) return;
    const hasRed = [...rows].some(el => el.classList.contains('dot-red'));
    dot.className = `dot ${hasRed ? 'dot-red' : 'dot-green'}`;
}

/* ══════════════════════════════════════════════════════════════════════
     Stage 1 — Time / Location Verification card (M8-010 / REQ-TIME-005)
══════════════════════════════════════════════════════════════════════ */

function _tlParam(label, value, level) {
    if (level !== undefined) return _healthRow(label, level, value ?? '—');
    return `<div class="param">
      <span class="param-label">${escHtml(label)}</span>
      <span class="param-value mono">${escHtml(String(value ?? '—'))}</span>
    </div>`;
}

function _renderStage1TL(d) {
    const dot   = document.getElementById('s1-tl-dot');
    const badge = document.getElementById('s1-tl-badge');
    const params = document.getElementById('s1-tl-params');
    const controls = document.getElementById('s1-tl-controls');
    if (!dot || !badge || !params) return;

    // Overall badge / dot
    const tl = d.onstep_time_location;
    const dotCls = tl === 'VERIFIED' ? 'dot-green' : tl === 'UNVERIFIED' ? 'dot-yellow' : 'dot-grey';
    dot.className = `dot ${dotCls}`;
    const badgeColor = tl === 'VERIFIED' ? 'var(--success)' : tl === 'UNVERIFIED' ? 'var(--warning)' : 'var(--muted)';
    badge.textContent = tl;
    badge.style.color = badgeColor;
    badge.style.borderColor = badgeColor;

    const fmtDelta = (v, tol, unit) => {
        if (v == null) return '—';
        const ok = v <= tol;
        const color = ok ? 'var(--success)' : 'var(--danger)';
        return `<span style="color:${color}">${Number(v).toFixed(1)}${unit} / ${tol}${unit} tol</span>`;
    };

    const fmtCoord = (v) => v != null ? Number(v).toFixed(6) + '°' : '—';
    const fmtTime  = (s) => s ? s.replace('T', ' ') : '—';
    const fmtTs    = (s) => s ? new Date(s).toLocaleString() : '— (not yet run)';

    const rows = [
        // Adapter
        _tlParam('Adapter connection', d.adapter_connection_state,
            d.adapter_connection_state === 'OPEN' ? 'ok' : 'error'),
        _tlParam('Adapter health', d.adapter_health_state,
            d.adapter_health_state === 'OK' ? 'ok' : d.adapter_health_state === 'UNKNOWN' ? 'warn' : 'error'),
        // Trust
        _tlParam('Raspberry Pi trust', d.raspberry_time_trust,
            d.raspberry_time_trust === 'TRUSTED' ? 'ok' : 'error'),
        _tlParam('Trust source', d.raspberry_trust_source,
            ['GPSD_FIX','NTP','ONSTEP_COMPARISON','USER_CONFIRMED'].includes(d.raspberry_trust_source) ? 'ok' : 'error'),
        _tlParam('Master source', d.master_source,
            d.master_source === 'FALLBACK' || d.master_source === 'STUB' ? 'warn' : 'ok'),
        // Verification
        _tlParam('Verification result', tl,
            tl === 'VERIFIED' ? 'ok' : tl === 'UNVERIFIED' ? 'warn' : 'error'),
        // Time
        _tlParam('OnStep time', fmtTime(d.onstep_time_local)),
        _tlParam('Master time (Pi)', fmtTime(d.master_time_local)),
        `<div class="param">
          <span class="param-label">Time delta</span>
          <span class="param-value">${fmtDelta(d.time_delta_s, d.time_tolerance_s, 's')}</span>
        </div>`,
        // Location
        _tlParam('OnStep lat', fmtCoord(d.onstep_lat)),
        _tlParam('OnStep lon', fmtCoord(d.onstep_lon)),
        _tlParam('Master lat', fmtCoord(d.master_lat)),
        _tlParam('Master lon', fmtCoord(d.master_lon)),
        `<div class="param">
          <span class="param-label">Location delta</span>
          <span class="param-value">${fmtDelta(d.location_delta_m, d.location_tolerance_m, 'm')}</span>
        </div>`,
        // Tolerances summary
        _tlParam('Active tolerances',
            `${d.time_tolerance_s}s / ${d.location_tolerance_m}m`),
        // Timestamps
        _tlParam('Last verified', fmtTs(d.last_verification_at_utc)),
        _tlParam('Last pushed',   fmtTs(d.last_push_at_utc)),
    ];
    params.innerHTML = rows.join('');

    // Action buttons
    if (controls) {
        controls.style.display = 'flex';
        const pushBtn    = document.getElementById('s1-tl-push-btn');
        const confirmBtn = document.getElementById('s1-tl-confirm-btn');
        if (pushBtn)    pushBtn.style.display    = d.available_actions.includes('push_to_onstep')           ? '' : 'none';
        if (confirmBtn) confirmBtn.style.display = d.available_actions.includes('confirm_raspberry_time')   ? '' : 'none';
    }
}

async function refreshStage1TL() {
    try {
        const d = await (await fetch('/api/stage1/time-location')).json();
        _renderStage1TL(d);
    } catch (_) {}
}

async function stage1PushClock() {
    setStatus('s1-tl-status', 'Pushing time/location to OnStep…');
    try {
        await apiPost('/api/mount/sync_clock');
        setStatus('s1-tl-status', 'Push succeeded — refreshing…');
        await refreshStage1TL();
        if (typeof refreshMount === 'function') await refreshMount();
        setStatus('s1-tl-status', '');
    } catch (e) { setStatus('s1-tl-status', e.message, true); }
}

async function stage1ConfirmTime() {
    setStatus('s1-tl-status', 'Confirming Pi clock…');
    try {
        await apiPost('/api/mount/confirm_time');
        setStatus('s1-tl-status', 'Pi clock confirmed — trust source: USER_CONFIRMED');
        await refreshStage1TL();
    } catch (e) { setStatus('s1-tl-status', e.message, true); }
}

// ── Command History card (M8-012 / REQ-API-003) ──────────────────────────────

const _CMD_STATUS_COLOR = {
    REQUESTED: 'var(--muted)',
    ISSUED:    'var(--accent)',
    RUNNING:   'var(--accent)',
    SUCCEEDED: 'var(--ok)',
    REJECTED:  'var(--warn)',
    FAILED:    'var(--err)',
    CANCELLED: 'var(--muted)',
};

function _renderCommandHistory(records) {
    const list    = document.getElementById('s1-cmd-list');
    const counter = document.getElementById('s1-cmd-count');
    if (!list) return;
    if (!counter) return;
    counter.textContent = records.length;
    if (records.length === 0) {
        list.innerHTML = '<span style="color:var(--muted)">No commands recorded yet.</span>';
        return;
    }
    const rows = [...records].reverse().slice(0, 50).map(r => {
        const color  = _CMD_STATUS_COLOR[r.status] || 'var(--fg)';
        const ts     = r.timestamp ? r.timestamp.replace('T', ' ') : '—';
        const action = escHtml(r.user_action || r.operation || '—');
        const status = escHtml(r.status);
        const msg    = r.human_message ? ` — ${escHtml(r.human_message)}` : '';
        return `<div style="display:flex;gap:0.5rem;padding:0.18rem 0;border-bottom:1px solid var(--border)">
          <span style="color:var(--muted);white-space:nowrap;min-width:6.5rem">${escHtml(ts)}</span>
          <span style="min-width:5rem">${action}</span>
          <span style="color:${color};min-width:5.5rem;font-weight:500">${status}</span>
          <span style="color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${msg}</span>
        </div>`;
    }).join('');
    list.innerHTML = rows;
}

async function refreshCommandHistory() {
    try {
        const d = await (await fetch('/api/commands')).json();
        _renderCommandHistory(d.commands || []);
    } catch (_) {}
}

/* ══════════════════════════════════════════════════════════════════════
     Init
══════════════════════════════════════════════════════════════════════ */

