"""
LabX Coach Platform — FastAPI entry point
=========================================
Arrancar:
    python start_coach_api.py
  o directamente:
    uvicorn api.coach_main:app --reload --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
import logging
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .database import engine, Base
from .routes.auth_routes            import router as auth_router
from .routes.admin_routes           import router as admin_router
from .routes.coach_routes           import router as coach_router
from .routes.athlete_routes         import router as athlete_router
from .routes.week_template_routes   import router as week_template_router
from .routes.personal_routes        import router as personal_router
from .routes.stripe_routes          import router as stripe_router
from .routes.social_routes          import router as social_router

_ROOT_DIR = Path(__file__).resolve().parent.parent

# ── Logging ────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("labx")

# ── CORS origins desde env ─────────────────────────────────────
_raw_origins = os.getenv("CORS_ORIGINS", "")
if _raw_origins:
    CORS_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]
    _CORS_CREDS = True
else:
    # Desarrollo local: wildcard sin credentials (compatible con file:// → Origin:null)
    CORS_ORIGINS = ["*"]
    _CORS_CREDS = False  # "*" + credentials=True es inválido en browsers

# Crear tablas si no existen (SQLite auto-bootstrap)
Base.metadata.create_all(bind=engine)

# Migración en caliente: agregar columnas nuevas a tablas existentes (SQLite no las agrega solo)
with engine.connect() as _conn:
    from sqlalchemy import text as _text
    for _sql in [
        "ALTER TABLE workout_templates ADD COLUMN tipo TEXT",
    ]:
        try:
            _conn.execute(_text(_sql))
            _conn.commit()
        except Exception:
            pass  # columna ya existe — ignorar


@asynccontextmanager
async def lifespan(app):
    from .scheduler import start_scheduler, stop_scheduler
    start_scheduler(os.getenv("DATABASE_URL"))
    yield
    stop_scheduler()


app = FastAPI(
    title       = "LabX Coach API",
    description = "Plataforma coach-atleta para LabX",
    version     = "1.2.0",
    docs_url    = "/docs" if os.getenv("ENABLE_DOCS", "1") == "1" else None,
    redoc_url   = None,
    lifespan    = lifespan,
)

# ── CORS ───────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = CORS_ORIGINS,
    allow_credentials = _CORS_CREDS,
    allow_methods     = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers     = ["Authorization", "Content-Type", "Accept"],
)

# ── Global exception handler ───────────────────────────────────
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Error interno del servidor. El equipo ha sido notificado."},
    )

# Routers bajo /api
app.include_router(auth_router,          prefix="/api")
app.include_router(admin_router,         prefix="/api")
app.include_router(coach_router,         prefix="/api")
app.include_router(athlete_router,       prefix="/api")
app.include_router(week_template_router, prefix="/api")
app.include_router(personal_router,      prefix="/api")
app.include_router(stripe_router,        prefix="/api")
app.include_router(social_router,        prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok", "service": "labx-coach-api", "version": "1.1.0"}


# ── Servir frontend estático ────────────────────────────────────
if os.getenv("APP_ENV", "development") == "production":
    if _ROOT_DIR.exists():
        app.mount("/", StaticFiles(directory=str(_ROOT_DIR), html=True), name="frontend")
