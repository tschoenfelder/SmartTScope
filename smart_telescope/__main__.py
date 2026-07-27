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


def _select_ws_protocol() -> str:
    """Prefer the "websockets-sansio" ASGI websocket implementation.

    Uvicorn's default ("auto") picks the legacy "websockets" implementation
    whenever the websockets package is importable, which it always is here.
    That legacy implementation's background keepalive-ping task and an
    in-flight frame write race on the same connection without a shared lock;
    under several simultaneous long-exposure preview streams (e.g. the
    Compare screen's main/guide/oag autogain streams) this reliably kills a
    connection with an AssertionError (M10-05x). "websockets-sansio" doesn't
    have this race. Only available on uvicorn >= 0.35 — fall back to "auto"
    (today's behavior) on older installs so this can never break startup.
    """
    try:
        from uvicorn.config import WS_PROTOCOLS
    except ImportError:
        return "auto"
    return "websockets-sansio" if "websockets-sansio" in WS_PROTOCOLS else "auto"


def main() -> None:
    _configure_app_logging()
    uvicorn.run(
        "smart_telescope.app:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        ws=_select_ws_protocol(),
    )


if __name__ == "__main__":
    main()
