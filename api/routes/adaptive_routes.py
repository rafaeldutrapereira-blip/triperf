"""
LabX Plan Adaptativo de Entrenamiento v1.0 — Sprint 16
========================================================
Motor adaptativo que combina Recovery Score + TSB + compliance + race countdown
para ajustar automáticamente la carga e intensidad del plan semanal.

Principio: "Show me why, not just what" — cada ajuste tiene razón textual.
No modifica las sesiones base; genera una capa de ajuste encima.

Endpoints:
  GET  /adaptive/dashboard                — Vista maestra del módulo
  GET  /adaptive/week                     — Plan semanal adaptado (7 días)
  GET  /adaptive/signal/{date_iso}        — Señal de adaptación para un día
  POST /adaptive/accept/{date_iso}        — Atleta acepta adaptación
  POST /adaptive/reject/{date_iso}        — Atleta rechaza adaptación
  POST /adaptive/recalculate/{date_iso}   — Forzar recálculo
  GET  /adaptive/compliance               — Historial de compliance (4/8/12 semanas)
  GET  /adaptive/phase                    — Fase actual + countdown a carrera
  GET  /adaptive/taper-protocol           — Protocolo tapering personalizado
  GET  /adaptive/form-windows             — Ventanas de forma óptima (30d)
  GET  /adaptive/history                  — Historial de adaptaciones
  GET  /adaptive/coach-queue              — Coach: adaptaciones pendientes de aprobación
  POST /adaptive/coach-approve/{adap_id} — Coach aprueba adaptación
  POST /adaptive/coach-reject/{adap_id}  — Coach rechaza con nota
  GET  /adaptive/projections              — Proyección CTL a la carrera objetivo
"""
from __future__ import annotations

import json
import logging
import math
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models import (
    User, GarminHealthDaily, GarminTrainingLoad, GarminActivity,
    RecoveryScore, RaceEvent, CoachAthlete,
    PlanAdaptation, WeeklyPlanSnapshot,
)

logger = logging.getLogger("labx.adaptive")
router = APIRouter(prefix="/adaptive", tags=["adaptive"])

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES FISIOLÓGICAS
# ─────────────────────────────────────────────────────────────────────────────

# TSS semanal objetivo por distancia de carrera y fase
RACE_WEEKLY_TSS = {
    "sprint": {"base": 180, "build": 250, "peak": 300, "taper": 150, "recovery": 70},
    "olympic":{"base": 260, "build": 360, "peak": 420, "taper": 200, "recovery": 110},
    "703":    {"base": 360, "build": 500, "peak": 580, "taper": 280, "recovery": 150},
    "full":   {"base": 500, "build": 680, "peak": 800, "taper": 380, "recovery": 190},
    "21k":    {"base": 220, "build": 310, "peak": 360, "taper": 175, "recovery": 90},
    "42k":    {"base": 340, "build": 460, "peak": 540, "taper": 260, "recovery": 140},
    "custom": {"base": 250, "build": 340, "peak": 400, "taper": 200, "recovery": 100},
}

# Distribución intensidad por fase (% de sesiones en cada zona)
PHASE_INTENSITY = {
    "base":     {"easy": 70, "moderate": 22, "hard": 8},
    "build":    {"easy": 60, "moderate": 25, "hard": 15},
    "peak":     {"easy": 55, "moderate": 25, "hard": 20},
    "taper":    {"easy": 72, "moderate": 20, "hard": 8},
    "recovery": {"easy": 92, "moderate": 8,  "hard": 0},
}

# Duración típica de fases por distancia de carrera (en semanas)
PHASE_DURATION = {
    "sprint": {"base": 4, "build": 3, "peak": 2, "taper": 1, "recovery": 1},
    "olympic":{"base": 5, "build": 4, "peak": 3, "taper": 2, "recovery": 1},
    "703":    {"base": 6, "build": 5, "peak": 3, "taper": 2, "recovery": 1},
    "full":   {"base": 8, "build": 6, "peak": 4, "taper": 3, "recovery": 2},
    "21k":    {"base": 4, "build": 4, "peak": 2, "taper": 1, "recovery": 1},
    "42k":    {"base": 6, "build": 5, "peak": 3, "taper": 2, "recovery": 1},
    "custom": {"base": 5, "build": 4, "peak": 3, "taper": 2, "recovery": 1},
}

# Colors UI por señal
SIGNAL_COLOR = {
    "increase": "#A855F7",  # purple — ventana óptima
    "maintain": "#10B981",  # green
    "decrease": "#F59E0B",  # amber
    "taper":    "#22D3EE",  # cyan
    "rest":     "#EF4444",  # red
}

SIGNAL_LABEL = {
    "increase": "🟣 Ventana de forma — aumentar carga",
    "maintain": "🟢 Carga normal según plan",
    "decrease": "🟡 Reducir intensidad",
    "taper":    "🩵 Tapering activo",
    "rest":     "🔴 Descanso recomendado",
}

INTENSITY_LABEL = {
    "easy":     "🟢 Fácil / Z1-Z2",
    "moderate": "🟡 Moderado / Z3",
    "hard":     "🟠 Intenso / Z4-Z5",
    "race":     "🔴 Ritmo carrera",
    "rest":     "⚪ Descanso",
}


# ─────────────────────────────────────────────────────────────────────────────
# MOTOR ADAPTATIVO — núcleo del módulo
# ─────────────────────────────────────────────────────────────────────────────

