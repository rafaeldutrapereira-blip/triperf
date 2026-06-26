"""
ORM Models — LabX Coach Platform
"""
from __future__ import annotations

import uuid
from datetime import datetime, date

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float,
    ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
)
from sqlalchemy.orm import relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, default=_uuid)
    email         = Column(String, unique=True, nullable=False, index=True)
    nombre        = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    rol           = Column(String, nullable=False, default="athlete")  # admin | coach | athlete
    plan_nivel    = Column(String, default="basico")                   # basico | pro | elite
    activo        = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=datetime.utcnow)
    # Credenciales Garmin del atleta (para sync directo a su cuenta)
    garmin_email    = Column(String, nullable=True)
    garmin_password = Column(String, nullable=True)
    # Carrera objetivo
    race_goal_name = Column(String, nullable=True)
    race_goal_date = Column(String, nullable=True)
    # Métricas de rendimiento (perfil atleta)
    ftp            = Column(Integer, nullable=True)   # Functional Threshold Power (W)
    weight_kg      = Column(Float,   nullable=True)
    height_cm      = Column(Integer, nullable=True)
    vo2max         = Column(Float,   nullable=True)
    fcmax          = Column(Integer, nullable=True)   # FC máxima (bpm)
    css            = Column(String,  nullable=True)   # Critical Swim Speed "1:48"
    run_pace       = Column(String,  nullable=True)   # Ritmo umbral carrera "4:52"

    # relations
    groups_coached = relationship("Group",       back_populates="coach",   foreign_keys="Group.coach_id")
    memberships    = relationship("GroupMember", back_populates="user", foreign_keys="GroupMember.athlete_id")
    workout_logs   = relationship("WorkoutLog",  back_populates="user")
    assigned_workouts = relationship("AssignedWorkout", back_populates="athlete",
                                    foreign_keys="AssignedWorkout.athlete_id")


# ─────────────────────────────────────────────
# GROUPS
# ─────────────────────────────────────────────
class Group(Base):
    __tablename__ = "groups"

    id          = Column(String, primary_key=True, default=_uuid)
    nombre      = Column(String, nullable=False)
    competencia = Column(String)                          # ej: "70.3 Concón Ago 2026"
    coach_id    = Column(String, ForeignKey("users.id"), nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow)

    coach   = relationship("User",        back_populates="groups_coached", foreign_keys=[coach_id])
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    assigned_workouts = relationship("AssignedWorkout", back_populates="group",
                                     foreign_keys="AssignedWorkout.group_id")


class GroupMember(Base):
    __tablename__ = "group_members"

    id         = Column(String, primary_key=True, default=_uuid)
    group_id   = Column(String, ForeignKey("groups.id"),  nullable=False, index=True)
    athlete_id = Column(String, ForeignKey("users.id"),   nullable=False, index=True)
    added_at   = Column(DateTime, default=datetime.utcnow)

    group = relationship("Group", back_populates="members")
    user  = relationship("User",  back_populates="memberships", foreign_keys=[athlete_id])


# ─────────────────────────────────────────────
# WORKOUT TEMPLATES
# ─────────────────────────────────────────────
class WorkoutTemplate(Base):
    __tablename__ = "workout_templates"

    id         = Column(String, primary_key=True, default=_uuid)
    coach_id   = Column(String, ForeignKey("users.id"), nullable=False)
    sport      = Column(String, nullable=False)           # swim | bike | run | str
    tipo       = Column(String, nullable=True)            # endurance | tempo | umbral | vo2max | race | recuperacion
    nombre     = Column(String, nullable=False)
    dur_min    = Column(Integer)
    dist_km    = Column(Float)
    tss        = Column(Integer)
    notas      = Column(Text)
    blocks_json = Column(Text, nullable=True)             # JSON: bloques estructurados (bike=Zwift, run=intervalos, swim=series)
    created_at = Column(DateTime, default=datetime.utcnow)

    coach     = relationship("User")
    assigned  = relationship("AssignedWorkout", back_populates="template")


