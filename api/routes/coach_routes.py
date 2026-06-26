from __future__ import annotations

import threading
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, Group, GroupMember, WorkoutTemplate,
    AssignedWorkout, WorkoutLog, WeekTemplate, WeekTemplateDay,
    WellnessLog,
)
from ..schemas import (
    GroupCreate, GroupOut, AddMemberRequest,
    WorkoutTemplateCreate, WorkoutTemplateUpdate, WorkoutTemplateOut,
    AssignRequest, AssignedWorkoutOut,
    AthleteAdherence, UserOut,
    GarminCredentials, GarminSyncResult,
    UserCreate, UserUpdate,
    PlanVsActualItem,
    AthleteReport, ReportSportRow, ReportWeek,
    WeekTemplateCreate, WeekTemplateDayCreate, WeekTemplateOut, WeekTemplateDayOut,
    ApplyWeekTemplateRequest, CalendarDay, CalendarAthleteDay,
)
from ..auth import require_role, hash_password
from ..crypto import decrypt as _dec

router   = APIRouter(prefix="/coach", tags=["coach"])
_coach   = require_role("coach", "admin")


# ── Athletes under this coach ───────────────────────────────
@router.get("/athletes", response_model=List[UserOut])
def list_athletes(db: Session = Depends(get_db), coach: User = Depends(_coach)):
    """Atletas que pertenecen a al menos un grupo del coach. Incluye has_garmin."""
    group_ids = [g.id for g in db.query(Group).filter(Group.coach_id == coach.id).all()]
    if not group_ids:
        return []
    members = (
        db.query(User)
        .join(GroupMember, GroupMember.athlete_id == User.id)
        .filter(GroupMember.group_id.in_(group_ids))
        .filter(User.activo == True)
        .distinct()
        .all()
    )
    return [UserOut.from_orm_user(u) for u in members]


# ── Groups ──────────────────────────────────────────────────
@router.get("/groups", response_model=List[GroupOut])
def list_groups(db: Session = Depends(get_db), coach: User = Depends(_coach)):
    groups = db.query(Group).filter(Group.coach_id == coach.id).all()
    result = []
    for g in groups:
        out        = GroupOut.model_validate(g)
        out.member_count = len(g.members)
        result.append(out)
    return result


