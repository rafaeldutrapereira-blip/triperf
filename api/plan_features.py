"""
LabX — Feature gating por plan (basico | agegroup | elite).

Única fuente de verdad para qué feature requiere qué plan del lado del
servidor. Debe mantenerse alineada con los `minPlan` de routes.config.js
(el gating del sidebar) — si se agrega un módulo nuevo ahí, agregar
también su feature acá para que la API quede realmente protegida y no
solo el link del sidebar.

Coach y admin bypasean el gating de plan por completo: gestionan atletas
independientemente de qué plan de "atleta" tengan contratado para sí
mismos (decisión de producto — ver memoria project-labx-plan-gating).
"""
from __future__ import annotations

from fastapi import Depends, HTTPException

from .auth import get_current_user
from .free_limits import free_limits_enabled
from .module_catalog import ADDON_FEATURES, addons_enabled
from .models import User

_PLAN_FEATURES: dict[str, set[str]] = {
    "basico": {"dashboard", "athlete_profile"},
    "agegroup": {
        "dashboard", "athlete_profile",
        "training_plan", "nutrition", "analytics", "recovery", "mental",
        "race_day", "race_predictor", "community", "community_write", "year_in_review", "gear",
        "calendar", "periodization",
    },
    "elite": {
        "dashboard", "athlete_profile",
        "training_plan", "nutrition", "analytics", "recovery", "mental",
        "race_day", "race_predictor", "community", "community_write", "year_in_review", "gear",
        "calendar", "periodization",
        "blood_labs", "training_detail", "adaptive", "ai_coach", "indoor_workout",
    },
}
# "coach" no es un nivel de acceso real (has_feature() ya da acceso total
# a rol=coach/admin sin mirar plan_nivel) — esta entrada solo existe para
# listar el catálogo de suscripciones en /stripe/plans.
_PLAN_FEATURES["coach"] = _PLAN_FEATURES["elite"] | {"coach_platform", "athlete_management"}


def normalize_plan(plan: str | None) -> str:
    """Nombre canónico del plan en BD. El cliente usa 'basic'; la BD guarda 'basico'."""
    p = (plan or "basico").lower()
    return "basico" if p == "basic" else p


def entitlement_features(user: User) -> set[str]:
    """Features desbloqueadas por addons vigentes (purchase, legacy o trial)."""
    from datetime import datetime, timezone
    from sqlalchemy.orm import object_session
    db = object_session(user) if user is not None else None
    if db is None or getattr(user, "id", None) is None:
        return set()
    from .models import Entitlement
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = (db.query(Entitlement)
            .filter(Entitlement.user_id == user.id, Entitlement.status.in_(("active", "canceled")))
            .all())
    out: set[str] = set()
    for e in rows:
        if e.expires_at is not None and e.expires_at <= now:
            continue
        out |= ADDON_FEATURES.get(e.addon_id, set())
    return out


def has_feature(user: User, feature: str) -> bool:
    """Verifica si el usuario tiene acceso a una feature según su plan."""
    if user.rol in ("coach", "admin"):
        return True
    if feature in entitlement_features(user):
        return True
    plan = normalize_plan(user.plan_nivel)
    allowed = _PLAN_FEATURES.get(plan, _PLAN_FEATURES["basico"])
    # B12: con addons activos, Labs deja de venir en Elite (sale por gracia o por addon).
    if feature == "blood_labs" and plan == "elite" and addons_enabled():
        return False
    # B11 (flag): Free accede al plan de entrenamiento, limitado a la semana actual.
    if feature == "training_plan" and plan == "basico" and free_limits_enabled():
        return True
    return feature in allowed


def require_feature(feature: str):
    """FastAPI dependency — lanza 403 si el usuario no tiene la feature."""
    def _check(user: User = Depends(get_current_user)) -> User:
        if not has_feature(user, feature):
            raise HTTPException(
                status_code=403,
                detail=f"Tu plan '{user.plan_nivel or 'basico'}' no incluye '{feature}'. Actualiza tu suscripción.",
            )
        return user
    return _check
