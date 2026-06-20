function _clipLineToRect(a, b, c, W, H) {
    /* Return up to 2 points where line ax+by+c=0 intersects the [0,W]x[0,H] rect */
    const eps = 1e-8;
    const pts = [];
    if (Math.abs(b) > eps) {
      const y0 = -c / b;
      const yW = (-a * W - c) / b;
      if (y0 >= -1 && y0 <= H + 1) pts.push([0, y0]);
      if (yW >= -1 && yW <= H + 1) pts.push([W, yW]);
    }
    if (Math.abs(a) > eps) {
      const x0 = -c / a;
      const xH = (-b * H - c) / a;
      if (x0 >= -1 && x0 <= W + 1) pts.push([x0, 0]);
      if (xH >= -1 && xH <= W + 1) pts.push([xH, H]);
    }
    const unique = [];
    for (const p of pts) {
      if (!unique.some(u => Math.abs(u[0] - p[0]) < 2 && Math.abs(u[1] - p[1]) < 2))
        unique.push(p);
    }
    return unique.slice(0, 2);
}

function _clearBahtinovOverlay() {
    const svg = document.getElementById('s4-bahtinov-svg');
    if (svg) { svg.innerHTML = ''; svg.style.display = 'none'; }
    const res = document.getElementById('s4-bahtinov-result');
    if (res) res.style.display = 'none';
    const zc = document.getElementById('s4-zoom-canvas');
    if (zc) zc.style.display = 'none';
    const zb = document.getElementById('s4-zoom-btn');
    if (zb) zb.style.display = 'none';
    _lastBahtinovData = null;
}

function _drawBahtinovOverlay(data) {
    const img   = document.getElementById('s4-preview-img');
    const frame = document.getElementById('s4-preview-frame');
    if (!img || !frame || img.style.display === 'none') return;

    const imgRect   = img.getBoundingClientRect();
    const frameRect = frame.getBoundingClientRect();
    const dispLeft = imgRect.left - frameRect.left;
    const dispTop  = imgRect.top  - frameRect.top;
    const dispW    = imgRect.width;
    const dispH    = imgRect.height;
    const [natW, natH] = data.image_size_px;

    let svg = document.getElementById('s4-bahtinov-svg');
    svg.style.left    = dispLeft + 'px';
    svg.style.top     = dispTop  + 'px';
    svg.style.width   = dispW    + 'px';
    svg.style.height  = dispH   + 'px';
    svg.setAttribute('viewBox', `0 0 ${natW} ${natH}`);
    svg.style.display = '';
    svg.innerHTML = `<defs>
      <marker id="ah" markerWidth="8" markerHeight="6" refX="4" refY="3" orient="auto">
        <polygon points="0 0, 8 3, 0 6" fill="#f87171"/>
      </marker></defs>`;

    /* classify middle spike (sorted by angle, take the middle index) */
    const sorted = data.lines
      .map((l, i) => ({ i, ang: l.angle_deg }))
      .sort((a, b) => a.ang - b.ang);
    const midIdx = sorted[1].i;

    /* draw spike lines */
    data.lines.forEach((line, i) => {
      const isMid  = (i === midIdx);
      const colour = isMid ? '#facc15' : 'rgba(100,160,255,0.8)';
      const dash   = isMid ? '' : '8 4';
      const pts    = _clipLineToRect(line.a, line.b, line.c, natW, natH);
      if (pts.length < 2) return;
      const el = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      el.setAttribute('x1', pts[0][0]); el.setAttribute('y1', pts[0][1]);
      el.setAttribute('x2', pts[1][0]); el.setAttribute('y2', pts[1][1]);
      el.setAttribute('stroke', colour);
      el.setAttribute('stroke-width', isMid ? '2' : '1.5');
      if (dash) el.setAttribute('stroke-dasharray', dash);
      svg.appendChild(el);
    });

    /* crossing point crosshair */
    const [cx, cy] = data.common_crossing_point_px;
    const r  = Math.max(8, natW / 80);
    const err = Math.abs(data.focus_error_px);
    const ringColor = err < 3 ? '#4ade80' : err < 10 ? '#facc15' : '#f87171';
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', cx); circle.setAttribute('cy', cy);
    circle.setAttribute('r', r); circle.setAttribute('fill', 'none');
    circle.setAttribute('stroke', ringColor); circle.setAttribute('stroke-width', '2.5');
    svg.appendChild(circle);

    /* focus error arrow along middle-spike normal direction */
    const mid      = data.lines[midIdx];
    const arrowLen = data.focus_error_px * 4;
    if (Math.abs(arrowLen) > 2) {
      const ax2 = cx - mid.a * arrowLen;
      const ay2 = cy - mid.b * arrowLen;
      const arr = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      arr.setAttribute('x1', cx); arr.setAttribute('y1', cy);
      arr.setAttribute('x2', ax2); arr.setAttribute('y2', ay2);
      arr.setAttribute('stroke', '#f87171'); arr.setAttribute('stroke-width', '2.5');
      arr.setAttribute('marker-end', 'url(#ah)');
      svg.appendChild(arr);
    }
}

// ── Bahtinov zoom (picture-in-picture crop around crossing point) ─────────────

let _bahtinovZoomEnabled = false;
let _lastBahtinovData    = null;

function bahtinovZoomToggle() {
    _bahtinovZoomEnabled = !_bahtinovZoomEnabled;
    const btn = document.getElementById('s4-zoom-btn');
    if (btn) btn.textContent = _bahtinovZoomEnabled ? 'Zoom off' : 'Zoom';
    if (!_bahtinovZoomEnabled) {
        const c = document.getElementById('s4-zoom-canvas');
        if (c) c.style.display = 'none';
    } else if (_lastBahtinovData) {
        _drawBahtinovZoom(_lastBahtinovData);
    }
}

