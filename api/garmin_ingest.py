"""Ingestor Garmin oficial, fase B: procesa la bandeja `garmin_push_payloads`.

Reusa las tablas y helpers de mapeo del sync legacy (garmin_pull_service); no toca el
motor legacy ni crea tablas de datos nuevas.

Tipos con destino:
  activities / manuallyUpdatedActivities -> garmin_activities  (upsert por user_id + activity_id)
  dailies                                -> garmin_health_daily (upsert por user_id + date_iso)
  sleeps                                 -> garmin_sleep_sessions (upsert por user_id + date_iso)
Cualquier otro tipo se marca procesado con nota en el log (sin destino en el modelo).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from .activity_dedupe import mark_new_activity
from .models import (
    GarminActivity, GarminHealthDaily, GarminOAuthToken, GarminPushPayload, GarminSleepSession,
)

log = logging.getLogger("garmin_official_ingest")

BATCH_SIZE = 100
_MO = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _num(v):
    """float o None (bool y no numericos => None)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _int(v):
    n = _num(v)
    return None if n is None else int(round(n))


def _mins(seconds):
    n = _num(seconds)
    return None if n is None else int(round(n / 60))


# ── Actividades ───────────────────────────────────────────────────────────────

def _upsert_activity(db: Session, user_id: str, it: dict) -> bool:
    from .garmin_pull_service import _SPORT_COLOR, _format_pace, _format_swim_pace, _norm_sport

    act_id = it.get("activityId") or it.get("summaryId")
    start = _num(it.get("startTimeInSeconds"))
    if act_id is None or start is None:
        return False
    offset = _num(it.get("startTimeOffsetInSeconds")) or 0
    local = datetime.utcfromtimestamp(start + offset)  # hora local del atleta, como startTimeLocal
    date_iso = local.date().isoformat()
    date_label = f"{local.day} {_MO[local.month - 1]}"

    raw_type = it.get("activityType")
    if isinstance(raw_type, dict):
        raw_type = raw_type.get("typeKey")
    sport = _norm_sport(str(raw_type) if raw_type else None)
    color, stroke = _SPORT_COLOR.get(sport, _SPORT_COLOR["other"])

    dur_min = _mins(it.get("durationInSeconds")) or 0
    dist_m = _num(it.get("distanceInMeters")) or 0.0
    avg_spd = _num(it.get("averageSpeedInMetersPerSecond")) or 0.0
    elev = _num(it.get("totalElevationGainInMeters"))
    fields = {
        "name": it.get("activityName") or sport.title(),
        "sport": sport,
        "date_iso": date_iso,
        "date_label": date_label,
        "dur_min": dur_min,
        "dist_km": round(dist_m / 1000, 2) if dist_m else 0.0,
        "avg_hr": _int(it.get("averageHeartRateInBeatsPerMinute")) or None,
        "avg_power": _int(it.get("averagePowerInWatts")) or None,
        "pace_str": _format_pace(avg_spd) if sport == "run" and avg_spd else None,
        "swim_pace": _format_swim_pace(avg_spd) if sport == "swim" and avg_spd else None,
        "calories": _int(it.get("activeKilocalories")) or None,
        "elev_m": round(elev) if elev else None,
    }
    act_id = str(act_id)
    row = db.query(GarminActivity).filter(
        GarminActivity.user_id == user_id, GarminActivity.activity_id == act_id).first()
    if row:
        for k, v in fields.items():
            if v is not None:  # no pisar con vacio datos que ya tenia (p. ej. el sync legacy)
                setattr(row, k, v)
        row.synced_at = _now()
    else:
        # tss queda en su default (0.0): requiere umbrales del atleta; el sync legacy lo recalcula.
        new_row = GarminActivity(user_id=user_id, activity_id=act_id,
                                 icon={"swim": "🏊", "bike": "🚴", "run": "🏃", "gym": "💪"}.get(sport, "🏅"),
                                 color=color, stroke=stroke, **fields)
        db.add(new_row)
        db.flush()
        mark_new_activity(db, new_row)  # PILA 374: misma sesion ya llegada por otra via
    return True


# ── Dailies -> garmin_health_daily ────────────────────────────────────────────

_DAILY_MAP = {
    "steps": ("steps", _int),
    "activeKilocalories": ("active_calories", _int),
    "restingHeartRateInBeatsPerMinute": ("resting_hr", _int),
    "averageStressLevel": ("avg_stress", _int),
}


def _upsert_daily(db: Session, user_id: str, it: dict) -> bool:
    date_iso = str(it.get("calendarDate") or "")[:10]
    if len(date_iso) != 10:
        return False
    vals = {}
    for src, (dst, conv) in _DAILY_MAP.items():
        v = conv(it.get(src))
        # Garmin manda -1/-2 como "sin dato" en estres
        if v is not None and not (dst == "avg_stress" and v < 0):
            vals[dst] = v
    if not vals:
        return False
    row = db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id == user_id, GarminHealthDaily.date_iso == date_iso).first()
    if row:
        for k, v in vals.items():
            setattr(row, k, v)
        row.synced_at = _now()
    else:
        db.add(GarminHealthDaily(user_id=user_id, date_iso=date_iso, synced_at=_now(), **vals))
    return True


# ── Sleeps -> garmin_sleep_sessions ───────────────────────────────────────────

