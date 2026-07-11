"""
Endpoints: Semanas Tipo (Week Templates) + Calendario
"""
from __future__ import annotations

import copy
from collections import defaultdict
from datetime import date as _date, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Group, GroupMember, WorkoutTemplate,
    AssignedWorkout, WeekTemplate, WeekTemplateDay,
    AthleteNote, Macrocycle, MacrocycleWeek,
)
from ..schemas import (
    WeekTemplateCreate, WeekTemplateDayCreate,
    WeekTemplateOut, WeekTemplateDayOut,
    ApplyWeekTemplateRequest,
    CalendarDay, CalendarAthleteDay,
    AssignedWorkoutOut, WorkoutTemplateOut,
    AthleteNoteCreate, AthleteNoteOut,
    MacrocycleCreate, MacrocycleWeekCreate,
    MacrocycleOut, MacrocycleWeekOut,
    ApplyMacrocycleRequest,
)
from ..auth import require_role
from ..permissions import assert_coach_owns_athlete

router = APIRouter(prefix="/coach", tags=["coach-plan"])
_coach = require_role("coach", "admin")


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def _wt_to_out(wt: WeekTemplate) -> WeekTemplateOut:
    days = []
    for d in wt.days:
        days.append(WeekTemplateDayOut(
            id                  = d.id,
            day_of_week         = d.day_of_week,
            workout_template_id = d.workout_template_id,
            workout_nombre      = d.workout.nombre,
            workout_sport       = d.workout.sport,
            workout_dur_min     = d.workout.dur_min,
            workout_dist_km     = d.workout.dist_km,
            workout_tss         = d.workout.tss,
            notas               = d.notas,
        ))
    return WeekTemplateOut(
        id=wt.id, nombre=wt.nombre, descripcion=wt.descripcion, days=days
    )


def _assign_to_out(a: AssignedWorkout) -> AssignedWorkoutOut:
    return AssignedWorkoutOut(
        id=a.id, date_iso=a.date_iso, created_at=a.created_at,
        athlete_id=a.athlete_id, group_id=a.group_id, notas=a.notas,
        template=WorkoutTemplateOut(
            id=a.template.id, coach_id=a.template.coach_id,
            sport=a.template.sport, nombre=a.template.nombre,
            dur_min=a.template.dur_min, dist_km=a.template.dist_km,
            tss=a.template.tss, notas=a.template.notas,
            created_at=a.template.created_at,
        )
    )


