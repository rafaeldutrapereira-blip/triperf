"""
LabX — FastAPI App Entry Point
=====================================
Levanta la app, conecta el pool de PostgreSQL,
inicializa el GarminSyncService y arranca el worker de fondo.

Ejecutar:
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Variables de entorno requeridas (.env):
    DATABASE_URL=postgresql://user:pass@localhost:5432/labx
    GARMIN_CLIENT_ID=...
    GARMIN_CLIENT_SECRET=...
    GARMIN_REDIRECT_URI=https://kona.app/api/garmin/callback
    SESSION_SECRET=<random 32 bytes hex>
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import asyncpg
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from .garmin_client import TokenStore
from .sync_service  import GarminSyncService, WorkoutRepository, run_sync_worker
from .routes.workouts import router as workouts_router

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s %(levelname)s %(name)s — %(message)s",
)

DATABASE_URL   = os.getenv("DATABASE_URL", "postgresql://kona:kona@localhost/labx")
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-production")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──
    pool = await asyncpg.create_pool(
        DATABASE_URL,
        min_size=2, max_size=10,
        command_timeout=30,
    )
    app.state.pool         = pool
    app.state.token_store  = TokenStore()   # reemplazar con DB-backed store en prod
    app.state.sync_service = GarminSyncService(
        WorkoutRepository(pool), app.state.token_store
    )
    # Worker de polling en background
    worker_task = asyncio.create_task(
        run_sync_worker(pool, app.state.token_store)
    )

    yield

    # ── Shutdown ──
    worker_task.cancel()
    await pool.close()


app = FastAPI(
    title       = "LabX API",
    description = "Backend para la plataforma de entrenamiento LabX",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:3000", "https://kona.app"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.include_router(workouts_router, prefix="/api")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "labx-api"}
