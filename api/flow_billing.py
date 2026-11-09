"""
Flow — lógica de entitlement (activar / cancelar / vencer) sobre FlowSubscription.

Regla de oro: el plan del usuario se activa SOLO desde `activate()`, que lo invoca
el webhook ya confirmado contra Flow. Nunca desde el retorno del navegador.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session, object_session

from .models import FlowSubscription, User

logger = logging.getLogger("labx.flow")

GRACE_DAYS = 5   # tolerancia tras period_end sin renovación antes de bajar el plan
LIVE_STATES = ("pendiente", "activa")


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_flow_dt(value) -> datetime | None:
    """Flow entrega 'yyyy-mm-dd hh:mm:ss' (o solo fecha)."""
    if not value:
        return None
    s = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def latest_subscription(db: Session, user_id: str, states=None) -> FlowSubscription | None:
    q = db.query(FlowSubscription).filter(FlowSubscription.user_id == user_id)
    if states:
        q = q.filter(FlowSubscription.status.in_(states))
    return q.order_by(FlowSubscription.created_at.desc()).first()


def _revert_plan(db: Session, user: User, row: FlowSubscription) -> None:
    """Baja a 'basico' solo si el plan actual lo otorgó esta suscripción y no hay otra activa."""
    other = (db.query(FlowSubscription)
             .filter(FlowSubscription.user_id == user.id,
                     FlowSubscription.id != row.id,
                     FlowSubscription.status == "activa").first())
    if other is None and (user.plan_nivel or "basico") == row.plan_nivel:
        user.plan_nivel = "basico"


def activate(db: Session, row: FlowSubscription, flow_sub: dict) -> None:
    """Pago confirmado por Flow + suscripción vigente → plan activo. Idempotente."""
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is None:
        return
    row.period_start = parse_flow_dt(flow_sub.get("period_start")) or row.period_start
    row.period_end = parse_flow_dt(flow_sub.get("period_end")) or row.period_end
    row.cancel_at_period_end = bool(int(flow_sub.get("cancel_at_period_end") or 0))
    row.status = "activa"
    row.updated_at = now()
    user.plan_nivel = row.plan_nivel
    db.commit()
    logger.info("Flow: plan activado user_id=%s plan=%s", user.id, row.plan_nivel)


def reconcile_row(db: Session, row: FlowSubscription) -> bool:
    """Aplica vencimientos. True si cambió algo."""
    if row.status != "activa" or row.period_end is None:
        return False
    t = now()
    new_status = None
    if row.cancel_at_period_end and row.period_end <= t:
        new_status = "cancelada"
    elif row.period_end + timedelta(days=GRACE_DAYS) <= t:
        new_status = "fallida"   # no llegó la renovación
    if new_status is None:
        return False
    row.status = new_status
    row.updated_at = t
    user = db.query(User).filter(User.id == row.user_id).first()
    if user is not None:
        _revert_plan(db, user, row)
    db.commit()
    logger.info("Flow: suscripción %s -> %s", row.id, new_status)
    return True


def reconcile_user(user: User) -> None:
    """Gancho barato para has_feature(): solo se invoca con FLOW_ENABLED=1."""
    db = object_session(user) if user is not None else None
    if db is None or getattr(user, "id", None) is None:
        return
    for row in (db.query(FlowSubscription)
                .filter(FlowSubscription.user_id == user.id, FlowSubscription.status == "activa").all()):
        reconcile_row(db, row)
