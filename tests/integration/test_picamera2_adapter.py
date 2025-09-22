import os
import pytest

pytestmark = pytest.mark.integration

def test_import_picamera2_adapter_without_runtime():
    # This test only checks that importing doesn't crash the rest of the project
    # when picamera2 is absent. It should not be collected on non-Pi unless marked.
    if os.getenv("SMARTTSCOPE_CAMERA") != "picamera2":
        pytest.skip("Not running picamera2 integration here.")
    from smarttscope.adapters.camera_picamera2 import Picamera2Camera  # noqa: F401
