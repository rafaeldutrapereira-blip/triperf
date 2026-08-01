from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, AssignedWorkout, WorkoutLog, WellnessLog, BloodLabExam, NutritionPlan,
    GarminActivity, GarminTrainingLoad, GarminSyncStatus, Message, AthleteNote,
    FoodDiaryEntry, GarminPlannedWorkout, RaceEvent, MentalCheckin, ActivityPhoto,
    WorkoutTemplate,
)
from ..schemas import (
    AssignedWorkoutOut, WorkoutLogCreate, WorkoutLogOut,
    GarminCredentials, GarminSyncResult, UserOut,
    AthleteProfileUpdate, GarminActivityOut,
)
from pydantic import BaseModel, field_validator
from datetime import date as _date
from ..auth import get_current_user, hash_password, require_role
from ..crypto import encrypt as _enc, decrypt as _dec, encrypt_if_plain, is_encrypted
from ..models import Group, GroupMember, Follow, CoachAthlete
from ..services.training_service import compute_acwr, compute_acwr_by_sport, build_training_alerts as _svc_alerts, build_daily_insight
from .mental_routes import _mfs_from_checkin
from ..garmin_pull_service import _CTL_DECAY, _ATL_DECAY

logger = logging.getLogger("labx.athlete")
router = APIRouter(prefix="/athlete", tags=["athlete"])


# ── Invitaciones de coach pendientes de aceptar (Caso B: el atleta ya
#    tenía cuenta propia en LabX antes de que un coach intentara agregarlo) ──
@router.get("/pending-coach-invites")
def list_pending_coach_invites(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    rows = (
        db.query(CoachAthlete, User)
        .join(User, User.id == CoachAthlete.coach_id)
        .filter(CoachAthlete.athlete_id == me.id, CoachAthlete.status == "pending")
        .all()
    )
    return [{"id": ca.id, "coach_nombre": u.nombre, "coach_email": u.email} for ca, u in rows]


@router.post("/pending-coach-invites/{ca_id}/accept")
def accept_coach_invite(ca_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    ca = db.query(CoachAthlete).filter(CoachAthlete.id == ca_id, CoachAthlete.athlete_id == me.id).first()
    if not ca:
        raise HTTPException(404, "Invitación no encontrada")
    ca.status = "active"
    if ca.group_id:
        already = db.query(GroupMember).filter(
            GroupMember.group_id == ca.group_id, GroupMember.athlete_id == me.id
        ).first()
        if not already:
            db.add(GroupMember(group_id=ca.group_id, athlete_id=me.id))
    db.commit()
    return {"ok": True}


@router.post("/pending-coach-invites/{ca_id}/reject")
def reject_coach_invite(ca_id: str, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    ca = db.query(CoachAthlete).filter(CoachAthlete.id == ca_id, CoachAthlete.athlete_id == me.id).first()
    if not ca:
        raise HTTPException(404, "Invitación no encontrada")
    db.delete(ca)
    db.commit()
    return {"ok": True}


def _read_garmin_pwd(user: "User", db: "Session") -> str | None:
    """
    Devuelve la contraseña Garmin descifrada.
    Si encuentra texto plano (legacy), lo cifra y persiste antes de devolver.
    """
    raw = user.garmin_password
    if not raw:
        return None
    if is_encrypted(raw):
        return _dec(raw)
    # Legacy plaintext — cifrar y persistir ahora
    encrypted = encrypt_if_plain(raw)
    if encrypted:
        user.garmin_password = encrypted
        try:
            db.commit()
            logger.warning("Lazy-migrated plaintext Garmin password for user %s", user.id)
        except Exception:
            db.rollback()
    return raw  # devolver el valor original (legible) en esta request


def _verify_coach_access(coach: User, athlete_id: str, db: Session) -> None:
    """Verifica que el coach (o admin) tiene acceso al atleta dado."""
    if coach.rol == "admin":
        return  # admin puede ver todo
    # Verifica que el atleta está en al menos un grupo del coach
    in_group = (
        db.query(GroupMember)
        .join(Group, Group.id == GroupMember.group_id)
        .filter(Group.coach_id == coach.id, GroupMember.athlete_id == athlete_id)
        .first()
    )
    if not in_group:
        raise HTTPException(403, "No tienes acceso a los datos de este atleta.")


@router.get("/plan", response_model=List[AssignedWorkoutOut])
def my_plan(
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user)
):
    """Entrenos asignados al atleta autenticado, con filtro de fechas opcional."""
    q = db.query(AssignedWorkout).filter(
        AssignedWorkout.athlete_id == me.id,
        AssignedWorkout.deleted_at.is_(None),
    )
    if start: q = q.filter(AssignedWorkout.date_iso >= start)
    if end:   q = q.filter(AssignedWorkout.date_iso <= end)
    return q.order_by(AssignedWorkout.date_iso).all()


@router.post("/log", response_model=WorkoutLogOut, status_code=201)
def log_workout(body: WorkoutLogCreate,
                db: Session = Depends(get_db),
                me: User = Depends(get_current_user)):
    """Registrar ejecución de un entreno asignado."""
    a = db.query(AssignedWorkout).filter(
        AssignedWorkout.id == body.assignment_id,
        AssignedWorkout.athlete_id == me.id
    ).first()
    if not a:
        raise HTTPException(404, "Entreno asignado no encontrado")

    existing = db.query(WorkoutLog).filter(
        WorkoutLog.assignment_id == body.assignment_id,
        WorkoutLog.user_id == me.id
    ).first()
    if existing:
        existing.tss_real   = body.tss_real
        existing.dist_real  = body.dist_real
        existing.dur_real   = body.dur_real
        existing.rpe        = body.rpe
        existing.completado = body.completado
        existing.notas      = body.notas
        db.commit(); db.refresh(existing)
        return existing

    log = WorkoutLog(
        user_id       = me.id,
        assignment_id = body.assignment_id,
        tss_real      = body.tss_real,
        dist_real     = body.dist_real,
        dur_real      = body.dur_real,
        rpe           = body.rpe,
        completado    = body.completado,
        notas         = body.notas,
    )
    db.add(log); db.commit(); db.refresh(log)
    return log


@router.get("/log", response_model=List[WorkoutLogOut])
def my_logs(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return db.query(WorkoutLog).filter(WorkoutLog.user_id == me.id)\
             .order_by(WorkoutLog.logged_at.desc()).all()


@router.post("/garmin-credentials", response_model=dict)
def save_garmin_credentials(
    body: GarminCredentials,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user)
):
    """
    Inicia la conexión con Garmin Connect.
    Si Garmin pide MFA retorna needs_mfa=True y el frontend muestra el campo de código.
    """
    try:
        from ..garmin_pull_service import start_mfa_flow
        # Guardar credenciales primero (el login las valida)
        me.garmin_email    = body.garmin_email
        me.garmin_password = _enc(body.garmin_password)
        db.commit()

        result = start_mfa_flow(me.id, body.garmin_email, body.garmin_password, db)
        if result.get("needs_mfa"):
            return {"ok": True, "needs_mfa": True, "garmin_email": body.garmin_email}
        if result.get("ok"):
            return {"ok": True, "needs_mfa": False, "garmin_email": body.garmin_email}
        # Login falló — revertir
        me.garmin_email    = None
        me.garmin_password = None
        db.commit()
        raise HTTPException(400, result.get("error", "Error al conectar con Garmin"))
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(500, "garminconnect no instalado en el servidor")
    except Exception as e:
        me.garmin_email    = None
        me.garmin_password = None
        db.commit()
        raise HTTPException(400, f"Error al conectar con Garmin: {e}")


@router.delete("/garmin-credentials", response_model=dict)
def remove_garmin_credentials(
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user)
):
    me.garmin_email    = None
    me.garmin_password = None
    db.commit()
    return {"ok": True}


@router.get("/profile", response_model=UserOut)
def my_profile(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    return UserOut.from_orm_user(me)


def _sync_goal_race_event(me: User, db: Session) -> None:
    """
    Mantiene sincronizada la carrera objetivo "simple" del perfil
    (User.race_goal_name/date/dist, editada desde Mi Perfil) con la tabla
    RaceEvent (is_goal_race=True) que consumen Mental→Pre-Carrera,
    Analytics→Goal Race Countdown y otras features de calendario de
    carreras. Sin esto, cargar la carrera solo en Perfil la deja invisible
    para cualquier feature que lea RaceEvent en vez de los campos simples.
    """
    existing = (
        db.query(RaceEvent)
        .filter(RaceEvent.user_id == me.id, RaceEvent.is_goal_race == True)
        .first()
    )
    if not me.race_goal_date:
        if existing:
            existing.is_goal_race = False
        return

    if existing:
        existing.name     = me.race_goal_name or existing.name or "Mi carrera objetivo"
        existing.date_iso = me.race_goal_date
        existing.distance = me.race_goal_dist or existing.distance
    else:
        import uuid as _uuid_mod
        db.add(RaceEvent(
            id           = str(_uuid_mod.uuid4()),
            user_id      = me.id,
            name         = me.race_goal_name or "Mi carrera objetivo",
            date_iso     = me.race_goal_date,
            distance     = me.race_goal_dist,
            is_goal_race = True,
        ))


@router.patch("/profile", response_model=dict)
def update_profile(
    body: AthleteProfileUpdate,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user)
):
    if body.nombre     is not None and body.nombre.strip(): me.nombre    = body.nombre.strip()
    if body.password:
        me.password_hash = hash_password(body.password)
    if body.race_goal_name is not None:
        me.race_goal_name = body.race_goal_name or None
    if body.race_goal_date is not None:
        me.race_goal_date = body.race_goal_date or None
    if body.race_goal_dist is not None:
        me.race_goal_dist = body.race_goal_dist or None
    if body.race_goal_name is not None or body.race_goal_date is not None or body.race_goal_dist is not None:
        _sync_goal_race_event(me, db)
    if body.ftp       is not None: me.ftp       = body.ftp
    if body.weight_kg is not None: me.weight_kg = body.weight_kg
    if body.height_cm is not None: me.height_cm = body.height_cm
    if body.age       is not None: me.age       = body.age
    if body.vo2max    is not None: me.vo2max    = body.vo2max
    if body.fcmax     is not None: me.fcmax     = body.fcmax
    if body.css       is not None: me.css       = body.css or None
    if body.run_pace  is not None: me.run_pace  = body.run_pace or None
    if body.sports    is not None: me.sports    = body.sports or None
    if body.onboarding_done:
        from datetime import datetime, timezone
        if not me.onboarding_completed_at:
            me.onboarding_completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True}


@router.get("/garmin/activities", response_model=List[GarminActivityOut])
def garmin_activities(
    start: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit: int           = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user)
):
    """
    Pull activities from the athlete's own Garmin Connect account.
    Requires garmin_email + garmin_password stored for this user.
    """
    if not me.garmin_email or not me.garmin_password:
        raise HTTPException(400, "Configura tus credenciales Garmin en Mi Perfil")

    from datetime import date, timedelta
    today = date.today().isoformat()
    _start = start or (date.today() - timedelta(days=30)).isoformat()
    _end   = end   or today

    _pwd = _read_garmin_pwd(me, db)
    try:
        from garminconnect import Garmin
        client = Garmin(me.garmin_email, _pwd)
        client.login()
        raw = client.get_activities_by_date(_start, _end) or []
    except ImportError:
        raise HTTPException(500, "garminconnect no instalado en el servidor")
    except Exception as e:
        raise HTTPException(502, f"Error conectando con Garmin: {e}")

    result = []
    for a in raw[:limit]:
        dist_m = a.get("distance") or 0
        result.append(GarminActivityOut(
            activity_id   = a.get("activityId"),
            name          = a.get("activityName"),
            sport         = a.get("activityType", {}).get("typeKey", ""),
            start_time    = a.get("startTimeLocal"),
            duration_secs = a.get("duration"),
            distance_km   = round(dist_m / 1000, 2) if dist_m else None,
            average_hr    = a.get("averageHR"),
            max_hr        = a.get("maxHR"),
            calories      = a.get("calories"),
            tss           = a.get("trainingStressScore"),
        ))
    return result


# ─────────────────────────────────────────────
# WELLNESS DIARIO
# ─────────────────────────────────────────────
class WellnessCreate(BaseModel):
    date_iso:  str = None   # YYYY-MM-DD, default hoy
    fatigue:   Optional[int] = None  # 1-5
    sleep_q:   Optional[int] = None  # 1-5
    soreness:  Optional[int] = None  # 1-5
    mood:      Optional[int] = None  # 1-5
    weight_kg: Optional[float] = None
    notes:     Optional[str]   = None

    @field_validator("date_iso", mode="before")
    @classmethod
    def _validate_date(cls, v):
        if v is None:
            return v
        from datetime import date as _d
        try:
            _d.fromisoformat(str(v))
        except ValueError:
            raise ValueError("date_iso debe ser YYYY-MM-DD")
        return v

    @field_validator("fatigue", "sleep_q", "soreness", "mood", mode="before")
    @classmethod
    def _clamp_1_5(cls, v):
        if v is None:
            return v
        v = int(v)
        if not (1 <= v <= 5):
            raise ValueError("El valor debe estar entre 1 y 5")
        return v

class WellnessOut(BaseModel):
    id: str; user_id: str; date_iso: str
    fatigue: Optional[int]; sleep_q: Optional[int]
    soreness: Optional[int]; mood: Optional[int]
    weight_kg: Optional[float]; notes: Optional[str]
    logged_at: str
    model_config = {"from_attributes": True}
    @classmethod
    def from_orm(cls, w):
        return cls(id=w.id, user_id=w.user_id, date_iso=w.date_iso,
                   fatigue=w.fatigue, sleep_q=w.sleep_q, soreness=w.soreness,
                   mood=w.mood, weight_kg=w.weight_kg, notes=w.notes,
                   logged_at=str(w.logged_at)[:19])


@router.post("/wellness", response_model=WellnessOut)
def log_wellness(body: WellnessCreate, db: Session = Depends(get_db),
                 me: User = Depends(get_current_user)):
    today = _date.today().isoformat()
    dt    = body.date_iso or today
    existing = db.query(WellnessLog).filter(
        WellnessLog.user_id == me.id, WellnessLog.date_iso == dt
    ).first()
    if existing:
        if body.fatigue  is not None: existing.fatigue  = body.fatigue
        if body.sleep_q  is not None: existing.sleep_q  = body.sleep_q
        if body.soreness is not None: existing.soreness = body.soreness
        if body.mood     is not None: existing.mood     = body.mood
        if body.weight_kg is not None: existing.weight_kg = body.weight_kg
        if body.notes    is not None: existing.notes    = body.notes
        db.commit(); db.refresh(existing)
        return WellnessOut.from_orm(existing)
    w = WellnessLog(user_id=me.id, date_iso=dt, fatigue=body.fatigue,
                    sleep_q=body.sleep_q, soreness=body.soreness, mood=body.mood,
                    weight_kg=body.weight_kg, notes=body.notes)
    db.add(w); db.commit(); db.refresh(w)
    return WellnessOut.from_orm(w)


