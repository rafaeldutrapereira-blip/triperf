"""
Pydantic v2 schemas — request / response bodies
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, field_validator


# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
class LoginRequest(BaseModel):
    email:    EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    rol:          str
    nombre:       str
    user_id:      str
    plan_nivel:   str = "basico"


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────
class UserCreate(BaseModel):
    email:      EmailStr
    nombre:     str
    password:   str
    rol:        str = "atleta"
    plan_nivel: str = "basico"

class UserOut(BaseModel):
    id:             str
    email:          str
    nombre:         str
    rol:            str
    plan_nivel:     str
    activo:         bool
    created_at:     datetime
    garmin_email:    Optional[str] = None
    has_garmin:      bool          = False
    race_goal_name:  Optional[str] = None
    race_goal_date:  Optional[str] = None
    ftp:             Optional[int]   = None
    weight_kg:       Optional[float] = None
    height_cm:       Optional[int]   = None
    vo2max:          Optional[float] = None
    fcmax:           Optional[int]   = None
    css:             Optional[str]   = None
    run_pace:        Optional[str]   = None

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_user(cls, u):
        d = cls.model_validate(u)
        d.has_garmin = bool(u.garmin_email and u.garmin_password)
        return d

class UserUpdate(BaseModel):
    nombre:     Optional[str]    = None
    email:      Optional[str]    = None
    rol:        Optional[str]    = None
    plan_nivel: Optional[str]    = None
    activo:     Optional[bool]   = None
    password:   Optional[str]    = None

class GarminCredentials(BaseModel):
    garmin_email:    str
    garmin_password: str

class GarminSyncResult(BaseModel):
    ok:         bool
    workout_id: Optional[str] = None
    date:       Optional[str] = None
    error:      Optional[str] = None


# ─────────────────────────────────────────────
# GROUPS
# ─────────────────────────────────────────────
class GroupCreate(BaseModel):
    nombre:      str
    competencia: Optional[str] = None

class GroupOut(BaseModel):
    id:          str
    nombre:      str
    competencia: Optional[str]
    coach_id:    str
    created_at:  datetime
    member_count: Optional[int] = 0

    model_config = {"from_attributes": True}

class AddMemberRequest(BaseModel):
    user_id: str


# ─────────────────────────────────────────────
# WORKOUT TEMPLATES
# ─────────────────────────────────────────────
class WorkoutTemplateCreate(BaseModel):
    sport:       str                   # swim | bike | run | str
    tipo:        Optional[str]   = None  # endurance | tempo | umbral | vo2max | race | recuperacion
    nombre:      str
    dur_min:     Optional[int]   = None
    dist_km:     Optional[float] = None
    tss:         Optional[int]   = None
    notas:       Optional[str]   = None
    blocks_json: Optional[str]   = None  # JSON bloques estructurados (bike=Zwift, run=intervalos, swim=series)

class WorkoutTemplateUpdate(BaseModel):
    sport:       Optional[str]   = None
    tipo:        Optional[str]   = None
    nombre:      Optional[str]   = None
    dur_min:     Optional[int]   = None
    dist_km:     Optional[float] = None
    tss:         Optional[int]   = None
    notas:       Optional[str]   = None
    blocks_json: Optional[str]   = None

class WorkoutTemplateOut(BaseModel):
    id:          str
    coach_id:    str
    sport:       str
    tipo:        Optional[str]   = None
    nombre:      str
    dur_min:     Optional[int]
    dist_km:     Optional[float]
    tss:         Optional[int]
    notas:       Optional[str]
    blocks_json: Optional[str]   = None
    created_at:  datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# ASSIGNED WORKOUTS
# ─────────────────────────────────────────────
class AssignRequest(BaseModel):
    template_id: str
    date_iso:    str            # "YYYY-MM-DD"
    athlete_id:  Optional[str] = None
    group_id:    Optional[str] = None
    notas:       Optional[str] = None

    @field_validator("date_iso")
    @classmethod
    def validate_date(cls, v: str) -> str:
        from datetime import date
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("date_iso debe ser YYYY-MM-DD")
        return v

class AssignedWorkoutOut(BaseModel):
    id:             str
    date_iso:       str
    notas:          Optional[str]
    coach_comment:  Optional[str] = None
    athlete_id:     Optional[str]
    group_id:       Optional[str]
    template:       WorkoutTemplateOut
    logs:           List["WorkoutLogOut"] = []
    created_at:     datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# WORKOUT LOG
# ─────────────────────────────────────────────
class WorkoutLogCreate(BaseModel):
    assignment_id: str
    tss_real:      Optional[int]   = None
    dist_real:     Optional[float] = None
    dur_real:      Optional[int]   = None
    rpe:           Optional[int]   = None  # 1-10
    completado:    bool            = True
    notas:         Optional[str]   = None

class WorkoutLogOut(BaseModel):
    id:            str
    user_id:       str
    assignment_id: str
    tss_real:      Optional[int]
    dist_real:     Optional[float]
    dur_real:      Optional[int]
    rpe:           Optional[int]
    completado:    bool
    notas:         Optional[str]
    logged_at:     datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────
# ADHERENCE (cumplimiento)
# ─────────────────────────────────────────────
class AthleteAdherence(BaseModel):
    user_id:    str
    nombre:     str
    email:      str
    total:      int
    completado: int
    pct:        float              # 0–100
    by_sport:   dict               # {"swim": {"total":2,"done":2,"pct":100}, ...}


# ─────────────────────────────────────────────
# ATHLETE PROFILE UPDATE
# ─────────────────────────────────────────────
class AthleteProfileUpdate(BaseModel):
    password:       Optional[str]   = None
    race_goal_name: Optional[str]   = None
    race_goal_date: Optional[str]   = None
    ftp:            Optional[int]   = None
    weight_kg:      Optional[float] = None
    height_cm:      Optional[int]   = None
    vo2max:         Optional[float] = None
    fcmax:          Optional[int]   = None
    css:            Optional[str]   = None
    run_pace:       Optional[str]   = None


# ─────────────────────────────────────────────
# PLAN VS ACTUAL (Fase 4)
# ─────────────────────────────────────────────
class PlanVsActualItem(BaseModel):
    assignment_id:    str
    date_iso:         str
    sport:            str
    template_nombre:  str
    planned_dist_km:  Optional[float] = None
    planned_dur_min:  Optional[int]   = None
    planned_tss:      Optional[int]   = None
    coach_notas:      Optional[str]   = None
    # Log manual del atleta
    log_completado:   bool            = False
    log_dist_real:    Optional[float] = None
    log_dur_real:     Optional[int]   = None
    log_tss_real:     Optional[int]   = None
    log_rpe:          Optional[int]   = None
    # Actividad matcheada en Garmin
    garmin_matched:      bool            = False
    garmin_activity_id:  Optional[int]   = None
    garmin_name:         Optional[str]   = None
    garmin_dist_km:      Optional[float] = None
    garmin_dur_secs:     Optional[float] = None
    garmin_avg_hr:       Optional[float] = None
    garmin_tss:          Optional[float] = None
    # Estado resumen: pending | done_manual | done_garmin | done_both | missed
    status:           str = "pending"


# ─────────────────────────────────────────────
# GARMIN ACTIVITY (historial del atleta)
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# REPORTE SEMANAL (Fase 5)
# ─────────────────────────────────────────────
class ReportSportRow(BaseModel):
    sport:              str
    sessions_planned:   int   = 0
    sessions_done:      int   = 0
    dist_planned_km:    float = 0.0
    dist_actual_km:     float = 0.0
    dur_planned_min:    int   = 0
    dur_actual_min:     int   = 0
    tss_planned:        int   = 0
    tss_actual:         int   = 0

class ReportWeek(BaseModel):
    week_start:         str
    sessions_planned:   int   = 0
    sessions_done:      int   = 0
    tss_planned:        int   = 0
    tss_actual:         int   = 0
    dist_actual_km:     float = 0.0

class AthleteReport(BaseModel):
    athlete_id:         str
    athlete_nombre:     str
    period_start:       str
    period_end:         str
    sessions_total:     int   = 0
    sessions_done:      int   = 0
    compliance_pct:     float = 0.0
    tss_planned:        int   = 0
    tss_actual:         int   = 0
    dist_total_km:      float = 0.0
    dur_total_min:      int   = 0
    by_sport:           List[ReportSportRow] = []
    weeks:              List[ReportWeek]     = []
    ctl:                Optional[float]      = None
    atl:                Optional[float]      = None
    tsb:                Optional[float]      = None
    has_garmin:         bool                 = False
    pmc_history:        List[dict]           = []
    acwr:               Optional[float]      = None
    race_goal_name:     Optional[str]        = None
    race_goal_date:     Optional[str]        = None


class GarminActivityOut(BaseModel):
    activity_id:   Optional[int]   = None
    name:          Optional[str]   = None
    sport:         Optional[str]   = None
    start_time:    Optional[str]   = None
    duration_secs: Optional[float] = None
    distance_km:   Optional[float] = None
    average_hr:    Optional[float] = None
    max_hr:        Optional[float] = None
    calories:      Optional[int]   = None
    tss:           Optional[float] = None


# ─────────────────────────────────────────────
# WEEK TEMPLATES (Semanas Tipo)
# ─────────────────────────────────────────────
class WeekTemplateDayCreate(BaseModel):
    day_of_week:         int             # 0=Lun … 6=Dom
    workout_template_id: str
    notas:               Optional[str] = None

class WeekTemplateDayOut(BaseModel):
    id:                  str
    day_of_week:         int
    workout_template_id: str
    workout_nombre:      str
    workout_sport:       str
    workout_dur_min:     Optional[int]   = None
    workout_dist_km:     Optional[float] = None
    workout_tss:         Optional[int]   = None
    notas:               Optional[str]   = None

class WeekTemplateCreate(BaseModel):
    nombre:      str
    descripcion: Optional[str] = None

class WeekTemplateOut(BaseModel):
    id:          str
    nombre:      str
    descripcion: Optional[str] = None
    days:        List[WeekTemplateDayOut] = []

class ApplyWeekTemplateRequest(BaseModel):
    start_date:   str             # lunes de la semana destino YYYY-MM-DD
    athlete_id:   Optional[str] = None
    group_id:     Optional[str] = None
    sync_garmin:  bool = False

# ─────────────────────────────────────────────
# CALENDAR
# ─────────────────────────────────────────────
class CalendarAthleteDay(BaseModel):
    athlete_id:     str
    athlete_nombre: str
    assignments:    List[AssignedWorkoutOut] = []

class CalendarDay(BaseModel):
    date_iso:  str
    athletes:  List[CalendarAthleteDay] = []


# ─────────────────────────────────────────────
# ATHLETE NOTES
# ─────────────────────────────────────────────
class AthleteNoteCreate(BaseModel):
    tipo:  str = "observacion"   # observacion | lesion | meta | carrera
    texto: str
    fecha: str                   # YYYY-MM-DD

class AthleteNoteOut(BaseModel):
    id:         str
    tipo:       str
    texto:      str
    fecha:      str
    created_at: Optional[str] = None


# ─────────────────────────────────────────────
# MACROCYCLES
# ─────────────────────────────────────────────
class MacrocycleWeekCreate(BaseModel):
    week_template_id: str
    notas:            Optional[str] = None

class MacrocycleWeekOut(BaseModel):
    id:               str
    position:         int
    week_template_id: str
    week_nombre:      str
    notas:            Optional[str] = None

class MacrocycleCreate(BaseModel):
    nombre:      str
    descripcion: Optional[str] = None

class MacrocycleOut(BaseModel):
    id:          str
    nombre:      str
    descripcion: Optional[str] = None
    weeks:       List[MacrocycleWeekOut] = []

class ApplyMacrocycleRequest(BaseModel):
    start_date:  str              # lunes de inicio YYYY-MM-DD
    athlete_id:  Optional[str] = None
    group_id:    Optional[str] = None
    sync_garmin: bool = False


# ─────────────────────────────────────────────
# SOCIAL — Comunidad
# ─────────────────────────────────────────────
class CommentCreate(BaseModel):
    body: str

class AuthorMini(BaseModel):
    id:     str
    nombre: str
    model_config = {"from_attributes": True}

class CommentOut(BaseModel):
    id:         str
    body:       str
    created_at: datetime
    author:     AuthorMini
    is_mine:    bool = False
    model_config = {"from_attributes": True}

class FeedItemOut(BaseModel):
    log_id:        str
    logged_at:     datetime
    sport:         str
    sport_label:   str
    sport_color:   str
    activity_name: str
    dist_real:     Optional[float] = None
    dur_real:      Optional[int]   = None
    tss_real:      Optional[int]   = None
    rpe:           Optional[int]   = None
    notas:         Optional[str]   = None
    author:        AuthorMini
    kudos_count:   int = 0
    my_kudo:       bool = False
    comments_count: int = 0

class FeedPage(BaseModel):
    data:        List[FeedItemOut]
    next_cursor: Optional[str] = None
    has_more:    bool = False

class KudoToggleOut(BaseModel):
    action:      str   # "added" | "removed"
    kudos_count: int

class SocialStatsOut(BaseModel):
    following:  int
    followers:  int
    total_logs: int
