// Guide Monitor card — polls /api/guiding/status every 2 s when running.

let _guidingPollTimer = null;

function guidingStart() {
  apiPost('/api/guiding/start', {})
    .then(() => { _guidingPollStart(); })
    .catch(err => setStatus('s5-guide-status', 'Start failed: ' + err, true));
}

function guidingStop() {
  apiPost('/api/guiding/stop', {})
    .then(data => { _guidingUpdateCard(data); _guidingPollStop(); })
    .catch(err => setStatus('s5-guide-status', 'Stop failed: ' + err, true));
}

function _guidingPollStart() {
  if (_guidingPollTimer) return;
  _guidingPollTimer = setInterval(_guidingPoll, 2000);
  _guidingPoll();
}

function _guidingPollStop() {
  clearInterval(_guidingPollTimer);
  _guidingPollTimer = null;
}

function _guidingPoll() {
  fetch('/api/guiding/status')
    .then(r => r.json())
    .then(_guidingUpdateCard)
    .catch(() => {});
}

function _guidingUpdateCard(data) {
  const badge = document.getElementById('s5-guide-state-badge');
  const srcDiv = document.getElementById('s5-guide-sources');
  const pulseDiv = document.getElementById('s5-guide-pulses');
  if (!badge) return;

  const stateColors = { idle: 'secondary', running: 'success', failed: 'danger' };
  badge.className = `badge bg-${stateColors[data.state] || 'secondary'}`;
  badge.textContent = (data.state || 'idle').toUpperCase();

  let srcHtml = '';
  for (const [role, src] of Object.entries(data.sources || {})) {
    const healthColor = { healthy: 'success', transient_bad: 'warning', hard_failed: 'danger' }[src.health] || 'secondary';
    const active = data.active_role === role ? ' (active)' : '';
    srcHtml += `<span class="badge bg-${healthColor} me-1">${escHtml(role)}${active}</span>`;
    if (src.measurement && src.measurement.accepted) {
      srcHtml += ` cx=${src.measurement.centroid_x?.toFixed(1)} cy=${src.measurement.centroid_y?.toFixed(1)}`;
      srcHtml += ` snr=${src.measurement.confidence?.toFixed(2)}`;
    }
    srcHtml += '<br>';
  }
  srcDiv.innerHTML = srcHtml || '<em>No sources</em>';

  const pulses = data.latest_pulses || [];
  pulseDiv.textContent = pulses.length
    ? pulses.map(p => `${p.axis} ${p.direction} ${p.duration_ms}ms${p.clipped ? ' (clip)' : ''}`).join(', ')
    : data.state === 'running' ? '—' : '';

  if (data.state === 'running') {
    _guidingPollStart();
  } else {
    _guidingPollStop();
  }
}