def _intensity_factor(recovery_score: Optional[int]) -> float:
    """
    Convierte Recovery Score en factor de intensidad.
    ≥85: ventana de oportunidad (+10%)
    70-84: nominal
    55-69: reducción leve (-15%)
    40-54: reducción moderada (-30%)
    <40: descanso (-50%)
    """
    if recovery_score is None:
        return 1.0  # sin datos → nominal
    if recovery_score >= 85: return 1.10
    if recovery_score >= 70: return 1.00
    if recovery_score >= 55: return 0.85
    if recovery_score >= 40: return 0.70
    return 0.50


def _taper_factor(days_to_race: Optional[int]) -> float:
    """
    Reduce carga progresivamente en las últimas 2-3 semanas.
    >21 días: sin tapering (1.0)
    15-21 días: reducción leve (0.85)
    10-14 días: reducción moderada (0.70)
    7-9 días: tapering real (0.55)
    4-6 días: carga mínima (0.40)
    1-3 días: pre-race (0.25)
    0: race day (0.15)
    """
    if days_to_race is None or days_to_race > 21:
        return 1.0
    if days_to_race >= 15: return 0.85
    if days_to_race >= 10: return 0.70
    if days_to_race >= 7:  return 0.55
    if days_to_race >= 4:  return 0.40
    if days_to_race >= 1:  return 0.25
    return 0.15  # race day


def _compliance_factor(compliance_7d: Optional[float]) -> float:
    """
    Ajusta carga futura basado en cumplimiento reciente.
    >105%: reducir ligeramente (sobreentrenamiento)
    90-105%: nominal
    75-89%: reducción leve (atleta rindiendo bien pero irregular)
    60-74%: reducción moderada (está costando completar)
    <60%: reducción significativa
    """
    if compliance_7d is None:
        return 1.0
    c = compliance_7d
    if c > 1.05:  return 0.95  # estaba haciendo demasiado
    if c >= 0.90: return 1.00
    if c >= 0.75: return 0.95
    if c >= 0.60: return 0.85
    return 0.75


def _combined_factor(intensity_f: float, taper_f: float, compliance_f: float) -> float:
    """
    Combina los tres factores con pesos.
    Taper es dominante cuando activo — no se puede anular con buena recovery.
    """
    if taper_f < 0.90:
        # Tapering activo: taper domina (60%), recovery (25%), compliance (15%)
        combined = taper_f * 0.60 + intensity_f * 0.25 + compliance_f * 0.15
    else:
        # Sin tapering: recovery domina (55%), compliance (30%), taper irrelevante (15%)
        combined = intensity_f * 0.55 + compliance_f * 0.30 + taper_f * 0.15
    return round(min(1.15, max(0.15, combined)), 3)


def _signal(
    recovery_score: Optional[int],
    combined_f: float,
    days_to_race: Optional[int],
) -> str:
    """Determina la señal de adaptación del día."""
    if days_to_race is not None and days_to_race <= 21:
        return "taper"
    # Recovery crítico (<40) → siempre descanso, sin importar compliance
    if recovery_score is not None and recovery_score < 40:
        return "rest"
    if combined_f >= 1.05:
        return "increase"
    if combined_f >= 0.93:
        return "maintain"
    if combined_f >= 0.60:
        return "decrease"
    return "rest"


def _adjust_intensity_label(original: str, factor: float) -> str:
    """Ajusta la etiqueta de intensidad según el factor."""
    order = ["rest", "easy", "moderate", "hard", "race"]
    if original not in order:
        return original
    idx = order.index(original)
    if factor >= 1.08 and idx < len(order) - 1:
        return order[min(idx + 1, len(order) - 1)]
    if factor <= 0.70 and idx > 0:
        return order[max(idx - 1, 0)]
    if factor <= 0.52:
        return "rest"
    return original


def _build_reason_text(
    recovery_score: Optional[int],
    tsb: Optional[float],
    compliance_7d: Optional[float],
    days_to_race: Optional[int],
    signal: str,
    factor: float,
) -> str:
    parts = []

    if days_to_race is not None and days_to_race <= 21:
        parts.append(f"🏁 Tapering activo — {days_to_race} días para tu carrera objetivo.")
        if days_to_race <= 7:
            parts.append("Prioridad: llegar descansado. Mantén la cadencia, reduce el volumen.")
        return " ".join(parts)

    if recovery_score is not None:
        if recovery_score >= 85:
            parts.append(f"💜 Recovery Score {recovery_score} — condiciones óptimas, ventana de carga.")
        elif recovery_score >= 70:
            parts.append(f"🟢 Recovery Score {recovery_score} — buenas condiciones para entrenar.")
        elif recovery_score >= 55:
            parts.append(f"🟡 Recovery Score {recovery_score} — recuperación moderada, intensidad reducida.")
        elif recovery_score >= 40:
            parts.append(f"🟠 Recovery Score {recovery_score} — fatiga acumulada, sesión suave o descanso activo.")
        else:
            parts.append(f"🔴 Recovery Score {recovery_score} — recuperación insuficiente. Descansa hoy.")

    if tsb is not None:
        if tsb > 10:
            parts.append(f"Forma: TSB +{int(tsb)} — fresco y con energía acumulada.")
        elif tsb < -25:
            parts.append(f"Fatiga: TSB {int(tsb)} — carga acumulada alta, no añadir estrés.")

    if compliance_7d is not None:
        pct = int(compliance_7d * 100)
        if compliance_7d < 0.75:
            parts.append(f"Cumplimiento 7d: {pct}% — sesiones incompletas recientes, reduciendo carga futura.")
        elif compliance_7d > 1.05:
            parts.append(f"Cumplimiento 7d: {pct}% — estás haciendo más de lo planificado, modera.")

    if not parts:
        parts.append("Plan nominal sin ajustes significativos.")

    return " ".join(parts)