function _drawBahtinovZoom(data) {
    if (!_bahtinovZoomEnabled) return;
    const img = document.getElementById('s4-preview-img');
    const canvas = document.getElementById('s4-zoom-canvas');
    if (!img || !canvas || img.style.display === 'none') return;
    const [natW, natH] = data.image_size_px;
    const [cx, cy]     = data.common_crossing_point_px;
    const cropR = Math.max(80, Math.min(natW, natH) / 10);  // crop radius in native pixels
    const x0 = Math.max(0, Math.round(cx - cropR));
    const y0 = Math.max(0, Math.round(cy - cropR));
    const x1 = Math.min(natW, Math.round(cx + cropR));
    const y1 = Math.min(natH, Math.round(cy + cropR));
    const cw = x1 - x0, ch = y1 - y0;
    if (cw < 4 || ch < 4) return;
    const offscreen = document.createElement('canvas');
    offscreen.width = natW; offscreen.height = natH;
    const ctx2 = offscreen.getContext('2d');
    ctx2.drawImage(img, 0, 0, natW, natH);
    const ctx = canvas.getContext('2d');
    canvas.width  = 180; canvas.height = 180;
    ctx.drawImage(offscreen, x0, y0, cw, ch, 0, 0, 180, 180);
    // Crosshair at centre of zoom canvas
    ctx.strokeStyle = 'rgba(250,204,21,0.8)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(90, 80); ctx.lineTo(90, 100); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(80, 90); ctx.lineTo(100, 90); ctx.stroke();
    canvas.style.display = '';
}

