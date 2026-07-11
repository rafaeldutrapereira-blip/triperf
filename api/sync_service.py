"""
LabX — Garmin Sync Service
================================
Orquesta la sincronización de workouts con Garmin:
  1. Coach presiona "Guardar y Sincronizar"
  2. Endpoint encola el job en sync_queue (DB)
  3. Worker en background lo procesa (polling o Celery/ARQ)
  4. Estado disponible via GET /workouts/{id}/sync-status

Diseñado para ser llamado tanto desde el endpoint HTTP
como desde un worker Celery independiente.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import asyncpg                                   # pip install asyncpg

from .garmin_client  import (
    GarminClient, GarminRateLimitError,
    GarminTokenExpiredError, GarminAPIError, GarminNotFoundError,
    TokenStore,
)
from .garmin_converter import (
    GarminWorkoutConverter, AthleteProfile,
    StructuredWorkout, WorkoutStep, ConversionError,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS   = 3
RATE_LIMIT_BACKOFF_SEC = 60   # mínimo, Garmin puede pedir más via Retry-After


# ─────────────────────────────────────────────────────────────────────────────
# REPOSITORIO — capa de acceso a datos (asyncpg)
# ─────────────────────────────────────────────────────────────────────────────

class WorkoutRepository:
    """
    Abstrae todas las queries a PostgreSQL para el módulo de sync.
    Reemplazar con SQLAlchemy async / Prisma si el stack lo requiere.
    """

    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def get_workout_with_steps(self, workout_id: str) -> dict | None:
        """Carga el workout + sus steps ordenados para conversión."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT w.*,
                       t.oauth2_access_token, t.oauth2_refresh_token,
                       t.oauth2_expires_at,   t.ftp_watts,
                       t.lthr_bpm, t.css_sec_100m, t.weight_kg
                FROM   workouts w
                JOIN   garmin_user_tokens t ON t.user_id = w.athlete_id
                WHERE  w.id = $1 AND w.deleted_at IS NULL
                """,
                workout_id,
            )
            if not row:
                return None

            steps = await conn.fetch(
                """
                SELECT * FROM workout_steps
                WHERE  workout_id = $1
                ORDER  BY step_order
                """,
                workout_id,
            )
            return dict(row) | {"_steps": [dict(s) for s in steps]}

    async def update_sync_status(
        self,
        workout_id:        str,
        status:            str,
        garmin_workout_id: int | None   = None,
        garmin_schedule_id: int | None  = None,
        error:             str | None   = None,
        next_retry_at:     datetime | None = None,
        garmin_payload:    dict | None  = None,
        garmin_response:   dict | None  = None,
    ) -> None:
        fields: list[str] = ["sync_status = $2", "updated_at = NOW()"]
        values: list[Any] = [workout_id, status]
        idx = 3

        def add(col: str, val: Any) -> None:
            nonlocal idx
            fields.append(f"{col} = ${idx}")
            values.append(val)
            idx += 1

        if garmin_workout_id is not None:
            add("garmin_workout_id", garmin_workout_id)
        if garmin_schedule_id is not None:
            add("garmin_schedule_id", garmin_schedule_id)
        if error is not None:
            add("sync_error", error)
        if next_retry_at is not None:
            add("sync_next_retry_at", next_retry_at)
        if garmin_payload is not None:
            add("garmin_payload", json.dumps(garmin_payload))
        if garmin_response is not None:
            add("garmin_response", json.dumps(garmin_response))
        if status == "SYNCED":
            fields.append("synced_at = NOW()")
            fields.append("sync_error = NULL")
            fields.append("sync_next_retry_at = NULL")

        async with self._pool.acquire() as conn:
            await conn.execute(
                f"UPDATE workouts SET {', '.join(fields)} WHERE id = $1",
                *values,
            )

    async def increment_retry(self, workout_id: str) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                "UPDATE workouts SET sync_retry_count = sync_retry_count + 1 WHERE id = $1",
                workout_id,
            )

    async def log_api_call(
        self,
        workout_id:     str,
        athlete_id:     str,
        endpoint:       str,
        method:         str,
        request_body:   dict | None = None,
        response_status: int        = 0,
        response_body:  dict | None = None,
        latency_ms:     int         = 0,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO garmin_api_log
                  (workout_id, athlete_id, endpoint, method,
                   request_body, response_status, response_body, latency_ms)
                VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                """,
                workout_id, athlete_id, endpoint, method,
                json.dumps(request_body) if request_body else None,
                response_status,
                json.dumps(response_body) if response_body else None,
                latency_ms,
            )

    async def has_garmin_token(self, athlete_id: str) -> bool:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id FROM garmin_user_tokens WHERE user_id = $1", athlete_id
            )
            return row is not None


# ─────────────────────────────────────────────────────────────────────────────
# ENSAMBLADOR — DB rows → StructuredWorkout
# ─────────────────────────────────────────────────────────────────────────────