def _current_phase(
    race_date_iso: Optional[str],
    race_distance: str,
    today_iso: Optional[str] = None,
) -> tuple[str, int, int]:
    """
    Calcula fase actual, semanas en la fase, semana de fase.
    Retorna (phase, days_to_race, phase_week).
    """
    today = date.fromisoformat(today_iso) if today_iso else date.today()

    if not race_date_iso:
        return "base", 9999, 1

    race_d       = date.fromisoformat(race_date_iso)
    days_to_race = (race_d - today).days

    if days_to_race < 0:
        return "recovery", 0, 1

    dist_key = race_distance if race_distance in PHASE_DURATION else "custom"
    durations = PHASE_DURATION[dist_key]

    taper_weeks    = durations["taper"]
    peak_weeks     = durations["peak"]
    build_weeks    = durations["build"]

    taper_days = taper_weeks * 7
    peak_days  = (taper_weeks + peak_weeks) * 7
    build_days = (taper_weeks + peak_weeks + build_weeks) * 7

    if days_to_race <= taper_days:
        phase      = "taper"
        week_in    = taper_weeks - max(1, math.ceil(days_to_race / 7)) + 1
    elif days_to_race <= peak_days:
        phase      = "peak"
        week_in    = peak_weeks - max(1, math.ceil((days_to_race - taper_days) / 7)) + 1
    elif days_to_race <= build_days:
        phase      = "build"
        week_in    = build_weeks - max(1, math.ceil((days_to_race - peak_days) / 7)) + 1
    else:
        phase      = "base"
        week_in    = max(1, math.ceil((days_to_race - build_days) / 7))

    return phase, days_to_race, max(1, week_in)


def _compliance_7d(user_id: str, db: Session) -> Optional[float]:
    """Ratio sesiones completadas vs planificadas (TSS real/TSS plan) últimos 7 días."""
    cutoff = (date.today() - timedelta(days=7)).isoformat()
    tl_rows = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == user_id,
        GarminTrainingLoad.date_iso >= cutoff,
    ).all()

    planned_total = sum((r.tss_planned or 0) for r in tl_rows)
    actual_total  = sum((r.tss_day or 0)     for r in tl_rows)

    if planned_total < 5:
        return None  # Sin datos de plan suficientes
    return round(actual_total / planned_total, 3)


def _next_race(user_id: str, db: Session) -> Optional[RaceEvent]:
    """Próxima carrera objetivo (is_goal_race=True) en el futuro."""
    today = date.today().isoformat()
    return db.query(RaceEvent).filter(
        RaceEvent.user_id      == user_id,
        RaceEvent.is_goal_race == True,
        RaceEvent.date_iso     >= today,
    ).order_by(asc(RaceEvent.date_iso)).first()


def _get_or_compute_adaptation(
    user_id:  str,
    date_iso: str,
    db:       Session,
    force:    bool = False,
) -> dict:
    """
    Recupera la adaptación del cache o la calcula.
    Cache válido 12h; force=True siempre recalcula.
    """
    if not force:
        cached = db.query(PlanAdaptation).filter(
            PlanAdaptation.user_id  == user_id,
            PlanAdaptation.date_iso == date_iso,
        ).first()
        if cached and cached.calculated_at:
            age_h = (datetime.now(timezone.utc).replace(tzinfo=None) - cached.calculated_at).total_seconds() / 3600
            if age_h < 12:
                return _adaptation_to_dict(cached)

    # Recolectar inputs
    rec_score_row = db.query(RecoveryScore).filter(
        RecoveryScore.user_id  == user_id,
        RecoveryScore.date_iso == date_iso,
    ).first()
    recovery_score = rec_score_row.score if rec_score_row else None

    tl_row = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == user_id,
        GarminTrainingLoad.date_iso == date_iso,
    ).first()
    tsb         = tl_row.tsb     if tl_row else None
    planned_tss = tl_row.tss_planned if tl_row else None
    actual_tss  = tl_row.tss_day    if tl_row else None

    race        = _next_race(user_id, db)
    compliance  = _compliance_7d(user_id, db)

    phase, days_to_race, phase_week = _current_phase(
        race.date_iso    if race else None,
        race.distance or "custom" if race else "custom",
    )

    # Calcular factores
    if_factor  = _intensity_factor(recovery_score)
    tf_factor  = _taper_factor(days_to_race)
    cf_factor  = _compliance_factor(compliance)
    combined   = _combined_factor(if_factor, tf_factor, cf_factor)
    sig        = _signal(recovery_score, combined, days_to_race if race else None)

    # Ajuste de TSS
    orig_tss     = planned_tss or 0
    adjusted_tss = round(orig_tss * combined, 1)

    # Ajuste de intensidad
    orig_intensity = "moderate"  # default cuando no hay tipo definido
    adj_intensity  = _adjust_intensity_label(orig_intensity, combined)

    # Trigger type
    if days_to_race is not None and days_to_race <= 21:
        trigger = "taper"
    elif recovery_score is not None and recovery_score < 50:
        trigger = "recovery_low"
    elif recovery_score is not None and recovery_score >= 85:
        trigger = "recovery_high"
    elif compliance is not None and compliance < 0.75:
        trigger = "compliance_low"
    else:
        trigger = "nominal"

    reason = _build_reason_text(recovery_score, tsb, compliance, days_to_race, sig, combined)

    # Persistir
    existing = db.query(PlanAdaptation).filter(
        PlanAdaptation.user_id  == user_id,
        PlanAdaptation.date_iso == date_iso,
    ).first()

    fields = dict(
        recovery_score        = recovery_score,
        tsb                   = tsb,
        compliance_7d         = compliance,
        days_to_race          = days_to_race if race else None,
        intensity_factor      = if_factor,
        taper_factor          = tf_factor,
        compliance_factor     = cf_factor,
        combined_factor       = combined,
        original_tss          = orig_tss,
        adjusted_tss          = adjusted_tss,
        original_intensity    = orig_intensity,
        adjusted_intensity    = adj_intensity,
        signal                = sig,
        trigger_type          = trigger,
        reason_text           = reason,
        phase                 = phase,
        calculated_at         = datetime.now(timezone.utc).replace(tzinfo=None),
    )

    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
        row = existing
    else:
        row = PlanAdaptation(user_id=user_id, date_iso=date_iso, **fields)
        db.add(row)
    db.commit()
    db.refresh(row)
    return _adaptation_to_dict(row)


