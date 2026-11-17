"""Punto de entrada de la API ObraTrack."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from . import __version__
from .config import get_settings
from .database import Base, engine
from .routers import alerts, auth, devices, geofences, overview, telemetry

settings = get_settings()
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(
        level=logging.DEBUG if settings.debug else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if settings.is_production and settings.jwt_secret.startswith(("dev-", "cambia-")):
        raise RuntimeError(
            "JWT_SECRET no puede ser el valor de desarrollo en producción"
        )

    # MVP: el esquema se crea al arrancar. Para producción usar Alembic.
    Base.metadata.create_all(bind=engine)
    logger.info(
        "ObraTrack %s iniciado (entorno=%s, bd=%s)",
        __version__,
        settings.environment,
        settings.db_name if not settings.database_url else "DATABASE_URL",
    )
    yield


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description=(
        "API para rastrear herramientas de construcción con una ESP32 + NEO-6M. "
        "Incluye autenticación JWT para el panel, token por dispositivo para la "
        "telemetría y geocercas circulares con alertas de salida."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(devices.router)
app.include_router(geofences.router)
app.include_router(telemetry.router)
app.include_router(alerts.router)
app.include_router(overview.router)


@app.get("/api/health", tags=["Sistema"], summary="Estado del servicio y de MySQL")
def health():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database = "ok"
    except Exception as exc:  # pragma: no cover - depende del entorno
        logger.error("Health check de BD falló: %s", exc)
        database = "error"

    return {
        "status": "ok" if database == "ok" else "degraded",
        "database": database,
        "version": __version__,
        "environment": settings.environment,
    }


if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC_DIR / "index.html")

else:  # pragma: no cover

    @app.get("/", include_in_schema=False)
    def root():
        return {
            "name": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "message": "Frontend no instalado; usa /docs para probar la API",
        }
