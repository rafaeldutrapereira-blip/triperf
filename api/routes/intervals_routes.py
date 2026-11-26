"""
Conexion OAuth2 con intervals.icu (S6): ESCRITURA de workouts al calendario
(scope CALENDAR:WRITE) y, detras del flag INTERVALS_READ_ENABLED, LECTURA de
actividades y wellness (POST /sync). Ver api/intervals_connector.py.
"""
from __future__ import annotations

import base64
import json
import logging
import os
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import intervals_connector as ic
from .. import intervals_sync_service as iss
from .. import provider_oauth
from ..app_url import get_app_url
from ..auth import get_current_user
from ..database import get_db
from ..models import User
from ..plan_features import require_feature

logger = logging.getLogger("labx.intervals")
router = APIRouter(prefix="/integrations/intervals", tags=["intervals"])

APP_URL = get_app_url()


def read_enabled() -> bool:
    """Flag apagado por defecto: sin INTERVALS_READ_ENABLED nada de lectura es alcanzable."""
    return os.getenv("INTERVALS_READ_ENABLED", "").strip().lower() in ("1", "true")


def _require_available():
    if not ic.available():
        raise HTTPException(503, "intervals.icu no esta configurado todavia")


def _connection_state(me: User) -> str:
    """not_connected | connected | invalid (token rechazado) | needs_reconnect (falta el permiso de lectura)."""
    if not me.intervals_access_token:
        return "not_connected"
    if ic.is_invalid(me):
        return "invalid"
    if ic.needs_reconnect(me):
        return "needs_reconnect"
    return "connected"


def _iso(dt):
    return dt.isoformat() if dt else None


@router.get("/status")
def intervals_status(me: User = Depends(get_current_user)):
    """`connected` = token presente Y no marcado invalido (401/403 de intervals)."""
    has_token = bool(me.intervals_access_token)
    state = _connection_state(me)
    connected = has_token and state != "invalid"
    return {
        "available":  ic.available(),
        "state":      state,
        "has_token":  has_token,
        "invalid":    state == "invalid",
        "last_sync":  _iso(me.intervals_last_sync_at) if has_token else None,
        "connected_at": _iso(me.intervals_connected_at) if has_token else None,
        "connected":  connected,
        "athlete_id": me.intervals_athlete_id if has_token else None,
        "scopes":     me.intervals_scope if has_token else None,
        "read_enabled":    read_enabled(),
        "needs_reconnect": state in ("needs_reconnect", "invalid"),
    }


@router.post("/sync")
async def intervals_sync(
    days: int = Query(90, ge=1, le=365),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not read_enabled():
        raise HTTPException(404, "No encontrado")
    return await iss.sync_intervals_user(db, me.id, days)


@router.post("/backfill")
async def intervals_backfill(
    floor: str = Query("2019-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not read_enabled():
        raise HTTPException(404, "No encontrado")
    try:
        d = date.fromisoformat(floor)
    except ValueError:
        raise HTTPException(422, "floor no es una fecha valida")
    if d > date.today():
        raise HTTPException(422, "floor no puede ser futuro")
    return await iss.backfill_intervals_user(db, me.id, floor)


def _oauth_state(db: Session, uid: str, ret: str | None) -> str:
    """H4: state aleatorio de un solo uso en BD (patron de provider_oauth.py).
    El destino de retorno viaja en el nombre de proveedor ('intervals' | 'intervals_profile');
    solo se acepta un destino conocido (nada de URLs libres)."""
    provider = "intervals_profile" if ret == "profile" else "intervals"
    return provider_oauth.create_state(db, uid, provider)


def _consume_oauth_state(db: Session, state: str | None) -> tuple[str | None, str | None]:
    """-> (user_id, ret). user_id None si el state es desconocido, reutilizado o expirado."""
    for provider, ret in (("intervals", None), ("intervals_profile", "profile")):
        uid = provider_oauth.consume_state(db, state or "", provider)
        if uid:
            return uid, ret
    return None, None


def _return_url(ret: str | None, outcome: str) -> str:
    page = "athlete_profile.html" if ret == "profile" else "indoor_workout.html"
    return f"{APP_URL}/{page}?intervals={outcome}"


@router.get("/connect")
def intervals_connect(
    ret: str | None = Query(None),
    me: User = Depends(require_feature("indoor_workout")),
    db: Session = Depends(get_db),
):
    _require_available()
    return RedirectResponse(ic.build_authorize_url(_oauth_state(db, me.id, ret)))


@router.post("/reconnect")
def intervals_reconnect(
    ret: str | None = Query(None),
    me: User = Depends(require_feature("indoor_workout")),
    db: Session = Depends(get_db),
):
    """RECONECTAR = soltar las credenciales guardadas + devolver la URL de un OAuth fresco.
    No borra actividades, salud ni planificados. Si intervals no esta configurado, no toca nada."""
    _require_available()
    ic.clear_tokens(me, db)
    logger.info("intervals.icu reconexion iniciada user=%s", me.id)
    return {"ok": True, "authorize_url": ic.build_authorize_url(_oauth_state(db, me.id, ret))}


@router.get("/callback")
async def intervals_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    _require_available()
    if error or not code or not state:
        # Sin state valido no hay destino de retorno confiable: se usa el historico.
        # Si el state existe se consume igual (un solo uso) para conservar el destino.
        _uid, ret = _consume_oauth_state(db, state) if state else (None, None)
        return RedirectResponse(_return_url(ret, "denied"))

    user_id, ret = _consume_oauth_state(db, state)
    if not user_id:
        raise HTTPException(400, "State OAuth invalido")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(404, "Usuario no encontrado")

    try:
        tokens = await ic.exchange_code(code)
        access_token = tokens.get("access_token")
        if not access_token:
            raise ic.IntervalsError("intervals.icu no devolvio un access_token")
        athlete_id = await ic.fetch_athlete_id(access_token)
        ic.save_tokens(user, access_token, athlete_id, db, scope=tokens.get("scope"))
    except ic.IntervalsError as exc:
        logger.warning("intervals.icu callback fallo user=%s: %s", user_id, exc)
        return RedirectResponse(_return_url(ret, "error"))

    logger.info("intervals.icu conectado user=%s athlete_id=%s", user_id, user.intervals_athlete_id)
    return RedirectResponse(_return_url(ret, "connected"))


@router.delete("/disconnect")
def intervals_disconnect(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Idempotente: sin conexion tambien responde ok. Solo borra credenciales y estado de
    sync (token, athlete_id, scope, fechas); actividades, salud y planificados importados quedan."""
    was_connected = bool(me.intervals_access_token)
    ic.clear_tokens(me, db)
    if was_connected:
        logger.info("intervals.icu desconectado user=%s", me.id)
    return {"ok": True, "was_connected": was_connected}
