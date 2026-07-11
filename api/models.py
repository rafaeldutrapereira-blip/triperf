"""
ORM Models â€” LabX Coach Platform
"""
from __future__ import annotations

import uuid
from datetime import datetime, date, timezone

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float,
    ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
)
from sqlalchemy.orm import relationship

from .database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# USERS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class User(Base):
    __tablename__ = "users"

    id            = Column(String, primary_key=True, default=_uuid)
    email         = Column(String, unique=True, nullable=False, index=True)
    nombre        = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    rol           = Column(String, nullable=False, default="atleta")   # admin | coach | atleta
    plan_nivel    = Column(String, default="basico")                   # basico | pro | elite
    activo        = Column(Boolean, default=True)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    last_login_at = Column(DateTime, nullable=True)                    # analytics: último inicio de sesión
    # Credenciales Garmin del atleta (para sync directo a su cuenta)
    garmin_email    = Column(String, nullable=True)
    garmin_password = Column(String, nullable=True)
    # Carrera objetivo
    race_goal_name = Column(String, nullable=True)
    race_goal_date = Column(String, nullable=True)
    race_goal_dist = Column(String, nullable=True)   # "sprint"|"olympic"|"703"|"full"|"21k"|"42k"
    # MÃ©tricas de rendimiento (perfil atleta)
    ftp            = Column(Integer, nullable=True)   # Functional Threshold Power (W)
    weight_kg      = Column(Float,   nullable=True)
    height_cm      = Column(Integer, nullable=True)
    age            = Column(Integer, nullable=True)
    vo2max         = Column(Float,   nullable=True)
    fcmax          = Column(Integer, nullable=True)   # FC mÃ¡xima (bpm)
    css            = Column(String,  nullable=True)   # Critical Swim Speed "1:48"
    run_pace       = Column(String,  nullable=True)   # Ritmo umbral carrera "4:52"
    # GeneraciÃ³n de tokens â€” incrementar para invalidar todas las sesiones activas
    token_gen      = Column(Integer, default=1, nullable=False, server_default="1")
    # 2FA TOTP â€” I-08: totp_secret cifrado con Fernet; I-01: backup codes
    totp_secret      = Column(String,  nullable=True)   # Fernet-cifrado; None = 2FA desactivado
    totp_enabled     = Column(Boolean, default=False)
    totp_backup_hash = Column(Text,    nullable=True)   # JSON list de hashes SHA-256 de backup codes
    # Sesiones activas â€” I-06: fingerprint del Ãºltimo dispositivo conocido
    last_device_hash = Column(String, nullable=True)    # SHA-256(user_agent+IP) del Ãºltimo login OK
    # Strava OAuth (D-06)
    strava_access_token    = Column(String,  nullable=True)
    strava_refresh_token   = Column(String,  nullable=True)
    strava_athlete_id      = Column(String,  nullable=True)
    strava_token_expires_at = Column(DateTime, nullable=True)
    # Stripe â€” S15: customer_id para portal de facturaciÃ³n
    stripe_customer_id      = Column(String,  nullable=True, index=True)
    stripe_subscription_id  = Column(String,  nullable=True, index=True)
    trial_end_at            = Column(DateTime, nullable=True)
    # Deportes practicados (comma-separated: “swim,bike,run”)
    sports                  = Column(String,   nullable=True)
    # Onboarding completado por primera vez (server-side flag)
    onboarding_completed_at = Column(DateTime, nullable=True)
    # GDPR â€” S11: fecha de consentimiento de tÃ©rminos
    gdpr_consent_at        = Column(DateTime, nullable=True)
    gdpr_consent_ip        = Column(String,   nullable=True)
    # Preferencias de notificaciÃ³n â€” S14
    notif_email_weekly     = Column(Boolean, default=True)
    notif_email_workout    = Column(Boolean, default=True)
    notif_push_wellness    = Column(Boolean, default=True)

    # relations
    groups_coached = relationship("Group",       back_populates="coach",   foreign_keys="Group.coach_id")
    memberships    = relationship("GroupMember", back_populates="user", foreign_keys="GroupMember.athlete_id")
    workout_logs   = relationship("WorkoutLog",  back_populates="user")
    assigned_workouts = relationship("AssignedWorkout", back_populates="athlete",
                                    foreign_keys="AssignedWorkout.athlete_id")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# GROUPS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class Group(Base):
    __tablename__ = "groups"

    id          = Column(String, primary_key=True, default=_uuid)
    nombre      = Column(String, nullable=False)
    descripcion = Column(Text, nullable=True)
    competencia = Column(String)
    coach_id    = Column(String, ForeignKey("users.id"), nullable=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    coach   = relationship("User",        back_populates="groups_coached", foreign_keys=[coach_id])
    members = relationship("GroupMember", back_populates="group", cascade="all, delete-orphan")
    assigned_workouts = relationship("AssignedWorkout", back_populates="group",
                                     foreign_keys="AssignedWorkout.group_id")


class GroupMember(Base):
    __tablename__ = "group_members"

    id         = Column(String, primary_key=True, default=_uuid)
    group_id   = Column(String, ForeignKey("groups.id"),  nullable=False, index=True)
    athlete_id = Column(String, ForeignKey("users.id"),   nullable=False, index=True)
    added_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    group = relationship("Group", back_populates="members")
    user  = relationship("User",  back_populates="memberships", foreign_keys=[athlete_id])


# Coach-Athlete relationship model
class CoachAthlete(Base):
    """Relacion explicita coach-atleta."""
    __tablename__ = "coach_athletes"
    __table_args__ = (
        UniqueConstraint("coach_id", "athlete_id", name="uq_coach_athlete"),
        Index("ix_ca_coach", "coach_id"),
        Index("ix_ca_athlete", "athlete_id"),
    )
    id         = Column(String, primary_key=True, default=_uuid)
    coach_id   = Column(String, ForeignKey("users.id"), nullable=False)
    athlete_id = Column(String, ForeignKey("users.id"), nullable=False)
    group_id   = Column(String, ForeignKey("groups.id"), nullable=True)
    activo     = Column(Boolean, default=True)
    status     = Column(String, default="active")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    coach   = relationship("User", foreign_keys=[coach_id])
    athlete = relationship("User", foreign_keys=[athlete_id])
    @property
    def active(self) -> bool:
        return self.activo



# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# WORKOUT TEMPLATES
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    coach     = relationship("User")
    # B-10: cascade soft-delete â€” al borrar template, las asignaciones se marcan deleted_at
    assigned  = relationship("AssignedWorkout", back_populates="template",
                             cascade="all, delete-orphan")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ASSIGNED WORKOUTS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class AssignedWorkout(Base):
    """
    Un workout asignado a un atleta individual O a un grupo.
    Solo uno de athlete_id / group_id debe estar presente.
    """
    __tablename__ = "assigned_workouts"
    __table_args__ = (
        Index("ix_aw_athlete_date", "athlete_id", "date_iso"),
        Index("ix_aw_date",         "date_iso"),
        # B-01: evita duplicar el mismo template para el mismo atleta en la misma fecha
        UniqueConstraint("template_id", "athlete_id", "date_iso",
                         name="uq_aw_template_athlete_date"),
    )

    id          = Column(String, primary_key=True, default=_uuid)
    template_id = Column(String, ForeignKey("workout_templates.id"), nullable=False)
    athlete_id  = Column(String, ForeignKey("users.id"),   nullable=True)  # asignaciÃ³n individual
    group_id    = Column(String, ForeignKey("groups.id"),  nullable=True)  # asignaciÃ³n grupal
    date_iso      = Column(String, nullable=False)          # "YYYY-MM-DD"
    notas         = Column(Text)                            # nota extra del coach para esta fecha
    coach_comment = Column(Text)                            # comentario post-sesiÃ³n del coach al atleta
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    deleted_at    = Column(DateTime, nullable=True)         # soft-delete

    template = relationship("WorkoutTemplate", back_populates="assigned")
    athlete  = relationship("User",  back_populates="assigned_workouts", foreign_keys=[athlete_id])
    group    = relationship("Group", back_populates="assigned_workouts", foreign_keys=[group_id])
    logs     = relationship("WorkoutLog", back_populates="assignment")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# WORKOUT LOG (ejecuciÃ³n real del atleta)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
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
    logged_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    deleted_at    = Column(DateTime, nullable=True)   # soft-delete

    user       = relationship("User",           back_populates="workout_logs")
    assignment = relationship("AssignedWorkout", back_populates="logs")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# WELLNESS DIARIO (Sprint 15: Recovery Inteligente)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class WellnessLog(Base):
    __tablename__ = "wellness_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_wellness_user_date"),
        Index("ix_wellness_user_date", "user_id", "date_iso"),
    )

    id            = Column(String,  primary_key=True, default=_uuid)
    user_id       = Column(String,  ForeignKey("users.id"), nullable=False)
    date_iso      = Column(String,  nullable=False)   # YYYY-MM-DD
    logged_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    fatigue       = Column(Integer, nullable=True)   # 1-5 (5=muy fatigado)
    sleep_q       = Column(Integer, nullable=True)   # 1-5 calidad sueño
    mood          = Column(Integer, nullable=True)   # 1-5
    soreness      = Column(Integer, nullable=True)   # 1-5
    weight_kg     = Column(Float,   nullable=True)
    notes         = Column(String,  nullable=True)
    deleted_at    = Column(DateTime, nullable=True)

    user = relationship("User", backref="wellness_logs")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# WEEK TEMPLATES (Semanas Tipo)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class WeekTemplate(Base):
    """Plantilla de semana reutilizable: conjunto de sesiones por dÃ­a."""
    __tablename__ = "week_templates"

    id          = Column(String, primary_key=True, default=_uuid)
    coach_id    = Column(String, ForeignKey("users.id"), nullable=False)
    nombre      = Column(String, nullable=False)
    descripcion = Column(Text)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    coach = relationship("User")
    days  = relationship(
        "WeekTemplateDay", back_populates="week_template",
        cascade="all, delete-orphan",
        order_by="WeekTemplateDay.day_of_week"
    )


