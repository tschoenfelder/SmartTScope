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

function _obsGuardDotClass(value) {
    if (value === true) return 'dot-green';
    if (value === false) return 'dot-red';
    return 'dot-grey';
}

function _renderObservingState(state) {
    document.getElementById('obs-phase-title').textContent = _obsPhaseLabel(state.phase);

    const badge = document.getElementById('obs-readiness-badge');
    badge.textContent = state.readiness.replace('_', ' ');
    badge.className = 'phase-readiness ' + state.readiness;

    const faultBanner = document.getElementById('obs-fault-banner');
    if (state.phase === 'FAULT' && state.fault_message) {
      faultBanner.style.display = '';
      document.getElementById('obs-fault-message').textContent = state.fault_message;
    } else {
      faultBanner.style.display = 'none';
    }

    const primaryBtn = document.getElementById('obs-primary-btn');
    const primary = state.primary_action;
    if (primary && primary.intent) {
      primaryBtn.textContent = primary.label;
      primaryBtn.disabled = !primary.enabled || _obsBusy;
      primaryBtn.onclick = () => _sendObservingIntent(primary.intent);
    } else {
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

_startObservingPoll();
