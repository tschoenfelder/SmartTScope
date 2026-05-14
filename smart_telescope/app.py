"""FastAPI application factory."""
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from serial import SerialException

_log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    yield
    # Graceful shutdown: stop moving parts before closing serial.
    # OnStep is autonomous — it keeps executing a move command even after the
    # serial port closes.  Send stop commands first so hardware halts cleanly.
    from .api import deps
    if deps._focuser is not None:
        with contextlib.suppress(Exception):
            deps._focuser.stop()
        _log.info("Shutdown: focuser stop sent")
    if deps._mount is not None:
        with contextlib.suppress(Exception):
            deps._mount.stop()
        _log.info("Shutdown: mount stop sent")
        with contextlib.suppress(Exception):
            deps._mount.disconnect()
        _log.info("Shutdown: mount serial closed")
    for cam in list(deps._preview_cameras.values()):
        with contextlib.suppress(Exception):
            cam.disconnect()
    if deps._preview_cameras:
        _log.info("Shutdown: %d secondary camera handle(s) closed", len(deps._preview_cameras))

from .api.autogain import router as autogain_router
from .api.collimation import router as collimation_router
from .api.guide_monitor import router as guide_monitor_router
from .api.bahtinov import router as bahtinov_router
from .api.calibration import router as calibration_router
from .api.cooling import router as cooling_router
from .api.histogram import router as histogram_router
from .api.cameras import router as cameras_router
from .api.version import router as version_router
from .api.catalog import router as catalog_router
from .api.emergency import router as emergency_router
from .api.focuser import router as focuser_router
from .api.health import router as health_router
from .api.mount import router as mount_router
from .api.polar import router as polar_router
from .api.preview import router as preview_router
from .api.queue import router as queue_router
from .api.session import router as session_router
from .api.solver import router as solver_router
from .api.stack import router as stack_router

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="SmartTelescope", version="0.1.0", lifespan=_lifespan)


@app.exception_handler(SerialException)
async def serial_exception_handler(request: Request, exc: SerialException) -> JSONResponse:
    _log.warning("Serial I/O error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "Mount serial connection lost — reconnect the USB cable and restart"})
app.include_router(autogain_router)
app.include_router(collimation_router)
app.include_router(guide_monitor_router)
app.include_router(bahtinov_router)
app.include_router(calibration_router)
app.include_router(cooling_router)
app.include_router(histogram_router)
app.include_router(cameras_router)
app.include_router(version_router)
app.include_router(catalog_router)
app.include_router(emergency_router)
app.include_router(health_router)
app.include_router(mount_router)
app.include_router(polar_router)
app.include_router(focuser_router)
app.include_router(preview_router)
app.include_router(queue_router)
app.include_router(session_router)
app.include_router(solver_router)
app.include_router(stack_router)


@app.get("/", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
