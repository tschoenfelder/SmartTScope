"""Thin re-export from the external onstep_adapter package (see SYNC.md).

No serial/LX200 implementation code may live in this repo — the pip-installed
``onstep_adapter`` wheel is the sole protocol implementation.
"""
from onstep_adapter.serial_bus import OnStepSerialBus

__all__ = ["OnStepSerialBus"]
