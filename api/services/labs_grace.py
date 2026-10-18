"""
B12 — Gracia de 90 días de Labs para los Elite actuales.

Decisión de Rafael: al desplegar B12, los usuarios Elite que ya tienen Labs
conservan el acceso 90 días (entitlement source='legacy', sin cancelación).
Después, Labs pasa a addon pagado. La gracia cuenta desde el despliegue.

- plan_grace(): dry-run, lista a quién se le daría la gracia.
- apply_grace(): crea los entitlements. Idempotente: no duplica.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from ..models import Entitlement, User
from ..module_catalog import LABS_GRACE_DAYS


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def plan_grace(db: Session) -> list[str]:
    """IDs de Elite que hoy no tienen entitlement de Labs."""
    elites = (db.query(User)
              .filter(User.plan_nivel == "elite", User.rol.notin_(("coach", "admin"))).all())
    out = []
    for u in elites:
        has = (db.query(Entitlement)
               .filter(Entitlement.user_id == u.id, Entitlement.addon_id == "labs").first())
        if has is None:
            out.append(u.id)
    return out


def apply_grace(db: Session, now: datetime | None = None) -> int:
    now = now or _now()
    expires = now + timedelta(days=LABS_GRACE_DAYS)
    created = 0
    for uid in plan_grace(db):
        db.add(Entitlement(user_id=uid, addon_id="labs", source="legacy",
                           status="active", expires_at=expires, created_at=now))
        created += 1
    db.commit()
    return created
