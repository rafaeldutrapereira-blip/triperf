"""
Adapter Sprint 48: envuelve el código Garmin existente detrás de
`WearableProvider` SIN modificar `garmin_pull_service.py`. Ver el
docstring de `base.py` para el porqué de este alcance.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import WearableProvider
from ..garmin_pull_service import (
    GarminPullService,
    _garmin_login,
    _parse_garmin_activity,
    _retry,
    _try_download_gps_track,
    _try_download_splits,
)


class GarminProvider(WearableProvider):
    name = "garmin"

    def __init__(self, db: Session):
        self.db = db
        self._service = GarminPullService(db)

    def authenticate(self, user_id: str, **credentials: Any) -> Any:
        """Delegado 1:1 a `_garmin_login` (login/MFA/token-store existentes)."""
        return _garmin_login(user_id, credentials["email"], credentials["password"])

    def list_activities(self, client: Any, since: Any, until: Any = None) -> list[dict]:
        """Delegado 1:1 a `client.get_activities_by_date` (misma llamada que
        usa `_do_sync` hoy), con el mismo wrapper de reintentos `_retry`.
        `since`/`until` deben venir en el mismo formato que ya usa `_do_sync`
        (string YYYY-MM-DD) — este wrapper no agrega parseo propio."""
        return _retry(lambda: client.get_activities_by_date(since, until))

    def get_activity_detail(self, raw_activity: dict, **parse_kwargs: Any) -> dict:
        """Delegado 1:1 a `_parse_garmin_activity` (misma normalización que
        usa `_do_sync` hoy)."""
        return _parse_garmin_activity(raw_activity, **parse_kwargs)

    def download_gps(self, client: Any, activity_id: str) -> None:
        return _try_download_gps_track(client, activity_id)

    def download_splits(self, client: Any, activity_id: str) -> None:
        return _try_download_splits(client, activity_id)

    def get_health_daily(self, client: Any, date_iso: str) -> dict | None:
        raise NotImplementedError(
            "get_health_daily no está desacoplado todavía: hoy vive fusionado "
            "dentro de GarminPullService._sync_health_data (fetch+parse+DB-write "
            "juntos, por rango de fechas). Ver docs/plan-multi-brand-wearables.md "
            "— extraerlo requiere su propio sprint con verificación de regresión, "
            "no se debe romper a la fuerza aquí."
        )

    def get_sleep(self, client: Any, date_iso: str) -> dict | None:
        raise NotImplementedError(
            "get_sleep no está desacoplado todavía: hoy vive fusionado dentro de "
            "GarminPullService._sync_health_data junto con el resto de métricas "
            "de salud. Mismo motivo que get_health_daily."
        )

    def sync(self, user_id: str, force: bool = False) -> dict:
        """Método adicional (fuera de la interfaz estricta): delega al
        orquestador real y ya probado, `GarminPullService.sync_user`, tal
        cual está hoy en producción. Es el punto de entrada que de verdad
        usan las rutas y el scheduler."""
        return self._service.sync_user(user_id, force=force)