async function bahtinovAnalyze() {
    const btn     = document.getElementById('s4-analyze-btn');
    const res     = document.getElementById('s4-bahtinov-result');
    const errLine = document.getElementById('s4-bahtinov-error-line');
    const rmsEl   = document.getElementById('s4-bahtinov-rms');
    const confEl  = document.getElementById('s4-bahtinov-conf');
    const exposure = parseFloat(document.getElementById('s4-exposure').value);
    const gain     = parseInt(document.getElementById('s4-gain').value, 10);

    btn.disabled = true;
    btn.innerHTML = '<span class="spin"></span>Analyzing…';
    _clearBahtinovOverlay();

    try {
      const data  = await apiPost('/api/bahtinov/analyze', { exposure, gain });
      const fErr  = data.focus_error_px;
      const rms   = data.crossing_error_rms_px;
      const conf  = data.detection_confidence;
      const color = Math.abs(fErr) < 3 ? '#4ade80' : Math.abs(fErr) < 10 ? '#facc15' : '#f87171';
      const dir   = fErr > 0.5 ? ' → turn IN' : fErr < -0.5 ? ' → turn OUT' : ' ✔ in focus';
      errLine.innerHTML =
        `Focus error: <span style="color:${color}">${fErr.toFixed(1)} px</span>${escHtml(dir)}`;
      rmsEl.textContent  = rms.toFixed(1) + ' px ' + (rms < 3 ? '✓' : rms < 10 ? '~' : '!');
      confEl.textContent = (conf * 100).toFixed(0) + '%';
      res.style.display = '';
      _lastBahtinovData = data;
      _drawBahtinovOverlay(data);
      _drawBahtinovZoom(data);
      const zb = document.getElementById('s4-zoom-btn');
      if (zb) zb.style.display = '';
    } catch (err) {
      if (res) res.style.display = '';
      if (errLine) errLine.textContent = 'Analysis failed: ' + err;
      if (rmsEl)   rmsEl.textContent = '—';
      if (confEl)  confEl.textContent = '—';
    } finally {
      btn.disabled = false;
      btn.innerHTML = 'Analyze';
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Camera Cooling (Stage 1)
══════════════════════════════════════════════════════════════════════ */
let _coolingPollInterval = null;


function _setWsStatus(state) {
    const labels = { live: 'Live', connecting: 'Connecting…', stopped: 'Stopped' };
    const html   = `<span class="ws-dot ws-${state}"></span>${labels[state] || state}`;
    ['s3-ws-status','s4-ws-status'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.innerHTML = html;
    });
}

function _updatePreviewBtns(running) {
    ['preview-start-btn','s4-start-btn'].forEach(id => {
      const b = document.getElementById(id);
      if (b) b.disabled = running;
    });
    ['preview-stop-btn','s4-stop-btn'].forEach(id => {
      const b = document.getElementById(id);
      if (b) b.disabled = !running;
    });
    const ab = document.getElementById('s4-analyze-btn');
    if (ab) ab.disabled = !running;
    if (!running) _clearBahtinovOverlay();
}

function previewStart() {
    _reconnect = true;
    _connectWs();
}

function previewReconnectIfRunning() {
    if (_ws) _connectWs();
}

function previewSendParams() {
    const exposure = parseFloat(document.getElementById('preview-exposure')?.value) || 2.0;
    const gain     = parseInt(document.getElementById('preview-gain')?.value, 10) || 100;
    const offset   = parseInt(document.getElementById('preview-offset')?.value, 10) || 0;
    const stretch  = document.getElementById('preview-stretch-chk')?.checked !== false;
    const autogain = document.getElementById('preview-autogain-chk')?.checked === true;
    if (_ws && _ws.readyState === WebSocket.OPEN) {
      _ws.send(JSON.stringify({ type: 'set_params', exposure, gain, offset, stretch, autogain }));
    } else if (_reconnect) {
      _connectWs();  // not yet connected — reconnect with new params baked into URL
    }
}

function previewStop() {
    _reconnect = false;
    clearTimeout(_reconnectTimer);
    if (_ws) { _ws.close(1000, 'user stop'); _ws = null; }
    clearInterval(_histInterval);
    _histInterval = null;
    _updatePreviewBtns(false);
    _setWsStatus('stopped');
    setStatus('s3-status', '');
    const adEl = document.getElementById('s3-cam-adapter');
    if (adEl) { adEl.textContent = ''; adEl.style.color = ''; adEl.style.fontWeight = ''; }
}

function _connectWs() {
    // Kill histogram poll before opening the socket so no in-flight fetch
    // can hold the camera lock when the WebSocket attempts its first capture.
    clearInterval(_histInterval);
    _histInterval = null;
    if (_ws) { _ws.close(); _ws = null; }
    const exposure   = parseFloat(document.getElementById('preview-exposure').value) || 2.0;
    const gain       = parseInt(document.getElementById('preview-gain').value, 10) || 100;
    const offset     = parseInt(document.getElementById('preview-offset')?.value, 10) || 0;
    const stretch    = document.getElementById('preview-stretch-chk')?.checked !== false;
    const camRole    = document.getElementById('preview-cam-select')?.value || 'main';
    const autoGain   = document.getElementById('preview-autogain-chk')?.checked ? '&autogain=true' : '';
    const proto      = location.protocol === 'https:' ? 'wss' : 'ws';
    const url        = `${proto}://${location.host}/ws/preview?exposure=${exposure}&gain=${gain}&camera_role=${encodeURIComponent(camRole)}&offset=${offset}&stretch=${stretch}${autoGain}`;

    _setWsStatus('connecting');
    _updatePreviewBtns(true);
    _ws = new WebSocket(url);
    _ws.binaryType = 'blob';

    _ws.onopen = () => {
      _frameCount = 0;
      _setWsStatus('live');
      // WS now delivers histogram with each frame — stop the API polling timer
      clearInterval(_histInterval);
      _histInterval = null;
    };

    _ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        let msg = null;
        try { msg = JSON.parse(ev.data); } catch (_) {}
        if (msg?.type === 'camera_info') {
          const el = document.getElementById('s3-cam-adapter');
          if (el) {
            const isMock = msg.adapter === 'MockCamera';
            el.textContent = isMock
              ? 'MockCamera — no real camera (check config / SDK)'
              : (msg.name || msg.adapter) + (msg.is_color ? ' · colour (' + msg.bayer_pattern + ')' : ' · mono');
            el.style.color  = isMock ? 'orange' : 'var(--muted)';
            el.style.fontWeight = isMock ? 'bold' : '';
          }
          // Reflect effective settings back into the input fields
          if (typeof msg.effective_exposure === 'number') {
            const expEl = document.getElementById('preview-exposure');
            if (expEl) expEl.value = msg.effective_exposure;
          }
          if (typeof msg.effective_gain === 'number') {
            const gainEl = document.getElementById('preview-gain');
            if (gainEl) gainEl.value = msg.effective_gain;
          }
          if (typeof msg.effective_offset === 'number') {
            const offEl = document.getElementById('preview-offset');
            if (offEl) offEl.value = msg.effective_offset;
          }
          return;
        }
        if (msg?.type === 'autogain') {
          const expEl  = document.getElementById('preview-exposure');
          const gainEl = document.getElementById('preview-gain');
          if (expEl)  expEl.value  = msg.exposure;
          if (gainEl) gainEl.value = msg.gain;
          const adEl = document.getElementById('s3-cam-adapter');
          if (adEl && adEl.textContent && !adEl.textContent.includes('MockCamera')) {
            const base = adEl.textContent.replace(/ · AG:.*$/, '');
            adEl.textContent = `${base} · AG: ${msg.exposure.toFixed(3)}s / gain ${msg.gain}`;
          }
          return;
        }
        if (msg?.type === 'histogram') {
          if (document.getElementById('preview-hist-chk')?.checked) {
            const panel = document.getElementById('s3-hist-panel');
            if (panel && panel.style.display !== 'none') {
              try {
                showHistogram('s3-histogram', 's3-hist-stats', msg.stats, msg.bin_counts, msg.bin_edges, msg.hist_adu_hi);
              } catch (_) {}
              // Low-range pedestal panel — always show (0–1000 ADU detail)
              const lowWrap = document.getElementById('s3-hist-low-wrap');
              if (lowWrap) {
                const showLow = !!(msg.low_bin_counts && msg.low_bin_counts.length);
                lowWrap.style.display = showLow ? '' : 'none';
                if (showLow) {
                  _updateLowLabel(msg.low_adu_hi, msg.low_bin_counts.length);
                  try {
                    showHistogram('s3-histogram-low', null, msg.stats, msg.low_bin_counts, msg.low_bin_edges, msg.low_adu_hi);
                  } catch (_) {}
                }
              }
            }
          }
          return;
        }
        // non-histogram text = camera error
        setStatus('s3-status', `Camera: ${ev.data}`, true);
        return;
      }
      // Stage 3 image
      const img3 = document.getElementById('s3-preview-img');
      const ph3  = document.getElementById('s3-preview-ph');
      if (img3.src?.startsWith('blob:')) URL.revokeObjectURL(img3.src);
      img3.src = URL.createObjectURL(ev.data);
      img3.style.display = 'block';
      if (ph3) ph3.style.display = 'none';

      // Stage 4 image (same frame, new blob URL)
      const img4 = document.getElementById('s4-preview-img');
      const ph4  = document.getElementById('s4-preview-ph');
      if (img4) {
        if (img4.src?.startsWith('blob:')) URL.revokeObjectURL(img4.src);
        img4.src = URL.createObjectURL(ev.data);
        img4.style.display = 'block';
        if (ph4) ph4.style.display = 'none';
        document.getElementById('s4-preview-overlay').textContent =
          `#${_frameCount + 1} · ${new Date().toLocaleTimeString()}`;
      }

      _frameCount++;
      document.getElementById('s3-frame-count').textContent =
        `${_frameCount} frame${_frameCount !== 1 ? 's' : ''}`;
      document.getElementById('s3-preview-overlay').textContent =
        `#${_frameCount} · ${new Date().toLocaleTimeString()}`;

      // histogram is now fetched via API on a timer; no per-frame JPEG decode needed
    };

    _ws.onerror = () => setStatus('s3-status', 'WebSocket error — check server', true);

    _ws.onclose = (ev) => {
      _ws = null;
      if (_reconnect && ev.code !== 1000) {
        _setWsStatus('connecting');
        setStatus('s3-status', `Disconnected (code ${ev.code}) — reconnecting in 3 s…`);
        _reconnectTimer = setTimeout(_connectWs, 3000);
      } else {
        _updatePreviewBtns(false);
        _setWsStatus('stopped');
        // Preview ended — if histogram is still enabled, resume API polling
        if (document.getElementById('preview-hist-chk')?.checked) {
          _fetchAndDrawHistogram();
          _histInterval = setInterval(_fetchAndDrawHistogram, 4000);
        }
      }
    };
}

/* ══════════════════════════════════════════════════════════════════════
     Histogram widget — shared across stages (AGT-2-2)
══════════════════════════════════════════════════════════════════════ */

