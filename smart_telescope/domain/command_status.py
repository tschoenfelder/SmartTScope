"""Command lifecycle statuses (REQ-CMD-001)."""
from enum import Enum


class CommandStatus(str, Enum):
    REQUESTED = "REQUESTED"
    REJECTED  = "REJECTED"
    ISSUED    = "ISSUED"
    RUNNING   = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED    = "FAILED"
    CANCELLED = "CANCELLED"
