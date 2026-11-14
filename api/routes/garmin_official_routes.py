"""
Integracion OFICIAL Garmin (OAuth2 + PKCE + webhook push). Convive con la via no
oficial, que no se toca. Ver api/garmin_official.py.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import garmin_official as go
from ..app_url import get_app_url
from ..auth import get_current_user
from ..database import get_db
from ..models import GarminOAuthToken, GarminPushPayload, User

logger = logging.getLogger("labx.garmin_official")
ingest_log = logging.getLogger("garmin_official_ingest")
router = APIRouter(prefix="/integrations/garmin", tags=["garmin-official"])

PROFILE_PAGE = "/athlete-app.html"
# Claves de lista del payload push de Garmin (Activity + Health APIs)
_PUSH_KEYS_MAX = 50


def _require_configured():
    if not go.configured():
        raise HTTPException(503, "garmin no configurado")


def _redirect(result: str) -> RedirectResponse:
    return RedirectResponse(f"{get_app_url()}{PROFILE_PAGE}?garmin={result}", status_code=302)


def dispatch_garmin_sync(user_id: str, background_tasks) -> str:
    from ..garmin_pull_service import dispatch_garmin_sync as _d
    return _d(user_id, background_tasks)


@router.get("/connect")
def garmin_connect(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _require_configured()
    state, challenge = go.create_state(db, me.id)
    return RedirectResponse(go.build_authorize_url(state, challenge), status_code=302)


@router.get("/callback")
def garmin_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    _require_configured()
    if not state:
        return _redirect("error_state")
    consumed = go.consume_state(db, state)
    if not consumed:
        return _redirect("error_state")
    user_id, verifier = consumed
    if error or not code:
        return _redirect("denied")
    try:
        tokens = go.exchange_code(code, verifier)
        garmin_uid = go._fetch_garmin_user_id(tokens["access_token"])
        go.save_tokens(db, user_id, tokens, garmin_uid)
    except go.GarminOfficialError as exc:
        logger.warning("Garmin callback fallo user=%s: %s", user_id, exc)
        return _redirect("error")
    logger.info("Garmin oficial conectado user=%s", user_id)
    return _redirect("connected")


@router.get("/status")
def garmin_status(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(GarminOAuthToken).filter(GarminOAuthToken.user_id == me.id).first()
    return {
        "available": go.configured(),
        "connected": bool(row),
        "scope": row.scope if row else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


PUSH_STALE_HOURS = 48
_PUSH_WINDOW_DAYS = 7
_GAP_LOOKBACK_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(ts) -> str | None:
    return ts.isoformat() if ts else None


def _last_silent_gap(db: Session, now: datetime) -> dict | None:
    """Ultimo hueco de >=2 dias SIN payloads dentro de los ultimos 30 dias (entre dias
    con datos, o hasta hoy). Un push que murio y revivio no queda invisible."""
    since = (now - timedelta(days=_GAP_LOOKBACK_DAYS)).date()
    rows = db.query(func.date(GarminPushPayload.received_at)).filter(
        GarminPushPayload.received_at >= datetime.combine(since, datetime.min.time())).distinct().all()
    days = sorted({str(r[0])[:10] for r in rows if r[0]})
    if not days:
        return None
    today = now.date()
    marks = [datetime.strptime(d, "%Y-%m-%d").date() for d in days] + [today + timedelta(days=1)]
    gap = None
    for prev, nxt in zip(marks, marks[1:]):
        missing = (nxt - prev).days - 1
        if missing >= 2:
            gap = {"from": (prev + timedelta(days=1)).isoformat(),
                   "to": (nxt - timedelta(days=1)).isoformat(), "days": missing,
                   "ongoing": nxt == today + timedelta(days=1)}
    return gap


@router.get("/push-status")
def garmin_push_status(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Salud del push de Garmin (bandeja garmin_push_payloads). Solo fechas y conteos."""
    now = _utcnow()
    P = GarminPushPayload
    week = now - timedelta(days=_PUSH_WINDOW_DAYS)
    last_global = db.query(func.max(P.received_at)).scalar()
    last_mine = db.query(func.max(P.received_at)).filter(P.user_id == me.id).scalar()
    by_type = {}
    for ptype, last in db.query(P.payload_type, func.max(P.received_at)).group_by(P.payload_type).all():
        by_type[ptype] = {"last_received_at": _iso(last), "count_7d": 0}
    for ptype, n in db.query(P.payload_type, func.count(P.id)).filter(
            P.received_at >= week).group_by(P.payload_type).all():
        by_type[ptype]["count_7d"] = n
    pending = db.query(func.count(P.id)).filter(P.processed.is_(False), P.error.is_(None)).scalar() or 0
    errors = db.query(func.count(P.id)).filter(P.processed.is_(False), P.error.isnot(None)).scalar() or 0
    count_7d = db.query(func.count(P.id)).filter(P.received_at >= week).scalar() or 0
    mine_7d = db.query(func.count(P.id)).filter(P.user_id == me.id, P.received_at >= week).scalar() or 0
    # Referencia de la advertencia: lo del propio usuario si existe; si no, el push global.
    ref = last_mine or last_global
    hours = round((now - ref).total_seconds() / 3600, 1) if ref else None
    stale = ref is None or hours > PUSH_STALE_HOURS
    return {
        "last_received_at": _iso(last_global),
        "mine_last_received_at": _iso(last_mine),
        "reference_at": _iso(ref),
        "hours_since": hours,
        "stale": stale,
        "stale_after_hours": PUSH_STALE_HOURS,
        "count_7d": count_7d,
        "mine_count_7d": mine_7d,
        "by_type": by_type,
        "pending": pending,
        "errors": errors,
        "last_gap": _last_silent_gap(db, now),
    }


