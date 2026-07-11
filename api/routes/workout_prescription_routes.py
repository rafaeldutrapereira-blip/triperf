"""Workout Prescription routes — coach writes structured workouts, athletes execute + feedback."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import WorkoutPrescription, PrescriptionFeedback, User
from .auth_routes import get_current_user

router = APIRouter(tags=["prescriptions"])


def _new_id() -> str:
    return str(uuid.uuid4())


# ── Schemas ───────────────────────────────────────────────────────────────────

class PrescriptionCreate(BaseModel):
    athlete_id: str
    title: str
    description: Optional[str] = None
    sport: str = "run"
    date_iso: str
    duration_min: Optional[int] = None
    tss_target: Optional[float] = None
    structure_json: Optional[str] = None


class FeedbackCreate(BaseModel):
    rpe: Optional[int] = None
    notes: Optional[str] = None
    actual_duration_min: Optional[int] = None
    tss_actual: Optional[float] = None


class SkipRequest(BaseModel):
    reason: Optional[str] = None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rx_dict(rx: WorkoutPrescription) -> dict:
    fb = rx.feedback
    return {
        "id": rx.id,
        "coach_id": rx.coach_id,
        "athlete_id": rx.athlete_id,
        "title": rx.title,
        "description": rx.description,
        "sport": rx.sport,
        "date_iso": rx.date_iso,
        "duration_min": rx.duration_min,
        "tss_target": rx.tss_target,
        "structure_json": rx.structure_json,
        "status": rx.status,
        "prescribed_at": rx.prescribed_at.isoformat() if rx.prescribed_at else None,
        "completed_at": rx.completed_at.isoformat() if rx.completed_at else None,
        "feedback": {
            "rpe": fb.rpe,
            "notes": fb.notes,
            "actual_duration_min": fb.actual_duration_min,
            "tss_actual": fb.tss_actual,
            "feedback_at": fb.feedback_at.isoformat() if fb.feedback_at else None,
        } if fb else None,
    }


# ── Coach endpoints ───────────────────────────────────────────────────────────

@router.post("/coach/prescriptions", status_code=201)
def create_prescription(
    body: PrescriptionCreate,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Coach creates a workout prescription for an athlete."""
    rx = WorkoutPrescription(
        id=_new_id(),
        coach_id=me.id,
        athlete_id=body.athlete_id,
        title=body.title,
        description=body.description,
        sport=body.sport,
        date_iso=body.date_iso,
        duration_min=body.duration_min,
        tss_target=body.tss_target,
        structure_json=body.structure_json,
        status="pending",
        prescribed_at=datetime.now(timezone.utc).replace(tzinfo=None),
    )
    db.add(rx)
    db.commit()
    db.refresh(rx)
    return _rx_dict(rx)


@router.get("/coach/prescriptions")
def list_coach_prescriptions(
    athlete_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None),
    date_to: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Coach lists prescriptions they authored (filterable by athlete, date range, status)."""
    q = db.query(WorkoutPrescription).filter(WorkoutPrescription.coach_id == me.id)
    if athlete_id:
        q = q.filter(WorkoutPrescription.athlete_id == athlete_id)
    if date_from:
        q = q.filter(WorkoutPrescription.date_iso >= date_from)
    if date_to:
        q = q.filter(WorkoutPrescription.date_iso <= date_to)
    if status:
        q = q.filter(WorkoutPrescription.status == status)
    rows = q.order_by(WorkoutPrescription.date_iso.desc()).limit(limit).all()
    return {"prescriptions": [_rx_dict(r) for r in rows], "total": len(rows)}


@router.get("/coach/prescriptions/{rx_id}/feedback")
def get_prescription_feedback(
    rx_id: str,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Coach views athlete feedback on a specific prescription."""
    rx = db.query(WorkoutPrescription).filter(
        WorkoutPrescription.id == rx_id,
        WorkoutPrescription.coach_id == me.id,
    ).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return _rx_dict(rx)


# ── Athlete endpoints ─────────────────────────────────────────────────────────

@router.get("/athlete/prescriptions")
def list_athlete_prescriptions(
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=30, ge=1, le=100),
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Athlete sees pending and recent prescriptions from their coach."""
    q = db.query(WorkoutPrescription).filter(WorkoutPrescription.athlete_id == me.id)
    if status:
        q = q.filter(WorkoutPrescription.status == status)
    rows = q.order_by(WorkoutPrescription.date_iso.desc()).limit(limit).all()
    pending = [r for r in rows if r.status == "pending"]
    recent  = [r for r in rows if r.status != "pending"]
    return {
        "pending": [_rx_dict(r) for r in pending],
        "recent":  [_rx_dict(r) for r in recent],
        "total":   len(rows),
    }


@router.get("/athlete/prescriptions/{rx_id}")
def get_prescription_detail(
    rx_id: str,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Athlete views a single prescription detail."""
    rx = db.query(WorkoutPrescription).filter(
        WorkoutPrescription.id == rx_id,
        WorkoutPrescription.athlete_id == me.id,
    ).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    return _rx_dict(rx)


@router.put("/athlete/prescriptions/{rx_id}/complete")
def complete_prescription(
    rx_id: str,
    body: FeedbackCreate,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Athlete marks prescription completed and submits feedback."""
    rx = db.query(WorkoutPrescription).filter(
        WorkoutPrescription.id == rx_id,
        WorkoutPrescription.athlete_id == me.id,
    ).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if rx.status == "completed":
        raise HTTPException(status_code=400, detail="Already completed")

    rx.status = "completed"
    rx.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)

    has_feedback = any(v is not None for v in [body.rpe, body.notes, body.actual_duration_min, body.tss_actual])
    if has_feedback:
        db.add(PrescriptionFeedback(
            id=_new_id(),
            prescription_id=rx.id,
            athlete_id=me.id,
            rpe=body.rpe,
            notes=body.notes,
            actual_duration_min=body.actual_duration_min,
            tss_actual=body.tss_actual,
            feedback_at=datetime.now(timezone.utc).replace(tzinfo=None),
        ))

    db.commit()
    db.refresh(rx)
    return _rx_dict(rx)


@router.put("/athlete/prescriptions/{rx_id}/skip")
def skip_prescription(
    rx_id: str,
    body: SkipRequest,
    me: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Athlete marks a pending prescription as skipped."""
    rx = db.query(WorkoutPrescription).filter(
        WorkoutPrescription.id == rx_id,
        WorkoutPrescription.athlete_id == me.id,
    ).first()
    if not rx:
        raise HTTPException(status_code=404, detail="Prescription not found")
    if rx.status != "pending":
        raise HTTPException(status_code=400, detail="Only pending prescriptions can be skipped")

    rx.status = "skipped"
    if body.reason:
        rx.description = (rx.description or "") + f"\n[Skipped: {body.reason}]"
    db.commit()
    db.refresh(rx)
    return _rx_dict(rx)
