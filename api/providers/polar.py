"""
Sprint 53 (multi-marca) — PolarProvider real contra la Polar AccessLink
API (https://www.polar.com/accesslink-api/), documentación oficial
consultada el 2026-08-21. Igual criterio que wahoo.py (Sprint 52):
endpoints y el fixture de ejemplo salen literalmente de la doc, nada
inventado.

Diferencias reales encontradas frente a Wahoo (documentadas para que el
siguiente sprint no las redescubra a los golpes):
  - Polar SÍ expone GPX/TCX real por actividad (`GET /v3/exercises/{id}/gpx`)
    — a diferencia de Wahoo, que solo da un .FIT crudo. `download_gps`
    está implementado de verdad acá, reusando el parser GPX ya existente
    (`_parse_gpx` de garmin_connector.py — es agnóstico de la fuente,
    parsea XML GPX estándar, no específico de Garmin).
  - El objeto `exercise` documentado NO trae potencia ni un TSS nativo
    (a diferencia de `power_bike_tss_last` de Wahoo) — acá el único TSS
    posible es el fallback por %FCmax, y solo si `fcmax` se pasa.
  - Polar exige un paso extra después del OAuth: registrar explícitamente
    al usuario vía `POST /v3/users` con un member-id, antes de poder
    pedirle datos — si se omite, las llamadas fallan aunque el token sea
    válido. `authenticate()` lo hace como parte del mismo flujo.
  - El campo `sport` de Polar es un string libre (ej. "OTHER",
    "RUNNING") pero la documentación pública no publica el enum completo
    de valores posibles — no hay una tabla como la de workout_type_id de
    Wahoo. Por eso `_norm_polar_sport` usa matching por substring
    (run/cycl/bik/swim/strength) en vez de un dict cerrado de valores
    exactos: es la única forma honesta de mapear sin inventar un enum
    que no está documentado.

Alcance NO cubierto, con NotImplementedError explícito:
  - `get_health_daily`/`get_sleep`: Polar AccessLink tiene endpoints de
    "Nightly Recharge"/actividad diaria en otras partes de su API (fuera
    de lo que alcancé a confirmar en esta pasada de documentación) — se
    deja sin implementar en vez de adivinar la forma exacta del payload.

Igual que Wahoo: esto NO se activa en producción (`POLAR_ENABLED=false`)
hasta conseguir un usuario real con dispositivo Polar que confirme que
el sync trae datos correctos. Ver docs/plan-multi-brand-wearables.md.
"""
from __future__ import annotations

import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from . import WearableProvider

_AUTH_URL  = "https://flow.polar.com/oauth2/authorization"
_TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
_API_BASE  = "https://www.polaraccesslink.com/v3"

_DURATION_RE = re.compile(r"^PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?$")

_SPORT_KEYWORDS = [
    ("run", "run"),
    ("cycl", "bike"),
    ("bik", "bike"),
    ("swim", "swim"),
    ("strength", "gym"),
    ("fitness", "gym"),
]


def _parse_iso8601_duration_minutes(duration: str | None) -> float:
    """Polar reporta duración como ISO 8601 ('PT2H44M', formato Java
    Duration.toString()), no en segundos como Garmin/Wahoo."""
    if not duration:
        return 0.0
    m = _DURATION_RE.match(duration)
    if not m:
        return 0.0
    h, mn, s = m.groups()
    total = (int(h) if h else 0) * 60 + (int(mn) if mn else 0) + (float(s) / 60 if s else 0.0)
    return round(total, 1)


def _norm_polar_sport(raw: str | None) -> str:
    """Polar no publica un enum cerrado del campo `sport` en su doc
    pública (a diferencia de la tabla workout_type_id de Wahoo) — se
    mapea por substring, no por diccionario exacto."""
    if not raw:
        return "other"
    low = raw.lower()
    for kw, sport in _SPORT_KEYWORDS:
        if kw in low:
            return sport
    return "other"