def build_structured_workout(data: dict) -> StructuredWorkout:
    """
    Convierte el resultado de WorkoutRepository.get_workout_with_steps()
    en un StructuredWorkout listo para el converter.
    """
    flat_steps = data["_steps"]

    # Construir árbol parent → children
    step_map: dict[str, WorkoutStep] = {}
    for s in flat_steps:
        ws = WorkoutStep(
            step_order    = s["step_order"],
            step_type     = s["step_type"],
            duration_type = s["duration_type"],
            duration_value= float(s["duration_value"]) if s["duration_value"] else None,
            target_type   = s["target_type"]  or "OPEN",
            target_low    = float(s["target_low"])  if s["target_low"]  else None,
            target_high   = float(s["target_high"]) if s["target_high"] else None,
            repeat_count  = s["repeat_count"],
            description   = s["description"] or "",
            swim_stroke   = s["swim_stroke"],
            label         = s["label"] or "",
        )
        step_map[str(s["id"])] = ws

    roots: list[WorkoutStep] = []
    for s in flat_steps:
        ws = step_map[str(s["id"])]
        if s["parent_step_id"] and str(s["parent_step_id"]) in step_map:
            step_map[str(s["parent_step_id"])].child_steps.append(ws)
        else:
            roots.append(ws)

    return StructuredWorkout(
        id          = str(data["id"]),
        name        = data["name"],
        sport       = data["sport"],
        description = data.get("description") or "",
        steps       = roots,
        estimated_duration_sec = data.get("estimated_duration_sec"),
        estimated_distance_m   = data.get("estimated_distance_m"),
    )


def build_athlete_profile(data: dict) -> AthleteProfile:
    return AthleteProfile(
        ftp_watts            = data.get("ftp_watts")    or 240,
        lthr_bpm             = data.get("lthr_bpm")     or 168,
        css_sec_100m         = data.get("css_sec_100m") or 110,
        weight_kg            = float(data.get("weight_kg") or 72.0),
    )


# ─────────────────────────────────────────────────────────────────────────────
# SYNC SERVICE — lógica principal
# ─────────────────────────────────────────────────────────────────────────────

class GarminSyncService:
    """
    Servicio que orquesta la sincronización completa.
    Instanciar una vez por proceso (comparte pool y token_store).
    """

    def __init__(self, repo: WorkoutRepository, token_store: TokenStore):
        self._repo        = repo
        self._token_store = token_store
        self._client      = GarminClient(token_store)

    async def sync_workout(self, workout_id: str) -> dict[str, Any]:
        """
        Sincroniza un workout con Garmin. Retorna dict con resultado.
        Captura todos los errores y los persiste en DB.
        """
        t0   = time.monotonic()
        data = await self._repo.get_workout_with_steps(workout_id)

        if not data:
            return {"ok": False, "error": "workout_not_found"}

        athlete_id = str(data["athlete_id"])

        # Verificar token antes de empezar
        if not await self._repo.has_garmin_token(athlete_id):
            await self._repo.update_sync_status(
                workout_id, "FAILED",
                error="El atleta no tiene Garmin conectado. Debe autorizar la app.",
            )
            return {"ok": False, "error": "no_garmin_token", "retryable": False}

        await self._repo.update_sync_status(workout_id, "SYNCING")
        await self._repo.increment_retry(data["id"])

        try:
            # 1 ── Convertir workout a formato Garmin
            structured = build_structured_workout(data)
            profile    = build_athlete_profile(data)
            converter  = GarminWorkoutConverter(profile)
            payload    = converter.convert(structured)

            # 2 ── Crear o actualizar en Garmin
            garmin_wid = data.get("garmin_workout_id")
            t_api = time.monotonic()

            if garmin_wid:
                await self._client.update_workout(athlete_id, garmin_wid, payload)
                garmin_wid = int(garmin_wid)
                op = "PUT"
            else:
                garmin_wid = await self._client.create_workout(athlete_id, payload)
                op = "POST"

            latency = int((time.monotonic() - t_api) * 1000)
            await self._repo.log_api_call(
                workout_id, athlete_id,
                f"/workout{'' if op=='POST' else '/'+str(garmin_wid)}",
                op, payload, 200, {"workoutId": garmin_wid}, latency,
            )

            # 3 ── Desagendar si ya estaba agendado (para re-agendar limpio)
            old_schedule_id = data.get("garmin_schedule_id")
            if old_schedule_id:
                try:
                    await self._client.unschedule_workout(athlete_id, int(old_schedule_id))
                except GarminNotFoundError:
                    pass   # ya no existía en Garmin

            # 4 ── Agendar si hay fecha objetivo
            garmin_sid = None
            scheduled_date = data.get("scheduled_date")
            if scheduled_date:
                date_str = (
                    scheduled_date.isoformat()
                    if hasattr(scheduled_date, "isoformat")
                    else str(scheduled_date)
                )
                garmin_sid = await self._client.schedule_workout(
                    athlete_id, garmin_wid, date_str
                )

            # 5 ── Persistir éxito
            await self._repo.update_sync_status(
                workout_id, "SYNCED",
                garmin_workout_id  = garmin_wid,
                garmin_schedule_id = garmin_sid,
                garmin_payload     = payload,
                garmin_response    = {"workoutId": garmin_wid, "scheduleId": garmin_sid},
            )

            logger.info(
                "Workout %s sincronizado en %.1fs (garminId=%s, scheduleId=%s)",
                workout_id, time.monotonic() - t0, garmin_wid, garmin_sid,
            )
            return {
                "ok":                True,
                "garmin_workout_id": garmin_wid,
                "garmin_schedule_id": garmin_sid,
            }

        except ConversionError as e:
            logger.error("Error de conversión workout %s: %s", workout_id, e)
            await self._repo.update_sync_status(workout_id, "FAILED", error=str(e))
            await self._repo.log_api_call(workout_id, athlete_id, "/convert", "INTERNAL", error=str(e))
            return {"ok": False, "error": str(e), "retryable": False}

        except GarminTokenExpiredError as e:
            logger.warning("Token expirado para atleta %s: %s", athlete_id, e)
            await self._repo.update_sync_status(
                workout_id, "FAILED",
                error="Token de Garmin expirado. El atleta debe reconectar su cuenta.",
            )
            return {"ok": False, "error": "token_expired", "retryable": False}

        except GarminRateLimitError as e:
            retry_at = datetime.now(timezone.utc) + timedelta(seconds=e.retry_after)
            logger.warning("Rate limit Garmin. Reintentando en %ds", e.retry_after)
            await self._repo.update_sync_status(
                workout_id, "RATE_LIMITED",
                error          = f"Rate limit Garmin. Reintentando en {e.retry_after}s.",
                next_retry_at  = retry_at,
            )
            return {
                "ok":           False,
                "error":        "rate_limited",
                "retryable":    True,
                "retry_after":  e.retry_after,
            }

        except GarminAPIError as e:
            retryable = e.status_code >= 500 or e.status_code == 0
            logger.error("Garmin API error %d para workout %s: %s", e.status_code, workout_id, e)
            await self._repo.update_sync_status(workout_id, "FAILED", error=str(e))
            await self._repo.log_api_call(
                workout_id, athlete_id, "/workout", "API",
                response_status=e.status_code, response_body=e.body,
            )
            return {"ok": False, "error": str(e), "retryable": retryable}

        except Exception as e:
            logger.exception("Error inesperado sincronizando workout %s", workout_id)
            await self._repo.update_sync_status(workout_id, "FAILED", error=str(e))
            return {"ok": False, "error": str(e), "retryable": False}


