"""
LabX — Daily Athlete Readiness Routes (Sprint 23)
==================================================
Endpoints:
  GET /readiness/daily           — DRS del día: 4 dimensiones integradas
  GET /readiness/history         — Historial DRS (default 30 días)
  GET /readiness/today-plan      — Plan de hoy ajustado al DRS
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    BloodLabExam,
    GarminTrainingLoad,
    GarminHealthDaily,
    User,
)
from ..auth import get_current_user
from ..services.readiness_service import (
    compute_daily_readiness,
    compute_readiness_history,
    tsb_to_form_score,
)

logger = logging.getLogger("labx.readiness")
router = APIRouter(prefix="/readiness", tags=["readiness"])


def _get_recovery_score(user_id: str, db: Session) -> Optional[float]:
    """Lee el RecoveryScore más reciente (últimos 3 días)."""
    cutoff = (date.today() - timedelta(days=3)).isoformat()
    try:
        from ..models import RecoveryScore
        row = (
            db.query(RecoveryScore)
            .filter(
                RecoveryScore.user_id == user_id,
                RecoveryScore.date_iso >= cutoff,
            )
            .order_by(RecoveryScore.date_iso.desc())
            .first()
        )
        return float(row.score) if row else None
    except Exception:
        # RecoveryScore puede no estar disponible si no hay datos Garmin
        return None


def _get_mental_score(user_id: str, db: Session) -> Optional[float]:
    """Lee el MentalFatigueScore más reciente (últimos 3 días)."""
    cutoff = (date.today() - timedelta(days=3)).isoformat()
    try:
        from ..models import MentalFatigueScore
        row = (
            db.query(MentalFatigueScore)
            .filter(
                MentalFatigueScore.user_id == user_id,
                MentalFatigueScore.date_iso >= cutoff,
            )
            .order_by(MentalFatigueScore.date_iso.desc())
            .first()
        )
        return float(row.score) if row else None
    except Exception:
        return None


def _get_trs(user_id: str, db: Session) -> Optional[float]:
    """Calcula TRS del último examen de blood labs (últimos 90 días)."""
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    try:
        exam = (
            db.query(BloodLabExam)
            .filter(
                BloodLabExam.user_id == user_id,
                BloodLabExam.date_iso >= cutoff,
            )
            .order_by(BloodLabExam.date_iso.desc())
            .first()
        )
        if not exam:
            return None

        values = json.loads(exam.values_json)
        sex = "M"
        user = db.query(User).filter(User.id == user_id).first()
        if user and hasattr(user, "sexo") and user.sexo == "F":
            sex = "F"
        elif user and hasattr(user, "sex") and user.sex == "F":
            sex = "F"

        from ..services.blood_labs_impact_service import compute_training_impact
        report = compute_training_impact(values=values, sex=sex)
        return float(report.trs)
    except Exception:
        return None


def _get_tsb(user_id: str, db: Session) -> Optional[float]:
    """Lee el TSB más reciente de GarminTrainingLoad."""
    try:
        load = (
            db.query(GarminTrainingLoad)
            .filter(GarminTrainingLoad.user_id == user_id)
            .order_by(GarminTrainingLoad.date.desc())
            .first()
        )
        return float(load.tsb) if load and load.tsb is not None else None
    except Exception:
        return None


@router.get("/daily")
def get_daily_readiness(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Daily Readiness Score del atleta autenticado.

    Integra 4 dimensiones fisiológicas:
    - Recovery (35%): HRV + sueño del módulo S15
    - Mental  (25%): Fatiga neurocognitiva del módulo S18
    - TRS     (20%): Blood Labs restriction score del módulo S22
    - Forma   (20%): TSB del modelo Banister (S20 AI Engine)
    """
    recovery = _get_recovery_score(me.id, db)
    mental   = _get_mental_score(me.id, db)
    trs      = _get_trs(me.id, db)
    tsb      = _get_tsb(me.id, db)

    report = compute_daily_readiness(
        recovery_score=recovery,
        mental_score=mental,
        trs=trs,
        tsb=tsb,
    )

    form_score = tsb_to_form_score(float(tsb)) if tsb is not None else None

    return {
        "date":             date.today().isoformat(),
        "drs":              report.drs,
        "drs_label":        report.drs_label,
        "drs_color":        report.drs_color,
        "drs_emoji":        report.drs_emoji,
        "recommendation":   report.recommendation,
        "training_guidance": report.training_guidance,
        "primary_limiter":  report.primary_limiter,
        "data_completeness": report.data_completeness,
        "dimensions": [
            {
                "name":       d.name,
                "score":      round(d.score) if d.score is not None else None,
                "weight_pct": int(d.weight * 100),
                "label":      d.label,
                "color":      d.color,
                "available":  d.available,
                "data_source": d.data_source,
            }
            for d in report.dimensions
        ],
        "raw_inputs": {
            "recovery_score": round(recovery) if recovery else None,
            "mental_score":   round(mental)   if mental   else None,
            "trs":            round(trs)       if trs      else None,
            "tsb":            round(tsb, 1)    if tsb is not None else None,
            "form_score":     round(form_score) if form_score is not None else None,
        },
        "computed_from": report.computed_from,
        "warnings":      report.warnings,
    }


