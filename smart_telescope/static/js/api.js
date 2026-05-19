function escHtml(s) {
    return String(s)
      .replace(/&/g,'&amp;').replace(/</g,'&lt;')
      .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}


const _ERROR_PATTERNS = [
    // Mount / OnStep
    [/serial.*timeout|timeout.*serial|timed.*out.*serial/i,
      'Mount not responding', 'Check the USB/serial cable connection and retry'],
    [/serial.*error|serial.*exception|write.*fail|read.*fail/i,
      'Serial communication error', 'Check the cable and the serial port setting in smart_telescope.toml'],
    [/refused|rejected|denied.*command|command.*denied/i,
      'Command rejected by mount', 'Mount may be in an unsafe state — check alignment and limits'],
    [/not.*connected|connect.*fail|disconnected/i,
      'Mount not connected', 'Use Connect All on Stage 1 to reconnect'],
    [/not.*initial|not.*aligned|align.*required/i,
      'Mount needs alignment', 'Complete the alignment procedure in Stage 2'],
    [/below.*horizon|above.*meridian|at.*limit|unsafe.*position/i,
      'Target is in an unsafe position', 'Choose a target above the horizon and within mount limits'],
    // Camera
    [/camera.*not.*found|no.*camera|cannot.*open.*camera|open.*device.*fail/i,
      'Camera not connected', 'Check the USB connection and verify the ToupTek driver is installed'],
    [/capture.*timeout|exposure.*timeout|grab.*timeout/i,
      'Camera capture timed out', 'Check the USB cable — try a shorter exposure'],
    [/camera.*error|camera.*exception/i,
      'Camera error', 'Check USB connection and restart'],
    // Solver
    [/astap.*not.*found|no.*astap/i,
      'Plate solver not installed', 'Download and install ASTAP from hnsky.org/astap'],
    [/catalog.*not.*found|no.*catalog|no.*star.*catalog/i,
      'Star catalog not found', 'Download the ASTAP D80 catalog and extract it to the catalog directory'],
    [/no.*stars.*found|no.*stars.*detect|too.*few.*stars/i,
      'No stars detected', 'Check focus and try a longer exposure'],
    [/plate.*solve.*fail|solution.*fail|wcs.*fail/i,
      'Plate solve failed', 'Verify the target is in the field and the star catalog is installed'],
    // Storage
    [/no.*space.*left|disk.*full|storage.*full/i,
      'Storage full', 'Free up disk space in the storage directory'],
    [/permission.*denied|cannot.*write|cannot.*save/i,
      'Cannot write to storage', 'Check permissions on the storage directory'],
];

function friendlyError(raw) {
    const s = String(raw);
    for (const [pat, message, hint] of _ERROR_PATTERNS) {
      if (pat.test(s)) return { message, hint };
    }
    return { message: s, hint: null };
}

function setStatus(id, msg, isError = false) {
    const el = document.getElementById(id);
    if (!el) return;
    if (isError && msg) {
      const { message, hint } = friendlyError(msg);
      el.innerHTML = escHtml(message) +
        (hint ? `<br><span style="font-size:0.76em;color:var(--muted)">${escHtml(hint)}</span>` : '') +
        `<br><a href="#" onclick="goToStage(1);return false"
               style="font-size:0.73em;color:var(--accent);text-decoration:none">→ Setup &amp; Diagnostics</a>`;
    } else {
      el.textContent = msg;
    }
    el.className = 'status-line' + (isError ? ' error' : '');
}

async function apiPost(url, body) {
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!resp.ok) {
      const text = await resp.text();
      const err = new Error(text || `Server error ${resp.status}`);
      try {
        const parsed = JSON.parse(text);
        if (typeof parsed?.detail === 'string') err.message = parsed.detail;
        else if (parsed?.detail !== undefined) err.message = JSON.stringify(parsed.detail);
      } catch {}
      throw err;
    }
    return resp.json();
}

