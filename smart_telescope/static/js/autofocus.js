/* ══════════════════════════════════════════════════════════════════════
     Autofocus screen (M10-033) — works on either the main or OAG optical
     train (selectable via the "Cam" dropdown); both share the same OnStep
     focuser. Guide has no focuser and is not selectable here.

     Arrow buttons step the focuser in fine
     increments — POST /api/focuser/nudge already clamps to OnStep's live-
     reported focuser range (GET /api/focuser/status max_position), so no
     client-side range logic is needed here. A continuous live preview
     streams the selected camera; in sky mode (terrestrial checkbox unchecked)
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
let _afSeqRunning      = false;
let _afCamRole         = 'main';   // optical train used by this screen's autofocus calls

function afEnter() {
    if (_afActive) return;
    _afActive = true;
    _afReconnect = true;
    _afLoadCameras();
    _afConnectWs();
    _afStartPositionPoll();
    _afStartMetricsPoll();
}

/* ── camera selection (main / OAG — both share the OnStep focuser) ──────── */

async function _afLoadCameras() {
    const sel = await _loadSelectFromTrains('af-cam-select', t => t.has_focuser);
    if (!sel) return;
    const mainOpt = sel.querySelector('option[value="main"]');
    if (mainOpt) sel.value = 'main';
    _afCamRole = sel.value || 'main';
    const row = document.getElementById('af-cam-row');
    if (row) row.style.display = sel.options.length <= 1 ? 'none' : '';
    // The fetch above is async and may resolve after afEnter()'s initial
    // (synchronous) _afConnectWs() call — reconnect so the preview socket
    // picks up the resolved role rather than staying on the default.
    afRestartPreview();
}

function afOnCamChange(role) {
    _afCamRole = role || 'main';
    afRestartPreview();
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
    const url      = `${proto}://${location.host}/ws/preview?exposure=${exposure}&gain=${gain}&camera_role=${_afCamRole}`;

    const statusEl = document.getElementById('af-status');
    if (statusEl) statusEl.textContent = 'Connecting…';

    _afWs = new WebSocket(url);
    _afWs.binaryType = 'blob';

    _afWs.onopen = () => { if (statusEl) statusEl.textContent = 'Live'; };

    _afWs.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        if (!ev.data.startsWith('{')) {
          // plain-text capture_error / camera_busy — surface as status.
          if (statusEl) statusEl.textContent = ev.data;
          return;
        }
        // JSON messages: camera_info carries the currently-effective
        // exposure/gain (there is no other feedback on this screen for
        // what the camera is actually capturing at).
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === 'camera_info') {
            const effEl = document.getElementById('af-eff-settings');
            if (effEl) {
              effEl.textContent =
                `Exp: ${msg.effective_exposure}s · Gain: ${msg.effective_gain}`;
            }
          } else if (msg.type === 'camera_busy') {
            // M10-045: the running capture sequence owns the camera for its
            // whole duration, so the live frame below is stale, not broken —
            // say so instead of leaving a frozen image with no explanation.
            if (statusEl) statusEl.textContent = 'Sequence running — live view paused';
          }
        } catch (_) {}
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

let _afSeqDefaultsClamped = false;
let _afLastPosition = null;
let _afLastMaxPosition = null;

function _afStartPositionPoll() {
    if (_afPosTimer) clearInterval(_afPosTimer);
    _afSeqDefaultsClamped = false;
    const poll = async () => {
      try {
        const st = await (await fetch('/api/focuser/status')).json();
        const posEl = document.getElementById('af-focuser-pos');
        if (posEl) {
          posEl.textContent = st.available
            ? `${st.position}${st.max_position != null ? ' / ' + st.max_position : ''}`
            : 'not available';
        }
        if (st.available) {
          _afLastPosition    = st.position;
          _afLastMaxPosition = st.max_position;
        }
        // Capture-sequence Start/End are offsets from the current position —
        // the static -500/+500 HTML defaults are physically impossible near
        // either end of a real focuser's range (e.g. position=15 of 50000).
        // Clamp them once, the first time a real position/max is known, so
        // the suggested defaults are always within [0, max_position].
        if (!_afSeqDefaultsClamped && st.available && st.max_position != null) {
          _afSeqDefaultsClamped = true;
          const startEl = document.getElementById('af-seq-start');
          const endEl   = document.getElementById('af-seq-end');
          if (startEl) startEl.value = Math.max(-500, -st.position);
          if (endEl)   endEl.value   = Math.min(500, st.max_position - st.position);
        }
        _afUpdateSeqRange();
      } catch (_) {}
    };
    poll();
    _afPosTimer = setInterval(poll, 1000);
}

function _afUpdateSeqRange() {
    const rangeEl = document.getElementById('af-seq-range');
    if (!rangeEl) return;
    if (_afLastPosition == null) { rangeEl.textContent = ''; return; }
    const startOffset = parseInt(document.getElementById('af-seq-start')?.value, 10);
    const endOffset    = parseInt(document.getElementById('af-seq-end')?.value, 10);
    if (Number.isNaN(startOffset) || Number.isNaN(endOffset)) { rangeEl.textContent = ''; return; }
    const absStart = _afLastPosition + startOffset;
    const absEnd   = _afLastPosition + endOffset;
    const maxTxt   = _afLastMaxPosition != null ? _afLastMaxPosition : '?';
    rangeEl.textContent =
      `Absolute positions: ${absStart} → ${absEnd} (focuser range 0 – ${maxTxt})`;
}

async function afNudge(delta) {
    if (_afSeqRunning) return;   // sequence job owns the focuser positions
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
          exposure, camera_role: _afCamRole,
        });
        el.textContent = (m.hfd != null ? `HFD: ${m.hfd.toFixed(2)} px` : 'HFD: no star detected')
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
    const gain          = parseInt(document.getElementById('af-gain')?.value, 10) || undefined;
    btn.disabled = true;
    statusEl.textContent = 'Starting…';
    _afSeqRunning = true;
    document.querySelectorAll('.nudge').forEach((b) => { b.disabled = true; });
    try {
      const r = await apiPost('/api/autofocus/sequence', {
        start_offset, end_offset, step, exposure, gain, camera_role: _afCamRole,
      });
      _afPollSequence(r.job_id, r.n_frames);
    } catch (err) {
      statusEl.textContent = String(err.message || err);
      btn.disabled = false;
      _afSeqEnded();
    }
}

function _afSeqEnded() {
    _afSeqRunning = false;
    document.querySelectorAll('.nudge').forEach((b) => { b.disabled = false; });
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
          _afSeqEnded();
        } else {
          clearInterval(_afSeqPollTimer);
          statusEl.textContent = `Failed: ${st.error}`;
          btn.disabled = false;
          _afSeqEnded();
        }
      } catch (_) {}
    }, 1000);
}
