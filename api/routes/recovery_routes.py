"""
LabX Recuperación Inteligente v1.0 — Sprint 15
===============================================
Motor de recuperación que combina datos objetivos Garmin + bienestar subjetivo
+ carga de entrenamiento (CTL/ATL/TSB) en un Recovery Score accionable.

Endpoints:
  GET  /recovery/dashboard               — Score + todos los factores del día
  GET  /recovery/score/{date_iso}        — Score de un día específico
  GET  /recovery/hrv/history             — Tendencia HRV (7/14/30/90d)
  GET  /recovery/sleep/history           — Tendencia sueño
  GET  /recovery/timeline                — Vista temporal superpuesta
  POST /recovery/wellness                — Log subjetivo diario (upsert)
  GET  /recovery/wellness/{date_iso}     — Bienestar de un día
  GET  /recovery/wellness/history        — Tendencia bienestar
  GET  /recovery/recommendation          — Recomendación IA para hoy
  GET  /recovery/correlations            — HRV × rendimiento histórico
  GET  /recovery/protocol/{ptype}        — Protocolo post-carrera/enfermedad
  GET  /recovery/coach-view              — Vista coach: todos los atletas
  POST /recovery/recalculate/{date_iso}  — Forzar recálculo del score
"""
from __future__ import annotations

import json
import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import desc, asc
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import get_current_user
from ..models import (
    Group, GroupMember,
    User, GarminHealthDaily, GarminSleepSession,
    GarminTrainingLoad, GarminActivity,
    WellnessLog, RecoveryScore, PlanSession,
)
from ..plan_features import require_feature

logger = logging.getLogger("labx.recovery")
router = APIRouter(prefix="/recovery", tags=["recovery"], dependencies=[Depends(require_feature("recovery"))])

# ─────────────────────────────────────────────────────────────────────────────
# MOTOR DE RECUPERACIÓN — corazón del módulo
# ─────────────────────────────────────────────────────────────────────────────

# Pesos del score compuesto (suman 1.0)
DEFAULT_WEIGHTS = {
    "hrv":           0.30,
    "sleep":         0.25,
    "tsb":           0.20,
    "stress":        0.15,
    "body_battery":  0.10,
}

# Pesos alternativos si no hay HRV (redistribuir a sueño + tsb)
WEIGHTS_NO_HRV = {
    "hrv":           0.00,
    "sleep":         0.40,
    "tsb":           0.30,
    "stress":        0.20,
    "body_battery":  0.10,
}

LEVEL_THRESHOLDS = [
    (85, "optimal",  "#10B981", "🟢 Forma óptima",      "full"),
    (70, "good",     "#22D3EE", "🟢 Buenas condiciones", "full"),
    (55, "moderate", "#F0A500", "🟡 Recuperación moderada","moderate"),
    (40, "low",      "#F59E0B", "🟡 Carga pendiente",   "easy"),
    (0,  "critical", "#EF4444", "🔴 Recuperación insuficiente","rest"),
]


def _level(score: int) -> tuple[str, str, str, str, str]:
    for thresh, lvl, color, label, sug in LEVEL_THRESHOLDS:
        if score >= thresh:
            return lvl, color, label, sug, thresh
    return "critical", "#EF4444", "🔴 Recuperación insuficiente", "rest", 0


def _hrv_factor(health: Optional[GarminHealthDaily],
                hrv_baseline: float) -> Optional[float]:
    """
    Convierte HRV en un factor 0-100.
    Compara HRV de anoche vs baseline personal (promedio 60d).
    """
    if not health or not health.hrv_last_night:
        return None
    if not hrv_baseline or hrv_baseline <= 0:
        # Sin baseline, usar absoluto con escala Garmin típica
        hrv = health.hrv_last_night
        if hrv >= 70:   return 90.0
        if hrv >= 55:   return 75.0
        if hrv >= 40:   return 55.0
        if hrv >= 25:   return 35.0
        return 15.0

    ratio = health.hrv_last_night / hrv_baseline
    # ratio 1.0 = baseline = 70 puntos, ratio 1.2 = óptimo = 95, ratio 0.7 = crítico = 10
    factor = min(100.0, max(0.0, (ratio - 0.7) / (1.2 - 0.7) * 90.0 + 10.0))
    return round(factor, 1)


def _sleep_factor(sleep: Optional[GarminSleepSession],
                  health: Optional[GarminHealthDaily]) -> Optional[float]:
    """
    Factor de sueño 0-100 basado en:
    - Score Garmin si disponible (0-100 → usado directamente)
    - Si no: tiempo total + % deep/REM
    """
    if sleep and sleep.sleep_score is not None:
        return float(sleep.sleep_score)

    if sleep and sleep.total_min:
        total_h = sleep.total_min / 60
        # Penalizar <6h y <5h
        if total_h >= 8:    base = 90
        elif total_h >= 7:  base = 78
        elif total_h >= 6:  base = 60
        elif total_h >= 5:  base = 38
        else:               base = 18

        # Bonus por calidad (REM + Deep)
        if sleep.total_min > 0:
            quality_min = (sleep.rem_min or 0) + (sleep.deep_min or 0)
            quality_ratio = quality_min / sleep.total_min
            bonus = min(10, quality_ratio * 25)
        else:
            bonus = 0
        return round(min(100.0, base + bonus), 1)

    # Sin datos de sueño → usar resting HR como proxy (si está disponible)
    if health and health.resting_hr:
        rhr = health.resting_hr
        if rhr <= 40:   return 80.0
        if rhr <= 48:   return 65.0
        if rhr <= 55:   return 50.0
        return 35.0

    return None


def _tsb_factor(tl: Optional[GarminTrainingLoad]) -> Optional[float]:
    """
    Convierte TSB en factor de recuperación 0-100.
    TSB > +15 = forma peak = 95
    TSB -5..+15 = fresco = 80
    TSB -20..-5 = fatiga leve = 60
    TSB -35..-20 = fatiga moderada = 40
    TSB < -35 = fatiga alta = 20
    """
    if not tl or tl.tsb is None:
        return None
    tsb = tl.tsb
    if tsb > 15:    return 95.0
    if tsb >= -5:   return 80.0
    if tsb >= -20:  return 60.0
    if tsb >= -35:  return 40.0
    return max(5.0, 20.0 + (tsb + 35) * 0.8)  # degradación gradual por debajo de -35


