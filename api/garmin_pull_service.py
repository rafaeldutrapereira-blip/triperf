"""
LabX — Garmin Pull Service
============================
Descarga el historial completo de actividades Garmin de un usuario
y lo almacena en la DB. Se llama en background al hacer login.

Flujo por usuario:
  1. Verificar si necesita sync (última vez < STALE_HOURS ago → skip)
  2. Descifrar credenciales Garmin del usuario
  3. Autenticar con garminconnect (librería unofficial)
  4. Fetch incremental: desde la última actividad registrada hasta hoy
  5. Calcular CTL/ATL/TSB sobre todo el historial
  6. Guardar en athlete_activities + athlete_training_load
  7. Actualizar garmin_sync_status

Ejecutar como BackgroundTask en FastAPI (non-blocking para el login).
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from .crypto   import decrypt
from .database import SessionLocal
from .models   import (
    GarminActivity, GarminSyncStatus, GarminTrainingLoad, User,
    GarminHealthDaily, GarminSleepSession,
    CommunityPost, GarminTrainingLoad as _TL,
    GarminPlannedWorkout,
)

# ── Token storage ─────────────────────────────────────────────────────────────
# Cada usuario tiene su propio directorio de tokens Garmin (garth session)
_BASE_DIR   = Path(__file__).resolve().parent.parent
TOKEN_DIR   = _BASE_DIR / "data" / "garmin_tokens"
TOKEN_DIR.mkdir(parents=True, exist_ok=True)

def _token_path(user_id: str) -> Path:
    return TOKEN_DIR / user_id

# ── C-20: MFA pending state en Redis (con TTL 10min) ─────────────────────────
# Ya NO se usa dict global en memoria (no persiste entre reinicios, no thread-safe).
# Fallback: dict en memoria si Redis no está disponible (solo para desarrollo).
_mfa_pending_fallback: dict[str, dict] = {}
_MFA_TTL_SECONDS = 600  # 10 minutos para completar el MFA


def _mfa_set(user_id: str, data: dict) -> None:
    """Guarda estado MFA en Redis. Si no disponible, usa fallback en memoria."""
    import json as _json
    from .redis_client import redis_set, is_available
    if is_available():
        redis_set(f"garmin_mfa:{user_id}", _json.dumps(data), ex=_MFA_TTL_SECONDS)
    else:
        _mfa_pending_fallback[user_id] = data


def _mfa_get(user_id: str) -> dict | None:
    """Recupera estado MFA."""
    import json as _json
    from .redis_client import redis_get, is_available
    if is_available():
        raw = redis_get(f"garmin_mfa:{user_id}")
        return _json.loads(raw) if raw else None
    return _mfa_pending_fallback.get(user_id)


def _mfa_del(user_id: str) -> None:
    """Elimina estado MFA tras completar o expirar."""
    from .redis_client import redis_delete, is_available
    if is_available():
        redis_delete(f"garmin_mfa:{user_id}")
    else:
        _mfa_pending_fallback.pop(user_id, None)


# Alias para compatibilidad con código existente que accede a _mfa_pending
class _MfaDict:
    """Proxy que redirige accesos al dict a Redis/fallback."""
    def __contains__(self, user_id): return _mfa_get(user_id) is not None
    def __setitem__(self, user_id, data): _mfa_set(user_id, data)
    def __getitem__(self, user_id):
        v = _mfa_get(user_id)
        if v is None: raise KeyError(user_id)
        return v
    def get(self, user_id, default=None): return _mfa_get(user_id) or default
    def pop(self, user_id, default=None):
        v = _mfa_get(user_id)
        _mfa_del(user_id)
        return v or default

_mfa_pending = _MfaDict()


class GarminMFARequired(Exception):
    """Garmin requires verification code — user must use reauth UI."""

logger = logging.getLogger("labx.garmin_pull")

# ── S13: Retry con backoff exponencial ────────────────────────────────────────

def _retry(func, max_attempts: int = 3, base_delay: float = 2.0):
    """
    S13: Ejecuta func con retry exponencial.
    Retorna el resultado o re-lanza la última excepción.
    """
    import time
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return func()
        except Exception as e:
            last_exc = e
            # Detectar rate limit de Garmin (HTTP 429)
            if "429" in str(e) or "Too Many" in str(e):
                wait = 60 * (2 ** attempt)   # 60s, 120s, 240s
                logger.warning("Garmin rate limit — esperando %ds (intento %d/%d)",
                               wait, attempt + 1, max_attempts)
                time.sleep(wait)
            elif attempt < max_attempts - 1:
                wait = base_delay * (2 ** attempt)  # 2s, 4s, 8s
                logger.warning("Garmin error — reintentando en %ds: %s", wait, e)
                time.sleep(wait)
    raise last_exc


# ── Constantes ────────────────────────────────────────────────────────────────
STALE_HOURS   = 4          # No re-sincronizar si el último sync fue hace menos de esto
HISTORY_START = "2010-01-01"  # Fecha desde donde arrancar si no hay actividades previas
CTL_TAU       = 42         # días constante de tiempo CTL (fitness)
ATL_TAU       = 7          # días constante de tiempo ATL (fatiga)
_CTL_K        = 1 - math.exp(-1 / CTL_TAU)
_ATL_K        = 1 - math.exp(-1 / ATL_TAU)
_CTL_DECAY    = math.exp(-1 / CTL_TAU)
_ATL_DECAY    = math.exp(-1 / ATL_TAU)

# Mapeo de sport_type Garmin → categoría interna
_SPORT_MAP: dict[str, str] = {
    # Natación
    "swimming":               "swim",
    "pool_swimming":          "swim",
    "open_water_swimming":    "swim",
    "lap_swimming":           "swim",
    "indoor_swimming":        "swim",
    "swim":                   "swim",
    # Ciclismo
    "cycling":                "bike",
    "indoor_cycling":         "bike",
    "virtual_ride":           "bike",
    "road_biking":            "bike",
    "mountain_biking":        "bike",
    "gravel_cycling":         "bike",
    "cycling_workout":        "bike",
    # Carrera
    "running":                "run",
    "trail_running":          "run",
    "treadmill_running":      "run",
    "indoor_running":         "run",
    "track_running":          "run",
    # Fuerza / Gym
    "strength_training":      "gym",
    "fitness_equipment":      "gym",
    "cardio":                 "gym",
    "hiit":                   "gym",
    "yoga":                   "gym",
    "pilates":                "gym",
    "bouldering":             "gym",
    # Otros
    "hiking":                 "other",
    "walking":                "other",
    "other":                  "other",
}

# Colores por deporte para el frontend
_SPORT_COLOR = {
    "swim":  ("rgba(14,165,233,.12)",  "var(--cyan)"),
    "bike":  ("rgba(255,101,53,.10)",  "var(--orange)"),
    "run":   ("rgba(16,185,129,.10)",  "var(--green)"),
    "gym":   ("rgba(168,85,247,.10)",  "var(--purple)"),
    "other": ("rgba(127,179,204,.08)", "var(--muted)"),
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _norm_sport(raw: str | None) -> str:
    if not raw:
        return "other"
    return _SPORT_MAP.get(raw.lower(), "other")


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v)) if v is not None else default
    except (TypeError, ValueError):
        return default


def _format_pace(speed_mps: float | None) -> str | None:
    """m/s → 'mm:ss /km'"""
    if not speed_mps or speed_mps <= 0:
        return None
    secs_per_km = 1000 / speed_mps
    return f"{int(secs_per_km // 60)}:{int(secs_per_km % 60):02d}"


def _format_swim_pace(speed_mps: float | None) -> str | None:
    """m/s → 'mm:ss /100m'"""
    if not speed_mps or speed_mps <= 0:
        return None
    secs_per_100 = 100 / speed_mps
    return f"{int(secs_per_100 // 60)}:{int(secs_per_100 % 60):02d}"


def _dur_str(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h}h {m}min" if h else f"{m}min"


# ─────────────────────────────────────────────────────────────────────────────
# TSS desde datos Garmin
# ─────────────────────────────────────────────────────────────────────────────

def _extract_tss(act: dict, ftp: int = 250) -> float:
    """
    Extrae TSS del activity dict de Garmin.
    Prioridad: trainingStressScore → estimación por tipo/duración.
    B-08: duration=None/null → _safe_float devuelve 0.0, nunca NaN.
    """
    tss = _safe_float(act.get("trainingStressScore"))
    if tss > 0 and not math.isnan(tss) and not math.isinf(tss):
        return round(tss, 1)

    dur_raw = act.get("duration")
    dur_h   = _safe_float(dur_raw) / 3600.0  # _safe_float(None) = 0.0 → dur_h = 0.0
    sport   = _norm_sport(act.get("activityType", {}).get("typeKey") if isinstance(act.get("activityType"), dict) else act.get("activityType"))

    # Sin duración válida no podemos estimar TSS — retornar 0 (no NaN)
    if dur_h <= 0:
        return 0.0

    # Estimación básica por HR si disponible
    avg_hr   = _safe_float(act.get("averageHR"))
    max_hr   = 190.0
    hrr_frac = (avg_hr / max_hr) if avg_hr > 0 else 0.7

    # IF estimado desde %HRmax (Karvonen simplificado)
    IF_est = hrr_frac * 0.95

    if sport in ("bike", "run", "swim"):
        result = IF_est ** 2 * dur_h * 100
        # Sanidad: nunca retornar NaN/Inf/valores absurdos
        if math.isnan(result) or math.isinf(result) or result < 0:
            return 0.0
        return round(min(result, 600.0), 1)  # cap en 600 TSS (sesión de 24h de IM es ~1000)

    # Gym/strength: TSS fijo bajo por duración
    if sport == "gym" and dur_h > 0:
        return round(dur_h * 25, 1)

    return round(IF_est ** 2 * dur_h * 100, 1)


# ─────────────────────────────────────────────────────────────────────────────
# CTL / ATL / TSB
# ─────────────────────────────────────────────────────────────────────────────

def _compute_training_load(
    activities: list[dict],
    start_ctl: float = 0.0,
    start_atl: float = 0.0,
) -> list[dict]:
    """
    Recalcula CTL/ATL/TSB día a día sobre toda la historia de actividades.
    Devuelve lista de dicts {date_iso, ctl, atl, tsb, tss}.
    """
    if not activities:
        return []

    # Agrupar TSS por día — B-08: filtrar NaN/Inf antes de acumular
    tss_by_day: dict[str, float] = {}
    for a in activities:
        d = a.get("date_iso") or ""
        if not d:
            continue
        tss_val = _safe_float(a.get("tss"))
        if math.isnan(tss_val) or math.isinf(tss_val) or tss_val < 0:
            tss_val = 0.0
        tss_by_day[d] = tss_by_day.get(d, 0.0) + tss_val

    if not tss_by_day:
        return []

    dates_sorted = sorted(tss_by_day)
    start_dt = date.fromisoformat(dates_sorted[0])
    end_dt   = date.today()

    ctl = start_ctl
    atl = start_atl
    result: list[dict] = []

    cur = start_dt
    while cur <= end_dt:
        iso = cur.isoformat()
        tss = tss_by_day.get(iso, 0.0)
        ctl = ctl * _CTL_DECAY + tss * _CTL_K
        atl = atl * _ATL_DECAY + tss * _ATL_K
        tsb = ctl - atl
        result.append({
            "date_iso": iso,
            "ctl":      round(ctl, 1),
            "atl":      round(atl, 1),
            "tsb":      round(tsb, 1),
            "tss":      round(tss, 1),
        })
        cur += timedelta(days=1)

    return result


# ─────────────────────────────────────────────────────────────────────────────
# ACWR (razón aguda:crónica, 7:28 días)
# ─────────────────────────────────────────────────────────────────────────────

def _compute_acwr(load_rows: list[dict]) -> float:
    """Últimas 28 filas → ACWR = promedio últimas 7 / promedio últimas 28."""
    if len(load_rows) < 7:
        return 0.0
    last28 = load_rows[-28:]
    last7  = load_rows[-7:]
    chronic = sum(r["tss"] for r in last28) / len(last28)
    acute   = sum(r["tss"] for r in last7)  / len(last7)
    if chronic < 1:
        return 0.0
    return round(acute / chronic, 2)


# ─────────────────────────────────────────────────────────────────────────────
# PARSE de activities Garmin → formato interno
# ─────────────────────────────────────────────────────────────────────────────

def _parse_garmin_activity(act: dict, ftp: int = 250) -> dict:
    """
    Convierte un dict de garminconnect.get_activities_by_date() al formato
    interno de GarminActivity / KL_DATA.activities.
    """
    raw_sport = (
        act.get("activityType", {}).get("typeKey")
        if isinstance(act.get("activityType"), dict)
        else act.get("activityType") or ""
    )
    sport = _norm_sport(raw_sport)
    color, stroke = _SPORT_COLOR.get(sport, _SPORT_COLOR["other"])

    # Fecha
    start_raw = act.get("startTimeLocal") or act.get("startTimeGMT") or ""
    date_iso  = start_raw[:10] if start_raw else ""
    mo_names  = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    date_label = ""
    if date_iso:
        try:
            dt = date.fromisoformat(date_iso)
            date_label = f"{dt.day} {mo_names[dt.month-1]}"
        except ValueError:
            pass

    dur_sec  = _safe_float(act.get("duration"))
    dur_min  = round(dur_sec / 60) if dur_sec else 0
    dist_m   = _safe_float(act.get("distance"))
    dist_km  = round(dist_m / 1000, 2) if dist_m else 0.0
    avg_hr   = _safe_int(act.get("averageHR"))
    avg_spd  = _safe_float(act.get("averageSpeed"))
    avg_pwr  = _safe_int(act.get("averagePower"))
    calories = _safe_int(act.get("calories"))
    elev     = _safe_float(act.get("elevationGain"))
    tss      = _extract_tss(act, ftp)

    pace_str  = _format_pace(avg_spd)   if sport == "run"  else None
    swim_pace = _format_swim_pace(avg_spd) if sport == "swim" else None

    # B-24: Swim metrics — Garmin returns averageSwolf, avgStrokes, avgStrokeRate, poolLength
    swolf           = _safe_float(act.get("averageSwolf"))   or _safe_float(act.get("avgSwolf"))
    avg_cadence_spm = _safe_float(act.get("avgStrokes"))     or _safe_float(act.get("averageStrokes"))
    pool_length_m   = _safe_int(act.get("poolLength"))
    if avg_cadence_spm and dur_sec:
        avg_cadence_spm = round(avg_cadence_spm, 1)

    return {
        "activity_id":    act.get("activityId"),
        "name":           act.get("activityName") or sport.title(),
        "sport":          sport,
        "icon":           {"swim":"🏊","bike":"🚴","run":"🏃","gym":"💪"}.get(sport,"🏅"),
        "color":          color,
        "stroke":         stroke,
        "date_iso":       date_iso,
        "date_label":     date_label,
        "dur_min":        dur_min,
        "dist_km":        dist_km,
        "avg_hr":         avg_hr or None,
        "avg_power":      avg_pwr or None,
        "pace_str":       pace_str,
        "swim_pace":      swim_pace,
        "calories":       calories or None,
        "elev_m":         round(elev) if elev else None,
        "tss":            tss,
        "swolf":          round(swolf, 1) if swolf else None,
        "avg_cadence_spm":avg_cadence_spm,
        "pool_length_m":  pool_length_m,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ACWR + MONOTONÍA + STRAIN sobre historial de carga
# ─────────────────────────────────────────────────────────────────────────────

def _enrich_load_with_acwr(load_rows: list[dict]) -> list[dict]:
    """
    Agrega acwr, monotony y strain a cada fila del historial de carga.
    Requiere al menos 7 filas para ACWR y 7 para monotonía (std desviación).
    """
    import statistics

    enriched = []
    for i, row in enumerate(load_rows):
        new_row = dict(row)

        # ACWR — 7 días agudos / 28 días crónicos
        if i >= 6:
            window28 = load_rows[max(0, i - 27): i + 1]
            window7  = load_rows[i - 6: i + 1]
            chronic  = sum(r["tss"] for r in window28) / len(window28)
            acute    = sum(r["tss"] for r in window7)  / len(window7)
            new_row["acwr"] = round(acute / chronic, 2) if chronic >= 1 else None
        else:
            new_row["acwr"] = None

        # Monotonía y strain — últimos 7 días
        if i >= 6:
            week_vals = [r["tss"] for r in load_rows[i - 6: i + 1]]
            avg_tss   = statistics.mean(week_vals)
            try:
                std_tss = statistics.stdev(week_vals)
            except statistics.StatisticsError:
                std_tss = 0.0
            monotony = round(avg_tss / std_tss, 2) if std_tss > 0 else 0.0
            strain   = round(monotony * sum(week_vals), 1)
            new_row["monotony"] = monotony
            new_row["strain"]   = strain
        else:
            new_row["monotony"] = None
            new_row["strain"]   = None

        enriched.append(new_row)

    return enriched


# ─────────────────────────────────────────────────────────────────────────────
# GARMIN LOGIN — token cache + MFA flow (garminconnect 0.3.6 API)
# ─────────────────────────────────────────────────────────────────────────────

def _garmin_login(user_id: str, email: str, password: str):
    """
    Autentica con Garmin Connect usando garminconnect 0.3.6.
    - Si hay token guardado lo carga (sin credenciales).
    - Si no, hace login completo con return_on_mfa=True.
    - Si Garmin pide MFA, guarda el estado en _mfa_pending y lanza GarminMFARequired.
    - El frontend debe llamar a /garmin/reauth para iniciar el flujo UI.
    """
    from garminconnect import Garmin

    token_store = str(_token_path(user_id).resolve())
    _token_path(user_id).mkdir(parents=True, exist_ok=True)

    client = Garmin(email, password, return_on_mfa=True)
    mfa_status, client_state = client.login(tokenstore=token_store)

    if mfa_status:
        logger.info("Garmin MFA required user=%s type=%s", user_id, mfa_status)
        _mfa_pending[user_id] = {
            "kind":         "state",
            "client":       client,
            "client_state": client_state,
            "mfa_type":     mfa_status,
            "token_store":  token_store,
        }
        raise GarminMFARequired(
            f"Verificación Garmin requerida (tipo: {mfa_status}). "
            "Ve a tu Perfil → Reconectar Garmin e ingresa el código."
        )

    # IMPORTANTE: con return_on_mfa=True, la librería garminconnect retorna
    # temprano en TODO login por credenciales (incluso sin MFA real) y NUNCA
    # guarda el token en disco ni carga el perfil (display_name) — ese
    # trabajo solo lo hace su rama return_on_mfa=False. Lo replicamos acá
    # a mano; si no, cada sync vuelve a pedir credenciales/MFA de cero y
    # cualquier endpoint que necesite display_name (RHR, sleep) falla.
    try:
        client.client.dump(token_store)
    except Exception as exc:
        logger.warning("Garmin token dump falló user=%s: %s", user_id, exc)
    if not client.display_name:
        try:
            prof = client.client.connectapi("/userprofile-service/socialProfile")
            if isinstance(prof, dict):
                client.display_name = prof.get("displayName")
                client.full_name = prof.get("fullName", "")
        except Exception as exc:
            logger.warning("Garmin profile fetch falló user=%s: %s", user_id, exc)

    logger.info("Garmin login ok user=%s display_name=%s", user_id, bool(client.display_name))
    return client


def start_mfa_flow(user_id: str, email: str, password: str, db: Session) -> dict:
    """
    Inicia o retoma el flujo MFA de Garmin desde la UI.
    Si ya hay un estado MFA pendiente (de un background sync fallido), lo retoma.
    Si no, hace un nuevo login y detecta si Garmin pide MFA.
    Retorna {ok, needs_mfa, mfa_type?}.
    """
    from garminconnect import Garmin

    # Retomar estado existente (de background sync que falló por MFA)
    existing = _mfa_pending.get(user_id)
    if existing and existing.get("kind") == "state":
        logger.info("Retomando sesión MFA existente user=%s", user_id)
        return {"ok": True, "needs_mfa": True, "mfa_type": existing.get("mfa_type", "unknown")}

    # Login nuevo
    try:
        token_store = str(_token_path(user_id).resolve())
        _token_path(user_id).mkdir(parents=True, exist_ok=True)

        client = Garmin(email, password, return_on_mfa=True)
        mfa_status, client_state = client.login(tokenstore=token_store)

        if mfa_status:
            _mfa_pending[user_id] = {
                "kind":         "state",
                "client":       client,
                "client_state": client_state,
                "mfa_type":     mfa_status,
                "token_store":  token_store,
            }
            return {"ok": True, "needs_mfa": True, "mfa_type": mfa_status}

        # Login OK sin MFA — replicar guardado de token + carga de perfil
        # que garminconnect se salta en modo return_on_mfa=True (ver
        # comentario en _garmin_login).
        try:
            client.client.dump(token_store)
        except Exception as exc:
            logger.warning("Garmin token dump falló user=%s: %s", user_id, exc)
        if not client.display_name:
            try:
                prof = client.client.connectapi("/userprofile-service/socialProfile")
                if isinstance(prof, dict):
                    client.display_name = prof.get("displayName")
                    client.full_name = prof.get("fullName", "")
            except Exception as exc:
                logger.warning("Garmin profile fetch falló user=%s: %s", user_id, exc)

        logger.info("start_mfa_flow: login sin MFA user=%s display_name=%s", user_id, bool(client.display_name))
        _update_sync_status_ok(user_id, db)
        return {"ok": True, "needs_mfa": False}

    except GarminMFARequired:
        raise
    except Exception as exc:
        logger.error("start_mfa_flow error user=%s: %s", user_id, exc)
        return {"ok": False, "error": str(exc)}


def submit_mfa_code(user_id: str, code: str, db: Session) -> dict:
    """
    Recibe el código MFA del usuario y completa la autenticación via resume_login().
    Guarda el token en disco para futuros syncs sin MFA.
    """
    entry = _mfa_pending.get(user_id)
    if not entry or entry.get("kind") != "state":
        return {"ok": False, "error": "No hay sesión MFA pendiente. Inicia reconexión desde tu perfil."}

    from garminconnect import Garmin
    client:       Garmin = entry["client"]
    client_state: dict   = entry["client_state"]
    token_store:  str    = entry["token_store"]

    try:
        client.resume_login(client_state, code.strip())
        # Guardar tokens en disco para futuros logins sin MFA
        client.client.dump(token_store)
        _mfa_pending.pop(user_id, None)
        logger.info("Garmin MFA completado y token guardado user=%s", user_id)

        _update_sync_status_ok(user_id, db)
        return {"ok": True}
    except Exception as exc:
        logger.error("submit_mfa_code error user=%s: %s", user_id, exc)
        return {"ok": False, "error": str(exc)}


def _update_sync_status_ok(user_id: str, db: Session) -> None:
    row = db.query(GarminSyncStatus).filter(GarminSyncStatus.user_id == user_id).first()
    if row:
        row.status = "ok"
        row.error  = None
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("_update_sync_status_ok commit falló user=%s: %s", user_id, exc)


# ─────────────────────────────────────────────────────────────────────────────
# SERVICIO PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

class GarminPullService:
    """
    Descarga y persiste los datos Garmin de un atleta.
    Instanciar una vez por tarea de background.
    """

    def __init__(self, db: Session):
        self._db = db

    # ── Public ──────────────────────────────────────────────────────────────

    def sync_user(self, user_id: str, force: bool = False) -> dict:
        """
        Entry point principal. Llama desde BackgroundTasks en login.
        force=True: ignora STALE_HOURS y re-sincroniza siempre.
        """
        db = self._db
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.garmin_email:
            return {"ok": False, "reason": "no_garmin_credentials"}

        # ── Stale check ──────────────────────────────────────────────────────
        status_row = db.query(GarminSyncStatus).filter(
            GarminSyncStatus.user_id == user_id
        ).first()

        if not force and status_row and status_row.last_sync_at:
            elapsed = (datetime.now(timezone.utc).replace(tzinfo=None) - status_row.last_sync_at).total_seconds() / 3600
            # B-06: solo saltar si fue en la última hora Y no es un nuevo día calendario.
            # Esto permite sincronizar un segundo entrenamiento del mismo día.
            same_day = status_row.last_sync_at.date() == date.today()
            if elapsed < 1.0 and same_day:
                logger.info("Sync skip user=%s (%.1fh < 1h, mismo día)", user_id, elapsed)
                return {"ok": True, "reason": "fresh", "elapsed_h": round(elapsed, 1)}
            elif elapsed < STALE_HOURS and not same_day:
                logger.info("Sync skip user=%s (%.1fh < %dh, día anterior)", user_id, elapsed, STALE_HOURS)
                return {"ok": True, "reason": "fresh", "elapsed_h": round(elapsed, 1)}

        # ── Marcar en progreso ────────────────────────────────────────────────
        self._set_status(user_id, "syncing", status_row)

        try:
            g_email = user.garmin_email
            g_pass  = decrypt(user.garmin_password) or user.garmin_password
            ftp     = user.ftp or 250

            result = self._do_sync(user_id, g_email, g_pass, ftp)
            self._set_status(user_id, "ok", status_row,
                             activities_total=result.get("total", 0))
            logger.info("Sync ok user=%s acts=%d", user_id, result.get("total", 0))
            try:
                from .sse_broker import publish_nowait
                publish_nowait(user_id, "garmin_sync_done",
                               {"activities_synced": result.get("total", 0),
                                "new_activities": result.get("new", 0)})
            except Exception:
                pass
            return {"ok": True, **result}

        except GarminMFARequired as exc:
            # No es un error fatal — el usuario debe reconectar desde el perfil
            logger.info("Sync pausado (MFA) user=%s", user_id)
            self._set_status(user_id, "needs_reauth", status_row, error=str(exc))
            return {"ok": False, "reason": "needs_reauth", "message": str(exc)}

        except Exception as exc:
            logger.exception("Sync error user=%s", user_id)
            self._set_status(user_id, "error", status_row, error=str(exc))
            return {"ok": False, "reason": str(exc)}

    # ── Privados ─────────────────────────────────────────────────────────────

    def _do_sync(self, user_id: str, email: str, password: str, ftp: int) -> dict:
        try:
            from garminconnect import Garmin
        except ImportError:
            raise RuntimeError("garminconnect no instalado: pip install garminconnect")

        db = self._db

        # Fecha desde la que arrancar (incremental)
        last_act = (
            db.query(GarminActivity)
              .filter(GarminActivity.user_id == user_id)
              .order_by(GarminActivity.date_iso.desc())
              .first()
        )
        fetch_from = last_act.date_iso if last_act else HISTORY_START
        fetch_to   = date.today().isoformat()

        logger.info("Garmin fetch user=%s from=%s to=%s", user_id, fetch_from, fetch_to)

        client = _retry(lambda: _garmin_login(user_id, email, password))

        raw_acts = _retry(lambda: client.get_activities_by_date(fetch_from, fetch_to))
        if not raw_acts:
            return {"total": 0, "new": 0}

        # Parsear y upsert
        new_count = 0
        for raw in raw_acts:
            parsed = _parse_garmin_activity(raw, ftp)
            act_id = str(parsed["activity_id"]) if parsed["activity_id"] else None
            if not act_id or not parsed["date_iso"]:
                continue

            existing = (
                db.query(GarminActivity)
                  .filter(GarminActivity.user_id == user_id,
                          GarminActivity.activity_id == act_id)
                  .first()
            )
            if existing:
                # Actualizar TSS por si cambió FTP
                existing.tss      = parsed["tss"]
                existing.avg_hr   = parsed["avg_hr"]
                existing.avg_power= parsed["avg_power"]
            else:
                import uuid as _uuid_mod
                new_act = GarminActivity(
                    user_id     = user_id,
                    activity_id = act_id,
                    name        = parsed["name"],
                    sport       = parsed["sport"],
                    date_iso    = parsed["date_iso"],
                    date_label  = parsed["date_label"],
                    dur_min     = parsed["dur_min"],
                    dist_km     = parsed["dist_km"],
                    avg_hr      = parsed["avg_hr"],
                    avg_power   = parsed["avg_power"],
                    pace_str    = parsed["pace_str"],
                    swim_pace   = parsed["swim_pace"],
                    calories    = parsed["calories"],
                    elev_m      = parsed["elev_m"],
                    tss         = parsed["tss"],
                    icon        = parsed["icon"],
                    color       = parsed["color"],
                    stroke      = parsed["stroke"],
                )
                db.add(new_act)
                db.flush()  # obtener ID antes de crear el post

                # B-14 Community: auto-publicar actividad con visibilidad "followers"
                # Solo actividades con duración mínima significativa (>= 10 min)
                if (parsed.get("dur_min") or 0) >= 10:
                    try:
                        # Buscar training load del día para incluir CTL/TSB
                        tl = db.query(_TL).filter(
                            _TL.user_id  == user_id,
                            _TL.date_iso == parsed["date_iso"],
                        ).first()
                        post = CommunityPost(
                            id          = str(_uuid_mod.uuid4()),
                            user_id     = user_id,
                            activity_id = new_act.id,
                            post_type   = "activity",
                            visibility  = "followers",
                            sport       = parsed["sport"],
                            dist_km     = parsed.get("dist_km"),
                            dur_min     = parsed.get("dur_min"),
                            tss         = parsed.get("tss"),
                            ctl_day     = tl.ctl if tl else None,
                            tsb_day     = tl.tsb if tl else None,
                        )
                        db.add(post)
                    except Exception as _post_err:
                        logger.debug("Auto-post comunidad fallo (no bloqueante): %s", _post_err)

                new_count += 1

        db.commit()

        # Recalcular CTL/ATL/TSB completo (necesario porque TSS puede haber cambiado)
        self._rebuild_training_load(user_id, ftp)

        # Sincronizar datos de salud — incremental: solo desde el último día
        # guardado (+1 de margen por si Garmin actualiza el día anterior).
        # Fallback a 30 días solo si el usuario nunca sincronizó salud antes.
        try:
            last_health = (
                db.query(GarminHealthDaily)
                  .filter(GarminHealthDaily.user_id == user_id)
                  .order_by(GarminHealthDaily.date_iso.desc())
                  .first()
            )
            if last_health:
                gap_days = (date.today() - date.fromisoformat(last_health.date_iso)).days
                health_days = max(2, min(gap_days + 1, 30))
            else:
                health_days = 30
            self._sync_health_data(client, user_id, days=health_days)
        except Exception as exc:
            logger.warning("Health sync parcial user=%s: %s", user_id, exc)

        # Calcular y persistir el LabX Daily Readiness Score (4 dimensiones)
        self._update_readiness(user_id)

        # Sincronizar entrenamientos planificados desde calendario Garmin
        # (Training Peaks, TrainerRoad, etc. pushean sus planes a Garmin Connect)
        try:
            self._sync_planned_workouts(client, user_id, ftp=ftp)
        except Exception as exc:
            logger.warning("Planned workouts sync parcial user=%s: %s", user_id, exc)

        all_count = db.query(GarminActivity).filter(GarminActivity.user_id == user_id).count()
        return {"total": all_count, "new": new_count}

    # ── Mapeo de tipos de actividad Garmin → deporte interno ──────────────────
    _SPORT_MAP_PLANNED = {
        "running": "run", "trail_running": "run", "treadmill_running": "run",
        "cycling": "bike", "road_cycling": "bike", "indoor_cycling": "bike",
        "gravel_cycling": "bike", "mountain_biking": "bike",
        "swimming": "swim", "lap_swimming": "swim", "open_water_swimming": "swim",
        "strength_training": "strength", "gym_and_fitness_equipment": "strength",
        "triathlon": "run",  # multi-sport: treat as run (most common single-metric)
        "other": "other",
    }

    @staticmethod
    def _estimate_planned_tss(workout, sport, ftp, fcmax, run_pace_s_km, css_s_100m):
        """
        TSS planificado no viene de Garmin (cálculo propietario de
        TrainingPeaks que no se transmite al empujar el workout a Garmin
        Connect). Se estima con la misma lógica que ya usa LabX para
        actividades reales: IF² × horas × 100.

        Diseñado para una plataforma multi-cliente/multi-plataforma
        (no solo un usuario ni un solo origen de plan) en DOS niveles:

        Nivel 1 — targets numéricos por paso (potencia/FC/ritmo), cuando
        la plataforma de origen los puebla (targetValueOne/Two).

        Nivel 2 — fallback por PROMEDIO de toda la sesión (distancia
        total ÷ duración total, campos estándar de Garmin siempre
        presentes cuando hay distancia real, sin importar la
        plataforma) contra el benchmark real del atleta (CSS para nado,
        ritmo umbral para carrera). Necesario porque, en la práctica,
        algunas plataformas (confirmado con TrainingPeaks) empujan el
        target del paso como TEXTO LIBRE en la descripción
        ("Pace 1:31-2:08/100 yards") en vez de valores numéricos —
        parsear texto libre por plataforma/idioma/unidad no escala para
        un producto internacional con múltiples orígenes de plan.

        Si ninguno de los dos niveles tiene información real suficiente
        (ni targets por paso, ni distancia+duración+benchmark), devuelve
        None — nunca inventa un número sin base real.
        """
        segments = workout.get("workoutSegments") or []
        total = 0.0
        any_computed = False
        for seg in segments:
            for step in (seg.get("workoutSteps") or []):
                if step.get("type") != "ExecutableStepDTO":
                    continue
                end_cond = (step.get("endCondition") or {}).get("conditionTypeKey")
                dur_s = step.get("endConditionValue") if end_cond == "time" else None
                if not dur_s:
                    continue
                v1, v2 = step.get("targetValueOne"), step.get("targetValueTwo")
                if v1 is None and v2 is None:
                    continue
                avg_target = (v1 + v2) / 2 if (v1 is not None and v2 is not None) else (v1 or v2)
                target_key = (step.get("targetType") or {}).get("workoutTargetTypeKey") or ""

                intensity = None
                if "power" in target_key and ftp:
                    intensity = avg_target / ftp
                elif "heart.rate" in target_key and fcmax:
                    intensity = avg_target / (fcmax * 0.92)
                elif "pace" in target_key and avg_target:
                    # avg_target viene en m/s en ambos deportes
                    if sport == "run" and run_pace_s_km:
                        step_pace_s_km = 1000 / avg_target
                        intensity = run_pace_s_km / step_pace_s_km
                    elif sport == "swim" and css_s_100m:
                        step_pace_s_100m = 100 / avg_target
                        intensity = css_s_100m / step_pace_s_100m
                if intensity is None:
                    continue

                intensity = max(0.3, min(1.3, intensity))
                total += (dur_s / 3600) * (intensity ** 2) * 100
                any_computed = True

        if any_computed:
            return round(total, 1)

        # Nivel 2: promedio de toda la sesión
        dur_secs = workout.get("estimatedDurationInSecs")
        dist_m   = workout.get("estimatedDistanceInMeters")
        if not dur_secs or not dist_m:
            return None
        avg_speed_ms = dist_m / dur_secs
        intensity = None
        if sport == "run" and run_pace_s_km and avg_speed_ms:
            avg_pace_s_km = 1000 / avg_speed_ms
            intensity = run_pace_s_km / avg_pace_s_km
        elif sport == "swim" and css_s_100m and avg_speed_ms:
            avg_pace_s_100m = 100 / avg_speed_ms
            intensity = css_s_100m / avg_pace_s_100m
        if intensity is None:
            return None
        intensity = max(0.3, min(1.3, intensity))
        return round((dur_secs / 3600) * (intensity ** 2) * 100, 1)

    def _sync_planned_workouts(self, client, user_id: str, months_ahead: int = 2, ftp: int = 250) -> None:
        """
        Descarga del calendario Garmin los entrenamientos planificados
        (Training Peaks, TrainerRoad, Garmin Coach, etc.) y los guarda en
        garmin_planned_workouts. Cubre el mes actual + meses_ahead hacia adelante
        y el mes anterior (para ver la semana completa si es inicio de mes).
        """
        import json as _json
        from datetime import date
        db   = self._db
        today = date.today()

        _user_row = db.query(User).filter(User.id == user_id).first()
        _fcmax = _user_row.fcmax if _user_row else None

        def _parse_mmss(val):
            """'M:SS' → segundos. Formato compartido por run_pace y css
            en el perfil del atleta (por 1km o por 100m respectivamente)."""
            if not val:
                return None
            try:
                _m, _s = val.split(":")
                return int(_m) * 60 + int(_s)
            except Exception:
                return None

        _run_pace_s_km  = _parse_mmss(_user_row.run_pace if _user_row else None)
        _css_s_100m     = _parse_mmss(_user_row.css      if _user_row else None)

        # Caché de workout_id → (dur_min, dist_km, sport) resuelto via
        # get_workout_by_id(), para no pedirle a Garmin la misma plantilla
        # dos veces (ni dentro de esta corrida, ni en la próxima sync si ya
        # quedó guardado en algún registro previo del usuario).
        _workout_cache: dict[str, dict] = {}
        _existing_resolved = (
            db.query(GarminPlannedWorkout)
              .filter(GarminPlannedWorkout.user_id == user_id,
                      GarminPlannedWorkout.workout_id.isnot(None),
                      GarminPlannedWorkout.dur_min.isnot(None),
                      GarminPlannedWorkout.tss_planned.isnot(None))
              .all()
        )
        for r in _existing_resolved:
            _workout_cache[r.workout_id] = {"dur_min": r.dur_min, "dist_km": r.dist_km, "tss_est": r.tss_planned}

        months_to_fetch = []
        # Mes anterior (para semanas que cruzan fin de mes)
        prev = (today.replace(day=1) - timedelta(days=1))
        months_to_fetch.append((prev.year, prev.month))
        # Mes actual + meses_ahead
        for delta in range(months_ahead + 1):
            m = today.month + delta
            y = today.year + (m - 1) // 12
            m = ((m - 1) % 12) + 1
            months_to_fetch.append((y, m))

        # IMPORTANTE (descubierto 2026-07-11): Garmin deja de devolver un
        # workout planificado en el calendario una vez que el atleta lo
        # ejecuta EN SU FECHA EXACTA — la entrada "workout" desaparece y
        # solo queda la actividad ejecutada. Si acá borráramos todo lo
        # planificado del usuario antes de reinsertar (como se hacía
        # antes), cada sync destruiría la única oportunidad de haber
        # capturado ese plan antes de que Garmin lo "consuma" — el
        # histórico de plan de la semana se iría perdiendo entrenamiento
        # a entrenamiento a medida que se ejecutan.
        #
        # Por eso ahora es upsert por (user_id, garmin_scheduled_id):
        # se actualiza lo que ya existe, se inserta lo nuevo, y NUNCA se
        # borra lo que Garmin ya no devuelve — eso simplemente significa
        # que ya se ejecutó, no que el plan nunca existió.
        _existing_by_sched_id = {
            r.garmin_scheduled_id: r
            for r in db.query(GarminPlannedWorkout)
                       .filter(GarminPlannedWorkout.user_id == user_id,
                               GarminPlannedWorkout.garmin_scheduled_id.isnot(None))
                       .all()
        }

        inserted = 0
        updated = 0
        seen_sched_ids = set()  # Garmin repite ítems entre meses (relleno de grilla de calendario)
        for (yr, mo) in months_to_fetch:
            try:
                data = _retry(
                    lambda y=yr, m=mo: client.get_scheduled_workouts(y, m),
                    max_attempts=2, base_delay=1.5
                )
            except Exception as exc:
                logger.debug("Scheduled workouts %d-%02d user=%s: %s", yr, mo, user_id, exc)
                continue

            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                # Puede venir como {"calendarItems": [...]} u otras estructuras.
                # Antes: "a or b or list(d.values())[0] if d else []" — el ternario
                # se evalúa DESPUÉS del último "or" por precedencia de Python, y
                # list(d.values())[0] puede ser cualquier tipo (ej. un int en
                # {"totalCount": 5, ...}), rompiendo el "for item in items" de abajo.
                candidate = data.get("calendarItems") or data.get("workouts")
                if candidate is None and data:
                    first_val = next(iter(data.values()), None)
                    candidate = first_val if isinstance(first_val, list) else None
                items = candidate if isinstance(candidate, list) else []

            for item in items:
                if not isinstance(item, dict):
                    continue

                # Filtrar: solo workouts planificados (type='workout' o 'scheduledWorkout')
                item_type = (item.get("itemType") or item.get("type") or "").lower()
                if item_type not in ("workout", "scheduledworkout", "scheduled_workout", ""):
                    # Skip activities already completed and other calendar types
                    if item_type in ("activity", "note", "event", "race"):
                        continue

                date_str = item.get("date") or item.get("scheduledDate") or item.get("startLocal", "")[:10]
                if not date_str or len(date_str) < 10:
                    continue
                date_str = date_str[:10]

                # ID único en Garmin
                sched_id = str(item.get("scheduledWorkoutId") or item.get("id") or "")
                if sched_id and sched_id in seen_sched_ids:
                    continue
                if sched_id:
                    seen_sched_ids.add(sched_id)

                title = (item.get("title") or item.get("workoutName") or
                         item.get("name") or "Entrenamiento planificado")

                # Deporte — el campo real en las entradas de calendario es
                # "sportTypeKey" plano (ej. "cycling"), NO "activityType.typeKey"
                # (ese campo no existe en la respuesta real de Garmin y siempre
                # caía a "other", sin importar la plataforma de origen).
                type_key = item.get("sportTypeKey") or ""
                if not type_key:
                    act_type = item.get("activityType") or {}
                    type_key = act_type.get("typeKey") or act_type.get("key") or "" if isinstance(act_type, dict) else str(act_type)
                sport = self._SPORT_MAP_PLANNED.get(type_key.lower(), "other")

                # Duración y distancia — el calendario casi nunca las trae
                # directo (son null); la plantilla completa vive en
                # get_workout_by_id(workoutId), sin importar qué plataforma
                # (TrainingPeaks, TrainerRoad, Garmin Coach, LabX) la haya
                # empujado a Garmin — todas terminan en la misma API.
                dur_secs = (item.get("duration") or item.get("estimatedDurationInSecs") or
                            item.get("durationInSeconds") or 0)
                dist_m  = (item.get("distance") or item.get("estimatedDistanceInMeters") or
                           item.get("distanceInMeters") or 0)

                # TSS planificado — Garmin NO lo trae (ver _estimate_planned_tss);
                # solo lo tendríamos si el calendario lo incluyera explícito
                # (no observado en la práctica, pero se deja el check por si
                # alguna plataforma lo llega a exponer).
                tss_p = (item.get("tssPlanned") or item.get("tss") or
                         item.get("trainingStressScore") or None)

                workout_id = str(item.get("workoutId") or "") or None
                if workout_id and (not dur_secs or not dist_m or tss_p is None):
                    if workout_id in _workout_cache:
                        cached = _workout_cache[workout_id]
                        dur_secs = dur_secs or (cached["dur_min"]*60 if cached["dur_min"] else 0)
                        dist_m   = dist_m   or (cached["dist_km"]*1000 if cached["dist_km"] else 0)
                        if tss_p is None: tss_p = cached.get("tss_est")
                    else:
                        try:
                            wk = _retry(lambda w=workout_id: client.get_workout_by_id(w),
                                        max_attempts=2, base_delay=1.0)
                            wk_dur  = (wk or {}).get("estimatedDurationInSecs") or 0
                            wk_dist = (wk or {}).get("estimatedDistanceInMeters") or 0
                            wk_tss  = self._estimate_planned_tss(
                                wk or {}, sport, ftp, _fcmax, _run_pace_s_km, _css_s_100m)
                            dur_secs = dur_secs or wk_dur
                            dist_m   = dist_m or wk_dist
                            if tss_p is None: tss_p = wk_tss
                            _workout_cache[workout_id] = {
                                "dur_min": round(wk_dur/60, 1) if wk_dur else None,
                                "dist_km": round(wk_dist/1000, 2) if wk_dist else None,
                                "tss_est": wk_tss,
                            }
                        except Exception as exc:
                            logger.debug("get_workout_by_id %s user=%s: %s", workout_id, user_id, exc)
                            _workout_cache[workout_id] = {"dur_min": None, "dist_km": None, "tss_est": None}

                dur_min = round(dur_secs / 60, 1) if dur_secs else None
                dist_km = round(dist_m / 1000, 2) if dist_m else None

                # Fuente: Training Peaks se identifica por el workoutSourceId
                source_id  = str(item.get("workoutSourceId") or item.get("source") or "")
                source_lbl = "trainingpeaks" if "trainingpeaks" in source_id.lower() else \
                             "garmin"        if source_id else "garmin"

                existing_row = _existing_by_sched_id.get(sched_id) if sched_id else None
                if existing_row:
                    existing_row.date_iso    = date_str
                    existing_row.workout_id  = workout_id
                    existing_row.title       = title[:200]
                    existing_row.sport       = sport
                    existing_row.dur_min     = dur_min
                    existing_row.dist_km     = dist_km
                    existing_row.tss_planned = float(tss_p) if tss_p is not None else existing_row.tss_planned
                    existing_row.source      = source_lbl
                    existing_row.raw_json    = _json.dumps(item, ensure_ascii=False)[:4000]
                    updated += 1
                else:
                    import uuid as _uuid_mod2
                    db.add(GarminPlannedWorkout(
                        id                  = str(_uuid_mod2.uuid4()),
                        user_id             = user_id,
                        date_iso            = date_str,
                        garmin_scheduled_id = sched_id or None,
                        workout_id          = workout_id,
                        title               = title[:200],
                        sport               = sport,
                        dur_min             = dur_min,
                        dist_km             = dist_km,
                        tss_planned         = float(tss_p) if tss_p is not None else None,
                        source              = source_lbl,
                        raw_json            = _json.dumps(item, ensure_ascii=False)[:4000],
                    ))
                    inserted += 1

        db.commit()
        logger.info("Planned workouts user=%s: %d insertados, %d actualizados (%s meses)",
                    user_id, inserted, updated, len(months_to_fetch))

    def _rebuild_training_load(self, user_id: str, ftp: int) -> None:
        db = self._db
        acts = (
            db.query(GarminActivity)
              .filter(GarminActivity.user_id == user_id)
              .order_by(GarminActivity.date_iso)
              .all()
        )
        act_dicts = [
            {"date_iso": a.date_iso, "tss": a.tss or 0}
            for a in acts
        ]
        load_rows = _compute_training_load(act_dicts)

        # Calcular ACWR, monotonía y strain sobre el historial completo
        load_rows = _enrich_load_with_acwr(load_rows)

        # Borrar y reinsertar (más simple que upsert para CTL)
        db.query(GarminTrainingLoad).filter(GarminTrainingLoad.user_id == user_id).delete()
        db.bulk_insert_mappings(GarminTrainingLoad, [
            {
                "user_id":  user_id,
                "date_iso": r["date_iso"],
                "ctl":      r["ctl"],
                "atl":      r["atl"],
                "tsb":      r["tsb"],
                "tss":      r["tss"],
                "acwr":     r.get("acwr"),
                "monotony": r.get("monotony"),
                "strain":   r.get("strain"),
            }
            for r in load_rows
        ])
        db.commit()

    def _update_readiness(self, user_id: str) -> None:
        """
        Calcula el LabX Daily Readiness Score (4 dimensiones: recuperación,
        estado mental, TRS de blood labs, forma/TSB) con el motor real de
        readiness_service y lo persiste en garmin_health_daily del día de
        hoy. Reemplaza el placeholder "50+TSB" que usaba el dashboard.
        """
        from .services.readiness_service import compute_daily_readiness_for_user

        db = self._db
        today_iso = date.today().isoformat()
        try:
            report = compute_daily_readiness_for_user(user_id, db)

            row = (
                db.query(GarminHealthDaily)
                  .filter(GarminHealthDaily.user_id == user_id,
                          GarminHealthDaily.date_iso == today_iso)
                  .first()
            )
            if row is None:
                row = GarminHealthDaily(user_id=user_id, date_iso=today_iso)
                db.add(row)

            row.labx_readiness_score = report.drs
            row.labx_readiness_factors = json.dumps({
                "label": report.drs_label,
                "primary_limiter": report.primary_limiter,
                "data_completeness": report.data_completeness,
                "computed_from": report.computed_from,
                "dimensions": [
                    {
                        "name": d.name,
                        "score": round(d.score) if d.score is not None else None,
                        "available": d.available,
                    }
                    for d in report.dimensions
                ],
            })
            db.commit()
        except Exception:
            logger.exception("Readiness update fallo user=%s", user_id)
            db.rollback()

    def _sync_health_data(self, client, user_id: str, days: int = 30) -> None:
        """
        Sincroniza datos de salud de los últimos `days` días desde Garmin:
        - HRV, Body Battery, sleep, stress, SpO2, Training Readiness.
        Realiza upsert en garmin_health_daily y garmin_sleep_sessions.
        Errores no fatales: se registran como warnings y se continúa.
        """
        import json as _json
        db = self._db
        today = date.today()

        # VO2max — histórico real por día (no solo el valor de hoy).
        # Garmin solo recalcula el VO2max en días puntuales (tras actividades
        # que califican), así que la mayoría de días da vacío — se guarda
        # cada valor real bajo SU fecha real para armar un histórico
        # genuino, en vez de aplastarlo todo contra "hoy".
        # Incremental: solo se pide desde el último día ya guardado en
        # adelante (o backfill acotado la primera vez) para no golpear
        # Garmin con decenas de requests en cada sync.
        last_vo2_row = (
            db.query(GarminHealthDaily)
              .filter(GarminHealthDaily.user_id == user_id,
                      (GarminHealthDaily.vo2max_running.isnot(None)) |
                      (GarminHealthDaily.vo2max_cycling.isnot(None)))
              .order_by(GarminHealthDaily.date_iso.desc())
              .first()
        )
        if last_vo2_row:
            vo2_start = date.fromisoformat(last_vo2_row.date_iso)
            vo2_days_back = min(365, max(1, (today - vo2_start).days))
        else:
            vo2_days_back = 365  # backfill inicial de 1 año (una sola vez;
                                  # después queda incremental desde el día
                                  # más reciente ya guardado)

        import time as _time
        consecutive_failures = 0
        for i, back in enumerate(range(vo2_days_back + 1)):
            d = today - timedelta(days=back)
            d_iso = d.isoformat()
            try:
                mm = _retry(lambda dd=d_iso: client.get_max_metrics(dd), max_attempts=2, base_delay=1.0)
                consecutive_failures = 0
                entry = None
                if mm and isinstance(mm, list) and mm:
                    entry = mm[0]
                elif isinstance(mm, dict) and mm:
                    entry = mm
                if not entry:
                    continue
                generic = entry.get("generic") or {}
                cycling = entry.get("cycling") or {}
                # "generic" (running/general) es lo que Garmin Connect
                # muestra como "VO2 Max" en el reloj/app.
                run_val = generic.get("vo2MaxPreciseValue") or generic.get("vo2MaxValue")
                cyc_val = cycling.get("vo2MaxValue")
                if not run_val and not cyc_val:
                    continue

                row = db.query(GarminHealthDaily).filter(
                    GarminHealthDaily.user_id == user_id,
                    GarminHealthDaily.date_iso == d_iso,
                ).first()
                if row:
                    if run_val: row.vo2max_running = run_val
                    if cyc_val: row.vo2max_cycling = cyc_val
                elif run_val or cyc_val:
                    db.add(GarminHealthDaily(
                        user_id=user_id, date_iso=d_iso,
                        vo2max_running=run_val, vo2max_cycling=cyc_val,
                        synced_at=datetime.now(timezone.utc).replace(tzinfo=None),
                    ))
            except Exception as exc:
                consecutive_failures += 1
                logger.debug("VO2max skip %s user=%s: %s", d_iso, user_id, exc)
                if consecutive_failures >= 8:
                    logger.warning(
                        "VO2max backfill cortado user=%s tras %d fallos seguidos "
                        "(quedó en %s) — sigue la próxima sync",
                        user_id, consecutive_failures, d_iso)
                    break

            if i % 20 == 19:
                db.flush()  # progreso persistido por si el resto falla/tarda mucho
            _time.sleep(0.2)  # evitar ráfaga que dispare rate-limit de Garmin
        db.flush()

        for delta in range(days):
            target = today - timedelta(days=delta)
            iso    = target.isoformat()

            # ── Body Battery ──────────────────────────────────────────────
            # Garmin no devuelve un nivel plano por entrada: cada item trae
            # un array de puntos [timestampMs, nivel] bajo
            # "bodyBatteryValuesArray" que hay que desanidar.
            bb_min = bb_max = bb_end = None
            try:
                bb_data = _retry(lambda d=iso: client.get_body_battery(d), max_attempts=2, base_delay=1.0)
                if bb_data and isinstance(bb_data, list):
                    points = []
                    for e in bb_data:
                        for pt in (e.get("bodyBatteryValuesArray") or []):
                            if isinstance(pt, (list, tuple)) and len(pt) >= 2 and pt[1] is not None:
                                points.append((pt[0], pt[1]))
                    if points:
                        points.sort(key=lambda p: p[0])
                        levels = [p[1] for p in points]
                        bb_min, bb_max, bb_end = min(levels), max(levels), levels[-1]
            except Exception as exc:
                logger.warning("BodyBattery skip %s user=%s: %s", iso, user_id, exc)

            # ── HRV ──────────────────────────────────────────────────────
            hrv_weekly = hrv_night = hrv_low = hrv_high = None
            hrv_status_str = None
            try:
                hrv_data = _retry(lambda d=iso: client.get_hrv_data(d), max_attempts=2, base_delay=1.0)
                if hrv_data and isinstance(hrv_data, dict):
                    summary = hrv_data.get("hrvSummary", {}) or {}
                    baseline = summary.get("baseline") or {}
                    hrv_weekly = _safe_float(summary.get("weeklyAvg")) or None
                    hrv_night  = _safe_float(summary.get("lastNightAvg")) or None
                    hrv_low    = _safe_float(baseline.get("balancedLow")) or None
                    hrv_high   = _safe_float(baseline.get("balancedUpper")) or None
                    hrv_status_str = summary.get("status")
            except Exception as exc:
                logger.warning("HRV skip %s user=%s: %s", iso, user_id, exc)

            # ── Stress ───────────────────────────────────────────────────
            stress_avg = rest_pct = None
            try:
                st_data = _retry(lambda d=iso: client.get_stress_data(d), max_attempts=2, base_delay=1.0)
                if st_data and isinstance(st_data, dict):
                    stress_avg = _safe_int(st_data.get("avgStressLevel")) or None
                    rest_sec   = _safe_float(st_data.get("restStressDuration", 0))
                    tot_sec    = _safe_float(st_data.get("totalDuration", 0))
                    if tot_sec > 0:
                        rest_pct = round(rest_sec / tot_sec * 100, 1)
            except Exception as exc:
                logger.debug("Stress skip %s user=%s: %s", iso, user_id, exc)

            # ── SpO2 / Respiration / Resting HR ──────────────────────────
            spo2_avg = spo2_min = resp_avg = resting_hr = None
            try:
                spo2_data = _retry(lambda d=iso: client.get_spo2_data(d), max_attempts=2, base_delay=1.0)
                if spo2_data and isinstance(spo2_data, dict):
                    spo2_avg = _safe_float(spo2_data.get("averageSpO2")) or None
                    spo2_min = _safe_float(spo2_data.get("lowestSpO2")) or None
            except Exception as exc:
                logger.warning("SpO2 skip %s user=%s: %s", iso, user_id, exc)

            try:
                resp_data = _retry(lambda d=iso: client.get_respiration_data(d), max_attempts=2, base_delay=1.0)
                if resp_data and isinstance(resp_data, dict):
                    resp_avg = _safe_float(resp_data.get("avgWakingRespirationValue")) or None
            except Exception as exc:
                logger.debug("Respiration skip %s user=%s: %s", iso, user_id, exc)

            try:
                rhr_data = _retry(lambda d=iso: client.get_rhr_day(d), max_attempts=2, base_delay=1.0)
                if rhr_data and isinstance(rhr_data, dict):
                    vals_list = rhr_data.get("allMetrics", {}).get("metricsMap", {}).get("WELLNESS_RESTING_HEART_RATE", [])
                    if vals_list:
                        resting_hr = _safe_int(vals_list[0].get("value")) or None
            except Exception as exc:
                logger.warning("RHR skip %s user=%s: %s", iso, user_id, exc)

            # ── Training Readiness ────────────────────────────────────────
            readiness = recovery_h = None
            try:
                tr_data = _retry(lambda d=iso: client.get_training_readiness(d), max_attempts=2, base_delay=1.0)
                if tr_data and isinstance(tr_data, list) and tr_data:
                    entry = tr_data[0]
                    readiness  = _safe_int(entry.get("score")) or None
                    recovery_h = _safe_int(entry.get("recoveryTime")) or None
            except Exception as exc:
                logger.debug("TrainingReadiness skip %s user=%s: %s", iso, user_id, exc)

            # ── Upsert garmin_health_daily ────────────────────────────────
            # (VO2max se sincroniza aparte, más arriba, con su propio
            # backfill incremental por fecha real — no depende de este loop)
            has_data = any(v is not None for v in [
                bb_end, hrv_night, stress_avg, spo2_avg, readiness,
            ])
            if not has_data:
                continue

            existing = db.query(GarminHealthDaily).filter(
                GarminHealthDaily.user_id  == user_id,
                GarminHealthDaily.date_iso == iso,
            ).first()

            if existing:
                if bb_min      is not None: existing.body_battery_min  = bb_min
                if bb_max      is not None: existing.body_battery_max  = bb_max
                if bb_end      is not None: existing.body_battery_end  = bb_end
                if hrv_weekly  is not None: existing.hrv_weekly_avg    = hrv_weekly
                if hrv_night   is not None: existing.hrv_last_night    = hrv_night
                if hrv_low     is not None: existing.hrv_baseline_low  = hrv_low
                if hrv_high    is not None: existing.hrv_baseline_high = hrv_high
                if hrv_status_str:          existing.hrv_status        = hrv_status_str
                if stress_avg  is not None: existing.avg_stress        = stress_avg
                if rest_pct    is not None: existing.rest_stress_pct   = rest_pct
                if resp_avg    is not None: existing.avg_respiration   = resp_avg
                if spo2_avg    is not None: existing.avg_spo2          = spo2_avg
                if spo2_min    is not None: existing.min_spo2          = spo2_min
                if resting_hr  is not None: existing.resting_hr        = resting_hr
                if readiness   is not None: existing.training_readiness = readiness
                if recovery_h  is not None: existing.recovery_time_h   = recovery_h
                existing.synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                db.add(GarminHealthDaily(
                    user_id           = user_id,
                    date_iso          = iso,
                    body_battery_min  = bb_min,
                    body_battery_max  = bb_max,
                    body_battery_end  = bb_end,
                    hrv_weekly_avg    = hrv_weekly,
                    hrv_last_night    = hrv_night,
                    hrv_baseline_low  = hrv_low,
                    hrv_baseline_high = hrv_high,
                    hrv_status        = hrv_status_str,
                    avg_stress        = stress_avg,
                    rest_stress_pct   = rest_pct,
                    avg_respiration   = resp_avg,
                    avg_spo2          = spo2_avg,
                    min_spo2          = spo2_min,
                    resting_hr        = resting_hr,
                    training_readiness= readiness,
                    recovery_time_h   = recovery_h,
                    synced_at         = datetime.now(timezone.utc).replace(tzinfo=None),
                ))

            # ── Sleep ─────────────────────────────────────────────────────
            try:
                sl_data = _retry(lambda d=iso: client.get_sleep_data(d), max_attempts=2, base_delay=1.0)
                if sl_data and isinstance(sl_data, dict):
                    daily = sl_data.get("dailySleepDTO", {}) or {}
                    phases = sl_data.get("sleepLevels", []) or []

                    total_min = _safe_int(daily.get("sleepTimeSeconds", 0)) // 60 or None
                    deep_min  = _safe_int(daily.get("deepSleepSeconds",  0)) // 60 or None
                    light_min = _safe_int(daily.get("lightSleepSeconds", 0)) // 60 or None
                    rem_min   = _safe_int(daily.get("remSleepSeconds",   0)) // 60 or None
                    awake_min = _safe_int(daily.get("awakeSleepSeconds", 0)) // 60 or None
                    score     = _safe_int(daily.get("sleepScores", {}).get("overall", {}).get("value", 0)) or None
                    qual_map  = {90: "excellent", 75: "good", 50: "fair"}
                    qual      = next((q for t, q in sorted(qual_map.items(), reverse=True) if score and score >= t), "poor") if score else None
                    spo2_night = _safe_float(daily.get("averageSpO2Value")) or None
                    resp_night = _safe_float(daily.get("averageRespirationValue")) or None
                    hrv_night_sleep = _safe_float(daily.get("hrvValue")) or None

                    sleep_start_raw = daily.get("sleepStartTimestampGMT")
                    sleep_end_raw   = daily.get("sleepEndTimestampGMT")
                    sleep_start_dt  = datetime.utcfromtimestamp(sleep_start_raw / 1000) if sleep_start_raw else None
                    sleep_end_dt    = datetime.utcfromtimestamp(sleep_end_raw   / 1000) if sleep_end_raw   else None

                    sl_existing = db.query(GarminSleepSession).filter(
                        GarminSleepSession.user_id  == user_id,
                        GarminSleepSession.date_iso == iso,
                    ).first()

                    raw_json = _json.dumps(phases[:50]) if phases else None  # cap para no inflar la DB

                    if sl_existing:
                        sl_existing.total_min             = total_min
                        sl_existing.deep_min              = deep_min
                        sl_existing.light_min             = light_min
                        sl_existing.rem_min               = rem_min
                        sl_existing.awake_min             = awake_min
                        sl_existing.sleep_score           = score
                        sl_existing.sleep_score_qual      = qual
                        sl_existing.avg_spo2_night        = spo2_night
                        sl_existing.avg_respiration_night = resp_night
                        sl_existing.hrv_rmssd_night       = hrv_night_sleep
                        sl_existing.sleep_start           = sleep_start_dt
                        sl_existing.sleep_end             = sleep_end_dt
                        sl_existing.raw_stages_json       = raw_json
                        sl_existing.synced_at             = datetime.now(timezone.utc).replace(tzinfo=None)
                    else:
                        db.add(GarminSleepSession(
                            user_id               = user_id,
                            date_iso              = iso,
                            sleep_start           = sleep_start_dt,
                            sleep_end             = sleep_end_dt,
                            total_min             = total_min,
                            deep_min              = deep_min,
                            light_min             = light_min,
                            rem_min               = rem_min,
                            awake_min             = awake_min,
                            sleep_score           = score,
                            sleep_score_qual      = qual,
                            avg_spo2_night        = spo2_night,
                            avg_respiration_night = resp_night,
                            hrv_rmssd_night       = hrv_night_sleep,
                            raw_stages_json       = raw_json,
                            synced_at             = datetime.now(timezone.utc).replace(tzinfo=None),
                        ))
            except Exception as exc:
                logger.warning("Sleep skip %s user=%s: %s", iso, user_id, exc)

        try:
            db.commit()
            logger.info("Health sync ok user=%s days=%d", user_id, days)
        except Exception as exc:
            db.rollback()
            logger.error("Health sync commit error user=%s: %s", user_id, exc)

    def _set_status(
        self,
        user_id: str,
        status: str,
        row: GarminSyncStatus | None,
        activities_total: int = 0,
        error: str | None = None,
    ) -> None:
        db = self._db
        if not row:
            row = db.query(GarminSyncStatus).filter(
                GarminSyncStatus.user_id == user_id
            ).first()

        if row:
            row.status            = status
            row.error             = error
            row.activities_total  = activities_total or row.activities_total
            if status in ("ok", "error"):
                row.last_sync_at = datetime.now(timezone.utc).replace(tzinfo=None)
        else:
            db.add(GarminSyncStatus(
                user_id          = user_id,
                status           = status,
                last_sync_at     = datetime.now(timezone.utc).replace(tzinfo=None) if status in ("ok","error") else None,
                activities_total = activities_total,
                error            = error,
            ))
        try:
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("garmin_sync_status commit falló user=%s status=%s, reintentando: %s", user_id, status, exc)
            import time as _time
            _time.sleep(0.5)
            try:
                db.commit()
            except Exception as exc2:
                db.rollback()
                logger.error("garmin_sync_status commit falló definitivamente user=%s status=%s: %s", user_id, status, exc2)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point para BackgroundTasks (función libre, sin estado)
# ─────────────────────────────────────────────────────────────────────────────

def background_sync_user(user_id: str, force: bool = False) -> None:
    """
    Crear una sesión DB propia — BackgroundTasks corre fuera del request context.
    BP-05: Invalida cache del dashboard tras sync exitoso.
    """
    db = SessionLocal()
    try:
        result = GarminPullService(db).sync_user(user_id, force=force)
        # BP-05: invalidar cache dashboard para que el próximo GET refleje datos frescos
        try:
            from .redis_client import cache_invalidate_prefix
            cache_invalidate_prefix(f"dashboard:{user_id}")
            logger.info("Cache dashboard invalidado post-sync user_id=%s", user_id)
        except Exception:
            pass
        return result
    finally:
        db.close()

    # Refrescar contexto IA tras sync exitoso
    if result and result.get("ok"):
        try:
            from .database import SessionLocal as _SL
            _db2 = _SL()
            try:
                from .services.context_engine import refresh_athlete_context
                refresh_athlete_context(user_id, _db2)
            finally:
                _db2.close()
        except Exception as _ce:
            logger.warning("Context refresh post-sync error user=%s: %s", user_id, _ce)


def dispatch_garmin_sync(user_id: str, background_tasks=None, force: bool = False) -> str:
    """Dispatch garmin sync — Celery when broker available, BackgroundTask otherwise.

    Returns "celery" | "background" | "skipped" to indicate dispatch method.
    """
    from .redis_client import is_available as _redis_ok
    if _redis_ok():
        try:
            from .tasks.garmin_tasks import sync_garmin_user
            kw = {} if not force else {}  # force not yet in Celery task signature
            sync_garmin_user.delay(user_id)
            logger.info("Garmin sync dispatched via Celery user_id=%s", user_id)
            return "celery"
        except Exception as e:
            logger.warning("Celery dispatch failed (%s), falling back to BackgroundTask", e)
    if background_tasks is not None:
        background_tasks.add_task(background_sync_user, user_id, force)
        logger.info("Garmin sync dispatched via BackgroundTask user_id=%s", user_id)
        return "background"
    logger.warning("Garmin sync skipped — no broker and no background_tasks user_id=%s", user_id)
    return "skipped"