class WeekTemplateDay(Base):
    """Una sesiÃ³n dentro de una semana tipo: quÃ© dÃ­a (0=Lunâ€¦6=Dom) y quÃ© workout."""
    __tablename__ = "week_template_days"

    id                  = Column(String, primary_key=True, default=_uuid)
    week_template_id    = Column(String, ForeignKey("week_templates.id"), nullable=False)
    day_of_week         = Column(Integer, nullable=False)  # 0=Lun â€¦ 6=Dom
    workout_template_id = Column(String, ForeignKey("workout_templates.id"), nullable=False)
    notas               = Column(Text)

    week_template = relationship("WeekTemplate", back_populates="days")
    workout       = relationship("WorkoutTemplate")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ATHLETE NOTES (Notas del coach por atleta)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class AthleteNote(Base):
    """Nota privada del coach sobre un atleta."""
    __tablename__ = "athlete_notes"

    id         = Column(String, primary_key=True, default=_uuid)
    coach_id   = Column(String, ForeignKey("users.id"), nullable=False)
    athlete_id = Column(String, ForeignKey("users.id"), nullable=False)
    tipo       = Column(String, default="observacion")  # observacion | lesion | meta | carrera
    texto      = Column(Text,   nullable=False)
    fecha      = Column(String, nullable=False)          # YYYY-MM-DD
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    coach   = relationship("User", foreign_keys=[coach_id])
    athlete = relationship("User", foreign_keys=[athlete_id])


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MACROCYCLES (Bloques de semanas tipo)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class Macrocycle(Base):
    """Bloque de entrenamiento: secuencia ordenada de semanas tipo."""
    __tablename__ = "macrocycles"

    id          = Column(String, primary_key=True, default=_uuid)
    coach_id    = Column(String, ForeignKey("users.id"), nullable=False)
    nombre      = Column(String, nullable=False)
    descripcion = Column(Text)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    coach = relationship("User")
    weeks = relationship(
        "MacrocycleWeek", back_populates="macrocycle",
        cascade="all, delete-orphan",
        order_by="MacrocycleWeek.position"
    )


class MacrocycleWeek(Base):
    """Una semana tipo dentro de un macrociclo, en una posiciÃ³n dada."""
    __tablename__ = "macrocycle_weeks"

    id               = Column(String, primary_key=True, default=_uuid)
    macrocycle_id    = Column(String, ForeignKey("macrocycles.id"), nullable=False)
    position         = Column(Integer, nullable=False)  # 1, 2, 3, â€¦
    week_template_id = Column(String, ForeignKey("week_templates.id"), nullable=False)
    notas            = Column(Text)

    macrocycle    = relationship("Macrocycle", back_populates="weeks")
    week_template = relationship("WeekTemplate")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# BLOOD LAB EXAMS (AnalÃ­ticas de sangre)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class BloodLabExam(Base):
    """Un examen de sangre del atleta con sus marcadores."""
    __tablename__ = "blood_lab_exams"

    id                 = Column(String, primary_key=True, default=_uuid)
    user_id            = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    date_iso           = Column(String, nullable=False)   # YYYY-MM-DD
    lab_name           = Column(String)
    context            = Column(String)                   # "Pre-temporada", "Post-Ironman", etc.
    values_json        = Column(Text, nullable=False)     # {"hb": 14.2, "ferritin": 28, ...}
    notes              = Column(Text)                     # Notas del atleta
    ai_interpretation  = Column(Text)                     # JSON de interpretaciÃ³n IA por marcador
    ai_interpreted_at  = Column(DateTime)
    created_at         = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user   = relationship("User", backref="blood_lab_exams")
    alerts = relationship("BloodLabAlert", back_populates="exam", cascade="all, delete-orphan")


class RaceEvent(Base):
    """Carrera registrada por el atleta â€” historial y predicciones."""
    __tablename__ = "race_events"

    id                  = Column(String, primary_key=True, default=_uuid)
    user_id             = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    name                = Column(String, nullable=False)
    date_iso            = Column(String, nullable=False, index=True)   # YYYY-MM-DD
    distance            = Column(String)    # sprint|olympic|703|full|21k|42k|custom
    location            = Column(String)
    is_goal_race        = Column(Boolean, default=False)
    surface             = Column(String)    # road|trail|xc (para running)

    # PredicciÃ³n tomada al momento de registrar
    pred_swim_sec       = Column(Integer)
    pred_bike_sec       = Column(Integer)
    pred_run_sec        = Column(Integer)
    pred_t1_sec         = Column(Integer)
    pred_t2_sec         = Column(Integer)
    pred_total_sec      = Column(Integer)
    pred_ctl_snapshot   = Column(Float)
    pred_tsb_projected  = Column(Float)
    pred_factors_json   = Column(Text)  # penalizaciones Labs + condiciones

    # Resultado real (post-carrera)
    actual_swim_sec     = Column(Integer)
    actual_bike_sec     = Column(Integer)
    actual_run_sec      = Column(Integer)
    actual_t1_sec       = Column(Integer)
    actual_t2_sec       = Column(Integer)
    actual_total_sec    = Column(Integer)
    actual_notes        = Column(Text)
    is_pr               = Column(Boolean, default=False)

    # Briefing IA
    ai_briefing_text    = Column(Text)
    ai_briefing_at      = Column(DateTime)

    created_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="race_events")


class BloodLabAlert(Base):
    """Alerta generada automÃ¡ticamente a partir de un examen de sangre."""
    __tablename__ = "blood_lab_alerts"

    id               = Column(String, primary_key=True, default=_uuid)
    user_id          = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    exam_id          = Column(String, ForeignKey("blood_lab_exams.id"), nullable=False, index=True)
    marker_key       = Column(String, nullable=False)   # "ferritin", "hb", etc.
    severity         = Column(String, nullable=False)   # "info"|"warning"|"critical"
    title            = Column(String, nullable=False)
    body             = Column(Text)
    correlation_note = Column(Text)                     # CorrelaciÃ³n con carga de entrenamiento
    dismissed_at     = Column(DateTime)
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    exam = relationship("BloodLabExam", back_populates="alerts")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# NUTRITION PLANS (Plan nutricional de carrera)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# LOGIN ATTEMPTS (rate limiting persistente)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class LoginAttempt(Base):
    """Registro de intentos fallidos de login por IP."""
    __tablename__ = "login_attempts"

    id           = Column(String, primary_key=True, default=_uuid)
    ip           = Column(String, nullable=False, index=True)
    attempted_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)


class DripLog(Base):
    """Registro de drip emails enviados â€” evita duplicados."""
    __tablename__ = "drip_logs"

    id         = Column(String, primary_key=True, default=_uuid)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    tag        = Column(String, nullable=False)   # "day3" | "day7"
    sent_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class FoodDiaryEntry(Base):
    """
    Entrada individual en el diario alimentario diario.
    Una fila por alimento/porciÃ³n registrado por el atleta.
    """
    __tablename__ = "food_diary_entries"
    __table_args__ = (
        Index("ix_food_diary_user_date", "user_id", "date_iso"),
    )

    id          = Column(String,  primary_key=True, default=_uuid)
    user_id     = Column(String,  ForeignKey("users.id"), nullable=False, index=True)
    date_iso    = Column(String,  nullable=False, index=True)  # YYYY-MM-DD
    meal_slot   = Column(String,  nullable=False, default="other")
    # 'breakfast'|'morning_snack'|'lunch'|'afternoon_snack'|'dinner'|'pre_workout'|'intra_workout'|'post_workout'|'other'

    # Datos del alimento
    food_name   = Column(String,  nullable=False)
    brand       = Column(String,  nullable=True)
    off_id      = Column(String,  nullable=True)   # Open Food Facts product ID
    quantity_g  = Column(Float,   nullable=False, default=100.0)  # gramos

    # Macronutrientes por porciÃ³n consumida (ya calculados con quantity_g)
    kcal        = Column(Float,   nullable=True)
    carbs_g     = Column(Float,   nullable=True)
    protein_g   = Column(Float,   nullable=True)
    fat_g       = Column(Float,   nullable=True)
    fiber_g     = Column(Float,   nullable=True)
    sodium_mg   = Column(Float,   nullable=True)
    sugar_g     = Column(Float,   nullable=True)

    notes       = Column(String,  nullable=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="food_diary_entries")


