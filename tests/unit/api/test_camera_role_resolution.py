"""Tests for POD-010: resolve_camera_index helper in api/deps.py."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from smart_telescope.api import deps
from smart_telescope.api.deps import resolve_camera_index


def _mock_registry(role: str | None, camera_index: int | None) -> MagicMock:
    """Return a mock OpticalTrainRegistry where `role` resolves to camera_index (or None)."""
    reg = MagicMock()
    if camera_index is not None:
        train = MagicMock()
        train.camera_index = camera_index
        reg.by_camera_role.return_value = train
    else:
        reg.by_camera_role.return_value = None
    return reg


class TestResolveCameraIndex:
    def test_no_role_returns_camera_index_unchanged(self) -> None:
        assert resolve_camera_index(3, None) == 3

    def test_empty_string_role_returns_camera_index_unchanged(self) -> None:
        assert resolve_camera_index(2, "") == 2

    def test_valid_role_returns_train_camera_index(self) -> None:
        reg = _mock_registry("main", camera_index=1)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            result = resolve_camera_index(0, "main")
        assert result == 1

    def test_valid_role_overrides_camera_index(self) -> None:
        reg = _mock_registry("guide", camera_index=2)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            result = resolve_camera_index(99, "guide")
        assert result == 2

    def test_unknown_role_raises_422(self) -> None:
        reg = _mock_registry("nonexistent", camera_index=None)
        with patch.object(deps, "get_optical_train_registry", return_value=reg):
            with pytest.raises(HTTPException) as exc_info:
                resolve_camera_index(0, "nonexistent")
        assert exc_info.value.status_code == 422
        assert "nonexistent" in exc_info.value.detail
