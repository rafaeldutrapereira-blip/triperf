"""
P0 — Puente app -> web.

La app (Capacitor, origen capacitor://localhost) no comparte sesion con la web
(labxperformanceapp.com). Flujo:
  1. POST /auth/web-handoff  (autenticado) {destino}  -> {url}
     Emite un token aleatorio de UN SOLO USO y vida corta (HANDOFF_TTL_SECONDS).
     Solo se guarda su hash SHA-256.
  2. La app abre {url} = /web-handoff.html?d=<destino>#t=<token> (el token va en
     el fragmento: no se envia al servidor ni queda en logs).
  3. web-handoff.html hace POST /auth/web-handoff/redeem {token}: el servidor
     marca el token como usado (atomico), emite una sesion NUEVA del MISMO
     usuario dueno del token, la deja en la cookie HttpOnly y devuelve los datos
     para el localStorage; la pagina redirige a la ruta fija del destino.

El destino es una LISTA CERRADA mapeada a rutas fijas del servidor: nunca se
acepta una URL del cliente (sin open-redirect).
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import Action, audit, ip_from_request
from ..auth import IS_PROD, TOKEN_HOURS, create_token, get_current_user, require_role
from ..database import get_db
from ..models import User, WebHandoff

logger = logging.getLogger("labx.web_handoff")
router = APIRouter(prefix="/auth/web-handoff", tags=["auth"])

HANDOFF_TTL_SECONDS = 120

# Lista cerrada destino -> ruta fija del servidor (nada de URLs arbitrarias).
DESTINOS: dict[str, str] = {
    "estado":    "/estado.html",
    "race_day":  "/race_day.html",
    "gear":      "/gear.html",
    "detalle":   "/detalle.html",
    "analytics": "/analytics.html",
}


class HandoffRequest(BaseModel):
    destino: str


class RedeemRequest(BaseModel):
    token: str


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("")
def issue_handoff(body: HandoffRequest, request: Request,
                  db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    destino = (body.destino or "").strip()
    if destino not in DESTINOS:
        raise HTTPException(status_code=400, detail="Destino no permitido")
    token = secrets.token_urlsafe(32)
    now = _now()
    # Limpieza best-effort de filas viejas (>1 dia) para que la tabla no crezca
    # de mas; las canjeadas se conservan: son el contador de uso.
    try:
        db.query(WebHandoff).filter(
            WebHandoff.used_at.is_(None),
            WebHandoff.expires_at < now - timedelta(days=1),
        ).delete(synchronize_session=False)
    except Exception:
        db.rollback()
    db.add(WebHandoff(
        token_hash=_hash(token), user_id=me.id, destino=destino,
        expires_at=now + timedelta(seconds=HANDOFF_TTL_SECONDS),
    ))
    db.commit()
    return {
        "ok": True,
        "token": token,
        "destino": destino,
        "expires_in": HANDOFF_TTL_SECONDS,
        "path": "/web-handoff.html?d=" + destino,   # la app antepone el origen web y agrega #t=<token>
    }


@router.post("/redeem")
def redeem_handoff(body: RedeemRequest, request: Request, response: Response,
                   db: Session = Depends(get_db)):
    now = _now()
    h = _hash((body.token or "").strip())
    # Canje atomico: solo UN request puede pasar de used_at NULL a now.
    updated = db.query(WebHandoff).filter(
        WebHandoff.token_hash == h,
        WebHandoff.used_at.is_(None),
        WebHandoff.expires_at > now,
    ).update({WebHandoff.used_at: now}, synchronize_session=False)
    db.commit()
    if updated != 1:
        raise HTTPException(status_code=401, detail="Enlace invalido, vencido o ya usado")
    row = db.query(WebHandoff).filter(WebHandoff.token_hash == h).first()
    user = db.query(User).filter(User.id == row.user_id).first()
    if not user or not user.activo:
        raise HTTPException(status_code=401, detail="Enlace invalido, vencido o ya usado")

    jwt_token = create_token(user.id, user.rol, user.nombre, user.token_gen or 1)
    response.set_cookie(
        key="lx_access_token", value=jwt_token, httponly=True, secure=IS_PROD,
        samesite="lax", max_age=TOKEN_HOURS * 3600, path="/",
    )
    audit(db, Action.WEB_HANDOFF, user_id=user.id, ip=ip_from_request(request))
    return {
        "ok": True,
        "access_token": jwt_token,
        "rol": user.rol,
        "nombre": user.nombre,
        "user_id": user.id,
        "plan_nivel": user.plan_nivel or "basico",
        "email": user.email,
        "lang": user.lang or "es",
        "destino": row.destino,
        "path": DESTINOS[row.destino],
    }


@router.get("/stats")
def handoff_stats(db: Session = Depends(get_db), me: User = Depends(require_role("admin"))):
    """Contador del puente por destino: emitidos y canjeados (telemetria de la poda)."""
    rows = db.query(
        WebHandoff.destino,
        func.count(WebHandoff.id),
        func.count(WebHandoff.used_at),
    ).group_by(WebHandoff.destino).all()
    por_destino = {d: {"emitidos": 0, "canjeados": 0} for d in DESTINOS}
    for destino, emitidos, canjeados in rows:
        por_destino[destino] = {"emitidos": emitidos, "canjeados": canjeados}
    return {"ok": True, "por_destino": por_destino}
