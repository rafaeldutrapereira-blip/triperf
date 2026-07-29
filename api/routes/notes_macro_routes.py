"""
Endpoints: Notas del coach por atleta + Macrociclos
"""
from __future__ import annotations

from datetime import date as _date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, GroupMember, WorkoutTemplate,
    AssignedWorkout, WeekTemplate, WeekTemplateDay,
    AthleteNote, Macrocycle, MacrocycleWeek,
)
from ..schemas import (
    AthleteNoteCreate, AthleteNoteOut,
    MacrocycleCreate, MacrocycleWeekCreate,
    MacrocycleOut, MacrocycleWeekOut,
    ApplyMacrocycleRequest,
)
from ..auth import require_role
from ..permissions import assert_coach_owns_athlete

router = APIRouter(prefix="/coach", tags=["coach-notes-macro"])
_coach = require_role("coach", "admin")


# ══════════════════════════════════════════════════════════════
# NOTAS DEL COACH POR ATLETA
# ══════════════════════════════════════════════════════════════

TIPO_ICONS = {
    "observacion": "📝",
    "lesion":      "🩹",
    "meta":        "🎯",
    "carrera":     "🏁",
}


@router.get("/athletes/{athlete_id}/notes", response_model=List[AthleteNoteOut])
def list_athlete_notes(
    athlete_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    notes = (
        db.query(AthleteNote)
        .filter(
            AthleteNote.coach_id   == coach.id,
            AthleteNote.athlete_id == athlete_id,
        )
        .order_by(AthleteNote.fecha.desc(), AthleteNote.created_at.desc())
        .all()
    )
    return [AthleteNoteOut(
        id=n.id, tipo=n.tipo, texto=n.texto, fecha=n.fecha,
        created_at=str(n.created_at)[:10] if n.created_at else None
    ) for n in notes]


@router.post("/athletes/{athlete_id}/notes", response_model=AthleteNoteOut, status_code=201)
def create_athlete_note(
    athlete_id: str,
    body: AthleteNoteCreate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    athlete = assert_coach_owns_athlete(coach.id, athlete_id, db)
    note = AthleteNote(
        coach_id   = coach.id,
        athlete_id = athlete_id,
        tipo       = body.tipo,
        texto      = body.texto,
        fecha      = body.fecha,
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return AthleteNoteOut(id=note.id, tipo=note.tipo, texto=note.texto, fecha=note.fecha)


@router.delete("/athletes/{athlete_id}/notes/{note_id}", status_code=204)
def delete_athlete_note(
    athlete_id: str,
    note_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    note = db.query(AthleteNote).filter(
        AthleteNote.id         == note_id,
        AthleteNote.athlete_id == athlete_id,
        AthleteNote.coach_id   == coach.id,
    ).first()
    if not note:
        raise HTTPException(404, "Nota no encontrada")
    db.delete(note)
    db.commit()


# ══════════════════════════════════════════════════════════════
# MACROCICLOS
# ══════════════════════════════════════════════════════════════

def _mc_to_out(mc: Macrocycle) -> MacrocycleOut:
    weeks = [
        MacrocycleWeekOut(
            id               = w.id,
            position         = w.position,
            week_template_id = w.week_template_id,
            week_nombre      = w.week_template.nombre,
            notas            = w.notas,
        )
        for w in mc.weeks
    ]
    return MacrocycleOut(
        id=mc.id, nombre=mc.nombre, descripcion=mc.descripcion, weeks=weeks
    )


@router.get("/macrocycles", response_model=List[MacrocycleOut])
def list_macrocycles(db: Session = Depends(get_db), coach: User = Depends(_coach)):
    mcs = (
        db.query(Macrocycle)
        .filter(Macrocycle.coach_id == coach.id)
        .order_by(Macrocycle.created_at.desc())
        .all()
    )
    return [_mc_to_out(mc) for mc in mcs]


@router.post("/macrocycles", response_model=MacrocycleOut, status_code=201)
def create_macrocycle(
    body: MacrocycleCreate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    mc = Macrocycle(coach_id=coach.id, nombre=body.nombre, descripcion=body.descripcion)
    db.add(mc)
    db.commit()
    db.refresh(mc)
    return _mc_to_out(mc)


@router.delete("/macrocycles/{mc_id}", status_code=204)
def delete_macrocycle(
    mc_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    mc = db.query(Macrocycle).filter(
        Macrocycle.id == mc_id, Macrocycle.coach_id == coach.id
    ).first()
    if not mc:
        raise HTTPException(404, "Macrociclo no encontrado")
    db.delete(mc)
    db.commit()


@router.post("/macrocycles/{mc_id}/weeks", response_model=MacrocycleWeekOut, status_code=201)
def add_macrocycle_week(
    mc_id: str,
    body: MacrocycleWeekCreate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    mc = db.query(Macrocycle).filter(
        Macrocycle.id == mc_id, Macrocycle.coach_id == coach.id
    ).first()
    if not mc:
        raise HTTPException(404, "Macrociclo no encontrado")
    wt = db.query(WeekTemplate).filter(WeekTemplate.id == body.week_template_id).first()
    if not wt:
        raise HTTPException(404, "Semana tipo no encontrada")

    next_pos = (max((w.position for w in mc.weeks), default=0) + 1)
    mw = MacrocycleWeek(
        macrocycle_id    = mc_id,
        position         = next_pos,
        week_template_id = body.week_template_id,
        notas            = body.notas,
    )
    db.add(mw)
    db.commit()
    db.refresh(mw)
    return MacrocycleWeekOut(
        id=mw.id, position=mw.position,
        week_template_id=mw.week_template_id,
        week_nombre=wt.nombre, notas=mw.notas,
    )


@router.delete("/macrocycles/{mc_id}/weeks/{mw_id}", status_code=204)
def remove_macrocycle_week(
    mc_id: str, mw_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    mw = db.query(MacrocycleWeek).filter(
        MacrocycleWeek.id == mw_id,
        MacrocycleWeek.macrocycle_id == mc_id,
    ).first()
    if not mw:
        raise HTTPException(404, "Semana no encontrada")
    db.delete(mw)
    db.commit()


@router.post("/macrocycles/{mc_id}/apply")
def apply_macrocycle(
    mc_id: str,
    body: ApplyMacrocycleRequest,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """
    Aplica el macrociclo a partir de start_date (lunes).
    Cada semana tipo se aplica en la semana consecutiva siguiente.
    """
    mc = db.query(Macrocycle).filter(
        Macrocycle.id == mc_id, Macrocycle.coach_id == coach.id
    ).first()
    if not mc:
        raise HTTPException(404, "Macrociclo no encontrado")
    if not mc.weeks:
        raise HTTPException(400, "El macrociclo no tiene semanas configuradas")
    if not body.athlete_id and not body.group_id:
        raise HTTPException(400, "Debes especificar athlete_id o group_id")

    start = _date.fromisoformat(body.start_date)
    total_created = 0
    total_synced  = 0

    try:
        from garmin_connector import schedule_workout_for_athlete as _sync_garmin
        has_sync_fn = True
    except ImportError:
        has_sync_fn = False

    for mc_week in mc.weeks:
        week_start = start + timedelta(weeks=mc_week.position - 1)
        wt = mc_week.week_template
        if not wt or not wt.days:
            continue

        for day in wt.days:
            target_date = (week_start + timedelta(days=day.day_of_week)).isoformat()
            a = AssignedWorkout(
                template_id = day.workout_template_id,
                athlete_id  = body.athlete_id,
                group_id    = body.group_id,
                date_iso    = target_date,
                notas       = day.notas,
            )
            db.add(a)
            total_created += 1

            if body.sync_garmin and has_sync_fn:
                db.flush()
                tpl = day.workout
                athletes_to_sync: list = []
                if body.athlete_id:
                    ath = db.query(User).filter(User.id == body.athlete_id).first()
                    if ath:
                        athletes_to_sync.append(ath)
                elif body.group_id:
                    members = (
                        db.query(User)
                        .join(GroupMember, GroupMember.athlete_id == User.id)
                        .filter(GroupMember.group_id == body.group_id, User.activo == True)
                        .all()
                    )
                    athletes_to_sync.extend(members)
                for ath in athletes_to_sync:
                    if ath.garmin_email and ath.garmin_password:
                        try:
                            from ..crypto import decrypt_credential
                            _sync_garmin(
                                session={
                                    "name": tpl.nombre, "sport": tpl.sport,
                                    "dur_min": tpl.dur_min, "dist_km": tpl.dist_km,
                                    "notes": tpl.notas or "",
                                    "blocks_json": tpl.blocks_json, "ftp": ath.ftp,
                                    "fcmax": ath.fcmax,
                                },
                                target_date=target_date,
                                athlete_id=ath.id,
                                athlete_email=ath.garmin_email,
                                athlete_password=decrypt_credential(ath.garmin_password),
                            )
                            total_synced += 1
                        except Exception:
                            pass

    db.commit()

    end_date = (start + timedelta(weeks=len(mc.weeks)) - timedelta(days=1)).isoformat()
    return {
        "macrocycle":    mc.nombre,
        "weeks_applied": len(mc.weeks),
        "created":       total_created,
        "synced_garmin": total_synced,
        "period_start":  body.start_date,
        "period_end":    end_date,
    }