@router.get("/wellness", response_model=List[WellnessOut])
def get_wellness(days: int = Query(30, ge=1, le=365),
                 db: Session = Depends(get_db),
                 me: User = Depends(get_current_user)):
    from datetime import timedelta
    cutoff = (_date.today() - timedelta(days=days)).isoformat()
    rows = db.query(WellnessLog).filter(
        WellnessLog.user_id == me.id, WellnessLog.date_iso >= cutoff
    ).order_by(WellnessLog.date_iso.desc()).all()
    return [WellnessOut.from_orm(r) for r in rows]


@router.get("/wellness/coach/{athlete_id}", response_model=List[WellnessOut])
def coach_get_wellness(
    athlete_id: str,
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
    coach: User = Depends(require_role("coach", "admin")),
):
    _verify_coach_access(coach, athlete_id, db)
    from datetime import timedelta
    cutoff = (_date.today() - timedelta(days=days)).isoformat()
    rows = db.query(WellnessLog).filter(
        WellnessLog.user_id == athlete_id, WellnessLog.date_iso >= cutoff
    ).order_by(WellnessLog.date_iso.desc()).all()
    return [WellnessOut.from_orm(r) for r in rows]


# ─────────────────────────────────────────────
# BLOOD LAB EXAMS — P1
# ─────────────────────────────────────────────
import json as _json

class BloodLabCreate(BaseModel):
    date_iso:    str
    lab_name:    Optional[str] = None
    context:     Optional[str] = None
    values_json: str           # JSON string con marcadores

class BloodLabOut(BaseModel):
    id: str; user_id: str; date_iso: str
    lab_name: Optional[str]; context: Optional[str]
    values_json: str; created_at: str
    model_config = {"from_attributes": True}
    @classmethod
    def from_orm(cls, b):
        return cls(id=b.id, user_id=b.user_id, date_iso=b.date_iso,
                   lab_name=b.lab_name, context=b.context,
                   values_json=b.values_json, created_at=str(b.created_at)[:19])


@router.post("/blood-labs", response_model=BloodLabOut, status_code=201)
def save_blood_lab(body: BloodLabCreate, db: Session = Depends(get_db),
                   me: User = Depends(get_current_user)):
    existing = db.query(BloodLabExam).filter(
        BloodLabExam.user_id == me.id, BloodLabExam.date_iso == body.date_iso
    ).first()
    if existing:
        existing.lab_name   = body.lab_name
        existing.context    = body.context
        existing.values_json = body.values_json
        db.commit(); db.refresh(existing)
        return BloodLabOut.from_orm(existing)
    exam = BloodLabExam(user_id=me.id, date_iso=body.date_iso,
                        lab_name=body.lab_name, context=body.context,
                        values_json=body.values_json)
    db.add(exam); db.commit(); db.refresh(exam)
    return BloodLabOut.from_orm(exam)