function _updateLowLabel(lowAduHi, nBins) {
    const el = document.getElementById('s3-hist-low-label');
    if (!el) return;
    const binSz = Math.round(lowAduHi / nBins);
    el.textContent = `0 – ${Math.round(lowAduHi)} ADU — pedestal detail (${binSz} ADU/bin)`;
}

/**
   * Render a raw linear histogram on *canvasId* using data from the API.
   * Also populates *statsId* text line when provided.
   *
   * @param {string}   canvasId   - id of <canvas> element
   * @param {string|null} statsId - id of text element for stats line (or null)
   * @param {object}   stats      - HistogramStats object from /api/histogram/analyze
   * @param {number[]} binCounts  - histogram bin counts
   * @param {number[]} binEdges   - histogram bin edges (length = binCounts.length + 1)
   */
function showHistogram(canvasId, statsId, stats, binCounts, binEdges, histAduHi) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const CW = canvas.offsetWidth || canvas.width || 400;
    const CH = canvas.height || 100;
    canvas.width = CW;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, CW, CH);

    // Layout: [bars] [statsStrip 14px] [xAxis 16px]
    const statsH = 14;
    const xAxisH = 16;
    const barH   = CH - statsH - xAxisH;  // ≈ 70 px

    const n       = binCounts.length;
    const peak    = Math.max(1, ...binCounts);
    const logPeak = Math.log1p(peak);
    const bw      = CW / n;
    const adcMax  = (stats && stats.adc_max) ? stats.adc_max : 65535;
    // histAduMax: the ADU value at the right edge of the histogram display
    const histAduMax = (typeof histAduHi === 'number' && histAduHi > 0) ? histAduHi : adcMax;

    // Background
    ctx.fillStyle = '#111';
    ctx.fillRect(0, 0, CW, CH);

    // Shaded region 0–4000 ADU (light blue tint)
    const x4k = Math.round(Math.min(4000 / histAduMax, 1.0) * CW);
    if (x4k > 0) {
      ctx.fillStyle = 'rgba(80,130,220,0.07)';
      ctx.fillRect(0, 0, x4k, barH);
    }

    // Draw bars (log scale for dynamic range); non-zero bins always get ≥1px
    ctx.fillStyle = 'rgba(170,195,235,0.85)';
    for (let i = 0; i < n; i++) {
      const hRaw = Math.log1p(binCounts[i]) / logPeak * barH;
      const h = binCounts[i] > 0 ? Math.max(1, Math.round(hRaw)) : 0;
      if (h > 0) ctx.fillRect(i * bw, barH - h, Math.max(1, bw - 0.5), h);
    }

    // 4000 ADU boundary line (dashed, only when it's in-range and not trivially at the edge)
    if (x4k > 4 && x4k < CW - 4) {
      ctx.save();
      ctx.setLineDash([2, 3]);
      ctx.strokeStyle = 'rgba(100,160,255,0.35)';
      ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x4k, 0); ctx.lineTo(x4k, barH); ctx.stroke();
      ctx.restore();
    }

    // Black-level marker (p0.5 ≈ pedestal) — position relative to focused range
    const blFrac = Math.min(stats.black_level * adcMax / histAduMax, 1.0);
    const blX = Math.round(blFrac * CW);
    ctx.strokeStyle = 'rgba(100,150,255,0.75)';
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(blX, 0); ctx.lineTo(blX, barH); ctx.stroke();

    // Target band 75–80 % of ADC range — only draw if in focused range
    const t75 = 0.75 * adcMax / histAduMax;
    const t80 = 0.80 * adcMax / histAduMax;
    if (t75 < 1.0) {
      ctx.fillStyle = 'rgba(0,210,100,0.10)';
      ctx.fillRect(Math.round(t75 * CW), 0, Math.round((t80 - t75) * CW), barH);
      ctx.strokeStyle = 'rgba(0,210,100,0.55)';
      ctx.lineWidth = 1;
      [t75, Math.min(t80, 1.0)].forEach(f => {
        if (f > 0.02 && f < 0.99) {
          const x = Math.round(f * CW);
          ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, barH); ctx.stroke();
        }
      });
    }

    // Saturation marker at right edge (red)
    ctx.strokeStyle = 'rgba(255,80,60,0.80)';
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(CW - 1, 0); ctx.lineTo(CW - 1, barH); ctx.stroke();

    // ── inline stats strip ──────────────────────────────────────────────
    const statsY = barH;
    ctx.fillStyle = 'rgba(0,0,0,0.65)';
    ctx.fillRect(0, statsY, CW, statsH);
    ctx.font = '9px ui-monospace, monospace';

    const p50adu  = Math.round(stats.p50  * adcMax);
    const p99adu  = Math.round(stats.p99  * adcMax);
    ctx.fillStyle = stats.zero_clipped_pct > 10 ? 'rgba(120,160,255,0.9)' : 'rgba(150,170,210,0.9)';
    ctx.textAlign = 'left';
    ctx.fillText(`0-clip:${stats.zero_clipped_pct.toFixed(1)}%`, 3, statsY + statsH - 3);

    ctx.fillStyle = 'rgba(180,200,230,0.9)';
    ctx.textAlign = 'center';
    ctx.fillText(`p50:${p50adu}  p99:${p99adu}`, CW / 2, statsY + statsH - 3);

    ctx.fillStyle = stats.saturation_pct > 1 ? 'rgba(255,110,80,0.95)' : 'rgba(150,170,210,0.9)';
    ctx.textAlign = 'right';
    ctx.fillText(`sat:${stats.saturation_pct.toFixed(1)}%`, CW - 3, statsY + statsH - 3);

    // ── x-axis strip with two-level ticks ───────────────────────────────
    const xY = barH + statsH;
    ctx.fillStyle = 'rgba(0,0,0,0.75)';
    ctx.fillRect(0, xY, CW, xAxisH);
    ctx.font = '8px ui-monospace, monospace';

    // Target ~8 major ticks with adaptive step sizes for small ranges (e.g. 0–1k ADU).
    const rawMajor = histAduMax / 8;
    let majorInt;
    if      (rawMajor <=   50) majorInt = 50;
    else if (rawMajor <=  100) majorInt = 100;
    else if (rawMajor <=  200) majorInt = 200;
    else if (rawMajor <=  500) majorInt = 500;
    else if (rawMajor <= 1000) majorInt = 1000;
    else majorInt = Math.round(rawMajor / 1000) * 1000;
    const minorInt = Math.max(10, majorInt / 5);

    // Minor ticks (4 px, no label)
    ctx.strokeStyle = 'rgba(140,165,200,0.75)';
    ctx.lineWidth = 1.2;
    for (let adu = minorInt; adu < histAduMax; adu += minorInt) {
      if (adu % majorInt === 0) continue;
      const x = Math.round((adu / histAduMax) * CW);
      ctx.beginPath(); ctx.moveTo(x, xY); ctx.lineTo(x, xY + 4); ctx.stroke();
    }

    // Major ticks (6 px + label)
    ctx.strokeStyle = 'rgba(160,185,215,0.9)';
    for (let adu = 0; adu <= histAduMax * 1.01; adu += majorInt) {
      const x = Math.round((adu / histAduMax) * CW);
      ctx.beginPath(); ctx.moveTo(x, xY); ctx.lineTo(x, xY + 6); ctx.stroke();
      const label = adu === 0 ? '0' : adu >= 1000 ? `${adu / 1000}k` : String(adu);
      const is4k  = adu === 4000;
      ctx.fillStyle = is4k ? 'rgba(110,170,255,0.95)' : 'rgba(160,185,215,0.9)';
      ctx.textAlign = x < 14 ? 'left' : x > CW - 14 ? 'right' : 'center';
      ctx.fillText(label, Math.min(Math.max(x, 4), CW - 4), xY + xAxisH - 2);
    }

    ctx.textAlign = 'left';

    // Range + block-size label — drawn inside canvas top-right corner
    const binSize = Math.round(histAduMax / n);
    const rangeLabel = histAduMax >= 1000
      ? `0–${(histAduMax / 1000).toFixed(histAduMax < 10000 ? 1 : 0)}k ADU · ${binSize} ADU/bin`
      : `0–${Math.round(histAduMax)} ADU · ${binSize} ADU/bin`;
    ctx.font = '8px ui-monospace, monospace';
    ctx.fillStyle = 'rgba(130,155,195,0.75)';
    ctx.textAlign = 'right';
    ctx.fillText(rangeLabel, CW - 3, 9);
    ctx.textAlign = 'left';

    // Full stats text line (below canvas) — show ADU values + bin size
    if (statsId) {
      const el = document.getElementById(statsId);
      if (el) {
        const fmt = f => Math.round(f * adcMax);
        el.textContent =
          `block:${binSize} ADU  ` +
          `p50:${fmt(stats.p50)}  ` +
          `p95:${fmt(stats.p95)}  ` +
          `p99:${fmt(stats.p99)}  ` +
          `p99.5:${fmt(stats.p99_5)}  ` +
          `p99.9:${fmt(stats.p99_9)}  ` +
          `sat:${stats.saturation_pct.toFixed(2)}%  ` +
          `0-clip:${stats.zero_clipped_pct.toFixed(2)}%`;
      }
    }
}