@router.get("/history")
def get_readiness_history(
    days: int = Query(default=30, ge=7, le=90),
    db: Session  = Depends(get_db),
    me: User     = Depends(get_current_user),
):
    """
    Historial del DRS para los últimos N días.
    Útil para el chart de tendencia en athlete-app.html.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()

    # Recopilar datos por fecha de cada dimensión
    from ..models import RecoveryScore, MentalFatigueScore

    # Recovery scores
    recovery_map: dict[str, float] = {}
    try:
        rows = (
            db.query(RecoveryScore)
            .filter(RecoveryScore.user_id == me.id, RecoveryScore.date_iso >= cutoff)
            .all()
        )
        recovery_map = {r.date_iso: float(r.score) for r in rows}
    except Exception:
        pass

    # Mental scores
    mental_map: dict[str, float] = {}
    try:
        rows = (
            db.query(MentalFatigueScore)
            .filter(MentalFatigueScore.user_id == me.id, MentalFatigueScore.date_iso >= cutoff)
            .all()
        )
        mental_map = {r.date_iso: float(r.score) for r in rows}
    except Exception:
        pass

    # Training load (TSB por fecha)
    tsb_map: dict[str, float] = {}
    try:
        loads = (
            db.query(GarminTrainingLoad)
            .filter(
                GarminTrainingLoad.user_id == me.id,
                GarminTrainingLoad.date >= cutoff,
            )
            .all()
        )
        tsb_map = {str(l.date)[:10]: float(l.tsb) for l in loads if l.tsb is not None}
    except Exception:
        pass

    # TRS — mismo valor para todas las fechas desde el último examen
    trs_value = _get_trs(me.id, db)

    # Construir series día a día
    data_points = []
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        iso = d.isoformat()
        data_points.append({
            "date_iso":      iso,
            "recovery_score": recovery_map.get(iso),
            "mental_score":   mental_map.get(iso),
            "trs":            trs_value,
            "tsb":            tsb_map.get(iso),
        })

    history = compute_readiness_history(data_points)

    return {
        "days":  days,
        "count": len(history),
        "history": [
            {
                "date":           p.date_iso,
                "drs":            p.drs,
                "label":          p.label,
                "color":          p.color,
                "recovery_score": round(p.recovery_score) if p.recovery_score is not None else None,
                "mental_score":   round(p.mental_score)   if p.mental_score is not None else None,
                "trs":            round(p.trs)             if p.trs is not None else None,
                "form_score":     round(p.form_score)      if p.form_score is not None else None,
            }
            for p in history
        ],
    }


@router.get("/today-plan")
def get_today_readiness_plan(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Plan de hoy ajustado dinámicamente al DRS.
    Combina el entrenamiento planificado con las restricciones fisiológicas actuales.
    """
    recovery = _get_recovery_score(me.id, db)
    mental   = _get_mental_score(me.id, db)
    trs      = _get_trs(me.id, db)
    tsb      = _get_tsb(me.id, db)

    report = compute_daily_readiness(
        recovery_score=recovery,
        mental_score=mental,
        trs=trs,
        tsb=tsb,
    )

    # Disciplina recomendada según DRS
    sport_priority = "run"
    if report.drs < 40:
        sport_priority = "swim"  # menor impacto excéntrico
    elif report.drs < 60:
        sport_priority = "bike"

    # Duración recomendada (fracción del plan estándar según DRS)
    duration_modifier = 1.0
    if report.drs >= 85:
        duration_modifier = 1.10   # +10% — aprovechar pico de forma
    elif report.drs >= 70:
        duration_modifier = 1.00   # normal
    elif report.drs >= 55:
        duration_modifier = 0.80   # -20%
    elif report.drs >= 35:
        duration_modifier = 0.55   # -45%
    else:
        duration_modifier = 0.0    # descanso

    # Zonas habilitadas
    if report.drs >= 70:
        allowed_zones = ["Z1", "Z2", "Z3", "Z4", "Z5"]
    elif report.drs >= 55:
        allowed_zones = ["Z1", "Z2", "Z3"]
    elif report.drs >= 35:
        allowed_zones = ["Z1", "Z2"]
    else:
        allowed_zones = ["Z1"]

    return {
        "date":               date.today().isoformat(),
        "drs":                report.drs,
        "drs_label":          report.drs_label,
        "drs_color":          report.drs_color,
        "recommendation":     report.recommendation,
        "sport_priority":     sport_priority,
        "duration_modifier":  duration_modifier,
        "allowed_zones":      allowed_zones,
        "training_guidance":  report.training_guidance,
        "primary_limiter":    report.primary_limiter,
        "skip_training":      report.drs < 35,
        "dimensions_summary": [
            {"name": d.name, "score": round(d.score) if d.score is not None else None, "color": d.color}
            for d in report.dimensions
        ],
    }
