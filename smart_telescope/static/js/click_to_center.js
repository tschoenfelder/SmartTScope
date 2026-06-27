/* ══════════════════════════════════════════════════════════════════════
     Click-to-center — M8-025 / REQ-CLICK-001
     Handles preview-frame clicks in Stage 3 (plate-solve) and Stage 4
     (Bahtinov Preview + Defocus Donut). When unavailable, shows the
     exact gate reason.
══════════════════════════════════════════════════════════════════════ */

// Map frame prefix → banner element id + overlay element id (if any)
const _CTC_FRAMES = {
    's3':       { banner: 's3-ctc-banner',       overlay: 's3-preview-overlay'  },
    's4':       { banner: 's4-ctc-banner',       overlay: 's4-preview-overlay'  },
    's4-donut': { banner: 's4-donut-ctc-banner', overlay: null                  },
};

// Last registered click per frame (used by M8-026/028 for refinement + centering)
const _ctcLastClick = {};

/**
 * Called by onclick on each preview frame div.
 * Normalises pixel coordinates to the image dimensions.
 */
async function ctcHandlePreviewClick(event, frameKey) {
    const frame = event.currentTarget;
    const img = frame.querySelector('img');

    // Ignore clicks when no image is visible
    if (!img || img.style.display === 'none') return;

    // Convert click position to image-relative normalised coordinates
    const rect = img.getBoundingClientRect();
    const relX = event.clientX - rect.left;
    const relY = event.clientY - rect.top;

    // Ignore clicks outside image bounds
    if (relX < 0 || relY < 0 || relX > rect.width || relY > rect.height) return;

    // Scale to natural image pixel coords
    const scaleX = img.naturalWidth  / rect.width;
    const scaleY = img.naturalHeight / rect.height;
    const px = Math.round(relX * scaleX);
    const py = Math.round(relY * scaleY);

    const banner = document.getElementById(_CTC_FRAMES[frameKey].banner);
    if (!banner) return;

    // Show marker immediately for visual feedback
    _ctcDrawMarker(frameKey, relX, relY);

    // Check gate readiness
    let data;
    try {
        data = await (await fetch('/api/click_to_center/readiness')).json();
    } catch {
        _ctcShowBanner(banner, 'Could not reach server — click-to-center unavailable.', true);
        return;
    }

    if (!data.allowed) {
        const reason = data.reason || 'Click-to-center is not available right now.';
        _ctcShowBanner(banner, 'Click-to-center unavailable: ' + reason, true);
        _ctcClearMarker(frameKey);
        return;
    }

    // Store click for M8-026 refinement + M8-028 centering loop
    _ctcLastClick[frameKey] = { px, py, frameKey };
    _ctcShowBanner(banner, `Click registered at pixel (${px}, ${py}) — ready to center.`, false);
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

function _ctcDrawMarker(frameKey, x, y) {
    const cfg = _CTC_FRAMES[frameKey];
    const frame = document.getElementById(
        frameKey === 's3' ? 's3-preview-frame' :
        frameKey === 's4' ? 's4-preview-frame' :
        's4-donut-preview-frame'
    );
    if (!frame) return;

    // Remove old marker if present
    _ctcClearMarker(frameKey);

    const SIZE = 20;
    const el = document.createElement('div');
    el.style.cssText = [
        'position:absolute',
        'pointer-events:none',
        `left:${Math.round(x - SIZE / 2)}px`,
        `top:${Math.round(y - SIZE / 2)}px`,
        `width:${SIZE}px`,
        `height:${SIZE}px`,
        'border:2px solid #f59e0b',
        'border-radius:50%',
        'box-shadow:0 0 4px rgba(0,0,0,0.7)',
        'z-index:10',
    ].join(';');

    // Crosshair lines
    ['horizontal', 'vertical'].forEach(dir => {
        const line = document.createElement('div');
        if (dir === 'horizontal') {
            line.style.cssText = `position:absolute;top:50%;left:-6px;width:${SIZE + 12}px;height:2px;margin-top:-1px;background:#f59e0b;`;
        } else {
            line.style.cssText = `position:absolute;left:50%;top:-6px;width:2px;height:${SIZE + 12}px;margin-left:-1px;background:#f59e0b;`;
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

/** Returns the last registered click for a given frame, or null. */
function ctcGetLastClick(frameKey) {
    return _ctcLastClick[frameKey] || null;
}
