"""
Sprint 52 (multi-marca) — WahooProvider real contra la API pública de
Wahoo Cloud (https://cloud-api.wahooligan.com/), documentación oficial
consultada el 2026-08-21. NADA de esto es JSON inventado: endpoints,
nombres de campo y el fixture de ejemplo salen literalmente de la doc.

IMPORTANTE — alcance real de este archivo:
  - `authenticate`/`list_activities`/`get_activity_detail`/`sync` están
    implementados contra el contrato documentado y son testeables con
    el fixture real (test_provider_contract.py).
  - `download_gps`/`download_splits`: Wahoo no expone splits ni GPS como
    endpoint aparte — solo un `workout_summary.file.url` con el .FIT
    original. Parsear FIT está fuera de alcance de este sprint; se deja
    NotImplementedError en vez de fingir soporte.
  - `get_health_daily`/`get_sleep`: la Cloud API de Wahoo es una API de
    workouts (bici/potencia/HR de entrenamiento), no encontré endpoints
    de salud diaria/sueño en la documentación pública — Wahoo son
    ciclocomputadoras/rodillos, no tienen ese sensor. NotImplementedError
    explícito, no un fallback silencioso.
  - Esta cuenta nunca fue probada end-to-end contra la API real: Wahoo
    limita el acceso a apps aprobadas ("Wahoo Fitness is currently
    limiting use of the API to those who request it"). El código sigue
    el contrato documentado al pie de la letra, pero SOLO se activa
    (WAHOO_ENABLED=true) cuando haya un usuario real con dispositivo
    Wahoo que confirme que el sync trae datos correctos. Ver
    docs/plan-multi-brand-wearables.md.
"""
from __future__ import annotations

import os
from typing import Any

import httpx
from sqlalchemy.orm import Session

from . import WearableProvider

_TOKEN_URL = "https://api.wahooligan.com/oauth/token"
_API_BASE = "https://api.wahooligan.com/v1"

# workout_type_id -> sport interno de LabX. Mapeo tomado literalmente de
# la tabla de "Workout Type IDs" de la documentación oficial (no todos
# los ~71 tipos están cubiertos, solo los relevantes para triatlón; el
# resto cae en "other", igual que hace _norm_sport con Garmin).
_WORKOUT_TYPE_SPORT = {
    0: "bike", 12: "bike", 13: "bike", 15: "bike", 61: "bike", 64: "bike", 68: "bike",
    1: "run", 5: "run", 67: "run", 71: "run",
    25: "swim", 26: "swim",
    42: "gym", 43: "gym", 66: "gym",
}


def _safe_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_wahoo_workout(raw: dict, ftp: int = 250, fcmax: float | None = None) -> dict:
    """Convierte un dict de GET /v1/workouts/:id (formato documentado, con
    `workout_summary` anidado) al formato interno de Activity."""
    sport = _WORKOUT_TYPE_SPORT.get(raw.get("workout_type_id"), "other")
    summary = raw.get("workout_summary") or {}

    starts = raw.get("starts") or ""
    date_iso = starts[:10] if starts else ""

    dur_min = round(_safe_float(raw.get("minutes")) or 0)
    dist_m = _safe_float(summary.get("distance_accum"))
    dist_km = round(dist_m / 1000, 2) if dist_m else 0.0
    avg_hr_f = _safe_float(summary.get("heart_rate_avg"))
    avg_hr = round(avg_hr_f) if avg_hr_f else None
    avg_power_f = _safe_float(summary.get("power_avg"))
    avg_power = round(avg_power_f) if avg_power_f else None
    calories_f = _safe_float(summary.get("calories_accum"))
    calories = round(calories_f) if calories_f else None
    ascent_f = _safe_float(summary.get("ascent_accum"))
    elev_m = round(ascent_f) if ascent_f else None

    # TSS: Wahoo trae su PROPIO cálculo nativo (power_bike_tss_last) para
    # actividades de bici con medidor de potencia real -- a diferencia de
    # Garmin, donde el campo equivalente (trainingStressScore) nunca se
    # observó poblado (ver comentario en _extract_tss, garmin_pull_service.py).
    # Se usa ese valor nativo si existe; solo se estima si Wahoo no lo trae.
    native_tss = _safe_float(summary.get("power_bike_tss_last"))
    if native_tss is not None:
        tss = round(native_tss, 1)
    elif avg_power:
        intensity_factor = avg_power / ftp
        tss = round((intensity_factor ** 2) * (dur_min / 60) * 100, 1)
    elif avg_hr and fcmax:
        hr_frac = avg_hr / fcmax
        tss = round((hr_frac ** 2) * (dur_min / 60) * 100, 1)
    else:
        tss = 0.0

    return {
        "activity_id": f"wahoo_{raw.get('id')}",
        "name": raw.get("name") or sport.title(),
        "sport": sport,
        "date_iso": date_iso,
        "dur_min": dur_min,
        "dist_km": dist_km,
        "avg_hr": avg_hr,
        "avg_power": avg_power,
        "calories": calories,
        "elev_m": elev_m,
        "tss": tss,
    }


class WahooProvider(WearableProvider):
    name = "wahoo"

    def __init__(self, db: Session):
        self.db = db

    async def authenticate(self, user_id: str, **credentials: Any) -> str:
        """Exchange/refresh OAuth2 token contra los endpoints documentados.
        `credentials` debe traer `code`+`redirect_uri` (primer login) o
        `refresh_token` (renovación). Retorna el access_token."""
        client_id = os.getenv("WAHOO_CLIENT_ID", "")
        client_secret = os.getenv("WAHOO_CLIENT_SECRET", "")
        params = {"client_id": client_id, "client_secret": client_secret}
        if "refresh_token" in credentials:
            params.update(grant_type="refresh_token", refresh_token=credentials["refresh_token"])
        else:
            params.update(
                grant_type="authorization_code",
                code=credentials["code"],
                redirect_uri=credentials["redirect_uri"],
            )
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(_TOKEN_URL, params=params)
            r.raise_for_status()
            return r.json()["access_token"]

    async def list_activities(self, client: Any, since: Any, page: int = 1, per_page: int = 30) -> list[dict]:
        """GET /v1/workouts (paginado, documentado)."""
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.get(
                f"{_API_BASE}/workouts",
                headers={"Authorization": f"Bearer {client}"},
                params={"page": page, "per_page": per_page},
            )
            r.raise_for_status()
            return r.json().get("workouts", [])

    def get_activity_detail(self, raw_activity: dict, **normalize_kwargs: Any) -> dict:
        return normalize_wahoo_workout(raw_activity, **normalize_kwargs)

    def download_gps(self, client: Any, activity_id: str) -> None:
        raise NotImplementedError(
            "Wahoo no expone GPS como endpoint aparte, solo workout_summary.file.url "
            "(.FIT original). Parsear FIT está fuera de alcance de este sprint."
        )

    def download_splits(self, client: Any, activity_id: str) -> None:
        raise NotImplementedError(
            "Wahoo no expone splits como endpoint aparte, solo el .FIT crudo "
            "via workout_summary.file.url. Mismo motivo que download_gps."
        )

    def get_health_daily(self, client: Any, date_iso: str) -> dict | None:
        raise NotImplementedError(
            "No se encontraron endpoints de salud diaria en la documentación "
            "pública de Wahoo Cloud API — es una API de workouts, no de wellness."
        )

    def get_sleep(self, client: Any, date_iso: str) -> dict | None:
        raise NotImplementedError(
            "No se encontraron endpoints de sueño en la documentación pública "
            "de Wahoo Cloud API. Mismo motivo que get_health_daily."
        )
