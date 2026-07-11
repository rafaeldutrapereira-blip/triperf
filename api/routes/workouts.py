"""
LabX — Workout Routes (FastAPI)
=====================================
Endpoints REST para el módulo de planificación y sincronización.

POST   /api/workouts                  — Crear workout estructurado
GET    /api/workouts/{id}             — Obtener workout con steps
PUT    /api/workouts/{id}             — Actualizar workout
DELETE /api/workouts/{id}             — Soft delete
POST   /api/workouts/{id}/sync        — Encolar sincronización con Garmin
GET    /api/workouts/{id}/sync-status — Estado actual de la sync
GET    /api/garmin/connect            — Iniciar flujo OAuth con Garmin
GET    /api/garmin/callback           — Callback OAuth (Garmin redirige aquí)
DELETE /api/garmin/disconnect         — Revocar token Garmin del atleta
"""

from __future__ import annotations

import secrets
import uuid
from datetime import date, datetime
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, field_validator, model_validator

from ..garmin_client  import build_auth_url, generate_pkce_pair, GarminClient
from ..sync_service   import GarminSyncService, WorkoutRepository

router = APIRouter()

# ─────────────────────────────────────────────────────────────────────────────
# DEPENDENCIAS
# ─────────────────────────────────────────────────────────────────────────────

async def get_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pool

async def get_sync_service(request: Request) -> GarminSyncService:
    return request.app.state.sync_service

async def get_current_user(request: Request) -> dict:
    """
    Placeholder — reemplazar con tu middleware JWT real.
    Retorna {"id": "...", "role": "coach"|"athlete"}.
    """
    user_id = request.headers.get("X-User-Id")
    if not user_id:
        raise HTTPException(status_code=401, detail="No autenticado")
    return {"id": user_id, "role": request.headers.get("X-User-Role", "athlete")}

Pool = Annotated[asyncpg.Pool, Depends(get_pool)]
SyncSvc = Annotated[GarminSyncService, Depends(get_sync_service)]
CurrentUser = Annotated[dict, Depends(get_current_user)]


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMAS (Pydantic v2)
# ─────────────────────────────────────────────────────────────────────────────

class WorkoutStepIn(BaseModel):
    step_order:    int                = Field(..., ge=1)
    step_type:     str                = Field(..., pattern="^(WARMUP|COOLDOWN|INTERVAL|RECOVERY|REST|REPEAT|OTHER)$")
    duration_type: str                = Field(..., pattern="^(TIME|DISTANCE|REPS|OPEN|FIXED_REST|HR_LESS_THAN|HR_GREATER_THAN|POWER_LESS_THAN|POWER_GREATER_THAN)$")
    duration_value: float | None      = None
    target_type:   str                = "OPEN"
    target_low:    float | None       = None
    target_high:   float | None       = None
    repeat_count:  int | None         = Field(default=None, ge=1, le=100)
    description:   str | None         = None
    swim_stroke:   str | None         = None
    label:         str | None         = None
    child_steps:   list["WorkoutStepIn"] = []

    @model_validator(mode="after")
    def check_repeat(self) -> "WorkoutStepIn":
        if self.step_type == "REPEAT" and not self.repeat_count:
            raise ValueError("repeat_count es obligatorio cuando step_type=REPEAT")
        if self.duration_type != "OPEN" and self.duration_value is None:
            raise ValueError(f"duration_value requerido para duration_type={self.duration_type}")
        return self


class WorkoutIn(BaseModel):
    athlete_id:   str                 = Field(..., description="UUID del atleta")
    sport:        str                 = Field(..., pattern="^(SWIMMING|CYCLING|RUNNING|STRENGTH)$")
    name:         str                 = Field(..., min_length=3, max_length=100)
    description:  str | None         = None
    notes_coach:  str | None         = None
    notes_athlete: str | None        = None
    scheduled_date: date | None      = None
    steps:        list[WorkoutStepIn] = Field(..., min_length=1)

    @field_validator("scheduled_date")
    @classmethod
    def date_not_past(cls, v: date | None) -> date | None:
        if v and v < date.today():
            raise ValueError("scheduled_date no puede ser en el pasado")
        return v


class WorkoutOut(BaseModel):
    id:                 str
    coach_id:           str
    athlete_id:         str
    sport:              str
    name:               str
    description:        str | None
    scheduled_date:     date | None
    estimated_duration_sec: int | None
    estimated_tss:      float | None
    sync_status:        str
    garmin_workout_id:  int | None
    garmin_schedule_id: int | None
    synced_at:          datetime | None
    sync_error:         str | None
    created_at:         datetime
    updated_at:         datetime


class SyncStatusOut(BaseModel):
    workout_id:         str
    sync_status:        str
    garmin_workout_id:  int | None
    garmin_schedule_id: int | None
    synced_at:          datetime | None
    sync_error:         str | None
    sync_retry_count:   int
    sync_next_retry_at: datetime | None


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