class TrainingPlan(Base):
    """
    Plan de entrenamiento de N semanas asignado a un atleta.
    Un atleta puede tener mÃºltiples planes (histÃ³rico), uno activo a la vez.
    """
    __tablename__ = "training_plans"
    __table_args__ = (
        Index("ix_training_plan_user", "athlete_id"),
        Index("ix_training_plan_coach", "coach_id"),
    )

    id           = Column(String,  primary_key=True, default=_uuid)
    coach_id     = Column(String,  ForeignKey("users.id"), nullable=False, index=True)
    athlete_id   = Column(String,  ForeignKey("users.id"), nullable=False, index=True)
    name         = Column(String,  nullable=False)
    description  = Column(Text,    nullable=True)
    start_date   = Column(String,  nullable=False)   # YYYY-MM-DD
    end_date     = Column(String,  nullable=False)   # YYYY-MM-DD
    weeks        = Column(Integer, nullable=False, default=16)
    race_id      = Column(String,  ForeignKey("race_events.id"), nullable=True)
    goal_ctl     = Column(Float,   nullable=True)    # CTL objetivo al pico
    peak_week    = Column(Integer, nullable=True)    # nÃºmero de semana del pico
    phase        = Column(String,  nullable=True)    # base|build|peak|race|taper
    template_id  = Column(String,  nullable=True)    # origen si viene de template
    is_active    = Column(Boolean, default=True)
    is_template  = Column(Boolean, default=False)    # True si es plantilla reutilizable
    template_name= Column(String,  nullable=True)    # nombre pÃºblico si is_template
    notes        = Column(Text,    nullable=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    coach    = relationship("User", foreign_keys=[coach_id],   backref="plans_as_coach")
    athlete  = relationship("User", foreign_keys=[athlete_id], backref="plans_as_athlete")
    sessions = relationship("PlanSession", back_populates="plan",
                            cascade="all, delete-orphan",
                            order_by="PlanSession.date_iso")


class PlanSession(Base):
    """
    SesiÃ³n de entrenamiento planificada dentro de un TrainingPlan.
    Una fila por sesiÃ³n (puede haber mÃºltiples por dÃ­a).
    """
    __tablename__ = "plan_sessions"
    __table_args__ = (
        Index("ix_plan_session_plan_date", "plan_id", "date_iso"),
        Index("ix_plan_session_athlete",   "athlete_id"),
    )

    id          = Column(String,  primary_key=True, default=_uuid)
    plan_id     = Column(String,  ForeignKey("training_plans.id"), nullable=False, index=True)
    athlete_id  = Column(String,  ForeignKey("users.id"), nullable=False, index=True)
    date_iso    = Column(String,  nullable=False)   # YYYY-MM-DD
    week_number = Column(Integer, nullable=True)    # 1-N dentro del plan
    day_of_week = Column(Integer, nullable=True)    # 0=Lun â€¦ 6=Dom

    sport       = Column(String,  nullable=False, default="other")
    # swim|bike|run|strength|rest|brick|other

    # PrescripciÃ³n
    title       = Column(String,  nullable=True)
    description = Column(Text,    nullable=True)
    duration_min= Column(Integer, nullable=True)
    distance_km = Column(Float,   nullable=True)
    tss_planned = Column(Float,   nullable=True)   # Training Stress Score planificado
    zone        = Column(String,  nullable=True)   # Z1|Z2|Z3|Z4|Z5|tempo|threshold|VO2|race
    intensity   = Column(String,  nullable=True)   # easy|moderate|hard|race

    # Resultado real (auto-match con actividad Garmin)
    garmin_activity_id = Column(String, ForeignKey("garmin_activities.id"), nullable=True)
    tss_actual         = Column(Float,   nullable=True)
    duration_actual_min= Column(Integer, nullable=True)
    distance_actual_km = Column(Float,   nullable=True)
    completed_at       = Column(DateTime, nullable=True)
    compliance_pct     = Column(Float,   nullable=True)   # 0-100: tss_actual/tss_planned

    # Control
    is_skipped  = Column(Boolean, default=False)
    skip_reason = Column(String,  nullable=True)
    coach_note        = Column(Text,    nullable=True)
    athlete_note      = Column(Text,    nullable=True)
    rpe               = Column(Integer, nullable=True)  # 1-10 Rate of Perceived Exertion
    perceived_effort  = Column(String,  nullable=True)  # easy|moderate|hard|very_hard
    mood              = Column(String,  nullable=True)  # great|good|neutral|tired|bad
    feedback_at       = Column(DateTime, nullable=True)
    was_adjusted= Column(Boolean, default=False)  # True si IA ajustÃ³ la sesiÃ³n
    adjust_reason=Column(String,  nullable=True)

    order_in_day= Column(Integer, default=0)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    plan    = relationship("TrainingPlan",    back_populates="sessions")
    athlete = relationship("User",            foreign_keys=[athlete_id], backref="plan_sessions")


class InjuryRiskSnapshot(Base):
    """
    Snapshot diario de riesgo de lesiÃ³n por atleta.
    Motor multifactorial: ACWR + HRV + MonotonÃ­a + Blood Labs.
    Una fila por (user_id, date_iso) â€” upsert diario vÃ­a scheduler.
    """
    __tablename__ = "injury_risk_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_injury_risk_daily"),
        Index("ix_injury_risk_user_date", "user_id", "date_iso"),
    )

    id       = Column(String,  primary_key=True, default=_uuid)
    user_id  = Column(String,  ForeignKey("users.id"), nullable=False)
    date_iso = Column(String,  nullable=False)

    # Score compuesto 0-100 (0=sin riesgo, 100=riesgo mÃ¡ximo)
    risk_score        = Column(Float,   nullable=True)
    risk_level        = Column(String,  nullable=True)  # 'low'|'moderate'|'high'|'critical'
    risk_color        = Column(String,  nullable=True)  # 'green'|'amber'|'red'|'critical_red'

    # Factores individuales (0-100 cada uno)
    acwr_score        = Column(Float,   nullable=True)   # ACWR component
    hrv_score         = Column(Float,   nullable=True)   # HRV drop vs baseline
    monotony_score    = Column(Float,   nullable=True)   # Foster monotony
    strain_score      = Column(Float,   nullable=True)   # Strain = load Ã— monotony
    labs_score        = Column(Float,   nullable=True)   # Blood Labs penalties

    # Inputs usados para el cÃ¡lculo
    acwr              = Column(Float,   nullable=True)
    hrv_last_night    = Column(Float,   nullable=True)
    hrv_7d_avg        = Column(Float,   nullable=True)
    monotony          = Column(Float,   nullable=True)
    strain            = Column(Float,   nullable=True)
    ctl               = Column(Float,   nullable=True)
    atl               = Column(Float,   nullable=True)
    tsb               = Column(Float,   nullable=True)

    # Alertas activas en este snapshot
    alerts_json       = Column(Text,    nullable=True)   # list[{level, msg}]
    recommendations_json = Column(Text, nullable=True)   # list[str]

    # Trend vs ayer
    risk_delta        = Column(Float,   nullable=True)   # risk_score - yesterday

    created_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="injury_risk_snapshots")


