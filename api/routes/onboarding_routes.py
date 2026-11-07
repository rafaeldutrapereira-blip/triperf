"""
Checklist de primeros pasos (A4) -- estado de solo lectura.

Los 4 booleanos se calculan siempre de datos reales (conexiones, actividades,
plan, perfil); no hay flags guardados. El descarte de la tarjeta ("No mostrar
mas", y el de la tarjeta de historial S-B) vive en el cliente (localStorage),
igual que los demas descartes de la app. Sin gating de plan: lo ve todo atleta.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import (
    AssignedWorkout, GarminActivity, GarminOAuthToken, GarminPlannedWorkout,
    OwnPlanSession, ProviderConnection, User,
)

router = APIRouter(prefix="/onboarding", tags=["onboarding"])

# Mismos campos que el medidor "Perfil completo" de athlete_profile.html
# (PROFILE_FIELDS): si cambia uno, cambiar el otro.
_PROFILE_CHECKS = {
    "ftp":       lambda u: (u.ftp or 0) > 0,
    "weight_kg": lambda u: (u.weight_kg or 0) > 0,
    "fcmax":     lambda u: (u.fcmax or 0) > 0,
    "css":       lambda u: bool((u.css or "").strip()),
    "run_pace":  lambda u: bool((u.run_pace or "").strip()),
    "sexo":      lambda u: u.sexo in ("f", "m"),
}


def _exists(db: Session, q) -> bool:
    return db.query(q.exists()).scalar() is True


def _has_connection(db: Session, me: User) -> bool:
    """Alguna conexion activa: Garmin oficial/legacy, intervals.icu, Strava, Polar/Wahoo."""
    if me.intervals_access_token or me.strava_access_token:
        return True
    if me.garmin_email and me.garmin_password:
        return True
    if _exists(db, db.query(GarminOAuthToken.id).filter(GarminOAuthToken.user_id == me.id)):
        return True
    return _exists(db, db.query(ProviderConnection.id).filter(ProviderConnection.user_id == me.id))


def _has_plan(db: Session, me: User) -> bool:
    today = date.today().isoformat()
    if _exists(db, db.query(OwnPlanSession.id).filter(OwnPlanSession.user_id == me.id)):
        return True
    if _exists(db, db.query(GarminPlannedWorkout.id).filter(
            GarminPlannedWorkout.user_id == me.id, GarminPlannedWorkout.date_iso >= today)):
        return True
    return _exists(db, db.query(AssignedWorkout.id).filter(
        AssignedWorkout.athlete_id == me.id, AssignedWorkout.date_iso >= today,
        AssignedWorkout.deleted_at.is_(None)))


@router.get("/status")
def onboarding_status(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    missing = [k for k, ok in _PROFILE_CHECKS.items() if not ok(me)]
    n_act = db.query(func.count(GarminActivity.id)).filter(GarminActivity.user_id == me.id).scalar() or 0
    steps = {
        "connect": _has_connection(db, me),
        "history": n_act > 0,
        "plan": _has_plan(db, me),
        "profile": not missing,
    }
    return {
        "steps": steps,
        "all_done": all(steps.values()),
        "profile_missing": missing,
        "activities_count": n_act,
    }
