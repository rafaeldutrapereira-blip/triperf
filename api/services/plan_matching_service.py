"""
LabX Plan Matching Service
===========================
Auto-match sesiones planificadas con actividades Garmin reales.

Algoritmo:
  1. Para cada sesión planificada sin match, buscar actividades Garmin
     en la misma fecha (±1 día de tolerancia para workouts nocturnos/madrugada)
  2. Filtrar por deporte compatible
  3. Si hay múltiples candidatos, tomar el de TSS más cercano al planificado
  4. Calcular compliance_pct = tss_actual / tss_planned × 100
  5. Marcar la sesión como completada

Mapping de deportes Garmin → deportes del plan:
  swimming/open_water_swimming → swim
  cycling/virtual_ride → bike
  running/trail_running → run
  strength_training/fitness_equipment → strength
  triathlon → brick
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import GarminActivity, PlanSession, TrainingPlan

logger = logging.getLogger("labx.plan_matching")

# Tolerancia: un día antes o después para workouts de madrugada / fin de semana largo
DATE_TOLERANCE_DAYS = 1

SPORT_MAP: dict[str, str] = {
    # Natación
    "swimming":              "swim",
    "open_water_swimming":   "swim",
    "pool_swimming":         "swim",
    # Ciclismo
    "cycling":               "bike",
    "road_cycling":          "bike",
    "virtual_ride":          "bike",
    "indoor_cycling":        "bike",
    "mountain_biking":       "bike",
    # Running
    "running":               "run",
    "trail_running":         "run",
    "treadmill_running":     "run",
    "indoor_running":        "run",
    "track_running":         "run",
    # Fuerza
    "strength_training":     "strength",
    "fitness_equipment":     "strength",
    "gym":                   "strength",
    # Brick / Triatlón
    "triathlon":             "brick",
    "multisport":            "brick",
    "duathlon":              "brick",
    # Otros
    "yoga":                  "other",
    "hiking":                "other",
    "walking":               "other",
}


def _garmin_sport_to_plan_sport(garmin_sport: Optional[str]) -> str:
    if not garmin_sport:
        return "other"
    return SPORT_MAP.get(garmin_sport.lower().replace(" ", "_"), "other")


def _is_sport_compatible(plan_sport: str, garmin_sport: str) -> bool:
    """Verifica si el deporte Garmin es compatible con el deporte del plan."""
    mapped = _garmin_sport_to_plan_sport(garmin_sport)
    if plan_sport == "brick":
        return mapped in ("brick", "bike", "run")
    if plan_sport == "other":
        return True
    return mapped == plan_sport


def match_sessions_for_user(
    user_id: str,
    db:      Session,
    days_back: int = 7,
) -> dict:
    """
    Intenta hacer match de sesiones planificadas sin asignar
    con actividades Garmin reales para el usuario dado.

    Retorna un dict con estadísticas del proceso de matching.
    """
    today      = date.today()
    cutoff     = (today - timedelta(days=days_back)).isoformat()

    # Sesiones sin match, no saltadas, en el periodo
    unmatched = (
        db.query(PlanSession)
        .join(TrainingPlan)
        .filter(
            PlanSession.athlete_id        == user_id,
            PlanSession.garmin_activity_id.is_(None),
            PlanSession.is_skipped        == False,
            PlanSession.date_iso          >= cutoff,
            PlanSession.date_iso          <= today.isoformat(),
            PlanSession.sport             != "rest",
        )
        .order_by(PlanSession.date_iso)
        .all()
    )

    matched_count  = 0
    skipped_count  = 0
    no_match_count = 0

    # Actividades Garmin ya usadas en este run (evitar doble-asignación)
    used_activity_ids: set[str] = set()

    for session in unmatched:
        sess_date = date.fromisoformat(session.date_iso)

        # Ventana de búsqueda ±DATE_TOLERANCE_DAYS
        date_lo = (sess_date - timedelta(days=DATE_TOLERANCE_DAYS)).isoformat()
        date_hi = (sess_date + timedelta(days=DATE_TOLERANCE_DAYS)).isoformat()

        candidates = (
            db.query(GarminActivity)
            .filter(
                GarminActivity.user_id  == user_id,
                GarminActivity.date_iso >= date_lo,
                GarminActivity.date_iso <= date_hi,
                ~GarminActivity.id.in_(used_activity_ids),
            )
            .all()
        )

        compatible = [
            a for a in candidates
            if _is_sport_compatible(session.sport, a.sport or "")
        ]

        if not compatible:
            no_match_count += 1
            # Si no hay actividad y la fecha ya pasó por más de un día → marcar skipped
            if sess_date < today - timedelta(days=1):
                session.is_skipped  = True
                session.skip_reason = "auto: sin actividad registrada"
                skipped_count += 1
            continue

        # Seleccionar la actividad con TSS más cercano al planificado
        tss_planned = session.tss_planned or 50.0
        best = min(
            compatible,
            key=lambda a: abs((a.training_stress_score or 0) - tss_planned),
        )

        tss_actual    = best.training_stress_score or 0
        dur_actual    = best.moving_time_seconds   // 60 if best.moving_time_seconds else None
        dist_actual   = round(best.distance_meters / 1000, 2) if best.distance_meters else None
        compliance    = round(tss_actual / tss_planned * 100, 1) if tss_planned > 0 else None

        session.garmin_activity_id  = best.id
        session.tss_actual          = tss_actual
        session.duration_actual_min = dur_actual
        session.distance_actual_km  = dist_actual
        session.compliance_pct      = compliance
        session.completed_at        = best.started_at

        used_activity_ids.add(best.id)
        matched_count += 1

        logger.info(
            "Match: session=%s (%s %s) → activity=%s tss=%.0f compliance=%.0f%%",
            session.id, session.sport, session.date_iso,
            best.id, tss_actual, compliance or 0,
        )

    if matched_count or skipped_count:
        db.commit()

    return {
        "user_id":     user_id,
        "matched":     matched_count,
        "auto_skipped":skipped_count,
        "no_match":    no_match_count,
        "total_checked":len(unmatched),
    }


def match_sessions_all_users(db: Session, days_back: int = 7) -> list[dict]:
    """
    Ejecuta match para todos los usuarios con planes activos.
    Llamado por el scheduler tras la sincronización de Garmin.
    """
    users = (
        db.query(TrainingPlan.athlete_id)
        .filter(TrainingPlan.is_active == True)
        .distinct()
        .all()
    )
    results = []
    for (uid,) in users:
        try:
            result = match_sessions_for_user(uid, db, days_back=days_back)
            if result["matched"] or result["auto_skipped"]:
                results.append(result)
        except Exception as e:
            logger.error("Match failed for user %s: %s", uid, e)
    return results
