"""FastAPI application factory."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from serial import SerialException

_log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    import threading
    from .runtime import RuntimeContext, set_runtime
    ctx = RuntimeContext()
    set_runtime(ctx)
    app.state.runtime = ctx

    def _eager_connect() -> None:
        import time
        time.sleep(3)  # allow USB devices to enumerate before probing serial
        try:
            ctx.connect_devices()
        except Exception as exc:
            _log.warning("Startup hardware connect failed: %s", exc)

    threading.Thread(target=_eager_connect, daemon=True, name="eager-connect").start()
    yield
    ctx.shutdown()

from .api.dawn import router as dawn_router
from .api.milestones import router as milestones_router
from .api.performance_targets import router as performance_targets_router
from .api.readiness import router as readiness_router
from .api.autogain import router as autogain_router
from .api.collimation import router as collimation_router
from .api.optical_trains import router as optical_trains_router
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
from .api.bias_estimation import router as bias_estimation_router
from .api.guiding import router as guiding_router
from .api.setup_check import router as setup_check_router
from .api.gpsd import router as gpsd_router
from .api.stage1 import router as stage1_router
from .api.commands import router as commands_router

_STATIC = Path(__file__).parent / "static"

app = FastAPI(title="SmartTelescope", version="0.1.0", lifespan=_lifespan)
app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.exception_handler(SerialException)
async def serial_exception_handler(request: Request, exc: SerialException) -> JSONResponse:
    _log.warning("Serial I/O error on %s: %s", request.url.path, exc)
    return JSONResponse(status_code=503, content={"detail": "Mount serial connection lost — reconnect the USB cable and restart"})


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    _log.error("Unhandled exception on %s: %s: %s", request.url.path, type(exc).__name__, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": f"{type(exc).__name__}: {exc}"})


app.include_router(dawn_router)
app.include_router(milestones_router)
app.include_router(performance_targets_router)
app.include_router(readiness_router)
app.include_router(autogain_router)
app.include_router(collimation_router)
app.include_router(optical_trains_router)
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
app.include_router(bias_estimation_router)
app.include_router(guiding_router)
app.include_router(setup_check_router)
app.include_router(gpsd_router)
app.include_router(stage1_router)
app.include_router(commands_router)


@app.get("/", response_class=HTMLResponse)
def ui() -> HTMLResponse:
    return HTMLResponse((_STATIC / "index.html").read_text(encoding="utf-8"))


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