@router.post("/groups", response_model=GroupOut, status_code=201)
def create_group(body: GroupCreate, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    g = Group(nombre=body.nombre, competencia=body.competencia, coach_id=coach.id)
    db.add(g); db.commit(); db.refresh(g)
    out              = GroupOut.model_validate(g)
    out.member_count = 0
    return out


@router.get("/groups/{group_id}/members", response_model=List[UserOut])
def list_group_members(group_id: str, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    g = db.query(Group).filter(Group.id == group_id, Group.coach_id == coach.id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    members = (
        db.query(User)
        .join(GroupMember, GroupMember.athlete_id == User.id)
        .filter(GroupMember.group_id == group_id, User.activo == True)
        .all()
    )
    return [UserOut.from_orm_user(u) for u in members]


@router.delete("/groups/{group_id}", status_code=204)
def delete_group(group_id: str, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    g = db.query(Group).filter(Group.id == group_id, Group.coach_id == coach.id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    db.delete(g); db.commit()


@router.post("/groups/{group_id}/members", status_code=201)
def add_member(group_id: str, body: AddMemberRequest,
               db: Session = Depends(get_db), coach: User = Depends(_coach)):
    g = db.query(Group).filter(Group.id == group_id, Group.coach_id == coach.id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    if not db.query(User).filter(User.id == body.user_id).first():
        raise HTTPException(404, "Usuario no encontrado")
    exists = db.query(GroupMember).filter(
        GroupMember.group_id == group_id, GroupMember.athlete_id == body.user_id
    ).first()
    if exists:
        raise HTTPException(409, "El atleta ya es miembro del grupo")
    m = GroupMember(group_id=group_id, athlete_id=body.user_id)
    db.add(m); db.commit()
    return {"ok": True}


@router.delete("/groups/{group_id}/members/{user_id}", status_code=204)
def remove_member(group_id: str, user_id: str,
                  db: Session = Depends(get_db), coach: User = Depends(_coach)):
    g = db.query(Group).filter(Group.id == group_id, Group.coach_id == coach.id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")
    m = db.query(GroupMember).filter(
        GroupMember.group_id == group_id, GroupMember.athlete_id == user_id
    ).first()
    if not m:
        raise HTTPException(404, "Miembro no encontrado")
    db.delete(m); db.commit()


# ── Workout Templates ───────────────────────────────────────
@router.get("/workouts", response_model=List[WorkoutTemplateOut])
def list_templates(db: Session = Depends(get_db), coach: User = Depends(_coach)):
    return db.query(WorkoutTemplate).filter(WorkoutTemplate.coach_id == coach.id)\
             .order_by(WorkoutTemplate.created_at.desc()).all()


@router.post("/workouts", response_model=WorkoutTemplateOut, status_code=201)
def create_template(body: WorkoutTemplateCreate,
                    db: Session = Depends(get_db), coach: User = Depends(_coach)):
    t = WorkoutTemplate(
        coach_id    = coach.id,
        sport       = body.sport,
        tipo        = body.tipo,
        nombre      = body.nombre,
        dur_min     = body.dur_min,
        dist_km     = body.dist_km,
        tss         = body.tss,
        notas       = body.notas,
        blocks_json = body.blocks_json,
    )
    db.add(t); db.commit(); db.refresh(t)
    return t


@router.put("/workouts/{template_id}", response_model=WorkoutTemplateOut)
def update_template(template_id: str, body: WorkoutTemplateUpdate,
                    db: Session = Depends(get_db), coach: User = Depends(_coach)):
    t = db.query(WorkoutTemplate).filter(
        WorkoutTemplate.id == template_id, WorkoutTemplate.coach_id == coach.id
    ).first()
    if not t:
        raise HTTPException(404, "Template no encontrado")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(t, field, val)
    db.commit(); db.refresh(t)
    return t


@router.post("/workouts/{template_id}/clone", response_model=WorkoutTemplateOut, status_code=201)
def clone_template(template_id: str,
                   db: Session = Depends(get_db), coach: User = Depends(_coach)):
    src = db.query(WorkoutTemplate).filter(
        WorkoutTemplate.id == template_id, WorkoutTemplate.coach_id == coach.id
    ).first()
    if not src:
        raise HTTPException(404, "Template no encontrado")
    copy = WorkoutTemplate(
        coach_id    = coach.id,
        sport       = src.sport,
        tipo        = src.tipo,
        nombre      = src.nombre + " (copia)",
        dur_min     = src.dur_min,
        dist_km     = src.dist_km,
        tss         = src.tss,
        notas       = src.notas,
        blocks_json = src.blocks_json,
    )
    db.add(copy); db.commit(); db.refresh(copy)
    return copy


@router.delete("/workouts/{template_id}", status_code=204)
def delete_template(template_id: str,
                    db: Session = Depends(get_db), coach: User = Depends(_coach)):
    t = db.query(WorkoutTemplate).filter(
        WorkoutTemplate.id == template_id, WorkoutTemplate.coach_id == coach.id
    ).first()
    if not t:
        raise HTTPException(404, "Template no encontrado")
    db.delete(t); db.commit()


# ── Assign ──────────────────────────────────────────────────
@router.post("/assign", response_model=AssignedWorkoutOut, status_code=201)
def assign_workout(body: AssignRequest,
                   db: Session = Depends(get_db), coach: User = Depends(_coach)):
    """
    Asigna un template a un atleta individual O a un grupo completo.
    Si es grupo, crea un AssignedWorkout por cada miembro.
    """
    tpl = db.query(WorkoutTemplate).filter(
        WorkoutTemplate.id == body.template_id,
        WorkoutTemplate.coach_id == coach.id
    ).first()
    if not tpl:
        raise HTTPException(404, "Template no encontrado")

    if not body.athlete_id and not body.group_id:
        raise HTTPException(400, "Debes indicar athlete_id o group_id")

    # Asignación a grupo → expandir a miembros
    if body.group_id:
        g = db.query(Group).filter(
            Group.id == body.group_id, Group.coach_id == coach.id
        ).first()
        if not g:
            raise HTTPException(404, "Grupo no encontrado")
        members = db.query(GroupMember).filter(GroupMember.group_id == body.group_id).all()
        assignments = []
        for m in members:
            a = AssignedWorkout(
                template_id = body.template_id,
                athlete_id  = m.user_id,
                group_id    = body.group_id,
                date_iso    = body.date_iso,
                notas       = body.notas,
            )
            db.add(a)
            assignments.append(a)
        db.commit()
        if not assignments:
            raise HTTPException(400, "El grupo no tiene miembros")
        # Auto-entrega para cada miembro si es workout bici con bloques
        if tpl.sport == "bike" and tpl.blocks_json:
            from ..workout_delivery import deliver_bike_workout
            for a in assignments:
                db.refresh(a)
                athlete = db.query(User).filter(User.id == a.athlete_id).first()
                if athlete:
                    _a, _ath, _tpl = a, athlete, tpl
                    threading.Thread(
                        target=deliver_bike_workout,
                        args=(_a, _ath, _tpl),
                        daemon=True,
                    ).start()
        db.refresh(assignments[0])
        return assignments[0]

    # Asignación individual
    a = AssignedWorkout(
        template_id = body.template_id,
        athlete_id  = body.athlete_id,
        group_id    = None,
        date_iso    = body.date_iso,
        notas       = body.notas,
    )
    db.add(a); db.commit(); db.refresh(a)
    # Auto-entrega si es workout bici con bloques
    if tpl.sport == "bike" and tpl.blocks_json:
        athlete = db.query(User).filter(User.id == body.athlete_id).first()
        if athlete:
            from ..workout_delivery import deliver_bike_workout
            threading.Thread(
                target=deliver_bike_workout,
                args=(a, athlete, tpl),
                daemon=True,
            ).start()
    return a


@router.get("/assignments/athlete/{athlete_id}", response_model=List[AssignedWorkoutOut])
def list_assignments_for_athlete(
    athlete_id: str,
    start: Optional[str] = Query(None),
    end:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """Asignaciones de un atleta específico (solo templates de este coach)."""
    template_ids = [t.id for t in db.query(WorkoutTemplate).filter(WorkoutTemplate.coach_id == coach.id).all()]
    q = db.query(AssignedWorkout).filter(
        AssignedWorkout.athlete_id == athlete_id,
        AssignedWorkout.template_id.in_(template_ids)
    )
    if start: q = q.filter(AssignedWorkout.date_iso >= start)
    if end:   q = q.filter(AssignedWorkout.date_iso <= end)
    return q.order_by(AssignedWorkout.date_iso).all()


@router.patch("/assignments/{assignment_id}/comment", response_model=dict)
def comment_assignment(
    assignment_id: str,
    body: dict,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """El coach añade o edita un comentario en una sesión asignada."""
    template_ids = [t.id for t in db.query(WorkoutTemplate).filter(WorkoutTemplate.coach_id == coach.id).all()]
    a = db.query(AssignedWorkout).filter(
        AssignedWorkout.id == assignment_id,
        AssignedWorkout.template_id.in_(template_ids)
    ).first()
    if not a:
        raise HTTPException(404, "Asignación no encontrada")
    a.coach_comment = body.get("coach_comment")
    db.commit()
    return {"ok": True}


@router.delete("/assignments/{assignment_id}", status_code=204)
def delete_assignment(
    assignment_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """Eliminar una asignación (solo si pertenece a un template de este coach)."""
    template_ids = [t.id for t in db.query(WorkoutTemplate).filter(WorkoutTemplate.coach_id == coach.id).all()]
    a = db.query(AssignedWorkout).filter(
        AssignedWorkout.id == assignment_id,
        AssignedWorkout.template_id.in_(template_ids)
    ).first()
    if not a:
        raise HTTPException(404, "Asignación no encontrada")
    db.delete(a)
    db.commit()


@router.get("/assignments", response_model=List[AssignedWorkoutOut])
def list_assignments(
    start: Optional[str] = Query(None),
    end:   Optional[str] = Query(None),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """Todos los entrenos asignados por este coach, con filtro de fechas opcional."""
    group_ids    = [g.id for g in db.query(Group).filter(Group.coach_id == coach.id).all()]
    template_ids = [t.id for t in db.query(WorkoutTemplate).filter(WorkoutTemplate.coach_id == coach.id).all()]

    q = db.query(AssignedWorkout).filter(
        AssignedWorkout.template_id.in_(template_ids)
    )
    if start: q = q.filter(AssignedWorkout.date_iso >= start)
    if end:   q = q.filter(AssignedWorkout.date_iso <= end)
    return q.order_by(AssignedWorkout.date_iso).all()


@router.post("/calendar/copy-week", response_model=dict, status_code=201)
def copy_week(
    body: dict,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """
    Copia todas las asignaciones de una semana fuente a otra semana destino.
    body: {source_start, target_start, athlete_id?, group_id?}
    source_start / target_start: lunes de la semana (YYYY-MM-DD)
    """
    from datetime import date, timedelta
    source_start = body.get("source_start")
    target_start = body.get("target_start")
    if not source_start or not target_start:
        raise HTTPException(400, "source_start y target_start requeridos")

    try:
        src_d   = date.fromisoformat(source_start)
        tgt_d   = date.fromisoformat(target_start)
    except ValueError:
        raise HTTPException(400, "Fechas inválidas")

    delta_days = (tgt_d - src_d).days
    source_end = (src_d + timedelta(days=6)).isoformat()

    template_ids = [t.id for t in db.query(WorkoutTemplate).filter(
        WorkoutTemplate.coach_id == coach.id
    ).all()]

    q = db.query(AssignedWorkout).filter(
        AssignedWorkout.template_id.in_(template_ids),
        AssignedWorkout.date_iso >= source_start,
        AssignedWorkout.date_iso <= source_end,
    )

    # Filtro opcional por atleta o grupo
    filter_athlete = body.get("athlete_id")
    filter_group   = body.get("group_id")
    if filter_athlete:
        q = q.filter(AssignedWorkout.athlete_id == filter_athlete)
    elif filter_group:
        q = q.filter(AssignedWorkout.group_id == filter_group)

    source_assigns = q.all()
    if not source_assigns:
        raise HTTPException(404, "No hay asignaciones en la semana fuente")

    created = 0
    for a in source_assigns:
        old_date = date.fromisoformat(a.date_iso)
        new_date = (old_date + timedelta(days=delta_days)).isoformat()
        copy = AssignedWorkout(
            template_id = a.template_id,
            athlete_id  = a.athlete_id,
            group_id    = a.group_id,
            date_iso    = new_date,
            notas       = a.notas,
        )
        db.add(copy)
        created += 1

    db.commit()
    return {"ok": True, "created": created, "target_start": target_start}


# ── Adherence / cumplimiento ────────────────────────────────
@router.get("/adherence", response_model=List[AthleteAdherence])
def adherence(
    start: str = Query(..., description="YYYY-MM-DD"),
    end:   str = Query(..., description="YYYY-MM-DD"),
    group_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """Cumplimiento por atleta para el período indicado."""
    # Atletas del coach (filtrado opcional por grupo)
    group_ids = [g.id for g in db.query(Group).filter(Group.coach_id == coach.id).all()]
    if group_id:
        if group_id not in group_ids:
            raise HTTPException(404, "Grupo no encontrado")
        group_ids = [group_id]

    athlete_ids = list({
        m.user_id
        for gid in group_ids
        for m in db.query(GroupMember).filter(GroupMember.group_id == gid).all()
    })

    template_ids = [t.id for t in db.query(WorkoutTemplate).filter(
        WorkoutTemplate.coach_id == coach.id
    ).all()]

    result = []
    for uid in athlete_ids:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            continue

        assignments = db.query(AssignedWorkout).filter(
            AssignedWorkout.athlete_id == uid,
            AssignedWorkout.template_id.in_(template_ids),
            AssignedWorkout.date_iso >= start,
            AssignedWorkout.date_iso <= end,
        ).all()

        by_sport: dict = {}
        done_total = 0

        for a in assignments:
            sport = a.template.sport
            if sport not in by_sport:
                by_sport[sport] = {"total": 0, "done": 0, "pct": 0.0}
            by_sport[sport]["total"] += 1

            log = db.query(WorkoutLog).filter(
                WorkoutLog.assignment_id == a.id,
                WorkoutLog.user_id == uid,
                WorkoutLog.completado == True
            ).first()
            if log:
                by_sport[sport]["done"] += 1
                done_total += 1

        for s in by_sport.values():
            s["pct"] = round(s["done"] / s["total"] * 100, 1) if s["total"] else 0.0

        total = len(assignments)
        result.append(AthleteAdherence(
            user_id    = uid,
            nombre     = user.nombre,
            email      = user.email,
            total      = total,
            completado = done_total,
            pct        = round(done_total / total * 100, 1) if total else 0.0,
            by_sport   = by_sport,
        ))

    result.sort(key=lambda x: x.pct, reverse=True)
    return result


# ── Crear atleta (coach crea la cuenta) ────────────────────
@router.post("/athletes", response_model=UserOut, status_code=201)
def create_athlete(body: UserCreate, db: Session = Depends(get_db), coach: User = Depends(_coach)):
    """Coach registra un nuevo atleta en el sistema."""
    if db.query(User).filter(User.email == body.email.lower()).first():
        raise HTTPException(409, "Email ya registrado")
    u = User(
        email         = body.email.lower(),
        nombre        = body.nombre,
        password_hash = hash_password(body.password),
        rol           = "athlete",
        plan_nivel    = body.plan_nivel or "basico",
        activo        = True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return UserOut.from_orm_user(u)


# ── Sync Garmin: enviar una asignación al Garmin del atleta ──
@router.post("/assign/{assignment_id}/sync-garmin", response_model=GarminSyncResult)
def sync_to_garmin(
    assignment_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """
    Empuja un workout ya asignado al Garmin Connect del atleta.
    Requiere que el atleta haya guardado sus credenciales Garmin.
    """
    template_ids = [
        t.id for t in db.query(WorkoutTemplate)
        .filter(WorkoutTemplate.coach_id == coach.id).all()
    ]
    a = db.query(AssignedWorkout).filter(
        AssignedWorkout.id == assignment_id,
        AssignedWorkout.template_id.in_(template_ids)
    ).first()
    if not a:
        raise HTTPException(404, "Asignación no encontrada")

    athlete = db.query(User).filter(User.id == a.athlete_id).first()
    if not athlete:
        raise HTTPException(404, "Atleta no encontrado")
    if not athlete.garmin_email or not athlete.garmin_password:
        raise HTTPException(400, f"El atleta {athlete.nombre} no tiene credenciales Garmin configuradas")

    tpl = a.template
    session_dict = {
        "name":    tpl.nombre,
        "sport":   tpl.sport,
        "dur_min": tpl.dur_min,
        "dist_km": tpl.dist_km,
        "notes":   tpl.notas or (a.notas or ""),
    }

    try:
        from garmin_connector import schedule_workout_for_athlete
        result = schedule_workout_for_athlete(
            session        = session_dict,
            target_date    = a.date_iso,
            athlete_email  = athlete.garmin_email,
            athlete_password = _dec(athlete.garmin_password) or athlete.garmin_password,
        )
        return GarminSyncResult(
            ok         = True,
            workout_id = str(result.get("workoutId", "")),
            date       = a.date_iso,
        )
    except Exception as e:
        return GarminSyncResult(ok=False, error=str(e))


# ── Sync Garmin masivo: enviar todas las asignaciones de un grupo ──
@router.post("/groups/{group_id}/sync-garmin", response_model=List[GarminSyncResult])
def sync_group_to_garmin(
    group_id: str,
    start: str = Query(..., description="YYYY-MM-DD"),
    end:   str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """
    Empuja todos los workouts del grupo en el rango de fechas al Garmin de cada atleta.
    Salta los atletas sin credenciales Garmin.
    """
    g = db.query(Group).filter(Group.id == group_id, Group.coach_id == coach.id).first()
    if not g:
        raise HTTPException(404, "Grupo no encontrado")

    template_ids = [
        t.id for t in db.query(WorkoutTemplate)
        .filter(WorkoutTemplate.coach_id == coach.id).all()
    ]

    assignments = db.query(AssignedWorkout).filter(
        AssignedWorkout.group_id   == group_id,
        AssignedWorkout.template_id.in_(template_ids),
        AssignedWorkout.date_iso   >= start,
        AssignedWorkout.date_iso   <= end,
    ).all()

    results = []
    try:
        from garmin_connector import schedule_workout_for_athlete
    except ImportError:
        raise HTTPException(500, "garminconnect no instalado en el servidor")

    for a in assignments:
        athlete = db.query(User).filter(User.id == a.athlete_id).first()
        if not athlete or not athlete.garmin_email or not athlete.garmin_password:
            results.append(GarminSyncResult(
                ok    = False,
                date  = a.date_iso,
                error = f"{(athlete.nombre if athlete else '?')} sin credenciales Garmin"
            ))
            continue
        try:
            tpl = a.template
            res = schedule_workout_for_athlete(
                session          = {"name": tpl.nombre, "sport": tpl.sport,
                                    "dur_min": tpl.dur_min, "dist_km": tpl.dist_km,
                                    "notes": tpl.notas or ""},
                target_date      = a.date_iso,
                athlete_email    = athlete.garmin_email,
                athlete_password = _dec(athlete.garmin_password) or athlete.garmin_password,
            )
            results.append(GarminSyncResult(
                ok         = True,
                workout_id = str(res.get("workoutId", "")),
                date       = a.date_iso,
            ))
        except Exception as e:
            results.append(GarminSyncResult(ok=False, date=a.date_iso, error=str(e)))

    return results


# ── Actividades Garmin de un atleta (para el coach) ──────────
@router.get("/athletes/{athlete_id}/garmin-activities")
def athlete_garmin_activities(
    athlete_id: str,
    limit: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """
    Retorna las últimas actividades Garmin del atleta.
    Solo accesible para coaches/admins con atletas en sus grupos.
    """
    athlete = db.query(User).filter(User.id == athlete_id, User.activo == True).first()
    if not athlete:
        raise HTTPException(404, "Atleta no encontrado")
    if not athlete.garmin_email or not athlete.garmin_password:
        raise HTTPException(400, "El atleta no tiene Garmin configurado")

    from datetime import date, timedelta
    end_date   = date.today().isoformat()
    start_date = (date.today() - timedelta(days=45)).isoformat()

    try:
        from garminconnect import Garmin
        _pwd = _dec(athlete.garmin_password) or athlete.garmin_password
        client = Garmin(athlete.garmin_email, _pwd)
        client.login()
        raw = client.get_activities_by_date(start_date, end_date) or []
    except ImportError:
        raise HTTPException(500, "garminconnect no instalado")
    except Exception as e:
        raise HTTPException(502, f"Error Garmin: {e}")

    result = []
    for a in raw[:limit]:
        dist_m = a.get("distance") or 0
        result.append({
            "activity_id":   a.get("activityId"),
            "name":          a.get("activityName"),
            "sport":         a.get("activityType", {}).get("typeKey", ""),
            "start_time":    a.get("startTimeLocal"),
            "duration_secs": a.get("duration"),
            "distance_km":   round(dist_m / 1000, 2) if dist_m else None,
            "average_hr":    a.get("averageHR"),
            "tss":           a.get("trainingStressScore"),
        })
    return result


# ── Plan vs Real (Fase 4) ────────────────────────────────────
_GARMIN_SPORT = {
    "lap_swimming": "swim", "swimming": "swim", "open_water_swimming": "swim",
    "cycling": "bike", "road_biking": "bike", "indoor_cycling": "bike",
    "mountain_biking": "bike", "virtual_ride": "bike",
    "running": "run", "trail_running": "run", "treadmill_running": "run",
    "strength_training": "str", "fitness_equipment": "str",
    "cross_training": "str", "hiit": "str",
}


@router.get("/athletes/{athlete_id}/plan-vs-actual", response_model=List[PlanVsActualItem])
def plan_vs_actual(
    athlete_id: str,
    start: str = Query(..., description="YYYY-MM-DD"),
    end:   str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """
    Para cada sesión asignada al atleta, cruza con:
    1. Log manual (WorkoutLog) — atleta marcó completado
    2. Actividad Garmin del mismo día y deporte — si tiene credenciales
    Devuelve status: pending | done_manual | done_garmin | done_both | missed
    """
    athlete = db.query(User).filter(User.id == athlete_id, User.activo == True).first()
    if not athlete:
        raise HTTPException(404, "Atleta no encontrado")

    # Asignaciones del período
    assignments = (
        db.query(AssignedWorkout)
        .filter(
            AssignedWorkout.athlete_id == athlete_id,
            AssignedWorkout.date_iso >= start,
            AssignedWorkout.date_iso <= end,
        )
        .order_by(AssignedWorkout.date_iso)
        .all()
    )

    # Logs manuales indexados por assignment_id
    log_map: dict = {}
    for a in assignments:
        log = db.query(WorkoutLog).filter(
            WorkoutLog.assignment_id == a.id,
            WorkoutLog.user_id == athlete_id,
            WorkoutLog.completado == True,
        ).first()
        if log:
            log_map[a.id] = log

    # Actividades Garmin indexadas por fecha → lista de actividades
    garmin_by_date: dict = {}
    has_garmin = bool(athlete.garmin_email and athlete.garmin_password)
    if has_garmin:
        try:
            from garminconnect import Garmin
            _pwd = _dec(athlete.garmin_password) or athlete.garmin_password
            client = Garmin(athlete.garmin_email, _pwd)
            client.login()
            raw_acts = client.get_activities_by_date(start, end) or []
            for act in raw_acts:
                act_date = (act.get("startTimeLocal") or "")[:10]
                if act_date:
                    garmin_by_date.setdefault(act_date, []).append(act)
        except Exception:
            pass  # Sin Garmin → solo logs manuales

    from datetime import date as _date
    today = _date.today().isoformat()

    result = []
    for a in assignments:
        log     = log_map.get(a.id)
        tpl     = a.template
        is_past = a.date_iso < today

        # Buscar match Garmin: mismo día, mismo deporte
        garmin_match = None
        day_acts = garmin_by_date.get(a.date_iso, [])
        for act in day_acts:
            gtype = act.get("activityType", {}).get("typeKey", "")
            if _GARMIN_SPORT.get(gtype) == tpl.sport:
                garmin_match = act
                break
        # Fallback: si hay solo 1 actividad ese día, aceptar sin importar deporte
        if not garmin_match and len(day_acts) == 1:
            garmin_match = day_acts[0]

        # Status
        if log and garmin_match:
            status = "done_both"
        elif garmin_match:
            status = "done_garmin"
        elif log:
            status = "done_manual"
        elif is_past:
            status = "missed"
        else:
            status = "pending"

        dist_m = (garmin_match.get("distance") or 0) if garmin_match else 0

        result.append(PlanVsActualItem(
            assignment_id   = a.id,
            date_iso        = a.date_iso,
            sport           = tpl.sport,
            template_nombre = tpl.nombre,
            planned_dist_km = tpl.dist_km,
            planned_dur_min = tpl.dur_min,
            planned_tss     = tpl.tss,
            coach_notas     = a.notas or tpl.notas,
            log_completado  = bool(log),
            log_dist_real   = log.dist_real if log else None,
            log_dur_real    = log.dur_real  if log else None,
            log_tss_real    = log.tss_real  if log else None,
            log_rpe         = log.rpe       if log else None,
            garmin_matched     = bool(garmin_match),
            garmin_activity_id = garmin_match.get("activityId")   if garmin_match else None,
            garmin_name        = garmin_match.get("activityName")  if garmin_match else None,
            garmin_dist_km     = round(dist_m / 1000, 2)          if dist_m else None,
            garmin_dur_secs    = garmin_match.get("duration")      if garmin_match else None,
            garmin_avg_hr      = garmin_match.get("averageHR")     if garmin_match else None,
            garmin_tss         = garmin_match.get("trainingStressScore") if garmin_match else None,
            status             = status,
        ))

    return result


# ── Reporte por atleta (Fase 5) ─────────────────────────────
@router.get("/report/athlete/{athlete_id}", response_model=AthleteReport)
def athlete_report(
    athlete_id: str,
    start: str = Query(..., description="YYYY-MM-DD"),
    end:   str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """
    Reporte completo del atleta para el período:
    - Totales planificado vs ejecutado
    - Desglose por deporte
    - Desglose por semana
    - CTL / ATL / TSB (computed from Garmin TSS last 84 days)
    """
    from datetime import date as _date, timedelta, datetime

    athlete = db.query(User).filter(User.id == athlete_id, User.activo == True).first()
    if not athlete:
        raise HTTPException(404, "Atleta no encontrado")

    # ── Asignaciones del período ──────────────────────────────
    assignments = (
        db.query(AssignedWorkout)
        .filter(AssignedWorkout.athlete_id == athlete_id,
                AssignedWorkout.date_iso >= start,
                AssignedWorkout.date_iso <= end)
        .order_by(AssignedWorkout.date_iso)
        .all()
    )

    # Logs indexados por assignment_id
    log_map: dict = {}
    for a in assignments:
        log = db.query(WorkoutLog).filter(
            WorkoutLog.assignment_id == a.id,
            WorkoutLog.user_id == athlete_id,
            WorkoutLog.completado == True,
        ).first()
        if log:
            log_map[a.id] = log

    # ── Garmin activities del período ─────────────────────────
    garmin_by_date: dict = {}
    has_garmin = bool(athlete.garmin_email and athlete.garmin_password)
    garmin_all: list = []

    if has_garmin:
        # Para CTL/ATL necesitamos 84 días antes del start
        ctl_start = (_date.fromisoformat(start) - timedelta(days=84)).isoformat()
        try:
            from garminconnect import Garmin
            _pwd = _dec(athlete.garmin_password) or athlete.garmin_password
            client = Garmin(athlete.garmin_email, _pwd)
            client.login()
            garmin_all = client.get_activities_by_date(ctl_start, end) or []
            for act in garmin_all:
                act_date = (act.get("startTimeLocal") or "")[:10]
                if act_date >= start:
                    garmin_by_date.setdefault(act_date, []).append(act)
        except Exception:
            pass

    # ── Desglose por deporte ──────────────────────────────────
    sport_map: dict = {}
    for a in assignments:
        tpl  = a.template
        log  = log_map.get(a.id)
        s    = tpl.sport
        if s not in sport_map:
            sport_map[s] = ReportSportRow(sport=s)
        row = sport_map[s]
        row.sessions_planned += 1
        row.dist_planned_km  += tpl.dist_km or 0
        row.dur_planned_min  += tpl.dur_min or 0
        row.tss_planned      += tpl.tss     or 0

        # Match Garmin por fecha+deporte
        day_acts = garmin_by_date.get(a.date_iso, [])
        garmin_m = None
        for act in day_acts:
            gtype = act.get("activityType", {}).get("typeKey", "")
            if _GARMIN_SPORT.get(gtype) == s:
                garmin_m = act; break
        if not garmin_m and len(day_acts) == 1:
            garmin_m = day_acts[0]

        if log or garmin_m:
            row.sessions_done += 1
            if log:
                row.dist_actual_km  += log.dist_real  or 0
                row.dur_actual_min  += log.dur_real   or 0
                row.tss_actual      += log.tss_real   or 0
            elif garmin_m:
                dist_m = garmin_m.get("distance") or 0
                row.dist_actual_km += round(dist_m / 1000, 2)
                dur_s  = garmin_m.get("duration") or 0
                row.dur_actual_min += int(dur_s / 60)
                row.tss_actual     += int(garmin_m.get("trainingStressScore") or 0)

    # ── Desglose por semana ISO ───────────────────────────────
    def _week_monday(iso: str) -> str:
        d = _date.fromisoformat(iso)
        return (d - timedelta(days=d.weekday())).isoformat()

    week_map: dict = {}
    for a in assignments:
        wk  = _week_monday(a.date_iso)
        log = log_map.get(a.id)
        if wk not in week_map:
            week_map[wk] = ReportWeek(week_start=wk)
        w = week_map[wk]
        w.sessions_planned += 1
        w.tss_planned      += a.template.tss or 0

        day_acts = garmin_by_date.get(a.date_iso, [])
        garmin_m = None
        for act in day_acts:
            gtype = act.get("activityType", {}).get("typeKey", "")
            if _GARMIN_SPORT.get(gtype) == a.template.sport:
                garmin_m = act; break
        if not garmin_m and len(day_acts) == 1:
            garmin_m = day_acts[0]

        if log or garmin_m:
            w.sessions_done += 1
            if log:
                w.tss_actual     += log.tss_real or 0
                w.dist_actual_km += log.dist_real or 0
            elif garmin_m:
                dist_m = garmin_m.get("distance") or 0
                w.dist_actual_km += round(dist_m / 1000, 2)
                w.tss_actual     += int(garmin_m.get("trainingStressScore") or 0)

    # ── CTL / ATL / TSB desde Garmin histórico ────────────────
    ctl = atl = tsb = None
    if garmin_all:
        # Construir serie diaria de TSS desde ctl_start hasta end
        tss_by_day: dict = {}
        for act in garmin_all:
            d_str = (act.get("startTimeLocal") or "")[:10]
            if d_str:
                tss_by_day[d_str] = tss_by_day.get(d_str, 0) + (act.get("trainingStressScore") or 0)

        # EWA: CTL τ=42, ATL τ=7
        ctl_val = 0.0
        atl_val = 0.0
        alpha_ctl = 2 / (42 + 1)
        alpha_atl = 2 / (7  + 1)

        ctl_start_d = _date.fromisoformat(ctl_start)
        end_d       = _date.fromisoformat(end)
        cur = ctl_start_d
        while cur <= end_d:
            tss_today = tss_by_day.get(cur.isoformat(), 0)
            ctl_val = ctl_val + alpha_ctl * (tss_today - ctl_val)
            atl_val = atl_val + alpha_atl * (tss_today - atl_val)
            cur += timedelta(days=1)

            ctl = round(ctl_val, 1)
        atl = round(atl_val, 1)
        tsb = round(ctl_val - atl_val, 1)

    # ── PMC history para gráfico (por semana, 26 semanas) ─────
    pmc_history = []
    if garmin_all:
        pmc_start = (_date.fromisoformat(end) - timedelta(weeks=26)).isoformat()
        tss_by_day2: dict = {}
        for act in garmin_all:
            d_str = (act.get("startTimeLocal") or "")[:10]
            if d_str and d_str >= pmc_start:
                tss_by_day2[d_str] = tss_by_day2.get(d_str, 0) + (act.get("trainingStressScore") or 0)
        # Agrupar por semana
        from collections import defaultdict
        by_week: dict = defaultdict(lambda: {"tss": 0, "ctl": 0.0, "atl": 0.0})
        # replay EWA desde ctl_start para tener valores correctos
        c2, a2 = 0.0, 0.0
        alpha_c, alpha_a = 2/(42+1), 2/(7+1)
        cur = _date.fromisoformat(ctl_start)
        end_d = _date.fromisoformat(end)
        while cur <= end_d:
            ts = tss_by_day.get(cur.isoformat(), 0)
            c2 = c2 + alpha_c*(ts - c2)
            a2 = a2 + alpha_a*(ts - a2)
            if cur.isoformat() >= pmc_start:
                dow = cur.weekday()
                wmon = (cur - timedelta(days=dow)).isoformat()
                by_week[wmon]["tss"] += ts
                by_week[wmon]["ctl"] = round(c2, 1)
                by_week[wmon]["atl"] = round(a2, 1)
                by_week[wmon]["tsb"] = round(c2 - a2, 1)
            cur += timedelta(days=1)
        pmc_history = [{"dt": k, "ctl": v["ctl"], "atl": v["atl"], "tsb": v["tsb"]} for k, v in sorted(by_week.items())]

    # ── ACWR ─────────────────────────────────────────────────
    acwr = None
    if garmin_all and ctl is not None and atl is not None:
        acwr = round(atl / ctl, 2) if ctl else None

    # ── Totales ───────────────────────────────────────────────
    total_planned = len(assignments)
    total_done    = sum(r.sessions_done for r in sport_map.values())
    tss_planned   = sum(r.tss_planned for r in sport_map.values())
    tss_actual    = sum(r.tss_actual  for r in sport_map.values())
    dist_total    = round(sum(r.dist_actual_km for r in sport_map.values()), 2)
    dur_total     = sum(r.dur_actual_min for r in sport_map.values())
    pct           = round(total_done / total_planned * 100, 1) if total_planned else 0.0

    return AthleteReport(
        athlete_id      = athlete_id,
        athlete_nombre  = athlete.nombre,
        period_start    = start,
        period_end      = end,
        sessions_total  = total_planned,
        sessions_done   = total_done,
        compliance_pct  = pct,
        tss_planned     = tss_planned,
        tss_actual      = tss_actual,
        dist_total_km   = dist_total,
        dur_total_min   = dur_total,
        by_sport        = sorted(sport_map.values(), key=lambda r: r.tss_planned, reverse=True),
        weeks           = sorted(week_map.values(), key=lambda w: w.week_start),
        ctl             = ctl,
        atl             = atl,
        tsb             = tsb,
        has_garmin      = has_garmin,
        pmc_history     = pmc_history,
        acwr            = acwr,
        race_goal_name  = athlete.race_goal_name,
        race_goal_date  = athlete.race_goal_date,
    )


# ── Alertas coach — P6 ──────────────────────────────────────
@router.get("/alerts")
def get_alerts(db: Session = Depends(get_db), coach: User = Depends(_coach)):
    """Atletas con fatigue>=4 o RPE>=8 en últimas 48h. Badge en coach.html."""
    from datetime import datetime, timedelta as _td
    cutoff_dt  = (datetime.utcnow() - _td(hours=48)).isoformat()
    cutoff_day = (datetime.utcnow() - _td(hours=48)).date().isoformat()

    group_ids = [g.id for g in db.query(Group).filter(Group.coach_id == coach.id).all()]
    if not group_ids:
        return {"alerts": [], "count": 0}
    athlete_ids = [
        m.user_id for m in
        db.query(GroupMember).filter(GroupMember.group_id.in_(group_ids)).all()
    ]

    alerts = []

    wellness_rows = (
        db.query(WellnessLog, User)
        .join(User, User.id == WellnessLog.user_id)
        .filter(
            WellnessLog.user_id.in_(athlete_ids),
            WellnessLog.date_iso >= cutoff_day,
            (WellnessLog.fatigue >= 4) | (WellnessLog.soreness >= 4),
        ).all()
    )
    for w, u in wellness_rows:
        parts = []
        if w.fatigue  and w.fatigue  >= 4: parts.append(f"Fatiga {w.fatigue}/5")
        if w.soreness and w.soreness >= 4: parts.append(f"Dolor {w.soreness}/5")
        alerts.append({
            "type": "wellness", "athlete_id": u.id, "athlete_name": u.nombre,
            "date": w.date_iso, "detail": " · ".join(parts),
            "level": "high" if (w.fatigue or 0) >= 5 or (w.soreness or 0) >= 5 else "warning",
        })

    rpe_rows = (
        db.query(WorkoutLog, User)
        .join(AssignedWorkout, AssignedWorkout.id == WorkoutLog.assignment_id)
        .join(User, User.id == WorkoutLog.user_id)
        .filter(
            WorkoutLog.user_id.in_(athlete_ids),
            WorkoutLog.rpe >= 8,
            WorkoutLog.logged_at >= cutoff_dt,
        ).all()
    )
    for log, u in rpe_rows:
        alerts.append({
            "type": "rpe", "athlete_id": u.id, "athlete_name": u.nombre,
            "date": str(log.logged_at)[:10], "detail": f"RPE {log.rpe}/10",
            "level": "high" if log.rpe >= 9 else "warning",
        })

    return {"alerts": alerts, "count": len(alerts)}


# ── Team Wellness summary ───────────────────────────────────
@router.get("/team-wellness")
def team_wellness(
    db: Session = Depends(get_db),
    coach: User = Depends(_coach)
):
    """Último registro de bienestar por atleta — para vista rápida en lista."""
    from datetime import date as _date, timedelta

    group_ids = [g.id for g in db.query(Group).filter(Group.coach_id == coach.id).all()]
    if not group_ids:
        return []

    athletes = (
        db.query(User)
        .join(GroupMember, GroupMember.athlete_id == User.id)
        .filter(GroupMember.group_id.in_(group_ids), User.activo == True)
        .distinct()
        .all()
    )

    today = _date.today().isoformat()
    cutoff = (_date.today() - timedelta(days=7)).isoformat()
    result = []
    for u in athletes:
        latest = (
            db.query(WellnessLog)
            .filter(WellnessLog.user_id == u.id, WellnessLog.date_iso >= cutoff)
            .order_by(WellnessLog.date_iso.desc())
            .first()
        )
        days_ago = None
        if latest:
            try:
                days_ago = (_date.fromisoformat(today) - _date.fromisoformat(latest.date_iso)).days
            except Exception:
                days_ago = None
        result.append({
            "athlete_id":   u.id,
            "athlete_name": u.nombre,
            "date_iso":     latest.date_iso if latest else None,
            "fatigue":      latest.fatigue  if latest else None,
            "sleep_q":      latest.sleep_q  if latest else None,
            "soreness":     latest.soreness if latest else None,
            "mood":         latest.mood     if latest else None,
            "days_ago":     days_ago,
        })
    return result