function previewHistToggle(enabled) {
    _histEnabled = enabled;
    const panel = document.getElementById('s3-hist-panel');
    if (panel) panel.style.display = enabled ? '' : 'none';
    clearInterval(_histInterval);
    _histInterval = null;
    if (!enabled) {
      const canvas = document.getElementById('s3-histogram');
      if (canvas) canvas.getContext('2d').clearRect(0, 0, canvas.width, canvas.height);
      const stats = document.getElementById('s3-hist-stats');
      if (stats) stats.textContent = '';
    } else if (!_reconnect) {
      // Preview WS not running and not reconnecting — use API polling
      _fetchAndDrawHistogram();
      _histInterval = setInterval(_fetchAndDrawHistogram, 4000);
    }
}

async function _fetchAndDrawHistogram() {
    if (!_histEnabled || _reconnect) return;  // skip when WS is active or reconnecting
    const exposure = parseFloat(document.getElementById('preview-exposure')?.value) || 2.0;
    const gain     = parseInt(document.getElementById('preview-gain')?.value, 10)   || 100;
    const camRole  = document.getElementById('preview-cam-select')?.value || 'main';
    const params   = new URLSearchParams({
      camera_role: camRole, exposure, gain, bit_depth: 12, n_bins: 256,
    });
    try {
      const r = await fetch(`/api/histogram/analyze?${params}`, { method: 'POST' });
      if (!r.ok) return;
      const d = await r.json();
      showHistogram('s3-histogram', 's3-hist-stats', d, d.bin_counts, d.bin_edges, d.hist_adu_hi);
      const lowWrap = document.getElementById('s3-hist-low-wrap');
      if (lowWrap && d.low_bin_counts?.length) {
        lowWrap.style.display = '';
        _updateLowLabel(d.low_adu_hi, d.low_bin_counts.length);
        try {
          showHistogram('s3-histogram-low', null, d, d.low_bin_counts, d.low_bin_edges, d.low_adu_hi);
        } catch (_) {}
      }
    } catch (_) { /* ignore network errors during preview */ }
}

/* ══════════════════════════════════════════════════════════════════════
     One-shot Auto Gain (Stage 3)
══════════════════════════════════════════════════════════════════════ */

let _agPollTimer = null;
let _agLastResult = null;  // { exposure_ms, gain, offset } from last OK run
let _agPreviewWasRunning = false;

function _agSetBusy(busy) {
    const runBtn    = document.getElementById('autogain-run-btn');
    const cancelBtn = document.getElementById('autogain-cancel-btn');
    const badge     = document.getElementById('autogain-status-badge');
    if (!runBtn) return;
    runBtn.disabled = busy;
    cancelBtn.style.display = busy ? '' : 'none';
    if (busy) {
      badge.style.display = '';
      badge.style.color = 'var(--muted)';
      badge.innerHTML = '<span class="spin"></span> Running…';
    }
}

