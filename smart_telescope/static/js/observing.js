/* ══════════════════════════════════════════════════════════════════════
     Observe screen — the guided single-flow UI (smarttscope_requirements_
     full.md §6-7). This file only renders what /api/observing/state
     returns and posts whatever intent the user picks (REQ-UX-004): it
     contains no phase-sequencing logic of its own.
══════════════════════════════════════════════════════════════════════ */

const _GUARD_LABELS = {
    g1_context_confirmed:      'Time & location confirmed (G1)',
    g2_home_confirmed:         'HOME confirmed (G2)',
    g3_polar_within_tolerance: 'Polar alignment within tolerance (G3)',
    g4_focus_sufficient:       'Focus quality sufficient (G4)',
    g5_target_centered:        'Target centered (G5)',
    g6_guiding_ok:              'Guiding stable / not required (G6)',
    g7_session_may_continue:   'Session may continue (G7)',
    g8_safe_stop_possible:     'Safe stop achieved (G8)',
    g9_error_recoverable:      'Error recoverable (G9)',
    g10_error_unrecoverable:   'Error not recoverable (G10)',
};

let _obsPollTimer = null;
let _obsBusy = false;
let _obsLastState = null;
let _obsLocPanelDirty = false;
let _obsLastLocationStatus = null;
let _obsLocSource = 'CONFIG_FILE';

function _obsGuardDotClass(value) {
    if (value === true) return 'dot-green';
    if (value === false) return 'dot-red';
    return 'dot-grey';
}

function _renderObservingState(state) {
    _obsLastState = state;
    document.getElementById('obs-phase-title').textContent = _obsPhaseLabel(state.phase);

    const badge = document.getElementById('obs-readiness-badge');
    badge.textContent = state.readiness.replace('_', ' ');
    badge.className = 'phase-readiness ' + state.readiness;

    // M9-029: observed mount state next to the readiness badge (null until
    // the first DeviceStateService poll lands — hide the badge then).
    const mountBadge = document.getElementById('obs-mount-state-badge');
    if (state.mount_state) {
      mountBadge.style.display = '';
      mountBadge.textContent = 'MOUNT: ' + state.mount_state.replace(/_/g, ' ');
    } else {
      mountBadge.style.display = 'none';
    }

    const faultBanner = document.getElementById('obs-fault-banner');
    if (state.phase === 'FAULT' && state.fault_message) {
      faultBanner.style.display = '';
      document.getElementById('obs-fault-message').textContent = state.fault_message;
    } else {
      faultBanner.style.display = 'none';
    }

    // WAIT_CONTEXT_CONFIRMATION gets the full Time & Location review panel
    // instead of a blind "Confirm time & location" button — the panel's own
    // Confirm button posts /api/location/confirm, then sends this same intent.
    const showContextCard = state.phase === 'WAIT_CONTEXT_CONFIRMATION';
    document.getElementById('obs-context-card').style.display = showContextCard ? '' : 'none';
    if (showContextCard) _obsRefreshLocationPanel();

    const primaryBtn = document.getElementById('obs-primary-btn');
    const primary = state.primary_action;
    if (showContextCard) {
      primaryBtn.style.display = 'none';
      primaryBtn.onclick = null;
    } else if (primary && primary.intent) {
      primaryBtn.style.display = '';
      primaryBtn.textContent = primary.label;
      primaryBtn.disabled = !primary.enabled || _obsBusy;
      primaryBtn.onclick = () => _sendObservingIntent(primary.intent);
    } else {
      primaryBtn.style.display = '';
      primaryBtn.textContent = (primary && primary.label) || '—';
      primaryBtn.disabled = true;
      primaryBtn.onclick = null;
    }

    const secondaryEl = document.getElementById('obs-secondary-actions');
    secondaryEl.innerHTML = '';
    for (const action of state.secondary_actions || []) {
      const btn = document.createElement('button');
      btn.className = 'secondary';
      btn.textContent = action.label;
      btn.disabled = _obsBusy;
      btn.onclick = () => _sendObservingIntent(action.intent);
      secondaryEl.appendChild(btn);
    }

    const guardGrid = document.getElementById('obs-guard-grid');
    guardGrid.innerHTML = '';
    for (const [key, label] of Object.entries(_GUARD_LABELS)) {
      const value = state.guards[key];
      const chip = document.createElement('div');
      chip.className = 'guard-chip';
      chip.innerHTML = `<span class="dot ${_obsGuardDotClass(value)}"></span>${escHtml(label)}`;
      guardGrid.appendChild(chip);
    }

    document.getElementById('obs-detail-json').textContent =
      Object.keys(state.detail || {}).length ? JSON.stringify(state.detail, null, 2) : '—';

    _obsBusy = !!state.busy;
}

function _obsPhaseLabel(phase) {
    return String(phase).replaceAll('_', ' ');
}