# ─────────────────────────────────────────────────────────────
# CRUD Semanas Tipo
# ─────────────────────────────────────────────────────────────
@router.get("/week-templates", response_model=List[WeekTemplateOut])
def list_week_templates(
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    wts = (
        db.query(WeekTemplate)
        .filter(WeekTemplate.coach_id == coach.id)
        .order_by(WeekTemplate.created_at.desc())
        .all()
    )
    return [_wt_to_out(w) for w in wts]


@router.post("/week-templates", response_model=WeekTemplateOut, status_code=201)
def create_week_template(
    body: WeekTemplateCreate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    wt = WeekTemplate(
        coach_id=coach.id, nombre=body.nombre, descripcion=body.descripcion
    )
    db.add(wt)
    db.commit()
    db.refresh(wt)
    return _wt_to_out(wt)


@router.delete("/week-templates/{wt_id}", status_code=204)
def delete_week_template(
    wt_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    wt = db.query(WeekTemplate).filter(
        WeekTemplate.id == wt_id, WeekTemplate.coach_id == coach.id
    ).first()
    if not wt:
        raise HTTPException(404, "Semana tipo no encontrada")
    db.delete(wt)
    db.commit()


# ─────────────────────────────────────────────────────────────
# Días de una semana tipo
# ─────────────────────────────────────────────────────────────
@router.post("/week-templates/{wt_id}/days", response_model=WeekTemplateDayOut, status_code=201)
def add_week_template_day(
    wt_id: str,
    body: WeekTemplateDayCreate,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    wt = db.query(WeekTemplate).filter(
        WeekTemplate.id == wt_id, WeekTemplate.coach_id == coach.id
    ).first()
    if not wt:
        raise HTTPException(404, "Semana tipo no encontrada")
    workout = db.query(WorkoutTemplate).filter(
        WorkoutTemplate.id == body.workout_template_id
    ).first()
    if not workout:
        raise HTTPException(404, "Template de workout no encontrado")

    day = WeekTemplateDay(
        week_template_id    = wt_id,
        day_of_week         = body.day_of_week,
        workout_template_id = body.workout_template_id,
        notas               = body.notas,
    )
    db.add(day)
    db.commit()
    db.refresh(day)
    return WeekTemplateDayOut(
        id=day.id, day_of_week=day.day_of_week,
        workout_template_id=day.workout_template_id,
        workout_nombre=workout.nombre, workout_sport=workout.sport,
        workout_dur_min=workout.dur_min, workout_dist_km=workout.dist_km,
        workout_tss=workout.tss, notas=day.notas,
    )


@router.delete("/week-templates/{wt_id}/days/{day_id}", status_code=204)
def remove_week_template_day(
    wt_id: str, day_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    day = db.query(WeekTemplateDay).filter(
        WeekTemplateDay.id == day_id,
        WeekTemplateDay.week_template_id == wt_id
    ).first()
    if not day:
        raise HTTPException(404, "Día no encontrado")
    db.delete(day)
    db.commit()


# ─────────────────────────────────────────────────────────────
# Aplicar semana tipo
# ─────────────────────────────────────────────────────────────
@router.post("/week-templates/{wt_id}/apply")
def apply_week_template(
    wt_id: str,
    body: ApplyWeekTemplateRequest,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    wt = db.query(WeekTemplate).filter(
        WeekTemplate.id == wt_id, WeekTemplate.coach_id == coach.id
    ).first()
    if not wt:
        raise HTTPException(404, "Semana tipo no encontrada")
    if not body.athlete_id and not body.group_id:
        raise HTTPException(400, "Debes especificar athlete_id o group_id")
    if not wt.days:
        raise HTTPException(400, "La semana tipo no tiene sesiones configuradas")

    start = _date.fromisoformat(body.start_date)
    created_assigns = []

    for d in wt.days:
        target_date = (start + timedelta(days=d.day_of_week)).isoformat()
        a = AssignedWorkout(
            template_id = d.workout_template_id,
            athlete_id  = body.athlete_id,
            group_id    = body.group_id,
            date_iso    = target_date,
            notas       = d.notas,
        )
        db.add(a)
        created_assigns.append((a, d.workout_template_id, target_date))

    db.commit()

    # Sync Garmin opcional
    synced = 0
    if body.sync_garmin:
        try:
            from garmin_connector import schedule_workout_for_athlete
            for a, _, date_iso in created_assigns:
                db.refresh(a)
                tpl = db.query(WorkoutTemplate).filter(
                    WorkoutTemplate.id == a.template_id
                ).first()
                if not tpl:
                    continue
                athletes_to_sync = []
                if a.athlete_id:
                    ath = db.query(User).filter(User.id == a.athlete_id).first()
                    if ath:
                        athletes_to_sync.append(ath)
                elif a.group_id:
                    members = (
                        db.query(User)
                        .join(GroupMember, GroupMember.athlete_id == User.id)
                        .filter(GroupMember.group_id == a.group_id, User.activo == True)
                        .all()
                    )
                    athletes_to_sync.extend(members)
                for ath in athletes_to_sync:
                    if ath.garmin_email and ath.garmin_password:
                        try:
                            schedule_workout_for_athlete(ath, tpl, date_iso)
                            synced += 1
                        except Exception:
                            pass
        except ImportError:
            pass

    return {
        "created": len(created_assigns),
        "synced_garmin": synced,
        "week_start": body.start_date,
        "week_end": (start + timedelta(days=6)).isoformat(),
    }


# ─────────────────────────────────────────────────────────────
# CALENDARIO
# ─────────────────────────────────────────────────────────────
@router.get("/calendar", response_model=List[CalendarDay], operation_id="get_coach_template_calendar")
def get_template_calendar(
    start:    str           = Query(..., description="YYYY-MM-DD"),
    end:      str           = Query(..., description="YYYY-MM-DD"),
    group_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    # Atletas activos (filtrado por grupo opcional)
    ath_q = db.query(User).filter(User.activo == True, User.rol == "atleta")
    if group_id:
        ath_q = (
            ath_q
            .join(GroupMember, GroupMember.athlete_id == User.id)
            .filter(GroupMember.group_id == group_id)
        )
    athletes = ath_q.all()
    athlete_ids = {a.id for a in athletes}
    athlete_map = {a.id: a for a in athletes}

    # Asignaciones individuales del período
    ind_assigns = (
        db.query(AssignedWorkout)
        .filter(
            AssignedWorkout.date_iso >= start,
            AssignedWorkout.date_iso <= end,
            AssignedWorkout.athlete_id.in_(list(athlete_ids)),
        )
        .all()
    )

    # Asignaciones grupales → expandir a miembros
    grp_assigns = (
        db.query(AssignedWorkout)
        .filter(
            AssignedWorkout.date_iso >= start,
            AssignedWorkout.date_iso <= end,
            AssignedWorkout.group_id.isnot(None),
        )
        .all()
    )
    extra = []
    for ga in grp_assigns:
        members = (
            db.query(GroupMember.athlete_id)
            .filter(GroupMember.group_id == ga.group_id)
            .all()
        )
        for (uid,) in members:
            if uid in athlete_ids:
                v = copy.copy(ga)
                v.athlete_id = uid
                extra.append(v)

    all_assigns = ind_assigns + extra

    # Agrupar fecha → atleta → lista
    by_date: dict = defaultdict(lambda: defaultdict(list))
    for a in all_assigns:
        if a.athlete_id and a.athlete_id in athlete_map:
            by_date[a.date_iso][a.athlete_id].append(_assign_to_out(a))

    # Construir lista de días (solo días con alguna sesión)
    result = []
    cur = _date.fromisoformat(start)
    end_d = _date.fromisoformat(end)
    while cur <= end_d:
        iso = cur.isoformat()
        day_athletes = [
            CalendarAthleteDay(
                athlete_id=a.id,
                athlete_nombre=a.nombre,
                assignments=by_date[iso][a.id],
            )
            for a in athletes
            if by_date[iso].get(a.id)
        ]
        result.append(CalendarDay(date_iso=iso, athletes=day_athletes))
        cur += timedelta(days=1)

    return result


# ══════════════════════════════════════════════════════════════
# NOTAS DEL COACH POR ATLETA
# ══════════════════════════════════════════════════════════════

@router.get("/athletes/{athlete_id}/notes", response_model=List[AthleteNoteOut])
def list_athlete_notes(athlete_id: str, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    notes = (
        db.query(AthleteNote)
        .filter(AthleteNote.coach_id == coach.id, AthleteNote.athlete_id == athlete_id)
        .order_by(AthleteNote.fecha.desc(), AthleteNote.created_at.desc())
        .all()
    )
    return [AthleteNoteOut(id=n.id, tipo=n.tipo, texto=n.texto, fecha=n.fecha) for n in notes]


@router.post("/athletes/{athlete_id}/notes", response_model=AthleteNoteOut, status_code=201)
def create_athlete_note(athlete_id: str, body: AthleteNoteCreate, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    assert_coach_owns_athlete(coach.id, athlete_id, db)
    note = AthleteNote(coach_id=coach.id, athlete_id=athlete_id, tipo=body.tipo, texto=body.texto, fecha=body.fecha)
    db.add(note); db.commit(); db.refresh(note)
    return AthleteNoteOut(id=note.id, tipo=note.tipo, texto=note.texto, fecha=note.fecha)


@router.delete("/athletes/{athlete_id}/notes/{note_id}", status_code=204)
def delete_athlete_note(athlete_id: str, note_id: str, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    note = db.query(AthleteNote).filter(
        AthleteNote.id == note_id, AthleteNote.athlete_id == athlete_id, AthleteNote.coach_id == coach.id
    ).first()
    if not note:
        raise HTTPException(404, "Nota no encontrada")
    db.delete(note); db.commit()


# ══════════════════════════════════════════════════════════════
# MACROCICLOS
# ══════════════════════════════════════════════════════════════

def _mc_to_out(mc: Macrocycle) -> MacrocycleOut:
    return MacrocycleOut(
        id=mc.id, nombre=mc.nombre, descripcion=mc.descripcion,
        weeks=[MacrocycleWeekOut(
            id=w.id, position=w.position,
            week_template_id=w.week_template_id,
            week_nombre=w.week_template.nombre, notas=w.notas,
        ) for w in mc.weeks]
    )


@router.get("/macrocycles", response_model=List[MacrocycleOut])
def list_macrocycles(db: Session = Depends(get_db), coach: User = Depends(_coach)):
    mcs = db.query(Macrocycle).filter(Macrocycle.coach_id == coach.id).order_by(Macrocycle.created_at.desc()).all()
    return [_mc_to_out(m) for m in mcs]


@router.post("/macrocycles", response_model=MacrocycleOut, status_code=201)
def create_macrocycle(body: MacrocycleCreate, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    mc = Macrocycle(coach_id=coach.id, nombre=body.nombre, descripcion=body.descripcion)
    db.add(mc); db.commit(); db.refresh(mc)
    return _mc_to_out(mc)


@router.delete("/macrocycles/{mc_id}", status_code=204)
def delete_macrocycle(mc_id: str, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    mc = db.query(Macrocycle).filter(Macrocycle.id == mc_id, Macrocycle.coach_id == coach.id).first()
    if not mc:
        raise HTTPException(404, "Macrociclo no encontrado")
    db.delete(mc); db.commit()


@router.post("/macrocycles/{mc_id}/weeks", response_model=MacrocycleWeekOut, status_code=201)
def add_macrocycle_week(mc_id: str, body: MacrocycleWeekCreate, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    mc = db.query(Macrocycle).filter(Macrocycle.id == mc_id, Macrocycle.coach_id == coach.id).first()
    if not mc:
        raise HTTPException(404, "Macrociclo no encontrado")
    wt = db.query(WeekTemplate).filter(WeekTemplate.id == body.week_template_id).first()
    if not wt:
        raise HTTPException(404, "Semana tipo no encontrada")
    pos = (max((w.position for w in mc.weeks), default=0) + 1)
    mw  = MacrocycleWeek(macrocycle_id=mc_id, position=pos, week_template_id=body.week_template_id, notas=body.notas)
    db.add(mw); db.commit(); db.refresh(mw)
    return MacrocycleWeekOut(id=mw.id, position=mw.position, week_template_id=mw.week_template_id, week_nombre=wt.nombre, notas=mw.notas)


@router.delete("/macrocycles/{mc_id}/weeks/{mw_id}", status_code=204)
def remove_macrocycle_week(mc_id: str, mw_id: str, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    mw = db.query(MacrocycleWeek).filter(MacrocycleWeek.id == mw_id, MacrocycleWeek.macrocycle_id == mc_id).first()
    if not mw:
        raise HTTPException(404, "Semana no encontrada")
    db.delete(mw); db.commit()


@router.post("/macrocycles/{mc_id}/apply")
def apply_macrocycle(mc_id: str, body: ApplyMacrocycleRequest, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    mc = db.query(Macrocycle).filter(Macrocycle.id == mc_id, Macrocycle.coach_id == coach.id).first()
    if not mc:
        raise HTTPException(404, "Macrociclo no encontrado")
    if not mc.weeks:
        raise HTTPException(400, "El macrociclo no tiene semanas configuradas")
    if not body.athlete_id and not body.group_id:
        raise HTTPException(400, "Debes especificar athlete_id o group_id")

    start = _date.fromisoformat(body.start_date)
    total_created = 0; total_synced = 0

    for mc_week in mc.weeks:
        week_start = start + timedelta(weeks=mc_week.position - 1)
        wt = mc_week.week_template
        if not wt or not wt.days:
            continue
        for day in wt.days:
            target_date = (week_start + timedelta(days=day.day_of_week)).isoformat()
            a = AssignedWorkout(
                template_id=day.workout_template_id,
                athlete_id=body.athlete_id, group_id=body.group_id,
                date_iso=target_date, notas=day.notas,
            )
            db.add(a); total_created += 1

    db.commit()

    end_date = (start + timedelta(weeks=len(mc.weeks)) - timedelta(days=1)).isoformat()
    return {"macrocycle": mc.nombre, "weeks_applied": len(mc.weeks),
            "created": total_created, "period_start": body.start_date, "period_end": end_date}
