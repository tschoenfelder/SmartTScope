"""FastAPI application factory."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .api.cameras import router as cameras_router
from .api.focuser import router as focuser_router
from .api.mount import router as mount_router

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="SmartTelescope", version="0.1.0")
app.include_router(cameras_router)
app.include_router(mount_router)
app.include_router(focuser_router)


@app.get("/", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
