"""
Integracion OFICIAL Garmin (OAuth2 + PKCE + webhook push). Convive con la via no
oficial, que no se toca. Ver api/garmin_official.py.
"""
from __future__ import annotations

import hashlib
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
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
