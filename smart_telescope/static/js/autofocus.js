/* ══════════════════════════════════════════════════════════════════════
     Autofocus screen (M10-033) — main-camera focus only.

     Guide camera has no focuser; OAG shares the main focuser and is synced
     manually (out of scope here). Arrow buttons step the focuser in fine
     increments — POST /api/focuser/nudge already clamps to OnStep's live-
     reported focuser range (GET /api/focuser/status max_position), so no
     client-side range logic is needed here. A continuous live preview
     streams the main camera; in sky mode (terrestrial checkbox unchecked)
     a periodic HFD/star-count readout is polled via
     POST /api/autofocus/frame_metrics. A separate button captures a
     bracketed FITS sequence at different focus positions
     (POST /api/autofocus/sequence) to support tuning autofocus later —
     distinct from /api/focuser/autofocus's own best-focus search.

     The live preview here is a small, self-contained websocket client
     (same wire protocol as preview.js's ws/preview consumer) rather than a
     reuse of preview.js's singleton _ws — that singleton reads/writes
     Stage 3/4-specific DOM ids and would tie this screen's preview to
     whatever Stage 3/4 happens to be configured with elsewhere.
══════════════════════════════════════════════════════════════════════ */

let _afActive         = false;
let _afWs             = null;
let _afReconnect       = false;
let _afReconnectTimer  = null;
let _afPosTimer        = null;
let _afMetricsTimer    = null;
let _afSeqPollTimer    = null;

function afEnter() {
    if (_afActive) return;
    _afActive = true;
    _afReconnect = true;
    _afConnectWs();
    _afStartPositionPoll();
    _afStartMetricsPoll();
}

function afLeave() {
    if (!_afActive) return;
    _afActive = false;
    _afReconnect = false;
    clearTimeout(_afReconnectTimer);
    if (_afWs) { try { _afWs.close(1000, 'leave autofocus'); } catch {} _afWs = null; }
    if (_afPosTimer)     { clearInterval(_afPosTimer);     _afPosTimer = null; }
    if (_afMetricsTimer) { clearInterval(_afMetricsTimer); _afMetricsTimer = null; }
    if (_afSeqPollTimer) { clearInterval(_afSeqPollTimer); _afSeqPollTimer = null; }
}

function afToggleTerrestrial() {
    if (document.getElementById('af-terrestrial-chk')?.checked) {
      const el = document.getElementById('af-metrics');
      if (el) el.textContent = '';
    }
}

/* ── live preview ───────────────────────────────────────────────────────── */

function _afConnectWs() {
    if (_afWs) { try { _afWs.close(); } catch {} _afWs = null; }
    const exposure = parseFloat(document.getElementById('af-exposure')?.value) || 2.0;
    const gain     = parseInt(document.getElementById('af-gain')?.value, 10) || 100;
    const proto    = location.protocol === 'https:' ? 'wss' : 'ws';
    const url      = `${proto}://${location.host}/ws/preview?exposure=${exposure}&gain=${gain}&camera_role=main`;

    const statusEl = document.getElementById('af-status');
    if (statusEl) statusEl.textContent = 'Connecting…';

    _afWs = new WebSocket(url);
    _afWs.binaryType = 'blob';

    _afWs.onopen = () => { if (statusEl) statusEl.textContent = 'Live'; };

    _afWs.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        // camera_error / camera_info text — surface errors, ignore the rest.
        if (!ev.data.startsWith('{') && statusEl) statusEl.textContent = ev.data;
        return;
      }
      const img = document.getElementById('af-preview-img');
      const ph  = document.getElementById('af-preview-ph');
      if (!img) return;
      if (img.src?.startsWith('blob:')) URL.revokeObjectURL(img.src);
      img.src = URL.createObjectURL(ev.data);
      img.style.display = 'block';
      if (ph) ph.style.display = 'none';
    };

    _afWs.onerror = () => { if (statusEl) statusEl.textContent = 'WebSocket error'; };

    _afWs.onclose = (ev) => {
      _afWs = null;
      if (_afReconnect && ev.code !== 1000) {
        if (statusEl) statusEl.textContent = `Disconnected (${ev.code}) — reconnecting…`;
        _afReconnectTimer = setTimeout(_afConnectWs, 3000);
      }
    };
}

