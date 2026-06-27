/* ══════════════════════════════════════════════════════════════════════
     Click-to-center — M8-025/026/027 / REQ-CLICK-001..003
     Handles preview-frame clicks in Stage 3 (plate-solve) and Stage 4
     (Bahtinov Preview + Defocus Donut). Refines to star centroid or
     ring center; shows exact gate/calibration reason when unavailable.
══════════════════════════════════════════════════════════════════════ */

// Map frame key → banner id + camera_index + default refinement mode
const _CTC_FRAMES = {
    's3':       { banner: 's3-ctc-banner',       cameraIndex: 0, mode: 'star_centroid' },
    's4':       { banner: 's4-ctc-banner',       cameraIndex: 0, mode: 'star_centroid' },
    's4-donut': { banner: 's4-donut-ctc-banner', cameraIndex: 0, mode: 'ring_center'   },
};

// Last refined click per frame (used by M8-028 centering loop)
const _ctcLastClick = {};

/**
 * Called by onclick on each preview frame div.
 * Normalises coordinates to image pixel space, checks gate, refines click.
 */
async function ctcHandlePreviewClick(event, frameKey) {
    const frame = event.currentTarget;
    const img = frame.querySelector('img');

    // Ignore clicks when no image is visible
    if (!img || img.style.display === 'none') return;

    const rect = img.getBoundingClientRect();
    const relX = event.clientX - rect.left;
    const relY = event.clientY - rect.top;

    if (relX < 0 || relY < 0 || relX > rect.width || relY > rect.height) return;

    const scaleX = img.naturalWidth  / rect.width;
    const scaleY = img.naturalHeight / rect.height;
    const rawPx = Math.round(relX * scaleX);
    const rawPy = Math.round(relY * scaleY);

    const cfg = _CTC_FRAMES[frameKey];
    const banner = document.getElementById(cfg.banner);
    if (!banner) return;

    // Show raw marker immediately for visual feedback
    _ctcDrawMarker(frameKey, relX, relY, 'raw');

    // 1. Check gate readiness
    let readiness;
    try {
        readiness = await (await fetch('/api/click_to_center/readiness')).json();
    } catch {
        _ctcShowBanner(banner, 'Could not reach server — click-to-center unavailable.', true);
        _ctcClearMarker(frameKey);
        return;
    }

    if (!readiness.allowed) {
        const reason = readiness.reason || 'Click-to-center is not available right now.';
        _ctcShowBanner(banner, 'Click-to-center unavailable: ' + reason, true);
        _ctcClearMarker(frameKey);
        return;
    }

    // 2. Refine click
    _ctcShowBanner(banner, 'Refining click…', false);
    let refined;
    try {
        refined = await (await fetch('/api/click_to_center/refine', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                x_px: rawPx,
                y_px: rawPy,
                camera_index: cfg.cameraIndex,
                mode: cfg.mode,
            }),
        })).json();
    } catch {
        refined = {
            raw_x: rawPx, raw_y: rawPy,
            refined_x: rawPx, refined_y: rawPy,
            method: 'raw_fallback', confidence: 0, fallback: true,
            fallback_reason: 'Refinement request failed.',
        };
    }

    // Store result for M8-028 centering loop
    _ctcLastClick[frameKey] = refined;

    // 3. Show refined marker (draw on top of raw)
    const refinedRelX = refined.refined_x / scaleX;
    const refinedRelY = refined.refined_y / scaleY;
    _ctcDrawMarker(frameKey, refinedRelX, refinedRelY, refined.fallback ? 'raw' : 'refined');

    // 4. Update banner
    if (refined.fallback) {
        const why = refined.fallback_reason || 'No feature found.';
        _ctcShowBanner(banner,
            `Using raw click (${rawPx}, ${rawPy}) — ${why}`, false);
    } else {
        const method = refined.method === 'star_centroid' ? 'star centroid'
                     : refined.method === 'ring_center'   ? 'ring center'
                     : refined.method;
        const conf = Math.round(refined.confidence * 100);
        _ctcShowBanner(banner,
            `${method} at (${refined.refined_x}, ${refined.refined_y}) — confidence ${conf}%`, false);
    }
}

