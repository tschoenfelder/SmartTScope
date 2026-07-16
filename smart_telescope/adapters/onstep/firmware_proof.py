"""Thin re-export from the external onstep_adapter package (see SYNC.md)."""
from onstep_adapter.firmware_proof import (
    AXIS1_FALLBACK_TEST_ID,
    DUAL_PIER_TEST_ID,
    PROOF_SCHEMA,
    load_firmware_proof,
    validate_firmware_proof,
    write_firmware_proof,
)

__all__ = [
    "AXIS1_FALLBACK_TEST_ID",
    "DUAL_PIER_TEST_ID",
    "PROOF_SCHEMA",
    "load_firmware_proof",
    "validate_firmware_proof",
    "write_firmware_proof",
]
