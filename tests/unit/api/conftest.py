"""Shared fixtures for API unit tests."""
import pytest


@pytest.fixture(autouse=True)
def reset_camera_scan_cache() -> None:
    """Invalidate the camera scan cache before every API test.

    The scan_cameras() endpoint caches results for 5 s to avoid SDK races.
    Without this reset, one test's patched sys.modules bleeds into the next.
    """
    from smart_telescope.api.cameras import invalidate_camera_scan
    invalidate_camera_scan()
