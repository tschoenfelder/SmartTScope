"""Resolve a camera role value (int index or model-name string) to a SDK index."""
from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)


class CameraNameResolver:
    """Maps a camera name or index to a ToupTek SDK enumeration index.

    Designed to be called once per adapter build so the import cost of
    Toupcam.EnumV2() is paid at startup, not per-capture.
    """

    def resolve(
        self,
        name_or_index: str | int,
        serial_map: dict[str, str],
        devices: list[Any] | None = None,
    ) -> int:
        """Return the SDK index for *name_or_index*.

        Args:
            name_or_index: Either an integer index (or numeric string) for
                backward compatibility, or a model-name string (e.g. "G3M678M").
            serial_map: Maps model name -> expected serial number.  When the
                resolved device's serial doesn't match, RuntimeError is raised.
                Pass an empty dict to skip serial verification.
            devices: Pre-enumerated device list (for testing).  When None,
                Toupcam.EnumV2() is called.

        Returns:
            Zero-based SDK index.

        Raises:
            RuntimeError: Device not found, serial mismatch, or index out of range.
        """
        # Numeric shortcut (backward compat)
        try:
            idx = int(name_or_index)
            devs = devices if devices is not None else self._enumerate()
            # Only validate bounds when the device list is non-empty (i.e. enumeration
            # succeeded and returned real results).  An empty list from a live call means
            # the SDK is unavailable or no camera is connected yet; in that case we trust
            # the caller-supplied index and let ToupcamCamera raise at open-time.
            if devs and idx >= len(devs):
                raise RuntimeError(
                    f"Camera index {idx} out of range — "
                    f"found {len(devs)} device(s): {self._names(devs)}"
                )
            # debug: fires on every readiness/registry tick (M10-018)
            _log.debug("CameraNameResolver: index=%d (no name-based lookup)", idx)
            return idx
        except (ValueError, TypeError):
            pass  # not numeric — fall through to name lookup

        name = str(name_or_index)
        devs = devices if devices is not None else self._enumerate()
        if not devs:
            raise RuntimeError(
                f"CameraNameResolver: no camera found — "
                f"cannot resolve '{name}'. Check USB connections."
            )

        name_lower = name.lower()
        for i, dev in enumerate(devs):
            dev_name = str(dev.displayname).lower()
            if name_lower in dev_name or dev_name in name_lower:
                # Name matched — optionally verify serial
                expected_serial = serial_map.get(name, serial_map.get(name.upper()))
                if expected_serial:
                    actual_serial = self._get_serial(dev)
                    if actual_serial and actual_serial != expected_serial:
                        raise RuntimeError(
                            f"Camera '{name}' found at index {i} "
                            f"(displayname='{dev.displayname}') but serial mismatch: "
                            f"expected '{expected_serial}', got '{actual_serial}'. "
                            f"Check [camera_serials] in config."
                        )
                # debug: fires on every readiness/registry tick (M10-018)
                _log.debug(
                    "CameraNameResolver: '%s' resolved to index=%d (displayname='%s')",
                    name, i, dev.displayname,
                )
                return i

        raise RuntimeError(
            f"Camera '{name_or_index}' not found. "
            f"Available: {self._names(devs)}. "
            f"Check [cameras] and [camera_serials] in config."
        )

    def _enumerate(self) -> list[Any]:
        """Return live device list, or empty list when toupcam SDK is unavailable."""
        try:
            import toupcam as _tc
            return list(_tc.Toupcam.EnumV2())
        except ImportError:
            _log.debug("toupcam SDK not available — device enumeration skipped")
            return []

    def _get_serial(self, device: Any) -> str:
        """Read serial from device stub (used in tests) or production device."""
        if hasattr(device, "_serial"):
            return device._serial  # test stub
        try:
            import toupcam as _tc
            cam = _tc.Toupcam.Open(device.id)
            if cam:
                serial = cam.SerialNumber()
                cam.Close()
                return serial
        except Exception:
            pass
        return ""

    @staticmethod
    def _names(devices: list[Any]) -> str:
        return ", ".join(f"{i}:{d.displayname}" for i, d in enumerate(devices))
