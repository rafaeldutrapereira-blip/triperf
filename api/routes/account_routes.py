"""CUENTA-BORRADO: POST /api/account/deletion-request (con sesion y contrasena)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..account_deletion import GRACE_DAYS, MAX_DAYS, request_deletion
from ..audit import audit
from ..auth import get_current_user, verify_password
from ..database import get_db
from ..models import User

logger = logging.getLogger("labx.account")
router = APIRouter(prefix="/account", tags=["account"])

ACTION_REQUESTED = "account.deletion.requested"


def confirm_and_request(db: Session, me: User, password: str, response: Response) -> dict:
    """Nucleo compartido por todas las rutas de borrado: exige la contrasena actual."""
    if not password or not verify_password(password, me.password_hash):
        raise HTTPException(400, "Contraseña incorrecta — confirma tu identidad para eliminar la cuenta")
    uid = me.id
    req = request_deletion(db, me)
    # Registro auditable: solo el id de la cuenta (sera anonimo), sin IP ni agente
    audit(db, ACTION_REQUESTED, user_id=uid, detail={"request_ref": req.user_ref})
    response.delete_cookie("lx_access_token", path="/")
    logger.info("Eliminacion de cuenta solicitada ref=%s", req.user_ref)
    return {
        "ok": True,
        "status": req.status,
        "purge_after": req.purge_after.isoformat(),
        "deadline_at": req.deadline_at.isoformat(),
        "grace_days": GRACE_DAYS,
        "max_days": MAX_DAYS,
        "message": "Tu cuenta quedó desactivada. Tus datos se eliminarán dentro del plazo indicado.",
    }


@router.post("/deletion-request")
def deletion_request(
    body: dict,
    response: Response,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Solo el titular de la sesion: el id sale del token, nunca del cuerpo."""
    return confirm_and_request(db, me, (body or {}).get("password", ""), response)
