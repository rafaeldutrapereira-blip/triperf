"""
Interfaz común para integraciones de wearables (Sprint 48 — ver
docs/plan-multi-brand-wearables.md).

IMPORTANTE — alcance real de este archivo en Sprint 48:
Esta interfaz describe la forma "ideal" (granular, por-actividad/por-día)
que debería tener cualquier integración nueva (Wahoo/Polar/Coros). Pero
Garmin y Strava HOY no están escritos así: `GarminPullService._do_sync`
y `strava_routes._sync_strava_activities` son orquestadores monolíticos
que hacen fetch+parse+DB-write juntos, por rango de fechas, no por
actividad individual. Descomponerlos a la fuerza para que "calcen" en
esta interfaz sería reescribir lógica de sync en producción sin forma
de probarla contra hardware real — exactamente el riesgo que este
sprint quiere evitar.

Por eso `GarminProvider`/`StravaProvider` (en garmin_provider.py /
strava_provider.py) implementan:
  - los métodos que SÍ existen ya como piezas reutilizables aisladas
    (login/auth, descarga de GPS/splits) delegando 1:1 al código
    existente, sin tocarlo.
  - `sync(...)` como método adicional (fuera de esta interfaz estricta)
    que delega al orquestador monolítico existente tal cual está.
  - los métodos que NO existen como piezas aisladas (get_health_daily,
    get_sleep, list_activities/get_activity_detail desacoplados de la
    escritura en DB) levantan NotImplementedError explícito — no se
    fingen implementaciones. Extraerlos de forma segura queda para un
    sprint de seguimiento dedicado, con tests de regresión antes/después.

Cualquier provider NUEVO (Wahoo, Polar, Coros) sí debe implementar la
interfaz completa desde cero, porque no arrastra la deuda histórica de
Garmin/Strava.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class WearableProvider(ABC):
    """Contrato común que debe cumplir cualquier integración de wearable."""

    #: nombre corto usado en la columna `provider` de las tablas (Sprint 48
    #: agrega esta columna vía migración Alembic). Ej: "garmin", "strava".
    name: str

    @abstractmethod
    def authenticate(self, user_id: str, **credentials: Any) -> Any:
        """Autentica contra la API del proveedor. Retorna un cliente/sesión
        autenticada opaca que el resto de los métodos puede reutilizar."""
        raise NotImplementedError

    @abstractmethod
    def list_activities(self, client: Any, since: Any) -> list[dict]:
        """Lista actividades crudas (formato propio del proveedor) desde
        `since` hasta ahora. No normaliza ni escribe en DB."""
        raise NotImplementedError

    @abstractmethod
    def get_activity_detail(self, raw_activity: dict) -> dict:
        """Normaliza una actividad cruda del proveedor al formato interno
        de LabX (sport, date_iso, dur_min, dist_km, tss, etc.)."""
        raise NotImplementedError

    def download_gps(self, client: Any, activity_id: str) -> None:
        """Descarga y guarda el track GPS de una actividad, si existe.
        Best-effort: no todos los proveedores/actividades tienen GPS."""
        raise NotImplementedError

    def download_splits(self, client: Any, activity_id: str) -> None:
        """Descarga y guarda los splits (parciales) de una actividad, si existen."""
        raise NotImplementedError

    def get_health_daily(self, client: Any, date_iso: str) -> dict | None:
        """Métricas diarias de salud (HRV, body battery, RHR, stress, etc.)
        para una fecha puntual. Retorna None si el proveedor no las expone."""
        raise NotImplementedError

    def get_sleep(self, client: Any, date_iso: str) -> dict | None:
        """Datos de sueño de una fecha puntual. Retorna None si el
        proveedor no los expone."""
        raise NotImplementedError