def normalize_polar_exercise(raw: dict, fcmax: float | None = None) -> dict:
    """Convierte un dict de GET /v3/exercises/{id} (formato documentado)
    al formato interno de Activity."""
    sport = _norm_polar_sport(raw.get("sport"))
    start = raw.get("start_time") or ""
    date_iso = start[:10] if start else ""
    dur_min = _parse_iso8601_duration_minutes(raw.get("duration"))
    dist_m = raw.get("distance")
    dist_km = round(dist_m / 1000, 2) if dist_m else 0.0
    hr = raw.get("heart_rate") or {}
    avg_hr = hr.get("average")
    calories = raw.get("calories")

    # Sin potencia ni TSS nativo documentados en el objeto exercise de
    # Polar (a diferencia de power_bike_tss_last de Wahoo) — único
    # fallback posible es %FCmax, y solo si se conoce fcmax real del atleta.
    if avg_hr and fcmax:
        hr_frac = avg_hr / fcmax
        tss = round((hr_frac ** 2) * (dur_min / 60) * 100, 1)
    else:
        tss = 0.0

    return {
        "activity_id": f"polar_{raw.get('id')}",
        "name": raw.get("device") or sport.title(),
        "sport": sport,
        "date_iso": date_iso,
        "dur_min": round(dur_min),
        "dist_km": dist_km,
        "avg_hr": avg_hr,
        "avg_power": None,
        "calories": calories,
        "elev_m": None,
        "tss": tss,
    }


class PolarProvider(WearableProvider):
    name = "polar"

    def __init__(self, db: Session):
        self.db = db

    async def authenticate(self, user_id: str, **credentials: Any) -> str:
        """Exchange de OAuth2 (`code` -> access_token) + registro obligatorio
        del usuario vía POST /v3/users (member_id) — sin esto, Polar
        rechaza cualquier pedido de datos aunque el token sea válido."""
        client_id = credentials.get("client_id", "")
        client_secret = credentials.get("client_secret", "")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                _TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "code": credentials["code"],
                    "redirect_uri": credentials["redirect_uri"],
                },
                auth=(client_id, client_secret),
                headers={"Accept": "application/json"},
            )
            r.raise_for_status()
            token_data = r.json()
            access_token = token_data["access_token"]

            reg = await client.post(
                f"{_API_BASE}/users",
                json={"member-id": credentials["member_id"]},
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            )
            # 409 = ya estaba registrado (idempotente, no es error real)
            if reg.status_code not in (200, 201, 409):
                reg.raise_for_status()

            return access_token

    async def list_activities(self, client: Any, since: Any) -> list[dict]:
        """GET /v3/exercises (lista de transacción de exercises nuevos)."""
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.get(
                f"{_API_BASE}/exercises",
                headers={"Authorization": f"Bearer {client}", "Accept": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
            return data.get("exercises", data) if isinstance(data, dict) else data

    def get_activity_detail(self, raw_activity: dict, **normalize_kwargs: Any) -> dict:
        return normalize_polar_exercise(raw_activity, **normalize_kwargs)

    async def download_gps(self, client: Any, activity_id: str) -> None:
        """GET /v3/exercises/{id}/gpx — reusa el parser GPX genérico ya
        existente (garmin_connector._parse_gpx), no específico de Garmin."""
        from garmin_connector import _parse_gpx, TRACKS_DIR
        import json as _json

        TRACKS_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = TRACKS_DIR / f"polar_{activity_id}.json"
        if cache_file.exists() and cache_file.stat().st_size > 10:
            return
        async with httpx.AsyncClient(timeout=20) as http:
            r = await http.get(
                f"{_API_BASE}/exercises/{activity_id}/gpx",
                headers={"Authorization": f"Bearer {client}"},
            )
            if r.status_code != 200:
                return
            pts = _parse_gpx(r.content)
            if pts:
                cache_file.write_text(_json.dumps(pts))

    def download_splits(self, client: Any, activity_id: str) -> None:
        raise NotImplementedError(
            "Polar no documenta un endpoint de 'splits/laps' equivalente al "
            "de Garmin (get_activity_splits) — solo samples/zones vía "
            "?samples=true&zones=true en GET /v3/exercises/{id}, que es un "
            "formato distinto (series de tiempo, no laps). Requiere su "
            "propio trabajo de normalización, no se improvisa acá."
        )

    def get_health_daily(self, client: Any, date_iso: str) -> dict | None:
        raise NotImplementedError(
            "Polar AccessLink probablemente expone actividad diaria/Nightly "
            "Recharge en otro endpoint, pero no lo confirmé en esta pasada "
            "de documentación — no se implementa a ciegas."
        )

    def get_sleep(self, client: Any, date_iso: str) -> dict | None:
        raise NotImplementedError(
            "Mismo motivo que get_health_daily: no confirmado en la "
            "documentación pública consultada."
        )
