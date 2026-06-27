"""SectionLogger — per-section log namespaces with session ID (REQ-LOG-001).

Provides 12 named log sections, each with its own file handler when a log
directory is configured.  Every log record carries session_id and section
name as extra fields so structured tooling can correlate entries.

Usage::

    logger = section_logger.get("goto")
    logger.info("GoTo requested ra=%s dec=%s", ra, dec)
    # record emitted to:
    #   smart_telescope.section.goto logger
    #   {log_dir}/{session_id[:8]}/goto.log  (when log_dir is set)
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

LOG_SECTIONS: tuple[str, ...] = (
    "startup",
    "stage1_time_location",
    "mount",
    "camera",
    "auto_gain",
    "autofocus",
    "collimation",
    "plate_solve",
    "goto",
    "click_to_center",
    "extended_setup_check",
    "github_delivery",
)

_FORMATTER = logging.Formatter(
    "%(asctime)s %(levelname)-8s [%(session_id)s] %(section)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

_log = logging.getLogger(__name__)


class _SectionAdapter(logging.LoggerAdapter):
    """Injects session_id and section into every log record."""

    def process(self, msg: str, kwargs: dict[str, Any]) -> tuple[str, dict]:
        extra = kwargs.setdefault("extra", {})
        extra.update(self.extra)
        return msg, kwargs


class SectionLogger:
    """Per-section log infrastructure.

    Parameters
    ----------
    session_id:
        UUID string for the current application session (first 8 chars used
        in file paths for readability).
    log_dir:
        Directory root for section log files.  Pass an empty string or None
        to disable file logging (in-memory only — useful in tests).
    """

    def __init__(self, session_id: str, log_dir: str | None = None) -> None:
        self._session_id = session_id
        self._lock       = threading.Lock()
        self._adapters: dict[str, _SectionAdapter] = {}
        self._paths: dict[str, str | None] = {s: None for s in LOG_SECTIONS}

        session_slug = session_id[:8]

        for section in LOG_SECTIONS:
            logger = logging.getLogger(f"smart_telescope.section.{section}")
            logger.setLevel(logging.DEBUG)
            logger.propagate = True  # still reach the root smart_telescope handler

            if log_dir:
                path = Path(log_dir) / session_slug / f"{section}.log"
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    fh = logging.FileHandler(str(path), encoding="utf-8")
                    fh.setFormatter(_FORMATTER)
                    logger.addHandler(fh)
                    self._paths[section] = str(path)
                except OSError as exc:
                    _log.warning(
                        "SectionLogger: cannot open log file %s: %s", path, exc
                    )

            self._adapters[section] = _SectionAdapter(
                logger,
                {"session_id": session_slug, "section": section},
            )

    # ── public API ────────────────────────────────────────────────────────────

    def get(self, section: str) -> _SectionAdapter:
        """Return the LoggerAdapter for *section*.

        Falls back to a generic adapter if the section name is not in
        LOG_SECTIONS (e.g. during development of a new section).
        """
        adapter = self._adapters.get(section)
        if adapter is None:
            _log.warning("SectionLogger.get: unknown section %r — using fallback", section)
            fallback_logger = logging.getLogger(f"smart_telescope.section.{section}")
            return _SectionAdapter(
                fallback_logger,
                {"session_id": self._session_id[:8], "section": section},
            )
        return adapter

    def get_paths(self) -> dict[str, str | None]:
        """Return {section: absolute_file_path_or_None} for all sections."""
        return dict(self._paths)

    def close(self) -> None:
        """Close all file handlers (called from RuntimeContext.shutdown())."""
        for section in LOG_SECTIONS:
            logger = logging.getLogger(f"smart_telescope.section.{section}")
            for handler in list(logger.handlers):
                try:
                    handler.close()
                except Exception:
                    pass
                logger.removeHandler(handler)
