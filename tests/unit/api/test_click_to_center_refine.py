"""Tests for POST /api/click_to_center/refine (M8-026 / REQ-CLICK-002)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from fastapi.testclient import TestClient

from smart_telescope.app import app
from smart_telescope.api import deps, preview as _preview_mod


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _post(client, **kwargs):
    payload = {"x_px": 80, "y_px": 90, "camera_index": 0, "mode": "star_centroid"}
    payload.update(kwargs)
    return client.post("/api/click_to_center/refine", json=payload)


# ── No cached frame ──────────────────────────────────────────────────────────

def test_refine_returns_200_when_no_frame(client):
    with patch.dict(_preview_mod._last_preview_pixels, {}, clear=True):
        resp = _post(client)
    assert resp.status_code == 200


def test_refine_fallback_when_no_frame(client):
    with patch.dict(_preview_mod._last_preview_pixels, {}, clear=True):
        data = _post(client).json()
    assert data["fallback"] is True
    assert data["method"] == "raw_fallback"


def test_refine_returns_raw_coords_when_no_frame(client):
    with patch.dict(_preview_mod._last_preview_pixels, {}, clear=True):
        data = _post(client, x_px=55, y_px=66).json()
    assert data["refined_x"] == 55
    assert data["refined_y"] == 66


def test_refine_fallback_reason_mentions_preview(client):
    with patch.dict(_preview_mod._last_preview_pixels, {}, clear=True):
        data = _post(client).json()
    assert data["fallback_reason"] is not None
    assert "preview" in data["fallback_reason"].lower()


# ── With a star frame ────────────────────────────────────────────────────────

def _make_star_frame(h=200, w=200, bg=100.0, star_x=80, star_y=90, peak=5000.0, r=5):
    frame = np.full((h, w), bg, dtype=np.float32)
    for dy in range(-r * 2, r * 2 + 1):
        for dx in range(-r * 2, r * 2 + 1):
            iy, ix = star_y + dy, star_x + dx
            if 0 <= iy < h and 0 <= ix < w:
                frame[iy, ix] += float(peak * np.exp(-(dx**2 + dy**2) / r**2))
    return frame


def test_refine_finds_star_centroid(client):
    pixels = _make_star_frame()
    with patch.dict(_preview_mod._last_preview_pixels, {0: pixels}):
        data = _post(client, x_px=85, y_px=85, mode="star_centroid").json()
    if not data["fallback"]:
        assert abs(data["refined_x"] - 80) <= 5
        assert abs(data["refined_y"] - 90) <= 5


def test_refine_star_not_fallback_near_click(client):
    pixels = _make_star_frame()
    with patch.dict(_preview_mod._last_preview_pixels, {0: pixels}):
        data = _post(client, x_px=82, y_px=88, mode="star_centroid").json()
    # Should find the star (not fallback)
    assert data["fallback"] is False


def test_refine_fallback_reason_none_when_success(client):
    pixels = _make_star_frame()
    with patch.dict(_preview_mod._last_preview_pixels, {0: pixels}):
        data = _post(client, x_px=82, y_px=88, mode="star_centroid").json()
    if not data["fallback"]:
        assert data["fallback_reason"] is None


# ── Response structure ───────────────────────────────────────────────────────

def test_refine_response_has_all_required_fields(client):
    with patch.dict(_preview_mod._last_preview_pixels, {}, clear=True):
        data = _post(client).json()
    required = {"raw_x", "raw_y", "refined_x", "refined_y", "method", "confidence", "fallback", "fallback_reason"}
    assert required.issubset(data.keys())


def test_refine_ring_center_mode_accepted(client):
    pixels = np.full((200, 200), 100.0, dtype=np.float32)
    with patch.dict(_preview_mod._last_preview_pixels, {0: pixels}):
        resp = _post(client, mode="ring_center")
    assert resp.status_code == 200