async function refreshObservingState() {
    try {
      const state = await (await fetch('/api/observing/state')).json();
      _renderObservingState(state);
    } catch (e) {
      document.getElementById('obs-phase-title').textContent = 'Could not reach server';
    }
}

async function _sendObservingIntent(intent) {
    _obsBusy = true;
    try {
      const state = await apiPost('/api/observing/intent', { intent });
      _renderObservingState(state);
    } catch (e) {
      alert(e.message || 'Failed to send intent');
      await refreshObservingState();
    }
}

function _startObservingPoll() {
    if (_obsPollTimer) return;
    refreshObservingState();
    _obsPollTimer = setInterval(refreshObservingState, 2500);
}

/* ── Time & Location review panel (WAIT_CONTEXT_CONFIRMATION only) ────────
   Mirrors static/js/setup.js's Confirm Time & Location panel against the
   same /api/location/* endpoints — kept as a separate copy (obs-loc-* ids)
   rather than sharing DOM nodes with the Maintenance screen's s1-tl-card,
   since both screens can be visible/rendered independently. */

function _obsMarkLocationDirty() { _obsLocPanelDirty = true; }

function _obsSetLocSource(src) {
    _obsLocSource = src;
    const b = document.getElementById('obs-loc-source-badge');
    if (b) {
        b.textContent = src;
        b.classList.toggle('badge-ok', src === 'GPS_FIX');
    }
}

function _obsOnLocationFieldInput() {
    _obsMarkLocationDirty();
    _obsSetLocSource('USER_ENTERED');
}

function _obsRenderLocationPanel(d) {
    _obsLastLocationStatus = d;

    const timeEl = document.getElementById('obs-loc-local-time');
    if (timeEl) timeEl.textContent = formatLocalTime(d.local_time_iso);
    const gpsBadge = document.getElementById('obs-loc-gps-badge');
    if (gpsBadge) gpsBadge.style.display = d.time_from_gps ? '' : 'none';
    const trustBadge = document.getElementById('obs-loc-time-trust-badge');
    if (trustBadge) {
        trustBadge.textContent = timeTrustLabel(d.time_trust_source);
        trustBadge.classList.toggle('badge-ok', timeTrustIsOk(d.time_trust_source));
    }
    const gpsBtn = document.getElementById('obs-loc-gps-btn');
    if (gpsBtn) gpsBtn.disabled = !(d.gps && d.gps.usable);
    const confirmBtn = document.getElementById('obs-loc-confirm-btn');
    if (confirmBtn) confirmBtn.disabled = false;

    if (_obsLocPanelDirty) return;

    const select = document.getElementById('obs-loc-select');
    if (select) {
        const homeLabel = (d.home && d.home.name) || 'Home';
        const optionDefs = [
            { value: 'Home', label: homeLabel },
            ...d.saved_locations.map(l => ({ value: l.name, label: l.name })),
            { value: '__new__', label: '+ New location…' },
        ];
        select.innerHTML = optionDefs.map(o =>
            `<option value="${escHtml(o.value)}">${escHtml(o.label)}</option>`).join('');
        select.value = d.active.name;
    }

    const latEl = document.getElementById('obs-loc-lat-input');
    const lonEl = document.getElementById('obs-loc-lon-input');
    const heightEl = document.getElementById('obs-loc-height-input');

    if (d.gps && d.gps.usable) {
        if (latEl) latEl.value = d.gps.lat;
        if (lonEl) lonEl.value = d.gps.lon;
        if (heightEl && d.gps.alt_m !== null && d.gps.alt_m !== undefined) heightEl.value = d.gps.alt_m;
        else if (heightEl) heightEl.value = d.active.height_m;
        _obsSetLocSource('GPS_FIX');
    } else {
        if (latEl) latEl.value = d.active.lat;
        if (lonEl) lonEl.value = d.active.lon;
        if (heightEl) heightEl.value = d.active.height_m;
        _obsSetLocSource(d.active.source);
    }

    const nameRow = document.getElementById('obs-loc-name-row');
    if (nameRow) nameRow.style.display = 'none';
    const delBtn = document.getElementById('obs-loc-delete-btn');
    if (delBtn) delBtn.style.display = d.active.name !== 'Home' ? '' : 'none';
}

async function _obsRefreshLocationPanel() {
    try {
        const d = await (await fetch('/api/location/status')).json();
        _obsRenderLocationPanel(d);
    } catch (_) {}
}

