"""
LabX Performance Analytics Routes
====================================
Endpoints para curva de potencia crítica, VO2max, personal records y distribución.

Rutas:
  GET /analytics/power-curve              — Curva CP para ciclismo (o deporte)
  GET /analytics/vo2max                   — Histórico VO2max estimado
  GET /analytics/personal-records         — PRs por deporte y distancia
  GET /analytics/training-distribution    — Heatmap de distribución
  GET /analytics/zone-calibration         — Auto-calibración de zonas
  GET /analytics/summary                  — Todo en un solo payload

Todos los endpoints requieren JWT.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models import User
from ..services.performance_analytics_service import (
    compute_power_curve,
    compute_vo2max_history,
    compute_personal_records,
    compute_training_distribution,
    compute_zone_calibration,
    project_ctl_tsb,
    compute_ramp_rate_risk,
    compute_season_summary,
    generate_automated_insights,
)
from ..plan_features import require_feature

logger = APIRouter()
router = APIRouter(prefix="/analytics", tags=["performance_analytics"], dependencies=[Depends(require_feature("analytics"))])


def _me(db=Depends(get_db), user=Depends(get_current_user)):
    return user, db


@router.get("/power-curve")
def get_power_curve(
    sport:     str = Query("bike", description="Deporte: bike | run"),
    days_back: int = Query(365,    ge=30, le=730, description="Días de historial"),
    db:        Session = Depends(get_db),
    me:        User    = Depends(get_current_user),
):
    """
    Curva de potencia crítica (CP).
    Para ciclismo: max potencia sostenida por cada duración 1s-3h.
    Incluye modelo CP2 (CP, W') y FTP estimado.
    """
    return compute_power_curve(me.id, db, days_back=days_back, sport=sport)


@router.get("/vo2max")
def get_vo2max_history(
    days_back: int = Query(365, ge=30, le=730),
    db:        Session = Depends(get_db),
    me:        User    = Depends(get_current_user),
):
    """
    Histórico de VO2max estimado: combina lecturas Garmin + estimación
    desde pace+FC de actividades de running.
    """
    return compute_vo2max_history(me.id, db, days_back=days_back)


@router.get("/personal-records")
def get_personal_records(
    sports: str = Query("run,bike,swim", description="Deportes separados por coma"),
    db:     Session = Depends(get_db),
    me:     User    = Depends(get_current_user),
):
    """Personal Records por deporte y distancia estándar."""
    sport_list = [s.strip() for s in sports.split(",") if s.strip()]
    return compute_personal_records(me.id, db, sports=sport_list)


@router.get("/training-distribution")
def get_training_distribution(
    days_back: int = Query(365, ge=30, le=730),
    db:        Session = Depends(get_db),
    me:        User    = Depends(get_current_user),
):
    """
    Distribución del entrenamiento: por deporte, día de la semana y zona de intensidad.
    Incluye Polarization Index.
    """
    return compute_training_distribution(me.id, db, days_back=days_back)


@router.get("/zone-calibration")
def get_zone_calibration(
    days_back: int = Query(90, ge=30, le=365),
    db:        Session = Depends(get_db),
    me:        User    = Depends(get_current_user),
):
    """
    Auto-calibra FTP (ciclismo), pace umbral (running) y CSS (natación)
    desde actividades recientes de alta intensidad.
    """
    return compute_zone_calibration(me.id, db, days_back=days_back)


@router.get("/summary")
def get_analytics_summary(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Resumen completo de analytics en un solo request.
    Útil para el dashboard inicial de la página de analytics.
    """
    power     = compute_power_curve(me.id, db, days_back=365, sport="bike")
    vo2max    = compute_vo2max_history(me.id, db, days_back=365)
    records   = compute_personal_records(me.id, db)
    distrib   = compute_training_distribution(me.id, db, days_back=365)
    zones     = compute_zone_calibration(me.id, db, days_back=90)

    return {
        "power_curve":           power,
        "vo2max":                vo2max,
        "personal_records":      records,
        "training_distribution": distrib,
        "zone_calibration":      zones,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sprint 25: Forward-looking & cross-module endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/ctl-projection")
def get_ctl_projection(
    planned_tss: float = Query(default=60.0, ge=0, le=400, description="TSS diario planificado"),
    days:        int   = Query(default=28,   ge=7, le=90,  description="Días de proyección"),
    db:          Session = Depends(get_db),
    me:          User    = Depends(get_current_user),
):
    """
    Proyecta CTL, ATL y TSB para los próximos N días con carga constante.
    Identifica la ventana de forma pico (TSB máximo) — clave para planificar A-races.
    Modelo de Banister (1975): CTL tau=42, ATL tau=7.
    """
    return project_ctl_tsb(me.id, db, planned_tss=planned_tss, days=days)


@router.get("/ramp-rate")
def get_ramp_rate_risk(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    ACWR (Acute:Chronic Workload Ratio) y ramp rate de CTL.
    Indica si la carga semanal actual pone al atleta en zona de riesgo de lesión.
    Base científica: Gabbett (2016), Br J Sports Med.
    """
    return compute_ramp_rate_risk(me.id, db)


@router.get("/season-summary")
def get_season_summary(
    year: int = Query(default=0, ge=0, le=2030, description="Año (0=actual)"),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """
    Resumen anual: volumen total, CTL máximo, semanas consistentes,
    distribución por deporte, highlights. Ideal para el Year in Review.
    """
    return compute_season_summary(me.id, db, season_year=year)


@router.get("/insights")
def get_automated_insights(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Insights automáticos cruzando todos los módulos:
    Training Load + Blood Labs + Recovery + Mental + Nutrition.
    Sin LLM — reglas deterministas sobre umbrales validados.
    Diferenciador: ningún competidor cruza estas 5 dimensiones en 1 endpoint.
    """
    return generate_automated_insights(me.id, db)
