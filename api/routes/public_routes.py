"""
LabX — Endpoints PÚBLICOS (sin autenticación).

Esta es la única superficie de la API pensada para ser accedida sin login
— igual que un link de "compartir" de Google Docs: no hay nada indexable
ni listable, solo se puede ver una actividad puntual si se tiene el token
opaco exacto de esa actividad (generado explícitamente por su dueño desde
POST /athlete/activities/{id}/share). Mantenido en un archivo separado a
propósito para que sea fácil de auditar qué es realmente público en LabX
sin tener que revisar decorators de auth en 30 routers distintos.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import GarminActivity, TrainingPlan, User

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/activities/{token}")
def get_public_activity(token: str, db: Session = Depends(get_db)):
    """
    Devuelve un subconjunto público-seguro de una actividad compartida.
    Respeta las preferencias de privacidad del dueño (share_route/hr/power/
    pace) — el link público NUNCA muestra más de lo que ese atleta ya
    aceptó compartir con sus seguidores.
    """
    from .athlete_routes import _get_share_prefs
    from .community_routes import _route_preview_for_activity, _avatar_url

    act = db.query(GarminActivity).filter(GarminActivity.share_token == token).first()
    if not act:
        raise HTTPException(404, "Este link no existe o fue revocado por su dueño")

    owner = db.query(User).filter(User.id == act.user_id).first()
    prefs = _get_share_prefs(owner) if owner else {}

    return {
        "name":        act.name,
        "sport":       act.sport,
        "date_iso":    act.date_iso,
        "date_label":  act.date_label,
        "dur_min":     act.dur_min,
        "dist_km":     act.dist_km,
        "elev_m":      act.elev_m,
        "avg_hr":      act.avg_hr    if prefs.get("share_hr", True)    else None,
        "avg_power":   act.avg_power if prefs.get("share_power", True) else None,
        "pace_str":    act.pace_str  if prefs.get("share_pace", True)  else None,
        "swim_pace":   act.swim_pace if prefs.get("share_pace", True)  else None,
        "tss":         act.tss,
        "calories":    act.calories,
        "route_preview": _route_preview_for_activity(act.activity_id) if prefs.get("share_route", True) else None,
        "owner": {
            "name":       (owner.nombre or owner.email.split("@")[0]) if owner else "Atleta LabX",
            "avatar_url": _avatar_url(owner) if owner else None,
        },
    }


@router.get("/plans/{token}")
def get_public_plan(token: str, db: Session = Depends(get_db)):
    """
    Vista de solo lectura de un plan compartido (M4). Solo prescripcion:
    nunca expone athlete_id, notas/feedback del atleta ni resultados reales.
    Del dueño solo el nombre.
    """
    plan = db.query(TrainingPlan).filter(TrainingPlan.share_token == token).first()
    if not plan:
        raise HTTPException(404, "Este link no existe o fue revocado por su dueño")

    owner = db.query(User).filter(User.id == plan.coach_id).first()
    weeks: dict = {}
    for s in plan.sessions:
        wn = s.week_number or 1
        weeks.setdefault(wn, []).append({
            "day_of_week":  s.day_of_week if s.day_of_week is not None else 0,
            "sport":        s.sport,
            "title":        s.title,
            "description":  s.description,
            "duration_min": s.duration_min,
            "distance_km":  s.distance_km,
            "tss_planned":  s.tss_planned,
            "zone":         s.zone,
            "intensity":    s.intensity,
            "coach_note":   s.coach_note,
        })
    return {
        "name":        plan.template_name or plan.name,
        "description": plan.description,
        "weeks":       plan.weeks,
        "goal_ctl":    plan.goal_ctl,
        "peak_week":   plan.peak_week,
        "total_sessions": len(plan.sessions),
        "total_tss":   round(sum(x.tss_planned or 0 for x in plan.sessions), 1),
        "sessions_by_week": {
            str(wn): sorted(items, key=lambda i: i["day_of_week"])
            for wn, items in sorted(weeks.items())
        },
        "owner": {"name": (owner.nombre or owner.email.split("@")[0]) if owner else "LabX"},
    }
