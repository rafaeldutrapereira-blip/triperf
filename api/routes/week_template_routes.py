"""
Endpoints: Semanas Tipo (Week Templates) + Calendario
"""
from __future__ import annotations

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
from ..permissions import assert_coach_owns_athlete, coach_athlete_ids
from ..services.performance_analytics_service import build_plan_impact

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
def _preview_athlete(body, coach: User, db: Session) -> str:
    """El preview proyecta sobre un atleta concreto (no sobre un grupo)."""
    if not body.athlete_id:
        raise HTTPException(400, "El impacto proyectado requiere un atleta individual")
    assert_coach_owns_athlete(coach.id, body.athlete_id, db)
    try:
        _date.fromisoformat(body.start_date)
    except ValueError:
        raise HTTPException(422, "start_date invalido (YYYY-MM-DD)")
    return body.athlete_id


@router.post("/week-templates/{wt_id}/preview-impact")
def preview_week_template_impact(
    wt_id: str,
    body: ApplyWeekTemplateRequest,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """Solo lectura: curva CTL/ATL/TSB que produciria aplicar esta semana tipo."""
    wt = db.query(WeekTemplate).filter(
        WeekTemplate.id == wt_id, WeekTemplate.coach_id == coach.id
    ).first()
    if not wt:
        raise HTTPException(404, "Semana tipo no encontrada")
    if not wt.days:
        raise HTTPException(400, "La semana tipo no tiene sesiones configuradas")
    athlete_id = _preview_athlete(body, coach, db)
    start = _date.fromisoformat(body.start_date)
    sessions = [(start + timedelta(days=d.day_of_week), d.workout.tss) for d in wt.days]
    return build_plan_impact(db, athlete_id, sessions)


@router.post("/macrocycles/{mc_id}/preview-impact")
def preview_macrocycle_impact(
    mc_id: str,
    body: ApplyMacrocycleRequest,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """Solo lectura: curva CTL/ATL/TSB que produciria aplicar este macrociclo."""
    mc = db.query(Macrocycle).filter(Macrocycle.id == mc_id, Macrocycle.coach_id == coach.id).first()
    if not mc:
        raise HTTPException(404, "Macrociclo no encontrado")
    if not mc.weeks:
        raise HTTPException(400, "El macrociclo no tiene semanas configuradas")
    athlete_id = _preview_athlete(body, coach, db)
    start = _date.fromisoformat(body.start_date)
    sessions = []
    for mc_week in mc.weeks:
        wt = mc_week.week_template
        if not wt or not wt.days:
            continue
        week_start = start + timedelta(weeks=mc_week.position - 1)
        for day in wt.days:
            sessions.append((week_start + timedelta(days=day.day_of_week), day.workout.tss))
    if not sessions:
        raise HTTPException(400, "El macrociclo no tiene sesiones configuradas")
    return build_plan_impact(db, athlete_id, sessions)


APPLY_MULTI_MAX = 500


def _resolve_multi_targets(db, coach, body):
    """Destino múltiple de apply (semana tipo / macrociclo).

    Valida cada id contra el universo único del coach (pila 360). Devuelve
    (validos, fallidos): `fallidos` = [{athlete_id, reason}] para ids ajenos,
    inexistentes, vacíos o repetidos. Un id inválido NO bloquea a los demás.
    """
    if body.athlete_id or body.group_id:
        raise HTTPException(400, "athlete_ids no se combina con athlete_id ni group_id")
    ids = body.athlete_ids or []
    if not ids:
        raise HTTPException(400, "athlete_ids está vacío")
    if len(ids) > APPLY_MULTI_MAX:
        raise HTTPException(400, f"Máximo {APPLY_MULTI_MAX} atletas por aplicación")
    universe = set(coach_athlete_ids(db, coach))
    valid, failed, seen = [], [], set()
    for aid in ids:
        if not aid or not str(aid).strip():
            failed.append({"athlete_id": aid, "reason": "id vacío"})
        elif aid in seen:
            failed.append({"athlete_id": aid, "reason": "atleta repetido en la lista"})
        elif aid not in universe:
            failed.append({"athlete_id": aid, "reason": "El atleta no pertenece a este coach"})
        else:
            valid.append(aid)
        seen.add(aid)
    return valid, failed


def _require_own_athlete(db, coach, athlete_id):
    if athlete_id and athlete_id not in set(coach_athlete_ids(db, coach)):
        raise HTTPException(403, "El atleta no pertenece a este coach")


def _sync_garmin_assigns(db, created_assigns):
    """Sync Garmin opcional de las asignaciones recién creadas. Devuelve cuántas se enviaron."""
    synced = 0
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
                        from ..crypto import decrypt_credential
                        schedule_workout_for_athlete(
                            session={
                                "name": tpl.nombre, "sport": tpl.sport,
                                "dur_min": tpl.dur_min, "dist_km": tpl.dist_km,
                                "notes": tpl.notas or "",
                                "blocks_json": tpl.blocks_json, "ftp": ath.ftp,
                                "fcmax": ath.fcmax,
                            },
                            target_date=date_iso,
                            athlete_id=ath.id,
                            athlete_email=ath.garmin_email,
                            athlete_password=decrypt_credential(ath.garmin_password),
                        )
                        synced += 1
                    except Exception:
                        pass
    except ImportError:
        pass
    return synced


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
    multi = body.athlete_ids is not None
    if multi:
        targets, failed = _resolve_multi_targets(db, coach, body)
    else:
        if not body.athlete_id and not body.group_id:
            raise HTTPException(400, "Debes especificar athlete_id o group_id")
        _require_own_athlete(db, coach, body.athlete_id)
        targets, failed = [None], []
    if not wt.days:
        raise HTTPException(400, "La semana tipo no tiene sesiones configuradas")

    start = _date.fromisoformat(body.start_date)
    created_assigns = []
    per_athlete = []

    for tid in targets:
        n = 0
        for d in wt.days:
            target_date = (start + timedelta(days=d.day_of_week)).isoformat()
            a = AssignedWorkout(
                template_id = d.workout_template_id,
                athlete_id  = tid if multi else body.athlete_id,
                group_id    = None if multi else body.group_id,
                date_iso    = target_date,
                notas       = d.notas,
            )
            db.add(a)
            created_assigns.append((a, d.workout_template_id, target_date))
            n += 1
        if multi:
            per_athlete.append({"athlete_id": tid, "ok": True, "created": n})

    db.commit()

    synced = _sync_garmin_assigns(db, created_assigns) if body.sync_garmin else 0

    out = {
        "created": len(created_assigns),
        "synced_garmin": synced,
        "week_start": body.start_date,
        "week_end": (start + timedelta(days=6)).isoformat(),
    }
    if multi:
        out["results"] = per_athlete + [
            {"athlete_id": f["athlete_id"], "ok": False, "created": 0, "error": f["reason"]}
            for f in failed
        ]
        out["athletes_ok"] = len(per_athlete)
        out["athletes_failed"] = len(failed)
    return out


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
    # Atletas del coach (nunca de otros coaches) — opcionalmente acotado a un grupo
    coach_group_ids = [g.id for g in db.query(Group).filter(Group.coach_id == coach.id).all()]
    if group_id and group_id not in coach_group_ids:
        raise HTTPException(404, "Grupo no encontrado")
    scope_group_ids = [group_id] if group_id else coach_group_ids
    if not scope_group_ids:
        return []
    athletes = (
        db.query(User)
        .join(GroupMember, GroupMember.athlete_id == User.id)
        .filter(User.activo == True, User.rol == "atleta", GroupMember.group_id.in_(scope_group_ids))
        .distinct()
        .all()
    )
    athlete_ids = {a.id for a in athletes}
    athlete_map = {a.id: a for a in athletes}

    # Todas las asignaciones del período — incluye tanto las individuales
    # como las de grupo: assign_workout() (POST /coach/assign) ya expande
    # una asignación grupal a UNA fila por miembro en el momento de crearla
    # (athlete_id + group_id ambos poblados), así que filtrar por
    # athlete_id ya las captura todas. (Antes había acá una segunda
    # "expansión" que volvía a duplicar cada fila de grupo por cada
    # miembro ACTUAL del grupo vía copy.copy() de un objeto ORM — rompía
    # el lazy-load de .template con "Deferred loader failed to populate
    # correctly" en cuanto había una asignación de grupo real, y además
    # habría duplicado las tarjetas del calendario.)
    all_assigns = (
        db.query(AssignedWorkout)
        .filter(
            AssignedWorkout.date_iso >= start,
            AssignedWorkout.date_iso <= end,
            AssignedWorkout.athlete_id.in_(list(athlete_ids)),
        )
        .all()
    )

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
    multi = body.athlete_ids is not None
    if multi:
        targets, failed = _resolve_multi_targets(db, coach, body)
    else:
        if not body.athlete_id and not body.group_id:
            raise HTTPException(400, "Debes especificar athlete_id o group_id")
        _require_own_athlete(db, coach, body.athlete_id)
        targets, failed = [None], []

    start = _date.fromisoformat(body.start_date)
    total_created = 0
    per_athlete = []

    for tid in targets:
        n = 0
        for mc_week in mc.weeks:
            week_start = start + timedelta(weeks=mc_week.position - 1)
            wt = mc_week.week_template
            if not wt or not wt.days:
                continue
            for day in wt.days:
                target_date = (week_start + timedelta(days=day.day_of_week)).isoformat()
                a = AssignedWorkout(
                    template_id=day.workout_template_id,
                    athlete_id=tid if multi else body.athlete_id,
                    group_id=None if multi else body.group_id,
                    date_iso=target_date, notas=day.notas,
                )
                db.add(a); n += 1
        total_created += n
        if multi:
            per_athlete.append({"athlete_id": tid, "ok": True, "created": n})

    db.commit()

    end_date = (start + timedelta(weeks=len(mc.weeks)) - timedelta(days=1)).isoformat()
    out = {"macrocycle": mc.nombre, "weeks_applied": len(mc.weeks),
           "created": total_created, "period_start": body.start_date, "period_end": end_date}
    if multi:
        out["results"] = per_athlete + [
            {"athlete_id": f["athlete_id"], "ok": False, "created": 0, "error": f["reason"]}
            for f in failed
        ]
        out["athletes_ok"] = len(per_athlete)
        out["athletes_failed"] = len(failed)
    return out
