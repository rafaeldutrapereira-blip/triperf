"""
LabX Injury Risk â€” API Endpoints
==================================
GET  /injury/risk/today          â€” Snapshot de hoy para el atleta
GET  /injury/risk/history        â€” Historial 30 dÃ­as del score
GET  /injury/risk/{date}         â€” Snapshot de fecha especÃ­fica
POST /injury/risk/recalculate    â€” Fuerza recalculo (Ãºtil tras sync Garmin)
GET  /coach/injury-alerts        â€” Panel coach: todos los atletas con riesgo
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import InjuryRiskSnapshot, User
from ..auth import get_current_user, require_role
from ..services.injury_risk_service import compute_injury_risk

logger = logging.getLogger("labx.injury_risk")

router = APIRouter(tags=["injury_risk"])


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Athlete endpoints
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/injury/risk/today")
def get_risk_today(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Retorna el snapshot de riesgo de lesiÃ³n de hoy.
    Si no existe o es antiguo, lo recalcula en tiempo real.
    """
    today = date.today().isoformat()

    existing = (
        db.query(InjuryRiskSnapshot)
        .filter(
            InjuryRiskSnapshot.user_id  == me.id,
            InjuryRiskSnapshot.date_iso == today,
        )
        .first()
    )

    # Si ya calculamos hoy, devolvemos el cache
    if existing and existing.risk_score is not None:
        return _serialize(existing)

    # Calcular (y persistir) en tiempo real
    return compute_injury_risk(me.id, db, today)