async def _insert_steps(
    conn: asyncpg.Connection,
    workout_id: str,
    steps: list[WorkoutStepIn],
    parent_id: str | None = None,
) -> None:
    """Inserta steps recursivamente (maneja REPEAT con hijos)."""
    for s in steps:
        step_id = str(uuid.uuid4())
        await conn.execute(
            """
            INSERT INTO workout_steps
              (id, workout_id, parent_step_id, step_order, step_type, label,
               duration_type, duration_value, target_type, target_low, target_high,
               repeat_count, description, swim_stroke)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
            step_id, workout_id, parent_id,
            s.step_order, s.step_type, s.label,
            s.duration_type, s.duration_value,
            s.target_type, s.target_low, s.target_high,
            s.repeat_count, s.description, s.swim_stroke,
        )
        if s.child_steps:
            await _insert_steps(conn, workout_id, s.child_steps, parent_id=step_id)


# ─────────────────────────────────────────────────────────────────────────────
# WORKOUT CRUD
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/workouts", response_model=WorkoutOut, status_code=201)
async def create_workout(
    body:    WorkoutIn,
    pool:    Pool,
    user:    CurrentUser,
):
    """Crea un workout estructurado y lo guarda en DB (sin sincronizar aún)."""
    wid = str(uuid.uuid4())

    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO workouts
                  (id, coach_id, athlete_id, sport, name, description,
                   notes_coach, notes_athlete, scheduled_date, sync_status)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,'PENDING')
                """,
                wid, user["id"], body.athlete_id, body.sport, body.name,
                body.description, body.notes_coach, body.notes_athlete,
                body.scheduled_date,
            )
            await _insert_steps(conn, wid, body.steps)

        row = await conn.fetchrow("SELECT * FROM workouts WHERE id=$1", wid)

    return dict(row)


@router.get("/workouts/{workout_id}", response_model=WorkoutOut)
async def get_workout(workout_id: str, pool: Pool, user: CurrentUser):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM workouts WHERE id=$1 AND deleted_at IS NULL", workout_id
        )
    if not row:
        raise HTTPException(404, "Workout no encontrado")
    return dict(row)