def _adaptation_to_dict(a: PlanAdaptation) -> dict:
    return {
        "id":                 a.id,
        "date_iso":           a.date_iso,
        "recovery_score":     a.recovery_score,
        "tsb":                a.tsb,
        "compliance_7d":      a.compliance_7d,
        "days_to_race":       a.days_to_race,
        "intensity_factor":   a.intensity_factor,
        "taper_factor":       a.taper_factor,
        "compliance_factor":  a.compliance_factor,
        "combined_factor":    a.combined_factor,
        "original_tss":       a.original_tss,
        "adjusted_tss":       a.adjusted_tss,
        "original_intensity": a.original_intensity,
        "adjusted_intensity": a.adjusted_intensity,
        "signal":             a.signal,
        "signal_color":       SIGNAL_COLOR.get(a.signal or "maintain"),
        "signal_label":       SIGNAL_LABEL.get(a.signal or "maintain"),
        "trigger_type":       a.trigger_type,
        "reason_text":        a.reason_text,
        "phase":              a.phase,
        "auto_applied":       a.auto_applied,
        "accepted":           a.accepted,
        "coach_note":         a.coach_note,
        "calculated_at":      a.calculated_at.isoformat() if a.calculated_at else None,
    }


def _today() -> str:
    return date.today().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def adaptive_dashboard(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Vista maestra del módulo adaptativo.
    1 llamada para cargar toda la página.
    """
    today_iso  = _today()
    today_d    = date.today()

    # Adaptación de hoy
    today_adap = _get_or_compute_adaptation(me.id, today_iso, db)

    # Próxima carrera
    race = _next_race(me.id, db)
    phase, days_to_race, phase_week = _current_phase(
        race.date_iso    if race else None,
        race.distance or "custom" if race else "custom",
    )

    # Semana actual (Lun → Dom)
    mon = today_d - timedelta(days=today_d.weekday())
    week_days = [(mon + timedelta(days=i)).isoformat() for i in range(7)]
    week_adaptations = []
    for d_iso in week_days:
        adap = _get_or_compute_adaptation(me.id, d_iso, db)
        week_adaptations.append(adap)

    tss_planned  = sum(a.get("original_tss", 0) or 0 for a in week_adaptations)
    tss_adjusted = sum(a.get("adjusted_tss", 0) or 0 for a in week_adaptations)

    # Compliance últimas 4 semanas
    compliance_history = _build_compliance_history(me.id, db, weeks=4)

    # CTL actual
    tl_today = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso == today_iso,
    ).first()

    # Ventanas de forma próximas 7 días
    form_windows = _detect_form_windows(me.id, db, days=14)

    return {
        "today_iso":            today_iso,
        "today_adaptation":     today_adap,

        "phase": {
            "current":          phase,
            "week":             phase_week,
            "total_weeks":      PHASE_DURATION.get(race.distance if race else "custom", {}).get(phase, 4) if race else 4,
            "days_to_race":     days_to_race if race else None,
            "race_name":        race.name    if race else None,
            "race_date":        race.date_iso if race else None,
            "race_distance":    race.distance if race else None,
        },

        "week": {
            "week_start":   mon.isoformat(),
            "adaptations":  week_adaptations,
            "tss_planned":  round(tss_planned, 1),
            "tss_adjusted": round(tss_adjusted, 1),
            "tss_delta_pct": round((tss_adjusted - tss_planned) / max(tss_planned, 1) * 100, 1),
        },

        "training_load": {
            "ctl":  tl_today.ctl  if tl_today else None,
            "atl":  tl_today.atl  if tl_today else None,
            "tsb":  tl_today.tsb  if tl_today else None,
        },

        "compliance_history":   compliance_history,
        "form_windows":         form_windows,
    }


@router.get("/week")
def adaptive_week(
    week_start: Optional[str] = Query(None, description="YYYY-MM-DD (Lunes de la semana)"),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Plan semanal adaptado completo (7 días)."""
    if week_start:
        mon = date.fromisoformat(week_start)
    else:
        today = date.today()
        mon   = today - timedelta(days=today.weekday())

    days = [(mon + timedelta(days=i)).isoformat() for i in range(7)]
    adaptations = [_get_or_compute_adaptation(me.id, d, db) for d in days]

    # TSS totales
    tss_planned  = sum(a.get("original_tss", 0) or 0 for a in adaptations)
    tss_adjusted = sum(a.get("adjusted_tss", 0) or 0 for a in adaptations)

    # TSS real de la semana (actividades Garmin ya completadas)
    actual_rows = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso.in_(days),
    ).all()
    tss_actual = sum((r.tss_day or 0) for r in actual_rows)

    # Snapshot de la semana
    _upsert_week_snapshot(me.id, mon.isoformat(), adaptations, tss_actual, db)

    return {
        "week_start":    mon.isoformat(),
        "week_end":      (mon + timedelta(days=6)).isoformat(),
        "adaptations":   adaptations,
        "tss_planned":   round(tss_planned, 1),
        "tss_adjusted":  round(tss_adjusted, 1),
        "tss_actual":    round(tss_actual, 1),
        "compliance_pct": round(tss_actual / max(tss_adjusted, 1) * 100, 1),
    }