# ─────────────────────────────────────────────
# ASSIGNED WORKOUTS
# ─────────────────────────────────────────────
class AssignedWorkout(Base):
    """
    Un workout asignado a un atleta individual O a un grupo.
    Solo uno de athlete_id / group_id debe estar presente.
    """
    __tablename__ = "assigned_workouts"

    id          = Column(String, primary_key=True, default=_uuid)
    template_id = Column(String, ForeignKey("workout_templates.id"), nullable=False)
    athlete_id  = Column(String, ForeignKey("users.id"),   nullable=True)  # asignación individual
    group_id    = Column(String, ForeignKey("groups.id"),  nullable=True)  # asignación grupal
    date_iso      = Column(String, nullable=False)          # "YYYY-MM-DD"
    notas         = Column(Text)                            # nota extra del coach para esta fecha
    coach_comment = Column(Text)                            # comentario post-sesión del coach al atleta
    created_at    = Column(DateTime, default=datetime.utcnow)

    template = relationship("WorkoutTemplate", back_populates="assigned")
    athlete  = relationship("User",  back_populates="assigned_workouts", foreign_keys=[athlete_id])
    group    = relationship("Group", back_populates="assigned_workouts", foreign_keys=[group_id])
    logs     = relationship("WorkoutLog", back_populates="assignment")


# ─────────────────────────────────────────────
# WORKOUT LOG (ejecución real del atleta)
# ─────────────────────────────────────────────
class WorkoutLog(Base):
    __tablename__ = "workout_logs"

    id            = Column(String, primary_key=True, default=_uuid)
    user_id       = Column(String, ForeignKey("users.id"),             nullable=False, index=True)
    assignment_id = Column(String, ForeignKey("assigned_workouts.id"), nullable=False, index=True)
    tss_real      = Column(Integer)
    dist_real     = Column(Float)
    dur_real      = Column(Integer)   # minutos
    rpe           = Column(Integer)   # 1-10 esfuerzo percibido
    completado    = Column(Boolean, default=True)
    notas         = Column(Text)
    logged_at     = Column(DateTime, default=datetime.utcnow)

    user       = relationship("User",           back_populates="workout_logs")
    assignment = relationship("AssignedWorkout", back_populates="logs")


# ─────────────────────────────────────────────
# WELLNESS DIARIO
# ─────────────────────────────────────────────
class WellnessLog(Base):
    __tablename__ = "wellness_logs"

    id         = Column(String, primary_key=True, default=_uuid)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    date_iso   = Column(String, nullable=False)   # YYYY-MM-DD
    fatigue    = Column(Integer)   # 1-5
    sleep_q    = Column(Integer)   # 1-5 calidad del sueño subjetiva
    soreness   = Column(Integer)   # 1-5 dolor muscular
    mood       = Column(Integer)   # 1-5 estado ánimo
    weight_kg  = Column(Float)
    notes      = Column(Text)
    logged_at  = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="wellness_logs")


# ─────────────────────────────────────────────
# WEEK TEMPLATES (Semanas Tipo)
# ─────────────────────────────────────────────
class WeekTemplate(Base):
    """Plantilla de semana reutilizable: conjunto de sesiones por día."""
    __tablename__ = "week_templates"

    id          = Column(String, primary_key=True, default=_uuid)
    coach_id    = Column(String, ForeignKey("users.id"), nullable=False)
    nombre      = Column(String, nullable=False)
    descripcion = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)

    coach = relationship("User")
    days  = relationship(
        "WeekTemplateDay", back_populates="week_template",
        cascade="all, delete-orphan",
        order_by="WeekTemplateDay.day_of_week"
    )


class WeekTemplateDay(Base):
    """Una sesión dentro de una semana tipo: qué día (0=Lun…6=Dom) y qué workout."""
    __tablename__ = "week_template_days"

    id                  = Column(String, primary_key=True, default=_uuid)
    week_template_id    = Column(String, ForeignKey("week_templates.id"), nullable=False)
    day_of_week         = Column(Integer, nullable=False)  # 0=Lun … 6=Dom
    workout_template_id = Column(String, ForeignKey("workout_templates.id"), nullable=False)
    notas               = Column(Text)

    week_template = relationship("WeekTemplate", back_populates="days")
    workout       = relationship("WorkoutTemplate")