@router.get("/blood-labs", response_model=List[BloodLabOut])
def get_blood_labs(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    rows = db.query(BloodLabExam).filter(BloodLabExam.user_id == me.id)\
             .order_by(BloodLabExam.date_iso.asc()).all()
    return [BloodLabOut.from_orm(r) for r in rows]


@router.get("/blood-labs/coach/{athlete_id}", response_model=List[BloodLabOut])
def coach_get_blood_labs(
    athlete_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(require_role("coach", "admin")),
):
    _verify_coach_access(coach, athlete_id, db)
    rows = db.query(BloodLabExam).filter(BloodLabExam.user_id == athlete_id)\
             .order_by(BloodLabExam.date_iso.asc()).all()
    return [BloodLabOut.from_orm(r) for r in rows]


@router.delete("/blood-labs/{exam_id}", response_model=dict)
def delete_blood_lab(exam_id: str, db: Session = Depends(get_db),
                     me: User = Depends(get_current_user)):
    exam = db.query(BloodLabExam).filter(
        BloodLabExam.id == exam_id, BloodLabExam.user_id == me.id
    ).first()
    if not exam:
        raise HTTPException(404, "Examen no encontrado")
    db.delete(exam); db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────
# NUTRITION PLANS — P2
# ─────────────────────────────────────────────
class NutritionPlanCreate(BaseModel):
    race_name:   Optional[str]   = None
    race_date:   Optional[str]   = None
    race_dist:   Optional[str]   = None
    total_kcal:  Optional[int]   = None
    cho_g:       Optional[float] = None
    fluid_ml:    Optional[int]   = None
    sodium_mg:   Optional[int]   = None
    params_json: Optional[str]   = None   # JSON completo de parámetros

class NutritionPlanOut(BaseModel):
    id: str; user_id: str
    race_name: Optional[str]; race_date: Optional[str]; race_dist: Optional[str]
    total_kcal: Optional[int]; cho_g: Optional[float]
    fluid_ml: Optional[int]; sodium_mg: Optional[int]
    params_json: Optional[str]; created_at: str; updated_at: str
    model_config = {"from_attributes": True}
    @classmethod
    def from_orm(cls, n):
        return cls(id=n.id, user_id=n.user_id, race_name=n.race_name,
                   race_date=n.race_date, race_dist=n.race_dist,
                   total_kcal=n.total_kcal, cho_g=n.cho_g,
                   fluid_ml=n.fluid_ml, sodium_mg=n.sodium_mg,
                   params_json=n.params_json,
                   created_at=str(n.created_at)[:19],
                   updated_at=str(n.updated_at or n.created_at)[:19])


@router.post("/nutrition-plan", response_model=NutritionPlanOut, status_code=201)
def save_nutrition_plan(body: NutritionPlanCreate, db: Session = Depends(get_db),
                        me: User = Depends(get_current_user)):
    existing = db.query(NutritionPlan).filter(NutritionPlan.user_id == me.id).first()
    if existing:
        if body.race_name  is not None: existing.race_name  = body.race_name
        if body.race_date  is not None: existing.race_date  = body.race_date
        if body.race_dist  is not None: existing.race_dist  = body.race_dist
        if body.total_kcal is not None: existing.total_kcal = body.total_kcal
        if body.cho_g      is not None: existing.cho_g      = body.cho_g
        if body.fluid_ml   is not None: existing.fluid_ml   = body.fluid_ml
        if body.sodium_mg  is not None: existing.sodium_mg  = body.sodium_mg
        if body.params_json is not None: existing.params_json = body.params_json
        from datetime import datetime as _dt
        existing.updated_at = _dt.utcnow()
        db.commit(); db.refresh(existing)
        return NutritionPlanOut.from_orm(existing)
    plan = NutritionPlan(user_id=me.id, race_name=body.race_name,
                         race_date=body.race_date, race_dist=body.race_dist,
                         total_kcal=body.total_kcal, cho_g=body.cho_g,
                         fluid_ml=body.fluid_ml, sodium_mg=body.sodium_mg,
                         params_json=body.params_json)
    db.add(plan); db.commit(); db.refresh(plan)
    return NutritionPlanOut.from_orm(plan)


@router.get("/nutrition-plan", response_model=Optional[NutritionPlanOut])
def get_nutrition_plan(db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    plan = db.query(NutritionPlan).filter(NutritionPlan.user_id == me.id).first()
    return NutritionPlanOut.from_orm(plan) if plan else None


@router.get("/nutrition-plan/coach/{athlete_id}", response_model=Optional[NutritionPlanOut])
def coach_get_nutrition_plan(
    athlete_id: str,
    db: Session = Depends(get_db),
    coach: User = Depends(require_role("coach", "admin")),
):
    _verify_coach_access(coach, athlete_id, db)
    plan = db.query(NutritionPlan).filter(NutritionPlan.user_id == athlete_id).first()
    return NutritionPlanOut.from_orm(plan) if plan else None


# ─────────────────────────────────────────────────────────────────────────────
# DASHBOARD — datos históricos Garmin para el atleta autenticado
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def athlete_dashboard(
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
    fresh: bool    = Query(False, description="Ignorar caché y recalcular"),
):
    """
    Devuelve el equivalente de window.KL_DATA para el atleta autenticado,
    construido desde las tablas garmin_activities + garmin_training_load.
    El frontend llama esto justo después del login para cargar datos fresh.
    Caché Redis de 5 minutos (si disponible).
    """
    from datetime import date as _date_, timedelta as _td
    from ..redis_client import cache_get, cache_set

    cache_key = f"dashboard:{me.id}"
    if not fresh:
        cached = cache_get(cache_key)
        if cached:
            return cached

    today_iso = _date_.today().isoformat()

    # ── Training load (CTL/ATL/TSB) ──────────────────────────────────────────
    load_rows = (
        db.query(GarminTrainingLoad)
          .filter(GarminTrainingLoad.user_id == me.id)
          .order_by(GarminTrainingLoad.date_iso)
          .all()
    )

    latest_load = load_rows[-1] if load_rows else None
    if latest_load:
        # Proyectar CTL/ATL forward con TSS=0 si hubo días sin sync (evita lag de fechas)
        _ctl_proj = latest_load.ctl
        _atl_proj = latest_load.atl
        _gap_start = _date_.fromisoformat(latest_load.date_iso) + _td(days=1)
        _cur = _gap_start
        while _cur <= _date_.today():
            _ctl_proj *= _CTL_DECAY
            _atl_proj *= _ATL_DECAY
            _cur += _td(days=1)
        ctl = round(_ctl_proj, 1)
        atl = round(_atl_proj, 1)
        tsb = round(_ctl_proj - _atl_proj, 1)
    else:
        ctl = atl = tsb = 0
    # TSS semana calendario (lunes → hoy), consistente con Resumen Semanal
    _week_start_iso = (_date_.today() - _td(days=_date_.today().weekday())).isoformat()
    tss_wk  = sum(r.tss for r in load_rows if r.date_iso >= _week_start_iso) if load_rows else 0

    # CTL change (vs 7 días atrás)
    ctl_week_ago = load_rows[-8].ctl if len(load_rows) >= 8 else 0
    ctl_change   = round(ctl - ctl_week_ago, 1)

    # ACWR (7:28) — BP-03: usa compute_acwr del service que maneja acute=0 / no_data
    acwr, acwr_zone = compute_acwr(list(load_rows))
    acwr_by_sport = compute_acwr_by_sport(me.id, db)

    # Mental Fatigue Score del check-in más reciente (hoy o ayer — se acepta
    # ayer para no perder la señal por el mismo desfase de huso horario ya
    # corregido en mental.html: "hoy" en UTC puede ya haber rotado mientras
    # todavía es "hoy" en la tarde/noche de Chile).
    _mental_recent = (
        db.query(MentalCheckin)
          .filter(MentalCheckin.user_id == me.id)
          .order_by(MentalCheckin.date_iso.desc())
          .first()
    )
    mental_score = None
    if _mental_recent:
        _days_old = (_date_.today() - _date_.fromisoformat(_mental_recent.date_iso)).days
        if _days_old <= 1:
            mental_score = _mfs_from_checkin(_mental_recent)

    # ── PMC (historial completo, muestreado semanal) + ACWR history ─────────
    # Sin tope de fecha: la opción "Todo" de detalle.html filtra en el
    # cliente sobre este mismo payload, así que si acá se corta a 52
    # semanas, "Todo" nunca puede mostrar más que eso aunque haya años de
    # historial real sincronizado.
    # Los últimos _PMC_DAILY_DAYS días van día por día (no solo domingos):
    # detalle.html filtra "Semana"/"Mes" recortando este mismo arreglo por
    # fecha, así que con muestreo semanal esas dos pestañas casi nunca
    # tenían más de 1 punto real dentro de la ventana pedida.
    _PMC_DAILY_DAYS = 35
    _pmc_daily_cutoff_iso = (_date_.today() - _td(days=_PMC_DAILY_DAYS)).isoformat()
    pmc = []
    acwr_history = []
    mo  = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    load_list = list(load_rows)  # already ordered by date_iso asc
    for idx, r in enumerate(load_list):
        try:
            dt = _date_.fromisoformat(r.date_iso)
        except ValueError:
            continue
        if dt.weekday() == 6 or r.date_iso >= _pmc_daily_cutoff_iso:
            pmc.append({
                "dt":  r.date_iso,
                "l":   f"{dt.day} {mo[dt.month-1]}",
                "ctl": round(r.ctl, 1),
                "atl": round(r.atl, 1),
                "tss": round(r.tss, 1),
                "tsb": round(r.tsb, 1),
            })
            # ACWR at this date: 7-day avg / 28-day avg TSS
            slice28 = load_list[max(0, idx-27):idx+1]
            slice7  = load_list[max(0, idx-6):idx+1]
            if len(slice7) >= 4:
                chronic28 = sum(x.tss for x in slice28) / len(slice28) if slice28 else 0
                acute7    = sum(x.tss for x in slice7)  / len(slice7)
                acwr_val  = round(acute7 / chronic28, 2) if chronic28 > 1 else 0.0
                acwr_history.append({"dt": r.date_iso, "acwr": acwr_val})

    # TSS Semanal (suma real de los 7 días de cada semana calendario) —
    # independiente del muestreo de "pmc" de arriba. "pmc" solo trae 1 fila
    # por domingo para semanas viejas, así que sumar tss ahí da el TSS de
    # UN SOLO día disfrazado de "semanal" (bug real reportado por un tester:
    # "me marca muy pocos TSS" — la barra se veía correcta solo en las
    # semanas recientes, que sí tienen datos diarios completos).
    _tss_wk_buckets = {}
    _tss_wk_order = []
    for r in load_list:
        try:
            dt = _date_.fromisoformat(r.date_iso)
        except ValueError:
            continue
        wk_iso = (dt - _td(days=dt.weekday())).isoformat()  # lunes de esa semana
        if wk_iso not in _tss_wk_buckets:
            _tss_wk_buckets[wk_iso] = 0.0
            _tss_wk_order.append(wk_iso)
        _tss_wk_buckets[wk_iso] += r.tss or 0
    tss_weekly = [{"wk": wk, "tss": round(_tss_wk_buckets[wk], 1)} for wk in _tss_wk_order]

    # ── Activities (últimos 100 días, no últimas N filas) ─────────────────────
    # El "Progreso Semanal" del dashboard grafica 12 semanas (84 días). Un
    # límite de filas (antes: 100 filas) se agota mucho antes de esa ventana
    # para atletas que entrenan varias veces al día, dejando semanas reales
    # vacías por recorte de payload, no por falta de datos reales.
    _acts_cutoff_iso = (_date_.today() - _td(days=100)).isoformat()
    acts_orm = (
        db.query(GarminActivity)
          .filter(GarminActivity.user_id == me.id, GarminActivity.date_iso >= _acts_cutoff_iso)
          .order_by(GarminActivity.date_iso.desc())
          .limit(500)
          .all()
    )
    activities = []
    for a in acts_orm:
        activities.append({
            "activity_id": a.activity_id,
            "name":        a.name,
            "sport":       a.sport,
            "icon":        a.icon,
            "color":       a.color,
            "stroke":      a.stroke,
            "date_iso":    a.date_iso,
            "date_label":  a.date_label,
            "dur_min":     a.dur_min,
            "dist_km":     a.dist_km,
            "avg_hr":      a.avg_hr,
            "avg_power":   a.avg_power,
            "pace_str":    a.pace_str,
            "swim_pace":   a.swim_pace,
            "calories":    a.calories,
            "tss":         a.tss,
            "avg_cadence_spm": a.avg_cadence_spm,
        })

    # ── Disciplinas esta semana ───────────────────────────────────────────────
    week_start = (_date_.today() - _td(days=_date_.today().weekday())).isoformat()
    week_acts  = [a for a in activities if a["date_iso"] >= week_start]

    swim_km = round(sum(a["dist_km"] or 0 for a in week_acts if a["sport"] == "swim"), 2)
    bike_km = round(sum(a["dist_km"] or 0 for a in week_acts if a["sport"] == "bike"), 2)
    run_km  = round(sum(a["dist_km"] or 0 for a in week_acts if a["sport"] == "run"),  2)
    gym_n   = sum(1 for a in week_acts if a["sport"] == "gym")
    # Minutos reales por disciplina — respaldo para comparar contra el plan
    # cuando el entrenamiento planificado es por duración/potencia y no
    # define una distancia objetivo (ej. bloques de bici con target de watts).
    swim_min = round(sum(a["dur_min"] or 0 for a in week_acts if a["sport"] == "swim"), 1)
    bike_min = round(sum(a["dur_min"] or 0 for a in week_acts if a["sport"] == "bike"), 1)
    run_min  = round(sum(a["dur_min"] or 0 for a in week_acts if a["sport"] == "run"),  1)

    # ── Sync status ───────────────────────────────────────────────────────────
    sync_row = db.query(GarminSyncStatus).filter(GarminSyncStatus.user_id == me.id).first()
    last_sync = str(sync_row.last_sync_at)[:16] if (sync_row and sync_row.last_sync_at) else None

    # ── Salud Garmin ─────────────────────────────────────────────────────────
    from ..models import GarminHealthDaily, GarminSleepSession, PlanSession

    # Últimas 14 filas de salud diaria para tendencias (7d vs 7d anterior)
    health_rows_14 = (
        db.query(GarminHealthDaily)
        .filter(GarminHealthDaily.user_id == me.id)
        .order_by(GarminHealthDaily.date_iso.desc())
        .limit(14)
        .all()
    )
    health_today  = health_rows_14[0] if health_rows_14 else None
    health_7d_ago = health_rows_14[7] if len(health_rows_14) >= 8 else None
    sleep_today = (
        db.query(GarminSleepSession)
        .filter(GarminSleepSession.user_id == me.id)
        .order_by(GarminSleepSession.date_iso.desc())
        .first()
    )

    # ── Históricos para wellbeing charts ─────────────────────────────────────
    # Sin tope de fecha (ver el mismo comentario en el bloque de PMC más
    # arriba): la opción "Todo" de detalle.html necesita el historial
    # completo, no solo los últimos 90/365 días.
    _health_90 = (
        db.query(GarminHealthDaily)
        .filter(GarminHealthDaily.user_id == me.id)
        .order_by(GarminHealthDaily.date_iso.asc())
        .all()
    )
    _health_vo2 = (
        db.query(GarminHealthDaily)
        .filter(GarminHealthDaily.user_id == me.id,
                (GarminHealthDaily.vo2max_running.isnot(None)) |
                (GarminHealthDaily.vo2max_cycling.isnot(None)))
        .order_by(GarminHealthDaily.date_iso.asc())
        .all()
    )
    _sleep_90 = (
        db.query(GarminSleepSession)
        .filter(GarminSleepSession.user_id == me.id)
        .order_by(GarminSleepSession.date_iso.asc())
        .all()
    )
    hrv_history = [
        {"dt": r.date_iso, "hrv": r.hrv_last_night, "hrv_avg": r.hrv_weekly_avg,
         "bb": r.body_battery_end, "stress": r.avg_stress, "rhr": r.resting_hr}
        for r in _health_90
        if r.hrv_last_night is not None or r.body_battery_end is not None
    ]
    sleep_history = [
        {"dt": r.date_iso, "h": round(r.total_min / 60, 1) if r.total_min else None,
         "score": r.sleep_score, "deep": round(r.deep_min / 60, 1) if r.deep_min else None,
         "rem": round(r.rem_min / 60, 1) if r.rem_min else None}
        for r in _sleep_90
        if r.total_min is not None
    ]
    rhr_history = [
        {"dt": r.date_iso, "rhr": r.resting_hr}
        for r in _health_90 if r.resting_hr is not None
    ]
    bb_history = [
        {"dt": r.date_iso, "bb": r.body_battery_end}
        for r in _health_90 if r.body_battery_end is not None
    ]
    # "running" (generic) es lo que Garmin Connect muestra como "VO2 Max"
    # en el reloj/app — se prioriza de forma CONSISTENTE en toda la serie
    # (no por fila) para no mezclar dos métricas distintas en un mismo
    # gráfico. Solo se usa "cycling" si no hay ningún running en la ventana.
    _vo2_running_rows = [r for r in _health_vo2 if r.vo2max_running is not None]
    if _vo2_running_rows:
        vo2_history = [{"dt": r.date_iso, "vo2": r.vo2max_running} for r in _vo2_running_rows]
    else:
        vo2_history = [{"dt": r.date_iso, "vo2": r.vo2max_cycling}
                       for r in _health_vo2 if r.vo2max_cycling is not None]
    vo2max_garmin = vo2_history[-1]["vo2"] if vo2_history else None

    # Garmin calcula el VO2max por separado para running y ciclismo (son
    # estimaciones distintas, no la misma métrica con dos nombres) — se
    # exponen las 2 series reales para mostrarlas desglosadas en el
    # dashboard, en vez de solo la versión "blended" (vo2_history de arriba,
    # que prioriza running y se usa para no romper vistas que ya la leían).
    vo2_history_running = [{"dt": r.date_iso, "vo2": r.vo2max_running} for r in _vo2_running_rows]
    vo2_history_cycling = [{"dt": r.date_iso, "vo2": r.vo2max_cycling}
                            for r in _health_vo2 if r.vo2max_cycling is not None]
    vo2max_running_garmin = vo2_history_running[-1]["vo2"] if vo2_history_running else None
    vo2max_cycling_garmin = vo2_history_cycling[-1]["vo2"] if vo2_history_cycling else None

    hrv_last_night   = health_today.hrv_last_night    if health_today else None
    hrv_7d_avg       = health_today.hrv_weekly_avg     if health_today else None
    body_battery_end = health_today.body_battery_end   if health_today else None
    stress_avg       = health_today.avg_stress         if health_today else None
    resting_hr       = health_today.resting_hr         if health_today else None

    sleep_score      = sleep_today.sleep_score  if sleep_today else None
    sleep_total_h    = round(sleep_today.total_min / 60, 1) if (sleep_today and sleep_today.total_min) else None
    sleep_deep_h     = round(sleep_today.deep_min  / 60, 1) if (sleep_today and sleep_today.deep_min)  else None

    # Readiness: usa el MISMO motor (readiness_service / DRS, Sprint 23) que
    # ya usan las otras 15+ páginas vía dash-header.js → GET /readiness/daily.
    # Antes este endpoint calculaba el suyo propio (context_engine.py, motor
    # viejo de 5 factores con pesos distintos, con fallback a un "50+TSB"
    # todavía más simple) — bug real encontrado auditando "los otros KPIs"
    # a pedido del usuario: dashboard.html mostraba un número de Readiness
    # y cualquier otra página mostraba OTRO, ambos para el mismo día del
    # mismo usuario (verificado con datos reales: 59 vs 68 el mismo día).
    from ..services.readiness_service import compute_daily_readiness_for_user
    _drs_report = compute_daily_readiness_for_user(me.id, db)
    readiness_score = _drs_report.drs

    # Tendencias HRV (7 días)
    # HRV trend: hoy vs hace 7 días
    hrv_trend = None
    if health_today and health_7d_ago:
        h_new = health_today.hrv_last_night
        h_old = health_7d_ago.hrv_last_night
        if h_new and h_old:
            hrv_trend = round(h_new - h_old, 1)

    # RHR (frecuencia cardíaca en reposo): trend hoy vs hace 7 días + promedio 7d
    rhr_trend = None
    if health_today and health_7d_ago:
        r_new = health_today.resting_hr
        r_old = health_7d_ago.resting_hr
        if r_new and r_old:
            rhr_trend = round(r_new - r_old, 1)
    rhr_vals_7d = [r.resting_hr for r in health_rows_14[:7] if r.resting_hr is not None]
    rhr_7d_avg = round(sum(rhr_vals_7d) / len(rhr_vals_7d), 1) if rhr_vals_7d else None

    # Training Readiness con label + color (B-05)
    tr_score = health_today.training_readiness if health_today else None
    if tr_score is None:
        tr_label = None; tr_color = None
    elif tr_score >= 73:
        tr_label = "Listo para entrenar fuerte"; tr_color = "#10B981"
    elif tr_score >= 50:
        tr_label = "Buena forma"; tr_color = "#EAB308"
    elif tr_score >= 26:
        tr_label = "Recuperación recomendada"; tr_color = "#F97316"
    else:
        tr_label = "Descanso necesario"; tr_color = "#EF4444"

    # Body Battery trend (hoy vs hace 7 días)
    bb_trend = None
    if health_today and health_7d_ago:
        bb_now = health_today.body_battery_end
        bb_old = health_7d_ago.body_battery_end
        if bb_now is not None and bb_old is not None:
            bb_trend = round(bb_now - bb_old)

    # Sleep trend (7d avg vs anterior 7d)
    sleep_rows = (
        db.query(GarminSleepSession)
        .filter(GarminSleepSession.user_id == me.id)
        .order_by(GarminSleepSession.date_iso.desc())
        .limit(14)
        .all()
    )
    sleep_7d_avg  = None
    sleep_prev_avg= None
    if len(sleep_rows) >= 1:
        recent_h = [r.total_min for r in sleep_rows[:7]  if r.total_min]
        prev_h   = [r.total_min for r in sleep_rows[7:]  if r.total_min]
        if recent_h: sleep_7d_avg   = round(sum(recent_h)/len(recent_h)/60, 1)
        if prev_h:   sleep_prev_avg = round(sum(prev_h)  /len(prev_h)  /60, 1)
    sleep_trend = round(sleep_7d_avg - sleep_prev_avg, 1) if (sleep_7d_avg and sleep_prev_avg) else None

    # TSS semanal trend (esta semana vs semana anterior calendario)
    _prev_week_start = (_date_.today() - _td(days=_date_.today().weekday() + 7)).isoformat()
    tss_prev_wk = sum(r.tss for r in load_rows if _prev_week_start <= r.date_iso < _week_start_iso) if load_rows else None
    tss_wk_trend = round(tss_wk - tss_prev_wk, 1) if tss_prev_wk is not None else None
    # % en vez de puntos absolutos — solo tiene sentido si hubo carga la
    # semana pasada (con prev=0 el % es indefinido, no "infinito positivo")
    tss_wk_trend_pct = (
        round((tss_wk - tss_prev_wk) / tss_prev_wk * 100, 1)
        if tss_prev_wk is not None and tss_prev_wk > 0 else None
    )

    # Compliance semanal desde plan_sessions (B-22)
    compliance_week = None
    try:
        cutoff_7 = (_date_.today() - _td(days=7)).isoformat()
        plan_sessions_week = (
            db.query(PlanSession)
            .filter(
                PlanSession.athlete_id == me.id,
                PlanSession.date_iso  >= cutoff_7,
                PlanSession.is_skipped == False,
            )
            .all()
        )
        if plan_sessions_week:
            completed = [s for s in plan_sessions_week if s.completed_at is not None]
            compliance_week = round(len(completed) / len(plan_sessions_week) * 100)
    except Exception:
        pass

    # Compliance trend (7d anterior)
    compliance_prev = None
    try:
        cutoff_14 = (_date_.today() - _td(days=14)).isoformat()
        prev_sessions = (
            db.query(PlanSession)
            .filter(
                PlanSession.athlete_id == me.id,
                PlanSession.date_iso  >= cutoff_14,
                PlanSession.date_iso  <  cutoff_7,
                PlanSession.is_skipped == False,
            )
            .all()
        )
        if prev_sessions:
            prev_done = [s for s in prev_sessions if s.completed_at is not None]
            compliance_prev = round(len(prev_done) / len(prev_sessions) * 100)
    except Exception:
        pass

    compliance_trend = round(compliance_week - compliance_prev) if (compliance_week is not None and compliance_prev is not None) else None

    result = {
        "source":       "api_db",
        "generated":    today_iso,
        "last_sync":    last_sync,
        "garmin_email": me.garmin_email,
        # KPI métricas
        "ctl":          ctl,
        "atl":          atl,
        "tsb":          tsb,
        "ctl_change":   ctl_change,
        "tss_week":     round(tss_wk, 1),
        "acwr":         acwr,
        "acwr_zone":    acwr_zone,
        "acwr_by_sport": acwr_by_sport,
        "readiness":    readiness_score,
        # Salud Garmin (Sprint 1)
        "hrv_last_night":   hrv_last_night,
        "hrv_7d_avg":       hrv_7d_avg,
        "hrv_trend":        hrv_trend,
        "body_battery":     body_battery_end,
        "sleep_score":      sleep_score,
        "sleep_total_h":    sleep_total_h,
        "sleep_deep_h":     sleep_deep_h,
        "stress_avg":       stress_avg,
        "resting_hr":       resting_hr,
        "rhr_7d_avg":       rhr_7d_avg,
        "rhr_trend":        rhr_trend,
        "readiness_source": "drs",
        # Training Readiness desglosado (B-05)
        "training_readiness":       tr_score,
        "training_readiness_label": tr_label,
        "training_readiness_color": tr_color,
        # Trends semana anterior (B-06)
        "trends": {
            "ctl":        ctl_change,
            "tss_week":   tss_wk_trend,
            "tss_week_pct": tss_wk_trend_pct,
            "hrv":        hrv_trend,
            "rhr":        rhr_trend,
            "body_battery": bb_trend,
            "sleep_h":    sleep_trend,
            "compliance": compliance_trend,
        },
        # Compliance semanal (B-22)
        "compliance_week":  compliance_week,
        "compliance_prev":  compliance_prev,
        # PMC
        "pmc": pmc,
        "acwr_history": acwr_history,
        "tss_weekly": tss_weekly,
        # Históricos wellbeing (90 días) para detalle.html?metric=wellbeing
        "sleep_history": sleep_history,
        "hrv_history":   hrv_history,
        "rhr_history":   rhr_history,
        "bb_history":    bb_history,
        "vo2max_garmin": vo2max_garmin,
        "vo2_history":   vo2_history,
        "vo2max_running_garmin": vo2max_running_garmin,
        "vo2max_cycling_garmin": vo2max_cycling_garmin,
        "vo2_history_running":   vo2_history_running,
        "vo2_history_cycling":   vo2_history_cycling,
        # Actividades
        "activities": activities,
        "streak_days": _current_streak_days(acts_orm),
        "injury_risk": _dashboard_injury_risk(me.id, db),
        # Resumen semanal por disciplina
        "weekly_disc": {
            "swim_km":    swim_km,
            "bike_km":    bike_km,
            "run_km":     run_km,
            "strength_n": gym_n,
            "swim_min":   swim_min,
            "bike_min":   bike_min,
            "run_min":    run_min,
        },
        # Carrera objetivo
        "race_goal_name": me.race_goal_name,
        "race_goal_date": me.race_goal_date,
        # Alertas de sobreentrenamiento
        "alerts": _svc_alerts(tsb=tsb, acwr=acwr, acwr_zone=acwr_zone, ctl=ctl),
        # Insight del día — síntesis carga + recuperación en una sola conclusión
        "insight": build_daily_insight(
            tsb=tsb, atl=atl, ctl=ctl, acwr=acwr, acwr_zone=acwr_zone,
            hrv_last_night=hrv_last_night, hrv_7d_avg=hrv_7d_avg, hrv_trend=hrv_trend,
            sleep_total_h=sleep_total_h, sleep_trend=sleep_trend, rhr_trend=rhr_trend,
            acwr_by_sport=acwr_by_sport, mental_score=mental_score,
        ),
        # Entrenamientos planificados (Training Peaks → Garmin → LabX)
        "planned_workouts": _get_planned_week(db, me.id),  # ver _get_planned_range() abajo
    }
    cache_set(cache_key, result, ttl_seconds=300)
    return result


def _get_planned_range(db: Session, user_id: str, start_iso: str, end_iso: str) -> list:
    """Devuelve los workouts planificados (Training Peaks/Garmin) entre start_iso y end_iso."""
    rows = (
        db.query(GarminPlannedWorkout)
          .filter(
              GarminPlannedWorkout.user_id  == user_id,
              GarminPlannedWorkout.date_iso >= start_iso,
              GarminPlannedWorkout.date_iso <= end_iso,
          )
          .order_by(GarminPlannedWorkout.date_iso)
          .all()
    )
    # Dedup por (fecha, workout_id): a veces Garmin/TrainingPeaks empuja el
    # MISMO workout al calendario dos veces con scheduledWorkoutId distintos
    # (confirmado: mismo workout_id, dos filas) — sin esto, el "Cumplimiento
    # Semanal" del dashboard sumaba el TSS planificado doble para ese día.
    #
    # NO se deduplica por "mismo día + mismo deporte + TSS parecido pero
    # workout_id distinto" — se intentó (un caso parecía duplicado: dos
    # bloques de ciclismo el mismo día, ~154 TSS cada uno, "outdoor" e
    # "indoor") pero el usuario confirmó que son 2 sesiones reales distintas
    # programadas a propósito por su coach (doble sesión el mismo día). TSS
    # similar en el mismo día NO es evidencia suficiente de duplicado.
    seen = set()
    out = []
    for r in rows:
        dedup_key = (r.date_iso, r.workout_id) if r.workout_id else None
        if dedup_key and dedup_key in seen:
            continue
        if dedup_key:
            seen.add(dedup_key)
        out.append({
            "date_iso": r.date_iso,
            "title":    r.title,
            "sport":    r.sport,
            "dur_min":  r.dur_min,
            "dist_km":  r.dist_km,
            "tss":      r.tss_planned,
            # True = TSS calculado con objetivo real por paso (preciso);
            # False = aproximación por promedio de sesión completa (puede
            # sobreestimar en series con descanso, ver _estimate_planned_tss);
            # None = no se pudo estimar.
            "tss_precise": r.tss_planned_precise,
            "source":   r.source,
        })
    return out


def _get_planned_week(db: Session, user_id: str) -> list:
    """Devuelve los workouts planificados de la semana actual (lun→dom)."""
    from datetime import date, timedelta
    today = date.today()
    mon   = today - timedelta(days=today.weekday())
    sun   = mon + timedelta(days=6)
    return _get_planned_range(db, user_id, mon.isoformat(), sun.isoformat())


@router.get("/planned-workouts")
def get_planned_workouts_range(
    start: str = Query(..., description="YYYY-MM-DD"),
    end:   str = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """
    Workouts planificados (Training Peaks/Garmin, tabla garmin_planned_workouts)
    en un rango de fechas arbitrario. Usado por training_plan.html para calcular
    "Cumplimiento" en las vistas Mes/Período, no solo la semana actual (que es lo
    único que cubre planned_workouts dentro de /athlete/dashboard).
    """
    return _get_planned_range(db, me.id, start, end)


# ─────────────────────────────────────────────
# HUELLA DE DATOS — conteos reales por categoría (para la flor dinámica)
# ─────────────────────────────────────────────

_FOOTPRINT_WINDOW_DAYS = {"month": 30, "year": 365}


@router.get("/data-footprint")
def get_data_footprint(
    period: str = Query(default="all", pattern="^(week|month|year|all)$"),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Cuenta cuántos registros REALES tiene el atleta por categoría de dato
    Garmin — usado por huella.html para dibujar la flor dinámica con el
    tamaño de cada pétalo proporcional a la cobertura real de esa métrica.
    Nunca inventa números: si una categoría está vacía, cuenta 0.

    `period` acota la ventana de conteo: week (lunes→hoy, semana calendario)
    | month (30d) | year (365d) | all (todo el historial, default).
    """
    from datetime import timedelta as _td
    from ..models import GarminHealthDaily, GarminSleepSession

    cutoff_iso = None
    window_len = None
    if period == "week":
        monday = _date.today() - _td(days=_date.today().weekday())
        cutoff_iso = monday.isoformat()
        window_len = (_date.today() - monday).days + 1  # lunes→hoy, inclusive
    elif period in _FOOTPRINT_WINDOW_DAYS:
        window_len = _FOOTPRINT_WINDOW_DAYS[period]
        cutoff_iso = (_date.today() - _td(days=window_len - 1)).isoformat()

    def _count(query, model):
        if cutoff_iso:
            query = query.filter(model.date_iso >= cutoff_iso)
        return query.count()

    activities = _count(db.query(GarminActivity).filter(GarminActivity.user_id == me.id), GarminActivity)
    training_load_days = _count(db.query(GarminTrainingLoad).filter(GarminTrainingLoad.user_id == me.id), GarminTrainingLoad)
    vo2_days = _count(
        db.query(GarminHealthDaily)
        .filter(GarminHealthDaily.user_id == me.id)
        .filter((GarminHealthDaily.vo2max_running.isnot(None)) | (GarminHealthDaily.vo2max_cycling.isnot(None))),
        GarminHealthDaily,
    )
    body_battery_days = _count(
        db.query(GarminHealthDaily)
        .filter(GarminHealthDaily.user_id == me.id, GarminHealthDaily.body_battery_end.isnot(None)),
        GarminHealthDaily,
    )
    sleep_nights = _count(
        db.query(GarminSleepSession)
        .filter(GarminSleepSession.user_id == me.id, GarminSleepSession.total_min.isnot(None)),
        GarminSleepSession,
    )
    hrv_days = _count(
        db.query(GarminHealthDaily)
        .filter(GarminHealthDaily.user_id == me.id, GarminHealthDaily.hrv_last_night.isnot(None)),
        GarminHealthDaily,
    )

    def _sum_km(sport=None):
        from sqlalchemy import func as _func
        q = db.query(_func.sum(GarminActivity.dist_km)).filter(GarminActivity.user_id == me.id)
        if cutoff_iso:
            q = q.filter(GarminActivity.date_iso >= cutoff_iso)
        if sport:
            q = q.filter(GarminActivity.sport == sport)
        total = q.scalar()
        return round(total, 1) if total else 0.0

    total_km = _sum_km()
    swim_km  = _sum_km("swim")
    bike_km  = _sum_km("bike")
    run_km   = _sum_km("run")

    # Días conectado = desde la actividad más antigua hasta hoy (ventana real de historial),
    # acotado a la ventana del período elegido (week/month/year) cuando corresponde.
    first_act = (
        db.query(GarminActivity)
        .filter(GarminActivity.user_id == me.id)
        .order_by(GarminActivity.date_iso.asc())
        .first()
    )
    days_connected = None
    first_sync_date = None
    if first_act:
        first_sync_date = first_act.date_iso
        try:
            days_connected = (_date.today() - _date.fromisoformat(first_act.date_iso)).days
        except ValueError:
            days_connected = None
        if days_connected is not None and window_len is not None:
            days_connected = min(days_connected, window_len)

    return {
        "period":              period,
        "activities":         activities,
        "training_load_days": training_load_days,
        "vo2_days":            vo2_days,
        "body_battery_days":   body_battery_days,
        "sleep_nights":        sleep_nights,
        "hrv_days":            hrv_days,
        "days_connected":      days_connected,
        "first_sync_date":     first_sync_date,
        "total_km":            total_km,
        "swim_km":             swim_km,
        "bike_km":             bike_km,
        "run_km":              run_km,
    }


# ─────────────────────────────────────────────
# PERSONAL RECORDS
# ─────────────────────────────────────────────

class _PRIn(BaseModel):
    # Nombres alineados con lo que manda el formulario de Records en
    # athlete_profile.html (antes este schema pedía value_sec/value_disp/
    # achieved_at, campos que el frontend nunca mandó — todo POST fallaba
    # 422 y el usuario solo veía "Error guardando record").
    sport:  str | None = None
    event:  str
    time:   str                    # "hh:mm:ss", "mm:ss" o segundos — se parsea abajo
    date:   str | None = None
    place:  str | None = None
    source: str = "manual"
    notes:  str | None = None


def _parse_time_to_sec(raw: str) -> float:
    """Acepta 'hh:mm:ss', 'mm:ss' o un número de segundos plano."""
    raw = (raw or "").strip()
    parts = raw.split(":")
    try:
        if len(parts) == 3:
            h, m, s = parts
            return int(h) * 3600 + int(m) * 60 + float(s)
        if len(parts) == 2:
            m, s = parts
            return int(m) * 60 + float(s)
        return float(raw)
    except ValueError:
        raise HTTPException(400, f"Formato de marca inválido: '{raw}' (usa hh:mm:ss o mm:ss)")


@router.get("/cycle-compare")
def cycle_compare(
    race_a:  str | None = Query(None, description="id de RaceEvent — ciclo A (opcional, atajo si ya está registrada)"),
    race_b:  str | None = Query(None, description="id de RaceEvent — ciclo B (opcional)"),
    race_c:  str | None = Query(None, description="id de RaceEvent — ciclo C (opcional, tercer ciclo)"),
    date_a:  str | None = Query(None, description="YYYY-MM-DD — día de referencia del ciclo A, alternativa a race_a"),
    date_b:  str | None = Query(None, description="YYYY-MM-DD — día de referencia del ciclo B, alternativa a race_b"),
    date_c:  str | None = Query(None, description="YYYY-MM-DD — día de referencia del ciclo C, alternativa a race_c"),
    label_a: str | None = Query(None, max_length=80),
    label_b: str | None = Query(None, max_length=80),
    label_c: str | None = Query(None, max_length=80),
    weeks:   int = Query(16, ge=4, le=52, description="semanas de bloque a comparar antes de cada fecha de referencia"),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Compara dos o tres bloques de entrenamiento (ej. el mismo ciclo
    sept-dic de años distintos) alineados por "días hasta el día de
    referencia" en vez de fecha de calendario — así el pico de carga de
    un año queda superpuesto sobre el punto equivalente del ciclo de
    otro año, sin importar que las fechas de calendario no coincidan.

    El día de referencia de cada ciclo puede venir de una carrera ya
    registrada (race_a/race_b/race_c) o elegirse directamente con
    date_a/date_b/date_c — no hace falta pasar por el Predictor de
    Carrera. El ciclo C es opcional: si no se manda race_c ni date_c,
    la respuesta solo trae cycle_a y cycle_b.
    """
    from datetime import timedelta as _td

    def _resolve_anchor(race_id: str | None, date_str: str | None, label: str | None, fallback_label: str):
        if race_id:
            race = (
                db.query(RaceEvent)
                  .filter(RaceEvent.id == race_id, RaceEvent.user_id == me.id)
                  .first()
            )
            if not race:
                raise HTTPException(404, f"Carrera {race_id} no encontrada")
            return {
                "id": race.id, "name": race.name, "date_iso": race.date_iso,
                "distance": race.distance,
            }
        if date_str:
            try:
                _date.fromisoformat(date_str)
            except ValueError:
                raise HTTPException(400, f"Fecha inválida: {date_str}")
            return {"id": None, "name": label or fallback_label, "date_iso": date_str, "distance": None}
        raise HTTPException(400, "Indica race_a/race_b (carrera registrada) o date_a/date_b (fecha directa)")

    _SPORT_LABELS_ES = {
        "swim": "natación", "bike": "ciclismo", "run": "carrera",
        "gym": "fuerza", "strength": "fuerza", "other": "otras actividades",
    }

    def _load_cycle(anchor: dict):
        anchor_date = _date.fromisoformat(anchor["date_iso"])
        window_start = (anchor_date - _td(weeks=weeks)).isoformat()
        rows = (
            db.query(GarminTrainingLoad)
              .filter(GarminTrainingLoad.user_id == me.id,
                      GarminTrainingLoad.date_iso >= window_start,
                      GarminTrainingLoad.date_iso <= anchor["date_iso"])
              .order_by(GarminTrainingLoad.date_iso.asc())
              .all()
        )
        series = []
        for r in rows:
            d = _date.fromisoformat(r.date_iso)
            series.append({
                "days_to_race": (d - anchor_date).days,
                "date_iso":     r.date_iso,
                "ctl":          round(r.ctl, 1),
                "atl":          round(r.atl, 1),
                "tsb":          round(r.tsb, 1),
                "tss":          round(r.tss, 1),
            })

        peak_ctl      = max((p["ctl"] for p in series), default=0)
        ctl_race_day  = series[-1]["ctl"] if series else None
        tsb_race_day  = series[-1]["tsb"] if series else None
        total_tss     = round(sum(p["tss"] for p in series), 0)

        # ── Qué explica la curva: desglose de las actividades reales del
        # bloque (no solo el resultado CTL/TSB/TSS, sino la causa: cuántas
        # horas, cuántas sesiones, qué tan intensas, en qué disciplina, y
        # con qué consistencia semana a semana).
        acts = (
            db.query(GarminActivity)
              .filter(GarminActivity.user_id == me.id,
                      GarminActivity.date_iso >= window_start,
                      GarminActivity.date_iso <= anchor["date_iso"])
              .all()
        )
        sessions = len(acts)
        total_hours = round(sum(a.dur_min or 0 for a in acts) / 60, 1)
        act_tss_sum = sum(a.tss or 0 for a in acts)
        avg_tss_per_session = round(act_tss_sum / sessions, 1) if sessions else None

        hours_by_sport: dict[str, float] = {}
        for a in acts:
            sp = (a.sport or "other").lower()
            hours_by_sport[sp] = hours_by_sport.get(sp, 0.0) + (a.dur_min or 0) / 60

        active_week_idxs = {
            (_date.fromisoformat(a.date_iso) - anchor_date).days // 7
            for a in acts
        }
        consistency_pct = round(len(active_week_idxs) / weeks * 100) if weeks else None

        return {
            "race": anchor,
            "series": series,
            "stats": {
                "peak_ctl":     round(peak_ctl, 1),
                "ctl_race_day": ctl_race_day,
                "tsb_race_day": tsb_race_day,
                "total_tss":    total_tss,
                "has_data":     len(series) > 0,
            },
            "breakdown": {
                "total_hours":          total_hours,
                "sessions":             sessions,
                "avg_tss_per_session":  avg_tss_per_session,
                "hours_by_sport":       {k: round(v, 1) for k, v in hours_by_sport.items()},
                "active_weeks":         len(active_week_idxs),
                "total_weeks":          weeks,
                "consistency_pct":      consistency_pct,
            },
        }

    def _build_insight(labeled_cycles: list[dict]) -> str | None:
        """Resumen ejecutivo de una línea: por qué el mejor ciclo fue mejor."""
        withdata = [c for c in labeled_cycles if c["cycle"]["stats"]["has_data"]]
        if len(withdata) < 2:
            return None
        ranked = sorted(withdata, key=lambda c: c["cycle"]["stats"]["peak_ctl"], reverse=True)
        best, worst = ranked[0], ranked[-1]
        if best["cycle"]["stats"]["peak_ctl"] == worst["cycle"]["stats"]["peak_ctl"]:
            return None

        bb, wb = best["cycle"]["breakdown"], worst["cycle"]["breakdown"]
        hour_diff = round(bb["total_hours"] - wb["total_hours"], 1)

        sports = set(list(bb["hours_by_sport"].keys()) + list(wb["hours_by_sport"].keys()))
        sport_diffs = {
            sp: round(bb["hours_by_sport"].get(sp, 0) - wb["hours_by_sport"].get(sp, 0), 1)
            for sp in sports
        }
        dominant_sport = max(sport_diffs, key=lambda k: abs(sport_diffs[k])) if sport_diffs else None
        dominant_diff  = sport_diffs.get(dominant_sport, 0) if dominant_sport else 0

        parts = []
        if hour_diff > 0.5:
            parts.append(f"{best['label']} acumuló {hour_diff}h más de entrenamiento que {worst['label']}")
        elif hour_diff < -0.5:
            parts.append(f"{best['label']} entrenó {abs(hour_diff)}h menos que {worst['label']} pero logró más fitness")
        else:
            parts.append(f"{best['label']} y {worst['label']} entrenaron un volumen similar")

        if dominant_sport and abs(dominant_diff) > 1:
            sport_es = _SPORT_LABELS_ES.get(dominant_sport, dominant_sport)
            if dominant_diff > 0:
                parts.append(f", principalmente en {sport_es} (+{dominant_diff}h)")
            else:
                parts.append(f", pese a tener menos volumen en {sport_es} ({dominant_diff}h)")

        ca, cw = bb.get("consistency_pct"), wb.get("consistency_pct")
        if ca is not None and cw is not None and abs(ca - cw) >= 15:
            parts.append(f" y una consistencia semanal mayor ({ca}% vs {cw}% de semanas activas)")

        return "".join(parts) + "."

    anchor_a = _resolve_anchor(race_a, date_a, label_a, "Ciclo A")
    anchor_b = _resolve_anchor(race_b, date_b, label_b, "Ciclo B")

    cycle_a = _load_cycle(anchor_a)
    cycle_b = _load_cycle(anchor_b)
    labeled = [
        {"label": anchor_a["name"], "cycle": cycle_a},
        {"label": anchor_b["name"], "cycle": cycle_b},
    ]

    if race_c or date_c:
        anchor_c = _resolve_anchor(race_c, date_c, label_c, "Ciclo C")
        cycle_c = _load_cycle(anchor_c)
        labeled.append({"label": anchor_c["name"], "cycle": cycle_c})
    else:
        cycle_c = None

    return {
        "weeks":   weeks,
        "cycle_a": cycle_a,
        "cycle_b": cycle_b,
        "cycle_c": cycle_c,
        "insight": _build_insight(labeled),
    }


@router.get("/personal-records")
def get_personal_records(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Lista todas las marcas personales del atleta."""
    from ..models import PersonalRecord
    prs = (
        db.query(PersonalRecord)
        .filter(PersonalRecord.user_id == me.id)
        .order_by(PersonalRecord.event, PersonalRecord.value_sec)
        .all()
    )
    return [
        {
            "id":           pr.id,
            "event":        pr.event,
            "sport":        pr.sport,
            "place":        pr.place,
            "value_sec":    pr.value_sec,
            "value_disp":   pr.value_disp,
            "achieved_at":  pr.achieved_at,
            "source":       pr.source,
            "notes":        pr.notes,
        }
        for pr in prs
    ]


@router.post("/personal-records", status_code=201)
def upsert_personal_record(
    body: _PRIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """
    Crea o actualiza una marca personal.
    Si ya existe un PR para ese evento y el nuevo tiempo es mejor, lo reemplaza.
    """
    from ..models import PersonalRecord
    value_sec = _parse_time_to_sec(body.time)
    if value_sec <= 0:
        raise HTTPException(400, "El tiempo debe ser mayor a 0 segundos")

    existing = (
        db.query(PersonalRecord)
        .filter(PersonalRecord.user_id == me.id, PersonalRecord.event == body.event)
        .order_by(PersonalRecord.value_sec)
        .first()
    )

    if existing and value_sec >= existing.value_sec:
        # No es un nuevo PR
        return {
            "improved": False,
            "current": {
                "value_sec": existing.value_sec,
                "value_disp": existing.value_disp,
                "achieved_at": existing.achieved_at,
            },
            "message": f"Tu PR actual es {existing.value_disp or existing.value_sec}s. Este resultado no lo mejora.",
        }

    pr = PersonalRecord(
        user_id=me.id,
        event=body.event,
        sport=body.sport,
        place=body.place,
        value_sec=value_sec,
        value_disp=body.time,
        achieved_at=body.date,
        source=body.source,
        notes=body.notes,
    )
    db.add(pr)
    db.commit()
    db.refresh(pr)
    return {
        "improved": True,
        "pr": {
            "id":          pr.id,
            "event":       pr.event,
            "sport":       pr.sport,
            "place":       pr.place,
            "value_sec":   pr.value_sec,
            "value_disp":  pr.value_disp,
            "achieved_at": pr.achieved_at,
        },
        "message": "¡Nuevo récord personal!",
    }


@router.delete("/personal-records/{pr_id}")
def delete_personal_record(
    pr_id: str,
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    from ..models import PersonalRecord
    pr = db.query(PersonalRecord).filter(
        PersonalRecord.id == pr_id,
        PersonalRecord.user_id == me.id,
    ).first()
    if not pr:
        raise HTTPException(404, "Registro no encontrado")
    db.delete(pr)
    db.commit()
    return {"ok": True}


@router.post("/garmin/sync")
def garmin_sync_now(
    background_tasks: BackgroundTasks,
    force: bool      = Query(False, description="Forzar sync aunque los datos sean recientes"),
    db: Session      = Depends(get_db),
    me: User         = Depends(get_current_user),
):
    """
    Dispara manualmente un sync Garmin en background.
    El frontend puede llamar este endpoint con un botón "Actualizar".
    La respuesta es inmediata; el sync ocurre en background.
    """
    if not me.garmin_email:
        raise HTTPException(400, "No tienes credenciales Garmin configuradas. Ve a Mi Perfil.")

    from ..garmin_pull_service import dispatch_garmin_sync
    dispatch_garmin_sync(me.id, background_tasks, force=force)

    sync_row = db.query(GarminSyncStatus).filter(GarminSyncStatus.user_id == me.id).first()
    return {
        "ok":        True,
        "status":    "syncing",
        "last_sync": str(sync_row.last_sync_at)[:16] if (sync_row and sync_row.last_sync_at) else None,
        "message":   "Sync iniciado en background. Refresca el dashboard en ~30s.",
    }


@router.get("/garmin/sync-status")
def garmin_sync_status(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Devuelve el estado actual del sync Garmin del atleta."""
    has_credentials = bool(me.garmin_email and me.garmin_password)
    row = db.query(GarminSyncStatus).filter(GarminSyncStatus.user_id == me.id).first()
    if not row:
        return {"status": "never", "last_sync": None, "activities_total": 0,
                "has_credentials": has_credentials}
    return {
        "status":           row.status,
        "last_sync":        str(row.last_sync_at)[:16] if row.last_sync_at else None,
        "activities_total": row.activities_total,
        "error":            row.error,
        "has_credentials":  has_credentials,
    }


@router.post("/garmin/reauth")
def garmin_reauth_start(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Inicia el flujo de reautorización Garmin.
    Garmin envía un código MFA al email/teléfono del atleta.
    Si no necesita MFA retorna needs_mfa=False directamente.
    """
    if not me.garmin_email or not me.garmin_password:
        raise HTTPException(400, "No tienes credenciales Garmin. Ve a Mi Perfil.")
    from ..garmin_pull_service import start_mfa_flow
    pwd = _read_garmin_pwd(me, db)
    result = start_mfa_flow(me.id, me.garmin_email, pwd, db)
    return result


@router.post("/garmin/reauth/mfa")
def garmin_reauth_mfa(
    body: dict,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Recibe el código MFA que el atleta ingresó y completa la autenticación."""
    code = (body.get("code") or "").strip()
    if not code:
        raise HTTPException(400, "Ingresa el código MFA")
    from ..garmin_pull_service import submit_mfa_code
    result = submit_mfa_code(me.id, code, db)
    if not result["ok"]:
        raise HTTPException(400, result.get("error", "Error MFA"))
    return {"ok": True, "message": "Garmin reautorizado — sync automático activo"}


# ─────────────────────────────────────────────────────────────────────────────
# I-16: Actividades con filtros y paginación
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/activities")
def list_activities(
    sport:    Optional[str] = Query(None, description="swim | bike | run | gym | walk"),
    from_dt:  Optional[str] = Query(None, alias="from", description="YYYY-MM-DD inicio"),
    to_dt:    Optional[str] = Query(None, alias="to",   description="YYYY-MM-DD fin"),
    page:     int           = Query(1,   ge=1),
    per_page: int           = Query(50,  ge=1, le=200),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    I-16: Lista actividades del atleta con filtros opcionales por deporte y rango de fechas.
    Paginada (máx 200 por página).
    """
    q = db.query(GarminActivity).filter(GarminActivity.user_id == me.id)
    if sport:
        q = q.filter(GarminActivity.sport == sport)
    if from_dt:
        q = q.filter(GarminActivity.date_iso >= from_dt)
    if to_dt:
        q = q.filter(GarminActivity.date_iso <= to_dt)
    q = q.order_by(GarminActivity.date_iso.desc())

    total    = q.count()
    items    = q.offset((page - 1) * per_page).limit(per_page).all()
    pages    = max(1, (total + per_page - 1) // per_page)

    return {
        "items":    [_activity_dict(a) for a in items],
        "total":    total,
        "page":     page,
        "per_page": per_page,
        "pages":    pages,
        "has_next": page < pages,
        "has_prev": page > 1,
    }


@router.get("/activities/{activity_id}")
def get_activity_detail(
    activity_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Detalle de una actividad puntual (para training_detail.html).
    Visible si es propia o de alguien que seguís en Comunidad."""
    act = _find_viewable_activity(activity_id, me, db)
    if not act:
        raise HTTPException(404, "Actividad no encontrada")
    out = _activity_dict(act)
    is_own = act.user_id == me.id
    owner = me if is_own else db.query(User).filter(User.id == act.user_id).first()
    out["is_own"]     = is_own
    out["owner_name"] = None if is_own else (owner.nombre or owner.email.split("@")[0]) if owner else None
    out["share_url"]  = f"/public_activity.html?t={act.share_token}" if (is_own and act.share_token) else None

    if not is_own and owner:
        prefs = _get_share_prefs(owner)
        if not prefs["share_hr"]:
            out["avg_hr"] = None
        if not prefs["share_power"]:
            out["avg_power"] = None
        if not prefs["share_pace"]:
            out["pace_str"]  = None
            out["swim_pace"] = None

    return out


@router.post("/activities/{activity_id}/share")
def share_activity(
    activity_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Genera (o devuelve el existente) link público de la actividad —
    accesible sin login por cualquiera que tenga la URL exacta, igual que
    'compartir' de Google Docs. Solo el dueño puede generarlo."""
    import secrets
    act = db.query(GarminActivity).filter(
        GarminActivity.activity_id == activity_id,
        GarminActivity.user_id == me.id,
    ).first()
    if not act:
        raise HTTPException(404, "Actividad no encontrada")
    if not act.share_token:
        act.share_token = secrets.token_urlsafe(16)
        db.commit()
    return {"ok": True, "share_token": act.share_token, "share_url": f"/public_activity.html?t={act.share_token}"}


@router.delete("/activities/{activity_id}/share")
def unshare_activity(
    activity_id: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Revoca el link público — cualquiera que lo tuviera guardado deja de poder verlo."""
    act = db.query(GarminActivity).filter(
        GarminActivity.activity_id == activity_id,
        GarminActivity.user_id == me.id,
    ).first()
    if not act:
        raise HTTPException(404, "Actividad no encontrada")
    act.share_token = None
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Indoor Workout Builder (indoor_workout.html) → envío directo a Garmin.
# A diferencia de la asignación de un coach (workout_delivery.py), acá el
# atleta arma su propio workout y lo manda a SU PROPIA cuenta Garmin — mismo
# motor de traducción de bloques (garmin_connector.py, Sprints A-E), pero
# sin pasar por AssignedWorkout/WorkoutTemplate (esto nunca se guarda en
# LabX, solo se genera y se envía).
# ─────────────────────────────────────────────────────────────────────────────

class _SendToGarminIn(BaseModel):
    name:   str
    date:   str  # YYYY-MM-DD
    blocks: list


def _blocks_total_duration_sec(blocks: list) -> int:
    total = 0
    for b in blocks:
        if b.get("type") == "intervals":
            total += int(b.get("repeat", 1)) * (int(b.get("on_duration", 0)) + int(b.get("off_duration", 0)))
        else:
            total += int(b.get("duration", 0))
    return total


@router.post("/indoor-workout/send-to-garmin")
def send_indoor_workout_to_garmin(
    body: _SendToGarminIn,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Envía un workout armado en indoor_workout.html directo a la cuenta
    Garmin del propio atleta logueado — sin descargar ni importar archivos."""
    if not me.garmin_email or not me.garmin_password:
        raise HTTPException(400, "Conectá tu cuenta Garmin desde tu Perfil antes de poder enviar entrenamientos.")
    if not me.ftp:
        raise HTTPException(400, "Configurá tu FTP en tu Perfil para calcular los objetivos de potencia.")
    if not body.blocks:
        raise HTTPException(400, "El entrenamiento no tiene bloques.")

    from garmin_connector import schedule_workout_for_athlete
    from ..crypto import decrypt_credential

    session = {
        "name":        body.name or "LabX Indoor Workout",
        "sport":       "bike",
        "dur_min":     _blocks_total_duration_sec(body.blocks) / 60,
        "dist_km":     0,
        "notes":       "",
        "blocks_json": json.dumps(body.blocks),
        "ftp":         me.ftp,
    }
    try:
        result = schedule_workout_for_athlete(
            session          = session,
            target_date      = body.date,
            athlete_id       = me.id,
            athlete_email    = me.garmin_email,
            athlete_password = decrypt_credential(me.garmin_password),
        )
    except Exception as e:
        raise HTTPException(502, f"No se pudo enviar a Garmin: {e}")

    return {"ok": True, "workout_id": result.get("workoutId"), "date": body.date}


@router.get("/zones")
def get_training_zones(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    S12: Zonas de entrenamiento personalizadas basadas en las métricas del atleta.
    Requiere: fcmax (FC), ftp (potencia), run_pace (ritmo), css (natación).
    """
    from ..services.training_service import athlete_zones
    zones = athlete_zones(me)
    if not zones:
        return {
            "ok":      False,
            "message": "Configura tus métricas (FTP, FC máx, ritmo umbral, CSS) en tu perfil para ver las zonas.",
            "zones":   {},
        }
    return {"ok": True, "zones": zones, "metrics": {
        "ftp":      me.ftp,
        "fcmax":    me.fcmax,
        "run_pace": me.run_pace,
        "css":      me.css,
    }}


def _activity_dict(a: GarminActivity) -> dict:
    return {
        "activity_id":    a.activity_id,
        "id":             a.id,
        "sport":          a.sport,
        "name":           a.name,
        "date_iso":       a.date_iso,
        "dur_min":        a.dur_min,
        "dist_km":        a.dist_km,
        "avg_hr":         a.avg_hr,
        "avg_power":      a.avg_power,
        "pace_str":       a.pace_str,
        "swim_pace":      a.swim_pace,
        "calories":       a.calories,
        "tss":            a.tss,
        "icon":           a.icon,
        "swolf":          a.swolf,
        "avg_cadence_spm":a.avg_cadence_spm,
        "pool_length_m":  a.pool_length_m,
        "aerobic_te":     a.aerobic_te,
        "anaerobic_te":   a.anaerobic_te,
        "te_label":       a.te_label,
        "photo_url":      ("/api/athlete/activities/"+a.id+"/photo") if a.photo_path else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# I-13: GDPR — Exportar todos los datos del atleta
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/export")
def export_athlete_data(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    I-13: GDPR Art.20 — Portabilidad de datos. Devuelve todos los datos del atleta en JSON.
    Incluye: perfil, actividades, training load, wellness, blood labs, workout logs, records.
    """
    from ..models import PersonalRecord, WellnessLog, BloodLabExam, WorkoutLog

    # Perfil (sin password_hash, sin credentials)
    profile = {
        "id":             me.id,
        "email":          me.email,
        "nombre":         me.nombre,
        "rol":            me.rol,
        "plan_nivel":     me.plan_nivel,
        "ftp":            me.ftp,
        "weight_kg":      me.weight_kg,
        "height_cm":      me.height_cm,
        "vo2max":         me.vo2max,
        "fcmax":          me.fcmax,
        "css":            me.css,
        "run_pace":       me.run_pace,
        "race_goal_name": me.race_goal_name,
        "race_goal_date": me.race_goal_date,
        "created_at":     str(me.created_at),
        "garmin_email":   me.garmin_email,  # email, nunca la contraseña
    }

    activities = [_activity_dict(a) for a in
                  db.query(GarminActivity).filter(GarminActivity.user_id == me.id)
                    .order_by(GarminActivity.date_iso.asc()).all()]

    tl_rows = db.query(GarminTrainingLoad).filter(GarminTrainingLoad.user_id == me.id)\
                .order_by(GarminTrainingLoad.date_iso.asc()).all()
    training_load = [{"date": r.date_iso, "ctl": r.ctl, "atl": r.atl, "tsb": r.tsb, "tss": r.tss}
                     for r in tl_rows]

    wellness = [{"date": w.date_iso, "fatigue": w.fatigue, "sleep_q": w.sleep_q,
                 "soreness": w.soreness, "mood": w.mood, "notas": w.notas}
                for w in db.query(WellnessLog)
                           .filter(WellnessLog.user_id == me.id, WellnessLog.deleted_at == None)
                           .all()]

    blood = [{"date": b.date_iso, "param": b.parameter, "value": b.value, "unit": b.unit}
             for b in db.query(BloodLabExam)
                        .filter(BloodLabExam.user_id == me.id, BloodLabExam.deleted_at == None)
                        .all()]

    logs = [{"date": l.date_iso, "sport": l.sport, "dur_min": l.dur_min,
              "dist_km": l.dist_km, "notas": l.notas, "tss": l.tss}
            for l in db.query(WorkoutLog)
                       .filter(WorkoutLog.user_id == me.id, WorkoutLog.deleted_at == None)
                       .all()]

    prs = [{"event": p.event, "value_sec": p.value_sec, "value_disp": p.value_disp,
             "achieved_at": p.achieved_at, "source": p.source}
           for p in db.query(PersonalRecord).filter(PersonalRecord.user_id == me.id).all()]

    return {
        "export_version": "1.0",
        "exported_at":    datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "profile":        profile,
        "activities":     activities,
        "training_load":  training_load,
        "wellness_logs":  wellness,
        "blood_labs":     blood,
        "workout_logs":   logs,
        "personal_records": prs,
    }


# ─────────────────────────────────────────────────────────────────────────────
# I-14: Derecho al olvido — Borrar cuenta completa (GDPR Art.17)
# ─────────────────────────────────────────────────────────────────────────────

@router.delete("/account")
def delete_account(
    body: dict,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """
    I-14: GDPR Art.17 — Derecho al olvido. Borra permanentemente todos los datos del atleta.
    Requiere contraseña actual como confirmación.
    """
    from fastapi import Response
    from ..auth import verify_password, _extract_token, revoke_token
    from ..models import (WellnessLog, BloodLabExam, WorkoutLog, GarminActivity,
                          GarminTrainingLoad, GarminSyncStatus, PersonalRecord,
                          AssignedWorkout, AuditLog, Message)
    from ..audit import audit, Action, ip_from_request

    if not verify_password(body.get("password", ""), me.password_hash):
        raise HTTPException(400, "Contraseña incorrecta — confirma tu identidad para eliminar la cuenta")

    confirm = body.get("confirm_text", "")
    if confirm.strip().lower() != "eliminar mi cuenta":
        raise HTTPException(422, 'Escribe exactamente "eliminar mi cuenta" para confirmar')

    user_id = me.id
    ip      = ip_from_request(request)

    # Registrar en audit ANTES de borrar (último registro)
    audit(db, Action.ACCOUNT_DELETE if hasattr(Action, "ACCOUNT_DELETE") else "account.delete",
          user_id=user_id, ip=ip, success=True,
          detail={"reason": "user_requested_gdpr_deletion"})

    # Revocar token actual
    token = _extract_token(request)
    if token:
        revoke_token(token, db=db)

    # Borrado en cascada (todas las tablas relacionadas)
    for Model in [WellnessLog, BloodLabExam, WorkoutLog, GarminActivity,
                  GarminTrainingLoad, GarminSyncStatus, PersonalRecord, AssignedWorkout]:
        try:
            db.query(Model).filter(
                getattr(Model, "user_id", None) == user_id or
                getattr(Model, "athlete_id", None) == user_id
            ).delete(synchronize_session=False)
        except Exception:
            pass

    # Mensajes (from y to)
    db.query(Message).filter(
        (Message.from_user_id == user_id) | (Message.to_user_id == user_id)
    ).delete(synchronize_session=False)

    # Finalmente borrar el usuario
    db.delete(me)
    db.commit()

    response.delete_cookie("lx_access_token", path="/")
    logger.info("Cuenta eliminada permanentemente user_id=%s ip=%s (GDPR)", user_id, ip)
    return {"ok": True, "message": "Tu cuenta y todos tus datos han sido eliminados permanentemente."}


# ─────────────────────────────────────────────────────────────────────────────
# B-23: Activity Photo Upload / Retrieve
# ─────────────────────────────────────────────────────────────────────────────

_MAX_PHOTO_BYTES = 8 * 1024 * 1024   # 8 MB raw; PIL will compress to JPEG ≤300KB
_PHOTO_PREFIX    = "activity_photos"  # storage key prefix


@router.post("/activities/{activity_id}/photo")
async def upload_activity_photo(
    activity_id: str,
    file: UploadFile = File(...),
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """B-23: Subir foto post-actividad (JPEG/PNG, max 8 MB → guardada como JPEG 640px)."""
    import io
    from ..storage import storage
    act = db.query(GarminActivity).filter(
        GarminActivity.id == activity_id,
        GarminActivity.user_id == me.id,
    ).first()
    if not act:
        raise HTTPException(404, "Actividad no encontrada")

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(400, "Solo se aceptan imágenes (JPEG / PNG)")

    raw = await file.read()
    if len(raw) > _MAX_PHOTO_BYTES:
        raise HTTPException(400, "Imagen demasiado grande (máx 8 MB)")

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.thumbnail((640, 640), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75, optimize=True)
        compressed = buf.getvalue()
    except ImportError:
        compressed = raw  # Pillow no instalado: guardar tal cual

    key = f"{_PHOTO_PREFIX}/{activity_id}.jpg"
    storage.save(key, compressed)

    act.photo_path = key
    db.commit()

    return {"ok": True, "photo_url": f"/api/athlete/activities/{activity_id}/photo"}


@router.get("/activities/{activity_id}/photo")
def get_activity_photo(
    activity_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """B-23: Descargar foto post-actividad."""
    from ..storage import storage
    act = db.query(GarminActivity).filter(
        GarminActivity.id == activity_id,
        GarminActivity.user_id == me.id,
    ).first()
    if not act or not act.photo_path:
        raise HTTPException(404, "Sin foto para esta actividad")

    try:
        data = storage.load(act.photo_path)
    except FileNotFoundError:
        raise HTTPException(404, "Archivo no encontrado")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=86400"})


# ─────────────────────────────────────────────────────────────────────────────
# Galería de fotos adicionales por actividad — a diferencia del "photo_path"
# de arriba (una sola foto de portada, sin uso desde el frontend todavía),
# esto permite subir varias fotos por actividad (equipo, selfie, paisaje) y
# se muestran en el feed de Comunidad junto a las auto-importadas de Strava.
# ─────────────────────────────────────────────────────────────────────────────

_MAX_PHOTOS_PER_ACTIVITY = 8


def _compress_photo(raw: bytes) -> bytes:
    import io
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img.thumbnail((1080, 1080), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=78, optimize=True)
        return buf.getvalue()
    except ImportError:
        return raw  # Pillow no instalado: guardar tal cual


@router.post("/activities/{activity_id}/photos")
async def upload_activity_photos(
    activity_id: str,
    files: List[UploadFile] = File(...),
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Subir 1+ fotos adicionales para una actividad propia (equipo, selfie,
    paisaje, etc.). Máx 8 fotos por actividad en total."""
    from ..storage import storage

    act = db.query(GarminActivity).filter(
        GarminActivity.activity_id == activity_id,
        GarminActivity.user_id == me.id,
    ).first()
    if not act:
        raise HTTPException(404, "Actividad no encontrada")

    existing_count = db.query(ActivityPhoto).filter(ActivityPhoto.activity_id == act.id).count()
    if existing_count + len(files) > _MAX_PHOTOS_PER_ACTIVITY:
        raise HTTPException(400, f"Máx {_MAX_PHOTOS_PER_ACTIVITY} fotos por actividad")

    created = []
    for file in files:
        content_type = file.content_type or ""
        if not content_type.startswith("image/"):
            raise HTTPException(400, "Solo se aceptan imágenes (JPEG / PNG)")
        raw = await file.read()
        if len(raw) > _MAX_PHOTO_BYTES:
            raise HTTPException(400, "Imagen demasiado grande (máx 8 MB)")

        compressed = _compress_photo(raw)
        photo = ActivityPhoto(activity_id=act.id, user_id=me.id, storage_key="")
        db.add(photo)
        db.flush()  # obtener photo.id antes de guardar el archivo con ese key
        key = f"{_PHOTO_PREFIX}/{act.id}/{photo.id}.jpg"
        storage.save(key, compressed)
        photo.storage_key = key
        created.append(photo)

    db.commit()
    return {
        "ok": True,
        "photos": [
            {"id": p.id, "url": f"/api/athlete/activities/{activity_id}/photos/{p.id}"}
            for p in created
        ],
    }


@router.get("/activities/{activity_id}/photos")
def list_activity_photos(
    activity_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Lista las fotos adicionales de una actividad propia o de alguien
    que seguís (mismas reglas de visibilidad que /track)."""
    act = _find_viewable_activity(activity_id, me, db)
    if not act:
        raise HTTPException(404, "Actividad no encontrada")
    rows = db.query(ActivityPhoto).filter(ActivityPhoto.activity_id == act.id).order_by(ActivityPhoto.created_at).all()
    return {
        "photos": [
            {"id": p.id, "url": f"/api/athlete/activities/{activity_id}/photos/{p.id}", "is_mine": p.user_id == me.id}
            for p in rows
        ]
    }


@router.get("/activities/{activity_id}/photos/{photo_id}")
def get_activity_gallery_photo(
    activity_id: str,
    photo_id: str,
    db: Session = Depends(get_db),
):
    """
    Descargar una foto de la galería de una actividad. Sin auth a propósito
    — se referencia desde <img src="..."> en el feed de Comunidad, igual
    que el avatar y las fotos de Strava (no es dato sensible una vez que la
    actividad ya es visible en el feed).
    """
    from ..storage import storage
    photo = db.query(ActivityPhoto).filter(ActivityPhoto.id == photo_id).first()
    if not photo:
        raise HTTPException(404, "Foto no encontrada")
    try:
        data = storage.load(photo.storage_key)
    except FileNotFoundError:
        raise HTTPException(404, "Archivo no encontrado")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=86400"})


@router.delete("/activities/{activity_id}/photos/{photo_id}")
def delete_activity_gallery_photo(
    activity_id: str,
    photo_id: str,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    """Borrar una foto propia de la galería de una actividad."""
    from ..storage import storage
    photo = db.query(ActivityPhoto).filter(
        ActivityPhoto.id == photo_id,
        ActivityPhoto.user_id == me.id,
    ).first()
    if not photo:
        raise HTTPException(404, "Foto no encontrada")
    storage.delete(photo.storage_key)
    db.delete(photo)
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# Foto de perfil (avatar) — misma lógica de compresión que la foto de actividad,
# pero pública dentro de la app (cualquiera que vea tu perfil/feed de Comunidad
# debe poder cargarla, no solo vos).
# ─────────────────────────────────────────────────────────────────────────────

_AVATAR_PREFIX = "avatar_photos"


@router.post("/profile/avatar")
async def upload_avatar_photo(
    file: UploadFile = File(...),
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Subir foto de perfil (JPEG/PNG, max 8 MB → guardada como JPEG 200x200)."""
    import io
    from ..storage import storage

    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(400, "Solo se aceptan imágenes (JPEG / PNG)")

    raw = await file.read()
    if len(raw) > _MAX_PHOTO_BYTES:
        raise HTTPException(400, "Imagen demasiado grande (máx 8 MB)")

    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        # Recorte cuadrado centrado antes de reducir, para que la pelota de
        # avatar no salga deformada con fotos rectangulares.
        w, h = img.size
        side = min(w, h)
        img = img.crop(((w - side) // 2, (h - side) // 2, (w + side) // 2, (h + side) // 2))
        img.thumbnail((200, 200), Image.LANCZOS)
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=80, optimize=True)
        compressed = buf.getvalue()
    except ImportError:
        compressed = raw  # Pillow no instalado: guardar tal cual

    key = f"{_AVATAR_PREFIX}/{me.id}.jpg"
    storage.save(key, compressed)

    me.avatar_photo_path = key
    db.commit()

    return {"ok": True, "avatar_url": f"/api/athlete/profile/avatar/{me.id}"}


@router.delete("/profile/avatar")
def delete_avatar_photo(
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Quitar la foto de perfil — vuelve a mostrarse la pelota con iniciales."""
    from ..storage import storage
    if me.avatar_photo_path:
        try:
            storage.delete(me.avatar_photo_path)
        except Exception:
            pass
        me.avatar_photo_path = None
        db.commit()
    return {"ok": True}


@router.get("/profile/avatar/{user_id}")
def get_avatar_photo(
    user_id: str,
    db:  Session = Depends(get_db),
):
    """
    Descargar foto de perfil de cualquier usuario. Sin auth a propósito: se
    referencia desde <img src="..."> en Comunidad (feed/leaderboard/sugerencias
    de OTROS usuarios), y un <img> no puede mandar el Bearer token — igual
    que un avatar público de cualquier red social, no es dato sensible.
    """
    from ..storage import storage
    user = db.query(User).filter(User.id == user_id).first()
    if not user or not user.avatar_photo_path:
        raise HTTPException(404, "Sin foto de perfil")
    try:
        data = storage.load(user.avatar_photo_path)
    except FileNotFoundError:
        raise HTTPException(404, "Archivo no encontrado")
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "max-age=3600"})


_DEFAULT_SHARE_PREFS = {
    "share_details": True,   # maestro: seguidores pueden abrir el detalle
    "share_route":   True,   # mapa / recorrido GPS
    "share_hr":      True,   # frecuencia cardíaca
    "share_power":   True,   # potencia / cadencia
    "share_pace":    True,   # ritmo, velocidad y parciales
}


def _get_share_prefs(user: User) -> dict:
    """Preferencias de privacidad de Comunidad del usuario (qué comparte con
    sus seguidores). None guardado = todo compartido (default histórico)."""
    prefs = dict(_DEFAULT_SHARE_PREFS)
    if user.community_share_prefs:
        try:
            saved = json.loads(user.community_share_prefs)
            if isinstance(saved, dict):
                for k in _DEFAULT_SHARE_PREFS:
                    if k in saved:
                        prefs[k] = bool(saved[k])
        except Exception:
            pass
    return prefs


def _find_viewable_activity(activity_id: str, me: User, db: Session) -> GarminActivity | None:
    """Busca una actividad por su activity_id de Garmin, autorizando si:
    1. es propia,
    2. o de alguien que el usuario actual sigue Y que no desactivó el
       detalle compartido (share_details) en su configuración de privacidad,
    3. o — si `me` es coach/admin — de un atleta propio (CoachAthlete activo
       o miembro de un grupo suyo). El coach ve el detalle de sus atletas
       siempre, sin depender de share_details: esa preferencia gobierna qué
       ven los SEGUIDORES en Comunidad, no la relación de entrenamiento.

    Nota: activity_id puede repetirse entre cuentas demo/QA sembradas con el
    mismo dataset sintético — por eso se buscan TODOS los candidatos y se
    prioriza siempre la propia, para no devolver por error la fila de otro
    usuario cuando también existe la propia con el mismo id.
    """
    candidates = db.query(GarminActivity).filter(
        GarminActivity.activity_id == activity_id
    ).all()
    if not candidates:
        return None
    own = next((a for a in candidates if a.user_id == me.id), None)
    if own:
        return own

    if me.rol in ("coach", "admin"):
        from ..permissions import get_athletes_for_coach
        coached_ids = set(get_athletes_for_coach(me.id, db))
        for a in candidates:
            if a.user_id in coached_ids:
                return a

    followed_ids = {f.followed_id for f in db.query(Follow).filter_by(follower_id=me.id).all()}
    for a in candidates:
        if a.user_id in followed_ids:
            owner = db.query(User).filter(User.id == a.user_id).first()
            if owner and _get_share_prefs(owner)["share_details"]:
                return a
    return None


@router.get("/community-privacy")
def get_community_privacy(me: User = Depends(get_current_user)):
    """Preferencias de qué info del detalle de actividad ve tus seguidores."""
    return {"prefs": _get_share_prefs(me)}


class _SharePrefsIn(BaseModel):
    share_details: Optional[bool] = None
    share_route:   Optional[bool] = None
    share_hr:      Optional[bool] = None
    share_power:   Optional[bool] = None
    share_pace:    Optional[bool] = None


@router.put("/community-privacy")
def update_community_privacy(
    body: _SharePrefsIn,
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    prefs = _get_share_prefs(me)
    updates = body.model_dump(exclude_unset=True)
    prefs.update({k: bool(v) for k, v in updates.items() if k in prefs})
    me.community_share_prefs = json.dumps(prefs)
    db.commit()
    return {"ok": True, "prefs": prefs}


@router.get("/activities/{activity_id}/track")
def get_activity_track(
    activity_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    GPS track real (lat/lon/ele) de una actividad, si fue descargado
    (ver download_gps.py). No genera datos sintéticos: 404 si no existe.
    Visible si es propia o de alguien que seguís.
    """
    from pathlib import Path
    import json as _json

    act = _find_viewable_activity(activity_id, me, db)
    if not act:
        raise HTTPException(404, "Actividad no encontrada")
    if act.user_id != me.id:
        owner = db.query(User).filter(User.id == act.user_id).first()
        if not owner or not _get_share_prefs(owner)["share_route"]:
            raise HTTPException(404, "Actividad no encontrada")

    track_path = Path("data/tracks") / f"{activity_id}.json"
    if not track_path.exists():
        raise HTTPException(404, "Sin track GPS disponible para esta actividad")

    try:
        points = _json.loads(track_path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(500, "Error leyendo el track GPS")

    return {"activity_id": activity_id, "points": points}


def _bucket_time_in_zone(samples: list, field: str, zdef: dict) -> list:
    """Tiempo acumulado (seg) en cada zona, ponderado por el intervalo real
    entre muestras consecutivas (los samples de Garmin no son 1seg parejo)."""
    totals  = {k: 0.0 for k in zdef}
    prev_t  = None
    for s in samples:
        t = s.get("t")
        v = s.get(field)
        if prev_t is not None and t is not None and v is not None:
            dt = t - prev_t
            if dt > 0:
                for k, (lo, hi) in zdef.items():
                    if v >= lo and (v < hi or hi >= 9999):
                        totals[k] += dt
                        break
        if t is not None:
            prev_t = t
    total = sum(totals.values()) or 1.0
    out = []
    for k, (lo, hi) in zdef.items():
        secs = totals[k]
        out.append({
            "key": k, "min": lo, "max": (hi if hi < 9999 else None),
            "seconds": round(secs), "pct": round(secs/total*100, 1),
        })
    return out


def _compute_activity_splits(samples: list, sport: str) -> list:
    """Parciales por segmento de distancia (1km carrera, 5km ciclismo).
    Usa distancia y tiempo acumulados reales de Garmin — no estima nada."""
    seg_m = 1000 if sport == "run" else 5000 if sport == "bike" else None
    if not seg_m:
        return []
    valid = [s for s in samples if s.get("dist") is not None and s.get("t") is not None]
    if len(valid) < 2:
        return []

    splits = []
    idx = 1
    seg_t0, seg_d0 = valid[0]["t"], valid[0]["dist"]
    pw, hr = [], []

    def _flush(dist_m, dur_s):
        return {
            "idx": idx, "distance_m": round(dist_m), "duration_s": round(dur_s),
            "avg_power": round(sum(pw)/len(pw)) if pw else None,
            "avg_hr":    round(sum(hr)/len(hr))  if hr else None,
            "avg_pace_s_per_km": round(dur_s/(dist_m/1000)) if dist_m else None,
        }

    for s in valid:
        if s.get("power") is not None: pw.append(s["power"])
        if s.get("hr")    is not None: hr.append(s["hr"])
        if s["dist"] - seg_d0 >= seg_m:
            splits.append(_flush(seg_m, s["t"] - seg_t0))
            idx += 1
            seg_t0, seg_d0 = s["t"], s["dist"]
            pw, hr = [], []

    last_d = valid[-1]["dist"] - seg_d0
    if last_d > seg_m * 0.2:
        splits.append(_flush(last_d, valid[-1]["t"] - seg_t0))
    return splits


def _splits_from_garmin_laps(activity_id: str, sport: str) -> list:
    """Parciales reales por lap de Garmin (get_activity_splits) — necesarios
    para natación en piscina, donde la telemetría no trae distancia continua
    (los largos se cuentan aparte). Se usan como respaldo cuando el cálculo
    por distancia (_compute_activity_splits) no arroja nada."""
    from pathlib import Path
    import json as _json

    path = Path("data/splits") / f"{activity_id}.json"
    if not path.exists():
        return []
    try:
        laps = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    out = []
    idx = 0
    for lap in laps:
        dist = lap.get("distance") or 0
        if dist <= 0:
            # Lap de descanso (pausa entre series) — no es un parcial de nado/
            # carrera/ciclismo real, se omite para no ensuciar la tabla.
            continue
        idx += 1
        dur = lap.get("duration") or 0
        spd = lap.get("averageSpeed")
        row = {
            "idx":         idx,
            "distance_m":  round(dist),
            "duration_s":  round(dur),
            "avg_power":   None,
            "avg_hr":      round(lap["averageHR"]) if lap.get("averageHR") else None,
            "avg_pace_s_per_km": None,
        }
        if sport == "swim":
            row["avg_pace_s_per_100m"] = round(100 / spd) if spd else None
            row["lengths"] = lap.get("numberOfActiveLengths")
            row["avg_swolf"] = lap.get("averageSWOLF")
        elif spd:
            row["avg_pace_s_per_km"] = round(1000 / spd)
        out.append(row)
    return out


def _swim_lengths_real(activity_id: str) -> Optional[dict]:
    """
    Ritmo/brazadas/Swolf por cada largo individual de 25m — más granular
    que _splits_from_garmin_laps() (que trabaja a nivel de lap/serie, ej.
    100m). Los lengthDTOs ya vienen cacheados en data/splits/{id}.json
    (misma descarga que ya se usa para los Parciales), sin llamada nueva
    a la API. None si no hay splits cacheados para esta actividad.
    """
    from pathlib import Path
    import json as _json

    path = Path("data/splits") / f"{activity_id}.json"
    if not path.exists():
        return None
    try:
        laps = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

    pace, strokes, swolf = [], [], []
    for lap in laps:
        for length in (lap.get("lengthDTOs") or []):
            spd = length.get("averageSpeed")
            pace.append(round(100 / spd) if spd else None)
            strokes.append(length.get("totalNumberOfStrokes"))
            swolf.append(length.get("averageSWOLF"))
    if not any(v is not None for v in swolf):
        return None
    return {"pace_s_per_100m": pace, "strokes": strokes, "swolf": swolf}


def _dashboard_injury_risk(user_id: str, db: Session) -> Optional[dict]:
    """
    Injury Risk Score liviano para la card "¿Cómo va mi carga?" — mismo
    motor oficial ya consolidado (injury_risk_service.py, ver commit
    6acbe38). Cache-first (misma InjuryRiskSnapshot que usa /injury/risk/
    today) para no recalcular el score completo en cada carga del
    dashboard; solo si no hay snapshot de hoy se calcula en tiempo real.
    """
    from datetime import date as _d
    from ..models import InjuryRiskSnapshot
    from ..services.injury_risk_service import compute_injury_risk

    today = _d.today().isoformat()
    existing = (
        db.query(InjuryRiskSnapshot)
        .filter(InjuryRiskSnapshot.user_id == user_id, InjuryRiskSnapshot.date_iso == today)
        .first()
    )
    if existing and existing.risk_score is not None:
        return {"score": existing.risk_score, "level": existing.risk_level, "color": existing.risk_color}
    try:
        rpt = compute_injury_risk(user_id, db, today)
        return {"score": rpt["risk_score"], "level": rpt["risk_level"], "color": rpt["risk_color"]}
    except Exception:
        return None


def _current_streak_days(acts: list) -> int:
    """
    Días consecutivos con al menos una actividad real, terminando hoy o ayer
    (si hoy todavía no hay sync, no se corta la racha por eso). Se corta en
    el primer día real sin actividad. Basado 100% en date_iso reales de
    GarminActivity — sin aproximar ni rellenar huecos.
    """
    from datetime import timedelta as _timedelta
    dates = sorted({a.date_iso for a in acts}, reverse=True)
    if not dates:
        return 0
    today = _date.today()
    if dates[0] == today.isoformat():
        streak = 1
        cursor = today - _timedelta(days=1)
    elif dates[0] == (today - _timedelta(days=1)).isoformat():
        streak = 1
        cursor = today - _timedelta(days=2)
    else:
        return 0
    date_set = set(dates)
    while cursor.isoformat() in date_set:
        streak += 1
        cursor -= _timedelta(days=1)
    return streak


def _bike_target_power_series(owner: User, act: GarminActivity, t_arr: list, db: Session):
    """
    Serie de potencia objetivo (W) alineada a t_arr, construida SOLO si existe
    un AssignedWorkout real (individual o de grupo) para ese atleta+fecha+bici
    con blocks_json de Zwift (bloques definidos por duración en segundos —
    los únicos que se pueden alinear al eje de tiempo real sin aproximar
    nada). Si no hay workout asignado ese día, o no hay FTP configurado,
    retorna None — nunca se inventa un objetivo.
    """
    import json as _json

    if act.sport != "bike" or not owner.ftp:
        return None

    group_ids = [
        gid for (gid,) in db.query(GroupMember.group_id)
        .filter(GroupMember.athlete_id == owner.id).all()
    ]
    aw = (
        db.query(AssignedWorkout, WorkoutTemplate)
        .join(WorkoutTemplate, WorkoutTemplate.id == AssignedWorkout.template_id)
        .filter(
            AssignedWorkout.date_iso == act.date_iso,
            AssignedWorkout.deleted_at.is_(None),
            WorkoutTemplate.sport == "bike",
            WorkoutTemplate.blocks_json.isnot(None),
            (AssignedWorkout.athlete_id == owner.id)
            | (AssignedWorkout.group_id.in_(group_ids) if group_ids else False),
        )
        .first()
    )
    if not aw:
        return None
    _, template = aw
    try:
        blocks = _json.loads(template.blocks_json)
    except Exception:
        return None
    if not blocks:
        return None

    # Expandir bloques (duración en segundos, potencia como fracción de FTP) a
    # una serie por segundo de potencia objetivo en vatios.
    per_second: list = []
    for b in blocks:
        btype = b.get("type")
        if btype == "intervals":
            reps = int(b.get("repeat") or 0)
            on_d = int(b.get("on_duration") or 0)
            off_d = int(b.get("off_duration") or 0)
            on_p = b.get("on_power")
            off_p = b.get("off_power")
            for _ in range(reps):
                if on_d and on_p is not None:
                    per_second.extend([round(owner.ftp * on_p)] * on_d)
                if off_d and off_p is not None:
                    per_second.extend([round(owner.ftp * off_p)] * off_d)
        else:
            dur = int(b.get("duration") or 0)
            if not dur:
                continue
            if "power" in b and b.get("power") is not None:
                per_second.extend([round(owner.ftp * b["power"])] * dur)
            elif b.get("power_low") is not None and b.get("power_high") is not None:
                lo, hi = b["power_low"], b["power_high"]
                for i in range(dur):
                    frac = lo + (hi - lo) * (i / dur if dur else 0)
                    per_second.append(round(owner.ftp * frac))

    if not per_second:
        return None

    total = len(per_second)
    return [per_second[int(t)] if t is not None and 0 <= int(t) < total else None for t in t_arr]


@router.get("/activities/{activity_id}/telemetry")
def get_activity_telemetry(
    activity_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Telemetría segundo a segundo (potencia/FC/cadencia/velocidad/elevación)
    de una actividad, si fue descargada. Incluye series para gráfico
    (downsampled), distribución de zonas y parciales por distancia —
    todo calculado desde datos reales de Garmin, sin generar nada sintético.
    Visible si es propia o de alguien que seguís; las zonas siempre se
    calculan con el FTP/FC máx del DUEÑO de la actividad, no del que mira.
    """
    from pathlib import Path
    import json as _json
    from ..services.training_service import hr_zones, ftp_zones

    act = _find_viewable_activity(activity_id, me, db)
    if not act:
        raise HTTPException(404, "Actividad no encontrada")

    is_own = act.user_id == me.id
    owner  = me if is_own else (db.query(User).filter(User.id == act.user_id).first() or me)

    tel_path = Path("data/telemetry") / f"{activity_id}.json"
    if not tel_path.exists():
        raise HTTPException(404, "Sin telemetría sincronizada para esta actividad")

    try:
        samples = _json.loads(tel_path.read_text(encoding="utf-8"))
    except Exception:
        raise HTTPException(500, "Error leyendo telemetría")
    if not samples:
        raise HTTPException(404, "Telemetría vacía")

    max_pts = 200
    stride  = max(1, len(samples) // max_pts)
    ss      = samples[::stride]
    series  = {
        "t":         [s.get("t")     for s in ss],
        "power":     [s.get("power") for s in ss],
        "hr":        [s.get("hr")    for s in ss],
        "cadence":   [s.get("cad")   for s in ss],
        "speed":     [s.get("spd")   for s in ss],
        "elevation": [s.get("ele")   for s in ss],
    }
    # Dinámica de carrera / impacto / stamina — solo si esta actividad los
    # tiene cacheados (telemetría descargada después de 2026-07-31). Si
    # ninguna muestra tiene la clave, no se agrega la serie — nunca se
    # rellena con None disfrazado de "sin datos parcial".
    _rd_keys = {
        "stride": "stride_length", "gct": "ground_contact_time",
        "gct_bal": "ground_contact_balance", "vert_osc": "vertical_oscillation",
        "vert_ratio": "vertical_ratio", "impact_load": "impact_load",
        "resp_rate": "respiration_rate", "perf_cond": "performance_condition",
        "stamina": "stamina", "stamina_pot": "stamina_potential",
    }
    for raw_key, out_key in _rd_keys.items():
        if any(raw_key in s for s in ss):
            series[out_key] = [s.get(raw_key) for s in ss]

    zones = {}
    zone_bounds = {}
    if owner.fcmax:
        zones["hr"] = _bucket_time_in_zone(samples, "hr", hr_zones(owner.fcmax))
        zone_bounds["hr"] = hr_zones(owner.fcmax)
    if owner.ftp and act.sport == "bike":
        zones["power"] = _bucket_time_in_zone(samples, "power", ftp_zones(owner.ftp))
        zone_bounds["power"] = ftp_zones(owner.ftp)

    splits = _compute_activity_splits(samples, act.sport)
    if not splits:
        splits = _splits_from_garmin_laps(activity_id, act.sport)

    swim_lengths = _swim_lengths_real(activity_id) if act.sport == "swim" else None

    target_power = _bike_target_power_series(owner, act, series["t"], db) if is_own else None

    if not is_own:
        prefs = _get_share_prefs(owner)
        if not prefs["share_hr"]:
            series["hr"] = [None] * len(series["hr"])
            zones.pop("hr", None)
        if not prefs["share_power"]:
            series["power"]   = [None] * len(series["power"])
            series["cadence"] = [None] * len(series["cadence"])
            zones.pop("power", None)
            for k in ("impact_load", "stamina", "stamina_potential"):
                series.pop(k, None)
        if not prefs["share_pace"]:
            series["speed"] = [None] * len(series["speed"])
            splits = []
            swim_lengths = None
            for k in ("stride_length", "ground_contact_time", "ground_contact_balance",
                      "vertical_oscillation", "vertical_ratio", "performance_condition"):
                series.pop(k, None)
        if not prefs["share_route"]:
            series["elevation"] = [None] * len(series["elevation"])
        if not prefs["share_hr"]:
            series.pop("respiration_rate", None)

    return {
        "activity_id":  activity_id,
        "sport":        act.sport,
        "series":       series,
        "zones":        zones,
        "zone_bounds":  zone_bounds,
        "splits":       splits,
        "swim_lengths": swim_lengths,
        "target_power": target_power,
        "is_own":       is_own,
        "owner_name":   None if is_own else (owner.nombre or owner.email.split("@")[0]),
    }


@router.get("/year-in-review")
def year_in_review(
    year: int       = Query(None),
    db:   Session   = Depends(get_db),
    me:   User      = Depends(get_current_user),
):
    """B-27: Year in Review — estadísticas anuales del atleta para tarjeta viral."""
    from ..models import GarminTrainingLoad
    from collections import defaultdict
    import calendar as _cal

    yr = year or datetime.now(timezone.utc).replace(tzinfo=None).year
    iso_start = f"{yr}-01-01"
    iso_end   = f"{yr}-12-31"

    acts = db.query(GarminActivity).filter(
        GarminActivity.user_id == me.id,
        GarminActivity.date_iso >= iso_start,
        GarminActivity.date_iso <= iso_end,
    ).all()

    # Aggregates
    totals:  dict[str, float] = defaultdict(float)   # sport → km
    tss_by_sport: dict[str, float] = defaultdict(float)
    by_month: dict[int, float]     = defaultdict(float)  # month → tss
    by_weekday: dict[int, int]     = defaultdict(int)    # 0=Mon tally
    longest:  dict[str, dict]      = {}                  # sport → best activity
    total_activities = 0
    total_tss   = 0.0
    total_hours = 0.0
    total_km    = 0.0

    DAYS = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]
    MONTHS_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

    for a in acts:
        sport = a.sport or "other"
        totals[sport]       += a.dist_km or 0
        tss_by_sport[sport] += a.tss     or 0
        total_tss            += a.tss    or 0
        total_hours          += (a.dur_min or 0) / 60.0
        total_km             += a.dist_km or 0
        total_activities     += 1

        try:
            d  = _date.fromisoformat(a.date_iso)
            by_month[d.month]     += a.tss or 0
            by_weekday[d.weekday()] += 1
        except ValueError:
            pass

        if a.dist_km and a.dist_km > (longest.get(sport,{}).get("dist_km",0)):
            longest[sport] = {
                "dist_km":  a.dist_km,
                "dur_min":  a.dur_min,
                "date_iso": a.date_iso,
                "name":     a.name,
            }

    # Peak week TSS
    by_week: dict[str, float] = defaultdict(float)
    for a in acts:
        try:
            d = _date.fromisoformat(a.date_iso)
            iso_week = d.strftime("%G-W%V")
            by_week[iso_week] += a.tss or 0
        except ValueError:
            pass

    peak_week = max(by_week.items(), key=lambda x: x[1], default=(None, 0))

    # CTL start vs end of year
    ctl_data = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso >= iso_start,
        GarminTrainingLoad.date_iso <= iso_end,
    ).order_by(GarminTrainingLoad.date_iso).all()

    ctl_start = round(ctl_data[0].ctl,  1) if ctl_data and ctl_data[0].ctl  else None
    ctl_end   = round(ctl_data[-1].ctl, 1) if ctl_data and ctl_data[-1].ctl else None
    ctl_peak  = None
    if ctl_data:
        best = max(ctl_data, key=lambda x: x.ctl or 0)
        ctl_peak = {"value": round(best.ctl, 1), "date_iso": best.date_iso} if best.ctl else None

    # Favourite weekday
    fav_weekday_idx = max(by_weekday.items(), key=lambda x: x[1], default=(None, 0))[0]
    fav_weekday     = DAYS[fav_weekday_idx] if fav_weekday_idx is not None else None

    # Month series
    month_series = [
        {"month": m, "label": MONTHS_ES[m-1], "tss": round(by_month[m], 1)}
        for m in range(1, 13)
    ]

    return {
        "year":              yr,
        "athlete_name":      me.nombre or me.email,
        "total_activities":  total_activities,
        "total_hours":       round(total_hours, 1),
        "total_km":          round(total_km, 1),
        "total_tss":         round(total_tss, 1),
        "by_sport":          {s: {"km": round(totals[s],1), "tss": round(tss_by_sport[s],1)} for s in totals},
        "longest_by_sport":  longest,
        "peak_week_iso":     peak_week[0],
        "peak_week_tss":     round(peak_week[1], 1),
        "fav_weekday":       fav_weekday,
        "ctl_start":         ctl_start,
        "ctl_end":           ctl_end,
        "ctl_peak":          ctl_peak,
        "month_series":      month_series,
        "ctl_improvement":   round(ctl_end - ctl_start, 1) if ctl_start and ctl_end else None,
    }


@router.delete("/activities/{activity_id}/photo")
def delete_activity_photo(
    activity_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """B-23: Eliminar foto de actividad."""
    from ..storage import storage
    act = db.query(GarminActivity).filter(
        GarminActivity.id == activity_id,
        GarminActivity.user_id == me.id,
    ).first()
    if not act or not act.photo_path:
        raise HTTPException(404, "Sin foto para esta actividad")

    storage.delete(act.photo_path)
    act.photo_path = None
    db.commit()
    return {"ok": True}


# ─────────────────────────────────────────────────────────────────────────────
# GDPR: Data Export & Account Deletion  (S37)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/me/export")
def gdpr_export_my_data(
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """GDPR Art. 20 — portable export of all athlete personal data."""
    activities = db.query(GarminActivity).filter(GarminActivity.user_id == me.id).all()
    wellness   = db.query(WellnessLog).filter(WellnessLog.user_id == me.id).all()
    labs       = db.query(BloodLabExam).filter(BloodLabExam.user_id == me.id).all()
    food       = db.query(FoodDiaryEntry).filter(FoodDiaryEntry.user_id == me.id).all()
    workouts   = db.query(WorkoutLog).filter(WorkoutLog.user_id == me.id).all()
    assigned   = db.query(AssignedWorkout).filter(AssignedWorkout.athlete_id == me.id).all()
    notes      = db.query(AthleteNote).filter(AthleteNote.athlete_id == me.id).all()
    messages   = db.query(Message).filter(
        (Message.from_user_id == me.id) | (Message.to_user_id == me.id)
    ).all()

    def _row(obj, exclude=()):
        return {
            c.name: getattr(obj, c.name)
            for c in obj.__table__.columns
            if c.name not in exclude
        }

    return {
        "export_date": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        "profile": _row(me, exclude=("password_hash", "totp_secret", "totp_backup_hash",
                                     "garmin_password", "strava_access_token",
                                     "strava_refresh_token", "last_device_hash")),
        "activities":       [_row(a) for a in activities],
        "wellness_logs":    [_row(w) for w in wellness],
        "blood_lab_exams":  [_row(l) for l in labs],
        "food_diary":       [_row(f) for f in food],
        "workout_logs":     [_row(w) for w in workouts],
        "assigned_workouts":[_row(a) for a in assigned],
        "notes_from_coach": [_row(n) for n in notes],
        "messages":         [_row(m) for m in messages],
    }


@router.delete("/me", status_code=200)
def gdpr_delete_my_account(
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """GDPR Art. 17 — right to erasure. Anonymizes PII and deactivates the account."""
    anon_id = f"deleted_{me.id[:8]}"

    me.email          = f"{anon_id}@deleted.invalid"
    me.nombre         = "Deleted User"
    me.password_hash  = ""
    me.garmin_email   = None
    me.garmin_password = None
    me.strava_access_token  = None
    me.strava_refresh_token = None
    me.strava_athlete_id    = None
    me.totp_secret          = None
    me.totp_backup_hash     = None
    me.last_device_hash     = None
    me.gdpr_consent_ip      = None
    me.activo = False

    db.commit()
    return {"ok": True, "message": "Account anonymized and deactivated per GDPR Art. 17"}
