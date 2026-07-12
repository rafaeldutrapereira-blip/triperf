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
from .models import User

_PLAN_FEATURES: dict[str, set[str]] = {
    "basico": {"dashboard", "athlete_profile"},
    "agegroup": {
        "dashboard", "athlete_profile",
        "training_plan", "nutrition", "analytics", "recovery", "mental",
        "race_day", "race_predictor", "community", "year_in_review",
    },
    "elite": {
        "dashboard", "athlete_profile",
        "training_plan", "nutrition", "analytics", "recovery", "mental",
        "race_day", "race_predictor", "community", "year_in_review",
        "blood_labs", "training_detail", "adaptive", "ai_coach", "indoor_workout",
    },
}
# "coach" no es un nivel de acceso real (has_feature() ya da acceso total
# a rol=coach/admin sin mirar plan_nivel) — esta entrada solo existe para
# listar el catálogo de suscripciones en /stripe/plans.
_PLAN_FEATURES["coach"] = _PLAN_FEATURES["elite"] | {"coach_platform", "athlete_management"}


def has_feature(user: User, feature: str) -> bool:
    """Verifica si el usuario tiene acceso a una feature según su plan."""
    if user.rol in ("coach", "admin"):
        return True
    plan = (user.plan_nivel or "basico").lower()
    allowed = _PLAN_FEATURES.get(plan, _PLAN_FEATURES["basico"])
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