# ─────────────────────────────────────────────────────────────────────────────
# WORKER DE POLLING (alternativa ligera a Celery para proyectos pequeños)
# En producción reemplazar por Celery + Redis o ARQ
# ─────────────────────────────────────────────────────────────────────────────

async def run_sync_worker(pool: asyncpg.Pool, token_store: TokenStore) -> None:
    """
    Worker simple de polling que procesa trabajos pendientes en sync_queue.
    Ejecutar como tarea de fondo en FastAPI lifespan.

    Para escalar: mover a worker Celery separado y usar sync_queue como
    tabla de outbox (PostgreSQL LISTEN/NOTIFY para push inmediato).
    """
    repo    = WorkoutRepository(pool)
    service = GarminSyncService(repo, token_store)

    logger.info("Garmin sync worker iniciado")

    while True:
        try:
            async with pool.acquire() as conn:
                # Tomar el siguiente job pendiente (FOR UPDATE SKIP LOCKED
                # permite múltiples workers sin colisiones)
                job = await conn.fetchrow(
                    """
                    SELECT id, workout_id, athlete_id, operation
                    FROM   sync_queue
                    WHERE  status IN ('PENDING', 'RATE_LIMITED')
                      AND  scheduled_for <= NOW()
                      AND  attempts < max_attempts
                    ORDER  BY priority, scheduled_for
                    LIMIT  1
                    FOR UPDATE SKIP LOCKED
                    """,
                )
                if job:
                    await conn.execute(
                        "UPDATE sync_queue SET status='SYNCING', started_at=NOW(), "
                        "attempts=attempts+1 WHERE id=$1",
                        job["id"],
                    )

            if job:
                result = await service.sync_workout(str(job["workout_id"]))
                async with pool.acquire() as conn:
                    if result["ok"]:
                        await conn.execute(
                            "UPDATE sync_queue SET status='SYNCED', completed_at=NOW() WHERE id=$1",
                            job["id"],
                        )
                    elif result.get("retryable") is False:
                        await conn.execute(
                            "UPDATE sync_queue SET status='FAILED', error_detail=$2 WHERE id=$1",
                            job["id"], result.get("error"),
                        )
                    else:
                        # Reintentable (rate limit, error de red)
                        delay = result.get("retry_after", 30)
                        await conn.execute(
                            "UPDATE sync_queue SET status='RATE_LIMITED', "
                            "scheduled_for=NOW()+($2 || ' seconds')::interval, "
                            "error_detail=$3 WHERE id=$1",
                            job["id"], str(delay), result.get("error"),
                        )

        except Exception:
            logger.exception("Error en sync worker loop")

        await asyncio.sleep(5)   # Polling cada 5s cuando no hay jobs
