"""
Rutas OAuth de Polar y Wahoo (connect / callback / status / disconnect).
Espejo de garmin_official_routes.py. Los redirects registrados en los portales son
/api/integrations/<provider>/callback. Ver api/provider_oauth.py.
"""
from __future__ import annotations

import logging
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .. import provider_oauth as po
from ..app_url import get_app_url
from ..auth import get_current_user
from ..database import get_db
from ..models import User

logger = logging.getLogger("labx.wearable_oauth")

PROFILE_PAGE = "/athlete-app.html"

polar_router = APIRouter(prefix="/integrations/polar", tags=["polar-oauth"])
wahoo_router = APIRouter(prefix="/integrations/wahoo", tags=["wahoo-oauth"])


def _redirect(provider: str, result: str) -> RedirectResponse:
    return RedirectResponse(f"{get_app_url()}{PROFILE_PAGE}?{provider}={result}", status_code=302)


def _require_available(provider: str):
    if not po.enabled(provider):
        raise HTTPException(404, f"{provider} no habilitado")
    if not po.configured(provider):
        raise HTTPException(503, f"{provider} no configurado")


async def _exchange(provider: str, db: Session, user_id: str, code: str) -> tuple[dict, str | None]:
    """Intercambia el code. -> (token_response, member_id)."""
    if provider == "polar":
        from ..providers.polar import PolarProvider
        prov = PolarProvider(db)
        await prov.authenticate(
            user_id, client_id=po.client_id(provider), client_secret=po.client_secret(provider),
            code=code, redirect_uri=po.redirect_uri(provider), member_id=str(user_id))
        return prov.last_token_response, str(user_id)
    from ..providers.wahoo import WahooProvider
    prov = WahooProvider(db)
    await prov.authenticate(user_id, code=code, redirect_uri=po.redirect_uri(provider))
    return prov.last_token_response, None


async def _connect(provider: str, me: User, db: Session):
    _require_available(provider)
    state = po.create_state(db, me.id, provider)
    params = {
        "response_type": "code",
        "client_id": po.client_id(provider),
        "redirect_uri": po.redirect_uri(provider),
        "state": state,
    }
    if po.scope(provider):
        params["scope"] = po.scope(provider)
    return RedirectResponse(f"{po.authorize_url(provider)}?{urlencode(params)}", status_code=302)


async def _callback(provider: str, code, state, error, db: Session):
    _require_available(provider)
    if not state:
        return _redirect(provider, "error_state")
    user_id = po.consume_state(db, state, provider)
    if not user_id:
        return _redirect(provider, "error_state")
    if error or not code:
        return _redirect(provider, "denied")
    try:
        token_response, member_id = await _exchange(provider, db, user_id, code)
        if not token_response or not token_response.get("access_token"):
            raise ValueError("respuesta de token vacia")
        po.save_connection(db, user_id, provider, token_response, member_id=member_id)
    except Exception as exc:
        logger.warning("%s callback fallo user=%s: %s", provider, user_id, type(exc).__name__)
        return _redirect(provider, "error")
    logger.info("%s conectado user=%s", provider, user_id)
    return _redirect(provider, "connected")


def _status(provider: str, me: User, db: Session) -> dict:
    row = po.get_connection(db, me.id, provider)
    return {
        "provider": provider,
        "available": po.enabled(provider) and po.configured(provider),
        "connected": bool(row),
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def _disconnect(provider: str, me: User, db: Session) -> dict:
    return {"ok": True, "disconnected": po.delete_connection(db, me.id, provider)}


# ── Polar ───────────────────────────────────────────────────────────────────

@polar_router.get("/connect")
async def polar_connect(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return await _connect("polar", me, db)


@polar_router.get("/callback")
async def polar_callback(code: str | None = None, state: str | None = None,
                         error: str | None = None, db: Session = Depends(get_db)):
    return await _callback("polar", code, state, error, db)


@polar_router.get("/status")
async def polar_status(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _status("polar", me, db)


@polar_router.post("/disconnect")
async def polar_disconnect(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _disconnect("polar", me, db)


# ── Wahoo ───────────────────────────────────────────────────────────────────

@wahoo_router.get("/connect")
async def wahoo_connect(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return await _connect("wahoo", me, db)


@wahoo_router.get("/callback")
async def wahoo_callback(code: str | None = None, state: str | None = None,
                         error: str | None = None, db: Session = Depends(get_db)):
    return await _callback("wahoo", code, state, error, db)


@wahoo_router.get("/status")
async def wahoo_status(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _status("wahoo", me, db)


@wahoo_router.post("/disconnect")
async def wahoo_disconnect(me: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _disconnect("wahoo", me, db)
