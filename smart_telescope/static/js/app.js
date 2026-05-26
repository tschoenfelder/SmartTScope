/* ══════════════════════════════════════════════════════════════════════
     App-wide state
══════════════════════════════════════════════════════════════════════ */
let _mountConnected  = false;
let _focuserOk       = false;
let _mountPendingCmd = null;   // set to command name while hardware is catching up
let _focusCamRole    = 'main';  // optical train role used for autofocus (set in Stage 1 focuser tile)
let _opticalTrains   = [];      // cached optical train list from /api/optical_trains

/* ── Advanced mode (UX4-001/002/003) ─────────────────────────────────── */
let _advancedMode = localStorage.getItem('tsc_advanced_mode') === '1';

function _applyAdvancedMode() {
    document.body.classList.toggle('advanced-mode', _advancedMode);
    const btn = document.getElementById('adv-toggle');
    if (btn) {
      btn.style.color       = _advancedMode ? 'var(--accent-hi)' : 'var(--muted)';
      btn.style.borderColor = _advancedMode ? 'var(--accent-hi)' : 'var(--border)';
    }
}

function toggleAdvancedMode() {
    _advancedMode = !_advancedMode;
    localStorage.setItem('tsc_advanced_mode', _advancedMode ? '1' : '0');
    _applyAdvancedMode();
}

let _observerLat     = 50.336;
let _observerLon     = 8.533;
let _clockInterval   = null;

const _stage = {
    current:   1,
    unlocked:  new Set([1]),
    completed: new Set(),
};

/* ══════════════════════════════════════════════════════════════════════
     Utilities
══════════════════════════════════════════════════════════════════════ */

/* ══════════════════════════════════════════════════════════════════════
     Stage navigation
══════════════════════════════════════════════════════════════════════ */
let _mountStripTimer = null;

function _startMountStripPoll() {
    if (_mountStripTimer) return;
    _mountStripTimer = setInterval(async () => {
      try {
        const data = await (await fetch('/api/mount/status')).json();
        _updateMountStrip(data);
      } catch {}
    }, 5000);
}

function _stopMountStripPoll() {
    clearInterval(_mountStripTimer);
    _mountStripTimer = null;
}

function goToStage(n) {
    if (!_stage.unlocked.has(n)) return;
    document.getElementById(`s${_stage.current}`).classList.remove('active');
    document.getElementById(`s${n}`).classList.add('active');
    _stage.current = n;
    // mount strip always visible; poll on all stages so timing race after OnStep boot resolves
    _startMountStripPoll();
    _renderStageBar();
    if (n === 4) { refreshFocuser(); loadCollimStars(); _refreshCollimWizardOnce(); }
    if (n === 5) { s5LoadTargets(); }
}

function unlockStage(n) {
    _stage.unlocked.add(n);
    _renderStageBar();
}

function completeStage(n) {
    _stage.completed.add(n);
    _renderStageBar();
}

function _renderStageBar() {
    for (let n = 1; n <= 5; n++) {
      const btn = document.getElementById(`stage-btn-${n}`);
      const num = document.getElementById(`stage-num-${n}`);
      if (!btn) continue;
      btn.disabled = !_stage.unlocked.has(n);
      btn.classList.toggle('active', n === _stage.current);
      btn.classList.toggle('done',   _stage.completed.has(n));
    }
}

/* ══════════════════════════════════════════════════════════════════════
     Clock & observer location (Stage 1)
══════════════════════════════════════════════════════════════════════ */
function _computeLST(lon_deg) {
    const now = new Date();
    const jd  = now.getTime() / 86400000.0 + 2440587.5;
    const T   = (jd - 2451545.0) / 36525.0;
    let gmst  = 6.697374558 + 2400.0513369 * T + 0.0000258622 * T * T;
    gmst = ((gmst % 24) + 24) % 24;
    let lst = gmst + lon_deg / 15.0;
    return ((lst % 24) + 24) % 24;
}

function _fmtHMS(h) {
    const hh = Math.floor(h);
    const mm = Math.floor((h - hh) * 60);
    const ss = Math.floor(((h - hh) * 60 - mm) * 60);
    return `${String(hh).padStart(2,'0')}h ${String(mm).padStart(2,'0')}m ${String(ss).padStart(2,'0')}s`;
}

function _tickClock() {
    const now = new Date();
    const utcStr = now.toUTCString().replace(' GMT','');
    const lst    = _computeLST(_observerLon);
    const utcEl  = document.getElementById('clock-utc');
    const lstEl  = document.getElementById('clock-lst');
    if (utcEl) utcEl.textContent = utcStr;
    if (lstEl) lstEl.textContent = _fmtHMS(lst);
}

async function initSiteConfig() {
    try {
      const d = await (await fetch('/api/mount/config')).json();
      _observerLat = d.observer_lat;
      _observerLon = d.observer_lon;
      const latEl = document.getElementById('site-lat');
      const lonEl = document.getElementById('site-lon');
      if (latEl) latEl.textContent = `${_observerLat.toFixed(4)}° N`;
      if (lonEl) lonEl.textContent = `${_observerLon.toFixed(4)}° E`;
      const altMinEl = document.getElementById("limit-alt-min");
      const altMaxEl = document.getElementById("limit-alt-max");
      const haEastEl = document.getElementById("limit-ha-east");
      const haWestEl = document.getElementById("limit-ha-west");
      if (altMinEl) altMinEl.textContent = d.mount_min_alt_deg.toFixed(1) + "°";
      if (altMaxEl) altMaxEl.textContent = d.mount_max_alt_deg.toFixed(1) + "°";
      if (haEastEl) haEastEl.textContent = d.mount_ha_east_limit_h.toFixed(2) + " h";
      if (haWestEl) haWestEl.textContent = d.mount_ha_west_limit_h.toFixed(2) + " h";
    } catch {}
    _tickClock();
    _clockInterval = setInterval(_tickClock, 1000);
}

async function loadVersion() {
    try {
      const v = await (await fetch('/api/version')).json();
      const pill = document.querySelector('header .pill');
      if (pill) {
        pill.textContent = v.git_hash ? `v${v.version} ${v.git_hash}` : `v${v.version}`;
        pill.title = `SmartTScope v${v.version}${v.git_hash ? ' (' + v.git_hash + ')' : ''}`;
      }
    } catch (_) {}
}

_applyAdvancedMode();
initSiteConfig();
loadVersion();
refreshMount();
_startMountStripPoll();
refreshReadiness();
refreshMilestones();
refreshHealth();
setInterval(refreshReadiness, 30_000);
setInterval(refreshHealth, 10_000);
loadFocuserCameras();
loadPreviewCameras();
_loadSelectFromTrains('s1-cooling-cam-select').then(async sel => {
    if (sel) await onCoolingCamChange(sel.value || 'main');
});
_loadSelectFromTrains('pa-cam-select').then(sel => {
    if (sel) onPaCamChange(sel.value || 'main');
});
loadStars();
updateElevationLabel();
// restore polar alignment state from server (in case page was reloaded mid-session)
_paPoll();
