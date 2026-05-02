"""Inject Bahtinov JS functions into index.html."""

import pathlib

HTML = pathlib.Path("C:/Users/tscho/Documents/Torsten/TSBrain/smart_telescope/static/index.html")
content = HTML.read_text(encoding="utf-8")

BAHTINOV_JS = r"""
  /* ══════════════════════════════════════════════════════════════════════
     Bahtinov analyzer (Stage 4)
  ══════════════════════════════════════════════════════════════════════ */

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
      _drawBahtinovOverlay(data);
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

"""

INSERT_BEFORE = (
    "  /* ══════════"
    "══════════"
    "══════════"
    "══════════"
    "══════════"
    "══════════"
    "══════════"
    "\n     Connect All (Stage 1)"
)

if INSERT_BEFORE in content:
    content = content.replace(INSERT_BEFORE, BAHTINOV_JS + INSERT_BEFORE, 1)
    print("Bahtinov JS inserted OK")
else:
    # Debug: show context around "Connect All"
    idx = content.find("Connect All (Stage 1)")
    print("MARKER NOT FOUND, context:", repr(content[max(0,idx-120):idx+30]))

HTML.write_text(content, encoding="utf-8")