def _stress_factor(health: Optional[GarminHealthDaily]) -> Optional[float]:
    """
    Convierte avg_stress Garmin (0-100) en factor de recuperación (invertido).
    Estrés bajo = recuperación alta.
    """
    if not health or health.avg_stress is None:
        return None
    stress = health.avg_stress
    # Invertir: 0 estrés = 100 puntos, 100 estrés = 10 puntos
    return round(max(10.0, 100.0 - stress * 0.90), 1)


def _body_battery_factor(health: Optional[GarminHealthDaily]) -> Optional[float]:
    """Body Battery end-of-day → factor directo (ya es 0-100)."""
    if not health:
        return None
    val = health.body_battery_end or health.body_battery_max
    if val is None:
        return None
    return float(val)


def _wellness_factor(wellness: Optional[WellnessLog]) -> Optional[float]:
    """Convierte logs subjetivos (1-5) en factor 0-100."""
    if not wellness:
        return None
    scores = []
    for field in ("energy", "mood", "motivation", "sleep_quality"):
        v = getattr(wellness, field, None)
        if v is not None:
            scores.append((v - 1) / 4 * 100)  # 1→0, 5→100
    # Soreness y stress están invertidos (5=sin dolor = bueno)
    for field in ("soreness", "stress"):
        v = getattr(wellness, field, None)
        if v is not None:
            scores.append((v - 1) / 4 * 100)
    return round(statistics.mean(scores), 1) if scores else None


def _compute_recovery_score(
    health:   Optional[GarminHealthDaily],
    sleep:    Optional[GarminSleepSession],
    tl:       Optional[GarminTrainingLoad],
    wellness: Optional[WellnessLog],
    hrv_baseline: float,
) -> dict:
    """
    Calcula el Recovery Score compuesto.
    Retorna dict con score, level, factores individuales, pesos usados.
    """
    hrv_f    = _hrv_factor(health, hrv_baseline)
    sleep_f  = _sleep_factor(sleep, health)
    tsb_f    = _tsb_factor(tl)
    stress_f = _stress_factor(health)
    bb_f     = _body_battery_factor(health)
    well_f   = _wellness_factor(wellness)

    factors  = {
        "hrv":           hrv_f,
        "sleep":         sleep_f,
        "tsb":           tsb_f,
        "stress":        stress_f,
        "body_battery":  bb_f,
        "wellness":      well_f,
    }

    # Si hay factor subjetivo, redistribuir peso
    weights = dict(DEFAULT_WEIGHTS)
    if well_f is not None:
        # Añadir wellness reduciendo proporcional los otros
        ww = 0.10
        for k in weights:
            weights[k] = weights[k] * (1 - ww)
        weights["wellness"] = ww
    else:
        weights["wellness"] = 0.0

    if hrv_f is None:
        weights = dict(WEIGHTS_NO_HRV)
        if well_f is not None:
            ww = 0.10
            for k in weights:
                weights[k] = weights[k] * (1 - ww)
            weights["wellness"] = ww

    # Calcular score ponderado
    total_weight = 0.0
    weighted_sum = 0.0
    available    = 0

    factor_keys = ["hrv", "sleep", "tsb", "stress", "body_battery", "wellness"]
    for k in factor_keys:
        v = factors.get(k)
        w = weights.get(k, 0)
        if v is not None and w > 0:
            weighted_sum += v * w
            total_weight  += w
            available     += 1

    if total_weight == 0:
        score = 50  # sin datos → neutral
        completeness = 0.0
    else:
        score = round(weighted_sum / total_weight)
        completeness = round(available / len(factor_keys), 2)

    lvl, color, label, suggestion, _ = _level(score)

    return {
        "score":              score,
        "level":              lvl,
        "color":              color,
        "label":              label,
        "training_suggestion":suggestion,
        "factors":            factors,
        "weights":            {k: round(v, 3) for k, v in weights.items()},
        "data_completeness":  completeness,
    }


def _get_hrv_baseline(user_id: str, db: Session) -> float:
    """Promedio de HRV últimos 60 días como baseline personal."""
    cutoff = (date.today() - timedelta(days=60)).isoformat()
    rows   = db.query(GarminHealthDaily.hrv_last_night).filter(
        GarminHealthDaily.user_id   == user_id,
        GarminHealthDaily.date_iso  >= cutoff,
        GarminHealthDaily.hrv_last_night.isnot(None),
    ).all()
    values = [r[0] for r in rows if r[0] and r[0] > 0]
    return statistics.mean(values) if values else 0.0


def _build_recommendation(result: dict, tl: Optional[GarminTrainingLoad],
                           health: Optional[GarminHealthDaily],
                           hrv_baseline: float) -> str:
    score      = result["score"]
    suggestion = result["training_suggestion"]
    factors    = result["factors"]

    lines = []

    if score >= 85:
        lines.append("Recuperación óptima. Sistema nervioso listo para alta intensidad.")
        lines.append("Ventana ideal para trabajo de calidad: VO2max, umbrales o bloque de fuerza.")
    elif score >= 70:
        lines.append("Buenas condiciones. Puedes entrenar con intensidad normal.")
        lines.append("Monitora la respuesta — si el esfuerzo percibido supera lo esperado, modera.")
    elif score >= 55:
        lines.append("Recuperación moderada. Sesión a intensidad controlada recomendada.")
        if factors.get("tsb") is not None and factors["tsb"] < 50:
            lines.append("Carga de entrenamiento acumulada detectada (TSB bajo). No añadas intensidad extra hoy.")
        if factors.get("hrv") is not None and factors["hrv"] < 50:
            lines.append("HRV bajo baseline. El sistema nervioso no está completamente recuperado.")
    elif score >= 40:
        lines.append("Fatiga acumulada significativa. Sesión técnica suave o descanso activo.")
        lines.append("Prioriza dormir bien esta noche — un buen sueño puede revertir el score mañana.")
    else:
        lines.append("Recuperación insuficiente. El riesgo de lesión o sobreentrenamiento es alto.")
        lines.append("Descanso completo o movilidad suave. No ignores esta señal.")
        if tl and (tl.tsb or 0) < -30:
            lines.append(f"TSB en {int(tl.tsb or 0)} — bloque de fatiga severa. Considera reducir carga 3-5 días.")

    # Contexto HRV vs baseline
    if hrv_baseline > 0 and health and health.hrv_last_night:
        delta_pct = (health.hrv_last_night - hrv_baseline) / hrv_baseline * 100
        if delta_pct < -15:
            lines.append(f"HRV {int(delta_pct)}% bajo tu baseline ({int(hrv_baseline)}ms). Recuperación neuro comprometida.")
        elif delta_pct > 10:
            lines.append(f"HRV {int(delta_pct)}% sobre tu baseline. Forma potencialmente óptima.")

    return " ".join(lines)


