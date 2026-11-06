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


@router.get("/status")
def intervals_status(me: User = Depends(get_current_user)):
    connected = bool(me.intervals_access_token)
    return {
        "available":  ic.available(),
        "connected":  connected,
        "athlete_id": me.intervals_athlete_id if connected else None,
        "scopes":     me.intervals_scope if connected else None,
        "read_enabled":    read_enabled(),
        "needs_reconnect": ic.needs_reconnect(me),
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


@router.get("/connect")
def intervals_connect(me: User = Depends(require_feature("indoor_workout"))):
    _require_available()
    state = base64.urlsafe_b64encode(json.dumps({"uid": me.id}).encode()).decode()
    return RedirectResponse(ic.build_authorize_url(state))


@router.get("/callback")
async def intervals_callback(
    code: str | None = None,
    error: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    _require_available()
    if error or not code or not state:
        return RedirectResponse(f"{APP_URL}/indoor_workout.html?intervals=denied")

    try:
        padded = state + "=" * (-len(state) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode())
        user_id = payload["uid"]
    except Exception:
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
        return RedirectResponse(f"{APP_URL}/indoor_workout.html?intervals=error")

    logger.info("intervals.icu conectado user=%s athlete_id=%s", user_id, user.intervals_athlete_id)
    return RedirectResponse(f"{APP_URL}/indoor_workout.html?intervals=connected")


@router.delete("/disconnect")
def intervals_disconnect(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not me.intervals_access_token:
        raise HTTPException(400, "intervals.icu no esta conectado")
    ic.clear_tokens(me, db)
    logger.info("intervals.icu desconectado user=%s", me.id)
    return {"ok": True}
