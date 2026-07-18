"""SmartTouptekCamera._select_device() — M10-026.

Hardware evidence (2026-07-18): on the Cameras screen, covering the guide
camera (GPCMOS02000KPA) changed the frame shown in the OAG panel. Root cause:
when a role's configured `model`/`name`/`camera_id` selector failed to match
any enumerated device, `_select_device()` silently fell back to a positional
index — binding the OAG role to whatever physical camera happened to be at
that index (here, the guide camera). `resolve_device_id()` (used by the
startup role-uniqueness validator) already treats a failed selector match as
"not found"; `_select_device()` must do the same so a bad match fails loudly
instead of cross-wiring two roles onto one physical device.
"""
from __future__ import annotations

from types import SimpleNamespace

from smart_telescope.adapters.touptek.managed import SmartTouptekCamera


def _dev(dev_id: str, displayname: str, model_name: str):
    return SimpleNamespace(id=dev_id, displayname=displayname, model=SimpleNamespace(name=model_name))


class TestModelSelector:
    def test_matching_model_is_found_regardless_of_position(self):
        cam = SmartTouptekCamera(model="G3M678M")
        devices = [
            _dev("A", "ToupTek GPCMOS02000KPA", "GPCMOS02000KPA"),
            _dev("B", "ToupTek G3M678M", "G3M678M"),
        ]
        idx, dev = cam._select_device(devices)
        assert dev is devices[1]
        assert idx == 1

    def test_no_match_does_not_fall_back_to_positional_index(self):
        # The exact hardware scenario: oag's selector doesn't match anything
        # (typo, firmware name mismatch, device unplugged) — must not
        # silently grab devices[0] (the guide camera in this repro).
        cam = SmartTouptekCamera(model="G3M678M", index=0)
        devices = [_dev("A", "ToupTek GPCMOS02000KPA", "GPCMOS02000KPA")]
        idx, dev = cam._select_device(devices)
        assert dev is None

    def test_no_match_with_empty_device_list(self):
        cam = SmartTouptekCamera(model="G3M678M", index=0)
        idx, dev = cam._select_device([])
        assert dev is None


class TestNameSelector:
    def test_no_match_does_not_fall_back_to_positional_index(self):
        cam = SmartTouptekCamera(name="FILTERWHEEL-CAM", index=0)
        devices = [_dev("A", "ToupTek GPCMOS02000KPA", "GPCMOS02000KPA")]
        idx, dev = cam._select_device(devices)
        assert dev is None


class TestCameraIdHint:
    def test_matching_id_is_found(self):
        cam = SmartTouptekCamera(camera_id="dev-b")
        devices = [_dev("dev-a", "Cam A", "MODEL_A"), _dev("dev-b", "Cam B", "MODEL_B")]
        idx, dev = cam._select_device(devices)
        assert dev is devices[1]

    def test_no_match_does_not_fall_back_to_positional_index(self):
        cam = SmartTouptekCamera(camera_id="does-not-exist", index=0)
        devices = [_dev("A", "ToupTek GPCMOS02000KPA", "GPCMOS02000KPA")]
        idx, dev = cam._select_device(devices)
        assert dev is None


class TestNoSelectorConfigured:
    def test_pure_index_config_still_falls_back_to_position(self):
        # Configs with neither model, name, nor camera_id set keep working
        # exactly as before — positional index is the only selector given.
        cam = SmartTouptekCamera(index=0)
        devices = [_dev("A", "ToupTek G3M678M", "G3M678M")]
        idx, dev = cam._select_device(devices)
        assert dev is devices[0]
        assert idx == 0

    def test_index_out_of_range_reports_not_found(self):
        cam = SmartTouptekCamera(index=5)
        devices = [_dev("A", "ToupTek G3M678M", "G3M678M")]
        idx, dev = cam._select_device(devices)
        assert dev is None
