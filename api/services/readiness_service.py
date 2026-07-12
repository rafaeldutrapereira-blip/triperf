"""
LabX — Daily Athlete Readiness Service (Sprint 23)
===================================================
Motor determinista que sintetiza TODAS las señales fisiológicas de LabX
en un único "Daily Readiness Score" (DRS) 0-100.

Dimensiones (pesos fisiológicamente validados):
  1. Recovery Score (HRV + sueño)       — 35% — base biológica del descanso
  2. Mental Fatigue Score (MFS)          — 25% — readiness neurocognitiva
  3. Training Restriction Score (TRS)    — 20% — limitaciones hematológicas/bioquímicas
  4. Training Form / TSB                 — 20% — carga aguda vs crónica (fatiga)

Diferenciador vs competidores:
  - TrainingPeaks: solo TSB (1 dimensión)
  - Whoop: Recovery (HRV + sueño) — 2 dimensiones
  - Intervals.icu: CTL/ATL/TSB — 1 dimensión
  - LabX: 4 dimensiones integradas con biomarcadores — único en el mercado LATAM

Fallback estratégico:
  Si alguna dimensión no tiene datos, se imputa con el promedio de las otras.
  Si hay 0 dimensiones, se devuelve DRS=70 (neutral) para no bloquear el UX.
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("labx.readiness")

# Pesos de cada dimensión (deben sumar 1.0)
_W_RECOVERY = 0.35
_W_MENTAL   = 0.25
_W_TRS      = 0.20
_W_FORM     = 0.20


# ─────────────────────────────────────────────────────────────────────────────
# Data types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReadinessDimension:
    name: str
    score: Optional[float]       # 0-100 o None si sin datos
    weight: float
    label: str
    color: str                   # hex
    available: bool
    data_source: str


@dataclass
class DailyReadinessReport:
    drs: int                              # 0-100 — Daily Readiness Score
    drs_label: str                        # "Óptimo" | "Bueno" | "Moderado" | "Bajo" | "Crítico"
    drs_color: str                        # hex
    drs_emoji: str                        # para mobile UI
    recommendation: str                   # 1 frase de qué hacer hoy
    training_guidance: str                # zona objetivo / tipo de sesión
    dimensions: list[ReadinessDimension]
    primary_limiter: Optional[str]        # dimensión que más baja el DRS
    data_completeness: float              # 0-1 — cuántas dimensiones tienen datos
    warnings: list[str]                   # avisos técnicos
    computed_from: list[str]              # dimensiones usadas en el cálculo


# ─────────────────────────────────────────────────────────────────────────────
# TSB → Form score conversion
# ─────────────────────────────────────────────────────────────────────────────

def tsb_to_form_score(tsb: float) -> float:
    """
    Convierte TSB (Training Stress Balance) a score 0-100.

    Modelo fisiológico:
      TSB ≤ -30:  score 10  (muy fatigado — riesgo sobreentrenamiento)
      TSB -30..0: score 10-60 (fatiga normal en bloque de carga)
      TSB 0..+10: score 60-80 (tapering — buena frescura)
      TSB +10..+25: score 80-95 (pico de forma)
      TSB > +25:  score 80  (demasiado descansado — pérdida de fitness)
    """
    if tsb <= -30:
        return 10.0
    if tsb < 0:
        # Lineal: -30→10, 0→60
        return 10.0 + (tsb + 30) * (50.0 / 30.0)
    if tsb <= 10:
        # Lineal: 0→60, 10→80
        return 60.0 + tsb * 2.0
    if tsb <= 25:
        # Lineal: 10→80, 25→95
        return 80.0 + (tsb - 10) * (15.0 / 15.0)
    # TSB muy positivo = desentrenado
    return max(80.0, 95.0 - (tsb - 25) * 1.5)


# ─────────────────────────────────────────────────────────────────────────────
# DRS label system
# ─────────────────────────────────────────────────────────────────────────────

def _drs_metadata(drs: int) -> tuple[str, str, str, str, str]:
    """Returns (label, color, emoji, recommendation, training_guidance)"""
    if drs >= 85:
        return (
            "Óptimo",
            "#10b981",
            "🟢",
            "Condiciones fisiológicas ideales. Aprovecha para sesiones de calidad.",
            "Sesión de alta intensidad o largo endurance según plan",
        )
    if drs >= 70:
        return (
            "Bueno",
            "#22d3ee",
            "🔵",
            "Buena disposición para entrenar. Ejecuta el plan con normalidad.",
            "Sigue el plan — intensidad moderada a alta según programa",
        )
    if drs >= 55:
        return (
            "Moderado",
            "#f59e0b",
            "🟡",
            "Readiness moderada. Ajusta la intensidad si sientes fatiga.",
            "Preferir Zona 2 — evitar series VO2 hoy",
        )
    if drs >= 35:
        return (
            "Bajo",
            "#f97316",
            "🟠",
            "Señales de fatiga acumulada. Considera reducir volumen o descansar.",
            "Solo Zona 1 o descanso activo (movilidad, natación suave)",
        )
    return (
        "Crítico",
        "#ef4444",
        "🔴",
        "Cuerpo en estado de recuperación. El entrenamiento duro hoy puede lesionar.",
        "Descanso completo o recuperación activa muy suave",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Core computation
# ─────────────────────────────────────────────────────────────────────────────

def compute_daily_readiness(
    recovery_score: Optional[float] = None,   # 0-100 (de recovery_routes)
    mental_score:   Optional[float] = None,   # 0-100 (de mental_routes)
    trs:            Optional[float] = None,   # 0-100 (de blood_labs_impact_service)
    tsb:            Optional[float] = None,   # raw TSB (se convierte internamente)
) -> DailyReadinessReport:
    """
    Compute the Daily Readiness Score from available signals.

    Args:
        recovery_score: 0-100 del módulo de recuperación (HRV + sueño)
        mental_score:   0-100 del módulo mental (MFS)
        trs:            0-100 Training Restriction Score (blood labs)
        tsb:            TSB raw del modelo Banister (se convierte a 0-100)

    Returns:
        DailyReadinessReport completo
    """
    warnings: list[str] = []

    # Convertir TSB a form_score
    form_score: Optional[float] = None
    if tsb is not None:
        form_score = tsb_to_form_score(float(tsb))

    # Construir dimensiones
    dims: list[ReadinessDimension] = [
        ReadinessDimension(
            name="Recuperación",
            score=float(recovery_score) if recovery_score is not None else None,
            weight=_W_RECOVERY,
            label="HRV + Sueño",
            color="#10b981",
            available=recovery_score is not None,
            data_source="recovery_scores",
        ),
        ReadinessDimension(
            name="Estado Mental",
            score=float(mental_score) if mental_score is not None else None,
            weight=_W_MENTAL,
            label="Fatiga Neurocognitiva",
            color="#a855f7",
            available=mental_score is not None,
            data_source="mental_fatigue_scores",
        ),
        ReadinessDimension(
            name="Bioquímica",
            score=float(trs) if trs is not None else None,
            weight=_W_TRS,
            label="Blood Labs TRS",
            color="#f59e0b",
            available=trs is not None,
            data_source="blood_lab_exams",
        ),
        ReadinessDimension(
            name="Forma",
            score=form_score,
            weight=_W_FORM,
            label="TSB (CTL−ATL)",
            color="#22d3ee",
            available=form_score is not None,
            data_source="garmin_training_load",
        ),
    ]

    available_dims = [d for d in dims if d.available and d.score is not None]
    n_available = len(available_dims)
    data_completeness = round(n_available / len(dims), 2)

    if n_available == 0:
        warnings.append("Sin datos fisiológicos disponibles — DRS neutral (70)")
        label, color, emoji, rec, guidance = _drs_metadata(70)
        return DailyReadinessReport(
            drs=70, drs_label=label, drs_color=color, drs_emoji=emoji,
            recommendation=rec, training_guidance=guidance,
            dimensions=dims, primary_limiter=None,
            data_completeness=0.0, warnings=warnings,
            computed_from=[],
        )

    # Weighted average con normalización de pesos de las dimensiones disponibles
    total_weight = sum(d.weight for d in available_dims)
    weighted_sum = sum(d.score * d.weight for d in available_dims)
    raw_drs = weighted_sum / total_weight

    # Penalización si datos incompletos (max -5 puntos por dimensión faltante)
    missing = len(dims) - n_available
    completeness_penalty = missing * 2.5
    adjusted_drs = max(0.0, min(100.0, raw_drs - completeness_penalty))

    drs = int(round(adjusted_drs))

    if missing > 0:
        missing_names = [d.name for d in dims if not d.available]
        warnings.append(f"DRS calculado con {n_available}/{len(dims)} dimensiones — datos faltantes: {', '.join(missing_names)}")

    # Identificar dimensión más limitante
    primary_limiter: Optional[str] = None
    if available_dims:
        worst = min(available_dims, key=lambda d: d.score)
        if worst.score < 60:
            primary_limiter = worst.name

    label, color, emoji, rec, guidance = _drs_metadata(drs)

    return DailyReadinessReport(
        drs=drs,
        drs_label=label,
        drs_color=color,
        drs_emoji=emoji,
        recommendation=rec,
        training_guidance=guidance,
        dimensions=dims,
        primary_limiter=primary_limiter,
        data_completeness=data_completeness,
        warnings=warnings,
        computed_from=[d.name for d in available_dims],
    )


# ─────────────────────────────────────────────────────────────────────────────
# History aggregation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ReadinessHistoryPoint:
    date_iso: str
    drs: int
    recovery_score: Optional[float]
    mental_score: Optional[float]
    trs: Optional[float]
    form_score: Optional[float]
    label: str
    color: str


def compute_readiness_history(data_points: list[dict]) -> list[ReadinessHistoryPoint]:
    """
    Computa el DRS histórico para una lista de puntos de datos.

    Args:
        data_points: list of {
            date_iso: str,
            recovery_score: float|None,
            mental_score: float|None,
            trs: float|None,
            tsb: float|None,
        }

    Returns:
        list[ReadinessHistoryPoint] ordenado por fecha
    """
    results = []
    for point in data_points:
        report = compute_daily_readiness(
            recovery_score=point.get("recovery_score"),
            mental_score=point.get("mental_score"),
            trs=point.get("trs"),
            tsb=point.get("tsb"),
        )
        form = tsb_to_form_score(point["tsb"]) if point.get("tsb") is not None else None
        results.append(ReadinessHistoryPoint(
            date_iso=point["date_iso"],
            drs=report.drs,
            recovery_score=point.get("recovery_score"),
            mental_score=point.get("mental_score"),
            trs=point.get("trs"),
            form_score=form,
            label=report.drs_label,
            color=report.drs_color,
        ))
    return sorted(results, key=lambda p: p.date_iso)


# ─────────────────────────────────────────────────────────────────────────────
# Data fetch helpers — leen las 4 dimensiones desde la DB para un usuario
# (compartido entre readiness_routes.py y el pipeline de sync de Garmin,
# para que el DRS se calcule igual en ambos lugares).
# ─────────────────────────────────────────────────────────────────────────────

def get_recovery_score(user_id: str, db: "Session") -> Optional[float]:
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
        return None


def get_mental_score(user_id: str, db: "Session") -> Optional[float]:
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


def get_trs(user_id: str, db: "Session") -> Optional[float]:
    """Calcula TRS del último examen de blood labs (últimos 90 días)."""
    cutoff = (date.today() - timedelta(days=90)).isoformat()
    try:
        from ..models import BloodLabExam, User
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


def get_tsb(user_id: str, db: "Session") -> Optional[float]:
    """Lee el TSB más reciente de GarminTrainingLoad."""
    try:
        from ..models import GarminTrainingLoad
        load = (
            db.query(GarminTrainingLoad)
            .filter(GarminTrainingLoad.user_id == user_id)
            .order_by(GarminTrainingLoad.date_iso.desc())
            .first()
        )
        return float(load.tsb) if load and load.tsb is not None else None
    except Exception:
        return None


def compute_daily_readiness_for_user(user_id: str, db: "Session") -> DailyReadinessReport:
    """Atajo: lee las 4 dimensiones de la DB y computa el DRS del día."""
    return compute_daily_readiness(
        recovery_score=get_recovery_score(user_id, db),
        mental_score=get_mental_score(user_id, db),
        trs=get_trs(user_id, db),
        tsb=get_tsb(user_id, db),
    )