def _get_or_compute_score(user_id: str, date_iso: str,
                          db: Session, force: bool = False) -> dict:
    """
    Recupera el score del cache o lo calcula.
    force=True siempre recalcula.
    """
    if not force:
        cached = db.query(RecoveryScore).filter(
            RecoveryScore.user_id  == user_id,
            RecoveryScore.date_iso == date_iso,
        ).first()
        if cached and cached.score is not None:
            return {
                "score":              cached.score,
                "level":              cached.level,
                "color":              cached.color,
                "label":              {
                    "optimal":  "🟢 Forma óptima",
                    "good":     "🟢 Buenas condiciones",
                    "moderate": "🟡 Recuperación moderada",
                    "low":      "🟡 Carga pendiente",
                    "critical": "🔴 Recuperación insuficiente",
                }.get(cached.level or "", cached.level),
                "training_suggestion":cached.training_suggestion,
                "recommendation":     cached.recommendation,
                "data_completeness":  cached.data_completeness,
                "factors": {
                    "hrv":          cached.hrv_factor,
                    "sleep":        cached.sleep_factor,
                    "tsb":          cached.tsb_factor,
                    "stress":       cached.stress_factor,
                    "body_battery": cached.body_battery_factor,
                    "wellness":     cached.wellness_factor,
                },
                "cached": True,
            }

    # Recolectar datos
    health   = db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id  == user_id,
        GarminHealthDaily.date_iso == date_iso,
    ).first()
    sleep    = db.query(GarminSleepSession).filter(
        GarminSleepSession.user_id  == user_id,
        GarminSleepSession.date_iso == date_iso,
    ).first()
    tl       = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == user_id,
        GarminTrainingLoad.date_iso == date_iso,
    ).first()
    wellness = db.query(WellnessLog).filter(
        WellnessLog.user_id  == user_id,
        WellnessLog.date_iso == date_iso,
    ).first()
    hrv_base = _get_hrv_baseline(user_id, db)

    result   = _compute_recovery_score(health, sleep, tl, wellness, hrv_base)
    rec_text = _build_recommendation(result, tl, health, hrv_base)
    result["recommendation"] = rec_text
    result["cached"] = False

    # Persistir en cache
    existing = db.query(RecoveryScore).filter(
        RecoveryScore.user_id  == user_id,
        RecoveryScore.date_iso == date_iso,
    ).first()
    factors = result["factors"]
    if existing:
        existing.score               = result["score"]
        existing.level               = result["level"]
        existing.color               = result["color"]
        existing.training_suggestion = result["training_suggestion"]
        existing.recommendation      = rec_text
        existing.data_completeness   = result["data_completeness"]
        existing.hrv_factor          = factors.get("hrv")
        existing.sleep_factor        = factors.get("sleep")
        existing.tsb_factor          = factors.get("tsb")
        existing.stress_factor       = factors.get("stress")
        existing.body_battery_factor = factors.get("body_battery")
        existing.wellness_factor     = factors.get("wellness")
        existing.weights_json        = json.dumps(result["weights"])
        existing.calculated_at       = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        db.add(RecoveryScore(
            user_id              = user_id,
            date_iso             = date_iso,
            score                = result["score"],
            level                = result["level"],
            color                = result["color"],
            training_suggestion  = result["training_suggestion"],
            recommendation       = rec_text,
            data_completeness    = result["data_completeness"],
            hrv_factor           = factors.get("hrv"),
            sleep_factor         = factors.get("sleep"),
            tsb_factor           = factors.get("tsb"),
            stress_factor        = factors.get("stress"),
            body_battery_factor  = factors.get("body_battery"),
            wellness_factor      = factors.get("wellness"),
            weights_json         = json.dumps(result["weights"]),
        ))
    try:
        db.commit()
    except IntegrityError:
        # Carrera: otro request concurrente ya insertó el score de este mismo día
        # (el frontend dispara /dashboard, /recommendation y /wellness casi a la vez).
        # El resultado ya calculado en esta request sigue siendo válido — se devuelve
        # tal cual sin persistir de nuevo, evitando el 500 por UNIQUE(user_id,date_iso).
        db.rollback()
    return result


def _today() -> str:
    return date.today().isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/dashboard")