// Actionable messages per diagnostic classification (FR-UI-002)
const _AG_DIAG_MESSAGES = {
    'AUTO_GAIN_NO_SIGNAL': {
      title: 'No signal at 10 s',
      msg: 'No photons detected even at maximum gain and 10 s exposure. Confirm the telescope is unobstructed and pointing at sky, polar alignment is correct, and tracking is active.',
    },
    'AUTO_GAIN_POSSIBLE_DUST_CAP': {
      title: 'Dust cap may be on',
      msg: 'The histogram is indistinguishable from a dark frame. Remove the dust cap (or lens cap) and try again.',
    },
    'AUTO_GAIN_POSSIBLE_FOCUS_OR_POINTING_ERROR': {
      title: 'Faint signal detected — pointing issue',
      msg: 'A very faint signal was found at 10 s. The target may be slightly out of frame or the mount may have lost tracking. Confirm the mount is tracking and re-center the target.',
      msgWithFocuser: 'A very faint signal was found at 10 s. The target may be defocused, slightly out of frame, or the mount may have lost tracking. Check focus, confirm the mount is tracking, and re-center the target.',
    },
};

function _agShowResult(d) {
    const badge     = document.getElementById('autogain-status-badge');
    const resultRow = document.getElementById('autogain-result-row');
    const resultTxt = document.getElementById('autogain-result-text');
    const applyBtn  = document.getElementById('autogain-apply-btn');
    const diagPrompt = document.getElementById('autogain-diag-prompt');
    const diagResult = document.getElementById('autogain-diag-result');
    if (!badge) return;

    // Hide diagnostic panels on a fresh result
    if (diagResult) diagResult.style.display = 'none';

    badge.style.display = '';
    const ok = d.status === 'AUTO_GAIN_OK';
    badge.style.color = ok ? 'var(--green,#4caf50)' : 'var(--warn,#f5a623)';
    badge.textContent = ok ? '✓ OK' : ('⚠ ' + (d.status || d.error || 'Error'));

    resultRow.style.display = '';
    if (d.error) {
      resultTxt.textContent = 'Error: ' + d.error;
      applyBtn.style.display = 'none';
      return;
    }
    const expS = d.exposure_ms != null ? (d.exposure_ms / 1000).toFixed(3) + ' s' : '—';
    const gain  = d.gain  != null ? d.gain  : '—';
    const off   = d.offset != null ? d.offset : '—';
    const warn  = d.warning_msg ? (' — ' + d.warning_msg) : '';
    resultTxt.innerHTML = `Exp <b>${expS}</b> &nbsp; Gain <b>${gain}</b> &nbsp; Off <b>${off}</b>${warn}`;
    // Show Apply whenever valid settings are returned, not just on OK.
    // NO_SIGNAL / GAIN_LIMIT_REACHED still carry the best-found max settings
    // which the user should be able to apply to the preview.
    const canApply = !d.error && d.exposure_ms != null && d.gain != null
        && d.status !== 'AUTO_GAIN_CANCELLED'
        && d.status !== 'AUTO_GAIN_UNSUPPORTED';
    if (canApply) {
      _agLastResult = { exposure_ms: d.exposure_ms, gain: d.gain, offset: d.offset ?? 0 };
      applyBtn.style.display = '';
    } else {
      applyBtn.style.display = 'none';
    }

    // Show diagnostic prompt only for NO_SIGNAL on a non-diagnostic run
    if (diagPrompt) {
      diagPrompt.style.display =
        (d.status === 'AUTO_GAIN_NO_SIGNAL' && !d.diagnostic) ? '' : 'none';
    }
    // Show force prompt for POSSIBLE_FOCUS_OR_POINTING_ERROR on a non-force run
    const forcePrompt = document.getElementById('autogain-force-prompt');
    if (forcePrompt) {
      forcePrompt.style.display =
        (d.status === 'AUTO_GAIN_POSSIBLE_FOCUS_OR_POINTING_ERROR') ? '' : 'none';
    }
}

function _agShowDiagResult(d) {
    const diagPrompt = document.getElementById('autogain-diag-prompt');
    const diagResult = document.getElementById('autogain-diag-result');
    const diagTitle  = document.getElementById('autogain-diag-title');
    const diagMsg    = document.getElementById('autogain-diag-msg');
    if (!diagResult) return;
    if (diagPrompt) diagPrompt.style.display = 'none';
    const info = _AG_DIAG_MESSAGES[d.status] || { title: d.status || 'Unknown', msg: d.warning_msg || '' };
    diagTitle.textContent = info.title;
    diagMsg.textContent   = (_focuserOk && info.msgWithFocuser) ? info.msgWithFocuser : info.msg;
    diagResult.style.display = '';
    // Expose Apply so the user can push the found max settings to the preview.
    const applyBtn  = document.getElementById('autogain-apply-btn');
    const resultRow = document.getElementById('autogain-result-row');
    if (applyBtn && d.exposure_ms != null && d.gain != null) {
        _agLastResult = { exposure_ms: d.exposure_ms, gain: d.gain, offset: d.offset ?? 0 };
        applyBtn.style.display = '';
        if (resultRow) resultRow.style.display = '';
    }
}

let _agIsDiag     = false;  // true while polling a diagnostic run
let _agCancelled  = false;  // race-guard: suppress stale poll callbacks after cancel

async function _agPoll() {
    if (_agCancelled) return;
    try {
      const r = await fetch('/api/autogain/status');
      if (!r.ok) return;
      const d = await r.json();
      if (_agCancelled) return;  // check again — cancel may have fired while awaiting
      if (d.running) {
        // Show "Cancelling…" once the server acknowledges the cancel request
        if (d.cancelling) {
          const badge = document.getElementById('autogain-status-badge');
          if (badge) { badge.style.display = ''; badge.style.color = 'var(--muted)'; badge.innerHTML = '<span class="spin"></span> Cancelling…'; }
        }
        return;
      }
      clearInterval(_agPollTimer);
      _agPollTimer = null;
      _agSetBusy(false);
      // Treat a CANCELLED result the same as a user-initiated cancel — don't show error badge
      if (d.status === 'AUTO_GAIN_CANCELLED') {
        const badge = document.getElementById('autogain-status-badge');
        if (badge) { badge.style.display = ''; badge.style.color = 'var(--muted)'; badge.textContent = 'Cancelled'; }
      } else if (_agIsDiag) {
        _agIsDiag = false;
        _agShowDiagResult(d);
      } else {
        _agShowResult(d);
      }
      if (_agPreviewWasRunning) { _agPreviewWasRunning = false; previewStart(); }
    } catch (_) { /* ignore transient network error */ }
}

