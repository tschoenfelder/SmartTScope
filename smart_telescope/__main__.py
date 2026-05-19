"""Entry point: python -m smart_telescope  or  smarttscope CLI."""
import logging
import sys

import uvicorn


def _configure_app_logging() -> None:
    """Add a stderr handler directly to the smart_telescope logger.

    uvicorn calls logging.config.dictConfig() on startup which leaves the
    root logger at WARNING.  Our loggers propagate to root and get dropped
    unless we attach our own handler with propagate=False.
    """
    log = logging.getLogger("smart_telescope")
    log.setLevel(logging.INFO)
    if not log.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            "%(levelname)-8s %(name)s: %(message)s"
        ))
        log.addHandler(handler)
    log.propagate = False  # don't let messages bubble up to root (avoids duplicates)


def main() -> None:
    _configure_app_logging()
    uvicorn.run("smart_telescope.app:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":
    main()
