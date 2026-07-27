"""Unit tests for smart_telescope.__main__._select_ws_protocol (M10-05x)."""
import uvicorn.config

from smart_telescope.__main__ import _select_ws_protocol


class TestSelectWsProtocol:
    def test_prefers_sansio_when_available(self, monkeypatch):
        monkeypatch.setattr(
            uvicorn.config, "WS_PROTOCOLS",
            {"auto": None, "none": None, "websockets": None,
             "websockets-sansio": None, "wsproto": None},
        )
        assert _select_ws_protocol() == "websockets-sansio"

    def test_falls_back_to_auto_on_older_uvicorn(self, monkeypatch):
        monkeypatch.setattr(
            uvicorn.config, "WS_PROTOCOLS",
            {"auto": None, "none": None, "websockets": None, "wsproto": None},
        )
        assert _select_ws_protocol() == "auto"