async function autoGainDiagnostic() {
    const camRole = document.getElementById('preview-cam-select')?.value || 'main';
    const diagPrompt = document.getElementById('autogain-diag-prompt');
    const diagResult = document.getElementById('autogain-diag-result');
    if (diagPrompt) diagPrompt.style.display = 'none';
    if (diagResult) diagResult.style.display = 'none';

    _agIsDiag    = true;
    _agCancelled = false;
    _agPreviewWasRunning = _reconnect && _ws !== null;
    if (_agPreviewWasRunning) previewStop();
    _agSetBusy(true);
    const badge = document.getElementById('autogain-status-badge');
    if (badge) { badge.style.display = ''; badge.style.color = 'var(--muted)'; badge.innerHTML = '<span class="spin"></span> Diagnostic…'; }

    try {
      const r = await fetch('/api/autogain/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_role: camRole, diagnostic: true, max_iterations: 15 }),
      });
      if (!r.ok) {
        _agIsDiag = false;
        _agSetBusy(false);
        if (_agPreviewWasRunning) { _agPreviewWasRunning = false; previewStart(); }
        const d = await r.json().catch(() => ({}));
        if (badge) { badge.textContent = '⚠ ' + (d.detail || r.statusText); }
        return;
      }
    } catch (err) {
      _agIsDiag = false;
      _agSetBusy(false);
      if (_agPreviewWasRunning) { _agPreviewWasRunning = false; previewStart(); }
      if (badge) { badge.textContent = '⚠ Network error'; }
      return;
    }
    _agPollTimer = setInterval(_agPoll, 1500);
}

function autoGainDiagDismiss() {
    const diagPrompt = document.getElementById('autogain-diag-prompt');
    if (diagPrompt) diagPrompt.style.display = 'none';
}

async function autoGainForce() {
    const forcePrompt = document.getElementById('autogain-force-prompt');
    if (forcePrompt) forcePrompt.style.display = 'none';
    const camRole = document.getElementById('preview-cam-select')?.value || 'main';
    const badge  = document.getElementById('autogain-status-badge');
    const row    = document.getElementById('autogain-result-row');
    if (badge) { badge.style.display = ''; badge.style.color = 'var(--muted)'; badge.innerHTML = '<span class="spin"></span> Running…'; }
    if (row)   { row.style.display = 'none'; }
    _agLastResult = null;
    _agIsDiag    = false;
    _agCancelled = false;
    _agPreviewWasRunning = _reconnect && _ws !== null;
    if (_agPreviewWasRunning) previewStop();
    _agSetBusy(true);
    try {
      const r = await fetch('/api/autogain/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_role: camRole, force: true }),
      });
      if (!r.ok) {
        _agSetBusy(false);
        if (_agPreviewWasRunning) { _agPreviewWasRunning = false; previewStart(); }
        const d = await r.json().catch(() => ({}));
        if (badge) { badge.textContent = '⚠ ' + (d.detail || r.statusText); }
        return;
      }
    } catch (err) {
      _agSetBusy(false);
      if (_agPreviewWasRunning) { _agPreviewWasRunning = false; previewStart(); }
      if (badge) { badge.textContent = '⚠ Network error'; }
      return;
    }
    _agPollTimer = setInterval(_agPoll, 1500);
}

async function autoGainRun() {
    const camRole = document.getElementById('preview-cam-select')?.value || 'main';
    const badge  = document.getElementById('autogain-status-badge');
    const row    = document.getElementById('autogain-result-row');
    const diagPrompt = document.getElementById('autogain-diag-prompt');
    const diagResult = document.getElementById('autogain-diag-result');
    const forcePrompt = document.getElementById('autogain-force-prompt');
    if (badge) { badge.style.display = 'none'; }
    if (row)   { row.style.display = 'none'; }
    if (diagPrompt) diagPrompt.style.display = 'none';
    if (diagResult) diagResult.style.display = 'none';
    if (forcePrompt) forcePrompt.style.display = 'none';
    _agLastResult = null;
    _agIsDiag    = false;
    _agCancelled = false;

    _agPreviewWasRunning = _reconnect && _ws !== null;
    if (_agPreviewWasRunning) previewStop();
    _agSetBusy(true);
    try {
      const r = await fetch('/api/autogain/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_role: camRole }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        _agSetBusy(false);
        if (_agPreviewWasRunning) { _agPreviewWasRunning = false; previewStart(); }
        if (badge) { badge.style.display = ''; badge.style.color = 'var(--warn,#f5a623)'; badge.textContent = '⚠ ' + (d.detail || r.statusText); }
        return;
      }
    } catch (err) {
      _agSetBusy(false);
      if (_agPreviewWasRunning) { _agPreviewWasRunning = false; previewStart(); }
      if (badge) { badge.style.display = ''; badge.style.color = 'var(--warn,#f5a623)'; badge.textContent = '⚠ Network error'; }
      return;
    }
    // Poll until done
    _agPollTimer = setInterval(_agPoll, 1500);
}

function autoGainCancel() {
    // Stop polling immediately — do not await network to keep the UI responsive
    clearInterval(_agPollTimer);
    _agPollTimer = null;
    _agCancelled = true;
    _agSetBusy(false);
    const resultRow  = document.getElementById('autogain-result-row');
    const diagPrompt = document.getElementById('autogain-diag-prompt');
    const diagResult = document.getElementById('autogain-diag-result');
    if (resultRow)  resultRow.style.display  = 'none';
    if (diagPrompt) diagPrompt.style.display = 'none';
    if (diagResult) diagResult.style.display = 'none';
    const badge = document.getElementById('autogain-status-badge');
    if (badge) { badge.style.display = ''; badge.style.color = 'var(--muted)'; badge.textContent = 'Cancelled'; }
    if (_agPreviewWasRunning) { _agPreviewWasRunning = false; previewStart(); }
    // Fire-and-forget — tell the server to stop the background thread
    fetch('/api/autogain/cancel', { method: 'POST' }).catch(() => {});
}

