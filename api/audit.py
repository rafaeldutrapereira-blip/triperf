"""
Audit logging helpers para LabX.
Registra acciones sensibles en la tabla audit_logs.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .models import AuditLog

# Acciones auditables (constantes para evitar typos en llamadas)
class Action:
    LOGIN_OK        = "auth.login.success"
    LOGIN_FAIL      = "auth.login.failed"
    LOGOUT          = "auth.logout"
    REGISTER        = "auth.register"
    PWD_CHANGE      = "auth.password.change"
    PWD_RESET_REQ   = "auth.password.reset.request"
    PWD_RESET_DONE  = "auth.password.reset.done"
    REVOKE_ALL      = "auth.revoke_all"
    DELETE_ACCOUNT  = "auth.account.delete"
    WORKOUT_ASSIGN  = "coach.workout.assign"
    WORKOUT_UNASSIGN= "coach.workout.unassign"
    ATHLETE_VIEW    = "coach.athlete.view"
    BLOOD_LAB_VIEW  = "athlete.blood_lab.view"
    GARMIN_SYNC     = "athlete.garmin.sync"
    TOTP_ENABLE     = "auth.2fa.enable"
    TOTP_DISABLE    = "auth.2fa.disable"


def audit(
    db:       Session,
    action:   str,
    *,
    user_id:  str | None = None,
    ip:       str | None = None,
    user_agent: str | None = None,
    resource: str | None = None,
    detail:   dict[str, Any] | None = None,
    success:  bool = True,
) -> None:
    """Escribe una entrada en audit_logs. No lanza excepciones para no interrumpir el flujo."""
    try:
        entry = AuditLog(
            user_id=user_id,
            action=action,
            ip=ip,
            user_agent=user_agent,
            resource=resource,
            detail=json.dumps(detail, default=str) if detail else None,
            success=success,
        )
        db.add(entry)
        db.commit()
    except Exception:
        # Nunca debe bloquear la operación principal
        try:
            db.rollback()
        except Exception:
            pass


def ip_from_request(request) -> str | None:
    """Extrae IP real del cliente, respetando X-Forwarded-For de proxies."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return getattr(request.client, "host", None) if request.client else None