function _ctcShowBanner(el, text, isError) {
    el.style.display = '';
    el.style.color = isError ? 'var(--danger)' : 'var(--text)';
    el.textContent = text;
}

function ctcClearBanner(frameKey) {
    const cfg = _CTC_FRAMES[frameKey];
    if (!cfg) return;
    const el = document.getElementById(cfg.banner);
    if (el) { el.style.display = 'none'; el.textContent = ''; }
    _ctcClearMarker(frameKey);
    delete _ctcLastClick[frameKey];
}

// ── Marker overlay ─────────────────────────────────────────────────────────

let _ctcMarkerEls = {};

const _FRAME_ID = {
    's3':       's3-preview-frame',
    's4':       's4-preview-frame',
    's4-donut': 's4-donut-preview-frame',
};

function _ctcDrawMarker(frameKey, x, y, kind) {
    const frame = document.getElementById(_FRAME_ID[frameKey]);
    if (!frame) return;

    _ctcClearMarker(frameKey);

    const SIZE = 20;
    // Amber for raw/fallback, green for refined
    const COLOR = kind === 'refined' ? '#22c55e' : '#f59e0b';
    const el = document.createElement('div');
    el.style.cssText = [
        'position:absolute',
        'pointer-events:none',
        `left:${Math.round(x - SIZE / 2)}px`,
        `top:${Math.round(y - SIZE / 2)}px`,
        `width:${SIZE}px`,
        `height:${SIZE}px`,
        `border:2px solid ${COLOR}`,
        'border-radius:50%',
        'box-shadow:0 0 4px rgba(0,0,0,0.7)',
        'z-index:10',
    ].join(';');

    ['horizontal', 'vertical'].forEach(dir => {
        const line = document.createElement('div');
        if (dir === 'horizontal') {
            line.style.cssText = `position:absolute;top:50%;left:-6px;width:${SIZE + 12}px;height:2px;margin-top:-1px;background:${COLOR};`;
        } else {
            line.style.cssText = `position:absolute;left:50%;top:-6px;width:2px;height:${SIZE + 12}px;margin-left:-1px;background:${COLOR};`;
        }
        el.appendChild(line);
    });

    frame.style.position = 'relative';
    frame.appendChild(el);
    _ctcMarkerEls[frameKey] = el;
}

function _ctcClearMarker(frameKey) {
    const el = _ctcMarkerEls[frameKey];
    if (el && el.parentNode) el.parentNode.removeChild(el);
    delete _ctcMarkerEls[frameKey];
}

/** Returns the last refined click for a given frame, or null. */
function ctcGetLastClick(frameKey) {
    return _ctcLastClick[frameKey] || null;
}

// ── Calibration helpers (M8-027) ───────────────────────────────────────────

/**
 * Fetch calibration status for optical_train/binning and update a status element.
 * Called on stage entry to warn the user when calibration is missing.
 */
async function ctcRefreshCalibrationStatus(elementId, opticalTrain = 'default', binning = 1) {
    const el = document.getElementById(elementId);
    if (!el) return;
    try {
        const data = await (await fetch(
            `/api/click_to_center/calibration?optical_train=${encodeURIComponent(opticalTrain)}&binning=${binning}`
        )).json();
        if (data.found && data.is_valid) {
            const age = data.age_hours !== undefined ? ` (${data.age_hours.toFixed(1)} h ago)` : '';
            el.style.display = '';
            el.style.color = 'var(--muted)';
            el.textContent = `CTC calibration OK${age} — click a star to center.`;
        } else {
            el.style.display = '';
            el.style.color = 'var(--warn, #f5a623)';
            el.textContent = data.reason || 'CTC calibration missing — click will be blocked.';
        }
    } catch {
        el.style.display = 'none';
    }
}
