"""
LabX Training Plan Intelligence
================================
Motor de planificaciÃ³n de entrenamiento con periodizaciÃ³n cientÃ­fica.

Endpoints:
  POST   /plans                          â€” Crear plan
  GET    /plans                          â€” Mis planes (como atleta)
  GET    /plans/{id}                     â€” Detalle con sesiones
  DELETE /plans/{id}                     â€” Eliminar plan
  PATCH  /plans/{id}                     â€” Actualizar metadatos
  POST   /plans/{id}/sessions            â€” Agregar sesiÃ³n
  PATCH  /plans/{id}/sessions/{sid}      â€” Actualizar sesiÃ³n (drag & drop)
  DELETE /plans/{id}/sessions/{sid}      â€” Eliminar sesiÃ³n
  GET    /plans/{id}/ctl-projection      â€” Curva CTL proyectada semana a semana
  GET    /plans/{id}/plan-vs-actual      â€” Plan vs Actual por semana
  POST   /plans/{id}/ai-adjust           â€” Ajuste inteligente IA segÃºn HRV/riesgo
  GET    /plans/templates                â€” CatÃ¡logo de templates
  POST   /plans/templates/{id}/apply     â€” Aplicar template a atleta

  Coach:
  GET    /coach/plans                    â€” Planes de todos mis atletas
  GET    /coach/plans/compliance         â€” Panel compliance todos los atletas
  POST   /coach/plans/bulk-assign        â€” Asignar template a grupo de atletas

PeriodizaciÃ³n:
  Modelo ATL/CTL para proyecciÃ³n: dCTL = (ATL - CTL) / 42
  Fases: Base (CTLâ†‘) â†’ Build (carga sostenida) â†’ Peak (max volumen) â†’ Taper (CTL baja, TSBâ†‘)
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    GarminActivity, GarminTrainingLoad, PlanSession, TrainingPlan, User,
)
from ..auth import get_current_user, require_role

logger = logging.getLogger("labx.plan_builder")
router = APIRouter(tags=["training_plans"])

# â”€â”€ Deportes permitidos â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
SPORTS = {"swim", "bike", "run", "strength", "brick", "rest", "other"}
ZONES  = {"Z1", "Z2", "Z3", "Z4", "Z5", "tempo", "threshold", "vo2max", "race", "recovery"}

# â”€â”€ Templates incorporados â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Cada template es una lista de semanas, cada semana es lista de sesiones por dÃ­a.
# Formato sesiÃ³n: {day:0-6, sport, duration_min, tss, zone, title, intensity}
BUILTIN_TEMPLATES = {
    "ironman_16w": {
        "name":     "Ironman 140.6 â€” 16 Semanas",
        "weeks":    16,
        "goal_ctl": 95,
        "peak_week":14,
        "description": "Plan progresivo con pico en semana 14 y taper 2 semanas. "
                        "Base aerÃ³bica primero, bloques especÃ­ficos de triatlÃ³n las Ãºltimas 8 semanas.",
        "phases": {
            "base":  [1,  5],
            "build": [6,  11],
            "peak":  [12, 14],
            "taper": [15, 16],
        },
        "week_pattern": [
            # [swim_min, bike_min, run_min, strength_min] por fase
            {"phase": "base",  "multiplier": 0.65},
            {"phase": "build", "multiplier": 0.85},
            {"phase": "peak",  "multiplier": 1.00},
            {"phase": "taper", "multiplier": 0.55},
        ],
    },
    "ironman_703_12w": {
        "name":     "Ironman 70.3 â€” 12 Semanas",
        "weeks":    12,
        "goal_ctl": 75,
        "peak_week":10,
        "description": "Plan 12 semanas para Half Ironman. Intensidad media-alta desde semana 5.",
        "phases": {
            "base":  [1, 4],
            "build": [5, 9],
            "peak":  [10, 10],
            "taper": [11, 12],
        },
    },
    "olympic_8w": {
        "name":     "OlÃ­mpico â€” 8 Semanas",
        "weeks":    8,
        "goal_ctl": 60,
        "peak_week":6,
        "description": "Plan de 8 semanas para distancia olÃ­mpica. Alta intensidad.",
        "phases": {
            "base":  [1, 2],
            "build": [3, 5],
            "peak":  [6, 6],
            "taper": [7, 8],
        },
    },
    "marathon_16w": {
        "name":     "MaratÃ³n â€” 16 Semanas",
        "weeks":    16,
        "goal_ctl": 70,
        "peak_week":13,
        "description": "Plan running puro. Larga dominical progresiva hasta 32km en semana 12.",
        "phases": {
            "base":  [1,  6],
            "build": [7,  12],
            "peak":  [13, 13],
            "taper": [14, 16],
        },
    },
}

# â”€â”€ Sesiones tipo por deporte y zona â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _default_sessions_for_week(
    week_num:  int,
    total_weeks: int,
    template_key: str,
    ctl_target: float,
    start_date: str,
    athlete_id: str,
    plan_id:    str,
) -> list[dict]:
    """
    Genera las sesiones por defecto de una semana segÃºn el template y la posiciÃ³n
    en el plan (inicio, build, pico, taper).
    Distribuye la carga para alcanzar ctl_target en el pico.
    """
    tpl = BUILTIN_TEMPLATES.get(template_key, BUILTIN_TEMPLATES["ironman_703_12w"])
    peak_week = tpl.get("peak_week", total_weeks - 2)
    phases    = tpl.get("phases", {})

    # Determinar fase actual
    phase = "base"
    for ph_name, (ph_start, ph_end) in phases.items():
        if ph_start <= week_num <= ph_end:
            phase = ph_name
            break

    # Multiplicador de carga segÃºn fase + progresiÃ³n dentro de la fase
    base_mult  = {"base": 0.55, "build": 0.78, "peak": 1.0, "taper": 0.5}.get(phase, 0.65)
    # Rampa dentro de la fase (semanas 3:1 - 3 semanas carga, 1 descanso)
    week_in_phase = (week_num - (phases.get(phase, (1,1))[0])) % 4
    if week_in_phase == 3:
        base_mult *= 0.65   # semana de recuperaciÃ³n

    # TSS semanal objetivo basado en CTL target
    tss_weekly = ctl_target * 7 * base_mult

    week_start = date.fromisoformat(start_date) + timedelta(weeks=week_num - 1)

    is_tri  = "ironman" in template_key or "703" in template_key or "olympic" in template_key
    is_run  = "marathon" in template_key or "half_marathon" in template_key

    sessions = []

    if is_tri:
        # DistribuciÃ³n TSS: nataciÃ³n 15%, ciclismo 55%, carrera 25%, fuerza 5%
        tss_swim = tss_weekly * 0.15
        tss_bike = tss_weekly * 0.55
        tss_run  = tss_weekly * 0.25
        tss_str  = tss_weekly * 0.05

        swim_if  = 0.72   # intensidad factor tÃ­pica nataciÃ³n Z2
        bike_if  = 0.75
        run_if   = 0.75

        sessions += [
            _ses(week_start, 0, "swim", round(tss_swim * 0.55), "Z2",
                 "NataciÃ³n tÃ©cnica + Z2", week_num, plan_id, athlete_id),
            _ses(week_start, 1, "bike", round(tss_bike * 0.40), "Z2",
                 "Ciclismo aerÃ³bico base", week_num, plan_id, athlete_id),
            _ses(week_start, 2, "run",  round(tss_run  * 0.35), "Z2",
                 "Carrera regenerativa Z2", week_num, plan_id, athlete_id),
            _ses(week_start, 3, "swim", round(tss_swim * 0.45), "threshold",
                 "Intervalos de nataciÃ³n" if phase != "base" else "NataciÃ³n Z1-Z2",
                 week_num, plan_id, athlete_id),
        ]
        if phase in ("build", "peak"):
            sessions.append(
                _ses(week_start, 4, "bike", round(tss_bike * 0.30), "threshold",
                     "Intervalos en bici FTP", week_num, plan_id, athlete_id)
            )
        # SÃ¡bado: ciclismo largo
        sessions.append(
            _ses(week_start, 5, "bike", round(tss_bike * 0.30),
                 "Z2" if phase == "base" else "tempo",
                 "Ciclismo largo", week_num, plan_id, athlete_id)
        )
        # Domingo: carrera larga (o brick en peak)
        if phase == "peak":
            sessions.append(
                _ses(week_start, 6, "brick", round(tss_run * 0.65),
                     "race", "Brick ciclismo + carrera", week_num, plan_id, athlete_id)
            )
        else:
            sessions.append(
                _ses(week_start, 6, "run", round(tss_run * 0.65),
                     "Z2", "Carrera larga Z2", week_num, plan_id, athlete_id)
            )

    elif is_run:
        # DistribuciÃ³n: 4 sesiones carrera, 1 fuerza
        tss_r = tss_weekly * 0.95
        sessions += [
            _ses(week_start, 0, "run", round(tss_r * 0.20), "Z2",
                 "Carrera fÃ¡cil recuperaciÃ³n", week_num, plan_id, athlete_id),
            _ses(week_start, 2, "run", round(tss_r * 0.30),
                 "threshold" if phase != "base" else "Z2",
                 "Tempo o intervalos", week_num, plan_id, athlete_id),
            _ses(week_start, 4, "run", round(tss_r * 0.15), "Z1",
                 "Rodaje suave previo a la larga", week_num, plan_id, athlete_id),
            _ses(week_start, 5, "strength", round(tss_weekly * 0.05),
                 "Z2", "Fuerza + movilidad", week_num, plan_id, athlete_id),
            _ses(week_start, 6, "run", round(tss_r * 0.35), "Z2",
                 "Carrera larga dominical", week_num, plan_id, athlete_id),
        ]

    # En taper: simplificar â€” solo 3 sesiones de calidad
    if phase == "taper":
        sessions = [s for s in sessions if s.get("tss_planned", 0) >= 20][:3]

    return sessions


def _ses(
    week_start:  date,
    day_offset:  int,
    sport:       str,
    tss:         int,
    zone:        str,
    title:       str,
    week_num:    int,
    plan_id:     str,
    athlete_id:  str,
) -> dict:
    """Construye el dict de una sesiÃ³n planificada."""
    d = week_start + timedelta(days=day_offset)
    # DuraciÃ³n estimada en min desde TSS (TSS = (dur/3600) Ã— IFÂ² Ã— FTPÂ² / FTPÂ²  â†’ aprox dur=TSS*60/IFÂ²/100)
    # Para Z2 IF~0.72, threshold IF~0.90 â†’ dur aprox = TSS/0.72Â²*60 â‰ˆ TSS*115
    if_map   = {"Z1":0.65,"Z2":0.72,"Z3":0.80,"threshold":0.88,"tempo":0.84,
                "vo2max":0.95,"race":0.95,"recovery":0.60}
    if_val   = if_map.get(zone, 0.75)
    dur_min  = max(20, round(tss / (if_val**2) / 100 * 60)) if tss > 0 else 45

    sport_dur = {"swim": min(dur_min, 90), "strength": min(dur_min, 60)}.get(sport, dur_min)

    return {
        "plan_id":     plan_id,
        "athlete_id":  athlete_id,
        "date_iso":    d.isoformat(),
        "week_number": week_num,
        "day_of_week": d.weekday(),
        "sport":       sport,
        "title":       title,
        "zone":        zone,
        "tss_planned": max(1, tss),
        "duration_min":sport_dur,
        "intensity":   "easy" if zone in ("Z1","Z2","recovery") else
                       "moderate" if zone in ("Z3","tempo") else "hard",
    }


# â”€â”€ ProyecciÃ³n CTL â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _project_ctl(
    ctl_now:   float,
    weekly_tss_by_week: list[float],
) -> list[float]:
    """
    Proyecta el CTL semana a semana dado el TSS planificado por semana.
    Usa el modelo exponencial de Banister: CTL(t+1) = CTL(t) + (ATL_daily - CTL(t)) / 42
    AproximaciÃ³n: CTL semanal += (TSS_sem/7 - CTL) / 42 Ã— 7
    """
    ctl   = ctl_now
    curve = [ctl]
    for tss_week in weekly_tss_by_week:
        tss_daily = tss_week / 7
        for _ in range(7):
            ctl += (tss_daily - ctl) / 42
        curve.append(round(ctl, 1))
    return curve


# â”€â”€ Serializers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _serialize_session(s: PlanSession) -> dict:
    return {
        "id":           s.id,
        "plan_id":      s.plan_id,
        "date_iso":     s.date_iso,
        "week_number":  s.week_number,
        "day_of_week":  s.day_of_week,
        "sport":        s.sport,
        "title":        s.title,
        "description":  s.description,
        "duration_min": s.duration_min,
        "distance_km":  s.distance_km,
        "tss_planned":  s.tss_planned,
        "zone":         s.zone,
        "intensity":    s.intensity,
        "is_skipped":   s.is_skipped,
        "skip_reason":  s.skip_reason,
        "coach_note":   s.coach_note,
        "athlete_note": s.athlete_note,
        "was_adjusted": s.was_adjusted,
        "adjust_reason":s.adjust_reason,
        "completed": {
            "activity_id":  s.garmin_activity_id,
            "tss_actual":   s.tss_actual,
            "dur_actual":   s.duration_actual_min,
            "dist_actual":  s.distance_actual_km,
            "compliance":   s.compliance_pct,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
        } if s.garmin_activity_id or s.tss_actual else None,
    }


def _serialize_plan(p: TrainingPlan, include_sessions: bool = False) -> dict:
    base = {
        "id":          p.id,
        "name":        p.name,
        "description": p.description,
        "athlete_id":  p.athlete_id,
        "coach_id":    p.coach_id,
        "start_date":  p.start_date,
        "end_date":    p.end_date,
        "weeks":       p.weeks,
        "goal_ctl":    p.goal_ctl,
        "peak_week":   p.peak_week,
        "phase":       p.phase,
        "is_active":   p.is_active,
        "is_template": p.is_template,
        "template_id": p.template_id,
        "race_id":     p.race_id,
        "created_at":  p.created_at.isoformat() if p.created_at else None,
    }
    if include_sessions:
        # Agrupar sesiones por semana y dÃ­a
        weeks: dict[int, dict[int, list]] = {}
        for s in p.sessions:
            wn = s.week_number or 1
            dd = s.day_of_week if s.day_of_week is not None else 0
            weeks.setdefault(wn, {}).setdefault(dd, []).append(_serialize_session(s))
        base["sessions_by_week"] = {
            str(wn): {str(dd): sessions for dd, sessions in days.items()}
            for wn, days in sorted(weeks.items())
        }
        base["total_sessions"]   = len(p.sessions)
        base["total_tss"]        = round(sum(s.tss_planned or 0 for s in p.sessions), 1)
    return base


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Endpoints â€” Atleta
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/plans/templates")
def list_templates(me: User = Depends(get_current_user)):
    """CatÃ¡logo de templates de plan disponibles."""
    result = [{"id": k, **{kk: vv for kk, vv in v.items() if kk not in ("week_pattern", "phases")}}
              for k, v in BUILTIN_TEMPLATES.items()]
    return result


@router.get("/plans")
def list_plans(
    active_only: bool = Query(False),
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Lista mis planes de entrenamiento."""
    q = db.query(TrainingPlan).filter(
        TrainingPlan.athlete_id == me.id,
        TrainingPlan.is_template == False,
    )
    if active_only:
        q = q.filter(TrainingPlan.is_active == True)
    plans = q.order_by(TrainingPlan.start_date.desc()).all()
    return [_serialize_plan(p) for p in plans]


