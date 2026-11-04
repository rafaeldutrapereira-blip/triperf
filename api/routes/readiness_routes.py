"""
LabX — Daily Athlete Readiness Routes (Sprint 23)
==================================================
Endpoints:
  GET /readiness/daily           — DRS del día: 4 dimensiones integradas
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..auth import get_current_user
from ..services.readiness_service import (
    compute_daily_readiness,
    tsb_to_form_score,
    get_recovery_score as _get_recovery_score,
    get_mental_score as _get_mental_score,
    get_trs as _get_trs,
    get_tsb as _get_tsb,
)

logger = logging.getLogger("labx.readiness")
router = APIRouter(prefix="/readiness", tags=["readiness"])


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
            "recovery_score": round(recovery) if recovery is not None else None,
            "mental_score":   round(mental)   if mental   is not None else None,
            "trs":            round(trs)       if trs      is not None else None,
            "tsb":            round(tsb, 1)    if tsb is not None else None,
            "form_score":     round(form_score) if form_score is not None else None,
        },
        "computed_from": report.computed_from,
        "warnings":      report.warnings,
    }
