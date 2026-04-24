"""Thread-safe in-memory circular event log for adapter command/response tracing."""

from __future__ import annotations

import threading
from collections import deque
from datetime import UTC, datetime

_MAX = 300
_lock = threading.Lock()
_entries: deque[dict[str, str]] = deque(maxlen=_MAX)


def _now() -> str:
    return datetime.now(UTC).strftime("%H:%M:%S.%f")[:-3] + "Z"


def log_tx(message: str) -> None:
    with _lock:
        _entries.append({"ts": _now(), "dir": "tx", "msg": message})


def log_rx(message: str) -> None:
    with _lock:
        _entries.append({"ts": _now(), "dir": "rx", "msg": message})


def log_err(message: str) -> None:
    with _lock:
        _entries.append({"ts": _now(), "dir": "err", "msg": message})


def get_recent(n: int = 200) -> list[dict[str, str]]:
    with _lock:
        entries = list(_entries)
    return entries[-n:]


def clear() -> None:
    with _lock:
        _entries.clear()