function _obsOnLocationSelectChange() {
    const select = document.getElementById('obs-loc-select');
    const value = select ? select.value : 'Home';
    const nameRow = document.getElementById('obs-loc-name-row');
    const nameInput = document.getElementById('obs-loc-name-input');
    const delBtn = document.getElementById('obs-loc-delete-btn');
    const latEl = document.getElementById('obs-loc-lat-input');
    const lonEl = document.getElementById('obs-loc-lon-input');
    const heightEl = document.getElementById('obs-loc-height-input');

    if (value === '__new__') {
        if (nameRow) nameRow.style.display = '';
        if (nameInput) nameInput.value = '';
        if (latEl) latEl.value = '';
        if (lonEl) lonEl.value = '';
        if (heightEl) heightEl.value = '';
        _obsSetLocSource('USER_ENTERED');
        if (delBtn) delBtn.style.display = 'none';
        _obsMarkLocationDirty();
        return;
    }

    if (nameRow) nameRow.style.display = 'none';
    const d = _obsLastLocationStatus;
    if (!d) return;
    const entry = value === 'Home' ? d.home : d.saved_locations.find(l => l.name === value);
    if (!entry) return;
    if (latEl) latEl.value = entry.lat;
    if (lonEl) lonEl.value = entry.lon;
    if (heightEl) heightEl.value = entry.height_m;
    _obsSetLocSource(value === 'Home' ? 'CONFIG_FILE' : 'SAVED_LOCATION');
    if (delBtn) delBtn.style.display = value !== 'Home' ? '' : 'none';
    _obsMarkLocationDirty();
}

function _obsUseGpsFix() {
    const gps = _obsLastLocationStatus && _obsLastLocationStatus.gps;
    if (!gps || !gps.usable) {
        setStatus('obs-loc-status', 'No usable GPS fix available', true);
        return;
    }
    const latEl = document.getElementById('obs-loc-lat-input');
    const lonEl = document.getElementById('obs-loc-lon-input');
    const heightEl = document.getElementById('obs-loc-height-input');
    if (latEl) latEl.value = gps.lat;
    if (lonEl) lonEl.value = gps.lon;
    if (heightEl && gps.alt_m !== null && gps.alt_m !== undefined) heightEl.value = gps.alt_m;
    _obsSetLocSource('GPS_FIX');
    _obsMarkLocationDirty();
}

async function _obsLookupByIp() {
    setStatus('obs-loc-status', 'Looking up location by IP…');
    try {
        const g = await (await fetch('/api/location/ip-lookup')).json();
        if (!g.available) {
            setStatus('obs-loc-status', 'IP lookup failed — no result', true);
            return;
        }
        const latEl = document.getElementById('obs-loc-lat-input');
        const lonEl = document.getElementById('obs-loc-lon-input');
        if (latEl) latEl.value = g.lat;
        if (lonEl) lonEl.value = g.lon;
        _obsSetLocSource('IP_LOOKUP');
        _obsMarkLocationDirty();
        setStatus('obs-loc-status', '');
    } catch (e) {
        setStatus('obs-loc-status', e.message, true);
    }
}

async function _obsConfirmPiTime() {
    setStatus('obs-loc-status', 'Confirming Pi clock…');
    try {
        await apiPost('/api/mount/confirm_time');
        await _obsRefreshLocationPanel();
        setStatus('obs-loc-status', 'Pi clock confirmed — trust source: USER_CONFIRMED');
    } catch (e) {
        setStatus('obs-loc-status', e.message, true);
    }
}

async function _obsConfirmTimeAndLocation() {
    const select = document.getElementById('obs-loc-select');
    const value = select ? select.value : 'Home';
    const lat = parseFloat(document.getElementById('obs-loc-lat-input').value);
    const lon = parseFloat(document.getElementById('obs-loc-lon-input').value);
    const height_m = parseFloat(document.getElementById('obs-loc-height-input').value) || 0.0;

    let target, name;
    if (value === 'Home') {
        target = 'home';
        name = undefined;
    } else if (value === '__new__') {
        target = 'saved';
        name = document.getElementById('obs-loc-name-input').value.trim();
    } else {
        target = 'saved';
        name = value;
    }

    setStatus('obs-loc-status', 'Confirming…');
    try {
        await apiPost('/api/location/confirm', {target, name, lat, lon, height_m, source: _obsLocSource});
        _obsLocPanelDirty = false;
        const intent = (_obsLastState && _obsLastState.primary_action &&
                        _obsLastState.primary_action.intent) || 'CONFIRM_CONTEXT';
        await _sendObservingIntent(intent);
    } catch (e) {
        setStatus('obs-loc-status', e.message, true);
    }
}

async function _obsDeleteSavedLocation() {
    const select = document.getElementById('obs-loc-select');
    const name = select ? select.value : null;
    if (!name || name === 'Home' || name === '__new__') return;
    try {
        const resp = await fetch('/api/location/saved/' + encodeURIComponent(name), {method: 'DELETE'});
        if (!resp.ok) {
            const body = await resp.json().catch(() => ({}));
            throw new Error(body.detail || 'Delete failed');
        }
        _obsLocPanelDirty = false;
        await _obsRefreshLocationPanel();
    } catch (e) {
        setStatus('obs-loc-status', e.message, true);
    }
}

_startObservingPoll();