@router.get("/signal/{date_iso}")
def get_signal(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Señal de adaptación para un día específico."""
    return _get_or_compute_adaptation(me.id, date_iso, db)


@router.post("/accept/{date_iso}", status_code=200)
def accept_adaptation(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Atleta acepta la adaptación propuesta para un día."""
    row = db.query(PlanAdaptation).filter(
        PlanAdaptation.user_id  == me.id,
        PlanAdaptation.date_iso == date_iso,
    ).first()
    if not row:
        raise HTTPException(404, f"Sin adaptación para {date_iso}")
    row.accepted    = True
    row.accepted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    return {"ok": True, "date_iso": date_iso, "accepted": True}


@router.post("/reject/{date_iso}", status_code=200)
def reject_adaptation(
    date_iso: str,
    note: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Atleta rechaza la adaptación (quiere hacer el plan original)."""
    row = db.query(PlanAdaptation).filter(
        PlanAdaptation.user_id  == me.id,
        PlanAdaptation.date_iso == date_iso,
    ).first()
    if not row:
        raise HTTPException(404, f"Sin adaptación para {date_iso}")
    row.accepted    = False
    row.accepted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if note:
        row.coach_note = note[:200]
    db.commit()
    return {"ok": True, "date_iso": date_iso, "accepted": False}


@router.post("/recalculate/{date_iso}")
def recalculate_adaptation(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Fuerza recálculo de la adaptación del día."""
    return _get_or_compute_adaptation(me.id, date_iso, db, force=True)


# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE
# ─────────────────────────────────────────────────────────────────────────────

def _build_compliance_history(user_id: str, db: Session, weeks: int = 8) -> list:
    today   = date.today()
    mon     = today - timedelta(days=today.weekday())
    history = []
    for i in range(weeks):
        w_start = mon - timedelta(weeks=i)
        w_days  = [(w_start + timedelta(days=j)).isoformat() for j in range(7)]
        tl_rows = db.query(GarminTrainingLoad).filter(
            GarminTrainingLoad.user_id  == user_id,
            GarminTrainingLoad.date_iso.in_(w_days),
        ).all()
        planned = sum((r.tss_planned or 0) for r in tl_rows)
        actual  = sum((r.tss_day     or 0) for r in tl_rows)
        pct     = round(actual / max(planned, 1) * 100, 1) if planned > 0 else None
        history.append({
            "week_start":    w_start.isoformat(),
            "tss_planned":   round(planned, 1),
            "tss_actual":    round(actual, 1),
            "compliance_pct":pct,
        })
    return list(reversed(history))


@router.get("/compliance")
def get_compliance(
    weeks: int = Query(8, ge=2, le=24),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Historial de compliance semanal."""
    history = _build_compliance_history(me.id, db, weeks)
    valid   = [h["compliance_pct"] for h in history if h["compliance_pct"] is not None]
    return {
        "weeks":   weeks,
        "history": history,
        "avg_pct": round(sum(valid) / len(valid), 1) if valid else None,
        "trend":   "improving" if len(valid) >= 2 and valid[-1] > valid[0] else "declining" if len(valid) >= 2 and valid[-1] < valid[0] else "stable",
    }


# ─────────────────────────────────────────────────────────────────────────────
# FASE + CARRERA OBJETIVO
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/phase")
def get_phase(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Fase actual de entrenamiento y countdown a carrera objetivo."""
    race = _next_race(me.id, db)
    dist = (race.distance or "custom") if race else "custom"
    phase, days_to_race, phase_week = _current_phase(
        race.date_iso if race else None, dist
    )

    weekly_tss_target = RACE_WEEKLY_TSS.get(dist, RACE_WEEKLY_TSS["custom"]).get(phase, 300)

    # CTL objetivo en la carrera (para proyección)
    tl_today = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso == _today(),
    ).first()
    ctl_current = tl_today.ctl if tl_today else None

    # Estimación CTL en carrera: CTL crece ~1-1.5 pts/semana en build
    ctl_projected_race = None
    if ctl_current and days_to_race:
        weeks_left = days_to_race / 7
        # Build fases aumentan; taper las baja ligeramente
        growth_factor = 1.0 if phase in ("taper","recovery") else 1.0 + (weeks_left * 0.015)
        ctl_projected_race = round(ctl_current * min(growth_factor, 1.4), 1)

    return {
        "phase":              phase,
        "phase_label": {
            "base":     "🔵 BASE — Construyendo aeróbico",
            "build":    "🟡 BUILD — Aumentando intensidad",
            "peak":     "🔴 PEAK — Máxima forma",
            "taper":    "🩵 TAPER — Descansando para la carrera",
            "recovery": "🟢 RECOVERY — Post-carrera",
        }.get(phase, phase),
        "phase_week":          phase_week,
        "phase_total_weeks":   PHASE_DURATION.get(dist, {}).get(phase, 4),
        "weekly_tss_target":   weekly_tss_target,
        "intensity_distribution": PHASE_INTENSITY.get(phase, {}),
        "days_to_race":        days_to_race,
        "race_name":           race.name     if race else None,
        "race_date":           race.date_iso if race else None,
        "race_distance":       dist          if race else None,
        "ctl_current":         ctl_current,
        "ctl_projected_race":  ctl_projected_race,
        "races_ahead": [
            {
                "name":     r.name,
                "date_iso": r.date_iso,
                "distance": r.distance,
                "priority": "A" if r.is_goal_race else "B",
            }
            for r in db.query(RaceEvent).filter(
                RaceEvent.user_id  == me.id,
                RaceEvent.date_iso >= _today(),
            ).order_by(asc(RaceEvent.date_iso)).limit(5).all()
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# TAPERING PERSONALIZADO
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/taper-protocol")
def get_taper_protocol(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Protocolo de tapering personalizado para la próxima carrera A.
    Calcula la curva de reducción de TSS para llegar con TSB objetivo.
    """
    race = _next_race(me.id, db)
    if not race:
        raise HTTPException(404, "No tienes carrera objetivo registrada. Agrega una en tu perfil.")

    today_d    = date.today()
    race_d     = date.fromisoformat(race.date_iso)
    days_left  = (race_d - today_d).days

    tl_today   = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso == _today(),
    ).first()

    ctl_now    = tl_today.ctl if tl_today else 60
    atl_now    = tl_today.atl if tl_today else 70
    tsb_now    = tl_today.tsb if tl_today else -10

    dist       = race.distance or "custom"

    # TSB objetivo el día de carrera (varía por distancia)
    TSB_TARGETS = {"sprint": 5, "olympic": 7, "703": 10, "full": 12, "21k": 6, "42k": 10, "custom": 8}
    tsb_target = TSB_TARGETS.get(dist, 8)

    # TSS semanal actual en base a plan
    dist_key   = dist if dist in RACE_WEEKLY_TSS else "custom"
    base_weekly_tss = RACE_WEEKLY_TSS[dist_key].get("peak", 400)

    # Generar curva diaria de tapering
    taper_days = []
    for i in range(min(days_left, 21)):
        d_iso   = (today_d + timedelta(days=i)).isoformat()
        t_factor = _taper_factor(days_left - i)
        daily_tss = round(base_weekly_tss / 7 * t_factor, 1)
        taper_days.append({
            "date_iso":     d_iso,
            "days_to_race": days_left - i,
            "taper_factor": t_factor,
            "tss_target":   daily_tss,
            "label": {
                1.0:  "✅ Normal",
                0.85: "🟡 Reducción leve",
                0.70: "🟡 Reducción moderada",
                0.55: "🟠 Tapering real",
                0.40: "🟠 Carga mínima",
                0.25: "🔴 Pre-carrera",
                0.15: "🏁 Día de carrera",
            }.get(round(t_factor, 2), f"×{t_factor}"),
        })

    # Proyección TSB a la carrera (modelo simplificado CTL/ATL)
    tsb_projected = tsb_now
    for i, day in enumerate(taper_days):
        tsb_projected = tsb_projected + day["tss_target"] * 0.05  # simplificado
    tsb_projected = round(tsb_projected, 1)

    return {
        "race_name":       race.name,
        "race_date":       race.date_iso,
        "race_distance":   dist,
        "days_to_race":    days_left,
        "ctl_now":         round(ctl_now, 1)  if ctl_now else None,
        "atl_now":         round(atl_now, 1)  if atl_now else None,
        "tsb_now":         round(tsb_now, 1)  if tsb_now else None,
        "tsb_target_race": tsb_target,
        "tsb_projected":   tsb_projected,
        "on_track":        tsb_projected >= tsb_target * 0.75,
        "taper_curve":     taper_days,
        "key_rules": [
            "Mantén la frecuencia de sesiones — reduce el volumen, no las veces que entrenas.",
            "1-2 sesiones cortas de intensidad esta semana para mantener las fibras rápidas.",
            "No hagas nada nuevo (equipamiento, nutrición, estrategia) durante el taper.",
            f"Objetivo TSB el día de carrera: +{tsb_target} (actualmente {round(tsb_now,1) if tsb_now else '—'}).",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# VENTANAS DE FORMA
# ─────────────────────────────────────────────────────────────────────────────

def _detect_form_windows(user_id: str, db: Session, days: int = 14) -> list:
    """
    Detecta días con condiciones óptimas para sesiones clave:
    Recovery Score alto + TSB favorable.
    """
    cutoff = (date.today() - timedelta(days=2)).isoformat()  # incluye 2d pasados
    future = (date.today() + timedelta(days=days)).isoformat()

    rec_rows = db.query(RecoveryScore).filter(
        RecoveryScore.user_id  == user_id,
        RecoveryScore.date_iso >= cutoff,
        RecoveryScore.date_iso <= future,
    ).order_by(asc(RecoveryScore.date_iso)).all()

    tl_rows  = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == user_id,
        GarminTrainingLoad.date_iso >= cutoff,
        GarminTrainingLoad.date_iso <= future,
    ).all()

    tsb_map = {r.date_iso: r.tsb for r in tl_rows}

    windows = []
    for r in rec_rows:
        tsb = tsb_map.get(r.date_iso)
        score = r.score or 0
        is_window = score >= 78 and (tsb is None or tsb > -10)
        if is_window:
            windows.append({
                "date_iso":      r.date_iso,
                "recovery_score":score,
                "tsb":           tsb,
                "label":         "🎯 VENTANA — condiciones óptimas para sesión clave",
                "recommendation":"Aprovecha para threshold, intervalos o brick largo.",
            })

    return windows


@router.get("/form-windows")
def get_form_windows(
    days: int = Query(14, ge=7, le=30),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Ventanas de forma detectadas (próximos N días)."""
    windows = _detect_form_windows(me.id, db, days)
    return {
        "days":    days,
        "windows": windows,
        "count":   len(windows),
    }


# ─────────────────────────────────────────────────────────────────────────────
# HISTORIAL DE ADAPTACIONES
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/history")
def adaptation_history(
    days: int = Query(30, ge=7, le=90),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Historial de adaptaciones: qué cambió y por qué."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows   = db.query(PlanAdaptation).filter(
        PlanAdaptation.user_id  == me.id,
        PlanAdaptation.date_iso >= cutoff,
    ).order_by(desc(PlanAdaptation.date_iso)).all()

    adapted  = [_adaptation_to_dict(r) for r in rows if r.signal not in (None, "maintain")]
    total    = len(rows)
    n_adapted= len(adapted)
    n_accepted   = sum(1 for r in rows if r.accepted is True)
    n_rejected   = sum(1 for r in rows if r.accepted is False)

    return {
        "days":       days,
        "history":    [_adaptation_to_dict(r) for r in rows],
        "stats": {
            "total_days":    total,
            "adapted_days":  n_adapted,
            "accepted":      n_accepted,
            "rejected":      n_rejected,
            "adapt_rate_pct":round(n_adapted / max(total, 1) * 100, 1),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# PROYECCIONES CTL
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/projections")
def get_projections(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Proyección de CTL a la carrera objetivo.
    Simula el CTL futuro asumiendo compliance del plan adaptado.
    """
    race = _next_race(me.id, db)
    if not race:
        return {"error": "Sin carrera objetivo registrada.", "ctl_projection": []}

    tl_today = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso == _today(),
    ).first()

    ctl_now    = (tl_today.ctl or 50) if tl_today else 50
    today_d    = date.today()
    race_d     = date.fromisoformat(race.date_iso)
    weeks_left = max(1, (race_d - today_d).days // 7)
    dist       = race.distance or "custom"

    # Proyectar CTL semana a semana
    projection = []
    ctl         = ctl_now
    compliance  = _compliance_7d(me.id, db) or 0.85

    for w in range(weeks_left):
        d_iso    = (today_d + timedelta(weeks=w)).isoformat()
        days_rem = (race_d - (today_d + timedelta(weeks=w))).days
        phase, _, _ = _current_phase(race.date_iso, dist, d_iso)

        weekly_tss = RACE_WEEKLY_TSS.get(dist, RACE_WEEKLY_TSS["custom"]).get(phase, 300)
        actual_tss = weekly_tss * compliance

        # CTL update: exponential decay + weekly TSS
        ctl = ctl * (1 - 1/42) + actual_tss / 7  # CTL time constant = 42d
        ctl = round(ctl, 1)

        projection.append({
            "week_start":    d_iso,
            "phase":         phase,
            "ctl_projected": ctl,
            "weekly_tss":    round(actual_tss, 1),
            "days_to_race":  days_rem,
        })

    # CTL objetivo para la carrera según distancia
    CTL_TARGETS = {"sprint":45, "olympic":60, "703":75, "full":90, "21k":55, "42k":70, "custom":60}
    ctl_target  = CTL_TARGETS.get(dist, 65)
    final_ctl   = projection[-1]["ctl_projected"] if projection else ctl_now

    return {
        "race_name":     race.name,
        "race_date":     race.date_iso,
        "weeks_left":    weeks_left,
        "ctl_now":       round(ctl_now, 1),
        "ctl_target":    ctl_target,
        "ctl_projected": final_ctl,
        "on_track":      final_ctl >= ctl_target * 0.88,
        "gap":           round(ctl_target - final_ctl, 1),
        "projection":    projection,
    }


# ─────────────────────────────────────────────────────────────────────────────
# COACH QUEUE
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/coach-queue")
def coach_queue(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Cola de adaptaciones pendientes de aprobación del coach."""
    if getattr(me, "role", None) not in ("coach", "admin"):
        raise HTTPException(403, "Solo coaches pueden acceder a la cola de aprobaciones.")

    athlete_rels = db.query(CoachAthlete).filter(
        CoachAthlete.coach_id == me.id,
        CoachAthlete.status   == "active",
    ).all()

    cutoff = (date.today() - timedelta(days=3)).isoformat()
    queue  = []
    for rel in athlete_rels:
        pending = db.query(PlanAdaptation).filter(
            PlanAdaptation.user_id     == rel.athlete_id,
            PlanAdaptation.auto_applied== False,
            PlanAdaptation.accepted    == None,
            PlanAdaptation.date_iso    >= cutoff,
        ).order_by(asc(PlanAdaptation.date_iso)).all()

        if not pending:
            continue

        athlete = db.query(User).filter(User.id == rel.athlete_id).first()
        for p in pending:
            d = _adaptation_to_dict(p)
            d["athlete_name"] = getattr(athlete, "nombre", None) or getattr(athlete, "username", rel.athlete_id)
            d["athlete_id"]   = rel.athlete_id
            queue.append(d)

    return {
        "pending_count": len(queue),
        "queue":         queue,
    }


class _CoachNoteIn(BaseModel):
    note: Optional[str] = None

    @field_validator("note")
    @classmethod
    def truncate(cls, v):
        return v[:250] if v else v


@router.post("/coach-approve/{adaptation_id}")
def coach_approve(
    adaptation_id: str,
    body: _CoachNoteIn = _CoachNoteIn(),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Coach aprueba adaptación propuesta para un atleta."""
    if getattr(me, "role", None) not in ("coach", "admin"):
        raise HTTPException(403, "Solo coaches pueden aprobar adaptaciones.")

    adap = db.query(PlanAdaptation).filter(PlanAdaptation.id == adaptation_id).first()
    if not adap:
        raise HTTPException(404, "Adaptación no encontrada.")

    # Verificar que el atleta pertenece al coach
    rel = db.query(CoachAthlete).filter(
        CoachAthlete.coach_id   == me.id,
        CoachAthlete.athlete_id == adap.user_id,
        CoachAthlete.status     == "active",
    ).first()
    if not rel:
        raise HTTPException(403, "Este atleta no pertenece a tu plantel.")

    adap.accepted    = True
    adap.accepted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if body.note:
        adap.coach_note = body.note
    db.commit()
    return {"ok": True, "adaptation_id": adaptation_id, "approved": True}


@router.post("/coach-reject/{adaptation_id}")
def coach_reject(
    adaptation_id: str,
    body: _CoachNoteIn = _CoachNoteIn(),
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Coach rechaza adaptación y puede añadir nota al atleta."""
    if getattr(me, "role", None) not in ("coach", "admin"):
        raise HTTPException(403, "Solo coaches pueden rechazar adaptaciones.")

    adap = db.query(PlanAdaptation).filter(PlanAdaptation.id == adaptation_id).first()
    if not adap:
        raise HTTPException(404, "Adaptación no encontrada.")

    rel = db.query(CoachAthlete).filter(
        CoachAthlete.coach_id   == me.id,
        CoachAthlete.athlete_id == adap.user_id,
        CoachAthlete.status     == "active",
    ).first()
    if not rel:
        raise HTTPException(403, "Este atleta no pertenece a tu plantel.")

    adap.accepted    = False
    adap.accepted_at = datetime.now(timezone.utc).replace(tzinfo=None)
    if body.note:
        adap.coach_note = body.note
    db.commit()
    return {"ok": True, "adaptation_id": adaptation_id, "approved": False}


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS INTERNOS
# ─────────────────────────────────────────────────────────────────────────────

def _upsert_week_snapshot(
    user_id:      str,
    week_start:   str,
    adaptations:  list,
    tss_actual:   float,
    db:           Session,
) -> None:
    """Actualiza el snapshot semanal con datos de compliance."""
    planned  = sum(a.get("original_tss", 0) or 0 for a in adaptations)
    adjusted = sum(a.get("adjusted_tss", 0) or 0 for a in adaptations)
    adapt_n  = sum(1 for a in adaptations if a.get("signal") not in (None, "maintain"))
    phase    = adaptations[0].get("phase") if adaptations else "base"
    comp_pct = round(tss_actual / max(adjusted, 1) * 100, 1)

    existing = db.query(WeeklyPlanSnapshot).filter(
        WeeklyPlanSnapshot.user_id       == user_id,
        WeeklyPlanSnapshot.week_start_iso== week_start,
    ).first()

    if existing:
        existing.phase               = phase
        existing.planned_tss         = planned
        existing.adjusted_tss        = adjusted
        existing.actual_tss          = tss_actual
        existing.compliance_pct      = comp_pct
        existing.adaptations_count   = adapt_n
        existing.updated_at          = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        db.add(WeeklyPlanSnapshot(
            user_id          = user_id,
            week_start_iso   = week_start,
            phase            = phase,
            planned_tss      = planned,
            adjusted_tss     = adjusted,
            actual_tss       = tss_actual,
            compliance_pct   = comp_pct,
            adaptations_count= adapt_n,
        ))
    db.commit()