class NutritionPlan(Base):
    """Plan de nutriciÃ³n para una carrera especÃ­fica del atleta."""
    __tablename__ = "nutrition_plans"

    id              = Column(String, primary_key=True, default=_uuid)
    user_id         = Column(String, ForeignKey("users.id"), nullable=False, index=True)
    race_name       = Column(String)              # ej: "ConcÃ³n 70.3"
    race_date       = Column(String)              # YYYY-MM-DD
    race_dist       = Column(String)              # "70.3" | "IM" | "sprint" | "oly"
    total_kcal      = Column(Integer)
    cho_g           = Column(Float)               # Carbohidratos gramos
    fluid_ml        = Column(Integer)             # Fluidos ml/h estimado
    sodium_mg       = Column(Integer)             # Sodio mg/h
    params_json     = Column(Text)                # JSON con parÃ¡metros completos de cÃ¡lculo
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="nutrition_plans")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SOCIAL â€” Follows / Kudos / Comments
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class SocialFollow(Base):
    """RelaciÃ³n unidireccional: follower_id sigue a following_id."""
    __tablename__ = "social_follows"

    follower_id  = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    following_id = Column(String, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    __table_args__ = (
        Index("ix_sf_follower",  "follower_id"),
        Index("ix_sf_following", "following_id"),
    )

    follower  = relationship("User", foreign_keys=[follower_id])
    following = relationship("User", foreign_keys=[following_id])


class SocialKudo(Base):
    """Un kudo (like) de un usuario a un WorkoutLog. MÃ¡ximo uno por par (log, user)."""
    __tablename__ = "social_kudos"

    id         = Column(String, primary_key=True, default=_uuid)
    log_id     = Column(String, ForeignKey("workout_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(String, ForeignKey("users.id",        ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

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
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, nullable=True)

    author = relationship("User")
    log    = relationship("WorkoutLog")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# GARMIN SYNC â€” datos histÃ³ricos por atleta
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

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
    pace_str    = Column(String,  nullable=True)   # "5:12" â†’ run
    swim_pace   = Column(String,  nullable=True)   # "1:45" â†’ swim
    calories    = Column(Integer, nullable=True)
    elev_m      = Column(Float,   nullable=True)
    tss         = Column(Float,   default=0.0)
    icon        = Column(String,  default="ðŸ…")
    color       = Column(String,  default="rgba(127,179,204,.08)")
    stroke      = Column(String,  default="var(--muted)")
    synced_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    # B-24: swim metrics
    swolf            = Column(Float,   nullable=True)   # strokes + seconds per length
    avg_cadence_spm  = Column(Float,   nullable=True)   # strokes per minute
    pool_length_m    = Column(Integer, nullable=True)   # 25 or 50
    # B-23: activity photo
    photo_path       = Column(String,  nullable=True)   # relative: activity_photos/{id}.jpg

    user = relationship("User", backref="garmin_activities")


class GarminTrainingLoad(Base):
    """
    Carga de entrenamiento diaria calculada (CTL/ATL/TSB/TSS/ACWR).
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
    tss      = Column(Float, default=0.0)       # TSS ese dÃ­a especÃ­fico
    acwr     = Column(Float, nullable=True)     # Acute:Chronic Workload Ratio (7:28d)
    monotony = Column(Float, nullable=True)     # TSS_avg / TSS_std (7d) â€” variabilidad
    strain   = Column(Float, nullable=True)     # monotony Ã— tss_week_total

    user = relationship("User", backref="training_load")


class GarminSyncStatus(Base):
    """
    Estado del Ãºltimo sync Garmin por usuario.
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


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SECURITY â€” Tokens revocados y reset de contraseÃ±a
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RevokedToken(Base):
    """
    Tokens JWT revocados explÃ­citamente (logout individual).
    Se almacena el hash SHA-256 para no guardar el token completo.
    Se limpian automÃ¡ticamente al expirar.
    """
    __tablename__ = "revoked_tokens"
    __table_args__ = (Index("ix_revoked_tokens_hash", "token_hash"),)

    id         = Column(String, primary_key=True, default=_uuid)
    token_hash = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class PasswordResetToken(Base):
    """
    Tokens de reset de contraseÃ±a persistentes en DB (reemplaza dict in-memory).
    Se almacena el hash SHA-256 del token. TTL: 1 hora.
    """
    __tablename__ = "password_reset_tokens"
    __table_args__ = (Index("ix_prt_hash", "token_hash"),)

    id         = Column(String, primary_key=True, default=_uuid)
    token_hash = Column(String, nullable=False, unique=True)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at    = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# AUDIT LOG (trazabilidad de acciones crÃ­ticas)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AuditLog(Base):
    """
    Registro inmutable de acciones sensibles: login, logout, cambio de contraseÃ±a,
    asignaciÃ³n de entrenamientos, acceso a datos de atletas, etc.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_user_ts",   "user_id",    "timestamp"),
        Index("ix_audit_action_ts", "action",     "timestamp"),
    )

    id         = Column(String, primary_key=True, default=_uuid)
    timestamp  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    user_id    = Column(String, ForeignKey("users.id"), nullable=True)
    action     = Column(String, nullable=False)
    ip         = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)
    resource   = Column(String, nullable=True)
    detail     = Column(Text,   nullable=True)
    success    = Column(Boolean, default=True)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# MENSAJERÃA INTERNA (coach â†” atleta)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Message(Base):
    """
    Mensajes directos entre coach y atleta.
    El frontend los muestra como inbox bÃ¡sico.
    """
    __tablename__ = "messages"
    __table_args__ = (
        Index("ix_msg_thread", "from_user_id", "to_user_id", "sent_at"),
        Index("ix_msg_to_unread", "to_user_id", "read_at"),
    )

    id           = Column(String, primary_key=True, default=_uuid)
    from_user_id = Column(String, ForeignKey("users.id"), nullable=False)
    to_user_id   = Column(String, ForeignKey("users.id"), nullable=False)
    body         = Column(Text, nullable=False)
    sent_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    read_at      = Column(DateTime, nullable=True)
    deleted_at   = Column(DateTime, nullable=True)

    sender   = relationship("User", foreign_keys=[from_user_id])
    receiver = relationship("User", foreign_keys=[to_user_id])


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PERSONAL RECORDS (marcas personales)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class PersonalRecord(Base):
    """
    Mejores marcas del atleta por distancia/disciplina.
    Pueden ser auto-detectadas desde Garmin o ingresadas manualmente.
    """
    __tablename__ = "personal_records"
    __table_args__ = (
        Index("ix_pr_user_event", "user_id", "event"),
    )

    id         = Column(String, primary_key=True, default=_uuid)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    event      = Column(String, nullable=False)    # "swim_1500m", "bike_40km", "run_10km", "ironman", etc.
    value_sec  = Column(Float,  nullable=False)    # tiempo en segundos
    value_disp = Column(String, nullable=True)     # "1:32:45" (display)
    achieved_at= Column(String, nullable=True)     # YYYY-MM-DD
    source     = Column(String, default="manual")  # "manual" | "garmin"
    garmin_activity_id = Column(String, nullable=True)
    notes      = Column(Text,   nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# GARMIN HEALTH DAILY (datos de salud diarios)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class GarminHealthDaily(Base):
    """
    Snapshot diario de mÃ©tricas de salud Garmin por usuario.
    Una fila por (user_id, date_iso). Se upserta en cada sync.
    Fuente: get_hrv_data(), get_body_battery(), get_sleep_data(), get_stress_data()
    """
    __tablename__ = "garmin_health_daily"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_health_daily"),
        Index("ix_health_user_date", "user_id", "date_iso"),
    )

    id       = Column(String, primary_key=True, default=_uuid)
    user_id  = Column(String, ForeignKey("users.id"), nullable=False)
    date_iso = Column(String, nullable=False)   # YYYY-MM-DD

    # Body Battery (0-100)
    body_battery_min  = Column(Integer, nullable=True)
    body_battery_max  = Column(Integer, nullable=True)
    body_battery_end  = Column(Integer, nullable=True)

    # HRV
    hrv_weekly_avg    = Column(Float, nullable=True)
    hrv_last_night    = Column(Float, nullable=True)    # RMSSD ms
    hrv_baseline_low  = Column(Float, nullable=True)
    hrv_baseline_high = Column(Float, nullable=True)
    hrv_status        = Column(String, nullable=True)   # 'balanced'|'unbalanced'|'low'|'poor'

    # EstrÃ©s (0-100)
    avg_stress        = Column(Integer, nullable=True)
    rest_stress_pct   = Column(Float,   nullable=True)

    # RespiraciÃ³n y SpO2
    avg_respiration   = Column(Float, nullable=True)
    avg_spo2          = Column(Float, nullable=True)
    min_spo2          = Column(Float, nullable=True)

    # Movimiento y FC
    steps             = Column(Integer, nullable=True)
    active_calories   = Column(Integer, nullable=True)
    resting_hr        = Column(Integer, nullable=True)

    # Training Readiness Garmin (0-100)
    training_readiness     = Column(Integer, nullable=True)
    recovery_time_h        = Column(Integer, nullable=True)

    # VO2 Max estimado por Garmin (get_max_metrics)
    vo2max_running    = Column(Float, nullable=True)
    vo2max_cycling    = Column(Float, nullable=True)

    # LabX Readiness Score propio (0-100) â€” calculado localmente
    labx_readiness_score   = Column(Integer, nullable=True)
    labx_readiness_factors = Column(Text,    nullable=True)  # JSON desglose por factor

    synced_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="health_daily")


class GarminSleepSession(Base):
    """
    SesiÃ³n de sueÃ±o detallada por noche (dÃ­a del despertar).
    Complementa GarminHealthDaily con el desglose de fases.
    """
    __tablename__ = "garmin_sleep_sessions"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_sleep_session"),
        Index("ix_sleep_user_date", "user_id", "date_iso"),
    )

    id            = Column(String, primary_key=True, default=_uuid)
    user_id       = Column(String, ForeignKey("users.id"), nullable=False)
    date_iso      = Column(String, nullable=False)   # YYYY-MM-DD

    sleep_start   = Column(DateTime, nullable=True)
    sleep_end     = Column(DateTime, nullable=True)

    # DuraciÃ³n por fases (minutos)
    total_min     = Column(Integer, nullable=True)
    deep_min      = Column(Integer, nullable=True)
    light_min     = Column(Integer, nullable=True)
    rem_min       = Column(Integer, nullable=True)
    awake_min     = Column(Integer, nullable=True)

    # Scores
    sleep_score        = Column(Integer, nullable=True)
    sleep_score_qual   = Column(String,  nullable=True)  # 'excellent'|'good'|'fair'|'poor'

    # MÃ©tricas nocturnas
    avg_spo2_night        = Column(Float, nullable=True)
    avg_respiration_night = Column(Float, nullable=True)
    hrv_rmssd_night       = Column(Float, nullable=True)

    raw_stages_json    = Column(Text, nullable=True)  # JSON: fases crudas para re-procesar

    synced_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="sleep_sessions")


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# AI ENGINE â€” Sesiones, mensajes, insights
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AISession(Base):
    """SesiÃ³n de conversaciÃ³n persistida con el Coach IA."""
    __tablename__ = "ai_sessions"
    __table_args__ = (
        Index("ix_ai_session_user", "user_id", "last_message_at"),
    )

    id              = Column(String, primary_key=True, default=_uuid)
    user_id         = Column(String, ForeignKey("users.id"), nullable=False)
    title           = Column(String, nullable=True)
    last_message_at = Column(DateTime, nullable=True)
    deleted_at      = Column(DateTime, nullable=True)
    created_at      = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user     = relationship("User", backref="ai_sessions")
    messages = relationship("AIMessage", back_populates="session",
                            cascade="all, delete-orphan",
                            order_by="AIMessage.created_at")


class AIMessage(Base):
    """Mensaje individual dentro de una sesiÃ³n de chat IA."""
    __tablename__ = "ai_messages"

    id               = Column(String, primary_key=True, default=_uuid)
    session_id       = Column(String, ForeignKey("ai_sessions.id"), nullable=False, index=True)
    role             = Column(String, nullable=False)   # 'user' | 'assistant'
    content          = Column(Text,   nullable=False)
    context_snapshot = Column(Text,   nullable=True)    # JSON: mÃ©tricas del atleta al momento
    tokens_input     = Column(Integer, nullable=True)
    tokens_output    = Column(Integer, nullable=True)
    model_version    = Column(String,  nullable=True)
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    session = relationship("AISession", back_populates="messages")


class AIInsight(Base):
    """
    Insight proactivo generado por la IA.
    Se genera cada maÃ±ana y tambiÃ©n tras sync de Garmin con datos anÃ³malos.
    """
    __tablename__ = "ai_insights"
    __table_args__ = (
        Index("ix_insight_user_active", "user_id", "created_at"),
    )

    id             = Column(String, primary_key=True, default=_uuid)
    user_id        = Column(String, ForeignKey("users.id"), nullable=False)
    type           = Column(String, nullable=False)    # 'daily_readiness'|'overtraining_risk'|
                                                       # 'injury_risk'|'low_hrv'|'lab_alert'
    severity       = Column(String, default="info")    # 'info'|'warning'|'critical'
    title          = Column(String, nullable=False)
    body           = Column(Text,   nullable=False)
    cta_text       = Column(String, nullable=True)
    cta_url        = Column(String, nullable=True)
    data_snapshot  = Column(Text,   nullable=True)     # JSON: datos que motivaron el insight
    acknowledged_at= Column(DateTime, nullable=True)
    dismissed_at   = Column(DateTime, nullable=True)
    expires_at     = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="ai_insights")


class AIAthleteContext(Base):
    """
    Snapshot diario del contexto completo del atleta para la IA.
    Actualizado cada maÃ±ana (scheduler 6am) y tras cada sync Garmin exitoso.
    Evita recalcular mÃ©tricas en cada llamada al chat.
    """
    __tablename__ = "ai_athlete_context"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_ai_context_user"),
    )

    user_id             = Column(String, ForeignKey("users.id"), primary_key=True)
    context_json        = Column(Text,    nullable=True)   # JSON completo para el prompt
    # MÃ©tricas clave para acceso rÃ¡pido sin parsear JSON
    current_ctl         = Column(Float,   nullable=True)
    current_atl         = Column(Float,   nullable=True)
    current_tsb         = Column(Float,   nullable=True)
    current_acwr        = Column(Float,   nullable=True)
    current_hrv         = Column(Float,   nullable=True)
    current_readiness   = Column(Integer, nullable=True)
    injury_risk_score   = Column(Float,   nullable=True)   # 0.0-1.0
    days_to_race        = Column(Integer, nullable=True)
    context_built_at    = Column(DateTime, nullable=True)
    updated_at          = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="ai_context")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# COMUNIDAD TRIATLÃ“N LATAM (Sprint 13 â€” MÃ³dulo Completo)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class Follow(Base):
    """RelaciÃ³n follower â†’ followed entre usuarios."""
    __tablename__ = "follows"
    __table_args__ = (
        UniqueConstraint("follower_id", "followed_id", name="uq_follow"),
        Index("ix_follow_follower", "follower_id"),
        Index("ix_follow_followed", "followed_id"),
    )
    id          = Column(String, primary_key=True, default=_uuid)
    follower_id = Column(String, ForeignKey("users.id"), nullable=False)
    followed_id = Column(String, ForeignKey("users.id"), nullable=False)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    follower = relationship("User", foreign_keys=[follower_id], backref="following")
    followed = relationship("User", foreign_keys=[followed_id], backref="followers")


class CommunityPost(Base):
    """
    Post de actividad publicada en el feed.
    Puede venir de GarminActivity (auto) o ser un post manual (tipo 'note').
    """
    __tablename__ = "community_posts"
    __table_args__ = (
        Index("ix_post_user_created", "user_id", "created_at"),
        Index("ix_post_visibility",   "visibility", "created_at"),
    )
    id           = Column(String, primary_key=True, default=_uuid)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    activity_id  = Column(String, ForeignKey("garmin_activities.id"), nullable=True)
    post_type    = Column(String, default="activity")  # activity | note | challenge_result
    title        = Column(String, nullable=True)        # override del nombre de actividad
    body         = Column(Text,   nullable=True)        # caption del atleta
    visibility   = Column(String, default="followers")  # public | followers | coach_only | private
    sport        = Column(String, nullable=True)
    dist_km      = Column(Float,  nullable=True)
    dur_min      = Column(Integer,nullable=True)
    tss          = Column(Float,  nullable=True)
    ctl_day      = Column(Float,  nullable=True)        # CTL del dÃ­a de la actividad
    tsb_day      = Column(Float,  nullable=True)        # TSB del dÃ­a
    rpe          = Column(Integer,nullable=True)        # 1-10 del feedback de sesiÃ³n
    card_image   = Column(String, nullable=True)        # path a PNG generada
    is_flagged   = Column(Boolean, default=False)
    flagged_by   = Column(String, ForeignKey("users.id"), nullable=True)
    created_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    updated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), onupdate=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user     = relationship("User",           foreign_keys=[user_id],  backref="community_posts")
    activity = relationship("GarminActivity", foreign_keys=[activity_id], backref="community_post")
    kudos    = relationship("Kudo",    back_populates="post", cascade="all, delete-orphan")
    comments = relationship("Comment", back_populates="post", cascade="all, delete-orphan",
                            order_by="Comment.created_at")


class Kudo(Base):
    """ReacciÃ³n emoji a un post. Un usuario puede dar un kudo por tipo por post."""
    __tablename__ = "kudos"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", "kudo_type", name="uq_kudo"),
        Index("ix_kudo_post", "post_id"),
    )
    id         = Column(String, primary_key=True, default=_uuid)
    post_id    = Column(String, ForeignKey("community_posts.id"), nullable=False)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    kudo_type  = Column(String, nullable=False)   # power|fire|trophy|epic|love
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    post = relationship("CommunityPost", back_populates="kudos")
    user = relationship("User", foreign_keys=[user_id])


class Comment(Base):
    """Comentario en un post. Soporta hilo de respuestas (parent_id)."""
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comment_post", "post_id"),
    )
    id         = Column(String, primary_key=True, default=_uuid)
    post_id    = Column(String, ForeignKey("community_posts.id"), nullable=False)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    parent_id  = Column(String, ForeignKey("comments.id"), nullable=True)
    body       = Column(String(500), nullable=False)
    is_flagged = Column(Boolean, default=False)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    post    = relationship("CommunityPost", back_populates="comments")
    author  = relationship("User", foreign_keys=[user_id])
    replies = relationship("Comment", backref=__import__("sqlalchemy.orm", fromlist=["backref"]).backref("parent", remote_side="Comment.id"))


class CommunityGroup(Base):
    """Grupo / Club de triatlón (comunidad social)."""
    __tablename__ = "community_groups"
    __table_args__ = (
        Index("ix_community_group_sport", "sport"),
    )
    id          = Column(String, primary_key=True, default=_uuid)
    owner_id    = Column(String, ForeignKey("users.id"), nullable=False)
    name        = Column(String, nullable=False, unique=True)
    description = Column(Text,   nullable=True)
    sport       = Column(String, default="triathlon")   # triathlon|swim|bike|run|all
    level       = Column(String, default="open")        # open|intermediate|elite
    is_private  = Column(Boolean, default=False)
    invite_code = Column(String, nullable=True, unique=True)
    avatar_path = Column(String, nullable=True)
    city        = Column(String, nullable=True)
    country     = Column(String, nullable=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    owner   = relationship("User", foreign_keys=[owner_id], backref="owned_community_groups")
    members = relationship("CommunityGroupMember", back_populates="group",
                           cascade="all, delete-orphan")


class CommunityGroupMember(Base):
    """Membresía de un usuario en un grupo de comunidad."""
    __tablename__ = "community_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_community_group_member"),
        Index("ix_cgm_user", "user_id"),
    )
    id         = Column(String, primary_key=True, default=_uuid)
    group_id   = Column(String, ForeignKey("community_groups.id"), nullable=False)
    user_id    = Column(String, ForeignKey("users.id"), nullable=False)
    role       = Column(String, default="member")       # member | admin | coach
    joined_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    group = relationship("CommunityGroup", back_populates="members")
    user  = relationship("User",  foreign_keys=[user_id], backref="community_group_memberships")


class Challenge(Base):
    """Reto de grupo con objetivo numÃ©rico y perÃ­odo."""
    __tablename__ = "challenges"
    __table_args__ = (
        Index("ix_challenge_group", "group_id"),
    )
    id          = Column(String, primary_key=True, default=_uuid)
    group_id    = Column(String, ForeignKey("community_groups.id"), nullable=False)
    creator_id  = Column(String, ForeignKey("users.id"), nullable=False)
    name        = Column(String, nullable=False)
    description = Column(Text,   nullable=True)
    metric      = Column(String, nullable=False)   # km | tss | activities | hours
    sport       = Column(String, default="all")
    target      = Column(Float,  nullable=False)
    start_date  = Column(String, nullable=False)   # YYYY-MM-DD
    end_date    = Column(String, nullable=False)
    is_active   = Column(Boolean, default=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    group   = relationship("CommunityGroup", foreign_keys=[group_id])
    creator = relationship("User",           foreign_keys=[creator_id])
    entries = relationship("ChallengeEntry", back_populates="challenge",
                           cascade="all, delete-orphan")


class ChallengeEntry(Base):
    """Progreso de cada participante en un reto."""
    __tablename__ = "challenge_entries"
    __table_args__ = (
        UniqueConstraint("challenge_id", "user_id", name="uq_challenge_entry"),
    )
    id           = Column(String, primary_key=True, default=_uuid)
    challenge_id = Column(String, ForeignKey("challenges.id"), nullable=False)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    progress     = Column(Float, default=0.0)       # km/TSS/actividades acumuladas
    last_updated = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    challenge = relationship("Challenge", back_populates="entries")
    user      = relationship("User", foreign_keys=[user_id])


class CommunityNotification(Base):
    """NotificaciÃ³n in-app para el feed social."""
    __tablename__ = "community_notifications"
    __table_args__ = (
        Index("ix_cn_user_read", "user_id", "read_at"),
    )
    id          = Column(String, primary_key=True, default=_uuid)
    user_id     = Column(String, ForeignKey("users.id"), nullable=False)  # destinatario
    actor_id    = Column(String, ForeignKey("users.id"), nullable=True)   # quien generÃ³
    notif_type  = Column(String, nullable=False)   # kudo|comment|follow|challenge|mention
    post_id     = Column(String, ForeignKey("community_posts.id"), nullable=True)
    group_id    = Column(String, ForeignKey("community_groups.id"), nullable=True)
    body        = Column(String(200), nullable=True)
    read_at     = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user  = relationship("User", foreign_keys=[user_id], backref="community_notifications")
    actor = relationship("User", foreign_keys=[actor_id])


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# NUTRICIÃ“N INTELIGENTE v2.0 (Sprint 14)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class HydrationLog(Base):
    """Registro de ingesta hÃ­drica diaria (agua + bebidas deportivas)."""
    __tablename__ = "hydration_logs"
    __table_args__ = (Index("ix_hyd_user_date", "user_id", "date_iso"),)

    id         = Column(String,  primary_key=True, default=_uuid)
    user_id    = Column(String,  ForeignKey("users.id"), nullable=False)
    date_iso   = Column(String,  nullable=False)   # YYYY-MM-DD
    logged_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    amount_ml  = Column(Integer, nullable=False)   # ml de la ingesta
    liquid_type= Column(String,  default="water")  # water|sport_drink|coffee|other
    notes      = Column(String,  nullable=True)

    user = relationship("User", backref="hydration_logs")


class WeightLog(Base):
    """Peso corporal diario del atleta (kg, en ayunas idealmente)."""
    __tablename__ = "weight_logs"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_weight_user_date"),
        Index("ix_weight_user_date", "user_id", "date_iso"),
    )

    id         = Column(String,  primary_key=True, default=_uuid)
    user_id    = Column(String,  ForeignKey("users.id"), nullable=False)
    date_iso   = Column(String,  nullable=False)   # YYYY-MM-DD
    weight_kg  = Column(Float,   nullable=False)
    body_fat_pct = Column(Float, nullable=True)    # si el atleta tiene bÃ¡scula de composiciÃ³n
    notes      = Column(String,  nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="weight_logs")


class SupplementLog(Base):
    """Registro de suplementos tomados por el atleta."""
    __tablename__ = "supplement_logs"
    __table_args__ = (Index("ix_supp_user_date", "user_id", "date_iso"),)

    id           = Column(String,  primary_key=True, default=_uuid)
    user_id      = Column(String,  ForeignKey("users.id"), nullable=False)
    date_iso     = Column(String,  nullable=False)
    taken_at     = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    supplement   = Column(String,  nullable=False)  # "caffeine"|"creatine"|"iron"|"vit_d"|custom
    dose_mg      = Column(Float,   nullable=True)
    notes        = Column(String,  nullable=True)

    user = relationship("User", backref="supplement_logs")


class CustomFood(Base):
    """Alimento personalizado creado por el atleta (no en Open Food Facts)."""
    __tablename__ = "custom_foods"
    __table_args__ = (Index("ix_custom_food_user", "user_id"),)

    id         = Column(String,  primary_key=True, default=_uuid)
    user_id    = Column(String,  ForeignKey("users.id"), nullable=False)
    name       = Column(String,  nullable=False)
    brand      = Column(String,  nullable=True)
    serving_g  = Column(Float,   default=100.0)   # tamaÃ±o de porciÃ³n
    kcal_100g  = Column(Float,   nullable=False)
    carbs_100g = Column(Float,   nullable=True)
    protein_100g=Column(Float,   nullable=True)
    fat_100g   = Column(Float,   nullable=True)
    fiber_100g = Column(Float,   nullable=True)
    sodium_100g= Column(Float,   nullable=True)
    is_public  = Column(Boolean, default=False)   # compartir con comunidad en futuro
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="custom_foods")


class FavoriteFood(Base):
    """Alimento marcado como favorito para acceso rÃ¡pido en el diario."""
    __tablename__ = "favorite_foods"
    __table_args__ = (
        UniqueConstraint("user_id", "food_ref", name="uq_fav_food"),
        Index("ix_fav_user", "user_id"),
    )

    id         = Column(String,  primary_key=True, default=_uuid)
    user_id    = Column(String,  ForeignKey("users.id"), nullable=False)
    food_ref   = Column(String,  nullable=False)  # off_id o "custom:{custom_food_id}"
    food_name  = Column(String,  nullable=False)
    brand      = Column(String,  nullable=True)
    default_g  = Column(Float,   default=100.0)  # cantidad habitual del atleta
    kcal_100g  = Column(Float,   nullable=True)
    carbs_100g = Column(Float,   nullable=True)
    protein_100g=Column(Float,   nullable=True)
    fat_100g   = Column(Float,   nullable=True)
    use_count  = Column(Integer, default=1)       # para ordenar por frecuencia
    last_used  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="favorite_foods")


class NutritionInsight(Base):
    """Cache de insights diarios generados por IA para el atleta."""
    __tablename__ = "nutrition_insights"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_insight_user_date"),
    )

    id         = Column(String,  primary_key=True, default=_uuid)
    user_id    = Column(String,  ForeignKey("users.id"), nullable=False)
    date_iso   = Column(String,  nullable=False)
    insights   = Column(Text,    nullable=True)    # JSON list[str]
    meal_suggestions = Column(Text, nullable=True) # JSON list[dict]
    generated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="nutrition_insights")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# RECUPERACIÃ“N INTELIGENTE v1.0 (Sprint 15)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class RecoveryScore(Base):
    """
    Cache del Recovery Score diario calculado por el motor LabX.
    Combina HRV + sueÃ±o + TSB + estrÃ©s + body battery.
    Se recalcula cada vez que llegan nuevos datos Garmin.
    """
    __tablename__ = "recovery_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_recovery_score"),
        Index("ix_recovery_user_date", "user_id", "date_iso"),
    )

    id           = Column(String,  primary_key=True, default=_uuid)
    user_id      = Column(String,  ForeignKey("users.id"), nullable=False)
    date_iso     = Column(String,  nullable=False)

    # Score compuesto 0-100
    score        = Column(Integer, nullable=True)
    level        = Column(String,  nullable=True)   # 'optimal'|'good'|'moderate'|'poor'|'critical'
    color        = Column(String,  nullable=True)   # '#10B981'|'#F0A500'|'#EF4444'

    # Factores individuales 0-100
    hrv_factor          = Column(Float, nullable=True)
    sleep_factor        = Column(Float, nullable=True)
    tsb_factor          = Column(Float, nullable=True)
    stress_factor       = Column(Float, nullable=True)
    body_battery_factor = Column(Float, nullable=True)
    wellness_factor     = Column(Float, nullable=True)  # subjetivo si disponible

    # Pesos usados
    weights_json = Column(Text,    nullable=True)  # JSON dict pesos utilizados

    # RecomendaciÃ³n textual generada
    recommendation      = Column(Text, nullable=True)
    training_suggestion = Column(String, nullable=True)  # 'full'|'moderate'|'easy'|'rest'

    # Metadatos
    data_completeness   = Column(Float, nullable=True)  # % factores disponibles (0-1)
    calculated_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="recovery_scores")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# PLAN ADAPTATIVO DE ENTRENAMIENTO v1.0 (Sprint 16)
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

class PlanAdaptation(Base):
    """
    Ajuste diario calculado por el motor adaptativo.
    Una fila por (user_id, date_iso) â€” upsert con cache 12h.
    No modifica las sesiones base; aÃ±ade una capa de ajuste encima.
    """
    __tablename__ = "plan_adaptations"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_adaptation_user_date"),
        Index("ix_adaptation_user_date", "user_id", "date_iso"),
    )

    id                    = Column(String,  primary_key=True, default=_uuid)
    user_id               = Column(String,  ForeignKey("users.id"), nullable=False)
    date_iso              = Column(String,  nullable=False)  # YYYY-MM-DD

    # Factores de entrada
    recovery_score        = Column(Integer, nullable=True)   # 0-100 from RecoveryScore
    tsb                   = Column(Float,   nullable=True)   # Training Stress Balance
    compliance_7d         = Column(Float,   nullable=True)   # ratio completed/planned 7d
    days_to_race          = Column(Integer, nullable=True)   # dÃ­as a la prÃ³xima carrera A

    # Factores calculados
    intensity_factor      = Column(Float,   nullable=True)   # 0.5-1.1
    taper_factor          = Column(Float,   nullable=True)   # 0.2-1.0
    compliance_factor     = Column(Float,   nullable=True)   # 0.75-1.05
    combined_factor       = Column(Float,   nullable=True)   # producto final

    # Ajuste de sesiÃ³n
    original_tss          = Column(Float,   nullable=True)   # TSS del plan base
    adjusted_tss          = Column(Float,   nullable=True)   # TSS tras ajuste
    original_intensity    = Column(String,  nullable=True)   # easy|moderate|hard|race|rest
    adjusted_intensity    = Column(String,  nullable=True)   # id.
    original_session_type = Column(String,  nullable=True)   # vo2max|threshold|endurance|...
    adjusted_session_type = Column(String,  nullable=True)

    # SeÃ±al y metadatos
    signal                = Column(String,  nullable=True)   # increase|maintain|decrease|taper|rest
    trigger_type          = Column(String,  nullable=True)   # recovery_low|compliance_low|taper|...
    reason_text           = Column(Text,    nullable=True)   # Texto legible en ES
    phase                 = Column(String,  nullable=True)   # base|build|peak|taper|recovery

    # Flujo de aprobaciÃ³n
    auto_applied          = Column(Boolean, default=True)    # False si hay coach que aprueba
    accepted              = Column(Boolean, nullable=True)   # None=pendiente, True/False=decidido
    coach_note            = Column(Text,    nullable=True)

    calculated_at         = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    accepted_at           = Column(DateTime, nullable=True)

    user = relationship("User", backref="plan_adaptations")


class WeeklyPlanSnapshot(Base):
    """
    Resumen semanal del plan: TSS objetivo vs actual, compliance, fase.
    Una fila por (user_id, week_start_iso) â€” upsert.
    """
    __tablename__ = "weekly_plan_snapshots"
    __table_args__ = (
        UniqueConstraint("user_id", "week_start_iso", name="uq_wps_user_week"),
        Index("ix_wps_user_week", "user_id", "week_start_iso"),
    )

    id                    = Column(String,  primary_key=True, default=_uuid)
    user_id               = Column(String,  ForeignKey("users.id"), nullable=False)
    week_start_iso        = Column(String,  nullable=False)  # Lunes de la semana YYYY-MM-DD

    phase                 = Column(String,  nullable=True)   # base|build|peak|taper|recovery
    phase_week            = Column(Integer, nullable=True)   # semana dentro de la fase (1..N)
    planned_tss           = Column(Float,   nullable=True)   # TSS objetivo del plan base
    adjusted_tss          = Column(Float,   nullable=True)   # TSS tras ajuste adaptativo
    actual_tss            = Column(Float,   nullable=True)   # TSS real (de actividades Garmin)
    compliance_pct        = Column(Float,   nullable=True)   # actual/adjusted * 100

    ctl_start             = Column(Float,   nullable=True)
    ctl_end               = Column(Float,   nullable=True)
    adaptations_count     = Column(Integer, default=0)       # cuÃ¡ntos dÃ­as se adaptaron

    updated_at            = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="weekly_plan_snapshots")


# ═══════════════════════════════════════════════════════════════════════════
# SPRINT 18 — RENDIMIENTO MENTAL / MENTAL PERFORMANCE
# ═══════════════════════════════════════════════════════════════════════════

class MentalCheckin(Base):
    __tablename__ = "mental_checkins"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_mental_user_date"),
        Index("ix_mental_user_date", "user_id", "date_iso"),
    )

    id           = Column(String, primary_key=True, default=_uuid)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    date_iso     = Column(String(10), nullable=False)

    # Subjetivo 1-5 (5 = mejor)
    anxiety      = Column(Integer, nullable=True)     # 1=muy ansioso, 5=calmo
    motivation   = Column(Integer, nullable=True)     # 1=sin ganas, 5=muy motivado
    focus        = Column(Integer, nullable=True)     # 1=disperso, 5=muy enfocado
    confidence   = Column(Integer, nullable=True)     # 1=inseguro, 5=muy confiado
    mood         = Column(Integer, nullable=True)     # 1=muy bajo, 5=excelente
    notes        = Column(String(300), nullable=True)

    logged_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="mental_checkins")


class MentalFatigueScore(Base):
    __tablename__ = "mental_fatigue_scores"
    __table_args__ = (
        UniqueConstraint("user_id", "date_iso", name="uq_mfs_user_date"),
        Index("ix_mfs_user_date", "user_id", "date_iso"),
    )

    id                   = Column(String, primary_key=True, default=_uuid)
    user_id              = Column(String, ForeignKey("users.id"), nullable=False)
    date_iso             = Column(String(10), nullable=False)

    score                = Column(Integer, nullable=False)    # 0-100
    level                = Column(String(12), nullable=False) # peak|good|moderate|low|critical
    color                = Column(String(7), nullable=False)  # hex

    # Factor contributions
    checkin_factor       = Column(Float, nullable=True)
    recovery_factor      = Column(Float, nullable=True)
    stress_factor        = Column(Float, nullable=True)
    hrv_factor           = Column(Float, nullable=True)

    signal               = Column(String(20), nullable=True)  # train|reduce|rest|pre_race
    recommendation       = Column(String(300), nullable=True)
    protocol_suggested   = Column(String(60), nullable=True)  # ID del protocolo recomendado

    data_completeness    = Column(Float, default=0.0)
    calculated_at        = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="mental_fatigue_scores")


class MentalProtocolSession(Base):
    """Registra qué protocolos ha completado el atleta."""
    __tablename__ = "mental_protocol_sessions"
    __table_args__ = (
        Index("ix_mps_user", "user_id"),
        Index("ix_mps_date", "date_iso"),
    )

    id           = Column(String, primary_key=True, default=_uuid)
    user_id      = Column(String, ForeignKey("users.id"), nullable=False)
    date_iso     = Column(String(10), nullable=False)
    protocol_id  = Column(String(60), nullable=False)   # slug del protocolo
    duration_min = Column(Integer, nullable=True)
    rating       = Column(Integer, nullable=True)        # 1-5 efectividad percibida
    notes        = Column(String(200), nullable=True)
    completed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    user = relationship("User", backref="mental_protocol_sessions")

# ═══════════════════════════════════════════════════════════════════════════
# SPRINT 19 — RACE DAY INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════════

class RaceResult(Base):
    """Post-race result — actual splits and performance."""
    __tablename__ = "race_results"
    __table_args__ = (
        UniqueConstraint("user_id", "race_event_id", name="uq_race_result_user_event"),
        Index("ix_rr_user", "user_id"),
    )

    id             = Column(String, primary_key=True, default=_uuid)
    user_id        = Column(String, ForeignKey("users.id"), nullable=False)
    race_event_id  = Column(String, ForeignKey("race_events.id"), nullable=True)

    # Actual times (seconds)
    swim_time_s    = Column(Integer, nullable=True)
    t1_time_s      = Column(Integer, nullable=True)
    bike_time_s    = Column(Integer, nullable=True)
    t2_time_s      = Column(Integer, nullable=True)
    run_time_s     = Column(Integer, nullable=True)
    total_time_s   = Column(Integer, nullable=True)

    # Performance metrics
    avg_power_bike_w   = Column(Integer, nullable=True)
    avg_hr_bike        = Column(Integer, nullable=True)
    avg_hr_run         = Column(Integer, nullable=True)
    avg_pace_run_s_km  = Column(Integer, nullable=True)  # seconds/km

    # Execution quality
    pacing_score       = Column(Integer, nullable=True)   # 0-100 how well they executed strategy
    nutrition_score    = Column(Integer, nullable=True)   # 0-100
    overall_feeling    = Column(Integer, nullable=True)   # 1-5 RPE

    # Predicted vs actual
    predicted_total_s  = Column(Integer, nullable=True)
    prediction_error_s = Column(Integer, nullable=True)  # actual - predicted

    dnf                = Column(Boolean, default=False)
    dnf_reason         = Column(String(200), nullable=True)
    notes              = Column(String(500), nullable=True)

    created_at         = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    garmin_activity_id = Column(String, ForeignKey("garmin_activities.id"), nullable=True)

    user = relationship("User", backref="race_results")


class RacePlan(Base):
    """Pre-race generated plan — splits, pacing, nutrition."""
    __tablename__ = "race_plans"
    __table_args__ = (
        UniqueConstraint("user_id", "race_event_id", name="uq_race_plan_user_event"),
        Index("ix_rp_user", "user_id"),
    )

    id             = Column(String, primary_key=True, default=_uuid)
    user_id        = Column(String, ForeignKey("users.id"), nullable=False)
    race_event_id  = Column(String, ForeignKey("race_events.id"), nullable=True)

    # CTL/TSB at time of plan generation
    ctl_at_generation  = Column(Float, nullable=True)
    tsb_at_generation  = Column(Float, nullable=True)
    recovery_score     = Column(Integer, nullable=True)

    # Predicted splits (seconds)
    swim_pred_s    = Column(Integer, nullable=True)
    t1_pred_s      = Column(Integer, nullable=True)
    bike_pred_s    = Column(Integer, nullable=True)
    t2_pred_s      = Column(Integer, nullable=True)
    run_pred_s     = Column(Integer, nullable=True)
    total_pred_s   = Column(Integer, nullable=True)

    # Pacing strategy
    bike_target_if     = Column(Float, nullable=True)   # Intensity Factor 0-1.1
    bike_target_power  = Column(Integer, nullable=True)  # watts
    run_target_pace    = Column(Integer, nullable=True)  # s/km
    run_target_hr      = Column(Integer, nullable=True)

    # Nutrition plan (JSON stored as string)
    nutrition_plan_json = Column(String(2000), nullable=True)

    generated_at   = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    race_date      = Column(String(10), nullable=True)

    user = relationship("User", backref="race_plans")


# ── Sprint 27: Workout Prescription Layer ────────────────────────────────────

class WorkoutPrescription(Base):
    """Coach-authored workout prescription delivered to an athlete."""
    __tablename__ = "workout_prescriptions"
    __table_args__ = (
        Index("ix_wp_athlete_date", "athlete_id", "date_iso"),
        Index("ix_wp_coach", "coach_id"),
    )

    id             = Column(String, primary_key=True, default=_uuid)
    coach_id       = Column(String, ForeignKey("users.id"), nullable=False)
    athlete_id     = Column(String, ForeignKey("users.id"), nullable=False)
    title          = Column(String(200), nullable=False)
    description    = Column(Text, nullable=True)
    sport          = Column(String(20), nullable=False, default="run")
    date_iso       = Column(String(10), nullable=False)
    duration_min   = Column(Integer, nullable=True)
    tss_target     = Column(Float, nullable=True)
    structure_json = Column(String(2000), nullable=True)
    status         = Column(String(20), nullable=False, default="pending")
    prescribed_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)
    completed_at   = Column(DateTime, nullable=True)

    coach    = relationship("User", foreign_keys=[coach_id], backref="prescriptions_given")
    athlete  = relationship("User", foreign_keys=[athlete_id], backref="prescriptions_received")
    feedback = relationship("PrescriptionFeedback", back_populates="prescription", uselist=False)


class PrescriptionFeedback(Base):
    """Athlete's post-workout feedback on a coach prescription."""
    __tablename__ = "prescription_feedbacks"
    __table_args__ = (
        Index("ix_pf_prescription", "prescription_id"),
    )

    id                  = Column(String, primary_key=True, default=_uuid)
    prescription_id     = Column(String, ForeignKey("workout_prescriptions.id"), nullable=False)
    athlete_id          = Column(String, ForeignKey("users.id"), nullable=False)
    rpe                 = Column(Integer, nullable=True)
    notes               = Column(String(500), nullable=True)
    actual_duration_min = Column(Integer, nullable=True)
    tss_actual          = Column(Float, nullable=True)
    feedback_at         = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None), nullable=False)

    prescription = relationship("WorkoutPrescription", back_populates="feedback")
    athlete      = relationship("User", foreign_keys=[athlete_id])


