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
    _stopAutoRemeasure();
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

    // Measurement metrics panel
    _updateCollimMetrics(s.last_measurement);

    // Session report (COMPLETE state)
    _updateCollimReport(s.state);

    // Buttons and controls
    const cameraRoleSel = document.getElementById('s4-wiz-camera-role');
    if (cameraRoleSel) cameraRoleSel.style.display = idle ? '' : 'none';
    _wizBtn('s4-wiz-start-btn',      idle);
    _wizBtn('s4-wiz-pause-btn',      (active || waiting) && !terminal);
    _wizBtn('s4-wiz-resume-btn',     paused);
    _wizBtn('s4-wiz-cancel-btn',     !idle && !terminal);
    _wizBtn('s4-wiz-retry-btn',      terminal);
    _wizBtn('s4-wiz-best-star-btn',  selectStar);
    _wizBtn('s4-wiz-next-btn',       waiting && !selectStar && !validateState,
            guideState ? 'Remeasure' : 'Next');
    _wizBtn('s4-wiz-finish-btn',     guideState,
            s.state === 'guide_rough_collimation' ? 'Finish Rough' : 'Finish Fine');
    _wizBtn('s4-wiz-accept-btn',     validateState);
    _wizBtn('s4-wiz-more-btn',       validateState);

    // Auto-remeasure label (guidance states only)
    const autoLabel = document.getElementById('s4-wiz-auto-remeasure-label');
    if (autoLabel) {
        autoLabel.style.display = guideState ? 'flex' : 'none';
        if (!guideState) _stopAutoRemeasure();
    }
}

function _show(id, visible) {
    const el = document.getElementById(id);
    if (el) el.style.display = visible ? '' : 'none';
}

function _text(id, t) {
    const el = document.getElementById(id);
    if (el) el.textContent = t;
}

