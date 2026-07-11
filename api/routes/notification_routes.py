"""
Web Push Notifications con VAPID.
- El atleta suscribe su browser al endpoint /api/notifications/subscribe
- Cuando el coach asigna un workout, se envía push automáticamente
- Usa la librería pywebpush (pip install pywebpush)
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Session

from ..database import get_db, Base
from ..auth import get_current_user
from ..models import User

logger = logging.getLogger("labx.notifications")
router = APIRouter(prefix="/notifications", tags=["notifications"])

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY  = os.getenv("VAPID_PUBLIC_KEY",  "")
VAPID_SUBJECT     = os.getenv("VAPID_SUBJECT",      "mailto:admin@labx.app")


# ── Modelo de suscripción ──────────────────────────────────────

class PushSubscription(Base):
    """Almacena las push subscriptions de los usuarios (una por device/browser)."""
    __tablename__ = "push_subscriptions"

    id         = Column(String, primary_key=True)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    endpoint   = Column(Text, nullable=False)
    p256dh     = Column(Text, nullable=False)
    auth_key   = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


# ── Schemas ────────────────────────────────────────────────────

class SubscribeIn(BaseModel):
    endpoint:   str
    p256dh:     str
    auth_key:   str
    device_id:  str | None = None


class PushPayload(BaseModel):
    title:   str
    body:    str
    url:     str | None = None
    icon:    str | None = "/icon-192.png"


# ── Endpoints ─────────────────────────────────────────────────

@router.get("/vapid-public-key")
def get_vapid_public_key():
    """Devuelve la VAPID public key para que el browser pueda suscribirse."""
    if not VAPID_PUBLIC_KEY:
        raise HTTPException(503, "Push notifications no configuradas (VAPID_PUBLIC_KEY faltante)")
    return {"vapid_public_key": VAPID_PUBLIC_KEY}


@router.post("/subscribe", status_code=201)
def subscribe(
    body: SubscribeIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Registra o actualiza la suscripción push del usuario."""
    import uuid
    existing = db.query(PushSubscription).filter(
        PushSubscription.user_id == me.id,
        PushSubscription.endpoint == body.endpoint,
    ).first()

    if existing:
        existing.p256dh   = body.p256dh
        existing.auth_key = body.auth_key
    else:
        sub = PushSubscription(
            id=str(uuid.uuid4()),
            user_id=me.id,
            endpoint=body.endpoint,
            p256dh=body.p256dh,
            auth_key=body.auth_key,
        )
        db.add(sub)
    db.commit()
    return {"ok": True, "message": "Notificaciones activadas"}


@router.delete("/unsubscribe")
def unsubscribe(
    endpoint: str,
    db:       Session = Depends(get_db),
    me:       User    = Depends(get_current_user),
):
    """Elimina la suscripción push del usuario para este endpoint."""
    db.query(PushSubscription).filter(
        PushSubscription.user_id == me.id,
        PushSubscription.endpoint == endpoint,
    ).delete()
    db.commit()
    return {"ok": True}


# ── Helper: enviar push a un usuario ─────────────────────────

def send_push_to_user(user_id: str, payload: dict, db: Session) -> int:
    """
    Envía una notificación push a todos los dispositivos registrados del usuario.
    Retorna el número de envíos exitosos.
    Requiere VAPID_PRIVATE_KEY y pywebpush instalado.
    """
    if not VAPID_PRIVATE_KEY:
        logger.debug("VAPID_PRIVATE_KEY no configurada — push omitido")
        return 0

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.warning("pywebpush no instalado — push omitido (pip install pywebpush)")
        return 0

    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    sent = 0
    to_delete = []

    for sub in subs:
        subscription_info = {
            "endpoint": sub.endpoint,
            "keys": {
                "p256dh": sub.p256dh,
                "auth":   sub.auth_key,
            },
        }
        try:
            webpush(
                subscription_info=subscription_info,
                data=json.dumps(payload),
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUBJECT},
            )
            sent += 1
        except WebPushException as e:
            status = getattr(e.response, "status_code", 0) if e.response else 0
            if status in (404, 410):
                # Suscripción expirada — eliminar
                to_delete.append(sub.id)
            else:
                logger.warning("Push error para user_id=%s: %s", user_id, e)
        except Exception as e:
            logger.error("Push inesperado para user_id=%s: %s", user_id, e)

    if to_delete:
        db.query(PushSubscription).filter(
            PushSubscription.id.in_(to_delete)
        ).delete(synchronize_session=False)
        db.commit()

    return sent
