"""
Adapter Sprint 48 para Strava — mismo criterio que garmin_provider.py:
envuelve `strava_routes.py` sin modificarlo. `_sync_strava_activities`
es hoy un orquestador monolítico (paginación + parseo + DB-write juntos),
igual que `GarminPullService._do_sync` — no se descompone a la fuerza.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import WearableProvider
from ..models import User
from ..routes.strava_routes import _get_valid_access_token, _sync_strava_activities


class StravaProvider(WearableProvider):
    name = "strava"

    def __init__(self, db: Session):
        self.db = db

    async def authenticate(self, user_id: str, **credentials: Any) -> Any:
        """Delegado 1:1 a `_get_valid_access_token` (refresca el token OAuth
        guardado si está expirado, igual que hace `_sync_strava_activities` hoy)."""
        user: User = credentials["user"]
        return await _get_valid_access_token(user, self.db)

    def list_activities(self, client: Any, since: Any) -> list[dict]:
        raise NotImplementedError(
            "list_activities no está desacoplado todavía: en Strava el fetch "
            "paginado, el dedup contra Garmin y el upsert en DB viven fusionados "
            "dentro de _sync_strava_activities. Ver docs/plan-multi-brand-wearables.md."
        )

    def get_activity_detail(self, raw_activity: dict) -> dict:
        raise NotImplementedError(
            "get_activity_detail no está desacoplado todavía: la normalización "
            "vive dentro de `_upsert_strava_activity`, fusionada con el dedup y "
            "el guardado en DB (garmin_activities). Mismo motivo que list_activities."
        )

    async def sync(self, user: User, days: int = 7) -> dict:
        """Método adicional (fuera de la interfaz estricta): delega al
        orquestador real y ya probado, `_sync_strava_activities`, tal cual
        está hoy en producción."""
        return await _sync_strava_activities(user, self.db, days)