def recovery_dashboard(
    date_iso: Optional[str] = Query(None),
    db:       Session       = Depends(get_db),
    me:       User          = Depends(get_current_user),
):
    """
    Endpoint maestro: Recovery Score + todos los datos de recuperación del día.
    1 llamada para toda la página de recuperación.
    """
    d_iso = date_iso or _today()

    # Score compuesto
    score_data = _get_or_compute_score(me.id, d_iso, db)

    # Datos crudos del día
    health = db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id  == me.id,
        GarminHealthDaily.date_iso == d_iso,
    ).first()
    sleep  = db.query(GarminSleepSession).filter(
        GarminSleepSession.user_id  == me.id,
        GarminSleepSession.date_iso == d_iso,
    ).first()
    tl     = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso == d_iso,
    ).first()
    wellness = db.query(WellnessLog).filter(
        WellnessLog.user_id  == me.id,
        WellnessLog.date_iso == d_iso,
    ).first()

    hrv_base = _get_hrv_baseline(me.id, db)

    # HRV histórico 7 días para mini-trend
    hrv_7d_raw = db.query(GarminHealthDaily.date_iso, GarminHealthDaily.hrv_last_night).filter(
        GarminHealthDaily.user_id  == me.id,
        GarminHealthDaily.date_iso >= (date.fromisoformat(d_iso) - timedelta(days=6)).isoformat(),
        GarminHealthDaily.date_iso <= d_iso,
    ).order_by(asc(GarminHealthDaily.date_iso)).all()

    hrv_trend = [{"date_iso": r[0], "hrv_ms": r[1]} for r in hrv_7d_raw if r[1]]
    hrv_change_pct = None
    if len(hrv_trend) >= 2:
        first_hrv = hrv_trend[0]["hrv_ms"]
        last_hrv  = hrv_trend[-1]["hrv_ms"]
        if first_hrv:
            hrv_change_pct = round((last_hrv - first_hrv) / first_hrv * 100, 1)

    return {
        "date_iso": d_iso,

        # Score
        "recovery": score_data,

        # HRV
        "hrv": {
            "last_night_ms":  health.hrv_last_night  if health else None,
            "weekly_avg_ms":  health.hrv_weekly_avg  if health else None,
            "baseline_ms":    round(hrv_base, 1)     if hrv_base else None,
            "status":         health.hrv_status       if health else None,
            "delta_pct":      round((health.hrv_last_night - hrv_base) / hrv_base * 100, 1)
                              if (health and health.hrv_last_night and hrv_base) else None,
            "trend_7d":       hrv_trend,
            "change_7d_pct":  hrv_change_pct,
        },

        # Sueño
        "sleep": {
            "total_min":   sleep.total_min    if sleep else None,
            "total_h":     round(sleep.total_min / 60, 1) if (sleep and sleep.total_min) else None,
            "deep_min":    sleep.deep_min     if sleep else None,
            "light_min":   sleep.light_min    if sleep else None,
            "rem_min":     sleep.rem_min      if sleep else None,
            "awake_min":   sleep.awake_min    if sleep else None,
            "score":       sleep.sleep_score  if sleep else None,
            "quality":     sleep.sleep_score_qual if sleep else None,
            "hrv_rmssd":   sleep.hrv_rmssd_night  if sleep else None,
            "spo2":        sleep.avg_spo2_night    if sleep else None,
        },

        # Carga
        "training_load": {
            "ctl":      tl.ctl     if tl else None,
            "atl":      tl.atl     if tl else None,
            "tsb":      tl.tsb     if tl else None,
            "tss_day":  tl.tss     if tl else None,
        },

        # Garmin wellness
        "garmin": {
            "body_battery_end":    health.body_battery_end  if health else None,
            "body_battery_max":    health.body_battery_max  if health else None,
            "avg_stress":          health.avg_stress         if health else None,
            "resting_hr":          health.resting_hr         if health else None,
            "training_readiness":  health.training_readiness if health else None,
            "recovery_time_h":     health.recovery_time_h    if health else None,
            "steps":               health.steps              if health else None,
            "avg_spo2":            health.avg_spo2           if health else None,
        },

        # Bienestar subjetivo
        "wellness": {
            "energy":      wellness.energy       if wellness else None,
            "mood":        wellness.mood         if wellness else None,
            "soreness":    wellness.soreness     if wellness else None,
            "motivation":  wellness.motivation   if wellness else None,
            "stress":      wellness.stress       if wellness else None,
            "sleep_quality":wellness.sleep_quality if wellness else None,
            "notes":       wellness.notes        if wellness else None,
            "logged":      wellness is not None,
        },
    }