@router.get("/plans/{plan_id}")
def get_plan(
    plan_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """Detalle del plan con todas las sesiones agrupadas por semana."""
    plan = db.query(TrainingPlan).filter(
        TrainingPlan.id == plan_id,
        TrainingPlan.athlete_id == me.id,
    ).first()
    if not plan:
        # Puede que sea un plan del coach para este atleta
        plan = db.query(TrainingPlan).filter(
            TrainingPlan.id == plan_id,
        ).first()
        if not plan or (plan.athlete_id != me.id and plan.coach_id != me.id):
            raise HTTPException(404, "Plan no encontrado")
    return _serialize_plan(plan, include_sessions=True)


@router.get("/plans/{plan_id}/ctl-projection")
def ctl_projection(
    plan_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Proyecta la curva de CTL semana a semana basada en el TSS planificado.
    Ãštil para el overlay SVG del plan builder.
    """
    plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan no encontrado")

    # CTL actual del atleta
    load = (
        db.query(GarminTrainingLoad)
        .filter(GarminTrainingLoad.user_id == plan.athlete_id)
        .order_by(GarminTrainingLoad.date_iso.desc())
        .first()
    )
    ctl_now = round(load.ctl, 1) if load and load.ctl else 40.0

    # TSS planificado por semana
    tss_by_week: dict[int, float] = {}
    for s in plan.sessions:
        wn = s.week_number or 1
        tss_by_week[wn] = tss_by_week.get(wn, 0) + (s.tss_planned or 0)

    weekly_tss = [tss_by_week.get(i, 0) for i in range(1, plan.weeks + 1)]
    ctl_curve  = _project_ctl(ctl_now, weekly_tss)

    return {
        "plan_id":     plan_id,
        "ctl_start":   ctl_now,
        "goal_ctl":    plan.goal_ctl,
        "peak_week":   plan.peak_week,
        "ctl_curve":   ctl_curve,       # len = weeks + 1
        "tss_by_week": weekly_tss,
        "max_ctl":     max(ctl_curve),
        "week_labels": [f"Sem {i}" for i in range(plan.weeks + 1)],
    }


@router.get("/plans/{plan_id}/plan-vs-actual")
def plan_vs_actual(
    plan_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Compara TSS planificado vs TSS real (de actividades Garmin) semana a semana.
    Solo incluye semanas ya pasadas.
    """
    plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan no encontrado")

    today = date.today().isoformat()
    weeks_data = []

    for week_num in range(1, plan.weeks + 1):
        week_start = date.fromisoformat(plan.start_date) + timedelta(weeks=week_num - 1)
        week_end   = week_start + timedelta(days=6)

        if week_start.isoformat() > today:
            break   # Semanas futuras no tienen "actual"

        sessions_this_week = [s for s in plan.sessions if s.week_number == week_num]

        tss_planned = round(sum(s.tss_planned or 0 for s in sessions_this_week), 1)

        # TSS real: actividades Garmin en esa semana
        garmin_acts = (
            db.query(GarminActivity)
            .filter(
                GarminActivity.user_id  == plan.athlete_id,
                GarminActivity.date_iso >= week_start.isoformat(),
                GarminActivity.date_iso <= week_end.isoformat(),
            )
            .all()
        )
        tss_actual = round(sum(a.training_stress_score or 0 for a in garmin_acts), 1)

        compliance = round(tss_actual / tss_planned * 100, 1) if tss_planned > 0 else None

        # Sesiones completadas vs planificadas
        sessions_planned  = len([s for s in sessions_this_week if not s.is_skipped])
        sessions_completed= len([s for s in sessions_this_week if s.garmin_activity_id])
        sessions_skipped  = len([s for s in sessions_this_week if s.is_skipped])

        weeks_data.append({
            "week":              week_num,
            "start_date":        week_start.isoformat(),
            "end_date":          week_end.isoformat(),
            "tss_planned":       tss_planned,
            "tss_actual":        tss_actual,
            "compliance_pct":    compliance,
            "status":            "on_track" if compliance and compliance >= 80
                                 else "under" if compliance and compliance < 60
                                 else "over"  if compliance and compliance > 110
                                 else "partial",
            "sessions_planned":  sessions_planned,
            "sessions_completed":sessions_completed,
            "sessions_skipped":  sessions_skipped,
        })

    overall_compliance = None
    if weeks_data:
        valid = [w["compliance_pct"] for w in weeks_data if w["compliance_pct"] is not None]
        if valid:
            overall_compliance = round(sum(valid) / len(valid), 1)

    return {
        "plan_id":           plan_id,
        "plan_name":         plan.name,
        "weeks":             weeks_data,
        "overall_compliance":overall_compliance,
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Endpoints â€” GestiÃ³n de sesiones
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/plans/{plan_id}/sessions")
def add_session(
    plan_id: str,
    body:    dict,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Agrega una sesiÃ³n al plan.
    Puede ser llamado por el coach (plan de otro atleta) o por el atleta mismo.
    """
    plan = _get_plan_with_access(plan_id, me, db)

    sport = (body.get("sport") or "other").lower()
    if sport not in SPORTS:
        raise HTTPException(422, f"Deporte invÃ¡lido. Opciones: {sorted(SPORTS)}")

    date_iso = (body.get("date_iso") or date.today().isoformat()).strip()
    try:
        d = date.fromisoformat(date_iso)
    except ValueError:
        raise HTTPException(422, "date_iso invÃ¡lido")

    week_num = body.get("week_number")
    if week_num is None:
        start = date.fromisoformat(plan.start_date)
        week_num = max(1, (d - start).days // 7 + 1)

    s = PlanSession(
        plan_id     = plan_id,
        athlete_id  = plan.athlete_id,
        date_iso    = date_iso,
        week_number = week_num,
        day_of_week = d.weekday(),
        sport       = sport,
        title       = (body.get("title") or "").strip() or None,
        description = (body.get("description") or "").strip() or None,
        duration_min= body.get("duration_min"),
        distance_km = body.get("distance_km"),
        tss_planned = body.get("tss_planned"),
        zone        = body.get("zone"),
        intensity   = body.get("intensity"),
        coach_note  = (body.get("coach_note") or "").strip() or None,
        order_in_day= body.get("order_in_day", 0),
    )
    db.add(s)
    db.commit()
    return {"ok": True, "session_id": s.id, "session": _serialize_session(s)}


@router.patch("/plans/{plan_id}/sessions/{session_id}")
def update_session(
    plan_id:    str,
    session_id: str,
    body:       dict,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Actualiza una sesiÃ³n â€” soporta drag & drop (nuevo date_iso),
    actualizaciÃ³n de resultado real y notas del coach/atleta.
    """
    _get_plan_with_access(plan_id, me, db)
    s = db.query(PlanSession).filter(
        PlanSession.id      == session_id,
        PlanSession.plan_id == plan_id,
    ).first()
    if not s:
        raise HTTPException(404, "SesiÃ³n no encontrada")

    # Drag & drop â€” cambio de fecha
    if "date_iso" in body:
        try:
            new_date = date.fromisoformat(body["date_iso"])
        except ValueError:
            raise HTTPException(422, "date_iso invÃ¡lido")
        plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
        s.date_iso    = new_date.isoformat()
        s.day_of_week = new_date.weekday()
        start = date.fromisoformat(plan.start_date)
        s.week_number = max(1, (new_date - start).days // 7 + 1)

    # Metadatos de la sesiÃ³n
    for field in ["sport","title","description","duration_min","distance_km",
                  "tss_planned","zone","intensity","coach_note","order_in_day"]:
        if field in body:
            setattr(s, field, body[field])

    # Resultado real (manual override si no hay auto-match)
    if "tss_actual" in body:
        s.tss_actual         = body["tss_actual"]
        s.duration_actual_min= body.get("duration_actual_min")
        s.distance_actual_km = body.get("distance_actual_km")
        if not s.completed_at:
            s.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        if s.tss_planned and s.tss_actual:
            s.compliance_pct = round(s.tss_actual / s.tss_planned * 100, 1)

    if "is_skipped" in body:
        s.is_skipped  = bool(body["is_skipped"])
        s.skip_reason = (body.get("skip_reason") or "").strip() or None

    if "athlete_note" in body:
        s.athlete_note = (body["athlete_note"] or "").strip() or None

    s.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True, "session": _serialize_session(s)}


@router.delete("/plans/{plan_id}/sessions/{session_id}")
def delete_session(
    plan_id:    str,
    session_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    _get_plan_with_access(plan_id, me, db)
    s = db.query(PlanSession).filter(
        PlanSession.id      == session_id,
        PlanSession.plan_id == plan_id,
    ).first()
    if not s:
        raise HTTPException(404, "SesiÃ³n no encontrada")
    db.delete(s)
    db.commit()
    return {"ok": True}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Endpoints â€” Coach
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/coach/plans")
def coach_create_plan(
    body: dict,
    db:  Session = Depends(get_db),
    me:  User    = Depends(require_role("coach","admin")),
):
    """
    Coach crea un plan para un atleta, opcionalmente desde un template.

    Body:
      athlete_id:   str (requerido)
      name:         str (requerido)
      start_date:   YYYY-MM-DD (requerido)
      weeks:        int (default: 16)
      template_id:  str (opcional â€” genera sesiones automÃ¡ticamente)
      goal_ctl:     float (opcional)
      peak_week:    int (opcional)
      race_id:      str (opcional)
      description:  str (opcional)
    """
    athlete_id = body.get("athlete_id", "").strip()
    name       = body.get("name", "").strip()
    start_date = body.get("start_date", "").strip()

    if not athlete_id:
        raise HTTPException(422, "athlete_id es requerido")
    if not name:
        raise HTTPException(422, "name es requerido")
    if not start_date:
        raise HTTPException(422, "start_date es requerido")

    try:
        start = date.fromisoformat(start_date)
    except ValueError:
        raise HTTPException(422, "start_date invÃ¡lido")

    weeks     = int(body.get("weeks", 16))
    end_date  = (start + timedelta(weeks=weeks)).isoformat()
    tpl_id    = body.get("template_id")
    goal_ctl  = body.get("goal_ctl")
    peak_week = body.get("peak_week")

    if tpl_id and tpl_id in BUILTIN_TEMPLATES:
        tpl = BUILTIN_TEMPLATES[tpl_id]
        goal_ctl  = goal_ctl  or tpl.get("goal_ctl", 75)
        peak_week = peak_week or tpl.get("peak_week", weeks - 2)
        weeks     = tpl.get("weeks", weeks)
        end_date  = (start + timedelta(weeks=weeks)).isoformat()

    plan = TrainingPlan(
        coach_id    = me.id,
        athlete_id  = athlete_id,
        name        = name,
        description = (body.get("description") or "").strip() or None,
        start_date  = start_date,
        end_date    = end_date,
        weeks       = weeks,
        goal_ctl    = goal_ctl,
        peak_week   = peak_week,
        template_id = tpl_id,
        race_id     = body.get("race_id"),
        is_active   = True,
    )
    db.add(plan)
    db.flush()  # para obtener plan.id antes de generar sesiones

    # Si viene con template â†’ generar sesiones por defecto
    sessions_created = 0
    if tpl_id and tpl_id in BUILTIN_TEMPLATES and goal_ctl:
        for wn in range(1, weeks + 1):
            sess_dicts = _default_sessions_for_week(
                week_num      = wn,
                total_weeks   = weeks,
                template_key  = tpl_id,
                ctl_target    = goal_ctl,
                start_date    = start_date,
                athlete_id    = athlete_id,
                plan_id       = plan.id,
            )
            for sd in sess_dicts:
                db.add(PlanSession(**sd))
                sessions_created += 1

    db.commit()

    logger.info("Plan creado coach=%s athlete=%s plan=%s sessions=%d",
                me.id, athlete_id, plan.id, sessions_created)

    return {
        "ok":               True,
        "plan_id":          plan.id,
        "sessions_created": sessions_created,
        "end_date":         end_date,
    }


@router.get("/coach/plans")
def coach_list_plans(
    athlete_id: Optional[str] = Query(None),
    active_only: bool = Query(True),
    db:  Session = Depends(get_db),
    me:  User    = Depends(require_role("coach","admin")),
):
    """Lista planes de todos los atletas del coach (o filtrado por atleta)."""
    q = db.query(TrainingPlan).filter(
        TrainingPlan.coach_id    == me.id,
        TrainingPlan.is_template == False,
    )
    if athlete_id:
        q = q.filter(TrainingPlan.athlete_id == athlete_id)
    if active_only:
        q = q.filter(TrainingPlan.is_active == True)
    plans = q.order_by(TrainingPlan.start_date.desc()).all()
    return [_serialize_plan(p) for p in plans]


@router.get("/coach/plans/compliance")
def coach_compliance_panel(
    db:  Session = Depends(get_db),
    me:  User    = Depends(require_role("coach","admin")),
):
    """
    Panel de compliance para todos los atletas activos del coach.
    Muestra adherencia al plan de la semana actual + 3 semanas anteriores.
    """
    from ..models import CoachAthlete

    today     = date.today()
    week_start= today - timedelta(days=today.weekday())

    athletes = db.query(CoachAthlete).filter(
        CoachAthlete.coach_id == me.id,
        CoachAthlete.activo   == True,
    ).all()

    result = []
    for ca in athletes:
        uid = ca.athlete_id

        # Plan activo
        plan = db.query(TrainingPlan).filter(
            TrainingPlan.athlete_id == uid,
            TrainingPlan.coach_id   == me.id,
            TrainingPlan.is_active  == True,
        ).order_by(TrainingPlan.start_date.desc()).first()

        if not plan:
            continue

        # Semana actual en el plan
        try:
            plan_start = date.fromisoformat(plan.start_date)
            current_week_num = (today - plan_start).days // 7 + 1
        except Exception:
            continue

        # TSS planificado vs real Ãºltimas 4 semanas
        weekly_compliance = []
        for offset in range(3, -1, -1):
            wn    = current_week_num - offset
            if wn < 1:
                continue
            ws    = plan_start + timedelta(weeks=wn - 1)
            we    = ws + timedelta(days=6)
            sesses= [s for s in plan.sessions if s.week_number == wn]
            tss_p = sum(s.tss_planned or 0 for s in sesses)
            acts  = db.query(GarminActivity).filter(
                GarminActivity.user_id  == uid,
                GarminActivity.date_iso >= ws.isoformat(),
                GarminActivity.date_iso <= we.isoformat(),
            ).all()
            tss_a = sum(a.training_stress_score or 0 for a in acts)
            comp  = round(tss_a / tss_p * 100, 1) if tss_p > 0 else None
            weekly_compliance.append({
                "week": wn, "tss_planned": round(tss_p, 1), "tss_actual": round(tss_a, 1),
                "compliance_pct": comp,
            })

        avg_comp = None
        valid = [w["compliance_pct"] for w in weekly_compliance if w["compliance_pct"] is not None]
        if valid:
            avg_comp = round(sum(valid) / len(valid), 1)

        user = db.query(User).filter(User.id == uid).first()
        result.append({
            "athlete_id":     uid,
            "name":           user.nombre if user else uid,
            "plan_name":      plan.name,
            "plan_id":        plan.id,
            "current_week":   current_week_num,
            "total_weeks":    plan.weeks,
            "compliance_avg": avg_comp,
            "weeks":          weekly_compliance,
            "status_color":   "#10B981" if (avg_comp or 0) >= 80
                              else "#EAB308" if (avg_comp or 0) >= 60
                              else "#EF4444",
        })

    result.sort(key=lambda x: x["compliance_avg"] or 0)   # peor adherencia primero
    return result


@router.post("/plans/templates/{template_id}/apply")
def apply_template(
    template_id: str,
    body:        dict,
    db:  Session = Depends(get_db),
    me:  User    = Depends(require_role("coach","admin")),
):
    """
    Aplica un template builtin a uno o mÃ¡s atletas del coach.
    Body: {athlete_ids: [str], start_date: YYYY-MM-DD, name?: str}
    """
    if template_id not in BUILTIN_TEMPLATES:
        raise HTTPException(404, f"Template '{template_id}' no encontrado")

    athlete_ids = body.get("athlete_ids", [])
    start_date  = body.get("start_date", "").strip()
    if not athlete_ids:
        raise HTTPException(422, "athlete_ids es requerido")
    if not start_date:
        raise HTTPException(422, "start_date es requerido")

    tpl   = BUILTIN_TEMPLATES[template_id]
    weeks = tpl["weeks"]
    name  = body.get("name") or tpl["name"]

    results = []
    for uid in athlete_ids:
        plan = TrainingPlan(
            coach_id    = me.id,
            athlete_id  = uid,
            name        = name,
            start_date  = start_date,
            end_date    = (date.fromisoformat(start_date) + timedelta(weeks=weeks)).isoformat(),
            weeks       = weeks,
            goal_ctl    = tpl.get("goal_ctl", 75),
            peak_week   = tpl.get("peak_week", weeks - 2),
            template_id = template_id,
            is_active   = True,
        )
        db.add(plan)
        db.flush()

        cnt = 0
        for wn in range(1, weeks + 1):
            for sd in _default_sessions_for_week(
                week_num=wn, total_weeks=weeks, template_key=template_id,
                ctl_target=tpl.get("goal_ctl", 75), start_date=start_date,
                athlete_id=uid, plan_id=plan.id,
            ):
                db.add(PlanSession(**sd))
                cnt += 1

        results.append({"athlete_id": uid, "plan_id": plan.id, "sessions": cnt})

    db.commit()
    return {"ok": True, "plans_created": len(results), "results": results}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Endpoint â€” AI Adjust (B-01 + B-15 integrado)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/plans/{plan_id}/ai-adjust")
def ai_adjust_plan(
    plan_id: str,
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Ajuste inteligente del plan para los prÃ³ximos 7 dÃ­as.
    Si el riesgo de lesiÃ³n es alto o el HRV estÃ¡ bajo:
    - Intercambia sesiones duras por fÃ¡ciles
    - Reduce TSS de sesiones en dÃ­as de bajo readiness
    - Genera nota de coach explicando el ajuste
    """
    import os
    plan = _get_plan_with_access(plan_id, me, db)

    # Datos de riesgo e HRV actuales
    from ..services.injury_risk_service import compute_injury_risk
    risk = compute_injury_risk(plan.athlete_id, db)

    # Sesiones de los prÃ³ximos 7 dÃ­as
    today  = date.today()
    week_end = (today + timedelta(days=7)).isoformat()
    upcoming = [s for s in plan.sessions
                if s.date_iso >= today.isoformat() and s.date_iso <= week_end
                and not s.is_skipped]

    if not upcoming:
        return {"ok": True, "adjustments": 0, "message": "No hay sesiones programadas esta semana"}

    adjustments = []
    risk_level  = risk.get("risk_level", "low")
    risk_score  = risk.get("risk_score", 0)

    for s in upcoming:
        adj = None
        if risk_level in ("high", "critical") and s.intensity == "hard":
            # Bajar intensidad de sesiones duras
            s.intensity    = "easy"
            s.zone         = "Z1" if s.zone in ("threshold","vo2max","race") else "Z2"
            s.tss_planned  = round((s.tss_planned or 50) * 0.60)
            s.was_adjusted = True
            s.adjust_reason= f"Riesgo lesiÃ³n {risk_score:.0f}/100 â†’ intensidad reducida"
            adj = {"session_id": s.id, "date": s.date_iso, "change": "intensidad reducida (riesgo lesiÃ³n alto)"}
        elif risk_level == "moderate" and s.intensity == "hard" and risk_score > 45:
            s.tss_planned  = round((s.tss_planned or 50) * 0.80)
            s.was_adjusted = True
            s.adjust_reason= f"Riesgo moderado {risk_score:.0f}/100 â†’ TSS -20%"
            adj = {"session_id": s.id, "date": s.date_iso, "change": "TSS reducido 20% (riesgo moderado)"}
        if adj:
            adjustments.append(adj)

    if adjustments:
        db.commit()

    # Generar nota IA con el razonamiento
    note = ""
    if adjustments:
        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if api_key:
            try:
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model="claude-haiku-4-5-20251001",
                    max_tokens=200,
                    messages=[{"role":"user","content":
                        f"El atleta tiene riesgo de lesiÃ³n {risk_score:.0f}/100 ({risk_level}). "
                        f"Se ajustaron {len(adjustments)} sesiones esta semana. "
                        f"Alertas: {[a['msg'] for a in risk.get('alerts', [])[:2]]}. "
                        "Escribe una nota corta de 2-3 oraciones para el atleta explicando el ajuste. En espaÃ±ol."}]
                )
                note = resp.content[0].text.strip() if resp.content else ""
            except Exception:
                pass

    return {
        "ok":          True,
        "adjustments": len(adjustments),
        "risk_score":  risk_score,
        "risk_level":  risk_level,
        "changes":     adjustments,
        "coach_note":  note,
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Helper de acceso
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ATHLETE FEEDBACK (Sprint 10 â€” B-22 RPE)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _FeedbackIn(BaseModel):
    rpe:              Optional[int]  = None   # 1-10
    perceived_effort: Optional[str] = None   # easy|moderate|hard|very_hard
    mood:             Optional[str] = None   # great|good|neutral|tired|bad
    athlete_note:     Optional[str] = None


@router.patch("/plans/{plan_id}/sessions/{session_id}/athlete-feedback")
def save_athlete_feedback(
    plan_id:    str,
    session_id: str,
    body:       _FeedbackIn,
    db:         Session = Depends(get_db),
    me:         User    = Depends(get_current_user),
):
    """
    El atleta registra su percepciÃ³n de esfuerzo (RPE), estado de Ã¡nimo
    y nota personal sobre la sesiÃ³n. Solo el propio atleta puede hacer esto.
    """
    sess = db.query(PlanSession).filter(
        PlanSession.id         == session_id,
        PlanSession.plan_id    == plan_id,
        PlanSession.athlete_id == me.id,
    ).first()
    if not sess:
        raise HTTPException(404, "SesiÃ³n no encontrada")

    if body.rpe is not None:
        if not (1 <= body.rpe <= 10):
            raise HTTPException(400, "RPE debe ser entre 1 y 10")
        sess.rpe = body.rpe
    if body.perceived_effort is not None:
        valid_pe = {"easy", "moderate", "hard", "very_hard"}
        if body.perceived_effort not in valid_pe:
            raise HTTPException(400, f"perceived_effort invÃ¡lido. Valores: {valid_pe}")
        sess.perceived_effort = body.perceived_effort
    if body.mood is not None:
        valid_moods = {"great", "good", "neutral", "tired", "bad"}
        if body.mood not in valid_moods:
            raise HTTPException(400, f"mood invÃ¡lido. Valores: {valid_moods}")
        sess.mood = body.mood
    if body.athlete_note is not None:
        sess.athlete_note = body.athlete_note.strip()[:1000]

    sess.feedback_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(sess)

    return {
        "id":               sess.id,
        "rpe":              sess.rpe,
        "perceived_effort": sess.perceived_effort,
        "mood":             sess.mood,
        "athlete_note":     sess.athlete_note,
        "feedback_at":      str(sess.feedback_at)[:19] if sess.feedback_at else None,
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# PLAN CALENDAR (Sprint 10 â€” Coach Calendar View)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/plans/{plan_id}/calendar")
def get_plan_calendar(
    plan_id:    str,
    year:       Optional[int] = Query(None, description="AÃ±o a mostrar (default: aÃ±o del plan)"),
    month:      Optional[int] = Query(None, ge=1, le=12, description="Mes especÃ­fico (1-12), si no: plan completo"),
    db:         Session = Depends(get_db),
    me:         User    = Depends(get_current_user),
):
    """
    Vista de calendario del plan: retorna sesiones organizadas por fecha ISO.

    El coach ve RPE y notas del atleta; el atleta solo ve las suyas.
    Para el frontend: cada dÃ­a â†’ lista de sesiones de ese dÃ­a con pill data.

    Retorna:
      calendar:   dict[date_iso] â†’ list[session_pill]
      weeks:      list[{week_num, dates, tss_planned, tss_actual, compliance_pct}]
      plan_meta:  {name, start_date, end_date, weeks, phase}
      rpe_summary: promedio RPE por semana
    """
    plan = _get_plan_with_access(plan_id, me, db)

    # Todas las sesiones del plan
    all_sessions = (
        db.query(PlanSession)
        .filter(PlanSession.plan_id == plan_id)
        .order_by(PlanSession.date_iso, PlanSession.order_in_day)
        .all()
    )

    # Filtrar por mes si se pide
    if month and year:
        month_prefix = f"{year:04d}-{month:02d}"
        all_sessions = [s for s in all_sessions if s.date_iso.startswith(month_prefix)]
    elif month:
        # Mes en cualquier aÃ±o del plan
        all_sessions = [s for s in all_sessions if s.date_iso[5:7] == f"{month:02d}"]

    # Construir dict calendario dia â†’ [sesiones]
    calendar: dict[str, list] = {}
    for sess in all_sessions:
        d = sess.date_iso
        if d not in calendar:
            calendar[d] = []

        is_coach = (plan.coach_id == me.id)
        pill = {
            "id":           sess.id,
            "sport":        sess.sport,
            "title":        sess.title,
            "duration_min": sess.duration_min,
            "distance_km":  sess.distance_km,
            "tss_planned":  sess.tss_planned,
            "tss_actual":   sess.tss_actual,
            "zone":         sess.zone,
            "intensity":    sess.intensity,
            "week_number":  sess.week_number,
            "completed":    sess.completed_at is not None,
            "is_skipped":   sess.is_skipped,
            "compliance_pct": sess.compliance_pct,
            "rpe":          sess.rpe,
            "perceived_effort": sess.perceived_effort,
            "mood":         sess.mood,
            "athlete_note": sess.athlete_note,
            "coach_note":   sess.coach_note if is_coach else None,
            "feedback_at":  str(sess.feedback_at)[:19] if sess.feedback_at else None,
        }
        calendar[d].append(pill)

    # Agrupar por semana (week_number â†’ stats)
    weeks_map: dict[int, dict] = {}
    for sess in all_sessions:
        wn = sess.week_number or 0
        if wn not in weeks_map:
            weeks_map[wn] = {
                "week_number":   wn,
                "tss_planned":   0.0,
                "tss_actual":    0.0,
                "n_sessions":    0,
                "n_completed":   0,
                "n_skipped":     0,
                "rpe_values":    [],
                "dates":         [],
            }
        w = weeks_map[wn]
        w["tss_planned"] += sess.tss_planned or 0
        w["tss_actual"]  += sess.tss_actual  or 0
        w["n_sessions"]  += 1
        if sess.completed_at:    w["n_completed"] += 1
        if sess.is_skipped:      w["n_skipped"]   += 1
        if sess.rpe:             w["rpe_values"].append(sess.rpe)
        if sess.date_iso not in w["dates"]: w["dates"].append(sess.date_iso)

    weeks = []
    for wn in sorted(weeks_map.keys()):
        w  = weeks_map[wn]
        rpe_avg = round(sum(w["rpe_values"]) / len(w["rpe_values"]), 1) if w["rpe_values"] else None
        non_skipped = w["n_sessions"] - w["n_skipped"]
        comp_pct    = round(w["n_completed"] / max(non_skipped, 1) * 100) if non_skipped else None
        weeks.append({
            "week_number":    wn,
            "tss_planned":    round(w["tss_planned"], 1),
            "tss_actual":     round(w["tss_actual"],  1),
            "n_sessions":     w["n_sessions"],
            "n_completed":    w["n_completed"],
            "compliance_pct": comp_pct,
            "rpe_avg":        rpe_avg,
            "dates":          sorted(w["dates"]),
        })

    return {
        "plan_meta": {
            "id":         plan.id,
            "name":       plan.name,
            "start_date": plan.start_date,
            "end_date":   plan.end_date,
            "weeks":      plan.weeks,
            "phase":      plan.phase,
            "goal_ctl":   plan.goal_ctl,
        },
        "calendar": calendar,
        "weeks":    weeks,
        "n_days_with_sessions": len(calendar),
        "n_total_sessions":     sum(len(v) for v in calendar.values()),
    }


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# COACH RPE DASHBOARD
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/coach/plans/rpe-summary")
def get_coach_rpe_summary(
    days_back: int = Query(14, ge=7, le=90),
    db:  Session = Depends(get_db),
    me:  User    = Depends(get_current_user),
):
    """
    Dashboard de RPE del coach: resumen de percepciÃ³n de esfuerzo de todos
    sus atletas en los Ãºltimos N dÃ­as. Detecta sobre-esfuerzo sistemÃ¡tico.
    """
    cutoff = (date.today() - timedelta(days=days_back)).isoformat()

    plans = (
        db.query(TrainingPlan)
        .filter(TrainingPlan.coach_id == me.id, TrainingPlan.is_active == True)
        .all()
    )

    summary = []
    for plan in plans:
        sessions = (
            db.query(PlanSession)
            .filter(
                PlanSession.plan_id  == plan.id,
                PlanSession.date_iso >= cutoff,
                PlanSession.rpe.isnot(None),
            )
            .order_by(PlanSession.date_iso.desc())
            .all()
        )
        if not sessions:
            continue

        rpe_vals     = [s.rpe for s in sessions if s.rpe]
        rpe_avg      = round(sum(rpe_vals) / len(rpe_vals), 1) if rpe_vals else None
        high_rpe     = sum(1 for r in rpe_vals if r >= 8)
        last_session = sessions[0]

        # Detectar patrÃ³n de sobre-esfuerzo: >50% sesiones con RPE>=8
        overload_flag = high_rpe / max(len(rpe_vals), 1) >= 0.5

        # Compliance reciente
        total_planned = db.query(PlanSession).filter(
            PlanSession.plan_id  == plan.id,
            PlanSession.date_iso >= cutoff,
            PlanSession.is_skipped == False,
        ).count()
        completed = db.query(PlanSession).filter(
            PlanSession.plan_id    == plan.id,
            PlanSession.date_iso   >= cutoff,
            PlanSession.completed_at.isnot(None),
        ).count()

        summary.append({
            "plan_id":      plan.id,
            "plan_name":    plan.name,
            "athlete_id":   plan.athlete_id,
            "rpe_avg":      rpe_avg,
            "rpe_sessions": len(rpe_vals),
            "high_rpe_count": high_rpe,
            "overload_flag":  overload_flag,
            "last_feedback":  str(last_session.feedback_at)[:10] if last_session.feedback_at else None,
            "compliance_pct": round(completed / max(total_planned, 1) * 100),
            "last_mood":      last_session.mood,
            "alert": (
                "âš ï¸ Atleta reporta sobrecarga sistemÃ¡tica"
                if overload_flag else None
            ),
        })

    # Ordenar por severidad: primero los que tienen overload_flag=True
    summary.sort(key=lambda x: (not x["overload_flag"], -(x["rpe_avg"] or 0)))

    return {
        "period":    f"Ãºltimos {days_back} dÃ­as",
        "athletes":  summary,
        "n_plans":   len(summary),
        "n_alerts":  sum(1 for a in summary if a["overload_flag"]),
    }


def _get_plan_with_access(plan_id: str, me: User, db: Session) -> TrainingPlan:
    """Retorna el plan si el usuario es el atleta o el coach del plan."""
    plan = db.query(TrainingPlan).filter(TrainingPlan.id == plan_id).first()
    if not plan:
        raise HTTPException(404, "Plan no encontrado")
    if plan.athlete_id != me.id and plan.coach_id != me.id:
        raise HTTPException(404, "Plan no encontrado")
    return plan


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Plan Template Library (Sprint 13)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class _SaveTemplateIn(BaseModel):
    template_name: str
    description:   Optional[str] = None
    is_public:     bool = False   # visible a otros coaches


@router.post("/coach/plans/{plan_id}/save-as-template", status_code=201)
def save_plan_as_template(
    plan_id:  str,
    body:     _SaveTemplateIn,
    db:       Session = Depends(get_db),
    me:       User    = Depends(require_role("coach","admin")),
):
    """
    Sprint 13: Guarda un plan existente como template reutilizable.
    Clona el plan + sesiones en modo template (sin athlete_id efectivo).
    """
    import uuid as _uuid_mod
    from datetime import date as _d

    plan = db.query(TrainingPlan).filter(
        TrainingPlan.id       == plan_id,
        TrainingPlan.coach_id == me.id,
    ).first()
    if not plan:
        raise HTTPException(404, "Plan no encontrado o no eres el coach")

    # Clonar el plan como template
    tmpl = TrainingPlan(
        id            = str(_uuid_mod.uuid4()),
        coach_id      = me.id,
        athlete_id    = me.id,   # self-referencia; templates no tienen atleta real
        name          = body.template_name.strip(),
        description   = (body.description or plan.description or "").strip(),
        start_date    = "2000-01-01",   # placeholder; se reajusta al aplicar
        end_date      = "2000-12-31",
        weeks         = plan.weeks,
        goal_ctl      = plan.goal_ctl,
        peak_week     = plan.peak_week,
        is_template   = True,
        is_active     = False,
        template_name = body.template_name.strip(),
        notes         = plan.notes,
        template_id   = plan.id,
    )
    db.add(tmpl)
    db.flush()

    # Clonar sesiones con offset de semana
    for sess in plan.sessions:
        try:
            orig_date = _d.fromisoformat(sess.date_iso)
            plan_start = _d.fromisoformat(plan.start_date)
            day_offset = (orig_date - plan_start).days
        except ValueError:
            day_offset = 0

        new_sess = PlanSession(
            id          = str(_uuid_mod.uuid4()),
            plan_id     = tmpl.id,
            athlete_id  = me.id,
            date_iso    = f"2000-01-{1 + (day_offset % 365):02d}",  # placeholder relativo
            week_number = sess.week_number,
            day_of_week = sess.day_of_week,
            sport       = sess.sport,
            title       = sess.title,
            zone        = sess.zone,
            duration_min= sess.duration_min,
            distance_km = sess.distance_km,
            tss_planned = sess.tss_planned,
            coach_note  = sess.coach_note,
        )
        db.add(new_sess)

    db.commit()
    return {
        "ok":         True,
        "template_id":tmpl.id,
        "template_name": tmpl.template_name,
        "weeks":      tmpl.weeks,
        "n_sessions": len(plan.sessions),
    }


@router.get("/coach/plan-templates")
def list_plan_templates(
    db: Session = Depends(get_db),
    me: User    = Depends(require_role("coach","admin")),
):
    """Sprint 13: Biblioteca de templates del coach."""
    templates = db.query(TrainingPlan).filter(
        TrainingPlan.is_template == True,
        TrainingPlan.coach_id    == me.id,
    ).order_by(TrainingPlan.created_at.desc()).all()

    return [
        {
            "id":           t.id,
            "name":         t.template_name or t.name,
            "description":  t.description,
            "weeks":        t.weeks,
            "goal_ctl":     t.goal_ctl,
            "n_sessions":   len(t.sessions),
            "created_at":   t.created_at.isoformat() if t.created_at else None,
        }
        for t in templates
    ]


class _CreateFromTemplateIn(BaseModel):
    athlete_id:  str
    start_date:  str   # YYYY-MM-DD â€” primer lunes del plan
    plan_name:   Optional[str] = None


@router.post("/coach/plan-templates/{template_id}/create-plan", status_code=201)
def create_plan_from_template(
    template_id: str,
    body:        _CreateFromTemplateIn,
    db:          Session = Depends(get_db),
    me:          User    = Depends(require_role("coach","admin")),
):
    """
    Sprint 13: Crea un nuevo plan para un atleta a partir de un template del coach.
    Reajusta las fechas de sesiones relativas al start_date indicado.
    """
    import uuid as _uuid_mod
    from datetime import date as _d, timedelta as _td

    tmpl = db.query(TrainingPlan).filter(
        TrainingPlan.id          == template_id,
        TrainingPlan.is_template == True,
        TrainingPlan.coach_id    == me.id,
    ).first()
    if not tmpl:
        raise HTTPException(404, "Template no encontrado")

    athlete = db.query(User).filter(User.id == body.athlete_id).first()
    if not athlete:
        raise HTTPException(404, "Atleta no encontrado")

    try:
        start = _d.fromisoformat(body.start_date)
    except ValueError:
        raise HTTPException(400, "start_date invÃ¡lido, usar YYYY-MM-DD")

    end = start + _td(weeks=tmpl.weeks) - _td(days=1)

    new_plan = TrainingPlan(
        id          = str(_uuid_mod.uuid4()),
        coach_id    = me.id,
        athlete_id  = body.athlete_id,
        name        = body.plan_name or tmpl.template_name or tmpl.name,
        description = tmpl.description,
        start_date  = start.isoformat(),
        end_date    = end.isoformat(),
        weeks       = tmpl.weeks,
        goal_ctl    = tmpl.goal_ctl,
        peak_week   = tmpl.peak_week,
        is_template = False,
        is_active   = True,
        template_id = tmpl.id,
        notes       = tmpl.notes,
    )
    db.add(new_plan)
    db.flush()

    # Reajustar fechas de sesiones
    # Las sesiones del template usan dÃ­a-offset basado en week_number + day_of_week
    n_created = 0
    for ts in sorted(tmpl.sessions, key=lambda s: (s.week_number or 0, s.day_of_week or 0)):
        wk  = max(0, (ts.week_number or 1) - 1)
        dow = ts.day_of_week or 0         # 0=Lun, 6=Dom
        session_date = start + _td(weeks=wk, days=dow)

        new_s = PlanSession(
            id          = str(_uuid_mod.uuid4()),
            plan_id     = new_plan.id,
            athlete_id  = body.athlete_id,
            date_iso    = session_date.isoformat(),
            week_number = ts.week_number,
            day_of_week = ts.day_of_week,
            sport       = ts.sport,
            title       = ts.title,
            zone        = ts.zone,
            duration_min= ts.duration_min,
            distance_km = ts.distance_km,
            tss_planned = ts.tss_planned,
            coach_note  = ts.coach_note,
        )
        db.add(new_s)
        n_created += 1

    db.commit()
    return {
        "ok":          True,
        "plan_id":     new_plan.id,
        "athlete_id":  body.athlete_id,
        "start_date":  start.isoformat(),
        "end_date":    end.isoformat(),
        "weeks":       tmpl.weeks,
        "n_sessions":  n_created,
    }
    return plan