# ─────────────────────────────────────────────
# ATHLETE NOTES (Notas del coach por atleta)
# ─────────────────────────────────────────────
class AthleteNote(Base):
    """Nota privada del coach sobre un atleta."""
    __tablename__ = "athlete_notes"

    id         = Column(String, primary_key=True, default=_uuid)
    coach_id   = Column(String, ForeignKey("users.id"), nullable=False)
    athlete_id = Column(String, ForeignKey("users.id"), nullable=False)
    tipo       = Column(String, default="observacion")  # observacion | lesion | meta | carrera
    texto      = Column(Text,   nullable=False)
    fecha      = Column(String, nullable=False)          # YYYY-MM-DD
    created_at = Column(DateTime, default=datetime.utcnow)

    coach   = relationship("User", foreign_keys=[coach_id])
    athlete = relationship("User", foreign_keys=[athlete_id])


# ─────────────────────────────────────────────
# MACROCYCLES (Bloques de semanas tipo)
# ─────────────────────────────────────────────
class Macrocycle(Base):
    """Bloque de entrenamiento: secuencia ordenada de semanas tipo."""
    __tablename__ = "macrocycles"

    id          = Column(String, primary_key=True, default=_uuid)
    coach_id    = Column(String, ForeignKey("users.id"), nullable=False)
    nombre      = Column(String, nullable=False)
    descripcion = Column(Text)
    created_at  = Column(DateTime, default=datetime.utcnow)

    coach = relationship("User")
    weeks = relationship(
        "MacrocycleWeek", back_populates="macrocycle",
        cascade="all, delete-orphan",
        order_by="MacrocycleWeek.position"
    )


class MacrocycleWeek(Base):
    """Una semana tipo dentro de un macrociclo, en una posición dada."""
    __tablename__ = "macrocycle_weeks"

    id               = Column(String, primary_key=True, default=_uuid)
    macrocycle_id    = Column(String, ForeignKey("macrocycles.id"), nullable=False)
    position         = Column(Integer, nullable=False)  # 1, 2, 3, …
    week_template_id = Column(String, ForeignKey("week_templates.id"), nullable=False)
    notas            = Column(Text)

    macrocycle    = relationship("Macrocycle", back_populates="weeks")
    week_template = relationship("WeekTemplate")


# ─────────────────────────────────────────────
# BLOOD LAB EXAMS (Analíticas de sangre)
# ─────────────────────────────────────────────
class BloodLabExam(Base):
    """Un examen de sangre del atleta con sus marcadores."""
    __tablename__ = "blood_lab_exams"

    id         = Column(String, primary_key=True, default=_uuid)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    date_iso   = Column(String, nullable=False)   # YYYY-MM-DD
    lab_name   = Column(String)                   # Nombre del laboratorio
    context    = Column(String)                   # ej: "Pre-temporada", "Post-Ironman"
    values_json = Column(Text, nullable=False)    # JSON: {"hb": 14.2, "hct": 42.1, ...}
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="blood_lab_exams")


# ─────────────────────────────────────────────
# NUTRITION PLANS (Plan nutricional de carrera)
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# LOGIN ATTEMPTS (rate limiting persistente)
# ─────────────────────────────────────────────
class LoginAttempt(Base):
    """Registro de intentos fallidos de login por IP."""
    __tablename__ = "login_attempts"

    id           = Column(String, primary_key=True, default=_uuid)
    ip           = Column(String, nullable=False, index=True)
    attempted_at = Column(DateTime, default=datetime.utcnow, index=True)


class DripLog(Base):
    """Registro de drip emails enviados — evita duplicados."""
    __tablename__ = "drip_logs"

    id         = Column(String, primary_key=True, default=_uuid)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    tag        = Column(String, nullable=False)   # "day3" | "day7"
    sent_at    = Column(DateTime, default=datetime.utcnow)


class NutritionPlan(Base):
    """Plan de nutrición para una carrera específica del atleta."""
    __tablename__ = "nutrition_plans"

    id              = Column(String, primary_key=True, default=_uuid)
    user_id         = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    race_name       = Column(String)              # ej: "Concón 70.3"
    race_date       = Column(String)              # YYYY-MM-DD
    race_dist       = Column(String)              # "70.3" | "IM" | "sprint" | "oly"
    total_kcal      = Column(Integer)
    cho_g           = Column(Float)               # Carbohidratos gramos
    fluid_ml        = Column(Integer)             # Fluidos ml/h estimado
    sodium_mg       = Column(Integer)             # Sodio mg/h
    params_json     = Column(Text)                # JSON con parámetros completos de cálculo
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", backref="nutrition_plans")


