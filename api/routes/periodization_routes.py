"""Sprint 31 — Season Periodization routes.

Coach endpoints: full CRUD for athlete training phases + Gantt view.
Athlete endpoint: read-only view of own phases.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import TrainingPhase, User
from ..auth import get_current_user, require_role
from ..permissions import assert_coach_owns_athlete
from ..services.periodization_service import (
    validate_no_overlap,
    _phase_dict,
    build_season_gantt,
    get_athlete_phases,
    VALID_PHASE_TYPES,
)

# ── Schemas ──────────────────────────────────────────────────────────────────

class PhaseCreate(BaseModel):
    phase_type:        str
    label:             Optional[str]    = None
    start_date:        str                     # YYYY-MM-DD
    end_date:          str                     # YYYY-MM-DD
    ctl_target:        Optional[float]  = None
    tss_weekly_target: Optional[float]  = None
    notes:             Optional[str]    = None


class PhaseUpdate(BaseModel):
    phase_type:        Optional[str]    = None
    label:             Optional[str]    = None
    start_date:        Optional[str]    = None
    end_date:          Optional[str]    = None
    ctl_target:        Optional[float]  = None
    tss_weekly_target: Optional[float]  = None
    notes:             Optional[str]    = None


# ── Helpers ──────────────────────────────────────────────────────────────────

_coach   = require_role("coach", "admin")
_athlete = require_role("athlete", "atleta", "coach", "admin")


def _import_uuid():
    import uuid
    return str(uuid.uuid4())


def _validate_phase_create(body: PhaseCreate) -> None:
    if body.phase_type not in VALID_PHASE_TYPES:
        raise HTTPException(400, f"phase_type inválido. Valores válidos: {sorted(VALID_PHASE_TYPES)}")
    if body.start_date >= body.end_date:
        raise HTTPException(400, "start_date debe ser anterior a end_date")


def _get_phase_or_404(phase_id: str, db: Session) -> TrainingPhase:
    ph = db.query(TrainingPhase).filter(TrainingPhase.id == phase_id).first()
    if not ph:
        raise HTTPException(404, "Fase no encontrada")
    return ph


# ── Coach router ─────────────────────────────────────────────────────────────

router = APIRouter(prefix="/coach", tags=["periodization"])


@router.post("/athletes/{athlete_id}/phases", status_code=201)
def create_phase(
    athlete_id: str,
    body: PhaseCreate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Create a training phase for an athlete. Rejects overlapping date ranges."""
    assert_coach_owns_athlete(coach.id, athlete_id, db)
    _validate_phase_create(body)

    ok, err = validate_no_overlap(athlete_id, body.start_date, body.end_date, db)
    if not ok:
        raise HTTPException(409, err)

    import uuid
    ph = TrainingPhase(
        id               = str(uuid.uuid4()),
        coach_id         = coach.id,
        athlete_id       = athlete_id,
        phase_type       = body.phase_type,
        label            = body.label,
        start_date       = body.start_date,
        end_date         = body.end_date,
        ctl_target       = body.ctl_target,
        tss_weekly_target = body.tss_weekly_target,
        notes            = body.notes,
    )
    db.add(ph); db.commit(); db.refresh(ph)
    return _phase_dict(ph)


@router.get("/athletes/{athlete_id}/phases")
def list_athlete_phases(
    athlete_id: str,
    include_gantt: bool = True,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """List all phases for an athlete, with optional Gantt visualization data."""
    assert_coach_owns_athlete(coach.id, athlete_id, db)
    phases = get_athlete_phases(athlete_id, db)
    result: dict = {"phases": phases, "count": len(phases)}
    if include_gantt:
        result["gantt"] = build_season_gantt(athlete_id, db)
    return result


@router.put("/phases/{phase_id}")
def update_phase(
    phase_id: str,
    body: PhaseUpdate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Update an existing phase. Rejects updates that cause overlaps."""
    ph = _get_phase_or_404(phase_id, db)
    if ph.coach_id != coach.id:
        raise HTTPException(403, "No tienes permiso para editar esta fase")

    new_type  = body.phase_type  or ph.phase_type
    new_start = body.start_date  or ph.start_date
    new_end   = body.end_date    or ph.end_date

    if new_type not in VALID_PHASE_TYPES:
        raise HTTPException(400, f"phase_type inválido: {new_type}")
    if new_start >= new_end:
        raise HTTPException(400, "start_date debe ser anterior a end_date")

    ok, err = validate_no_overlap(ph.athlete_id, new_start, new_end, db, exclude_id=phase_id)
    if not ok:
        raise HTTPException(409, err)

    ph.phase_type        = new_type
    ph.start_date        = new_start
    ph.end_date          = new_end
    if body.label            is not None: ph.label             = body.label
    if body.ctl_target       is not None: ph.ctl_target        = body.ctl_target
    if body.tss_weekly_target is not None: ph.tss_weekly_target = body.tss_weekly_target
    if body.notes            is not None: ph.notes             = body.notes

    db.commit(); db.refresh(ph)
    return _phase_dict(ph)


@router.delete("/phases/{phase_id}", status_code=204)
def delete_phase(
    phase_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach),
):
    """Delete a training phase."""
    ph = _get_phase_or_404(phase_id, db)
    if ph.coach_id != coach.id:
        raise HTTPException(403, "No tienes permiso para eliminar esta fase")
    db.delete(ph); db.commit()
    return None


# ── Athlete router ────────────────────────────────────────────────────────────

athlete_router = APIRouter(prefix="/athlete", tags=["periodization"])


@athlete_router.get("/phases")
def get_my_phases(
    db: Session = Depends(get_db),
    me: User = Depends(_athlete),
):
    """Athlete reads their own training phases and season Gantt."""
    return {
        "phases": get_athlete_phases(me.id, db),
        "gantt":  build_season_gantt(me.id, db),
    }