# ═══════════════════════════════════════════════════════════════════════════════
# SEASON PERIODIZATION (Sprint 31)
# ═══════════════════════════════════════════════════════════════════════════════

class TrainingPhase(Base):
    """Macro-ciclo de periodización asignado por el coach a un atleta.

    Permite definir la estructura anual: Base → Build → Peak → Taper → Transition.
    El motor adaptativo usa estos límites para ajustar la carga objetivo por fase.
    """
    __tablename__ = "training_phases"
    __table_args__ = (
        Index("ix_tp_athlete_dates", "athlete_id", "start_date"),
        Index("ix_tp_coach", "coach_id"),
    )

    id               = Column(String, primary_key=True, default=_uuid)
    coach_id         = Column(String, ForeignKey("users.id"), nullable=False)
    athlete_id       = Column(String, ForeignKey("users.id"), nullable=False)
    phase_type       = Column(String(20), nullable=False)   # base|build|peak|taper|transition|recovery
    label            = Column(String(100), nullable=True)   # custom label e.g. "Build 1"
    start_date       = Column(String(10), nullable=False)   # YYYY-MM-DD
    end_date         = Column(String(10), nullable=False)   # YYYY-MM-DD
    ctl_target       = Column(Float, nullable=True)         # CTL objetivo al final de la fase
    tss_weekly_target = Column(Float, nullable=True)        # TSS/semana objetivo
    notes            = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    coach   = relationship("User", foreign_keys=[coach_id],   backref="phases_assigned")
    athlete = relationship("User", foreign_keys=[athlete_id], backref="training_phases")


