"""
Sync de LECTURA desde intervals.icu: actividades -> garmin_activities y
wellness -> garmin_health_daily / garmin_sleep_sessions.

Reglas:
  - Solo corre si el scope guardado del usuario incluye ACTIVITY:READ; si no,
    {"status": "needs_reconnect"} sin llamar a la API.
  - Actividades: activity_id = "intervals:<id>". Dedupe estilo
    provider_sync_service._upsert: si ya hay una fila del mismo usuario+fecha+deporte
    con OTRO prefijo (o sin prefijo, p. ej. Garmin) NO se crea duplicado ("merged").
    Solo se refresca la fila si es tambien de intervals.
  - Origen Garmin: si intervals informa source=GARMIN* y un external_id, se usa como
    clave de dedupe ADICIONAL (external_id == activity_id Garmin existente del usuario).
    Es solo una pista extra; el criterio base sigue siendo usuario+fecha+deporte porque
    external_id no siempre viene ni siempre es el id de Garmin Connect.
  - Dedupe fina (Sprint 2): la pista por external_id de Garmin sigue teniendo prioridad
    (si coincide -> "merged"). Si no, se miran TODAS las filas de otro origen del mismo
    usuario+fecha+deporte: la actividad de intervals es una sesion DISTINTA (se IMPORTA)
    solo si TODAS difieren claramente, es decir |dur_min_existente - dur_intervals| > 10 min.
    Si alguna coincide en duracion (<= 10 min), o falta el dato de duracion en cualquiera
    de los dos lados, es "merged". Criterio de hora de inicio (> 30 min): se aplica solo
    cuando ambos lados tienen hora; GarminActivity NO persiste hora de inicio, por lo que
    hoy no se puede evaluar contra filas existentes y la duracion es el unico criterio activo.
  - Peso: wellness.weight (kg) -> weight_logs (GarminHealthDaily no tiene columna de peso).
    Solo se crea la fila si no hay ninguna para ese usuario+fecha (source="intervals");
    jamas se modifica una existente. Valores <= 0 se ignoran.
  - Backfill (backfill_intervals_user): ventanas de 90 dias hacia atras, commit por ventana.
  - Wellness: REGLA DURA, nunca se pisa un valor no vacio con uno vacio; lo de
    intervals solo completa huecos o crea la fila.
  - Idempotente.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from . import intervals_connector as ic
from .activity_dedupe import mark_new_activity
from .models import GarminActivity, GarminHealthDaily, GarminSleepSession, User, WeightLog

logger = logging.getLogger("labx.intervals_sync")

PREFIX = "intervals:"
_MO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]
_ICONS = {"swim": "🏊", "bike": "🚴", "run": "🏃", "gym": "💪"}

_SPORT_MAP = {
    "ride": "bike", "virtualride": "bike", "mountainbikeride": "bike", "gravelride": "bike",
    "ebikeride": "bike", "emountainbikeride": "bike", "handcycle": "bike", "velomobile": "bike",
    "run": "run", "virtualrun": "run", "trailrun": "run",
    "swim": "swim", "openwaterswim": "swim",
    "weighttraining": "gym", "workout": "gym", "crossfit": "gym", "hiit": "gym",
}

# Campos de la actividad de intervals que SI se mapean (el resto se ignora y se cuenta).
_ACT_USED = {"id", "start_date_local", "type", "name", "moving_time", "elapsed_time", "distance",
             "average_heartrate", "icu_average_watts", "average_watts", "calories",
             "total_elevation_gain", "average_speed", "icu_training_load", "source", "external_id"}
# Campos de wellness que SI se mapean.
_WELL_USED = {"id", "restingHR", "hrv", "steps", "spO2", "respiration", "sleepSecs", "sleepScore", "weight"}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pos(v):
    n = _num(v)
    return n if n is not None and n > 0 else None


def _int_pos(v):
    n = _pos(v)
    return None if n is None else int(round(n))


def _pace(speed_mps, per: int) -> str | None:
    if not speed_mps:
        return None
    secs = per / speed_mps
    return f"{int(secs // 60)}:{int(secs % 60):02d}"


# ── Actividades ─────────────────────────────────────────────────────────────

_WINDOW_DAYS = 90
_DUR_TOL_MIN = 10
_START_TOL_MIN = 30


def _parse_start(v):
    try:
        t = str(v or "")
        return datetime.fromisoformat(t) if len(t) > 10 else None
    except ValueError:
        return None


def _same_session_clash(db: Session, user_id: str, date_iso: str, sport: str, it: dict, dur_s):
    """Fila de otro origen (mismo usuario+fecha+deporte) que es la MISMA sesion, o None."""
    rows = db.query(GarminActivity).filter(
        GarminActivity.user_id == user_id,
        GarminActivity.date_iso == date_iso,
        GarminActivity.sport == sport,
        GarminActivity.activity_id.notlike(f"{PREFIX}%"),
    ).all()
    if not rows:
        return None
    new_min = (dur_s / 60) if dur_s else None
    new_start = _parse_start(it.get("start_date_local"))
    for r in rows:
        if new_min is None or not r.dur_min:
            return r  # sin datos para distinguir -> merged
        if abs(r.dur_min - new_min) <= _DUR_TOL_MIN:
            # La duracion coincide; la hora solo desempata si ambos lados la tienen
            # (GarminActivity no la persiste, ver docstring del modulo).
            r_start = getattr(r, "start_local", None)
            if new_start and isinstance(r_start, datetime) and \
                    abs((r_start - new_start).total_seconds()) / 60 > _START_TOL_MIN:
                continue
            return r
    return None


def _upsert_activity(db: Session, user_id: str, it: dict, counters: dict) -> str:
    """-> 'imported' | 'updated' | 'merged' | 'skipped'. Sin commit."""
    from .garmin_pull_service import _SPORT_COLOR

    ext_id = it.get("id")
    start = str(it.get("start_date_local") or "")
    date_iso = start[:10]
    if ext_id is None or len(date_iso) != 10:
        return "skipped"  # p. ej. stubs de Strava ("_note") sin datos utilizables
    counters["ignored_fields"] += len(set(it) - _ACT_USED - {"_note"})

    sport = _SPORT_MAP.get(str(it.get("type") or "").lower(), "other")
    color, stroke = _SPORT_COLOR.get(sport, _SPORT_COLOR["other"])
    try:
        dt = datetime.fromisoformat(date_iso)
        date_label = f"{dt.day} {_MO[dt.month - 1]}"
    except ValueError:
        return "skipped"

    dur_s = _pos(it.get("moving_time")) or _pos(it.get("elapsed_time"))
    dist_m = _pos(it.get("distance"))
    speed = _pos(it.get("average_speed"))
    elev = _pos(it.get("total_elevation_gain"))
    fields = {
        "name": it.get("name") or sport.title(),
        "sport": sport,
        "date_iso": date_iso,
        "date_label": date_label,
        "dur_min": int(round(dur_s / 60)) if dur_s else 0,
        "dist_km": round(dist_m / 1000, 2) if dist_m else 0.0,
        "avg_hr": _int_pos(it.get("average_heartrate")),
        "avg_power": _int_pos(it.get("icu_average_watts") or it.get("average_watts")),
        "pace_str": _pace(speed, 1000) if sport == "run" else None,
        "swim_pace": _pace(speed, 100) if sport == "swim" else None,
        "calories": _int_pos(it.get("calories")),
        "elev_m": round(elev) if elev else None,
    }
    tss = _pos(it.get("icu_training_load"))
    if tss is not None:
        fields["tss"] = round(tss, 1)

    act_id = f"{PREFIX}{ext_id}"
    own = db.query(GarminActivity).filter(
        GarminActivity.user_id == user_id, GarminActivity.activity_id == act_id).first()
    if own:
        for k, v in fields.items():
            if v is not None:
                setattr(own, k, v)
        own.synced_at = _now()
        return "updated"

    # Pista Garmin por external_id: prioridad sobre el criterio fecha+deporte.
    clash = None
    if str(it.get("source") or "").upper().startswith("GARMIN") and it.get("external_id"):
        clash = db.query(GarminActivity).filter(
            GarminActivity.user_id == user_id,
            GarminActivity.activity_id == str(it["external_id"]),
        ).first()
    if clash is None:
        clash = _same_session_clash(db, user_id, date_iso, sport, it, dur_s)
    if clash is not None:
        return "merged"

    new_row = GarminActivity(
        user_id=user_id, activity_id=act_id, icon=_ICONS.get(sport, "🏅"),
        color=color, stroke=stroke, synced_at=_now(), **fields)
    db.add(new_row)
    db.flush()
    mark_new_activity(db, new_row)  # PILA 374
    return "imported"


# ── Wellness ────────────────────────────────────────────────────────────────

def _fill(row, vals: dict) -> bool:
    """Completa SOLO atributos vacios (None). Nunca pisa un valor existente."""
    changed = False
    for k, v in vals.items():
        cur = getattr(row, k)
        # HRV 0 (o negativo) es un vacio mal guardado: no debe bloquear el relleno.
        empty = cur is None or (k.startswith("hrv") and cur <= 0)
        if v is not None and empty:
            setattr(row, k, v)
            changed = True
    return changed


def _upsert_wellness(db: Session, user_id: str, it: dict, counters: dict) -> bool:
    date_iso = str(it.get("id") or "")[:10]
    if len(date_iso) != 10:
        return False
    counters["ignored_fields"] += len(set(it) - _WELL_USED)

    health = {
        "resting_hr": _int_pos(it.get("restingHR")),
        "hrv_last_night": _pos(it.get("hrv")),
        "steps": _int_pos(it.get("steps")),
        "avg_spo2": _pos(it.get("spO2")),
        "avg_respiration": _pos(it.get("respiration")),
    }
    health = {k: v for k, v in health.items() if v is not None}
    sleep_secs = _pos(it.get("sleepSecs"))
    sleep = {
        "total_min": int(round(sleep_secs / 60)) if sleep_secs else None,
        "sleep_score": _int_pos(it.get("sleepScore")),
        "hrv_rmssd_night": _pos(it.get("hrv")),
        "avg_spo2_night": _pos(it.get("spO2")),
        "avg_respiration_night": _pos(it.get("respiration")),
    }
    # El sueno solo se escribe si el payload trae datos propios de sueno.
    has_sleep = sleep["total_min"] is not None or sleep["sleep_score"] is not None
    sleep = {k: v for k, v in sleep.items() if v is not None} if has_sleep else {}
    weight = _pos(it.get("weight"))
    if not health and not sleep and weight is None:
        return False

    if health:
        row = db.query(GarminHealthDaily).filter(
            GarminHealthDaily.user_id == user_id, GarminHealthDaily.date_iso == date_iso).first()
        if row is None:
            db.add(GarminHealthDaily(user_id=user_id, date_iso=date_iso, synced_at=_now(), **health))
        elif _fill(row, health):
            row.synced_at = _now()
    if sleep:
        srow = db.query(GarminSleepSession).filter(
            GarminSleepSession.user_id == user_id, GarminSleepSession.date_iso == date_iso).first()
        if srow is None:
            db.add(GarminSleepSession(user_id=user_id, date_iso=date_iso, synced_at=_now(), **sleep))
        elif _fill(srow, sleep):
            srow.synced_at = _now()
    if weight is not None:
        exists = db.query(WeightLog.id).filter(
            WeightLog.user_id == user_id, WeightLog.date_iso == date_iso).first()
        if exists is None:  # nunca se toca una fila existente (manual o garmin)
            db.add(WeightLog(user_id=user_id, date_iso=date_iso,
                             weight_kg=round(weight, 1), source="intervals"))
    return True


# ── Orquestador ─────────────────────────────────────────────────────────────

async def _sync_window(db, user_id, user, token, oldest, newest, res, counters) -> None:
    """Actividades + wellness de [oldest, newest]. Sin commit; acumula en res/counters."""
    # Llamadas secuenciales: primero actividades, luego wellness.
    try:
        acts = await ic.fetch_activities(token, oldest.isoformat(), newest.isoformat())
    except ic.IntervalsError as exc:
        logger.warning("intervals sync actividades user=%s: %s", user_id, exc)
        acts, res["errors"] = [], res["errors"] + 1
    for it in acts:
        try:
            with db.begin_nested():  # savepoint: una fila mala no descarta las anteriores
                outcome = _upsert_activity(db, user_id, it, counters)
        except Exception as exc:  # noqa: BLE001 -- una actividad mala no frena el resto
            logger.warning("intervals actividad omitida user=%s: %s", user_id, type(exc).__name__)
            res["errors"] += 1
            continue
        res[outcome] += 1

    if not ic.has_scope(user, "WELLNESS:READ"):
        res["wellness_skipped"] = "sin_scope"  # visible: antes el wellness se omitia en silencio
    else:
        try:
            wellness = await ic.fetch_wellness(token, oldest.isoformat(), newest.isoformat())
        except ic.IntervalsError as exc:
            logger.warning("intervals sync wellness user=%s: %s", user_id, exc)
            wellness, res["errors"] = [], res["errors"] + 1
        for it in wellness:
            try:
                with db.begin_nested():
                    if _upsert_wellness(db, user_id, it, counters):
                        res["wellness_days"] += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("intervals wellness omitido user=%s: %s", user_id, type(exc).__name__)
                res["errors"] += 1


def recalc_load_after_sync(db: Session, user_id: str) -> None:
    """CARGA-AL-DIA: reconstruye garmin_training_load (idempotente, hasta hoy) tras un sync
    exitoso. Best-effort: un fallo del recalculo no rompe el sync. Sin tocar formulas."""
    try:
        from .services.training_service import recalculate_training_load
        recalculate_training_load(db, user_id)
        try:
            from .redis_client import cache_invalidate_prefix
            cache_invalidate_prefix(f"dashboard:{user_id}")
        except Exception:  # noqa: BLE001
            pass
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("recalculo de carga post-sync fallo user=%s: %s", user_id, type(exc).__name__)


async def sync_intervals_user(db: Session, user_id: str, days: int = 90) -> dict:
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.intervals_access_token:
        return {"status": "not_connected"}
    if not ic.has_scope(user, "ACTIVITY:READ"):
        return {"status": "needs_reconnect"}
    token = ic.read_access_token(user)
    if not token:
        return {"status": "not_connected"}

    days = max(1, min(int(days), 365))
    newest = _now().date()
    oldest = newest - timedelta(days=days)
    res = {"status": "ok", "imported": 0, "merged": 0, "skipped": 0, "updated": 0,
           "wellness_days": 0, "errors": 0}
    counters = {"ignored_fields": 0}

    await _sync_window(db, user_id, user, token, oldest, newest, res, counters)

    try:
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("intervals sync commit fallo user=%s: %s", user_id, type(exc).__name__)
        res["errors"] += 1
        res["status"] = "error"
    if res["status"] == "ok":
        recalc_load_after_sync(db, user_id)
    res["ignored_fields"] = counters["ignored_fields"]
    return res


async def backfill_intervals_user(db: Session, user_id: str, floor_iso: str = "2019-01-01") -> dict:
    """Historial completo: ventanas de 90 dias hacia atras desde hoy hasta floor_iso.

    Commit por ventana (un fallo deja lo ya importado y se cuenta en errors). Secuencial,
    con pausa de 0.3 s entre ventanas. Idempotente (misma logica de dedupe que el sync).
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None or not user.intervals_access_token:
        return {"status": "not_connected"}
    if not ic.has_scope(user, "ACTIVITY:READ"):
        return {"status": "needs_reconnect"}
    token = ic.read_access_token(user)
    if not token:
        return {"status": "not_connected"}

    floor = datetime.fromisoformat(floor_iso).date()
    newest = _now().date()
    res = {"status": "ok", "windows": 0, "imported": 0, "merged": 0, "skipped": 0,
           "updated": 0, "wellness_days": 0, "errors": 0}
    counters = {"ignored_fields": 0}
    first = True
    while newest >= floor:
        oldest = max(floor, newest - timedelta(days=_WINDOW_DAYS))
        if not first:
            await asyncio.sleep(0.3)
        first = False
        try:
            await _sync_window(db, user_id, user, token, oldest, newest, res, counters)
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("intervals backfill ventana %s..%s user=%s: %s",
                           oldest, newest, user_id, type(exc).__name__)
            res["errors"] += 1
        res["windows"] += 1
        newest = oldest - timedelta(days=1)
    if res["imported"] or res["updated"] or res["merged"]:
        recalc_load_after_sync(db, user_id)
    res["ignored_fields"] = counters["ignored_fields"]
    return res