@router.put("/workouts/{workout_id}", response_model=WorkoutOut)
async def update_workout(
    workout_id: str,
    body:       WorkoutIn,
    pool:       Pool,
    user:       CurrentUser,
):
    """Actualiza workout + reconstruye steps. Resetea estado sync a PENDING."""
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT id FROM workouts WHERE id=$1 AND coach_id=$2 AND deleted_at IS NULL",
            workout_id, user["id"],
        )
        if not exists:
            raise HTTPException(404, "Workout no encontrado o sin permisos")

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE workouts SET
                  sport=$2, name=$3, description=$4, notes_coach=$5,
                  notes_athlete=$6, scheduled_date=$7,
                  sync_status='PENDING', sync_error=NULL,
                  garmin_workout_id=NULL, garmin_schedule_id=NULL
                WHERE id=$1
                """,
                workout_id, body.sport, body.name, body.description,
                body.notes_coach, body.notes_athlete, body.scheduled_date,
            )
            # Reconstruir steps
            await conn.execute("DELETE FROM workout_steps WHERE workout_id=$1", workout_id)
            await _insert_steps(conn, workout_id, body.steps)

        row = await conn.fetchrow("SELECT * FROM workouts WHERE id=$1", workout_id)
    return dict(row)


@router.delete("/workouts/{workout_id}", status_code=204)
async def delete_workout(workout_id: str, pool: Pool, user: CurrentUser):
    async with pool.acquire() as conn:
        updated = await conn.execute(
            "UPDATE workouts SET deleted_at=NOW() WHERE id=$1 AND coach_id=$2 AND deleted_at IS NULL",
            workout_id, user["id"],
        )
    if updated == "UPDATE 0":
        raise HTTPException(404, "Workout no encontrado")


# ─────────────────────────────────────────────────────────────────────────────
# SYNC — Encolar y consultar estado
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/workouts/{workout_id}/sync", status_code=202)
async def enqueue_sync(
    workout_id:       str,
    background_tasks: BackgroundTasks,
    pool:             Pool,
    svc:              SyncSvc,
    user:             CurrentUser,
):
    """
    Encola la sincronización del workout con Garmin.
    Retorna 202 inmediatamente; el sync ocurre en background.
    El cliente debe hacer polling a /sync-status para ver el resultado.
    """
    async with pool.acquire() as conn:
        workout = await conn.fetchrow(
            "SELECT id, athlete_id, sync_retry_count, sync_status "
            "FROM workouts WHERE id=$1 AND coach_id=$2 AND deleted_at IS NULL",
            workout_id, user["id"],
        )
    if not workout:
        raise HTTPException(404, "Workout no encontrado o sin permisos")

    if workout["sync_retry_count"] >= 3 and workout["sync_status"] == "FAILED":
        raise HTTPException(
            409,
            "El workout alcanzó el máximo de reintentos. "
            "Edita el workout para resetearlo o revisa el error.",
        )

    # Verificar que el atleta tiene token Garmin antes de encolar
    repo = WorkoutRepository(pool)
    if not await repo.has_garmin_token(str(workout["athlete_id"])):
        raise HTTPException(
            409,
            "El atleta no tiene Garmin conectado. "
            "Debe autorizar la app desde su perfil.",
        )

    # Resetear retry counter y encolar
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE workouts SET sync_status='QUEUED', sync_retry_count=0 WHERE id=$1",
            workout_id,
        )
        await conn.execute(
            """
            INSERT INTO sync_queue (workout_id, athlete_id, operation)
            VALUES ($1, $2, 'CREATE')
            ON CONFLICT DO NOTHING
            """,
            workout_id, str(workout["athlete_id"]),
        )

    # Fire-and-forget (el worker de fondo también lo procesará)
    background_tasks.add_task(svc.sync_workout, workout_id)

    return {
        "status":     "queued",
        "workout_id": workout_id,
        "message":    "Sincronización encolada. Usa /sync-status para ver el progreso.",
    }


@router.get("/workouts/{workout_id}/sync-status", response_model=SyncStatusOut)
async def get_sync_status(workout_id: str, pool: Pool, user: CurrentUser):
    """Polling endpoint — retorna el estado actual de la sync con Garmin."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT id::text AS workout_id, sync_status, garmin_workout_id,
                   garmin_schedule_id, synced_at, sync_error,
                   sync_retry_count, sync_next_retry_at
            FROM   workouts
            WHERE  id=$1 AND deleted_at IS NULL
            """,
            workout_id,
        )
    if not row:
        raise HTTPException(404, "Workout no encontrado")
    return dict(row)


# ─────────────────────────────────────────────────────────────────────────────
# GARMIN OAUTH — Connect / Callback / Disconnect
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/garmin/connect")
async def garmin_connect(request: Request, user: CurrentUser):
    """
    Paso 1 del flujo OAuth 2.0:
    Genera la URL de autorización y redirige al atleta a Garmin Connect.
    """
    state          = secrets.token_urlsafe(32)
    verifier, challenge = generate_pkce_pair()

    # Guardar state + verifier en sesión (usa tu session middleware real)
    request.session["garmin_oauth_state"]    = state
    request.session["garmin_code_verifier"]  = verifier
    request.session["garmin_user_id"]        = user["id"]

    auth_url = build_auth_url(state, challenge)
    return RedirectResponse(auth_url)


@router.get("/garmin/callback")
async def garmin_callback(
    code:  str,
    state: str,
    request: Request,
    pool: Pool,
):
    """
    Paso 2: Garmin redirige aquí con el code.
    Intercambiamos por tokens y los guardamos en DB.
    """
    stored_state   = request.session.get("garmin_oauth_state")
    code_verifier  = request.session.get("garmin_code_verifier")
    athlete_id     = request.session.get("garmin_user_id")

    if state != stored_state or not code_verifier or not athlete_id:
        raise HTTPException(400, "Estado OAuth inválido. Intenta conectar de nuevo.")

    token_store = request.app.state.token_store
    client      = GarminClient(token_store)

    try:
        token = await client.exchange_code(athlete_id, code, code_verifier)
    except Exception as e:
        raise HTTPException(502, f"Error al obtener token de Garmin: {e}")

    # Persistir en DB
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO garmin_user_tokens
              (user_id, garmin_user_id, oauth2_access_token, oauth2_refresh_token,
               oauth2_expires_at, oauth2_scope)
            VALUES ($1, $1, $2, $3, $4, $5)
            ON CONFLICT (user_id) DO UPDATE SET
              oauth2_access_token  = EXCLUDED.oauth2_access_token,
              oauth2_refresh_token = EXCLUDED.oauth2_refresh_token,
              oauth2_expires_at    = EXCLUDED.oauth2_expires_at,
              oauth2_scope         = EXCLUDED.oauth2_scope,
              updated_at           = NOW()
            """,
            athlete_id,
            token.access_token, token.refresh_token,
            token.expires_at, token.scope,
        )

    # Limpiar sesión OAuth
    request.session.pop("garmin_oauth_state", None)
    request.session.pop("garmin_code_verifier", None)
    request.session.pop("garmin_user_id", None)

    # Redirigir al perfil del atleta con éxito
    return RedirectResponse("/profile?garmin=connected")


@router.delete("/garmin/disconnect", status_code=204)
async def garmin_disconnect(pool: Pool, user: CurrentUser):
    """Revoca la conexión Garmin del atleta (borra tokens de DB)."""
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM garmin_user_tokens WHERE user_id=$1", user["id"]
        )
    # En producción: también llamar al endpoint de revocación de Garmin