function autoGainApply() {
    if (!_agLastResult) return;
    const expEl = document.getElementById('preview-exposure');
    const gainEl = document.getElementById('preview-gain');
    const offEl  = document.getElementById('preview-offset');
    if (expEl)  expEl.value  = (_agLastResult.exposure_ms / 1000).toFixed(3);
    if (gainEl) gainEl.value = _agLastResult.gain;
    if (offEl)  offEl.value  = _agLastResult.offset;
    previewSendParams();
    const applyBtn = document.getElementById('autogain-apply-btn');
    if (applyBtn) { applyBtn.textContent = 'Applied'; setTimeout(() => { applyBtn.textContent = 'Apply'; }, 1500); }
}

/* ══════════════════════════════════════════════════════════════════════
     Guide Camera Auto Gain (Stage 4 — FR-GUIDE-001)
══════════════════════════════════════════════════════════════════════ */

let _guideAgPollTimer = null;

function guideAgRun() {
    const camIdx = parseInt(document.getElementById('guide-ag-cam-idx').value, 10) || 1;
    const model  = document.getElementById('guide-ag-model').value;
    const dot    = document.getElementById('guide-ag-dot');
    document.getElementById('guide-ag-run-btn').disabled = true;
    document.getElementById('guide-ag-cancel-btn').style.display = '';
    const badge = document.getElementById('guide-ag-status-badge');
    badge.style.display = '';
    badge.textContent = 'Running…';
    document.getElementById('guide-ag-result').style.display = 'none';
    if (dot) dot.className = 'dot dot-yellow';

    fetch('/api/autogain/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ camera_index: camIdx, camera_model: model, mode: 'GUIDING' }),
    }).then(async r => {
      if (r.status === 202) {
        _guideAgStartPolling();
      } else {
        const d = await r.json().catch(() => ({}));
        _guideAgSetIdle(r.status === 409
          ? 'Another run is in progress'
          : ('Error ' + r.status + (d.detail ? ': ' + d.detail : '')));
      }
    }).catch(e => _guideAgSetIdle('Network error: ' + e));
}

function guideAgCancel() {
    fetch('/api/autogain/cancel', { method: 'POST' });
}

function _guideAgSetIdle(msg) {
    const dot    = document.getElementById('guide-ag-dot');
    const runBtn = document.getElementById('guide-ag-run-btn');
    const cancelBtn = document.getElementById('guide-ag-cancel-btn');
    const badge  = document.getElementById('guide-ag-status-badge');
    runBtn.disabled = false;
    cancelBtn.style.display = 'none';
    if (msg) { badge.style.display = ''; badge.textContent = msg; }
    else badge.style.display = 'none';
    if (dot) dot.className = 'dot dot-grey';
}

function _guideAgStartPolling() {
    if (_guideAgPollTimer) clearInterval(_guideAgPollTimer);
    _guideAgPollTimer = setInterval(_guideAgPoll, 800);
}

async function _guideAgPoll() {
    try {
      const d = await fetch('/api/autogain/status').then(r => r.json());
      if (!d.running) {
        clearInterval(_guideAgPollTimer);
        _guideAgPollTimer = null;
        _guideAgShowResult(d);
      }
    } catch {}
}

function _guideAgShowResult(d) {
    const dot        = document.getElementById('guide-ag-dot');
    const resultDiv  = document.getElementById('guide-ag-result');
    const resultTxt  = document.getElementById('guide-ag-result-text');
    const lockedBadge = document.getElementById('guide-ag-locked-badge');
    const reuseBtn   = document.getElementById('guide-ag-reuse-btn');
    const badge      = document.getElementById('guide-ag-status-badge');

    _guideAgSetIdle(null);

    if (d.error) {
      badge.style.display = '';
      badge.textContent = 'Error: ' + d.error;
      if (dot) dot.className = 'dot dot-red';
      return;
    }

    const ok = d.status === 'AUTO_GAIN_OK';
    const label = d.status ? d.status.replace('AUTO_GAIN_', '').replace(/_/g, ' ') : 'Unknown';
    badge.style.display = '';
    badge.textContent = label;
    if (dot) dot.className = ok ? 'dot dot-green' : 'dot dot-red';

    if (d.exposure_ms != null) {
      resultDiv.style.display = '';
      resultTxt.textContent = `Exp: ${d.exposure_ms.toFixed(0)} ms  Gain: ${d.gain ?? '—'}`;
      if (ok) {
        lockedBadge.style.display = '';
        reuseBtn.style.display = '';
      } else {
        lockedBadge.style.display = 'none';
        reuseBtn.style.display = 'none';
      }
      if (d.warning_msg) {
        resultTxt.textContent += '  ⚠ ' + d.warning_msg;
      }
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Guide Monitor (Stage 4 — FR-GUIDE-002)
══════════════════════════════════════════════════════════════════════ */

const _GM_STATUS_COLORS = {
    GUIDE_GAIN_OK:  'var(--accent)',
    STAR_WEAK:      'var(--warning,#e67e22)',
    STAR_SATURATED: 'var(--warning,#e67e22)',
    ADJUSTED:       '#5b8dd9',
    DAWN_WARNING:   'var(--warn,#f5a623)',
};

let _gmPollTimer = null;

async function guideMonStart() {
    const camIdx   = parseInt(document.getElementById('guide-ag-cam-idx').value, 10) || 1;
    const model    = document.getElementById('guide-ag-model').value;
    try {
      const r = await fetch('/api/guide_monitor/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ camera_index: camIdx, camera_model: model }),
      });
      if (r.status === 202) {
        _gmSetRunning(true);
        _gmStartPolling();
      } else {
        const d = await r.json().catch(() => ({}));
        setStatus('s4-status', 'Monitor start failed: ' + (d.detail || r.status), true);
      }
    } catch (e) {
      setStatus('s4-status', 'Monitor start error: ' + e, true);
    }
}

async function guideMonStop() {
    await fetch('/api/guide_monitor/stop', { method: 'POST' }).catch(() => {});
    _gmSetRunning(false);
    if (_gmPollTimer) { clearInterval(_gmPollTimer); _gmPollTimer = null; }
}

