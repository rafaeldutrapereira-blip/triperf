"""Sprint 33 — Training Plan Templates routes."""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..auth import get_current_user, require_role
from ..permissions import assert_coach_owns_athlete
from ..services.template_service import (
    VALID_SPORTS,
    VALID_DISTANCES,
    VALID_DIFFICULTY,
    VALID_PHASES,
    BUILTIN_TEMPLATES,
    list_templates,
    get_template,
    create_template,
    update_template,
    delete_template,
    assign_template_to_athlete,
    compliance_trend,
)

# ── Schemas ───────────────────────────────────────────────────────────────────

class SessionStub(BaseModel):
    sport:        str
    title:        str
    duration_min: Optional[int]   = None
    tss:          Optional[float] = None
    zone:         Optional[str]   = None


class TemplateWeekIn(BaseModel):
    week_num:     int
    phase_type:   Optional[str]         = None
    label:        Optional[str]         = None
    tss_target:   Optional[float]       = None
    hours_target: Optional[float]       = None
    sessions:     list[SessionStub]     = []
    notes:        Optional[str]         = None

    @field_validator("phase_type")
    @classmethod
    def _chk_phase(cls, v):
        if v and v not in VALID_PHASES:
            raise ValueError(f"phase_type inválido: {v}")
        return v


class TemplateCreate(BaseModel):
    name:          str
    sport:         str              = "triathlon"
    distance_type: Optional[str]   = None
    difficulty:    Optional[str]   = None
    description:   Optional[str]   = None
    is_public:     bool            = False
    plan_weeks:    list[TemplateWeekIn] = []

    @field_validator("sport")
    @classmethod
    def _chk_sport(cls, v):
        if v not in VALID_SPORTS:
            raise ValueError(f"sport inválido")
        return v


class TemplateUpdate(BaseModel):
    name:          Optional[str]  = None
    sport:         Optional[str]  = None
    distance_type: Optional[str]  = None
    difficulty:    Optional[str]  = None
    description:   Optional[str]  = None
    is_public:     Optional[bool] = None


class AssignBody(BaseModel):
    athlete_id: str
    start_date: str    # YYYY-MM-DD (Monday of W1)


# ── Helpers ───────────────────────────────────────────────────────────────────

_coach   = require_role("coach", "admin")
_athlete = require_role("atleta", "coach", "admin")


# ── Coach router ──────────────────────────────────────────────────────────────

router = APIRouter(prefix="/coach", tags=["templates"])


@router.get("/templates")
def coach_list_templates(
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """List built-in templates + coach's own templates."""
    return list_templates(coach.id, db)


@router.post("/templates", status_code=201)
def coach_create_template(
    body: TemplateCreate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Create a new training plan template."""
    if not body.plan_weeks:
        raise HTTPException(400, "Se requiere al menos 1 semana en plan_weeks")
    return create_template(coach.id, body.model_dump(), db)


@router.get("/templates/{template_id}")
def coach_get_template(
    template_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Get full template detail including week structure."""
    t = get_template(template_id, coach.id, db)
    if not t:
        raise HTTPException(404, "Plantilla no encontrada")
    return t


@router.put("/templates/{template_id}")
def coach_update_template(
    template_id: str,
    body: TemplateUpdate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Update metadata of a coach-authored template (built-ins are immutable)."""
    # Reject attempt to edit built-in
    if any(bt["id"] == template_id for bt in BUILTIN_TEMPLATES):
        raise HTTPException(403, "Las plantillas integradas no se pueden editar")
    t = update_template(template_id, coach.id, body.model_dump(exclude_none=True), db)
    if not t:
        raise HTTPException(404, "Plantilla no encontrada o no pertenece a este coach")
    return t


@router.delete("/templates/{template_id}", status_code=204)
def coach_delete_template(
    template_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Delete a coach-authored template (built-ins cannot be deleted)."""
    if any(bt["id"] == template_id for bt in BUILTIN_TEMPLATES):
        raise HTTPException(403, "Las plantillas integradas no se pueden eliminar")
    if not delete_template(template_id, coach.id, db):
        raise HTTPException(404, "Plantilla no encontrada o no pertenece a este coach")


@router.post("/templates/{template_id}/assign", status_code=201)
def coach_assign_template(
    template_id: str,
    body: AssignBody,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Expand template into WorkoutPrescriptions + TrainingPhases for an athlete."""
    assert_coach_owns_athlete(coach.id, body.athlete_id, db)
    result = assign_template_to_athlete(
        template_id  = template_id,
        athlete_id   = body.athlete_id,
        coach_id     = coach.id,
        start_date   = body.start_date,
        db           = db,
    )
    if result.get("error") == "template_not_found":
        raise HTTPException(404, "Plantilla no encontrada")
    return result


@router.get("/athletes/{athlete_id}/compliance-trend")
def coach_compliance_trend(
    athlete_id: str,
    weeks: int = Query(12, ge=1, le=52),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Weekly compliance trend for a specific athlete (last N weeks)."""
    assert_coach_owns_athlete(coach.id, athlete_id, db)
    return compliance_trend(athlete_id, weeks, db)


@router.get("/squad/compliance-trend")
def squad_compliance_trend(
    weeks: int = Query(4, ge=1, le=52),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Squad-level compliance trend: one entry per athlete, sorted by avg pct ascending."""
    from ..models import Group, GroupMember
    athlete_ids = [
        row.athlete_id
        for row in (
            db.query(GroupMember.athlete_id)
            .join(Group, Group.id == GroupMember.group_id)
            .filter(Group.coach_id == coach.id)
            .distinct()
            .all()
        )
    ]
    result = []
    for aid in athlete_ids:
        athlete = db.query(User).filter(User.id == aid).first()
        trend_weeks = compliance_trend(aid, weeks, db)
        filled = [w for w in trend_weeks if w.get("compliance_pct") is not None]
        avg_pct = round(sum(w["compliance_pct"] for w in filled) / len(filled), 1) if filled else None
        result.append({
            "athlete_id":   aid,
            "athlete_name": getattr(athlete, "nombre", aid) if athlete else aid,
            "average_pct":  avg_pct,
            "trend":        trend_weeks,
        })
    result.sort(key=lambda x: (x["average_pct"] is None, x["average_pct"] or 0))
    return {"coach_id": coach.id, "weeks": weeks, "athletes": result}


# ── Athlete router ────────────────────────────────────────────────────────────

athlete_router = APIRouter(prefix="/athlete", tags=["templates"])


@athlete_router.get("/compliance-trend")
def athlete_compliance_trend(
    weeks: int = Query(8, ge=1, le=52),
    db: Session = Depends(get_db),
    me: User = Depends(_athlete),
):
    """Athlete's own weekly compliance trend."""
    return compliance_trend(me.id, weeks, db)