@router.post("/injury/risk/recalculate")
def recalculate_risk(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Fuerza recalcular el riesgo de hoy (Ãºtil tras un sync Garmin reciente).
    Borra el snapshot existente y lo recalcula.
    """
    today = date.today().isoformat()
    existing = (
        db.query(InjuryRiskSnapshot)
        .filter(
            InjuryRiskSnapshot.user_id  == me.id,
            InjuryRiskSnapshot.date_iso == today,
        )
        .first()
    )
    if existing:
        db.delete(existing)
        db.commit()

    result = compute_injury_risk(me.id, db, today)
    logger.info("Risk recalculated user=%s score=%.1f level=%s",
                me.id, result["risk_score"], result["risk_level"])
    return result


@router.get("/injury/risk/history")
def get_risk_history(
    days:     int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Historial de riesgo de los Ãºltimos N dÃ­as.
    Ãštil para el chart de tendencia en el dashboard.
    """
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows = (
        db.query(InjuryRiskSnapshot)
        .filter(
            InjuryRiskSnapshot.user_id  == me.id,
            InjuryRiskSnapshot.date_iso >= cutoff,
        )
        .order_by(InjuryRiskSnapshot.date_iso)
        .all()
    )
    return [_serialize_compact(r) for r in rows]


@router.get("/injury/risk/{date_str}")
def get_risk_date(
    date_str: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Snapshot de riesgo para una fecha especÃ­fica."""
    try:
        date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(422, "Formato de fecha invÃ¡lido. Use YYYY-MM-DD")

    row = (
        db.query(InjuryRiskSnapshot)
        .filter(
            InjuryRiskSnapshot.user_id  == me.id,
            InjuryRiskSnapshot.date_iso == date_str,
        )
        .first()
    )
    if not row:
        # Calcular si no existe
        return compute_injury_risk(me.id, db, date_str)

    return _serialize(row)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Coach endpoint â€” panel multi-atleta
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.get("/coach/injury-alerts")
def coach_injury_alerts(
    min_level: str = Query("moderate", description="Nivel mÃ­nimo: low|moderate|high|critical"),
    group_id:  Optional[str] = Query(None),
    db:  Session = Depends(get_db),
    me:  User    = Depends(require_role("coach","admin")),
):
    """
    Panel del coach: lista todos los atletas con riesgo >= min_level,
    ordenados por score descendente.
    Usado para la vista de equipo en coach.html.
    """
    from ..models import CoachAthlete, AthleteProfile

    level_order = {"low": 0, "moderate": 1, "high": 2, "critical": 3}
    min_order   = level_order.get(min_level, 1)

    today  = date.today().isoformat()

    # Atletas del coach
    q = db.query(CoachAthlete).filter(CoachAthlete.coach_id == me.id)
    if group_id:
        q = q.filter(CoachAthlete.group_id == group_id)
    athletes = q.filter(CoachAthlete.activo == True).all()

    result = []
    for ca in athletes:
        uid = ca.athlete_id

        snap = (
            db.query(InjuryRiskSnapshot)
            .filter(
                InjuryRiskSnapshot.user_id  == uid,
                InjuryRiskSnapshot.date_iso == today,
            )
            .first()
        )

        if snap is None:
            # Calcular silenciosamente (no bloquea mucho â€” en prod usar cache)
            try:
                computed = compute_injury_risk(uid, db, today)
                risk_score = computed["risk_score"]
                risk_level = computed["risk_level"]
                risk_color = computed["risk_color"]
                alerts     = computed["alerts"]
                recs       = computed["recommendations"]
            except Exception as e:
                logger.warning("Coach injury risk error uid=%s: %s", uid, e)
                continue
        else:
            risk_score = snap.risk_score or 0
            risk_level = snap.risk_level or "low"
            risk_color = snap.risk_color or "#10B981"
            try:
                alerts = json.loads(snap.alerts_json or "[]")
                recs   = json.loads(snap.recommendations_json or "[]")
            except Exception:
                alerts, recs = [], []

        # Filtrar por nivel mÃ­nimo
        if level_order.get(risk_level, 0) < min_order:
            continue

        # Nombre del atleta
        athlete_user = db.query(User).filter(User.id == uid).first()
        name = (athlete_user.nombre or athlete_user.email) if athlete_user else uid

        result.append({
            "athlete_id":  uid,
            "name":        name,
            "risk_score":  risk_score,
            "risk_level":  risk_level,
            "risk_color":  risk_color,
            "alerts_count": len(alerts),
            "top_alert":   alerts[0]["msg"] if alerts else None,
            "top_factor":  alerts[0]["factor"] if alerts else None,
            "recommendation": recs[0] if recs else None,
        })

    # Ordenar por riesgo descendente
    result.sort(key=lambda x: x["risk_score"], reverse=True)
    return result


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Serializers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _serialize(snap: InjuryRiskSnapshot) -> dict:
    try:
        alerts = json.loads(snap.alerts_json or "[]")
    except Exception:
        alerts = []
    try:
        recs = json.loads(snap.recommendations_json or "[]")
    except Exception:
        recs = []

    return {
        "date_iso":   snap.date_iso,
        "risk_score": snap.risk_score,
        "risk_level": snap.risk_level,
        "risk_color": snap.risk_color,
        "risk_delta": snap.risk_delta,
        "factors": {
            "acwr":     {"score": snap.acwr_score,     "value": snap.acwr},
            "hrv":      {"score": snap.hrv_score,      "value": snap.hrv_last_night,
                         "avg_7d": snap.hrv_7d_avg},
            "monotony": {"score": snap.monotony_score, "value": snap.monotony,
                         "strain": snap.strain},
            "labs":     {"score": snap.labs_score},
        },
        "training":        {"ctl": snap.ctl, "atl": snap.atl, "tsb": snap.tsb},
        "alerts":          alerts,
        "recommendations": recs,
    }


def _serialize_compact(snap: InjuryRiskSnapshot) -> dict:
    return {
        "date_iso":  snap.date_iso,
        "score":     snap.risk_score,
        "level":     snap.risk_level,
        "color":     snap.risk_color,
        "delta":     snap.risk_delta,
        "acwr":      snap.acwr,
        "ctl":       snap.ctl,
        "tsb":       snap.tsb,
    }

