"""
Mensajería interna coach ↔ atleta.
Inbox básico: enviar, listar, marcar como leído, eliminar (soft-delete).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models import Message, User

router = APIRouter(prefix="/messages", tags=["messages"])

MAX_BODY_LEN = 2000


class MessageIn(BaseModel):
    to_user_id: str
    body:       str

    @field_validator("body")
    @classmethod
    def body_not_empty(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("El mensaje no puede estar vacío")
        if len(v) > MAX_BODY_LEN:
            raise ValueError(f"El mensaje no puede superar {MAX_BODY_LEN} caracteres")
        return v


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:           str
    from_user_id: str
    to_user_id:   str
    from_nombre:  str
    body:         str
    sent_at:      datetime
    read_at:      Optional[datetime]


def _msg_out(m: Message) -> dict:
    return {
        "id":           m.id,
        "from_user_id": m.from_user_id,
        "to_user_id":   m.to_user_id,
        "from_nombre":  m.sender.nombre if m.sender else "—",
        "body":         m.body,
        "sent_at":      m.sent_at.isoformat(),
        "read_at":      m.read_at.isoformat() if m.read_at else None,
    }


@router.post("", status_code=201)
def send_message(
    body: MessageIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Envía un mensaje a otro usuario (coach→atleta o atleta→coach)."""
    recipient = db.query(User).filter(User.id == body.to_user_id, User.activo == True).first()
    if not recipient:
        raise HTTPException(404, "Destinatario no encontrado")
    if recipient.id == me.id:
        raise HTTPException(400, "No puedes enviarte un mensaje a ti mismo")

    msg = Message(
        from_user_id=me.id,
        to_user_id=body.to_user_id,
        body=body.body.strip(),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    try:
        from ..sse_broker import publish_nowait
        publish_nowait(body.to_user_id, "message_received",
                       {"from_user_id": me.id,
                        "from_name": getattr(me, "nombre", me.email),
                        "preview": body.body.strip()[:80]})
    except Exception:
        pass
    return _msg_out(msg)


@router.get("/inbox")
def get_inbox(
    skip:  int = Query(0,  ge=0),
    limit: int = Query(30, ge=1, le=100),
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    """Mensajes recibidos por el usuario autenticado."""
    msgs = (
        db.query(Message)
        .filter(Message.to_user_id == me.id, Message.deleted_at.is_(None))
        .order_by(Message.sent_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_msg_out(m) for m in msgs]


@router.get("/sent")
def get_sent(
    skip:  int = Query(0,  ge=0),
    limit: int = Query(30, ge=1, le=100),
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    """Mensajes enviados por el usuario autenticado."""
    msgs = (
        db.query(Message)
        .filter(Message.from_user_id == me.id, Message.deleted_at.is_(None))
        .order_by(Message.sent_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return [_msg_out(m) for m in msgs]


@router.get("/unread-count")
def unread_count(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Número de mensajes no leídos del usuario."""
    count = (
        db.query(Message)
        .filter(
            Message.to_user_id == me.id,
            Message.read_at.is_(None),
            Message.deleted_at.is_(None),
        )
        .count()
    )
    return {"unread": count}


@router.post("/{message_id}/read")
def mark_read(
    message_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Marca un mensaje como leído."""
    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.to_user_id == me.id,
        Message.deleted_at.is_(None),
    ).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    if not msg.read_at:
        msg.read_at = datetime.now(timezone.utc).replace(tzinfo=None)
        db.commit()
    return {"ok": True}


@router.delete("/{message_id}")
def delete_message(
    message_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Soft-delete de un mensaje (sender o receiver pueden eliminarlo)."""
    msg = db.query(Message).filter(
        Message.id == message_id,
        Message.deleted_at.is_(None),
    ).first()
    if not msg:
        raise HTTPException(404, "Mensaje no encontrado")
    if msg.from_user_id != me.id and msg.to_user_id != me.id:
        raise HTTPException(403, "No tienes permiso para eliminar este mensaje")
    msg.deleted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True}


@router.get("/thread/{other_user_id}")
def get_thread(
    other_user_id: str,
    skip:  int = Query(0,  ge=0),
    limit: int = Query(50, ge=1, le=200),
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    """Conversación entre el usuario actual y otro usuario."""
    msgs = (
        db.query(Message)
        .filter(
            Message.deleted_at.is_(None),
            (
                (Message.from_user_id == me.id) & (Message.to_user_id == other_user_id)
            ) | (
                (Message.from_user_id == other_user_id) & (Message.to_user_id == me.id)
            )
        )
        .order_by(Message.sent_at.asc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    # Marcar como leídos los que el usuario recibe
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for m in msgs:
        if m.to_user_id == me.id and not m.read_at:
            m.read_at = now
    db.commit()
    return [_msg_out(m) for m in msgs]


@router.get("/contacts")
def get_contacts(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Lista de contactos con quienes se han intercambiado mensajes.
    Devuelve el último mensaje de cada conversación + unread count.
    """
    from sqlalchemy import or_, func, case

    # Todos los mensajes en los que el usuario participó
    all_msgs = (
        db.query(Message)
        .filter(
            Message.deleted_at.is_(None),
            or_(Message.from_user_id == me.id, Message.to_user_id == me.id),
        )
        .order_by(Message.sent_at.desc())
        .all()
    )

    # Agrupar por "otro usuario"
    seen:    set[str]  = set()
    convs:   list[dict] = []

    for m in all_msgs:
        other_id = m.to_user_id if m.from_user_id == me.id else m.from_user_id
        if other_id in seen:
            continue
        seen.add(other_id)

        other = db.query(User).filter(User.id == other_id).first()
        if not other:
            continue

        # Mensajes no leídos de este contacto hacia mí
        unread = db.query(func.count(Message.id)).filter(
            Message.from_user_id == other_id,
            Message.to_user_id   == me.id,
            Message.read_at.is_(None),
            Message.deleted_at.is_(None),
        ).scalar() or 0

        convs.append({
            "user_id":     other.id,
            "nombre":      other.nombre or other.email,
            "rol":         other.rol,
            "last_body":   m.body[:80] + ("…" if len(m.body) > 80 else ""),
            "last_sent_at":m.sent_at.isoformat(),
            "unread":      unread,
            "is_mine":     m.from_user_id == me.id,
        })

    return {"contacts": convs, "total_unread": sum(c["unread"] for c in convs)}


@router.get("/coach-notifications")
def coach_notifications(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Aggregated notification summary for coaches: unread msgs + feedback + upcoming races."""
    from ..services.messaging_service import get_coach_notifications
    return get_coach_notifications(me.id, db)


@router.get("/athlete-summary")
def athlete_message_summary(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Unread message count + latest message for an athlete."""
    from ..services.messaging_service import get_athlete_message_summary
    return get_athlete_message_summary(me.id, db)