# ═══════════════════════════════════════════════════════════════════════════════
# PERFORMANCE BENCHMARKS & TRAINING ZONES (Sprint 32)
# ═══════════════════════════════════════════════════════════════════════════════

class PerformanceBenchmark(Base):
    """FTP / threshold values per sport, per athlete.

    From these values the zones_service auto-computes 5-zone models for
    power (bike), pace (run/swim) and heart rate.
    """
    __tablename__ = "performance_benchmarks"
    __table_args__ = (
        Index("ix_pb_athlete_sport", "athlete_id", "sport"),
        Index("ix_pb_athlete_date",  "athlete_id", "test_date"),
    )

    id          = Column(String, primary_key=True, default=_uuid)
    athlete_id  = Column(String, ForeignKey("users.id"), nullable=False)
    coach_id    = Column(String, ForeignKey("users.id"), nullable=True)   # who entered it

    sport       = Column(String(20), nullable=False)  # bike | run | swim

    # Cycling
    ftp_watts   = Column(Integer, nullable=True)       # Functional Threshold Power

    # Running / Swimming pace (seconds per km / per 100 m)
    threshold_pace_sec_km  = Column(Integer, nullable=True)   # T-pace for run
    threshold_pace_sec_100m = Column(Integer, nullable=True)  # CSS for swim

    # Heart rate
    max_hr      = Column(Integer, nullable=True)
    lthr        = Column(Integer, nullable=True)               # Lactate Threshold HR

    # Body metrics (for w/kg)
    weight_kg   = Column(Float, nullable=True)

    # Test metadata
    test_date   = Column(String(10), nullable=False)    # YYYY-MM-DD
    test_type   = Column(String(50), nullable=True)     # 20min | ramp | 8min | CSS | manual
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    athlete = relationship("User", foreign_keys=[athlete_id], backref="benchmarks")
    coach   = relationship("User", foreign_keys=[coach_id])


