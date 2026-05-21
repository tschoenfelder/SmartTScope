// smart_telescope/static/js/bias_estimation.js
// Bias-frame offset estimation wizard card (Stage 6)

let _beJobId = null;
let _bePollTimer = null;

function beLaunchWizard() {
  document.getElementById("be-wizard-section").style.display = "block";
  document.getElementById("be-launch-btn").style.display = "none";
  beResetState();
}

function beHideWizard() {
  document.getElementById("be-wizard-section").style.display = "none";
  document.getElementById("be-launch-btn").style.display = "";
  if (_bePollTimer) { clearInterval(_bePollTimer); _bePollTimer = null; }
  _beJobId = null;
}

function beResetState() {
  document.getElementById("be-status").textContent = "";
  document.getElementById("be-results-table").innerHTML = "";
  document.getElementById("be-recommendation").textContent = "";
  document.getElementById("be-toml-snippet").textContent = "";
  document.getElementById("be-toml-section").style.display = "none";
}

async function beStartEstimation() {
  const cameraRole = document.getElementById("be-camera-role").value;
  const gainMode   = document.getElementById("be-gain-mode").value;
  const frameCount = parseInt(document.getElementById("be-frame-count").value, 10) || 10;
  const runSweep   = document.getElementById("be-run-sweep").checked;

  beResetState();
  document.getElementById("be-status").textContent = "Starting estimation…";

  const resp = await apiPost("/api/bias_estimation/start", {
    camera_role: cameraRole,
    gain_mode:   gainMode,
    frame_count: frameCount,
    run_sweep:   runSweep,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    document.getElementById("be-status").textContent =
      "Error: " + (err.detail || resp.statusText);
    return;
  }

  const data = await resp.json();
  _beJobId = data.job_id;
  document.getElementById("be-status").textContent = "Running…";
  _bePollTimer = setInterval(bePollStatus, 500);
}

async function bePollStatus() {
  if (!_beJobId) return;
  const resp = await fetch(`/api/bias_estimation/status/${_beJobId}`);
  if (!resp.ok) return;
  const data = await resp.json();

  if (data.status === "RUNNING") return;  // keep polling

  clearInterval(_bePollTimer);
  _bePollTimer = null;

  if (data.status === "FAILED" || data.status === "CANCELLED") {
    document.getElementById("be-status").textContent =
      data.status + ": " + (data.error || "");
    return;
  }

  // DONE
  document.getElementById("be-status").textContent =
    `Done — ${data.frame_count} frames captured`;

  // Build results table
  const table = document.getElementById("be-results-table");
  table.innerHTML = `<tr>
    <th>Offset</th><th>Zero %</th><th>Min ADU</th><th>Safe?</th>
  </tr>`;
  for (const pt of (data.sweep || [])) {
    const row = document.createElement("tr");
    const safeBadge = pt.is_safe
      ? '<span style="color:green">✓ Safe</span>'
      : '<span style="color:red">✗ Clipping</span>';
    if (pt.offset === data.recommended_offset) {
      row.style.fontWeight = "bold";
      row.style.background = "#d4f4dd";
    }
    row.innerHTML = `<td>${pt.offset}</td>
      <td>${(pt.zero_fraction * 100).toFixed(3)}%</td>
      <td>${pt.min_val.toFixed(1)}</td>
      <td>${safeBadge}</td>`;
    table.appendChild(row);
  }

  // Recommendation + TOML snippet
  const recEl = document.getElementById("be-recommendation");
  if (data.safe) {
    recEl.textContent = `Recommended offset: ${data.recommended_offset}`;
    recEl.style.color = "green";
  } else {
    recEl.textContent =
      `No fully safe offset found. Best estimate: ${data.recommended_offset}. ` +
      `Consider re-running with higher offset range.`;
    recEl.style.color = "orange";
  }

  if (data.toml_snippet) {
    document.getElementById("be-toml-snippet").textContent = data.toml_snippet;
    document.getElementById("be-toml-section").style.display = "block";
  }
}