# ─────────────────────────────────────────────
# SOCIAL — Follows / Kudos / Comments
# ─────────────────────────────────────────────
class SocialFollow(Base):
    """Relación unidireccional: follower_id sigue a following_id."""
    __tablename__ = "social_follows"

    follower_id  = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    following_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_sf_follower",  "follower_id"),
        Index("ix_sf_following", "following_id"),
    )

    follower  = relationship("User", foreign_keys=[follower_id])
    following = relationship("User", foreign_keys=[following_id])


class SocialKudo(Base):
    """Un kudo (like) de un usuario a un WorkoutLog. Máximo uno por par (log, user)."""
    __tablename__ = "social_kudos"

    id         = Column(String, primary_key=True, default=_uuid)
    log_id     = Column(String, ForeignKey("workout_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(String, ForeignKey("users.id",        ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("log_id", "user_id", name="uq_kudo_log_user"),)

    user = relationship("User")
    log  = relationship("WorkoutLog")


class SocialComment(Base):
    """Comentario de texto sobre un WorkoutLog completado."""
    __tablename__ = "social_comments"

    id         = Column(String, primary_key=True, default=_uuid)
    log_id     = Column(String, ForeignKey("workout_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id  = Column(String, ForeignKey("users.id",        ondelete="CASCADE"), nullable=False, index=True)
    body       = Column(String(1000), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=True)

    author = relationship("User")
    log    = relationship("WorkoutLog")


# ─────────────────────────────────────────────
# GARMIN SYNC — datos históricos por atleta
# ─────────────────────────────────────────────

class GarminActivity(Base):
    """
    Actividad Garmin sincronizada por usuario.
    Una fila por actividad. Upsert por (user_id, activity_id).
    """
    __tablename__ = "garmin_activities"
    __table_args__ = (
        UniqueConstraint("user_id", "activity_id", name="uq_garmin_act"),
        Index("ix_garmin_act_user_date", "user_id", "date_iso"),
    )

    id          = Column(String, primary_key=True, default=_uuid)
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)
    activity_id = Column(String, nullable=False)   # Garmin activityId como string
    name        = Column(String)
    sport       = Column(String)                   # swim | bike | run | gym | other
    date_iso    = Column(String, nullable=False)   # YYYY-MM-DD
    date_label  = Column(String)                   # "15 Jun"
    dur_min     = Column(Integer, default=0)
    dist_km     = Column(Float,   default=0.0)
    avg_hr      = Column(Integer, nullable=True)
    avg_power   = Column(Integer, nullable=True)
    pace_str    = Column(String,  nullable=True)   # "5:12" → run
    swim_pace   = Column(String,  nullable=True)   # "1:45" → swim
    calories    = Column(Integer, nullable=True)
    elev_m      = Column(Float,   nullable=True)
    tss         = Column(Float,   default=0.0)
    icon        = Column(String,  default="🏅")
    color       = Column(String,  default="rgba(127,179,204,.08)")
    stroke      = Column(String,  default="var(--muted)")
    synced_at   = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="garmin_activities")


class GarminTrainingLoad(Base):
    """
    Carga de entrenamiento diaria calculada (CTL/ATL/TSB/TSS).
    Una fila por (user_id, date_iso). Se recalcula en cada sync.
    """
    __tablename__ = "garmin_training_load"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_garmin_load"),
    )

    id       = Column(String, primary_key=True, default=_uuid)
    user_id  = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    date_iso = Column(String, nullable=False)   # YYYY-MM-DD
    ctl      = Column(Float, default=0.0)
    atl      = Column(Float, default=0.0)
    tsb      = Column(Float, default=0.0)
    tss      = Column(Float, default=0.0)       # TSS ese día específico

    user = relationship("User", backref="training_load")


class GarminSyncStatus(Base):
    """
    Estado del último sync Garmin por usuario.
    Una fila por usuario (upsert).
    """
    __tablename__ = "garmin_sync_status"

    id               = Column(String, primary_key=True, default=_uuid)
    user_id          = Column(String, ForeignKey("users.id"), nullable=False, unique=True, index=True)
    status           = Column(String, default="never")  # never | syncing | ok | error
    last_sync_at     = Column(DateTime, nullable=True)
    activities_total = Column(Integer, default=0)
    error            = Column(Text,    nullable=True)

    user = relationship("User", backref="garmin_sync_status")