# ═══════════════════════════════════════════════════════════════════════════════
# TRAINING PLAN TEMPLATES (Sprint 33)
# ═══════════════════════════════════════════════════════════════════════════════

class PlanTemplate(Base):
    """Reusable multi-week training plan skeleton.

    coach_id=NULL means it is a LabX built-in template available to all coaches.
    is_public=True means the coach has shared it with the LabX community.
    """
    __tablename__ = "plan_templates"
    __table_args__ = (
        Index("ix_pt_coach", "coach_id"),
        Index("ix_pt_sport_dist", "sport", "distance_type"),
    )

    id            = Column(String, primary_key=True, default=_uuid)
    coach_id      = Column(String, ForeignKey("users.id"), nullable=True)   # NULL = built-in
    name          = Column(String(200), nullable=False)
    sport         = Column(String(20), nullable=False, default="triathlon")  # triathlon|run|bike|swim
    distance_type = Column(String(30), nullable=True)    # ironman|70.3|sprint|olympic|marathon|…
    weeks         = Column(Integer, nullable=False)
    difficulty    = Column(String(20), nullable=True)    # beginner|intermediate|advanced
    description   = Column(Text, nullable=True)
    is_public     = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    coach   = relationship("User", foreign_keys=[coach_id], backref="plan_templates")
    plan_weeks = relationship(
        "PlanTemplateWeek",
        back_populates="template",
        order_by="PlanTemplateWeek.week_num",
        cascade="all, delete-orphan",
    )


