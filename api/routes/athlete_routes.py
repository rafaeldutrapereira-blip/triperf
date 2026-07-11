from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    User, AssignedWorkout, WorkoutLog, WellnessLog, BloodLabExam, NutritionPlan,
    GarminActivity, GarminTrainingLoad, GarminSyncStatus, Message, AthleteNote,
    FoodDiaryEntry, GarminPlannedWorkout,
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
from ..models import Group, GroupMember
from ..services.training_service import compute_acwr, build_training_alerts as _svc_alerts
from ..garmin_pull_service import _CTL_DECAY, _ATL_DECAY

logger = logging.getLogger("labx.athlete")
router = APIRouter(prefix="/athlete", tags=["athlete"])


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
    q = db.query(AssignedWorkout).filter(AssignedWorkout.athlete_id == me.id)
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

    # ── PMC (últimas 52 semanas) + ACWR history ──────────────────────────────
    pmc = []
    acwr_history = []
    mo  = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
    cutoff_pmc = (_date_.today() - _td(weeks=52)).isoformat()
    load_list = list(load_rows)  # already ordered by date_iso asc
    for idx, r in enumerate(load_list):
        try:
            dt = _date_.fromisoformat(r.date_iso)
        except ValueError:
            continue
        if r.date_iso >= cutoff_pmc and dt.weekday() == 6:  # domingos
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

    # ── Activities (últimas 100, ordenadas desc) ──────────────────────────────
    acts_orm = (
        db.query(GarminActivity)
          .filter(GarminActivity.user_id == me.id)
          .order_by(GarminActivity.date_iso.desc())
          .limit(100)
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
        })

    # ── Disciplinas esta semana ───────────────────────────────────────────────
    week_start = (_date_.today() - _td(days=_date_.today().weekday())).isoformat()
    week_acts  = [a for a in activities if a["date_iso"] >= week_start]

    swim_km = round(sum(a["dist_km"] or 0 for a in week_acts if a["sport"] == "swim"), 2)
    bike_km = round(sum(a["dist_km"] or 0 for a in week_acts if a["sport"] == "bike"), 2)
    run_km  = round(sum(a["dist_km"] or 0 for a in week_acts if a["sport"] == "run"),  2)
    gym_n   = sum(1 for a in week_acts if a["sport"] == "gym")

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

    # ── Históricos para wellbeing charts (90 días) ───────────────────────────
    _ninety_ago = (_date_.today() - _td(days=90)).isoformat()
    _health_90 = (
        db.query(GarminHealthDaily)
        .filter(GarminHealthDaily.user_id == me.id,
                GarminHealthDaily.date_iso >= _ninety_ago)
        .order_by(GarminHealthDaily.date_iso.asc())
        .all()
    )
    _sleep_90 = (
        db.query(GarminSleepSession)
        .filter(GarminSleepSession.user_id == me.id,
                GarminSleepSession.date_iso >= _ninety_ago)
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
    _vo2_rows = [r for r in reversed(_health_90) if r.vo2max_running or r.vo2max_cycling]
    vo2max_garmin = (_vo2_rows[0].vo2max_running or _vo2_rows[0].vo2max_cycling) if _vo2_rows else None
    vo2_history = [
        {"dt": r.date_iso, "vo2": r.vo2max_running or r.vo2max_cycling}
        for r in _health_90 if r.vo2max_running is not None or r.vo2max_cycling is not None
    ]

    hrv_last_night   = health_today.hrv_last_night    if health_today else None
    hrv_7d_avg       = health_today.hrv_weekly_avg     if health_today else None
    body_battery_end = health_today.body_battery_end   if health_today else None
    stress_avg       = health_today.avg_stress         if health_today else None
    resting_hr       = health_today.resting_hr         if health_today else None

    sleep_score      = sleep_today.sleep_score  if sleep_today else None
    sleep_total_h    = round(sleep_today.total_min / 60, 1) if (sleep_today and sleep_today.total_min) else None
    sleep_deep_h     = round(sleep_today.deep_min  / 60, 1) if (sleep_today and sleep_today.deep_min)  else None

    # Readiness: usa LabX Readiness Score cuando está disponible, sino fallback TSB
    labx_readiness = health_today.labx_readiness_score if health_today else None
    readiness_score = labx_readiness if labx_readiness is not None else max(0, min(100, round(50 + tsb)))

    # Tendencias HRV (7 días)
    # HRV trend: hoy vs hace 7 días
    hrv_trend = None
    if health_today and health_7d_ago:
        h_new = health_today.hrv_last_night
        h_old = health_7d_ago.hrv_last_night
        if h_new and h_old:
            hrv_trend = round(h_new - h_old, 1)

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
        "readiness_source": "labx" if labx_readiness is not None else "tsb",
        # Training Readiness desglosado (B-05)
        "training_readiness":       tr_score,
        "training_readiness_label": tr_label,
        "training_readiness_color": tr_color,
        # Trends semana anterior (B-06)
        "trends": {
            "ctl":        ctl_change,
            "tss_week":   tss_wk_trend,
            "hrv":        hrv_trend,
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
        # Históricos wellbeing (90 días) para detalle.html?metric=wellbeing
        "sleep_history": sleep_history,
        "hrv_history":   hrv_history,
        "rhr_history":   rhr_history,
        "bb_history":    bb_history,
        "vo2max_garmin": vo2max_garmin,
        "vo2_history":   vo2_history,
        # Actividades
        "activities": activities,
        # Resumen semanal por disciplina
        "weekly_disc": {
            "swim_km":    swim_km,
            "bike_km":    bike_km,
            "run_km":     run_km,
            "strength_n": gym_n,
        },
        # Carrera objetivo
        "race_goal_name": me.race_goal_name,
        "race_goal_date": me.race_goal_date,
        # Alertas de sobreentrenamiento
        "alerts": _svc_alerts(tsb=tsb, acwr=acwr, acwr_zone=acwr_zone, ctl=ctl),
        # Entrenamientos planificados (Training Peaks → Garmin → LabX)
        "planned_workouts": _get_planned_week(db, me.id),
    }
    cache_set(cache_key, result, ttl_seconds=300)
    return result


def _get_planned_week(db: Session, user_id: str) -> list:
    """Devuelve los workouts planificados de la semana actual (lun→dom)."""
    from datetime import date, timedelta
    today    = date.today()
    mon      = today - timedelta(days=today.weekday())
    sun      = mon + timedelta(days=6)
    rows = (
        db.query(GarminPlannedWorkout)
          .filter(
              GarminPlannedWorkout.user_id  == user_id,
              GarminPlannedWorkout.date_iso >= mon.isoformat(),
              GarminPlannedWorkout.date_iso <= sun.isoformat(),
          )
          .order_by(GarminPlannedWorkout.date_iso)
          .all()
    )
    return [
        {
            "date_iso": r.date_iso,
            "title":    r.title,
            "sport":    r.sport,
            "dur_min":  r.dur_min,
            "dist_km":  r.dist_km,
            "tss":      r.tss_planned,
            "source":   r.source,
        }
        for r in rows
    ]


# ─────────────────────────────────────────────
# PERSONAL RECORDS
# ─────────────────────────────────────────────

class _PRIn(BaseModel):
    event:      str
    value_sec:  float
    value_disp: str | None = None
    achieved_at: str | None = None
    source:     str = "manual"
    notes:      str | None = None


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
    if body.value_sec <= 0:
        raise HTTPException(400, "El tiempo debe ser mayor a 0 segundos")

    existing = (
        db.query(PersonalRecord)
        .filter(PersonalRecord.user_id == me.id, PersonalRecord.event == body.event)
        .order_by(PersonalRecord.value_sec)
        .first()
    )

    if existing and body.value_sec >= existing.value_sec:
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
        value_sec=body.value_sec,
        value_disp=body.value_disp,
        achieved_at=body.achieved_at,
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
    row = db.query(GarminSyncStatus).filter(GarminSyncStatus.user_id == me.id).first()
    if not row:
        return {"status": "never", "last_sync": None, "activities_total": 0}
    return {
        "status":           row.status,
        "last_sync":        str(row.last_sync_at)[:16] if row.last_sync_at else None,
        "activities_total": row.activities_total,
        "error":            row.error,
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