function afRestartPreview() {
    if (_afActive) _afConnectWs();
}

/* ── focuser position + arrow nudge ─────────────────────────────────────── */

function _afStartPositionPoll() {
    if (_afPosTimer) clearInterval(_afPosTimer);
    const poll = async () => {
      try {
        const st = await (await fetch('/api/focuser/status')).json();
        const posEl = document.getElementById('af-focuser-pos');
        if (posEl) {
          posEl.textContent = st.available
            ? `${st.position}${st.max_position != null ? ' / ' + st.max_position : ''}`
            : 'not available';
        }
      } catch (_) {}
    };
    poll();
    _afPosTimer = setInterval(poll, 1000);
}

async function afNudge(delta) {
    const statusEl = document.getElementById('af-status');
    try {
      await apiPost('/api/focuser/nudge', { delta });
    } catch (err) {
      if (statusEl) statusEl.textContent = String(err.message || err);
    }
}

async function afFocuserStop() {
    try { await apiPost('/api/focuser/stop', {}); } catch (_) {}
}

/* ── HFD / star-count readout (sky mode only) ───────────────────────────── */

function _afStartMetricsPoll() {
    if (_afMetricsTimer) clearInterval(_afMetricsTimer);
    _afMetricsTimer = setInterval(async () => {
      if (document.getElementById('af-terrestrial-chk')?.checked) return;
      const el = document.getElementById('af-metrics');
      if (!el) return;
      const exposure = parseFloat(document.getElementById('af-exposure')?.value) || 2.0;
      try {
        const m = await apiPost('/api/autofocus/frame_metrics', {
          exposure, camera_role: 'main',
        });
        el.textContent = `HFD: ${m.hfd.toFixed(2)} px`
          + (m.stars_found != null ? ` · ${m.stars_found} star${m.stars_found === 1 ? '' : 's'} found` : '')
          + (m.image_quality ? ` · ${m.image_quality}` : '');
      } catch (_) {}
    }, 4000);
}

/* ── bracketed focus-sequence capture ───────────────────────────────────── */

async function afStartSequence() {
    const btn      = document.getElementById('af-seq-btn');
    const statusEl = document.getElementById('af-seq-status');
    const start_offset = parseInt(document.getElementById('af-seq-start').value, 10);
    const end_offset   = parseInt(document.getElementById('af-seq-end').value, 10);
    const step         = parseInt(document.getElementById('af-seq-step').value, 10);
    const exposure      = parseFloat(document.getElementById('af-exposure')?.value) || 2.0;
    btn.disabled = true;
    statusEl.textContent = 'Starting…';
    try {
      const r = await apiPost('/api/autofocus/sequence', {
        start_offset, end_offset, step, exposure, camera_role: 'main',
      });
      _afPollSequence(r.job_id, r.n_frames);
    } catch (err) {
      statusEl.textContent = String(err.message || err);
      btn.disabled = false;
    }
}

function _afPollSequence(jobId, nFrames) {
    const statusEl = document.getElementById('af-seq-status');
    const btn      = document.getElementById('af-seq-btn');
    if (_afSeqPollTimer) clearInterval(_afSeqPollTimer);
    _afSeqPollTimer = setInterval(async () => {
      try {
        const st = await (await fetch(`/api/autofocus/sequence/status/${jobId}`)).json();
        if (st.status === 'running') {
          statusEl.textContent = `Capturing ${st.frames_done} / ${nFrames}…`;
        } else if (st.status === 'done') {
          clearInterval(_afSeqPollTimer);
          statusEl.textContent = `Done — ${st.frames_done} frames saved to ${st.result_dir}`;
          btn.disabled = false;
        } else {
          clearInterval(_afSeqPollTimer);
          statusEl.textContent = `Failed: ${st.error}`;
          btn.disabled = false;
        }
      } catch (_) {}
    }, 1000);
}