class PlanTemplateWeek(Base):
    """One week's structure inside a PlanTemplate.

    sessions_json is a list of session stubs:
      [{"sport":"bike","title":"Fondo Z2","duration_min":120,"tss":80,"zone":"Z2"}, ...]
    """
    __tablename__ = "plan_template_weeks"
    __table_args__ = (
        Index("ix_ptw_template", "template_id"),
    )

    id            = Column(String, primary_key=True, default=_uuid)
    template_id   = Column(String, ForeignKey("plan_templates.id"), nullable=False)
    week_num      = Column(Integer, nullable=False)   # 1-based
    phase_type    = Column(String(20), nullable=True) # base|build|peak|taper|transition|recovery
    label         = Column(String(100), nullable=True)
    tss_target    = Column(Float, nullable=True)
    hours_target  = Column(Float, nullable=True)
    sessions_json = Column(Text, nullable=True)       # JSON array of session stubs
    notes         = Column(Text, nullable=True)

    template = relationship("PlanTemplate", back_populates="plan_weeks")


class GarminPlannedWorkout(Base):
    """
    Entrenamientos planificados sincronizados desde el calendario Garmin Connect.
    Incluye workouts de Training Peaks, TrainerRoad, etc. pusheados a Garmin.
    """
    __tablename__ = "garmin_planned_workouts"
    __table_args__ = (
        UniqueConstraint("user_id", "garmin_scheduled_id", name="uq_gpw_scheduled"),
        Index("ix_gpw_user_date", "user_id", "date_iso"),
    )

    id                  = Column(String, primary_key=True, default=_uuid)
    user_id             = Column(String, ForeignKey("users.id"), nullable=False)
    date_iso            = Column(String,  nullable=False)   # YYYY-MM-DD fecha planificada
    garmin_scheduled_id = Column(String,  nullable=True)    # ID en Garmin calendar
    workout_id          = Column(String,  nullable=True)    # ID de la plantilla (get_workout_by_id)
    title               = Column(String,  nullable=True)    # nombre del workout
    sport               = Column(String,  nullable=True)    # swim/bike/run/strength/other
    dur_min             = Column(Float,   nullable=True)
    dist_km             = Column(Float,   nullable=True)
    tss_planned         = Column(Float,   nullable=True)    # si Training Peaks lo incluye
    source              = Column(String,  nullable=True)    # 'trainingpeaks'|'garmin'|etc
    raw_json            = Column(Text,    nullable=True)    # payload original