@router.get("/score/{date_iso}")
def get_recovery_score(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Score de recuperación de un día específico."""
    return _get_or_compute_score(me.id, date_iso, db)


@router.post("/recalculate/{date_iso}")
def recalculate_score(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """Fuerza recálculo del score del día."""
    return _get_or_compute_score(me.id, date_iso, db, force=True)


# ─────────────────────────────────────────────────────────────────────────────
# HRV HISTORY
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/hrv/history")
def hrv_history(
    days: int = Query(30, ge=7, le=365),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Tendencia HRV y estadísticas."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows   = db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id  == me.id,
        GarminHealthDaily.date_iso >= cutoff,
    ).order_by(asc(GarminHealthDaily.date_iso)).all()

    points = [
        {
            "date_iso":       r.date_iso,
            "hrv_ms":         r.hrv_last_night,
            "hrv_weekly_avg": r.hrv_weekly_avg,
            "status":         r.hrv_status,
            "stress":         r.avg_stress,
            "resting_hr":     r.resting_hr,
        }
        for r in rows
    ]
    valid_hrv = [p["hrv_ms"] for p in points if p["hrv_ms"]]

    # Tendencia lineal del HRV
    trend_slope = None
    if len(valid_hrv) >= 7:
        n     = len(valid_hrv)
        xs    = list(range(n))
        x_m   = sum(xs) / n
        y_m   = sum(valid_hrv) / n
        num   = sum((xs[i] - x_m) * (valid_hrv[i] - y_m) for i in range(n))
        den   = sum((xs[i] - x_m) ** 2 for i in range(n))
        if den:
            slope = num / den
            trend_slope = round(slope * 7, 2)  # ms/semana

    # Zonas (% de días en cada zona)
    baseline = _get_hrv_baseline(me.id, db)
    zones = {"optimal": 0, "normal": 0, "low": 0, "critical": 0}
    for v in valid_hrv:
        if baseline > 0:
            r = v / baseline
            if r > 1.10:    zones["optimal"]  += 1
            elif r > 0.95:  zones["normal"]   += 1
            elif r > 0.80:  zones["low"]      += 1
            else:           zones["critical"] += 1
        else:
            if v >= 60:     zones["optimal"]  += 1
            elif v >= 45:   zones["normal"]   += 1
            elif v >= 30:   zones["low"]      += 1
            else:           zones["critical"] += 1

    total_valid = len(valid_hrv)
    zones_pct = {k: round(v / total_valid * 100) if total_valid else 0 for k, v in zones.items()}

    return {
        "days":           days,
        "points":         points,
        "baseline_ms":    round(baseline, 1) if baseline else None,
        "avg_ms":         round(statistics.mean(valid_hrv), 1) if valid_hrv else None,
        "min_ms":         min(valid_hrv) if valid_hrv else None,
        "max_ms":         max(valid_hrv) if valid_hrv else None,
        "stdev_ms":       round(statistics.stdev(valid_hrv), 1) if len(valid_hrv) >= 2 else None,
        "trend_ms_week":  trend_slope,
        "trend_direction":"up" if trend_slope and trend_slope > 0.5 else ("down" if trend_slope and trend_slope < -0.5 else "stable"),
        "zones_pct":      zones_pct,
        "n_valid":        total_valid,
    }


# ─────────────────────────────────────────────────────────────────────────────
# SLEEP HISTORY
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/sleep/history")
def sleep_history(
    days: int = Query(30, ge=7, le=180),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Tendencia de sueño con desglose de fases."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows   = db.query(GarminSleepSession).filter(
        GarminSleepSession.user_id  == me.id,
        GarminSleepSession.date_iso >= cutoff,
    ).order_by(asc(GarminSleepSession.date_iso)).all()

    points = [
        {
            "date_iso":   r.date_iso,
            "total_h":    round(r.total_min / 60, 1) if r.total_min else None,
            "deep_min":   r.deep_min,
            "light_min":  r.light_min,
            "rem_min":    r.rem_min,
            "awake_min":  r.awake_min,
            "score":      r.sleep_score,
            "quality":    r.sleep_score_qual,
            "hrv_rmssd":  r.hrv_rmssd_night,
        }
        for r in rows
    ]

    valid_scores = [p["score"]   for p in points if p["score"]   is not None]
    valid_hours  = [p["total_h"] for p in points if p["total_h"] is not None]

    # Deuda de sueño (vs 8h objetivo)
    SLEEP_TARGET_H = 8.0
    sleep_debt_h = 0.0
    for p in points[-7:]:
        if p["total_h"] is not None:
            sleep_debt_h += max(0, SLEEP_TARGET_H - p["total_h"])

    # Porcentaje de noches con <6h
    nights_under_6h = sum(1 for p in points if p["total_h"] and p["total_h"] < 6)

    return {
        "days":           days,
        "points":         points,
        "avg_score":      round(statistics.mean(valid_scores), 1) if valid_scores else None,
        "avg_hours":      round(statistics.mean(valid_hours), 1)  if valid_hours  else None,
        "sleep_debt_7d_h":round(sleep_debt_h, 1),
        "nights_under_6h":nights_under_6h,
        "target_h":       SLEEP_TARGET_H,
        "n":              len(points),
    }


# ─────────────────────────────────────────────────────────────────────────────
# TIMELINE (superpuesto)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/timeline")
def recovery_timeline(
    days: int = Query(30, ge=7, le=90),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """
    Vista temporal superpuesta: Recovery Score + HRV + Sleep + TSB.
    Permite identificar patrones y ventanas de forma.
    """
    cutoff   = (date.today() - timedelta(days=days)).isoformat()

    # Recovery scores
    scores_q = db.query(RecoveryScore).filter(
        RecoveryScore.user_id  == me.id,
        RecoveryScore.date_iso >= cutoff,
    ).order_by(asc(RecoveryScore.date_iso)).all()

    # HRV
    health_q = db.query(GarminHealthDaily).filter(
        GarminHealthDaily.user_id  == me.id,
        GarminHealthDaily.date_iso >= cutoff,
    ).order_by(asc(GarminHealthDaily.date_iso)).all()

    # Sleep
    sleep_q  = db.query(GarminSleepSession).filter(
        GarminSleepSession.user_id  == me.id,
        GarminSleepSession.date_iso >= cutoff,
    ).order_by(asc(GarminSleepSession.date_iso)).all()

    # TSB
    tl_q     = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso >= cutoff,
    ).order_by(asc(GarminTrainingLoad.date_iso)).all()

    # Indexar por fecha
    score_map  = {r.date_iso: r.score          for r in scores_q}
    color_map  = {r.date_iso: r.color          for r in scores_q}
    hrv_map    = {r.date_iso: r.hrv_last_night for r in health_q}
    sleep_map  = {r.date_iso: r.sleep_score    for r in sleep_q}
    tsb_map    = {r.date_iso: r.tsb            for r in tl_q}
    tss_map    = {r.date_iso: r.tss             for r in tl_q}

    # Generar timeline diaria
    all_dates = sorted(set(
        list(score_map.keys()) + list(hrv_map.keys()) +
        list(sleep_map.keys()) + list(tsb_map.keys())
    ))

    timeline = []
    for d_iso in all_dates:
        timeline.append({
            "date_iso":      d_iso,
            "recovery_score":score_map.get(d_iso),
            "recovery_color":color_map.get(d_iso),
            "hrv_ms":        hrv_map.get(d_iso),
            "sleep_score":   sleep_map.get(d_iso),
            "tsb":           tsb_map.get(d_iso),
            "tss_day":       tss_map.get(d_iso),
        })

    # Identificar ventanas de forma óptima (score ≥ 70, 3+ días consecutivos)
    optimal_windows = []
    streak_start    = None
    streak_count    = 0
    for t in timeline:
        if (t["recovery_score"] or 0) >= 70:
            if streak_start is None:
                streak_start = t["date_iso"]
            streak_count += 1
        else:
            if streak_count >= 3:
                optimal_windows.append({
                    "start": streak_start,
                    "days":  streak_count,
                    "label": f"{streak_count} días en forma",
                })
            streak_start = None
            streak_count = 0
    if streak_count >= 3:
        optimal_windows.append({"start": streak_start, "days": streak_count, "label": f"{streak_count} días en forma"})

    return {
        "days":            days,
        "timeline":        timeline,
        "optimal_windows": optimal_windows,
        "data_points":     len(timeline),
    }


# ─────────────────────────────────────────────────────────────────────────────
# WELLNESS LOG
# ─────────────────────────────────────────────────────────────────────────────

class _WellnessIn(BaseModel):
    energy:       Optional[int] = None
    mood:         Optional[int] = None
    soreness:     Optional[int] = None
    motivation:   Optional[int] = None
    stress:       Optional[int] = None
    sleep_quality:Optional[int] = None
    notes:        Optional[str] = None
    date_iso:     Optional[str] = None

    @field_validator("energy", "mood", "soreness", "motivation", "stress", "sleep_quality", mode="before")
    @classmethod
    def validate_scale(cls, v):
        if v is not None and (v < 1 or v > 5):
            raise ValueError("Escala debe ser 1-5")
        return v

    @field_validator("notes")
    @classmethod
    def truncate_notes(cls, v):
        return v[:300] if v else v


@router.post("/wellness", status_code=201)
def log_wellness(
    body: _WellnessIn,
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """Registra o actualiza el bienestar subjetivo del día (upsert)."""
    d_iso    = body.date_iso or _today()
    existing = db.query(WellnessLog).filter(
        WellnessLog.user_id  == me.id,
        WellnessLog.date_iso == d_iso,
    ).first()

    fields = ("energy","mood","soreness","motivation","stress","sleep_quality","notes")
    if existing:
        for f in fields:
            v = getattr(body, f)
            if v is not None:
                setattr(existing, f, v)
    else:
        db.add(WellnessLog(
            user_id       = me.id,
            date_iso      = d_iso,
            energy        = body.energy,
            mood          = body.mood,
            soreness      = body.soreness,
            motivation    = body.motivation,
            stress        = body.stress,
            sleep_quality = body.sleep_quality,
            notes         = body.notes,
        ))
    db.commit()

    # Invalidar cache del score del día (se recalculará con wellness)
    _get_or_compute_score(me.id, d_iso, db, force=True)

    return {"ok": True, "date_iso": d_iso, "message": "Bienestar registrado"}


@router.get("/wellness/{date_iso}")
def get_wellness(
    date_iso: str,
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    w = db.query(WellnessLog).filter(
        WellnessLog.user_id  == me.id,
        WellnessLog.date_iso == date_iso,
    ).first()
    if not w:
        return {"logged": False, "date_iso": date_iso}
    return {
        "logged":       True,
        "date_iso":     w.date_iso,
        "energy":       w.energy,
        "mood":         w.mood,
        "soreness":     w.soreness,
        "motivation":   w.motivation,
        "stress":       w.stress,
        "sleep_quality":w.sleep_quality,
        "notes":        w.notes,
    }


@router.get("/wellness/history")
def wellness_history(
    days: int = Query(30, ge=7, le=180),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    rows   = db.query(WellnessLog).filter(
        WellnessLog.user_id  == me.id,
        WellnessLog.date_iso >= cutoff,
    ).order_by(asc(WellnessLog.date_iso)).all()

    points = [
        {
            "date_iso":     w.date_iso,
            "energy":       w.energy,
            "mood":         w.mood,
            "soreness":     w.soreness,
            "motivation":   w.motivation,
            "stress":       w.stress,
            "sleep_quality":w.sleep_quality,
        }
        for w in rows
    ]

    # Promedios
    def avg(field):
        vals = [getattr(r, field) for r in rows if getattr(r, field) is not None]
        return round(statistics.mean(vals), 1) if vals else None

    return {
        "days":   days,
        "points": points,
        "avgs": {
            "energy":       avg("energy"),
            "mood":         avg("mood"),
            "soreness":     avg("soreness"),
            "motivation":   avg("motivation"),
            "stress":       avg("stress"),
            "sleep_quality":avg("sleep_quality"),
        },
        "n": len(points),
    }


# ─────────────────────────────────────────────────────────────────────────────
# RECOMENDACIÓN IA
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/recommendation")
def get_recommendation(
    date_iso: Optional[str] = Query(None),
    db:       Session       = Depends(get_db),
    me:       User          = Depends(get_current_user),
):
    """
    Recomendación completa de entrenamiento para el día.
    Incluye sugerencia de carga, protocolos específicos y alertas.
    """
    d_iso    = date_iso or _today()
    score_d  = _get_or_compute_score(me.id, d_iso, db)
    score    = score_d.get("score", 50)
    sug      = score_d.get("training_suggestion", "moderate")
    factors  = score_d.get("factors", {})

    tl = db.query(GarminTrainingLoad).filter(
        GarminTrainingLoad.user_id  == me.id,
        GarminTrainingLoad.date_iso == d_iso,
    ).first()

    # Obtener plan programado para el día (sesiones prescritas, no carga ya ejecutada)
    planned_sessions = db.query(PlanSession).filter(
        PlanSession.athlete_id == me.id,
        PlanSession.date_iso   == d_iso,
        PlanSession.is_skipped == False,
    ).all()
    planned_tss = sum(s.tss_planned or 0 for s in planned_sessions)

    # Sugerencia de carga ajustada
    adjustment_factor = {
        "full":     1.00,
        "moderate": 0.75,
        "easy":     0.50,
        "rest":     0.00,
    }.get(sug, 0.75)

    recommended_tss = round(planned_tss * adjustment_factor) if planned_tss else None

    # Tipo de sesión recomendada
    session_type = {
        "full":     "Sesión completa según plan. Alta intensidad disponible.",
        "moderate": "Sesión moderada. Reduce intensidad al 75-80% del plan.",
        "easy":     "Solo Z1-Z2. Técnica o recuperación activa. TSS ≤ 50.",
        "rest":     "Descanso completo o stretching suave. Cero carga.",
    }.get(sug, "Moderado")

    # Alertas adicionales
    alerts = []
    if factors.get("hrv") is not None and factors["hrv"] < 30:
        alerts.append({
            "type":    "hrv_critical",
            "level":   "high",
            "message": "HRV muy bajo. El sistema nervioso autónomo no está recuperado. Riesgo de sobreentrenamiento.",
        })
    if factors.get("sleep") is not None and factors["sleep"] < 40:
        alerts.append({
            "type":    "sleep_deficit",
            "level":   "medium",
            "message": "Sueño insuficiente. El 75% de la hormona de crecimiento se libera en sueño profundo.",
        })
    if tl and (tl.tsb or 0) < -30:
        alerts.append({
            "type":    "high_fatigue",
            "level":   "medium",
            "message": f"Fatiga acumulada alta (TSB {int(tl.tsb or 0)}). Considera 2-3 días de carga reducida.",
        })

    # Prioridades de recuperación
    recovery_priorities = []
    if factors.get("sleep") is not None and factors["sleep"] < 60:
        recovery_priorities.append("🌙 Prioriza dormir 8h esta noche")
    if factors.get("stress") is not None and factors["stress"] < 50:
        recovery_priorities.append("🧘 Estrés alto detectado — técnicas de relajación o meditación")
    if factors.get("hrv") is not None and factors["hrv"] < 50:
        recovery_priorities.append("🫀 HRV bajo — protocolo de recuperación neuro (Z1, baño frío, respiración)")

    return {
        "date_iso":          d_iso,
        "score":             score,
        "training_suggestion":sug,
        "session_type":      session_type,
        "planned_tss":       planned_tss,
        "recommended_tss":   recommended_tss,
        "adjustment_pct":    round((1 - adjustment_factor) * 100),
        "main_recommendation":score_d.get("recommendation", ""),
        "alerts":            alerts,
        "recovery_priorities":recovery_priorities,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CORRELACIONES HRV × RENDIMIENTO
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/correlations")
def recovery_correlations(
    days: int = Query(90, ge=30, le=365),
    db:   Session = Depends(get_db),
    me:   User    = Depends(get_current_user),
):
    """
    Correlación HRV × rendimiento histórico.
    Identifica las condiciones objetivas del atleta cuando rinde mejor.
    """
    cutoff   = (date.today() - timedelta(days=days)).isoformat()

    # Actividades del período
    acts = db.query(GarminActivity).filter(
        GarminActivity.user_id  == me.id,
        GarminActivity.date_iso >= cutoff,
        GarminActivity.tss.isnot(None),
    ).order_by(asc(GarminActivity.date_iso)).all()

    # Hacer join con HRV del mismo día
    correlations = []
    for a in acts:
        health = db.query(GarminHealthDaily).filter(
            GarminHealthDaily.user_id  == me.id,
            GarminHealthDaily.date_iso == a.date_iso,
        ).first()
        if not health or not health.hrv_last_night:
            continue

        # Recovery score del día
        rs = db.query(RecoveryScore).filter(
            RecoveryScore.user_id  == me.id,
            RecoveryScore.date_iso == a.date_iso,
        ).first()

        correlations.append({
            "date_iso":       a.date_iso,
            "sport":          a.sport,
            "hrv_ms":         health.hrv_last_night,
            "recovery_score": rs.score if rs else None,
            "tsb":            None,  # se podría añadir
            "tss":            a.tss,
            "dist_km":        a.dist_km,
            "dur_min":        a.dur_min,
        })

    # Análisis estadístico simple
    if len(correlations) >= 10:
        hrv_values = [c["hrv_ms"] for c in correlations if c["hrv_ms"]]
        median_hrv = statistics.median(hrv_values) if hrv_values else None

        if median_hrv:
            high_hrv_acts = [c for c in correlations if c["hrv_ms"] and c["hrv_ms"] >= median_hrv]
            low_hrv_acts  = [c for c in correlations if c["hrv_ms"] and c["hrv_ms"] <  median_hrv]

            def avg_tss(group):
                vals = [c["tss"] for c in group if c["tss"]]
                return round(statistics.mean(vals), 1) if vals else None

            insights = []
            hi_avg = avg_tss(high_hrv_acts)
            lo_avg = avg_tss(low_hrv_acts)
            if hi_avg and lo_avg and hi_avg != lo_avg:
                diff_pct = round((hi_avg - lo_avg) / lo_avg * 100, 1)
                if diff_pct > 5:
                    insights.append(
                        f"Cuando tu HRV es ≥{int(median_hrv)}ms, tu TSS promedio es {hi_avg} "
                        f"(+{diff_pct}% vs días con HRV bajo). Rindes más con HRV alto."
                    )
                elif diff_pct < -5:
                    insights.append(
                        f"Curiosamente, tu TSS promedio es similar independientemente del HRV. "
                        f"Podrías estar sobreforzando cuando el HRV es bajo."
                    )
        else:
            insights = []
    else:
        insights = ["Se necesitan más datos (mínimo 10 actividades con HRV) para análisis de correlación."]

    return {
        "days":         days,
        "correlations": correlations,
        "n":            len(correlations),
        "insights":     insights,
    }


# ─────────────────────────────────────────────────────────────────────────────
# PROTOCOLOS DE RECUPERACIÓN
# ─────────────────────────────────────────────────────────────────────────────

RECOVERY_PROTOCOLS = {
    "post_sprint": {
        "name":     "Post Sprint",
        "duration": "3-5 días",
        "days": [
            {"day": 1, "label": "Día 1 (post-carrera)", "load": "rest",     "tss_max": 0,  "actions": ["Hidratación 3L", "Proteína 2g/kg", "Baño frío 10min", "Sueño 9h"]},
            {"day": 2, "label": "Día 2",                "load": "easy",     "tss_max": 20, "actions": ["30min natación técnica", "Masaje/foam roller", "Nutrición recuperación"]},
            {"day": 3, "label": "Día 3",                "load": "moderate", "tss_max": 45, "actions": ["Bici Z1-Z2 45min o carrera 30min suave"]},
            {"day": 4, "label": "Día 4",                "load": "full",     "tss_max": 70, "actions": ["Entrenamiento normal si HRV normalizado"]},
        ],
        "hrv_clearance": "HRV ≥ 90% del baseline antes de retomar intensidad",
    },
    "post_703": {
        "name":     "Post 70.3",
        "duration": "10-14 días",
        "days": [
            {"day": 1,  "label": "Días 1-2",   "load": "rest",     "tss_max": 0,  "actions": ["Descanso total", "Hidratación activa", "Anti-inflamatorio natural", "Sueño ≥9h"]},
            {"day": 3,  "label": "Días 3-4",   "load": "easy",     "tss_max": 25, "actions": ["Caminata suave 30min", "Natación técnica 20min", "Masaje profesional"]},
            {"day": 5,  "label": "Días 5-7",   "load": "easy",     "tss_max": 40, "actions": ["Bici Z1 45min o run 20min Z1", "Continúa foam roller diario"]},
            {"day": 8,  "label": "Días 8-10",  "load": "moderate", "tss_max": 60, "actions": ["Sesiones técnicas, sin intensidad", "Monitorear HRV — si <baseline, extender"]},
            {"day": 11, "label": "Días 11-14", "load": "full",     "tss_max": 80, "actions": ["Reintroducir intensidad solo si HRV ≥ 95% baseline y TSB > -5"]},
        ],
        "hrv_clearance": "HRV ≥ 95% del baseline antes de sesión umbral",
    },
    "post_ironman": {
        "name":     "Post Ironman",
        "duration": "21-28 días",
        "days": [
            {"day": 1,  "label": "Semana 1",  "load": "rest",     "tss_max": 0,  "actions": ["Descanso activo únicamente", "No nadar, no correr, no bici", "Crioterapia si disponible", "Proteína 2.2g/kg/día"]},
            {"day": 8,  "label": "Semana 2",  "load": "easy",     "tss_max": 150,"actions": ["Solo Z1-Z2 todas las sesiones", "Natación técnica OK", "Sin umbrales"]},
            {"day": 15, "label": "Semana 3",  "load": "moderate", "tss_max": 250,"actions": ["Aumentar volumen progresivo", "Una sesión moderada al inicio de la semana"]},
            {"day": 22, "label": "Semana 4+", "load": "full",     "tss_max": 350,"actions": ["Retorno a intensidad normal", "Solo si HRV ≥ baseline y TSB > 0"]},
        ],
        "hrv_clearance": "No realizar intervalos hasta semana 4 Y HRV ≥ baseline",
        "warning": "El Ironman produce daño muscular detectable hasta 4 semanas post-carrera. Subestimar la recuperación es la principal causa de lesiones en triatletas.",
    },
    "illness": {
        "name":     "Post-Enfermedad",
        "duration": "Variable (48h sin fiebre mínimo)",
        "days": [
            {"day": 1,  "label": "Durante síntomas", "load": "rest",     "tss_max": 0,  "actions": ["Cero entrenamiento con fiebre", "Hidratación máxima", "Descanso total"]},
            {"day": 2,  "label": "48h asintomático",  "load": "easy",     "tss_max": 20, "actions": ["Solo movilidad suave", "No aumentes si síntomas regresan"]},
            {"day": 4,  "label": "4-5 días OK",       "load": "moderate", "tss_max": 50, "actions": ["Retorno muy gradual", "HRV como guía principal"]},
            {"day": 7,  "label": "7+ días OK",        "load": "full",     "tss_max": None, "actions": ["Normal si HRV normalizado"]},
        ],
        "hrv_clearance": "HRV normalizado al menos 3 días consecutivos",
        "warning": "Entrenar con fiebre o síntomas activos aumenta el riesgo de miocarditis. Regla: nunca."
    },
    "overtraining": {
        "name":     "Sobreentrenamiento",
        "duration": "2-8 semanas (según severidad)",
        "days": [
            {"day": 1,  "label": "Fase 1 (1-2 sem)", "load": "rest",     "tss_max": 0,   "actions": ["Reducción drástica de carga", "Análisis de sangre (ferritina, cortisol, testosterona)", "Revisión nutricional"]},
            {"day": 15, "label": "Fase 2 (2-4 sem)", "load": "easy",     "tss_max": 100, "actions": ["Solo Z1 si HRV muestra mejora", "Monitoreo HRV diario obligatorio"]},
            {"day": 29, "label": "Fase 3 (4-8 sem)", "load": "moderate", "tss_max": 200, "actions": ["Aumento muy gradual", "CTL objetivo 50% del anterior"]},
        ],
        "hrv_clearance": "HRV estable ≥ baseline durante 7 días consecutivos",
        "warning": "Sobreentrenamiento real puede requerir semanas o meses. Continuar entrenando agrava el síndrome."
    },
}


@router.get("/protocol/{ptype}")
def get_recovery_protocol(
    ptype: str,
    db:    Session = Depends(get_db),
    me:    User    = Depends(get_current_user),
):
    """
    Protocolo de recuperación detallado.
    Types: post_sprint | post_703 | post_ironman | illness | overtraining
    """
    protocol = RECOVERY_PROTOCOLS.get(ptype)
    if not protocol:
        raise HTTPException(
            404,
            f"Protocolo '{ptype}' no encontrado. Disponibles: {list(RECOVERY_PROTOCOLS.keys())}"
        )

    # Añadir contexto del atleta actual
    d_iso = _today()
    score_d = _get_or_compute_score(me.id, d_iso, db)

    hrv_base = _get_hrv_baseline(me.id, db)

    return {
        "protocol":     protocol,
        "athlete_context": {
            "recovery_score_today": score_d.get("score"),
            "hrv_baseline_ms":      round(hrv_base, 1) if hrv_base else None,
            "recommendation":       "Sigue el protocolo día por día. Usa el HRV diario como semáforo de avance.",
        },
        "available_types": list(RECOVERY_PROTOCOLS.keys()),
    }


# ─────────────────────────────────────────────────────────────────────────────
# COACH VIEW — todos los atletas con recovery
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/coach-view")
def coach_recovery_view(
    db: Session = Depends(get_db),
    me: User    = Depends(get_current_user),
):
    """
    Vista coach: recovery score de todos sus atletas hoy.
    Semáforo rojo/amarillo/verde instantáneo.
    Requiere rol de coach.
    """
    if getattr(me, "role", None) not in ("coach", "admin"):
        raise HTTPException(403, "Solo coaches pueden acceder a esta vista.")

    # Atletas del coach
    _group_ids = [g.id for g in db.query(Group).filter(Group.coach_id == me.id).all()]
    athlete_rels = db.query(GroupMember).filter(GroupMember.group_id.in_(_group_ids)).all()

    d_iso   = _today()
    results = []

    for rel in athlete_rels:
        athlete_id  = rel.athlete_id
        athlete     = db.query(User).filter(User.id == athlete_id).first()
        if not athlete:
            continue

        score_d = _get_or_compute_score(athlete_id, d_iso, db)

        # HRV tendencia (↑↓→)
        hrv_q = db.query(GarminHealthDaily.hrv_last_night).filter(
            GarminHealthDaily.user_id  == athlete_id,
            GarminHealthDaily.date_iso >= (date.today() - timedelta(days=3)).isoformat(),
        ).order_by(asc(GarminHealthDaily.date_iso)).all()
        hrv_vals = [r[0] for r in hrv_q if r[0]]
        hrv_trend = "→"
        if len(hrv_vals) >= 2:
            hrv_trend = "↑" if hrv_vals[-1] > hrv_vals[0] else ("↓" if hrv_vals[-1] < hrv_vals[0] else "→")

        # Alertas automáticas (2+ días en rojo)
        recent_scores = db.query(RecoveryScore.score, RecoveryScore.date_iso).filter(
            RecoveryScore.user_id  == athlete_id,
            RecoveryScore.date_iso >= (date.today() - timedelta(days=2)).isoformat(),
        ).order_by(asc(RecoveryScore.date_iso)).all()
        consecutive_red = sum(1 for r in recent_scores if (r.score or 100) < 40)
        needs_attention = consecutive_red >= 2

        results.append({
            "athlete_id":    athlete_id,
            "name":          getattr(athlete, "nombre", "") or getattr(athlete, "username", athlete_id),
            "score":         score_d.get("score"),
            "level":         score_d.get("level"),
            "color":         score_d.get("color"),
            "suggestion":    score_d.get("training_suggestion"),
            "hrv_trend":     hrv_trend,
            "needs_attention":needs_attention,
            "factors": {
                "hrv":   score_d.get("factors", {}).get("hrv"),
                "sleep": score_d.get("factors", {}).get("sleep"),
                "tsb":   score_d.get("factors", {}).get("tsb"),
            },
        })

    # Ordenar: rojo primero, luego amarillo, verde al final
    level_order = {"critical": 0, "low": 1, "moderate": 2, "good": 3, "optimal": 4}
    results.sort(key=lambda x: level_order.get(x.get("level", "moderate"), 2))

    return {
        "date_iso":      d_iso,
        "athletes":      results,
        "n":             len(results),
        "red_count":     sum(1 for r in results if r.get("level") in ("critical","low")),
        "green_count":   sum(1 for r in results if r.get("level") in ("optimal","good")),
        "needs_attention":[r for r in results if r.get("needs_attention")],
    }