function _updateCollimMetrics(meas) {
    const panel = document.getElementById('s4-wiz-metrics');
    if (!panel) return;
    if (!meas || !meas.measurement_type) {
        panel.style.display = 'none';
        return;
    }
    panel.style.display = 'flex';
    _show('s4-wiz-metric-error', false);
    _show('s4-wiz-metric-focus', false);
    _show('s4-wiz-metric-fwhm',  false);

    _text('s4-wiz-metric-type', meas.measurement_type);
    _text('s4-wiz-metric-conf',
        meas.confidence != null ? `conf ${(meas.confidence * 100).toFixed(0)}%` : '');

    if (meas.measurement_type === 'donut' && meas.donut) {
        const d = meas.donut;
        _show('s4-wiz-metric-error', true);
        _text('s4-wiz-metric-err-val', `${d.error_magnitude_px.toFixed(1)} px`);
        const pct = (d.error_fraction * 100).toFixed(1);
        const colour = d.is_collimated ? 'var(--green,#4caf50)' :
                       d.error_fraction < 0.10 ? 'var(--accent)' : 'var(--red,#e53935)';
        const pctEl = document.getElementById('s4-wiz-metric-err-pct');
        if (pctEl) { pctEl.textContent = `(${pct}% of ring)`; pctEl.style.color = colour; }
    } else if (meas.measurement_type === 'spikes' && meas.spikes) {
        const sp = meas.spikes;
        _show('s4-wiz-metric-focus', true);
        _text('s4-wiz-metric-foc-val', sp.focus_error_px.toFixed(2));
        _text('s4-wiz-metric-foc-rms', `${sp.crossing_error_rms_px.toFixed(2)} px`);
    }

    if (meas.star) {
        _show('s4-wiz-metric-fwhm', true);
        _text('s4-wiz-metric-fwhm-val', meas.star.fwhm_px.toFixed(1));
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Frame Archive Browser (COL-ARC UI)
══════════════════════════════════════════════════════════════════════ */

let _arcOpen   = false;
let _s3ArcOpen = false;

// Stage 3 pending archive data (populated after successful GoTo/Solve/AF)
let _s3ArchiveEnabled = false;
let _s3GotoData  = null;
let _s3SolveData = null;
let _s3AfData    = null;

async function archiveToggle() {
    _arcOpen = !_arcOpen;
    const body    = document.getElementById('s4-archive-body');
    const chevron = document.getElementById('s4-arc-chevron');
    if (body)    body.style.display    = _arcOpen ? '' : 'none';
    if (chevron) chevron.textContent   = _arcOpen ? '▼' : '▶';
    if (_arcOpen) await archiveLoad();
}

async function archiveLoad() {
    const status = document.getElementById('s4-arc-status');
    const list   = document.getElementById('s4-arc-sessions');
    const dot    = document.getElementById('s4-arc-dot');
    const badge  = document.getElementById('s4-arc-badge');
    if (status) status.textContent = 'Loading…';
    try {
        const r = await fetch('/api/collimation/archive');
        const d = await r.json();
        if (!d.enabled) {
            if (status) status.textContent = 'Archive disabled — set [collimation.archive] enabled = true in config.toml';
            if (dot)   dot.className = 'dot dot-grey';
            if (badge) { badge.textContent = 'Disabled'; badge.className = 'state-badge state-unknown'; }
            if (list)  list.innerHTML = '';
            return;
        }
        if (status) status.textContent = '';
        if (dot)   dot.className = 'dot dot-green';
        if (badge) {
            badge.textContent = `${d.sessions.length} session${d.sessions.length !== 1 ? 's' : ''}`;
            badge.className = 'state-badge state-tracking';
        }
        if (list) list.innerHTML = d.sessions.length === 0
            ? '<p style="color:var(--muted);font-size:0.83rem">No archived sessions yet.</p>'
            : d.sessions.map(s => _arcSessionHtml(s)).join('');
    } catch (e) {
        if (status) status.textContent = `Error: ${e.message}`;
    }
}

function _arcSessionHtml(s) {
    const counts = Object.entries(s.state_counts || {})
        .map(([st, n]) => `${n}× ${st.replace('measure_', '')}`)
        .join(', ');
    const kb = (s.size_bytes / 1024).toFixed(0);
    const shortId = s.session_id.slice(0, 8);
    return `<details style="margin-bottom:0.4rem;border:1px solid var(--border);
                             border-radius:4px;padding:0.3rem 0.5rem"
                      onToggle="if(this.open) archiveLoadFrames(this, '${escHtml(s.session_id)}')">
      <summary style="cursor:pointer;font-size:0.83rem;list-style:none;display:flex;
                       gap:0.6rem;align-items:center">
        <span style="font-family:monospace">${escHtml(shortId)}…</span>
        <span style="color:var(--muted)">${s.frame_count} frame${s.frame_count !== 1 ? 's' : ''}</span>
        ${counts ? `<span style="color:var(--muted);font-size:0.75rem">(${escHtml(counts)})</span>` : ''}
        <span style="margin-left:auto;color:var(--muted);font-size:0.75rem">${kb} KB</span>
      </summary>
      <div class="arc-frames" style="margin-top:0.4rem"></div>
    </details>`;
}

async function archiveLoadFrames(details, sessionId) {
    const container = details.querySelector('.arc-frames');
    if (!container || container.dataset.loaded) return;
    container.dataset.loaded = '1';
    container.innerHTML = '<span style="color:var(--muted);font-size:0.8rem">Loading frames…</span>';
    try {
        const r = await fetch(`/api/collimation/archive/${encodeURIComponent(sessionId)}`);
        const d = await r.json();
        if (!d.frames || d.frames.length === 0) {
            container.innerHTML = '<span style="color:var(--muted);font-size:0.8rem">No frames.</span>';
            return;
        }
        container.innerHTML = `<table style="width:100%;font-size:0.78rem;border-collapse:collapse">
          <tr style="color:var(--muted);text-align:left">
            <th style="padding:0.15rem 0.3rem">Frame</th>
            <th style="padding:0.15rem 0.3rem">State</th>
            <th style="padding:0.15rem 0.3rem">Captured</th>
            <th style="padding:0.15rem 0.3rem">Size</th>
            <th style="padding:0.15rem 0.3rem"></th>
          </tr>
          ${d.frames.map(f => _arcFrameRow(sessionId, f)).join('')}
        </table>`;
    } catch (e) {
        container.innerHTML = `<span style="color:var(--red,#e53935);font-size:0.8rem">Error: ${escHtml(e.message)}</span>`;
    }
}

function _arcFrameRow(sessionId, f) {
    const ts  = (f.captured_at || f.tagged_at || '').slice(0, 19).replace('T', ' ') || '—';
    const kb  = f.size_bytes ? (f.size_bytes / 1024).toFixed(0) + ' KB' : '—';
    const act = f.has_fits !== false
        ? `<button class="secondary" style="font-size:0.72rem;padding:0.1rem 0.4rem"
                   onclick="archiveReplay(this, '${escHtml(sessionId)}', '${escHtml(f.frame_stem)}')">
             Replay
           </button>`
        : `<span style="font-size:0.72rem;color:var(--muted)">tag</span>`;
    return `<tr style="border-top:1px solid var(--border)">
      <td style="padding:0.15rem 0.3rem;font-family:monospace">${escHtml(f.frame_stem)}</td>
      <td style="padding:0.15rem 0.3rem">${escHtml(f.state || '—')}</td>
      <td style="padding:0.15rem 0.3rem;color:var(--muted)">${ts}</td>
      <td style="padding:0.15rem 0.3rem;color:var(--muted)">${kb}</td>
      <td style="padding:0.15rem 0.3rem">${act}</td>
    </tr>
    <tr id="arc-replay-${escHtml(f.frame_stem)}" style="display:none">
      <td colspan="5" style="padding:0.2rem 0.5rem 0.4rem;font-size:0.78rem"></td>
    </tr>`;
}

async function archiveReplay(btn, sessionId, frameStem) {
    const resultRow = document.getElementById(`arc-replay-${frameStem}`);
    if (!resultRow) return;
    const cell = resultRow.querySelector('td');
    btn.disabled = true;
    btn.textContent = '…';
    resultRow.style.display = '';
    if (cell) cell.textContent = 'Running replay…';
    try {
        const r = await fetch(
            `/api/collimation/archive/${encodeURIComponent(sessionId)}/${encodeURIComponent(frameStem)}/replay`,
            { method: 'POST' }
        );
        const d = await r.json();
        if (!r.ok) {
            if (cell) cell.textContent = `Error ${r.status}: ${d.detail || ''}`;
            return;
        }
        const orig    = d.original || {};
        const replayed = d.replayed || {};
        const keys    = [...new Set([...Object.keys(orig), ...Object.keys(replayed)])];
        const rows    = keys.map(k => {
            const o = orig[k]     != null ? (typeof orig[k]     === 'number' ? orig[k].toFixed(3)     : orig[k])     : '—';
            const n = replayed[k] != null ? (typeof replayed[k] === 'number' ? replayed[k].toFixed(3) : replayed[k]) : '—';
            const changed = String(o) !== String(n);
            return `<tr ${changed ? 'style="color:var(--accent)"' : ''}>
              <td style="padding:0.1rem 0.3rem;color:var(--muted)">${escHtml(k)}</td>
              <td style="padding:0.1rem 0.3rem">${escHtml(String(o))}</td>
              <td style="padding:0.1rem 0.3rem">${escHtml(String(n))}</td>
            </tr>`;
        }).join('');
        if (cell) cell.innerHTML = `
          <table style="font-size:0.77rem;border-collapse:collapse">
            <tr style="color:var(--muted)">
              <th style="padding:0.1rem 0.3rem;text-align:left">Field</th>
              <th style="padding:0.1rem 0.3rem;text-align:left">Original</th>
              <th style="padding:0.1rem 0.3rem;text-align:left">Replayed</th>
            </tr>
            ${rows}
          </table>`;
    } catch (e) {
        if (cell) cell.textContent = `Error: ${e.message}`;
    } finally {
        btn.disabled = false;
        btn.textContent = 'Replay';
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Stage 3 Archive (GoTo / Solve / AF tagging)
══════════════════════════════════════════════════════════════════════ */

async function _s3CheckArchiveEnabled() {
    try {
        const r = await fetch('/api/collimation/archive');
        const d = await r.json();
        _s3ArchiveEnabled = d.enabled === true;
        const badge = document.getElementById('s3-arc-badge');
        const dot   = document.getElementById('s3-arc-dot');
        if (_s3ArchiveEnabled) {
            if (badge) { badge.textContent = `${d.sessions.length} session${d.sessions.length !== 1 ? 's' : ''}`; badge.className = 'state-badge state-tracking'; }
            if (dot)   dot.className = 'dot dot-green';
        } else {
            if (badge) { badge.textContent = 'Disabled'; badge.className = 'state-badge state-unknown'; }
            if (dot)   dot.className = 'dot dot-grey';
        }
        _updateS3ArcButtons();
    } catch (_) {}
}

async function s3ArchiveToggle() {
    _s3ArcOpen = !_s3ArcOpen;
    const body    = document.getElementById('s3-archive-body');
    const chevron = document.getElementById('s3-arc-chevron');
    if (body)    body.style.display  = _s3ArcOpen ? '' : 'none';
    if (chevron) chevron.textContent = _s3ArcOpen ? '▼' : '▶';
    if (_s3ArcOpen) await s3ArchiveLoad();
}

async function s3ArchiveLoad() {
    const status = document.getElementById('s3-arc-status');
    const list   = document.getElementById('s3-arc-sessions');
    const dot    = document.getElementById('s3-arc-dot');
    const badge  = document.getElementById('s3-arc-badge');
    if (status) status.textContent = 'Loading…';
    try {
        const r = await fetch('/api/collimation/archive');
        const d = await r.json();
        if (!d.enabled) {
            if (status) status.textContent = 'Archive disabled — set [collimation.archive] enabled = true in config.toml';
            if (dot)   dot.className = 'dot dot-grey';
            if (badge) { badge.textContent = 'Disabled'; badge.className = 'state-badge state-unknown'; }
            if (list)  list.innerHTML = '';
            _s3ArchiveEnabled = false;
            _updateS3ArcButtons();
            return;
        }
        _s3ArchiveEnabled = true;
        _updateS3ArcButtons();
        if (status) status.textContent = '';
        if (dot)   dot.className = 'dot dot-green';
        if (badge) {
            badge.textContent = `${d.sessions.length} session${d.sessions.length !== 1 ? 's' : ''}`;
            badge.className = 'state-badge state-tracking';
        }
        if (list) list.innerHTML = d.sessions.length === 0
            ? '<p style="color:var(--muted);font-size:0.83rem">No archived sessions yet.</p>'
            : d.sessions.map(s => _arcSessionHtml(s)).join('');
    } catch (e) {
        if (status) status.textContent = `Error: ${e.message}`;
    }
}

function _updateS3ArcButtons() {
    const gotoBtn  = document.getElementById('s3-arc-goto-btn');
    const solveBtn = document.getElementById('s3-arc-solve-btn');
    const afBtn    = document.getElementById('s3-arc-af-btn');
    if (gotoBtn)  gotoBtn.disabled  = !(_s3ArchiveEnabled && _s3GotoData);
    if (solveBtn) solveBtn.disabled = !(_s3ArchiveEnabled && _s3SolveData);
    if (afBtn)    afBtn.disabled    = !(_s3ArchiveEnabled && _s3AfData);
}

async function s3ArchiveTag(type) {
    let data = null;
    if (type === 'goto'  && _s3GotoData)  data = { ..._s3GotoData };
    if (type === 'solve' && _s3SolveData) data = { ..._s3SolveData };
    if (type === 'af'    && _s3AfData)    data = { ..._s3AfData };
    if (!data) return;
    try {
        await apiPost('/api/collimation/archive/tag', { tag_type: type, data });
        // Clear the pending data so the button disables again
        if (type === 'goto')  _s3GotoData  = null;
        if (type === 'solve') _s3SolveData = null;
        if (type === 'af')    _s3AfData    = null;
        _updateS3ArcButtons();
        // Refresh the archive list if open
        if (_s3ArcOpen) await s3ArchiveLoad();
        setStatus('s3-status', `${type} result saved to archive`);
    } catch (err) {
        setStatus('s3-status', `Archive save failed: ${err.message}`, true);
    }
}

// ── Session report on COMPLETE ────────────────────────────────────────────────

let _reportFetched = false;

async function _updateCollimReport(state) {
    const panel = document.getElementById('s4-wiz-report');
    const body  = document.getElementById('s4-wiz-report-body');
    if (!panel || !body) return;
    if (state !== 'complete') {
        panel.style.display = 'none';
        _reportFetched = false;
        return;
    }
    panel.style.display = '';
    if (_reportFetched) return;
    _reportFetched = true;
    try {
        const r = await (await fetch('/api/collimation/report')).json();
        const dur = (r.started_at && r.finished_at)
            ? `${Math.round(r.finished_at - r.started_at)} s` : '—';
        const fwhmRow = (r.initial_focus_fwhm_px != null || r.final_focus_fwhm_px != null)
            ? `<div>FWHM: ${r.initial_focus_fwhm_px != null ? r.initial_focus_fwhm_px.toFixed(1) + ' px' : '—'}
               → ${r.final_focus_fwhm_px != null ? r.final_focus_fwhm_px.toFixed(1) + ' px' : '—'}</div>` : '';
        const errRow = r.final_donut_error_px != null
            ? `<div>Final donut error: <strong>${r.final_donut_error_px.toFixed(1)} px</strong>
               (${escHtml(r.final_donut_status || '')})</div>` : '';
        const warnRows = (r.warnings || []).map(w =>
            `<div style="color:var(--accent)">⚠ ${escHtml(w)}</div>`).join('');
        const statusColour = r.overall_status === 'complete' ? 'var(--green,#4caf50)' :
                             r.overall_status === 'acceptable' ? 'var(--accent)' : 'var(--muted)';
        body.innerHTML = `
          <div><strong style="color:${statusColour}">${escHtml(r.overall_status || '—')}</strong>
               &nbsp;·&nbsp; Duration: ${escHtml(dur)}
               ${r.selected_star ? `&nbsp;·&nbsp; Star: ${escHtml(r.selected_star)}` : ''}</div>
          ${fwhmRow}${errRow}${warnRows}`;
    } catch (e) {
        body.innerHTML = `<span style="color:var(--muted)">Report unavailable: ${escHtml(e.message)}</span>`;
    }
}

// ── Auto-remeasure in guidance phases ─────────────────────────────────────────

let _autoRemeasureTimer = null;

function _stopAutoRemeasure() {
    if (_autoRemeasureTimer) { clearInterval(_autoRemeasureTimer); _autoRemeasureTimer = null; }
    const cb = document.getElementById('s4-wiz-auto-remeasure');
    if (cb) cb.checked = false;
}

function collimAutoRemeasureToggle(enabled) {
    if (enabled) {
        _autoRemeasureTimer = setInterval(() => collimNext(false), 5000);
    } else {
        _stopAutoRemeasure();
    }
}

// ── "Use Best Star" quick-select ──────────────────────────────────────────────

async function collimUseBestStar() {
    const list = document.getElementById('s4-star-list');
    if (!list) return;
    // First item in the list is the brightest magnitude star; read ra/dec from its onclick
    const firstItem = list.querySelector('.star-item');
    if (!firstItem) {
        setStatus('s4-status', 'No stars in list — load stars first', true);
        return;
    }
    // Extract onclick args: collimSelect(ra, dec, 'name')
    const onclick = firstItem.getAttribute('onclick') || '';
    const m = onclick.match(/collimSelect\(([\d.]+),([-\d.]+)/);
    if (!m) {
        setStatus('s4-status', 'Could not read star coordinates', true);
        return;
    }
    const ra  = parseFloat(m[1]);
    const dec = parseFloat(m[2]);
    firstItem.style.outline = '2px solid var(--accent)';
    await collimSelectStar(ra, dec);
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
      const cameraRole = (document.getElementById('s4-wiz-camera-role') || {}).value || 'main';
      const s = await apiPost('/api/collimation/start', { camera_role: cameraRole });
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
    const btns = document.getElementById('s4-st-mount-btns');
    const el   = document.getElementById('s4-st-mount-result');
    if (btns) btns.querySelectorAll('button').forEach(b => { b.disabled = true; });
    if (el) { el.textContent = `moving ${dir.toUpperCase()} 2 s…`; el.style.color = 'var(--muted)'; }
    try {
      const r = await apiPost('/api/collimation/selftest/mount',
                              { direction: dir, duration_ms: 2000 });
      _stResult('s4-st-mount-result', true, `${dir.toUpperCase()} 2 s — moved`);
    } catch (err) {
      _stResult('s4-st-mount-result', false, err.message);
    } finally {
      if (btns) btns.querySelectorAll('button').forEach(b => { b.disabled = false; });
    }
}

async function selftestFocuser(steps) {
    const btnPlus  = document.getElementById('s4-st-focuser-plus');
    const btnMinus = document.getElementById('s4-st-focuser-minus');
    const el = document.getElementById('s4-st-focuser-result');
    if (btnPlus)  btnPlus.disabled  = true;
    if (btnMinus) btnMinus.disabled = true;
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
    } finally {
      if (btnPlus)  btnPlus.disabled  = false;
      if (btnMinus) btnMinus.disabled = false;
      // Refresh both the Stage 4 card and the Stage 1 position tile
      await refreshFocuser();
      await _refreshS1FocuserPos();
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

/* ══════════════════════════════════════════════════════════════════════
     Collimation Modes (M8-024 / REQ-UI-002..003)
══════════════════════════════════════════════════════════════════════ */

let _collimationMode = null;  // "bahtinov_preview" | "defocus_donut" | null

async function refreshCollimationModes() {
    let data;
    try {
        data = await (await fetch('/api/collimation/modes')).json();
    } catch (e) {
        return;
    }
    let anyAvail = false;
    for (const mode of (data.modes || [])) {
        const tileId = mode.name === 'bahtinov_preview' ? 's4-mode-bahtinov' : 's4-mode-donut';
        const availId = tileId + '-avail';
        const reasonId = tileId + '-reason';
        const tile = document.getElementById(tileId);
        const availEl = document.getElementById(availId);
        const reasonEl = document.getElementById(reasonId);
        if (!tile) continue;
        if (mode.preview_available) {
            availEl.textContent = 'Preview available';
            availEl.style.color = 'var(--success, green)';
            reasonEl.style.display = 'none';
            tile.style.opacity = '1';
            tile.style.cursor = 'pointer';
            anyAvail = true;
        } else {
            availEl.textContent = 'Preview unavailable';
            availEl.style.color = 'var(--danger)';
            if (mode.preview_unavailable_reason) {
                reasonEl.textContent = mode.preview_unavailable_reason;
                reasonEl.style.display = '';
            }
            tile.style.opacity = '0.5';
            tile.style.cursor = 'not-allowed';
        }
        // Slew/center gate
        if (!mode.slew_allowed && tile.title !== undefined) {
            tile.title = 'Slew to target: ' + (mode.slew_unavailable_reason || 'gated');
        }
    }
    const dot = document.getElementById('s4-modes-dot');
    if (dot) {
        dot.className = anyAvail ? 'dot dot-green' : 'dot dot-red';
    }
}

function selectCollimationMode(name) {
    _collimationMode = name;
    // Highlight selected tile
    for (const id of ['s4-mode-bahtinov', 's4-mode-donut']) {
        const el = document.getElementById(id);
        if (!el) continue;
        const isSelected = (id === 's4-mode-bahtinov' && name === 'bahtinov_preview')
                        || (id === 's4-mode-donut'    && name === 'defocus_donut');
        el.style.borderColor = isSelected ? 'var(--accent, #3b82f6)' : 'var(--border)';
    }
    // Show/hide relevant preview sections
    const bahtinovSection = document.querySelector('#s4 .stage-columns') || document.getElementById('s4-preview-frame')?.closest('.card')?.parentElement?.parentElement;
    const donutSection = document.getElementById('s4-donut-section');
    // The Bahtinov preview is inside the 2-column layout (stage-columns div)
    const cols = document.querySelector('#s4 .stage-columns');
    if (cols) cols.style.display = name === 'bahtinov_preview' ? '' : 'none';
    if (donutSection) donutSection.style.display = name === 'defocus_donut' ? '' : 'none';
}

function s4DonutPreviewStart() {
    const exp  = parseFloat(document.getElementById('s4-donut-exposure').value) || 1.0;
    const gain = parseInt(document.getElementById('s4-donut-gain').value, 10)   || 100;
    document.getElementById('preview-exposure').value = exp;
    document.getElementById('preview-gain').value     = gain;
    // Defocus Donut uses the main imaging camera
    previewStart('main');
}