def _upsert_sleep(db: Session, user_id: str, it: dict) -> bool:
    date_iso = str(it.get("calendarDate") or "")[:10]
    if len(date_iso) != 10:
        return False
    start = _num(it.get("startTimeInSeconds"))
    dur = _num(it.get("durationInSeconds"))
    score = it.get("overallSleepScore")
    vals = {
        "total_min": _mins(dur),
        "deep_min": _mins(it.get("deepSleepDurationInSeconds")),
        "light_min": _mins(it.get("lightSleepDurationInSeconds")),
        "rem_min": _mins(it.get("remSleepInSeconds")),
        "awake_min": _mins(it.get("awakeDurationInSeconds")),
        "nap_min": _mins(it.get("napTimeInSeconds")),
        "sleep_start": datetime.utcfromtimestamp(start) if start is not None else None,
        "sleep_end": datetime.utcfromtimestamp(start + dur) if start is not None and dur is not None else None,
        "sleep_score": _int(score.get("value")) if isinstance(score, dict) else None,
        "sleep_score_qual": score.get("qualifierKey") if isinstance(score, dict) else None,
    }
    vals = {k: v for k, v in vals.items() if v is not None}
    if not vals:
        return False
    row = db.query(GarminSleepSession).filter(
        GarminSleepSession.user_id == user_id, GarminSleepSession.date_iso == date_iso).first()
    if row:
        for k, v in vals.items():
            setattr(row, k, v)
        row.synced_at = _now()
    else:
        db.add(GarminSleepSession(user_id=user_id, date_iso=date_iso, synced_at=_now(), **vals))
    return True


_HANDLERS = {
    "activities": _upsert_activity,
    "manuallyUpdatedActivities": _upsert_activity,
    "dailies": _upsert_daily,
    "sleeps": _upsert_sleep,
}


_ACTIVITY_TYPES = ("activities", "manuallyUpdatedActivities")


def _recalc_load(db: Session, user_id: str) -> None:
    """CARGA-AL-DIA: recalcula garmin_training_load del usuario tras ingerir actividades.
    Best-effort: nunca frena el ingestor."""
    from .intervals_sync_service import recalc_load_after_sync
    recalc_load_after_sync(db, user_id)


def _process_one(db: Session, row: GarminPushPayload, connected: dict) -> str:
    """Escribe los datos de un payload (sin commit). Devuelve una nota de resultado."""
    if not row.user_id:
        log.warning("payload %s (%s) sin usuario atribuible: se omite", row.id, row.payload_type)
        return "sin_usuario"
    if row.user_id not in connected:
        connected[row.user_id] = db.query(GarminOAuthToken.id).filter(
            GarminOAuthToken.user_id == row.user_id).first() is not None
    if not connected[row.user_id]:
        log.info("payload %s: usuario sin conexion Garmin oficial, se omite", row.id)
        return "desconectado"
    handler = _HANDLERS.get(row.payload_type)
    if handler is None:
        log.info("payload %s: tipo '%s' sin destino en el modelo, marcado procesado", row.id, row.payload_type)
        return "sin_destino"
    body = json.loads(row.payload_json)
    items = body.get(row.payload_type) if isinstance(body, dict) else None
    if not isinstance(items, list):
        raise ValueError("payload_json sin lista para el tipo")
    written = 0
    for it in items:
        if isinstance(it, dict) and handler(db, row.user_id, it):
            written += 1
    return f"ok:{written}/{len(items)}"


def process_pending(db: Session, limit: int = BATCH_SIZE, retry_failed: bool = False) -> dict:
    """Procesa hasta `limit` payloads pendientes (received_at asc). Cada payload en su propia
    transaccion: un fallo queda con processed=False + error y no frena al resto. Los fallidos
    no se reintentan salvo retry_failed=True (evita que un payload corrupto acapare el lote)."""
    q = db.query(GarminPushPayload).filter(GarminPushPayload.processed.is_(False))
    if not retry_failed:
        q = q.filter(GarminPushPayload.error.is_(None))
    ids = [r[0] for r in q.order_by(GarminPushPayload.received_at.asc()).limit(max(1, limit)).with_entities(
        GarminPushPayload.id).all()]
    stats = {"selected": len(ids), "processed": 0, "failed": 0, "written": 0}
    connected: dict = {}
    load_users: set[str] = set()  # CARGA-AL-DIA: usuarios con actividades nuevas en el lote
    for pid in ids:
        try:
            row = db.get(GarminPushPayload, pid)
            note = _process_one(db, row, connected)
            row.processed = True
            row.processed_at = _now()
            row.error = None
            db.commit()
            stats["processed"] += 1
            if note.startswith("ok:"):
                n_written = int(note[3:].split("/")[0])
                stats["written"] += n_written
                if n_written and row.payload_type in _ACTIVITY_TYPES and row.user_id:
                    load_users.add(row.user_id)
        except Exception as exc:
            db.rollback()
            stats["failed"] += 1
            log.warning("payload %s fallo: %s", pid, type(exc).__name__)
            try:
                row = db.get(GarminPushPayload, pid)
                if row is not None:
                    row.error = f"{type(exc).__name__}: {exc}"[:300]
                    db.commit()
            except Exception:
                db.rollback()
    for uid in load_users:
        _recalc_load(db, uid)
    log.info("ingest fase B: %s", stats)
    return stats


def process_pending_background() -> None:
    """Entrada para BackgroundTasks / scripts: abre su propia sesion. Nunca propaga errores."""
    from .database import SessionLocal
    db = SessionLocal()
    try:
        process_pending(db)
    except Exception as exc:
        log.warning("ingest background error: %s", type(exc).__name__)
    finally:
        db.close()


if __name__ == "__main__":  # vaciar la bandeja acumulada: python -m api.garmin_ingest
    logging.basicConfig(level=logging.INFO)
    from .database import SessionLocal
    _db = SessionLocal()
    try:
        while True:
            s = process_pending(_db)
            if not s["selected"] or s["processed"] == 0:
                break
    finally:
        _db.close()