def _sync_fail(status_code: int, status: str, message: str, **extra) -> JSONResponse:
    return JSONResponse({"ok": False, "status": status, "message": message,
                         "errors": [{"message": message}], **extra}, status_code=status_code)


@router.post("/sync")
def garmin_sync(background_tasks: BackgroundTasks, me: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    """Sync manual de ACTIVIDADES por la API oficial (la salud llega solo por push y no se pide).
    Via 1: pull oficial con el token del usuario. Via 2 (solo si el pull no es posible):
    dispatch legacy con credenciales y el interruptor encendido. Sin via: error honesto."""
    from .athlete_routes import _latest_live_sync_str
    token_row = db.query(GarminOAuthToken).filter(GarminOAuthToken.user_id == me.id).first()
    if not token_row:
        return _sync_fail(409, "not_connected",
                          "Garmin no está conectado por la vía oficial. Conéctalo primero.")
    if not go.configured():
        return _sync_fail(503, "unavailable", "La integración oficial de Garmin no está disponible.")
    access = go.get_valid_access_token(db, me.id)
    pull_error = None
    if not access:
        pull_error = "needs_reconnect"
    else:
        try:
            items = go.fetch_recent_activities(access)
        except go.GarminOfficialError as exc:
            pull_error = "pull_failed"
            logger.warning("Garmin sync manual: pull fallo user=%s: %s", me.id, exc)
        else:
            from ..garmin_ingest import _upsert_activity, _recalc_load
            saved = 0
            for it in items:
                try:
                    if _upsert_activity(db, me.id, it):
                        saved += 1
                except Exception as exc:
                    db.rollback()
                    logger.warning("Garmin sync manual: item omitido (%s)", type(exc).__name__)
            db.commit()
            if saved:
                _recalc_load(db, me.id)
            return {"ok": True, "status": "ok", "via": "official", "saved": saved,
                    "health_included": False, "last_sync": _latest_live_sync_str(db, me.id),
                    "message": f"Actividades al día ({saved} recibidas)."}

    # El pull no fue posible: fallback legacy solo si hay credenciales y el interruptor lo permite.
    from ..garmin_legacy_flags import legacy_sync_enabled
    if me.garmin_email and legacy_sync_enabled():
        dispatch_garmin_sync(me.id, background_tasks)
        return {"ok": True, "status": "syncing", "via": "legacy", "saved": None,
                "health_included": False, "last_sync": _latest_live_sync_str(db, me.id),
                "message": "Sincronización iniciada por la vía anterior."}
    if pull_error == "needs_reconnect":
        return _sync_fail(409, "needs_reconnect",
                          "La conexión con Garmin venció. Reconecta Garmin para sincronizar.",
                          last_sync=_latest_live_sync_str(db, me.id))
    return _sync_fail(502, "pull_failed",
                      "Garmin no permitió traer las actividades ahora. Las nuevas llegan solas por el envío automático de Garmin.",
                      last_sync=_latest_live_sync_str(db, me.id))


@router.post("/disconnect")
def garmin_disconnect(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    deleted = db.query(GarminOAuthToken).filter(GarminOAuthToken.user_id == me.id).delete()
    db.commit()
    return {"ok": True, "disconnected": bool(deleted)}


def _hash_id(value) -> str:
    return hashlib.sha256(str(value).encode()).hexdigest()[:8]


def _has_data(items: list) -> bool:
    """True si algun item trae algo mas que userId (un ping vacio no cuenta)."""
    return any(isinstance(it, dict) and set(it) - {"userId"} for it in items)


def _record_push(db: Session, payload: dict, uid_map: dict) -> None:
    """Fase A del ingestor: log de FORMA (sin valores) + bandeja cruda por tipo.
    Nunca propaga errores: no debe alterar la respuesta a Garmin ni el dispatch."""
    try:
        shape = {}
        for key, items in payload.items():
            if isinstance(items, list):
                first = next((it for it in items if isinstance(it, dict)), None)
                shape[key] = {"n": len(items), "keys": sorted(first)[:_PUSH_KEYS_MAX] if first else []}
            else:
                shape[key] = type(items).__name__
        hashed = sorted({_hash_id(it["userId"]) for items in payload.values() if isinstance(items, list)
                         for it in items[:500] if isinstance(it, dict) and it.get("userId")})
        ingest_log.info("push shape=%s users=%s", json.dumps(shape, default=str)[:2000], hashed[:20])

        saved = False
        for key, items in payload.items():
            if not isinstance(items, list) or not _has_data(items):
                continue
            ids = [str(it["userId"]) for it in items if isinstance(it, dict) and it.get("userId")]
            resolved = next((uid_map[i] for i in ids if i in uid_map), None)
            db.add(GarminPushPayload(payload_type=str(key)[:100], user_id=resolved,
                                     payload_json=json.dumps({key: items}, default=str), processed=False))
            saved = True
        if saved:
            db.commit()
    except Exception as exc:
        db.rollback()
        logger.warning("Garmin push inbox error: %s", type(exc).__name__)


def _ingest_pending() -> None:
    from ..garmin_ingest import process_pending_background
    process_pending_background()


@router.post("/notify")
async def garmin_notify(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Webhook push de Garmin. Nunca 500: payload no resoluble => 200 y log."""
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "error": "payload invalido"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"ok": False, "error": "payload invalido"}, status_code=400)

    garmin_ids: set[str] = set()
    for key, items in payload.items():
        if not isinstance(items, list):
            continue
        for it in items[:500]:
            if isinstance(it, dict) and it.get("userId"):
                garmin_ids.add(str(it["userId"]))

    queued = 0
    try:
        rows = []
        if garmin_ids:
            rows = db.query(GarminOAuthToken).filter(
                GarminOAuthToken.garmin_user_id.in_(list(garmin_ids))).all()
        _record_push(db, payload, {r.garmin_user_id: r.user_id for r in rows})
        background_tasks.add_task(_ingest_pending)
        if garmin_ids:
            for row in rows:
                dispatch_garmin_sync(row.user_id, background_tasks)
                queued += 1
        if not queued:
            logger.info("Garmin notify sin usuario resoluble (keys=%s, ids=%d)",
                        list(payload.keys())[:_PUSH_KEYS_MAX], len(garmin_ids))
    except Exception as exc:  # nunca 500 hacia Garmin
        logger.warning("Garmin notify error: %s", type(exc).__name__)
    return {"ok": True, "queued": queued}
