"""FastAPI application factory."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .api.cameras import router as cameras_router
from .api.catalog import router as catalog_router
from .api.emergency import router as emergency_router
from .api.focuser import router as focuser_router
from .api.mount import router as mount_router
from .api.preview import router as preview_router
from .api.session import router as session_router
from .api.solver import router as solver_router
from .api.stack import router as stack_router

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="SmartTelescope", version="0.1.0")
app.include_router(cameras_router)
app.include_router(catalog_router)
app.include_router(emergency_router)
app.include_router(mount_router)
app.include_router(focuser_router)
app.include_router(preview_router)
app.include_router(session_router)
app.include_router(solver_router)
app.include_router(stack_router)


@app.get("/", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
